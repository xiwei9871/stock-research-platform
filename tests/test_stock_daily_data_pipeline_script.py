from pathlib import Path


def test_stock_daily_data_pipeline_host_script_uses_cli_entrypoint() -> None:
    script = Path("scripts/run_stock_daily_data_pipeline.sh").read_text()

    assert "run-stock-daily-data-pipeline" in script
    assert "STOCK_DAILY_PIPELINE_TRADE_DATE" in script
    assert "STOCK_DAILY_PIPELINE_FEISHU_TARGET" in script
    assert "logs/stock_daily_data_pipeline.host.log" in script
    assert "set -euo pipefail" in script
