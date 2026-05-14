from __future__ import annotations

from typing import Any

from stock_research.backfill_watchdog import BackfillSummary, format_watchdog_message, run_watchdog_once
from stock_research.feishu_notify import send_openclaw_feishu_message
from stock_research.minute_backfill import summarize_backfill_status
from stock_research.minute_backfill_adapter import MinuteBackfillAdapter, _reconcile_timeout_run_result


WATCHDOG_ACTION_HEALTHY = "healthy"
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
    workers: int = 6,
    stale_after_minutes: int = 20,
    run_timeout_seconds: int = 1800,
    report_target: str,
    report_account: str = "jarvis",
    openclaw_bin: str = "openclaw",
    report_dry_run: bool = False,
) -> dict[str, Any]:
    adapter = MinuteBackfillAdapter(
        start_date=start_date,
        end_date=end_date,
        freq=freq,
        adjust_types=adjust_types,
        batch_by=batch_by,
        retry_failed=retry_failed,
        sleep_seconds=sleep_seconds,
    )
    result = run_watchdog_once(
        adapter=adapter,
        stale_after_minutes=stale_after_minutes,
        run_timeout_seconds=run_timeout_seconds,
        max_jobs=max_jobs,
        workers=workers,
        send_message=None,
    )

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
    }


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
