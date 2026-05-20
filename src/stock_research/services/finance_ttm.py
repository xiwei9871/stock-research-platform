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
    by_period: dict[str, float] = {}
    for row in available:
        period = str(row["report_period"])[:10]
        if period in by_period:
            continue
        by_period[period] = float(row[value_column])
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
    rows = load_income_ttm_rows(
        conn,
        [str(asset_id)],
        trade_date,
        value_columns=[value_column],
    )
    return rows.get(str(asset_id), {}).get(f"{value_column}_ttm")


def load_income_ttm_rows(
    conn,
    asset_ids: list[str],
    trade_date: str,
    *,
    value_columns: list[str],
) -> dict[str, dict[str, float | None]]:
    if not asset_ids or not value_columns:
        return {}

    selected_columns = ", ".join(value_columns)
    non_null_filters = " OR ".join(f"{value_column} IS NOT NULL" for value_column in value_columns)
    sql = f"""
    SELECT asset_id, report_period, announcement_date, {selected_columns}
    FROM finance.income_statement
    WHERE asset_id = ANY(%s)
      AND announcement_date <= %s
      AND ({non_null_filters})
    ORDER BY asset_id, report_period DESC, announcement_date DESC
    """
    rows = fetch_all(conn, sql, [asset_ids, trade_date])
    rows_by_asset: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        rows_by_asset.setdefault(str(row["asset_id"]), []).append(row)

    ttm_rows: dict[str, dict[str, float | None]] = {}
    for asset_id in asset_ids:
        asset_key = str(asset_id)
        asset_rows = rows_by_asset.get(asset_key, [])
        if not asset_rows:
            continue
        ttm_rows[asset_key] = {
            f"{value_column}_ttm": calc_ttm_from_cumulative_rows(
                asset_rows,
                value_column=value_column,
                trade_date=trade_date,
            )
            for value_column in value_columns
        }
    return ttm_rows
