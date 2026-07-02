from __future__ import annotations

import datetime as dt
import fcntl
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all
from stock_research.minute_backfill import TRADING_MINUTE_BARS_PER_DAY


DEFAULT_BAOSTOCK_DAILY_REQUEST_LIMIT = 50_000
DEFAULT_BAOSTOCK_SAFETY_MULTIPLIER = 1.1
DEFAULT_BAOSTOCK_REQUEST_LEDGER_PATH = Path("logs/baostock_minute_request_quota.json")


@dataclass(frozen=True)
class BaostockMinuteBudget:
    active_asset_count: int
    today_adjust_type_count: int
    daily_request_limit: int
    safety_multiplier: float
    safe_daily_request_budget: int
    today_reserved_requests: int
    backfill_request_budget: int
    full_market_raw_days: float
    full_market_raw_qfq_days: float


@dataclass(frozen=True)
class BackfillQuotaAllocation:
    day: dt.date
    allocated_requests: int
    consumed_requests: int
    active_reserved_requests: int
    backfill_request_budget: int


def calculate_baostock_minute_budget(
    *,
    active_asset_count: int,
    today_adjust_types: list[str],
    daily_request_limit: int = DEFAULT_BAOSTOCK_DAILY_REQUEST_LIMIT,
    safety_multiplier: float = DEFAULT_BAOSTOCK_SAFETY_MULTIPLIER,
    max_backfill_requests: int | None = None,
) -> BaostockMinuteBudget:
    if active_asset_count < 0:
        raise ValueError("active_asset_count must be non-negative")
    if daily_request_limit <= 0:
        raise ValueError("daily_request_limit must be positive")
    if safety_multiplier < 1:
        raise ValueError("safety_multiplier must be >= 1")

    adjust_type_count = len(today_adjust_types)
    safe_daily_budget = math.floor(daily_request_limit / safety_multiplier)
    today_reserved = active_asset_count * adjust_type_count
    available = max(0, safe_daily_budget - today_reserved)
    if max_backfill_requests is not None:
        if max_backfill_requests < 0:
            raise ValueError("max_backfill_requests must be non-negative")
        available = min(available, max_backfill_requests)

    return BaostockMinuteBudget(
        active_asset_count=active_asset_count,
        today_adjust_type_count=adjust_type_count,
        daily_request_limit=daily_request_limit,
        safety_multiplier=safety_multiplier,
        safe_daily_request_budget=safe_daily_budget,
        today_reserved_requests=today_reserved,
        backfill_request_budget=available,
        full_market_raw_days=(available / active_asset_count) if active_asset_count else 0.0,
        full_market_raw_qfq_days=(available / (active_asset_count * 2)) if active_asset_count else 0.0,
    )


def allocate_daily_backfill_quota(
    *,
    ledger_path: str | Path,
    day: dt.date,
    backfill_request_budget: int,
    requested_requests: int,
) -> BackfillQuotaAllocation:
    if backfill_request_budget < 0:
        raise ValueError("backfill_request_budget must be non-negative")
    if requested_requests < 0:
        raise ValueError("requested_requests must be non-negative")

    def update(payload: dict[str, Any]) -> tuple[dict[str, Any], BackfillQuotaAllocation]:
        bucket = _daily_bucket(payload, day)
        consumed = int(bucket.get("backfill_consumed_requests", 0) or 0)
        reserved = int(bucket.get("backfill_active_reserved_requests", 0) or 0)
        available = max(0, backfill_request_budget - consumed - reserved)
        allocated = min(requested_requests, available)
        bucket["backfill_active_reserved_requests"] = reserved + allocated
        bucket["backfill_request_budget"] = backfill_request_budget
        allocation = BackfillQuotaAllocation(
            day=day,
            allocated_requests=allocated,
            consumed_requests=consumed,
            active_reserved_requests=reserved + allocated,
            backfill_request_budget=backfill_request_budget,
        )
        return payload, allocation

    return _update_ledger(Path(ledger_path), update)


