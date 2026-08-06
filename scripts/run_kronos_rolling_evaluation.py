#!/usr/bin/env python3
"""Run the frozen Kronos rolling-evaluation experiment in three stages.

The command intentionally keeps preparation, prediction, and reporting
separate.  After ``prepare`` has frozen the experiment directory, ``predict``
does not read the database, the current dashboard, or a live universe file.
It only loads the prepared metadata and lets the existing runner consume the
frozen snapshots.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from dataclasses import fields as dataclass_fields
from pathlib import Path
from typing import Any, Mapping, NoReturn, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from stock_research.kronos_evaluation_runner import (
    EXPERIMENT_FILENAME,
    SNAPSHOT_DIRECTORY,
    build_report,
    prepare_experiment,
    run_model,
)
from stock_research.kronos_evaluation_types import (
    DEFAULT_KRONOS_SEED,
    KronosEvaluationConfig,
    normalize_asset_ids,
)


# Keep parser/prepare/report usable in lightweight test environments where the
# optional HTTP dependency is not installed.  The real client is imported only
# when the predict stage is selected; tests can replace this name with a fake.
KronosClient: Any = None


_ASSET_COLUMNS = ("asset_id", "code", "stock_code", "ts_code", "symbol", "ticker")
_EXCHANGE_COLUMNS = ("exchange", "market", "exchange_code")
_BARE_ASSET_RE = re.compile(r"^\d{6}$")
_STAGES = ("prepare", "predict", "report")


class _CliArgumentParser(argparse.ArgumentParser):
    """Let ``main`` render parser failures in the normal JSON envelope."""

    def error(self, message: str) -> NoReturn:
        raise ValueError(message)


def build_parser() -> argparse.ArgumentParser:
    parser = _CliArgumentParser(
        description="Run the Kronos small/base rolling evaluation experiment."
    )
    subparsers = parser.add_subparsers(dest="stage", required=True)

    prepare_parser = subparsers.add_parser(
        "prepare",
        help="freeze historical snapshots and initialize experiment artifacts",
    )
    prepare_parser.add_argument("--universe-file", type=Path, required=True)
    prepare_parser.add_argument("--start-date", required=True)
    prepare_parser.add_argument("--end-date", required=True)
    prepare_parser.add_argument("--output-dir", type=Path, required=True)
    prepare_parser.add_argument("--input-window", type=int, default=250)
    prepare_parser.add_argument("--forecast-horizon", type=int, default=10)
    prepare_parser.add_argument(
        "--horizons",
        nargs="+",
        default=["1", "3", "5", "10"],
        help="evaluation horizons, as comma-separated or separate integers",
    )
    prepare_parser.add_argument("--sample-count", type=int, default=20)
    prepare_parser.add_argument("--seed", type=int, default=DEFAULT_KRONOS_SEED)
    prepare_parser.add_argument("--adjust-type", default="qfq")
    prepare_parser.add_argument("--db-service", default="stock_research")
    prepare_parser.add_argument("--timeout-seconds", type=float, default=60.0)
    prepare_parser.add_argument("--allow-smoke", action="store_true")

    predict_parser = subparsers.add_parser(
        "predict",
        help="run one requested model over the prepared frozen snapshots",
    )
    predict_parser.add_argument("--model", choices=("small", "base"), required=True)
    predict_parser.add_argument("--output-dir", type=Path, required=True)
    predict_parser.add_argument("--predict-url", required=True)
    predict_parser.add_argument("--token-env")

    report_parser = subparsers.add_parser(
        "report",
        help="build metrics, comparison, and report artifacts",
    )
    report_parser.add_argument("--output-dir", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    stage = _stage_from_argv(argv)
    try:
        args = parser.parse_args(argv)
        stage = args.stage
        if args.stage == "prepare":
            summary = _run_prepare(args)
        elif args.stage == "predict":
            summary = _run_predict(args)
        elif args.stage == "report":
            summary = _run_report(args)
        else:  # pragma: no cover - argparse enforces the stage choices.
            raise ValueError(f"unsupported stage: {args.stage!r}")
    except Exception as exc:  # noqa: BLE001 - CLI converts failures to one JSON line.
        _print_summary(
            {
                "stage": stage or "unknown",
                "status": "error",
                "error": str(exc) or exc.__class__.__name__,
            }
        )
        return 1

    _print_summary(summary)
    return 1 if summary.get("status") == "error" else 0


def _run_prepare(args: argparse.Namespace) -> dict[str, Any]:
    asset_ids = _read_universe(args.universe_file)
    if len(asset_ids) != 20 and not args.allow_smoke:
        raise ValueError(
            "normalized universe must contain exactly 20 assets; "
            "pass --allow-smoke only for a smaller fixture"
        )

    config = KronosEvaluationConfig(
        asset_ids=asset_ids,
        start_date=args.start_date,
        end_date=args.end_date,
        input_window=args.input_window,
        forecast_horizon=args.forecast_horizon,
        evaluation_horizons=_parse_horizons(args.horizons),
        sample_count=args.sample_count,
        adjust_type=args.adjust_type,
        db_service=args.db_service,
        timeout_seconds=args.timeout_seconds,
        seed=args.seed,
    )
    result = prepare_experiment(config, output_dir=args.output_dir)
    return {
        "stage": "prepare",
        "status": "ok",
        "output_dir": str(args.output_dir),
        "asset_count": len(config.asset_ids),
        "snapshot_count": int(result.snapshot_count),
        "status_counts": dict(result.status_counts),
    }


def _run_predict(args: argparse.Namespace) -> dict[str, Any]:
    output_dir = Path(args.output_dir)
    metadata_path = _validate_predict_output_dir(output_dir)
    metadata = _read_json_object(metadata_path)
    config = _config_from_metadata(metadata)

    token_env = args.token_env or config.token_env
    token = os.environ.get(token_env)
    if not token:
        raise ValueError(f"missing Kronos token in environment variable {token_env}")

    client_class = KronosClient
    if client_class is None:
        try:
            from stock_research.kronos_evaluation_client import (  # noqa: PLC0415
                KronosClient as client_class,
            )
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "Kronos predict dependencies are unavailable; install requests"
            ) from exc

    client = client_class(
        args.predict_url,
        token=token,
        timeout=config.timeout_seconds,
    )
    try:
        # This is an explicit preflight.  A mismatch is a hard CLI failure;
        # the runner is never allowed to silently use another model.
        client.assert_model(args.model)
        result = run_model(
            config,
            model=args.model,
            output_dir=output_dir,
            client=client,
        )
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            close()

    status_counts = dict(result.status_counts)
    status = _predict_summary_status(status_counts)
    summary = {
        "stage": "predict",
        "status": status,
        "model": args.model,
        "output_dir": str(output_dir),
        "attempted_count": int(result.attempted_count),
        "cache_hit_count": int(result.cache_hit_count),
        "skipped_count": int(result.skipped_count),
        "status_counts": status_counts,
    }
    if status == "error":
        summary["error"] = "all prediction units failed"
    return summary


def _validate_predict_output_dir(output_dir: Path) -> Path:
    _reject_cli_symlink(output_dir, "experiment output directory")
    if not output_dir.exists():
        raise FileNotFoundError(f"missing experiment output directory: {output_dir}")
    if not output_dir.is_dir():
        raise ValueError(
            f"experiment output directory must be a directory: {output_dir}"
        )

    metadata_path = output_dir / EXPERIMENT_FILENAME
    _reject_cli_symlink(metadata_path, "experiment metadata")
    if not metadata_path.exists():
        raise FileNotFoundError(
            f"prepared experiment metadata is missing: {metadata_path}"
        )
    if not metadata_path.is_file():
        raise ValueError(
            f"experiment metadata must be a regular file: {metadata_path}"
        )

    snapshot_dir = output_dir / SNAPSHOT_DIRECTORY
    _reject_cli_symlink(snapshot_dir, "frozen snapshot directory")
    if not snapshot_dir.exists():
        raise FileNotFoundError(f"missing frozen snapshot directory: {snapshot_dir}")
    if not snapshot_dir.is_dir():
        raise ValueError(
            f"frozen snapshot directory must be a directory: {snapshot_dir}"
        )
    return metadata_path


def _reject_cli_symlink(path: Path, label: str) -> None:
    if path.is_symlink():
        raise ValueError(f"{label} must not be a symlink: {path}")


def _predict_summary_status(status_counts: Mapping[str, int]) -> str:
    total_count = sum(int(value) for value in status_counts.values())
    success_count = int(status_counts.get("success", 0))
    if total_count <= 0 or success_count <= 0:
        return "error"
    if success_count < total_count:
        return "partial"
    return "ok"


def _run_report(args: argparse.Namespace) -> dict[str, Any]:
    report = build_report(output_dir=args.output_dir)
    summary = dict(report)
    summary.update(
        {
            "stage": "report",
            "status": "ok",
            "output_dir": str(args.output_dir),
        }
    )
    return summary


def _read_universe(path: Path) -> tuple[str, ...]:
    if not path.is_file():
        raise FileNotFoundError(f"universe file does not exist: {path}")
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fieldnames = tuple(reader.fieldnames or ())
        if not fieldnames:
            raise ValueError(f"universe file has no header: {path}")
        rows = list(reader)

    raw_asset_ids: list[str] = []
    for row_number, row in enumerate(rows, start=2):
        raw_value = _first_non_empty(row, _ASSET_COLUMNS)
        if raw_value is None:
            raise ValueError(
                f"universe row {row_number} has no asset_id/code/symbol value"
            )
        exchange = _first_non_empty(row, _EXCHANGE_COLUMNS)
        if _BARE_ASSET_RE.fullmatch(raw_value) and exchange:
            raw_value = f"{exchange}.{raw_value}"
        raw_asset_ids.append(raw_value)

    normalized = normalize_asset_ids(raw_asset_ids)
    if not normalized:
        raise ValueError(f"universe file contains no assets: {path}")
    return normalized


def _first_non_empty(row: Mapping[str, Any], names: Sequence[str]) -> str | None:
    for name in names:
        value = row.get(name)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _parse_horizons(values: Sequence[str] | str) -> tuple[int, ...]:
    if isinstance(values, str):
        values = (values,)
    tokens: list[str] = []
    for value in values:
        tokens.extend(part.strip() for part in str(value).split(","))
    if not tokens or any(not token for token in tokens):
        raise ValueError("horizons must contain one or more positive integers")
    try:
        horizons = tuple(int(token) for token in tokens)
    except ValueError as exc:
        raise ValueError("horizons must contain only integers") from exc
    return horizons


def _config_from_metadata(metadata: Mapping[str, Any]) -> KronosEvaluationConfig:
    payload = metadata.get("config")
    if not isinstance(payload, Mapping):
        raise ValueError("experiment.json is missing config metadata")
    try:
        values = {
            field.name: payload[field.name]
            for field in dataclass_fields(KronosEvaluationConfig)
        }
    except KeyError as exc:
        raise ValueError("experiment.json config metadata is incomplete") from exc
    return KronosEvaluationConfig(**values)


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid experiment metadata {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"experiment metadata must be a JSON object: {path}")
    return value


def _stage_from_argv(argv: list[str] | None) -> str | None:
    arguments = sys.argv[1:] if argv is None else argv
    if not arguments:
        return None
    candidate = str(arguments[0])
    return candidate if candidate in _STAGES else None


def _print_summary(summary: Mapping[str, Any]) -> None:
    print(
        json.dumps(
            dict(summary),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
