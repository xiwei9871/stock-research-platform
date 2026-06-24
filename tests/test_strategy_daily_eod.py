from stock_research import strategy_daily_eod_store


def test_build_status_payload_returns_expected_fields():
    payload = strategy_daily_eod_store.build_status_payload(
        trade_date="2026-06-24",
        status="running",
        dependency_check_status="success",
        lhb_shortline_status="running",
        mid_trend_status="skipped",
        tech_bottleneck_status="failed",
        review_rows="12",
        output_dir="/tmp/eod",
        summary_path="/tmp/eod/summary.md",
        error_summary="mid trend source timeout",
    )

    assert payload == {
        "trade_date": "2026-06-24",
        "status": "running",
        "dependency_check_status": "success",
        "lhb_shortline_status": "running",
        "mid_trend_status": "skipped",
        "tech_bottleneck_status": "failed",
        "review_rows": 12,
        "output_dir": "/tmp/eod",
        "summary_path": "/tmp/eod/summary.md",
        "error_summary": "mid trend source timeout",
    }


def test_strategy_daily_eod_status_schema_contains_expected_columns():
    sql = strategy_daily_eod_store.STRATEGY_DAILY_EOD_STATUS_SQL.lower()

    assert "create table if not exists ops.strategy_daily_eod_status" in sql
    assert "lhb_shortline_status text not null" in sql
    assert "mid_trend_status text not null" in sql
    assert "tech_bottleneck_status text not null" in sql
