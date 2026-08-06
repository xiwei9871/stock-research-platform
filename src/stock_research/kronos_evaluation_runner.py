"""Resumable orchestration for frozen Kronos rolling-evaluation experiments.

This module deliberately keeps the research experiment on the filesystem.  It
never writes the production Kronos cache and, after preparation, prediction
and reporting read only the frozen experiment directory.
"""

from __future__ import annotations

import csv
import inspect
import json
import math
import os
import subprocess
import tempfile
import time
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, fields
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from stock_research.kronos_evaluation_client import KronosClient

from stock_research.kronos_evaluation_metrics import (
    aggregate_metrics,
    build_baselines,
    compare_models,
    score_forecast,
)
from stock_research.kronos_evaluation_types import (
    KronosEvaluationConfig,
    RollingSnapshot,
    canonical_json_fingerprint,
    snapshot_to_json_payload,
    thaw_json_value,
)


EXPERIMENT_FILENAME = "experiment.json"
UNIVERSE_FILENAME = "universe.csv"
SNAPSHOT_DIRECTORY = "input_snapshots"
MANIFEST_FILENAME = "run_manifest.csv"
FORECAST_FILENAME = "forecast_bars.parquet"
REALIZED_FILENAME = "realized_bars.parquet"
METRICS_BY_STOCK_FILENAME = "metrics_by_stock_horizon.csv"
METRICS_BY_MODEL_FILENAME = "metrics_by_model_horizon.csv"
MODEL_COMPARISON_FILENAME = "model_comparison.csv"
REPORT_FILENAME = "report.md"

_SUCCESS_RESPONSE_STATUSES = frozenset(
    {"ok", "partial", "complete", "completed", "success", "succeeded"}
)
_FAILURE_RESPONSE_STATUSES = frozenset(
    {"error", "failed", "model_error", "unavailable", "timeout"}
)
_SUCCESS_MANIFEST_STATUS = "success"
_CONCLUSIONS = frozenset(
    {"small_preferred", "base_preferred", "no_clear_winner", "not_proven"}
)

MANIFEST_COLUMNS = (
    "run_key",
    "snapshot_key",
    "asset_id",
    "origin_date",
    "model",
    "status",
    "reason",
    "error_category",
    "error_code",
    "input_fingerprint",
    "model_identity",
    "weights_identity",
    "parameters_json",
    "sample_count",
    "seed",
    "started_at",
    "finished_at",
    "latency_ms",
    "health_metadata_json",
    "raw_response_json",
    "raw_body_excerpt",
    "forecast_artifact",
    "realized_artifact",
    "forecast_row_count",
    "realized_row_count",
    "cache_hit",
)

FORECAST_COLUMNS = (
    "asset_id",
    "origin_date",
    "model",
    "run_key",
    "input_fingerprint",
    "timestamp",
    "horizon",
    "p10",
    "p50",
    "p90",
    "sample_count",
    "seed",
    "status",
    "model_identity",
    "weights_identity",
    "device",
    "cuda",
)

REALIZED_COLUMNS = (
    "asset_id",
    "origin_date",
    "model",
    "run_key",
    "input_fingerprint",
    "timestamp",
    "horizon",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "amount",
    "sample_count",
    "seed",
    "status",
    "model_identity",
    "weights_identity",
    "device",
    "cuda",
)

_METRIC_OUTPUT_COLUMNS = (
    "asset_id",
    "model",
    "horizon",
    "row_count",
    "total_count",
    "success_count",
    "failed_count",
    "missing_count",
    "excluded_count",
    "metric_count",
    "mean_actual_return",
    "mean_predicted_return",
    "mean_absolute_return_error",
    "mean_normalized_price_error",
    "mean_direction_hit",
    "mean_interval_coverage",
    "mean_interval_width",
    "mean_pinball_loss_p10",
    "mean_pinball_loss_p50",
    "mean_pinball_loss_p90",
    "direction_hit_count",
    "direction_hit_rate",
    "coverage_count",
    "coverage_denominator",
    "coverage_rate",
    "status_counts_json",
    "metric_denominators_json",
)

_COMPARISON_OUTPUT_COLUMNS = (
    "comparison",
    "metric",
    "left_model",
    "right_model",
    "delta_orientation",
    "status",
    "paired_count",
    "paired_row_count",
    "excluded_count",
    "delta_mean",
    "ci_low",
    "ci_high",
    "ci_method",
    "seed",
    "bootstrap_samples",
)

SnapshotLoader = Callable[
    [KronosEvaluationConfig],
    tuple[Sequence[RollingSnapshot], Mapping[str, Any]]
    | Sequence[RollingSnapshot],
]


@dataclass(frozen=True)
class SnapshotLoadResult:
    """Dependency-injection result for deterministic preparation tests."""

    snapshots: tuple[RollingSnapshot, ...]
    source_metadata: Mapping[str, Any]


@dataclass(frozen=True)
class PreparationResult:
    output_dir: Path
    experiment_path: Path
    universe_path: Path
    snapshot_paths: tuple[Path, ...]
    manifest_path: Path
    forecast_path: Path
    realized_path: Path
    snapshot_count: int
    snapshot_fingerprints: tuple[str, ...]
    status_counts: Mapping[str, int]


@dataclass(frozen=True)
class ModelRunResult:
    output_dir: Path
    model: str
    manifest_path: Path
    forecast_path: Path
    realized_path: Path
    attempted_count: int
    cache_hit_count: int
    skipped_count: int
    status_counts: Mapping[str, int]


class _RunnerFailure(RuntimeError):
    def __init__(
        self,
        reason: str,
        *,
        status: str,
        category: str,
        code: str,
        raw_response: Mapping[str, Any] | None = None,
        raw_body_excerpt: str | None = None,
    ) -> None:
        super().__init__(reason)
        self.status = status
        self.category = category
        self.code = code
        self.raw_response = _jsonable(raw_response) if raw_response is not None else None
        self.raw_body_excerpt = raw_body_excerpt


def prepare_experiment(
    config: KronosEvaluationConfig,
    *,
    output_dir: Path,
    snapshot_loader: SnapshotLoader | None = None,
) -> PreparationResult:
    """Freeze an experiment's inputs and initialize its research artifacts.

    ``snapshot_loader`` is intentionally injectable so unit tests can provide
    deterministic snapshots without touching PostgreSQL.  A prepared
    directory is immutable by default: a compatible existing directory is
    returned as-is, while a different configuration is rejected.
    """

    _require_config(config)
    normalized_output_dir = Path(output_dir)
    experiment_path = normalized_output_dir / EXPERIMENT_FILENAME

    if experiment_path.exists():
        metadata = _read_json(experiment_path)
        _validate_existing_experiment_config(metadata, config)
        return _existing_preparation_result(normalized_output_dir, metadata)

    normalized_output_dir.mkdir(parents=True, exist_ok=True)
    loaded = (
        _default_snapshot_loader(config)
        if snapshot_loader is None
        else _invoke_snapshot_loader(snapshot_loader, config)
    )
    snapshots, source_metadata = _normalize_loader_result(loaded)
    snapshots = _validate_prepared_snapshots(config, snapshots)
    source_payload = _jsonable(dict(source_metadata))

    metadata = _build_experiment_metadata(config, snapshots, source_payload)
    snapshot_dir = normalized_output_dir / SNAPSHOT_DIRECTORY
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    snapshot_paths: list[Path] = []
    for snapshot in snapshots:
        path = snapshot_dir / _snapshot_filename(snapshot)
        _atomic_write_json(path, snapshot_to_json_payload(snapshot))
        snapshot_paths.append(path)

    _atomic_write_csv(
        normalized_output_dir / UNIVERSE_FILENAME,
        [
            {"asset_id": asset_id, "position": position}
            for position, asset_id in enumerate(config.asset_ids, start=1)
        ],
        ("asset_id", "position"),
    )

    manifest_rows = [
        _initial_manifest_row(snapshot, model, config)
        for snapshot in snapshots
        for model in config.models
    ]
    _atomic_write_csv(
        normalized_output_dir / MANIFEST_FILENAME,
        manifest_rows,
        MANIFEST_COLUMNS,
    )
    _atomic_write_table(
        normalized_output_dir / FORECAST_FILENAME,
        [],
        FORECAST_COLUMNS,
    )
    _atomic_write_table(
        normalized_output_dir / REALIZED_FILENAME,
        [],
        REALIZED_COLUMNS,
    )
    _atomic_write_json(experiment_path, metadata)

    return _preparation_result_from_paths(
        normalized_output_dir,
        snapshots,
        snapshot_paths=snapshot_paths,
        metadata=metadata,
    )


