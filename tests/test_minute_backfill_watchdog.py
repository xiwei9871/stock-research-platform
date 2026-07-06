import datetime as dt
import json
from argparse import Namespace
import threading
import time
from pathlib import Path

import pytest

from stock_research.backfill_watchdog import BackfillSummary, BackfillWatchdogStatus
import stock_research.baostock_minute_backfill_watchdog as baostock_minute_backfill_watchdog
from stock_research.baostock_minute_backfill_watchdog import allocate_daily_backfill_quota
from stock_research.minute_backfill_adapter import (
    MinuteBackfillAdapter,
    _run_backfill_once_with_timeout,
)
import stock_research.minute_backfill_watchdog as minute_backfill_watchdog
from stock_research.minute_backfill_watchdog import run_minute_backfill_watchdog


def _row(
    start_date: dt.date,
    end_date: dt.date,
    status: str,
    *,
    adjust_type: str = "raw",
    ts_code: str = "600000.SH",
) -> dict[str, object]:
    return {
        "job_id": f"{ts_code}-{adjust_type}-{start_date.isoformat()}",
        "ts_code": ts_code,
        "adjust_type": adjust_type,
        "start_date": start_date,
        "end_date": end_date,
        "status": status,
    }


def test_baostock_daily_progress_treats_skipped_jobs_as_handled():
    sql = baostock_minute_backfill_watchdog._MINUTE_BACKFILL_DAILY_PROGRESS_SQL

    assert "j.status = ANY(ARRAY['success','skipped'])" in sql


def test_run_minute_backfill_watchdog_delegates_through_generic_runner(monkeypatch):
    generic_calls = []
    sent = []

    def fake_run_watchdog_once(**kwargs):
        generic_calls.append(kwargs)
        return {
            "scope": {"run_id": "minute-backfill:5min:raw:2024-01-01:2024-01-31", "window": "2024-01-01..2024-01-31"},
            "pre_rows": [],
            "post_rows": [],
            "pre_summary": BackfillSummary(0, 0, 0, 0, 0, 0, 0),
            "post_summary": BackfillSummary(0, 0, 0, 0, 0, 0, 0),
            "previous_frontier": {"completed_through": None, "currently_working_on": None},
            "frontier": {"completed_through": None, "currently_working_on": None},
            "status": BackfillWatchdogStatus(
                watchdog_action="healthy",
                progress_advanced=False,
                work_remaining=False,
                stale_tasks_reset=0,
                timed_out=False,
                previous_frontier={"completed_through": None, "currently_working_on": None},
                current_frontier={"completed_through": None, "currently_working_on": None},
            ),
            "stale_tasks_reset": 0,
            "run_result": {
                "attempted": 0,
                "success": 0,
                "failed": 0,
                "rows": 0,
                "status": "completed",
                "timed_out": False,
            },
            "timed_out": False,
            "message": "backfill_watchdog|status\naction=healthy",
        }

    monkeypatch.setattr(minute_backfill_watchdog, "run_watchdog_once", fake_run_watchdog_once)
    monkeypatch.setattr(
        minute_backfill_watchdog,
        "send_openclaw_feishu_message",
        lambda **kwargs: sent.append(kwargs),
    )

    result = run_minute_backfill_watchdog(
        start_date="2024-01-01",
        end_date="2024-01-31",
        freq="5min",
        adjust_types=["raw"],
        report_target="chat:test",
        report_account="jarvis",
        openclaw_bin="openclaw",
        report_dry_run=True,
    )

    assert len(generic_calls) == 1
    assert isinstance(generic_calls[0]["adapter"], MinuteBackfillAdapter)
    assert generic_calls[0]["stale_after_minutes"] == 20
    assert generic_calls[0]["run_timeout_seconds"] == 1800
    assert generic_calls[0]["max_jobs"] == 1200
    assert generic_calls[0]["workers"] == 8
    assert generic_calls[0]["send_message"] is None
    assert sent == []
    assert result["pre_summary"] == {
        "total_jobs": 0,
        "pending_jobs": 0,
        "running_jobs": 0,
        "success_jobs": 0,
        "failed_jobs": 0,
        "skipped_jobs": 0,
        "total_market_rows": 0,
        "total_staging_rows": 0,
        "latest_success_at": None,
        "latest_failed_at": None,
        "failed_examples": [],
    }
    assert result["status"] == {
        "watchdog_action": "healthy",
        "frontier": {"completed_through": None, "currently_working_on": None},
        "previous_frontier": {"completed_through": None, "currently_working_on": None},
        "progress_advanced": False,
        "work_remaining": False,
        "stale_jobs_reset": 0,
        "timed_out": False,
        "status_counts": {},
        "total_jobs": 0,
    }
    assert result["run_result"] == {
        "attempted": 0,
        "success": 0,
        "failed": 0,
        "rows": 0,
        "status": "completed",
        "timed_out": False,
    }
    assert result["timed_out"] is False
    assert result["message"] == "backfill_watchdog|status\naction=healthy"


