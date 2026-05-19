from collections.abc import Callable
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, as_completed, wait
import time

import pandas as pd

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all
from stock_research.factor_backfill import (
    build_trade_date_range,
    load_trade_dates_for_backfill,
)
from stock_research.research_windows import load_market_date_bounds
from stock_research.technical_feature_store import (
    TECHNICAL_FEATURE_CALC_VERSION,
    TECHNICAL_FEATURE_SOURCE,
    build_and_store_stock_technical_features_daily,
)


def load_complete_technical_feature_dates(
    start_date: str,
    end_date: str,
    adjust_type: str = "qfq",
    calc_version: str = TECHNICAL_FEATURE_CALC_VERSION,
    source_data_version: str | None = None,
    service: str = SETTINGS.research_service,
) -> set[str]:
    version = source_data_version or f"market_daily_bar:{adjust_type}"
    sql = """
    WITH expected_assets AS (
        SELECT DISTINCT trade_date, asset_id
        FROM market_daily_bar
        WHERE adjust_type = %s
          AND trade_date BETWEEN %s AND %s
    ),
    actual_assets AS (
        SELECT DISTINCT trade_date, asset_id
        FROM factor.stock_technical_features_daily
        WHERE adjust_type = %s
          AND source = %s
          AND source_data_version = %s
          AND calc_version = %s
          AND trade_date BETWEEN %s AND %s
    )
    SELECT DISTINCT expected_assets.trade_date
    FROM expected_assets
    WHERE NOT EXISTS (
        SELECT 1
        FROM expected_assets missing_expected
        WHERE missing_expected.trade_date = expected_assets.trade_date
          AND NOT EXISTS (
              SELECT 1
              FROM actual_assets
              WHERE actual_assets.trade_date = missing_expected.trade_date
                AND actual_assets.asset_id = missing_expected.asset_id
          )
    )
      AND NOT EXISTS (
          SELECT 1
          FROM actual_assets stale_actual
          WHERE stale_actual.trade_date = expected_assets.trade_date
            AND NOT EXISTS (
                SELECT 1
                FROM expected_assets
                WHERE expected_assets.trade_date = stale_actual.trade_date
                  AND expected_assets.asset_id = stale_actual.asset_id
            )
      )
    ORDER BY expected_assets.trade_date
    """
    with connect(service) as conn:
        rows = fetch_all(
            conn,
            sql,
            [
                adjust_type,
                start_date,
                end_date,
                adjust_type,
                TECHNICAL_FEATURE_SOURCE,
                version,
                calc_version,
                start_date,
                end_date,
            ],
        )
    return {str(row["trade_date"])[:10] for row in rows}


def derive_technical_feature_backfill_window(
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    lookback_bars: int = 260,
    adjust_type: str = "qfq",
) -> dict[str, str | int | None]:
    bounds = load_market_date_bounds(adjust_type=adjust_type)
    window_start = start_date or bounds["start_date"]
    window_end = end_date or bounds["end_date"]
    if window_start is None or window_end is None:
        return {"start_date": None, "end_date": None, "date_count": 0}
    if start_date is None and end_date is None:
        date_count = int(bounds.get("date_count") or 0)
    else:
        date_count = len(
            load_trade_dates_for_backfill(
                start_date=str(window_start),
                end_date=str(window_end),
                adjust_type=adjust_type,
            )
        )
    return {
        "start_date": str(window_start),
        "end_date": str(window_end),
        "date_count": date_count,
    }


def _build_technical_features_daily_for_task(
    trade_date: str,
    lookback_bars: int,
    adjust_type: str,
    source_data_version: str | None,
    build_strategy: str,
) -> dict:
    started_at = time.perf_counter()
    count = build_and_store_stock_technical_features_daily(
        trade_date=trade_date,
        lookback_bars=lookback_bars,
        adjust_type=adjust_type,
        source_data_version=source_data_version,
        build_strategy=build_strategy,
    )
    return {
        "trade_date": trade_date,
        "feature_rows": count,
        "elapsed_seconds": time.perf_counter() - started_at,
    }