def run_model(
    config: KronosEvaluationConfig,
    *,
    model: str,
    output_dir: Path,
    client: KronosClient,
) -> ModelRunResult:
    """Run one requested model over only the prepared snapshot files.

    Each snapshot/model unit is persisted independently.  A completed row is
    reused only when all cache identity fields still match; a changed model or
    input identity removes the old artifact rows before replacement.
    """

    _require_config(config)
    normalized_model = _normalize_model(model)
    if normalized_model not in config.models:
        raise ValueError(f"model {normalized_model!r} is not enabled in config.models")
    normalized_output_dir = Path(output_dir)
    metadata = _read_json(normalized_output_dir / EXPERIMENT_FILENAME)
    _validate_existing_experiment_config(metadata, config)
    snapshots = _read_frozen_snapshots(normalized_output_dir)
    if not snapshots:
        raise ValueError("prepared experiment has no input snapshots")

    manifest = _load_manifest(normalized_output_dir / MANIFEST_FILENAME)
    manifest = _ensure_manifest_rows(manifest, snapshots, config)
    forecast_rows = _read_table(normalized_output_dir / FORECAST_FILENAME)
    realized_rows = _read_table(normalized_output_dir / REALIZED_FILENAME)
    parameters_by_key = {
        snapshot.key: _prediction_parameters(config, snapshot)
        for snapshot in snapshots
    }

    health: Mapping[str, Any] = {}
    health_failure: _RunnerFailure | None = None
    try:
        health = _load_health_metadata(client, normalized_model)
    except _RunnerFailure as exc:
        health_failure = exc
    except Exception as exc:  # noqa: BLE001 - runner must record service failures.
        health_failure = _failure_from_exception(exc, health_check=True)

    attempted_count = 0
    cache_hit_count = 0
    skipped_count = 0

    for snapshot in snapshots:
        run_key = f"{snapshot.key}|{normalized_model}"
        row = manifest[run_key]
        parameters = parameters_by_key[snapshot.key]

        if snapshot.status != "ready":
            skipped_count += 1
            row.update(
                {
                    "status": snapshot.status,
                    "reason": snapshot.reason or "snapshot is not ready",
                    "input_fingerprint": snapshot.input_fingerprint,
                    "model": normalized_model,
                    "cache_hit": False,
                }
            )
            _write_run_artifacts(normalized_output_dir, manifest, forecast_rows, realized_rows)
            continue

        if health_failure is None and _manifest_cache_matches(
            row,
            snapshot,
            normalized_model,
            parameters,
            health,
            forecast_rows,
            realized_rows,
        ):
            cache_hit_count += 1
            row.update(
                {
                    "cache_hit": True,
                    "reason": "cache_hit",
                    "finished_at": _now_iso(),
                }
            )
            _write_run_artifacts(normalized_output_dir, manifest, forecast_rows, realized_rows)
            continue

        attempted_count += 1
        forecast_rows = [item for item in forecast_rows if item.get("run_key") != run_key]
        realized_rows = [item for item in realized_rows if item.get("run_key") != run_key]
        started_at = _now_iso()
        start_clock = time.perf_counter()
        row.update(
            _attempt_row_update(
                snapshot,
                normalized_model,
                parameters,
                health,
                started_at=started_at,
            )
        )
        _write_run_artifacts(normalized_output_dir, manifest, forecast_rows, realized_rows)

        failure: _RunnerFailure | None = health_failure
        response: Mapping[str, Any] | None = None
        response_model_metadata: Mapping[str, Any] = {}
        new_forecast_rows: list[dict[str, Any]] = []
        new_realized_rows: list[dict[str, Any]] = []
        try:
            if failure is not None:
                raise failure
            response_value = client.predict_daily(
                snapshot,
                model=normalized_model,
                sample_count=config.sample_count,
                seed=config.seed,
            )
            if not isinstance(response_value, Mapping):
                raise _RunnerFailure(
                    "Kronos prediction response must be a JSON object",
                    status="protocol_error",
                    category="protocol",
                    code="invalid_response",
                )
            response = _jsonable(dict(response_value))
            response_model_metadata = _response_model_metadata(response)
            new_forecast_rows, new_realized_rows = _build_artifact_rows(
                snapshot,
                normalized_model,
                config,
                response,
                health,
                response_model_metadata,
            )
        except _RunnerFailure as exc:
            failure = exc
        except Exception as exc:  # noqa: BLE001 - malformed runs are manifest data.
            failure = _failure_from_exception(exc)
            if hasattr(exc, "raw_response") and getattr(exc, "raw_response"):
                response = _jsonable(getattr(exc, "raw_response"))
            row["reason"] = str(exc)

        latency_ms = _elapsed_milliseconds(start_clock)
        finished_at = _now_iso()
        if failure is None:
            forecast_rows.extend(new_forecast_rows)
            realized_rows.extend(new_realized_rows)
            row.update(
                {
                    "status": _SUCCESS_MANIFEST_STATUS,
                    "reason": "",
                    "error_category": "",
                    "error_code": "",
                    "model_identity": _first_identity(
                        response_model_metadata, health, normalized_model
                    ),
                    "weights_identity": _first_weight_identity(
                        response_model_metadata, health
                    ),
                    "finished_at": finished_at,
                    "latency_ms": latency_ms,
                    "raw_response_json": _canonical_json(
                        _raw_response_for_manifest(response)
                    ),
                    "raw_body_excerpt": "",
                    "forecast_artifact": FORECAST_FILENAME,
                    "realized_artifact": REALIZED_FILENAME,
                    "forecast_row_count": len(new_forecast_rows),
                    "realized_row_count": len(new_realized_rows),
                    "cache_hit": False,
                }
            )
        else:
            row.update(
                {
                    "status": failure.status,
                    "reason": str(failure),
                    "error_category": failure.category,
                    "error_code": failure.code,
                    "model_identity": _first_identity(
                        response_model_metadata, health, normalized_model
                    ),
                    "weights_identity": _first_weight_identity(
                        response_model_metadata, health
                    ),
                    "finished_at": finished_at,
                    "latency_ms": latency_ms,
                    "raw_response_json": _canonical_json(
                        _raw_response_for_manifest(
                            response if response is not None else failure.raw_response
                        )
                    ),
                    "raw_body_excerpt": failure.raw_body_excerpt or "",
                    "forecast_artifact": "",
                    "realized_artifact": "",
                    "forecast_row_count": 0,
                    "realized_row_count": 0,
                    "cache_hit": False,
                }
            )
        _write_run_artifacts(normalized_output_dir, manifest, forecast_rows, realized_rows)

    _write_run_artifacts(normalized_output_dir, manifest, forecast_rows, realized_rows)
    status_counts = Counter(
        row.get("status", "")
        for row in manifest.values()
        if row.get("model") == normalized_model
    )
    return ModelRunResult(
        output_dir=normalized_output_dir,
        model=normalized_model,
        manifest_path=normalized_output_dir / MANIFEST_FILENAME,
        forecast_path=normalized_output_dir / FORECAST_FILENAME,
        realized_path=normalized_output_dir / REALIZED_FILENAME,
        attempted_count=attempted_count,
        cache_hit_count=cache_hit_count,
        skipped_count=skipped_count,
        status_counts=dict(sorted(status_counts.items())),
    )


