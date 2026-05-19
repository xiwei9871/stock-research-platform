import json
import os
from pathlib import Path
import stat
import subprocess
import xml.etree.ElementTree as ET

import pandas as pd

from stock_research.backfill_watchdog import BackfillSummary
from stock_research import technical_feature_watchdog
from stock_research.technical_feature_watchdog import TechnicalFeatureBackfillAdapter


def test_technical_feature_adapter_status_and_frontier(monkeypatch):
    monkeypatch.setattr(
        technical_feature_watchdog,
        "load_trade_dates_for_backfill",
        lambda **kwargs: ["1991-01-02", "1991-01-03", "1991-01-04"],
    )
    monkeypatch.setattr(
        technical_feature_watchdog,
        "load_complete_technical_feature_dates",
        lambda **kwargs: {"1991-01-02"},
    )
    monkeypatch.setattr(
        technical_feature_watchdog,
        "_load_technical_feature_row_counts",
        lambda **kwargs: {"1991-01-02": 100},
    )

    adapter = TechnicalFeatureBackfillAdapter(
        start_date="1991-01-01",
        end_date="2026-05-14",
    )
    rows = adapter.load_status_rows()

    assert rows == [
        {"trade_date": "1991-01-02", "status": "success", "row_count": 100},
        {"trade_date": "1991-01-03", "status": "pending", "row_count": 0},
        {"trade_date": "1991-01-04", "status": "pending", "row_count": 0},
    ]
    assert adapter.summarize_status(rows) == BackfillSummary(
        total_tasks=3,
        pending_tasks=2,
        running_tasks=0,
        success_tasks=1,
        failed_tasks=0,
        skipped_tasks=0,
        total_rows_written=100,
    )
    assert adapter.compute_frontier(rows) == {
        "completed_through": "1991-01-02",
        "currently_working_on": "1991-01-03",
    }


def test_technical_feature_adapter_run_once_uses_next_pending_batch(monkeypatch):
    adapter = TechnicalFeatureBackfillAdapter(
        start_date="1991-01-01",
        end_date="2026-05-14",
        adjust_type="qfq",
        source_data_version="market_daily_bar:qfq",
    )
    monkeypatch.setattr(
        TechnicalFeatureBackfillAdapter,
        "load_status_rows",
        lambda self: [
            {"trade_date": "1991-01-02", "status": "success", "row_count": 100},
            {"trade_date": "1991-01-03", "status": "pending", "row_count": 0},
            {"trade_date": "1991-01-04", "status": "pending", "row_count": 0},
            {"trade_date": "1991-01-07", "status": "pending", "row_count": 0},
        ],
    )
    calls = []

    class FakeFrame:
        empty = False

        def __len__(self):
            return 2

        def __getitem__(self, key):
            assert key == "feature_rows"
            return self

        def sum(self):
            return 250

    monkeypatch.setattr(
        technical_feature_watchdog,
        "backfill_technical_features_daily_range",
        lambda **kwargs: calls.append(kwargs) or FakeFrame(),
    )

    result = adapter.run_once(
        scope=adapter.load_scope(),
        max_jobs=2,
        workers=2,
        run_timeout_seconds=1800,
    )

    assert calls == [
        {
            "start_date": "1991-01-03",
            "end_date": "1991-01-04",
            "lookback_bars": 260,
            "adjust_type": "qfq",
            "source_data_version": "market_daily_bar:qfq",
            "trading_days_only": True,
            "workers": 2,
            "skip_complete": True,
            "run_timeout_seconds": 1800,
        }
    ]
    assert result["attempted"] == 2
    assert result["success"] == 2
    assert result["failed"] == 0
    assert result["rows"] == 250
    assert result["status"] == "completed"
    assert result["timed_out"] is False
    assert result["batch_size_days"] == 2
    assert result["worker_count"] == 2


