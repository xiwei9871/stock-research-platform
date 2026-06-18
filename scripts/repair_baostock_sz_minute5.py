from __future__ import annotations

import argparse
import concurrent.futures
import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from stock_research.config import SETTINGS
from stock_research.daily_close_pipeline import (
    PipelineConfig,
    baostock_login_or_raise,
    fetch_baostock_minute5_worker,
    inspect_minute5_quality_from_db,
    load_active_ts_codes,
    upsert_job,
    upsert_minute5_bars,
    upsert_quality,
)
from stock_research.db import connect, fetch_all


def latest_missing_for_exchange(trade_date: date, exchange: str) -> list[str]:
    sql = """
    SELECT missing_symbols
    FROM ops.daily_pipeline_quality
    WHERE trade_date = %s
      AND dataset_name = 'minute5_bar'
    ORDER BY updated_at DESC
    LIMIT 1
    """
    with connect(SETTINGS.research_service) as conn:
        rows = fetch_all(conn, sql, [trade_date])
    missing = list(rows[0]["missing_symbols"]) if rows else []
    return [
        str(ts_code)
        for ts_code in missing
        if str(ts_code).endswith(f".{exchange.upper()}")
    ]


def repair_baostock_exchange_minute5(
    trade_date: date,
    *,
    exchange: str,
    workers: int,
    timeout_seconds: int,
) -> dict[str, int | str]:
    workers = max(1, min(workers, 2))
    exchange = exchange.upper()
    label = exchange.lower()
    config = PipelineConfig.from_env()
    service = SETTINGS.research_service
    repair_codes = latest_missing_for_exchange(trade_date, exchange)
    print(
        f"baostock_{label}_repair|trade_date|{trade_date}|symbols|{len(repair_codes)}|workers|{workers}",
        flush=True,
    )
    if not repair_codes:
        return {"status": "skipped", "rows": 0, "failures": 0}

    lookback_start = trade_date - timedelta(days=max(config.minute5_lookback_days - 1, 0))
    rows_by_symbol: dict[str, list[dict]] = {}
    failures: dict[str, str] = {}
    attempts: dict[str, int] = {}
    started = datetime.now(ZoneInfo(config.timezone))
    deadline = time.monotonic() + timeout_seconds

    executor = concurrent.futures.ProcessPoolExecutor(
        max_workers=workers,
        initializer=baostock_login_or_raise,
    )
    try:
        future_to_code = {
            executor.submit(
                fetch_baostock_minute5_worker,
                ts_code,
                lookback_start,
                trade_date,
                config.request_timeout_seconds,
                config.max_retries,
            ): ts_code
            for ts_code in repair_codes
        }
        pending = set(future_to_code)
        completed = 0
        while pending:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                for future in pending:
                    failures[future_to_code[future]] = f"baostock {label} repair timeout"
                if hasattr(executor, "terminate_workers"):
                    executor.terminate_workers()
                else:
                    executor.shutdown(wait=False, cancel_futures=True)
                break
            done, pending = concurrent.futures.wait(
                pending,
                timeout=min(10.0, remaining),
                return_when=concurrent.futures.FIRST_COMPLETED,
            )
            for future in done:
                ts_code = future_to_code[future]
                try:
                    ts_code, fetched_rows, attempt_count, error = future.result()
                except Exception as exc:  # noqa: BLE001 - per-symbol repair failure.
                    fetched_rows, attempt_count = [], 0
                    error = f"{type(exc).__name__}: {exc}"
                attempts[ts_code] = attempt_count
                completed += 1
                if error:
                    failures[ts_code] = error
                else:
                    rows_by_symbol[ts_code] = fetched_rows
                if completed % 25 == 0 or completed == len(repair_codes):
                    print(
                        f"baostock_{label}_repair|progress|"
                        f"{completed}/{len(repair_codes)}|success_symbols|{len(rows_by_symbol)}|"
                        f"failures|{len(failures)}",
                        flush=True,
                    )
    finally:
        executor.shutdown(wait=False, cancel_futures=True)

    all_rows = [row for symbol_rows in rows_by_symbol.values() for row in symbol_rows]
    rows_upserted = upsert_minute5_bars(service, all_rows)
    expected = load_active_ts_codes(service, trade_date)
    quality = inspect_minute5_quality_from_db(service, expected, trade_date)
    upsert_quality(service=service, trade_date=trade_date, dataset_name="minute5_bar", **quality)
    coverage = quality["actual_count"] / quality["expected_count"] if quality["expected_count"] else 1.0
    status = (
        "success"
        if not quality["missing_symbols"] and not quality["abnormal_symbols"]
        else "partial_success"
        if rows_upserted
        else "failed"
    )
    finished = datetime.now(ZoneInfo(config.timezone))
    upsert_job(
        service=service,
        trade_date=trade_date,
        job_name="minute5_bar",
        stage="minute5",
        source=f"baostock_{label}_repair",
        status=status,
        started_at=started,
        finished_at=finished,
        attempt_count=max(attempts.values(), default=0),
        rows_inserted=rows_upserted,
        rows_failed=len(failures),
        missing_symbols_count=len(quality["missing_symbols"]),
        error_summary="; ".join(f"{code}:{err}" for code, err in list(failures.items())[:5]) or None,
    )
    print(
        f"baostock_{label}_repair|done|"
        f"status|{status}|rows|{rows_upserted}|failures|{len(failures)}|"
        f"coverage|{coverage:.4f}|missing|{len(quality['missing_symbols'])}|"
        f"abnormal|{len(quality['abnormal_symbols'])}",
        flush=True,
    )
    if failures:
        print(f"baostock_{label}_repair|failure_samples|{list(failures.items())[:10]}", flush=True)
    return {"status": status, "rows": rows_upserted, "failures": len(failures)}


def repair_baostock_sz_minute5(
    trade_date: date,
    *,
    workers: int,
    timeout_seconds: int,
) -> dict[str, int | str]:
    return repair_baostock_exchange_minute5(
        trade_date,
        exchange="SZ",
        workers=workers,
        timeout_seconds=timeout_seconds,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trade-date", required=True)
    parser.add_argument("--exchange", choices=["SH", "SZ"], default="SZ")
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--timeout-seconds", type=int, default=1800)
    args = parser.parse_args()
    repair_baostock_exchange_minute5(
        date.fromisoformat(args.trade_date),
        exchange=args.exchange,
        workers=args.workers,
        timeout_seconds=args.timeout_seconds,
    )


if __name__ == "__main__":
    main()
