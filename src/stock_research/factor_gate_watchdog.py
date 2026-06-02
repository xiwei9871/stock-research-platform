from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from stock_research.backfill_watchdog import (
    BackfillSummary,
    BackfillWatchdogStatus,
    run_watchdog_once,
    should_send_watchdog_message,
)
from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all
from stock_research.factor_config import candidate_factor_names
from stock_research.factor_eval_batch import run_factor_gate_batch
from stock_research.feishu_notify import send_openclaw_feishu_message


DEFAULT_FACTOR_GATE_WATCHDOG_LOG = (
    Path("/Users/xiwei/stock_research")
    / "logs"
    / "full_history_completion"
    / "wave5-factor-gate-watchdog.log"
)


@dataclass(frozen=True)
class FactorGateBatchWatchdogAdapter:
    start_date: str
    end_date: str
    validation_start_date: str | None = None
    horizons: list[int] | None = None
    primary_horizon: int = 5
    calc_version: str = "v1"
    score_version: str = "manual_v1"
    quantiles: int = 5
    top_n: int = 30
    factor_names: list[str] | None = None
    log_path: Path = DEFAULT_FACTOR_GATE_WATCHDOG_LOG

    task_name: str = "factor_gate_batch"
    dataset: str = "factor.factor_approval"

    def selected_factor_names(self) -> list[str]:
        return self.factor_names if self.factor_names is not None else candidate_factor_names()

    def selected_horizons(self) -> list[int]:
        return self.horizons or [5, 10, 20, 60]

    def load_scope(self) -> dict[str, str]:
        return {
            "task": self.task_name,
            "task_name": self.task_name,
            "dataset": self.dataset,
            "run_id": (
                f"factor-gate:{self.score_version}:{self.calc_version}:"
                f"{self.start_date}:{self.end_date}"
            ),
            "window": f"{self.start_date}..{self.end_date}",
        }

    def load_status_rows(self) -> list[dict[str, Any]]:
        factors = self.selected_factor_names()
        approval_by_factor = {
            str(row["factor_name"]): row
            for row in _load_factor_gate_approval_rows(
                factor_names=factors,
                calc_version=self.calc_version,
                score_version=self.score_version,
            )
        }
        rows = []
        for factor_name in factors:
            approval = approval_by_factor.get(factor_name)
            rows.append(
                {
                    "factor_name": factor_name,
                    "status": "success" if approval is not None else "pending",
                    "approval_status": approval.get("status") if approval else None,
                    "reason": approval.get("reason") if approval else None,
                    "eval_run_id": approval.get("eval_run_id") if approval else None,
                    "row_count": 1 if approval is not None else 0,
                }
            )
        return rows

    def summarize_status(self, rows: list[dict[str, Any]]) -> BackfillSummary:
        pending = sum(1 for row in rows if row["status"] == "pending")
        success = sum(1 for row in rows if row["status"] == "success")
        return BackfillSummary(
            total_tasks=len(rows),
            pending_tasks=pending,
            running_tasks=0,
            success_tasks=success,
            failed_tasks=0,
            skipped_tasks=0,
            total_rows_written=sum(int(row.get("row_count") or 0) for row in rows),
        )

    def compute_frontier(self, rows: list[dict[str, Any]]) -> dict[str, str | None]:
        completed_through: str | None = None
        currently_working_on: str | None = None
        for row in rows:
            factor_name = str(row["factor_name"])
            if row["status"] == "success":
                completed_through = factor_name
                continue
            currently_working_on = factor_name
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
        del scope, workers, run_timeout_seconds
        pending_factors = [
            str(row["factor_name"])
            for row in self.load_status_rows()
            if row["status"] == "pending"
        ][:max_jobs]
        if not pending_factors:
            return {
                "attempted": 0,
                "success": 0,
                "failed": 0,
                "rows": 0,
                "status": "completed",
                "timed_out": False,
            }

        result = run_factor_gate_batch(
            factor_names=pending_factors,
            start_date=self.start_date,
            end_date=self.end_date,
            horizons=self.selected_horizons(),
            primary_horizon=self.primary_horizon,
            calc_version=self.calc_version,
            score_version=self.score_version,
            quantiles=self.quantiles,
            top_n=self.top_n,
            validation_start_date=self.validation_start_date,
        )
        success = len(result)
        return {
            "attempted": len(pending_factors),
            "success": success,
            "failed": 0,
            "rows": success,
            "status": "completed",
            "timed_out": False,
        }

    def format_extra_status_lines(
        self,
        *,
        rows: list[dict[str, Any]],
        summary: BackfillSummary,
        scope: dict[str, str],
        run_result: dict[str, Any],
        status: BackfillWatchdogStatus,
    ) -> list[str]:
        del summary, scope, status
        approved = sum(1 for row in rows if row.get("approval_status") == "approved")
        rejected = sum(1 for row in rows if row.get("approval_status") == "rejected")
        return [
            f"score_version={self.score_version}",
            f"calc_version={self.calc_version}",
            f"approved={approved}",
            f"rejected={rejected}",
            f"run_status={run_result.get('status', '')}",
            f"run_attempted={int(run_result.get('attempted', 0) or 0)}",
            f"run_success={int(run_result.get('success', 0) or 0)}",
            f"run_failed={int(run_result.get('failed', 0) or 0)}",
            f"run_rows={int(run_result.get('rows', 0) or 0)}",
        ]


def run_factor_gate_batch_watchdog(
    *,
    start_date: str,
    end_date: str,
    validation_start_date: str | None = None,
    horizons: list[int] | None = None,
    primary_horizon: int = 5,
    calc_version: str = "v1",
    score_version: str = "manual_v1",
    quantiles: int = 5,
    top_n: int = 30,
    factor_names: list[str] | None = None,
    max_jobs: int = 1,
    workers: int = 1,
    stale_after_minutes: int = 20,
    run_timeout_seconds: int = 1800,
    report_target: str,
    report_account: str = "jarvis",
    openclaw_bin: str = "openclaw",
    report_dry_run: bool = False,
    log_path: str | Path = DEFAULT_FACTOR_GATE_WATCHDOG_LOG,
) -> dict[str, Any]:
    adapter = FactorGateBatchWatchdogAdapter(
        start_date=start_date,
        end_date=end_date,
        validation_start_date=validation_start_date,
        horizons=horizons,
        primary_horizon=primary_horizon,
        calc_version=calc_version,
        score_version=score_version,
        quantiles=quantiles,
        top_n=top_n,
        factor_names=factor_names,
        log_path=Path(log_path),
    )
    result = run_watchdog_once(
        adapter=adapter,
        stale_after_minutes=stale_after_minutes,
        run_timeout_seconds=run_timeout_seconds,
        max_jobs=max_jobs,
        workers=workers,
        send_message=None,
    )
    if should_send_watchdog_message(result["status"]):
        send_openclaw_feishu_message(
            message=result["message"],
            target=report_target,
            account=report_account,
            openclaw_bin=openclaw_bin,
            dry_run=report_dry_run,
        )
    return result

def _load_factor_gate_approval_rows(
    *,
    factor_names: list[str],
    calc_version: str,
    score_version: str,
    service: str = SETTINGS.research_service,
) -> list[dict[str, Any]]:
    if not factor_names:
        return []
    sql = """
    SELECT factor_name, status, reason, eval_run_id
    FROM factor.factor_approval
    WHERE factor_name = ANY(%s)
      AND calc_version = %s
      AND score_version = %s
    """
    with connect(service) as conn:
        return fetch_all(conn, sql, [factor_names, calc_version, score_version])
