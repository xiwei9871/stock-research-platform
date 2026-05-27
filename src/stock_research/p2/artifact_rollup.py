from __future__ import annotations

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
