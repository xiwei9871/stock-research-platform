from datetime import date, datetime

from stock_research.dashboard.ops_snapshot import (
    build_internal_ops_snapshot,
    build_public_snapshot,
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
