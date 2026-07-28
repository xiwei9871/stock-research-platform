from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from stock_research.config import SETTINGS
from stock_research.data_run_manifest import (
    apply_data_run_manifest_schema,
    load_recent_data_run_manifest,
    upsert_data_run_manifest_with_connection,
)
from stock_research.db import connect

SCHEMA_VERSION = "strategy_manifest_transfer_v1"
REQUIRED_MODULES = {
    "daily_bars",
    "technical_features",
    "score_topn",
    "lhb_features",
    "tech_bottleneck_candidates",
    "strategy_lhb_shortline",
    "strategy_mid_trend",
    "strategy_tech_bottleneck",
    "review_queue_strategy_manifest",
}


def export_strategy_manifest_snapshot(
    *,
    trade_date: str,
    source_root: str | Path,
    target_root: str | Path = "/app",
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    run_id = f"strategy-eod-{trade_date}-local"
    rows = [
        row
        for row in load_recent_data_run_manifest(trade_date=trade_date, service=service)
        if str(row.get("run_id") or "") == run_id
    ]
    _validate_rows(rows, trade_date=trade_date, run_id=run_id)
    return {
        "schema_version": SCHEMA_VERSION,
        "trade_date": trade_date,
        "run_id": run_id,
        "rows": _relocate_value(rows, str(Path(source_root).resolve()), str(target_root)),
    }


def import_strategy_manifest_snapshot(
    payload: dict[str, Any],
    *,
    service: str = SETTINGS.research_service,
) -> int:
    if str(payload.get("schema_version") or "") != SCHEMA_VERSION:
        raise ValueError("unsupported strategy manifest transfer schema")
    trade_date = str(payload.get("trade_date") or "")
    run_id = str(payload.get("run_id") or "")
    rows = list(payload.get("rows") or [])
    _validate_rows(rows, trade_date=trade_date, run_id=run_id)
    apply_data_run_manifest_schema(service=service)
    with connect(service) as conn:
        for row in rows:
            upsert_data_run_manifest_with_connection(row, conn=conn)
    return len(rows)


def _validate_rows(rows: list[dict[str, Any]], *, trade_date: str, run_id: str) -> None:
    expected_run_id = f"strategy-eod-{trade_date}-local"
    if not trade_date or run_id != expected_run_id:
        raise ValueError("strategy manifest snapshot identity mismatch")
    if not rows:
        raise ValueError("strategy manifest snapshot is empty")
    if any(str(row.get("trade_date") or "")[:10] != trade_date for row in rows):
        raise ValueError("strategy manifest snapshot contains another trade date")
    if any(str(row.get("run_id") or "") != run_id for row in rows):
        raise ValueError("strategy manifest snapshot contains another run")
    by_module = {str(row.get("module") or ""): row for row in rows}
    missing = sorted(REQUIRED_MODULES - set(by_module))
    failed = sorted(
        module
        for module in REQUIRED_MODULES
        if str((by_module.get(module) or {}).get("status") or "") != "success"
    )
    if missing or failed:
        raise ValueError(f"strategy manifest snapshot is not publishable: missing={missing}, failed={failed}")


def _relocate_value(value: Any, source_root: str, target_root: str) -> Any:
    if isinstance(value, dict):
        return {key: _relocate_value(item, source_root, target_root) for key, item in value.items()}
    if isinstance(value, list):
        return [_relocate_value(item, source_root, target_root) for item in value]
    if isinstance(value, str) and (value == source_root or value.startswith(f"{source_root}/")):
        return f"{target_root.rstrip('/')}{value[len(source_root):]}"
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    export_parser = subparsers.add_parser("export")
    export_parser.add_argument("--trade-date", required=True)
    export_parser.add_argument("--source-root", required=True)
    export_parser.add_argument("--target-root", default="/app")
    subparsers.add_parser("import")
    args = parser.parse_args(argv)
    if args.command == "export":
        payload = export_strategy_manifest_snapshot(
            trade_date=args.trade_date,
            source_root=args.source_root,
            target_root=args.target_root,
        )
        json.dump(payload, sys.stdout, ensure_ascii=False, default=str)
        sys.stdout.write("\n")
        return 0
    payload = json.load(sys.stdin)
    print(import_strategy_manifest_snapshot(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