def build_report(*, output_dir: Path) -> dict[str, Any]:
    """Build all report artifacts using only the prepared experiment files."""

    normalized_output_dir = Path(output_dir)
    metadata = _read_json(normalized_output_dir / EXPERIMENT_FILENAME)
    snapshots = _read_frozen_snapshots(normalized_output_dir)
    manifest = {
        str(row.get("run_key", "")): row
        for row in _load_manifest(normalized_output_dir / MANIFEST_FILENAME)
        if row.get("run_key")
    }
    forecast_rows = _read_table(normalized_output_dir / FORECAST_FILENAME)
    realized_rows = _read_table(normalized_output_dir / REALIZED_FILENAME)

    config_payload = metadata.get("config")
    if not isinstance(config_payload, Mapping):
        raise ValueError("experiment.json is missing config metadata")
    horizons = _integer_sequence(config_payload.get("evaluation_horizons"), "evaluation_horizons")
    raw_seed = config_payload.get("seed")
    seed = int(raw_seed) if isinstance(raw_seed, int) and not isinstance(raw_seed, bool) else None

    metric_rows = _build_metric_rows(
        snapshots,
        manifest,
        forecast_rows,
        realized_rows,
        horizons,
        config_payload,
    )
    stock_summaries = aggregate_metrics(
        metric_rows,
        group_by=("asset_id", "model", "horizon"),
    )
    model_summaries = aggregate_metrics(
        metric_rows,
        group_by=("model", "horizon"),
    )
    stock_output = [_metric_summary_row(row) for row in stock_summaries]
    model_output = [_metric_summary_row(row) for row in model_summaries]
    _atomic_write_csv(
        normalized_output_dir / METRICS_BY_STOCK_FILENAME,
        stock_output,
        _METRIC_OUTPUT_COLUMNS,
    )
    _atomic_write_csv(
        normalized_output_dir / METRICS_BY_MODEL_FILENAME,
        model_output,
        _METRIC_OUTPUT_COLUMNS,
    )

    comparisons = _build_comparisons(metric_rows, seed=seed)
    _atomic_write_csv(
        normalized_output_dir / MODEL_COMPARISON_FILENAME,
        comparisons,
        _COMPARISON_OUTPUT_COLUMNS,
    )

    status_counts = Counter(row.get("status", "") for row in manifest.values())
    model_status_counts: dict[str, dict[str, int]] = defaultdict(lambda: Counter())
    for row in manifest.values():
        model_status_counts[row.get("model", "")] [row.get("status", "")] += 1
    model_status_counts = {
        model: dict(sorted(counts.items()))
        for model, counts in sorted(model_status_counts.items())
    }
    coverage = _coverage_by_model_horizon(manifest, forecast_rows, horizons)
    latency = _latency_summary(manifest)
    model_metadata = _model_metadata_summary(manifest)
    conclusion = _choose_conclusion(
        comparisons,
        model_summaries,
        metric_rows,
    )
    if conclusion not in _CONCLUSIONS:  # pragma: no cover - defensive invariant.
        raise ValueError(f"unsupported conclusion {conclusion!r}")

    report_text = _render_report(
        metadata=metadata,
        conclusion=conclusion,
        status_counts=dict(sorted(status_counts.items())),
        model_status_counts=model_status_counts,
        coverage=coverage,
        model_summaries=model_output,
        comparisons=comparisons,
        latency=latency,
        model_metadata=model_metadata,
    )
    _atomic_write_text(normalized_output_dir / REPORT_FILENAME, report_text)

    counts = {
        "snapshots": len(snapshots),
        "runs": len(manifest),
        "successful_runs": sum(
            1 for row in manifest.values() if row.get("status") == _SUCCESS_MANIFEST_STATUS
        ),
        "failed_runs": sum(
            1
            for row in manifest.values()
            if row.get("status")
            in {"model_error", "timeout", "transport_error", "protocol_error", "unavailable"}
        ),
        "forecast_rows": len(forecast_rows),
        "realized_rows": len(realized_rows),
        "metric_rows": len(metric_rows),
    }
    paths = {
        "metrics_by_stock_horizon": str(normalized_output_dir / METRICS_BY_STOCK_FILENAME),
        "metrics_by_model_horizon": str(normalized_output_dir / METRICS_BY_MODEL_FILENAME),
        "model_comparison": str(normalized_output_dir / MODEL_COMPARISON_FILENAME),
        "report": str(normalized_output_dir / REPORT_FILENAME),
    }
    return {
        "output_dir": str(normalized_output_dir),
        "paths": paths,
        "counts": counts,
        "conclusion": conclusion,
        "status_counts": dict(sorted(status_counts.items())),
        "model_status_counts": model_status_counts,
        "coverage_by_model_horizon": coverage,
        "latency": latency,
        "model_metadata": model_metadata,
        "comparisons": comparisons,
    }


def _default_snapshot_loader(
    config: KronosEvaluationConfig,
) -> tuple[Sequence[RollingSnapshot], Mapping[str, Any]]:
    """Load Task 2 data through a bounded truth window and freeze snapshots."""

    # Task 2 uses the global trading calendar.  A conservative calendar-day
    # extension ensures the last requested origin can see its future truth
    # without querying any live endpoint during prediction/reporting.
    max_date = (
        date.fromisoformat(config.end_date)
        + timedelta(days=max(14, config.forecast_horizon * 4))
    ).isoformat()
    from stock_research import kronos_evaluation_data as data

    frame = data.load_daily_bars(
        config.asset_ids,
        max_date,
        config.adjust_type,
        config.db_service,
    )
    trade_dates = data.load_global_trade_dates(
        config.adjust_type,
        config.start_date,
        max_date,
        config.db_service,
    )
    origin_dates = [
        timestamp
        for timestamp in trade_dates
        if config.start_date <= timestamp <= config.end_date
    ][:: config.roll_step]
    if not origin_dates:
        raise ValueError("evaluation period has no trading-day origins")
    snapshots = data.build_rolling_snapshots(
        frame,
        trade_dates,
        config.input_window,
        config.forecast_horizon,
        origin_dates=origin_dates,
        asset_ids=config.asset_ids,
    )
    return snapshots, data.build_source_metadata(frame, adjust_type=config.adjust_type)


def _invoke_snapshot_loader(loader: SnapshotLoader, config: KronosEvaluationConfig) -> Any:
    try:
        signature = inspect.signature(loader)
    except (TypeError, ValueError):
        return loader(config)
    parameters = tuple(signature.parameters.values())
    if not parameters:
        return loader()  # type: ignore[call-arg]
    return loader(config)


def _normalize_loader_result(
    loaded: Any,
) -> tuple[tuple[RollingSnapshot, ...], Mapping[str, Any]]:
    if isinstance(loaded, SnapshotLoadResult):
        snapshots = loaded.snapshots
        source_metadata = loaded.source_metadata
    elif (
        isinstance(loaded, tuple)
        and len(loaded) == 2
        and isinstance(loaded[1], Mapping)
    ):
        snapshots, source_metadata = loaded
    else:
        snapshots, source_metadata = loaded, {}
    if isinstance(snapshots, (str, bytes)):
        raise ValueError("snapshot loader must return RollingSnapshot values")
    try:
        normalized_snapshots = tuple(snapshots)
    except TypeError as exc:
        raise ValueError("snapshot loader must return an iterable") from exc
    if not isinstance(source_metadata, Mapping):
        raise ValueError("snapshot loader source metadata must be a mapping")
    return normalized_snapshots, source_metadata


def _validate_prepared_snapshots(
    config: KronosEvaluationConfig,
    snapshots: Sequence[RollingSnapshot],
) -> tuple[RollingSnapshot, ...]:
    if not snapshots:
        raise ValueError("snapshot loader returned no snapshots")
    normalized = sorted(snapshots, key=lambda snapshot: snapshot.key)
    seen_keys: set[str] = set()
    for snapshot in normalized:
        if not isinstance(snapshot, RollingSnapshot):
            raise ValueError("snapshot loader must return RollingSnapshot values")
        if snapshot.asset_id not in config.asset_ids:
            raise ValueError(f"snapshot asset {snapshot.asset_id!r} is outside config universe")
        if not config.start_date <= snapshot.origin_date <= config.end_date:
            raise ValueError(f"snapshot origin {snapshot.origin_date!r} is outside config dates")
        if snapshot.key in seen_keys:
            raise ValueError(f"duplicate snapshot key {snapshot.key}")
        seen_keys.add(snapshot.key)
        expected_fingerprint = canonical_json_fingerprint(
            {
                "asset_id": snapshot.asset_id,
                "origin_date": snapshot.origin_date,
                "history": thaw_json_value(snapshot.history),
            }
        )
        if snapshot.input_fingerprint != expected_fingerprint:
            raise ValueError(f"snapshot {snapshot.key} has an invalid input fingerprint")
    return tuple(normalized)


def _build_experiment_metadata(
    config: KronosEvaluationConfig,
    snapshots: Sequence[RollingSnapshot],
    source_metadata: Mapping[str, Any],
) -> dict[str, Any]:
    source_payload = _jsonable(dict(source_metadata))
    immutable = {
        "schema_version": 1,
        "config": _config_payload(config),
        "universe": list(config.asset_ids),
        "source": source_payload,
        "source_metadata": source_payload,
        "code_revision": _code_revision(),
        "snapshot_count": len(snapshots),
        "snapshot_fingerprints": [
            {
                "key": snapshot.key,
                "asset_id": snapshot.asset_id,
                "origin_date": snapshot.origin_date,
                "status": snapshot.status,
                "input_fingerprint": snapshot.input_fingerprint,
            }
            for snapshot in snapshots
        ],
    }
    metadata = dict(immutable)
    metadata["created_at"] = _now_iso()
    metadata["experiment_fingerprint"] = canonical_json_fingerprint(immutable)
    return metadata


def _validate_existing_experiment_config(
    metadata: Mapping[str, Any],
    config: KronosEvaluationConfig,
) -> None:
    existing_config = metadata.get("config")
    expected_config = _config_payload(config)
    if _jsonable(existing_config) != expected_config:
        raise FileExistsError(
            "prepared experiment metadata is incompatible with the requested config"
        )
    if _jsonable(metadata.get("universe")) != list(config.asset_ids):
        raise FileExistsError("prepared experiment universe is incompatible")


