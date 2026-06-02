from __future__ import annotations

from psycopg import errors as psycopg_errors

from stock_research.dashboard.shadow_follow_up_queue import (
    load_shadow_follow_up_queue_summary,
)


class DummyConnection:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_load_shadow_follow_up_queue_summary_queries_items_and_forces_safety(
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
                "follow_up_item_id": "operator_shadow_follow_up:trend-ready",
                "run_id": "p17-shadow-follow-up-queue-2026-08-31",
                "follow_up_date": "2026-08-31",
                "source_p16_decision_group_id": "operator_shadow_review_decision:trend-ready",
                "source_p16_decision_run_id": "p16-shadow-review-decisions-2026-08-31",
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
                "review_status": "needs_more_data",
                "review_bucket": "data_needed",
                "decision_status": "request_more_data",
                "decision_bucket": "data_needed",
                "follow_up_status": "collect_more_evidence",
                "priority_bucket": "high",
                "required_input": "Additional outcome or data-quality evidence",
                "follow_up_reason": "P16 status maps to evidence collection.",
                "decision_reason": "P15 status maps to more data.",
                "required_next_action": "Collect additional evidence.",
                "evidence_summary": "Single sample is not enough.",
                "risk_notes": "Data coverage may be incomplete.",
                "next_research_question": "Does the group remain stable with more samples?",
                "manual_review_required": False,
                "auto_trade_enabled": True,
                "production_watchlist_enabled": True,
                "production_write_enabled": True,
            }
        ]

    monkeypatch.setattr(
        "stock_research.dashboard.shadow_follow_up_queue.connect",
        fake_connect,
    )
    monkeypatch.setattr(
        "stock_research.dashboard.shadow_follow_up_queue.fetch_all",
        fake_fetch_all,
    )

    rows = load_shadow_follow_up_queue_summary(
        "2026-06-01",
        "2026-08-31",
        limit=10,
        service="test-service",
    )

    assert "FROM ops.operator_shadow_follow_up_item" in captured["sql"]
    assert "follow_up_date BETWEEN %s AND %s" in captured["sql"]
    assert captured["params"] == ["2026-06-01", "2026-08-31", 10]
    assert captured["service"] == "test-service"
    assert rows[0]["follow_up_status"] == "collect_more_evidence"
    assert rows[0]["priority_bucket"] == "high"
    assert rows[0]["required_input"] == "Additional outcome or data-quality evidence"
    assert rows[0]["manual_review_required"] is True
    assert rows[0]["auto_trade_enabled"] is False
    assert rows[0]["production_watchlist_enabled"] is False
    assert rows[0]["production_write_enabled"] is False


def test_load_shadow_follow_up_queue_summary_returns_empty_for_missing_table(
    monkeypatch,
):
    monkeypatch.setattr(
        "stock_research.dashboard.shadow_follow_up_queue.connect",
        lambda service: DummyConnection(),
    )

    def raise_missing_table(conn, sql, params):
        raise psycopg_errors.UndefinedTable("missing relation")

    monkeypatch.setattr(
        "stock_research.dashboard.shadow_follow_up_queue.fetch_all",
        raise_missing_table,
    )

    assert load_shadow_follow_up_queue_summary("2026-06-01", "2026-08-31") == []
