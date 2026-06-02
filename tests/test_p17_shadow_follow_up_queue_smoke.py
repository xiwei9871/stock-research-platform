from pathlib import Path

from stock_research.operator_decision.p17_smoke import build_p17_shadow_follow_up_queue_smoke


def test_p17_smoke_builds_shadow_follow_up_artifacts_and_read_model_rows(tmp_path):
    result = build_p17_shadow_follow_up_queue_smoke(tmp_path)

    assert Path(result["p16_shadow_review_decisions_json_path"]).exists()
    assert Path(result["p17_shadow_follow_up_queue_json_path"]).exists()
    assert Path(result["p17_shadow_follow_up_queue_items_csv_path"]).exists()
    assert Path(result["p17_shadow_follow_up_queue_markdown_path"]).exists()
    assert result["source_decision_group_count"] == 1
    assert result["follow_up_item_count"] == 1
    assert result["read_model_item_count"] == 1
    assert result["follow_up_statuses"] == ["collect_more_evidence"]
    assert result["priority_buckets"] == ["high"]
    assert result["group_keys"] == ["trend_shadow|shadow_ready"]
    assert result["source_p16_decision_run_ids"] == ["p16-smoke-shadow-review-decisions-2026-08-29"]
    assert result["manual_review_required"] is True
    assert result["auto_trade_enabled"] is False
    assert result["production_watchlist_enabled"] is False
    assert result["production_write_enabled"] is False