def finalize_daily_backfill_quota(
    *,
    ledger_path: str | Path,
    day: dt.date,
    allocated_requests: int,
    attempted_requests: int,
) -> BackfillQuotaAllocation:
    if allocated_requests < 0:
        raise ValueError("allocated_requests must be non-negative")
    if attempted_requests < 0:
        raise ValueError("attempted_requests must be non-negative")

    def update(payload: dict[str, Any]) -> tuple[dict[str, Any], BackfillQuotaAllocation]:
        bucket = _daily_bucket(payload, day)
        consumed = int(bucket.get("backfill_consumed_requests", 0) or 0)
        reserved = int(bucket.get("backfill_active_reserved_requests", 0) or 0)
        consumed += min(attempted_requests, allocated_requests)
        reserved = max(0, reserved - allocated_requests)
        budget = int(bucket.get("backfill_request_budget", 0) or 0)
        bucket["backfill_consumed_requests"] = consumed
        bucket["backfill_active_reserved_requests"] = reserved
        allocation = BackfillQuotaAllocation(
            day=day,
            allocated_requests=0,
            consumed_requests=consumed,
            active_reserved_requests=reserved,
            backfill_request_budget=budget,
        )
        return payload, allocation

    return _update_ledger(Path(ledger_path), update)


def load_active_baostock_asset_count(
    research_service: str = SETTINGS.research_service,
) -> int:
    with connect(research_service) as conn:
        row = fetch_all(conn, _ACTIVE_ASSET_COUNT_SQL)[0]
    return int(row["active_baostock_assets"] or 0)


def load_baostock_minute_backfill_probe_summary(
    conn,
    *,
    start_date: dt.date,
    end_date: dt.date,
    freq: str,
    adjust_types: list[str],
) -> dict[str, Any]:
    if freq not in TRADING_MINUTE_BARS_PER_DAY:
        raise ValueError(f"Unsupported minute frequency: {freq}")
    if start_date > end_date:
        raise ValueError("start_date must be <= end_date")

    active = fetch_all(conn, _ACTIVE_ASSET_COUNT_SQL)[0]
    open_days = fetch_all(conn, _DISTINCT_OPEN_DAYS_SQL, [start_date, end_date])[0]
    asset_days = fetch_all(conn, _ASSET_TRADE_DAYS_SQL, [start_date, end_date])[0]
    asset_months = fetch_all(conn, _ASSET_MONTHS_SQL, [start_date, end_date])[0]

    adjust_type_count = len(adjust_types)
    asset_trade_days = int(asset_days["asset_trade_days"] or 0)
    asset_month_count = int(asset_months["asset_months"] or 0)
    daily_chunk_requests = asset_trade_days * adjust_type_count
    monthly_chunk_requests = asset_month_count * adjust_type_count
    estimated_rows = asset_trade_days * adjust_type_count * TRADING_MINUTE_BARS_PER_DAY[freq]

    return {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "freq": freq,
        "adjust_types": ",".join(adjust_types),
        "active_baostock_assets": int(active["active_baostock_assets"] or 0),
        "open_days": int(open_days["open_days"] or 0),
        "first_open": open_days.get("first_open"),
        "last_open": open_days.get("last_open"),
        "asset_trade_days": asset_trade_days,
        "daily_min_assets": int(asset_days["min_assets"] or 0),
        "daily_max_assets": int(asset_days["max_assets"] or 0),
        "daily_avg_assets": str(asset_days.get("avg_assets") or "0"),
        "months": int(asset_months["months"] or 0),
        "asset_months": asset_month_count,
        "monthly_min_assets": int(asset_months["min_assets"] or 0),
        "monthly_max_assets": int(asset_months["max_assets"] or 0),
        "monthly_avg_assets": str(asset_months.get("avg_assets") or "0"),
        "daily_chunk_requests": daily_chunk_requests,
        "monthly_chunk_requests": monthly_chunk_requests,
        "estimated_rows": estimated_rows,
    }


