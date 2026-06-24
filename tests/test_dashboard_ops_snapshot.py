from datetime import date

from stock_research.dashboard.ops_snapshot import (
    build_internal_ops_snapshot,
    build_public_snapshot,
)


def test_build_internal_ops_snapshot_distinguishes_requested_date_from_latest_status_row(monkeypatch):
    monkeypatch.setattr(
        "stock_research.dashboard.ops_snapshot._load_pipeline_status_context",
        lambda service, trade_date: {
            "data_status": {
                "latest_ready_trade_date": "2026-06-23",
                "current_trade_date": "2026-06-24",
                "pipeline_status": "READY",
                "daily_status": "success",
                "minute5_status": "success",
                "deps_status": "success",
                "failed_jobs": [],
                "warnings": [],
                "last_updated_at": "2026-06-23T20:00:00+08:00",
            },
            "requested_trade_date": "2026-06-24",
            "status_trade_date": "2026-06-23",
            "latest_available_trade_date": "2026-06-23",
            "matches_requested_trade_date": False,
        },
    )
    monkeypatch.setattr(
        "stock_research.dashboard.ops_snapshot.load_intraday_status",
        lambda service, run_date: {
            "run_date": "2026-06-24",
            "jobs": [],
            "universe_count": 0,
            "universe": [],
            "market_sentiment": None,
        },
    )
    monkeypatch.setattr(
        "stock_research.dashboard.ops_snapshot.summarize_operational_health",
        lambda **kwargs: {
            "trade_date": "2026-06-24",
            "status": "ok",
            "alert_count": 0,
            "ingest": {},
            "stale_ingest": {},
            "backfill": {},
            "stale_backfill": {},
            "daily_jobs": [],
        },
    )
    monkeypatch.setattr(
        "stock_research.dashboard.ops_snapshot.load_ops_stage_details",
        lambda service, trade_date=None: [],
    )
    monkeypatch.setattr(
        "stock_research.dashboard.ops_snapshot._now_in_timezone",
        lambda tz_name: "2026-06-24T04:20:00+08:00",
    )

    snapshot = build_internal_ops_snapshot("stock_research", trade_date=date(2026, 6, 24))

    assert snapshot["run_window"]["requested_trade_date"] == "2026-06-24"
    assert snapshot["run_window"]["status_trade_date"] == "2026-06-23"
    assert snapshot["run_window"]["latest_available_trade_date"] == "2026-06-23"
    assert snapshot["run_window"]["status_matches_requested_trade_date"] is False
    assert snapshot["pipeline"]["overall_status"] == "not_started"
    assert snapshot["readiness"]["ready_for_publication"] is False
    assert snapshot["intervention"]["reason_code"] == "not_started"


def test_build_internal_ops_snapshot_uses_health_alerts_in_readiness(monkeypatch):
    monkeypatch.setattr(
        "stock_research.dashboard.ops_snapshot._load_pipeline_status_context",
        lambda service, trade_date: {
            "data_status": {
                "latest_ready_trade_date": "2026-06-24",
                "current_trade_date": "2026-06-24",
                "pipeline_status": "NOT_READY",
                "daily_status": "running",
                "minute5_status": "running",
                "deps_status": "pending",
                "failed_jobs": [],
                "warnings": [],
                "last_updated_at": "2026-06-24T08:06:00+08:00",
            },
            "requested_trade_date": "2026-06-24",
            "status_trade_date": "2026-06-24",
            "latest_available_trade_date": "2026-06-24",
            "matches_requested_trade_date": True,
        },
    )
    monkeypatch.setattr(
        "stock_research.dashboard.ops_snapshot.load_intraday_status",
        lambda service, run_date: {
            "run_date": "2026-06-24",
            "jobs": [],
            "universe_count": 0,
            "universe": [],
            "market_sentiment": {"sentiment_state": "neutral", "sentiment_score": 0.11},
        },
    )
    monkeypatch.setattr(
        "stock_research.dashboard.ops_snapshot.summarize_operational_health",
        lambda **kwargs: {
            "trade_date": "2026-06-24",
            "status": "alert",
            "alert_count": 2,
            "ingest": {},
            "stale_ingest": {},
            "backfill": {},
            "stale_backfill": {},
            "daily_jobs": [],
        },
    )
    monkeypatch.setattr(
        "stock_research.dashboard.ops_snapshot.load_ops_stage_details",
        lambda service, trade_date=None: [
            {
                "stage": "minute5",
                "status": "running",
                "started_at": "2026-06-24T07:10:00+08:00",
                "updated_at": "2026-06-24T08:06:00+08:00",
                "error_summary": None,
            }
        ],
    )
    monkeypatch.setattr(
        "stock_research.dashboard.ops_snapshot._now_in_timezone",
        lambda tz_name: "2026-06-24T08:10:00+08:00",
    )

    snapshot = build_internal_ops_snapshot("stock_research", trade_date=date(2026, 6, 24))

    assert snapshot["pipeline"]["overall_status"] == "delayed"
    assert snapshot["health"]["has_alerts"] is True
    assert snapshot["readiness"]["blocking_issue_count"] == 2
    assert snapshot["readiness"]["ready_for_publication"] is False
    assert snapshot["intervention"]["severity"] == "warning"


def test_build_public_snapshot_hides_internal_errors_and_uses_release_status(monkeypatch):
    monkeypatch.setattr(
        "stock_research.dashboard.ops_snapshot.build_internal_ops_snapshot",
        lambda service, trade_date=None: {
            "run_window": {},
            "pipeline": {"overall_status": "delayed"},
            "health": {"last_error_summary": "source timeout"},
            "intervention": {
                "needs_intervention": True,
                "severity": "warning",
                "reason_code": "deadline_risk",
                "reason_text": "deadline risk",
                "suggested_action": "check watchdog",
            },
            "readiness": {
                "latest_ready_trade_date": "2026-06-23",
                "ready_status": "degraded_ready",
                "ready_for_dashboard": True,
                "ready_for_publication": True,
                "blocking_issue_count": 0,
            },
            "snapshot_preview": {
                "market_state": {"state": "neutral"},
                "topn_preview": [{"asset_id": "000001.SZ", "stock_name": "Ping An Bank"}],
                "coverage_summary": {
                    "core": "97.8%",
                    "pipeline_status": "READY",
                    "failed_jobs": 4,
                    "warnings": ["source timeout"],
                },
                "factor_gate_summary": {"approved_count": 12},
                "published_at": "2026-06-24T08:12:00+08:00",
            },
        },
    )

    snapshot = build_public_snapshot("stock_research", trade_date=date(2026, 6, 24))

    assert snapshot["status"] == "delayed"
    assert snapshot["latest_ready_trade_date"] == "2026-06-23"
    assert snapshot["coverage_summary"] == {"core": "97.8%"}
    assert "source timeout" not in str(snapshot)
    assert "suggested_action" not in str(snapshot)
    assert "pipeline_status" not in str(snapshot["coverage_summary"])
    assert "failed_jobs" not in str(snapshot["coverage_summary"])
    assert "warnings" not in str(snapshot["coverage_summary"])
