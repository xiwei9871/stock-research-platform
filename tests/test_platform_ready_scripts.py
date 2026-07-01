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


def test_platform_build_script_runs_required_platform_steps(tmp_path: Path) -> None:
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
            "PLATFORM_READY_ROOT": str(fake_root),
            "PLATFORM_READY_PYTHON": str(fake_python),
            "PLATFORM_READY_TRADE_DATE": "2026-06-18",
            "PLATFORM_READY_OUTPUT_DIR": str(tmp_path / "outputs"),
            "PLATFORM_READY_REPORTS_DIR": str(tmp_path / "reports"),
            "PLATFORM_READY_LOG_DIR": str(tmp_path / "logs"),
            "PLATFORM_READY_LHB_CASE_PATH": str(tmp_path / "case.csv"),
            "PLATFORM_READY_LHB_FEATURES_PATH": str(tmp_path / "features.csv"),
            "PLATFORM_READY_LHB_ALIGNMENT_PATH": str(tmp_path / "alignment.csv"),
            "HTTP_PROXY": "http://192.168.3.185:7890",
            "HTTPS_PROXY": "http://192.168.3.185:7890",
            "ALL_PROXY": "socks5://192.168.3.185:7890",
            "http_proxy": "http://192.168.3.185:7890",
            "https_proxy": "http://192.168.3.185:7890",
            "all_proxy": "socks5://192.168.3.185:7890",
        }
    )

    result = subprocess.run(
        ["scripts/run_platform_ready_build_cron.sh"],
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    calls = calls_file.read_text(encoding="utf-8")
    assert "-m stock_research.cli free-enrichment-backfill" in calls
    assert "-m stock_research.cli run-daily-factor-pipeline" in calls
    assert "-m stock_research.cli build-technical-features-daily" in calls
    assert "-m stock_research.cli run-lhb-shortline-daily-v1" in calls
    assert "-m stock_research.cli watchlist-build" in calls
    assert "-m stock_research.platform_ready --trade-date 2026-06-18" in calls


def test_platform_ready_check_script_runs_eod_auto_repair_and_exits_with_status(tmp_path: Path) -> None:
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
printf '%s\\n' "$*" > "{calls_file}"
exit 3
""",
        encoding="utf-8",
    )
    fake_python.chmod(0o755)

    env = os.environ.copy()
    env.update(
        {
            "PLATFORM_READY_ROOT": str(fake_root),
            "PLATFORM_READY_PYTHON": str(fake_python),
            "PLATFORM_READY_TRADE_DATE": "2026-06-18",
            "PLATFORM_READY_LOG_DIR": str(tmp_path / "logs"),
            "HTTP_PROXY": "http://192.168.3.185:7890",
            "HTTPS_PROXY": "http://192.168.3.185:7890",
            "ALL_PROXY": "socks5://192.168.3.185:7890",
            "http_proxy": "http://192.168.3.185:7890",
            "https_proxy": "http://192.168.3.185:7890",
            "all_proxy": "socks5://192.168.3.185:7890",
        }
    )

    result = subprocess.run(
        ["scripts/run_platform_ready_check_cron.sh"],
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 3
    call = calls_file.read_text(encoding="utf-8")
    assert "-m stock_research.eod_auto_repair --trade-date 2026-06-18" in call
    assert "--output-dir" in call
    assert "eod_auto_repair/2026-06-18" in call
    assert "--mode repair" in call
    assert "-m stock_research.platform_ready" not in call


def test_platform_ready_check_script_defaults_to_latest_market_date(tmp_path: Path) -> None:
    fake_root = tmp_path / "root"
    fake_root.mkdir()
    _prepare_fake_guard(fake_root)
    fake_python = tmp_path / "python.sh"
    calls_file = tmp_path / "calls.txt"

    fake_python.write_text(
        f"""#!/usr/bin/env bash
    if [[ "$#" -eq 1 && "$1" == "-" ]]; then
  printf 'date-resolver\\n' >> "{calls_file}"
  printf '2026-06-29\\n'
  exit 0
fi
printf '%s\\n' "$*" >> "{calls_file}"
exit 0
""",
        encoding="utf-8",
    )
    fake_python.chmod(0o755)

    env = os.environ.copy()
    env.update(
        {
            "PLATFORM_READY_ROOT": str(fake_root),
            "PLATFORM_READY_PYTHON": str(fake_python),
            "PLATFORM_READY_LOG_DIR": str(tmp_path / "logs"),
        }
    )
    env.pop("PLATFORM_READY_TRADE_DATE", None)

    result = subprocess.run(
        ["scripts/run_platform_ready_check_cron.sh"],
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    calls = calls_file.read_text(encoding="utf-8")
    assert "date-resolver" in calls
    assert "-m stock_research.eod_auto_repair --trade-date 2026-06-29" in calls
    assert "eod_auto_repair/2026-06-29" in result.stdout


def test_trading_calendar_sync_script_clears_proxy_env(tmp_path: Path) -> None:
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
if [[ "$1" == "-m" && "$2" == "stock_research.cli" ]]; then
  exit 0
fi
printf '2026-06-22\\n'
""",
        encoding="utf-8",
    )
    fake_python.chmod(0o755)

    env = os.environ.copy()
    env.update(
        {
            "TRADING_CALENDAR_SYNC_ROOT": str(fake_root),
            "TRADING_CALENDAR_SYNC_PYTHON": str(fake_python),
            "TRADING_CALENDAR_SYNC_LOG_DIR": str(tmp_path / "logs"),
            "TRADING_CALENDAR_SYNC_START_DATE": "2026-06-22",
            "TRADING_CALENDAR_SYNC_END_DATE": "2026-10-20",
            "HTTP_PROXY": "http://192.168.3.185:7890",
            "HTTPS_PROXY": "http://192.168.3.185:7890",
            "ALL_PROXY": "socks5://192.168.3.185:7890",
            "http_proxy": "http://192.168.3.185:7890",
            "https_proxy": "http://192.168.3.185:7890",
            "all_proxy": "socks5://192.168.3.185:7890",
        }
    )

    result = subprocess.run(
        ["scripts/run_trading_calendar_sync_cron.sh"],
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    calls = calls_file.read_text(encoding="utf-8")
    assert "-m stock_research.cli sync-tushare-trading-calendar" in calls
    assert "--start-date 2026-06-22" in calls
    assert "--end-date 2026-10-20" in calls
