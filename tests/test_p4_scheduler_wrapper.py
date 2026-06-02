from pathlib import Path

from stock_research.p4.scheduler_wrapper import build_p4_scheduler_cron_entry


def test_build_p4_scheduler_cron_entry_formats_manual_install_line():
    entry = build_p4_scheduler_cron_entry(
        project_dir="/Users/xiwei/stock_research",
        trade_date_expr="$(date +%F)",
        hour=19,
        minute=15,
        weekdays="1-5",
        portfolio_id="p2_smoke_demo",
        service="stock_research_test",
        log_path="logs/p4_scheduler_daily.log",
    )

    assert entry.startswith("15 19 * * 1-5 cd /Users/xiwei/stock_research")
    assert "TRADE_DATE=$(date +%F)" in entry
    assert "PORTFOLIO_ID=p2_smoke_demo" in entry
    assert "SERVICE=stock_research_test" in entry
    assert "scripts/run_p4_scheduler_daily.sh" in entry
    assert ">> logs/p4_scheduler_daily.log 2>&1" in entry


def test_p4_scheduler_wrapper_script_is_dry_run_safe():
    script = Path("scripts/run_p4_scheduler_daily.sh").read_text(encoding="utf-8")

    assert "DRY_RUN" in script
    assert "p4-daily-orchestration" in script
    assert "--apply-daily-run-schema" in script
    assert "--record-run" in script
    assert "p4-read-model-smoke" in script
    assert "${OUTPUT_DIR}/manifest.json" in script
