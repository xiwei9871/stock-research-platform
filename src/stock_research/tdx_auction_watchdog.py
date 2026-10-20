"""Watchdog control plane for the TDX opening-auction backfill."""

from __future__ import annotations

from dataclasses import dataclass
import datetime as dt
import json
from pathlib import Path
import time
from typing import Any, Callable, Sequence

from stock_research.backfill_runs import (
    claim_backfill_tasks_for_service,
    create_backfill_run,
    mark_backfill_task_failed_for_service,
    mark_backfill_task_success_for_service,
    reset_stale_backfill_tasks_for_service,
)
from stock_research.backfill_watchdog import (
    BackfillSummary,
    BackfillWatchdogStatus,
    run_watchdog_once,
    should_send_watchdog_message,
)
from stock_research.config import SETTINGS
from stock_research.db import connect, execute, fetch_all
from stock_research.feishu_notify import send_openclaw_feishu_message
from stock_research.tdx_auction_backfill import (
    TDX_AUCTION_ENDPOINT,
    TDX_AUCTION_SOURCE,
    TDX_AUCTION_SOURCE_VERSION,
    backfill_tdx_auction_date,
    tdx_date_result_is_fatal,
)


TDX_AUCTION_DATASET = "market.stock_auction_bar"
DEFAULT_REPORT_TARGET = "chat:oc_82dd978138a0cde5864868c5b5b8e754"
DEFAULT_MONTH_LEDGER = Path(
    "/Users/xiwei/stock_research/outputs/research/tdx_auction_backfill_watchdog/reported_months.json"
)


def build_daily_partitions(trade_dates: Sequence[str | dt.date]) -> list[dict[str, str]]:
    """Create one ingest task per open trading date."""

    normalized = sorted({_date_text(value) for value in trade_dates})
    return [
        {
            "partition_key": value,
            "start_date": value,
            "end_date": value,
        }
        for value in normalized
    ]


def _date_text(value: str | dt.date | dt.datetime | None) -> str:
    if value is None:
        return ""
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()[:10]
    return str(value)[:10]


def _month_key(value: str | dt.date | dt.datetime) -> str:
    return _date_text(value)[:7]


