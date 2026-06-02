from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from stock_research.operator_decision.experiment_replay_read_model import (
    load_experiment_replay_read_model_rows,
)
from stock_research.operator_decision.p11_smoke import build_p11_experiment_replay_smoke
from stock_research.operator_decision.shadow_watchlist import (
    build_shadow_watchlist_review,
    write_shadow_watchlist_review,
)
from stock_research.operator_decision.shadow_watchlist_read_model import (
    load_shadow_watchlist_read_model_rows,
)


def build_p12_shadow_watchlist_smoke(output_dir: str | Path) -> dict[str, Any]:
    output_path = Path(output_dir)
    p11_result = build_p11_experiment_replay_smoke(output_path)
    p12_dir = output_path / "p12"
    p12_dir.mkdir(parents=True, exist_ok=True)

    replay_rows = load_experiment_replay_read_model_rows(p11_result["p11_replay_json_path"])
    replay_results = pd.DataFrame(replay_rows["results"])
    passed = replay_results.loc[replay_results["replay_status"] == "passed_offline_replay"].iloc[0].to_dict()

    candidate_events = pd.DataFrame(
        [
            {
                "shadow_candidate_id": "p12-smoke-shadow:001",
                "replay_result_id": passed["replay_result_id"],
                "source_p11_replay_run_id": passed["run_id"],
                "source_p10_proposal_run_id": passed["source_p10_proposal_run_id"],
                "source_p9_analytics_run_id": passed["source_p9_analytics_run_id"],
                "candidate_date": "2026-06-30",
                "asset_id": "000001.SZ",
                "stock_code": "000001",
                "stock_name": "Ping An Bank",
                "shadow_layer": "trend_shadow",
                "candidate_reason": "Passed P11 offline replay; observe in shadow watchlist only.",
                "evidence_artifact_paths": [p11_result["p11_replay_json_path"]],
                "metric_summary": passed["metric_summary"],
                "reviewer_id": "p12-smoke-reviewer",
                "status": "shadow_ready",
                "review_notes": "Synthetic P12 smoke candidate for review-only shadow tracking.",
                "manual_review_required": True,
                "auto_trade_enabled": False,
                "production_watchlist_enabled": False,
                "production_write_enabled": False,
            }
        ]
    )
    review = build_shadow_watchlist_review(
        replay_results=replay_results,
        candidate_events=candidate_events,
        run_id="p12-smoke-shadow-watchlist-2026-06-30",
        review_date="2026-06-30",
    )
    shadow_paths = write_shadow_watchlist_review(review, p12_dir)
    shadow_rows = load_shadow_watchlist_read_model_rows(shadow_paths["json_path"])

    return {
        "p11_replay_json_path": p11_result["p11_replay_json_path"],
        "p12_shadow_json_path": shadow_paths["json_path"],
        "p12_shadow_candidates_csv_path": shadow_paths["candidates_csv_path"],
        "p12_shadow_markdown_path": shadow_paths["markdown_path"],
        "candidate_count": int(review["candidate_count"]),
        "read_model_candidate_count": len(shadow_rows["candidates"]),
        "status_counts": review["status_counts"],
        "source_p11_replay_run_ids": sorted(
            {str(row["source_p11_replay_run_id"]) for row in shadow_rows["candidates"]}
        ),
        "source_p10_proposal_run_ids": sorted(
            {str(row["source_p10_proposal_run_id"]) for row in shadow_rows["candidates"]}
        ),
        "source_p9_analytics_run_ids": sorted(
            {str(row["source_p9_analytics_run_id"]) for row in shadow_rows["candidates"]}
        ),
        "manual_review_required": bool(review["manual_review_required"]),
        "auto_trade_enabled": bool(review["auto_trade_enabled"]),
        "production_watchlist_enabled": bool(review["production_watchlist_enabled"]),
        "production_write_enabled": bool(review["production_write_enabled"]),
    }
