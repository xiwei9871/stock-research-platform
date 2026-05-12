from stock_research.reports.daily_research_cron import build_daily_research_cron_entry


def test_build_daily_research_cron_entry_formats_command():
    entry = build_daily_research_cron_entry(
        project_dir="/Users/xiwei/stock_research",
        trade_date_expr="$(date +%F)",
        hour=18,
        minute=30,
        score_version="manual_v1",
        top_n=30,
        index_id="CSI300",
        industry_system="csrc",
        reports_dir="reports",
        record_run=True,
    )

    assert entry.startswith("30 18 * * 1-5 cd /Users/xiwei/stock_research")
    assert ".venv/bin/python -m stock_research.reports.daily_research_report_cli" in entry
    assert "--trade-date $(date +%F)" in entry
    assert "--score-version manual_v1" in entry
    assert "--record-run" in entry
    assert ">> logs/daily_research_report.log 2>&1" in entry
