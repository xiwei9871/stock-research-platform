#!/usr/bin/env python3
"""Run one validated, configuration-driven Kronos rolling experiment.

The legacy ``run_kronos_rolling_evaluation.py`` entry point remains available
for callers that already have a frozen output directory.  This entry point is
the higher-level workflow: it resolves the configured data boundary, freezes a
universe and snapshot calendar during ``prepare``, invokes exactly one
configured model during ``predict``, and builds the report during ``report``.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import tempfile
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from stock_research.kronos_evaluation_runner import (
    EXPERIMENT_CONFIG_FILENAME,
    EXPERIMENT_FILENAME,
    FORECAST_FILENAME,
    LATEST_FORECAST_FILENAME,
    MANIFEST_FILENAME,
    REPORT_FILENAME,
    SNAPSHOT_DIRECTORY,
    UNIVERSE_SELECTION_FILENAME,
    build_report,
    prepare_experiment,
    run_model,
)
from stock_research.kronos_evaluation_types import KronosEvaluationConfig, normalize_asset_ids
from stock_research.kronos_experiment_config import (
    KronosExperimentSpec,
    canonical_spec_payload,
    load_experiment_spec,
)
from stock_research.kronos_experiment_universe import (
    UniverseSelection,
    load_trade_calendar_dates,
    resolve_latest_market_date,
    select_universe,
)

try:
    from stock_research.kronos_evaluation_client import KronosClient as _KronosClient
except ModuleNotFoundError:  # pragma: no cover - allows parser-only environments.
    _KronosClient = None


# These names are deliberately module-level seams.  Tests and offline tools
# can replace them without opening a PostgreSQL connection or a real GPU
# service, while the production defaults still use the existing modules.
KronosClient: Any = _KronosClient
OUTPUT_ROOT = REPO_ROOT / "outputs" / "research" / "kronos_rolling_eval"
_STAGES = ("prepare", "predict", "report", "run")


class _JsonArgumentParser(argparse.ArgumentParser):
    """Turn argparse validation failures into the CLI's single JSON line."""

    def error(self, message: str) -> None:  # pragma: no cover - exercised by main.
        raise ValueError(f"argument error: {message}")


