"""CAP-09 workbench API — serves the unified capability browse indexes
emitted to ``outputs/research/cap_workbench/<theme>/index.json`` by the
cap-chain pipeline.  Read-only; never touches research state.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def workbench_dir() -> Path:
    raw = os.environ.get("STOCK_RESEARCH_CAP_WORKBENCH_DIR", "").strip()
    if raw:
        return Path(raw)
    return Path("outputs/research/cap_workbench")


def list_workbench_themes() -> dict[str, Any]:
    root = workbench_dir()
    items = []
    if root.is_dir():
        for idx in sorted(root.glob("*/index.json")):
            try:
                doc = json.loads(idx.read_text(encoding="utf-8"))
            except Exception:
                continue
            items.append({
                "theme_id": doc.get("theme_id"),
                "as_of": doc.get("as_of"),
                "run_id": doc.get("run_id"),
                "node_count": len(doc.get("nodes") or []),
                "gap_count": len(doc.get("gap_backlog") or []),
                "research_only": True,
            })
    return {"themes": items, "workbench_dir": str(root)}


def load_workbench_index(theme_id: str) -> dict[str, Any] | None:
    safe = "".join(ch for ch in str(theme_id) if ch.isalnum() or ch in "_-")
    path = workbench_dir() / safe / "index.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
