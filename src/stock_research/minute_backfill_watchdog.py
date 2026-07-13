from __future__ import annotations

import datetime as dt
from dataclasses import asdict
from pathlib import Path
from typing import Any

from stock_research.baostock_minute_backfill_watchdog import (
    DEFAULT_BAOSTOCK_DAILY_REQUEST_LIMIT,
    DEFAULT_BAOSTOCK_REQUEST_LEDGER_PATH,
    DEFAULT_BAOSTOCK_SAFETY_MULTIPLIER,
    allocate_daily_backfill_quota,
    calculate_baostock_minute_budget,
    finalize_daily_backfill_quota,
    load_active_baostock_asset_count,
    load_baostock_minute_backfill_progress,
)
from stock_research.backfill_watchdog import (
    BackfillSummary,
    format_watchdog_message,
    run_watchdog_once,
    should_send_watchdog_message,
)
from stock_research.feishu_notify import send_openclaw_feishu_message
from stock_research.minute_backfill import summarize_backfill_status
from stock_research.minute_backfill_adapter import MinuteBackfillAdapter, _reconcile_timeout_run_result


WATCHDOG_ACTION_RESTARTED = "restarted"
WATCHDOG_ACTION_STALLED = "stalled_needs_manual_attention"


def run_minute_backfill_watchdog(
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    freq: str | None = None,
    adjust_types: list[str] | None = None,
    batch_by: str = "month",
    max_jobs: int = 1200,
    retry_failed: bool = True,
    sleep_seconds: float = 0.0,
    workers: int = 8,
    stale_after_minutes: int = 20,
    run_timeout_seconds: int = 1800,
    report_target: str,
    report_account: str = "jarvis",
    openclaw_bin: str = "openclaw",
    report_dry_run: bool = False,
    enable_baostock_request_budget: bool = False,
    baostock_daily_request_limit: int = DEFAULT_BAOSTOCK_DAILY_REQUEST_LIMIT,
    baostock_safety_multiplier: float = DEFAULT_BAOSTOCK_SAFETY_MULTIPLIER,
    max_daily_backfill_requests: int | None = None,
    today_adjust_types: list[str] | None = None,
    request_ledger_path: str | Path = DEFAULT_BAOSTOCK_REQUEST_LEDGER_PATH,
    quota_day: dt.date | None = None,
) -> dict[str, Any]:
    requested_adjust_types = adjust_types
    effective_adjust_types = adjust_types
    if enable_baostock_request_budget:
        effective_adjust_types = ["raw"]
    derive_qfq_from_raw = bool(
        enable_baostock_request_budget
        and requested_adjust_types is not None
        and "qfq" in requested_adjust_types
    )
    adapter = MinuteBackfillAdapter(
        start_date=start_date,
        end_date=end_date,
        freq=freq,
        adjust_types=effective_adjust_types,
        batch_by=batch_by,
        retry_failed=retry_failed,
        sleep_seconds=sleep_seconds,
        derive_qfq_from_raw=derive_qfq_from_raw,
    )
    effective_max_jobs = max_jobs
    effective_workers = workers
    budget_payload: dict[str, Any] | None = None
    pre_daily_progress: dict[str, Any] | None = None
    post_daily_progress: dict[str, Any] | None = None
    allocation = None
    if enable_baostock_request_budget:
        effective_workers = 1
        budget = calculate_baostock_minute_budget(
            active_asset_count=load_active_baostock_asset_count(),
            today_adjust_types=today_adjust_types or adjust_types or ["raw", "qfq"],
            daily_request_limit=baostock_daily_request_limit,
            safety_multiplier=baostock_safety_multiplier,
            max_backfill_requests=max_daily_backfill_requests,
        )
        allocation_day = quota_day or dt.date.today()
        allocation = allocate_daily_backfill_quota(
            ledger_path=request_ledger_path,
            day=allocation_day,
            backfill_request_budget=budget.backfill_request_budget,
            requested_requests=max_jobs,
        )
        effective_max_jobs = allocation.allocated_requests
        budget_payload = {
            **asdict(budget),
            "quota_day": allocation_day.isoformat(),
            "allocated_requests": allocation.allocated_requests,
            "consumed_requests": allocation.consumed_requests,
            "active_reserved_requests": allocation.active_reserved_requests,
            "request_ledger_path": str(request_ledger_path),
            "requested_adjust_types": list(requested_adjust_types or []),
            "baostock_fetch_adjust_types": list(effective_adjust_types or []),
        }
        if start_date is not None and end_date is not None and freq is not None:
            pre_daily_progress = load_baostock_minute_backfill_progress(
                start_date=start_date,
                end_date=end_date,
                freq=freq,
                adjust_types=effective_adjust_types,
            )

    try:
        result = run_watchdog_once(
            adapter=adapter,
            stale_after_minutes=stale_after_minutes,
            run_timeout_seconds=run_timeout_seconds,
            max_jobs=effective_max_jobs,
            workers=effective_workers,
            send_message=None,
        )
    except Exception:
        if allocation is not None:
            finalize_daily_backfill_quota(
                ledger_path=request_ledger_path,
                day=allocation.day,
                allocated_requests=allocation.allocated_requests,
                attempted_requests=0,
            )
        raise

    run_result = _reconcile_timeout_run_result(
        run_result=result["run_result"],
        pre_summary=_legacy_summary_from_rows(result["pre_rows"], result["pre_summary"]),
        post_summary=_legacy_summary_from_rows(result["post_rows"], result["post_summary"]),
    )
    pre_summary = _legacy_summary_from_rows(result["pre_rows"], result["pre_summary"])
    post_summary = _legacy_summary_from_rows(result["post_rows"], result["post_summary"])
    if run_result == result["run_result"]:
        message = result["message"]
    else:
        extra_lines = adapter.format_extra_status_lines(
            rows=result["post_rows"],
            summary=result["post_summary"],
            scope=result["scope"],
            run_result=run_result,
            status=result["status"],
        )
        message = format_watchdog_message(
            task_name=adapter.task_name,
            dataset=adapter.dataset,
            run_id=result["scope"].get("run_id", ""),
            window=result["scope"].get("window", ""),
            pre_summary=result["pre_summary"],
            post_summary=result["post_summary"],
            run_result=run_result,
            status=result["status"],
            extra_lines=extra_lines,
        )
    if allocation is not None and budget_payload is not None:
        finalized = finalize_daily_backfill_quota(
            ledger_path=request_ledger_path,
            day=allocation.day,
            allocated_requests=allocation.allocated_requests,
            attempted_requests=int(run_result.get("attempted", 0) or 0),
        )
        budget_payload.update(
            {
                "consumed_requests": finalized.consumed_requests,
                "active_reserved_requests": finalized.active_reserved_requests,
            }
        )
        if start_date is not None and end_date is not None and freq is not None:
            post_daily_progress = load_baostock_minute_backfill_progress(
                start_date=start_date,
                end_date=end_date,
                freq=freq,
                adjust_types=effective_adjust_types,
            )
            post_daily_progress = _with_progress_delta(
                pre_daily_progress=pre_daily_progress,
                post_daily_progress=post_daily_progress,
            )
            message = _append_daily_progress_message(message, post_daily_progress)
    if should_send_watchdog_message(result["status"]):
        send_openclaw_feishu_message(
            message=message,
            target=report_target,
            account=report_account,
            openclaw_bin=openclaw_bin,
            dry_run=report_dry_run,
        )
    legacy_status = _legacy_status_dict(
        post_rows=result["post_rows"],
        post_summary=post_summary,
        status=result["status"],
    )
    return {
        "pre_rows": result["pre_rows"],
        "post_rows": result["post_rows"],
        "pre_summary": pre_summary,
        "post_summary": post_summary,
        "status": legacy_status,
        "frontier": dict(result["frontier"]),
        "stale_jobs_reset": int(result["stale_tasks_reset"]),
        "run_result": run_result,
        "timed_out": bool(run_result.get("timed_out")),
        "message": message,
        **({"baostock_request_budget": budget_payload} if budget_payload is not None else {}),
        **({"baostock_backfill_progress": post_daily_progress} if post_daily_progress is not None else {}),
    }


