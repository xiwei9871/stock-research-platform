from datetime import date, datetime

from stock_research.dashboard.ops_snapshot import (
    build_internal_ops_snapshot,
    build_public_snapshot,
    _load_pipeline_status_context,
    load_ops_stage_details,
)


def test_build_internal_ops_snapshot_shapes_payload(monkeypatch):
    monkeypatch.setattr(
        "stock_research.dashboard.ops_snapshot._load_pipeline_status_context",
        lambda service, trade_date: {
            "data_status": {
                "latest_ready_trade_date": "2026-06-23",
                "current_trade_date": "2026-06-23",
                "pipeline_status": "READY",
                "daily_status": "success",
                "minute5_status": "success",
                "deps_status": "success",
                "failed_jobs": [],
                "warnings": [],
                "last_updated_at": "2026-06-23T20:43:10+08:00",
            },
            "requested_trade_date": "2026-06-23",
            "status_trade_date": "2026-06-23",
            "latest_available_trade_date": "2026-06-23",
            "matches_requested_trade_date": True,
        },
    )
    monkeypatch.setattr(
        "stock_research.dashboard.ops_snapshot.load_intraday_status",
        lambda service, trade_date: {"market_state": {"state": "warm", "score": 74.2}},
    )
    monkeypatch.setattr(
        "stock_research.dashboard.ops_snapshot.summarize_operational_health",
        lambda trade_date, service: {"status": "ok", "alert_count": 0, "last_error_summary": None},
    )
    monkeypatch.setattr(
        "stock_research.dashboard.ops_snapshot.load_ops_stage_details",
        lambda service, trade_date: [
            {
                "stage": "daily",
                "status": "success",
                "started_at": None,
                "updated_at": None,
                "error_summary": None,
            }
        ],
    )
    monkeypatch.setattr(
        "stock_research.dashboard.ops_snapshot._now_in_timezone",
        lambda timezone_name: "2026-06-24T10:00:00+08:00",
    )

    payload = build_internal_ops_snapshot("stock_research", trade_date=date(2026, 6, 23))

    assert sorted(payload.keys()) == ["health", "intervention", "pipeline", "readiness", "run_window", "snapshot_preview"]
    assert payload["pipeline"]["overall_status"] == "ready"
    assert payload["readiness"]["ready_status"] == "ready"


def test_build_public_snapshot_uses_release_safe_shape(monkeypatch):
    monkeypatch.setattr(
        "stock_research.dashboard.ops_snapshot.build_internal_ops_snapshot",
        lambda service="stock_research", trade_date=None: {
            "readiness": {
                "latest_ready_trade_date": "2026-06-23",
                "ready_for_publication": True,
                "ready_status": "ready",
            },
            "snapshot_preview": {
                "market_state": {"state": "warm", "score": 74.2, "internal_reason": "hidden"},
                "topn_preview": [
                    {
                        "asset_id": "000001.SZ",
                        "stock_name": "平安银行",
                        "score_total": 88.5,
                        "debug": "drop",
                    }
                ],
                "coverage_summary": {"core": "daily/minute ready", "internal": "drop"},
                "factor_gate_summary": {"approved_count": 5, "raw_count": 30},
                "published_at": "2026-06-23T20:43:10+08:00",
            },
        },
    )

    payload = build_public_snapshot("stock_research", trade_date=date(2026, 6, 23))

    assert sorted(payload.keys()) == [
        "coverage_summary",
        "factor_gate_summary",
        "latest_ready_trade_date",
        "market_state",
        "notes",
        "published_at",
        "status",
        "status_text",
        "topn_preview",
        "trade_date",
    ]
    assert payload["market_state"] == {"state": "warm", "score": 74.2}
    assert payload["topn_preview"] == [{"asset_id": "000001.SZ", "stock_name": "平安银行", "score_total": 88.5}]


def test_load_ops_stage_details_returns_normalized_items(monkeypatch):
    class _DummyConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr("stock_research.dashboard.ops_snapshot.connect", lambda service: _DummyConnection())
    monkeypatch.setattr(
        "stock_research.dashboard.ops_snapshot.fetch_all",
        lambda conn, sql, params=None: [
            {
                "stage": "daily",
                "status": "success",
                "started_at": datetime(2026, 6, 23, 9, 30),
                "updated_at": datetime(2026, 6, 23, 9, 45),
                "error_summary": None,
            }
        ],
    )

    items = load_ops_stage_details("stock_research", trade_date=date(2026, 6, 23))

    assert items == [
        {
            "stage": "daily",
            "status": "success",
            "started_at": "2026-06-23T09:30:00",
            "updated_at": "2026-06-23T09:45:00",
            "error_summary": None,
        }
    ]