def test_run_minute_backfill_watchdog_limits_jobs_by_baostock_daily_quota(monkeypatch, tmp_path):
    generic_calls = []

    def fake_run_watchdog_once(**kwargs):
        generic_calls.append(kwargs)
        return {
            "scope": {"run_id": "minute-backfill:5min:raw,qfq:2024-01-01:2024-01-31", "window": "2024-01-01..2024-01-31"},
            "pre_rows": [],
            "post_rows": [],
            "pre_summary": BackfillSummary(0, 0, 0, 0, 0, 0, 0),
            "post_summary": BackfillSummary(0, 0, 0, 0, 0, 0, 0),
            "previous_frontier": {"completed_through": None, "currently_working_on": None},
            "frontier": {"completed_through": None, "currently_working_on": None},
            "status": BackfillWatchdogStatus(
                watchdog_action="healthy",
                progress_advanced=True,
                work_remaining=True,
                stale_tasks_reset=0,
                timed_out=False,
                previous_frontier={"completed_through": None, "currently_working_on": None},
                current_frontier={"completed_through": None, "currently_working_on": "2024-01"},
            ),
            "stale_tasks_reset": 0,
            "run_result": {
                "attempted": 12,
                "success": 12,
                "failed": 0,
                "rows": 576,
                "status": "completed",
                "timed_out": False,
            },
            "timed_out": False,
            "message": "backfill_watchdog|status\nrun_success=12",
        }

    monkeypatch.setattr(minute_backfill_watchdog, "run_watchdog_once", fake_run_watchdog_once)
    monkeypatch.setattr(minute_backfill_watchdog, "send_openclaw_feishu_message", lambda **kwargs: None)
    monkeypatch.setattr(minute_backfill_watchdog, "load_active_baostock_asset_count", lambda: 10)

    result = run_minute_backfill_watchdog(
        start_date="2024-01-01",
        end_date="2024-01-31",
        freq="5min",
        adjust_types=["raw", "qfq"],
        max_jobs=100,
        enable_baostock_request_budget=True,
        baostock_daily_request_limit=100,
        baostock_safety_multiplier=1.1,
        today_adjust_types=["raw", "qfq"],
        request_ledger_path=tmp_path / "quota.json",
        quota_day=dt.date(2026, 7, 2),
        report_target="chat:test",
    )

    assert generic_calls[0]["max_jobs"] == 70
    assert result["baostock_request_budget"]["safe_daily_request_budget"] == 90
    assert result["baostock_request_budget"]["today_reserved_requests"] == 20
    assert result["baostock_request_budget"]["backfill_request_budget"] == 70
    assert result["baostock_request_budget"]["allocated_requests"] == 70
    assert result["baostock_request_budget"]["consumed_requests"] == 12


def test_run_minute_backfill_watchdog_claims_only_raw_jobs_when_baostock_budget_is_enabled(monkeypatch, tmp_path):
    generic_calls = []

    def fake_run_watchdog_once(**kwargs):
        generic_calls.append(kwargs)
        return {
            "scope": {"run_id": "minute-backfill:5min:raw:2024-01-01:2024-01-31", "window": "2024-01-01..2024-01-31"},
            "pre_rows": [],
            "post_rows": [],
            "pre_summary": BackfillSummary(0, 0, 0, 0, 0, 0, 0),
            "post_summary": BackfillSummary(0, 0, 0, 0, 0, 0, 0),
            "previous_frontier": {"completed_through": None, "currently_working_on": None},
            "frontier": {"completed_through": None, "currently_working_on": None},
            "status": BackfillWatchdogStatus(
                watchdog_action="healthy",
                progress_advanced=True,
                work_remaining=True,
                stale_tasks_reset=0,
                timed_out=False,
                previous_frontier={"completed_through": None, "currently_working_on": None},
                current_frontier={"completed_through": None, "currently_working_on": "2024-01"},
            ),
            "stale_tasks_reset": 0,
            "run_result": {
                "attempted": 5,
                "success": 5,
                "failed": 0,
                "rows": 240,
                "status": "completed",
                "timed_out": False,
            },
            "timed_out": False,
            "message": "backfill_watchdog|status\nrun_success=5",
        }

    monkeypatch.setattr(minute_backfill_watchdog, "run_watchdog_once", fake_run_watchdog_once)
    monkeypatch.setattr(minute_backfill_watchdog, "send_openclaw_feishu_message", lambda **kwargs: None)
    monkeypatch.setattr(minute_backfill_watchdog, "load_active_baostock_asset_count", lambda: 10)

    result = run_minute_backfill_watchdog(
        start_date="2024-01-01",
        end_date="2024-01-31",
        freq="5min",
        adjust_types=["raw", "qfq"],
        max_jobs=100,
        enable_baostock_request_budget=True,
        baostock_daily_request_limit=100,
        baostock_safety_multiplier=1.1,
        today_adjust_types=["raw", "qfq"],
        request_ledger_path=tmp_path / "quota.json",
        quota_day=dt.date(2026, 7, 2),
        report_target="chat:test",
    )

    assert generic_calls[0]["adapter"].adjust_types == ["raw"]
    assert generic_calls[0]["adapter"].derive_qfq_from_raw is True
    assert result["baostock_request_budget"]["baostock_fetch_adjust_types"] == ["raw"]
    assert result["baostock_request_budget"]["requested_adjust_types"] == ["raw", "qfq"]


