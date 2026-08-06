"""Resumable orchestration for frozen Kronos rolling-evaluation experiments.

This module deliberately keeps the research experiment on the filesystem.  It
never writes the production Kronos cache and, after preparation, prediction
and reporting read only the frozen experiment directory.
"""

from __future__ import annotations

import csv
import hashlib
import inspect
import json
import math
import os
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from contextlib import contextmanager
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
from stock_research.kronos_evaluation_identity import (
    IdentityValidationError,
    explicit_model_identity,
    explicit_weight_identity,
    canonical_identity,
    iter_identity_fields as _shared_iter_identity_fields,
    model_family as _shared_model_family,
    model_identity_parts as _shared_model_identity_parts,
    validate_identity_payloads,
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
TRANSACTION_FILENAME = ".kronos_transaction.json"
REPORT_TRANSACTION_FILENAME = ".kronos_report_transaction.json"
REPORT_INVALIDATION_FILENAME = ".kronos_report_invalidation.json"
REPORT_DIGEST_FILENAME = ".kronos_report_digest.json"
WRITER_LOCK_PREFIX = "."
WRITER_LOCK_SUFFIX = ".kronos-writer.lock"
_PREPARATION_OWNER_FILENAME = ".kronos_prepare_owner.json"
_PREPARATION_JOURNAL_SCHEMA_VERSION = 1
_EXPERIMENT_SCHEMA_VERSION = 3
_TRANSACTION_SCHEMA_VERSION = 4
_REPORT_TRANSACTION_SCHEMA_VERSION = 2
_REPORT_INVALIDATION_SCHEMA_VERSION = 1
_REPORT_DIGEST_SCHEMA_VERSION = 1

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
_TERMINAL_MANIFEST_STATUSES = frozenset(
    {
        "success",
        "model_error",
        "unavailable",
        "protocol_error",
        "timeout",
        "transport_error",
        "insufficient_input",
        "insufficient_truth",
        "invalid_input",
    }
)
_CLIENT_RAW_RESPONSE_SLOT_MARKER = "__kronos_client_raw_response_slot__"
_DERIVED_REPORT_FILENAMES = (
    METRICS_BY_STOCK_FILENAME,
    METRICS_BY_MODEL_FILENAME,
    MODEL_COMPARISON_FILENAME,
    REPORT_FILENAME,
)
_REPORT_PUBLISHED_FILENAMES = _DERIVED_REPORT_FILENAMES + (REPORT_DIGEST_FILENAME,)

_WRITER_LOCK_STATE: dict[str, dict[str, Any]] = {}
_WRITER_LOCK_STATE_GUARD = threading.RLock()
_WRITER_LOCK_CONDITION = threading.Condition(_WRITER_LOCK_STATE_GUARD)

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
    "snapshot_fingerprint",
    "model_identity",
    "weights_identity",
    "health_model_identity",
    "health_weights_identity",
    "health_model_raw_identity",
    "health_weights_raw_identity",
    "response_model_identity",
    "response_weights_identity",
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
    "forecast_fingerprint",
    "realized_fingerprint",
    "cache_hit",
    "generation",
)

