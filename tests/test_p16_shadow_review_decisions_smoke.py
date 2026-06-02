from pathlib import Path

from stock_research.operator_decision.p16_smoke import build_p16_shadow_review_decisions_smoke


def test_p16_smoke_builds_shadow_review_decision_artifacts_and_read_model_rows(tmp_path):
    result = build_p16_shadow_review_decisions_smoke(tmp_path)

    assert Path(result["p15_shadow_analytics_review_json_path"]).exists()
    assert Path(result["p16_shadow_review_decisions_json_path"]).exists()
    assert Path(result["p16_shadow_review_decisions_groups_csv_path"]).exists()
    assert Path(result["p16_shadow_review_decisions_markdown_path"]).exists()
    assert result["source_group_count"] == 1
    assert result["decision_group_count"] == 1
    assert result["read_model_group_count"] == 1
    assert result["decision_statuses"] == ["request_more_data"]
    assert result["decision_buckets"] == ["data_needed"]
    assert result["group_keys"] == ["trend_shadow|shadow_ready"]
    assert result["source_p15_review_run_ids"] == ["p15-smoke-shadow-analytics-review-2026-06-30-2026-08-29"]
    assert result["manual_review_required"] is True
    assert result["auto_trade_enabled"] is False
    assert result["production_watchlist_enabled"] is False
    assert result["production_write_enabled"] is False
