import json
import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "run_strategy_daily_eod_cron.sh"
JOBS_PATH = Path("/Users/xiwei/.openclaw/cron/jobs.json")
APPROVALS_PATH = Path("/Users/xiwei/.openclaw/exec-approvals.json")


def test_strategy_daily_eod_cron_script_uses_guard_and_cli_entrypoint() -> None:
    script = SCRIPT_PATH.read_text()

    assert 'source "$ROOT/scripts/stock_cron_guard.sh"' in script
    assert 'stock_cron_guard_or_exit "$PYTHON" "$TRADE_DATE" "${RESEARCH_SERVICE:-}"' in script
    assert "run-strategy-daily-eod" in script
    assert "--trade-date \"$TRADE_DATE\"" in script
    assert "--output-root \"$OUTPUT_ROOT\"" in script
    assert "strategy_daily_eod.host.log" in script
    assert "set -euo pipefail" in script


def test_strategy_daily_eod_cron_script_preserves_cli_rc_when_tee_fails(tmp_path: Path) -> None:
    fake_root = tmp_path / "fake_root"
    fake_scripts = fake_root / "scripts"
    fake_scripts.mkdir(parents=True)
    (fake_scripts / "stock_cron_guard.sh").write_text(
        """#!/usr/bin/env bash
stock_cron_guard_or_exit() {
  return 0
}
"""
    )

    fake_python = tmp_path / "fake_python.sh"
    arg_file = tmp_path / "python_args.txt"
    log_dir = tmp_path / "logs"
    run_log_dir = log_dir / "custom"
    output_root = tmp_path / "outputs"

    run_log_dir.mkdir(parents=True)
    fake_python.write_text(
        f"""#!/usr/bin/env bash
printf '%s\\n' "$*" > "{arg_file}"
exit 7
"""
    )
    fake_python.chmod(0o755)

    env = os.environ.copy()
    env.update(
        {
            "STRATEGY_DAILY_EOD_ROOT": str(fake_root),
            "STRATEGY_DAILY_EOD_PYTHON": str(fake_python),
            "STRATEGY_DAILY_EOD_LOG_DIR": str(log_dir),
            "STRATEGY_DAILY_EOD_RUN_LOG": str(run_log_dir),
            "STRATEGY_DAILY_EOD_TRADE_DATE": "2026-06-24",
            "STRATEGY_DAILY_EOD_OUTPUT_ROOT": str(output_root),
        }
    )

    result = subprocess.run(
        [str(SCRIPT_PATH)],
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 7
    assert "-m stock_research.cli run-strategy-daily-eod" in arg_file.read_text()
    assert "--trade-date 2026-06-24" in arg_file.read_text()
    assert f"--output-root {output_root}" in arg_file.read_text()


def test_openclaw_jobs_json_contains_strategy_daily_eod_job() -> None:
    data = json.loads(JOBS_PATH.read_text())
    job = next(job for job in data["jobs"] if job["name"] == "stock-strategy-daily-eod")

    assert job["agentId"] == "agent_jarvis"
    assert job["sessionTarget"] == "isolated"
    assert job["wakeMode"] == "now"
    assert job["schedule"]["expr"] == "40 19 * * 1-5"
    assert job["schedule"]["tz"] == "Asia/Shanghai"
    assert job["payload"]["kind"] == "agentTurn"
    assert job["payload"]["timeoutSeconds"] == 3600
    assert job["payload"]["toolsAllow"] == ["exec"]
    assert "/Users/xiwei/stock_research/scripts/run_strategy_daily_eod_cron.sh" in job["payload"]["message"]
    assert "最终中文汇报" in job["payload"]["message"]
    assert "交易日" in job["payload"]["message"]
    assert "lhb_shortline" in job["payload"]["message"]
    assert "mid_trend" in job["payload"]["message"]
    assert "tech_bottleneck" in job["payload"]["message"]
    assert "summary" in job["payload"]["message"]
    assert "不要写交易建议" in job["payload"]["message"]
    assert "description" in job
    assert "createdAtMs" in job
    assert "delivery" in job
    assert "failureAlert" in job
    assert "state" in job


def test_openclaw_exec_approvals_allow_strategy_daily_eod_script() -> None:
    data = json.loads(APPROVALS_PATH.read_text())
    patterns = [entry["pattern"] for entry in data["agents"]["agent_jarvis"]["allowlist"]]

    assert "/Users/xiwei/stock_research/scripts/run_strategy_daily_eod_cron.sh" in patterns
