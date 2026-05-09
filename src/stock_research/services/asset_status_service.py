from typing import Any

import psycopg

from stock_research.db import fetch_all


def get_status(
    conn: psycopg.Connection,
    asset_id: str,
    trade_date: str,
) -> dict[str, Any] | None:
    sql = """
    SELECT *
    FROM core.asset_status_daily
    WHERE asset_id = %s
      AND trade_date = %s
    LIMIT 1
    """
    rows = fetch_all(conn, sql, [asset_id, trade_date])
    return rows[0] if rows else None


def is_tradable(
    conn: psycopg.Connection,
    asset_id: str,
    trade_date: str,
    *,
    allow_limit_up: bool = False,
) -> bool:
    status = get_status(conn, asset_id, trade_date)
    if status is None:
        return False
    if not status["is_trade"]:
        return False
    if status["is_st"]:
        return False
    if status["is_suspended"]:
        return False
    return allow_limit_up or not status["is_limit_up"]
