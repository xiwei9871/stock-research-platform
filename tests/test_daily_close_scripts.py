import os
import subprocess
from pathlib import Path


def _write_proxy_check_python(path: Path, calls_file: Path) -> None:
    path.write_text(
        f"""#!/usr/bin/env bash
printf '%s\\n' "$*" >> "{calls_file}"
for name in HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy; do
  value="${{!name:-}}"
  if [[ -n "$value" ]]; then
    echo "proxy-leak:$name=$value" >&2
    exit 9
  fi
done
exit 0
""",
        encoding="utf-8",
    )
    path.chmod(0o755)


def _write_fake_curl(path: Path, calls_file: Path) -> None:
    path.write_text(
        f"""#!/usr/bin/env bash
printf '%s\\n' "$*" >> "{calls_file}"
exit 0
""",
        encoding="utf-8",
    )
    path.chmod(0o755)


def test_daily_close_pipeline_script_clears_proxy_env(tmp_path: Path) -> None:
    fake_python = tmp_path / "python.sh"
    calls_file = tmp_path / "calls.txt"
    _write_proxy_check_python(fake_python, calls_file)

    env = os.environ.copy()
    env.update(
        {
            "PYTHON_BIN": str(fake_python),
            "TRADE_DATE": "2026-06-22",
            "HTTP_PROXY": "http://192.168.3.185:7890",
            "HTTPS_PROXY": "http://192.168.3.185:7890",
            "ALL_PROXY": "socks5://192.168.3.185:7890",
            "http_proxy": "http://192.168.3.185:7890",
            "https_proxy": "http://192.168.3.185:7890",
            "all_proxy": "socks5://192.168.3.185:7890",
        }
    )

    result = subprocess.run(
        ["scripts/run_daily_close_pipeline_cron.sh", "minute5"],
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    calls = calls_file.read_text(encoding="utf-8")
    assert "-m stock_research.stock_cron_guard --date 2026-06-22" in calls
    assert "-m scripts.daily_pipeline --date 2026-06-22 --stage minute5" in calls
    assert "股票日终阶段完成" in result.stdout
    assert "阶段: minute5" in result.stdout
    assert "交易日: 2026-06-22" in result.stdout
    assert "详细日志:" in result.stdout


def test_daily_close_pipeline_script_smoke_mode_does_not_run_stage(tmp_path: Path) -> None:
    fake_python = tmp_path / "python.sh"
    calls_file = tmp_path / "calls.txt"
    _write_proxy_check_python(fake_python, calls_file)

    env = os.environ.copy()
    env.update(
        {
            "PYTHON_BIN": str(fake_python),
            "TRADE_DATE": "2026-06-22",
            "DAILY_CLOSE_SMOKE_ONLY": "1",
        }
    )

    result = subprocess.run(
        ["scripts/run_daily_close_pipeline_cron.sh", "minute5"],
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    calls = calls_file.read_text(encoding="utf-8")
    assert "-m stock_research.stock_cron_guard --date 2026-06-22" in calls
    assert "-m scripts.daily_pipeline --date 2026-06-22 --stage minute5" not in calls
    assert "daily_close_pipeline|smoke|would_run|stage=minute5|trade_date=2026-06-22" in result.stdout


def test_daily_close_pipeline_script_exits_nonzero_when_minute5_business_fails(tmp_path: Path) -> None:
    fake_python = tmp_path / "python.sh"
    calls_file = tmp_path / "calls.txt"
    fake_python.write_text(
        f"""#!/usr/bin/env bash
printf '%s\n' "$*" >> "{calls_file}"
if [[ "$*" == *"stock_research.stock_cron_guard"* ]]; then
  exit 0
fi
if [[ "$*" == *"--stage minute5"* ]]; then
  if [[ "${{DAILY_PIPELINE_CRON_OUTPUT:-}}" == "compact" ]]; then
    printf '%s\n' '{{"stage":"minute5","status":"failed","rows":0,"quality":{{"expected_count":5191,"actual_count":3939,"missing_count":1252}}}}'
  else
    printf '%s\n' '{{"stage":"minute5","status":"failed","rows":0,"quality":{{"missing_symbols":["600000.SH","600004.SH"]}}}}'
  fi
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
            "PYTHON_BIN": str(fake_python),
            "TRADE_DATE": "2026-06-22",
        }
    )

    result = subprocess.run(
        ["scripts/run_daily_close_pipeline_cron.sh", "minute5"],
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "股票日终阶段失败" in result.stdout
    assert "阶段: minute5" in result.stdout
    assert "交易日: 2026-06-22" in result.stdout
    assert "状态: failed" in result.stdout
    assert "缺失: 1252" in result.stdout
    assert "详细日志:" in result.stdout
    assert "600000.SH" not in result.stdout
    assert "daily_close_pipeline|business_failed|stage=minute5|trade_date=2026-06-22" not in result.stderr


def test_daily_close_minute5_wrapper_keeps_heartbeat_in_detail_log_only(tmp_path: Path) -> None:
    fake_python = tmp_path / "python.sh"
    fake_python.write_text(
        """#!/usr/bin/env bash
if [[ "$*" == *"stock_research.stock_cron_guard"* ]]; then
  exit 0
fi
if [[ "$*" == *"--stage minute5"* ]]; then
  echo 'progress|minute5_bar|event|minute5_progress|completed|50|total|100'
  sleep 2
  echo '{"stage":"minute5","status":"success","rows":4800,"quality":{"expected_count":100,"actual_count":100,"missing_count":0}}'
fi
exit 0
""",
        encoding="utf-8",
    )
    fake_python.chmod(0o755)
    log_dir = tmp_path / "logs"
    env = os.environ.copy()
    env.update(
        {
            "PYTHON_BIN": str(fake_python),
            "TRADE_DATE": "2026-07-10",
            "DAILY_CLOSE_CRON_LOG_DIR": str(log_dir),
            "DAILY_CLOSE_HEARTBEAT_SECONDS": "1",
        }
    )

    result = subprocess.run(
        ["scripts/run_daily_close_pipeline_cron.sh", "minute5"],
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 0
    assert "daily_close_pipeline|started|stage=minute5" not in result.stdout
    assert "daily_close_pipeline|heartbeat|stage=minute5" not in result.stdout
    assert "股票日终阶段完成" in result.stdout
    detail_log = next(log_dir.glob("daily_close_pipeline_minute5_*.log"))
    detail_text = detail_log.read_text(encoding="utf-8")
    assert "daily_close_pipeline|started|stage=minute5" in detail_text
    assert "daily_close_pipeline|heartbeat|stage=minute5" in detail_text
    assert "completed|50|total|100" in detail_text
    assert '"status":"success"' in detail_text


def test_open_auction_spot_snapshot_script_clears_proxy_env(tmp_path: Path) -> None:
    fake_python = tmp_path / "python.sh"
    calls_file = tmp_path / "calls.txt"
    _write_proxy_check_python(fake_python, calls_file)

    env = os.environ.copy()
    env.update(
        {
            "OPEN_AUCTION_SPOT_PYTHON": str(fake_python),
            "OPEN_AUCTION_SPOT_OUTPUT_DIR": str(tmp_path / "snapshots"),
            "HTTP_PROXY": "http://192.168.3.185:7890",
            "HTTPS_PROXY": "http://192.168.3.185:7890",
            "ALL_PROXY": "socks5://192.168.3.185:7890",
            "http_proxy": "http://192.168.3.185:7890",
            "https_proxy": "http://192.168.3.185:7890",
            "all_proxy": "socks5://192.168.3.185:7890",
        }
    )

    result = subprocess.run(
        ["scripts/run_open_auction_spot_snapshot.sh", "09:21", "2026-07-03"],
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "[open_auction_spot_snapshot] stock proxy env cleared" in result.stdout
    calls = calls_file.read_text(encoding="utf-8")
    assert "-m stock_research.cli collect-open-auction-spot-snapshot-v1" in calls
    assert "--trade-date 2026-07-03" in calls
    assert "--target-time 09:21" in calls


def test_daily_close_finalize_script_clears_proxy_env(tmp_path: Path) -> None:
    fake_python = tmp_path / "python.sh"
    calls_file = tmp_path / "calls.txt"
    curl_calls_file = tmp_path / "curl-calls.txt"
    fake_curl = tmp_path / "curl"
    _write_proxy_check_python(fake_python, calls_file)
    _write_fake_curl(fake_curl, curl_calls_file)

    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{tmp_path}:{env['PATH']}",
            "PYTHON_BIN": str(fake_python),
            "TRADE_DATE": "2026-06-22",
            "HTTP_PROXY": "http://192.168.3.185:7890",
            "HTTPS_PROXY": "http://192.168.3.185:7890",
            "ALL_PROXY": "socks5://192.168.3.185:7890",
            "http_proxy": "http://192.168.3.185:7890",
            "https_proxy": "http://192.168.3.185:7890",
            "all_proxy": "socks5://192.168.3.185:7890",
        }
    )

    result = subprocess.run(
        ["scripts/run_daily_close_finalize_cron.sh"],
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    calls = calls_file.read_text(encoding="utf-8")
    assert "-m stock_research.stock_cron_guard --date 2026-06-22" in calls
    assert calls.count("-m scripts.daily_pipeline --date 2026-06-22 --stage retry_failed") == 1
    assert calls.count("-m scripts.daily_pipeline --date 2026-06-22 --stage market_monitor") == 1
    assert calls.count("-m scripts.daily_pipeline --date 2026-06-22 --stage deps") == 1
    assert calls.count("-m scripts.daily_pipeline --date 2026-06-22 --stage health") == 1
    assert "-X POST http://127.0.0.1:8765/api/dashboard/cache/clear" in curl_calls_file.read_text(encoding="utf-8")
    assert "股票收盘修复完成" in result.stdout
    assert "交易日: 2026-06-22" in result.stdout
    assert "阶段: retry_failed=success, market_monitor=success, deps=success, health=success" in result.stdout
    assert "Dashboard缓存: success" in result.stdout
    assert "详细日志:" in result.stdout
    assert "daily_close_finalize|stage|" not in result.stdout


def test_daily_close_finalize_script_smoke_mode_does_not_run_stages(tmp_path: Path) -> None:
    fake_python = tmp_path / "python.sh"
    calls_file = tmp_path / "calls.txt"
    fake_curl = tmp_path / "curl"
    _write_proxy_check_python(fake_python, calls_file)
    _write_fake_curl(fake_curl, tmp_path / "curl-calls.txt")

    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{tmp_path}:{env['PATH']}",
            "PYTHON_BIN": str(fake_python),
            "TRADE_DATE": "2026-06-22",
            "DAILY_CLOSE_SMOKE_ONLY": "1",
        }
    )

    result = subprocess.run(
        ["scripts/run_daily_close_finalize_cron.sh"],
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    calls = calls_file.read_text(encoding="utf-8")
    assert "-m stock_research.stock_cron_guard --date 2026-06-22" in calls
    assert "-m scripts.daily_pipeline --date 2026-06-22 --stage retry_failed" not in calls
    assert "daily_close_finalize|smoke|would_run|stage=retry_failed|trade_date=2026-06-22" in result.stdout
    assert "daily_close_finalize|dashboard_cache_clear" not in result.stdout


def test_daily_close_finalize_script_times_out_a_stuck_stage(tmp_path: Path) -> None:
    fake_python = tmp_path / "python.sh"
    calls_file = tmp_path / "calls.txt"
    fake_python.write_text(
        f"""#!/usr/bin/env bash
printf '%s\\n' "$*" >> "{calls_file}"
if [[ "$*" == *"--stage retry_failed"* ]]; then
  sleep 2
fi
exit 0
""",
        encoding="utf-8",
    )
    fake_python.chmod(0o755)

    env = os.environ.copy()
    env.update(
        {
            "PYTHON_BIN": str(fake_python),
            "TRADE_DATE": "2026-06-22",
            "FINALIZE_STAGE_TIMEOUT_SECONDS": "1",
        }
    )

    result = subprocess.run(
        ["scripts/run_daily_close_finalize_cron.sh"],
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 124
    assert "股票收盘修复失败" in result.stdout
    assert "失败阶段: retry_failed" in result.stdout
    assert "退出码: 124" in result.stdout
    assert "详细日志:" in result.stdout
    assert "daily_close_finalize|stage|retry_failed|timeout|1" not in result.stdout
    calls = calls_file.read_text(encoding="utf-8")
    assert "-m scripts.daily_pipeline --date 2026-06-22 --stage retry_failed" in calls
    assert "-m scripts.daily_pipeline --date 2026-06-22 --stage deps" not in calls


def test_daily_close_finalize_script_emits_heartbeat_while_stage_runs(tmp_path: Path) -> None:
    fake_python = tmp_path / "python.sh"
    calls_file = tmp_path / "calls.txt"
    fake_python.write_text(
        f"""#!/usr/bin/env bash
printf '%s\\n' "$*" >> "{calls_file}"
if [[ "$*" == *"--stage retry_failed"* ]]; then
  sleep 2
fi
exit 0
""",
        encoding="utf-8",
    )
    fake_python.chmod(0o755)

    env = os.environ.copy()
    env.update(
        {
            "PYTHON_BIN": str(fake_python),
            "TRADE_DATE": "2026-06-22",
            "FINALIZE_STAGE_TIMEOUT_SECONDS": "10",
            "FINALIZE_STAGE_HEARTBEAT_SECONDS": "1",
            "DASHBOARD_CACHE_CLEAR_URL": "",
        }
    )

    result = subprocess.run(
        ["scripts/run_daily_close_finalize_cron.sh"],
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "股票收盘修复完成" in result.stdout
    assert "heartbeat" not in result.stdout
