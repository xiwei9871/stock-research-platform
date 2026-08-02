"""Scoped, resumable market-daily-bar backfill for rolling oversold gaps."""

from __future__ import annotations

import csv
import hashlib
import json
import os
from collections import Counter
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from stock_research.config import SETTINGS
from stock_research.daily_close_pipeline import (
    fetch_akshare_daily_rows,
    fetch_tushare_adjusted_daily_rows,
    fetch_tushare_daily_rows,
)
from stock_research.db import connect, execute_many, fetch_all


SUPPORTED_ADJUST_TYPES = ("raw", "qfq", "hfq")
SUPPORTED_SOURCES = ("akshare", "tushare")
DEFAULT_OUTPUT_DIR = Path("outputs/research/rolling_sector_oversold_backfill")
DEFAULT_TIMEOUT_SECONDS = 60
DEFAULT_MAX_RETRIES = 3

REPORT_COLUMNS = (
    "asset_id",
    "trade_date",
    "adjust_type",
    "status",
    "source",
    "endpoint",
    "request_start_date",
    "request_end_date",
    "attempts",
    "payload_hash",
    "error",
)

RAW_DAILY_PAYLOAD_SQL = """
INSERT INTO raw_baostock.daily_bar_payload (
    source_service, source_table, adjust_type, trade_date, asset_id, payload, payload_hash
)
VALUES (
    %(source_service)s, %(source_table)s, %(adjust_type)s, %(trade_date)s,
    %(asset_id)s, %(payload)s::jsonb, %(payload_hash)s
)
ON CONFLICT (source_service, source_table, adjust_type, trade_date, asset_id)
DO UPDATE SET
    payload = EXCLUDED.payload,
    payload_hash = EXCLUDED.payload_hash,
    fetched_at = now()
"""

MARKET_DAILY_BAR_SQL = """
INSERT INTO market_daily_bar (
    asset_id, trade_date, open, high, low, close, preclose, volume, amount,
    turnover_rate, pct_chg, trade_status, is_st, adjust_type, source
)
VALUES (
    %(asset_id)s, %(trade_date)s, %(open)s, %(high)s, %(low)s, %(close)s,
    %(preclose)s, %(volume)s, %(amount)s, %(turnover_rate)s, %(pct_chg)s,
    %(trade_status)s, %(is_st)s, %(adjust_type)s, %(source)s
)
ON CONFLICT (asset_id, trade_date, adjust_type) DO UPDATE SET
    open = EXCLUDED.open,
    high = EXCLUDED.high,
    low = EXCLUDED.low,
    close = EXCLUDED.close,
    preclose = EXCLUDED.preclose,
    volume = EXCLUDED.volume,
    amount = EXCLUDED.amount,
    turnover_rate = EXCLUDED.turnover_rate,
    pct_chg = EXCLUDED.pct_chg,
    trade_status = EXCLUDED.trade_status,
    is_st = EXCLUDED.is_st,
    source = EXCLUDED.source,
    updated_at = now()
"""


