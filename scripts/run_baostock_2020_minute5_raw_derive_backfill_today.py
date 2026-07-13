from __future__ import annotations

import datetime as dt
import os
import sys

from stock_research.baostock_minute_backfill_watchdog import (
    allocate_daily_backfill_quota,
    calculate_baostock_minute_budget,
    finalize_daily_backfill_quota,
    load_active_baostock_asset_count,
)
from stock_research.cli_progress import ProgressRenderer
from stock_research.minute_backfill import (
    load_backfill_status_rows,
    run_baostock_minute_backfill,
    summarize_backfill_status,
)


def _int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    return int(value) if value else default


def main() -> int:
    start = dt.date.fromisoformat(os.getenv("BACKFILL_START_DATE", "2020-01-01"))
    end = dt.date.fromisoformat(os.getenv("BACKFILL_END_DATE", "2020-12-31"))
    quota_day = dt.date.fromisoformat(os.getenv("QUOTA_DAY", dt.date.today().isoformat()))
    requested_requests = _int_env("REQUESTED_REQUESTS", 3000)
    ledger_path = os.getenv("REQUEST_LEDGER_PATH", "logs/baostock_minute_request_quota.json")

    budget = calculate_baostock_minute_budget(
        active_asset_count=load_active_baostock_asset_count(),
        today_adjust_types=["raw"],
        daily_request_limit=50_000,
        safety_multiplier=1.1,
    )
    allocation = allocate_daily_backfill_quota(
        ledger_path=ledger_path,
        day=quota_day,
        backfill_request_budget=budget.backfill_request_budget,
        requested_requests=requested_requests,
    )
    print(f"baostock_2020_minute5_backfill|budget|{budget}", flush=True)
    print(f"baostock_2020_minute5_backfill|allocation|{allocation}", flush=True)
    if allocation.allocated_requests <= 0:
        print("baostock_2020_minute5_backfill|status|no_quota", flush=True)
        return 2

    result: dict[str, int] = {"attempted": 0, "success": 0, "failed": 0, "rows": 0}
    try:
        before_raw = summarize_backfill_status(
            load_backfill_status_rows(start_date=start, end_date=end, freq="5min", adjust_types=["raw"])
        )
        before_qfq = summarize_backfill_status(
            load_backfill_status_rows(start_date=start, end_date=end, freq="5min", adjust_types=["qfq"])
        )
        print(f"baostock_2020_minute5_backfill|before_raw|{before_raw}", flush=True)
        print(f"baostock_2020_minute5_backfill|before_qfq|{before_qfq}", flush=True)
        result = run_baostock_minute_backfill(
            start_date=start.isoformat(),
            end_date=end.isoformat(),
            freq="5min",
            adjust_types=["raw"],
            batch_by="month",
            max_jobs=allocation.allocated_requests,
            retry_failed=True,
            sleep_seconds=0.75,
            workers=1,
            progress=ProgressRenderer("minute5_2020_raw_backfill_today"),
            progress_interval=50,
            progress_heartbeat_seconds=300,
            derive_qfq_from_raw=True,
        )
    finally:
        finalized = finalize_daily_backfill_quota(
            ledger_path=ledger_path,
            day=quota_day,
            allocated_requests=allocation.allocated_requests,
            attempted_requests=int(result.get("attempted", 0) or 0),
        )
        print(f"baostock_2020_minute5_backfill|finalized_quota|{finalized}", flush=True)

    after_raw = summarize_backfill_status(
        load_backfill_status_rows(start_date=start, end_date=end, freq="5min", adjust_types=["raw"])
    )
    after_qfq = summarize_backfill_status(
        load_backfill_status_rows(start_date=start, end_date=end, freq="5min", adjust_types=["qfq"])
    )
    print(f"baostock_2020_minute5_backfill|run_result|{result}", flush=True)
    print(f"baostock_2020_minute5_backfill|after_raw|{after_raw}", flush=True)
    print(f"baostock_2020_minute5_backfill|after_qfq|{after_qfq}", flush=True)
    return 0 if int(result.get("failed", 0) or 0) == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