def test_run_minute_backfill_watchdog_reports_raw_daily_progress(monkeypatch, tmp_path):
    progress_snapshots = iter(
        [
            {
                "completed_through": "2020-01-02",
                "current_trade_date": "2020-01-03",
                "current_expected_jobs": 3560,
                "current_success_jobs": 100,
                "current_remaining_jobs": 3460,
                "current_progress_pct": "2.81",
                "completed_trade_days": 1,
                "total_trade_days": 20,
            },
            {
                "completed_through": "2020-01-02",
                "current_trade_date": "2020-01-03",
                "current_expected_jobs": 3560,
                "current_success_jobs": 150,
                "current_remaining_jobs": 3410,
                "current_progress_pct": "4.21",
                "completed_trade_days": 1,
                "total_trade_days": 20,
            },
        ]
    )

    def fake_run_watchdog_once(**kwargs):
        return {
            "scope": {"run_id": "minute-backfill:5min:raw:2020-01-02:2020-01-31", "window": "2020-01-02..2020-01-31"},
            "pre_rows": [],
            "post_rows": [],
            "pre_summary": BackfillSummary(0, 0, 0, 0, 0, 0, 0),
            "post_summary": BackfillSummary(0, 0, 0, 0, 0, 0, 0),
            "previous_frontier": {"completed_through": None, "currently_working_on": None},
            "frontier": {"completed_through": None, "currently_working_on": "2020-01"},
            "status": BackfillWatchdogStatus(
                watchdog_action="healthy",
                progress_advanced=True,
                work_remaining=True,
                stale_tasks_reset=0,
                timed_out=False,
                previous_frontier={"completed_through": None, "currently_working_on": None},
                current_frontier={"completed_through": None, "currently_working_on": "2020-01"},
            ),
            "stale_tasks_reset": 0,
            "run_result": {
                "attempted": 50,
                "success": 50,
                "failed": 0,
                "rows": 2400,
                "status": "completed",
                "timed_out": False,
            },
            "timed_out": False,
            "message": "backfill_watchdog|status\nrun_success=50",
        }

    monkeypatch.setattr(minute_backfill_watchdog, "run_watchdog_once", fake_run_watchdog_once)
    monkeypatch.setattr(minute_backfill_watchdog, "send_openclaw_feishu_message", lambda **kwargs: None)
    monkeypatch.setattr(minute_backfill_watchdog, "load_active_baostock_asset_count", lambda: 10)
    monkeypatch.setattr(
        minute_backfill_watchdog,
        "load_baostock_minute_backfill_progress",
        lambda **kwargs: next(progress_snapshots),
        raising=False,
    )

    result = run_minute_backfill_watchdog(
        start_date="2020-01-02",
        end_date="2020-01-31",
        freq="5min",
        adjust_types=["raw", "qfq"],
        max_jobs=100,
        enable_baostock_request_budget=True,
        baostock_daily_request_limit=100,
        baostock_safety_multiplier=1.1,
        today_adjust_types=["raw", "qfq"],
        request_ledger_path=tmp_path / "quota.json",
        quota_day=dt.date(2026, 7, 2),
        report_target="chat:test",
    )

    progress = result["baostock_backfill_progress"]
    assert progress["current_trade_date"] == "2020-01-03"
    assert progress["current_success_jobs"] == 150
    assert progress["run_delta_current_success_jobs"] == 50
    assert "baostock_raw_completed_through=2020-01-02" in result["message"]
    assert "baostock_raw_current_progress=150/3560 (4.21%)" in result["message"]
    assert "baostock_raw_run_delta_current_success_jobs=50" in result["message"]


def test_baostock_minute_backfill_watchdog_cli_prints_raw_daily_progress(monkeypatch, capsys):
    from stock_research import cli

    monkeypatch.setattr(
        cli,
        "run_minute_backfill_watchdog",
        lambda **kwargs: {
            "pre_summary": {"success_jobs": 10},
            "post_summary": {"success_jobs": 15},
            "status": {"watchdog_action": "healthy", "work_remaining": True},
            "run_result": {"rows": 240},
            "baostock_request_budget": {
                "safe_daily_request_budget": 90,
                "today_reserved_requests": 20,
                "backfill_request_budget": 70,
                "allocated_requests": 70,
                "consumed_requests": 5,
            },
            "baostock_backfill_progress": {
                "completed_through": "2020-01-02",
                "current_trade_date": "2020-01-03",
                "current_expected_jobs": 3560,
                "current_success_jobs": 150,
                "current_remaining_jobs": 3410,
                "current_progress_pct": "4.21",
                "run_delta_current_success_jobs": 50,
            },
        },
    )

    cli.run_baostock_minute_backfill_watchdog_command(
        Namespace(
            start_date="2020-01-02",
            end_date="2020-01-31",
            freq="5min",
            adjust_types=["raw", "qfq"],
            max_jobs=100,
            workers=1,
            stale_after_minutes=20,
            run_timeout_seconds=1800,
            report_target="chat:test",
            report_account="jarvis",
            openclaw_bin="openclaw",
            report_dry_run=False,
            baostock_daily_request_limit=100,
            baostock_safety_multiplier=1.1,
            max_daily_backfill_requests=None,
            today_adjust_types=["raw", "qfq"],
            request_ledger_path="quota.json",
            quota_day=None,
        )
    )

    output = capsys.readouterr().out
    assert "baostock_minute_backfill_watchdog|raw_completed_through|2020-01-02" in output
    assert "baostock_minute_backfill_watchdog|raw_current_trade_date|2020-01-03" in output
    assert "baostock_minute_backfill_watchdog|raw_current_progress|150/3560|4.21" in output
    assert "baostock_minute_backfill_watchdog|raw_run_delta_current_success_jobs|50" in output