def run_market_backfill(
    *,
    asset_ids: list[str] | tuple[str, ...],
    start_date: str | date,
    end_date: str | date,
    adjust_types: tuple[str, ...] | list[str],
    source: str,
    service: str = SETTINGS.research_service,
    dry_run: bool = True,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    include_invalid_assets: bool = False,
    max_retries: int = DEFAULT_MAX_RETRIES,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Backfill explicitly requested assets without discovering a universe."""
    normalized_assets = _normalize_asset_ids(asset_ids)
    parsed_start = _parse_date(start_date, "start_date")
    parsed_end = _parse_date(end_date, "end_date")
    if parsed_end < parsed_start:
        raise ValueError("end_date must not precede start_date")
    normalized_adjust_types = _normalize_adjust_types(adjust_types)
    normalized_source = _normalize_source(source)
    if type(max_retries) is not int or max_retries < 1:
        raise ValueError("max_retries must be a positive integer")
    if type(timeout_seconds) is not int or timeout_seconds < 1:
        raise ValueError("timeout_seconds must be a positive integer")

    master_rows = _load_asset_master(service, normalized_assets)
    master_by_asset = {
        str(row.get("asset_id")): row for row in master_rows if row.get("asset_id")
    }
    endpoint = _endpoint_for_source(normalized_source)
    request_start = parsed_start.isoformat()
    request_end = parsed_end.isoformat()
    report_rows: list[dict[str, Any]] = []
    raw_rows: list[dict[str, Any]] = []
    bar_rows: list[dict[str, Any]] = []

    current_date = parsed_start
    while current_date <= parsed_end:
        for asset_id in normalized_assets:
            validation = _validate_asset_for_date(
                asset_id,
                master_by_asset.get(asset_id),
                current_date,
                include_invalid_assets=include_invalid_assets,
            )
            for adjust_type in normalized_adjust_types:
                detail = _report_row(
                    asset_id=asset_id,
                    trade_date=current_date,
                    adjust_type=adjust_type,
                    source=normalized_source,
                    endpoint=endpoint,
                    request_start=request_start,
                    request_end=request_end,
                )
                if validation is not None:
                    detail["status"] = validation
                    report_rows.append(detail)
                    continue
                if dry_run:
                    detail["status"] = "planned"
                    report_rows.append(detail)
            if validation is not None or dry_run:
                continue

            ts_code = _asset_id_to_ts_code(asset_id)
            fetched_rows, attempts, error = _fetch_source_with_retries(
                normalized_source,
                current_date,
                ts_code,
                normalized_adjust_types,
                timeout_seconds=timeout_seconds,
                max_retries=max_retries,
            )
            rows_by_adjust = {
                str(row.get("adjust_type") or "raw"): row
                for row in fetched_rows
                if _same_asset_and_date(row, asset_id, current_date)
            }
            for adjust_type in normalized_adjust_types:
                detail = _report_row(
                    asset_id=asset_id,
                    trade_date=current_date,
                    adjust_type=adjust_type,
                    source=normalized_source,
                    endpoint=endpoint,
                    request_start=request_start,
                    request_end=request_end,
                )
                detail["attempts"] = attempts
                row = rows_by_adjust.get(adjust_type)
                if error is not None:
                    detail["status"] = "retryable_failure"
                    detail["error"] = error
                elif row is None:
                    detail["status"] = "missing"
                else:
                    normalized_row = _normalize_bar_row(
                        row,
                        asset_id=asset_id,
                        trade_date=current_date,
                        adjust_type=adjust_type,
                        source=normalized_source,
                    )
                    payload = _raw_payload(
                        row,
                        source=normalized_source,
                        endpoint=endpoint,
                        asset_id=asset_id,
                        trade_date=current_date,
                        request_start=request_start,
                        request_end=request_end,
                    )
                    raw_record = _raw_payload_row(
                        payload,
                        asset_id=asset_id,
                        trade_date=current_date,
                        adjust_type=adjust_type,
                        source=normalized_source,
                        endpoint=endpoint,
                    )
                    detail["status"] = "fetched"
                    detail["payload_hash"] = raw_record["payload_hash"]
                    raw_rows.append(raw_record)
                    bar_rows.append(normalized_row)
                report_rows.append(detail)
        current_date += timedelta(days=1)

    if not dry_run and (raw_rows or bar_rows):
        _write_rows(service, raw_rows, bar_rows)

    report = _build_report(
        source=normalized_source,
        start_date=request_start,
        end_date=request_end,
        adjust_types=normalized_adjust_types,
        dry_run=dry_run,
        include_invalid_assets=include_invalid_assets,
        report_rows=report_rows,
        raw_rows=len(raw_rows),
        bar_rows=len(bar_rows),
    )
    paths = _write_reports(report, output_dir)
    report["paths"] = paths
    report["report_path"] = paths["json"]
    return report


def load_gap_workplan_asset_ids(
    path: str | Path,
    dataset: str = "market_daily_bar",
) -> list[str]:
    """Extract explicit asset keys from a Task1 gap-workplan artifact."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = payload.get("gap_rows", [])
    asset_ids = {
        str(row.get("asset_or_key") or "").strip()
        for row in rows
        if row.get("dataset") == dataset and str(row.get("asset_or_key") or "").strip()
    }
    if asset_ids:
        return sorted(asset_ids)
    buckets = payload.get("buckets", {})
    selected = set()
    for bucket in ("market_bar_backfill", "out_of_scope_bse"):
        selected.update(str(value).strip() for value in buckets.get(bucket, ()) if str(value).strip())
    return sorted(selected)


def _normalize_asset_ids(asset_ids: list[str] | tuple[str, ...]) -> list[str]:
    if isinstance(asset_ids, (str, bytes)):
        raise ValueError("asset_ids must be an explicit sequence")
    normalized = sorted({str(asset_id).strip().upper() for asset_id in asset_ids if str(asset_id).strip()})
    if not normalized:
        raise ValueError("asset_ids must not be empty")
    return normalized


def _parse_date(value: str | date, field: str) -> date:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise ValueError(f"{field} must use YYYY-MM-DD") from exc


def _normalize_adjust_types(adjust_types: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    if isinstance(adjust_types, str):
        values = tuple(part.strip().lower() for part in adjust_types.split(",") if part.strip())
    else:
        values = tuple(str(value).strip().lower() for value in adjust_types if str(value).strip())
    if not values:
        raise ValueError("adjust_types must not be empty")
    unsupported = sorted(set(values) - set(SUPPORTED_ADJUST_TYPES))
    if unsupported:
        raise ValueError(f"unsupported adjust types: {unsupported}")
    if len(set(values)) != len(values):
        raise ValueError("adjust_types must be unique")
    return values


def _normalize_source(source: str) -> str:
    normalized = str(source).strip().lower()
    if normalized not in SUPPORTED_SOURCES:
        raise ValueError(f"unsupported source: {source!r}")
    return normalized


def _load_asset_master(service: str, asset_ids: list[str]) -> list[dict[str, Any]]:
    sql = """
    SELECT asset_id, exchange, list_date, delist_date, is_active, is_beijing
    FROM core.asset_master
    WHERE asset_id = ANY(%s)
    ORDER BY asset_id
    """
    with connect(service) as conn:
        return fetch_all(conn, sql, [asset_ids])


def _validate_asset_for_date(
    asset_id: str,
    master: dict[str, Any] | None,
    trade_date: date,
    *,
    include_invalid_assets: bool,
) -> str | None:
    if asset_id.startswith("CN:BJ:"):
        return "out_of_scope_bse"
    exchange_from_id = _asset_exchange(asset_id)
    if exchange_from_id not in {"SH", "SZ"}:
        return "out_of_scope_exchange"
    if master is None:
        return None if include_invalid_assets else "missing_master"
    exchange = str(master.get("exchange") or exchange_from_id).strip().upper()
    if exchange == "BJ" or bool(master.get("is_beijing")):
        return "out_of_scope_bse"
    if exchange not in {"SH", "SZ"}:
        return "out_of_scope_bse" if exchange == "BJ" else "out_of_scope_exchange"
    if include_invalid_assets:
        return None
    if master.get("is_active") is False:
        return "inactive_pit"
    list_date = _optional_date(master.get("list_date"))
    delist_date = _optional_date(master.get("delist_date"))
    if list_date is not None and list_date > trade_date:
        return "inactive_pit"
    if delist_date is not None and delist_date <= trade_date:
        return "inactive_pit"
    return None


def _asset_exchange(asset_id: str) -> str:
    parts = asset_id.split(":")
    return parts[1] if len(parts) == 3 and parts[0] == "CN" else ""


def _optional_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _endpoint_for_source(source: str) -> str:
    return {
        "akshare": "akshare.stock_zh_a_hist",
        "tushare": "tushare.pro.daily",
    }[source]


def _asset_id_to_ts_code(asset_id: str) -> str:
    _, exchange, symbol = asset_id.split(":", 2)
    return f"{symbol}.{exchange}"


def _fetch_source_with_retries(
    source: str,
    trade_date: date,
    ts_code: str,
    adjust_types: tuple[str, ...],
    *,
    timeout_seconds: int,
    max_retries: int,
) -> tuple[list[dict[str, Any]], int, str | None]:
    last_error: str | None = None
    for attempt in range(1, max_retries + 1):
        try:
            if source == "akshare":
                rows = fetch_akshare_daily_rows(
                    trade_date=trade_date,
                    ts_codes=[ts_code],
                    timeout_seconds=timeout_seconds,
                    adjust_types=adjust_types,
                )
            else:
                rows = fetch_tushare_daily_rows(
                    trade_date=trade_date,
                    token=os.environ.get("TUSHARE_TOKEN"),
                    timeout_seconds=timeout_seconds,
                    ts_codes=[ts_code],
                )
                rows.extend(
                    fetch_tushare_adjusted_daily_rows(
                        trade_date=trade_date,
                        token=os.environ.get("TUSHARE_TOKEN"),
                        timeout_seconds=timeout_seconds,
                        ts_codes=[ts_code],
                        adjust_types=adjust_types,
                    )
                )
            return list(rows or []), attempt, None
        except Exception as exc:  # noqa: BLE001 - report retryable source failures.
            last_error = f"{type(exc).__name__}: {exc}"
    return [], max_retries, last_error


def _same_asset_and_date(row: dict[str, Any], asset_id: str, trade_date: date) -> bool:
    row_asset = str(row.get("asset_id") or "").strip().upper()
    row_date = row.get("trade_date")
    if isinstance(row_date, date):
        parsed = row_date
    else:
        try:
            parsed = date.fromisoformat(str(row_date)[:10])
        except ValueError:
            return False
    return row_asset == asset_id and parsed == trade_date


def _normalize_bar_row(
    row: dict[str, Any],
    *,
    asset_id: str,
    trade_date: date,
    adjust_type: str,
    source: str,
) -> dict[str, Any]:
    normalized = {
        "asset_id": asset_id,
        "trade_date": trade_date,
        "open": row.get("open"),
        "high": row.get("high"),
        "low": row.get("low"),
        "close": row.get("close"),
        "preclose": row.get("preclose"),
        "volume": row.get("volume"),
        "amount": row.get("amount"),
        "turnover_rate": row.get("turnover_rate"),
        "pct_chg": row.get("pct_chg"),
        "trade_status": str(row.get("trade_status") or "1"),
        "is_st": bool(row.get("is_st", False)),
        "adjust_type": adjust_type,
        "source": source,
    }
    return normalized


def _raw_payload(
    row: dict[str, Any],
    *,
    source: str,
    endpoint: str,
    asset_id: str,
    trade_date: date,
    request_start: str,
    request_end: str,
) -> dict[str, Any]:
    return {
        "source": source,
        "endpoint": endpoint,
        "request": {
            "asset_id": asset_id,
            "trade_date": trade_date.isoformat(),
            "start_date": request_start,
            "end_date": request_end,
        },
        "row": _jsonable(row),
    }


def _raw_payload_row(
    payload: dict[str, Any],
    *,
    asset_id: str,
    trade_date: date,
    adjust_type: str,
    source: str,
    endpoint: str,
) -> dict[str, Any]:
    canonical = _canonical_json(payload)
    return {
        "source_service": source,
        "source_table": endpoint,
        "adjust_type": adjust_type,
        "trade_date": trade_date,
        "asset_id": asset_id,
        "payload": canonical,
        "payload_hash": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
    }


def _write_rows(
    service: str,
    raw_rows: list[dict[str, Any]],
    bar_rows: list[dict[str, Any]],
) -> None:
    with connect(service) as conn:
        if raw_rows:
            execute_many(conn, RAW_DAILY_PAYLOAD_SQL, raw_rows)
        if bar_rows:
            execute_many(conn, MARKET_DAILY_BAR_SQL, bar_rows)


def _report_row(
    *,
    asset_id: str,
    trade_date: date,
    adjust_type: str,
    source: str,
    endpoint: str,
    request_start: str,
    request_end: str,
) -> dict[str, Any]:
    return {
        "asset_id": asset_id,
        "trade_date": trade_date.isoformat(),
        "adjust_type": adjust_type,
        "status": "",
        "source": source,
        "endpoint": endpoint,
        "request_start_date": request_start,
        "request_end_date": request_end,
        "attempts": 0,
        "payload_hash": "",
        "error": "",
    }


def _build_report(
    *,
    source: str,
    start_date: str,
    end_date: str,
    adjust_types: tuple[str, ...],
    dry_run: bool,
    include_invalid_assets: bool,
    report_rows: list[dict[str, Any]],
    raw_rows: int,
    bar_rows: int,
) -> dict[str, Any]:
    statuses = Counter(str(row["status"]) for row in report_rows)
    return {
        "schema_version": "rolling_oversold_market_backfill_v1",
        "source": source,
        "start_date": start_date,
        "end_date": end_date,
        "adjust_types": list(adjust_types),
        "dry_run": dry_run,
        "include_invalid_assets": include_invalid_assets,
        "upsert_conflict_key": ["asset_id", "trade_date", "adjust_type"],
        "raw_rows": raw_rows,
        "bar_rows": bar_rows,
        "failed": statuses.get("retryable_failure", 0),
        "missing": statuses.get("missing", 0),
        "status_counts": dict(sorted(statuses.items())),
        "rows": report_rows,
    }


def _write_reports(report: dict[str, Any], output_dir: str | Path) -> dict[str, str]:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    json_path = root / "market_backfill_report.json"
    csv_path = root / "market_backfill_report.csv"
    paths = {"json": str(json_path), "csv": str(csv_path)}
    report["paths"] = paths
    json_path.write_text(
        json.dumps(_jsonable(report), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REPORT_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(report["rows"])
    return paths


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, (date,)):
        return value.isoformat()
    if hasattr(value, "item"):
        try:
            return value.item()
        except (TypeError, ValueError):
            pass
    return value


def _canonical_json(value: Any) -> str:
    return json.dumps(_jsonable(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