def test_build_internal_ops_snapshot_defaults_trade_date_from_timezone_helper(monkeypatch):
    captured = {}

    monkeypatch.setattr(
        "stock_research.dashboard.ops_snapshot._today_in_timezone",
        lambda timezone_name: date(2026, 6, 24),
    )
    monkeypatch.setattr(
        "stock_research.dashboard.ops_snapshot._load_pipeline_status_context",
        lambda service, trade_date: {
            "data_status": {
                "latest_ready_trade_date": "2026-06-24",
                "current_trade_date": trade_date.isoformat(),
                "pipeline_status": "READY",
                "daily_status": "success",
                "minute5_status": "success",
                "deps_status": "success",
                "failed_jobs": [],
                "warnings": [],
                "last_updated_at": "2026-06-24T20:43:10+08:00",
            },
            "requested_trade_date": trade_date.isoformat(),
            "status_trade_date": trade_date.isoformat(),
            "latest_available_trade_date": trade_date.isoformat(),
            "matches_requested_trade_date": True,
        },
    )
    def fake_intraday_status(service, trade_date):
        captured["intraday_trade_date"] = trade_date
        return {"market_state": {}}

    def fake_health_summary(trade_date, service):
        captured["health_trade_date"] = trade_date
        return {"status": "ok", "alert_count": 0, "last_error_summary": None}

    def fake_stage_details(service, trade_date):
        captured["stages_trade_date"] = trade_date
        return []

    monkeypatch.setattr(
        "stock_research.dashboard.ops_snapshot.load_intraday_status",
        fake_intraday_status,
    )
    monkeypatch.setattr(
        "stock_research.dashboard.ops_snapshot.summarize_operational_health",
        fake_health_summary,
    )
    monkeypatch.setattr(
        "stock_research.dashboard.ops_snapshot.load_ops_stage_details",
        fake_stage_details,
    )
    monkeypatch.setattr(
        "stock_research.dashboard.ops_snapshot._now_in_timezone",
        lambda timezone_name: "2026-06-24T10:00:00+08:00",
    )

    payload = build_internal_ops_snapshot("stock_research")

    assert payload["run_window"]["trade_date"] == "2026-06-24"
    assert captured["intraday_trade_date"] == date(2026, 6, 24)
    assert captured["health_trade_date"] == "2026-06-24"
    assert captured["stages_trade_date"] == date(2026, 6, 24)


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
        lambda service, trade_date: {"market_state": {"state": "neutral", "score": 0.11}},
    )
    monkeypatch.setattr(
        "stock_research.dashboard.ops_snapshot.summarize_operational_health",
        lambda trade_date, service: {"status": "alert", "alert_count": 2, "last_error_summary": None},
    )
    monkeypatch.setattr(
        "stock_research.dashboard.ops_snapshot.load_ops_stage_details",
        lambda service, trade_date: [
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
        lambda timezone_name: "2026-06-24T08:10:00+08:00",
    )

    payload = build_internal_ops_snapshot("stock_research", trade_date=date(2026, 6, 24))

    assert payload["pipeline"]["overall_status"] == "delayed"
    assert payload["health"]["has_alerts"] is True
    assert payload["readiness"]["blocking_issue_count"] == 2
    assert payload["readiness"]["ready_for_publication"] is False
    assert payload["intervention"]["severity"] == "warning"


def test_load_ops_stage_details_defaults_to_latest_trade_date_when_missing(monkeypatch):
    captured = []

    class _DummyConnection:
        def __enter__(self):
            return self

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

    monkeypatch.setattr("stock_research.dashboard.ops_snapshot.connect", lambda service: _DummyConnection())
    monkeypatch.setattr("stock_research.dashboard.ops_snapshot.fetch_all", fake_fetch_all)

    items = load_ops_stage_details("stock_research")

    assert items == [
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
    class _DummyConnection:
        def __enter__(self):
            return self

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
                    "updated_at": datetime(2026, 6, 24, 20, 0),
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
                    "updated_at": datetime(2026, 6, 24, 20, 0),
                }
            ]
        raise AssertionError(sql)

    monkeypatch.setattr("stock_research.dashboard.ops_snapshot.connect", lambda service: _DummyConnection())
    monkeypatch.setattr("stock_research.dashboard.ops_snapshot.fetch_all", fake_fetch_all)

    context = _load_pipeline_status_context("stock_research", date(2026, 6, 24))

    assert context["matches_requested_trade_date"] is True
    assert context["status_trade_date"] == "2026-06-24"
    assert context["latest_available_trade_date"] == "2026-06-24"
    assert context["data_status"]["pipeline_status"] == "READY"
    assert calls[0][1] == [date(2026, 6, 24)]


