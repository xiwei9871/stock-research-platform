"""Unified data freshness & consumer-contract gate (M0.6).

Tri-state health semantics, deliberately independent of job execution status:

- READY: input is fresh, complete over the expected trading-day window, and within
  coverage bounds — safe for formal consumption.
- DEGRADED: an optional/enhancement input is stale, missing, or incomplete. Formal
  publication may proceed only under the strategy's documented degradation contract,
  and the reason must be surfaced in the manifest.
- BLOCKED: a required input is missing/stale/invalid — formal publish prohibited.
- NOT_EVALUATED: input is declared unused/retired for this consumer — never treated as
  data-health evidence either way.

`job_status=success` means a task ran; it does NOT imply READY. Coverage, latest date,
and intermediate trading-day gaps are evaluated against `market.trading_calendar`,
not just `MAX(trade_date)`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

import pandas as pd

READY = "READY"
DEGRADED = "DEGRADED"
BLOCKED = "BLOCKED"
NOT_EVALUATED = "NOT_EVALUATED"

REQUIRED_DAILY = "required_daily"
OPTIONAL_ENHANCEMENT = "optional_enhancement"
CONDITIONAL = "conditional"  # checked only when its specific task runs; reported, not blocking, otherwise
STATIC_FROZEN = "static_frozen"
UNUSED = "unused"

WINDOW_INTRADAY = "intraday"
WINDOW_POST_CLOSE = "post_close"


@dataclass(frozen=True)
class InputSpec:
    name: str
    category: str  # required_daily | optional_enhancement | static_frozen | unused
    kind: str = "table"  # table | file | artifact_dir
    table: str | None = None
    date_column: str = "trade_date"
    coverage_column: str | None = None
    min_daily_rows: int | None = None
    consumers: tuple[str, ...] = field(default_factory=tuple)
    window: str = WINDOW_POST_CLOSE
    degradation_contract: str | None = None  # e.g. "publish_allowed", "publish_blocked"
    file_path: str | None = None


def _open_days(cal: pd.DataFrame) -> list[str]:
    frame = cal.copy()
    frame["trade_date"] = frame["trade_date"].astype(str).str[:10]
    if "is_open" in frame.columns:
        frame = frame[frame["is_open"].astype(bool)]
    # calendar may carry one row per exchange — dedupe to calendar days
    return sorted(set(frame["trade_date"].tolist()))


def expected_trade_date_for_window(
    cal: pd.DataFrame, as_of_date: str, *, window: str = WINDOW_POST_CLOSE
) -> str | None:
    """Expected freshest trade_date for an as_of timestamp.

    - ``post_close``: the most recent open day <= as_of (evening jobs expect the
      just-closed session).
    - ``intraday``: as_of itself when it is an open day (a 09:25/15:10 snapshot may
      legitimately target today), else the previous open day.
    """
    days = _open_days(cal)
    if not days:
        return None
    as_of = str(as_of_date)[:10]
    eligible = [d for d in days if d <= as_of]
    if not eligible:
        return None
    if window == WINDOW_INTRADAY:
        return as_of if as_of in days else eligible[-1]
    return eligible[-1]


def missing_trading_days(
    present_dates: Iterable[Any], calendar_days: Iterable[Any]
) -> list[str]:
    """Expected open days absent from ``present_dates`` — catches mid-range holes
    that a MAX(trade_date) check would hide."""
    present = {str(d)[:10] for d in present_dates}
    return sorted(str(d)[:10] for d in calendar_days if str(d)[:10] not in present)


def evaluate_input_status(
    *,
    category: str,
    expected_date: str | None,
    latest_date: str | None,
    missing_dates: Iterable[Any] | None,
    coverage_actual: int | float | None,
    coverage_min: int | float | None,
    file_exists: bool | None = None,
) -> str:
    if category == UNUSED:
        return NOT_EVALUATED
    if category == STATIC_FROZEN:
        # frozen inputs are compared by version/hash/existence, never by date
        return READY if file_exists else BLOCKED

    missing = list(missing_dates or [])
    stale = latest_date is None or str(latest_date)[:10] != str(expected_date)[:10]
    low_coverage = (
        coverage_min is not None
        and (coverage_actual is None or coverage_actual < coverage_min)
    )
    unhealthy = stale or bool(missing) or low_coverage

    if category == REQUIRED_DAILY:
        return BLOCKED if unhealthy else READY
    if category in (OPTIONAL_ENHANCEMENT, CONDITIONAL):
        # optional/conditional inputs may degrade but never silently vanish — surface,
        # don't block; enforcement happens at the consuming task's own gate
        return DEGRADED if unhealthy else READY
    raise ValueError(f"unknown input category: {category}")


def check_table_input(
    spec: InputSpec,
    *,
    as_of_date: str,
    fetcher: Callable[[str, tuple], list[dict[str, Any]]],
    lookback_days: int = 15,
) -> dict[str, Any]:
    """Evaluate one table input end-to-end. ``fetcher(sql, params)`` runs read-only
    SQL and returns dict rows — injected so the gate is testable without a DB."""
    cal_rows = fetcher(
        "SELECT trade_date, is_open FROM market.trading_calendar WHERE trade_date <= %s "
        "ORDER BY trade_date DESC LIMIT %s",
        (as_of_date, lookback_days + 10),
    )
    cal = pd.DataFrame(cal_rows)
    expected = expected_trade_date_for_window(cal, as_of_date, window=spec.window)
    cal_days = _open_days(cal)
    window_days = [d for d in cal_days if expected and d <= expected][-lookback_days:]

    distinct_rows = fetcher(
        f"SELECT DISTINCT {spec.date_column}::text AS trade_date FROM {spec.table} "
        f"WHERE {spec.date_column} = ANY(%s)",
        (window_days,),
    )
    present = [r["trade_date"] for r in distinct_rows]
    missing = missing_trading_days(present, window_days)

    coverage_expr = (
        f"count(distinct {spec.coverage_column})" if spec.coverage_column else "count(*)"
    )
    agg = fetcher(
        f"SELECT max({spec.date_column}) AS latest_trade_date, count(*) AS row_count, "
        f"{coverage_expr} AS asset_count "
        f"FROM {spec.table} WHERE {spec.date_column} = %s",
        (expected,),
    )
    latest = (agg or [{}])[0].get("latest_trade_date")
    coverage = None
    if spec.coverage_column and agg:
        coverage = agg[0].get("asset_count")
    elif agg:
        coverage = agg[0].get("row_count")

    status = evaluate_input_status(
        category=spec.category,
        expected_date=expected,
        latest_date=str(latest)[:10] if latest else None,
        missing_dates=missing,
        coverage_actual=coverage,
        coverage_min=spec.min_daily_rows,
    )
    return {
        "input": spec.name,
        "table": spec.table,
        "category": spec.category,
        "consumer": spec.consumers,
        "window": spec.window,
        "expected_trade_date": expected,
        "actual_latest_date": str(latest)[:10] if latest else None,
        "missing_trade_dates": missing,
        "coverage": coverage,
        "coverage_min": spec.min_daily_rows,
        "freshness_status": status,
        "fallback_used": spec.category == OPTIONAL_ENHANCEMENT and status == DEGRADED,
        "degradation_reason": (
            f"{spec.name} stale/incomplete (latest={latest}, expected={expected}, "
            f"missing={len(missing)}d)"
            if status == DEGRADED
            else None
        ),
    }
