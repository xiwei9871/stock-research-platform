from datetime import date

from stock_research.dashboard.ops_snapshot import (
    build_internal_ops_snapshot,
    build_public_snapshot,
    _load_pipeline_status_context,
    load_ops_stage_details,
)


def test_build_internal_ops_snapshot_keeps_ready_requested_date_ready(monkeypatch):
    monkeypatch.setattr(
        "stock_research.dashboard.ops_snapshot._load_pipeline_status_context",
        lambda service, trade_date: {
            "data_status": {
                "latest_ready_trade_date": "2026-06-24",
                "current_trade_date": "2026-06-24",
                "pipeline_status": "READY",
                "daily_status": "success",
                "minute5_status": "success",
                "deps_status": "success",
                "failed_jobs": [],
                "warnings": [],
                "last_updated_at": "2026-06-24T20:00:00+08:00",
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
    assert snapshot["run_window"]["status_trade_date"] == "2026-06-24"
    assert snapshot["run_window"]["status_matches_requested_trade_date"] is True
    assert snapshot["pipeline"]["overall_status"] == "ready"
    assert snapshot["readiness"]["ready_for_publication"] is True
    assert snapshot["intervention"]["reason_code"] == "ready"


def test_build_internal_ops_snapshot_defaults_to_latest_status_trade_date(monkeypatch):
    captured: dict[str, date] = {}

    monkeypatch.setattr(
        "stock_research.dashboard.ops_snapshot._fetch_latest_pipeline_status_row",
        lambda service: {"trade_date": date(2026, 6, 29)},
    )
    monkeypatch.setattr(
        "stock_research.dashboard.ops_snapshot._today_in_timezone",
        lambda tz_name: date(2026, 6, 30),
    )

    def fake_status_context(service, trade_date):
        captured["status_date"] = trade_date
        return {
            "data_status": {
                "latest_ready_trade_date": "2026-06-29",
                "current_trade_date": "2026-06-29",
                "pipeline_status": "DEGRADED_READY",
                "daily_status": "partial_success",
                "minute5_status": "partial_success",
                "deps_status": "success",
                "failed_jobs": [],
                "warnings": [],
                "last_updated_at": "2026-06-29T22:08:33+08:00",
            },
            "requested_trade_date": "2026-06-29",
            "status_trade_date": "2026-06-29",
            "latest_available_trade_date": "2026-06-29",
            "matches_requested_trade_date": True,
        }

    monkeypatch.setattr("stock_research.dashboard.ops_snapshot._load_pipeline_status_context", fake_status_context)
    monkeypatch.setattr("stock_research.dashboard.ops_snapshot.load_intraday_status", lambda service, run_date: {})
    monkeypatch.setattr(
        "stock_research.dashboard.ops_snapshot.summarize_operational_health",
        lambda **kwargs: {
            "trade_date": "2026-06-29",
            "status": "ok",
            "alert_count": 0,
            "ingest": {},
            "stale_ingest": {},
            "backfill": {},
            "stale_backfill": {},
            "daily_jobs": [],
        },
    )
    monkeypatch.setattr("stock_research.dashboard.ops_snapshot.load_ops_stage_details", lambda service, trade_date=None: [])
    monkeypatch.setattr(
        "stock_research.dashboard.ops_snapshot._now_in_timezone",
        lambda tz_name: "2026-06-30T06:30:00+08:00",
    )

    snapshot = build_internal_ops_snapshot("stock_research")

    assert captured["status_date"] == date(2026, 6, 29)
    assert snapshot["run_window"]["requested_trade_date"] == "2026-06-29"
    assert snapshot["readiness"]["ready_status"] == "degraded_ready"
    assert snapshot["readiness"]["ready_for_dashboard"] is True
    assert snapshot["readiness"]["ready_for_publication"] is False
    assert snapshot["readiness"]["blocking_issue_count"] == 2
    assert snapshot["readiness"]["blocking_reasons"] == [
        "daily_status=partial_success",
        "minute5_status=partial_success",
    ]


def test_build_internal_ops_snapshot_reports_degraded_ready_publication_blockers(monkeypatch):
    monkeypatch.setattr(
        "stock_research.dashboard.ops_snapshot._load_pipeline_status_context",
        lambda service, trade_date: {
            "data_status": {
                "latest_ready_trade_date": "2026-06-30",
                "current_trade_date": "2026-06-30",
                "pipeline_status": "DEGRADED_READY",
                "daily_status": "partial_success",
                "minute5_status": "partial_success",
                "deps_status": "success",
                "failed_jobs": [{"stage": "minute5", "status": "partial_success"}],
                "warnings": ["optional_or_partial_data_failed"],
                "last_updated_at": "2026-06-30T21:02:37+08:00",
            },
            "requested_trade_date": "2026-06-30",
            "status_trade_date": "2026-06-30",
            "latest_available_trade_date": "2026-06-30",
            "matches_requested_trade_date": True,
        },
    )
    monkeypatch.setattr("stock_research.dashboard.ops_snapshot.load_intraday_status", lambda service, run_date: {})
    monkeypatch.setattr(
        "stock_research.dashboard.ops_snapshot.summarize_operational_health",
        lambda **kwargs: {
            "trade_date": "2026-06-30",
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
                "started_at": "2026-06-30T19:00:00+08:00",
                "updated_at": "2026-06-30T19:00:00+08:00",
                "error_summary": None,
            }
        ],
    )
    monkeypatch.setattr(
        "stock_research.dashboard.ops_snapshot._now_in_timezone",
        lambda tz_name: "2026-06-30T21:30:00+08:00",
    )

    snapshot = build_internal_ops_snapshot("stock_research", trade_date=date(2026, 6, 30))

    assert snapshot["readiness"]["ready_status"] == "degraded_ready"
    assert snapshot["readiness"]["ready_for_dashboard"] is True
    assert snapshot["readiness"]["ready_for_publication"] is False
    assert snapshot["readiness"]["blocking_issue_count"] == 2
    assert snapshot["readiness"]["blocking_reasons"] == [
        "daily_status=partial_success",
        "minute5_status=partial_success",
    ]


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
    assert snapshot["readiness"]["blocking_issue_count"] == 3
    assert "pipeline_status=NOT_READY" in snapshot["readiness"]["blocking_reasons"]
    assert snapshot["readiness"]["ready_for_publication"] is False
    assert snapshot["intervention"]["severity"] == "warning"


def test_load_ops_stage_details_defaults_to_latest_trade_date_when_missing(monkeypatch):
    captured = []

    class _Context:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_fetch_all(conn, sql, params=None):
        captured.append((sql.strip(), params))
        if "SELECT trade_date" in sql:
            return [{"trade_date": date(2026, 6, 23)}]
        if "SELECT stage, status" in sql:
            return [
                {
                    "stage": "daily",
                    "status": "success",
                    "started_at": None,
                    "updated_at": None,
                    "error_summary": None,
                }
            ]
        raise AssertionError(sql)

    monkeypatch.setattr("stock_research.dashboard.ops_snapshot.connect", lambda service: _Context())
    monkeypatch.setattr("stock_research.dashboard.ops_snapshot.fetch_all", fake_fetch_all)

    rows = load_ops_stage_details("stock_research")

    assert rows == [
        {
            "stage": "daily",
            "status": "success",
            "started_at": None,
            "updated_at": None,
            "error_summary": None,
        }
    ]
    assert captured[0][1] is None
    assert captured[1][1] == [date(2026, 6, 23)]


def test_load_pipeline_status_context_prefers_requested_row_when_present(monkeypatch):
    class _Context:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, tb):
            return False

    calls = []

    def fake_fetch_all(conn, sql, params=None):
        calls.append((sql.strip(), params))
        if "WHERE trade_date = %s" in sql:
            return [
                {
                    "trade_date": date(2026, 6, 24),
                    "pipeline_status": "READY",
                    "daily_status": "success",
                    "minute5_status": "success",
                    "deps_status": "success",
                    "latest_ready_trade_date": date(2026, 6, 24),
                    "warnings": [],
                    "failed_jobs": [],
                    "updated_at": date(2026, 6, 24),
                }
            ]
        if "ORDER BY trade_date DESC, updated_at DESC" in sql:
            return [
                {
                    "trade_date": date(2026, 6, 24),
                    "pipeline_status": "READY",
                    "daily_status": "success",
                    "minute5_status": "success",
                    "deps_status": "success",
                    "latest_ready_trade_date": date(2026, 6, 24),
                    "warnings": [],
                    "failed_jobs": [],
                    "updated_at": date(2026, 6, 24),
                }
            ]
        raise AssertionError(sql)

    monkeypatch.setattr("stock_research.dashboard.ops_snapshot.connect", lambda service: _Context())
    monkeypatch.setattr("stock_research.dashboard.ops_snapshot.fetch_all", fake_fetch_all)

    context = _load_pipeline_status_context("stock_research", date(2026, 6, 24))

    assert context["matches_requested_trade_date"] is True
    assert context["status_trade_date"] == "2026-06-24"
    assert context["latest_available_trade_date"] == "2026-06-24"
    assert context["data_status"]["pipeline_status"] == "READY"
    assert calls[0][1] == [date(2026, 6, 24)]


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
                "market_state": {
                    "state": "neutral",
                    "score": 0.11,
                    "internal_confidence": 0.92,
                },
                "topn_preview": [
                    {
                        "asset_id": "000001.SZ",
                        "stock_name": "Ping An Bank",
                        "score_total": 93.1,
                        "operator_note": "do not release",
                    }
                ],
                "coverage_summary": {
                    "core": "97.8%",
                    "pipeline_status": "READY",
                    "failed_jobs": 4,
                    "warnings": ["source timeout"],
                    "experimental_internal_metric": "do not publish",
                },
                "factor_gate_summary": {
                    "approved_count": 12,
                    "rejected_count": 2,
                    "internal_rules": ["no release"],
                },
                "published_at": "2026-06-24T08:12:00+08:00",
            },
        },
    )

    snapshot = build_public_snapshot("stock_research", trade_date=date(2026, 6, 24))

    assert snapshot["status"] == "delayed"
    assert snapshot["latest_ready_trade_date"] == "2026-06-23"
    assert snapshot["market_state"] == {"state": "neutral", "score": 0.11}
    assert snapshot["topn_preview"] == [
        {
            "asset_id": "000001.SZ",
            "stock_name": "Ping An Bank",
            "score_total": 93.1,
        }
    ]
    assert snapshot["coverage_summary"] == {"core": "97.8%"}
    assert snapshot["factor_gate_summary"] == {"approved_count": 12}
    assert "source timeout" not in str(snapshot)
    assert "suggested_action" not in str(snapshot)
    assert "pipeline_status" not in str(snapshot["coverage_summary"])
    assert "failed_jobs" not in str(snapshot["coverage_summary"])
    assert "warnings" not in str(snapshot["coverage_summary"])
    assert "experimental_internal_metric" not in str(snapshot["coverage_summary"])
    assert "internal_confidence" not in str(snapshot["market_state"])
    assert "operator_note" not in str(snapshot["topn_preview"])
    assert "internal_rules" not in str(snapshot["factor_gate_summary"])


def test_build_public_snapshot_ignores_placeholder_market_state(monkeypatch):
    monkeypatch.setattr(
        "stock_research.dashboard.ops_snapshot.build_internal_ops_snapshot",
        lambda service, trade_date=None: {
            "run_window": {},
            "pipeline": {"overall_status": "not_started"},
            "health": {"last_error_summary": None},
            "intervention": {
                "needs_intervention": False,
                "severity": "info",
                "reason_code": "monitor",
                "reason_text": "monitor",
                "suggested_action": None,
            },
            "readiness": {
                "latest_ready_trade_date": "2026-06-23",
                "ready_status": "not_ready",
                "ready_for_dashboard": False,
                "ready_for_publication": False,
                "blocking_issue_count": 0,
            },
            "snapshot_preview": {
                "market_state": {"state": None, "score": None},
                "topn_preview": [],
                "coverage_summary": {},
                "factor_gate_summary": {},
                "published_at": "2026-06-24T08:12:00+08:00",
            },
        },
    )

    snapshot = build_public_snapshot("stock_research", trade_date=date(2026, 6, 24))

    assert snapshot["status"] == "unavailable"
    assert snapshot["market_state"] == {"state": None, "score": None}
