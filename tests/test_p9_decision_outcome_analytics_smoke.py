from pathlib import Path

from stock_research.operator_decision.p9_smoke import build_p9_decision_outcome_analytics_smoke


def test_p9_smoke_builds_analytics_artifacts_and_read_model_rows(tmp_path):
    result = build_p9_decision_outcome_analytics_smoke(tmp_path)

    assert Path(result["p8_outcome_json_path"]).exists()
    assert Path(result["p9_analytics_json_path"]).exists()
    assert Path(result["p9_analytics_groups_csv_path"]).exists()
    assert Path(result["p9_analytics_diagnostics_csv_path"]).exists()
    assert Path(result["p9_analytics_markdown_path"]).exists()

    assert result["source_outcome_count"] == 2
    assert result["analytics_group_count"] >= 4
    assert result["read_model_group_count"] == result["analytics_group_count"]
    assert "decision_label" in result["analytics_levels"]
    assert "source_context" in result["analytics_levels"]
    assert result["manual_review_required"] is True
    assert result["auto_trade_enabled"] is False
    assert result["diagnostic_count"] > 0
    assert all(path.endswith("operator_decision_outcome_analytics_2026-05-30_2026-06-30.json") for path in result["analytics_artifact_paths"])
