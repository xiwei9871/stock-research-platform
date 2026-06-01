from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from stock_research.operator_decision.p15_smoke import build_p15_shadow_analytics_review_smoke
from stock_research.operator_decision.shadow_review_decisions import (
    build_shadow_review_decisions,
    write_shadow_review_decisions,
)
from stock_research.operator_decision.shadow_review_decisions_read_model import (
    load_shadow_review_decision_read_model_rows,
)


def build_p16_shadow_review_decisions_smoke(output_dir: str | Path) -> dict[str, Any]:
    output_path = Path(output_dir)
    p15_result = build_p15_shadow_analytics_review_smoke(output_path)
    p15_json_path = Path(p15_result["p15_shadow_analytics_review_json_path"])
    p15_payload = json.loads(p15_json_path.read_text(encoding="utf-8"))

    decisions = build_shadow_review_decisions(
        p15_review=p15_payload,
        run_id="p16-smoke-shadow-review-decisions-2026-08-29",
        decision_date="2026-08-29",
        operator_id="operator",
    )
    decision_paths = write_shadow_review_decisions(decisions, output_path / "p16")
    read_rows = load_shadow_review_decision_read_model_rows(decision_paths["json_path"])
    run = read_rows["run"]
    groups = read_rows["groups"]

    return {
        "p15_shadow_analytics_review_json_path": str(p15_json_path),
        "p16_shadow_review_decisions_json_path": decision_paths["json_path"],
        "p16_shadow_review_decisions_groups_csv_path": decision_paths["groups_csv_path"],
        "p16_shadow_review_decisions_markdown_path": decision_paths["markdown_path"],
        "source_group_count": int(p15_payload.get("group_count") or len(p15_payload.get("groups") or [])),
        "decision_group_count": int(run["group_count"]),
        "read_model_group_count": len(groups),
        "decision_statuses": sorted({str(row["decision_status"]) for row in groups}),
        "decision_buckets": sorted({str(row["decision_bucket"]) for row in groups}),
        "group_keys": sorted({str(row["group_key"]) for row in groups}),
        "source_p15_review_run_ids": list(run["source_p15_review_run_ids"]),
        "manual_review_required": bool(run["manual_review_required"]),
        "auto_trade_enabled": bool(run["auto_trade_enabled"]),
        "production_watchlist_enabled": bool(run["production_watchlist_enabled"]),
        "production_write_enabled": bool(run["production_write_enabled"]),
    }
