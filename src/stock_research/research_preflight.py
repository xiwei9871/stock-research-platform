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
        SELECT min(trade_date) AS min_date, max(trade_date) AS max_date,
               count(DISTINCT trade_date) AS date_count
        FROM factor.factor_daily
        WHERE factor_name = ANY(%s)
          AND calc_version = %s
          AND trade_date BETWEEN %s AND %s
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
        factor_rows = fetch_all(conn, factor_sql, [factor_names, calc_version, start_date, end_date])
        label_rows = fetch_all(conn, label_sql, [horizons, start_date, end_date])

    factor = factor_rows[0] if factor_rows else {}
    factor_date_count = int(factor.get("date_count") or 0)
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
        "label_horizons": label_horizons,
        "missing_horizons": missing_horizons,
        "short_label_horizons": short_label_horizons,
        "min_label_dates": min_label_dates,
    }
