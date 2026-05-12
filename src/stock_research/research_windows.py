from typing import Any

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all


def _date_text(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)[:10]


def _empty_window() -> dict[str, str | int | None]:
    return {"start_date": None, "end_date": None, "date_count": 0}


def load_market_date_bounds(
    *,
    adjust_type: str = "hfq",
    service: str = SETTINGS.research_service,
) -> dict[str, str | int | None]:
    sql = """
    SELECT
        min(trade_date) AS min_date,
        max(trade_date) AS max_date,
        count(DISTINCT trade_date) AS date_count
    FROM market_daily_bar
    WHERE adjust_type = %s
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, [adjust_type])
    row = rows[0] if rows else {}
    return {
        "start_date": _date_text(row.get("min_date")),
        "end_date": _date_text(row.get("max_date")),
        "date_count": int(row.get("date_count") or 0),
    }


def load_trade_dates(
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
    return [_date_text(row["trade_date"]) or "" for row in rows]


def derive_feature_window(
    *,
    start_date: str,
    end_date: str,
    lookback_bars: int,
    adjust_type: str = "hfq",
    service: str = SETTINGS.research_service,
) -> dict[str, str | int | None]:
    if lookback_bars < 1:
        raise ValueError("lookback_bars must be >= 1")
    dates = load_trade_dates(
        start_date,
        end_date,
        adjust_type=adjust_type,
        service=service,
    )
    usable = dates[lookback_bars - 1 :]
    if not usable:
        return _empty_window()
    return {
        "start_date": usable[0],
        "end_date": usable[-1],
        "date_count": len(usable),
    }


def derive_label_window(
    *,
    start_date: str,
    end_date: str,
    horizons: list[int],
    adjust_type: str = "hfq",
    service: str = SETTINGS.research_service,
) -> dict[str, str | int | None]:
    if not horizons:
        raise ValueError("horizons must not be empty")
    max_horizon = max(horizons)
    if max_horizon < 1:
        raise ValueError("horizons must be positive")
    dates = load_trade_dates(
        start_date,
        end_date,
        adjust_type=adjust_type,
        service=service,
    )
    usable = dates[: len(dates) - max_horizon]
    if not usable:
        return _empty_window()
    return {
        "start_date": usable[0],
        "end_date": usable[-1],
        "date_count": len(usable),
    }
