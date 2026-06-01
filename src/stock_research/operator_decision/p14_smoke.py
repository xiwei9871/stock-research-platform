from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from stock_research.operator_decision.p13_smoke import build_p13_shadow_outcome_smoke
from stock_research.operator_decision.shadow_outcome_analytics import (
    build_shadow_outcome_analytics,
    write_shadow_outcome_analytics,
)
from stock_research.operator_decision.shadow_outcome_analytics_read_model import (
    load_shadow_outcome_analytics_read_model_rows,
)
from stock_research.operator_decision.shadow_outcomes_read_model import (
    load_shadow_outcome_read_model_rows,
)


def build_p14_shadow_outcome_analytics_smoke(output_dir: str | Path) -> dict[str, Any]:
    output_path = Path(output_dir)
    p13_result = build_p13_shadow_outcome_smoke(output_path)
    p14_dir = output_path / "p14"
    p14_dir.mkdir(parents=True, exist_ok=True)

    outcome_rows = load_shadow_outcome_read_model_rows(p13_result["p13_shadow_outcome_json_path"])
    analytics = build_shadow_outcome_analytics(
        review_start_date="2026-06-30",
        review_end_date="2026-08-29",
        shadow_outcomes=pd.DataFrame(outcome_rows["candidates"]),
        run_id="p14-smoke-shadow-outcome-analytics-2026-06-30-2026-08-29",
    )
    analytics_paths = write_shadow_outcome_analytics(analytics, p14_dir)
    read_rows = load_shadow_outcome_analytics_read_model_rows(analytics_paths["json_path"])
    run = read_rows["run"]
    groups = read_rows["groups"]
    return {
        "p13_shadow_outcome_json_path": p13_result["p13_shadow_outcome_json_path"],
        "p14_shadow_outcome_analytics_json_path": analytics_paths["json_path"],
        "p14_shadow_outcome_analytics_groups_csv_path": analytics_paths["groups_csv_path"],
        "p14_shadow_outcome_analytics_markdown_path": analytics_paths["markdown_path"],
        "source_outcome_count": int(run["source_outcome_count"]),
        "group_count": int(run["group_count"]),
        "read_model_group_count": len(groups),
        "group_keys": sorted({str(row["group_key"]) for row in groups}),
        "sample_counts": sorted({int(row["sample_count"]) for row in groups}),
        "complete_counts": sorted({int(row["complete_count"]) for row in groups}),
        "insufficient_data_counts": sorted({int(row["insufficient_data_count"]) for row in groups}),
        "manual_review_required": bool(run["manual_review_required"]),
        "auto_trade_enabled": bool(run["auto_trade_enabled"]),
        "production_watchlist_enabled": bool(run["production_watchlist_enabled"]),
        "production_write_enabled": bool(run["production_write_enabled"]),
    }