def _existing_preparation_result(
    output_dir: Path,
    metadata: Mapping[str, Any],
) -> PreparationResult:
    required = (
        output_dir / UNIVERSE_FILENAME,
        output_dir / MANIFEST_FILENAME,
        output_dir / FORECAST_FILENAME,
        output_dir / REALIZED_FILENAME,
    )
    missing = [str(path) for path in required if not path.exists()]
    snapshot_dir = output_dir / SNAPSHOT_DIRECTORY
    if not snapshot_dir.exists():
        missing.append(str(snapshot_dir))
    if missing:
        raise FileNotFoundError("prepared experiment is incomplete: " + ", ".join(missing))
    snapshot_paths = tuple(sorted(snapshot_dir.glob("*.json"), key=lambda path: path.name))
    frozen_snapshots = _read_frozen_snapshots(output_dir)
    metadata_fingerprints = {
        str(item.get("key")): (
            item.get("input_fingerprint"),
            item.get("status"),
        )
        for item in metadata.get("snapshot_fingerprints", [])
        if isinstance(item, Mapping)
    }
    actual_fingerprints = {
        snapshot.key: (snapshot.input_fingerprint, snapshot.status)
        for snapshot in frozen_snapshots
    }
    if metadata_fingerprints != actual_fingerprints:
        raise FileExistsError("prepared experiment snapshot metadata is incompatible")
    fingerprints = tuple(
        item.get("input_fingerprint", "")
        for item in metadata.get("snapshot_fingerprints", [])
        if isinstance(item, Mapping)
    )
    status_counts = Counter(
        item.get("status", "")
        for item in metadata.get("snapshot_fingerprints", [])
        if isinstance(item, Mapping)
    )
    return PreparationResult(
        output_dir=output_dir,
        experiment_path=output_dir / EXPERIMENT_FILENAME,
        universe_path=output_dir / UNIVERSE_FILENAME,
        snapshot_paths=snapshot_paths,
        manifest_path=output_dir / MANIFEST_FILENAME,
        forecast_path=output_dir / FORECAST_FILENAME,
        realized_path=output_dir / REALIZED_FILENAME,
        snapshot_count=int(metadata.get("snapshot_count", len(snapshot_paths))),
        snapshot_fingerprints=fingerprints,
        status_counts=dict(sorted(status_counts.items())),
    )


def _preparation_result_from_paths(
    output_dir: Path,
    snapshots: Sequence[RollingSnapshot],
    *,
    snapshot_paths: Sequence[Path],
    metadata: Mapping[str, Any],
) -> PreparationResult:
    status_counts = Counter(snapshot.status for snapshot in snapshots)
    return PreparationResult(
        output_dir=output_dir,
        experiment_path=output_dir / EXPERIMENT_FILENAME,
        universe_path=output_dir / UNIVERSE_FILENAME,
        snapshot_paths=tuple(snapshot_paths),
        manifest_path=output_dir / MANIFEST_FILENAME,
        forecast_path=output_dir / FORECAST_FILENAME,
        realized_path=output_dir / REALIZED_FILENAME,
        snapshot_count=len(snapshots),
        snapshot_fingerprints=tuple(
            item["input_fingerprint"]
            for item in metadata["snapshot_fingerprints"]
        ),
        status_counts=dict(sorted(status_counts.items())),
    )


def _read_frozen_snapshots(output_dir: Path) -> tuple[RollingSnapshot, ...]:
    snapshot_dir = output_dir / SNAPSHOT_DIRECTORY
    paths = sorted(snapshot_dir.glob("*.json"), key=lambda path: path.name)
    snapshots: list[RollingSnapshot] = []
    for path in paths:
        payload = _read_json(path)
        try:
            snapshot = RollingSnapshot(
                asset_id=payload["asset_id"],
                origin_date=payload["origin_date"],
                history=payload["history"],
                future_timestamps=payload["future_timestamps"],
                realized=payload.get("realized", []),
                input_fingerprint=payload["input_fingerprint"],
                status=payload["status"],
                reason=payload.get("reason"),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"invalid frozen snapshot {path.name}: {exc}") from exc
        expected_fingerprint = canonical_json_fingerprint(
            {
                "asset_id": snapshot.asset_id,
                "origin_date": snapshot.origin_date,
                "history": thaw_json_value(snapshot.history),
            }
        )
        if snapshot.input_fingerprint != expected_fingerprint:
            raise ValueError(f"frozen snapshot {path.name} has an invalid fingerprint")
        snapshots.append(snapshot)
    return tuple(snapshots)


def _snapshot_filename(snapshot: RollingSnapshot) -> str:
    return f"{snapshot.asset_id}__{snapshot.origin_date}.json"


def _initial_manifest_row(
    snapshot: RollingSnapshot,
    model: str,
    config: KronosEvaluationConfig,
) -> dict[str, Any]:
    return {
        "run_key": f"{snapshot.key}|{model}",
        "snapshot_key": snapshot.key,
        "asset_id": snapshot.asset_id,
        "origin_date": snapshot.origin_date,
        "model": model,
        "status": snapshot.status if snapshot.status != "ready" else "pending",
        "reason": snapshot.reason or "",
        "error_category": "",
        "error_code": "",
        "input_fingerprint": snapshot.input_fingerprint,
        "model_identity": "",
        "weights_identity": "",
        "parameters_json": _canonical_json(_prediction_parameters(config, snapshot)),
        "sample_count": config.sample_count,
        "seed": config.seed,
        "started_at": "",
        "finished_at": "",
        "latency_ms": "",
        "health_metadata_json": "",
        "raw_response_json": "",
        "raw_body_excerpt": "",
        "forecast_artifact": "",
        "realized_artifact": "",
        "forecast_row_count": 0,
        "realized_row_count": 0,
        "cache_hit": False,
    }


def _prediction_parameters(
    config: KronosEvaluationConfig,
    snapshot: RollingSnapshot,
) -> dict[str, Any]:
    return {
        "input_window": config.input_window,
        "forecast_horizon": len(snapshot.future_timestamps),
        "adjust_type": config.adjust_type,
        "sample_count": config.sample_count,
        "seed": config.seed,
    }


def _load_health_metadata(client: Any, model: str) -> Mapping[str, Any]:
    health_method = getattr(client, "health", None)
    if callable(health_method):
        value = health_method()
    else:
        assert_method = getattr(client, "assert_model", None)
        value = assert_method(model) if callable(assert_method) else {}
    if value is None:
        value = {}
    if not isinstance(value, Mapping):
        raise _RunnerFailure(
            "Kronos health metadata must be a JSON object",
            status="protocol_error",
            category="protocol",
            code="invalid_health_response",
        )
    health = _jsonable(dict(value))
    reported_model = health.get("model")
    if reported_model is not None and _normalize_model_alias(reported_model) != model:
        raise _RunnerFailure(
            "Kronos health model does not match the requested model",
            status="unavailable",
            category="model",
            code="model_mismatch",
            raw_response=health,
        )
    status = health.get("status")
    if status is not None and str(status).lower() not in {"ok", "ready", "succeeded"}:
        raise _RunnerFailure(
            "Kronos health status is not ready",
            status="unavailable",
            category="transport",
            code="service_unavailable",
            raw_response=health,
        )
    return health


def _attempt_row_update(
    snapshot: RollingSnapshot,
    model: str,
    parameters: Mapping[str, Any],
    health: Mapping[str, Any],
    *,
    started_at: str,
) -> dict[str, Any]:
    return {
        "run_key": f"{snapshot.key}|{model}",
        "snapshot_key": snapshot.key,
        "asset_id": snapshot.asset_id,
        "origin_date": snapshot.origin_date,
        "model": model,
        "status": "running",
        "reason": "",
        "error_category": "",
        "error_code": "",
        "input_fingerprint": snapshot.input_fingerprint,
        "model_identity": _first_identity({}, health, model) or "",
        "weights_identity": _first_weight_identity({}, health) or "",
        "parameters_json": _canonical_json(parameters),
        "sample_count": parameters.get("sample_count", ""),
        "seed": parameters.get("seed"),
        "started_at": started_at,
        "finished_at": "",
        "latency_ms": "",
        "health_metadata_json": _canonical_json(health),
        "raw_response_json": "",
        "raw_body_excerpt": "",
        "forecast_artifact": "",
        "realized_artifact": "",
        "forecast_row_count": 0,
        "realized_row_count": 0,
        "cache_hit": False,
    }


