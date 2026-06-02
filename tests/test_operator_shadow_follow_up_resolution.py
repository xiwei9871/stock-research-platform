import json
from pathlib import Path

import pytest

from stock_research.operator_decision.shadow_follow_up_resolution import (
    RESOLUTION_STATUSES,
    build_shadow_follow_up_resolution,
    build_shadow_follow_up_resolution_from_rows,
    write_shadow_follow_up_resolution,
)


def _follow_up_item(**overrides):
    row = {
        "follow_up_item_id": "operator_shadow_follow_up:p17-run:trend-ready",
        "run_id": "p17-shadow-follow-up-queue-2026-08-29",
        "source_p16_decision_group_id": "operator_shadow_review_decision:p16-run:trend-ready",
        "source_p16_decision_run_id": "p16-shadow-review-decisions-2026-08-29",
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
        "follow_up_status": "collect_more_evidence",
        "priority_bucket": "high",
        "required_input": "Additional outcome or data-quality evidence",
        "follow_up_reason": "P16 status maps to evidence collection.",
        "decision_reason": "P15 review needs more data.",
        "required_next_action": "Collect additional evidence.",
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


def test_build_shadow_follow_up_resolution_maps_p17_statuses_to_review_resolutions():
    rows = [
        _follow_up_item(follow_up_item_id="p17:data", follow_up_status="collect_more_evidence", priority_bucket="high"),
        _follow_up_item(follow_up_item_id="p17:research", follow_up_status="open_research_ticket", priority_bucket="high"),
        _follow_up_item(follow_up_item_id="p17:observe", follow_up_status="observe_shadow_group", priority_bucket="normal"),
        _follow_up_item(follow_up_item_id="p17:closed", follow_up_status="deprioritized", priority_bucket="low"),
    ]

    resolution = build_shadow_follow_up_resolution_from_rows(
        rows,
        run_id="p18-shadow-follow-up-resolution-2026-08-29",
        resolution_date="2026-08-29",
        operator_id="operator",
    )

    items = {row["source_p17_follow_up_item_id"]: row for row in resolution["items"]}
    assert items["p17:data"]["resolution_status"] == "stale_unresolved"
    assert items["p17:data"]["resolution_bucket"] == "needs_operator_review"
    assert items["p17:data"]["recommended_resolution_action"] == "Review whether the requested evidence has been collected."
    assert items["p17:research"]["resolution_status"] == "research_ticket_opened"
    assert items["p17:research"]["resolution_bucket"] == "research_follow_up"
    assert items["p17:observe"]["resolution_status"] == "continue_observing"
    assert items["p17:observe"]["resolution_bucket"] == "observe"
    assert items["p17:closed"]["resolution_status"] == "deprioritized_closed"
    assert items["p17:closed"]["resolution_bucket"] == "closed_low_priority"
    assert items["p17:research"]["manual_review_required"] is True
    assert items["p17:research"]["auto_trade_enabled"] is False
    assert items["p17:research"]["production_watchlist_enabled"] is False
    assert items["p17:research"]["production_write_enabled"] is False
    assert sorted(RESOLUTION_STATUSES) == sorted(
        [
            "evidence_collected",
            "research_ticket_opened",
            "continue_observing",
            "deprioritized_closed",
            "stale_unresolved",
        ]
    )


def test_build_shadow_follow_up_resolution_preserves_lineage_and_writes_artifacts(tmp_path):
    resolution = build_shadow_follow_up_resolution(
        p17_follow_up={
            "run_id": "p17-shadow-follow-up-queue-2026-08-29",
            "items": [_follow_up_item()],
            "manual_review_required": True,
            "auto_trade_enabled": False,
            "production_watchlist_enabled": False,
            "production_write_enabled": False,
        },
        run_id="p18-shadow-follow-up-resolution-2026-08-29",
        resolution_date="2026-08-29",
        operator_id="operator",
    )

    assert resolution["status"] == "shadow_follow_up_resolution_ready"
    assert resolution["source_p17_follow_up_run_ids"] == ["p17-shadow-follow-up-queue-2026-08-29"]
    assert resolution["operator_id"] == "operator"
    assert resolution["item_count"] == 1
    item = resolution["items"][0]
    assert item["source_p17_follow_up_item_id"] == "operator_shadow_follow_up:p17-run:trend-ready"
    assert item["source_p16_decision_run_id"] == "p16-shadow-review-decisions-2026-08-29"
    assert item["source_p15_review_run_id"] == "p15-shadow-analytics-review-2026-06-30-2026-08-29"
    assert item["source_p14_analytics_run_id"] == "p14-shadow-outcome-analytics-2026-06-30-2026-08-29"

    paths = write_shadow_follow_up_resolution(resolution, tmp_path)
    assert Path(paths["json_path"]).exists()
    assert Path(paths["items_csv_path"]).exists()
    assert Path(paths["markdown_path"]).exists()
    payload = json.loads(Path(paths["json_path"]).read_text(encoding="utf-8"))
    assert payload["items"][0]["resolution_status"] == "stale_unresolved"
    assert "stale_unresolved" in Path(paths["markdown_path"]).read_text(encoding="utf-8")


def test_build_shadow_follow_up_resolution_rejects_production_enabled_item():
    row = _follow_up_item(production_watchlist_enabled=True)

    with pytest.raises(ValueError, match="production_watchlist_not_allowed"):
        build_shadow_follow_up_resolution_from_rows(
            [row],
            run_id="p18-shadow-follow-up-resolution-2026-08-29",
            resolution_date="2026-08-29",
            operator_id="operator",
        )


def test_build_shadow_follow_up_resolution_rejects_unsafe_execution_fields():
    row = _follow_up_item(order_id="unsafe")

    with pytest.raises(ValueError, match="unsafe_execution_field"):
        build_shadow_follow_up_resolution_from_rows(
            [row],
            run_id="p18-shadow-follow-up-resolution-2026-08-29",
            resolution_date="2026-08-29",
            operator_id="operator",
        )


def test_build_shadow_follow_up_resolution_rejects_unknown_follow_up_status():
    row = _follow_up_item(follow_up_status="approve_production")

    with pytest.raises(ValueError, match="unknown_follow_up_status"):
        build_shadow_follow_up_resolution_from_rows(
            [row],
            run_id="p18-shadow-follow-up-resolution-2026-08-29",
            resolution_date="2026-08-29",
            operator_id="operator",
        )
