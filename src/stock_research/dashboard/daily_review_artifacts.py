from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def write_daily_review_artifacts(payload: dict[str, Any], output_dir: str | Path) -> dict[str, str]:
    trade_date = str(payload.get("trade_date") or "")[:10]
    if not trade_date:
        raise ValueError("daily_review_trade_date_required")

    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    stem = f"daily_review_lite_{trade_date}"
    json_path = root / f"{stem}.json"
    markdown_path = root / f"{stem}.md"
    manifest_path = root / "manifest.json"
    operator_plan_template_path = root / "operator_plan_template.json"

    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(_render_markdown(payload), encoding="utf-8")

    operator_plan_template = {
        "trade_date": trade_date,
        "status": "draft",
        "items": [],
    }
    operator_plan_template_path.write_text(
        json.dumps(operator_plan_template, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    manifest = {
        "trade_date": trade_date,
        "status": str(payload.get("status") or ""),
        "generated_at": _generated_at(),
        "artifacts": {
            "json_path": str(json_path),
            "markdown_path": str(markdown_path),
            "operator_plan_template_path": str(operator_plan_template_path),
        },
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    return {
        "json_path": str(json_path),
        "markdown_path": str(markdown_path),
        "manifest_path": str(manifest_path),
        "operator_plan_template_path": str(operator_plan_template_path),
    }


def load_daily_review_payload(json_path: str | Path) -> dict[str, Any]:
    return json.loads(Path(json_path).read_text(encoding="utf-8"))


def _render_markdown(payload: dict[str, Any]) -> str:
    trade_date = str(payload.get("trade_date") or "")
    lines = [f"# Daily Review Lite {trade_date}", ""]
    warnings = list(payload.get("warnings") or [])
    if warnings:
        lines.append("## Warnings")
        for warning in warnings:
            lines.append(f"- {warning}")
        lines.append("")

    for section in payload.get("sections") or []:
        lines.append(f"## {section.get('title') or section.get('key')}")
        lines.append(f"Status: {section.get('status') or ''}")
        items = list(section.get("items") or [])
        if not items:
            lines.append("")
            continue
        for item in items:
            lines.append(f"- {item.get('label')}: {item.get('value')}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _generated_at() -> str:
    return datetime.now(timezone.utc).isoformat()
