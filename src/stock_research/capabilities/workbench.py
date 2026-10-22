"""CAP-09 workbench index — unified read-only browse artifact.

Reuses the existing dashboard deep-link conventions (``/tech-bottleneck/
stock/<code>?source=theme_research``) and emits one JSON index per theme
run under ``outputs/research/cap_workbench/<theme>/index.json`` — themes →
nodes → companies → evidence refs → envelopes → DATA/CAP gaps.  UI polish
is explicitly out of scope; the contract is the index.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def build_workbench_index(chain_out: dict[str, Any]) -> dict[str, Any]:
    """Chain output → unified browse index."""
    cap03 = chain_out["envelopes"].get("CAP-03", {})
    nodes_meta = {
        n["node_id"]: n
        for n in (cap03.get("findings") or {}).get("nodes", [])
    }
    nodes = []
    for node_id, envs in chain_out.get("per_node", {}).items():
        if node_id.endswith("__error"):
            nodes.append({
                "node_id": node_id, "status": "error",
                "error": envs["CAP-04"].get("findings", {}).get("error"),
            })
            continue
        env4 = envs["CAP-04"]["findings"]
        env8 = envs["CAP-08"]["findings"]
        env6 = envs["CAP-06"]["findings"]
        nodes.append({
            "node_id": node_id,
            "theme_node": (nodes_meta.get(node_id) or {}).get("name"),
            "node_verdict": env4.get("node_verdict"),
            "cap_statuses": {c: e["status"] for c, e in envs.items()},
            "companies": [
                {"stock_code": code,
                 "dashboard_link": f"/tech-bottleneck/stock/{code}?source=capabilities",
                 **{k: v for k, v in row.items()
                    if k in {"overall_verdict", "delivery", "revenue", "order"}}}
                for code, row in (env6.get("comparison") or {}).items()
            ],
            "synthesis": {
                "favorable_support": env8.get("supports", []),
                "market_structure": env8.get("market_structure", []),
                "counter_evidence": env8.get("counter_evidence", []),
                "hype_risks": env8.get("hype_risks", []),
                "unresolved": env8.get("unresolved", []),
            },
            "evidence_refs": env8.get("evidence_refs", []),
            "upstream_fingerprints": env8.get("upstream_fingerprints", []),
        })
    gap_summary: dict[str, int] = {}
    for g in chain_out.get("gap_backlog", []):
        key = f"{g['owner']}:{g['kind']}"
        gap_summary[key] = gap_summary.get(key, 0) + 1
    return {
        "theme_id": chain_out.get("theme_id"),
        "as_of": chain_out.get("as_of"),
        "run_id": chain_out.get("run_id"),
        "nodes": nodes,
        "gap_summary": gap_summary,
        "gap_backlog": chain_out.get("gap_backlog", []),
        "errors": chain_out.get("errors", []),
        "research_only": True,
    }


def write_workbench_index(
    chain_out: dict[str, Any], workbench_dir: str | Path,
) -> str:
    theme = chain_out.get("theme_id") or "unknown_theme"
    path = Path(workbench_dir) / theme / "index.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(
        build_workbench_index(chain_out), ensure_ascii=False, indent=1,
    ), encoding="utf-8")
    return str(path)
