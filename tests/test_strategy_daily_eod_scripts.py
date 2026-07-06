import os
import subprocess
from pathlib import Path


def _prepare_fake_guard(fake_root: Path) -> None:
    scripts_dir = fake_root / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    (scripts_dir / "stock_cron_guard.sh").write_text(
        """#!/usr/bin/env bash
set -euo pipefail

clear_stock_proxy_env() {
  unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy
  export NO_PROXY="*"
  export no_proxy="*"
}

stock_cron_guard_or_exit() {
  "$1" "${@:4}" -m stock_research.stock_cron_guard "${@:2:1:+--date}" "${@:2:1}" >/dev/null 2>&1 || true
}
""",
        encoding="utf-8",
    )


def test_run_strategy_daily_eod_cron_script_clears_proxy_and_calls_cli(tmp_path: Path) -> None:
    fake_root = tmp_path / "root"
    fake_root.mkdir()
    _prepare_fake_guard(fake_root)
    fake_python = tmp_path / "python.sh"
    calls_file = tmp_path / "calls.txt"

    fake_python.write_text(
        f"""#!/usr/bin/env bash
for name in HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy; do
  value="${{!name:-}}"
  if [[ -n "$value" ]]; then
    echo "proxy-leak:$name=$value" >&2
    exit 9
  fi
done
printf '%s\\n' "$*" >> "{calls_file}"
exit 0
""",
        encoding="utf-8",
    )
    fake_python.chmod(0o755)

    env = os.environ.copy()
    env.update(
        {
            "STRATEGY_DAILY_EOD_ROOT": str(fake_root),
            "STRATEGY_DAILY_EOD_PYTHON": str(fake_python),
            "STRATEGY_DAILY_EOD_TRADE_DATE": "2026-06-24",
            "HTTP_PROXY": "http://192.168.3.185:7890",
            "HTTPS_PROXY": "http://192.168.3.185:7890",
            "ALL_PROXY": "socks5://192.168.3.185:7890",
            "http_proxy": "http://192.168.3.185:7890",
            "https_proxy": "http://192.168.3.185:7890",
            "all_proxy": "socks5://192.168.3.185:7890",
        }
    )

    result = subprocess.run(
        ["scripts/run_strategy_daily_eod_cron.sh"],
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    calls = calls_file.read_text(encoding="utf-8")
    assert "-m stock_research.cli run-strategy-daily-eod --trade-date 2026-06-24" in calls


def test_run_strategy_daily_eod_cron_exits_nonzero_when_business_status_failed(tmp_path: Path) -> None:
    fake_root = tmp_path / "root"
    fake_root.mkdir()
    _prepare_fake_guard(fake_root)
    fake_python = tmp_path / "python.sh"

    fake_python.write_text(
        """#!/usr/bin/env bash
if [[ "$*" == *"run-strategy-daily-eod"* ]]; then
  echo "strategy_daily_eod|status|failed"
  echo "strategy_daily_eod|summary_path|/tmp/summary.json"
  exit 0
fi
exit 0
""",
        encoding="utf-8",
    )
    fake_python.chmod(0o755)

    env = os.environ.copy()
    env.update(
        {
            "STRATEGY_DAILY_EOD_ROOT": str(fake_root),
            "STRATEGY_DAILY_EOD_PYTHON": str(fake_python),
            "STRATEGY_DAILY_EOD_TRADE_DATE": "2026-06-24",
        }
    )

    result = subprocess.run(
        ["scripts/run_strategy_daily_eod_cron.sh"],
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "strategy_daily_eod|status|failed" in result.stdout
    assert "strategy_daily_eod|business_failed" in result.stderr
