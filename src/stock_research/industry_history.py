from __future__ import annotations

import calendar
from datetime import date, timedelta
from time import perf_counter
from typing import Callable

from stock_research.core_data import build_industry_daily_bars_for_service
from stock_research.loaders.baostock_ingestion import sync_industry_memberships


def _elapsed_seconds(value: float) -> float:
    return round(value, 3)


def build_industry_history_dates(
    start_date: str,
    end_date: str,
    max_dates: int | None = None,
    frequency: str = "daily",
) -> list[str]:
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    if end < start:
        raise ValueError("end_date must be greater than or equal to start_date")

    if frequency == "daily":
        rows = []
        current = start
        while current <= end:
            rows.append(current.isoformat())
            if max_dates is not None and len(rows) >= max_dates:
                break
            current += timedelta(days=1)
        return rows

    if frequency not in {"monthly", "quarterly"}:
        raise ValueError("frequency must be daily, monthly, or quarterly")

    rows = []
    year = start.year
    month = start.month
    while True:
        month_end = date(year, month, calendar.monthrange(year, month)[1])
        if frequency == "quarterly" and month not in {3, 6, 9, 12}:
            pass
        elif month_end >= start:
            rows.append(min(month_end, end).isoformat())
        if month_end >= end:
            break
        if max_dates is not None and len(rows) >= max_dates:
            break
        month += 1
        if month > 12:
            month = 1
            year += 1
    if frequency == "quarterly" and rows and rows[-1] != end.isoformat():
        rows.append(end.isoformat())
    if max_dates is not None:
        rows = rows[:max_dates]
    return rows


def benchmark_industry_day(
    trade_date: str,
    industry_system: str = "csrc",
    adjust_type: str = "hfq",
    sync_func: Callable[[str], int] = sync_industry_memberships,
    build_func: Callable[..., None] = build_industry_daily_bars_for_service,
    timer: Callable[[], float] = perf_counter,
    use_cache: bool = True,
) -> dict:
    started = timer()
    if sync_func is sync_industry_memberships:
        membership_rows = int(sync_func(trade_date, use_cache=use_cache))
    else:
        membership_rows = int(sync_func(trade_date))
    after_sync = timer()
    before_build = timer()
    build_func(
        start_date=trade_date,
        end_date=trade_date,
        industry_system=industry_system,
        adjust_type=adjust_type,
    )
    after_build = timer()
    return {
        "trade_date": trade_date,
        "membership_rows": membership_rows,
        "sync_seconds": _elapsed_seconds(after_sync - started),
        "build_seconds": _elapsed_seconds(after_build - before_build),
        "total_seconds": _elapsed_seconds(after_build - started),
    }


def run_industry_history_range(
    start_date: str,
    end_date: str,
    max_dates: int,
    frequency: str = "daily",
    industry_system: str = "csrc",
    adjust_type: str = "hfq",
    use_cache: bool = True,
    benchmark_func: Callable[..., dict] = benchmark_industry_day,
    progress: Callable[[dict], None] | None = None,
    timer: Callable[[], float] = perf_counter,
) -> dict:
    dates = build_industry_history_dates(
        start_date,
        end_date,
        max_dates=max_dates,
        frequency=frequency,
    )
    started = timer()
    membership_rows = 0
    for index, trade_date in enumerate(dates, start=1):
        try:
            result = benchmark_func(
                trade_date=trade_date,
                industry_system=industry_system,
                adjust_type=adjust_type,
                use_cache=use_cache,
            )
        except TypeError:
            result = benchmark_func(
                trade_date=trade_date,
                industry_system=industry_system,
                adjust_type=adjust_type,
            )
        membership_rows += int(result["membership_rows"])
        if progress is not None:
            progress(
                {
                    "event": "date_done",
                    "trade_date": trade_date,
                    "index": index,
                    "total": len(dates),
                    "membership_rows": int(result["membership_rows"]),
                    "seconds": result["total_seconds"],
                }
            )
    return {
        "dates": len(dates),
        "membership_rows": membership_rows,
        "seconds": _elapsed_seconds(timer() - started),
        "start_date": start_date,
        "end_date": dates[-1] if dates else start_date,
    }