def test_run_minute_backfill_watchdog_forces_single_worker_for_baostock_budget(monkeypatch, tmp_path):
    generic_calls = []

    def fake_run_watchdog_once(**kwargs):
        generic_calls.append(kwargs)
        return {
            "scope": {"run_id": "minute-backfill:5min:raw,qfq:2024-01-01:2024-01-31", "window": "2024-01-01..2024-01-31"},
            "pre_rows": [],
            "post_rows": [],
            "pre_summary": BackfillSummary(0, 0, 0, 0, 0, 0, 0),
            "post_summary": BackfillSummary(0, 0, 0, 0, 0, 0, 0),
            "previous_frontier": {"completed_through": None, "currently_working_on": None},
            "frontier": {"completed_through": None, "currently_working_on": None},
            "status": BackfillWatchdogStatus(
                watchdog_action="healthy",
                progress_advanced=False,
                work_remaining=True,
                stale_tasks_reset=0,
                timed_out=False,
                previous_frontier={"completed_through": None, "currently_working_on": None},
                current_frontier={"completed_through": None, "currently_working_on": "2024-01"},
            ),
            "stale_tasks_reset": 0,
            "run_result": {
                "attempted": 0,
                "success": 0,
                "failed": 0,
                "rows": 0,
                "status": "completed",
                "timed_out": False,
            },
            "timed_out": False,
            "message": "backfill_watchdog|status\nrun_success=0",
        }

    monkeypatch.setattr(minute_backfill_watchdog, "run_watchdog_once", fake_run_watchdog_once)
    monkeypatch.setattr(minute_backfill_watchdog, "send_openclaw_feishu_message", lambda **kwargs: None)
    monkeypatch.setattr(minute_backfill_watchdog, "load_active_baostock_asset_count", lambda: 10)

    run_minute_backfill_watchdog(
        start_date="2024-01-01",
        end_date="2024-01-31",
        freq="5min",
        adjust_types=["raw", "qfq"],
        max_jobs=100,
        workers=8,
        enable_baostock_request_budget=True,
        baostock_daily_request_limit=100,
        baostock_safety_multiplier=1.1,
        today_adjust_types=["raw", "qfq"],
        request_ledger_path=tmp_path / "quota.json",
        quota_day=dt.date(2026, 7, 2),
        report_target="chat:test",
    )

    assert generic_calls[0]["workers"] == 1


def test_run_minute_backfill_watchdog_releases_baostock_quota_when_runner_raises(monkeypatch, tmp_path):
    def raise_from_runner(**kwargs):
        raise RuntimeError("runner failed before attempting jobs")

    ledger_path = tmp_path / "quota.json"
    quota_day = dt.date(2026, 7, 2)
    monkeypatch.setattr(minute_backfill_watchdog, "run_watchdog_once", raise_from_runner)
    monkeypatch.setattr(minute_backfill_watchdog, "load_active_baostock_asset_count", lambda: 10)

    with pytest.raises(RuntimeError, match="runner failed"):
        run_minute_backfill_watchdog(
            start_date="2024-01-01",
            end_date="2024-01-31",
            freq="5min",
            adjust_types=["raw", "qfq"],
            max_jobs=100,
            enable_baostock_request_budget=True,
            baostock_daily_request_limit=100,
            baostock_safety_multiplier=1.1,
            today_adjust_types=["raw", "qfq"],
            request_ledger_path=ledger_path,
            quota_day=quota_day,
            report_target="chat:test",
        )

    allocation = allocate_daily_backfill_quota(
        ledger_path=ledger_path,
        day=quota_day,
        backfill_request_budget=70,
        requested_requests=70,
    )
    assert allocation.allocated_requests == 70


