from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from stock_research.operator_decision.experiment_proposals_read_model import (
    load_experiment_proposal_read_model_rows,
)
from stock_research.operator_decision.experiment_replay import (
    build_experiment_replay_review,
    write_experiment_replay_review,
)
from stock_research.operator_decision.experiment_replay_read_model import (
    load_experiment_replay_read_model_rows,
)
from stock_research.operator_decision.p10_smoke import build_p10_experiment_proposals_smoke


def build_p11_experiment_replay_smoke(output_dir: str | Path) -> dict[str, Any]:
    output_path = Path(output_dir)
    p10_result = build_p10_experiment_proposals_smoke(output_path)
    p11_dir = output_path / "p11"
    p11_dir.mkdir(parents=True, exist_ok=True)

    proposal_rows = load_experiment_proposal_read_model_rows(p10_result["p10_proposals_json_path"])
    proposals = pd.DataFrame(proposal_rows["proposals"])
    approved = proposals.loc[proposals["status"] == "approved_for_experiment"].iloc[0].to_dict()

    metrics_csv_path = p11_dir / "replay_metrics_2026-06-30.csv"
    replay_events = pd.DataFrame(
        [
            {
                "replay_result_id": "p11-smoke-replay:001",
                "proposal_id": approved["proposal_id"],
                "source_p10_proposal_run_id": approved["run_id"],
                "source_p9_analytics_run_id": approved["source_p9_analytics_run_id"],
                "replay_start_date": "2026-01-01",
                "replay_end_date": "2026-06-30",
                "replay_input_artifact_paths": json.dumps([str(metrics_csv_path)]),
                "validation_method": "offline replay smoke",
                "replay_status": "passed_offline_replay",
                "sample_count": 24,
                "passed_count": 18,
                "failed_count": 6,
                "metric_summary": json.dumps({"forward_5d_return_mean": 0.08, "win_rate": 0.75}),
                "failure_reason": "",
                "defer_reason": "",
                "manual_review_required": True,
                "auto_trade_enabled": False,
                "production_write_enabled": False,
            }
        ]
    )
    replay_events.to_csv(metrics_csv_path, index=False)

    review = build_experiment_replay_review(
        proposals=proposals,
        replay_events=replay_events,
        run_id="p11-smoke-replay-2026-06-30",
        replay_start_date="2026-01-01",
        replay_end_date="2026-06-30",
    )
    replay_paths = write_experiment_replay_review(review, p11_dir)
    replay_rows = load_experiment_replay_read_model_rows(replay_paths["json_path"])

    return {
        "p10_proposals_json_path": p10_result["p10_proposals_json_path"],
        "p11_replay_input_metrics_csv_path": str(metrics_csv_path),
        "p11_replay_json_path": replay_paths["json_path"],
        "p11_replay_results_csv_path": replay_paths["results_csv_path"],
        "p11_replay_markdown_path": replay_paths["markdown_path"],
        "result_count": int(review["result_count"]),
        "read_model_result_count": len(replay_rows["results"]),
        "status_counts": review["status_counts"],
        "source_p10_proposal_run_ids": sorted(
            {str(row["source_p10_proposal_run_id"]) for row in replay_rows["results"]}
        ),
        "source_p9_analytics_run_ids": sorted(
            {str(row["source_p9_analytics_run_id"]) for row in replay_rows["results"]}
        ),
        "manual_review_required": bool(review["manual_review_required"]),
        "auto_trade_enabled": bool(review["auto_trade_enabled"]),
        "production_write_enabled": bool(review["production_write_enabled"]),
        "replay_artifact_paths": [str(row["replay_artifact_path"]) for row in replay_rows["results"]],
    }