def _manifest_cache_matches(
    row: Mapping[str, Any],
    snapshot: RollingSnapshot,
    model: str,
    parameters: Mapping[str, Any],
    health: Mapping[str, Any],
    forecast_rows: Sequence[Mapping[str, Any]],
    realized_rows: Sequence[Mapping[str, Any]],
) -> bool:
    if row.get("status") != _SUCCESS_MANIFEST_STATUS:
        return False
    if row.get("input_fingerprint") != snapshot.input_fingerprint:
        return False
    if row.get("model") != model:
        return False
    if _parse_json_cell(row.get("parameters_json")) != _jsonable(dict(parameters)):
        return False
    if _as_int(row.get("sample_count")) != int(parameters["sample_count"]):
        return False
    if _optional_int(row.get("seed")) != parameters.get("seed"):
        return False
    current_identity = _first_identity({}, health, model)
    current_weights = _first_weight_identity({}, health)
    if row.get("model_identity") or current_identity:
        if row.get("model_identity") != (current_identity or ""):
            return False
    if row.get("weights_identity") or current_weights:
        if row.get("weights_identity") != (current_weights or ""):
            return False
    run_key = f"{snapshot.key}|{model}"
    forecast_count = sum(1 for item in forecast_rows if item.get("run_key") == run_key)
    realized_count = sum(1 for item in realized_rows if item.get("run_key") == run_key)
    return forecast_count == len(snapshot.future_timestamps) and realized_count == len(
        snapshot.realized
    )


