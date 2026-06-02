from pathlib import Path

from stock_research.operator_decision.p10_smoke import build_p10_experiment_proposals_smoke


def test_p10_smoke_builds_proposal_artifacts_and_read_model_rows(tmp_path):
    result = build_p10_experiment_proposals_smoke(tmp_path)

    assert Path(result["p9_analytics_json_path"]).exists()
    assert Path(result["p10_proposals_json_path"]).exists()
    assert Path(result["p10_proposals_csv_path"]).exists()
    assert Path(result["p10_proposals_markdown_path"]).exists()

    assert result["proposal_count"] == 2
    assert result["read_model_proposal_count"] == 2
    assert result["status_counts"] == {
        "approved_for_experiment": 1,
        "needs_more_data": 1,
    }
    assert result["source_p9_analytics_run_ids"] == ["p9-smoke-analytics-2026-05-30-2026-06-30"]
    assert result["manual_review_required"] is True
    assert result["auto_trade_enabled"] is False
    assert result["promotion_enabled"] is False
    assert all(
        path.endswith("operator_experiment_proposals_2026-06-30.json")
        for path in result["proposal_artifact_paths"]
    )
