from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from stock_research.operator_decision.p14_smoke import build_p14_shadow_outcome_analytics_smoke
from stock_research.operator_decision.shadow_analytics_review import (
    build_shadow_analytics_review,
    write_shadow_analytics_review,
)
from stock_research.operator_decision.shadow_analytics_review_read_model import (
    load_shadow_analytics_review_read_model_rows,
)


def build_p15_shadow_analytics_review_smoke(output_dir: str | Path) -> dict[str, Any]:
    output_path = Path(output_dir)
    p14_result = build_p14_shadow_outcome_analytics_smoke(output_path)
    p14_json_path = Path(p14_result["p14_shadow_outcome_analytics_json_path"])
    p14_payload = json.loads(p14_json_path.read_text(encoding="utf-8"))

    review = build_shadow_analytics_review(
        p14_analytics=p14_payload,
        run_id="p15-smoke-shadow-analytics-review-2026-06-30-2026-08-29",
        review_start_date="2026-06-30",
        review_end_date="2026-08-29",
        reviewer_id="operator",
    )
    review_paths = write_shadow_analytics_review(review, output_path / "p15")
    read_rows = load_shadow_analytics_review_read_model_rows(review_paths["json_path"])
    run = read_rows["run"]
    groups = read_rows["groups"]

    return {
        "p14_shadow_outcome_analytics_json_path": str(p14_json_path),
        "p15_shadow_analytics_review_json_path": review_paths["json_path"],
        "p15_shadow_analytics_review_groups_csv_path": review_paths["groups_csv_path"],
        "p15_shadow_analytics_review_markdown_path": review_paths["markdown_path"],
        "source_group_count": int(p14_payload.get("group_count") or len(p14_payload.get("groups") or [])),
        "review_group_count": int(run["group_count"]),
        "read_model_group_count": len(groups),
        "review_statuses": sorted({str(row["review_status"]) for row in groups}),
        "review_buckets": sorted({str(row["review_bucket"]) for row in groups}),
        "group_keys": sorted({str(row["group_key"]) for row in groups}),
        "manual_review_required": bool(run["manual_review_required"]),
        "auto_trade_enabled": bool(run["auto_trade_enabled"]),
        "production_watchlist_enabled": bool(run["production_watchlist_enabled"]),
        "production_write_enabled": bool(run["production_write_enabled"]),
    }
