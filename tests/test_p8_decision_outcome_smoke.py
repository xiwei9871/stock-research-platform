from pathlib import Path

import pytest

from stock_research.operator_decision.p8_smoke import build_p8_decision_outcome_smoke


def test_p8_smoke_builds_outcome_artifacts_and_read_model_rows(tmp_path):
    result = build_p8_decision_outcome_smoke(tmp_path)

    assert Path(result["p7_journal_json_path"]).exists()
    assert Path(result["p8_outcome_json_path"]).exists()
    assert Path(result["p8_outcome_details_csv_path"]).exists()
    assert Path(result["p8_outcome_summary_csv_path"]).exists()
    assert Path(result["p8_outcome_markdown_path"]).exists()

    assert result["journal_decision_count"] == 2
    assert result["outcome_count"] == 2
    assert result["read_model_event_count"] == 2
    assert result["decision_labels"] == ["candidate", "caution"]
    assert result["manual_review_required"] is True
    assert result["auto_trade_enabled"] is False
    assert all(path.endswith("operator_decision_journal_2026-05-30_p8-smoke.json") for path in result["source_artifact_paths"])
    assert result["forward_1d_returns_by_label"]["candidate"] == pytest.approx(0.1)
