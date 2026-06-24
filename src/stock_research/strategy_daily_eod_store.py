from typing import Literal, TypedDict

from stock_research.config import SETTINGS
from stock_research.db import connect, execute


StrategyDailyEodStatus = Literal["success", "failed", "running", "skipped"]


class StrategyDailyEodStatusPayload(TypedDict):
    trade_date: str
    status: StrategyDailyEodStatus
    dependency_check_status: StrategyDailyEodStatus
    lhb_shortline_status: StrategyDailyEodStatus
    mid_trend_status: StrategyDailyEodStatus
    tech_bottleneck_status: StrategyDailyEodStatus
    review_rows: int
    output_dir: str | None
    summary_path: str | None
    error_summary: str | None


STRATEGY_DAILY_EOD_STATUS_SQL = """
CREATE SCHEMA IF NOT EXISTS ops;

CREATE TABLE IF NOT EXISTS ops.strategy_daily_eod_status (
    trade_date date PRIMARY KEY,
    status text NOT NULL CHECK (status IN ('success', 'failed', 'running', 'skipped')),
    dependency_check_status text NOT NULL CHECK (dependency_check_status IN ('success', 'failed', 'running', 'skipped')),
    lhb_shortline_status text NOT NULL CHECK (lhb_shortline_status IN ('success', 'failed', 'running', 'skipped')),
    mid_trend_status text NOT NULL CHECK (mid_trend_status IN ('success', 'failed', 'running', 'skipped')),
    tech_bottleneck_status text NOT NULL CHECK (tech_bottleneck_status IN ('success', 'failed', 'running', 'skipped')),
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
    status: StrategyDailyEodStatus,
    dependency_check_status: StrategyDailyEodStatus,
    lhb_shortline_status: StrategyDailyEodStatus,
    mid_trend_status: StrategyDailyEodStatus,
    tech_bottleneck_status: StrategyDailyEodStatus,
    review_rows: int | str,
    output_dir: str | None,
    summary_path: str | None,
    error_summary: str | None,
) -> StrategyDailyEodStatusPayload:
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
