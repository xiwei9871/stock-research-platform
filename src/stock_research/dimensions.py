from collections.abc import Iterable

import pandas as pd

from stock_research.config import SETTINGS
from stock_research.db import connect, execute_many, fetch_all


def build_calendar_rows(
    trade_dates: Iterable[str],
    exchanges: Iterable[str],
    *,
    source: str,
    source_version: str,
) -> list[dict[str, object]]:
    rows = []
    for trade_date in trade_dates:
        normalized_trade_date = str(trade_date)[:10]
        for exchange in exchanges:
            rows.append(
                {
                    "exchange": str(exchange),
                    "trade_date": normalized_trade_date,
                    "is_open": True,
                    "source": source,
                    "source_version": source_version,
                }
            )
    return rows


def load_distinct_market_trade_dates(
    start_date: str,
    end_date: str,
    *,
    adjust_type: str = "hfq",
    service: str = SETTINGS.research_service,
) -> list[str]:
    sql = """
    SELECT DISTINCT trade_date
    FROM market_daily_bar
    WHERE adjust_type = %s
      AND trade_date BETWEEN %s AND %s
    ORDER BY trade_date
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, [adjust_type, start_date, end_date])
    return [str(row["trade_date"])[:10] for row in rows]


def upsert_trading_calendar(conn, rows: list[dict[str, object]]) -> int:
    if not rows:
        return 0
    sql = """
    INSERT INTO market.trading_calendar (
        exchange, trade_date, is_open, source, source_version
    )
    VALUES (%s, %s, %s, %s, %s)
    ON CONFLICT (exchange, trade_date, source_version) DO UPDATE SET
        is_open = EXCLUDED.is_open,
        source = EXCLUDED.source,
        updated_at = now()
    """
    execute_many(
        conn,
        sql,
        [
            (
                row["exchange"],
                row["trade_date"],
                row["is_open"],
                row["source"],
                row["source_version"],
            )
            for row in rows
        ],
    )
    return len(rows)


def seed_trading_calendar_from_bars(
    start_date: str,
    end_date: str,
    *,
    exchanges: Iterable[str],
    source_version: str,
    adjust_type: str = "hfq",
    service: str = SETTINGS.research_service,
) -> int:
    trade_dates = load_distinct_market_trade_dates(
        start_date,
        end_date,
        adjust_type=adjust_type,
        service=service,
    )
    rows = build_calendar_rows(
        trade_dates,
        exchanges,
        source="derived:market_daily_bar",
        source_version=source_version,
    )
    with connect(service) as conn:
        return upsert_trading_calendar(conn, rows)


def load_asset_master_lifecycle_inputs(
    service: str = SETTINGS.research_service,
) -> list[dict[str, object]]:
    sql = """
    SELECT asset_id, list_date, delist_date
    FROM core.asset_master
    ORDER BY asset_id
    """
    with connect(service) as conn:
        return fetch_all(conn, sql)


def build_lifecycle_rows_from_assets(
    assets: Iterable[dict[str, object]],
    *,
    source_version: str,
) -> list[dict[str, object]]:
    rows = []
    for asset in assets:
        asset_id = str(asset["asset_id"])
        list_date = asset.get("list_date")
        delist_date = asset.get("delist_date")
        if list_date is not None:
            rows.append(
                {
                    "asset_id": asset_id,
                    "event_date": str(list_date)[:10],
                    "event_type": "listed",
                    "event_value": None,
                    "source": "core.asset_master",
                    "source_version": source_version,
                }
            )
        if delist_date is not None:
            rows.append(
                {
                    "asset_id": asset_id,
                    "event_date": str(delist_date)[:10],
                    "event_type": "delisted",
                    "event_value": None,
                    "source": "core.asset_master",
                    "source_version": source_version,
                }
            )
    return rows


def upsert_asset_lifecycle_events(conn, rows: list[dict[str, object]]) -> int:
    if not rows:
        return 0
    sql = """
    INSERT INTO core.asset_lifecycle_event (
        asset_id, event_date, event_type, event_value, source, source_version
    )
    VALUES (%s, %s, %s, %s, %s, %s)
    ON CONFLICT (asset_id, event_date, event_type, source_version) DO UPDATE SET
        event_value = EXCLUDED.event_value,
        source = EXCLUDED.source,
        updated_at = now()
    """
    execute_many(
        conn,
        sql,
        [
            (
                row["asset_id"],
                row["event_date"],
                row["event_type"],
                row["event_value"],
                row["source"],
                row["source_version"],
            )
            for row in rows
        ],
    )
    return len(rows)


def sync_asset_lifecycle_from_master(
    *,
    source_version: str = "core_asset_master_v1",
    service: str = SETTINGS.research_service,
) -> int:
    assets = load_asset_master_lifecycle_inputs(service=service)
    rows = build_lifecycle_rows_from_assets(assets, source_version=source_version)
    with connect(service) as conn:
        return upsert_asset_lifecycle_events(conn, rows)
