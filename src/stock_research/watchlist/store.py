import json
from typing import Any

import pandas as pd

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all


WATCHLIST_ITEM_COLUMNS = [
    "watchlist_id",
    "asset_id",
    "stock_code",
    "stock_name",
    "priority",
    "active",
    "note",
    "source",
]

WATCHLIST_SIGNAL_COLUMNS = [
    "watchlist_id",
    "trade_date",
    "asset_id",
    "stock_code",
    "stock_name",
    "priority",
    "signal_score",
    "primary_signal",
    "signal_tags",
    "risk_tags",
    "must_watch",
    "reason_json",
    "output_version",
]


def upsert_watchlist_items(
    items: pd.DataFrame,
    service: str = SETTINGS.research_service,
) -> int:
    if items.empty:
        return 0

    rows = items.to_dict("records")
    sql = """
    INSERT INTO watchlist.watchlist_item (
        watchlist_id, asset_id, stock_code, stock_name, priority, active, note, source
    )
    VALUES (
        %(watchlist_id)s, %(asset_id)s, %(stock_code)s, %(stock_name)s,
        %(priority)s, %(active)s, %(note)s, %(source)s
    )
    ON CONFLICT (watchlist_id, asset_id)
    DO UPDATE SET
        stock_code = EXCLUDED.stock_code,
        stock_name = EXCLUDED.stock_name,
        priority = EXCLUDED.priority,
        active = EXCLUDED.active,
        note = EXCLUDED.note,
        source = EXCLUDED.source,
        updated_at = now()
    """
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.executemany(sql, rows)
    return len(rows)


def load_watchlist_items(
    watchlist_id: str,
    active_only: bool = True,
    service: str = SETTINGS.research_service,
) -> pd.DataFrame:
    sql = """
    SELECT
        watchlist_id,
        asset_id,
        stock_code,
        stock_name,
        priority,
        active,
        note,
        source
    FROM watchlist.watchlist_item
    WHERE watchlist_id = %s
    """
    params: list[Any] = [watchlist_id]
    if active_only:
        sql += "\n      AND active = true"
    sql += "\n    ORDER BY priority, stock_code"
    with connect(service) as conn:
        rows = fetch_all(conn, sql, params)
    return pd.DataFrame(rows)


def store_watchlist_daily_signals(
    signals: pd.DataFrame,
    service: str = SETTINGS.research_service,
) -> int:
    if signals.empty:
        return 0

    rows = [_signal_row(row) for row in signals.to_dict("records")]
    sql = """
    INSERT INTO watchlist.watchlist_daily_signal (
        watchlist_id, trade_date, asset_id, stock_code, stock_name, priority,
        signal_score, primary_signal, signal_tags, risk_tags, must_watch,
        reason_json, output_version
    )
    VALUES (
        %(watchlist_id)s, %(trade_date)s, %(asset_id)s, %(stock_code)s, %(stock_name)s,
        %(priority)s, %(signal_score)s, %(primary_signal)s, %(signal_tags)s::jsonb,
        %(risk_tags)s::jsonb, %(must_watch)s, %(reason_json)s::jsonb, %(output_version)s
    )
    ON CONFLICT (watchlist_id, trade_date, asset_id)
    DO UPDATE SET
        stock_code = EXCLUDED.stock_code,
        stock_name = EXCLUDED.stock_name,
        priority = EXCLUDED.priority,
        signal_score = EXCLUDED.signal_score,
        primary_signal = EXCLUDED.primary_signal,
        signal_tags = EXCLUDED.signal_tags,
        risk_tags = EXCLUDED.risk_tags,
        must_watch = EXCLUDED.must_watch,
        reason_json = EXCLUDED.reason_json,
        output_version = EXCLUDED.output_version,
        updated_at = now()
    """
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.executemany(sql, rows)
    return len(rows)


def load_watchlist_daily_signals(
    watchlist_id: str,
    trade_date: object | None = None,
    service: str = SETTINGS.research_service,
) -> pd.DataFrame:
    sql = """
    SELECT
        watchlist_id,
        trade_date,
        asset_id,
        stock_code,
        stock_name,
        priority,
        signal_score,
        primary_signal,
        signal_tags,
        risk_tags,
        must_watch,
        reason_json,
        output_version
    FROM watchlist.watchlist_daily_signal
    WHERE watchlist_id = %s
    """
    params: list[Any] = [watchlist_id]
    if trade_date is not None:
        sql += "\n      AND trade_date = %s"
        params.append(trade_date)
    sql += "\n    ORDER BY must_watch DESC, priority, stock_code"
    with connect(service) as conn:
        rows = fetch_all(conn, sql, params)
    return pd.DataFrame(rows)


def _signal_row(row: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(row)
    normalized["signal_tags"] = _json_dumps(normalized.get("signal_tags", []))
    normalized["risk_tags"] = _json_dumps(normalized.get("risk_tags", []))
    normalized["reason_json"] = _json_dumps(normalized.get("reason_json", {}))
    return normalized


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)