def test_technical_feature_adapter_run_once_passes_timeout_and_exposes_batch_metrics(
    monkeypatch,
):
    adapter = TechnicalFeatureBackfillAdapter(
        start_date="1991-01-01",
        end_date="2026-05-14",
        adjust_type="qfq",
        source_data_version="market_daily_bar:qfq",
    )
    monkeypatch.setattr(
        TechnicalFeatureBackfillAdapter,
        "load_status_rows",
        lambda self: [
            {"trade_date": "1991-01-03", "status": "pending", "row_count": 0},
            {"trade_date": "1991-01-04", "status": "pending", "row_count": 0},
        ],
    )
    calls = []

    def fake_backfill(**kwargs):
        calls.append(kwargs)
        frame = pd.DataFrame(
            [
                {"trade_date": "1991-01-03", "feature_rows": 120},
                {"trade_date": "1991-01-04", "feature_rows": 130},
            ]
        )
        frame.attrs.update(
            {
                "timed_out": True,
                "batch_start_date": "1991-01-03",
                "batch_end_date": "1991-01-04",
                "batch_size_days": 2,
                "worker_count": 3,
                "compute_seconds": 90.0,
                "rows_written": 250,
                "days_per_hour": 80.0,
                "rows_per_hour": 10000.0,
            }
        )
        return frame

    monkeypatch.setattr(
        technical_feature_watchdog,
        "backfill_technical_features_daily_range",
        fake_backfill,
    )

    result = adapter.run_once(
        scope=adapter.load_scope(),
        max_jobs=2,
        workers=3,
        run_timeout_seconds=1200,
    )

    assert calls == [
        {
            "start_date": "1991-01-03",
            "end_date": "1991-01-04",
            "lookback_bars": 260,
            "adjust_type": "qfq",
            "source_data_version": "market_daily_bar:qfq",
            "trading_days_only": True,
            "workers": 3,
            "skip_complete": True,
            "run_timeout_seconds": 1200,
        }
    ]
    assert result["timed_out"] is True
    assert result["batch_start_date"] == "1991-01-03"
    assert result["batch_end_date"] == "1991-01-04"
    assert result["batch_size_days"] == 2
    assert result["worker_count"] == 3
    assert result["compute_seconds"] == 90.0
    assert result["rows_per_hour"] == 10000.0

    lines = adapter.format_extra_status_lines(
        rows=[],
        summary=BackfillSummary(2, 0, 0, 2, 0, 0, 250),
        scope=adapter.load_scope(),
        run_result=result,
        status=None,
    )
    assert "batch_start_date=1991-01-03" in lines
    assert "batch_end_date=1991-01-04" in lines
    assert "batch_size_days=2" in lines
    assert "worker_count=3" in lines
    assert "compute_seconds=90.0" in lines
    assert "sleep_between_runs_seconds=0.0" in lines
    assert "rows_written=250" in lines
    assert "days_per_hour=80.0" in lines
    assert "rows_per_hour=10000.0" in lines


def test_run_technical_feature_backfill_watchdog_respects_sleep_between_runs_seconds(
    monkeypatch,
):
    sleep_calls = []
    send_calls = []

    monkeypatch.setattr(
        technical_feature_watchdog,
        "run_watchdog_once",
        lambda **kwargs: {
            "message": "watchdog message",
            "status": object(),
            "pre_summary": object(),
            "post_summary": object(),
            "run_result": {},
        },
    )
    monkeypatch.setattr(
        technical_feature_watchdog,
        "send_openclaw_feishu_message",
        lambda **kwargs: send_calls.append(kwargs),
    )

    result = technical_feature_watchdog.run_technical_feature_backfill_watchdog(
        start_date="1991-01-01",
        end_date="2026-05-14",
        report_target="chat:test",
        report_dry_run=True,
        sleep_between_runs_seconds=12.5,
        sleep=sleep_calls.append,
    )

    assert result["message"] == "watchdog message"
    assert send_calls[0]["message"] == "watchdog message"
    assert sleep_calls == [12.5]


def test_cron_jobs_include_technical_feature_backfill_watchdog():
    jobs = json.loads(Path("/Users/xiwei/.openclaw/cron/jobs.json").read_text())["jobs"]
    job = next(
        (item for item in jobs if item["name"] == "technical-feature-backfill-watchdog"),
        None,
    )

    assert job is not None
    assert job["agentId"] == "agent_jarvis"
    assert isinstance(job["enabled"], bool)
    assert job["schedule"] == {
        "kind": "cron",
        "expr": "*/30 * * * *",
        "tz": "Asia/Shanghai",
    }
    assert job["payload"]["kind"] == "agentTurn"
    assert job["payload"]["toolsAllow"] == ["exec"]
    assert job["payload"]["timeoutSeconds"] == 2100
    assert "/Users/xiwei/stock_research/scripts/run_technical_feature_backfill_watchdog_host.sh" in job["payload"]["message"]
    assert "cd /Users/xiwei/stock_research &&" not in job["payload"]["message"]
    assert "stock_research.cli backfill-watchdog" not in job["payload"]["message"]
    assert "/approval" not in job["payload"]["message"]
    assert "approval" not in job["payload"]["message"].lower()

    approvals = json.loads(Path("/Users/xiwei/.openclaw/exec-approvals.json").read_text())
    jarvis_allowlist = approvals["agents"]["agent_jarvis"]["allowlist"]
    assert any(
        item["pattern"]
        == "/Users/xiwei/stock_research/scripts/run_technical_feature_backfill_watchdog_host.sh"
        for item in jarvis_allowlist
    )