def _with_progress_delta(
    *,
    pre_daily_progress: dict[str, Any] | None,
    post_daily_progress: dict[str, Any],
) -> dict[str, Any]:
    progress = dict(post_daily_progress)
    if (
        pre_daily_progress is not None
        and pre_daily_progress.get("current_trade_date") == post_daily_progress.get("current_trade_date")
    ):
        progress["run_delta_current_success_jobs"] = (
            int(post_daily_progress.get("current_success_jobs", 0) or 0)
            - int(pre_daily_progress.get("current_success_jobs", 0) or 0)
        )
    else:
        progress["run_delta_current_success_jobs"] = int(post_daily_progress.get("current_success_jobs", 0) or 0)
    return progress


def _append_daily_progress_message(message: str, progress: dict[str, Any]) -> str:
    current_trade_date = progress.get("current_trade_date") or ""
    completed_through = progress.get("completed_through") or ""
    current_expected = int(progress.get("current_expected_jobs", 0) or 0)
    current_success = int(progress.get("current_success_jobs", 0) or 0)
    current_remaining = int(progress.get("current_remaining_jobs", 0) or 0)
    current_pct = progress.get("current_progress_pct") or "0.00"
    lines = [
        f"baostock_raw_completed_through={completed_through}",
        f"baostock_raw_current_trade_date={current_trade_date}",
        f"baostock_raw_current_progress={current_success}/{current_expected} ({current_pct}%)",
        f"baostock_raw_current_remaining_jobs={current_remaining}",
        f"baostock_raw_run_delta_current_success_jobs={int(progress.get('run_delta_current_success_jobs', 0) or 0)}",
    ]
    return "\n".join([message, *lines])


