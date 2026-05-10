from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all


def check_factor_label_coverage(
    factor_names: list[str],
    start_date: str,
    end_date: str,
    horizons: list[int],
    calc_version: str = "v1",
    service: str = SETTINGS.research_service,
) -> dict:
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
          AND trade_date BETWEEN %s AND %s
        GROUP BY horizon
        ORDER BY horizon
    """
    with connect(service) as conn:
        factor_rows = fetch_all(conn, factor_sql, [factor_names, calc_version, start_date, end_date])
        label_rows = fetch_all(conn, label_sql, [horizons, start_date, end_date])
    factor = factor_rows[0] if factor_rows else {}
    label_horizons = {int(row["horizon"]): row for row in label_rows}
    status = "ok" if int(factor.get("date_count") or 0) > 0 and label_horizons else "blocked"
    return {
        "status": status,
        "factor_min_date": factor.get("min_date"),
        "factor_max_date": factor.get("max_date"),
        "factor_date_count": int(factor.get("date_count") or 0),
        "label_horizons": label_horizons,
    }
