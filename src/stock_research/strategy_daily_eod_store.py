from __future__ import annotations

from typing import Any

from stock_research.config import SETTINGS
from stock_research.db import connect, execute, fetch_all


STRATEGY_DAILY_EOD_STATUS_SQL = """
CREATE SCHEMA IF NOT EXISTS ops;

CREATE TABLE IF NOT EXISTS ops.strategy_daily_eod_status (
    trade_date date PRIMARY KEY,
    status text NOT NULL CHECK (status IN ('success', 'failed', 'running', 'skipped')),
    dependency_check_status text NOT NULL,
    lhb_shortline_status text NOT NULL,
    mid_trend_status text NOT NULL,
    tech_bottleneck_status text NOT NULL,
    review_rows integer NOT NULL DEFAULT 0,
    output_dir text,
    summary_path text,
    error_summary text,
    updated_at timestamptz NOT NULL DEFAULT now()
);
"""


def apply_strategy_daily_eod_status_schema(
    service: str = SETTINGS.research_service,
) -> None:
    with connect(service) as conn:
        execute(conn, STRATEGY_DAILY_EOD_STATUS_SQL)


def build_status_payload(
    *,
    trade_date: str,
    status: str,
    dependency_check_status: str,
    lhb_shortline_status: str,
    mid_trend_status: str,
    tech_bottleneck_status: str,
    review_rows: int,
    output_dir: str | None,
    summary_path: str | None,
    error_summary: str | None,
) -> dict[str, Any]:
    return {
        "trade_date": trade_date,
        "status": status,
        "dependency_check_status": dependency_check_status,
        "lhb_shortline_status": lhb_shortline_status,
        "mid_trend_status": mid_trend_status,
        "tech_bottleneck_status": tech_bottleneck_status,
        "review_rows": int(review_rows),
        "output_dir": output_dir,
        "summary_path": summary_path,
        "error_summary": error_summary,
    }


def upsert_strategy_daily_eod_status(
    payload: dict[str, Any],
    *,
    service: str = SETTINGS.research_service,
) -> None:
    sql = """
    INSERT INTO ops.strategy_daily_eod_status (
        trade_date,
        status,
        dependency_check_status,
        lhb_shortline_status,
        mid_trend_status,
        tech_bottleneck_status,
        review_rows,
        output_dir,
        summary_path,
        error_summary
    )
    VALUES (
        %(trade_date)s,
        %(status)s,
        %(dependency_check_status)s,
        %(lhb_shortline_status)s,
        %(mid_trend_status)s,
        %(tech_bottleneck_status)s,
        %(review_rows)s,
        %(output_dir)s,
        %(summary_path)s,
        %(error_summary)s
    )
    ON CONFLICT (trade_date)
    DO UPDATE SET
        status = EXCLUDED.status,
        dependency_check_status = EXCLUDED.dependency_check_status,
        lhb_shortline_status = EXCLUDED.lhb_shortline_status,
        mid_trend_status = EXCLUDED.mid_trend_status,
        tech_bottleneck_status = EXCLUDED.tech_bottleneck_status,
        review_rows = EXCLUDED.review_rows,
        output_dir = EXCLUDED.output_dir,
        summary_path = EXCLUDED.summary_path,
        error_summary = EXCLUDED.error_summary,
        updated_at = now()
    """
    with connect(service) as conn:
        execute(conn, sql, payload)


def load_strategy_daily_eod_status(
    trade_date: str,
    *,
    service: str = SETTINGS.research_service,
) -> dict[str, Any] | None:
    sql = """
    SELECT
        trade_date::text AS trade_date,
        status,
        dependency_check_status,
        lhb_shortline_status,
        mid_trend_status,
        tech_bottleneck_status,
        review_rows,
        output_dir,
        summary_path,
        error_summary
    FROM ops.strategy_daily_eod_status
    WHERE trade_date = %s
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, [trade_date])
    return rows[0] if rows else None
