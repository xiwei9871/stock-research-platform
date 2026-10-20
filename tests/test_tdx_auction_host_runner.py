from pathlib import Path
import os
import stat
import subprocess


def test_tdx_host_runner_and_launchd_job_are_present():
    script = Path("/Users/xiwei/stock_research/scripts/run_tdx_auction_backfill_watchdog_host.sh")
    plist = Path("/Users/xiwei/stock_research/deploy/launchd/com.stockresearch.tdx-auction-backfill-watchdog.plist")

    assert script.exists()
    assert plist.exists()
    assert "tdx-auction-backfill-watchdog" in script.read_text()
    assert "StartCalendarInterval" in plist.read_text()


def test_tdx_launchd_uses_daily_mode_with_bounded_post_close_retries():
    plist = Path("/Users/xiwei/stock_research/deploy/launchd/com.stockresearch.tdx-auction-backfill-watchdog.plist")
    text = plist.read_text()

    assert "<key>TDX_AUCTION_WATCHDOG_MODE</key>" in text
    assert "<string>daily</string>" in text
    assert "StartInterval" not in text
    # bounded retries after close (measured TDX availability ~16:40)
    assert text.count("<key>Hour</key>") == 3


def test_tdx_host_runner_daily_mode_passes_daily_flag_and_rotating_sentinel(tmp_path):
    script = Path("/Users/xiwei/stock_research/scripts/run_tdx_auction_backfill_watchdog_host.sh")
    fake_python = tmp_path / "fake_python.sh"
    fake_python.write_text(
        "#!/usr/bin/env bash\n"
        "if [ \"$1\" = \"-c\" ]; then printf '2026-10-20\\n'; exit 0; fi\n"
        "printf '%s\\n' \"$*\" >> \"$TDX_TEST_INVOKE_LOG\"\n"
        "printf '%s\\n' 'tdx_auction_watchdog|action|healthy'\n"
        "printf '%s\\n' 'tdx_auction_watchdog|work_remaining|False'\n"
    )
    fake_python.chmod(fake_python.stat().st_mode | stat.S_IXUSR)
    invoke_log = tmp_path / "invoke.log"
    sentinel = tmp_path / "done"
    env = os.environ.copy()
    env.update(
        {
            "TDX_AUCTION_WATCHDOG_ROOT": "/Users/xiwei/stock_research",
            "TDX_AUCTION_WATCHDOG_PYTHON": str(fake_python),
            "TDX_AUCTION_WATCHDOG_LOG_DIR": str(tmp_path / "logs"),
            "TDX_AUCTION_WATCHDOG_RUN_LOG": str(tmp_path / "run.log"),
            "TDX_AUCTION_WATCHDOG_LOCK_DIR": str(tmp_path / "lock"),
            "TDX_AUCTION_WATCHDOG_COMPLETION_SENTINEL": str(sentinel),
            "TDX_AUCTION_WATCHDOG_MODE": "daily",
            "TDX_AUCTION_WATCHDOG_REPORT_DRY_RUN": "1",
            "TDX_TEST_INVOKE_LOG": str(invoke_log),
        }
    )

    result = subprocess.run(["bash", str(script)], check=False, env=env,
                            capture_output=True, text=True)

    assert result.returncode == 0
    invoked = invoke_log.read_text()
    assert "--daily" in invoked
    assert "--start-date" not in invoked
    assert sentinel.read_text().strip() == "tdx-auction-daily|2026-10-20|coverage0.98"

    # second trigger same day: sentinel current → exits before invoking python
    invoke_log.unlink()
    result = subprocess.run(["bash", str(script)], check=False, env=env,
                            capture_output=True, text=True)
    assert result.returncode == 0
    assert not invoke_log.exists()


def test_tdx_host_runner_partial_coverage_blocks_completion_sentinel(tmp_path):
    script = Path("/Users/xiwei/stock_research/scripts/run_tdx_auction_backfill_watchdog_host.sh")
    fake_python = tmp_path / "fake_python.sh"
    fake_python.write_text(
        "#!/usr/bin/env bash\n"
        "if [ \"$1\" = \"-c\" ]; then printf '2026-10-20\\n'; exit 0; fi\n"
        "printf '%s\\n' 'tdx_auction_watchdog|action|degraded'\n"
        "printf '%s\\n' 'tdx_auction_watchdog|run_partial|1'\n"
        "printf '%s\\n' 'tdx_auction_watchdog|work_remaining|True'\n"
    )
    fake_python.chmod(fake_python.stat().st_mode | stat.S_IXUSR)
    sentinel = tmp_path / "done"
    env = os.environ.copy()
    env.update(
        {
            "TDX_AUCTION_WATCHDOG_ROOT": "/Users/xiwei/stock_research",
            "TDX_AUCTION_WATCHDOG_PYTHON": str(fake_python),
            "TDX_AUCTION_WATCHDOG_LOG_DIR": str(tmp_path / "logs"),
            "TDX_AUCTION_WATCHDOG_RUN_LOG": str(tmp_path / "run.log"),
            "TDX_AUCTION_WATCHDOG_LOCK_DIR": str(tmp_path / "lock"),
            "TDX_AUCTION_WATCHDOG_COMPLETION_SENTINEL": str(sentinel),
            "TDX_AUCTION_WATCHDOG_MODE": "daily",
            "TDX_AUCTION_WATCHDOG_REPORT_DRY_RUN": "1",
        }
    )

    result = subprocess.run(["bash", str(script)], check=False, env=env,
                            capture_output=True, text=True)

    assert result.returncode == 0
    assert not sentinel.exists()


