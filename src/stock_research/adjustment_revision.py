"""R2/R4 adjustment-revision machinery: detect supplier revisions to stored
qfq/hfq daily bars, classify candidates, apply diff-driven repairs, and
support backup/rollback. Raw rows are never modified by this module.
"""
from __future__ import annotations

from typing import Any, Iterable

REVISION_SOURCE_PREFIX = "baostock_revision"
PRECLOSE_EVENT_THRESHOLD = 0.001
PRICE_DIFF_TOLERANCE = 0.0005

STATUS_CONFIRMED_DIRTY = "CONFIRMED_DIRTY"
STATUS_ALREADY_CORRECT = "ALREADY_CORRECT"
STATUS_NEEDS_REVIEW = "NEEDS_REVIEW"

REVIEW_MAX_DIFF_RATIO = 0.5

CLASSIFIABLE_STATUSES = {
    STATUS_CONFIRMED_DIRTY,
    STATUS_ALREADY_CORRECT,
    STATUS_NEEDS_REVIEW,
}


def detect_preclose_events(
    conn,
    *,
    start_date: str,
    end_date: str,
    lookback_days: int = 30,
    threshold: float = PRECLOSE_EVENT_THRESHOLD,
) -> list[dict[str, Any]]:
    """Return raw-bar preclose vs previous-close jumps (exchange marks
    ex-rights days by adjusting preclose). Read-only detection."""
    from stock_research.db import fetch_all

    sql = """
    WITH ordered AS (
        SELECT asset_id, trade_date, close, preclose,
               LAG(close) OVER (PARTITION BY asset_id ORDER BY trade_date) AS prev_close
        FROM market_daily_bar
        WHERE adjust_type = 'raw'
          AND trade_date >= %s::date - %s::int
          AND trade_date <= %s
    )
    SELECT asset_id, trade_date AS event_date, close, preclose, prev_close,
           (preclose - prev_close) / NULLIF(prev_close, 0) AS ratio
    FROM ordered
    WHERE prev_close IS NOT NULL
      AND ABS(preclose - prev_close) / prev_close > %s
      AND trade_date >= %s
    ORDER BY trade_date, asset_id
    """
    return fetch_all(conn, sql, [start_date, lookback_days, end_date, threshold, start_date])


def diff_stored_vs_live(
    stored: dict[str, float],
    live: dict[str, float],
    *,
    tolerance: float = PRICE_DIFF_TOLERANCE,
) -> dict[str, Any]:
    """Compare stored vs live close prices for one adjust_type."""
    diffs: list[str] = []
    missing_live: list[str] = []
    for date_key, stored_close in stored.items():
        live_close = live.get(date_key)
        if live_close is None:
            missing_live.append(date_key)
            continue
        if stored_close in (None, 0):
            diffs.append(date_key)
            continue
        if abs(live_close - stored_close) / abs(stored_close) > tolerance:
            diffs.append(date_key)
    extra_live = [d for d in live if d not in stored]
    diffs.sort()
    return {
        "diff_dates": diffs,
        "diff_count": len(diffs),
        "first_diff": diffs[0] if diffs else None,
        "last_diff": diffs[-1] if diffs else None,
        "missing_in_live": len(missing_live),
        "extra_in_live": len(extra_live),
    }


def classify_asset_revision(
    *,
    qfq_diff: dict[str, Any],
    hfq_diff: dict[str, Any],
    stored_rows: int,
) -> str:
    """Classify one candidate asset after live-vs-stored comparison."""
    total_diff = qfq_diff["diff_count"] + hfq_diff["diff_count"]
    if qfq_diff["missing_in_live"] or hfq_diff["missing_in_live"]:
        return STATUS_NEEDS_REVIEW
    if stored_rows and total_diff / max(stored_rows, 1) > REVIEW_MAX_DIFF_RATIO and not total_diff:
        return STATUS_NEEDS_REVIEW
    if total_diff == 0:
        return STATUS_ALREADY_CORRECT
    return STATUS_CONFIRMED_DIRTY


def diff_driven_update_rows(
    stored_rows: list[dict[str, Any]],
    live_rows: list[dict[str, Any]],
    *,
    key_fields: tuple[str, ...] = ("asset_id", "trade_date", "adjust_type"),
    price_fields: tuple[str, ...] = (
        "open", "high", "low", "close", "preclose",
        "volume", "amount", "turnover_rate", "pct_chg",
    ),
    tolerance: float = PRICE_DIFF_TOLERANCE,
) -> list[dict[str, Any]]:
    """Return live rows that actually differ from stored on price fields —
    diff-driven writes only. Rows equal to stored are skipped."""
    stored_by_key = {
        tuple(str(row.get(k)) for k in key_fields): row for row in stored_rows
    }
    updates: list[dict[str, Any]] = []
    for live in live_rows:
        key = tuple(str(live.get(k)) for k in key_fields)
        stored = stored_by_key.get(key)
        if stored is None:
            updates.append(live)
            continue
        changed = False
        for field in price_fields:
            lv = live.get(field)
            sv = stored.get(field)
            if lv is None and sv is None:
                continue
            if lv is None or sv is None:
                changed = True
                break
            try:
                if abs(float(lv) - float(sv)) > max(abs(float(sv)) * tolerance, 1e-9):
                    changed = True
                    break
            except (TypeError, ValueError):
                if str(lv) != str(sv):
                    changed = True
                    break
        if changed:
            updates.append(live)
    return updates


def assert_no_raw_rows(rows: Iterable[dict[str, Any]]) -> None:
    for row in rows:
        if row.get("adjust_type") == "raw":
            raise ValueError("revision path must never write raw rows")


def earliest_event_date(events: list[dict[str, Any]], asset_id: str) -> str | None:
    dates = [
        str(e["event_date"])
        for e in events
        if e.get("asset_id") == asset_id
    ]
    return min(dates) if dates else None
