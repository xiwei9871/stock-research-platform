from stock_research.config import SETTINGS
from stock_research.db import connect, execute


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
    trade_date: object,
    status: str,
    dependency_check_status: str,
    lhb_shortline_status: str,
    mid_trend_status: str,
    tech_bottleneck_status: str,
    review_rows: object,
    output_dir: str | None,
    summary_path: str | None,
    error_summary: str | None,
) -> dict[str, object]:
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
