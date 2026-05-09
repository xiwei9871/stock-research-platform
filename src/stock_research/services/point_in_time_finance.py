from typing import Any

import psycopg

from stock_research.db import fetch_all


def _latest_finance_row(
    conn: psycopg.Connection,
    table_name: str,
    asset_id: str,
    trade_date: str,
) -> dict[str, Any] | None:
    sql = f"""
    SELECT *
    FROM {table_name}
    WHERE asset_id = %s
      AND announcement_date <= %s
    ORDER BY announcement_date DESC, report_period DESC
    LIMIT 1
    """
    rows = fetch_all(conn, sql, [asset_id, trade_date])
    return rows[0] if rows else None


def get_latest_indicator(
    conn: psycopg.Connection,
    asset_id: str,
    trade_date: str,
) -> dict[str, Any] | None:
    return _latest_finance_row(
        conn,
        "finance.indicator_quarter",
        asset_id,
        trade_date,
    )


def get_latest_income_statement(
    conn: psycopg.Connection,
    asset_id: str,
    trade_date: str,
) -> dict[str, Any] | None:
    return _latest_finance_row(
        conn,
        "finance.income_statement",
        asset_id,
        trade_date,
    )


def get_latest_balance_sheet(
    conn: psycopg.Connection,
    asset_id: str,
    trade_date: str,
) -> dict[str, Any] | None:
    return _latest_finance_row(
        conn,
        "finance.balance_sheet",
        asset_id,
        trade_date,
    )


def get_latest_cash_flow(
    conn: psycopg.Connection,
    asset_id: str,
    trade_date: str,
) -> dict[str, Any] | None:
    return _latest_finance_row(conn, "finance.cash_flow", asset_id, trade_date)
