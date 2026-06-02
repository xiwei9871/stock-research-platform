from pathlib import Path

from stock_research.operator_decision.p11_smoke import build_p11_experiment_replay_smoke


def test_p11_smoke_builds_replay_artifacts_and_read_model_rows(tmp_path):
    result = build_p11_experiment_replay_smoke(tmp_path)

    assert Path(result["p10_proposals_json_path"]).exists()
    assert Path(result["p11_replay_json_path"]).exists()
    assert Path(result["p11_replay_results_csv_path"]).exists()
    assert Path(result["p11_replay_markdown_path"]).exists()

    assert result["result_count"] == 1
    assert result["read_model_result_count"] == 1
    assert result["status_counts"] == {"passed_offline_replay": 1}
    assert result["source_p10_proposal_run_ids"] == ["p10-smoke-proposals-2026-06-30"]
    assert result["source_p9_analytics_run_ids"] == ["p9-smoke-analytics-2026-05-30-2026-06-30"]
    assert result["manual_review_required"] is True
    assert result["auto_trade_enabled"] is False
    assert result["production_write_enabled"] is False
    assert all(
        path.endswith("operator_experiment_replay_2026-01-01_2026-06-30.json")
        for path in result["replay_artifact_paths"]
    )
