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

from stock_research.capabilities.reasoning import verification_tasks


def build_workbench_index(chain_out: dict[str, Any]) -> dict[str, Any]:
    """Chain output → unified browse index.  Covers BOTH case-executed
    nodes and theme nodes with no research case (coverage_gap, owner
    CAP-02) — missing capability coverage is visible, never silently
    dropped."""
    cap03 = chain_out["envelopes"].get("CAP-03", {})
    cap03_findings = cap03.get("findings") or {}
    theme_nodes = cap03_findings.get("nodes") or []
    nodes_meta = {n["node_id"]: n for n in theme_nodes}

    # case node_id → theme-node meta (internal case ids, via CAP-03 match)
    case_to_theme: dict[str, dict[str, Any]] = {}
    for tn in theme_nodes:
        for rc in tn.get("runnable_cases") or []:
            key = rc.get("case_node_id") or Path(rc["path"]).stem
            case_to_theme.setdefault(key, tn)

    theme_link = (
        f"/theme-research/{chain_out.get('theme_id')}"
        if cap03_findings.get("node_count") else None
    )
    nodes = []
    covered_theme_nodes: set[str] = set()
    for node_id, envs in chain_out.get("per_node", {}).items():
        if node_id.endswith("__error"):
            nodes.append({
                "node_id": node_id, "status": "error",
                "error": envs["CAP-04"].get("findings", {}).get("error"),
            })
            continue
        env4 = envs["CAP-04"]["findings"]
        env8_env = envs["CAP-08"]
        env8 = env8_env["findings"]
        env6 = envs["CAP-06"]["findings"]
        env7 = envs.get("CAP-07", {}).get("findings") or {}
        env5 = envs.get("CAP-05", {}).get("findings") or {}
        tn = case_to_theme.get(node_id) or nodes_meta.get(node_id) or {}
        if tn.get("node_id"):
            covered_theme_nodes.add(tn["node_id"])
        nodes.append({
            "node_id": node_id,
            "theme_node_id": tn.get("node_id"),
            "theme_node": tn.get("name"),
            "node_verdict": env4.get("node_verdict"),
            "cap_statuses": {c: e["status"] for c, e in envs.items()},
            "companies": [
                {"stock_code": code,
                 "dashboard_link": f"/tech-bottleneck/stock/{code}?source=capabilities",
                 "overall_verdict": row.get("overall_verdict"),
                 "delivery": row.get("delivery_capability"),
                 "revenue": (row.get("revenue_identifiability") or {})
                 .get("revenue"),
                 "order": row.get("order_visibility"),
                 "scope_class": row.get("scope_class"),
                 "cert": row.get("certification_customer_validation"),
                 # R2B.1: four independent facts — no stage label shared
                 "cert_facts": row.get("cert_facts"),
                 "evidence_coverage": row.get("evidence_coverage"),
                 "comparable_with": row.get("comparable_with"),
                 # R2B: commercial-realization stage summary
                 "confirmed_stages": (
                     ((env5.get("economics") or {}).get(code) or {})
                     .get("commercialization_assessment") or {}
                 ).get("confirmed_stages"),
                 # R2B.1: dual attribution — a company product-line fact
                 # is not a theme-application fact
                 "product_line_attribution": (
                     ((env5.get("economics") or {}).get(code) or {})
                     .get("commercialization_assessment") or {}
                 ).get("product_line_attribution"),
                 "theme_application_attribution": (
                     ((env5.get("economics") or {}).get(code) or {})
                     .get("commercialization_assessment") or {}
                 ).get("theme_application_attribution"),
                 "theme_specific_revenue": (
                     ((env5.get("economics") or {}).get(code) or {})
                     .get("commercialization_assessment") or {}
                 ).get("theme_specific_revenue")}
                for code, row in (env6.get("comparison") or {}).items()
            ],
            "pairwise_scope": env6.get("pairwise_scope") or [],
            "scope_classes": env6.get("scope_classes") or {},
            "technical_assessment": {
                area: {
                    "assessment": (env4.get("technical_assessment") or {})
                    .get(area, {}).get("assessment"),
                    "sub_checks": {
                        k: v.get("state") for k, v in
                        ((env4.get("technical_assessment") or {})
                         .get(area, {}).get("sub_checks") or {}).items()
                    },
                }
                for area in ("supply_constraint", "non_substitutability",
                             "entry_barrier")
            },
            "hypothesis_assessment": env8.get("hypothesis_assessment") or [],
            "synthesis": {
                "favorable_support": env8.get("favorable_support", []),
                "market_structure": env8.get("market_structure", []),
                "counter_evidence": env8.get("counter_evidence", []),
                "hype_risks": env8.get("hype_risks", []),
                "unresolved": env8.get("unresolved", []),
            },
            # traceability: envelope TOP-LEVEL fields, never findings
            "evidence_refs": env8_env.get("evidence_refs", []),
            "upstream_fingerprints": env8_env.get("upstream_fingerprints", []),
            "theme_link": theme_link,
            "changes": {
                "baseline_found": env7.get("baseline_found"),
                "baseline_version": env7.get("baseline_version"),
                "state_changed": env7.get("state_changed"),
                "added": env7.get("added"),
                "removed": env7.get("removed"),
                "changed": env7.get("changed"),
                "materiality": env7.get("materiality"),
                "items": env7.get("changes") or [],
            } if env7 else None,
        })
    # theme nodes with NO research case — capability coverage, owner CAP-02
    for tn in theme_nodes:
        if tn.get("runnable_cases") or tn["node_id"] in covered_theme_nodes:
            continue
        nodes.append({
            "node_id": tn["node_id"],
            "theme_node_id": tn["node_id"],
            "theme_node": tn.get("name"),
            "status": "no_case",
            "coverage": "coverage_gap",
            "coverage_owner": "CAP-02",
            "cap_statuses": {"CAP-02": "coverage_gap", "CAP-03": "ok"},
            "node_review_status": tn.get("node_review_status"),
            "bottleneck_score": tn.get("bottleneck_score"),
            "value_capture_score": tn.get("value_capture_score"),
            "mapped_companies": [
                {"stock_code": c["company_code"],
                 "review_status": c.get("review_status"),
                 "dashboard_link": (
                     f"/tech-bottleneck/stock/{c['company_code']}"
                     "?source=capabilities"
                 )}
                for c in tn.get("mapped_companies") or []
            ],
            "theme_link": theme_link,
        })
    gap_summary: dict[str, int] = {}
    for g in chain_out.get("gap_backlog", []):
        key = f"{g['owner']}:{g['kind']}"
        gap_summary[key] = gap_summary.get(key, 0) + 1
    return {
        "theme_id": chain_out.get("theme_id"),
        "as_of": chain_out.get("as_of"),
        "run_id": chain_out.get("run_id"),
        "theme_link": theme_link,
        "read_source": cap03_findings.get("read_source"),
        "pit_note": cap03_findings.get("pit_note"),
        "theme_node_count": len(theme_nodes),
        "covered_node_count": len(covered_theme_nodes),
        "theme_synthesis": chain_out.get("theme_synthesis"),
        # R2B/R2C: proposed verification tasks — read-only, never
        # auto-trigger.  Prefer the gap-linked list computed by the
        # chain; recompute only for direct (non-chain) callers.
        "verification_tasks": chain_out.get("verification_tasks")
        or verification_tasks(
            chain_out.get("per_node", {}), cap03_findings,
            chain_out.get("theme_id") or ""),
        # R2C: research gap inventory summary (categories × bands)
        "research_gap_summary": _gap_category_summary(
            chain_out.get("research_gaps")),
        "nodes": nodes,
        "gap_summary": gap_summary,
        "gap_backlog": chain_out.get("gap_backlog", []),
        "errors": chain_out.get("errors", []),
        "research_only": True,
    }


