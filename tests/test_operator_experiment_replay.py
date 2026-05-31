import json
from pathlib import Path

import pandas as pd
import pytest

from stock_research.operator_decision.experiment_replay import (
    EXPERIMENT_REPLAY_STATUSES,
    build_experiment_replay_results_from_frames,
    build_experiment_replay_review,
    write_experiment_replay_review,
)


def _approved_proposals() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "proposal_id": "p10-proposal:001",
                "run_id": "p10-proposals-2026-06-30",
                "proposal_title": "Replay dashboard top-N",
                "hypothesis": "Dashboard top-N candidates should be replayed offline.",
                "source_p9_analytics_run_id": "p9-outcome-analytics-2026-05-01-2026-05-31",
                "source_analytics_group_ids": ["decision_label:candidate"],
                "source_diagnostic_refs": ["top_forward_return:5:decision_label:candidate"],
                "source_artifact_paths": ["outputs/p9/analytics.json"],
                "expected_validation_method": "offline replay",
                "reviewer_id": "reviewer-a",
                "status": "approved_for_experiment",
                "manual_review_required": True,
                "auto_trade_enabled": False,
                "promotion_enabled": False,
            },
            {
                "proposal_id": "p10-proposal:002",
                "run_id": "p10-proposals-2026-06-30",
                "proposal_title": "Collect more caution samples",
                "hypothesis": "Caution samples need more data before replay.",
                "source_p9_analytics_run_id": "p9-outcome-analytics-2026-05-01-2026-05-31",
                "source_analytics_group_ids": ["decision_label:caution"],
                "source_diagnostic_refs": [],
                "source_artifact_paths": ["outputs/p9/analytics.json"],
                "expected_validation_method": "collect another review cycle",
                "reviewer_id": "reviewer-a",
                "status": "needs_more_data",
                "manual_review_required": True,
                "auto_trade_enabled": False,
                "promotion_enabled": False,
            },
        ]
    )


def _replay_rows() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "replay_result_id": "p11-replay:001",
                "proposal_id": "p10-proposal:001",
                "source_p10_proposal_run_id": "p10-proposals-2026-06-30",
                "source_p9_analytics_run_id": "p9-outcome-analytics-2026-05-01-2026-05-31",
                "replay_start_date": "2026-01-01",
                "replay_end_date": "2026-05-31",
                "replay_input_artifact_paths": json.dumps(["inputs/p11/replay_candidates.csv"]),
                "validation_method": "offline replay",
                "replay_status": "passed_offline_replay",
                "sample_count": 24,
                "passed_count": 18,
                "failed_count": 6,
                "metric_summary": json.dumps({"forward_5d_return_mean": 0.08, "win_rate": 0.75}),
                "failure_reason": "",
                "defer_reason": "",
                "manual_review_required": True,
                "auto_trade_enabled": False,
                "production_write_enabled": False,
            }
        ]
    )


def test_build_experiment_replay_results_preserves_proposal_and_p9_references():
    results = build_experiment_replay_results_from_frames(
        proposals=_approved_proposals(),
        replay_events=_replay_rows(),
    )

    assert set(EXPERIMENT_REPLAY_STATUSES) == {
        "replay_ready",
        "passed_offline_replay",
        "failed_offline_replay",
        "needs_more_data",
        "blocked",
    }
    assert results["replay_result_id"].tolist() == ["p11-replay:001"]
    row = results.iloc[0]
    assert row["proposal_id"] == "p10-proposal:001"
    assert row["source_p10_proposal_run_id"] == "p10-proposals-2026-06-30"
    assert row["source_p9_analytics_run_id"] == "p9-outcome-analytics-2026-05-01-2026-05-31"
    assert row["replay_input_artifact_paths"] == ["inputs/p11/replay_candidates.csv"]
    assert row["metric_summary"] == {"forward_5d_return_mean": 0.08, "win_rate": 0.75}
    assert row["manual_review_required"] is True
    assert row["auto_trade_enabled"] is False
    assert row["production_write_enabled"] is False


