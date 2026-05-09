from typing import Any

import psycopg

from stock_research.db import fetch_all


def get_membership(
    conn: psycopg.Connection,
    asset_id: str,
    trade_date: str,
    industry_system: str,
) -> dict[str, Any] | None:
    sql = """
    SELECT *
    FROM core.industry_membership
    WHERE asset_id = %s
      AND industry_system = %s
      AND start_date <= %s
      AND (end_date IS NULL OR %s < end_date)
    ORDER BY level DESC, start_date DESC
    LIMIT 1
    """
    rows = fetch_all(conn, sql, [asset_id, industry_system, trade_date, trade_date])
    return rows[0] if rows else None