FORECAST_COLUMNS = (
    "asset_id",
    "origin_date",
    "model",
    "run_key",
    "input_fingerprint",
    "timestamp",
    "horizon",
    "representative_open",
    "representative_high",
    "representative_low",
    "representative_close",
    "representative_volume",
    "representative_amount",
    "representative_path_json",
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

_SNAPSHOT_JSON_KEYS = frozenset(
    {
        "asset_id",
        "origin_date",
        "history",
        "future_timestamps",
        "realized",
        "input_fingerprint",
        "status",
        "reason",
    }
)

_DOCUMENTED_TOP_LEVEL_ENTRIES = frozenset(
    {
        EXPERIMENT_FILENAME,
        UNIVERSE_FILENAME,
        SNAPSHOT_DIRECTORY,
        MANIFEST_FILENAME,
        FORECAST_FILENAME,
        REALIZED_FILENAME,
        METRICS_BY_STOCK_FILENAME,
        METRICS_BY_MODEL_FILENAME,
        MODEL_COMPARISON_FILENAME,
        REPORT_FILENAME,
        REPORT_DIGEST_FILENAME,
    }
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
    "generation",
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
    "generation",
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
    snapshot_full_fingerprints: tuple[str, ...] = ()


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


class WriterLockError(RuntimeError):
    """The requested experiment output is already owned by another writer."""


def _writer_lock_path(output_dir: Path) -> Path:
    normalized = Path(output_dir)
    name = normalized.name or "output"
    return normalized.parent / f"{WRITER_LOCK_PREFIX}{name}{WRITER_LOCK_SUFFIX}"


def _active_writer_owner(output_dir: Path) -> Mapping[str, Any] | None:
    key = str(Path(output_dir).resolve(strict=False))
    with _WRITER_LOCK_STATE_GUARD:
        state = _WRITER_LOCK_STATE.get(key)
        if state is None:
            return None
        return dict(state["owner"])


@contextmanager
def _writer_lock(output_dir: Path, *, wait: bool = False):
    """Hold an exclusive per-output lock across preparation or publication."""

    normalized = Path(output_dir)
    _reject_symlink(normalized, "experiment output directory")
    parent = normalized.parent
    _reject_symlink(parent, "experiment output parent")
    if not parent.exists():
        parent.mkdir(parents=True, exist_ok=True)
    _require_regular_directory(parent, "experiment output parent")
    lock_path = _writer_lock_path(normalized)
    _reject_symlink(lock_path, "experiment writer lock")
    key = str(normalized.resolve(strict=False))
    thread_id = threading.get_ident()

    reentrant = False
    with _WRITER_LOCK_CONDITION:
        while True:
            active = _WRITER_LOCK_STATE.get(key)
            if active is None:
                break
            if active["thread_id"] == thread_id:
                active["depth"] += 1
                reentrant = True
                break
            if not wait:
                raise WriterLockError(
                    f"writer lock is held for output directory {normalized}"
                )
            _WRITER_LOCK_CONDITION.wait()

        if not reentrant:
            try:
                import fcntl
            except ModuleNotFoundError:  # pragma: no cover - supported CI is POSIX.
                fcntl = None

            try:
                handle = lock_path.open("a+", encoding="utf-8")
            except OSError as exc:
                raise RuntimeError(f"cannot open experiment writer lock {lock_path}") from exc
            try:
                if fcntl is not None:
                    try:
                        flags = fcntl.LOCK_EX if wait else fcntl.LOCK_EX | fcntl.LOCK_NB
                        fcntl.flock(handle.fileno(), flags)
                    except (BlockingIOError, OSError) as exc:
                        raise WriterLockError(
                            f"writer lock is held for output directory {normalized}"
                        ) from exc
                owner = {
                    "owner_id": uuid.uuid4().hex,
                    "pid": os.getpid(),
                    "thread_id": thread_id,
                    "output_dir": str(normalized.resolve(strict=False)),
                    "lock_path": str(lock_path.resolve(strict=False)),
                    "started_at": _now_iso(),
                }
                handle.seek(0)
                handle.truncate()
                handle.write(_canonical_json(owner) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
                _WRITER_LOCK_STATE[key] = {
                    "thread_id": thread_id,
                    "depth": 1,
                    "handle": handle,
                    "fcntl": fcntl,
                    "owner": owner,
                }
            except BaseException:
                try:
                    if fcntl is not None:
                        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                except OSError:
                    pass
                handle.close()
                raise

    try:
        yield
    finally:
        with _WRITER_LOCK_STATE_GUARD:
            state = _WRITER_LOCK_STATE.get(key)
            if state is not None and state["thread_id"] == thread_id:
                state["depth"] -= 1
                if state["depth"] == 0:
                    _WRITER_LOCK_STATE.pop(key, None)
                    handle = state["handle"]
                    fcntl = state["fcntl"]
                    try:
                        if fcntl is not None:
                            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                    finally:
                        handle.close()
                    _WRITER_LOCK_CONDITION.notify_all()


def prepare_experiment(
    config: KronosEvaluationConfig,
    *,
    output_dir: Path,
    snapshot_loader: SnapshotLoader | None = None,
) -> PreparationResult:
    normalized_output_dir = Path(output_dir)
    _reject_symlink(normalized_output_dir, "experiment output directory")
    with _writer_lock(normalized_output_dir, wait=True):
        return _prepare_experiment_locked(
            config,
            output_dir=normalized_output_dir,
            snapshot_loader=snapshot_loader,
        )


def _prepare_experiment_locked(
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
    _reject_symlink(normalized_output_dir, "experiment output directory")
    experiment_path = normalized_output_dir / EXPERIMENT_FILENAME

    _cleanup_orphan_preparation_stages(normalized_output_dir)
    _recover_pending_transaction_locked(normalized_output_dir)
    _recover_report_invalidation_locked(normalized_output_dir)
    _recover_report_transaction_locked(normalized_output_dir)
    if experiment_path.exists():
        _validate_top_level_entries(normalized_output_dir)
        metadata = _read_json(experiment_path)
        _validate_existing_experiment_config(metadata, config)
        return _existing_preparation_result(normalized_output_dir, metadata, config)

    if normalized_output_dir.exists():
        try:
            has_existing_entries = any(normalized_output_dir.iterdir())
        except OSError as exc:
            raise FileExistsError(
                f"cannot safely prepare experiment in {normalized_output_dir}"
            ) from exc
        if has_existing_entries:
            raise FileExistsError(
                f"output directory is non-empty and lacks {EXPERIMENT_FILENAME}"
            )

    # Preparation always creates the two required Parquet artifacts.  Check
    # the real writer before creating any experiment files so a missing
    # dependency cannot leave a partially prepared directory behind.
    _load_pyarrow()
    loaded = (
        _default_snapshot_loader(config)
        if snapshot_loader is None
        else _invoke_snapshot_loader(snapshot_loader, config)
    )
    snapshots, source_metadata = _normalize_loader_result(loaded)
    snapshots = _validate_prepared_snapshots(config, snapshots)
    source_payload = _jsonable(dict(source_metadata))

    metadata = _build_experiment_metadata(config, snapshots, source_payload)
    manifest_rows = [
        _initial_manifest_row(snapshot, model, config)
        for snapshot in snapshots
        for model in config.models
    ]

    # Stage every initial artifact in a sibling directory.  The destination
    # remains absent (or empty) if any write, including experiment metadata,
    # fails, so a retry never encounters a contaminated fresh experiment.
    normalized_output_dir.parent.mkdir(parents=True, exist_ok=True)
    stage_id = uuid.uuid4().hex
    stage_dir = normalized_output_dir.parent / (
        f".{normalized_output_dir.name}.prepare-{stage_id}"
    )
    preparation_journal = {
        "schema_version": _PREPARATION_JOURNAL_SCHEMA_VERSION,
        "state": "staging",
        "owner_id": (_active_writer_owner(normalized_output_dir) or {}).get(
            "owner_id", ""
        ),
        "pid": os.getpid(),
        "output_dir": str(normalized_output_dir.resolve(strict=False)),
        "lock_path": str(_writer_lock_path(normalized_output_dir).resolve(strict=False)),
        "stage_dir": stage_dir.name,
    }
    published = False
    snapshot_paths: list[Path] = []
    try:
        _persist_preparation_journal(normalized_output_dir, preparation_journal)
        stage_dir.mkdir(exist_ok=False)
        owner = _active_writer_owner(normalized_output_dir) or {}
        _atomic_write_json(
            stage_dir / _PREPARATION_OWNER_FILENAME,
            {
                "owner_id": owner.get("owner_id", uuid.uuid4().hex),
                "pid": os.getpid(),
                "output_dir": str(normalized_output_dir.resolve(strict=False)),
                "lock_path": str(
                    _writer_lock_path(normalized_output_dir).resolve(strict=False)
                ),
            },
        )
        snapshot_dir = stage_dir / SNAPSHOT_DIRECTORY
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        for snapshot in snapshots:
            path = snapshot_dir / _snapshot_filename(snapshot)
            _atomic_write_json(path, snapshot_to_json_payload(snapshot))
            snapshot_paths.append(path)

        _atomic_write_csv(
            stage_dir / UNIVERSE_FILENAME,
            [
                {"asset_id": asset_id, "position": position}
                for position, asset_id in enumerate(config.asset_ids, start=1)
            ],
            ("asset_id", "position"),
        )
        _write_run_artifacts_locked(
            stage_dir,
            {row["run_key"]: row for row in manifest_rows},
            [],
            [],
        )
        _atomic_write_json(stage_dir / EXPERIMENT_FILENAME, metadata)
        _reject_symlink(stage_dir / _PREPARATION_OWNER_FILENAME, "preparation owner marker")
        (stage_dir / _PREPARATION_OWNER_FILENAME).unlink(missing_ok=True)

        preparation_journal["state"] = "publishing"
        _persist_preparation_journal(normalized_output_dir, preparation_journal)
        if normalized_output_dir.exists():
            # The non-empty case was rejected above.  Remove only the known
            # empty placeholder immediately before the atomic publication.
            normalized_output_dir.rmdir()
        os.replace(stage_dir, normalized_output_dir)
        published = True
        snapshot_paths = [
            normalized_output_dir / SNAPSHOT_DIRECTORY / path.name
            for path in snapshot_paths
        ]
    finally:
        if not published:
            shutil.rmtree(stage_dir, ignore_errors=True)
        _remove_preparation_journal(normalized_output_dir)

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
    normalized_output_dir = Path(output_dir)
    with _writer_lock(normalized_output_dir, wait=True):
        return _run_model_locked(
            config,
            model=model,
            output_dir=normalized_output_dir,
            client=client,
        )


def _run_model_locked(
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
    _recover_pending_transaction_locked(normalized_output_dir)
    _recover_report_invalidation_locked(normalized_output_dir)
    _recover_report_transaction_locked(normalized_output_dir)
    metadata = _read_json(normalized_output_dir / EXPERIMENT_FILENAME)
    snapshots, manifest = _validate_experiment_integrity(
        normalized_output_dir,
        metadata,
        config,
    )
    if not snapshots:
        raise ValueError("prepared experiment has no input snapshots")

    forecast_rows, forecast_generation, forecast_schema = _read_table_with_generation(
        normalized_output_dir / FORECAST_FILENAME,
        FORECAST_COLUMNS,
    )
    realized_rows, realized_generation, realized_schema = _read_table_with_generation(
        normalized_output_dir / REALIZED_FILENAME,
        REALIZED_COLUMNS,
    )
    _validate_artifact_generation(
        manifest,
        forecast_rows,
        realized_rows,
        forecast_generation,
        realized_generation,
        forecast_schema,
        realized_schema,
    )
    artifact_generation = next(iter({str(row["generation"]) for row in manifest.values()}))
    _validate_existing_report_artifacts(normalized_output_dir, artifact_generation)
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
            continue

        if _manifest_cache_matches(
            row,
            snapshot,
            normalized_model,
            parameters,
            None if health_failure is not None else health,
            forecast_rows,
            realized_rows,
        ):
            cache_hit_count += 1
            continue

        attempted_count += 1

        if health_failure is not None:
            forecast_rows = [item for item in forecast_rows if item.get("run_key") != run_key]
            realized_rows = [item for item in realized_rows if item.get("run_key") != run_key]
            row.update(
                _unavailable_row_update(
                    snapshot,
                    normalized_model,
                    parameters,
                    health_failure,
                )
            )
            _write_run_artifacts_locked(
                normalized_output_dir,
                manifest,
                forecast_rows,
                realized_rows,
            )
            continue

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
        _write_run_artifacts_locked(
            normalized_output_dir,
            manifest,
            forecast_rows,
            realized_rows,
        )

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
                if isinstance(response, Mapping):
                    response_model_metadata = _response_model_metadata(response)
            row["reason"] = str(exc)

        latency_ms = _elapsed_milliseconds(start_clock)
        finished_at = _now_iso()
        (
            health_identity,
            health_weights,
            health_model_raw,
            health_weights_raw,
        ) = _health_identity_values(health, normalized_model)
        response_identity = _response_identity_value(
            response_model_metadata,
            "model",
        ) or ""
        response_weights = _response_identity_value(
            response_model_metadata,
            "weights",
        ) or ""
        if failure is None:
            forecast_rows.extend(new_forecast_rows)
            realized_rows.extend(new_realized_rows)
            row.update(
                {
                    "status": _SUCCESS_MANIFEST_STATUS,
                    "reason": "",
                    "error_category": "",
                    "error_code": "",
                    "model_identity": health_identity,
                    "weights_identity": health_weights,
                    "health_model_identity": health_identity,
                    "health_weights_identity": health_weights,
                    "health_model_raw_identity": health_model_raw,
                    "health_weights_raw_identity": health_weights_raw,
                    "response_model_identity": response_identity,
                    "response_weights_identity": response_weights,
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
                    "forecast_fingerprint": _artifact_fingerprint(
                        new_forecast_rows,
                        FORECAST_COLUMNS,
                    ),
                    "realized_fingerprint": _artifact_fingerprint(
                        new_realized_rows,
                        REALIZED_COLUMNS,
                    ),
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
                    "model_identity": health_identity,
                    "weights_identity": health_weights,
                    "health_model_identity": health_identity,
                    "health_weights_identity": health_weights,
                    "health_model_raw_identity": health_model_raw,
                    "health_weights_raw_identity": health_weights_raw,
                    "response_model_identity": response_identity,
                    "response_weights_identity": response_weights,
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
                    "forecast_fingerprint": "",
                    "realized_fingerprint": "",
                    "cache_hit": False,
                }
            )
        _write_run_artifacts_locked(
            normalized_output_dir,
            manifest,
            forecast_rows,
            realized_rows,
        )

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
    normalized_output_dir = Path(output_dir)
    with _writer_lock(normalized_output_dir, wait=True):
        return _build_report_locked(output_dir=normalized_output_dir)


def _build_report_locked(*, output_dir: Path) -> dict[str, Any]:
    """Build all report artifacts using only the prepared experiment files."""

    normalized_output_dir = Path(output_dir)
    _recover_pending_transaction_locked(normalized_output_dir)
    _recover_report_invalidation_locked(normalized_output_dir)
    _recover_report_transaction_locked(normalized_output_dir)
    metadata = _read_json(normalized_output_dir / EXPERIMENT_FILENAME)
    config_payload = metadata.get("config")
    if not isinstance(config_payload, Mapping):
        raise ValueError("experiment.json is missing config metadata")
    report_config = _config_from_payload(config_payload)
    snapshots, manifest = _validate_experiment_integrity(
        normalized_output_dir,
        metadata,
        report_config,
    )
    forecast_rows, forecast_generation, forecast_schema = _read_table_with_generation(
        normalized_output_dir / FORECAST_FILENAME,
        FORECAST_COLUMNS,
    )
    realized_rows, realized_generation, realized_schema = _read_table_with_generation(
        normalized_output_dir / REALIZED_FILENAME,
        REALIZED_COLUMNS,
    )
    _validate_artifact_generation(
        manifest,
        forecast_rows,
        realized_rows,
        forecast_generation,
        realized_generation,
        forecast_schema,
        realized_schema,
    )
    artifact_generation = next(iter({str(row["generation"]) for row in manifest.values()}))
    _validate_report_artifacts(
        snapshots,
        manifest,
        report_config,
        forecast_rows,
        realized_rows,
    )
    _validate_existing_report_artifacts(normalized_output_dir, artifact_generation)

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
    stock_output = [
        _metric_summary_row(row, generation=artifact_generation)
        for row in stock_summaries
    ]
    model_output = [
        _metric_summary_row(row, generation=artifact_generation)
        for row in model_summaries
    ]
    comparisons = _build_comparisons(metric_rows, seed=seed)
    comparisons = [
        {**row, "generation": artifact_generation}
        for row in comparisons
    ]

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
        artifact_generation=artifact_generation,
    )
    _publish_report_artifacts_locked(
        normalized_output_dir,
        artifact_generation=artifact_generation,
        stock_output=stock_output,
        model_output=model_output,
        comparisons=comparisons,
        report_text=report_text,
    )

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
        "generation": artifact_generation,
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
        expected_fingerprint = _snapshot_input_fingerprint(snapshot)
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
        "schema_version": _EXPERIMENT_SCHEMA_VERSION,
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
                "snapshot_fingerprint": _snapshot_full_fingerprint(snapshot),
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


def _validate_top_level_entries(output_dir: Path) -> None:
    _reject_symlink(output_dir, "experiment output directory")
    if not output_dir.exists() or not output_dir.is_dir():
        raise FileNotFoundError(f"missing experiment output directory: {output_dir}")
    unknown = []
    for path in output_dir.iterdir():
        if path.name not in _DOCUMENTED_TOP_LEVEL_ENTRIES:
            unknown.append(path.name)
            continue
        _reject_symlink(path, f"experiment artifact {path.name}")
        if path.name == SNAPSHOT_DIRECTORY:
            if not path.is_dir():
                raise ValueError(f"{SNAPSHOT_DIRECTORY} must be a directory")
        elif not path.is_file():
            raise ValueError(f"experiment artifact {path.name} must be a regular file")
    if unknown:
        raise ValueError(
            "output directory contains unknown or stale entries: "
            + ", ".join(unknown)
        )


def _reject_symlink(path: Path, label: str) -> None:
    if path.is_symlink():
        raise ValueError(f"{label} must not be a symlink: {path}")


def _require_regular_file(path: Path, label: str) -> None:
    _reject_symlink(path, label)
    if not path.exists():
        raise FileNotFoundError(f"missing {label}: {path}")
    if not path.is_file():
        raise ValueError(f"{label} must be a regular file: {path}")


def _require_regular_directory(path: Path, label: str) -> None:
    _reject_symlink(path, label)
    if not path.exists():
        raise FileNotFoundError(f"missing {label}: {path}")
    if not path.is_dir():
        raise ValueError(f"{label} must be a regular directory: {path}")


def _cleanup_orphan_preparation_stages(output_dir: Path) -> None:
    """Remove only owner-marked stages after acquiring the output lock.

    A directory with the preparation naming pattern is not, by itself,
    evidence that it is abandoned: another process may have created it just
    before acquiring the parent lock.  Stages created by this runner carry an
    owner marker before any payload I/O, so only those markers are eligible
    for recovery here.
    """

    _reject_symlink(output_dir, "experiment output directory")
    if _active_writer_owner(output_dir) is None:
        raise RuntimeError("preparation-stage cleanup requires the writer lock")
    parent = output_dir.parent
    _reject_symlink(parent, "experiment output parent")
    if not parent.exists():
        return
    _require_regular_directory(parent, "experiment output parent")
    journal_path = _preparation_journal_path(output_dir)
    journal_temp = _preparation_journal_temp_path(output_dir)
    _reject_symlink(journal_path, "preparation journal")
    _reject_symlink(journal_temp, "preparation journal temporary path")
    if journal_temp.exists():
        _require_regular_file(journal_temp, "preparation journal temporary path")
        journal_temp.unlink()
    if journal_path.exists():
        _require_regular_file(journal_path, "preparation journal")
        journal = _read_json(journal_path)
        stage_dir = _validate_preparation_journal(output_dir, journal)
        active_owner = _active_writer_owner(output_dir) or {}
        if journal.get("owner_id") == active_owner.get("owner_id"):
            raise WriterLockError("preparation stage is owned by the active writer")
        if stage_dir.exists():
            _reject_symlink(stage_dir, "preparation stage")
            _require_regular_directory(stage_dir, "preparation stage")
            shutil.rmtree(stage_dir)
        _remove_preparation_journal(output_dir)
    prefix = f".{output_dir.name}.prepare-"
    for candidate in sorted(parent.iterdir(), key=lambda item: item.name):
        if not candidate.name.startswith(prefix):
            continue
        _reject_symlink(candidate, "orphan preparation stage")
        if not candidate.is_dir():
            raise ValueError(f"orphan preparation stage is not a directory: {candidate}")
        owner_path = candidate / _PREPARATION_OWNER_FILENAME
        if not owner_path.exists():
            continue
        _require_regular_file(owner_path, "preparation owner marker")
        owner = _read_json(owner_path)
        if not isinstance(owner, Mapping):
            raise ValueError(f"preparation owner marker is invalid: {owner_path}")
        expected_output = str(output_dir.resolve(strict=False))
        if owner.get("output_dir") != expected_output:
            raise ValueError(f"preparation owner marker targets another output: {owner_path}")
        shutil.rmtree(candidate)


def _preparation_journal_path(output_dir: Path) -> Path:
    normalized = Path(output_dir)
    return normalized.parent / f".{normalized.name}.kronos-prepare.json"


def _preparation_journal_temp_path(output_dir: Path) -> Path:
    journal_path = _preparation_journal_path(output_dir)
    return journal_path.parent / f".{journal_path.name}.tmp"


def _persist_preparation_journal(
    output_dir: Path,
    journal: Mapping[str, Any],
) -> None:
    path = _preparation_journal_path(output_dir)
    _reject_symlink(path, "preparation journal")
    _atomic_write_json(
        path,
        journal,
        temporary_path=_preparation_journal_temp_path(output_dir),
    )
    _fsync_directory(path.parent)


def _remove_preparation_journal(output_dir: Path) -> None:
    path = _preparation_journal_path(output_dir)
    temporary = _preparation_journal_temp_path(output_dir)
    for candidate in (path, temporary):
        _reject_symlink(candidate, "preparation journal path")
        if not candidate.exists():
            continue
        _require_regular_file(candidate, "preparation journal path")
        candidate.unlink()
    _fsync_directory(path.parent)


def _validate_preparation_journal(
    output_dir: Path,
    journal: Mapping[str, Any],
) -> Path:
    required = {
        "schema_version",
        "state",
        "owner_id",
        "pid",
        "output_dir",
        "lock_path",
        "stage_dir",
    }
    if set(journal) != required:
        raise ValueError("preparation journal fields are invalid")
    if journal.get("schema_version") != _PREPARATION_JOURNAL_SCHEMA_VERSION:
        raise ValueError("unsupported preparation journal schema")
    if journal.get("state") not in {"staging", "publishing"}:
        raise ValueError("preparation journal state is invalid")
    if not isinstance(journal.get("owner_id"), str) or not journal.get("owner_id"):
        raise ValueError("preparation journal owner is invalid")
    if isinstance(journal.get("pid"), bool) or not isinstance(journal.get("pid"), int):
        raise ValueError("preparation journal pid is invalid")
    expected_output = str(Path(output_dir).resolve(strict=False))
    expected_lock = str(_writer_lock_path(output_dir).resolve(strict=False))
    if journal.get("output_dir") != expected_output:
        raise ValueError("preparation journal output is invalid")
    if journal.get("lock_path") != expected_lock:
        raise ValueError("preparation journal lock is invalid")
    stage_name = journal.get("stage_dir")
    if (
        not isinstance(stage_name, str)
        or Path(stage_name).name != stage_name
        or not stage_name.startswith(f".{Path(output_dir).name}.prepare-")
    ):
        raise ValueError("preparation journal stage path is invalid")
    stage_dir = Path(output_dir).parent / stage_name
    _reject_symlink(stage_dir, "preparation stage")
    return stage_dir


def _cleanup_known_atomic_temps(output_dir: Path) -> None:
    """Remove only deterministic temps owned by documented output writers."""

    _reject_symlink(output_dir, "experiment output directory")
    if not output_dir.exists():
        return
    _require_regular_directory(output_dir, "experiment output directory")
    base_names = {
        EXPERIMENT_FILENAME,
        UNIVERSE_FILENAME,
        MANIFEST_FILENAME,
        FORECAST_FILENAME,
        REALIZED_FILENAME,
        *(_DERIVED_REPORT_FILENAMES),
        REPORT_DIGEST_FILENAME,
        TRANSACTION_FILENAME,
        REPORT_TRANSACTION_FILENAME,
        REPORT_INVALIDATION_FILENAME,
    }
    for path in sorted(output_dir.iterdir(), key=lambda item: item.name):
        if not path.name.startswith(".") or not path.name.endswith(".tmp"):
            continue
        if not any(
            path.name.startswith(f".{base_name}.")
            or path.name == f".{base_name}.tmp"
            for base_name in base_names
        ):
            continue
        _reject_symlink(path, "atomic temporary path")
        if not path.is_file():
            raise ValueError(f"atomic temporary path is not a regular file: {path}")
        path.unlink()


def _transaction_child(output_dir: Path, name: Any) -> Path:
    if not isinstance(name, str) or not name or Path(name).name != name:
        raise ValueError("transaction journal contains an unsafe artifact path")
    path = output_dir / name
    if path.parent != output_dir:
        raise ValueError("transaction journal contains an unsafe artifact path")
    _reject_symlink(path, "transaction artifact path")
    return path


def _copy_file_durable(source: Path, destination: Path) -> None:
    _require_regular_file(source, "transaction source")
    _reject_symlink(destination, "transaction destination")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    with destination.open("rb") as handle:
        os.fsync(handle.fileno())


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _unlink_transaction_path(path: Path) -> None:
    """Unlink one journal-owned regular file, treating absence as idempotent."""

    _reject_symlink(path, "transaction path")
    if not path.exists():
        return
    if not path.is_file():
        raise ValueError(f"transaction path is not a regular file: {path}")
    path.unlink()


def _persist_transaction_journal(output_dir: Path, journal: Mapping[str, Any]) -> None:
    transaction_path = output_dir / TRANSACTION_FILENAME
    _reject_symlink(transaction_path, "transaction journal")
    transaction_id = journal.get("transaction_id")
    if not isinstance(transaction_id, str) or not transaction_id:
        raise ValueError("transaction journal has no transaction id")
    expected_temp_name = f".{TRANSACTION_FILENAME}.{transaction_id}.tmp"
    journal_temp = journal.get("journal_temp")
    if journal_temp != expected_temp_name:
        raise ValueError("transaction journal temporary path is invalid")
    _atomic_write_json(
        transaction_path,
        journal,
        temporary_path=output_dir / expected_temp_name,
    )
    _fsync_directory(output_dir)


def _transaction_entries(
    output_dir: Path,
    journal: Mapping[str, Any],
) -> list[dict[str, Any]]:
    transaction_id = journal.get("transaction_id")
    if not isinstance(transaction_id, str) or not transaction_id:
        raise ValueError("Kronos artifact transaction id is invalid")
    raw_files = journal.get("files")
    if not isinstance(raw_files, list) or len(raw_files) != 3:
        raise ValueError("Kronos artifact transaction journal has invalid files")
    expected_finals = {
        MANIFEST_FILENAME,
        FORECAST_FILENAME,
        REALIZED_FILENAME,
    }
    entries: list[dict[str, Any]] = []
    seen_finals: set[str] = set()
    required_fields = {
        "final",
        "stage",
        "temporary",
        "backup",
        "had_original",
        "final_state",
        "restore_state",
        "stage_state",
        "temporary_state",
        "backup_state",
    }
    for raw_entry in raw_files:
        if not isinstance(raw_entry, dict) or set(raw_entry) != required_fields:
            raise ValueError("Kronos artifact transaction journal entry is invalid")
        final_name = raw_entry.get("final")
        if final_name not in expected_finals or final_name in seen_finals:
            raise ValueError("Kronos artifact transaction final set is invalid")
        seen_finals.add(final_name)
        stage = _transaction_child(output_dir, raw_entry.get("stage"))
        if stage.name in _DOCUMENTED_TOP_LEVEL_ENTRIES or stage.name == TRANSACTION_FILENAME:
            raise ValueError("transaction journal contains an unsafe staging path")
        backup_name = raw_entry.get("backup")
        if backup_name not in ("", None) and not isinstance(backup_name, str):
            raise ValueError("transaction journal backup path is invalid")
        backup = _transaction_child(output_dir, backup_name) if backup_name else None
        if backup is not None and (
            backup.name in _DOCUMENTED_TOP_LEVEL_ENTRIES
            or backup.name == TRANSACTION_FILENAME
        ):
            raise ValueError("transaction journal contains an unsafe backup path")
        had_original = raw_entry.get("had_original")
        if not isinstance(had_original, bool):
            raise ValueError("Kronos artifact transaction original marker is invalid")
        if had_original and backup is None:
            raise ValueError("Kronos artifact transaction is missing a backup")
        if not had_original and backup is not None:
            raise ValueError("Kronos artifact transaction has an unexpected backup")
        expected_stage_name = f".{final_name}.{transaction_id}.stage"
        if stage.name != expected_stage_name:
            raise ValueError("transaction journal contains an unexpected staging path")
        temporary = _transaction_child(output_dir, raw_entry.get("temporary"))
        if temporary.name != f"{stage.name}.tmp":
            raise ValueError("transaction journal contains an unexpected temporary path")
        if temporary.name in _DOCUMENTED_TOP_LEVEL_ENTRIES:
            raise ValueError("transaction journal contains an unsafe temporary path")
        if had_original and backup is not None:
            expected_backup_name = f".{final_name}.{transaction_id}.backup"
            if backup.name != expected_backup_name:
                raise ValueError("transaction journal contains an unexpected backup path")
        if raw_entry.get("final_state") not in {"old", "new"}:
            raise ValueError("Kronos artifact transaction final state is invalid")
        if raw_entry.get("restore_state") not in {"pending", "restored"}:
            raise ValueError("Kronos artifact transaction restore state is invalid")
        if raw_entry.get("stage_state") not in {
            "planned",
            "present",
            "deleting",
            "deleted",
        }:
            raise ValueError("Kronos artifact transaction stage state is invalid")
        if raw_entry.get("temporary_state") not in {
            "planned",
            "deleted",
            "deleting",
        }:
            raise ValueError("Kronos artifact transaction temporary state is invalid")
        valid_backup_states = {
            "none",
            "planned",
            "present",
            "delete_pending",
            "deleted",
        }
        if raw_entry.get("backup_state") not in valid_backup_states:
            raise ValueError("Kronos artifact transaction backup state is invalid")
        if had_original and raw_entry.get("backup_state") == "none":
            raise ValueError("Kronos artifact transaction backup state is invalid")
        if not had_original and raw_entry.get("backup_state") != "none":
            raise ValueError("Kronos artifact transaction backup state is invalid")
        entries.append(
            {
                "raw": raw_entry,
                "final": _transaction_child(output_dir, final_name),
                "stage": stage,
                "temporary": temporary,
                "backup": backup,
                "had_original": had_original,
            }
        )
    if seen_finals != expected_finals:
        raise ValueError("Kronos artifact transaction final set is incomplete")
    return entries


def _restore_transaction(
    output_dir: Path,
    transaction_path: Path,
    journal: dict[str, Any],
    entries: Sequence[Mapping[str, Any]],
) -> None:
    for entry in entries:
        raw = entry["raw"]
        final_path = entry["final"]
        backup = entry["backup"]
        if entry["had_original"]:
            _reject_symlink(final_path, "transaction final artifact")
            if raw["restore_state"] != "restored":
                if (
                    journal.get("state") == "prepared"
                    and raw["final_state"] == "old"
                    and final_path.exists()
                ):
                    # No final has been replaced while a prepared journal is
                    # active.  The old final is already authoritative even
                    # when backup creation was interrupted before completion.
                    raw["restore_state"] = "restored"
                    _persist_transaction_journal(output_dir, journal)
                    continue
                if not isinstance(backup, Path):
                    raise ValueError("transaction rollback is missing a backup")
                _require_regular_file(backup, "transaction backup")
                with tempfile.NamedTemporaryFile(
                    mode="wb",
                    dir=output_dir,
                    prefix=f".{final_path.name}.recover-",
                    suffix=".tmp",
                    delete=False,
                ) as handle:
                    temporary = Path(handle.name)
                try:
                    _copy_file_durable(backup, temporary)
                    _reject_symlink(final_path, "transaction final artifact")
                    os.replace(temporary, final_path)
                finally:
                    try:
                        temporary.unlink()
                    except FileNotFoundError:
                        pass
                raw["final_state"] = "old"
                raw["restore_state"] = "restored"
                _persist_transaction_journal(output_dir, journal)
            elif not final_path.exists():
                if isinstance(backup, Path) and backup.exists():
                    _require_regular_file(backup, "transaction backup")
                    with tempfile.NamedTemporaryFile(
                        mode="wb",
                        dir=output_dir,
                        prefix=f".{final_path.name}.recover-",
                        suffix=".tmp",
                        delete=False,
                    ) as handle:
                        temporary = Path(handle.name)
                    try:
                        _copy_file_durable(backup, temporary)
                        os.replace(temporary, final_path)
                    finally:
                        try:
                            temporary.unlink()
                        except FileNotFoundError:
                            pass
                else:
                    raise FileNotFoundError(
                        f"transaction rollback lost final and backup for {final_path.name}"
                    )
        else:
            _reject_symlink(final_path, "transaction final artifact")
            if final_path.exists():
                _unlink_transaction_path(final_path)
            if raw["restore_state"] != "restored":
                raw["final_state"] = "old"
                raw["restore_state"] = "restored"
                _persist_transaction_journal(output_dir, journal)

    journal["state"] = "rolled_back"
    _persist_transaction_journal(output_dir, journal)


def _cleanup_transaction(
    output_dir: Path,
    transaction_path: Path,
    journal: dict[str, Any],
    entries: Sequence[Mapping[str, Any]],
) -> None:
    state = journal.get("state")
    for entry in entries:
        raw = entry["raw"]
        temporary = entry["temporary"]
        if raw["temporary_state"] != "deleted":
            if temporary.exists():
                raw["temporary_state"] = "deleting"
                _persist_transaction_journal(output_dir, journal)
                _unlink_transaction_path(temporary)
            raw["temporary_state"] = "deleted"
            _persist_transaction_journal(output_dir, journal)

        stage = entry["stage"]
        if raw["stage_state"] != "deleted":
            if stage.exists():
                raw["stage_state"] = "deleting"
                _persist_transaction_journal(output_dir, journal)
                _unlink_transaction_path(stage)
            raw["stage_state"] = "deleted"
            _persist_transaction_journal(output_dir, journal)

        backup = entry["backup"]
        if backup is None:
            continue
        if raw["backup_state"] == "deleted":
            continue
        if not backup.exists():
            if (
                state in {"prepared", "committed"}
                or raw["backup_state"] in {"planned", "delete_pending"}
                or raw["restore_state"] == "restored"
            ):
                raw["backup_state"] = "deleted"
                _persist_transaction_journal(output_dir, journal)
                continue
            raise FileNotFoundError(f"transaction backup is missing: {backup}")
        _require_regular_file(backup, "transaction backup")
        raw["backup_state"] = "delete_pending"
        _persist_transaction_journal(output_dir, journal)
        _unlink_transaction_path(backup)
        raw["backup_state"] = "deleted"
        _persist_transaction_journal(output_dir, journal)

    _unlink_transaction_path(transaction_path)
    _fsync_directory(output_dir)


def _repair_committed_finals(
    output_dir: Path,
    journal: dict[str, Any],
    entries: Sequence[Mapping[str, Any]],
) -> None:
    """Repair a committed journal if cleanup was interrupted after a final loss."""

    missing = []
    for entry in entries:
        final_path = entry["final"]
        _reject_symlink(final_path, "transaction final artifact")
        if final_path.exists():
            _require_regular_file(final_path, "transaction final artifact")
        else:
            missing.append(entry)
    if not missing:
        return

    if all(entry["stage"].exists() for entry in missing):
        for entry in missing:
            stage = entry["stage"]
            final_path = entry["final"]
            _require_regular_file(stage, "transaction staged artifact")
            os.replace(stage, final_path)
            entry["raw"]["final_state"] = "new"
            entry["raw"]["stage_state"] = "deleted"
            _persist_transaction_journal(output_dir, journal)
        return

    # The new staged content is gone, so the only safe complete generation is
    # the backed-up prior one.  Roll back all three files before cleanup.
    journal["state"] = "committing"
    _persist_transaction_journal(output_dir, journal)
    _restore_transaction(
        output_dir,
        output_dir / TRANSACTION_FILENAME,
        journal,
        entries,
    )


def _recover_pending_transaction(output_dir: Path) -> None:
    normalized_output_dir = Path(output_dir)
    with _writer_lock(normalized_output_dir):
        _recover_pending_transaction_locked(normalized_output_dir)


def _recover_pending_transaction_locked(output_dir: Path) -> None:
    """Recover the previous three-file publication before any reads/writes."""

    _reject_symlink(output_dir, "experiment output directory")
    _cleanup_known_atomic_temps(output_dir)
    transaction_path = output_dir / TRANSACTION_FILENAME
    _reject_symlink(transaction_path, "transaction journal")
    if not transaction_path.exists():
        return
    journal = _read_json(transaction_path)
    if journal.get("schema_version") != _TRANSACTION_SCHEMA_VERSION:
        raise ValueError("unsupported Kronos artifact transaction schema")
    transaction_id = journal.get("transaction_id")
    owner = journal.get("owner")
    expected_output_dir = str(output_dir.resolve(strict=False))
    expected_lock_path = str(_writer_lock_path(output_dir).resolve(strict=False))
    if not isinstance(transaction_id, str) or not transaction_id:
        raise ValueError("Kronos artifact transaction journal has no transaction id")
    if not isinstance(owner, Mapping):
        raise ValueError("Kronos artifact transaction journal has no owner marker")
    if owner.get("owner_id") != transaction_id:
        raise ValueError("Kronos artifact transaction owner marker is invalid")
    if owner.get("output_dir") != expected_output_dir:
        raise ValueError("Kronos artifact transaction owner output is invalid")
    if owner.get("lock_path") != expected_lock_path:
        raise ValueError("Kronos artifact transaction owner lock is invalid")
    if isinstance(owner.get("pid"), bool) or not isinstance(owner.get("pid"), int):
        raise ValueError("Kronos artifact transaction owner pid is invalid")
    expected_journal_temp = f".{TRANSACTION_FILENAME}.{transaction_id}.tmp"
    if journal.get("journal_temp") != expected_journal_temp:
        raise ValueError("Kronos artifact transaction journal temp is invalid")
    state = journal.get("state")
    if state not in {"prepared", "committing", "rolled_back", "committed"}:
        raise ValueError("Kronos artifact transaction journal has an invalid state")
    entries = _transaction_entries(output_dir, journal)
    if state in {"prepared", "committing"}:
        _restore_transaction(output_dir, transaction_path, journal, entries)
    elif state == "committed":
        _repair_committed_finals(output_dir, journal, entries)
    _cleanup_transaction(output_dir, transaction_path, journal, entries)


def _persist_report_transaction(
    output_dir: Path,
    journal: Mapping[str, Any],
) -> None:
    transaction_id = journal.get("transaction_id")
    if not isinstance(transaction_id, str) or not transaction_id:
        raise ValueError("report transaction id is invalid")
    expected_temp = f".{REPORT_TRANSACTION_FILENAME}.{transaction_id}.tmp"
    if journal.get("journal_temp") != expected_temp:
        raise ValueError("report transaction temp is invalid")
    path = output_dir / REPORT_TRANSACTION_FILENAME
    _reject_symlink(path, "report transaction journal")
    _atomic_write_json(
        path,
        journal,
        temporary_path=output_dir / expected_temp,
    )


def _report_transaction_file_paths(
    output_dir: Path,
    journal: Mapping[str, Any],
) -> tuple[Path, dict[str, Path]]:
    transaction_id = journal.get("transaction_id")
    if not isinstance(transaction_id, str) or not transaction_id:
        raise ValueError("report transaction id is invalid")
    expected_stage_dir = f".{REPORT_TRANSACTION_FILENAME}.{transaction_id}.stage"
    stage_dir_name = journal.get("stage_dir")
    if stage_dir_name != expected_stage_dir:
        raise ValueError("report transaction stage directory is invalid")
    stage_dir = output_dir / stage_dir_name
    _reject_symlink(stage_dir, "report transaction stage directory")
    raw_files = journal.get("files")
    if not isinstance(raw_files, list) or len(raw_files) != len(_REPORT_PUBLISHED_FILENAMES):
        raise ValueError("report transaction file set is invalid")
    paths: dict[str, Path] = {}
    for item in raw_files:
        if not isinstance(item, Mapping) or set(item) != {"final", "stage"}:
            raise ValueError("report transaction entry is invalid")
        final_name = item.get("final")
        stage_name = item.get("stage")
        if final_name not in _REPORT_PUBLISHED_FILENAMES or final_name in paths:
            raise ValueError("report transaction final set is invalid")
        if stage_name != final_name:
            raise ValueError("report transaction staged filename is invalid")
        paths[final_name] = stage_dir / stage_name
        _reject_symlink(paths[final_name], "report staged artifact")
    if set(paths) != set(_REPORT_PUBLISHED_FILENAMES):
        raise ValueError("report transaction final set is incomplete")
    return stage_dir, paths


def _clear_report_transaction_outputs(output_dir: Path) -> None:
    for filename in _REPORT_PUBLISHED_FILENAMES:
        path = output_dir / filename
        _reject_symlink(path, "derived report artifact")
        if path.exists():
            if not path.is_file():
                raise ValueError(f"derived report artifact is not a regular file: {path}")
            path.unlink()


def _recover_report_transaction_locked(output_dir: Path) -> None:
    path = output_dir / REPORT_TRANSACTION_FILENAME
    _reject_symlink(path, "report transaction journal")
    if not path.exists():
        return
    journal = _read_json(path)
    if journal.get("schema_version") != _REPORT_TRANSACTION_SCHEMA_VERSION:
        raise ValueError("unsupported report transaction schema")
    transaction_id = journal.get("transaction_id")
    owner = journal.get("owner")
    expected_output = str(output_dir.resolve(strict=False))
    expected_lock = str(_writer_lock_path(output_dir).resolve(strict=False))
    if not isinstance(transaction_id, str) or not transaction_id:
        raise ValueError("report transaction id is invalid")
    if not isinstance(owner, Mapping):
        raise ValueError("report transaction owner marker is missing")
    if owner.get("owner_id") != transaction_id:
        raise ValueError("report transaction owner marker is invalid")
    if owner.get("output_dir") != expected_output or owner.get("lock_path") != expected_lock:
        raise ValueError("report transaction owner path is invalid")
    if journal.get("journal_temp") != f".{REPORT_TRANSACTION_FILENAME}.{transaction_id}.tmp":
        raise ValueError("report transaction journal temp is invalid")
    state = journal.get("state")
    if state not in {"prepared", "publishing", "committed", "cleaning"}:
        raise ValueError("report transaction state is invalid")
    stage_dir, staged_paths = _report_transaction_file_paths(output_dir, journal)

    committed_complete = state == "committed" and all(
        (output_dir / filename).exists() for filename in _REPORT_PUBLISHED_FILENAMES
    )
    if committed_complete:
        # A committed report set is already complete; only its journal/stage
        # cleanup remains.  Persist cleaning before destructive cleanup.
        journal["state"] = "cleaning"
        _persist_report_transaction(output_dir, journal)
    else:
        if state != "cleaning":
            journal["state"] = "cleaning"
            _persist_report_transaction(output_dir, journal)
        _clear_report_transaction_outputs(output_dir)

    if stage_dir.exists():
        _reject_symlink(stage_dir, "report transaction stage directory")
        if not stage_dir.is_dir():
            raise ValueError("report transaction stage directory is not a directory")
        shutil.rmtree(stage_dir)
    for staged_path in staged_paths.values():
        _reject_symlink(staged_path, "report staged artifact")
    _unlink_transaction_path(path)
    _fsync_directory(output_dir)


def _report_file_digest(path: Path) -> str:
    _require_regular_file(path, "derived report artifact")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _report_digest_payload(
    paths: Mapping[str, Path],
    artifact_generation: str,
) -> dict[str, Any]:
    return {
        "schema_version": _REPORT_DIGEST_SCHEMA_VERSION,
        "generation": artifact_generation,
        "files": {
            filename: _report_file_digest(paths[filename])
            for filename in _DERIVED_REPORT_FILENAMES
        },
    }


def _persist_report_invalidation_journal(
    output_dir: Path,
    journal: Mapping[str, Any],
) -> None:
    transaction_id = journal.get("transaction_id")
    if not isinstance(transaction_id, str) or not transaction_id:
        raise ValueError("report invalidation transaction id is invalid")
    expected_temp = f".{REPORT_INVALIDATION_FILENAME}.{transaction_id}.tmp"
    if journal.get("journal_temp") != expected_temp:
        raise ValueError("report invalidation journal temp is invalid")
    path = output_dir / REPORT_INVALIDATION_FILENAME
    _reject_symlink(path, "report invalidation journal")
    _atomic_write_json(
        path,
        journal,
        temporary_path=output_dir / expected_temp,
    )
    _fsync_directory(output_dir)


def _report_invalidation_entries(
    output_dir: Path,
    journal: Mapping[str, Any],
) -> list[tuple[dict[str, Any], Path]]:
    if set(journal) != {
        "schema_version",
        "transaction_id",
        "journal_temp",
        "state",
        "owner",
        "files",
    }:
        raise ValueError("report invalidation journal fields are invalid")
    transaction_id = journal.get("transaction_id")
    if not isinstance(transaction_id, str) or not transaction_id:
        raise ValueError("report invalidation transaction id is invalid")
    if journal.get("journal_temp") != (
        f".{REPORT_INVALIDATION_FILENAME}.{transaction_id}.tmp"
    ):
        raise ValueError("report invalidation journal temp is invalid")
    state = journal.get("state")
    if state not in {"prepared", "deleting", "committed", "cleaning"}:
        raise ValueError("report invalidation journal state is invalid")
    owner = journal.get("owner")
    expected_output = str(output_dir.resolve(strict=False))
    expected_lock = str(_writer_lock_path(output_dir).resolve(strict=False))
    if not isinstance(owner, Mapping):
        raise ValueError("report invalidation owner marker is missing")
    if owner.get("owner_id") != transaction_id:
        raise ValueError("report invalidation owner marker is invalid")
    if owner.get("output_dir") != expected_output or owner.get("lock_path") != expected_lock:
        raise ValueError("report invalidation owner path is invalid")
    if isinstance(owner.get("pid"), bool) or not isinstance(owner.get("pid"), int):
        raise ValueError("report invalidation owner pid is invalid")
    raw_files = journal.get("files")
    if not isinstance(raw_files, list) or len(raw_files) != len(_REPORT_PUBLISHED_FILENAMES):
        raise ValueError("report invalidation file set is invalid")
    entries: list[tuple[dict[str, Any], Path]] = []
    seen: set[str] = set()
    for raw in raw_files:
        if not isinstance(raw, dict) or set(raw) != {"final", "state"}:
            raise ValueError("report invalidation entry is invalid")
        filename = raw.get("final")
        if filename not in _REPORT_PUBLISHED_FILENAMES or filename in seen:
            raise ValueError("report invalidation final set is invalid")
        if raw.get("state") not in {"planned", "deleting", "deleted"}:
            raise ValueError("report invalidation entry state is invalid")
        seen.add(filename)
        path = output_dir / filename
        _reject_symlink(path, "report invalidation artifact")
        entries.append((raw, path))
    if seen != set(_REPORT_PUBLISHED_FILENAMES):
        raise ValueError("report invalidation final set is incomplete")
    return entries


def _unlink_report_invalidation_path(path: Path) -> None:
    _reject_symlink(path, "report invalidation artifact")
    if not path.exists():
        return
    _require_regular_file(path, "report invalidation artifact")
    path.unlink()


def _recover_report_invalidation_locked(output_dir: Path) -> None:
    path = output_dir / REPORT_INVALIDATION_FILENAME
    temporary_paths = sorted(
        output_dir.glob(f".{REPORT_INVALIDATION_FILENAME}.*.tmp"),
        key=lambda item: item.name,
    )
    _reject_symlink(path, "report invalidation journal")
    for temporary in temporary_paths:
        _reject_symlink(temporary, "report invalidation journal temporary path")
        _unlink_transaction_path(temporary)
    if not path.exists():
        return
    journal = _read_json(path)
    if journal.get("schema_version") != _REPORT_INVALIDATION_SCHEMA_VERSION:
        raise ValueError("unsupported report invalidation journal schema")
    entries = _report_invalidation_entries(output_dir, journal)
    for raw, artifact_path in entries:
        if artifact_path.exists():
            raw["state"] = "deleting"
            journal["state"] = "deleting"
            _persist_report_invalidation_journal(output_dir, journal)
            _unlink_report_invalidation_path(artifact_path)
        raw["state"] = "deleted"
        _persist_report_invalidation_journal(output_dir, journal)
    journal["state"] = "committed"
    _persist_report_invalidation_journal(output_dir, journal)
    journal["state"] = "cleaning"
    _persist_report_invalidation_journal(output_dir, journal)
    _unlink_transaction_path(path)
    _fsync_directory(output_dir)


def _publish_report_artifacts_locked(
    output_dir: Path,
    *,
    artifact_generation: str,
    stock_output: Sequence[Mapping[str, Any]],
    model_output: Sequence[Mapping[str, Any]],
    comparisons: Sequence[Mapping[str, Any]],
    report_text: str,
) -> None:
    _recover_report_invalidation_locked(output_dir)
    _recover_report_transaction_locked(output_dir)
    transaction_id = uuid.uuid4().hex
    stage_dir = output_dir / f".{REPORT_TRANSACTION_FILENAME}.{transaction_id}.stage"
    journal: dict[str, Any] = {
        "schema_version": _REPORT_TRANSACTION_SCHEMA_VERSION,
        "transaction_id": transaction_id,
        "journal_temp": f".{REPORT_TRANSACTION_FILENAME}.{transaction_id}.tmp",
        "state": "prepared",
        "owner": {
            "owner_id": transaction_id,
            "writer_owner_id": (_active_writer_owner(output_dir) or {}).get("owner_id", ""),
            "pid": os.getpid(),
            "output_dir": str(output_dir.resolve(strict=False)),
            "lock_path": str(_writer_lock_path(output_dir).resolve(strict=False)),
        },
        "stage_dir": stage_dir.name,
        "files": [
            {"final": filename, "stage": filename}
            for filename in _REPORT_PUBLISHED_FILENAMES
        ],
    }
    _persist_report_transaction(output_dir, journal)
    stage_dir.mkdir(parents=True, exist_ok=False)
    staged = {filename: stage_dir / filename for filename in _REPORT_PUBLISHED_FILENAMES}
    _atomic_write_csv(
        staged[METRICS_BY_STOCK_FILENAME],
        stock_output,
        _METRIC_OUTPUT_COLUMNS,
    )
    _atomic_write_csv(
        staged[METRICS_BY_MODEL_FILENAME],
        model_output,
        _METRIC_OUTPUT_COLUMNS,
    )
    _atomic_write_csv(
        staged[MODEL_COMPARISON_FILENAME],
        comparisons,
        _COMPARISON_OUTPUT_COLUMNS,
    )
    _atomic_write_text(staged[REPORT_FILENAME], report_text)
    _atomic_write_json(
        staged[REPORT_DIGEST_FILENAME],
        _report_digest_payload(staged, artifact_generation),
    )
    journal["state"] = "publishing"
    _persist_report_transaction(output_dir, journal)
    for filename in _REPORT_PUBLISHED_FILENAMES:
        final_path = output_dir / filename
        _reject_symlink(final_path, "derived report artifact")
        os.replace(staged[filename], final_path)
    journal["state"] = "committed"
    _persist_report_transaction(output_dir, journal)
    _recover_report_transaction_locked(output_dir)


def _validate_experiment_integrity(
    output_dir: Path,
    metadata: Mapping[str, Any],
    config: KronosEvaluationConfig,
) -> tuple[tuple[RollingSnapshot, ...], dict[str, dict[str, Any]]]:
    """Validate the immutable experiment boundary before reading run state."""

    if not isinstance(metadata, Mapping):  # pragma: no cover - _read_json guards this.
        raise ValueError("experiment.json must contain an object")
    if metadata.get("schema_version") != _EXPERIMENT_SCHEMA_VERSION:
        raise ValueError(
            f"unsupported experiment schema_version {metadata.get('schema_version')!r}"
        )
    stored_fingerprint = metadata.get("experiment_fingerprint")
    if not isinstance(stored_fingerprint, str) or not stored_fingerprint:
        raise ValueError("experiment fingerprint is missing")
    immutable_metadata = {
        str(key): value
        for key, value in metadata.items()
        if key not in {"created_at", "experiment_fingerprint"}
    }
    computed_fingerprint = canonical_json_fingerprint(immutable_metadata)
    if computed_fingerprint != stored_fingerprint:
        raise ValueError("experiment fingerprint does not match immutable metadata")

    _validate_top_level_entries(output_dir)
    _validate_existing_experiment_config(metadata, config)
    source = metadata.get("source")
    source_metadata = metadata.get("source_metadata")
    if not isinstance(source, Mapping) or not isinstance(source_metadata, Mapping):
        raise ValueError("experiment source/source_metadata metadata is invalid")
    if _jsonable(source) != _jsonable(source_metadata):
        raise ValueError("experiment source/source_metadata metadata diverges")
    if not isinstance(metadata.get("code_revision"), str):
        raise ValueError("experiment code_revision metadata is invalid")
    if not isinstance(metadata.get("created_at"), str):
        raise ValueError("experiment creation time metadata is invalid")

    raw_snapshot_metadata = metadata.get("snapshot_fingerprints")
    if not isinstance(raw_snapshot_metadata, list):
        raise ValueError("experiment snapshot_fingerprints metadata is invalid")
    expected_snapshot_count = metadata.get("snapshot_count")
    if _as_int(expected_snapshot_count) != len(raw_snapshot_metadata):
        raise ValueError("experiment snapshot_count does not match snapshot metadata")

    expected_snapshot_entries: list[dict[str, Any]] = []
    expected_snapshot_keys: list[str] = []
    for item in raw_snapshot_metadata:
        if not isinstance(item, Mapping):
            raise ValueError("experiment snapshot metadata entry is invalid")
        required_fields = {
            "key",
            "asset_id",
            "origin_date",
            "status",
            "input_fingerprint",
            "snapshot_fingerprint",
        }
        if set(item) != required_fields:
            raise ValueError("experiment snapshot metadata fields are invalid")
        entry = {field: _jsonable(item[field]) for field in required_fields}
        key = entry["key"]
        if not isinstance(key, str) or key in expected_snapshot_keys:
            raise ValueError("experiment snapshot metadata keys are invalid")
        expected_snapshot_keys.append(key)
        expected_snapshot_entries.append(entry)

    snapshot_dir = output_dir / SNAPSHOT_DIRECTORY
    _require_regular_directory(snapshot_dir, "frozen snapshot directory")
    expected_filenames = sorted(
        f"{entry['asset_id']}__{entry['origin_date']}.json"
        for entry in expected_snapshot_entries
    )
    actual_directory_entries = sorted(path.name for path in snapshot_dir.iterdir())
    if actual_directory_entries != expected_filenames:
        raise ValueError("frozen snapshot file set does not match experiment metadata")
    if any(
        not path.is_file() or path.is_symlink()
        for path in snapshot_dir.iterdir()
    ):
        raise ValueError("frozen snapshot directory contains a non-regular file")

    snapshots = _read_frozen_snapshots(output_dir)
    if [snapshot.key for snapshot in snapshots] != sorted(expected_snapshot_keys):
        raise ValueError("frozen snapshot key set does not match experiment metadata")
    expected_by_key = {
        str(entry["key"]): entry for entry in expected_snapshot_entries
    }
    for entry in expected_snapshot_entries:
        path = snapshot_dir / f"{entry['asset_id']}__{entry['origin_date']}.json"
        payload = _read_json(path)
        payload_key = f"{payload.get('asset_id')}|{payload.get('origin_date')}"
        if payload_key != entry["key"]:
            raise ValueError(f"frozen snapshot filename {path.name} is inconsistent")
    for snapshot in snapshots:
        expected = expected_by_key.get(snapshot.key)
        if expected is None:
            raise ValueError(f"frozen snapshot {snapshot.key} is not in experiment metadata")
        actual = {
            "key": snapshot.key,
            "asset_id": snapshot.asset_id,
            "origin_date": snapshot.origin_date,
            "status": snapshot.status,
            "input_fingerprint": snapshot.input_fingerprint,
            "snapshot_fingerprint": _snapshot_full_fingerprint(snapshot),
        }
        if actual != expected:
            raise ValueError(f"frozen snapshot {snapshot.key} does not match experiment metadata")

    _validate_universe_file(output_dir / UNIVERSE_FILENAME, config)
    manifest = _load_and_validate_manifest(
        output_dir / MANIFEST_FILENAME,
        snapshots,
        config,
    )
    return snapshots, manifest


def _validate_universe_file(path: Path, config: KronosEvaluationConfig) -> None:
    _require_regular_file(path, "universe.csv")
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != ["asset_id", "position"]:
            raise ValueError("universe.csv columns are invalid")
        rows = list(reader)
    expected_rows = [
        {"asset_id": asset_id, "position": str(position)}
        for position, asset_id in enumerate(config.asset_ids, start=1)
    ]
    if rows != expected_rows:
        raise ValueError("universe.csv set or order does not match experiment metadata")


def _load_and_validate_manifest(
    path: Path,
    snapshots: Sequence[RollingSnapshot],
    config: KronosEvaluationConfig,
) -> dict[str, dict[str, Any]]:
    _require_regular_file(path, "run_manifest.csv")
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != list(MANIFEST_COLUMNS):
            raise ValueError("run_manifest.csv columns are invalid")
        rows = [dict(row) for row in reader]
    expected_by_key = {
        f"{snapshot.key}|{model}": (snapshot, model)
        for snapshot in snapshots
        for model in config.models
    }
    actual_keys = [str(row.get("run_key", "")) for row in rows]
    if len(actual_keys) != len(set(actual_keys)):
        raise ValueError("run_manifest.csv contains duplicate run keys")
    if set(actual_keys) != set(expected_by_key):
        raise ValueError("run_manifest.csv run-key set does not match experiment metadata")

    manifest: dict[str, dict[str, Any]] = {}
    for source in rows:
        if set(source) != set(MANIFEST_COLUMNS):
            raise ValueError("run_manifest.csv row fields are invalid")
        run_key = str(source.get("run_key", ""))
        snapshot, model = expected_by_key[run_key]
        expected_parameters = _prediction_parameters(config, snapshot)
        if (
            source.get("snapshot_key") != snapshot.key
            or source.get("asset_id") != snapshot.asset_id
            or source.get("origin_date") != snapshot.origin_date
            or source.get("model") != model
            or source.get("input_fingerprint") != snapshot.input_fingerprint
            or source.get("snapshot_fingerprint") != _snapshot_full_fingerprint(snapshot)
            or _parse_json_cell(source.get("parameters_json"))
            != _jsonable(expected_parameters)
            or _as_int(source.get("sample_count")) != config.sample_count
            or _optional_int(source.get("seed")) != config.seed
        ):
            raise ValueError(f"run_manifest.csv row {run_key} is inconsistent with experiment")
        if snapshot.status != "ready" and source.get("status") != snapshot.status:
            raise ValueError(f"run_manifest.csv row {run_key} has an invalid snapshot status")
        manifest[run_key] = source
    return manifest


def _existing_preparation_result(
    output_dir: Path,
    metadata: Mapping[str, Any],
    config: KronosEvaluationConfig,
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
    frozen_snapshots, _ = _validate_experiment_integrity(output_dir, metadata, config)
    snapshot_paths = tuple(
        output_dir / SNAPSHOT_DIRECTORY / _snapshot_filename(snapshot)
        for snapshot in frozen_snapshots
    )
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
        snapshot_full_fingerprints=tuple(
            item.get("snapshot_fingerprint", "")
            for item in metadata.get("snapshot_fingerprints", [])
            if isinstance(item, Mapping)
        ),
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
        snapshot_full_fingerprints=tuple(
            item["snapshot_fingerprint"]
            for item in metadata["snapshot_fingerprints"]
        ),
    )


def _read_frozen_snapshots(output_dir: Path) -> tuple[RollingSnapshot, ...]:
    snapshot_dir = output_dir / SNAPSHOT_DIRECTORY
    _require_regular_directory(snapshot_dir, "frozen snapshot directory")
    paths = sorted(snapshot_dir.glob("*.json"), key=lambda path: path.name)
    snapshots: list[RollingSnapshot] = []
    for path in paths:
        _require_regular_file(path, "frozen snapshot")
        payload = _read_json(path)
        if set(payload) != _SNAPSHOT_JSON_KEYS:
            raise ValueError(f"frozen snapshot {path.name} has unknown or missing keys")
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
        expected_fingerprint = _snapshot_input_fingerprint(snapshot)
        if snapshot.input_fingerprint != expected_fingerprint:
            raise ValueError(f"frozen snapshot {path.name} has an invalid fingerprint")
        expected_full_fingerprint = _snapshot_full_fingerprint(snapshot)
        payload_full_fingerprint = canonical_json_fingerprint(
            {
                "asset_id": payload["asset_id"],
                "origin_date": payload["origin_date"],
                "history": payload["history"],
                "future_timestamps": payload["future_timestamps"],
                "realized": payload["realized"],
                "status": payload["status"],
                "reason": payload["reason"],
            }
        )
        if payload_full_fingerprint != expected_full_fingerprint:
            raise ValueError(f"frozen snapshot {path.name} has an invalid full fingerprint")
        snapshots.append(snapshot)
    return tuple(snapshots)


def _snapshot_filename(snapshot: RollingSnapshot) -> str:
    return f"{snapshot.asset_id}__{snapshot.origin_date}.json"


def _snapshot_input_fingerprint(snapshot: RollingSnapshot) -> str:
    return canonical_json_fingerprint(
        {
            "asset_id": snapshot.asset_id,
            "origin_date": snapshot.origin_date,
            "history": thaw_json_value(snapshot.history),
        }
    )


def _snapshot_full_fingerprint(snapshot: RollingSnapshot) -> str:
    return canonical_json_fingerprint(
        {
            "asset_id": snapshot.asset_id,
            "origin_date": snapshot.origin_date,
            "history": thaw_json_value(snapshot.history),
            "future_timestamps": list(snapshot.future_timestamps),
            "realized": thaw_json_value(snapshot.realized),
            "status": snapshot.status,
            "reason": snapshot.reason,
        }
    )


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
        "snapshot_fingerprint": _snapshot_full_fingerprint(snapshot),
        "model_identity": "",
        "weights_identity": "",
        "health_model_identity": "",
        "health_weights_identity": "",
        "health_model_raw_identity": "",
        "health_weights_raw_identity": "",
        "response_model_identity": "",
        "response_weights_identity": "",
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
        "forecast_fingerprint": "",
        "realized_fingerprint": "",
        "cache_hit": False,
        "generation": "",
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
    try:
        _validate_health_model_identity(health, model)
    except _RunnerFailure as exc:
        raise _RunnerFailure(
            str(exc),
            status="unavailable",
            category=exc.category,
            code=exc.code,
            raw_response=health,
        ) from exc
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
    (
        health_identity,
        health_weights,
        health_model_raw,
        health_weights_raw,
    ) = _health_identity_values(health, model)
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
        "snapshot_fingerprint": _snapshot_full_fingerprint(snapshot),
        "model_identity": health_identity,
        "weights_identity": health_weights,
        "health_model_identity": health_identity,
        "health_weights_identity": health_weights,
        "health_model_raw_identity": health_model_raw,
        "health_weights_raw_identity": health_weights_raw,
        "response_model_identity": "",
        "response_weights_identity": "",
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
        "forecast_fingerprint": "",
        "realized_fingerprint": "",
        "cache_hit": False,
        "generation": "",
    }


def _unavailable_row_update(
    snapshot: RollingSnapshot,
    model: str,
    parameters: Mapping[str, Any],
    failure: _RunnerFailure,
) -> dict[str, Any]:
    finished_at = _now_iso()
    return {
        "run_key": f"{snapshot.key}|{model}",
        "snapshot_key": snapshot.key,
        "asset_id": snapshot.asset_id,
        "origin_date": snapshot.origin_date,
        "model": model,
        "status": "unavailable",
        "reason": str(failure),
        "error_category": failure.category,
        "error_code": failure.code,
        "input_fingerprint": snapshot.input_fingerprint,
        "snapshot_fingerprint": _snapshot_full_fingerprint(snapshot),
        "model_identity": "",
        "weights_identity": "",
        "health_model_identity": "",
        "health_weights_identity": "",
        "health_model_raw_identity": "",
        "health_weights_raw_identity": "",
        "response_model_identity": "",
        "response_weights_identity": "",
        "parameters_json": _canonical_json(parameters),
        "sample_count": parameters.get("sample_count", ""),
        "seed": parameters.get("seed"),
        "started_at": finished_at,
        "finished_at": finished_at,
        "latency_ms": "",
        "health_metadata_json": "",
        "raw_response_json": _canonical_json(failure.raw_response or {}),
        "raw_body_excerpt": failure.raw_body_excerpt or "",
        "forecast_artifact": "",
        "realized_artifact": "",
        "forecast_row_count": 0,
        "realized_row_count": 0,
        "forecast_fingerprint": "",
        "realized_fingerprint": "",
        "cache_hit": False,
        "generation": "",
    }


def _manifest_cache_matches(
    row: Mapping[str, Any],
    snapshot: RollingSnapshot,
    model: str,
    parameters: Mapping[str, Any],
    health: Mapping[str, Any] | None,
    forecast_rows: Sequence[Mapping[str, Any]],
    realized_rows: Sequence[Mapping[str, Any]],
) -> bool:
    if row.get("status") != _SUCCESS_MANIFEST_STATUS:
        return False
    try:
        _validate_report_success_identity(row, model)
    except ValueError:
        return False
    if (
        not _valid_iso_timestamp(row.get("started_at"))
        or not _valid_iso_timestamp(row.get("finished_at"))
        or _finite_number(row.get("latency_ms")) is None
        or _finite_number(row.get("latency_ms")) < 0
        or row.get("reason") not in (None, "")
        or row.get("error_category") not in (None, "")
        or row.get("error_code") not in (None, "")
    ):
        return False
    if row.get("input_fingerprint") != snapshot.input_fingerprint:
        return False
    if row.get("snapshot_fingerprint") != _snapshot_full_fingerprint(snapshot):
        return False
    if row.get("model") != model:
        return False
    if row.get("forecast_artifact") != FORECAST_FILENAME:
        return False
    if row.get("realized_artifact") != REALIZED_FILENAME:
        return False
    if _parse_json_cell(row.get("parameters_json")) != _jsonable(dict(parameters)):
        return False
    if _as_int(row.get("sample_count")) != int(parameters["sample_count"]):
        return False
    if _optional_int(row.get("seed")) != parameters.get("seed"):
        return False
    if health is not None:
        current_identity, current_weights, _, _ = _health_identity_values(health, model)
        if not current_weights:
            # A model family alone is not a stable loaded-weights identity.
            # Preserve the successful artifacts, but require a healthy
            # rerun when the service cannot attest to its weights/build.
            return False
        stored_identity = str(row.get("model_identity") or "")
        stored_weights = str(row.get("weights_identity") or "")
        if (
            not stored_weights
            or stored_identity != current_identity
            or stored_weights != current_weights
        ):
            return False
    run_key = f"{snapshot.key}|{model}"
    forecast_for_run = [item for item in forecast_rows if item.get("run_key") == run_key]
    realized_for_run = [item for item in realized_rows if item.get("run_key") == run_key]
    if _as_int(row.get("forecast_row_count")) != len(forecast_for_run):
        return False
    if _as_int(row.get("realized_row_count")) != len(realized_for_run):
        return False
    if len(forecast_for_run) != len(snapshot.future_timestamps):
        return False
    if len(realized_for_run) != len(snapshot.realized):
        return False
    if any(set(item) != set(FORECAST_COLUMNS) for item in forecast_for_run):
        return False
    if any(set(item) != set(REALIZED_COLUMNS) for item in realized_for_run):
        return False
    if not row.get("forecast_fingerprint") or not row.get("realized_fingerprint"):
        return False
    if _artifact_fingerprint(forecast_for_run, FORECAST_COLUMNS) != row.get(
        "forecast_fingerprint"
    ):
        return False
    if _artifact_fingerprint(realized_for_run, REALIZED_COLUMNS) != row.get(
        "realized_fingerprint"
    ):
        return False
    return _validate_cached_artifact_rows(
        snapshot,
        model,
        row,
        forecast_for_run,
        realized_for_run,
    )


def _validate_cached_artifact_rows(
    snapshot: RollingSnapshot,
    model: str,
    manifest_row: Mapping[str, Any],
    forecast_rows: Sequence[Mapping[str, Any]],
    realized_rows: Sequence[Mapping[str, Any]],
) -> bool:
    expected_identity = str(manifest_row.get("model_identity") or "")
    expected_weights = str(manifest_row.get("weights_identity") or "")
    expected_timestamps = tuple(snapshot.future_timestamps)
    forecast_by_horizon: dict[int, Mapping[str, Any]] = {}
    canonical_path_json: str | None = None
    for item in forecast_rows:
        horizon = _as_int(item.get("horizon"))
        if horizon is None or horizon in forecast_by_horizon:
            return False
        if not 1 <= horizon <= len(expected_timestamps):
            return False
        forecast_by_horizon[horizon] = item
        if (
            item.get("asset_id") != snapshot.asset_id
            or item.get("origin_date") != snapshot.origin_date
            or item.get("model") != model
            or item.get("run_key") != f"{snapshot.key}|{model}"
            or item.get("input_fingerprint") != snapshot.input_fingerprint
            or item.get("timestamp") != expected_timestamps[horizon - 1]
            or item.get("status") != _SUCCESS_MANIFEST_STATUS
            or str(item.get("model_identity") or "") != expected_identity
            or str(item.get("weights_identity") or "") != expected_weights
            or _as_int(item.get("sample_count"))
            != _as_int(manifest_row.get("sample_count"))
            or _optional_int(item.get("seed")) != _optional_int(manifest_row.get("seed"))
        ):
            return False
        quantiles = [
            _finite_number(item.get(field_name))
            for field_name in ("p10", "p50", "p90")
        ]
        if any(value is None for value in quantiles):
            return False
        p10, p50, p90 = quantiles
        if not p10 <= p50 <= p90:  # type: ignore[operator]
            return False
        path = _parse_representative_path_json(item.get("representative_path_json"))
        if path is None or not _validate_representative_path(path, expected_timestamps):
            return False
        serialized_path = _canonical_json(path)
        if item.get("representative_path_json") != serialized_path:
            return False
        if canonical_path_json is None:
            canonical_path_json = serialized_path
        elif canonical_path_json != serialized_path:
            return False
        representative = path[horizon - 1]
        for field_name in (
            "open",
            "high",
            "low",
            "close",
            "volume",
            "amount",
        ):
            if _finite_number(item.get(f"representative_{field_name}")) != _finite_number(
                representative[field_name]
            ):
                return False
        if not _validate_forecast_ohlc(
            representative["open"],
            representative["high"],
            representative["low"],
            representative["close"],
        ):
            return False
        if item.get("cuda") not in (None, True, False):
            return False

    if set(forecast_by_horizon) != set(range(1, len(expected_timestamps) + 1)):
        return False

    realized_by_horizon: dict[int, Mapping[str, Any]] = {}
    for item in realized_rows:
        horizon = _as_int(item.get("horizon"))
        if horizon is None or horizon in realized_by_horizon:
            return False
        if not 1 <= horizon <= len(snapshot.realized):
            return False
        realized_by_horizon[horizon] = item
        source = thaw_json_value(snapshot.realized[horizon - 1])
        if (
            item.get("asset_id") != snapshot.asset_id
            or item.get("origin_date") != snapshot.origin_date
            or item.get("model") != model
            or item.get("run_key") != f"{snapshot.key}|{model}"
            or item.get("input_fingerprint") != snapshot.input_fingerprint
            or item.get("timestamp") != source.get("timestamp")
            or item.get("status") != _SUCCESS_MANIFEST_STATUS
            or str(item.get("model_identity") or "") != expected_identity
            or str(item.get("weights_identity") or "") != expected_weights
            or _as_int(item.get("sample_count"))
            != _as_int(manifest_row.get("sample_count"))
            or _optional_int(item.get("seed")) != _optional_int(manifest_row.get("seed"))
        ):
            return False
        for field_name in ("open", "high", "low", "close", "volume", "amount"):
            actual = _finite_number(item.get(field_name))
            expected = _finite_number(source.get(field_name))
            if actual is None or expected is None or actual != expected:
                return False
        if not _validate_forecast_ohlc(
            item.get("open"),
            item.get("high"),
            item.get("low"),
            item.get("close"),
        ):
            return False

    return set(realized_by_horizon) == set(range(1, len(snapshot.realized) + 1))


def _validate_artifact_generation(
    manifest: Mapping[str, Mapping[str, Any]],
    forecast_rows: Sequence[Mapping[str, Any]],
    realized_rows: Sequence[Mapping[str, Any]],
    forecast_generation: str | None,
    realized_generation: str | None,
    forecast_schema: Sequence[Sequence[Any]],
    realized_schema: Sequence[Sequence[Any]],
) -> None:
    manifest_generations = {
        str(row.get("generation", ""))
        for row in manifest.values()
    }
    if len(manifest_generations) != 1 or "" in manifest_generations:
        raise ValueError("artifact generation marker is missing or mixed in manifest")
    manifest_generation = next(iter(manifest_generations))
    if forecast_generation != manifest_generation or realized_generation != manifest_generation:
        raise ValueError("artifact generation markers are mixed")
    expected_generation = _artifact_generation(
        list(manifest.values()),
        forecast_rows,
        realized_rows,
        forecast_schema=forecast_schema,
        realized_schema=realized_schema,
    )
    if expected_generation != manifest_generation:
        raise ValueError("authenticated artifact generation digest mismatch")


def _validate_report_artifacts(
    snapshots: Sequence[RollingSnapshot],
    manifest: Mapping[str, Mapping[str, Any]],
    config: KronosEvaluationConfig,
    forecast_rows: Sequence[Mapping[str, Any]],
    realized_rows: Sequence[Mapping[str, Any]],
) -> None:
    expected_by_key = {
        f"{snapshot.key}|{model}": (snapshot, model)
        for snapshot in snapshots
        for model in config.models
    }
    forecast_by_key: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    realized_by_key: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for artifact_name, rows, grouped in (
        (FORECAST_FILENAME, forecast_rows, forecast_by_key),
        (REALIZED_FILENAME, realized_rows, realized_by_key),
    ):
        for row in rows:
            run_key = str(row.get("run_key", ""))
            if run_key not in expected_by_key:
                raise ValueError(f"{artifact_name} contains an out-of-experiment run key")
            grouped[run_key].append(row)

    for run_key, (snapshot, model) in expected_by_key.items():
        manifest_row = manifest[run_key]
        status = manifest_row.get("status")
        if status not in _TERMINAL_MANIFEST_STATUSES:
            raise ValueError(
                f"run manifest row {run_key} has non-terminal or unknown status {status!r}"
            )
        if status == _SUCCESS_MANIFEST_STATUS:
            _validate_report_success_identity(manifest_row, model)
            if not _manifest_cache_matches(
                manifest_row,
                snapshot,
                model,
                _prediction_parameters(config, snapshot),
                None,
                forecast_rows,
                realized_rows,
            ):
                raise ValueError(f"artifact validation failed for successful run {run_key}")
        elif forecast_by_key.get(run_key) or realized_by_key.get(run_key):
            raise ValueError(f"failed run {run_key} has stale artifact rows")


def _validate_existing_report_artifacts(
    output_dir: Path,
    artifact_generation: str,
) -> None:
    paths = [output_dir / filename for filename in _REPORT_PUBLISHED_FILENAMES]
    for path in paths:
        _reject_symlink(path, "derived report artifact")
    existing = [path for path in paths if path.exists()]
    if not existing:
        return
    if len(existing) != len(paths):
        raise ValueError("derived report artifacts are incomplete")

    for filename in (
        METRICS_BY_STOCK_FILENAME,
        METRICS_BY_MODEL_FILENAME,
        MODEL_COMPARISON_FILENAME,
    ):
        path = output_dir / filename
        _require_regular_file(path, "derived report artifact")
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            expected_columns = (
                _METRIC_OUTPUT_COLUMNS
                if filename != MODEL_COMPARISON_FILENAME
                else _COMPARISON_OUTPUT_COLUMNS
            )
            if reader.fieldnames != list(expected_columns):
                raise ValueError(f"derived report artifact {filename} columns are invalid")
            rows = list(reader)
        if any(row.get("generation") != artifact_generation for row in rows):
            raise ValueError(f"derived report artifact {filename} generation is stale")

    report_path = output_dir / REPORT_FILENAME
    _require_regular_file(report_path, "report.md")
    report = report_path.read_text(encoding="utf-8")
    marker = f"Artifact generation: `{artifact_generation}`"
    if marker not in report:
        raise ValueError("report.md generation is stale or missing")

    digest_payload = _read_json(output_dir / REPORT_DIGEST_FILENAME)
    if set(digest_payload) != {"schema_version", "generation", "files"}:
        raise ValueError("report digest manifest fields are invalid")
    if digest_payload.get("schema_version") != _REPORT_DIGEST_SCHEMA_VERSION:
        raise ValueError("unsupported report digest manifest schema")
    if digest_payload.get("generation") != artifact_generation:
        raise ValueError("report digest manifest generation is stale")
    stored_digests = digest_payload.get("files")
    if not isinstance(stored_digests, Mapping) or set(stored_digests) != set(
        _DERIVED_REPORT_FILENAMES
    ):
        raise ValueError("report digest manifest file set is invalid")
    for filename in _DERIVED_REPORT_FILENAMES:
        stored_digest = stored_digests.get(filename)
        if (
            not isinstance(stored_digest, str)
            or len(stored_digest) != hashlib.sha256().digest_size * 2
            or any(character not in "0123456789abcdef" for character in stored_digest)
        ):
            raise ValueError(f"report digest manifest entry {filename} is invalid")
        actual_digest = _report_file_digest(output_dir / filename)
        if actual_digest != stored_digest:
            raise ValueError(f"derived report artifact {filename} content digest mismatch")


def _invalidate_derived_report_artifacts_locked(output_dir: Path) -> None:
    _recover_report_invalidation_locked(output_dir)
    paths = [output_dir / filename for filename in _REPORT_PUBLISHED_FILENAMES]
    for path in paths:
        _reject_symlink(path, "derived report artifact")
    if not any(path.exists() for path in paths):
        return

    transaction_id = uuid.uuid4().hex
    writer_owner = _active_writer_owner(output_dir) or {}
    journal: dict[str, Any] = {
        "schema_version": _REPORT_INVALIDATION_SCHEMA_VERSION,
        "transaction_id": transaction_id,
        "journal_temp": f".{REPORT_INVALIDATION_FILENAME}.{transaction_id}.tmp",
        "state": "prepared",
        "owner": {
            "owner_id": transaction_id,
            "writer_owner_id": writer_owner.get("owner_id", ""),
            "pid": os.getpid(),
            "output_dir": str(output_dir.resolve(strict=False)),
            "lock_path": str(_writer_lock_path(output_dir).resolve(strict=False)),
        },
        "files": [
            {
                "final": filename,
                "state": "planned" if (output_dir / filename).exists() else "deleted",
            }
            for filename in _REPORT_PUBLISHED_FILENAMES
        ],
    }
    _persist_report_invalidation_journal(output_dir, journal)
    _recover_report_invalidation_locked(output_dir)


def _validate_report_success_identity(
    manifest_row: Mapping[str, Any],
    requested_model: str,
) -> None:
    """Validate persisted success identity without relying on live health."""

    stored_identity = str(manifest_row.get("model_identity") or "")
    health_identity = str(manifest_row.get("health_model_identity") or "")
    stored_parts = _model_identity_parts(stored_identity)
    health_parts = _model_identity_parts(health_identity)
    requested_family = _model_family_from_identity(requested_model)
    if stored_parts is None or health_parts is None:
        raise ValueError(
            "successful run is missing a recognized stored model identity"
        )
    if stored_parts[0] != requested_family or health_parts[0] != requested_family:
        raise ValueError("successful run model identity does not match requested model")
    if not _identity_values_compatible(stored_identity, health_identity):
        raise ValueError("successful run stored and health model identities disagree")

    manifest_payloads: list[tuple[str, Any]] = [
        (
            "manifest",
            {
                "model_identity": stored_identity,
                "weights_identity": manifest_row.get("weights_identity", ""),
            },
        ),
        (
            "manifest_health",
            {
                "model_identity": health_identity,
                "weights_identity": manifest_row.get("health_weights_identity", ""),
            },
        ),
    ]
    response_identity = manifest_row.get("response_model_identity")
    response_weights = manifest_row.get("response_weights_identity")
    if response_identity not in (None, "") or response_weights not in (None, ""):
        manifest_payloads.append(
            (
                "manifest_response",
                {
                    "model_identity": response_identity,
                    "weights_identity": response_weights,
                },
            )
        )
    for source_name, field_name in (
        ("health_metadata", "health_metadata_json"),
        ("raw_response", "raw_response_json"),
    ):
        payload = _parse_json_cell(manifest_row.get(field_name))
        if payload not in (None, ""):
            if not isinstance(payload, Mapping):
                raise ValueError(f"successful run {field_name} is not a JSON object")
            manifest_payloads.append((source_name, payload))
    try:
        validation = validate_identity_payloads(manifest_payloads, requested_model)
    except IdentityValidationError as exc:
        raise ValueError(f"successful run model identity is invalid: {exc}") from exc
    if not validation.model_records:
        raise ValueError("successful run has no recognized model identity")


def _artifact_fingerprint(
    rows: Sequence[Mapping[str, Any]],
    columns: Sequence[str],
) -> str:
    canonical_rows = [
        {
            column: _canonical_artifact_value(column, row.get(column))
            for column in columns
        }
        for row in _sort_artifact_rows(rows)
    ]
    return canonical_json_fingerprint(canonical_rows)


_ARTIFACT_FLOAT_COLUMNS = frozenset(
    {
        "representative_open",
        "representative_high",
        "representative_low",
        "representative_close",
        "representative_volume",
        "representative_amount",
        "p10",
        "p50",
        "p90",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "amount",
    }
)
_ARTIFACT_INT_COLUMNS = frozenset({"horizon", "sample_count", "seed"})


def _canonical_artifact_value(column: str, value: Any) -> Any:
    if value is None:
        return None
    if column in _ARTIFACT_FLOAT_COLUMNS:
        numeric = _finite_number(value)
        return numeric if numeric is not None else _jsonable(value)
    if column in _ARTIFACT_INT_COLUMNS:
        integer = _as_int(value)
        return integer if integer is not None else _jsonable(value)
    if column == "cuda":
        return value if isinstance(value, bool) else _jsonable(value)
    if column in {
        "asset_id",
        "origin_date",
        "model",
        "run_key",
        "input_fingerprint",
        "timestamp",
        "representative_path_json",
        "status",
        "model_identity",
        "weights_identity",
        "device",
    }:
        return str(value)
    return _jsonable(value)


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

    _validate_response_model_identity(response, health, model, raw_response)
    _validate_response_parameters(
        response,
        expected_horizon=len(snapshot.future_timestamps),
        sample_count=config.sample_count,
        raw_response=raw_response,
    )
    quantiles = _extract_quantiles(response)
    expected_length = len(snapshot.future_timestamps)
    representative_path = _extract_representative_path(
        response,
        snapshot.future_timestamps,
        raw_response,
    )
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

    # Health is the canonical cache/artifact identity.  Response identities
    # are retained separately in the manifest as audit metadata.
    identity, weights, _, _ = _health_identity_values(health, model)
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
            "representative_open": representative_path[horizon - 1]["open"],
            "representative_high": representative_path[horizon - 1]["high"],
            "representative_low": representative_path[horizon - 1]["low"],
            "representative_close": representative_path[horizon - 1]["close"],
            "representative_volume": representative_path[horizon - 1]["volume"],
            "representative_amount": representative_path[horizon - 1]["amount"],
            "representative_path_json": _canonical_json(representative_path),
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
    daily = _extract_daily(response)
    result = response.get("result")
    if isinstance(daily, Mapping):
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


def _validate_response_parameters(
    response: Mapping[str, Any],
    *,
    expected_horizon: int,
    sample_count: int,
    raw_response: Mapping[str, Any],
) -> None:
    daily = _extract_daily(response)
    result = response.get("result")
    mappings = (
        ("response", response),
        ("result", result if isinstance(result, Mapping) else {}),
        ("daily", daily if isinstance(daily, Mapping) else {}),
    )
    for location, source in mappings:
        if "sample_count" in source:
            value = source.get("sample_count")
            if isinstance(value, bool) or not isinstance(value, int):
                raise _RunnerFailure(
                    f"Kronos prediction sample_count at {location} is invalid",
                    status="protocol_error",
                    category="protocol",
                    code="invalid_response",
                    raw_response=raw_response,
                )
            if value != sample_count:
                raise _RunnerFailure(
                    f"Kronos prediction sample_count at {location} mismatches request",
                    status="model_error",
                    category="model",
                    code="sample_count_mismatch",
                    raw_response=raw_response,
                )
        for field_name in ("horizon", "forecast_horizon"):
            if field_name not in source:
                continue
            value = source.get(field_name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise _RunnerFailure(
                    f"Kronos prediction {field_name} at {location} is invalid",
                    status="protocol_error",
                    category="protocol",
                    code="invalid_response",
                    raw_response=raw_response,
                )
            if value != expected_horizon:
                raise _RunnerFailure(
                    f"Kronos prediction {field_name} at {location} mismatches forecast",
                    status="model_error",
                    category="model",
                    code="horizon_mismatch",
                    raw_response=raw_response,
                )


def _extract_daily(response: Mapping[str, Any]) -> Mapping[str, Any] | None:
    daily: Any = response.get("daily")
    result = response.get("result")
    if daily is None and isinstance(result, Mapping):
        daily = result.get("daily")
    return daily if isinstance(daily, Mapping) else None


def _extract_representative_path(
    response: Mapping[str, Any],
    expected_timestamps: Sequence[str],
    raw_response: Mapping[str, Any],
) -> list[dict[str, Any]]:
    daily = _extract_daily(response)
    candidate = daily.get("representative_path") if daily is not None else None
    if candidate is None:
        result = response.get("result")
        if isinstance(result, Mapping):
            result_daily = result.get("daily")
            if isinstance(result_daily, Mapping):
                candidate = result_daily.get("representative_path")
    if not isinstance(candidate, (list, tuple)):
        raise _RunnerFailure(
            "Kronos prediction response has no representative daily path",
            status="protocol_error",
            category="protocol",
            code="invalid_representative_path",
            raw_response=raw_response,
        )
    normalized: list[dict[str, Any]] = []
    for index, source in enumerate(candidate):
        if not isinstance(source, Mapping):
            raise _RunnerFailure(
                "Kronos representative path contains a non-object row",
                status="protocol_error",
                category="protocol",
                code="invalid_representative_path",
                raw_response=raw_response,
            )
        timestamp = source.get("timestamp")
        if not isinstance(timestamp, str) or not timestamp:
            raise _RunnerFailure(
                f"Kronos representative path row {index + 1} has no timestamp",
                status="protocol_error",
                category="protocol",
                code="invalid_representative_path",
                raw_response=raw_response,
            )
        row = {"timestamp": timestamp}
        for field_name in ("open", "high", "low", "close", "volume", "amount"):
            numeric = _finite_number(source.get(field_name))
            if numeric is None:
                raise _RunnerFailure(
                    f"Kronos representative path row {index + 1} has invalid {field_name}",
                    status="protocol_error",
                    category="protocol",
                    code="invalid_representative_path",
                    raw_response=raw_response,
                )
            row[field_name] = numeric
        normalized.append(row)
    if len(normalized) != len(expected_timestamps) or not _validate_representative_path(
        normalized,
        expected_timestamps,
    ):
        raise _RunnerFailure(
            "Kronos representative path has an invalid horizon or OHLCV shape",
            status="protocol_error",
            category="protocol",
            code="invalid_representative_path",
            raw_response=raw_response,
        )
    return normalized


def _parse_representative_path_json(value: Any) -> list[dict[str, Any]] | None:
    parsed = _parse_json_cell(value)
    if not isinstance(parsed, list):
        return None
    normalized: list[dict[str, Any]] = []
    for item in parsed:
        if not isinstance(item, Mapping):
            return None
        normalized.append(dict(item))
    return normalized


def _validate_representative_path(
    path: Sequence[Mapping[str, Any]],
    expected_timestamps: Sequence[str],
) -> bool:
    required_fields = {"timestamp", "open", "high", "low", "close", "volume", "amount"}
    if len(path) != len(expected_timestamps):
        return False
    for index, row in enumerate(path):
        if set(row) != required_fields or row.get("timestamp") != expected_timestamps[index]:
            return False
        for field_name in ("open", "high", "low", "close", "volume", "amount"):
            if _finite_number(row.get(field_name)) is None:
                return False
        if not _validate_forecast_ohlc(
            row.get("open"),
            row.get("high"),
            row.get("low"),
            row.get("close"),
        ):
            return False
    return True


def _validate_forecast_ohlc(
    open_value: Any,
    high_value: Any,
    low_value: Any,
    close_value: Any,
) -> bool:
    open_numeric = _finite_number(open_value)
    high_numeric = _finite_number(high_value)
    low_numeric = _finite_number(low_value)
    close_numeric = _finite_number(close_value)
    if any(value is None for value in (open_numeric, high_numeric, low_numeric, close_numeric)):
        return False
    return (
        high_numeric >= max(open_numeric, close_numeric)
        and low_numeric <= min(open_numeric, close_numeric)
        and high_numeric >= low_numeric
    )


def _response_model_metadata(response: Mapping[str, Any]) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    for _, key, value in _iter_identity_fields(response):
        if key not in metadata:
            metadata[key] = value
    for _, key, value in _iter_metadata_fields(response):
        if key not in metadata:
            metadata[key] = value
    return metadata


def _response_identity_value(
    response_metadata: Mapping[str, Any],
    kind: str,
) -> str | None:
    fields = (
        ("model_identity", "model_name", "model")
        if kind == "model"
        else ("weights_identity", "weights_fingerprint", "weights")
    )
    for field_name in fields:
        value = response_metadata.get(field_name)
        if value in (None, ""):
            continue
        return (
            _canonical_json(value)
            if isinstance(value, (Mapping, list, tuple))
            else str(value)
        )
    return None


def _validate_health_model_identity(
    health: Mapping[str, Any],
    requested_model: str,
) -> None:
    validation = _validate_model_identity_payloads(
        (("health", health),),
        requested_model,
        health,
    )
    if not validation.model_records:
        raise _RunnerFailure(
            "Kronos health metadata is missing an explicit model family",
            status="unavailable",
            category="model",
            code="missing_health_model_identity",
            raw_response=health,
        )


def _validate_response_model_identity(
    response: Mapping[str, Any],
    health: Mapping[str, Any],
    requested_model: str,
    raw_response: Mapping[str, Any],
) -> None:
    _validate_model_identity_payloads(
        (("health", health), ("response", response)),
        requested_model,
        raw_response,
    )


def _validate_model_identity_payloads(
    payloads: Sequence[tuple[str, Mapping[str, Any]]],
    requested_model: str,
    raw_response: Mapping[str, Any],
) -> Any:
    try:
        return validate_identity_payloads(payloads, requested_model)
    except IdentityValidationError as exc:
        is_health = any(source == "health" for source, _ in payloads)
        is_response = any(source == "response" for source, _ in payloads)
        is_model_failure = exc.code in {
            "model_identity_mismatch",
            "weights_identity_mismatch",
            "model_identity_version_mismatch",
            "weights_identity_version_mismatch",
        }
        raise _RunnerFailure(
            str(exc),
            status=("unavailable" if is_health and not is_response else "model_error")
            if is_model_failure
            else "protocol_error",
            category="model" if is_model_failure else "protocol",
            code=(
                "model_mismatch"
                if is_health and not is_response and exc.code == "model_identity_mismatch"
                else exc.code
            ),
            raw_response=raw_response,
        ) from exc


def _iter_identity_fields(
    value: Any,
    path: str = "",
    seen: set[int] | None = None,
) -> Iterable[tuple[str, str, Any]]:
    yield from _shared_iter_identity_fields(value, path, seen)


def _iter_metadata_fields(
    value: Any,
    path: str = "",
    seen: set[int] | None = None,
) -> Iterable[tuple[str, str, Any]]:
    if seen is None:
        seen = set()
    if isinstance(value, Mapping):
        object_id = id(value)
        if object_id in seen:
            return
        seen.add(object_id)
        for key, item in value.items():
            if not isinstance(key, str):
                continue
            location = f"{path}.{key}" if path else key
            if key in {"device", "cuda", "cuda_available"}:
                yield location, key, item
            if isinstance(item, (Mapping, list, tuple)):
                yield from _iter_metadata_fields(item, location, seen)
    elif isinstance(value, (list, tuple)):
        object_id = id(value)
        if object_id in seen:
            return
        seen.add(object_id)
        for index, item in enumerate(value):
            if isinstance(item, (Mapping, list, tuple)):
                yield from _iter_metadata_fields(item, f"{path}[{index}]", seen)


def _normalize_model_identity(value: Any) -> str | None:
    return _model_family_from_identity(value)


def _model_family_from_identity(value: Any) -> str | None:
    return _shared_model_family(value)


def _model_identity_parts(
    value: Any,
    *,
    allow_weight_prefix: bool = False,
) -> tuple[str, str | None] | None:
    return _shared_model_identity_parts(
        value,
        allow_weight_prefix=allow_weight_prefix,
    )


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
            "health_model_identity": set(),
            "health_weights_identity": set(),
            "health_model_raw_identity": set(),
            "health_weights_raw_identity": set(),
            "response_model_identity": set(),
            "response_weights_identity": set(),
            "device": set(),
            "cuda": set(),
        }
    )
    for row in manifest.values():
        model = str(row.get("model", ""))
        health = _parse_json_cell(row.get("health_metadata_json"))
        for field in (
            "model_identity",
            "weights_identity",
            "health_model_identity",
            "health_weights_identity",
            "health_model_raw_identity",
            "health_weights_raw_identity",
            "response_model_identity",
            "response_weights_identity",
        ):
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


def _metric_summary_row(
    summary: Mapping[str, Any],
    *,
    generation: str,
) -> dict[str, Any]:
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
    row["generation"] = generation
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
    artifact_generation: str,
) -> str:
    lines = [
        "# Kronos rolling evaluation report",
        "",
        f"Conclusion: `{conclusion}`",
        "",
        f"Experiment fingerprint: `{metadata.get('experiment_fingerprint', '')}`",
        "",
        f"Artifact generation: `{artifact_generation}`",
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
    normalized_output_dir = Path(output_dir)
    with _writer_lock(normalized_output_dir):
        _write_run_artifacts_locked(
            normalized_output_dir,
            manifest,
            forecast_rows,
            realized_rows,
        )


def _write_run_artifacts_locked(
    output_dir: Path,
    manifest: Mapping[str, Mapping[str, Any]],
    forecast_rows: Sequence[Mapping[str, Any]],
    realized_rows: Sequence[Mapping[str, Any]],
) -> None:
    _recover_pending_transaction_locked(output_dir)
    normalized_manifest = [manifest[key] for key in sorted(manifest)]
    normalized_forecast = _sort_artifact_rows(forecast_rows)
    normalized_realized = _sort_artifact_rows(realized_rows)
    _reject_symlink(output_dir, "experiment output directory")
    output_dir.mkdir(parents=True, exist_ok=True)
    _require_regular_directory(output_dir, "experiment output directory")
    final_paths = [
        output_dir / MANIFEST_FILENAME,
        output_dir / FORECAST_FILENAME,
        output_dir / REALIZED_FILENAME,
    ]
    staged_paths: list[Path] = []
    backup_paths: list[Path] = []
    backup_paths_by_index: list[Path | None] = []
    journal_published = False
    journal_planned = False
    transaction_path = output_dir / TRANSACTION_FILENAME
    transaction_id = uuid.uuid4().hex
    try:
        pa, _ = _load_pyarrow()
        forecast_schema = _schema_signature(_artifact_schema(pa, FORECAST_COLUMNS))
        realized_schema = _schema_signature(_artifact_schema(pa, REALIZED_COLUMNS))
        generation = _artifact_generation(
            normalized_manifest,
            normalized_forecast,
            normalized_realized,
            forecast_schema=forecast_schema,
            realized_schema=realized_schema,
        )
        manifest_with_generation = []
        for source in normalized_manifest:
            row = dict(source)
            row["generation"] = generation
            manifest_with_generation.append(row)
        for final_path in final_paths:
            staged_path = output_dir / f".{final_path.name}.{transaction_id}.stage"
            staged_paths.append(staged_path)
        journal_files: list[dict[str, Any]] = []
        for final_path in final_paths:
            _reject_symlink(final_path, "artifact final path")
            had_original = final_path.exists()
            if had_original:
                _require_regular_file(final_path, "artifact final")
            backup_path = (
                output_dir / f".{final_path.name}.{transaction_id}.backup"
                if had_original
                else None
            )
            if backup_path is not None:
                backup_paths.append(backup_path)
            backup_paths_by_index.append(backup_path)
            journal_files.append(
                {
                    "final": final_path.name,
                    "stage": staged_paths[len(journal_files)].name,
                    "temporary": f".{final_path.name}.{transaction_id}.stage.tmp",
                    "backup": backup_path.name if backup_path is not None else "",
                    "had_original": had_original,
                    "final_state": "old",
                    "restore_state": "pending",
                    "stage_state": "planned",
                    "temporary_state": "planned",
                    "backup_state": "planned" if had_original else "none",
                }
            )
        writer_owner = _active_writer_owner(output_dir) or {}
        journal: dict[str, Any] = {
            "schema_version": _TRANSACTION_SCHEMA_VERSION,
            "transaction_id": transaction_id,
            "journal_temp": f".{TRANSACTION_FILENAME}.{transaction_id}.tmp",
            "state": "prepared",
            "owner": {
                "owner_id": transaction_id,
                "writer_owner_id": writer_owner.get("owner_id", ""),
                "pid": os.getpid(),
                "output_dir": str(output_dir.resolve(strict=False)),
                "lock_path": str(_writer_lock_path(output_dir).resolve(strict=False)),
            },
            "files": journal_files,
        }
        journal_planned = True
        try:
            _persist_transaction_journal(output_dir, journal)
        except BaseException:
            journal_published = transaction_path.exists()
            raise
        journal_published = True

        _atomic_write_csv(
            staged_paths[0],
            manifest_with_generation,
            MANIFEST_COLUMNS,
            temporary_path=output_dir / journal_files[0]["temporary"],
        )
        journal_files[0]["stage_state"] = "present"
        journal_files[0]["temporary_state"] = "deleted"
        _persist_transaction_journal(output_dir, journal)
        _atomic_write_table(
            staged_paths[1],
            normalized_forecast,
            FORECAST_COLUMNS,
            generation=generation,
            temporary_path=output_dir / journal_files[1]["temporary"],
        )
        journal_files[1]["stage_state"] = "present"
        journal_files[1]["temporary_state"] = "deleted"
        _persist_transaction_journal(output_dir, journal)
        _atomic_write_table(
            staged_paths[2],
            normalized_realized,
            REALIZED_COLUMNS,
            generation=generation,
            temporary_path=output_dir / journal_files[2]["temporary"],
        )
        journal_files[2]["stage_state"] = "present"
        journal_files[2]["temporary_state"] = "deleted"
        _persist_transaction_journal(output_dir, journal)

        for index, final_path in enumerate(final_paths):
            backup_path = backup_paths_by_index[index]
            if backup_path is None:
                continue
            _reject_symlink(backup_path, "transaction backup path")
            if backup_path.exists():
                raise FileExistsError(f"transaction backup path already exists: {backup_path}")
            _copy_file_durable(final_path, backup_path)
            journal_files[index]["backup_state"] = "present"
            _persist_transaction_journal(output_dir, journal)

        journal["state"] = "committing"
        _persist_transaction_journal(output_dir, journal)
        _commit_staged_artifacts(staged_paths, final_paths)
        for raw_entry in journal_files:
            raw_entry["final_state"] = "new"
            raw_entry["stage_state"] = "present"
        journal["state"] = "committed"
        _persist_transaction_journal(output_dir, journal)
        _recover_pending_transaction_locked(output_dir)
        if (output_dir / EXPERIMENT_FILENAME).exists():
            _invalidate_derived_report_artifacts_locked(output_dir)
    finally:
        if not journal_published and not journal_planned:
            for path in (*staged_paths, *backup_paths):
                _unlink_transaction_path(path)
            _unlink_transaction_path(transaction_path)
        elif not journal_published:
            # The journal write may have failed before replacing its target.
            # Clean only paths that were planned by this transaction; if the
            # journal exists, leave it for the normal recovery path.
            if not transaction_path.exists():
                for path in (*staged_paths, *backup_paths):
                    _unlink_transaction_path(path)


def _artifact_generation(
    manifest_rows: Sequence[Mapping[str, Any]],
    forecast_rows: Sequence[Mapping[str, Any]],
    realized_rows: Sequence[Mapping[str, Any]],
    *,
    forecast_schema: Sequence[Sequence[Any]] | None = None,
    realized_schema: Sequence[Sequence[Any]] | None = None,
) -> str:
    volatile_manifest_fields = {
        "started_at",
        "finished_at",
        "latency_ms",
        "generation",
    }
    stable_manifest = [
        {
            column: _canonical_manifest_value(row.get(column))
            for column in MANIFEST_COLUMNS
            if column not in volatile_manifest_fields
        }
        for row in sorted(manifest_rows, key=lambda item: str(item.get("run_key", "")))
    ]
    return canonical_json_fingerprint(
        {
            "schema": {
                "forecast": [list(item) for item in (forecast_schema or _declared_schema_signature(FORECAST_COLUMNS))],
                "realized": [list(item) for item in (realized_schema or _declared_schema_signature(REALIZED_COLUMNS))],
            },
            "manifest": stable_manifest,
            "forecast": [
                {
                    column: _canonical_artifact_value(column, row.get(column))
                    for column in FORECAST_COLUMNS
                }
                for row in forecast_rows
            ],
            "realized": [
                {
                    column: _canonical_artifact_value(column, row.get(column))
                    for column in REALIZED_COLUMNS
                }
                for row in realized_rows
            ],
        }
    )


def _canonical_manifest_value(value: Any) -> str:
    serialized = _csv_value(value)
    return "" if serialized is None else str(serialized)


def _declared_schema_signature(columns: Sequence[str]) -> tuple[tuple[str, str, bool], ...]:
    type_names = {
        "horizon": "int64",
        "sample_count": "int64",
        "seed": "int64",
        "cuda": "bool",
    }
    float_columns = {
        "representative_open",
        "representative_high",
        "representative_low",
        "representative_close",
        "representative_volume",
        "representative_amount",
        "p10",
        "p50",
        "p90",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "amount",
    }
    return tuple(
        (
            column,
            "double" if column in float_columns else type_names.get(column, "string"),
            True,
        )
        for column in columns
    )


def _schema_signature(schema: Any) -> tuple[tuple[str, str, bool], ...]:
    return tuple(
        (str(field.name), str(field.type), bool(field.nullable))
        for field in schema
    )


def _staged_path(final_path: Path) -> Path:
    with tempfile.NamedTemporaryFile(
        mode="wb",
        dir=final_path.parent,
        prefix=f".{final_path.name}.",
        suffix=".stage",
        delete=False,
    ) as handle:
        staged_path = Path(handle.name)
    staged_path.unlink()
    return staged_path


def _commit_staged_artifacts(
    staged_paths: Sequence[Path],
    final_paths: Sequence[Path],
) -> None:
    if len(staged_paths) != len(final_paths):
        raise ValueError("staged and final artifact path counts differ")
    for staged_path, final_path in zip(staged_paths, final_paths):
        os.replace(staged_path, final_path)


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
    _require_regular_file(path, "run_manifest.csv")
    with path.open(newline="", encoding="utf-8") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _read_table(path: Path, columns: Sequence[str] | None = None) -> list[dict[str, Any]]:
    rows, _, _ = _read_table_with_generation(path, columns)
    return rows


def _read_table_with_generation(
    path: Path,
    columns: Sequence[str] | None = None,
) -> tuple[list[dict[str, Any]], str | None, tuple[tuple[str, str, bool], ...]]:
    _require_regular_file(path, "Parquet artifact")
    pa, parquet = _load_pyarrow()
    try:
        table = parquet.read_table(path)
        if columns is not None:
            expected_schema = _artifact_schema(pa, columns)
            if not table.schema.equals(expected_schema, check_metadata=False):
                raise ValueError(f"Parquet artifact {path} has an invalid schema")
        schema_signature = _schema_signature(table.schema)
        metadata = table.schema.metadata or {}
        raw_generation = metadata.get(b"kronos_generation")
        generation = raw_generation.decode("utf-8") if raw_generation is not None else None
        return [dict(row) for row in table.to_pylist()], generation, schema_signature
    except Exception as exc:  # noqa: BLE001 - preserve a clear artifact failure.
        raise RuntimeError(f"failed to read Parquet artifact {path}: {exc}") from exc


def _atomic_write_json(
    path: Path,
    value: Any,
    *,
    temporary_path: Path | None = None,
) -> None:
    _atomic_write_text(
        path,
        _canonical_json(value) + "\n",
        temporary_path=temporary_path,
    )


def _atomic_write_text(
    path: Path,
    value: str,
    *,
    temporary_path: Path | None = None,
) -> None:
    _atomic_write_bytes(
        path,
        value.encode("utf-8"),
        temporary_path=temporary_path,
    )


def _atomic_write_csv(
    path: Path,
    rows: Sequence[Mapping[str, Any]],
    columns: Sequence[str],
    *,
    temporary_path: Path | None = None,
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
    _atomic_write_text(path, buffer.getvalue(), temporary_path=temporary_path)


def _artifact_schema(pa: Any, columns: Sequence[str]) -> Any:
    arrow_types = {
        "asset_id": pa.string(),
        "origin_date": pa.string(),
        "model": pa.string(),
        "run_key": pa.string(),
        "input_fingerprint": pa.string(),
        "timestamp": pa.string(),
        "horizon": pa.int64(),
        "representative_open": pa.float64(),
        "representative_high": pa.float64(),
        "representative_low": pa.float64(),
        "representative_close": pa.float64(),
        "representative_volume": pa.float64(),
        "representative_amount": pa.float64(),
        "representative_path_json": pa.string(),
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
    return pa.schema(
        [pa.field(column, arrow_types.get(column, pa.string())) for column in columns]
    )


def _atomic_write_table(
    path: Path,
    rows: Sequence[Mapping[str, Any]],
    columns: Sequence[str],
    *,
    generation: str | None = None,
    temporary_path: Path | None = None,
) -> None:
    pa, parquet = _load_pyarrow()
    schema = _artifact_schema(pa, columns)
    if generation is not None:
        schema = schema.with_metadata({b"kronos_generation": generation.encode("utf-8")})
    normalized_rows = [
        {column: _pyarrow_value(row.get(column)) for column in columns}
        for row in rows
    ]
    table = pa.Table.from_pylist(normalized_rows, schema=schema)
    path.parent.mkdir(parents=True, exist_ok=True)
    _require_regular_directory(path.parent, "artifact parent directory")
    _reject_symlink(path, "Parquet artifact")
    temporary = (
        Path(temporary_path)
        if temporary_path is not None
        else path.parent / f".{path.name}.tmp"
    )
    if temporary.parent != path.parent:
        raise ValueError("Parquet temporary path must share the artifact parent")
    _reject_symlink(temporary, "Parquet temporary path")
    try:
        parquet.write_table(
            table,
            temporary,
            compression=None,
            use_dictionary=False,
            write_statistics=False,
        )
        with temporary.open("rb") as handle:
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        if temporary.exists():
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass


def _load_pyarrow() -> tuple[Any, Any]:
    try:
        import pyarrow as pa
        import pyarrow.parquet as parquet
    except (ImportError, ModuleNotFoundError) as exc:
        raise RuntimeError(
            "pyarrow is required to read/write Kronos Parquet artifacts"
        ) from exc
    return pa, parquet


def _atomic_write_bytes(
    path: Path,
    value: bytes,
    *,
    temporary_path: Path | None = None,
) -> None:
    _reject_symlink(path, "artifact path")
    path.parent.mkdir(parents=True, exist_ok=True)
    _require_regular_directory(path.parent, "artifact parent directory")
    temporary = (
        Path(temporary_path)
        if temporary_path is not None
        else path.parent / f".{path.name}.tmp"
    )
    if temporary.parent != path.parent:
        raise ValueError("atomic temporary path must share the artifact parent")
    _reject_symlink(temporary, "atomic temporary path")
    try:
        with temporary.open("wb") as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        if temporary.exists():
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass


def _read_json(path: Path) -> dict[str, Any]:
    _require_regular_file(path, "JSON artifact")
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


def _config_from_payload(payload: Mapping[str, Any]) -> KronosEvaluationConfig:
    try:
        values = {field.name: payload[field.name] for field in fields(KronosEvaluationConfig)}
        return KronosEvaluationConfig(**values)
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("experiment config metadata is invalid") from exc


def _require_config(config: KronosEvaluationConfig) -> None:
    if not isinstance(config, KronosEvaluationConfig):
        raise TypeError("config must be a KronosEvaluationConfig")


def _normalize_model(model: Any) -> str:
    normalized = _normalize_model_alias(model)
    if normalized not in {"small", "base"}:
        raise ValueError("model must be small or base")
    return normalized


def _normalize_model_alias(model: Any) -> str:
    return _model_family_from_identity(model) or ""


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


def _valid_iso_timestamp(value: Any) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        datetime.fromisoformat(value)
    except ValueError:
        return False
    return True


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
    if response_metadata:
        value = _explicit_identity(response_metadata)
        if value is not None:
            return value
    if health:
        value = _health_model_identity(health)
        if value is not None:
            return value
    return None


def _health_model_identity(source: Mapping[str, Any]) -> str | None:
    records = []
    for _, field, value in _iter_identity_fields(source):
        if field not in {"model", "model_identity", "model_name"}:
            continue
        if _model_identity_parts(value) is not None:
            records.append(value)
    if not records:
        return None
    versioned = [value for value in records if _model_identity_parts(value)[1] is not None]
    return canonical_identity(versioned[0] if versioned else records[0])


def _explicit_identity(source: Mapping[str, Any]) -> str | None:
    return explicit_model_identity(source)


def _identity_values_compatible(left: Any, right: Any) -> bool:
    """Compare model identities while treating family-only values as wildcards."""

    if left in (None, "") or right in (None, ""):
        return left in (None, "") and right in (None, "")
    left_parts = _model_identity_parts(left)
    right_parts = _model_identity_parts(right)
    if left_parts is None or right_parts is None:
        return str(left) == str(right)
    if left_parts[0] != right_parts[0]:
        return False
    return (
        left_parts[1] is None
        or right_parts[1] is None
        or left_parts[1] == right_parts[1]
    )


def _first_weight_identity(
    response_metadata: Mapping[str, Any],
    health: Mapping[str, Any],
) -> str | None:
    for source in (response_metadata, health):
        value = _explicit_weight_identity(source)
        if value is not None:
            return value
    return None


def _explicit_weight_identity(source: Mapping[str, Any]) -> str | None:
    value = explicit_weight_identity(source)
    if value is None:
        return None
    return value


def _identity_raw_value(records: Sequence[Any]) -> str:
    values: list[Any] = []
    for record in records:
        if record.value in (None, "") or record.value in values:
            continue
        values.append(record.value)
    if not values:
        return ""
    if len(values) == 1:
        value = values[0]
        return _canonical_json(value) if isinstance(value, (Mapping, list, tuple)) else str(value)
    return _canonical_json(values)


def _cache_identity_from_records(
    records: Sequence[Any],
    *,
    allow_weight_prefix: bool,
) -> str:
    recognized = [record for record in records if record.family in {"small", "base"}]
    versioned = [record for record in recognized if record.version is not None]
    if recognized:
        value = canonical_identity(
            (versioned or recognized)[0].value,
            allow_weight_prefix=allow_weight_prefix,
        )
        if value is not None:
            return value
    return _identity_raw_value(records)


def _health_identity_values(
    health: Mapping[str, Any],
    requested_model: str,
) -> tuple[str, str, str, str]:
    validation = _validate_model_identity_payloads(
        (("health", health),),
        requested_model,
        health,
    )
    if not validation.model_records:
        raise _RunnerFailure(
            "Kronos health metadata is missing an explicit model family",
            status="unavailable",
            category="model",
            code="missing_health_model_identity",
            raw_response=health,
        )
    model_records = (*validation.model_records, *validation.opaque_model_records)
    weight_records = (*validation.weight_records, *validation.opaque_weight_records)
    model_identity = _cache_identity_from_records(
        validation.model_records,
        allow_weight_prefix=False,
    )
    weights_identity = _cache_identity_from_records(
        weight_records,
        allow_weight_prefix=True,
    )
    if not model_identity:
        raise _RunnerFailure(
            "Kronos health metadata has no usable model cache identity",
            status="unavailable",
            category="model",
            code="missing_health_model_identity",
            raw_response=health,
        )
    return (
        model_identity,
        weights_identity,
        _identity_raw_value(model_records),
        _identity_raw_value(weight_records),
    )


def _raw_response_for_manifest(response: Mapping[str, Any] | None) -> Mapping[str, Any]:
    if not isinstance(response, Mapping):
        return {}
    try:
        from stock_research.kronos_evaluation_client import complete_raw_response
    except (ImportError, ModuleNotFoundError):
        complete_raw_response = None  # type: ignore[assignment]
    if complete_raw_response is not None:
        complete = complete_raw_response(response)
        if isinstance(complete, Mapping):
            return complete
    marker_slot = response.get(_CLIENT_RAW_RESPONSE_SLOT_MARKER)
    if isinstance(marker_slot, str):
        complete_response = response.get(marker_slot)
        if isinstance(complete_response, Mapping):
            return complete_response
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