def backfill_technical_features_daily_range(
    start_date: str,
    end_date: str,
    lookback_bars: int = 260,
    adjust_type: str = "qfq",
    source_data_version: str | None = None,
    trading_days_only: bool = True,
    workers: int = 1,
    skip_complete: bool = False,
    build_strategy: str = "latest_only",
    progress: Callable[[dict], None] | None = None,
    clock: Callable[[], float] = time.perf_counter,
    run_timeout_seconds: float | None = None,
) -> pd.DataFrame:
    batch_started_at: float | None = None
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
        complete_dates = load_complete_technical_feature_dates(
            start_date=start_date,
            end_date=end_date,
            adjust_type=adjust_type,
            source_data_version=source_data_version,
        )
        trade_dates = [trade_date for trade_date in trade_dates if trade_date not in complete_dates]

    total_dates = len(trade_dates)
    if workers < 1:
        raise ValueError("workers must be >= 1")
    if total_dates == 0:
        return _build_backfill_result_frame(
            rows=[],
            trade_dates=[],
            workers=workers,
            compute_seconds=0.0,
            timed_out=False,
        )

    if workers > 1:
        if run_timeout_seconds is None:
            with ProcessPoolExecutor(max_workers=workers) as executor:
                futures = {
                    executor.submit(
                        _build_technical_features_daily_for_task,
                        trade_date,
                        lookback_bars,
                        adjust_type,
                        source_data_version,
                        build_strategy,
                    ): {"trade_date": trade_date, "index": index}
                    for index, trade_date in enumerate(trade_dates, start=1)
                }
                for future in as_completed(futures):
                    metadata = futures[future]
                    item = future.result()
                    item["index"] = metadata["index"]
                    item["total"] = total_dates
                    if progress is not None:
                        progress({"event": "done", **item})
                    rows.append(
                        {
                            "trade_date": item["trade_date"],
                            "feature_rows": item["feature_rows"],
                        }
                    )
            return _build_backfill_result_frame(
                rows=rows,
                trade_dates=trade_dates,
                workers=workers,
                compute_seconds=(clock() - batch_started_at) if batch_started_at is not None else 0.0,
                timed_out=False,
            )

        batch_started_at = clock()
        deadline = batch_started_at + max(0.0, float(run_timeout_seconds))
        timed_out = False
        executor = ProcessPoolExecutor(max_workers=workers)
        futures = {
            executor.submit(
                _build_technical_features_daily_for_task,
                trade_date,
                lookback_bars,
                adjust_type,
                source_data_version,
                build_strategy,
            ): {"trade_date": trade_date, "index": index}
            for index, trade_date in enumerate(trade_dates, start=1)
        }
        pending = set(futures)
        try:
            while pending:
                remaining_seconds = deadline - clock()
                if remaining_seconds <= 0:
                    timed_out = True
                    break
                done, pending = wait(
                    pending,
                    timeout=remaining_seconds,
                    return_when=FIRST_COMPLETED,
                )
                if not done:
                    timed_out = True
                    break
                for future in done:
                    metadata = futures[future]
                    item = future.result()
                    item["index"] = metadata["index"]
                    item["total"] = total_dates
                    if progress is not None:
                        progress({"event": "done", **item})
                    rows.append(
                        {
                            "trade_date": item["trade_date"],
                            "feature_rows": item["feature_rows"],
                        }
                    )
        finally:
            executor.shutdown(wait=not timed_out, cancel_futures=timed_out)
        return _build_backfill_result_frame(
            rows=rows,
            trade_dates=trade_dates,
            workers=workers,
            compute_seconds=(clock() - batch_started_at) if batch_started_at is not None else 0.0,
            timed_out=timed_out,
        )

    timed_out = False
    total_compute_seconds = 0.0
    if run_timeout_seconds is not None:
        batch_started_at = clock()
    for index, trade_date in enumerate(trade_dates, start=1):
        if (
            run_timeout_seconds is not None
            and batch_started_at is not None
            and (clock() - batch_started_at) >= float(run_timeout_seconds)
        ):
            timed_out = True
            break
        if progress is not None:
            progress(
                {
                    "event": "start",
                    "trade_date": trade_date,
                    "index": index,
                    "total": total_dates,
                }
            )
        started_at = clock()
        count = build_and_store_stock_technical_features_daily(
            trade_date=trade_date,
            lookback_bars=lookback_bars,
            adjust_type=adjust_type,
            source_data_version=source_data_version,
            build_strategy=build_strategy,
        )
        elapsed_seconds = clock() - started_at
        total_compute_seconds += elapsed_seconds
        if progress is not None:
            progress(
                {
                    "event": "done",
                    "trade_date": trade_date,
                    "index": index,
                    "total": total_dates,
                    "feature_rows": count,
                    "elapsed_seconds": elapsed_seconds,
                }
            )
        rows.append({"trade_date": trade_date, "feature_rows": count})
    return _build_backfill_result_frame(
        rows=rows,
        trade_dates=trade_dates,
        workers=workers,
        compute_seconds=(
            (clock() - batch_started_at)
            if (run_timeout_seconds is not None and batch_started_at is not None)
            else total_compute_seconds
        ),
        timed_out=timed_out,
    )


