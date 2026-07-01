from pathlib import Path


def test_eod_auto_repair_cron_uses_module_entrypoint_and_lock():
    script = Path("scripts/run_eod_auto_repair_cron.sh").read_text()

    assert "python -m stock_research.eod_auto_repair" in script
    assert "flock" in script
    assert "--mode repair" in script
    assert "logs/eod_auto_repair" in script
