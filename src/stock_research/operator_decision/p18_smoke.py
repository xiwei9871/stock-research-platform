from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from stock_research.operator_decision.p17_smoke import build_p17_shadow_follow_up_queue_smoke
from stock_research.operator_decision.shadow_follow_up_resolution import (
    build_shadow_follow_up_resolution,
    write_shadow_follow_up_resolution,
)
from stock_research.operator_decision.shadow_follow_up_resolution_read_model import (
    load_shadow_follow_up_resolution_read_model_rows,
)


def build_p18_shadow_follow_up_resolution_smoke(output_dir: str | Path) -> dict[str, Any]:
    output_path = Path(output_dir)
    p17_result = build_p17_shadow_follow_up_queue_smoke(output_path)
    p17_json_path = Path(p17_result["p17_shadow_follow_up_queue_json_path"])
    p17_payload = json.loads(p17_json_path.read_text(encoding="utf-8"))

    resolution = build_shadow_follow_up_resolution(
        p17_follow_up=p17_payload,
        run_id="p18-smoke-shadow-follow-up-resolution-2026-08-29",
        resolution_date="2026-08-29",
        operator_id="operator",
    )
    resolution_paths = write_shadow_follow_up_resolution(resolution, output_path / "p18")
    read_rows = load_shadow_follow_up_resolution_read_model_rows(resolution_paths["json_path"])
    run = read_rows["run"]
    items = read_rows["items"]

    return {
        "p17_shadow_follow_up_queue_json_path": str(p17_json_path),
        "p18_shadow_follow_up_resolution_json_path": resolution_paths["json_path"],
        "p18_shadow_follow_up_resolution_items_csv_path": resolution_paths["items_csv_path"],
        "p18_shadow_follow_up_resolution_markdown_path": resolution_paths["markdown_path"],
        "source_follow_up_item_count": int(p17_payload.get("item_count") or len(p17_payload.get("items") or [])),
        "resolution_item_count": int(run["item_count"]),
        "read_model_item_count": len(items),
        "follow_up_statuses": sorted({str(row["follow_up_status"]) for row in items}),
        "resolution_statuses": sorted({str(row["resolution_status"]) for row in items}),
        "resolution_buckets": sorted({str(row["resolution_bucket"]) for row in items}),
        "group_keys": sorted({str(row["group_key"]) for row in items}),
        "source_p17_follow_up_run_ids": list(run["source_p17_follow_up_run_ids"]),
        "manual_review_required": bool(run["manual_review_required"]),
        "auto_trade_enabled": bool(run["auto_trade_enabled"]),
        "production_watchlist_enabled": bool(run["production_watchlist_enabled"]),
        "production_write_enabled": bool(run["production_write_enabled"]),
    }