def run_technical_feature_backfill_benchmark(
    *,
    start_date: str,
    end_date: str,
    lookback_bars: int = 260,
    adjust_type: str = "qfq",
    workers: int = 1,
    strategy: str = "current",
    bench_tag: str | None = None,
    source_data_version: str | None = None,
) -> dict[str, str | int | float]:
    resolved_strategy = str(strategy)
    if resolved_strategy not in {"current", "parallel_dates"}:
        raise ValueError(f"unsupported benchmark strategy: {resolved_strategy}")
    resolved_workers = 1 if resolved_strategy == "current" else max(1, int(workers))
    resolved_source_data_version = source_data_version or (
        f"market_daily_bar:{adjust_type}@bench_{bench_tag or 'default'}"
    )

    started_at = time.perf_counter()
    result = backfill_technical_features_daily_range(
        start_date=start_date,
        end_date=end_date,
        lookback_bars=lookback_bars,
        adjust_type=adjust_type,
        source_data_version=resolved_source_data_version,
        workers=resolved_workers,
        skip_complete=False,
        build_strategy="legacy",
        trading_days_only=True,
        progress=None,
    )
    elapsed_seconds = time.perf_counter() - started_at
    date_count = int(len(result))
    row_count = int(result["feature_rows"].sum()) if not result.empty else 0
    rows_per_second = 0.0 if elapsed_seconds <= 0 else row_count / elapsed_seconds
    dates_per_second = 0.0 if elapsed_seconds <= 0 else date_count / elapsed_seconds
    return {
        "strategy": resolved_strategy,
        "workers": resolved_workers,
        "bench_tag": bench_tag or "default",
        "source_data_version": resolved_source_data_version,
        "dates": date_count,
        "rows": row_count,
        "elapsed_seconds": round(elapsed_seconds, 4),
        "rows_per_second": round(rows_per_second, 4),
        "dates_per_second": round(dates_per_second, 4),
    }


def _build_backfill_result_frame(
    *,
    rows: list[dict[str, int | str]],
    trade_dates: list[str],
    workers: int,
    compute_seconds: float,
    timed_out: bool,
) -> pd.DataFrame:
    if rows:
        frame = pd.DataFrame(rows).sort_values("trade_date").reset_index(drop=True)
    else:
        frame = pd.DataFrame(columns=["trade_date", "feature_rows"])
    rows_written = int(frame["feature_rows"].sum()) if not frame.empty else 0
    completed_days = int(len(frame))
    hours = compute_seconds / 3600.0 if compute_seconds > 0 else 0.0
    frame.attrs.update(
        {
            "timed_out": bool(timed_out),
            "batch_start_date": trade_dates[0] if trade_dates else None,
            "batch_end_date": trade_dates[-1] if trade_dates else None,
            "batch_size_days": int(len(trade_dates)),
            "completed_days": completed_days,
            "worker_count": int(workers),
            "compute_seconds": float(compute_seconds),
            "rows_written": rows_written,
            "days_per_hour": (completed_days / hours) if hours > 0 else 0.0,
            "rows_per_hour": (rows_written / hours) if hours > 0 else 0.0,
        }
    )
    return frame