def test_run_minute_backfill_watchdog_reuses_generic_message_when_reconciliation_is_unchanged(monkeypatch):
    sent = []
    prebuilt_message = "backfill_watchdog|status\nrun_success=0"

    monkeypatch.setattr(
        minute_backfill_watchdog,
        "run_watchdog_once",
        lambda **kwargs: {
            "scope": {"run_id": "minute-backfill:5min:raw:2024-01-01:2024-01-31", "window": "2024-01-01..2024-01-31"},
            "pre_rows": [],
            "post_rows": [],
            "pre_summary": BackfillSummary(0, 0, 0, 0, 0, 0, 0),
            "post_summary": BackfillSummary(0, 0, 0, 0, 0, 0, 0),
            "previous_frontier": {"completed_through": None, "currently_working_on": None},
            "frontier": {"completed_through": None, "currently_working_on": None},
            "status": BackfillWatchdogStatus(
                watchdog_action="healthy",
                progress_advanced=False,
                work_remaining=False,
                stale_tasks_reset=0,
                timed_out=False,
                previous_frontier={"completed_through": None, "currently_working_on": None},
                current_frontier={"completed_through": None, "currently_working_on": None},
            ),
            "stale_tasks_reset": 0,
            "run_result": {
                "attempted": 0,
                "success": 0,
                "failed": 0,
                "rows": 0,
                "status": "completed",
                "timed_out": False,
            },
            "timed_out": False,
            "message": prebuilt_message,
        },
    )
    monkeypatch.setattr(
        minute_backfill_watchdog,
        "send_openclaw_feishu_message",
        lambda **kwargs: sent.append(kwargs),
    )

    result = run_minute_backfill_watchdog(
        start_date="2024-01-01",
        end_date="2024-01-31",
        freq="5min",
        adjust_types=["raw"],
        report_target="chat:test",
    )

    assert result["message"] == prebuilt_message
    assert sent == []


def test_run_minute_backfill_watchdog_skips_feishu_when_work_is_complete_and_healthy(monkeypatch):
    sent = []

    monkeypatch.setattr(
        minute_backfill_watchdog,
        "run_watchdog_once",
        lambda **kwargs: {
            "scope": {"run_id": "minute-backfill:5min:raw:2024-01-01:2024-01-31", "window": "2024-01-01..2024-01-31"},
            "pre_rows": [],
            "post_rows": [],
            "pre_summary": BackfillSummary(1, 0, 0, 1, 0, 0, 0),
            "post_summary": BackfillSummary(1, 0, 0, 1, 0, 0, 0),
            "previous_frontier": {"completed_through": "2024-01", "currently_working_on": None},
            "frontier": {"completed_through": "2024-01", "currently_working_on": None},
            "status": BackfillWatchdogStatus(
                watchdog_action="healthy",
                progress_advanced=False,
                work_remaining=False,
                stale_tasks_reset=0,
                timed_out=False,
                previous_frontier={"completed_through": "2024-01", "currently_working_on": None},
                current_frontier={"completed_through": "2024-01", "currently_working_on": None},
            ),
            "stale_tasks_reset": 0,
            "run_result": {
                "attempted": 0,
                "success": 0,
                "failed": 0,
                "rows": 0,
                "status": "completed",
                "timed_out": False,
            },
            "timed_out": False,
            "message": "unused",
        },
    )
    monkeypatch.setattr(
        minute_backfill_watchdog,
        "send_openclaw_feishu_message",
        lambda **kwargs: sent.append(kwargs),
    )

    result = run_minute_backfill_watchdog(
        start_date="2024-01-01",
        end_date="2024-01-31",
        freq="5min",
        adjust_types=["raw"],
        report_target="chat:test",
    )

    assert result["status"]["watchdog_action"] == "healthy"
    assert result["status"]["work_remaining"] is False
    assert sent == []


def test_run_minute_backfill_watchdog_restores_legacy_summary_fields_from_rows(monkeypatch):
    sent = []
    finished_at = dt.datetime(2024, 2, 1, 9, 1)
    failed_at = dt.datetime(2024, 2, 1, 9, 2)

    monkeypatch.setattr(
        minute_backfill_watchdog,
        "run_watchdog_once",
        lambda **kwargs: {
            "scope": {"run_id": "minute-backfill:5min:raw:2024-01-01:2024-01-31", "window": "2024-01-01..2024-01-31"},
            "pre_rows": [
                {
                    "job_id": "job1",
                    "ts_code": "600000.SH",
                    "start_date": dt.date(2024, 1, 1),
                    "end_date": dt.date(2024, 1, 31),
                    "status": "failed",
                    "row_count_market": 0,
                    "row_count_staging": 12,
                    "finished_at": failed_at,
                    "last_error": "boom",
                }
            ],
            "post_rows": [
                {
                    "job_id": "job1",
                    "ts_code": "600000.SH",
                    "start_date": dt.date(2024, 1, 1),
                    "end_date": dt.date(2024, 1, 31),
                    "status": "success",
                    "row_count_market": 240,
                    "row_count_staging": 240,
                    "finished_at": finished_at,
                    "last_error": None,
                }
            ],
            "pre_summary": BackfillSummary(1, 0, 0, 0, 1, 0, 0),
            "post_summary": BackfillSummary(1, 0, 0, 1, 0, 0, 240),
            "previous_frontier": {"completed_through": None, "currently_working_on": "2024-01"},
            "frontier": {"completed_through": "2024-01", "currently_working_on": None},
            "status": BackfillWatchdogStatus(
                watchdog_action="healthy",
                progress_advanced=True,
                work_remaining=False,
                stale_tasks_reset=0,
                timed_out=False,
                previous_frontier={"completed_through": None, "currently_working_on": "2024-01"},
                current_frontier={"completed_through": "2024-01", "currently_working_on": None},
            ),
            "stale_tasks_reset": 0,
            "run_result": {
                "attempted": 1,
                "success": 1,
                "failed": 0,
                "rows": 240,
                "status": "completed",
                "timed_out": False,
            },
            "timed_out": False,
            "message": "backfill_watchdog|status\naction=restarted",
        },
    )
    monkeypatch.setattr(
        minute_backfill_watchdog,
        "send_openclaw_feishu_message",
        lambda **kwargs: sent.append(kwargs),
    )

    result = run_minute_backfill_watchdog(
        start_date="2024-01-01",
        end_date="2024-01-31",
        freq="5min",
        adjust_types=["raw"],
        report_target="chat:test",
    )

    assert result["pre_summary"]["total_staging_rows"] == 12
    assert result["pre_summary"]["latest_failed_at"] == failed_at
    assert result["pre_summary"]["failed_examples"] == [
        {
            "job_id": "job1",
            "ts_code": "600000.SH",
            "period": "2024-01-01:2024-01-31",
            "error": "boom",
        }
    ]
    assert result["post_summary"]["total_staging_rows"] == 240
    assert result["post_summary"]["latest_success_at"] == finished_at