def test_build_public_snapshot_redacts_internal_fields_from_real_internal_shape(monkeypatch):
    monkeypatch.setattr(
        "stock_research.dashboard.ops_snapshot._load_pipeline_status_context",
        lambda service, trade_date: {
            "data_status": {
                "latest_ready_trade_date": "2026-06-23",
                "current_trade_date": trade_date.isoformat(),
                "pipeline_status": "READY",
                "daily_status": "success",
                "minute5_status": "success",
                "deps_status": "success",
                "failed_jobs": [{"error_summary": "should not leak"}],
                "warnings": ["internal warning"],
                "last_updated_at": "2026-06-23T20:43:10+08:00",
            },
            "requested_trade_date": trade_date.isoformat(),
            "status_trade_date": trade_date.isoformat(),
            "latest_available_trade_date": trade_date.isoformat(),
            "matches_requested_trade_date": True,
        },
    )
    monkeypatch.setattr(
        "stock_research.dashboard.ops_snapshot.load_intraday_status",
        lambda service, trade_date: {
            "market_state": {"state": "warm", "score": 74.2, "internal_reason": "hidden"},
        },
    )
    monkeypatch.setattr(
        "stock_research.dashboard.ops_snapshot.summarize_operational_health",
        lambda trade_date, service: {
            "status": "ok",
            "alert_count": 0,
            "last_error_summary": "source timeout",
        },
    )
    monkeypatch.setattr(
        "stock_research.dashboard.ops_snapshot.load_ops_stage_details",
        lambda service, trade_date: [
            {
                "stage": "daily",
                "status": "success",
                "started_at": None,
                "updated_at": None,
                "error_summary": "hidden",
            }
        ],
    )
    monkeypatch.setattr(
        "stock_research.dashboard.ops_snapshot._now_in_timezone",
        lambda timezone_name: "2026-06-24T10:00:00+08:00",
    )

    payload = build_public_snapshot("stock_research", trade_date=date(2026, 6, 24))

    assert payload["coverage_summary"] == {"core": "daily success, minute5 success, deps success"}
    assert payload["market_state"] == {"state": "warm", "score": 74.2}
    assert payload["topn_preview"] == []
    assert payload["factor_gate_summary"] == {}
    assert "internal_reason" not in str(payload["market_state"])
    assert "source timeout" not in str(payload)
    assert "failed_jobs" not in str(payload["coverage_summary"])
    assert "warnings" not in str(payload["coverage_summary"])


def test_build_public_snapshot_defaults_trade_date_from_timezone_helper(monkeypatch):
    captured = {}

    monkeypatch.setattr(
        "stock_research.dashboard.ops_snapshot._today_in_timezone",
        lambda timezone_name: date(2026, 6, 24),
    )
    def fake_internal_snapshot(service="stock_research", trade_date=None):
        captured["trade_date"] = trade_date
        return {
            "readiness": {
                "latest_ready_trade_date": "2026-06-24",
                "ready_for_publication": True,
                "ready_status": "ready",
            },
            "snapshot_preview": {
                "market_state": {"state": "warm", "score": 74.2},
                "topn_preview": [],
                "coverage_summary": {"core": "daily success, minute5 success, deps success"},
                "factor_gate_summary": {},
                "published_at": "2026-06-24T20:43:10+08:00",
            },
        }

    monkeypatch.setattr(
        "stock_research.dashboard.ops_snapshot.build_internal_ops_snapshot",
        fake_internal_snapshot,
    )

    payload = build_public_snapshot("stock_research")

    assert captured["trade_date"] == date(2026, 6, 24)
    assert payload["trade_date"] == "2026-06-24"
