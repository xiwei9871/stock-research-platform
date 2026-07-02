import os
from pathlib import Path
import stat
import subprocess

import pytest


@pytest.mark.parametrize(
    ("script_path", "env_prefix", "expected_adapter"),
    [
        (
            "/Users/xiwei/stock_research/scripts/run_technical_feature_backfill_watchdog_host.sh",
            "TECHNICAL_FEATURE_WATCHDOG",
            "technical-features",
        ),
        (
            "/Users/xiwei/stock_research/scripts/run_minute_backfill_watchdog_host.sh",
            "MINUTE_BACKFILL_WATCHDOG",
            "minute",
        ),
        (
            "/Users/xiwei/stock_research/scripts/run_wave5_factor_gate_watchdog_host.sh",
            "FACTOR_GATE_WATCHDOG",
            "factor-gate",
        ),
    ],
)
def test_backfill_watchdog_host_scripts_skip_after_completion_sentinel(
    tmp_path,
    script_path,
    env_prefix,
    expected_adapter,
):
    run_log = tmp_path / "watchdog.host.log"
    invoke_log = tmp_path / "python_invoked.log"
    sentinel = tmp_path / "watchdog.completed"
    fake_python = _write_fake_python(tmp_path)
    env = _host_env(
        tmp_path=tmp_path,
        env_prefix=env_prefix,
        fake_python=fake_python,
        run_log=run_log,
        invoke_log=invoke_log,
        sentinel=sentinel,
    )

    first = subprocess.run(
        ["bash", script_path],
        check=False,
        env=env,
        capture_output=True,
        text=True,
    )

    assert first.returncode == 0
    assert f"--adapter {expected_adapter}" in invoke_log.read_text()
    assert sentinel.read_text().strip() == "test-completion-key"
    assert "completion_sentinel_written=true" in run_log.read_text()

    invoke_log.unlink()
    second = subprocess.run(
        ["bash", script_path],
        check=False,
        env=env,
        capture_output=True,
        text=True,
    )

    assert second.returncode == 0
    assert not invoke_log.exists()
    contents = run_log.read_text()
    assert f"completion_sentinel={sentinel}" in contents
    assert "skipped because backfill completion sentinel is current" in contents


def test_minute_backfill_watchdog_host_uses_workers_8_by_default(tmp_path):
    run_log = tmp_path / "minute_backfill_watchdog.host.log"
    invoke_log = tmp_path / "python_invoked.log"
    sentinel = tmp_path / "watchdog.completed"
    fake_python = _write_fake_python(tmp_path)
    env = _host_env(
        tmp_path=tmp_path,
        env_prefix="MINUTE_BACKFILL_WATCHDOG",
        fake_python=fake_python,
        run_log=run_log,
        invoke_log=invoke_log,
        sentinel=sentinel,
    )

    result = subprocess.run(
        ["bash", "/Users/xiwei/stock_research/scripts/run_minute_backfill_watchdog_host.sh"],
        check=False,
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "--workers 8" in invoke_log.read_text()


def test_baostock_minute_backfill_watchdog_host_uses_budgeted_command(tmp_path):
    run_log = tmp_path / "baostock_minute_backfill_watchdog.host.log"
    invoke_log = tmp_path / "python_invoked.log"
    sentinel = tmp_path / "watchdog.completed"
    fake_python = _write_fake_python(tmp_path)
    env = _host_env(
        tmp_path=tmp_path,
        env_prefix="BAOSTOCK_MINUTE_BACKFILL_WATCHDOG",
        fake_python=fake_python,
        run_log=run_log,
        invoke_log=invoke_log,
        sentinel=sentinel,
    )
    env["BACKFILL_WATCHDOG_TEST_OUTPUT"] = (
        "baostock_minute_backfill_watchdog|action|healthy\n"
        "baostock_minute_backfill_watchdog|work_remaining|False\n"
    )

    result = subprocess.run(
        ["bash", "/Users/xiwei/stock_research/scripts/run_baostock_minute_backfill_watchdog_host.sh"],
        check=False,
        env=env,
        capture_output=True,
        text=True,
    )

    invoked = invoke_log.read_text()
    assert result.returncode == 0
    assert "stock_research.cli baostock-minute-backfill-watchdog" in invoked
    assert "--start-date 2020-01-02" in invoked
    assert "--baostock-daily-request-limit 50000" in invoked
    assert "--baostock-safety-multiplier 1.1" in invoked
    assert "--request-ledger-path" in invoked
    assert sentinel.read_text().strip() == "test-completion-key"


def _write_fake_python(tmp_path: Path) -> Path:
    fake_python = tmp_path / "fake_python.sh"
    fake_python.write_text(
        "#!/usr/bin/env bash\n"
        "printf '%s\\n' \"$*\" >> \"$BACKFILL_WATCHDOG_TEST_INVOKE_LOG\"\n"
        "printf '%s\\n' \"${BACKFILL_WATCHDOG_TEST_OUTPUT}\"\n"
        "exit 0\n"
    )
    fake_python.chmod(fake_python.stat().st_mode | stat.S_IXUSR)
    return fake_python


def _host_env(
    *,
    tmp_path: Path,
    env_prefix: str,
    fake_python: Path,
    run_log: Path,
    invoke_log: Path,
    sentinel: Path,
) -> dict[str, str]:
    root = tmp_path / "root"
    logs_dir = tmp_path / "logs"
    root.mkdir(exist_ok=True)
    logs_dir.mkdir(exist_ok=True)
    env = os.environ.copy()
    env.update(
        {
            f"{env_prefix}_ROOT": str(root),
            f"{env_prefix}_PYTHON": str(fake_python),
            f"{env_prefix}_OPENCLAW_BIN": "/tmp/fake_openclaw",
            f"{env_prefix}_LOG_DIR": str(logs_dir),
            f"{env_prefix}_RUN_LOG": str(run_log),
            f"{env_prefix}_COMPLETION_SENTINEL": str(sentinel),
            f"{env_prefix}_COMPLETION_KEY": "test-completion-key",
            f"{env_prefix}_LOCK_DIR": str(tmp_path / "watchdog.lock"),
            "BACKFILL_WATCHDOG_TEST_INVOKE_LOG": str(invoke_log),
            "BACKFILL_WATCHDOG_TEST_OUTPUT": (
                "backfill_watchdog|action|healthy\n"
                "backfill_watchdog|work_remaining|False\n"
            ),
        }
    )
    return env