def build_parser() -> argparse.ArgumentParser:
    parser = _JsonArgumentParser(
        description="run a validated configuration-driven Kronos experiment"
    )
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--stage", choices=_STAGES, required=True)
    parser.add_argument(
        "--resume",
        action="store_true",
        help="continue an existing experiment only when its fingerprint matches",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    stage = _stage_hint(argv)
    try:
        args = parser.parse_args(argv)
        stage = args.stage
        summary = run_experiment(
            args.config,
            stage=args.stage,
            resume=args.resume,
        )
    except Exception as exc:  # noqa: BLE001 - CLI must emit one structured result.
        summary = {
            "stage": stage,
            "status": "error",
            "error": str(exc) or exc.__class__.__name__,
        }
        _print_summary(summary)
        return 1

    _print_summary(summary)
    return 1 if summary.get("status") == "error" else 0


def run_experiment(
    spec_path: Path,
    *,
    stage: str,
    resume: bool = False,
) -> dict[str, Any]:
    """Run one stage of a validated experiment and return a JSON-ready summary."""

    if stage not in _STAGES:
        raise ValueError(f"unsupported stage: {stage!r}")
    spec = load_experiment_spec(Path(spec_path))
    output_dir = _output_dir(spec)
    _validate_output_target(output_dir)

    exists = output_dir.exists()
    if exists and not resume:
        raise FileExistsError(
            f"experiment directory already exists: {output_dir}; "
            "use --resume only with the same config fingerprint"
        )

    if exists:
        context = _load_existing_context(spec, output_dir)
    else:
        if stage not in {"prepare", "run"}:
            raise FileNotFoundError(
                f"experiment directory is not prepared: {output_dir}"
            )
        context = _new_context(spec, output_dir)

    preparation: Any = None
    if stage in {"prepare", "run"}:
        preparation = prepare_experiment(
            context["config"],
            output_dir=output_dir,
            snapshot_loader=context["snapshot_loader"],
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        if not exists:
            _write_experiment_sidecars(
                spec,
                context,
                output_dir,
                resume=resume,
            )
        else:
            _validate_sidecars(spec, context, output_dir)

    if stage == "prepare":
        return _preparation_summary(spec, context, preparation, output_dir)

    prediction_summary: dict[str, Any] | None = None
    if stage in {"predict", "run"}:
        prediction_summary = _predict_stage(spec, context, output_dir)

    if stage in {"report", "run"}:
        report_summary = _report_stage(spec, context, output_dir)
    else:
        report_summary = None

    if stage == "predict":
        return prediction_summary or _error_summary(stage, "prediction did not run")
    if stage == "report":
        return report_summary or _error_summary(stage, "report did not run")

    assert prediction_summary is not None
    assert report_summary is not None
    status = "ok"
    if prediction_summary.get("status") == "error":
        status = "error"
    elif prediction_summary.get("status") == "partial":
        status = "partial"
    combined = dict(report_summary)
    combined.update(
        {
            "stage": "run",
            "status": status,
            "prediction": prediction_summary,
        }
    )
    return combined


def _new_context(spec: KronosExperimentSpec, output_dir: Path) -> dict[str, Any]:
    resolved_end_date = (
        resolve_latest_market_date(
            adjust_type=spec.adjust_type,
            service="stock_research",
        )
        if spec.end_date_latest
        else spec.end_date
    )
    if resolved_end_date is None:  # pragma: no cover - guarded by the loader.
        raise ValueError("resolved end_date is missing")
    cutoff_date = (
        date.fromisoformat(spec.start_date) - timedelta(days=1)
    ).isoformat()
    selection = select_universe(
        mode=spec.universe_mode,
        count=spec.universe_count,
        seed=spec.universe_seed,
        market=spec.market,
        asset_ids=spec.asset_ids if spec.universe_mode == "explicit" else None,
        adjust_type=spec.adjust_type,
        input_window=spec.input_window,
        cutoff_date=cutoff_date,
        service="stock_research",
    )
    if len(selection.asset_ids) != spec.universe_count:
        raise ValueError(
            "universe selector returned "
            f"{len(selection.asset_ids)} assets; expected {spec.universe_count}"
        )
    config = spec.to_evaluation_config(
        asset_ids=selection.asset_ids,
        end_date=resolved_end_date,
    )
    return {
        "config": config,
        "selection": selection,
        "resolved_end_date": resolved_end_date,
        "cutoff_date": cutoff_date,
        "output_dir": output_dir,
        "snapshot_loader": _make_snapshot_loader(spec, resolved_end_date),
    }


def _load_existing_context(
    spec: KronosExperimentSpec,
    output_dir: Path,
) -> dict[str, Any]:
    config_sidecar = _read_json_object(output_dir / EXPERIMENT_CONFIG_FILENAME)
    selection_sidecar = _read_json_object(output_dir / UNIVERSE_SELECTION_FILENAME)
    _require_matching_fingerprint(config_sidecar, spec.config_fingerprint, "experiment_config.json")
    _require_matching_fingerprint(selection_sidecar, spec.config_fingerprint, "universe_selection.json")

    resolved_end_date = config_sidecar.get("resolved", {}).get("end_date")
    if not isinstance(resolved_end_date, str):
        raise ValueError("experiment_config.json is missing resolved end_date")
    try:
        resolved_end_date = date.fromisoformat(resolved_end_date).isoformat()
    except ValueError as exc:
        raise ValueError("experiment_config.json has an invalid resolved end_date") from exc
    if spec.end_date is not None and resolved_end_date != spec.end_date:
        raise ValueError(
            "resolved end_date does not match the supplied configuration"
        )

    raw_asset_ids = selection_sidecar.get("asset_ids")
    if raw_asset_ids is None and isinstance(selection_sidecar.get("selection"), Mapping):
        raw_asset_ids = selection_sidecar["selection"].get("asset_ids")
    asset_ids = normalize_asset_ids(raw_asset_ids or ())
    if len(asset_ids) != spec.universe_count:
        raise ValueError("frozen universe count does not match the supplied configuration")
    config = spec.to_evaluation_config(asset_ids=asset_ids, end_date=resolved_end_date)
    experiment_path = output_dir / EXPERIMENT_FILENAME
    if not experiment_path.is_file():
        raise FileNotFoundError(f"prepared experiment metadata is missing: {experiment_path}")
    return {
        "config": config,
        "selection": selection_sidecar,
        "resolved_end_date": resolved_end_date,
        "cutoff_date": config_sidecar.get("resolved", {}).get("universe_cutoff_date"),
        "output_dir": output_dir,
        "snapshot_loader": _make_snapshot_loader(spec, resolved_end_date),
    }


def _validate_sidecars(
    spec: KronosExperimentSpec,
    context: Mapping[str, Any],
    output_dir: Path,
) -> None:
    config_sidecar = _read_json_object(output_dir / EXPERIMENT_CONFIG_FILENAME)
    selection_sidecar = _read_json_object(output_dir / UNIVERSE_SELECTION_FILENAME)
    _require_matching_fingerprint(config_sidecar, spec.config_fingerprint, "experiment_config.json")
    _require_matching_fingerprint(selection_sidecar, spec.config_fingerprint, "universe_selection.json")
    if config_sidecar.get("resolved", {}).get("end_date") != context["resolved_end_date"]:
        raise ValueError("experiment_config.json resolved end_date is incompatible")


def _write_experiment_sidecars(
    spec: KronosExperimentSpec,
    context: Mapping[str, Any],
    output_dir: Path,
    *,
    resume: bool,
) -> None:
    selection = context["selection"]
    selection_payload = (
        _jsonable(asdict(selection))
        if isinstance(selection, UniverseSelection)
        else _jsonable(selection)
    )
    if not isinstance(selection_payload, dict):
        raise ValueError("universe selection is not JSON-serializable")
    selection_payload.update(
        {
            "experiment_id": spec.experiment_id,
            "config_fingerprint": spec.config_fingerprint,
            "resolved_end_date": context["resolved_end_date"],
            "universe_cutoff_date": context["cutoff_date"],
        }
    )
    config_payload = {
        "schema_version": 1,
        "experiment_id": spec.experiment_id,
        "config_fingerprint": spec.config_fingerprint,
        "spec": canonical_spec_payload(spec),
        "resolved": {
            "end_date": context["resolved_end_date"],
            "universe_cutoff_date": context["cutoff_date"],
        },
        "provenance": {
            "asset_ids": list(context["config"].asset_ids),
            "frequency": context["config"].frequency,
            "adjust_type": context["config"].adjust_type,
            "model": context["config"].models[0],
            "fallback": context["config"].fallback,
            "sample_count": context["config"].sample_count,
            "input_window": context["config"].input_window,
            "forecast_horizon": context["config"].forecast_horizon,
            "report_horizons": list(context["config"].evaluation_horizons),
            "primary_horizon": context["config"].primary_horizon,
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
    }
    _write_sidecar(
        output_dir / EXPERIMENT_CONFIG_FILENAME,
        config_payload,
        fingerprint=spec.config_fingerprint,
        resume=resume,
    )
    _write_sidecar(
        output_dir / UNIVERSE_SELECTION_FILENAME,
        selection_payload,
        fingerprint=spec.config_fingerprint,
        resume=resume,
    )


def _write_sidecar(
    path: Path,
    payload: Mapping[str, Any],
    *,
    fingerprint: str,
    resume: bool,
) -> None:
    if path.exists():
        existing = _read_json_object(path)
        _require_matching_fingerprint(existing, fingerprint, path.name)
        if not resume:
            raise FileExistsError(f"refusing to overwrite existing sidecar: {path}")
        return
    _atomic_write_json(path, payload)


def _predict_stage(
    spec: KronosExperimentSpec,
    context: Mapping[str, Any],
    output_dir: Path,
) -> dict[str, Any]:
    config = context["config"]
    if config.fallback or config.models != (spec.model_name,):
        raise ValueError("prediction must use exactly one configured model without fallback")
    token = os.environ.get(config.token_env)
    if not token:
        raise ValueError(f"missing Kronos token in environment variable {config.token_env}")
    client_factory = KronosClient
    if client_factory is None:  # pragma: no cover - optional dependency guard.
        raise RuntimeError("Kronos client dependencies are unavailable")
    client = client_factory(
        config.predict_url,
        token=token,
        timeout=config.timeout_seconds,
    )
    try:
        client.assert_model(spec.model_name)
        result = run_model(
            config,
            model=spec.model_name,
            output_dir=output_dir,
            client=client,
        )
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            close()

    status_counts = dict(sorted(getattr(result, "status_counts", {}).items()))
    success_count = int(status_counts.get("success", 0))
    failure_count = sum(
        int(count)
        for status, count in status_counts.items()
        if status in {"model_error", "unavailable", "protocol_error", "timeout", "transport_error"}
    )
    if success_count == 0 and status_counts:
        status = "error"
    elif failure_count:
        status = "partial"
    else:
        status = "ok"
    return {
        "stage": "predict",
        "status": status,
        "experiment_id": spec.experiment_id,
        "output_dir": str(output_dir),
        "frozen_end_date": context["resolved_end_date"],
        "selected_count": len(config.asset_ids),
        "model": spec.model_name,
        "snapshot_count": len(_read_snapshot_payloads(output_dir)),
        "attempted_count": int(getattr(result, "attempted_count", 0)),
        "cache_hit_count": int(getattr(result, "cache_hit_count", 0)),
        "skipped_count": int(getattr(result, "skipped_count", 0)),
        "status_counts": status_counts,
        "primary_horizon_coverage": None,
        "paths": _standard_paths(output_dir),
    }


def _report_stage(
    spec: KronosExperimentSpec,
    context: Mapping[str, Any],
    output_dir: Path,
) -> dict[str, Any]:
    report_value = build_report(output_dir=output_dir)
    report = dict(report_value) if isinstance(report_value, Mapping) else {}
    latest_path = write_latest_forecast(
        output_dir,
        experiment_id=spec.experiment_id,
        config_fingerprint=spec.config_fingerprint,
        model=spec.model_name,
    )
    paths = dict(report.get("paths", {})) if isinstance(report.get("paths"), Mapping) else {}
    paths.update(
        {
            "experiment_config": str(output_dir / EXPERIMENT_CONFIG_FILENAME),
            "universe_selection": str(output_dir / UNIVERSE_SELECTION_FILENAME),
            "latest_forecast": str(latest_path),
            "report": str(output_dir / REPORT_FILENAME),
        }
    )
    status_counts = report.get("status_counts", {})
    return {
        **report,
        "stage": "report",
        "status": "ok",
        "experiment_id": spec.experiment_id,
        "output_dir": str(output_dir),
        "frozen_end_date": context["resolved_end_date"],
        "selected_count": len(context["config"].asset_ids),
        "snapshot_count": len(_read_snapshot_payloads(output_dir)),
        "model": spec.model_name,
        "paths": paths,
        "primary_horizon_coverage": report.get("primary_coverage"),
        "latest_forecast": str(latest_path),
        "status_counts": _jsonable(status_counts),
    }


def write_latest_forecast(
    output_dir: Path,
    *,
    experiment_id: str,
    config_fingerprint: str,
    model: str,
) -> Path:
    """Write the latest-origin forecast sidecar without querying live data."""

    snapshots = _read_snapshot_payloads(output_dir)
    latest_origin = max(
        (str(item.get("origin_date")) for item in snapshots),
        default=None,
    )
    latest_snapshots = [
        item for item in snapshots if item.get("origin_date") == latest_origin
    ]
    manifest_rows = _read_csv_rows(output_dir / MANIFEST_FILENAME)
    manifest_by_run_key = {
        str(row.get("run_key")): row for row in manifest_rows if row.get("run_key")
    }
    forecast_rows = _read_parquet_rows(output_dir / FORECAST_FILENAME)
    forecast_by_key: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for row in forecast_rows:
        key = (
            str(row.get("asset_id")),
            str(row.get("origin_date")),
            str(row.get("model")),
        )
        forecast_by_key.setdefault(key, []).append(_jsonable(row))

    entries: list[dict[str, Any]] = []
    status_counts: Counter[str] = Counter()
    for snapshot in sorted(latest_snapshots, key=lambda item: str(item.get("asset_id"))):
        asset_id = str(snapshot.get("asset_id"))
        origin_date = str(snapshot.get("origin_date"))
        snapshot_status = str(snapshot.get("status", ""))
        status_counts[snapshot_status] += 1
        run_key = f"{asset_id}|{origin_date}|{model}"
        manifest = manifest_by_run_key.get(run_key, {})
        entries.append(
            {
                "asset_id": asset_id,
                "origin_date": origin_date,
                "snapshot_status": snapshot_status,
                "reason": snapshot.get("reason"),
                "future_timestamps": snapshot.get("future_timestamps", []),
                "realized_timestamps": [
                    row.get("timestamp") for row in snapshot.get("realized", [])
                ],
                "realized_horizon_count": len(snapshot.get("realized", [])),
                "pending_horizons": list(
                    range(
                        len(snapshot.get("realized", [])) + 1,
                        len(snapshot.get("future_timestamps", [])) + 1,
                    )
                ),
                "manifest_status": manifest.get("status"),
                "forecast_rows": forecast_by_key.get((asset_id, origin_date, model), []),
            }
        )
    payload = {
        "schema_version": 1,
        "experiment_id": experiment_id,
        "config_fingerprint": config_fingerprint,
        "model": model,
        "latest_origin": latest_origin,
        "status_counts": dict(sorted(status_counts.items())),
        "pending": [
            entry["asset_id"]
            for entry in entries
            if entry["snapshot_status"]
            in {"partial_truth", "forecast_only", "pending_truth", "pending_calendar"}
        ],
        "snapshots": entries,
    }
    path = output_dir / LATEST_FORECAST_FILENAME
    _atomic_write_json(path, payload)
    return path


def _make_snapshot_loader(spec: KronosExperimentSpec, resolved_end_date: str):
    def loader(config: KronosEvaluationConfig):
        from stock_research import kronos_evaluation_data as evaluation_data  # noqa: PLC0415

        frame = evaluation_data.load_daily_bars(
            config.asset_ids,
            resolved_end_date,
            config.adjust_type,
            config.db_service,
        )
        calendar_end_date = (
            date.fromisoformat(resolved_end_date)
            + timedelta(days=max(14, config.forecast_horizon * 4))
        ).isoformat()
        observed_dates = []
        if "trade_date" in frame.columns:
            observed_dates = [
                _jsonable(value) for value in frame["trade_date"].dropna().unique().tolist()
            ]
        trade_dates = load_trade_calendar_dates(
            config.adjust_type,
            config.start_date,
            calendar_end_date,
            config.db_service,
            observed_dates=observed_dates,
            observed_asset_ids=config.asset_ids,
        )
        origin_dates = [
            timestamp
            for timestamp in trade_dates
            if config.start_date <= timestamp <= resolved_end_date
        ][:: config.roll_step]
        if not origin_dates:
            raise ValueError("evaluation period has no trading-day origins")
        latest_origin = origin_dates[-1]
        forecast_only_origins = (
            (latest_origin,) if spec.include_latest_forecast else ()
        )
        snapshots = evaluation_data.build_rolling_snapshots(
            frame,
            trade_dates,
            config.input_window,
            config.forecast_horizon,
            origin_dates=origin_dates,
            asset_ids=config.asset_ids,
            minimum_truth_horizon=config.primary_horizon,
            forecast_only_origins=forecast_only_origins,
        )
        metadata = evaluation_data.build_source_metadata(
            frame,
            adjust_type=config.adjust_type,
            trade_dates=trade_dates,
            minimum_truth_horizon=config.primary_horizon,
            snapshots=snapshots,
        )
        metadata.update(
            {
                "frozen_end_date": resolved_end_date,
                "calendar_end_date": calendar_end_date,
                "origin_count": len(origin_dates),
                "latest_origin": latest_origin,
            }
        )
        return snapshots, metadata

    return loader


def _preparation_summary(
    spec: KronosExperimentSpec,
    context: Mapping[str, Any],
    preparation: Any,
    output_dir: Path,
) -> dict[str, Any]:
    status_counts = dict(getattr(preparation, "status_counts", {}))
    return {
        "stage": "prepare",
        "status": "ok",
        "experiment_id": spec.experiment_id,
        "output_dir": str(output_dir),
        "frozen_end_date": context["resolved_end_date"],
        "selected_count": len(context["config"].asset_ids),
        "model": spec.model_name,
        "snapshot_count": int(getattr(preparation, "snapshot_count", 0)),
        "status_counts": status_counts,
        "primary_horizon_coverage": None,
        "paths": _standard_paths(output_dir),
    }


def _standard_paths(output_dir: Path) -> dict[str, str]:
    return {
        "experiment": str(output_dir / EXPERIMENT_FILENAME),
        "experiment_config": str(output_dir / EXPERIMENT_CONFIG_FILENAME),
        "universe_selection": str(output_dir / UNIVERSE_SELECTION_FILENAME),
        "manifest": str(output_dir / MANIFEST_FILENAME),
        "forecast": str(output_dir / FORECAST_FILENAME),
        "report": str(output_dir / REPORT_FILENAME),
        "latest_forecast": str(output_dir / LATEST_FORECAST_FILENAME),
    }


def _output_dir(spec: KronosExperimentSpec) -> Path:
    return OUTPUT_ROOT / spec.experiment_id


def _validate_output_target(output_dir: Path) -> None:
    if output_dir.is_symlink():
        raise ValueError(f"experiment output directory must not be a symlink: {output_dir}")
    if output_dir.exists() and not output_dir.is_dir():
        raise ValueError(f"experiment output path must be a directory: {output_dir}")


def _read_json_object(path: Path) -> dict[str, Any]:
    if path.is_symlink():
        raise ValueError(f"experiment artifact must not be a symlink: {path}")
    if not path.is_file():
        raise FileNotFoundError(f"missing experiment artifact: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid JSON artifact: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"JSON artifact must contain an object: {path}")
    return value


def _require_matching_fingerprint(
    payload: Mapping[str, Any],
    fingerprint: str,
    label: str,
) -> None:
    actual = payload.get("config_fingerprint")
    if actual != fingerprint:
        raise ValueError(
            f"resume fingerprint mismatch in {label}: "
            f"stored={actual!r}, current={fingerprint!r}"
        )


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
        text=True,
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(_jsonable(payload), handle, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _read_snapshot_payloads(output_dir: Path) -> list[dict[str, Any]]:
    snapshot_dir = output_dir / SNAPSHOT_DIRECTORY
    if not snapshot_dir.is_dir():
        return []
    payloads: list[dict[str, Any]] = []
    for path in sorted(snapshot_dir.glob("*.json")):
        if path.is_symlink():
            raise ValueError(f"frozen snapshot must not be a symlink: {path}")
        payload = _read_json_object(path)
        payloads.append(payload)
    return payloads


def _read_csv_rows(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _read_parquet_rows(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    try:
        import pyarrow.parquet as parquet  # noqa: PLC0415
    except ModuleNotFoundError as exc:  # pragma: no cover - runner also requires it.
        raise RuntimeError("pyarrow is required to read frozen forecast artifacts") from exc
    return [dict(row) for row in parquet.read_table(path).to_pylist()]


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "item") and callable(value.item):
        try:
            return _jsonable(value.item())
        except (ValueError, TypeError):
            pass
    return value


def _print_summary(summary: Mapping[str, Any]) -> None:
    print(json.dumps(_jsonable(summary), ensure_ascii=False, sort_keys=True, allow_nan=False))


def _stage_hint(argv: list[str] | None) -> str:
    values = list(sys.argv[1:] if argv is None else argv)
    for index, value in enumerate(values[:-1]):
        if value == "--stage":
            return values[index + 1]
    return "unknown"


def _error_summary(stage: str, message: str) -> dict[str, Any]:
    return {"stage": stage, "status": "error", "error": message}


if __name__ == "__main__":  # pragma: no cover - exercised through subprocess tests.
    raise SystemExit(main())
