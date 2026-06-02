import json
from pathlib import Path

import pytest

from stock_research.operator_decision.shadow_follow_up_queue import (
    FOLLOW_UP_STATUSES,
    build_shadow_follow_up_queue,
    build_shadow_follow_up_queue_from_rows,
    write_shadow_follow_up_queue,
)


def _decision_group(**overrides):
    row = {
        "decision_group_id": "operator_shadow_review_decision:p16-run:trend-ready",
        "run_id": "p16-shadow-review-decisions-2026-08-29",
        "source_p15_review_group_id": "operator_shadow_analytics_review:p15-run:trend-ready",
        "source_p15_review_run_id": "p15-shadow-analytics-review-2026-06-30-2026-08-29",
        "source_p14_analytics_group_id": "operator_shadow_outcome_analytics:p14-run:trend-ready",
        "source_p14_analytics_run_id": "p14-shadow-outcome-analytics-2026-06-30-2026-08-29",
        "group_key": "trend_shadow|shadow_ready",
        "shadow_layer": "trend_shadow",
        "shadow_status": "shadow_ready",
        "sample_count": 30,
        "complete_count": 28,
        "insufficient_data_count": 2,
        "review_status": "needs_more_data",
        "review_bucket": "data_needed",
        "decision_status": "request_more_data",
        "decision_bucket": "data_needed",
        "decision_reason": "P15 review needs more data.",
        "required_next_action": "Collect additional outcome or data-quality evidence.",
        "evidence_summary": "single sample is not enough",
        "risk_notes": "data coverage may be incomplete",
        "next_research_question": "Does the group remain stable with more samples?",
        "manual_review_required": True,
        "auto_trade_enabled": False,
        "production_watchlist_enabled": False,
        "production_write_enabled": False,
    }
    row.update(overrides)
    return row


def test_build_shadow_follow_up_queue_maps_p16_decisions_to_follow_up_items():
    rows = [
        _decision_group(decision_group_id="p16:observe", decision_status="continue_shadow_observation"),
        _decision_group(decision_group_id="p16:data", decision_status="request_more_data"),
        _decision_group(decision_group_id="p16:research", decision_status="open_research_follow_up"),
        _decision_group(decision_group_id="p16:deprioritize", decision_status="deprioritize_shadow_group"),
    ]

    queue = build_shadow_follow_up_queue_from_rows(
        rows,
        run_id="p17-shadow-follow-up-queue-2026-08-29",
        follow_up_date="2026-08-29",
        operator_id="operator",
    )

    items = {row["source_p16_decision_group_id"]: row for row in queue["items"]}
    assert items["p16:observe"]["follow_up_status"] == "observe_shadow_group"
    assert items["p16:observe"]["priority_bucket"] == "normal"
    assert items["p16:data"]["follow_up_status"] == "collect_more_evidence"
    assert items["p16:data"]["priority_bucket"] == "high"
    assert items["p16:data"]["required_input"] == "Additional outcome or data-quality evidence"
    assert items["p16:research"]["follow_up_status"] == "open_research_ticket"
    assert items["p16:research"]["priority_bucket"] == "high"
    assert items["p16:deprioritize"]["follow_up_status"] == "deprioritized"
    assert items["p16:deprioritize"]["priority_bucket"] == "low"
    assert items["p16:research"]["manual_review_required"] is True
    assert items["p16:research"]["auto_trade_enabled"] is False
    assert items["p16:research"]["production_watchlist_enabled"] is False
    assert items["p16:research"]["production_write_enabled"] is False
    assert sorted(FOLLOW_UP_STATUSES) == sorted(
        [
            "observe_shadow_group",
            "collect_more_evidence",
            "open_research_ticket",
            "deprioritized",
        ]
    )


def test_build_shadow_follow_up_queue_preserves_lineage_and_writes_artifacts(tmp_path):
    queue = build_shadow_follow_up_queue(
        p16_decisions={
            "run_id": "p16-shadow-review-decisions-2026-08-29",
            "groups": [_decision_group()],
            "manual_review_required": True,
            "auto_trade_enabled": False,
            "production_watchlist_enabled": False,
            "production_write_enabled": False,
        },
        run_id="p17-shadow-follow-up-queue-2026-08-29",
        follow_up_date="2026-08-29",
        operator_id="operator",
    )

    assert queue["status"] == "shadow_follow_up_queue_ready"
    assert queue["source_p16_decision_run_ids"] == ["p16-shadow-review-decisions-2026-08-29"]
    assert queue["operator_id"] == "operator"
    assert queue["item_count"] == 1
    item = queue["items"][0]
    assert item["source_p16_decision_group_id"] == "operator_shadow_review_decision:p16-run:trend-ready"
    assert item["source_p15_review_run_id"] == "p15-shadow-analytics-review-2026-06-30-2026-08-29"
    assert item["source_p14_analytics_run_id"] == "p14-shadow-outcome-analytics-2026-06-30-2026-08-29"

    paths = write_shadow_follow_up_queue(queue, tmp_path)
    assert Path(paths["json_path"]).exists()
    assert Path(paths["items_csv_path"]).exists()
    assert Path(paths["markdown_path"]).exists()
    payload = json.loads(Path(paths["json_path"]).read_text(encoding="utf-8"))
    assert payload["items"][0]["follow_up_status"] == "collect_more_evidence"
    assert "collect_more_evidence" in Path(paths["markdown_path"]).read_text(encoding="utf-8")


def test_build_shadow_follow_up_queue_rejects_production_enabled_group():
    row = _decision_group(production_watchlist_enabled=True)

    with pytest.raises(ValueError, match="production_watchlist_not_allowed"):
        build_shadow_follow_up_queue_from_rows(
            [row],
            run_id="p17-shadow-follow-up-queue-2026-08-29",
            follow_up_date="2026-08-29",
            operator_id="operator",
        )


def test_build_shadow_follow_up_queue_rejects_unsafe_execution_fields():
    row = _decision_group(order_id="unsafe")

    with pytest.raises(ValueError, match="unsafe_execution_field"):
        build_shadow_follow_up_queue_from_rows(
            [row],
            run_id="p17-shadow-follow-up-queue-2026-08-29",
            follow_up_date="2026-08-29",
            operator_id="operator",
        )


def test_build_shadow_follow_up_queue_rejects_unknown_decision_status():
    row = _decision_group(decision_status="approve_production")

    with pytest.raises(ValueError, match="unknown_decision_status"):
        build_shadow_follow_up_queue_from_rows(
            [row],
            run_id="p17-shadow-follow-up-queue-2026-08-29",
            follow_up_date="2026-08-29",
            operator_id="operator",
        )