def completed_month_summaries(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return only months whose every planned trading-day task succeeded."""

    grouped: dict[str, dict[str, int]] = {}
    for row in rows:
        month = _month_key(row["trade_date"])
        bucket = grouped.setdefault(month, {"total_days": 0, "success_days": 0, "rows_written": 0})
        bucket["total_days"] += 1
        if str(row.get("status")) == "success":
            bucket["success_days"] += 1
        bucket["rows_written"] += int(row.get("rows_written") or row.get("row_count") or 0)
        params = row.get("params") or {}
        if isinstance(params, str):
            try:
                params = json.loads(params)
            except json.JSONDecodeError:
                params = {}
        for metric in (
            "requested_symbols",
            "failed_symbols",
            "missing_symbols",
            "unsupported_symbols",
            "excluded_symbols",
        ):
            value = int(params.get(metric, row.get(metric, 0)) or 0) if isinstance(params, dict) else 0
            if value:
                bucket[metric] = bucket.get(metric, 0) + value
    return [
        {"month": month, **summary}
        for month, summary in sorted(grouped.items())
        if summary["total_days"] > 0 and summary["success_days"] == summary["total_days"]
    ]


def newly_completed_months(
    rows: Sequence[dict[str, Any]],
    *,
    reported_months: set[str],
) -> list[str]:
    return [
        str(summary["month"])
        for summary in completed_month_summaries(rows)
        if str(summary["month"]) not in reported_months
    ]


def _load_report_ledger(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text())
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return {"reported_months": []}
    if not isinstance(payload, dict):
        return {"reported_months": []}
    reported = payload.get("reported_months", [])
    if not isinstance(reported, list):
        reported = []
    return {**payload, "reported_months": [str(item) for item in reported]}


def _save_report_ledger(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def _load_month_summary(rows: Sequence[dict[str, Any]], month: str) -> dict[str, Any]:
    for summary in completed_month_summaries(rows):
        if summary["month"] == month:
            return summary
    return {"month": month, "total_days": 0, "success_days": 0, "rows_written": 0}


def send_monthly_completion_reports(
    *,
    rows: Sequence[dict[str, Any]],
    ledger_path: str | Path,
    report_target: str,
    report_account: str = "jarvis",
    openclaw_bin: str = "openclaw",
    report_dry_run: bool = False,
    send: Callable[..., Any] = send_openclaw_feishu_message,
) -> list[dict[str, Any]]:
    """Send each newly completed month once and return delivery outcomes."""

    path = Path(ledger_path)
    ledger = _load_report_ledger(path)
    reported = set(ledger["reported_months"])
    reports: list[dict[str, Any]] = []
    for month in newly_completed_months(rows, reported_months=reported):
        summary = _load_month_summary(rows, month)
        message = (
            "TDX集合竞价回填月度完成\n"
            f"月份={month}\n"
            f"交易日={summary['success_days']}/{summary['total_days']}\n"
            f"查询标的数={summary.get('requested_symbols', 0)}\n"
            f"正式撮合行数={summary['rows_written']}\n"
            f"无匹配={summary.get('missing_symbols', 0)}\n"
            f"TDX格式不支持={summary.get('unsupported_symbols', 0)}\n"
            f"请求异常={summary.get('failed_symbols', 0)}\n"
            f"当前退市未请求={summary.get('excluded_symbols', 0)}\n"
            f"来源={TDX_AUCTION_ENDPOINT}，volume单位=手"
        )
        outcome: dict[str, Any] = {"month": month, "message": message, "sent": False}
        try:
            send(
                message=message,
                target=report_target,
                account=report_account,
                openclaw_bin=openclaw_bin,
                dry_run=report_dry_run,
            )
            outcome["sent"] = True
            if not report_dry_run:
                reported.add(month)
                ledger["reported_months"] = sorted(reported)
                ledger["updated_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
                _save_report_ledger(path, ledger)
        except Exception as exc:  # noqa: BLE001 - delivery must not lose DB progress
            outcome["error"] = f"{exc.__class__.__name__}: {exc}"
        reports.append(outcome)
    return reports


def _load_tdx_trade_dates(
    *,
    start_date: str,
    end_date: str,
    service: str,
) -> list[str]:
    sql = """
    SELECT DISTINCT trade_date::text AS trade_date
    FROM market.trading_calendar
    WHERE is_open = true
      AND trade_date BETWEEN %s AND %s
    ORDER BY trade_date
    """
    with connect(service) as conn:
        return [str(row["trade_date"])[:10] for row in fetch_all(conn, sql, [start_date, end_date])]


def _load_status_rows(*, run_id: str, service: str) -> list[dict[str, Any]]:
    sql = """
    SELECT
        task_id, partition_key, start_date::text AS trade_date, end_date::text AS end_date,
        status, rows_read, rows_written, attempts, error_message, params
    FROM ingest.backfill_task
    WHERE run_id = %s
    ORDER BY start_date, partition_key
    """
    with connect(service) as conn:
        return fetch_all(conn, sql, [run_id])


@dataclass
class TdxAuctionBackfillAdapter:
    start_date: str
    end_date: str
    service: str = SETTINGS.research_service
    hosts: tuple[str, ...] | None = None
    timeout_seconds: float = 8.0
    server_count: int = 4
    connections_per_server: int = 1
    retry_attempts: int = 2
    retry_sleep_seconds: float = 0.25
    max_pages: int = 100

    task_name: str = "tdx_auction_backfill"
    dataset: str = TDX_AUCTION_DATASET

    def load_scope(self) -> dict[str, str]:
        trade_dates = _load_tdx_trade_dates(
            start_date=self.start_date,
            end_date=self.end_date,
            service=self.service,
        )
        partitions = build_daily_partitions(trade_dates)
        run_id = (
            f"tdx-auction-open:{TDX_AUCTION_SOURCE_VERSION}:"
            f"{self.start_date}:{self.end_date}"
        )
        with connect(self.service) as conn:
            create_backfill_run(
                conn,
                run_id=run_id,
                dataset=self.dataset,
                source=TDX_AUCTION_SOURCE,
                source_version=TDX_AUCTION_SOURCE_VERSION,
                start_date=self.start_date,
                end_date=self.end_date,
                partitions=partitions,
                params={"auction_phase": "open_call", "endpoint": TDX_AUCTION_ENDPOINT},
            )
        return {
            "task": self.task_name,
            "task_name": self.task_name,
            "dataset": self.dataset,
            "run_id": run_id,
            "window": f"{self.start_date}..{self.end_date}",
        }

    def load_status_rows(self) -> list[dict[str, Any]]:
        run_id = (
            f"tdx-auction-open:{TDX_AUCTION_SOURCE_VERSION}:"
            f"{self.start_date}:{self.end_date}"
        )
        return _load_status_rows(run_id=run_id, service=self.service)

    def summarize_status(self, rows: list[dict[str, Any]]) -> BackfillSummary:
        counts = {status: sum(1 for row in rows if row.get("status") == status) for status in (
            "pending", "running", "success", "failed", "skipped"
        )}
        return BackfillSummary(
            total_tasks=len(rows),
            pending_tasks=counts["pending"],
            running_tasks=counts["running"],
            success_tasks=counts["success"],
            failed_tasks=counts["failed"],
            skipped_tasks=counts["skipped"],
            total_rows_written=sum(int(row.get("rows_written") or 0) for row in rows),
        )

    def compute_frontier(self, rows: list[dict[str, Any]]) -> dict[str, str | None]:
        completed_through: str | None = None
        currently_working_on: str | None = None
        for row in rows:
            if str(row.get("status")) == "success":
                completed_through = _date_text(row.get("trade_date"))
                continue
            currently_working_on = _date_text(row.get("trade_date")) or None
            break
        return {
            "completed_through": completed_through,
            "currently_working_on": currently_working_on,
        }

    def reset_stale_tasks(self, stale_after_minutes: int) -> int:
        return reset_stale_backfill_tasks_for_service(
            dataset=self.dataset,
            older_than_minutes=stale_after_minutes,
            service=self.service,
        )

    def _record_task_metrics(self, *, task_id: str, result: dict[str, Any]) -> None:
        metrics = {
            "requested_symbols": int(result.get("requested_codes", 0) or 0),
            "matched_rows": int(result.get("matched_rows", result.get("rows_written", 0)) or 0),
            "missing_symbols": int(result.get("missing_codes", 0) or 0),
            "failed_symbols": int(result.get("failed_codes", 0) or 0),
            "unsupported_symbols": int(result.get("unsupported_codes", 0) or 0),
            "excluded_symbols": int(result.get("excluded_codes", 0) or 0),
            "failed_examples": result.get("failed_examples", [])[:20],
            "unsupported_examples": result.get("unsupported_examples", [])[:20],
        }
        with connect(self.service) as conn:
            execute(
                conn,
                """
                UPDATE ingest.backfill_task
                SET params = COALESCE(params, '{}'::jsonb) || %s::jsonb,
                    updated_at = now()
                WHERE task_id = %s
                """,
                [json.dumps(metrics), task_id],
            )

    def run_once(
        self,
        *,
        scope: dict[str, str],
        max_jobs: int,
        workers: int,
        run_timeout_seconds: int,
    ) -> dict[str, Any]:
        claimed = claim_backfill_tasks_for_service(
            run_id=scope["run_id"],
            limit=max_jobs,
            service=self.service,
        )
        if not claimed:
            return {"attempted": 0, "success": 0, "failed": 0, "rows": 0, "status": "completed", "timed_out": False}
        started = time.monotonic()
        success = failed = rows = requested = missing = failed_symbols = unsupported_symbols = excluded_symbols = 0
        timed_out = False
        errors: list[str] = []
        for task in claimed:
            if time.monotonic() - started >= run_timeout_seconds:
                timed_out = True
                break
            date_text = _date_text(task["start_date"])
            try:
                result = backfill_tdx_auction_date(
                    date_text,
                    service=self.service,
                    hosts=self.hosts,
                    timeout_seconds=self.timeout_seconds,
                    server_count=self.server_count,
                    connections_per_server=self.connections_per_server,
                    workers=workers,
                    retry_attempts=self.retry_attempts,
                    retry_sleep_seconds=self.retry_sleep_seconds,
                    max_pages=self.max_pages,
                )
                requested += int(result.get("requested_codes", 0))
                missing += int(result.get("missing_codes", 0))
                failed_symbols += int(result.get("failed_codes", 0))
                unsupported_symbols += int(result.get("unsupported_codes", 0))
                excluded_symbols += int(result.get("excluded_codes", 0))
                rows += int(result.get("rows_written", 0))
                if tdx_date_result_is_fatal(result):
                    failed += 1
                    detail = result.get("failed_examples") or []
                    error = f"TDX symbol failures: {detail[:3]}"
                    errors.append(f"{date_text}: {error}")
                    mark_backfill_task_failed_for_service(
                        task_id=str(task["task_id"]), error_message=error, service=self.service
                    )
                    self._record_task_metrics(task_id=str(task["task_id"]), result=result)
                else:
                    success += 1
                    mark_backfill_task_success_for_service(
                        task_id=str(task["task_id"]),
                        rows_read=int(result.get("requested_codes", 0)),
                        rows_written=int(result.get("rows_written", 0)),
                        service=self.service,
                    )
                    self._record_task_metrics(task_id=str(task["task_id"]), result=result)
            except Exception as exc:  # noqa: BLE001 - task is retriable
                failed += 1
                error = f"{exc.__class__.__name__}: {exc}"
                errors.append(f"{date_text}: {error}")
                mark_backfill_task_failed_for_service(
                    task_id=str(task["task_id"]), error_message=error, service=self.service
                )
        return {
            "attempted": len(claimed),
            "success": success,
            "failed": failed,
            "rows": rows,
            "rows_written": rows,
            "requested_codes": requested,
            "missing_codes": missing,
            "failed_symbols": failed_symbols,
            "unsupported_symbols": unsupported_symbols,
            "excluded_symbols": excluded_symbols,
            "errors": errors[:20],
            "status": "timed_out" if timed_out else "completed",
            "timed_out": timed_out,
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
        return [
            f"endpoint={TDX_AUCTION_ENDPOINT}",
            f"volume_unit=hand",
            f"run_status={run_result.get('status', '')}",
            f"run_attempted={int(run_result.get('attempted', 0) or 0)}",
            f"run_success={int(run_result.get('success', 0) or 0)}",
            f"run_failed={int(run_result.get('failed', 0) or 0)}",
            f"run_rows={int(run_result.get('rows', 0) or 0)}",
            f"run_requested_symbols={int(run_result.get('requested_codes', 0) or 0)}",
            f"run_failed_symbols={int(run_result.get('failed_symbols', 0) or 0)}",
            f"run_unsupported_symbols={int(run_result.get('unsupported_symbols', 0) or 0)}",
            f"run_excluded_symbols={int(run_result.get('excluded_symbols', 0) or 0)}",
            f"run_missing_symbols={int(run_result.get('missing_codes', 0) or 0)}",
            f"completed_months={len(completed_month_summaries(rows))}",
        ]


def run_tdx_auction_backfill_watchdog(
    *,
    start_date: str,
    end_date: str,
    max_jobs: int = 4,
    workers: int = 8,
    stale_after_minutes: int = 60,
    run_timeout_seconds: int = 3600,
    hosts: Sequence[str] | None = None,
    timeout_seconds: float = 8.0,
    server_count: int = 4,
    connections_per_server: int = 1,
    retry_attempts: int = 2,
    retry_sleep_seconds: float = 0.25,
    max_pages: int = 100,
    service: str = SETTINGS.research_service,
    report_target: str = DEFAULT_REPORT_TARGET,
    report_account: str = "jarvis",
    openclaw_bin: str = "openclaw",
    report_dry_run: bool = False,
    ledger_path: str | Path = DEFAULT_MONTH_LEDGER,
    send: Callable[..., Any] = send_openclaw_feishu_message,
) -> dict[str, Any]:
    adapter = TdxAuctionBackfillAdapter(
        start_date=start_date,
        end_date=end_date,
        service=service,
        hosts=tuple(hosts) if hosts else None,
        timeout_seconds=timeout_seconds,
        server_count=server_count,
        connections_per_server=connections_per_server,
        retry_attempts=retry_attempts,
        retry_sleep_seconds=retry_sleep_seconds,
        max_pages=max_pages,
    )
    result = run_watchdog_once(
        adapter=adapter,
        stale_after_minutes=stale_after_minutes,
        run_timeout_seconds=run_timeout_seconds,
        max_jobs=max_jobs,
        workers=workers,
        send_message=None,
    )
    result["monthly_reports"] = send_monthly_completion_reports(
        rows=result["post_rows"],
        ledger_path=ledger_path,
        report_target=report_target,
        report_account=report_account,
        openclaw_bin=openclaw_bin,
        report_dry_run=report_dry_run,
        send=send,
    )
    # The daily watchdog state remains in the host log.  Feishu is reserved
    # for monthly completion events and exceptional watchdog states, so a
    # seven-day catch-up does not flood the group with one heartbeat per run.
    should_send_status = bool(result["monthly_reports"]) or result["status"].watchdog_action != "healthy"
    if should_send_status and should_send_watchdog_message(result["status"]):
        try:
            send(
                message=result["message"],
                target=report_target,
                account=report_account,
                openclaw_bin=openclaw_bin,
                dry_run=report_dry_run,
            )
        except Exception as exc:  # noqa: BLE001 - status remains available locally
            result["watchdog_report_error"] = f"{exc.__class__.__name__}: {exc}"
    return result
