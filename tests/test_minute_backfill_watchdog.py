import datetime as dt
import json
import threading
import time
from pathlib import Path

import pytest

from stock_research.backfill_watchdog import BackfillSummary, BackfillWatchdogStatus
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
    assert generic_calls[0]["workers"] == 6
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


def test_cron_jobs_include_stock_daily_data_pipeline():
    jobs = json.loads(Path("/Users/xiwei/.openclaw/cron/jobs.json").read_text())["jobs"]
    job = next((item for item in jobs if item["name"] == "stock-daily-data-pipeline"), None)

    assert job is not None
    assert job["enabled"] is True
    assert job["agentId"] == "agent_jarvis"
    assert job["schedule"] == {
        "kind": "cron",
        "expr": "10 21 * * 1-5",
        "tz": "Asia/Shanghai",
    }
    assert job["delivery"] == {"mode": "none"}
    assert job["failureAlert"]["channel"] == "feishu"
    assert job["payload"]["kind"] == "agentTurn"
    assert job["payload"]["toolsAllow"] == ["exec"]
    assert job["payload"]["timeoutSeconds"] == 7200
    assert "/Users/xiwei/stock_research/scripts/run_stock_daily_data_pipeline.sh" in job["payload"]["message"]
    assert "/approval" not in job["payload"]["message"]
    assert "不要申请 approval" in job["payload"]["message"]
    assert job["payload"]["message"].lower().count("approval") == 1
    assert "飞书进度报告由脚本自己发送" in job["payload"]["message"]
    assert job["sessionTarget"] == "isolated"
