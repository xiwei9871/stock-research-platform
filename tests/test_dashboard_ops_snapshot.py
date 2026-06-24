from datetime import date

from stock_research.dashboard.ops_snapshot import (
    build_internal_ops_snapshot,
    build_public_snapshot,
)


def test_build_internal_ops_snapshot_marks_not_started_as_critical(monkeypatch):
    monkeypatch.setattr(
        "stock_research.dashboard.ops_snapshot.load_data_status_for_dashboard",
        lambda service, current_trade_date=None: {
            "latest_ready_trade_date": "2026-06-23",
            "current_trade_date": "2026-06-24",
            "pipeline_status": "NOT_READY",
            "daily_status": "pending",
            "minute5_status": "pending",
            "deps_status": "pending",
            "failed_jobs": [],
            "warnings": [],
            "last_updated_at": "2026-06-24T03:40:00+08:00",
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

    assert snapshot["intervention"]["needs_intervention"] is True
    assert snapshot["intervention"]["severity"] == "critical"
    assert snapshot["intervention"]["reason_code"] == "not_started"


def test_build_internal_ops_snapshot_marks_delayed_but_progressing_as_warning(monkeypatch):
    monkeypatch.setattr(
        "stock_research.dashboard.ops_snapshot.load_data_status_for_dashboard",
        lambda service, current_trade_date=None: {
            "latest_ready_trade_date": "2026-06-23",
            "current_trade_date": "2026-06-24",
            "pipeline_status": "NOT_READY",
            "daily_status": "running",
            "minute5_status": "running",
            "deps_status": "pending",
            "failed_jobs": [],
            "warnings": [],
            "last_updated_at": "2026-06-24T08:06:00+08:00",
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
    assert snapshot["intervention"]["needs_intervention"] is True
    assert snapshot["intervention"]["severity"] == "warning"
    assert snapshot["health"]["stalled"] is False


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
                "coverage_summary": {"core": "97.8%"},
                "factor_gate_summary": {"approved_count": 12},
                "published_at": "2026-06-24T08:12:00+08:00",
            },
        },
    )

    snapshot = build_public_snapshot("stock_research", trade_date=date(2026, 6, 24))

    assert snapshot["status"] == "delayed"
    assert snapshot["latest_ready_trade_date"] == "2026-06-23"
    assert "source timeout" not in str(snapshot)
    assert "suggested_action" not in str(snapshot)
