from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from stock_research.operator_decision.outcome_analytics import (
    build_decision_outcome_analytics,
    write_decision_outcome_analytics,
)
from stock_research.operator_decision.outcome_analytics_read_model import (
    load_decision_outcome_analytics_read_model_rows,
)
from stock_research.operator_decision.outcome_read_model import load_decision_outcome_read_model_rows
from stock_research.operator_decision.p8_smoke import build_p8_decision_outcome_smoke


def build_p9_decision_outcome_analytics_smoke(output_dir: str | Path) -> dict[str, Any]:
    output_path = Path(output_dir)
    p8_result = build_p8_decision_outcome_smoke(output_path)
    p9_dir = output_path / "p9"
    p9_dir.mkdir(parents=True, exist_ok=True)

    outcome_rows = load_decision_outcome_read_model_rows(p8_result["p8_outcome_json_path"])
    analytics = build_decision_outcome_analytics(
        start_date="2026-05-30",
        end_date="2026-06-30",
        outcome_events=pd.DataFrame(outcome_rows["events"]),
        horizons=[1, 5, 20],
        run_id="p9-smoke-analytics-2026-05-30-2026-06-30",
    )
    analytics_paths = write_decision_outcome_analytics(analytics, p9_dir)
    analytics_rows = load_decision_outcome_analytics_read_model_rows(analytics_paths["json_path"])

    return {
        "p8_outcome_json_path": p8_result["p8_outcome_json_path"],
        "p9_analytics_json_path": analytics_paths["json_path"],
        "p9_analytics_groups_csv_path": analytics_paths["groups_csv_path"],
        "p9_analytics_diagnostics_csv_path": analytics_paths["diagnostics_csv_path"],
        "p9_analytics_markdown_path": analytics_paths["markdown_path"],
        "source_outcome_count": int(analytics["source_outcome_count"]),
        "analytics_group_count": int(analytics["group_count"]),
        "read_model_group_count": len(analytics_rows["groups"]),
        "analytics_levels": sorted({str(row["analytics_level"]) for row in analytics_rows["groups"]}),
        "manual_review_required": bool(analytics["manual_review_required"]),
        "auto_trade_enabled": bool(analytics["auto_trade_enabled"]),
        "diagnostic_count": int(analytics["diagnostic_count"]),
        "analytics_artifact_paths": [str(row["analytics_artifact_path"]) for row in analytics_rows["groups"]],
    }
