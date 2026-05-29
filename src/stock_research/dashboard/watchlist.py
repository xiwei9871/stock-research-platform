from typing import Any

from stock_research.config import SETTINGS
from stock_research.dashboard.schemas import WatchlistSignalRow
from stock_research.db import connect, fetch_all


def load_watchlist_signals_for_dashboard(
    watchlist_id: str,
    trade_date: str,
    service: str = SETTINGS.research_service,
) -> list[dict[str, Any]]:
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
        reason_json
    FROM watchlist.watchlist_daily_signal
    WHERE watchlist_id = %s
      AND trade_date = %s
    ORDER BY must_watch DESC, priority ASC, signal_score DESC NULLS LAST, asset_id
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, [watchlist_id, trade_date])
    return [_signal_row(row).to_dict() for row in rows]


def load_asset_watchlist_signals_for_dashboard(
    asset_id: str,
    trade_date: str,
    service: str = SETTINGS.research_service,
) -> list[dict[str, Any]]:
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
        reason_json
    FROM watchlist.watchlist_daily_signal
    WHERE asset_id = %s
      AND trade_date = %s
    ORDER BY must_watch DESC, priority ASC, signal_score DESC NULLS LAST, watchlist_id
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, [asset_id, trade_date])
    return [_signal_row(row).to_dict() for row in rows]


def _signal_row(row: dict[str, Any]) -> WatchlistSignalRow:
    return WatchlistSignalRow(
        watchlist_id=str(row["watchlist_id"]),
        trade_date=str(row["trade_date"]),
        asset_id=str(row["asset_id"]),
        stock_code=str(row["stock_code"]),
        stock_name=str(row["stock_name"]),
        priority=int(row["priority"]),
        signal_score=_float_or_none(row.get("signal_score")),
        primary_signal=str(row["primary_signal"]),
        signal_tags=_json_list(row.get("signal_tags"), "signal_tags"),
        risk_tags=_json_list(row.get("risk_tags"), "risk_tags"),
        must_watch=bool(row["must_watch"]),
        reason_json=_json_dict(row.get("reason_json"), "reason_json"),
    )


def _json_list(value: Any, field_name: str) -> list[Any]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be a JSON array")
    return value


def _json_dict(value: Any, field_name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be a JSON object")
    return value


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)
