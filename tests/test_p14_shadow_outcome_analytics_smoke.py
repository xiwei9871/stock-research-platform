from pathlib import Path

from stock_research.operator_decision.p14_smoke import build_p14_shadow_outcome_analytics_smoke


def test_p14_smoke_builds_shadow_outcome_analytics_artifacts_and_read_model_rows(tmp_path):
    result = build_p14_shadow_outcome_analytics_smoke(tmp_path)

    assert Path(result["p13_shadow_outcome_json_path"]).exists()
    assert Path(result["p14_shadow_outcome_analytics_json_path"]).exists()
    assert Path(result["p14_shadow_outcome_analytics_groups_csv_path"]).exists()
    assert Path(result["p14_shadow_outcome_analytics_markdown_path"]).exists()
    assert result["source_outcome_count"] == 1
    assert result["group_count"] == 1
    assert result["read_model_group_count"] == 1
    assert result["group_keys"] == ["trend_shadow|shadow_ready"]
    assert result["sample_counts"] == [1]
    assert result["complete_counts"] == [1]
    assert result["insufficient_data_counts"] == [0]
    assert result["manual_review_required"] is True
    assert result["auto_trade_enabled"] is False
    assert result["production_watchlist_enabled"] is False
    assert result["production_write_enabled"] is False
