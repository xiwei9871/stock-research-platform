from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def build_p2_artifact_rollup(manifest: dict[str, Any]) -> dict[str, Any]:
    trade_date = str(manifest.get("trade_date") or "")
    run_id = str(manifest.get("run_id") or "")
    artifacts = manifest.get("artifacts")
    if not trade_date:
        raise ValueError("p2 artifact rollup requires trade_date")
    if not run_id:
        raise ValueError("p2 artifact rollup requires run_id")
    if not isinstance(artifacts, list):
        raise ValueError("p2 artifact rollup requires artifacts list")

    rows = []
    for item in artifacts:
        path = str(item["path"])
        required = bool(item.get("required"))
        exists = Path(path).exists()
        rows.append(
            {
                "group": str(item["group"]),
                "name": str(item["name"]),
                "path": path,
                "required": required,
                "exists": exists,
            }
        )

    missing_required_count = sum(1 for row in rows if row["required"] and not row["exists"])
    warning_count = sum(1 for row in rows if not row["required"] and not row["exists"])
    status = "blocked" if missing_required_count else "warning" if warning_count else "ready"
    return {
        "trade_date": trade_date,
        "run_id": run_id,
        "status": status,
        "artifact_count": len(rows),
        "missing_required_count": missing_required_count,
        "warning_count": warning_count,
        "groups": sorted({row["group"] for row in rows}),
        "artifacts": rows,
    }


def write_p2_artifact_rollup(
    rollup: dict[str, Any],
    output_dir: str | Path,
) -> dict[str, str]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    stem = f"p2_artifact_rollup_{rollup['trade_date']}_{rollup['run_id']}"
    json_path = output_path / f"{stem}.json"
    markdown_path = output_path / f"{stem}.md"
    json_path.write_text(
        json.dumps(rollup, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    markdown_path.write_text(_render_rollup_markdown(rollup), encoding="utf-8")
    return {"json_path": str(json_path), "markdown_path": str(markdown_path)}


def _render_rollup_markdown(rollup: dict[str, Any]) -> str:
    lines = [
        f"# P2 Artifact Rollup {rollup['trade_date']}",
        "",
        f"- Run ID: `{rollup['run_id']}`",
        f"- Status: `{rollup['status']}`",
        f"- Artifacts: {rollup['artifact_count']}",
        f"- Missing required: {rollup['missing_required_count']}",
        f"- Warnings: {rollup['warning_count']}",
        "",
        "## Groups",
        "",
    ]
    for group in rollup["groups"]:
        lines.append(f"- {group}")

    lines.extend(
        [
            "",
            "## Artifacts",
            "",
            "| group | name | required | exists | path |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for row in rollup["artifacts"]:
        lines.append(
            "| "
            + " | ".join(
                [
                    _markdown_cell(row["group"]),
                    _markdown_cell(row["name"]),
                    "yes" if row["required"] else "no",
                    "yes" if row["exists"] else "no",
                    _markdown_cell(row["path"]),
                ]
            )
            + " |"
        )
    return "\n".join(lines) + "\n"


def _markdown_cell(value: Any) -> str:
    return str(value).replace("|", r"\|").replace("\n", "<br>")
