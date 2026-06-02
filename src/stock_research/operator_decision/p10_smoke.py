from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from stock_research.operator_decision.experiment_proposals import (
    build_experiment_proposal_review,
    write_experiment_proposal_review,
)
from stock_research.operator_decision.experiment_proposals_read_model import (
    load_experiment_proposal_read_model_rows,
)
from stock_research.operator_decision.outcome_analytics_read_model import (
    load_decision_outcome_analytics_read_model_rows,
)
from stock_research.operator_decision.p9_smoke import build_p9_decision_outcome_analytics_smoke


def build_p10_experiment_proposals_smoke(output_dir: str | Path) -> dict[str, Any]:
    output_path = Path(output_dir)
    p9_result = build_p9_decision_outcome_analytics_smoke(output_path)
    p10_dir = output_path / "p10"
    p10_dir.mkdir(parents=True, exist_ok=True)

    analytics_rows = load_decision_outcome_analytics_read_model_rows(p9_result["p9_analytics_json_path"])
    source_run_id = str(analytics_rows["run"]["run_id"])
    group_ids = [str(row["analytics_group_id"]) for row in analytics_rows["groups"]]
    artifact_path = str(p9_result["p9_analytics_json_path"])

    proposal_events = pd.DataFrame(
        [
            {
                "proposal_id": "p10-smoke-proposal:001",
                "proposal_title": "Replay strong candidate segment",
                "hypothesis": "Candidate outcome analytics should be replayed offline before any implementation scope.",
                "source_p9_analytics_run_id": source_run_id,
                "source_analytics_group_ids": [group_ids[0]],
                "source_diagnostic_refs": ["top_forward_return:5:decision_label:candidate"],
                "source_artifact_paths": [artifact_path],
                "expected_validation_method": "offline replay over held-out review windows",
                "risk_notes": "Keep proposal review-only; no scoring mutation in P10.",
                "reviewer_id": "p10-smoke-reviewer",
                "status": "approved_for_experiment",
                "manual_review_required": True,
                "auto_trade_enabled": False,
            },
            {
                "proposal_id": "p10-smoke-proposal:002",
                "proposal_title": "Collect more caution samples",
                "hypothesis": "Low-sample caution analytics need more data before replay.",
                "source_p9_analytics_run_id": source_run_id,
                "source_analytics_group_ids": [group_ids[-1]],
                "source_diagnostic_refs": [],
                "source_artifact_paths": [artifact_path],
                "expected_validation_method": "collect one additional review cycle",
                "risk_notes": "Do not promote under insufficient sample size.",
                "reviewer_id": "p10-smoke-reviewer",
                "status": "needs_more_data",
                "manual_review_required": True,
                "auto_trade_enabled": False,
            },
        ]
    )
    review = build_experiment_proposal_review(
        proposal_events=proposal_events,
        run_id="p10-smoke-proposals-2026-06-30",
        review_date="2026-06-30",
    )
    proposal_paths = write_experiment_proposal_review(review, p10_dir)
    proposal_rows = load_experiment_proposal_read_model_rows(proposal_paths["json_path"])

    return {
        "p9_analytics_json_path": p9_result["p9_analytics_json_path"],
        "p10_proposals_json_path": proposal_paths["json_path"],
        "p10_proposals_csv_path": proposal_paths["proposals_csv_path"],
        "p10_proposals_markdown_path": proposal_paths["markdown_path"],
        "proposal_count": int(review["proposal_count"]),
        "read_model_proposal_count": len(proposal_rows["proposals"]),
        "status_counts": review["status_counts"],
        "source_p9_analytics_run_ids": sorted(
            {str(row["source_p9_analytics_run_id"]) for row in proposal_rows["proposals"]}
        ),
        "manual_review_required": bool(review["manual_review_required"]),
        "auto_trade_enabled": bool(review["auto_trade_enabled"]),
        "promotion_enabled": bool(review["promotion_enabled"]),
        "proposal_artifact_paths": [str(row["proposal_artifact_path"]) for row in proposal_rows["proposals"]],
    }
