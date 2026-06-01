import json
from pathlib import Path

import pytest

from stock_research.operator_decision.shadow_analytics_review import (
    DEFAULT_SHADOW_ANALYTICS_REVIEW_THRESHOLDS,
    REVIEW_STATUSES,
    build_shadow_analytics_review,
    build_shadow_analytics_review_from_rows,
    write_shadow_analytics_review,
)


def _group(**overrides):
    row = {
        "analytics_group_id": "operator_shadow_outcome_analytics:p14:001",
        "run_id": "p14-shadow-outcome-analytics-2026-06-30-2026-08-29",
        "review_start_date": "2026-06-30",
        "review_end_date": "2026-08-29",
        "group_key": "trend_shadow|shadow_ready",
        "shadow_layer": "trend_shadow",
        "shadow_status": "shadow_ready",
        "sample_count": 20,
        "complete_count": 18,
        "insufficient_data_count": 2,
        "source_p12_shadow_run_count": 1,
        "source_p11_replay_run_count": 1,
        "source_p10_proposal_run_count": 1,
        "source_p9_analytics_run_count": 1,
        "horizon_metrics": {
            "20": {
                "forward_return_mean": 0.04,
                "forward_return_median": 0.03,
                "forward_win_rate": 0.60,
                "max_high_return_mean": 0.10,
                "max_low_drawdown_mean": -0.06,
                "max_low_drawdown_worst": -0.12,
            }
        },
        "analytics_artifact_path": "/tmp/operator_shadow_outcome_analytics.json",
        "manual_review_required": True,
        "auto_trade_enabled": False,
        "production_watchlist_enabled": False,
        "production_write_enabled": False,
    }
    row.update(overrides)
    return row


def test_build_shadow_analytics_review_assigns_conservative_statuses():
    rows = [
        _group(analytics_group_id="p14:follow-up", group_key="trend_shadow|shadow_ready"),
        _group(analytics_group_id="p14:low-sample", group_key="trend_shadow|low_sample", sample_count=9),
        _group(
            analytics_group_id="p14:data-quality",
            group_key="trend_shadow|data_quality",
            sample_count=20,
            complete_count=10,
            insufficient_data_count=10,
        ),
        _group(
            analytics_group_id="p14:deprioritize-negative",
            group_key="trend_shadow|negative",
            horizon_metrics={"20": {"forward_return_mean": -0.03, "max_low_drawdown_worst": -0.10}},
        ),
        _group(
            analytics_group_id="p14:deprioritize-drawdown",
            group_key="trend_shadow|drawdown",
            horizon_metrics={"20": {"forward_return_mean": 0.02, "max_low_drawdown_worst": -0.25}},
        ),
        _group(
            analytics_group_id="p14:observe",
            group_key="trend_shadow|observe",
            horizon_metrics={"20": {"forward_return_mean": 0.02, "max_low_drawdown_worst": -0.10}},
        ),
    ]

    review = build_shadow_analytics_review_from_rows(
        rows,
        run_id="p15-shadow-analytics-review-2026-06-30-2026-08-29",
        review_start_date="2026-06-30",
        review_end_date="2026-08-29",
        reviewer_id="operator",
    )

    groups = {group["source_p14_analytics_group_id"]: group for group in review["groups"]}
    assert groups["p14:follow-up"]["review_status"] == "research_follow_up_candidate"
    assert groups["p14:follow-up"]["review_bucket"] == "follow_up"
    assert groups["p14:low-sample"]["review_status"] == "needs_more_data"
    assert groups["p14:data-quality"]["review_status"] == "investigate_data_quality"
    assert groups["p14:deprioritize-negative"]["review_status"] == "deprioritize_review"
    assert groups["p14:deprioritize-drawdown"]["review_status"] == "deprioritize_review"
    assert groups["p14:observe"]["review_status"] == "continue_observing"
    for group in review["groups"]:
        assert group["manual_review_required"] is True
        assert group["auto_trade_enabled"] is False
        assert group["production_watchlist_enabled"] is False
        assert group["production_write_enabled"] is False


def test_build_shadow_analytics_review_preserves_run_metadata_and_writes_artifacts(tmp_path):
    p14_analytics = {
        "run_id": "p14-shadow-outcome-analytics-2026-06-30-2026-08-29",
        "review_start_date": "2026-06-30",
        "review_end_date": "2026-08-29",
        "manual_review_required": True,
        "auto_trade_enabled": False,
        "production_watchlist_enabled": False,
        "production_write_enabled": False,
        "groups": [_group()],
    }

    review = build_shadow_analytics_review(
        p14_analytics=p14_analytics,
        run_id="p15-shadow-analytics-review-2026-06-30-2026-08-29",
        review_start_date="2026-06-30",
        review_end_date="2026-08-29",
        reviewer_id="operator",
    )
    paths = write_shadow_analytics_review(review, tmp_path)

    payload = json.loads(Path(paths["json_path"]).read_text(encoding="utf-8"))
    assert payload["status"] == "shadow_analytics_review_ready"
    assert payload["source_p14_analytics_run_ids"] == [
        "p14-shadow-outcome-analytics-2026-06-30-2026-08-29"
    ]
    assert payload["reviewer_id"] == "operator"
    assert payload["group_count"] == 1
    assert payload["groups"][0]["review_status"] == "research_follow_up_candidate"
    assert Path(paths["groups_csv_path"]).exists()
    assert Path(paths["markdown_path"]).exists()
    assert "research_follow_up_candidate" in Path(paths["markdown_path"]).read_text(encoding="utf-8")


def test_build_shadow_analytics_review_rejects_production_enabled_group():
    row = _group(production_watchlist_enabled=True)

    with pytest.raises(ValueError, match="production_watchlist_not_allowed"):
        build_shadow_analytics_review_from_rows(
            [row],
            run_id="p15-shadow-analytics-review-2026-06-30-2026-08-29",
            review_start_date="2026-06-30",
            review_end_date="2026-08-29",
            reviewer_id="operator",
        )


def test_build_shadow_analytics_review_rejects_unsafe_execution_fields():
    row = _group(order_id="order-001")

    with pytest.raises(ValueError, match="unsafe_execution_field.*order_id"):
        build_shadow_analytics_review_from_rows(
            [row],
            run_id="p15-shadow-analytics-review-2026-06-30-2026-08-29",
            review_start_date="2026-06-30",
            review_end_date="2026-08-29",
            reviewer_id="operator",
        )


def test_review_status_constants_are_scope_frozen():
    assert REVIEW_STATUSES == [
        "continue_observing",
        "needs_more_data",
        "investigate_data_quality",
        "deprioritize_review",
        "research_follow_up_candidate",
    ]
    assert DEFAULT_SHADOW_ANALYTICS_REVIEW_THRESHOLDS["min_sample_count"] == 10
