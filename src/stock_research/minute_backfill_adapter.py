from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
import fcntl
import multiprocessing as mp
from pathlib import Path
import queue
from typing import Any

from stock_research.backfill_watchdog import BackfillSummary, BackfillWatchdogStatus
from stock_research.minute_backfill import (
    load_backfill_status_rows,
    parse_date,
    reset_stale_running_jobs,
    run_baostock_minute_backfill,
    summarize_backfill_status,
)


TERMINAL_COMPLETED_STATUSES = {"success", "skipped"}
DEFAULT_MINUTE_BACKFILL_WATCHDOG_LOCK = Path("/tmp/stock-research-minute-backfill-watchdog.lock")


@dataclass(frozen=True)
class MinuteBackfillAdapter:
    start_date: str | None = None
    end_date: str | None = None
    freq: str | None = None
    adjust_types: list[str] | None = None
    batch_by: str = "month"
    retry_failed: bool = True
    sleep_seconds: float = 0.0

    task_name: str = "minute_backfill"
    dataset: str = "market.stock_minute_bar"

    def load_scope(self) -> dict[str, str]:
        adjust_types = ",".join(self.adjust_types or [])
        return {
            "task": self.task_name,
            "task_name": self.task_name,
            "dataset": self.dataset,
            "run_id": (
                f"minute-backfill:{self.freq or 'all'}:{adjust_types or 'all'}:"
                f"{self.start_date or 'begin'}:{self.end_date or 'latest'}"
            ),
            "window": f"{self.start_date or 'begin'}..{self.end_date or 'latest'}",
        }

    def load_status_rows(self) -> list[dict[str, Any]]:
        return load_backfill_status_rows(
            start_date=parse_date(self.start_date) if self.start_date else None,
            end_date=parse_date(self.end_date) if self.end_date else None,
            freq=self.freq,
            adjust_types=self.adjust_types,
        )

    def summarize_status(self, rows: list[dict[str, Any]]) -> BackfillSummary:
        summary = summarize_backfill_status(rows)
        return BackfillSummary(
            total_tasks=int(summary["total_jobs"]),
            pending_tasks=int(summary["pending_jobs"]),
            running_tasks=int(summary["running_jobs"]),
            success_tasks=int(summary["success_jobs"]),
            failed_tasks=int(summary["failed_jobs"]),
            skipped_tasks=int(summary["skipped_jobs"]),
            total_rows_written=int(summary["total_market_rows"]),
        )

    def compute_frontier(self, rows: list[dict[str, Any]]) -> dict[str, str | None]:
        period_statuses = _group_period_statuses(rows)
        completed_through: str | None = None
        currently_working_on: str | None = None

        for period_start, period_end, statuses in period_statuses:
            if statuses and all(status in TERMINAL_COMPLETED_STATUSES for status in statuses):
                completed_through = f"{period_end.year:04d}-{period_end.month:02d}"
                continue
            currently_working_on = f"{period_start.year:04d}-{period_start.month:02d}"
            break

        return {
            "completed_through": completed_through,
            "currently_working_on": currently_working_on,
        }

    def reset_stale_tasks(self, stale_after_minutes: int) -> int:
        return reset_stale_running_jobs(stale_after_minutes=stale_after_minutes)

    def run_once(
        self,
        *,
        scope: dict[str, str],
        max_jobs: int,
        workers: int,
        run_timeout_seconds: int,
    ) -> dict[str, Any]:
        del scope
        return _run_backfill_once_with_timeout(
            start_date=self.start_date,
            end_date=self.end_date,
            freq=self.freq,
            adjust_types=self.adjust_types,
            batch_by=self.batch_by,
            max_jobs=max_jobs,
            retry_failed=self.retry_failed,
            sleep_seconds=self.sleep_seconds,
            workers=workers,
            run_timeout_seconds=run_timeout_seconds,
            reset_stale_before_run=False,
        )

    def format_extra_status_lines(
        self,
        *,
        rows: list[dict[str, Any]],
        summary: BackfillSummary,
        scope: dict[str, str],
        run_result: dict[str, Any],
        status: BackfillWatchdogStatus,
    ) -> list[str]:
        del rows, summary, scope, status
        return [
            f"run_status={run_result.get('status', '')}",
            f"run_attempted={int(run_result.get('attempted', 0) or 0)}",
            f"run_success={int(run_result.get('success', 0) or 0)}",
            f"run_failed={int(run_result.get('failed', 0) or 0)}",
            f"run_rows={int(run_result.get('rows', 0) or 0)}",
        ]