def _legacy_summary_dict(summary: BackfillSummary) -> dict[str, int]:
    return {
        "total_jobs": summary.total_tasks,
        "pending_jobs": summary.pending_tasks,
        "running_jobs": summary.running_tasks,
        "success_jobs": summary.success_tasks,
        "failed_jobs": summary.failed_tasks,
        "skipped_jobs": summary.skipped_tasks,
        "total_market_rows": summary.total_rows_written,
    }


def _legacy_summary_from_rows(rows: list[dict[str, Any]], fallback: BackfillSummary) -> dict[str, Any]:
    summary = _legacy_summary_dict(fallback)
    summary.update(
        {
            "total_staging_rows": 0,
            "latest_success_at": None,
            "latest_failed_at": None,
            "failed_examples": [],
        }
    )
    if rows:
        summary.update(summarize_backfill_status(rows))
    return summary


def _legacy_status_dict(
    *,
    post_rows: list[dict[str, Any]],
    post_summary: dict[str, Any],
    status: Any,
) -> dict[str, Any]:
    return {
        "watchdog_action": status.watchdog_action,
        "frontier": dict(status.current_frontier),
        "previous_frontier": dict(status.previous_frontier),
        "progress_advanced": status.progress_advanced,
        "work_remaining": status.work_remaining,
        "stale_jobs_reset": status.stale_tasks_reset,
        "timed_out": status.timed_out,
        "status_counts": _count_statuses(post_rows),
        "total_jobs": int(post_summary.get("total_jobs", 0) or 0),
    }


def _count_statuses(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        row_status = str(row.get("status"))
        counts[row_status] = counts.get(row_status, 0) + 1
    return counts
