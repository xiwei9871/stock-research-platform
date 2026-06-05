import os
import subprocess
from pathlib import Path


def test_stock_daily_data_pipeline_host_script_uses_cli_entrypoint() -> None:
    script = Path("scripts/run_stock_daily_data_pipeline.sh").read_text()

    assert "run-stock-daily-data-pipeline" in script
    assert "STOCK_DAILY_PIPELINE_TRADE_DATE" in script
    assert "STOCK_DAILY_PIPELINE_FEISHU_TARGET" in script
    assert "logs/stock_daily_data_pipeline.host.log" in script
    assert "set -euo pipefail" in script


def test_stock_daily_data_pipeline_host_script_logs_failed_cli_run(
    tmp_path: Path,
) -> None:
    fake_root = tmp_path / "fake_root"
    fake_root.mkdir()
    fake_python = tmp_path / "fake_python.sh"
    arg_file = tmp_path / "python_args.txt"
    log_dir = tmp_path / "logs"
    run_log = log_dir / "custom" / "stock_daily_data_pipeline.host.log"
    output_dir = tmp_path / "outputs"

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
            "STOCK_DAILY_PIPELINE_ROOT": str(fake_root),
            "STOCK_DAILY_PIPELINE_PYTHON": str(fake_python),
            "STOCK_DAILY_PIPELINE_OPENCLAW_BIN": "openclaw-test",
            "STOCK_DAILY_PIPELINE_LOG_DIR": str(log_dir),
            "STOCK_DAILY_PIPELINE_RUN_LOG": str(run_log),
            "STOCK_DAILY_PIPELINE_TRADE_DATE": "2026-06-05",
            "STOCK_DAILY_PIPELINE_OUTPUT_DIR": str(output_dir),
            "STOCK_DAILY_PIPELINE_FEISHU_TARGET": "chat:test",
            "STOCK_DAILY_PIPELINE_FEISHU_ACCOUNT": "jarvis",
        }
    )

    result = subprocess.run(
        ["scripts/run_stock_daily_data_pipeline.sh"],
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 7
    run_log_text = run_log.read_text()
    assert "stock daily data pipeline host run start" in run_log_text
    assert "stock daily data pipeline host run end" in run_log_text
    assert "rc=7" in run_log_text

    arg_text = arg_file.read_text()
    assert "-m stock_research.cli run-stock-daily-data-pipeline" in arg_text
    assert "--trade-date 2026-06-05" in arg_text
    assert f"--output-dir {output_dir}" in arg_text
    assert "--feishu-target chat:test" in arg_text
    assert "--feishu-account jarvis" in arg_text
    assert "--openclaw-bin openclaw-test" in arg_text