def test_launchd_plist_uses_60_second_start_interval_and_exports_value():
    plist_path = Path(
        "/Users/xiwei/stock_research/deploy/launchd/com.stockresearch.technical-feature-backfill-watchdog.plist"
    )
    root = ET.fromstring(plist_path.read_text())
    entries = list(root.find("dict"))
    start_interval = None
    env_values: dict[str, str] = {}
    for index, node in enumerate(entries):
        if node.tag == "key" and node.text == "StartInterval":
            start_interval = int(entries[index + 1].text)
        if node.tag == "key" and node.text == "EnvironmentVariables":
            env_dict = entries[index + 1]
            env_entries = list(env_dict)
            for env_index, env_node in enumerate(env_entries):
                if env_node.tag == "key":
                    env_values[str(env_node.text)] = str(env_entries[env_index + 1].text)

    assert start_interval == 60
    assert env_values["TECHNICAL_FEATURE_WATCHDOG_START_INTERVAL_SECONDS"] == "60"


def test_host_script_skips_when_lock_exists(tmp_path):
    run_log = tmp_path / "technical_feature_backfill_watchdog.host.log"
    invoke_log = tmp_path / "python_invoked.log"
    lock_dir = tmp_path / "technical-feature-watchdog.lock"
    lock_dir.mkdir()
    fake_python = _write_fake_python(tmp_path)

    result = subprocess.run(
        [
            "bash",
            "/Users/xiwei/stock_research/scripts/run_technical_feature_backfill_watchdog_host.sh",
        ],
        check=False,
        env=_host_script_env(
            tmp_path=tmp_path,
            fake_python=fake_python,
            run_log=run_log,
            invoke_log=invoke_log,
            lock_dir=lock_dir,
        ),
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert not invoke_log.exists()
    contents = run_log.read_text()
    assert f"lock_path={lock_dir}" in contents
    assert "whether_lock_acquired=false" in contents
    assert "skipped because another technical-feature watchdog is running" in contents


def test_host_script_releases_lock_after_run(tmp_path):
    run_log = tmp_path / "technical_feature_backfill_watchdog.host.log"
    invoke_log = tmp_path / "python_invoked.log"
    lock_dir = tmp_path / "technical-feature-watchdog.lock"
    fake_python = _write_fake_python(tmp_path)

    result = subprocess.run(
        [
            "bash",
            "/Users/xiwei/stock_research/scripts/run_technical_feature_backfill_watchdog_host.sh",
        ],
        check=False,
        env=_host_script_env(
            tmp_path=tmp_path,
            fake_python=fake_python,
            run_log=run_log,
            invoke_log=invoke_log,
            lock_dir=lock_dir,
        ),
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert not lock_dir.exists()
    assert invoke_log.read_text().strip() != ""
    contents = run_log.read_text()
    assert f"lock_path={lock_dir}" in contents
    assert "whether_lock_acquired=true" in contents
    assert "start_interval_seconds=300" in contents
    assert "sleep_between_runs_seconds=0" in contents
    assert "--workers 5" in invoke_log.read_text()


def _write_fake_python(tmp_path: Path) -> Path:
    fake_python = tmp_path / "fake_python.sh"
    fake_python.write_text(
        "#!/usr/bin/env bash\n"
        "printf '%s\\n' \"$*\" >> \"$TECHNICAL_FEATURE_TEST_INVOKE_LOG\"\n"
        "exit 0\n"
    )
    fake_python.chmod(fake_python.stat().st_mode | stat.S_IXUSR)
    return fake_python


def _host_script_env(
    *,
    tmp_path: Path,
    fake_python: Path,
    run_log: Path,
    invoke_log: Path,
    lock_dir: Path,
) -> dict[str, str]:
    root = tmp_path / "root"
    logs_dir = tmp_path / "logs"
    root.mkdir(exist_ok=True)
    logs_dir.mkdir(exist_ok=True)
    env = os.environ.copy()
    env.update(
        {
            "TECHNICAL_FEATURE_WATCHDOG_ROOT": str(root),
            "TECHNICAL_FEATURE_WATCHDOG_PYTHON": str(fake_python),
            "TECHNICAL_FEATURE_WATCHDOG_OPENCLAW_BIN": "/tmp/fake_openclaw",
            "TECHNICAL_FEATURE_WATCHDOG_LOG_DIR": str(logs_dir),
            "TECHNICAL_FEATURE_WATCHDOG_RUN_LOG": str(run_log),
            "TECHNICAL_FEATURE_WATCHDOG_LOCK_DIR": str(lock_dir),
            "TECHNICAL_FEATURE_WATCHDOG_START_INTERVAL_SECONDS": "300",
            "TECHNICAL_FEATURE_WATCHDOG_SLEEP_BETWEEN_RUNS_SECONDS": "0",
            "TECHNICAL_FEATURE_TEST_INVOKE_LOG": str(invoke_log),
        }
    )
    return env
