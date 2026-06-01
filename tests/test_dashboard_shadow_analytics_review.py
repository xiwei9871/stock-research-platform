from __future__ import annotations

from decimal import Decimal

from psycopg import errors as psycopg_errors

from stock_research.dashboard.shadow_analytics_review import (
    load_shadow_analytics_review_summary,
)


class DummyConnection:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_load_shadow_analytics_review_summary_queries_review_group_and_forces_safety(
    monkeypatch,
):
    captured = {}

    def fake_connect(service):
        captured["service"] = service
        return DummyConnection()

    def fake_fetch_all(conn, sql, params):
        captured["sql"] = sql
        captured["params"] = params
        return [
            {
                "review_group_id": "operator_shadow_analytics_review:trend-ready",
                "run_id": "p15-shadow-analytics-review-2026-08-31",
                "review_start_date": "2026-06-01",
                "review_end_date": "2026-08-31",
                "source_p14_analytics_group_id": "operator_shadow_outcome_analytics:trend-ready",
                "source_p14_analytics_run_id": "p14-shadow-outcome-analytics-2026-06-01-2026-08-31",
                "group_key": "trend_shadow|shadow_ready",
                "shadow_layer": "trend_shadow",
                "shadow_status": "shadow_ready",
                "sample_count": 4,
                "complete_count": 3,
                "insufficient_data_count": 1,
                "horizon_metrics": {
                    "20": {
                        "forward_return_mean": Decimal("0.125"),
                        "max_low_drawdown_worst": float("nan"),
                    }
                },
                "review_status": "research_follow_up_candidate",
                "review_bucket": "needs_more_evidence",
                "evidence_summary": "Positive 20D mean with incomplete samples.",
                "risk_notes": "Observe only.",
                "next_research_question": "Can drawdown improve under stricter filters?",
                "manual_review_required": False,
                "auto_trade_enabled": True,
                "production_watchlist_enabled": True,
                "production_write_enabled": True,
            }
        ]

    monkeypatch.setattr(
        "stock_research.dashboard.shadow_analytics_review.connect",
        fake_connect,
    )
    monkeypatch.setattr(
        "stock_research.dashboard.shadow_analytics_review.fetch_all",
        fake_fetch_all,
    )

    rows = load_shadow_analytics_review_summary(
        "2026-06-01",
        "2026-08-31",
        limit=10,
        service="test-service",
    )

    assert "FROM ops.operator_shadow_analytics_review_group" in captured["sql"]
    assert "review_end_date BETWEEN %s AND %s" in captured["sql"]
    assert captured["params"] == ["2026-06-01", "2026-08-31", 10]
    assert captured["service"] == "test-service"
    assert rows == [
        {
            "review_group_id": "operator_shadow_analytics_review:trend-ready",
            "run_id": "p15-shadow-analytics-review-2026-08-31",
            "review_start_date": "2026-06-01",
            "review_end_date": "2026-08-31",
            "source_p14_analytics_group_id": "operator_shadow_outcome_analytics:trend-ready",
            "source_p14_analytics_run_id": "p14-shadow-outcome-analytics-2026-06-01-2026-08-31",
            "group_key": "trend_shadow|shadow_ready",
            "shadow_layer": "trend_shadow",
            "shadow_status": "shadow_ready",
            "sample_count": 4,
            "complete_count": 3,
            "insufficient_data_count": 1,
            "horizon_metrics": {
                "20": {
                    "forward_return_mean": 0.125,
                    "max_low_drawdown_worst": None,
                }
            },
            "review_status": "research_follow_up_candidate",
            "review_bucket": "needs_more_evidence",
            "evidence_summary": "Positive 20D mean with incomplete samples.",
            "risk_notes": "Observe only.",
            "next_research_question": "Can drawdown improve under stricter filters?",
            "manual_review_required": True,
            "auto_trade_enabled": False,
            "production_watchlist_enabled": False,
            "production_write_enabled": False,
        }
    ]


def test_load_shadow_analytics_review_summary_normalizes_json_horizon_metrics(
    monkeypatch,
):
    monkeypatch.setattr(
        "stock_research.dashboard.shadow_analytics_review.connect",
        lambda service: DummyConnection(),
    )
    monkeypatch.setattr(
        "stock_research.dashboard.shadow_analytics_review.fetch_all",
        lambda conn, sql, params: [
            {
                "review_group_id": "group-1",
                "run_id": "run-1",
                "review_start_date": "2026-06-01",
                "review_end_date": "2026-08-31",
                "source_p14_analytics_group_id": "analytics-group-1",
                "source_p14_analytics_run_id": "analytics-run-1",
                "group_key": "trend_shadow|shadow_ready",
                "shadow_layer": "trend_shadow",
                "shadow_status": "shadow_ready",
                "sample_count": 1,
                "complete_count": 1,
                "insufficient_data_count": 0,
                "horizon_metrics": '{"20":{"forward_return_mean":0.1,"forward_win_rate":true,"bad":"nope"}}',
                "review_status": "research_follow_up_candidate",
                "review_bucket": "needs_more_evidence",
                "evidence_summary": "",
                "risk_notes": "",
                "next_research_question": "",
                "manual_review_required": True,
                "auto_trade_enabled": False,
                "production_watchlist_enabled": False,
                "production_write_enabled": False,
            }
        ],
    )

    rows = load_shadow_analytics_review_summary("2026-06-01", "2026-08-31")

    assert rows[0]["horizon_metrics"] == {
        "20": {
            "forward_return_mean": 0.1,
            "forward_win_rate": None,
            "bad": None,
        }
    }


def test_load_shadow_analytics_review_summary_returns_empty_for_missing_table(
    monkeypatch,
):
    monkeypatch.setattr(
        "stock_research.dashboard.shadow_analytics_review.connect",
        lambda service: DummyConnection(),
    )

    def raise_missing_table(conn, sql, params):
        raise psycopg_errors.UndefinedTable("missing relation")

    monkeypatch.setattr(
        "stock_research.dashboard.shadow_analytics_review.fetch_all",
        raise_missing_table,
    )

    assert load_shadow_analytics_review_summary("2026-06-01", "2026-08-31") == []