def _gap_category_summary(
    gaps: list[dict[str, Any]] | None,
) -> dict[str, Any] | None:
    if gaps is None:
        return None
    by_cat: dict[str, int] = {}
    by_band: dict[str, int] = {}
    for g in gaps:
        by_cat[g["category"]] = by_cat.get(g["category"], 0) + 1
        band = (g.get("priority") or {}).get("band")
        if band:
            by_band[band] = by_band.get(band, 0) + 1
    return {"total": len(gaps), "by_category": by_cat,
            "by_priority_band": by_band}


def write_workbench_index(
    chain_out: dict[str, Any], workbench_dir: str | Path,
) -> str:
    theme = chain_out.get("theme_id") or "unknown_theme"
    index = build_workbench_index(chain_out)

    # R2C P4: fold this run's task list + material changes into the
    # append-only per-theme ledger, then stamp each task's current
    # verification_status / last_material_change.  History is never
    # silently overwritten — every transition is recorded.
    from stock_research.capabilities.task_ledger import update_task_ledger
    material_changes: list[dict[str, Any]] = []
    for nid, envs in (chain_out.get("per_node") or {}).items():
        changes = ((envs.get("CAP-07") or {}).get("findings") or {}) \
            .get("changes") or []
        for ch in changes:
            material_changes.append({**ch, "node_id": nid})
    ledger = update_task_ledger(
        str(workbench_dir), theme,
        index.get("verification_tasks") or [], material_changes)
    ltasks = ledger.get("tasks") or {}
    for t in index.get("verification_tasks") or []:
        e = ltasks.get(t["task_id"])
        if e:
            t["verification_status"] = e["verification_status"]
            t["last_material_change"] = e.get("last_material_change")

    path = Path(workbench_dir) / theme / "index.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(index, ensure_ascii=False, indent=1),
                    encoding="utf-8")
    return str(path)
