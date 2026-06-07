from __future__ import annotations

import json
from pathlib import Path

import pytest

from stock_research.research_infra.run_evidence import (
    EvidenceBundleValidationError,
    write_evidence_bundle,
)


def test_write_evidence_bundle_writes_run_card_artifacts(tmp_path: Path) -> None:
    result = write_evidence_bundle(
        output_dir=tmp_path,
        run_type="mid_trend_review",
        run_id="mid-trend-review-2026-06-06",
        title="Mid Trend Review 2026-06-06",
        research_question="Which candidates deserve continued review after drawdown control?",
        sample_window={"start_date": "2026-05-01", "end_date": "2026-06-06"},
        universe={"name": "mid_trend_watchlist", "asset_count": 20},
        feature_set=["ret_20", "research_support_score"],
        label_definition={"name": "entry_success_20d", "horizon_days": 20},
        input_artifacts={"candidates": "outputs/research/candidates.csv"},
        output_artifacts={"review": "outputs/research/mid_trend_review.md"},
        metrics={"reviewed_count": 20},
        warnings=["research coverage is thin for two candidates"],
        caveats=["review-only; no execution instruction"],
        reuse_status="monitor_only",
    )

    run_dir = Path(result["run_card_dir"])
    for filename in [
        "run_card.json",
        "run_card.md",
        "config_snapshot.json",
        "metrics.json",
        "data_coverage.json",
        "warnings.md",
    ]:
        assert (run_dir / filename).exists()
    assert (run_dir / "evidence" / "manifest.json").exists()

    payload = json.loads((run_dir / "run_card.json").read_text(encoding="utf-8"))
    assert payload["metadata"]["research_question"] == (
        "Which candidates deserve continued review after drawdown control?"
    )
    assert payload["metadata"]["reuse_status"] == "monitor_only"
    assert payload["metadata"]["caveats"] == ["review-only; no execution instruction"]
    assert payload["config"]["sample_window"] == {
        "start_date": "2026-05-01",
        "end_date": "2026-06-06",
    }
    assert payload["config"]["universe"] == {
        "name": "mid_trend_watchlist",
        "asset_count": 20,
    }
    assert payload["config"]["feature_set"] == ["ret_20", "research_support_score"]
    assert payload["artifact_paths"]["review"] == "outputs/research/mid_trend_review.md"


def test_write_evidence_bundle_rejects_missing_required_context(tmp_path: Path) -> None:
    with pytest.raises(EvidenceBundleValidationError) as exc:
        write_evidence_bundle(
            output_dir=tmp_path,
            run_type="daily_factor_research",
            run_id="daily-factor-2026-06-06",
            title="Daily Factor Research",
            research_question="",
            sample_window={"start_date": "2026-06-01", "end_date": "2026-06-06"},
            universe={},
            feature_set=["ret_20"],
            label_definition={"name": "future_return_5d", "horizon_days": 5},
            input_artifacts={"features": "outputs/features.csv"},
            output_artifacts={},
        )

    message = str(exc.value)
    assert "research_question" in message
    assert "universe" in message
    assert "output_artifacts" in message