def test_build_experiment_replay_review_summarizes_replay_statuses_without_production_writes():
    review = build_experiment_replay_review(
        proposals=_approved_proposals(),
        replay_events=_replay_rows(),
        run_id="p11-replay-run-2026-06-30",
        replay_start_date="2026-01-01",
        replay_end_date="2026-05-31",
    )

    assert review["run_id"] == "p11-replay-run-2026-06-30"
    assert review["replay_start_date"] == "2026-01-01"
    assert review["replay_end_date"] == "2026-05-31"
    assert review["status"] == "replay_review_ready"
    assert review["result_count"] == 1
    assert review["status_counts"] == {"passed_offline_replay": 1}
    assert review["manual_review_required"] is True
    assert review["auto_trade_enabled"] is False
    assert review["production_write_enabled"] is False


def test_build_experiment_replay_results_rejects_unapproved_proposals():
    replay_rows = _replay_rows().copy()
    replay_rows.loc[0, "proposal_id"] = "p10-proposal:002"

    with pytest.raises(ValueError, match="proposal_not_approved_for_experiment"):
        build_experiment_replay_results_from_frames(
            proposals=_approved_proposals(),
            replay_events=replay_rows,
        )


def test_build_experiment_replay_results_rejects_missing_source_evidence():
    missing = _replay_rows().copy()
    missing.loc[0, "replay_input_artifact_paths"] = json.dumps([])

    with pytest.raises(ValueError, match="replay_input_artifact_required"):
        build_experiment_replay_results_from_frames(
            proposals=_approved_proposals(),
            replay_events=missing,
        )


def test_build_experiment_replay_results_rejects_invalid_status():
    invalid = _replay_rows().copy()
    invalid.loc[0, "replay_status"] = "promoted_to_shadow_watchlist"

    with pytest.raises(ValueError, match="invalid_replay_status"):
        build_experiment_replay_results_from_frames(
            proposals=_approved_proposals(),
            replay_events=invalid,
        )


def test_build_experiment_replay_results_rejects_execution_fields_and_production_writes():
    unsafe = _replay_rows().copy()
    unsafe["order_id"] = ["order-1"]

    with pytest.raises(ValueError, match="unsafe_execution_field: order_id"):
        build_experiment_replay_results_from_frames(
            proposals=_approved_proposals(),
            replay_events=unsafe,
        )

    production_write = _replay_rows().copy()
    production_write.loc[0, "production_write_enabled"] = True

    with pytest.raises(ValueError, match="production_write_not_allowed"):
        build_experiment_replay_results_from_frames(
            proposals=_approved_proposals(),
            replay_events=production_write,
        )


def test_write_experiment_replay_review_outputs_review_only_artifacts(tmp_path):
    review = build_experiment_replay_review(
        proposals=_approved_proposals(),
        replay_events=_replay_rows(),
        run_id="p11-replay-run-2026-06-30",
        replay_start_date="2026-01-01",
        replay_end_date="2026-05-31",
    )

    paths = write_experiment_replay_review(review, tmp_path)

    assert set(paths) == {"json_path", "results_csv_path", "markdown_path"}
    payload = json.loads(Path(paths["json_path"]).read_text(encoding="utf-8"))
    assert payload["manual_review_required"] is True
    assert payload["auto_trade_enabled"] is False
    assert payload["production_write_enabled"] is False
    assert payload["results"][0]["source_p10_proposal_run_id"] == "p10-proposals-2026-06-30"

    results = pd.read_csv(paths["results_csv_path"])
    assert results.loc[0, "replay_result_id"] == "p11-replay:001"
    assert results.loc[0, "replay_status"] == "passed_offline_replay"

    markdown = Path(paths["markdown_path"]).read_text(encoding="utf-8")
    assert "P11 Experiment Replay Review" in markdown
    assert "manual_review_required: true" in markdown
    assert "auto_trade_enabled: false" in markdown
    assert "production_write_enabled: false" in markdown
