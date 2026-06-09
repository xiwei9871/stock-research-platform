from typing import Any

from stock_research.config import SETTINGS
from stock_research.dashboard.schemas import BarPoint
from stock_research.db import connect, fetch_all


def normalize_market_asset_id(asset_id: str) -> str:
    text = str(asset_id or "").strip().upper()
    if text.startswith("CN:"):
        return text
    if "." not in text:
        return text
    code, exchange = text.split(".", 1)
    if exchange in {"SH", "SZ", "BJ"} and len(code) == 6 and code.isdigit():
        return f"CN:{exchange}:{code}"
    return text


def load_daily_bars(
    asset_id: str,
    start_date: str,
    end_date: str,
    adjust_type: str = "qfq",
    service: str = SETTINGS.research_service,
) -> list[dict[str, Any]]:
    sql = """
    SELECT
        trade_date::text AS time,
        open,
        high,
        low,
        close,
        volume,
        amount
    FROM market_daily_bar
    WHERE asset_id = %s
      AND trade_date BETWEEN %s AND %s
      AND adjust_type = %s
    ORDER BY trade_date
    """
    with connect(service) as conn:
        rows = fetch_all(
            conn,
            sql,
            [normalize_market_asset_id(asset_id), start_date, end_date, adjust_type],
        )
    return [_bar_point(row).to_dict() for row in rows]


def load_minute_bars(
    asset_id: str,
    start_time: str,
    end_time: str,
    freq: str = "5min",
    adjust_type: str = "qfq",
    source: str = "baostock",
    service: str = SETTINGS.research_service,
) -> list[dict[str, Any]]:
    sql = """
    SELECT
        trade_time::text AS time,
        open,
        high,
        low,
        close,
        volume,
        amount
    FROM market.stock_minute_bar
    WHERE asset_id = %s
      AND trade_time BETWEEN %s AND %s
      AND freq = %s
      AND adjust_type = %s
      AND source = %s
    ORDER BY trade_time
    """
    with connect(service) as conn:
        rows = fetch_all(
            conn,
            sql,
            [
                normalize_market_asset_id(asset_id),
                start_time,
                end_time,
                freq,
                adjust_type,
                source,
            ],
        )
    return [_bar_point(row).to_dict() for row in rows]


def _bar_point(row: dict[str, Any]) -> BarPoint:
    return BarPoint(
        time=str(row["time"]),
        open=_float_or_none(row.get("open")),
        high=_float_or_none(row.get("high")),
        low=_float_or_none(row.get("low")),
        close=_float_or_none(row.get("close")),
        volume=_float_or_none(row.get("volume")),
        amount=_float_or_none(row.get("amount")),
    )


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)
