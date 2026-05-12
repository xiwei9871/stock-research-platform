from typing import Any

from stock_research.db import fetch_all


def calc_ttm_from_cumulative_rows(
    rows: list[dict[str, Any]],
    *,
    value_column: str,
    trade_date: str,
) -> float | None:
    available = [
        row
        for row in rows
        if str(row["announcement_date"])[:10] <= trade_date
        and row.get(value_column) is not None
    ]
    by_period = {
        str(row["report_period"])[:10]: float(row[value_column]) for row in available
    }
    if not by_period:
        return None

    latest_period = max(by_period)
    latest_value = by_period[latest_period]
    if latest_period.endswith("-12-31"):
        return latest_value

    year = int(latest_period[:4])
    suffix = latest_period[4:]
    previous_fy = f"{year - 1}-12-31"
    prior_same_period = f"{year - 1}{suffix}"
    if previous_fy not in by_period or prior_same_period not in by_period:
        return None
    return latest_value + by_period[previous_fy] - by_period[prior_same_period]


def load_income_ttm(
    conn,
    asset_id: str,
    trade_date: str,
    *,
    value_column: str,
) -> float | None:
    sql = f"""
    SELECT report_period, announcement_date, {value_column}
    FROM finance.income_statement
    WHERE asset_id = %s
      AND announcement_date <= %s
      AND {value_column} IS NOT NULL
    ORDER BY report_period DESC, announcement_date DESC
    """
    rows = fetch_all(conn, sql, [asset_id, trade_date])
    return calc_ttm_from_cumulative_rows(
        rows,
        value_column=value_column,
        trade_date=trade_date,
    )