def _build_artifact_rows(
    snapshot: RollingSnapshot,
    model: str,
    config: KronosEvaluationConfig,
    response: Mapping[str, Any],
    health: Mapping[str, Any],
    response_model_metadata: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    response_status = str(response.get("status", "")).lower()
    raw_response = _raw_response_for_manifest(response)
    if response_status in _FAILURE_RESPONSE_STATUSES:
        category = _string_or_default(
            response.get("error_category")
            or _nested_error_value(response, "category"),
            "model",
        )
        code = _string_or_default(
            response.get("error_code") or _nested_error_value(response, "code"),
            "model_error",
        )
        raise _RunnerFailure(
            _response_reason(response, "Kronos prediction failed"),
            status="timeout" if response_status == "timeout" else "model_error",
            category=category,
            code=code,
            raw_response=raw_response,
        )
    if response_status not in _SUCCESS_RESPONSE_STATUSES:
        raise _RunnerFailure(
            "Kronos prediction response has an invalid status",
            status="protocol_error",
            category="protocol",
            code="invalid_response",
            raw_response=raw_response,
        )

    quantiles = _extract_quantiles(response)
    expected_length = len(snapshot.future_timestamps)
    values: dict[str, list[float]] = {}
    for name in ("p10", "p50", "p90"):
        candidate = quantiles.get(name)
        if not isinstance(candidate, (list, tuple)) or len(candidate) != expected_length:
            raise _RunnerFailure(
                f"Kronos prediction response {name} has invalid horizon",
                status="protocol_error",
                category="protocol",
                code="invalid_response",
                raw_response=raw_response,
            )
        normalized_values: list[float] = []
        for value in candidate:
            numeric = _finite_number(value)
            if numeric is None:
                raise _RunnerFailure(
                    f"Kronos prediction response {name} has invalid values",
                    status="protocol_error",
                    category="protocol",
                    code="invalid_response",
                    raw_response=raw_response,
                )
            normalized_values.append(numeric)
        values[name] = normalized_values
    for index, (p10, p50, p90) in enumerate(
        zip(values["p10"], values["p50"], values["p90"])
    ):
        if not p10 <= p50 <= p90:
            raise _RunnerFailure(
                f"Kronos prediction quantiles are not ordered at horizon {index + 1}",
                status="protocol_error",
                category="protocol",
                code="invalid_response",
                raw_response=raw_response,
            )

    identity = _first_identity(response_model_metadata, health, model)
    weights = _first_weight_identity(response_model_metadata, health)
    device = _first_value(response_model_metadata, health, "device", "gpu")
    cuda = _first_value(response_model_metadata, health, "cuda", "cuda_available")
    run_key = f"{snapshot.key}|{model}"
    forecast_rows = [
        {
            "asset_id": snapshot.asset_id,
            "origin_date": snapshot.origin_date,
            "model": model,
            "run_key": run_key,
            "input_fingerprint": snapshot.input_fingerprint,
            "timestamp": timestamp,
            "horizon": horizon,
            "p10": values["p10"][horizon - 1],
            "p50": values["p50"][horizon - 1],
            "p90": values["p90"][horizon - 1],
            "sample_count": config.sample_count,
            "seed": config.seed,
            "status": _SUCCESS_MANIFEST_STATUS,
            "model_identity": identity,
            "weights_identity": weights,
            "device": device,
            "cuda": cuda,
        }
        for horizon, timestamp in enumerate(snapshot.future_timestamps, start=1)
    ]
    realized_rows = []
    for horizon, source_row in enumerate(snapshot.realized, start=1):
        row = thaw_json_value(source_row)
        realized_rows.append(
            {
                "asset_id": snapshot.asset_id,
                "origin_date": snapshot.origin_date,
                "model": model,
                "run_key": run_key,
                "input_fingerprint": snapshot.input_fingerprint,
                "timestamp": row["timestamp"],
                "horizon": horizon,
                "open": row.get("open"),
                "high": row.get("high"),
                "low": row.get("low"),
                "close": row.get("close"),
                "volume": row.get("volume"),
                "amount": row.get("amount"),
                "sample_count": config.sample_count,
                "seed": config.seed,
                "status": _SUCCESS_MANIFEST_STATUS,
                "model_identity": identity,
                "weights_identity": weights,
                "device": device,
                "cuda": cuda,
            }
        )
    return forecast_rows, realized_rows


def _extract_quantiles(response: Mapping[str, Any]) -> Mapping[str, Any]:
    daily: Any = response.get("daily")
    result = response.get("result")
    if daily is None and isinstance(result, Mapping):
        daily = result.get("daily")
    if not isinstance(daily, Mapping):
        raise _RunnerFailure(
            "Kronos prediction response has no daily forecast",
            status="protocol_error",
            category="protocol",
            code="invalid_response",
            raw_response=_raw_response_for_manifest(response),
        )
    if all(name in daily for name in ("p10", "p50", "p90")):
        return daily
    summary = daily.get("summary")
    if isinstance(summary, Mapping):
        close = summary.get("close")
        if isinstance(close, Mapping):
            return close
    if isinstance(result, Mapping):
        result_summary = result.get("summary")
        if isinstance(result_summary, Mapping):
            close = result_summary.get("close")
            if isinstance(close, Mapping):
                return close
    raise _RunnerFailure(
        "Kronos prediction response has no supported daily quantiles",
        status="protocol_error",
        category="protocol",
        code="invalid_response",
        raw_response=_raw_response_for_manifest(response),
    )


def _response_model_metadata(response: Mapping[str, Any]) -> dict[str, Any]:
    raw = response.get("raw_response")
    metadata: dict[str, Any] = {}
    for source in (response, raw if isinstance(raw, Mapping) else {}):
        for key in (
            "model",
            "model_identity",
            "model_name",
            "weights",
            "weights_identity",
            "weights_fingerprint",
            "device",
            "cuda",
            "cuda_available",
        ):
            if key in source and key not in metadata:
                metadata[key] = source[key]
    return metadata


def _failure_from_exception(error: Exception, *, health_check: bool = False) -> _RunnerFailure:
    if isinstance(error, _RunnerFailure):
        return error
    try:
        from stock_research.kronos_evaluation_client import KronosClientError
    except ModuleNotFoundError:
        KronosClientError = None  # type: ignore[assignment]
    if KronosClientError is not None and isinstance(error, KronosClientError):
        return _failure_from_client_error(error)
    return _RunnerFailure(
        "Kronos health check failed" if health_check else "Kronos prediction attempt failed",
        status="unavailable" if health_check else "protocol_error",
        category="transport" if health_check else "protocol",
        code="health_check_error" if health_check else "runner_error",
    )


def _failure_from_client_error(error: Any) -> _RunnerFailure:
    category = str(error.category)
    if category == "model":
        status = "unavailable" if str(error.code) == "model_mismatch" else "model_error"
    elif category == "timeout":
        status = "timeout"
    elif category == "transport":
        status = "transport_error"
    elif category == "protocol":
        status = "protocol_error"
    else:
        status = "protocol_error"
    raw_response = error.raw_response if isinstance(error.raw_response, Mapping) else None
    return _RunnerFailure(
        str(error),
        status=status,
        category=category,
        code=str(error.code),
        raw_response=raw_response,
        raw_body_excerpt=error.raw_body_excerpt,
    )


def _build_metric_rows(
    snapshots: Sequence[RollingSnapshot],
    manifest: Mapping[str, Mapping[str, Any]],
    forecast_rows: Sequence[Mapping[str, Any]],
    realized_rows: Sequence[Mapping[str, Any]],
    horizons: Sequence[int],
    config_payload: Mapping[str, Any],
) -> list[dict[str, Any]]:
    by_forecast_key: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    by_realized_key: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in forecast_rows:
        by_forecast_key[str(row.get("run_key", ""))].append(row)
    for row in realized_rows:
        by_realized_key[str(row.get("run_key", ""))].append(row)
    metric_rows: list[dict[str, Any]] = []
    configured_models = tuple(
        str(model) for model in config_payload.get("models", ("small", "base"))
    )
    for snapshot in snapshots:
        for model in configured_models:
            run_key = f"{snapshot.key}|{model}"
            manifest_row = manifest.get(run_key, {})
            status = str(manifest_row.get("status", "missing"))
            forecast = sorted(
                by_forecast_key.get(run_key, []),
                key=lambda row: _as_int(row.get("horizon")) or 0,
            )
            realized = sorted(
                by_realized_key.get(run_key, []),
                key=lambda row: _as_int(row.get("horizon")) or 0,
            )
            scores: Mapping[str, Mapping[str, Any]] = {}
            if status == _SUCCESS_MANIFEST_STATUS:
                try:
                    scores = score_forecast(
                        _last_close(snapshot),
                        [_required_float(row.get("close"), "realized close") for row in realized],
                        [_required_float(row.get("p10"), "forecast p10") for row in forecast],
                        [_required_float(row.get("p50"), "forecast p50") for row in forecast],
                        [_required_float(row.get("p90"), "forecast p90") for row in forecast],
                        horizons=horizons,
                    )
                except (ValueError, TypeError):
                    status = "insufficient_artifact"
            for horizon in horizons:
                row: dict[str, Any] = {
                    "asset_id": snapshot.asset_id,
                    "origin_date": snapshot.origin_date,
                    "model": model,
                    "horizon": horizon,
                    "status": status,
                }
                if f"h{horizon}" in scores:
                    row.update(scores[f"h{horizon}"])
                metric_rows.append(row)

        if snapshot.status != "ready" or len(snapshot.realized) < max(horizons):
            continue
        try:
            history_closes = [
                _required_float(row.get("close"), "history close")
                for row in snapshot.history
            ]
            actual_closes = [
                _required_float(row.get("close"), "realized close")
                for row in snapshot.realized
            ]
            baseline_horizon = max(horizons)
            baselines = build_baselines(
                history_closes,
                horizon=baseline_horizon,
                drift_window=min(20, len(history_closes) - 1),
            )
            for baseline_name, forecast in baselines.items():
                scores = score_forecast(
                    history_closes[-1],
                    actual_closes,
                    forecast,
                    forecast,
                    forecast,
                    horizons=horizons,
                )
                for horizon in horizons:
                    metric_rows.append(
                        {
                            "asset_id": snapshot.asset_id,
                            "origin_date": snapshot.origin_date,
                            "model": baseline_name,
                            "horizon": horizon,
                            "status": _SUCCESS_MANIFEST_STATUS,
                            **scores[f"h{horizon}"],
                        }
                    )
        except (ValueError, TypeError):
            continue
    return metric_rows


def _build_comparisons(
    metric_rows: Sequence[Mapping[str, Any]],
    *,
    seed: int | None,
) -> list[dict[str, Any]]:
    comparison_rows: list[dict[str, Any]] = []
    model_names = sorted(
        {
            str(row.get("model"))
            for row in metric_rows
            if str(row.get("model")) in {"small", "base", "persistence", "drift"}
        }
    )
    pairs = (
        ("small", "base", "base_minus_small"),
        ("persistence", "small", "small_minus_persistence"),
        ("drift", "small", "small_minus_drift"),
        ("persistence", "base", "base_minus_persistence"),
        ("drift", "base", "base_minus_drift"),
    )
    if seed is None:
        for left, right, label in pairs:
            if left in model_names and right in model_names:
                comparison_rows.append(_empty_comparison(label, left, right, seed=None))
        return comparison_rows

    wide: dict[tuple[str, str, int], dict[str, Any]] = defaultdict(dict)
    for row in metric_rows:
        if row.get("status") != _SUCCESS_MANIFEST_STATUS:
            continue
        value = _finite_number(row.get("absolute_return_error"))
        if value is None:
            continue
        key = (
            str(row.get("asset_id")),
            str(row.get("origin_date")),
            int(row.get("horizon")),
        )
        wide[key][str(row.get("model"))] = value
    wide_rows = [
        {
            "asset_id": asset_id,
            "origin_date": origin_date,
            "horizon": horizon,
            **values,
        }
        for (asset_id, origin_date, horizon), values in sorted(wide.items())
    ]
    for left, right, label in pairs:
        if left not in model_names or right not in model_names:
            continue
        comparison = compare_models(wide_rows, left=left, right=right, seed=seed)
        comparison_rows.append(
            {
                "comparison": label,
                "metric": "absolute_return_error",
                "left_model": left,
                "right_model": right,
                "delta_orientation": comparison.get("delta_orientation", f"{right}_minus_{left}"),
                "status": comparison.get("status", "empty"),
                "paired_count": comparison.get("paired_count", 0),
                "paired_row_count": comparison.get("paired_row_count", 0),
                "excluded_count": comparison.get("excluded_count", 0),
                "delta_mean": comparison.get("delta_mean"),
                "ci_low": comparison.get("ci_low"),
                "ci_high": comparison.get("ci_high"),
                "ci_method": comparison.get("ci_method", "none"),
                "seed": comparison.get("seed"),
                "bootstrap_samples": comparison.get("bootstrap_samples"),
            }
        )
    return comparison_rows


def _empty_comparison(
    label: str,
    left: str,
    right: str,
    *,
    seed: int | None,
) -> dict[str, Any]:
    return {
        "comparison": label,
        "metric": "absolute_return_error",
        "left_model": left,
        "right_model": right,
        "delta_orientation": f"{right}_minus_{left}",
        "status": "seed_missing" if seed is None else "empty",
        "paired_count": 0,
        "paired_row_count": 0,
        "excluded_count": 0,
        "delta_mean": None,
        "ci_low": None,
        "ci_high": None,
        "ci_method": "none",
        "seed": seed,
        "bootstrap_samples": None,
    }


def _choose_conclusion(
    comparisons: Sequence[Mapping[str, Any]],
    model_summaries: Sequence[Mapping[str, Any]],
    metric_rows: Sequence[Mapping[str, Any]],
) -> str:
    by_label = {str(row.get("comparison")): row for row in comparisons}
    base_small = by_label.get("base_minus_small")
    if not base_small or _as_int(base_small.get("paired_count")) is None:
        return "not_proven"
    if (_as_int(base_small.get("paired_count")) or 0) < 2:
        return "not_proven"
    paired_assets_by_model: dict[str, set[str]] = defaultdict(set)
    for row in metric_rows:
        if (
            row.get("model") in {"small", "base"}
            and row.get("status") == _SUCCESS_MANIFEST_STATUS
            and _finite_number(row.get("absolute_return_error")) is not None
        ):
            paired_assets_by_model[str(row["model"])].add(str(row.get("asset_id")))
    paired_assets = paired_assets_by_model.get("small", set()) & paired_assets_by_model.get(
        "base", set()
    )
    if len(paired_assets) < 2:
        return "not_proven"

    small_baseline_proven = _baseline_proven(
        by_label.get("small_minus_persistence"),
        by_label.get("small_minus_drift"),
    )
    base_baseline_proven = _baseline_proven(
        by_label.get("base_minus_persistence"),
        by_label.get("base_minus_drift"),
    )
    coverage = _mean_coverage_by_model(model_summaries)
    small_coverage = coverage.get("small")
    base_coverage = coverage.get("base")
    delta_low = _finite_number(base_small.get("ci_low"))
    delta_high = _finite_number(base_small.get("ci_high"))
    if delta_low is None or delta_high is None:
        return "not_proven"
    if (
        base_baseline_proven
        and delta_high < 0
        and base_coverage is not None
        and small_coverage is not None
        and base_coverage >= small_coverage - 0.05
    ):
        return "base_preferred"
    if (
        small_baseline_proven
        and delta_low > 0
        and small_coverage is not None
        and base_coverage is not None
        and small_coverage >= base_coverage - 0.05
    ):
        return "small_preferred"
    if small_baseline_proven or base_baseline_proven:
        return "no_clear_winner"
    # Keep the explicit metric-row argument in the decision boundary so a
    # report with no usable model metric cannot accidentally become a winner.
    if not any(
        row.get("model") in {"small", "base"}
        and row.get("status") == _SUCCESS_MANIFEST_STATUS
        for row in metric_rows
    ):
        return "not_proven"
    return "not_proven"


def _baseline_proven(
    against_persistence: Mapping[str, Any] | None,
    against_drift: Mapping[str, Any] | None,
) -> bool:
    for comparison in (against_persistence, against_drift):
        if not comparison or str(comparison.get("status")) not in {"ok", "single_block"}:
            return False
        if (_as_int(comparison.get("paired_count")) or 0) < 2:
            return False
        delta_high = _finite_number(comparison.get("ci_high"))
        if delta_high is None or delta_high >= 0:
            return False
    return True


def _coverage_by_model_horizon(
    manifest: Mapping[str, Mapping[str, Any]],
    forecast_rows: Sequence[Mapping[str, Any]],
    horizons: Sequence[int],
) -> list[dict[str, Any]]:
    forecast_keys = {
        (str(row.get("run_key")), _as_int(row.get("horizon")))
        for row in forecast_rows
    }
    models = sorted({str(row.get("model", "")) for row in manifest.values()})
    output: list[dict[str, Any]] = []
    for model in models:
        model_rows = [row for row in manifest.values() if row.get("model") == model]
        for horizon in horizons:
            total = len(model_rows)
            successful = sum(
                1
                for row in model_rows
                if row.get("status") == _SUCCESS_MANIFEST_STATUS
                and (str(row.get("run_key")), horizon) in forecast_keys
            )
            output.append(
                {
                    "model": model,
                    "horizon": horizon,
                    "total": total,
                    "successful": successful,
                    "failed_or_missing": total - successful,
                    "coverage_rate": successful / total if total else None,
                }
            )
    return output


def _latency_summary(manifest: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    by_model: dict[str, list[float]] = defaultdict(list)
    for row in manifest.values():
        value = _finite_number(row.get("latency_ms"))
        if value is not None:
            by_model[str(row.get("model", ""))].append(value)
    output: dict[str, Any] = {}
    for model, values in sorted(by_model.items()):
        output[model] = {
            "count": len(values),
            "min_ms": min(values),
            "max_ms": max(values),
            "mean_ms": sum(values) / len(values),
        }
    return output


def _model_metadata_summary(manifest: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    by_model: dict[str, dict[str, set[Any]]] = defaultdict(
        lambda: {
            "model_identity": set(),
            "weights_identity": set(),
            "device": set(),
            "cuda": set(),
        }
    )
    for row in manifest.values():
        model = str(row.get("model", ""))
        health = _parse_json_cell(row.get("health_metadata_json"))
        for field in ("model_identity", "weights_identity"):
            value = row.get(field)
            if value not in (None, ""):
                by_model[model][field].add(value)
        if isinstance(health, Mapping):
            for field in ("device", "cuda"):
                if health.get(field) is not None:
                    by_model[model][field].add(health[field])
    return {
        model: {
            field: sorted(values, key=lambda value: str(value))
            for field, values in sorted(fields_by_name.items())
        }
        for model, fields_by_name in sorted(by_model.items())
    }


def _metric_summary_row(summary: Mapping[str, Any]) -> dict[str, Any]:
    row: dict[str, Any] = {
        "asset_id": summary.get("asset_id", ""),
        "model": summary.get("model", ""),
        "horizon": summary.get("horizon", ""),
    }
    for field in _METRIC_OUTPUT_COLUMNS[3:]:
        if field == "status_counts_json":
            row[field] = _canonical_json(summary.get("status_counts", {}))
        elif field == "metric_denominators_json":
            row[field] = _canonical_json(summary.get("metric_denominators", {}))
        else:
            row[field] = summary.get(field)
    return row


def _render_report(
    *,
    metadata: Mapping[str, Any],
    conclusion: str,
    status_counts: Mapping[str, int],
    model_status_counts: Mapping[str, Mapping[str, int]],
    coverage: Sequence[Mapping[str, Any]],
    model_summaries: Sequence[Mapping[str, Any]],
    comparisons: Sequence[Mapping[str, Any]],
    latency: Mapping[str, Any],
    model_metadata: Mapping[str, Any],
) -> str:
    lines = [
        "# Kronos rolling evaluation report",
        "",
        f"Conclusion: `{conclusion}`",
        "",
        f"Experiment fingerprint: `{metadata.get('experiment_fingerprint', '')}`",
        "",
        "## Run counts",
        "",
        "| status | count |",
        "|---|---:|",
    ]
    lines.extend(
        f"| {status} | {count} |" for status, count in sorted(status_counts.items())
    )
    lines.extend(["", "| model | status counts |", "|---|---|"])
    lines.extend(
        f"| {model} | `{_canonical_json(counts)}` |"
        for model, counts in sorted(model_status_counts.items())
    )
    lines.extend(["", "## Coverage by model/horizon", "", "| model | horizon | total | successful | failed/missing | coverage |", "|---|---:|---:|---:|---:|---:|"])
    lines.extend(
        "| {model} | {horizon} | {total} | {successful} | {failed_or_missing} | {coverage} |".format(
            model=row.get("model"),
            horizon=row.get("horizon"),
            total=row.get("total"),
            successful=row.get("successful"),
            failed_or_missing=row.get("failed_or_missing"),
            coverage=_format_number(row.get("coverage_rate")),
        )
        for row in coverage
    )
    lines.extend(["", "## Metrics by model/horizon", "", "| model | horizon | count | absolute return error | direction hit | interval coverage |", "|---|---:|---:|---:|---:|---:|"])
    lines.extend(
        "| {model} | {horizon} | {count} | {error} | {direction} | {coverage} |".format(
            model=row.get("model"),
            horizon=row.get("horizon"),
            count=row.get("metric_count"),
            error=_format_number(row.get("mean_absolute_return_error")),
            direction=_format_number(row.get("mean_direction_hit")),
            coverage=_format_number(row.get("mean_interval_coverage")),
        )
        for row in model_summaries
    )
    lines.extend(["", "Persistence and drift baselines are included in the metric tables.", ""])
    lines.extend(["## Model comparison", "", "| comparison | status | paired blocks | delta | 95% CI |", "|---|---|---:|---:|---|"])
    lines.extend(
        "| {comparison} | {status} | {paired} | {delta} | [{low}, {high}] |".format(
            comparison=row.get("comparison"),
            status=row.get("status"),
            paired=row.get("paired_count"),
            delta=_format_number(row.get("delta_mean")),
            low=_format_number(row.get("ci_low")),
            high=_format_number(row.get("ci_high")),
        )
        for row in comparisons
    )
    lines.extend(["", "The base-minus-small paired delta is reported above with block-bootstrap confidence intervals.", ""])
    lines.extend(["## Latency and model metadata", ""])
    lines.append(f"Latency: `{_canonical_json(latency)}`")
    lines.append("")
    lines.append(f"Model metadata: `{_canonical_json(model_metadata)}`")
    lines.append("")
    return "\n".join(lines) + "\n"


def _mean_coverage_by_model(
    model_summaries: Sequence[Mapping[str, Any]],
) -> dict[str, float | None]:
    values: dict[str, list[float]] = defaultdict(list)
    for row in model_summaries:
        model = str(row.get("model", ""))
        coverage = _finite_number(row.get("mean_interval_coverage"))
        if coverage is not None and model in {"small", "base"}:
            values[model].append(coverage)
    return {
        model: (sum(items) / len(items) if items else None)
        for model, items in values.items()
    }


def _write_run_artifacts(
    output_dir: Path,
    manifest: Mapping[str, Mapping[str, Any]],
    forecast_rows: Sequence[Mapping[str, Any]],
    realized_rows: Sequence[Mapping[str, Any]],
) -> None:
    normalized_manifest = [manifest[key] for key in sorted(manifest)]
    _atomic_write_csv(output_dir / MANIFEST_FILENAME, normalized_manifest, MANIFEST_COLUMNS)
    _atomic_write_table(
        output_dir / FORECAST_FILENAME,
        _sort_artifact_rows(forecast_rows),
        FORECAST_COLUMNS,
    )
    _atomic_write_table(
        output_dir / REALIZED_FILENAME,
        _sort_artifact_rows(realized_rows),
        REALIZED_COLUMNS,
    )


def _sort_artifact_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        [dict(row) for row in rows],
        key=lambda row: (
            str(row.get("run_key", "")),
            _as_int(row.get("horizon")) or 0,
            str(row.get("timestamp", "")),
        ),
    )


def _ensure_manifest_rows(
    rows: Sequence[Mapping[str, Any]],
    snapshots: Sequence[RollingSnapshot],
    config: KronosEvaluationConfig,
) -> dict[str, dict[str, Any]]:
    keyed: dict[str, dict[str, Any]] = {}
    for source in rows:
        row = {field: source.get(field, "") for field in MANIFEST_COLUMNS}
        run_key = str(row.get("run_key", ""))
        if run_key:
            keyed[run_key] = row
    for snapshot in snapshots:
        for model in config.models:
            run_key = f"{snapshot.key}|{model}"
            keyed.setdefault(run_key, _initial_manifest_row(snapshot, model, config))
    return keyed


def _load_manifest(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"missing run manifest: {path}")
    with path.open(newline="", encoding="utf-8") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _read_table(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        import pyarrow.parquet as parquet

        try:
            return [dict(row) for row in parquet.read_table(path).to_pylist()]
        except Exception:
            pass
    except ModuleNotFoundError:
        pass
    with path.open(newline="", encoding="utf-8") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _atomic_write_json(path: Path, value: Any) -> None:
    _atomic_write_text(path, _canonical_json(value) + "\n")


def _atomic_write_text(path: Path, value: str) -> None:
    _atomic_write_bytes(path, value.encode("utf-8"))


def _atomic_write_csv(
    path: Path,
    rows: Sequence[Mapping[str, Any]],
    columns: Sequence[str],
) -> None:
    from io import StringIO

    buffer = StringIO(newline="")
    writer = csv.DictWriter(
        buffer,
        fieldnames=list(columns),
        extrasaction="ignore",
        lineterminator="\n",
    )
    writer.writeheader()
    for source in rows:
        writer.writerow({column: _csv_value(source.get(column)) for column in columns})
    _atomic_write_text(path, buffer.getvalue())


def _atomic_write_table(
    path: Path,
    rows: Sequence[Mapping[str, Any]],
    columns: Sequence[str],
) -> None:
    try:
        import pyarrow as pa
        import pyarrow.parquet as parquet
    except ModuleNotFoundError:
        _atomic_write_csv(path, rows, columns)
        return

    arrow_types = {
        "asset_id": pa.string(),
        "origin_date": pa.string(),
        "model": pa.string(),
        "run_key": pa.string(),
        "input_fingerprint": pa.string(),
        "timestamp": pa.string(),
        "horizon": pa.int64(),
        "p10": pa.float64(),
        "p50": pa.float64(),
        "p90": pa.float64(),
        "sample_count": pa.int64(),
        "seed": pa.int64(),
        "status": pa.string(),
        "model_identity": pa.string(),
        "weights_identity": pa.string(),
        "device": pa.string(),
        "cuda": pa.bool_(),
        "open": pa.float64(),
        "high": pa.float64(),
        "low": pa.float64(),
        "close": pa.float64(),
        "volume": pa.float64(),
        "amount": pa.float64(),
    }
    schema = pa.schema(
        [pa.field(column, arrow_types.get(column, pa.string())) for column in columns]
    )
    normalized_rows = [
        {column: _pyarrow_value(row.get(column)) for column in columns}
        for row in rows
    ]
    table = pa.Table.from_pylist(normalized_rows, schema=schema)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
        parquet.write_table(
            table,
            temporary_path,
            compression=None,
            use_dictionary=False,
            write_statistics=False,
        )
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink()
            except FileNotFoundError:
                pass


def _atomic_write_bytes(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink()
            except FileNotFoundError:
                pass


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise
    except (OSError, ValueError) as exc:
        raise ValueError(f"invalid JSON artifact {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"JSON artifact {path} must contain an object")
    return value


def _config_payload(config: KronosEvaluationConfig) -> dict[str, Any]:
    return {
        field.name: _jsonable(getattr(config, field.name))
        for field in fields(config)
    }


def _require_config(config: KronosEvaluationConfig) -> None:
    if not isinstance(config, KronosEvaluationConfig):
        raise TypeError("config must be a KronosEvaluationConfig")


def _normalize_model(model: Any) -> str:
    normalized = _normalize_model_alias(model)
    if normalized not in {"small", "base"}:
        raise ValueError("model must be small or base")
    return normalized


def _normalize_model_alias(model: Any) -> str:
    if not isinstance(model, str):
        return ""
    value = model.strip().lower()
    return {
        "small": "small",
        "kronos-small": "small",
        "base": "base",
        "kronos-base": "base",
    }.get(value, value)


def _code_revision() -> str:
    try:
        repository = Path(__file__).resolve().parents[2]
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repository,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    revision = completed.stdout.strip()
    return revision or "unknown"


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, bool) or value is None or isinstance(value, (str, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("JSON values must contain finite numbers")
        return value
    raise TypeError(f"unsupported JSON value type: {type(value).__name__}")


def _canonical_json(value: Any) -> str:
    return json.dumps(
        _jsonable(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _csv_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (Mapping, list, tuple)):
        return _canonical_json(value)
    return value


def _pyarrow_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return _canonical_json(value)
    if isinstance(value, (list, tuple)):
        return _canonical_json(value)
    return value


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _elapsed_milliseconds(start_clock: float) -> float:
    elapsed = (time.perf_counter() - start_clock) * 1000.0
    return round(elapsed, 6)


def _snapshot_key_from_row(row: Mapping[str, Any]) -> str:
    return str(row.get("snapshot_key") or f"{row.get('asset_id')}|{row.get('origin_date')}")


def _first_value(*arguments: Any) -> Any:
    sources = tuple(argument for argument in arguments if isinstance(argument, Mapping))
    keys = tuple(argument for argument in arguments if isinstance(argument, str))
    for source in sources:
        for key in keys:
            if source.get(key) is not None:
                return source[key]
    return None


def _first_identity(
    response_metadata: Mapping[str, Any],
    health: Mapping[str, Any],
    fallback_model: str | None = None,
) -> str | None:
    value = _first_value(
        response_metadata,
        health,
        "model_identity",
        "model_name",
    )
    if value is None:
        value = _first_value(response_metadata, health, "model")
    if value is None:
        return fallback_model
    return str(value)


def _first_weight_identity(
    response_metadata: Mapping[str, Any],
    health: Mapping[str, Any],
) -> str | None:
    value = _first_value(
        response_metadata,
        health,
        "weights_identity",
        "weights_fingerprint",
        "weights",
    )
    if value is None:
        return None
    return _canonical_json(value) if isinstance(value, (Mapping, list, tuple)) else str(value)


def _raw_response_for_manifest(response: Mapping[str, Any] | None) -> Mapping[str, Any]:
    if not isinstance(response, Mapping):
        return {}
    raw = response.get("raw_response")
    if isinstance(raw, Mapping):
        return raw
    return response


def _nested_error_value(response: Mapping[str, Any], field: str) -> Any:
    error = response.get("error")
    return error.get(field) if isinstance(error, Mapping) else None


def _response_reason(response: Mapping[str, Any], fallback: str) -> str:
    error = response.get("error")
    if isinstance(error, Mapping):
        message = error.get("message") or error.get("reason")
        if message:
            return str(message)
    for key in ("reason", "message", "error"):
        value = response.get(key)
        if value not in (None, "") and not isinstance(value, Mapping):
            return str(value)
    return fallback


def _string_or_default(value: Any, default: str) -> str:
    return str(value) if value not in (None, "") else default


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return numeric if math.isfinite(numeric) else None


def _required_float(value: Any, label: str) -> float:
    numeric = _finite_number(value)
    if numeric is None:
        raise ValueError(f"{label} must be finite")
    return numeric


def _last_close(snapshot: RollingSnapshot) -> float:
    if not snapshot.history:
        raise ValueError("snapshot has no history")
    return _required_float(snapshot.history[-1].get("close"), "history close")


def _integer_sequence(value: Any, field_name: str) -> tuple[int, ...]:
    if isinstance(value, (str, bytes)) or value is None:
        raise ValueError(f"{field_name} must be a sequence of integers")
    try:
        values = tuple(value)
    except TypeError as exc:
        raise ValueError(f"{field_name} must be a sequence of integers") from exc
    if any(isinstance(item, bool) or not isinstance(item, int) or item <= 0 for item in values):
        raise ValueError(f"{field_name} must be a sequence of positive integers")
    return values


def _parse_json_cell(value: Any) -> Any:
    if isinstance(value, Mapping):
        return _jsonable(value)
    if not isinstance(value, str) or not value:
        return None
    try:
        return json.loads(value)
    except ValueError:
        return None


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool) or value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return None


def _optional_int(value: Any) -> int | None:
    return _as_int(value)


def _format_number(value: Any) -> str:
    numeric = _finite_number(value)
    if numeric is None:
        return ""
    return f"{numeric:.6g}"


__all__ = [
    "ModelRunResult",
    "PreparationResult",
    "SnapshotLoadResult",
    "build_report",
    "prepare_experiment",
    "run_model",
]