def _run_backfill_once_with_timeout(
    *,
    start_date: str | None,
    end_date: str | None,
    freq: str | None,
    adjust_types: list[str] | None,
    batch_by: str,
    max_jobs: int,
    retry_failed: bool,
    sleep_seconds: float,
    workers: int,
    run_timeout_seconds: int,
    reset_stale_before_run: bool = True,
    lock_path: str | Path = DEFAULT_MINUTE_BACKFILL_WATCHDOG_LOCK,
) -> dict[str, Any]:
    lock_handle = _try_acquire_watchdog_lock(lock_path)
    if lock_handle is None:
        return {
            "attempted": 0,
            "success": 0,
            "failed": 0,
            "rows": 0,
            "status": "already_running",
            "timed_out": False,
            "lock_busy": True,
        }
    context = _timeout_process_context()
    try:
        result_queue: mp.queues.Queue[dict[str, Any]] = context.Queue(maxsize=1)
        process = context.Process(
            target=_run_backfill_once_target,
            args=(
                result_queue,
                {
                    "start_date": start_date,
                    "end_date": end_date,
                    "freq": freq,
                    "adjust_types": adjust_types,
                    "batch_by": batch_by,
                    "max_jobs": max_jobs,
                    "retry_failed": retry_failed,
                    "sleep_seconds": sleep_seconds,
                    "workers": workers,
                    "reset_stale_before_run": reset_stale_before_run,
                },
            ),
        )
        process.start()
        process.join(timeout=run_timeout_seconds)
        if process.is_alive():
            process.terminate()
            process.join(timeout=1)
            if process.is_alive() and hasattr(process, "kill"):
                process.kill()
                process.join(timeout=1)
            result_queue.close()
            return {
                "attempted": 0,
                "success": 0,
                "failed": 0,
                "rows": 0,
                "status": "timed_out",
                "timed_out": True,
            }
        exitcode = process.exitcode
        try:
            result = result_queue.get_nowait()
        except queue.Empty:
            return {
                "attempted": 0,
                "success": 0,
                "failed": 1,
                "rows": 0,
                "status": "failed",
                "timed_out": False,
            }
        finally:
            result_queue.close()
            result_queue.join_thread()
        if exitcode not in (0, None):
            return {
                "attempted": 0,
                "success": 0,
                "failed": 1,
                "rows": 0,
                "status": "failed",
                "timed_out": False,
            }
        return {
            **result,
            "status": "completed",
            "timed_out": False,
        }
    finally:
        _release_watchdog_lock(lock_handle)


def _run_backfill_once_target(result_queue: Any, kwargs: dict[str, Any]) -> None:
    result_queue.put(run_baostock_minute_backfill(**kwargs))


def _timeout_process_context() -> Any:
    for method in ("fork", "spawn"):
        try:
            return mp.get_context(method)
        except ValueError:
            continue
    return mp.get_context()


def _try_acquire_watchdog_lock(lock_path: str | Path) -> Any | None:
    path = Path(lock_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        return None
    return handle


def _release_watchdog_lock(handle: Any | None) -> None:
    if handle is None:
        return
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    finally:
        handle.close()


def _reconcile_timeout_run_result(
    *,
    run_result: dict[str, Any],
    pre_summary: dict[str, Any],
    post_summary: dict[str, Any],
) -> dict[str, Any]:
    if not run_result.get("timed_out"):
        return run_result

    success = _non_negative_delta(post_summary, pre_summary, "success_jobs")
    failed = _non_negative_delta(post_summary, pre_summary, "failed_jobs")
    skipped = _non_negative_delta(post_summary, pre_summary, "skipped_jobs")
    rows = _non_negative_delta(post_summary, pre_summary, "total_market_rows")
    attempted = max(int(run_result.get("attempted", 0) or 0), success + failed + skipped)

    return {
        **run_result,
        "attempted": attempted,
        "success": max(int(run_result.get("success", 0) or 0), success),
        "failed": max(int(run_result.get("failed", 0) or 0), failed),
        "rows": max(int(run_result.get("rows", 0) or 0), rows),
    }


def _group_period_statuses(
    rows: list[dict[str, Any]],
) -> list[tuple[dt.date, dt.date, list[str]]]:
    grouped: dict[tuple[dt.date, dt.date], list[str]] = {}
    for row in rows:
        start_date = _as_date(row.get("start_date"))
        end_date = _as_date(row.get("end_date"))
        grouped.setdefault((start_date, end_date), []).append(str(row.get("status")))
    return [
        (start_date, end_date, grouped[(start_date, end_date)])
        for start_date, end_date in sorted(grouped)
    ]


def _non_negative_delta(
    current: dict[str, Any],
    previous: dict[str, Any],
    key: str,
) -> int:
    return max(0, int(current.get(key, 0) or 0) - int(previous.get(key, 0) or 0))


def _as_date(value: Any) -> dt.date:
    if isinstance(value, dt.date):
        return value
    if isinstance(value, str):
        return dt.date.fromisoformat(value)
    raise TypeError(f"expected ISO date string or date, got {type(value)!r}")