def test_run_minute_backfill_watchdog_reconciles_timeout_in_legacy_result(monkeypatch):
    sent = []

    monkeypatch.setattr(
        minute_backfill_watchdog,
        "run_watchdog_once",
        lambda **kwargs: {
            "scope": {"run_id": "minute-backfill:5min:raw:2024-01-01:2024-02-29", "window": "2024-01-01..2024-02-29"},
            "pre_rows": [],
            "post_rows": [],
            "pre_summary": BackfillSummary(2, 1, 1, 0, 0, 0, 0),
            "post_summary": BackfillSummary(2, 0, 0, 1, 0, 0, 0),
            "previous_frontier": {"completed_through": "2024-01", "currently_working_on": "2024-02"},
            "frontier": {"completed_through": "2024-02", "currently_working_on": None},
            "status": BackfillWatchdogStatus(
                watchdog_action="restarted",
                progress_advanced=True,
                work_remaining=False,
                stale_tasks_reset=1,
                timed_out=True,
                previous_frontier={"completed_through": "2024-01", "currently_working_on": "2024-02"},
                current_frontier={"completed_through": "2024-02", "currently_working_on": None},
            ),
            "stale_tasks_reset": 1,
            "run_result": {
                "attempted": 0,
                "success": 0,
                "failed": 0,
                "rows": 0,
                "status": "timed_out",
                "timed_out": True,
            },
            "timed_out": True,
            "message": "unused",
        },
    )
    monkeypatch.setattr(
        minute_backfill_watchdog,
        "send_openclaw_feishu_message",
        lambda **kwargs: sent.append(kwargs),
    )

    result = run_minute_backfill_watchdog(
        start_date="2024-01-01",
        end_date="2024-02-29",
        freq="5min",
        adjust_types=["raw"],
        report_target="chat:test",
    )

    assert result["run_result"] == {
        "attempted": 1,
        "success": 1,
        "failed": 0,
        "rows": 0,
        "status": "timed_out",
        "timed_out": True,
    }
    assert result["timed_out"] is True
    assert result["status"]["watchdog_action"] == "restarted"
    assert "本轮: timed_out，尝试 1，成功 1，失败 0，新增行 0" in sent[0]["message"]


def test_run_minute_backfill_watchdog_resets_stale_jobs_and_restarts_backfill(monkeypatch):
    sent = []

    monkeypatch.setattr(
        minute_backfill_watchdog,
        "run_watchdog_once",
        lambda **kwargs: {
            "scope": {"run_id": "minute-backfill:5min:raw:2024-01-01:2024-02-29", "window": "2024-01-01..2024-02-29"},
            "pre_rows": [_row(dt.date(2024, 1, 1), dt.date(2024, 1, 31), "success")],
            "post_rows": [
                _row(dt.date(2024, 1, 1), dt.date(2024, 1, 31), "success"),
                _row(dt.date(2024, 2, 1), dt.date(2024, 2, 29), "success"),
            ],
            "pre_summary": BackfillSummary(2, 0, 1, 1, 0, 0, 0),
            "post_summary": BackfillSummary(2, 0, 0, 2, 0, 0, 240),
            "previous_frontier": {"completed_through": "2024-01", "currently_working_on": "2024-02"},
            "frontier": {"completed_through": "2024-02", "currently_working_on": None},
            "status": BackfillWatchdogStatus(
                watchdog_action="restarted",
                progress_advanced=True,
                work_remaining=False,
                stale_tasks_reset=1,
                timed_out=False,
                previous_frontier={"completed_through": "2024-01", "currently_working_on": "2024-02"},
                current_frontier={"completed_through": "2024-02", "currently_working_on": None},
            ),
            "stale_tasks_reset": 1,
            "run_result": {
                "attempted": 1,
                "success": 1,
                "failed": 0,
                "rows": 240,
                "status": "completed",
                "timed_out": False,
            },
            "timed_out": False,
            "message": "backfill_watchdog|status\naction=restarted",
        },
    )
    monkeypatch.setattr(
        minute_backfill_watchdog,
        "send_openclaw_feishu_message",
        lambda **kwargs: sent.append(kwargs),
    )

    result = run_minute_backfill_watchdog(
        start_date="2024-01-01",
        end_date="2024-02-29",
        freq="5min",
        adjust_types=["raw"],
        report_target="chat:test",
    )

    assert result["stale_jobs_reset"] == 1
    assert result["timed_out"] is False
    assert result["run_result"]["status"] == "completed"
    assert result["status"]["watchdog_action"] == "restarted"
    assert result["status"]["frontier"]["completed_through"] == "2024-02"
    assert sent[0]["target"] == "chat:test"
    assert sent[0]["message"] == "backfill_watchdog|status\naction=restarted"


