import json
from pathlib import Path

import pandas as pd
import pytest

from stock_research.operator_decision.experiment_proposals import (
    EXPERIMENT_PROPOSAL_STATUSES,
    build_experiment_proposal_review,
    build_experiment_proposals_from_frames,
    write_experiment_proposal_review,
)


def _proposal_rows() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "proposal_id": "p10-proposal:001",
                "proposal_title": "Test stronger dashboard top-N follow-through",
                "hypothesis": "Candidate decisions from dashboard_topn with positive 5D mean deserve an offline replay.",
                "source_p9_analytics_run_id": "p9-outcome-analytics-2026-05-01-2026-05-31",
                "source_analytics_group_ids": json.dumps(["decision_label:candidate", "source_context:dashboard_topn"]),
                "source_diagnostic_refs": json.dumps(["top_forward_return:5:decision_label:candidate"]),
                "source_artifact_paths": json.dumps(["outputs/p9/operator_decision_outcome_analytics.json"]),
                "expected_validation_method": "offline replay against held-out review windows",
                "risk_notes": "Check sample size and downside concentration before any implementation scope.",
                "reviewer_id": "reviewer-a",
                "status": "approved_for_experiment",
                "manual_review_required": True,
                "auto_trade_enabled": False,
            },
            {
                "proposal_id": "p10-proposal:002",
                "proposal_title": "Defer low-sample caution segment",
                "hypothesis": "Caution decisions need more observations before a replay is useful.",
                "source_p9_analytics_run_id": "p9-outcome-analytics-2026-05-01-2026-05-31",
                "source_analytics_group_ids": ["decision_label:caution"],
                "source_diagnostic_refs": [],
                "source_artifact_paths": ["outputs/p9/operator_decision_outcome_analytics.json"],
                "expected_validation_method": "collect one more review cycle",
                "risk_notes": "Insufficient complete outcomes.",
                "reviewer_id": "reviewer-a",
                "status": "needs_more_data",
                "manual_review_required": True,
                "auto_trade_enabled": False,
            },
        ]
    )


def test_build_experiment_proposals_preserves_p9_evidence_and_review_only_safety_fields():
    proposals = build_experiment_proposals_from_frames(proposal_events=_proposal_rows())

    assert set(EXPERIMENT_PROPOSAL_STATUSES) == {
        "draft",
        "needs_more_data",
        "approved_for_experiment",
        "rejected",
        "deferred",
    }
    assert proposals["proposal_id"].tolist() == ["p10-proposal:001", "p10-proposal:002"]
    assert proposals["manual_review_required"].tolist() == [True, True]
    assert proposals["auto_trade_enabled"].tolist() == [False, False]

    first = proposals.iloc[0]
    assert first["source_p9_analytics_run_id"] == "p9-outcome-analytics-2026-05-01-2026-05-31"
    assert first["source_analytics_group_ids"] == [
        "decision_label:candidate",
        "source_context:dashboard_topn",
    ]
    assert first["source_diagnostic_refs"] == ["top_forward_return:5:decision_label:candidate"]
    assert first["source_artifact_paths"] == ["outputs/p9/operator_decision_outcome_analytics.json"]
    assert first["status"] == "approved_for_experiment"


def test_build_experiment_proposal_review_summarizes_statuses_without_promotion_side_effects():
    review = build_experiment_proposal_review(
        proposal_events=_proposal_rows(),
        run_id="p10-proposals-2026-05-31",
        review_date="2026-05-31",
    )

    assert review["run_id"] == "p10-proposals-2026-05-31"
    assert review["review_date"] == "2026-05-31"
    assert review["status"] == "proposal_review_ready"
    assert review["manual_review_required"] is True
    assert review["auto_trade_enabled"] is False
    assert review["proposal_count"] == 2
    assert review["status_counts"] == {
        "approved_for_experiment": 1,
        "needs_more_data": 1,
    }
    assert review["promotion_enabled"] is False
    assert review["proposals"][0]["hypothesis"].startswith("Candidate decisions")


def test_build_experiment_proposals_rejects_missing_p9_evidence():
    missing_evidence = _proposal_rows().copy()
    missing_evidence.loc[0, "source_analytics_group_ids"] = json.dumps([])
    missing_evidence.loc[0, "source_diagnostic_refs"] = json.dumps([])

    with pytest.raises(ValueError, match="source_evidence_required"):
        build_experiment_proposals_from_frames(proposal_events=missing_evidence)


def test_build_experiment_proposals_rejects_invalid_status():
    invalid = _proposal_rows().copy()
    invalid.loc[0, "status"] = "promoted_to_production"

    with pytest.raises(ValueError, match="invalid_proposal_status"):
        build_experiment_proposals_from_frames(proposal_events=invalid)


def test_build_experiment_proposals_rejects_execution_fields_and_auto_trade():
    unsafe = _proposal_rows().copy()
    unsafe["order_id"] = ["order-1", ""]

    with pytest.raises(ValueError, match="unsafe_execution_field: order_id"):
        build_experiment_proposals_from_frames(proposal_events=unsafe)

    auto_trade = _proposal_rows().copy()
    auto_trade.loc[0, "auto_trade_enabled"] = True

    with pytest.raises(ValueError, match="auto_trade_not_allowed"):
        build_experiment_proposals_from_frames(proposal_events=auto_trade)


def test_write_experiment_proposal_review_outputs_json_csv_and_markdown(tmp_path):
    review = build_experiment_proposal_review(
        proposal_events=_proposal_rows().iloc[:1],
        run_id="p10-proposals-2026-05-31",
        review_date="2026-05-31",
    )

    paths = write_experiment_proposal_review(review, tmp_path)

    assert set(paths) == {"json_path", "proposals_csv_path", "markdown_path"}
    payload = json.loads(Path(paths["json_path"]).read_text(encoding="utf-8"))
    assert payload["manual_review_required"] is True
    assert payload["auto_trade_enabled"] is False
    assert payload["promotion_enabled"] is False
    assert payload["proposals"][0]["source_analytics_group_ids"] == [
        "decision_label:candidate",
        "source_context:dashboard_topn",
    ]

    proposals = pd.read_csv(paths["proposals_csv_path"])
    assert proposals.loc[0, "proposal_id"] == "p10-proposal:001"
    assert proposals.loc[0, "status"] == "approved_for_experiment"

    markdown = Path(paths["markdown_path"]).read_text(encoding="utf-8")
    assert "P10 Experiment Proposal Review" in markdown
    assert "manual_review_required: true" in markdown
    assert "auto_trade_enabled: false" in markdown
    assert "promotion_enabled: false" in markdown
