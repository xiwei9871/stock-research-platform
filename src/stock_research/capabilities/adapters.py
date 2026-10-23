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
    GAP_ATTRIBUTION_UNKNOWN, GAP_MISSING_SOURCE, GAP_UNPARSED,
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


_NODE_CLAIM_ROLES = {
    "supply_scarcity", "non_substitutability", "market_structure",
    "entry_barrier", "hype",
}


def _claims_by_role(claims: list[dict[str, Any]], roles: set[str],
                    invert: bool = False) -> list[dict[str, Any]]:
    out = []
    for c in claims:
        role = c.get("claim_role") or "market_structure"
        if (role not in _NODE_CLAIM_ROLES) if invert else (role in roles):
            out.append({
                "claim_id": c["claim_id"], "dimension": c.get("dimension"),
                "claim_role": role, "verdict": c.get("verdict"),
                "claim_text": c.get("claim_text"),
                "evidence_ids": list(c.get("evidence_ids") or ()),
                "support_count": c.get("support_count", 0),
                "refute_count": c.get("refute_count", 0),
            })
    return out


def cap03_orchestrate(
    theme_id: str,
    case_paths: Sequence[str],
    as_of: str,
    run_id: str,
) -> ResearchEnvelope:
    """Theme → nodes → companies → research-task orchestration (R0)."""
    nodes: list[dict[str, Any]] = []
    tasks: list[dict[str, str]] = []
    invalid: list[dict[str, str]] = []
    for p in case_paths:
        try:
            case = load_node_case(p)
        except Exception as exc:
            invalid.append({"case_path": p, "error": str(exc)})
            continue
        members = [m["stock_code"] for m in case.get("member_companies", [])]
        nodes.append({
            "node_id": case["node_id"], "name": case["node_name"],
            "product_lines": sorted(case.get("product_lines") or []),
            "members": members,
        })
        for m in members:
            tasks.append({
                "subject_type": "company", "subject_id": str(m),
                "capability": "CAP-01", "node_id": case["node_id"],
            })
    if nodes and invalid:
        status = "partial"
    elif nodes:
        status = "ok"
    else:
        status = "unknown"
    return make_envelope(
        "CAP-03", "theme", theme_id, as_of, run_id,
        status=status,
        findings={
            "theme_id": theme_id,
            "nodes": nodes,
            "research_tasks": tasks,
            "task_count": len(tasks),
            "invalid_cases": invalid,
        },
        uncertainties=tuple(
            f"invalid_case:{i['case_path']}:{i['error']}" for i in invalid
        ) or (() if nodes else ("no node cases provided",)),
        data_gaps=[] if nodes else [DataGap(
            kind=GAP_MISSING_SOURCE, item=f"node_cases:{theme_id}",
            note="theme→node case files missing")],
    )


def _index_cases(case_dir: str | Path) -> dict[str, dict[str, Any]]:
    """Scan a case dir → {node_id: {path, derived_from}}; skips unreadable."""
    out: dict[str, dict[str, Any]] = {}
    for p in sorted(Path(case_dir).glob("*.json")):
        try:
            case = load_node_case(str(p))
        except Exception:
            continue
        out[case["node_id"]] = {
            "path": str(p),
            "case_node_id": case["node_id"],
            "derived_from": case.get("derived_from") or "",
            "theme_node_id": case.get("theme_node_id") or "",
        }
    return out