def test_tdx_host_runner_uses_a_small_failover_pool_by_default():
    script = Path("/Users/xiwei/stock_research/scripts/run_tdx_auction_backfill_watchdog_host.sh")

    assert (
        'TDX_HOSTS="${TDX_AUCTION_WATCHDOG_HOSTS:-'
        '116.205.183.150:7709,116.205.171.132:7709,111.230.186.52:7709,129.204.230.128:7709}"'
    ) in script.read_text()


def test_tdx_host_runner_uses_all_four_failover_servers_by_default():
    script = Path("/Users/xiwei/stock_research/scripts/run_tdx_auction_backfill_watchdog_host.sh")
    plist = Path("/Users/xiwei/stock_research/deploy/launchd/com.stockresearch.tdx-auction-backfill-watchdog.plist")

    assert 'TDX_SERVER_COUNT="${TDX_AUCTION_WATCHDOG_SERVER_COUNT:-4}"' in script.read_text()
    assert "<key>TDX_AUCTION_WATCHDOG_SERVER_COUNT</key>" in plist.read_text()
    assert "<string>4</string>" in plist.read_text()


def test_tdx_host_runner_logs_effective_parallelism_for_incident_diagnosis():
    script = Path("/Users/xiwei/stock_research/scripts/run_tdx_auction_backfill_watchdog_host.sh")

    text = script.read_text()
    assert 'echo "max_jobs=$MAX_JOBS"' in text
    assert 'echo "tdx_server_count=$TDX_SERVER_COUNT"' in text


def test_tdx_host_runner_forwards_settings_and_handles_report_dry_run(tmp_path):
    fake_python = tmp_path / "fake_python.sh"
    fake_python.write_text(
        "#!/usr/bin/env bash\n"
        "printf '%s\\n' \"$*\" >> \"$TDX_TEST_INVOKE_LOG\"\n"
        "printf '%s\\n' 'tdx_auction_watchdog|action|healthy'\n"
        "printf '%s\\n' 'tdx_auction_watchdog|work_remaining|False'\n"
    )
    fake_python.chmod(fake_python.stat().st_mode | stat.S_IXUSR)
    run_log = tmp_path / "run.log"
    invoke_log = tmp_path / "invoke.log"
    sentinel = tmp_path / "done"
    env = os.environ.copy()
    env.update(
        {
            "TDX_AUCTION_WATCHDOG_ROOT": "/Users/xiwei/stock_research",
            "TDX_AUCTION_WATCHDOG_PYTHON": str(fake_python),
            "TDX_AUCTION_WATCHDOG_LOG_DIR": str(tmp_path / "logs"),
            "TDX_AUCTION_WATCHDOG_RUN_LOG": str(run_log),
            "TDX_AUCTION_WATCHDOG_LOCK_DIR": str(tmp_path / "lock"),
            "TDX_AUCTION_WATCHDOG_COMPLETION_SENTINEL": str(sentinel),
            "TDX_AUCTION_WATCHDOG_COMPLETION_KEY": "tdx-test",
            "TDX_AUCTION_WATCHDOG_REPORT_DRY_RUN": "1",
            "TDX_AUCTION_WATCHDOG_HOSTS": "116.205.183.150:7709",
            "TDX_TEST_INVOKE_LOG": str(invoke_log),
        }
    )

    result = subprocess.run(
        ["bash", "/Users/xiwei/stock_research/scripts/run_tdx_auction_backfill_watchdog_host.sh"],
        check=False,
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    invoked = invoke_log.read_text()
    assert "tdx-auction-backfill-watchdog" in invoked
    assert "--tdx-hosts 116.205.183.150:7709" in invoked
    assert "--report-dry-run" in invoked
    assert sentinel.read_text().strip() == "tdx-test"


def test_tdx_host_runner_does_not_mark_complete_when_month_report_failed(tmp_path):
    fake_python = tmp_path / "fake_python.sh"
    fake_python.write_text(
        "#!/usr/bin/env bash\n"
        "printf '%s\\n' 'tdx_auction_watchdog|action|healthy'\n"
        "printf '%s\\n' 'tdx_auction_watchdog|work_remaining|False'\n"
        "printf '%s\\n' 'tdx_auction_watchdog|month_report|2018-02|sent|False'\n"
    )
    fake_python.chmod(fake_python.stat().st_mode | stat.S_IXUSR)
    sentinel = tmp_path / "done"
    env = os.environ.copy()
    env.update(
        {
            "TDX_AUCTION_WATCHDOG_ROOT": "/Users/xiwei/stock_research",
            "TDX_AUCTION_WATCHDOG_PYTHON": str(fake_python),
            "TDX_AUCTION_WATCHDOG_LOG_DIR": str(tmp_path / "logs"),
            "TDX_AUCTION_WATCHDOG_RUN_LOG": str(tmp_path / "run.log"),
            "TDX_AUCTION_WATCHDOG_LOCK_DIR": str(tmp_path / "lock"),
            "TDX_AUCTION_WATCHDOG_COMPLETION_SENTINEL": str(sentinel),
            "TDX_AUCTION_WATCHDOG_COMPLETION_KEY": "tdx-test",
        }
    )

    result = subprocess.run(
        ["bash", "/Users/xiwei/stock_research/scripts/run_tdx_auction_backfill_watchdog_host.sh"],
        check=False,
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert not sentinel.exists()
