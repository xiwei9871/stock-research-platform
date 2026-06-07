from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from stock_research.backfill_watchdog import (
    BackfillSummary,
    run_watchdog_once,
    should_send_watchdog_message,
)
from stock_research.feishu_notify import send_openclaw_feishu_message
from stock_research.stock_report_backfill import STATUS_FILE, TASKS_FILE


@dataclass(frozen=True)
class StockReportBackfillWatchdogAdapter:
    output_dir: str | Path
    task_name: str = "stock_report_backfill"
    dataset: str = "research.stock_report_event"

    def load_scope(self) -> dict[str, str]:
        return {
            "task": self.task_name,
            "task_name": self.task_name,
            "dataset": self.dataset,
            "run_id": f"stock-report-backfill:{Path(self.output_dir)}",
            "window": str(Path(self.output_dir)),
        }

    @property
    def status_path(self) -> Path:
        return Path(self.output_dir) / STATUS_FILE

    @property
    def tasks_path(self) -> Path:
        return Path(self.output_dir) / TASKS_FILE

    def load_status_rows(self) -> list[dict[str, Any]]:
        if not self.status_path.exists() and not self.tasks_path.exists():
            return []
        base_path = self.tasks_path if self.tasks_path.exists() else self.status_path
        frame = pd.read_csv(
            base_path,
            dtype={"symbol": "string", "ts_code": "string", "asset_id": "string", "task_id": "string"},
            low_memory=False,
        ).fillna("")
        if self.status_path.exists() and self.tasks_path.exists():
            status = pd.read_csv(
                self.status_path,
                dtype={"symbol": "string", "ts_code": "string", "asset_id": "string", "task_id": "string"},
                low_memory=False,
            ).fillna("")
            if "task_id" in status.columns and "task_id" in frame.columns:
                status_by_task = status.drop_duplicates(subset=["task_id"], keep="last").set_index("task_id")
                frame = frame.copy()
                for idx, row in frame.iterrows():
                    task_id = row.get("task_id")
                    if task_id not in status_by_task.index:
                        continue
                    existing = status_by_task.loc[task_id]
                    for column, value in existing.items():
                        if column in frame.columns:
                            frame.at[idx, column] = value
        return frame.fillna("").to_dict("records")

    def summarize_status(self, rows: list[dict[str, Any]]) -> BackfillSummary:
        statuses = [str(row.get("status") or "pending") for row in rows]
        pending = sum(1 for value in statuses if value in {"pending", ""})
        return BackfillSummary(
            total_tasks=len(rows),
            pending_tasks=pending,
            running_tasks=1 if pending > 0 else 0,
            success_tasks=sum(1 for value in statuses if value == "done"),
            failed_tasks=sum(1 for value in statuses if value in {"fetch_error", "schema_error"}),
            skipped_tasks=sum(1 for value in statuses if value == "no_report"),
            total_rows_written=sum(_safe_int(row.get("report_count")) for row in rows),
        )

    def compute_frontier(self, rows: list[dict[str, Any]]) -> dict[str, str | None]:
        completed_through: str | None = None
        currently_working_on: str | None = None
        for row in rows:
            label = str(row.get("ts_code") or row.get("symbol") or row.get("task_id") or "")
            status = str(row.get("status") or "pending")
            if status in {"done", "no_report"}:
                completed_through = label
                continue
            currently_working_on = label
            break
        return {
            "completed_through": completed_through,
            "currently_working_on": currently_working_on,
        }

    def reset_stale_tasks(self, stale_after_minutes: int) -> int:
        del stale_after_minutes
        return 0

    def run_once(
        self,
        *,
        scope: dict[str, str],
        max_jobs: int,
        workers: int,
        run_timeout_seconds: int,
    ) -> dict[str, Any]:
        del scope, max_jobs, workers, run_timeout_seconds
        summary = self.summarize_status(self.load_status_rows())
        return {
            "attempted": 0,
            "success": 0,
            "failed": 0,
            "rows": 0,
            "status": "observe_only",
            "timed_out": False,
            "lock_busy": summary.pending_tasks > 0,
        }

    def format_extra_status_lines(
        self,
        *,
        rows: list[dict[str, Any]],
        summary: BackfillSummary,
        scope: dict[str, str],
        run_result: dict[str, Any],
        status: Any,
    ) -> list[str]:
        del rows, scope, status
        return [
            f"status_path={self.status_path}",
            f"tasks_path={self.tasks_path}",
            f"run_status={run_result.get('status', '')}",
            f"done={summary.success_tasks}",
            f"no_report={summary.skipped_tasks}",
            f"fetch_error={summary.failed_tasks}",
            f"pending={summary.pending_tasks}",
            f"report_rows={summary.total_rows_written}",
        ]


def run_stock_report_backfill_watchdog(
    *,
    output_dir: str | Path,
    stale_after_minutes: int = 30,
    run_timeout_seconds: int = 60,
    max_jobs: int = 0,
    workers: int = 0,
    report_target: str,
    report_account: str = "jarvis",
    openclaw_bin: str = "openclaw",
    report_dry_run: bool = False,
) -> dict[str, Any]:
    adapter = StockReportBackfillWatchdogAdapter(output_dir=output_dir)
    result = run_watchdog_once(
        adapter=adapter,
        stale_after_minutes=stale_after_minutes,
        run_timeout_seconds=run_timeout_seconds,
        max_jobs=max_jobs,
        workers=workers,
        send_message=None,
    )
    if should_send_watchdog_message(result["status"]) and not report_dry_run:
        send_openclaw_feishu_message(
            message=result["message"],
            target=report_target,
            account=report_account,
            openclaw_bin=openclaw_bin,
            dry_run=report_dry_run,
        )
    return result


def _safe_int(value: Any) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0
