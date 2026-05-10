from collections.abc import Callable
import time

import pandas as pd

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all
from stock_research.factor_pipeline import build_and_store_factor_daily


def build_trade_date_range(start_date: str, end_date: str) -> list[str]:
    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date)
    if end < start:
        raise ValueError("end_date must be >= start_date")
    return [value.date().isoformat() for value in pd.date_range(start, end, freq="D")]


def load_trade_dates_for_backfill(
    start_date: str,
    end_date: str,
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


def backfill_factor_daily_range(
    start_date: str,
    end_date: str,
    lookback_bars: int = 130,
    industry_system: str = "csrc",
    trading_days_only: bool = True,
    adjust_type: str = "hfq",
    progress: Callable[[dict], None] | None = None,
    clock: Callable[[], float] = time.perf_counter,
) -> pd.DataFrame:
    rows = []
    trade_dates = (
        load_trade_dates_for_backfill(
            start_date=start_date,
            end_date=end_date,
            adjust_type=adjust_type,
        )
        if trading_days_only
        else build_trade_date_range(start_date, end_date)
    )
    total_dates = len(trade_dates)
    for index, trade_date in enumerate(trade_dates, start=1):
        if progress is not None:
            progress({"event": "start", "trade_date": trade_date, "index": index, "total": total_dates})
        started_at = clock()
        count = build_and_store_factor_daily(
            trade_date=trade_date,
            lookback_bars=lookback_bars,
            industry_system=industry_system,
        )
        elapsed_seconds = clock() - started_at
        if progress is not None:
            progress(
                {
                    "event": "done",
                    "trade_date": trade_date,
                    "index": index,
                    "total": total_dates,
                    "factor_rows": count,
                    "elapsed_seconds": elapsed_seconds,
                }
            )
        rows.append({"trade_date": trade_date, "factor_rows": count})
    return pd.DataFrame(rows)
