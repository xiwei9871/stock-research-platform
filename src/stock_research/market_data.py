import hashlib
import json
from typing import Any

from stock_research.assets import (
    asset_id_from_baostock_code,
    discover_source_tables,
    is_stock_table,
)
from stock_research.config import SETTINGS
from stock_research.db import connect, execute_many, fetch_all


def parse_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def normalize_source_row(row: dict[str, Any], adjust_type: str) -> dict[str, Any]:
    return {
        "asset_id": asset_id_from_baostock_code(row["stock_code"]),
        "trade_date": str(row["trade_date"]),
        "open": parse_float(row["open_price"]),
        "high": parse_float(row["high_price"]),
        "low": parse_float(row["low_price"]),
        "close": parse_float(row["close_price"]),
        "preclose": parse_float(row["preclose_price"]),
        "volume": parse_float(row["volume"]),
        "amount": parse_float(row["amount"]),
        "turnover_rate": parse_float(row["turnover"]),
        "pct_chg": parse_float(row["pctChg"]),
        "trade_status": str(row["tradestatus"]),
        "is_st": str(row["isST"]) == "1",
        "adjust_type": adjust_type,
        "source": "baostock",
    }


def jsonable_payload(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): jsonable_payload(item) for key, item in value.items()}
    if isinstance(value, list):
        return [jsonable_payload(item) for item in value]
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def canonical_payload_json(payload: dict[str, Any]) -> str:
    return json.dumps(
        jsonable_payload(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def raw_payload_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_payload_json(payload).encode("utf-8")).hexdigest()


def raw_daily_bar_payload_row(
    source_service: str,
    table_name: str,
    adjust_type: str,
    row: dict[str, Any],
) -> dict[str, Any]:
    payload = jsonable_payload(row)
    return {
        "source_service": source_service,
        "source_table": table_name,
        "adjust_type": adjust_type,
        "trade_date": str(row["trade_date"])[:10],
        "asset_id": asset_id_from_baostock_code(row["stock_code"]),
        "payload": payload,
        "payload_hash": raw_payload_hash(payload),
    }


def fetch_source_rows(
    service: str,
    table_name: str,
    start_date: str | None,
    end_date: str | None,
) -> list[dict[str, Any]]:
    if not is_stock_table(table_name):
        raise ValueError(f"Invalid stock table name: {table_name}")

    filters = []
    params: list[Any] = []
    if start_date:
        filters.append("trade_date >= %s")
        params.append(start_date)
    if end_date:
        filters.append("trade_date <= %s")
        params.append(end_date)
    where_sql = f"WHERE {' AND '.join(filters)}" if filters else ""

    sql = f"""
    SELECT
        trade_date,
        stock_code,
        open_price,
        high_price,
        low_price,
        close_price,
        preclose_price,
        volume,
        amount,
        adjustflag,
        turnover,
        tradestatus,
        "pctChg",
        "isST"
    FROM {table_name}
    {where_sql}
    ORDER BY trade_date
    """
    with connect(service) as conn:
        return fetch_all(conn, sql, params)


def latest_source_trade_date(service: str, table_name: str = "sh600000") -> str | None:
    if not is_stock_table(table_name):
        raise ValueError(f"Invalid stock table name: {table_name}")

    sql = f"SELECT max(trade_date)::text AS trade_date FROM {table_name}"
    with connect(service) as conn:
        rows = fetch_all(conn, sql)
    return rows[0]["trade_date"]


def upsert_raw_daily_bar_payloads(
    rows: list[dict[str, Any]],
    research_service: str = SETTINGS.research_service,
) -> int:
    if not rows:
        return 0

    sql = """
    INSERT INTO raw_baostock.daily_bar_payload (
        source_service, source_table, adjust_type, trade_date, asset_id, payload, payload_hash
    )
    VALUES (
        %(source_service)s, %(source_table)s, %(adjust_type)s, %(trade_date)s,
        %(asset_id)s, %(payload)s::jsonb, %(payload_hash)s
    )
    ON CONFLICT (source_service, source_table, adjust_type, trade_date, asset_id)
    DO UPDATE SET
        payload = EXCLUDED.payload,
        payload_hash = EXCLUDED.payload_hash,
        fetched_at = now()
    """
    params = [
        {
            **row,
            "payload": canonical_payload_json(row["payload"]),
        }
        for row in rows
    ]
    with connect(research_service) as conn:
        execute_many(conn, sql, params)
    return len(rows)


def upsert_market_rows(
    rows: list[dict[str, Any]],
    research_service: str = SETTINGS.research_service,
) -> int:
    if not rows:
        return 0

    sql = """
    INSERT INTO market_daily_bar (
        asset_id, trade_date, open, high, low, close, preclose, volume, amount,
        turnover_rate, pct_chg, trade_status, is_st, adjust_type, source
    )
    VALUES (
        %(asset_id)s, %(trade_date)s, %(open)s, %(high)s, %(low)s, %(close)s,
        %(preclose)s, %(volume)s, %(amount)s, %(turnover_rate)s, %(pct_chg)s,
        %(trade_status)s, %(is_st)s, %(adjust_type)s, %(source)s
    )
    ON CONFLICT (asset_id, trade_date, adjust_type) DO UPDATE SET
        open = EXCLUDED.open,
        high = EXCLUDED.high,
        low = EXCLUDED.low,
        close = EXCLUDED.close,
        preclose = EXCLUDED.preclose,
        volume = EXCLUDED.volume,
        amount = EXCLUDED.amount,
        turnover_rate = EXCLUDED.turnover_rate,
        pct_chg = EXCLUDED.pct_chg,
        trade_status = EXCLUDED.trade_status,
        is_st = EXCLUDED.is_st,
        source = EXCLUDED.source,
        updated_at = now()
    """
    with connect(research_service) as conn:
        with conn.cursor() as cur:
            cur.executemany(sql, rows)
    return len(rows)


def load_market_daily_bars(
    source_service: str,
    adjust_type: str,
    start_date: str | None = None,
    end_date: str | None = None,
    limit_tables: int | None = None,
    archive_raw: bool = False,
) -> int:
    tables = discover_source_tables(source_service)
    if limit_tables is not None:
        tables = tables[:limit_tables]

    total = 0
    for table_name in tables:
        source_rows = fetch_source_rows(source_service, table_name, start_date, end_date)
        if archive_raw:
            upsert_raw_daily_bar_payloads(
                [
                    raw_daily_bar_payload_row(source_service, table_name, adjust_type, row)
                    for row in source_rows
                ]
            )
        normalized = [normalize_source_row(row, adjust_type) for row in source_rows]
        total += upsert_market_rows(normalized)
    return total
