from pathlib import Path

from stock_research.operator_decision.p12_smoke import build_p12_shadow_watchlist_smoke


def test_p12_smoke_builds_shadow_artifacts_and_read_model_rows(tmp_path):
    result = build_p12_shadow_watchlist_smoke(tmp_path)

    assert Path(result["p11_replay_json_path"]).exists()
    assert Path(result["p12_shadow_json_path"]).exists()
    assert Path(result["p12_shadow_candidates_csv_path"]).exists()
    assert Path(result["p12_shadow_markdown_path"]).exists()
    assert result["candidate_count"] == 1
    assert result["read_model_candidate_count"] == 1
    assert result["status_counts"] == {"shadow_ready": 1}
    assert result["source_p11_replay_run_ids"] == ["p11-smoke-replay-2026-06-30"]
    assert result["source_p10_proposal_run_ids"] == ["p10-smoke-proposals-2026-06-30"]
    assert result["source_p9_analytics_run_ids"] == ["p9-smoke-analytics-2026-05-30-2026-06-30"]
    assert result["manual_review_required"] is True
    assert result["auto_trade_enabled"] is False
    assert result["production_watchlist_enabled"] is False
    assert result["production_write_enabled"] is False
