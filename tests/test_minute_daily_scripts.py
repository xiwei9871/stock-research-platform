import os
import subprocess
from pathlib import Path


def test_run_baostock_minute_daily_cron_script_clears_proxy_and_calls_cli(tmp_path: Path) -> None:
    fake_root = tmp_path / "root"
    fake_root.mkdir()
    (fake_root / "scripts").mkdir()
    (fake_root / "logs").mkdir()
    calls_file = tmp_path / "calls.txt"
    env_file = tmp_path / "env.txt"
    fake_python = tmp_path / "python.sh"

    fake_python.write_text(
        f"""#!/usr/bin/env bash
printf '%s\\n' "$*" >> "{calls_file}"
env | sort > "{env_file}"
exit 0
""",
        encoding="utf-8",
    )
    fake_python.chmod(0o755)

    (fake_root / "scripts" / "stock_cron_guard.sh").write_text(
        f"""#!/usr/bin/env bash
clear_stock_proxy_env() {{
  printf '%s\\n' "clear_stock_proxy_env" >> "{calls_file}"
  unset HTTP_PROXY HTTPS_PROXY ALL_PROXY NO_PROXY
  unset http_proxy https_proxy all_proxy no_proxy
}}

stock_cron_guard_or_exit() {{
  printf '%s\\n' "stock_cron_guard_or_exit $*" >> "{calls_file}"
  "$1" -m stock_research.stock_cron_guard --date "$2" --service "$3"
}}
""",
        encoding="utf-8",
    )

    env = os.environ.copy()
    env.update(
        {
            "ROOT": str(fake_root),
            "PYTHON_BIN": str(fake_python),
            "TRADE_DATE": "2026-06-23",
            "RESEARCH_SERVICE": "minute-daily",
            "HTTP_PROXY": "http://127.0.0.1:9000",
            "HTTPS_PROXY": "http://127.0.0.1:9001",
            "ALL_PROXY": "socks5://127.0.0.1:9002",
        }
    )
    env["http_proxy"] = "http://127.0.0.1:9100"
    env["https_proxy"] = "http://127.0.0.1:9101"
    env["all_proxy"] = "socks5://127.0.0.1:9102"

    result = subprocess.run(
        ["scripts/run_baostock_minute_daily_cron.sh"],
        cwd=Path.cwd(),
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    calls = calls_file.read_text(encoding="utf-8")
    assert "clear_stock_proxy_env" in calls
    assert "-m stock_research.stock_cron_guard --date 2026-06-23 --service minute-daily" in calls
    assert "-m stock_research.cli run-baostock-minute-daily --trade-date 2026-06-23" in calls

    captured_env = env_file.read_text(encoding="utf-8")
    assert "HTTP_PROXY=" not in captured_env
    assert "HTTPS_PROXY=" not in captured_env
    assert "ALL_PROXY=" not in captured_env
    assert "http_proxy=" not in captured_env
    assert "https_proxy=" not in captured_env
    assert "all_proxy=" not in captured_env
