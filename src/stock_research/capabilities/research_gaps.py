"""CAP-R2C P1/P2 — evidence-traceable research gap inventory and
explainable priority scoring.

A gap is a (theme, node, company, dimension) cell whose required fact
class is missing or weaker than the node's need.  Every gap carries a
traceable ``basis`` (record ids / states that justify the category) —
classification is a deterministic function of observed evidence states,
never free-text judgment.

Categories (frozen taxonomy):
  not_searched            — no dossier and no record of this fact class
                            was ever collected for the company
  searched_not_found      — collection happened; the fact is absent or
                            only weaker ladder states exist
  out_of_node_scope       — qualified records exist but pinned to product
                            lines outside this node
  out_of_pit              — records exist only after the PIT cutoff
  pending_review          — records exist but review_status isn't
                            accepted/verified
  stale_evidence          — accepted evidence exists but predates the
                            freshness horizon for a live conclusion
  contradictory_evidence  — qualified support AND counter evidence on
                            the same claim/dimension
  insufficient_granularity— facts exist at a broader scope than needed
                            (industry_board/segment/company when a
                            product_line fact is required)
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

GAP_CATEGORIES = (
    "not_searched", "searched_not_found", "out_of_node_scope",
    "out_of_pit", "pending_review", "stale_evidence",
    "contradictory_evidence", "insufficient_granularity",
)

_STATE_TO_CATEGORY = {
    "out_of_node_scope": "out_of_node_scope",
    "out_of_pit": "out_of_pit",
    "pending_review": "pending_review",
    "disclosed_broader_scope": "insufficient_granularity",
    "broader_scope_only": "insufficient_granularity",
    "customer_relationship_at_industry_board": "insufficient_granularity",
    "customer_relationship_disclosed_at_industry_board":
        "insufficient_granularity",
    "order_growth_at_industry_board": "insufficient_granularity",
    "validated_unspecified_customer": "insufficient_granularity",
}
_MISSING_STATES = {
    "unknown", "none_seen", "missing", "undisclosed",
    "no_major_contract_disclosure", "claims_only",
}
_PARTIAL_LADDER = {"lead_only", "contact", "testing", "sample_sent",
                   "small_batch", "intent"}
_SATISFIED_STATES = {
    "product_certified", "participating", "validated", "certified",
    "verified_delivered", "confirmed", "verified", "present",
    "disclosed", "attributed",
}
_STALE_HORIZON_YEARS = 2  # evidence older than ~2 years is stale for live facts

# What closes the gap + where it plausibly lives (annual-report source
# classes first — they are the reachable ones in this dataset).
_DIMENSION_CLOSURE = {
    "product_certification": (
        ["product_level_certification_disclosure"],
        ["annual_report_product_section", "certification_body_notice"]),
    "ecosystem_participation": (
        ["ecosystem_partner_list_or_certificate"],
        ["partner_official_ecosystem_list", "announcement"]),
    "customer_validation": (
        ["named_customer_validated_record_product_line_scope"],
        ["annual_report_customer_section", "design_win_announcement"]),
    "commercial_delivery": (
        ["product_line_scoped_delivery_or_acceptance_record"],
        ["annual_report", "delivery_or_contract_announcement"]),
    "revenue_attribution": (
        ["product_line_attributed_revenue"],
        ["annual_report_segment_note", "operating_data_announcement"]),
    "profitability": (
        ["product_line_gross_margin"],
        ["annual_report_segment_note"]),
    "order_evidence": (
        ["order_or_bid_award_record"],
        ["contract_announcement", "bid_award_notice"]),
    "cash_realization": (
        ["receivable_or_cash_attribution_disclosure"],
        ["annual_report_notes", "exchange_inquiry_reply"]),
    "technology_demonstration": (
        ["credible_tech_capability_evidence_on_node_line"],
        ["annual_report_rd_section", "third_party_test_report"]),
    "theme_application_attribution": (
        ["theme_scenario_level_revenue_or_customer_disclosure"],
        ["annual_report_scenario_breakdown", "investor_relations_minutes"]),
}
_DIM_WEIGHT = {
    "customer_validation": 3, "commercial_delivery": 3,
    "revenue_attribution": 3, "technology_demonstration": 3,
    "profitability": 2, "cash_realization": 2,
    "product_certification": 2, "ecosystem_participation": 2,
    "theme_application_attribution": 2, "order_evidence": 2,
}
_AVAILABILITY = {
    "revenue_attribution": 3, "profitability": 3,
    "product_certification": 3, "order_evidence": 3,
    "commercial_delivery": 3, "technology_demonstration": 3,
    "theme_application_attribution": 2, "ecosystem_participation": 2,
    "customer_validation": 1, "cash_realization": 1,
}


def _gap_id(theme_id: str, node_id: str, company: str,
            dimension: str, category: str) -> str:
    raw = json.dumps(
        [theme_id, node_id, company or "", dimension, category],
        ensure_ascii=False)
    return "rg-" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:10]


def _year(v: Any) -> int | None:
    m = re.match(r"(\d{4})", str(v or ""))
    return int(m.group(1)) if m else None


def _classify_state(state: str | None) -> str | None:
    """Map an observed fact-state to a gap category (None → satisfied)."""
    s = (state or "").strip()
    if not s or s in _SATISFIED_STATES:
        return None
    if s in _STATE_TO_CATEGORY:
        return _STATE_TO_CATEGORY[s]
    if s in _MISSING_STATES:
        return "searched_not_found"
    if s in _PARTIAL_LADDER:
        return "searched_not_found"
    return "searched_not_found"


def _max_trace_year(trace: list[dict[str, Any]]) -> int | None:
    years = [_year(t.get("effective_as_of")) for t in trace]
    years = [y for y in years if y]
    return max(years) if years else None


def build_gap_inventory(
    per_node: dict[str, dict[str, Any]],
    cap03_findings: dict[str, Any],
    theme_id: str,
    as_of: str,
) -> list[dict[str, Any]]:
    """Enumerate (node × company × dimension) gaps with evidence basis."""
    head_nodes = set(cap03_findings.get("head_node_ids") or [])
    as_of_year = _year(as_of) or 0
    gaps: list[dict[str, Any]] = []

    def _emit(node_id: str, company: str, dimension: str,
              category: str, basis: list[str], note: str) -> None:
        req, srcs = _DIMENSION_CLOSURE.get(
            dimension, ([f"evidence:{dimension}"], ["tbd"]))
        gaps.append({
            "gap_id": _gap_id(theme_id, node_id, company,
                              dimension, category),
            "theme_id": theme_id, "node_id": node_id,
            "company_code": company or None,
            "dimension": dimension, "category": category,
            "basis": sorted(set(b for b in basis if b)),
            "required_evidence": req,
            "suggested_sources": srcs,
            "is_head_node": node_id in head_nodes,
            "note": note,
        })

    for node_id, envs in per_node.items():
        if node_id.endswith("__error"):
            continue
        f5 = (envs.get("CAP-05") or {}).get("findings") or {}
        f6 = (envs.get("CAP-06") or {}).get("findings") or {}
        f8 = (envs.get("CAP-08") or {}).get("findings") or {}
        comparison = f6.get("comparison") or {}
        eco_map = f5.get("economics") or {}

        # node-level contradictory / unresolved hypotheses
        for h in f8.get("hypothesis_assessment") or []:
            hid = h.get("hypothesis_id") or ""
            st = h.get("assessment_state")
            if st == "contested":
                _emit(node_id, "", f"hypothesis:{hid}",
                      "contradictory_evidence",
                      list(h.get("counter_evidence") or []) +
                      list(h.get("supporting_evidence") or []),
                      "合格支持+反证并存，需要能区分的证据")
            elif st == "unresolved" and h.get("decisive_gaps"):
                _emit(node_id, "", f"hypothesis:{hid}",
                      "searched_not_found",
                      list(h.get("decisive_gaps") or []),
                      "假设未决且有决定性缺口")
            elif st == "risk_flagged":
                _emit(node_id, "", f"hypothesis:{hid}",
                      "pending_review",
                      ["theme_mapping_independent_evidence"],
                      "主题映射缺乏独立证据——验证待办")

        for code, eco in eco_map.items():
            comp = comparison.get(code) or {}
            ca = eco.get("commercialization_assessment") or {}
            has_dossier = comp.get("overall_verdict") != "no_dossier"
            rec_ids = list(comp.get("cert_delivery_record_ids") or [])
            rel_facts = [r.get("record_id") for r in
                         ca.get("related_company_facts") or []
                         if r.get("record_id")]
            oos_ids = [eid for sev in
                       (ca.get("stage_evidence") or {}).values()
                       for eid in (sev.get("out_of_scope_evidence_ids") or [])]
            searched_anything = has_dossier or bool(
                rec_ids or rel_facts or
                (eco.get("independent_facts") or {}).get("revenue"))

            dims: dict[str, tuple[str | None, list[str], str]] = {}
            cert = comp.get("cert_facts") or {}
            for d in ("product_certification", "ecosystem_participation",
                      "customer_validation", "commercial_delivery"):
                dims[d] = (cert.get(d), rec_ids, f"cert_facts.{d}")
            facts = eco.get("independent_facts") or {}
            dims["revenue_attribution"] = (
                facts.get("revenue") or eco.get("revenue_state"),
                rel_facts or rec_ids, "economics.revenue")
            dims["profitability"] = (
                facts.get("margin") or eco.get("margin_state"),
                rel_facts, "economics.margin")
            dims["order_evidence"] = (
                facts.get("order") or eco.get("order_state"),
                rec_ids, "economics.order")
            dims["cash_realization"] = (
                facts.get("cash") or eco.get("cash_state"),
                [], "economics.cash")
            dims["theme_application_attribution"] = (
                ca.get("theme_application_attribution"), rel_facts,
                "assessment.theme_application_attribution")

            for dim, (state, basis, note) in dims.items():
                cat = _classify_state(state)
                if cat is None:
                    continue
                if cat in {"searched_not_found"} and not searched_anything:
                    cat = "not_searched"
                if cat == "out_of_node_scope":
                    basis = basis + oos_ids + rel_facts
                if not basis:
                    basis = [f"{note}={state}"]
                _emit(node_id, code, dim, cat, basis,
                      f"{note}={state}")

            # stale: a stage with trace rows but all evidence older than
            # the freshness horizon — the fact existed once, is now dated
            for stage, sev in (ca.get("stage_evidence") or {}).items():
                if sev.get("confirmed"):
                    continue
                trace = sev.get("trace") or []
                latest = _max_trace_year(trace)
                if trace and latest and as_of_year - latest \
                        >= _STALE_HORIZON_YEARS:
                    _emit(node_id, code, stage, "stale_evidence",
                          [t.get("record_id") for t in trace],
                          f"最新有效证据 {latest}，距 as_of 超期")

    # coverage gaps: nodes with no runnable case at all
    for nid in cap03_findings.get("coverage_gap_nodes") or []:
        _emit(nid, "", "node_case", "not_searched",
              [f"coverage_gap_nodes:{nid}"],
              "节点无研究案例——能力覆盖缺口")

    return gaps


def score_gap_priority(
    gap: dict[str, Any],
    per_node: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Explainable research-priority score.  Sub-scores are independent
    deterministic inputs — never a black-box number, and never an
    investment-attractiveness proxy.

    conclusion_impact   — does closing this gap move a research conclusion
    bottleneck_impact   — is the gap on a head/decisive node
    evidence_availability — is the needed evidence plausibly obtainable
    timeliness_need     — is the gap itself a staleness/contradiction risk
    dedup_cost          — how much of the work would repeat known results
    """
    dim = gap.get("dimension") or ""
    cat = gap.get("category") or ""
    w = _DIM_WEIGHT.get(dim, 1)
    conclusion_impact = w if gap.get("is_head_node") else max(w - 1, 1)
    if cat == "contradictory_evidence":
        conclusion_impact = 3
    bottleneck_impact = (3 if gap.get("is_head_node") and w >= 3 else
                         2 if gap.get("is_head_node") else 1)
    availability = _AVAILABILITY.get(dim, 2)
    timeliness = (3 if cat in {"stale_evidence", "out_of_pit"} else
                  2 if cat == "contradictory_evidence" else 1)
    dedup = {"out_of_node_scope": 2, "searched_not_found": 2,
             "insufficient_granularity": 1, "not_searched": 1,
             "contradictory_evidence": 0}.get(cat, 1)

    if conclusion_impact >= 3 and bottleneck_impact >= 2:
        band = "high"
    elif conclusion_impact >= 2 or cat == "contradictory_evidence":
        band = "medium"
    else:
        band = "low"
    reason = (
        f"结论影响{conclusion_impact}({dim}{'·头部节点' if gap.get('is_head_node') else '·非头部'})"
        f"；瓶颈{bottleneck_impact}；可得性{availability}"
        f"；时效{timeliness}；重复成本{dedup}({cat})")
    return {
        "band": band,
        "subscores": {
            "conclusion_impact": conclusion_impact,
            "bottleneck_impact": bottleneck_impact,
            "evidence_availability": availability,
            "timeliness_need": timeliness,
            "dedup_cost": dedup,
        },
        "reason": reason,
    }