def test_run_minute_backfill_watchdog_marks_timeout(monkeypatch):
    sent = []

    monkeypatch.setattr(
        minute_backfill_watchdog,
        "run_watchdog_once",
        lambda **kwargs: {
            "scope": {"run_id": "minute-backfill:5min:raw:2024-01-01:2024-02-29", "window": "2024-01-01..2024-02-29"},
            "pre_rows": [],
            "post_rows": [],
            "pre_summary": BackfillSummary(2, 1, 0, 1, 0, 0, 0),
            "post_summary": BackfillSummary(2, 0, 0, 2, 0, 0, 0),
            "previous_frontier": {"completed_through": "2024-01-31", "currently_working_on": "2024-02-01"},
            "frontier": {"completed_through": "2024-02-29", "currently_working_on": None},
            "status": BackfillWatchdogStatus(
                watchdog_action="restarted",
                progress_advanced=True,
                work_remaining=False,
                stale_tasks_reset=1,
                timed_out=True,
                previous_frontier={"completed_through": "2024-01-31", "currently_working_on": "2024-02-01"},
                current_frontier={"completed_through": "2024-02-29", "currently_working_on": None},
            ),
            "stale_tasks_reset": 1,
            "run_result": {
                "attempted": 0,
                "success": 0,
                "failed": 0,
                "rows": 0,
                "status": "timed_out",
                "timed_out": True,
            },
            "timed_out": True,
            "message": "unused",
        },
    )
    monkeypatch.setattr(
        minute_backfill_watchdog,
        "send_openclaw_feishu_message",
        lambda **kwargs: sent.append(kwargs),
    )

    result = run_minute_backfill_watchdog(
        start_date="2024-01-01",
        end_date="2024-02-29",
        freq="5min",
        adjust_types=["raw"],
        report_target="chat:test",
        run_timeout_seconds=5,
    )

    assert result["timed_out"] is True
    assert result["run_result"]["status"] == "timed_out"
    assert result["run_result"]["attempted"] == 1
    assert result["run_result"]["success"] == 1
    assert result["run_result"]["failed"] == 0
    assert result["run_result"]["rows"] == 0
    assert result["status"]["watchdog_action"] == "restarted"
    assert "本轮: timed_out，尝试 1，成功 1，失败 0，新增行 0" in sent[0]["message"]


@pytest.mark.parametrize(
    ("report_dry_run", "expected_dry_run"),
    [
        (False, False),
        (True, True),
    ],
)
def test_run_minute_backfill_watchdog_feishu_send_respects_dry_run(
    monkeypatch,
    report_dry_run,
    expected_dry_run,
):
    sent = []

    monkeypatch.setattr(
        minute_backfill_watchdog,
        "run_watchdog_once",
        lambda **kwargs: {
            "scope": {"run_id": "minute-backfill:5min:raw:2024-01-01:2024-01-31", "window": "2024-01-01..2024-01-31"},
            "pre_rows": [],
            "post_rows": [],
            "pre_summary": BackfillSummary(1, 0, 0, 1, 0, 0, 0),
            "post_summary": BackfillSummary(1, 0, 0, 1, 0, 0, 0),
            "previous_frontier": {"completed_through": "2024-01", "currently_working_on": None},
            "frontier": {"completed_through": "2024-01", "currently_working_on": None},
            "status": BackfillWatchdogStatus(
                watchdog_action="healthy",
                progress_advanced=False,
                work_remaining=False,
                stale_tasks_reset=0,
                timed_out=False,
                previous_frontier={"completed_through": "2024-01", "currently_working_on": None},
                current_frontier={"completed_through": "2024-01", "currently_working_on": None},
            ),
            "stale_tasks_reset": 0,
            "run_result": {
                "attempted": 0,
                "success": 0,
                "failed": 0,
                "rows": 0,
                "status": "completed",
                "timed_out": False,
            },
            "timed_out": False,
            "message": "unused",
        },
    )
    monkeypatch.setattr(
        minute_backfill_watchdog,
        "send_openclaw_feishu_message",
        lambda **kwargs: sent.append(kwargs),
    )

    run_minute_backfill_watchdog(
        start_date="2024-01-01",
        end_date="2024-01-31",
        freq="5min",
        adjust_types=["raw"],
        report_target="chat:test",
        report_dry_run=report_dry_run,
    )

    assert sent == []


