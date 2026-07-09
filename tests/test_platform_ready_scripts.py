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
    assert "-m scripts.daily_pipeline --date 2026-06-18 --stage market_monitor" in calls
    assert "-m scripts.daily_pipeline --date 2026-06-18 --stage deps" in calls
    assert "-m scripts.daily_pipeline --date 2026-06-18 --stage health" in calls
    assert "-m stock_research.cli run-strategy-daily-eod --trade-date 2026-06-18" in calls
    assert "-m stock_research.platform_ready --trade-date 2026-06-18" in calls
    assert calls.index("-m stock_research.cli watchlist-build") < calls.index(
        "-m scripts.daily_pipeline --date 2026-06-18 --stage market_monitor"
    )
    assert calls.index("-m scripts.daily_pipeline --date 2026-06-18 --stage health") < calls.index(
        "-m stock_research.cli run-strategy-daily-eod"
    )
    assert calls.index("-m stock_research.cli run-strategy-daily-eod") < calls.index("-m stock_research.platform_ready")
    assert "平台就绪构建完成" in result.stdout
    assert "交易日: 2026-06-18" in result.stdout
    assert "详细日志:" in result.stdout
    assert "platform_ready_build|step|" not in result.stdout
    assert "free_enrichment_batch|" not in result.stdout


def test_platform_build_script_smoke_mode_does_not_run_data_steps(tmp_path: Path) -> None:
    fake_root = tmp_path / "root"
    fake_root.mkdir()
    _prepare_fake_guard(fake_root)
    fake_python = tmp_path / "python.sh"
    calls_file = tmp_path / "calls.txt"

    fake_python.write_text(
        f"""#!/usr/bin/env bash
printf '%s\\n' "$*" >> "{calls_file}"
if [[ "$1" == "-c" ]]; then
  printf 'platform_ready_build|smoke|imports_ok\\n'
fi
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
            "PLATFORM_READY_LOG_DIR": str(tmp_path / "logs"),
            "PLATFORM_READY_SMOKE_ONLY": "1",
        }
    )

    result = subprocess.run(
        ["scripts/run_platform_ready_build_cron.sh"],
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "platform_ready_build|smoke|would_run|finalize_market_monitor" in result.stdout
    assert "platform_ready_build|smoke|would_run|finalize_deps" in result.stdout
    assert "platform_ready_build|smoke|would_run|finalize_health" in result.stdout
    assert "platform_ready_build|smoke|would_run|strategy_daily_eod" in result.stdout
    calls = calls_file.read_text(encoding="utf-8")
    assert "-m stock_research.cli free-enrichment-backfill" not in calls
    assert "-m stock_research.cli run-daily-factor-pipeline" not in calls
    assert "-m stock_research.platform_ready" not in calls


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
    assert "EOD自动修复失败" in result.stdout
    assert "交易日: 2026-06-18" in result.stdout
    assert "退出码: 3" in result.stdout
    assert "详细日志:" in result.stdout


def test_platform_ready_check_script_emits_heartbeat_while_repair_runs(tmp_path: Path) -> None:
    fake_root = tmp_path / "root"
    fake_root.mkdir()
    _prepare_fake_guard(fake_root)
    fake_python = tmp_path / "python.sh"
    calls_file = tmp_path / "calls.txt"

    fake_python.write_text(
        f"""#!/usr/bin/env bash
printf '%s\\n' "$*" > "{calls_file}"
sleep 2
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
            "PLATFORM_READY_LOG_DIR": str(tmp_path / "logs"),
            "PLATFORM_READY_CHECK_HEARTBEAT_SECONDS": "1",
        }
    )

    result = subprocess.run(
        ["scripts/run_platform_ready_check_cron.sh"],
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 0
    assert "EOD自动修复完成" in result.stdout
    assert "platform_ready_check|stage|eod_auto_repair|heartbeat|elapsed=" not in result.stdout
    log_text = (tmp_path / "logs" / "platform_ready_check.host.log").read_text(encoding="utf-8")
    assert "platform_ready_check|stage|eod_auto_repair|heartbeat|elapsed=" in log_text


def test_platform_ready_check_script_defaults_to_latest_market_date(tmp_path: Path) -> None:
    fake_root = tmp_path / "root"
    fake_root.mkdir()
    _prepare_fake_guard(fake_root)
    fake_python = tmp_path / "python.sh"
    calls_file = tmp_path / "calls.txt"

    fake_python.write_text(
        f"""#!/usr/bin/env bash
if [[ "$#" -ge 2 && "$1" == "-c" ]]; then
  printf 'date-resolver-via-c\\n' >> "{calls_file}"
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
    assert "date-resolver-via-c" in calls
    assert "-m stock_research.eod_auto_repair --trade-date 2026-06-29" in calls
    assert "eod_auto_repair/2026-06-29" in result.stdout
    assert "EOD自动修复完成" in result.stdout


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
    assert "交易日历同步完成" in result.stdout
    assert "范围: 2026-06-22 ~ 2026-10-20" in result.stdout
    assert "详细日志:" in result.stdout
    assert "trading calendar sync start" not in result.stdout
