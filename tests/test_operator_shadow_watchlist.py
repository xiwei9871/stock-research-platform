import json
from pathlib import Path

import pandas as pd
import pytest

from stock_research.operator_decision.shadow_watchlist import (
    SHADOW_WATCHLIST_STATUSES,
    build_shadow_watchlist_candidates_from_frames,
    build_shadow_watchlist_review,
    write_shadow_watchlist_review,
)


def _replay_results() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "replay_result_id": "p11-replay:001",
                "run_id": "p11-replay-run-2026-06-30",
                "proposal_id": "p10-proposal:001",
                "source_p10_proposal_run_id": "p10-proposals-2026-06-30",
                "source_p9_analytics_run_id": "p9-outcome-analytics-2026-05-01-2026-05-31",
                "replay_start_date": "2026-01-01",
                "replay_end_date": "2026-06-30",
                "replay_input_artifact_paths": ["inputs/p11/replay_candidates.csv"],
                "replay_status": "passed_offline_replay",
                "metric_summary": {"win_rate": 0.75},
                "manual_review_required": True,
                "auto_trade_enabled": False,
                "production_write_enabled": False,
            }
        ]
    )


def _candidate_rows() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "shadow_candidate_id": "p12-shadow:001",
                "replay_result_id": "p11-replay:001",
                "source_p11_replay_run_id": "p11-replay-run-2026-06-30",
                "source_p10_proposal_run_id": "p10-proposals-2026-06-30",
                "source_p9_analytics_run_id": "p9-outcome-analytics-2026-05-01-2026-05-31",
                "candidate_date": "2026-06-30",
                "asset_id": "000001.SZ",
                "stock_code": "000001",
                "stock_name": "Ping An Bank",
                "shadow_layer": "trend_shadow",
                "candidate_reason": "Passed replay with acceptable drawdown.",
                "evidence_artifact_paths": json.dumps(["outputs/p11/replay.json"]),
                "metric_summary": json.dumps({"win_rate": 0.75}),
                "reviewer_id": "reviewer-a",
                "status": "shadow_ready",
                "review_notes": "Observe in shadow list only.",
                "manual_review_required": True,
                "auto_trade_enabled": False,
                "production_watchlist_enabled": False,
                "production_write_enabled": False,
            }
        ]
    )


def test_shadow_watchlist_candidates_preserve_replay_sources_and_safety_fields():
    candidates = build_shadow_watchlist_candidates_from_frames(
        replay_results=_replay_results(),
        candidate_events=_candidate_rows(),
    )

    assert set(SHADOW_WATCHLIST_STATUSES) == {
        "shadow_ready",
        "shadow_observe",
        "shadow_rejected",
        "needs_more_data",
        "blocked",
    }
    row = candidates.iloc[0]
    assert row["shadow_candidate_id"] == "p12-shadow:001"
    assert row["replay_result_id"] == "p11-replay:001"
    assert row["source_p11_replay_run_id"] == "p11-replay-run-2026-06-30"
    assert row["source_p10_proposal_run_id"] == "p10-proposals-2026-06-30"
    assert row["source_p9_analytics_run_id"] == "p9-outcome-analytics-2026-05-01-2026-05-31"
    assert row["asset_id"] == "000001.SZ"
    assert row["evidence_artifact_paths"] == ["outputs/p11/replay.json"]
    assert row["metric_summary"] == {"win_rate": 0.75}
    assert row["manual_review_required"] is True
    assert row["auto_trade_enabled"] is False
    assert row["production_watchlist_enabled"] is False
    assert row["production_write_enabled"] is False


def test_shadow_watchlist_review_summarizes_statuses():
    review = build_shadow_watchlist_review(
        replay_results=_replay_results(),
        candidate_events=_candidate_rows(),
        run_id="p12-shadow-watchlist-2026-06-30",
        review_date="2026-06-30",
    )

    assert review["run_id"] == "p12-shadow-watchlist-2026-06-30"
    assert review["review_date"] == "2026-06-30"
    assert review["status"] == "shadow_watchlist_review_ready"
    assert review["candidate_count"] == 1
    assert review["status_counts"] == {"shadow_ready": 1}
    assert review["manual_review_required"] is True
    assert review["auto_trade_enabled"] is False
    assert review["production_watchlist_enabled"] is False
    assert review["production_write_enabled"] is False


def test_shadow_watchlist_rejects_invalid_or_unsafe_inputs():
    invalid = _candidate_rows().copy()
    invalid.loc[0, "status"] = "write_to_watchlist"
    with pytest.raises(ValueError, match="invalid_shadow_status"):
        build_shadow_watchlist_candidates_from_frames(
            replay_results=_replay_results(),
            candidate_events=invalid,
        )

    missing_evidence = _candidate_rows().copy()
    missing_evidence.loc[0, "evidence_artifact_paths"] = json.dumps([])
    with pytest.raises(ValueError, match="evidence_artifact_required"):
        build_shadow_watchlist_candidates_from_frames(
            replay_results=_replay_results(),
            candidate_events=missing_evidence,
        )

    production = _candidate_rows().copy()
    production.loc[0, "production_watchlist_enabled"] = True
    with pytest.raises(ValueError, match="production_watchlist_not_allowed"):
        build_shadow_watchlist_candidates_from_frames(
            replay_results=_replay_results(),
            candidate_events=production,
        )

    unsafe = _candidate_rows().copy()
    unsafe["order_id"] = ["order-1"]
    with pytest.raises(ValueError, match="unsafe_execution_field: order_id"):
        build_shadow_watchlist_candidates_from_frames(
            replay_results=_replay_results(),
            candidate_events=unsafe,
        )


def test_write_shadow_watchlist_review_outputs_review_only_artifacts(tmp_path):
    review = build_shadow_watchlist_review(
        replay_results=_replay_results(),
        candidate_events=_candidate_rows(),
        run_id="p12-shadow-watchlist-2026-06-30",
        review_date="2026-06-30",
    )

    paths = write_shadow_watchlist_review(review, tmp_path)

    assert set(paths) == {"json_path", "candidates_csv_path", "markdown_path"}
    payload = json.loads(Path(paths["json_path"]).read_text(encoding="utf-8"))
    assert payload["manual_review_required"] is True
    assert payload["auto_trade_enabled"] is False
    assert payload["production_watchlist_enabled"] is False
    assert payload["production_write_enabled"] is False
    assert payload["candidates"][0]["asset_id"] == "000001.SZ"

    csv_rows = pd.read_csv(paths["candidates_csv_path"])
    assert csv_rows.loc[0, "shadow_candidate_id"] == "p12-shadow:001"

    markdown = Path(paths["markdown_path"]).read_text(encoding="utf-8")
    assert "P12 Shadow Watchlist Review" in markdown
    assert "production_watchlist_enabled: false" in markdown
