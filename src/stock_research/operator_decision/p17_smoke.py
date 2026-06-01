from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from stock_research.operator_decision.p16_smoke import build_p16_shadow_review_decisions_smoke
from stock_research.operator_decision.shadow_follow_up_queue import (
    build_shadow_follow_up_queue,
    write_shadow_follow_up_queue,
)
from stock_research.operator_decision.shadow_follow_up_queue_read_model import (
    load_shadow_follow_up_queue_read_model_rows,
)


def build_p17_shadow_follow_up_queue_smoke(output_dir: str | Path) -> dict[str, Any]:
    output_path = Path(output_dir)
    p16_result = build_p16_shadow_review_decisions_smoke(output_path)
    p16_json_path = Path(p16_result["p16_shadow_review_decisions_json_path"])
    p16_payload = json.loads(p16_json_path.read_text(encoding="utf-8"))

    queue = build_shadow_follow_up_queue(
        p16_decisions=p16_payload,
        run_id="p17-smoke-shadow-follow-up-queue-2026-08-29",
        follow_up_date="2026-08-29",
        operator_id="operator",
    )
    queue_paths = write_shadow_follow_up_queue(queue, output_path / "p17")
    read_rows = load_shadow_follow_up_queue_read_model_rows(queue_paths["json_path"])
    run = read_rows["run"]
    items = read_rows["items"]

    return {
        "p16_shadow_review_decisions_json_path": str(p16_json_path),
        "p17_shadow_follow_up_queue_json_path": queue_paths["json_path"],
        "p17_shadow_follow_up_queue_items_csv_path": queue_paths["items_csv_path"],
        "p17_shadow_follow_up_queue_markdown_path": queue_paths["markdown_path"],
        "source_decision_group_count": int(p16_payload.get("group_count") or len(p16_payload.get("groups") or [])),
        "follow_up_item_count": int(run["item_count"]),
        "read_model_item_count": len(items),
        "follow_up_statuses": sorted({str(row["follow_up_status"]) for row in items}),
        "priority_buckets": sorted({str(row["priority_bucket"]) for row in items}),
        "group_keys": sorted({str(row["group_key"]) for row in items}),
        "source_p16_decision_run_ids": list(run["source_p16_decision_run_ids"]),
        "manual_review_required": bool(run["manual_review_required"]),
        "auto_trade_enabled": bool(run["auto_trade_enabled"]),
        "production_watchlist_enabled": bool(run["production_watchlist_enabled"]),
        "production_write_enabled": bool(run["production_write_enabled"]),
    }