def test_run_backfill_once_with_timeout_returns_promptly(monkeypatch, tmp_path):
    completed = threading.Event()

    def fake_run_baostock_minute_backfill(**kwargs):
        time.sleep(0.2)
        completed.set()
        return {
            "attempted": 3,
            "success": 2,
            "failed": 1,
            "rows": 480,
        }

    monkeypatch.setattr(
        "stock_research.minute_backfill_adapter.run_baostock_minute_backfill",
        fake_run_baostock_minute_backfill,
    )

    started = time.monotonic()
    result = _run_backfill_once_with_timeout(
        start_date="2024-01-01",
        end_date="2024-01-31",
        freq="5min",
        adjust_types=["raw"],
        batch_by="month",
        max_jobs=100,
        retry_failed=True,
        sleep_seconds=0.0,
        workers=2,
        run_timeout_seconds=0.01,
        lock_path=tmp_path / "minute-backfill-watchdog.lock",
    )
    elapsed = time.monotonic() - started

    assert result["timed_out"] is True
    assert result["status"] == "timed_out"
    assert elapsed < 0.1
    assert completed.is_set() is False


def test_run_backfill_once_with_timeout_returns_completed_result(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "stock_research.minute_backfill_adapter.run_baostock_minute_backfill",
        lambda **kwargs: {
            "attempted": 3,
            "success": 2,
            "failed": 1,
            "rows": 480,
        },
    )

    result = _run_backfill_once_with_timeout(
        start_date="2024-01-01",
        end_date="2024-01-31",
        freq="5min",
        adjust_types=["raw"],
        batch_by="month",
        max_jobs=100,
        retry_failed=True,
        sleep_seconds=0.0,
        workers=2,
        run_timeout_seconds=5,
        lock_path=tmp_path / "minute-backfill-watchdog.lock",
    )

    assert result == {
        "attempted": 3,
        "success": 2,
        "failed": 1,
        "rows": 480,
        "status": "completed",
        "timed_out": False,
    }


def test_cron_jobs_include_minute_backfill_watchdog():
    jobs = json.loads(Path("/Users/xiwei/.openclaw/cron/jobs.json").read_text())["jobs"]
    job = next((item for item in jobs if item["name"] == "minute-backfill-watchdog"), None)

    assert job is not None
    assert isinstance(job["enabled"], bool)
    assert job["agentId"] == "agent_jarvis"
    assert job["schedule"] == {
        "kind": "cron",
        "expr": "*/10 * * * *",
        "tz": "Asia/Shanghai",
    }
    assert job["delivery"] == {"mode": "none"}
    assert job["failureAlert"] == {
        "after": 1,
        "channel": "feishu",
        "to": "chat:oc_82dd978138a0cde5864868c5b5b8e754",
        "cooldownMs": 7200000,
        "mode": "announce",
        "accountId": "jarvis",
    }
    assert job["payload"]["kind"] == "agentTurn"
    assert job["payload"]["toolsAllow"] == ["exec"]
    assert job["payload"]["timeoutSeconds"] == 2100
    assert "/Users/xiwei/stock_research/scripts/run_minute_backfill_watchdog_host.sh" in job["payload"]["message"]
    assert "cd /Users/xiwei/stock_research &&" not in job["payload"]["message"]
    assert "stock_research.cli backfill-watchdog" not in job["payload"]["message"]
    assert "/approval" not in job["payload"]["message"]
    assert "approval" not in job["payload"]["message"].lower()

    approvals = json.loads(Path("/Users/xiwei/.openclaw/exec-approvals.json").read_text())
    jarvis_allowlist = approvals["agents"]["agent_jarvis"]["allowlist"]
    assert any(
        item["pattern"] == "/Users/xiwei/stock_research/scripts/run_minute_backfill_watchdog_host.sh"
        for item in jarvis_allowlist
    )


def test_cron_jobs_include_stock_close_and_ready_jobs():
    jobs = json.loads(Path("/Users/xiwei/.openclaw/cron/jobs.json").read_text())["jobs"]
    minute_job = next(
        (item for item in jobs if item["name"] == "stock-daily-close-minute5-split"),
        None,
    )
    build_job = next(
        (item for item in jobs if item["name"] == "stock-platform-ready-build"),
        None,
    )
    check_job = next(
        (item for item in jobs if item["name"] == "stock-platform-ready-check"),
        None,
    )

    assert minute_job is not None
    assert minute_job["enabled"] is True
    assert minute_job["agentId"] == "agent_jarvis"
    assert minute_job["schedule"] == {
        "kind": "cron",
        "expr": "0 17 * * 1-5",
        "tz": "Asia/Shanghai",
        "staggerMs": 0,
    }
    assert minute_job["payload"]["timeoutSeconds"] == 5400
    assert (
        "/Users/xiwei/stock_research/scripts/run_daily_close_pipeline_cron.sh minute5"
        in minute_job["payload"]["message"]
    )

    assert build_job is not None
    assert build_job["enabled"] is True
    assert build_job["schedule"] == {
        "kind": "cron",
        "expr": "0 19 * * 1-5",
        "tz": "Asia/Shanghai",
        "staggerMs": 0,
    }
    assert build_job["payload"]["timeoutSeconds"] == 5400

    assert check_job is not None
    assert check_job["enabled"] is True
    assert check_job["schedule"] == {
        "kind": "cron",
        "expr": "55 19 * * 1-5",
        "tz": "Asia/Shanghai",
        "staggerMs": 0,
    }
    assert check_job["payload"]["timeoutSeconds"] == 1200
