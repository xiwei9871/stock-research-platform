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


def test_daily_close_finalize_script_clears_proxy_env(tmp_path: Path) -> None:
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
