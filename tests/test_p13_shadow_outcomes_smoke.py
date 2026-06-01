from pathlib import Path

from stock_research.operator_decision import p13_smoke
from stock_research.operator_decision.p13_smoke import build_p13_shadow_outcome_smoke


def test_p13_smoke_builds_shadow_outcome_artifacts_and_read_model_rows(tmp_path):
    result = build_p13_shadow_outcome_smoke(tmp_path)

    assert Path(result["p12_shadow_json_path"]).exists()
    assert Path(result["p13_shadow_outcome_json_path"]).exists()
    assert Path(result["p13_shadow_outcome_details_csv_path"]).exists()
    assert Path(result["p13_shadow_outcome_markdown_path"]).exists()
    assert result["outcome_count"] == 1
    assert result["read_model_candidate_count"] == 1
    assert result["outcome_statuses"] == ["complete"]
    assert result["source_p12_shadow_run_ids"] == ["p12-smoke-shadow-watchlist-2026-06-30"]
    assert result["source_p11_replay_run_ids"] == ["p11-smoke-replay-2026-06-30"]
    assert result["source_p10_proposal_run_ids"] == ["p10-smoke-proposals-2026-06-30"]
    assert result["source_p9_analytics_run_ids"] == ["p9-smoke-analytics-2026-05-30-2026-06-30"]
    assert result["manual_review_required"] is True
    assert result["auto_trade_enabled"] is False
    assert result["production_watchlist_enabled"] is False
    assert result["production_write_enabled"] is False


def test_p13_smoke_reports_run_fields_from_written_read_model(monkeypatch, tmp_path):
    original_load = p13_smoke.load_shadow_outcome_read_model_rows

    def load_with_run_sentinels(path):
        rows = original_load(path)
        rows["run"] = {
            **rows["run"],
            "outcome_count": 7,
            "manual_review_required": False,
            "auto_trade_enabled": True,
            "production_watchlist_enabled": True,
            "production_write_enabled": True,
        }
        return rows

    monkeypatch.setattr(p13_smoke, "load_shadow_outcome_read_model_rows", load_with_run_sentinels)

    result = build_p13_shadow_outcome_smoke(tmp_path)

    assert result["outcome_count"] == 7
    assert result["manual_review_required"] is False
    assert result["auto_trade_enabled"] is True
    assert result["production_watchlist_enabled"] is True
    assert result["production_write_enabled"] is True
    assert result["outcome_statuses"] == ["complete"]
    assert result["source_p12_shadow_run_ids"] == ["p12-smoke-shadow-watchlist-2026-06-30"]
