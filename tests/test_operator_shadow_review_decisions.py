import hashlib
import json
from pathlib import Path

import pytest

from stock_research.operator_decision.shadow_review_decisions import (
    DECISION_STATUSES,
    build_shadow_review_decisions,
    build_shadow_review_decisions_from_rows,
    write_shadow_review_decisions,
)


def _review_group(**overrides):
    row = {
        "review_group_id": "operator_shadow_analytics_review:p15-run:trend-ready",
        "run_id": "p15-shadow-analytics-review-2026-06-30-2026-08-29",
        "source_p14_analytics_group_id": "operator_shadow_outcome_analytics:p14:trend-ready",
        "source_p14_analytics_run_id": "p14-shadow-outcome-analytics-2026-06-30-2026-08-29",
        "group_key": "trend_shadow|shadow_ready",
        "shadow_layer": "trend_shadow",
        "shadow_status": "shadow_ready",
        "sample_count": 30,
        "complete_count": 28,
        "insufficient_data_count": 2,
        "review_status": "research_follow_up_candidate",
        "review_bucket": "follow_up",
        "evidence_summary": "adequate positive evidence",
        "risk_notes": "requires separate research validation",
        "next_research_question": "Should this group be researched further?",
        "manual_review_required": True,
        "auto_trade_enabled": False,
        "production_watchlist_enabled": False,
        "production_write_enabled": False,
    }
    row.update(overrides)
    return row


def test_build_shadow_review_decisions_maps_p15_statuses_to_p16_decisions():
    rows = [
        _review_group(review_group_id="p15:needs-data", review_status="needs_more_data"),
        _review_group(review_group_id="p15:data-quality", review_status="investigate_data_quality"),
        _review_group(review_group_id="p15:follow-up", review_status="research_follow_up_candidate"),
        _review_group(review_group_id="p15:deprioritize", review_status="deprioritize_review"),
        _review_group(review_group_id="p15:observe", review_status="continue_observing"),
    ]

    decisions = build_shadow_review_decisions_from_rows(
        rows,
        run_id="p16-shadow-review-decisions-2026-08-29",
        decision_date="2026-08-29",
        operator_id="operator",
    )

    groups = {row["source_p15_review_group_id"]: row for row in decisions["groups"]}
    assert groups["p15:needs-data"]["decision_status"] == "request_more_data"
    assert groups["p15:data-quality"]["decision_status"] == "request_more_data"
    assert groups["p15:follow-up"]["decision_status"] == "open_research_follow_up"
    assert groups["p15:deprioritize"]["decision_status"] == "deprioritize_shadow_group"
    assert groups["p15:observe"]["decision_status"] == "continue_shadow_observation"
    assert groups["p15:follow-up"]["decision_bucket"] == "research_follow_up"
    assert groups["p15:follow-up"]["manual_review_required"] is True
    assert groups["p15:follow-up"]["auto_trade_enabled"] is False
    assert groups["p15:follow-up"]["production_watchlist_enabled"] is False
    assert groups["p15:follow-up"]["production_write_enabled"] is False
    assert sorted(DECISION_STATUSES) == sorted(
        [
            "continue_shadow_observation",
            "request_more_data",
            "open_research_follow_up",
            "deprioritize_shadow_group",
        ]
    )


def test_build_shadow_review_decisions_preserves_run_metadata_and_writes_artifacts(tmp_path):
    decisions = build_shadow_review_decisions(
        p15_review={
            "run_id": "p15-shadow-analytics-review-2026-06-30-2026-08-29",
            "groups": [_review_group()],
            "manual_review_required": True,
            "auto_trade_enabled": False,
            "production_watchlist_enabled": False,
            "production_write_enabled": False,
        },
        run_id="p16-shadow-review-decisions-2026-08-29",
        decision_date="2026-08-29",
        operator_id="operator",
    )

    assert decisions["status"] == "shadow_review_decisions_ready"
    assert decisions["source_p15_review_run_ids"] == ["p15-shadow-analytics-review-2026-06-30-2026-08-29"]
    assert decisions["operator_id"] == "operator"
    assert decisions["group_count"] == 1
    paths = write_shadow_review_decisions(decisions, tmp_path)
    assert Path(paths["json_path"]).exists()
    assert Path(paths["groups_csv_path"]).exists()
    assert Path(paths["markdown_path"]).exists()
    payload = json.loads(Path(paths["json_path"]).read_text(encoding="utf-8"))
    assert payload["groups"][0]["decision_status"] == "open_research_follow_up"
    assert "open_research_follow_up" in Path(paths["markdown_path"]).read_text(encoding="utf-8")


def test_build_shadow_review_decision_group_id_matches_read_model_derivation(tmp_path):
    run_id = "p16-shadow-review-decisions-2026-08-29"
    source_group_id = "operator_shadow_analytics_review:p15-run:trend-ready"
    decisions = build_shadow_review_decisions_from_rows(
        [_review_group(review_group_id=source_group_id)],
        run_id=run_id,
        decision_date="2026-08-29",
        operator_id="operator",
    )
    expected_digest = hashlib.sha256(
        f"{run_id}|{source_group_id}|open_research_follow_up".encode("utf-8")
    ).hexdigest()[:16]
    expected_id = f"operator_shadow_review_decision:{run_id}:{expected_digest}"
    assert decisions["groups"][0]["decision_group_id"] == expected_id


def test_build_shadow_review_decisions_rejects_production_enabled_group():
    row = _review_group(production_watchlist_enabled=True)

    with pytest.raises(ValueError, match="production_watchlist_not_allowed"):
        build_shadow_review_decisions_from_rows(
            [row],
            run_id="p16-shadow-review-decisions-2026-08-29",
            decision_date="2026-08-29",
            operator_id="operator",
        )


def test_build_shadow_review_decisions_rejects_unsafe_execution_fields():
    row = _review_group(order_id="unsafe")

    with pytest.raises(ValueError, match="unsafe_execution_field"):
        build_shadow_review_decisions_from_rows(
            [row],
            run_id="p16-shadow-review-decisions-2026-08-29",
            decision_date="2026-08-29",
            operator_id="operator",
        )


def test_build_shadow_review_decisions_rejects_unknown_review_status():
    row = _review_group(review_status="promote_to_production")

    with pytest.raises(ValueError, match="unknown_review_status"):
        build_shadow_review_decisions_from_rows(
            [row],
            run_id="p16-shadow-review-decisions-2026-08-29",
            decision_date="2026-08-29",
            operator_id="operator",
        )