def _match_case_meta(theme_node_id: str,
                     case_index: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Theme node → case metadata.  Deterministic linkage:
    explicit theme_node_id > node_id equality > derived_from lineage >
    sub-node prefix."""
    return [
        meta for nid, meta in case_index.items()
        if (
            meta.get("theme_node_id") == theme_node_id
            or nid == theme_node_id
            or nid.endswith(f"_{theme_node_id}")
            or nid.startswith(f"{theme_node_id}_")
            or theme_node_id in (meta["derived_from"] or "")
            or nid.replace("ai_power_", "") == theme_node_id
        )
    ]


def cap03_orchestrate_theme(
    theme_id: str,
    as_of: str,
    run_id: str,
    case_dir: str = "docs/cap02/cases",
    artifact_dir: str | None = None,
    mapping_dir: str | None = None,
) -> ResearchEnvelope:
    """R1: orchestrate from the theme read layer — reuses
    ``dashboard.theme_research`` (PostgreSQL ``db`` / ``artifact`` /
    ``compare`` per THEME_RESEARCH_READ_SOURCE, artifact as controlled
    fallback).  Unreviewed company mappings generate pending tasks, never
    confirmed relations.  Nodes without cases become CAP-02 coverage tasks
    (capability gap, not an external DATA gap)."""
    from stock_research.dashboard.theme_research import (
        configured_theme_research_read_source,
        list_theme_research_companies,
        list_theme_research_nodes,
    )

    requested_source = configured_theme_research_read_source()
    effective_source = requested_source
    source_note = ""
    try:
        node_rows = list_theme_research_nodes(
            theme_id, read_source=requested_source)["items"]
        company_rows = list_theme_research_companies(
            theme_id, read_source=requested_source)["items"]
    except Exception as exc:
        # Controlled fallback: artifact read when the configured source
        # (e.g. db) is unreachable — never silent.
        effective_source = "artifact"
        source_note = f"{requested_source}_unavailable:{exc}"
        try:
            node_rows = list_theme_research_nodes(
                theme_id, read_source="artifact")["items"]
            company_rows = list_theme_research_companies(
                theme_id, read_source="artifact")["items"]
        except Exception as exc2:
            return make_envelope(
                "CAP-03", "theme", theme_id, as_of, run_id, status="unknown",
                findings={"error": f"theme_read:{exc2}",
                          "requested_source": requested_source},
                data_gaps=[DataGap(kind=GAP_MISSING_SOURCE,
                                   item=f"theme_package:{theme_id}",
                                   note=str(exc2))],
            )
    if not node_rows:
        return make_envelope(
            "CAP-03", "theme", theme_id, as_of, run_id, status="unknown",
            findings={"error": f"theme {theme_id} not found",
                      "read_source": effective_source},
            data_gaps=[DataGap(kind=GAP_MISSING_SOURCE, item=f"theme:{theme_id}")],
        )

    # as_of/PIT: theme artifacts carry no intrinsic as_of — the envelope
    # records the package provenance and treats rows as a latest snapshot;
    # historical PIT replay requires a versioned package (gap noted).
    pit_note = "theme package is a snapshot without intrinsic as_of; rows read as latest"
    mappings: dict[str, list[dict[str, Any]]] = {}
    for c in company_rows:
        mappings.setdefault(c["mapped_node_id"], []).append(c)

    case_index = _index_cases(case_dir)
    nodes: list[dict[str, Any]] = []
    tasks: list[dict[str, str]] = []
    coverage_gaps: list[str] = []
    for n in node_rows:
        nid = n["node_id"]
        case_metas = _match_case_meta(nid, case_index)
        case_paths = [m["path"] for m in case_metas]
        comps = mappings.get(nid, [])
        reviewed = [c for c in comps
                    if c.get("review_status") in {"approved", "reviewed"}]
        pending = [c for c in comps
                   if c.get("review_status") not in {"approved", "reviewed"}]
        nodes.append({
            "node_id": nid, "name": n.get("node_name"),
            "priority_score": n.get("priority_score"),
            "bottleneck_score": n.get("bottleneck_score"),
            "value_capture_score": n.get("value_capture_score"),
            "node_review_status": n.get("node_review_status"),
            # lineage: a sub-node case derived_from a parent is the same
            # evidence, not independent confirmation
            "runnable_cases": [
                {"path": m["path"], "case_node_id": m.get("case_node_id"),
                 "lineage": m.get("derived_from") or None}
                for m in _match_case_meta(nid, case_index)
            ],
            "mapped_companies": [
                {"company_code": c["company_code"],
                 "review_status": c.get("review_status") or "unknown",
                 "mapping_type": c.get("mapping_type")}
                for c in comps
            ],
        })
        if case_paths:
            tasks.append({"subject_type": "node", "subject_id": nid,
                          "capability": "CAP-02",
                          "cases": ",".join(case_paths)})
        else:
            # capability coverage task — owned by CAP-02, not a DATA gap
            coverage_gaps.append(nid)
            tasks.append({"subject_type": "node", "subject_id": nid,
                          "capability": "CAP-02",
                          "task_type": "coverage_gap"})
        for c in reviewed:
            tasks.append({"subject_type": "company",
                          "subject_id": c["company_code"],
                          "capability": "CAP-01", "node_id": nid})
        for c in pending:
            tasks.append({"subject_type": "company",
                          "subject_id": c["company_code"],
                          "capability": "CAP-01", "node_id": nid,
                          "task_type": "pending_mapping_review"})
    status = "ok" if any(n["runnable_cases"] for n in nodes) else "partial"
    return make_envelope(
        "CAP-03", "theme", theme_id, as_of, run_id, status=status,
        findings={
            "theme_id": theme_id,
            "read_source": effective_source,
            "requested_source": requested_source,
            "source_note": source_note,
            "pit_note": pit_note,
            "node_count": len(node_rows),
            "nodes_with_cases": sum(1 for n in nodes if n["runnable_cases"]),
            "coverage_gap_nodes": coverage_gaps,
            "nodes": nodes,
            "research_tasks": tasks,
            "task_count": len(tasks),
        },
        uncertainties=(source_note,) if source_note else (),
    )


def cap04_tech_supply(
    case_path: str, dossier_dir: str,
    as_of: str, run_id: str,
) -> tuple[ResearchEnvelope, dict[str, Any], dict[str, dict[str, Any]]]:
    """Technology-route & supply-constraint view over a node case (R0)."""
    dossier, dossier_by_code = _build_node_dossier(case_path, dossier_dir)
    node_id = dossier["node_id"]
    claims = dossier["node_claims"]
    # P0-1: views classify by claim_role (frozen five-role taxonomy), never
    # by evidence dimension.  A market_structure claim can cite
    # process_irreplaceability evidence — it is still a roster fact, not
    # scarcity/substitutability proof.
    views = {
        "supply_scarcity": _claims_by_role(claims, {"supply_scarcity"}),
        "non_substitutability": _claims_by_role(claims, {"non_substitutability"}),
        "market_structure": _claims_by_role(claims, {"market_structure"}),
        "entry_barrier": _claims_by_role(claims, {"entry_barrier"}),
        "hype": _claims_by_role(claims, {"hype"}),
        "unclassified": _claims_by_role(claims, set(), invert=True),
    }
    # R2A: structured bottleneck assessment — sub-checks + evidence
    # boundaries; the frozen CAP-02 node_verdict stays untouched.
    from stock_research.capabilities.reasoning import assess_technical
    env = make_envelope(
        "CAP-04", "node", node_id, as_of, run_id,
        status="ok" if claims else "unknown",
        findings={
            "node_verdict": dossier["conclusion"]["node_verdict"],
            "views": views,
            "claim_count": len(claims),
            "technical_assessment": assess_technical(dossier),
            # claim → evidence → source traceability for CAP-08/09
            "evidence_index": {
                r["evidence_id"]: {
                    "evidence_id": r["evidence_id"],
                    "source_id": r.get("source_id"),
                    "direction": r.get("direction"),
                    "aspect": r.get("aspect"),
                    "dimension": r.get("dimension"),
                    "excerpt": r.get("excerpt"),
                    "review_status": r.get("review_status"),
                    "pit_status": r.get("pit_status"),
                    "verdict_weight": r.get("verdict_weight"),
                }
                for r in dossier.get("evidence_matrix", [])
            },
            # flat claim list for CAP-08 hypothesis assessment
            "claims": [
                {k: c.get(k) for k in (
                    "claim_id", "claim_text", "claim_role", "dimension",
                    "verdict", "evidence_ids", "support_count",
                    "refute_count", "unverified_evidence_ids")}
                for c in claims
            ],
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
        # C: consume precise product-line revenue & margin from the matrix
        # cell facts — only exact product_line scope counts; broader segment
        # numbers never flow into the sub-node line.
        rev_cell = row.get("revenue_profit")
        facts = (rev_cell or {}).get("facts") or []
        exact = [f for f in facts if f.get("scope") == "product_line"]
        broader = [f for f in facts
                   if f.get("scope") in {"segment", "industry_board", "company_total"}]
        if exact:
            margin_state = "disclosed" if any(
                f.get("gross_margin") is not None for f in exact) else "unknown"
        elif broader:
            margin_state = "segment_level"  # 板块口径，不下钻产品线
        else:
            margin_state = "unknown"
        # R2A-P1: five mutually independent facts — delivery never
        # upgrades to revenue; cash stays unknown until a source exists.
        stage = (
            "revenue_visible" if exact else
            "delivery_seen" if del_state in {
                "validated", "mass_delivery", "verified_delivered"} else
            "order_seen" if ord_state not in {"missing", "none_seen"} else
            "not_evaluated"
        )
        economics[code] = {
            "revenue_state": rev_state,
            "revenue_value": exact[0]["revenue"] if exact else None,
            "margin_state": margin_state,
            "margin_value": (
                next((f["gross_margin"] for f in exact
                      if f.get("gross_margin") is not None), None)
            ),
            "delivery_state": del_state,
            "order_state": ord_state,
            # P0-2: R0 stays conservative.  disclosed_broader_scope only proves
            # a larger segment exists; verified_delivered is a delivery fact,
            # not an identifiable contract or revenue recognition.  Until a
            # precisely product_line-attributed revenue record exists, no
            # value-capture claim is made.
            "value_capture_verdict": "not_evaluated",
            "value_capture_requires": [
                "product_line_attributed_revenue",
                "operating_evidence(margin/order/cash)",
            ],
            "cash_state": "unknown",
            "commercialization_stage": stage,
            "independent_facts": {
                "revenue": rev_state, "margin": margin_state,
                "order": ord_state, "delivery": del_state,
                "cash": "unknown",
            },
        }
        if rev_state == "unextracted":
            gaps.append(DataGap(kind=GAP_UNPARSED, item=f"product_revenue:{code}",
                                note="source exists, segment table unextracted"))
        elif rev_state in {"missing", "undisclosed"}:
            gaps.append(DataGap(kind=GAP_MISSING_SOURCE, item=f"product_revenue:{code}",
                                note=f"rev_state={rev_state}"))
        if margin_state == "unknown":
            gaps.append(DataGap(kind=GAP_MISSING_SOURCE,
                                item=f"product_gross_margin:{code}"))
        elif margin_state == "segment_level":
            gaps.append(DataGap(kind=GAP_ATTRIBUTION_UNKNOWN,
                                item=f"product_gross_margin:{code}",
                                note="segment margin exists, product line unattributed"))
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
    """Same-node supplier comparison + moat evidence positions (R0).

    R2A: same-scope comparison — ``comparison_scope`` labels every pair
    directly_comparable / partially_comparable / not_comparable /
    insufficient_evidence.  Component suppliers never rank against
    full-system makers; more disclosure never means stronger."""
    from stock_research.capabilities.reasoning import compare_competition
    result = compare_competition(dossier, dossier_by_code)
    return make_envelope(
        "CAP-06", "node", node_id, as_of, run_id,
        status="ok" if result["comparison"] else "not_evaluated",
        findings=result,
        upstream_fingerprints=upstream_fingerprints,
    )


def cap07_changes(
    subject_id: str, current_snapshot: dict[str, Any],
    baseline_snapshots: Iterable[dict[str, Any]] | None,
    as_of: str, run_id: str,
) -> ResearchEnvelope:
    """Dynamic tracking: explainable content diff vs versioned baselines
    (verdicts / claims / economics / cap-statuses), not just fingerprints."""
    from stock_research.capabilities.baseline import diff_baselines

    base = list(baseline_snapshots or [])
    if not base:
        return make_envelope(
            "CAP-07", "node", subject_id, as_of, run_id,
            status="unknown",
            findings={"note": "no baseline snapshot — first run seeds baseline"},
            data_gaps=[DataGap(kind=GAP_MISSING_SOURCE,
                               item=f"baseline_fingerprint:{subject_id}",
                               owner="CAP-07",
                               note="capability run-state, not external data")],
        )
    diff = diff_baselines(current_snapshot, base)
    return make_envelope(
        "CAP-07", "node", subject_id, as_of, run_id,
        status="ok",
        findings={
            **diff,
            "current_fingerprint": current_snapshot.get("dossier_fingerprint"),
            "baseline_count": len(base),
        },
        evidence_refs=tuple(
            c["field"] for c in diff.get("changes", [])[:20]
        ),
    )


def cap08_synthesis(
    subject_id: str, upstream: Sequence[ResearchEnvelope],
    as_of: str, run_id: str,
) -> ResearchEnvelope:
    """Comprehensive verdict: supports / refutes / gaps / priorities (R0)."""
    # R1: five-bucket evidence split.
    #   favorable_support — supply_scarcity / non_substitutability /
    #                       entry_barrier claims with positive verdicts
    #   market_structure  — descriptive roster facts (never auto-refutes)
    #   counter_evidence  — claims actually REFUTED (bound hypothesis +
    #                       qualified opposing evidence); "several suppliers
    #                       exist" alone never becomes counter evidence
    #   hype_risks        — supported hype claims = risk evidence
    #   unresolved        — needs_evidence / unknown claims
    # Every entry carries claim + evidence_ids + source_ids traceability;
    # upstream fingerprints are provenance, not a substitute for evidence.
    favorable: dict[str, dict[str, Any]] = {}
    structure: dict[str, dict[str, Any]] = {}
    counter: dict[str, dict[str, Any]] = {}
    hype_risks: dict[str, dict[str, Any]] = {}
    unresolved: dict[str, dict[str, Any]] = {}
    uncertainties: list[str] = []
    gaps: list[DataGap] = []
    evidence_refs: set[str] = set()
    _POS = {"confirmed", "partially_supported"}
    for env in upstream:
        evidence_index = env.findings.get("evidence_index") or {}
        for view in (env.findings.get("views") or {}).values():
            for c in view:
                cid = c.get("claim_id") or "?"
                role = c.get("claim_role") or "market_structure"
                verdict = c.get("verdict")
                eids = list(c.get("evidence_ids") or ())
                sids = sorted({
                    (evidence_index.get(e) or {}).get("source_id")
                    for e in eids if evidence_index.get(e)
                } - {None})
                entry = {
                    "claim_id": cid, "role": role, "verdict": verdict,
                    "hypothesis": c.get("claim_text"),
                    "evidence_ids": eids, "source_ids": sids,
                    "capability": env.capability_id,
                }
                if verdict in _POS:
                    if role == "hype":
                        hype_risks.setdefault(cid, entry)
                    elif role == "market_structure":
                        structure.setdefault(cid, entry)
                    else:
                        favorable.setdefault(cid, entry)
                elif verdict == "refuted":
                    counter.setdefault(cid, entry)
                else:
                    unresolved.setdefault(cid, entry)
                evidence_refs.update(eids)
        for code, e in (env.findings.get("economics") or {}).items():
            if e.get("value_capture_verdict") == "verified":
                favorable.setdefault(f"vc:{code}", {
                    "claim_id": f"value_capture:{code}", "role": "economics",
                    "verdict": "verified", "hypothesis": "value capture",
                    "evidence_ids": [], "source_ids": [],
                    "capability": env.capability_id,
                })
        uncertainties.extend(f"{env.capability_id}:{u}" for u in env.uncertainties)
        gaps.extend(env.data_gaps)
    # R2A: per-claim hypothesis assessment — built from CAP-04's flat
    # claim list + evidence index (claim/evidence/source traceability).
    hypothesis_assessment: list[dict[str, Any]] = []
    for env in upstream:
        if env.capability_id != "CAP-04":
            continue
        from stock_research.capabilities.reasoning import assess_hypotheses
        ev_index = env.findings.get("evidence_index") or {}
        hypothesis_assessment.extend(assess_hypotheses(
            env.findings.get("claims") or [], ev_index,
            subject_id, as_of))
    status = "ok" if (favorable or structure or counter or hype_risks) else (
        "partial" if upstream else "unknown")
    return make_envelope(
        "CAP-08", "node", subject_id, as_of, run_id, status=status,
        findings={
            "favorable_support": list(favorable.values()),
            "market_structure": list(structure.values()),
            "counter_evidence": list(counter.values()),
            "hype_risks": list(hype_risks.values()),
            "unresolved": list(unresolved.values()),
            "hypothesis_assessment": hypothesis_assessment,
            "support_claim_count": len(favorable),
            "uncertainties": uncertainties,
            "next_verification": sorted({g.item for g in gaps})[:10],
            "research_priority": [
                g.item for g in gaps if g.kind == GAP_MISSING_SOURCE
            ][:10],
        },
        evidence_refs=sorted(evidence_refs),
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
