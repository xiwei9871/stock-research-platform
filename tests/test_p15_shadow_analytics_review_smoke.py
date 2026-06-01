from pathlib import Path

from stock_research.operator_decision.p15_smoke import build_p15_shadow_analytics_review_smoke


def test_p15_smoke_builds_shadow_analytics_review_artifacts_and_read_model_rows(tmp_path):
    result = build_p15_shadow_analytics_review_smoke(tmp_path)

    assert Path(result["p14_shadow_outcome_analytics_json_path"]).exists()
    assert Path(result["p15_shadow_analytics_review_json_path"]).exists()
    assert Path(result["p15_shadow_analytics_review_groups_csv_path"]).exists()
    assert Path(result["p15_shadow_analytics_review_markdown_path"]).exists()
    assert result["source_group_count"] == 1
    assert result["review_group_count"] == 1
    assert result["read_model_group_count"] == 1
    assert result["review_statuses"] == ["needs_more_data"]
    assert result["review_buckets"] == ["data_needed"]
    assert result["group_keys"] == ["trend_shadow|shadow_ready"]
    assert result["manual_review_required"] is True
    assert result["auto_trade_enabled"] is False
    assert result["production_watchlist_enabled"] is False
    assert result["production_write_enabled"] is False