def run_baostock_minute_backfill_probe(
    *,
    start_date: str | dt.date,
    end_date: str | dt.date,
    freq: str = "5min",
    adjust_types: list[str] | None = None,
    research_service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    parsed_start = _parse_date(start_date)
    parsed_end = _parse_date(end_date)
    with connect(research_service) as conn:
        return load_baostock_minute_backfill_probe_summary(
            conn,
            start_date=parsed_start,
            end_date=parsed_end,
            freq=freq,
            adjust_types=adjust_types or ["raw", "qfq"],
        )


def _parse_date(value: str | dt.date) -> dt.date:
    if isinstance(value, dt.date):
        return value
    return dt.date.fromisoformat(value)


def _daily_bucket(payload: dict[str, Any], day: dt.date) -> dict[str, Any]:
    days = payload.setdefault("days", {})
    return days.setdefault(day.isoformat(), {})


def _update_ledger(path: Path, update):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        handle.seek(0)
        text = handle.read().strip()
        payload = json.loads(text) if text else {"days": {}}
        payload, result = update(payload)
        handle.seek(0)
        handle.truncate()
        json.dump(payload, handle, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        handle.write("\n")
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        return result


_ACTIVE_ASSET_COUNT_SQL = """
/* active_baostock_assets */
SELECT count(*)::int AS active_baostock_assets
FROM core.asset_master
WHERE is_active = true
  AND baostock_code IS NOT NULL
  AND baostock_code <> ''
"""

_DISTINCT_OPEN_DAYS_SQL = """
/* distinct_open_days */
WITH open_dates AS (
    SELECT DISTINCT trade_date
    FROM market.trading_calendar
    WHERE trade_date BETWEEN %s AND %s
      AND is_open = true
)
SELECT count(*)::int AS open_days,
       min(trade_date)::text AS first_open,
       max(trade_date)::text AS last_open
FROM open_dates
"""

_ASSET_TRADE_DAYS_SQL = """
/* asset_trade_days */
WITH open_dates AS (
    SELECT DISTINCT trade_date
    FROM market.trading_calendar
    WHERE trade_date BETWEEN %s AND %s
      AND is_open = true
), daily_counts AS (
    SELECT d.trade_date, count(a.asset_id)::int AS listed_assets
    FROM open_dates d
    JOIN core.asset_master a
      ON a.baostock_code IS NOT NULL
     AND a.baostock_code <> ''
     AND (a.list_date IS NULL OR a.list_date <= d.trade_date)
     AND (a.delist_date IS NULL OR a.delist_date >= d.trade_date)
    GROUP BY d.trade_date
)
SELECT sum(listed_assets)::bigint AS asset_trade_days,
       min(listed_assets)::int AS min_assets,
       max(listed_assets)::int AS max_assets,
       round(avg(listed_assets), 2)::text AS avg_assets
FROM daily_counts
"""

_ASSET_MONTHS_SQL = """
/* asset_months */
WITH months AS (
    SELECT generate_series(
        date_trunc('month', %s::date)::date,
        date_trunc('month', %s::date)::date,
        interval '1 month'
    )::date AS month_start
), month_ranges AS (
    SELECT month_start,
           (month_start + interval '1 month - 1 day')::date AS month_end
    FROM months
), monthly_assets AS (
    SELECT m.month_start, count(a.asset_id)::int AS listed_assets
    FROM month_ranges m
    JOIN core.asset_master a
      ON a.baostock_code IS NOT NULL
     AND a.baostock_code <> ''
     AND (a.list_date IS NULL OR a.list_date <= m.month_end)
     AND (a.delist_date IS NULL OR a.delist_date >= m.month_start)
    GROUP BY m.month_start
)
SELECT count(*)::int AS months,
       sum(listed_assets)::bigint AS asset_months,
       min(listed_assets)::int AS min_assets,
       max(listed_assets)::int AS max_assets,
       round(avg(listed_assets), 2)::text AS avg_assets
FROM monthly_assets
"""
