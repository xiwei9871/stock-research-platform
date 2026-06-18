import datetime as dt
from typing import Any

from stock_research.config import SETTINGS
from stock_research.dashboard.schemas import BarPoint
from stock_research.db import connect, fetch_all

RESOLUTION_TRADING_DAYS = {
    "1D": 90,
    "60m": 40,
    "30m": 20,
    "10m": 8,
    "5m": 5,
}


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


def load_bars(
    asset_id: str,
    end_date: str,
    start_date: str | None = None,
    resolution: str = "1D",
    adjust_type: str = "qfq",
    source: str = "baostock",
    service: str = SETTINGS.research_service,
) -> list[dict[str, Any]]:
    normalized_resolution = normalize_resolution(resolution)
    if start_date is None:
        start_date, end_date = recent_trade_date_window(
            end_date=end_date,
            trading_days=RESOLUTION_TRADING_DAYS[normalized_resolution],
            service=service,
        )
    if normalized_resolution == "1D":
        return load_daily_bars(asset_id, start_date, end_date, adjust_type, service)

    minute_rows = load_minute_bars(
        asset_id=asset_id,
        start_time=f"{start_date} 09:30:00",
        end_time=f"{end_date} 15:00:00",
        freq="5min",
        adjust_type=adjust_type,
        source=source,
        service=service,
    )
    if normalized_resolution == "5m":
        return minute_rows
    return aggregate_minute_bars(minute_rows, normalized_resolution)


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


def normalize_resolution(resolution: str) -> str:
    text = str(resolution or "1D").strip()
    aliases = {
        "D": "1D",
        "1d": "1D",
        "day": "1D",
        "daily": "1D",
        "5min": "5m",
        "10min": "10m",
        "30min": "30m",
        "60min": "60m",
    }
    normalized = aliases.get(text, aliases.get(text.lower(), text))
    if normalized not in RESOLUTION_TRADING_DAYS:
        raise ValueError(f"unsupported bars resolution: {resolution}")
    return normalized


def recent_trade_date_window(
    *,
    end_date: str,
    trading_days: int,
    service: str = SETTINGS.research_service,
) -> tuple[str, str]:
    sql = """
    SELECT trade_date::text AS trade_date
    FROM market.trading_calendar
    WHERE exchange = 'SSE'
      AND is_open = TRUE
      AND trade_date <= %s
    ORDER BY trade_date DESC
    LIMIT %s
    """
    try:
        with connect(service) as conn:
            rows = fetch_all(conn, sql, [end_date, max(1, int(trading_days))])
    except Exception:
        rows = []
    dates = [str(row["trade_date"])[:10] for row in rows]
    if dates:
        return dates[-1], dates[0]
    end = dt.date.fromisoformat(str(end_date)[:10])
    start = end - dt.timedelta(days=max(1, int(trading_days)) * 2)
    return start.isoformat(), end.isoformat()


def aggregate_minute_bars(rows: list[dict[str, Any]], resolution: str) -> list[dict[str, Any]]:
    minutes = int(normalize_resolution(resolution).rstrip("m"))
    buckets: dict[tuple[str, int], list[dict[str, Any]]] = {}
    for row in rows:
        parsed = _parse_bar_time(str(row.get("time") or ""))
        if parsed is None:
            continue
        session_start = _session_start_minutes(parsed)
        if session_start is None:
            continue
        minute_of_day = parsed.hour * 60 + parsed.minute
        offset = minute_of_day - session_start
        if offset <= 0:
            continue
        bucket_index = (offset - 1) // minutes
        bucket_key = (parsed.date().isoformat(), session_start + (bucket_index + 1) * minutes)
        buckets.setdefault(bucket_key, []).append(row)

    result = []
    for (date_text, bucket_end_minutes), bucket_rows in sorted(buckets.items()):
        ordered = sorted(bucket_rows, key=lambda item: str(item.get("time") or ""))
        open_value = _first_number(ordered, "open")
        close_value = _last_number(ordered, "close")
        highs = [_to_float(item.get("high")) for item in ordered]
        lows = [_to_float(item.get("low")) for item in ordered]
        if (
            open_value is None
            or close_value is None
            or all(value is None for value in highs)
            or all(value is None for value in lows)
        ):
            continue
        result.append(
            {
                "time": _format_bucket_time(date_text, bucket_end_minutes),
                "open": open_value,
                "high": max(value for value in highs if value is not None),
                "low": min(value for value in lows if value is not None),
                "close": close_value,
                "volume": _sum_optional(ordered, "volume"),
                "amount": _sum_optional(ordered, "amount"),
            }
        )
    return result


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


def _parse_bar_time(value: str) -> dt.datetime | None:
    text = value.strip().replace("T", " ")
    try:
        return dt.datetime.fromisoformat(text)
    except ValueError:
        return None


def _session_start_minutes(value: dt.datetime) -> int | None:
    minute = value.hour * 60 + value.minute
    if 9 * 60 + 30 < minute <= 11 * 60 + 30:
        return 9 * 60 + 30
    if 13 * 60 < minute <= 15 * 60:
        return 13 * 60
    return None


def _format_bucket_time(date_text: str, minutes: int) -> str:
    hour, minute = divmod(minutes, 60)
    return f"{date_text} {hour:02d}:{minute:02d}:00"


def _first_number(rows: list[dict[str, Any]], column: str) -> float | None:
    for row in rows:
        value = _to_float(row.get(column))
        if value is not None:
            return value
    return None


def _last_number(rows: list[dict[str, Any]], column: str) -> float | None:
    for row in reversed(rows):
        value = _to_float(row.get(column))
        if value is not None:
            return value
    return None


def _sum_optional(rows: list[dict[str, Any]], column: str) -> float | None:
    values = [_to_float(row.get(column)) for row in rows]
    numeric = [value for value in values if value is not None]
    if not numeric:
        return None
    return float(sum(numeric))


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
