from datetime import date
import json
from typing import Any

from stock_research.config import SETTINGS
from stock_research.db import connect, execute, fetch_all


def quality_status(metric: int | float, min_value: int | float) -> str:
    return "ok" if metric >= min_value else "fail"


def latest_trade_date(
    adjust_type: str = "hfq",
    service: str = SETTINGS.research_service,
) -> str | None:
    sql = """
    SELECT max(trade_date)::text AS trade_date
    FROM market_daily_bar
    WHERE adjust_type = %s
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, [adjust_type])
    return rows[0]["trade_date"]


def count_bars_for_date(
    trade_date: str,
    adjust_type: str = "hfq",
    service: str = SETTINGS.research_service,
) -> int:
    sql = """
    SELECT count(*) AS count
    FROM market_daily_bar
    WHERE trade_date = %s AND adjust_type = %s
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, [trade_date, adjust_type])
    return int(rows[0]["count"])


def record_quality_check(
    check_date: str,
    check_name: str,
    status: str,
    metric_value: int | float,
    details: dict[str, Any],
) -> None:
    sql = """
    INSERT INTO data_quality_check (check_date, check_name, status, metric_value, details)
    VALUES (%s, %s, %s, %s, %s::jsonb)
    ON CONFLICT (check_date, check_name) DO UPDATE SET
        status = EXCLUDED.status,
        metric_value = EXCLUDED.metric_value,
        details = EXCLUDED.details,
        created_at = now()
    """
    with connect(SETTINGS.research_service) as conn:
        execute(
            conn,
            sql,
            [
                check_date,
                check_name,
                status,
                metric_value,
                json.dumps(details, ensure_ascii=False),
            ],
        )


def run_daily_quality_checks(
    trade_date: str | None = None,
    min_bar_count: int = 5000,
) -> list[dict[str, Any]]:
    effective_date = trade_date or latest_trade_date("hfq")
    if effective_date is None:
        result = {
            "check_date": date.today().isoformat(),
            "check_name": "latest_trade_date",
            "status": "fail",
            "metric_value": 0,
        }
        record_quality_check(
            result["check_date"],
            result["check_name"],
            result["status"],
            result["metric_value"],
            {"reason": "no market data"},
        )
        return [result]

    count = count_bars_for_date(effective_date, "hfq")
    status = quality_status(count, min_bar_count)
    result = {
        "check_date": effective_date,
        "check_name": "hfq_bar_count",
        "status": status,
        "metric_value": count,
    }
    record_quality_check(
        effective_date,
        "hfq_bar_count",
        status,
        count,
        {"min_bar_count": min_bar_count},
    )
    return [result]
