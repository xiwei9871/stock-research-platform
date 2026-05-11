from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all


def find_latest_common_label_date(
    start_date: str,
    horizons: list[int],
    label_set: str = "forward_return",
    label_version: str = "v1",
    service: str = SETTINGS.research_service,
) -> dict:
    if not horizons:
        raise ValueError("horizons must not be empty")

    sql = """
    SELECT max(trade_date) AS latest_common_date,
           count(*) AS date_count
    FROM (
        SELECT trade_date
        FROM label_snapshot
        WHERE label_set = %s
          AND label_version = %s
          AND horizon = ANY(%s)
          AND trade_date >= %s
          AND label_name IN ('forward_return', 'future_return')
        GROUP BY trade_date
        HAVING count(DISTINCT horizon) = %s
    ) covered_dates
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, [label_set, label_version, horizons, start_date, len(horizons)])
    row = rows[0] if rows else {}
    latest = row.get("latest_common_date")
    return {
        "latest_common_date": str(latest)[:10] if latest is not None else None,
        "date_count": int(row.get("date_count") or 0),
        "horizons": list(horizons),
    }


def check_factor_label_coverage(
    factor_names: list[str],
    start_date: str,
    end_date: str,
    horizons: list[int],
    calc_version: str = "v1",
    min_label_dates: int = 20,
    service: str = SETTINGS.research_service,
) -> dict:
    if not factor_names:
        raise ValueError("factor_names must not be empty")
    if not horizons:
        raise ValueError("horizons must not be empty")

    factor_sql = """
        SELECT min_date, max_date, date_count, complete_date_count
        FROM (
            SELECT
                min(trade_date) AS min_date,
                max(trade_date) AS max_date,
                count(DISTINCT trade_date) AS date_count,
                count(*) FILTER (WHERE factor_count = %s) AS complete_date_count
            FROM (
                SELECT trade_date, count(DISTINCT factor_name) AS factor_count
                FROM factor.factor_daily
                WHERE factor_name = ANY(%s)
                  AND calc_version = %s
                  AND trade_date BETWEEN %s AND %s
                GROUP BY trade_date
            ) factor_dates
        ) factor_summary
    """
    label_sql = """
        SELECT horizon, min(trade_date) AS min_date, max(trade_date) AS max_date,
               count(DISTINCT trade_date) AS date_count
        FROM label_snapshot
        WHERE label_set = 'forward_return'
          AND label_version = 'v1'
          AND horizon = ANY(%s)
          AND label_name IN ('forward_return', 'future_return')
          AND trade_date BETWEEN %s AND %s
        GROUP BY horizon
        ORDER BY horizon
    """
    with connect(service) as conn:
        factor_rows = fetch_all(
            conn,
            factor_sql,
            [len(factor_names), factor_names, calc_version, start_date, end_date],
        )
        label_rows = fetch_all(conn, label_sql, [horizons, start_date, end_date])

    factor = factor_rows[0] if factor_rows else {}
    factor_date_count = int(factor.get("date_count") or 0)
    factor_complete_date_count = int(factor.get("complete_date_count") or 0)
    label_horizons = {int(row["horizon"]): row for row in label_rows}
    missing_horizons = [horizon for horizon in horizons if horizon not in label_horizons]
    short_label_horizons = [
        horizon
        for horizon in horizons
        if horizon in label_horizons and int(label_horizons[horizon].get("date_count") or 0) < min_label_dates
    ]

    reasons = []
    if factor_date_count <= 0:
        reasons.append("missing_factor_rows")
    if factor_complete_date_count < min_label_dates:
        reasons.append("insufficient_complete_factor_dates")
    if missing_horizons:
        reasons.append("missing_label_horizons")
    if short_label_horizons:
        reasons.append("insufficient_label_dates")

    return {
        "status": "ok" if not reasons else "blocked",
        "reasons": reasons,
        "factor_min_date": factor.get("min_date"),
        "factor_max_date": factor.get("max_date"),
        "factor_date_count": factor_date_count,
        "factor_complete_date_count": factor_complete_date_count,
        "label_horizons": label_horizons,
        "missing_horizons": missing_horizons,
        "short_label_horizons": short_label_horizons,
        "min_label_dates": min_label_dates,
    }


def check_industry_membership_coverage(
    start_date: str,
    end_date: str,
    industry_system: str = "csrc",
    adjust_type: str = "hfq",
    service: str = SETTINGS.research_service,
) -> dict:
    sql = """
    SELECT
        count(*) AS market_rows,
        count(*) FILTER (WHERE has_membership) AS covered_rows,
        count(*) FILTER (WHERE NOT has_membership) AS missing_rows,
        count(DISTINCT trade_date) AS date_count
    FROM (
        SELECT
            b.trade_date,
            b.asset_id,
            EXISTS (
                SELECT 1
                FROM core.industry_membership m
                WHERE m.asset_id = b.asset_id
                  AND m.industry_system = %s
                  AND m.start_date <= b.trade_date
                  AND (m.end_date IS NULL OR b.trade_date < m.end_date)
            ) AS has_membership
        FROM market_daily_bar b
        WHERE b.adjust_type = %s
          AND b.trade_date BETWEEN %s AND %s
    ) covered
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, [industry_system, adjust_type, start_date, end_date])
    row = rows[0] if rows else {}
    market_rows = int(row.get("market_rows") or 0)
    covered_rows = int(row.get("covered_rows") or 0)
    missing_rows = int(row.get("missing_rows") or 0)
    return {
        "status": "ok" if missing_rows == 0 else "blocked",
        "market_rows": market_rows,
        "covered_rows": covered_rows,
        "missing_rows": missing_rows,
        "date_count": int(row.get("date_count") or 0),
    }
