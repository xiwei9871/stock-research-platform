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


def _latest_finance_rows(
    conn: psycopg.Connection,
    table_name: str,
    asset_ids: list[str],
    trade_date: str,
) -> dict[str, dict[str, Any]]:
    if not asset_ids:
        return {}

    sql = f"""
    SELECT DISTINCT ON (asset_id) *
    FROM {table_name}
    WHERE asset_id = ANY(%s)
      AND announcement_date <= %s
    ORDER BY asset_id, announcement_date DESC, report_period DESC
    """
    rows = fetch_all(conn, sql, [asset_ids, trade_date])
    return {str(row["asset_id"]): row for row in rows}


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


def get_latest_indicator_rows(
    conn: psycopg.Connection,
    asset_ids: list[str],
    trade_date: str,
) -> dict[str, dict[str, Any]]:
    return _latest_finance_rows(conn, "finance.indicator_quarter", asset_ids, trade_date)


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


def get_latest_income_statement_rows(
    conn: psycopg.Connection,
    asset_ids: list[str],
    trade_date: str,
) -> dict[str, dict[str, Any]]:
    return _latest_finance_rows(conn, "finance.income_statement", asset_ids, trade_date)


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


def get_latest_balance_sheet_rows(
    conn: psycopg.Connection,
    asset_ids: list[str],
    trade_date: str,
) -> dict[str, dict[str, Any]]:
    return _latest_finance_rows(conn, "finance.balance_sheet", asset_ids, trade_date)


def get_latest_cash_flow(
    conn: psycopg.Connection,
    asset_id: str,
    trade_date: str,
) -> dict[str, Any] | None:
    return _latest_finance_row(conn, "finance.cash_flow", asset_id, trade_date)


def get_latest_cash_flow_rows(
    conn: psycopg.Connection,
    asset_ids: list[str],
    trade_date: str,
) -> dict[str, dict[str, Any]]:
    return _latest_finance_rows(conn, "finance.cash_flow", asset_ids, trade_date)


def get_latest_share_capital_event_rows(
    conn: psycopg.Connection,
    asset_ids: list[str],
    trade_date: str,
) -> dict[str, dict[str, Any]]:
    if not asset_ids:
        return {}

    sql = """
    SELECT DISTINCT ON (asset_id) *
    FROM finance.share_capital_event
    WHERE asset_id = ANY(%s)
      AND event_date <= %s
      AND (announcement_date IS NULL OR announcement_date <= %s)
    ORDER BY asset_id, event_date DESC, announcement_date DESC NULLS LAST
    """
    rows = fetch_all(conn, sql, [asset_ids, trade_date, trade_date])
    return {str(row["asset_id"]): row for row in rows}
