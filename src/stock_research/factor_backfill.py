from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor, as_completed
import time

import pandas as pd

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all
from stock_research.factor_config import manual_v1_config
from stock_research.factor_pipeline import build_and_store_factor_daily
from stock_research.research_windows import derive_feature_window, load_market_date_bounds


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


def load_complete_factor_dates(
    start_date: str,
    end_date: str,
    expected_factor_count: int | None = None,
    calc_version: str | None = None,
    service: str = SETTINGS.research_service,
) -> set[str]:
    config = manual_v1_config()
    expected = expected_factor_count or len(config["factor_groups"])
    version = calc_version or config["calc_version"]
    sql = """
    SELECT trade_date
    FROM factor.factor_daily
    WHERE trade_date BETWEEN %s AND %s
      AND calc_version = %s
    GROUP BY trade_date
    HAVING count(DISTINCT factor_name) >= %s
    ORDER BY trade_date
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, [start_date, end_date, version, expected])
    return {str(row["trade_date"])[:10] for row in rows}


def derive_factor_backfill_window(
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    lookback_bars: int = 130,
    industry_system: str = "csrc",
    adjust_type: str = "hfq",
) -> dict[str, str | int | None]:
    bounds = load_market_date_bounds(adjust_type=adjust_type)
    window_start = start_date or bounds["start_date"]
    window_end = end_date or bounds["end_date"]
    if window_start is None or window_end is None:
        return {"start_date": None, "end_date": None, "date_count": 0}
    return derive_feature_window(
        start_date=str(window_start),
        end_date=str(window_end),
        lookback_bars=lookback_bars,
        adjust_type=adjust_type,
    )


def _build_factor_daily_for_task(
    trade_date: str,
    lookback_bars: int,
    industry_system: str,
) -> dict:
    started_at = time.perf_counter()
    count = build_and_store_factor_daily(
        trade_date=trade_date,
        lookback_bars=lookback_bars,
        industry_system=industry_system,
    )
    return {
        "trade_date": trade_date,
        "factor_rows": count,
        "elapsed_seconds": time.perf_counter() - started_at,
    }


def backfill_factor_daily_range(
    start_date: str,
    end_date: str,
    lookback_bars: int = 130,
    industry_system: str = "csrc",
    trading_days_only: bool = True,
    adjust_type: str = "hfq",
    workers: int = 1,
    skip_complete: bool = False,
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
    if skip_complete:
        complete_dates = load_complete_factor_dates(
            start_date=start_date,
            end_date=end_date,
        )
        trade_dates = [date for date in trade_dates if date not in complete_dates]

    total_dates = len(trade_dates)
    if workers < 1:
        raise ValueError("workers must be >= 1")
    if total_dates == 0:
        return pd.DataFrame(columns=["trade_date", "factor_rows"])
    if workers > 1:
        with ProcessPoolExecutor(
            max_workers=workers,
            max_tasks_per_child=1,
        ) as executor:
            futures = {
                executor.submit(
                    _build_factor_daily_for_task,
                    trade_date,
                    lookback_bars,
                    industry_system,
                ): trade_date
                for trade_date in trade_dates
            }
            for index, future in enumerate(as_completed(futures), start=1):
                item = future.result()
                item["index"] = index
                item["total"] = total_dates
                if progress is not None:
                    progress({"event": "done", **item})
                rows.append(
                    {
                        "trade_date": item["trade_date"],
                        "factor_rows": item["factor_rows"],
                    }
                )
        if not rows:
            return pd.DataFrame(columns=["trade_date", "factor_rows"])
        return pd.DataFrame(rows).sort_values("trade_date").reset_index(drop=True)

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
    if not rows:
        return pd.DataFrame(columns=["trade_date", "factor_rows"])
    return pd.DataFrame(rows)
