from stock_research.dashboard.readiness_policy import (
    ReadinessDecision,
    classify_pipeline_readiness,
)


def test_ready_status_allows_dashboard_and_publication():
    decision = classify_pipeline_readiness(
        {
            "pipeline_status": "READY",
            "daily_status": "success",
            "minute5_status": "success",
            "deps_status": "success",
            "market_monitor_status": "success",
            "latest_ready_trade_date": "2026-07-03",
        },
        requested_trade_date="2026-07-03",
    )

    assert decision == ReadinessDecision(
        status="ready",
        ready_for_dashboard=True,
        ready_for_publication=True,
        blocking_reasons=[],
        warnings=[],
    )


def test_degraded_ready_allows_dashboard_but_blocks_publication_when_daily_partial():
    decision = classify_pipeline_readiness(
        {
            "pipeline_status": "DEGRADED_READY",
            "daily_status": "partial_success",
            "minute5_status": "success",
            "deps_status": "success",
            "market_monitor_status": "success",
            "latest_ready_trade_date": "2026-07-03",
        },
        requested_trade_date="2026-07-03",
    )

    assert decision.status == "degraded_ready"
    assert decision.ready_for_dashboard is True
    assert decision.ready_for_publication is False
    assert decision.blocking_reasons == ["daily_status=partial_success"]
    assert decision.warnings == ["pipeline_status=DEGRADED_READY"]


def test_mismatched_latest_ready_date_blocks_dashboard_and_publication():
    decision = classify_pipeline_readiness(
        {
            "pipeline_status": "READY",
            "daily_status": "success",
            "minute5_status": "success",
            "deps_status": "success",
            "market_monitor_status": "success",
            "latest_ready_trade_date": "2026-07-02",
        },
        requested_trade_date="2026-07-03",
    )

    assert decision.status == "blocked"
    assert decision.ready_for_dashboard is False
    assert decision.ready_for_publication is False
    assert decision.blocking_reasons == ["latest_ready_trade_date=2026-07-02"]
