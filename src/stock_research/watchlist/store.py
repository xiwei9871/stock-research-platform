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

WATCHLIST_ITEM_DEFAULTS = {
    "priority": 100,
    "active": True,
}

WATCHLIST_SIGNAL_DEFAULTS = {
    "priority": 100,
    "signal_tags": [],
    "risk_tags": [],
    "must_watch": False,
    "reason_json": {},
}


def upsert_watchlist_items(
    items: pd.DataFrame,
    service: str = SETTINGS.research_service,
) -> int:
    if items.empty:
        return 0

    rows = _shape_rows(items, WATCHLIST_ITEM_COLUMNS, WATCHLIST_ITEM_DEFAULTS)
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
    return pd.DataFrame(rows, columns=WATCHLIST_ITEM_COLUMNS)


def store_watchlist_daily_signals(
    signals: pd.DataFrame,
    service: str = SETTINGS.research_service,
) -> int:
    if signals.empty:
        return 0

    rows = _shape_rows(signals, WATCHLIST_SIGNAL_COLUMNS, WATCHLIST_SIGNAL_DEFAULTS)
    rows = [_signal_row(row) for row in rows]
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
    return pd.DataFrame(rows, columns=WATCHLIST_SIGNAL_COLUMNS)


def _signal_row(row: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(row)
    normalized["signal_tags"] = _json_dumps(_clean_json_value(normalized["signal_tags"]))
    normalized["risk_tags"] = _json_dumps(_clean_json_value(normalized["risk_tags"]))
    normalized["reason_json"] = _json_dumps(_clean_json_value(normalized["reason_json"]))
    return normalized


def _shape_rows(
    frame: pd.DataFrame,
    columns: list[str],
    defaults: dict[str, Any],
) -> list[dict[str, Any]]:
    shaped_rows: list[dict[str, Any]] = []
    for record in frame.to_dict("records"):
        shaped_row: dict[str, Any] = {}
        for column in columns:
            value = record.get(column)
            if column in defaults and _is_missing(value):
                value = defaults[column]
            shaped_row[column] = value
        shaped_rows.append(shaped_row)
    return shaped_rows


def _clean_json_value(value: Any) -> Any:
    if _is_missing(value):
        return None
    if isinstance(value, dict):
        return {key: _clean_json_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_clean_json_value(item) for item in value]
    if isinstance(value, tuple):
        return [_clean_json_value(item) for item in value]
    return value


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, (list, tuple, dict)):
        return False
    try:
        return bool(pd.isna(value))
    except Exception:
        return False


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)
