from __future__ import annotations

from psycopg import errors as psycopg_errors

from stock_research.dashboard.shadow_review_decisions import (
    load_shadow_review_decision_summary,
)


class DummyConnection:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_load_shadow_review_decision_summary_queries_decision_group_and_forces_safety(
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
                "decision_group_id": "operator_shadow_review_decision:trend-ready",
                "run_id": "p16-shadow-review-decisions-2026-08-31",
                "decision_date": "2026-08-31",
                "source_p15_review_group_id": "operator_shadow_analytics_review:trend-ready",
                "source_p15_review_run_id": "p15-shadow-analytics-review-2026-08-31",
                "source_p14_analytics_group_id": "operator_shadow_outcome_analytics:trend-ready",
                "source_p14_analytics_run_id": "p14-shadow-outcome-analytics-2026-06-01-2026-08-31",
                "group_key": "trend_shadow|shadow_ready",
                "shadow_layer": "trend_shadow",
                "shadow_status": "shadow_ready",
                "sample_count": 4,
                "complete_count": 3,
                "insufficient_data_count": 1,
                "review_status": "research_follow_up_candidate",
                "review_bucket": "needs_more_evidence",
                "decision_status": "open_research_follow_up",
                "decision_bucket": "research_follow_up",
                "decision_reason": "P15 status maps to follow-up.",
                "required_next_action": "Create a separately scoped research follow-up.",
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
        "stock_research.dashboard.shadow_review_decisions.connect",
        fake_connect,
    )
    monkeypatch.setattr(
        "stock_research.dashboard.shadow_review_decisions.fetch_all",
        fake_fetch_all,
    )

    rows = load_shadow_review_decision_summary(
        "2026-06-01",
        "2026-08-31",
        limit=10,
        service="test-service",
    )

    assert "FROM ops.operator_shadow_review_decision_group" in captured["sql"]
    assert "decision_date BETWEEN %s AND %s" in captured["sql"]
    assert captured["params"] == ["2026-06-01", "2026-08-31", 10]
    assert captured["service"] == "test-service"
    assert rows == [
        {
            "decision_group_id": "operator_shadow_review_decision:trend-ready",
            "run_id": "p16-shadow-review-decisions-2026-08-31",
            "decision_date": "2026-08-31",
            "source_p15_review_group_id": "operator_shadow_analytics_review:trend-ready",
            "source_p15_review_run_id": "p15-shadow-analytics-review-2026-08-31",
            "source_p14_analytics_group_id": "operator_shadow_outcome_analytics:trend-ready",
            "source_p14_analytics_run_id": "p14-shadow-outcome-analytics-2026-06-01-2026-08-31",
            "group_key": "trend_shadow|shadow_ready",
            "shadow_layer": "trend_shadow",
            "shadow_status": "shadow_ready",
            "sample_count": 4,
            "complete_count": 3,
            "insufficient_data_count": 1,
            "review_status": "research_follow_up_candidate",
            "review_bucket": "needs_more_evidence",
            "decision_status": "open_research_follow_up",
            "decision_bucket": "research_follow_up",
            "decision_reason": "P15 status maps to follow-up.",
            "required_next_action": "Create a separately scoped research follow-up.",
            "evidence_summary": "Positive 20D mean with incomplete samples.",
            "risk_notes": "Observe only.",
            "next_research_question": "Can drawdown improve under stricter filters?",
            "manual_review_required": True,
            "auto_trade_enabled": False,
            "production_watchlist_enabled": False,
            "production_write_enabled": False,
        }
    ]


def test_load_shadow_review_decision_summary_returns_empty_for_missing_table(
    monkeypatch,
):
    monkeypatch.setattr(
        "stock_research.dashboard.shadow_review_decisions.connect",
        lambda service: DummyConnection(),
    )

    def raise_missing_table(conn, sql, params):
        raise psycopg_errors.UndefinedTable("missing relation")

    monkeypatch.setattr(
        "stock_research.dashboard.shadow_review_decisions.fetch_all",
        raise_missing_table,
    )

    assert load_shadow_review_decision_summary("2026-06-01", "2026-08-31") == []
