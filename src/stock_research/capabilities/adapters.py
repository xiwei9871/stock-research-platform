"""CAP-00 skeleton adapters — thin reusable envelopes over frozen engines.

Each CAP-* function answers a ResearchEnvelope.  Missing inputs degrade to
``not_evaluated``/``unknown`` with explicit data_gaps; nothing fabricates a
positive finding.  All envelopes carry research_only / no-signal flags.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Sequence

from stock_research.chain_bottleneck import build_node_dossier, load_node_case
from stock_research.chain_value_matrix import build_value_matrix, load_dossiers
from stock_research.company_intelligence import CompanyEvidence
from stock_research.chain_t3_evidence import (
    load_t3_records, rival_supply_as_evidence,
)
from stock_research.capabilities.contract import (
    DataGap, ResearchEnvelope, make_envelope,
    GAP_MISSING_SOURCE, GAP_UNPARSED,
)


def _build_node_dossier(case_path: str, dossier_dir: str | Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """Reproduce the frozen CLI wiring: case → t3 → matrix → node dossier."""
    case = load_node_case(case_path)
    member_codes = [str(m.get("stock_code") or "") for m in case["member_companies"]]
    dossier_by_code = load_dossiers(dossier_dir, member_codes)

    t3 = {"segment_records": (), "rival_supply": ()}
    if case.get("t3_records_path"):
        t3 = load_t3_records(case["t3_records_path"])
    extra_evidence = list(case["evidence"])
    extra_sources = {s.source_id: s for s in case["sources"]}
    for rec in t3["rival_supply"]:
        if rec.node_id != case["node_id"]:
            continue
        ev, src = rival_supply_as_evidence(rec, direction="refute")
        extra_evidence.append(ev)
        extra_evidence.append(CompanyEvidence(
            evidence_id=rec.record_id + "_roster",
            source_id=ev.source_id, dimension=ev.dimension,
            direction="support", excerpt=ev.excerpt,
            page_or_section=ev.page_or_section, confidence=ev.confidence,
            review_status=rec.review_status, checklist_item="供应格局",
            evidence_scope="node", product_line="",
        ))
        extra_sources[src.source_id] = src
    matrix = build_value_matrix(
        node_id=case["node_id"],
        node_name=case["node_name"],
        as_of=case["as_of"],
        member_companies=case["member_companies"],
        dossier_by_code=dossier_by_code,
        node_product_lines=case.get("product_lines"),
        segment_records=t3["segment_records"],
        validation_records=t3.get("customer_validation") or (),
        order_records=t3.get("orders") or (),
    )
    dossier = build_node_dossier(
        node_id=case["node_id"],
        node_name=case["node_name"],
        as_of=case["as_of"],
        node_claims=case["node_claims"],
        evidence=extra_evidence,
        sources=list(extra_sources.values()),
        member_companies=case["member_companies"],
        product_lines=case.get("product_lines"),
        value_matrix=matrix,
        t3={
            "segment_records": t3["segment_records"],
            "rival_supply": t3["rival_supply"],
            "customer_validation": t3.get("customer_validation") or (),
            "orders": t3.get("orders") or (),
        },
        input_snapshot=case["input_snapshot"],
    )
    return dossier, dossier_by_code


def _cell_state(v: Any) -> str:
    """Matrix cells may be a state string or a ``{state, ...}`` cell dict."""
    if isinstance(v, dict):
        return str(v.get("state") or "missing")
    return str(v or "missing")


def _claim_verdicts(claims: list[dict[str, Any]], dims: set[str]) -> list[dict[str, Any]]:
    return [
        {
            "claim_id": c["claim_id"], "dimension": c.get("dimension"),
            "claim_role": c.get("claim_role"), "verdict": c.get("verdict"),
            "claim_text": c.get("claim_text"),
        }
        for c in claims if c.get("dimension") in dims
    ]


def cap03_orchestrate(
    theme_id: str,
    case_paths: Sequence[str],
    as_of: str,
    run_id: str,
) -> ResearchEnvelope:
    """Theme → nodes → companies → research-task orchestration (R0)."""
    nodes: list[dict[str, Any]] = []
    tasks: list[dict[str, str]] = []
    for p in case_paths:
        try:
            case = load_node_case(p)
        except Exception:
            continue
        members = [m["stock_code"] for m in case.get("member_companies", [])]
        nodes.append({
            "node_id": case["node_id"], "name": case["node_name"],
            "product_lines": case.get("product_lines", []),
            "members": members,
        })
        for m in members:
            tasks.append({
                "subject_type": "company", "subject_id": str(m),
                "capability": "CAP-01", "node_id": case["node_id"],
            })
    return make_envelope(
        "CAP-03", "theme", theme_id, as_of, run_id,
        status="ok" if nodes else "unknown",
        findings={
            "theme_id": theme_id,
            "nodes": nodes,
            "research_tasks": tasks,
            "task_count": len(tasks),
        },
        uncertainties=() if nodes else ("no node cases provided",),
        data_gaps=[] if nodes else [DataGap(
            kind=GAP_MISSING_SOURCE, item=f"node_cases:{theme_id}",
            note="theme→node case files missing")],
    )


def cap04_tech_supply(
    case_path: str, dossier_dir: str,
    as_of: str, run_id: str,
) -> tuple[ResearchEnvelope, dict[str, Any], dict[str, dict[str, Any]]]:
    """Technology-route & supply-constraint view over a node case (R0)."""
    dossier, dossier_by_code = _build_node_dossier(case_path, dossier_dir)
    node_id = dossier["node_id"]
    claims = dossier["node_claims"]
    views = {
        "scarcity": _claim_verdicts(claims, {"technology_capability", "process_irreplaceability"}),
        "substitutability": _claim_verdicts(claims, {"process_irreplaceability"}),
        "market_structure": _claim_verdicts(claims, {"market_structure"}),
        "entry_barriers": _claim_verdicts(claims, {"entry_barrier", "certification_barrier", "capacity_constraint"}),
        "hype_check": _claim_verdicts(claims, {"hype_only"}),
    }
    env = make_envelope(
        "CAP-04", "node", node_id, as_of, run_id,
        status="ok" if claims else "unknown",
        findings={
            "node_verdict": dossier["conclusion"]["node_verdict"],
            "views": views,
            "claim_count": len(claims),
        },
        evidence_refs=tuple(
            eid for c in claims for eid in c.get("evidence_ids", ())
        ),
        uncertainties=tuple(
            f"{c['claim_id']}={c['verdict']}" for c in claims
            if c["verdict"] in {"needs_evidence", "unknown"}
        ),
    )
    return env, dossier, dossier_by_code


def cap05_value_economics(
    node_id: str, dossier: dict[str, Any], as_of: str, run_id: str,
    upstream_fingerprints: Sequence[str] = (),
) -> ResearchEnvelope:
    """Industrial economics: revenue/margin/order/delivery states (R0)."""
    rows = (dossier.get("value_matrix") or {}).get("rows") or []
    economics: dict[str, dict[str, Any]] = {}
    gaps: list[DataGap] = []
    for row in rows:
        code = row["stock_code"]
        rev_state = _cell_state(row.get("revenue_profit"))
        ord_state = _cell_state(row.get("verified_orders"))
        del_state = _cell_state(row.get("validation_delivery"))
        economics[code] = {
            "revenue_state": rev_state,
            "margin_state": "unknown",  # 分产品毛利无独立矩阵列 — 如实标注
            "delivery_state": del_state,
            "order_state": ord_state,
            "value_capture_verdict": (
                "verified"
                if rev_state in {"disclosed", "disclosed_broader_scope"}
                and ord_state in {"verified_contracted", "verified_delivered"}
                else "not_evaluated"
            ),
        }
        if rev_state == "unextracted":
            gaps.append(DataGap(kind=GAP_UNPARSED, item=f"product_revenue:{code}",
                                note="source exists, segment table unextracted"))
        elif rev_state in {"missing", "undisclosed"}:
            gaps.append(DataGap(kind=GAP_MISSING_SOURCE, item=f"product_revenue:{code}",
                                note=f"rev_state={rev_state}"))
        gaps.append(DataGap(kind=GAP_MISSING_SOURCE, item=f"product_gross_margin:{code}"))
        if ord_state in {"missing", "none_seen"}:
            gaps.append(DataGap(kind=GAP_MISSING_SOURCE, item=f"verifiable_order:{code}"))
    status = "ok" if economics else "not_evaluated"
    return make_envelope(
        "CAP-05", "node", node_id, as_of, run_id, status=status,
        findings={"economics": economics, "member_count": len(economics)},
        data_gaps=gaps,
        upstream_fingerprints=upstream_fingerprints,
    )


def cap06_competition(
    node_id: str, dossier: dict[str, Any],
    dossier_by_code: dict[str, dict[str, Any]],
    as_of: str, run_id: str,
    upstream_fingerprints: Sequence[str] = (),
) -> ResearchEnvelope:
    """Same-node supplier comparison + moat evidence positions (R0)."""
    rows = (dossier.get("value_matrix") or {}).get("rows") or []
    table: dict[str, dict[str, Any]] = {}
    for row in rows:
        code = row["stock_code"]
        dims = (dossier_by_code.get(code) or {}).get("dimensions") or {}
        table[code] = {
            "company_name": row.get("company_name"),
            "overall_verdict": row.get("overall_verdict") or "no_dossier",
            "tech_participation": row.get("tech_participation"),
            "delivery": _cell_state(row.get("validation_delivery")),
            "revenue": _cell_state(row.get("revenue_profit")),
            "order": _cell_state(row.get("verified_orders")),
            "concept_only_risk": row.get("concept_only_risk"),
            "moat_dimensions": {
                d: dims.get(d, {}).get("verdict")
                for d in ("tech_moat", "competitive_advantage")
            },
        }
    return make_envelope(
        "CAP-06", "node", node_id, as_of, run_id,
        status="ok" if table else "not_evaluated",
        findings={
            "comparison": table,
            "note": "component delivery ≠ full-system substitution; product cert ≠ customer cert",
        },
        upstream_fingerprints=upstream_fingerprints,
    )


def cap07_changes(
    subject_id: str, current_fingerprint: str,
    baseline_fingerprints: Iterable[str] | None,
    as_of: str, run_id: str,
) -> ResearchEnvelope:
    """Dynamic tracking: fingerprint diff vs baseline (R0)."""
    base = list(baseline_fingerprints or [])
    if not base:
        return make_envelope(
            "CAP-07", "node", subject_id, as_of, run_id,
            status="unknown",
            findings={"note": "no baseline fingerprint — cannot diff"},
            data_gaps=[DataGap(kind=GAP_MISSING_SOURCE,
                               item=f"baseline_fingerprint:{subject_id}",
                               note="store prior envelope fingerprint")],
        )
    changed = current_fingerprint not in base
    return make_envelope(
        "CAP-07", "node", subject_id, as_of, run_id,
        status="ok",
        findings={
            "state_changed": changed,
            "current_fingerprint": current_fingerprint,
            "baseline_count": len(base),
        },
        evidence_refs=[current_fingerprint],
    )


def cap08_synthesis(
    subject_id: str, upstream: Sequence[ResearchEnvelope],
    as_of: str, run_id: str,
) -> ResearchEnvelope:
    """Comprehensive verdict: supports / refutes / gaps / priorities (R0)."""
    supports: list[str] = []
    uncertainties: list[str] = []
    gaps: list[DataGap] = []
    for env in upstream:
        for view in (env.findings.get("views") or {}).values():
            for c in view:
                if c.get("verdict") in {"confirmed", "partially_supported"}:
                    supports.append(f"{env.capability_id}:{c['claim_id']}={c['verdict']}")
        for code, e in (env.findings.get("economics") or {}).items():
            if e.get("value_capture_verdict") == "verified":
                supports.append(f"{env.capability_id}:{code}:value_capture")
        uncertainties.extend(f"{env.capability_id}:{u}" for u in env.uncertainties)
        gaps.extend(env.data_gaps)
    status = "ok" if supports else ("partial" if upstream else "unknown")
    return make_envelope(
        "CAP-08", "node", subject_id, as_of, run_id, status=status,
        findings={
            "supports": supports,
            "uncertainties": uncertainties,
            "next_verification": sorted({g.item for g in gaps})[:10],
            "research_priority": [
                g.item for g in gaps if g.kind == GAP_MISSING_SOURCE
            ][:10],
        },
        data_gaps=gaps,
        upstream_fingerprints=[e.fingerprint for e in upstream],
    )


def cap09_workbench(as_of: str, run_id: str) -> ResearchEnvelope:
    """Workbench pointers — reuse existing dashboard/workflow (R0)."""
    endpoints = [
        "dashboard:company_intelligence panel",
        "tech_bottleneck review workflow",
        "research_queue_publish / research_review_actions",
        "dashboard:daily_review_lite",
        "dashboard:backtest_jobs",
    ]
    return make_envelope(
        "CAP-09", "platform", "workbench", as_of, run_id, status="ok",
        findings={
            "reuse_endpoints": endpoints,
            "note": "unified browsing layer — no UI rebuild",
        },
    )


def cap10_strategy_bridge(as_of: str, run_id: str) -> ResearchEnvelope:
    """Strategy-validation pointer — isolated from research findings (R0)."""
    return make_envelope(
        "CAP-10", "portfolio", "strategy_infra", as_of, run_id,
        status="not_evaluated",
        findings={
            "reuse_assets": [
                "backtest", "portfolio_backtest", "vectorized_topn_backtest",
                "factor_eval_batch", "strategy_eod", "performance_tearsheet",
            ],
            "isolation": "research envelopes never enter signals/admission",
        },
    )
