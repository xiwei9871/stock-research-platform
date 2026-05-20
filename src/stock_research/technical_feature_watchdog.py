from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import time
from typing import Any

from stock_research.backfill_watchdog import BackfillSummary, BackfillWatchdogStatus
from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all
from stock_research.factor_config import historical_research_start_date
from stock_research.factor_backfill import load_trade_dates_for_backfill
from stock_research.feishu_notify import send_openclaw_feishu_message
from stock_research.technical_feature_backfill import (
    backfill_technical_features_daily_range,
    load_complete_technical_feature_dates,
)
from stock_research.technical_feature_store import (
    TECHNICAL_FEATURE_CALC_VERSION,
    TECHNICAL_FEATURE_SOURCE,
)
from stock_research.backfill_watchdog import run_watchdog_once


@dataclass(frozen=True)
class TechnicalFeatureBackfillAdapter:
    start_date: str
    end_date: str
    adjust_type: str = "qfq"
    lookback_bars: int = 260
    source_data_version: str | None = None
    calc_version: str = TECHNICAL_FEATURE_CALC_VERSION
    sleep_between_runs_seconds: float = 0.0

    task_name: str = "technical_feature_backfill"
    dataset: str = "factor.stock_technical_features_daily"

    def load_scope(self) -> dict[str, str]:
        version = self.source_data_version or f"market_daily_bar:{self.adjust_type}"
        return {
            "task": self.task_name,
            "task_name": self.task_name,
            "dataset": self.dataset,
            "run_id": (
                f"technical-features:{self.adjust_type}:{version}:"
                f"{self.start_date}:{self.end_date}"
            ),
            "window": f"{self.start_date}..{self.end_date}",
        }

    def load_status_rows(self) -> list[dict[str, Any]]:
        trade_dates = load_trade_dates_for_backfill(
            start_date=self.start_date,
            end_date=self.end_date,
            adjust_type=self.adjust_type,
        )
        trade_dates = _prioritize_trade_dates_for_research_window(
            trade_dates,
            priority_start=historical_research_start_date(),
            priority_end=self.end_date,
        )
        complete_dates = load_complete_technical_feature_dates(
            start_date=self.start_date,
            end_date=self.end_date,
            adjust_type=self.adjust_type,
            calc_version=self.calc_version,
            source_data_version=self.source_data_version,
        )
        row_counts = _load_technical_feature_row_counts(
            start_date=self.start_date,
            end_date=self.end_date,
            adjust_type=self.adjust_type,
            calc_version=self.calc_version,
            source_data_version=self.source_data_version,
        )
        return [
            {
                "trade_date": trade_date,
                "status": "success" if trade_date in complete_dates else "pending",
                "row_count": int(row_counts.get(trade_date, 0)),
            }
            for trade_date in trade_dates
        ]

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
            trade_date = str(row["trade_date"])
            if row["status"] == "success":
                completed_through = trade_date
                continue
            currently_working_on = trade_date
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
        del scope
        pending_dates = [
            str(row["trade_date"])
            for row in self.load_status_rows()
            if row["status"] == "pending"
        ][:max_jobs]
        if not pending_dates:
            return {
                "attempted": 0,
                "success": 0,
                "failed": 0,
                "rows": 0,
                "status": "completed",
                "timed_out": False,
            }
        result = backfill_technical_features_daily_range(
            start_date=pending_dates[0],
            end_date=pending_dates[-1],
            lookback_bars=self.lookback_bars,
            adjust_type=self.adjust_type,
            source_data_version=self.source_data_version,
            trading_days_only=True,
            workers=workers,
            skip_complete=True,
            run_timeout_seconds=run_timeout_seconds,
        )
        result_attrs = getattr(result, "attrs", {})
        rows = int(result["feature_rows"].sum()) if not result.empty else 0
        return {
            "attempted": len(pending_dates),
            "success": len(result),
            "failed": 0,
            "rows": rows,
            "rows_written": int(result_attrs.get("rows_written", rows)),
            "batch_start_date": result_attrs.get("batch_start_date"),
            "batch_end_date": result_attrs.get("batch_end_date"),
            "batch_size_days": int(result_attrs.get("batch_size_days", len(pending_dates)) or 0),
            "worker_count": int(result_attrs.get("worker_count", workers) or 0),
            "compute_seconds": float(result_attrs.get("compute_seconds", 0.0) or 0.0),
            "days_per_hour": float(result_attrs.get("days_per_hour", 0.0) or 0.0),
            "rows_per_hour": float(result_attrs.get("rows_per_hour", 0.0) or 0.0),
            "sleep_between_runs_seconds": float(self.sleep_between_runs_seconds),
            "status": "completed",
            "timed_out": bool(result_attrs.get("timed_out", False)),
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
        del rows, summary, scope, status
        return [
            f"adjust_type={self.adjust_type}",
            f"lookback_bars={self.lookback_bars}",
            f"run_status={run_result.get('status', '')}",
            f"run_attempted={int(run_result.get('attempted', 0) or 0)}",
            f"run_success={int(run_result.get('success', 0) or 0)}",
            f"run_failed={int(run_result.get('failed', 0) or 0)}",
            f"run_rows={int(run_result.get('rows', 0) or 0)}",
            f"batch_start_date={run_result.get('batch_start_date') or ''}",
            f"batch_end_date={run_result.get('batch_end_date') or ''}",
            f"batch_size_days={int(run_result.get('batch_size_days', 0) or 0)}",
            f"worker_count={int(run_result.get('worker_count', 0) or 0)}",
            f"compute_seconds={float(run_result.get('compute_seconds', 0.0) or 0.0)}",
            f"sleep_between_runs_seconds={float(run_result.get('sleep_between_runs_seconds', 0.0) or 0.0)}",
            f"rows_written={int(run_result.get('rows_written', 0) or 0)}",
            f"days_per_hour={float(run_result.get('days_per_hour', 0.0) or 0.0)}",
            f"rows_per_hour={float(run_result.get('rows_per_hour', 0.0) or 0.0)}",
        ]


def run_technical_feature_backfill_watchdog(
    *,
    start_date: str,
    end_date: str,
    adjust_type: str = "qfq",
    lookback_bars: int = 260,
    source_data_version: str | None = None,
    max_jobs: int = 50,
    workers: int = 2,
    stale_after_minutes: int = 20,
    run_timeout_seconds: int = 1800,
    sleep_between_runs_seconds: float = 0.0,
    report_target: str,
    report_account: str = "jarvis",
    openclaw_bin: str = "openclaw",
    report_dry_run: bool = False,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    adapter = TechnicalFeatureBackfillAdapter(
        start_date=start_date,
        end_date=end_date,
        adjust_type=adjust_type,
        lookback_bars=lookback_bars,
        source_data_version=source_data_version,
        sleep_between_runs_seconds=sleep_between_runs_seconds,
    )
    result = run_watchdog_once(
        adapter=adapter,
        stale_after_minutes=stale_after_minutes,
        run_timeout_seconds=run_timeout_seconds,
        max_jobs=max_jobs,
        workers=workers,
        send_message=None,
    )
    send_openclaw_feishu_message(
        message=result["message"],
        target=report_target,
        account=report_account,
        openclaw_bin=openclaw_bin,
        dry_run=report_dry_run,
    )
    if sleep_between_runs_seconds > 0:
        sleep(float(sleep_between_runs_seconds))
    return result


def _load_technical_feature_row_counts(
    *,
    start_date: str,
    end_date: str,
    adjust_type: str,
    calc_version: str,
    source_data_version: str | None,
    service: str = SETTINGS.research_service,
) -> dict[str, int]:
    version = source_data_version or f"market_daily_bar:{adjust_type}"
    sql = """
    SELECT trade_date, count(*) AS rows
    FROM factor.stock_technical_features_daily
    WHERE adjust_type = %s
      AND source = %s
      AND source_data_version = %s
      AND calc_version = %s
      AND trade_date BETWEEN %s AND %s
    GROUP BY trade_date
    """
    with connect(service) as conn:
        rows = fetch_all(
            conn,
            sql,
            [
                adjust_type,
                TECHNICAL_FEATURE_SOURCE,
                version,
                calc_version,
                start_date,
                end_date,
            ],
        )
    return {str(row["trade_date"])[:10]: int(row["rows"]) for row in rows}


def _prioritize_trade_dates_for_research_window(
    trade_dates: list[str],
    *,
    priority_start: str,
    priority_end: str,
) -> list[str]:
    def _priority_key(raw_value: str) -> tuple[int, str]:
        trade_date = str(raw_value)[:10]
        if priority_start <= trade_date <= priority_end:
            return (0, trade_date)
        if trade_date < priority_start:
            return (1, trade_date)
        return (2, trade_date)

    return sorted((str(value)[:10] for value in trade_dates), key=_priority_key)
