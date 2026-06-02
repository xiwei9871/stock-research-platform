from pathlib import Path

from stock_research.operator_decision.p18_smoke import build_p18_shadow_follow_up_resolution_smoke


def test_p18_smoke_builds_shadow_follow_up_resolution_artifacts_and_read_model_rows(tmp_path):
    result = build_p18_shadow_follow_up_resolution_smoke(tmp_path)

    assert Path(result["p17_shadow_follow_up_queue_json_path"]).exists()
    assert Path(result["p18_shadow_follow_up_resolution_json_path"]).exists()
    assert Path(result["p18_shadow_follow_up_resolution_items_csv_path"]).exists()
    assert Path(result["p18_shadow_follow_up_resolution_markdown_path"]).exists()
    assert result["source_follow_up_item_count"] == 1
    assert result["resolution_item_count"] == 1
    assert result["read_model_item_count"] == 1
    assert result["follow_up_statuses"] == ["collect_more_evidence"]
    assert result["resolution_statuses"] == ["stale_unresolved"]
    assert result["resolution_buckets"] == ["needs_operator_review"]
    assert result["group_keys"] == ["trend_shadow|shadow_ready"]
    assert result["source_p17_follow_up_run_ids"] == ["p17-smoke-shadow-follow-up-queue-2026-08-29"]
    assert result["manual_review_required"] is True
    assert result["auto_trade_enabled"] is False
    assert result["production_watchlist_enabled"] is False
    assert result["production_write_enabled"] is False