# ------------------------------------------------------------ P3 hypotheses

def build_competing_hypotheses(
    per_node: dict[str, dict[str, Any]],
    gaps: list[dict[str, Any]],
    cases: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """CAP-R2C P3 — structured competing-hypothesis cards for named real
    cases.  Each card holds ≥2 explanations with supporting / counter /
    pending evidence drawn from REAL records and open gaps — plus the
    decisive verification that would discriminate the explanations.

    Nothing here is a recommendation; ``current_reading`` only reports
    which explanation the evidence currently *supports*, never upgrades.
    """
    by_key = {}
    for g in gaps:
        by_key.setdefault((g["node_id"], g["company_code"] or ""), []).append(g)

    out: list[dict[str, Any]] = []
    for case in cases:
        node_id, code = case["node_id"], case["company_code"]
        envs = per_node.get(node_id) or {}
        eco = ((envs.get("CAP-05") or {}).get("findings") or {}) \
            .get("economics") or {}
        comp = ((envs.get("CAP-06") or {}).get("findings") or {}) \
            .get("comparison") or {}
        entry = eco.get(code) or {}
        ca = entry.get("commercialization_assessment") or {}
        cert = (comp.get(code) or {}).get("cert_facts") or {}
        facts = entry.get("independent_facts") or {}
        node_gaps = by_key.get((node_id, code), [])

        satisfied = sorted(
            r.get("record_id") for r in ca.get("related_company_facts") or []
            if r.get("record_id"))
        satisfied += sorted(
            i for i, st in {**cert, **facts}.items() if st in _SATISFIED_STATES)
        counter = sorted(
            f"{k}={v}" for k, v in {**cert, **facts}.items()
            if v and _classify_state(v) is not None)
        if ca.get("theme_application_attribution") not in (None, "confirmed"):
            counter.append(
                "theme_application_attribution="
                f"{ca['theme_application_attribution']}")
        pending = sorted({e for g in node_gaps
                          for e in g.get("required_evidence") or []})
        decisive = sorted({e for g in node_gaps
                           if g["category"] in {"insufficient_granularity",
                                                "out_of_node_scope",
                                                "searched_not_found"}
                           for e in g.get("required_evidence") or []})
        gap_refs = sorted(g["gap_id"] for g in node_gaps)

        positive = {
            "id": f"{case['case_id']}:H_broad",
            "statement": "公司既有事实足以支撑主题级研究结论（宽口径解读）",
            "state": "risk_flagged" if counter else "supported",
            "supporting_evidence": satisfied,
            "counter_evidence": counter,
            "pending_evidence": pending,
            "decisive_verification": decisive,
        }
        narrow = {
            "id": f"{case['case_id']}:H_narrow",
            "statement": "事实仅在公司既有口径成立，主题级结论未证实（窄口径解读）",
            "state": "supported" if counter else "unresolved",
            "supporting_evidence": counter + satisfied,
            "counter_evidence": [
                "无可反驳的事实级证据——但口径归属未闭合"],
            "pending_evidence": pending,
            "decisive_verification": decisive,
        }
        out.append({
            "case_id": case["case_id"],
            "node_id": node_id,
            "company_code": code,
            "question": case["question"],
            "hypotheses": [positive, narrow],
            "current_reading": (
                "narrow_supported" if counter else "unresolved"),
            "research_gap_ids": gap_refs,
            "research_only": True,
        })
    return out
