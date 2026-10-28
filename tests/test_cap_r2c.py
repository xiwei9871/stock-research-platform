"""CAP-R2C contract tests — research-gap taxonomy, priority scoring,
competing hypotheses, task closure, and P0 acceptance supplements.

research_only invariants apply throughout: nothing here may touch
signals, admission, or production scheduling.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from stock_research.capabilities.trace_audit import (
    build_trace_resolver,
    validate_stage_traces,
)


def _resolver_fixture() -> dict:
    return {
        "records": {
            "seg_1": {"record_id": "seg_1", "source_id": "src_a",
                      "review_status": "accepted", "scope": "product_line"},
            "ord_1": {"record_id": "ord_1", "source_id": "src_b",
                      "review_status": "verified", "scope": "product_line"},
        },
        "evidence": {
            "ev_1": {"evidence_id": "ev_1", "source_id": "src_a",
                     "review_status": "accepted"},
        },
        "sources": {"src_a", "src_b"},
    }


def _snap(trace_rows, confirmed=True):
    sev = {"confirmed": confirmed,
           "evidence_ids": [r["record_id"] for r in trace_rows],
           "trace": trace_rows}
    return {"per_node": {"n1": {"CAP-05": {"findings": {"economics": {
        "000001": {"commercialization_assessment": {
            "stage_evidence": {"revenue_attributed": sev}}}}}}}}}


def test_p0a_fully_resolvable_trace_passes():
    rows = validate_stage_traces(_snap([{
        "record_id": "seg_1", "source_id": "src_a",
        "review_status": "accepted", "scope": "product_line",
        "effective_as_of": "2025",
    }]), _resolver_fixture())
    assert len(rows) == 1
    r = rows[0]
    assert r["trace_complete"] is True
    assert r["classification"] == "resolved"
    assert r["unresolved"] == []


def test_p0a_unresolvable_record_fails_resolution():
    rows = validate_stage_traces(_snap([{
        "record_id": "ghost_9", "source_id": "src_a",
        "review_status": "accepted", "scope": "product_line",
        "effective_as_of": "2025",
    }]), _resolver_fixture())
    r = rows[0]
    assert r["trace_complete"] is False
    assert "record_id:ghost_9" in r["unresolved"]
    # confirmed stage with no valid direct evidence → contract breach
    assert r["gate_breach"] is True


def test_p0a_unconfirmed_stage_missing_trace_is_expected_gap_not_fault():
    rows = validate_stage_traces(
        _snap([], confirmed=False), _resolver_fixture())
    r = rows[0]
    assert r["trace_complete"] is False
    assert r["gate_breach"] is False
    assert r["classification"] == "expected_gap"


def test_p0a_bad_review_status_and_scope_flagged():
    rows = validate_stage_traces(_snap([{
        "record_id": "ord_1", "source_id": "src_b",
        "review_status": "bogus_state", "scope": None,
        "effective_as_of": "not-a-date!!",
    }]), _resolver_fixture())
    r = rows[0]
    joined = ";".join(r["unresolved"])
    assert "review_status" in joined
    assert "scope" in joined
    assert "effective_as_of" in joined


# ---------------------------------------------------------------- P1 gaps
from stock_research.capabilities.research_gaps import (
    build_gap_inventory, score_gap_priority, GAP_CATEGORIES)


def _eco(code, cert=None, econ=None, ca=None, dossier_status="loaded",
         comparison=None):
    """Real shape: CAP-05 economics entry + CAP-06 comparison entry."""
    return {"eco": {code: {
                "independent_facts": econ or {},
                "revenue_state": (econ or {}).get("revenue"),
                "margin_state": (econ or {}).get("margin"),
                "order_state": (econ or {}).get("order"),
                "cash_state": (econ or {}).get("cash"),
                "commercialization_assessment": ca or {},
            }},
            "comparison": {code: comparison or {
                "overall_verdict": dossier_status,
                "cert_facts": cert or {},
                "cert_delivery_record_ids": []}}}


def _node(eco_bundles, hypotheses=None, contested=None):
    """Accepts one bundle from _eco() or a list of them."""
    if isinstance(eco_bundles, dict) and "eco" in eco_bundles:
        eco_bundles = [eco_bundles]
    eco_map, comp_map = {}, {}
    for b in eco_bundles:
        eco_map.update(b["eco"])
        comp_map.update(b["comparison"])
    f5 = {"economics": eco_map}
    f6 = {"comparison": comp_map}
    f8 = {"hypothesis_assessment": hypotheses or []}
    return {"CAP-05": {"findings": f5},
            "CAP-06": {"findings": f6},
            "CAP-08": {"findings": f8}}


def test_p1_gap_categories_cover_taxonomy():
    assert {"not_searched", "searched_not_found", "out_of_node_scope",
            "out_of_pit", "pending_review", "stale_evidence",
            "contradictory_evidence", "insufficient_granularity"} \
        == set(GAP_CATEGORIES)


def test_p1_oos_and_granularity_classified_from_traceable_states():
    per_node = {"n1": _node(_eco(
        "603757",
        cert={"product_certification": "product_certified",
              "ecosystem_participation": "none_seen",
              "customer_validation": "contact",
              "commercial_delivery": "verified_delivered"},
        econ={"revenue": "disclosed_broader_scope"},
    ))}
    gaps = build_gap_inventory(per_node, {}, "t1", "2026-10-23")
    by_dim = {g["dimension"]: g for g in gaps if g["company_code"] == "603757"}
    assert by_dim["ecosystem_participation"]["category"] == "searched_not_found"
    # contact = weak partial evidence, not named-customer validation
    assert by_dim["customer_validation"]["category"] == "searched_not_found"
    # broader-scope revenue exists but not product-line scoped
    assert by_dim["revenue_attribution"]["category"] == "insufficient_granularity"
    assert all(g["gap_id"] for g in gaps)


def test_p1_out_of_node_scope_and_out_of_pit():
    per_node = {"n1": _node(_eco(
        "301018",
        cert={"customer_validation": "out_of_node_scope",
              "commercial_delivery": "out_of_pit"},
    ))}
    gaps = build_gap_inventory(per_node, {}, "t1", "2026-10-23")
    by_dim = {g["dimension"]: g["category"] for g in gaps}
    assert by_dim["customer_validation"] == "out_of_node_scope"
    assert by_dim["commercial_delivery"] == "out_of_pit"


def test_p1_not_searched_vs_searched_not_found():
    per_node = {"n1": _node(
        _eco("002050", cert={"customer_validation": "unknown"},
             dossier_status="no_dossier"))}
    # second company WITH dossier+records but missing the dim
    per_node["n1"]["CAP-05"]["findings"]["economics"]["002051"] = {
        "independent_facts": {"revenue": "missing"},
        "commercialization_assessment": {},
    }
    per_node["n1"]["CAP-06"]["findings"]["comparison"]["002051"] = {
        "overall_verdict": "unverified",
        "cert_facts": {"customer_validation": "none_seen"},
        "cert_delivery_record_ids": ["r1"],
    }
    gaps = {g["company_code"]: g for g in build_gap_inventory(
        per_node, {}, "t1", "2026-10-23")
        if g["dimension"] == "customer_validation"}
    assert gaps["002050"]["category"] == "not_searched"
    assert gaps["002051"]["category"] == "searched_not_found"


def test_p1_contradictory_and_stale():
    per_node = {"n1": _node(
        _eco("002837", cert={
            "commercial_delivery": "verified_delivered"}),
        hypotheses=[{"hypothesis_id": "h1",
                     "assessment_state": "contested"}])}
    # stale: last accepted evidence far before as_of
    per_node["n1"]["CAP-05"]["findings"]["economics"]["002837"][
        "commercialization_assessment"] = {
        "stage_evidence": {"customer_validated": {
            "confirmed": False,
            "trace": [{"record_id": "r1", "effective_as_of": "2023",
                       "review_status": "accepted"}]}}}
    gaps = build_gap_inventory(per_node, {}, "t1", "2026-10-23")
    cats = {g["category"] for g in gaps}
    assert "contradictory_evidence" in cats
    assert "stale_evidence" in cats


def test_p1_gap_id_stable_and_basis_recorded():
    pn = _node(_eco("301018", cert={"customer_validation": "out_of_node_scope"}))
    g1 = build_gap_inventory({"n1": pn}, {}, "t1", "2026-10-23")
    g2 = build_gap_inventory({"n1": pn}, {}, "t1", "2026-10-23")
    assert [g["gap_id"] for g in g1] == [g["gap_id"] for g in g2]
    oos = [g for g in g1 if g["category"] == "out_of_node_scope"][0]
    assert oos["basis"]


# ------------------------------------------------------------- P2 priority
def test_p2_priority_has_explainable_subscores():
    pn = _node(_eco("301018", cert={"customer_validation": "out_of_node_scope"}))
    gaps = build_gap_inventory({"n1": pn}, {}, "t1", "2026-10-23")
    g = gaps[0]
    s = score_gap_priority(g, {"n1": pn})
    for k in ("conclusion_impact", "bottleneck_impact",
              "evidence_availability", "timeliness_need", "dedup_cost"):
        assert k in s["subscores"]
    assert s["band"] in {"high", "medium", "low"}
    assert s["reason"]


def test_p2_head_node_blocking_gap_outranks_coverage_gap():
    head = _node(_eco("301018", cert={
        "customer_validation": "out_of_node_scope"}))
    pn = {"liquid_cooling_cdu_system": head}
    gaps = build_gap_inventory(
        pn, {"head_node_ids": ["liquid_cooling_cdu_system"]},
        "t1", "2026-10-23")
    g = [g for g in gaps if g["dimension"] == "customer_validation"][0]
    s_head = score_gap_priority(g, pn)
    # a coverage gap on a non-head node scores lower on conclusion impact
    pn2 = {"other_node": _node(_eco("301018", cert={
        "customer_validation": "out_of_node_scope"}))}
    g2 = build_gap_inventory(pn2, {}, "t1", "2026-10-23")
    g2 = [g for g in g2 if g["dimension"] == "customer_validation"][0]
    s_other = score_gap_priority(g2, pn2)
    assert s_head["subscores"]["conclusion_impact"] \
        > s_other["subscores"]["conclusion_impact"]


# ------------------------------------------- P3 competing hypotheses
from stock_research.capabilities.research_gaps import (
    build_competing_hypotheses)


def test_p3_competing_hypothesis_structure_real_case():
    """688686: product-line revenue cannot prove theme application."""
    per_node = {"humanoid_vision_sensing": _node(_eco(
        "688686",
        ca={
            "product_line_attribution": "confirmed",
            "theme_application_attribution": "unknown",
            "theme_specific_revenue": "not_evaluated",
            "related_company_facts": [
                {"record_id": "seg_688686_mv_2025FY",
                 "product_line": "machine_vision"}],
            "stage_evidence": {},
        }))}
    gaps = build_gap_inventory(per_node, {}, "t1", "2026-10-23")
    cases = [{"case_id": "opt-688686", "company_code": "688686",
              "node_id": "humanoid_vision_sensing",
              "question": "机器视觉收入是否证明人形机器人商业兑现"}]
    out = build_competing_hypotheses(per_node, gaps, cases)
    assert len(out) == 1
    h = out[0]
    assert len(h["hypotheses"]) >= 2
    joined = json.dumps(h, ensure_ascii=False)
    assert "seg_688686_mv_2025FY" in joined  # real record cited
    states = {x["statement"] for x in h["hypotheses"]}
    assert any("主题" in s or "人形" in s for s in states)
    for x in h["hypotheses"]:
        for k in ("supporting_evidence", "counter_evidence",
                  "pending_evidence", "decisive_verification"):
            assert k in x


# ------------------------------------------------------- P4 task closure
from stock_research.capabilities.reasoning import verification_tasks
from stock_research.capabilities.task_ledger import (
    update_task_ledger, load_task_ledger)


def _pn_with_gap():
    return {"n1": _node(_eco(
        "301018", cert={"customer_validation": "out_of_node_scope"}))}


def test_p4_tasks_carry_gap_id_and_closure_fields(tmp_path):
    pn = _pn_with_gap()
    gaps = build_gap_inventory(pn, {}, "t1", "2026-10-23")
    tasks = verification_tasks(pn, {}, "t1", research_gaps=gaps)
    gap_tasks = [t for t in tasks if t.get("research_gap_id")]
    assert gap_tasks, "expected gap-linked tasks"
    for t in gap_tasks:
        for k in ("suggested_sources", "completion_criteria",
                  "verification_status", "last_material_change"):
            assert k in t
    ids = {t["research_gap_id"] for t in gap_tasks}
    assert ids & {g["gap_id"] for g in gaps}


def test_p4_ledger_proposed_resolved_reopened(tmp_path):
    t = {"task_id": "vt-aaa", "status": "proposed",
         "research_gap_id": "rg-1", "node_id": "n1",
         "company_code": "301018", "related_node_ids": ["n1"]}
    ledger = update_task_ledger(str(tmp_path), "t1", [t], [])
    assert ledger["tasks"]["vt-aaa"]["verification_status"] == "proposed"
    assert len(ledger["tasks"]["vt-aaa"]["history"]) == 1
    # gap closes → task resolves with an appended history entry
    ledger2 = update_task_ledger(str(tmp_path), "t1", [], [])
    assert ledger2["tasks"]["vt-aaa"]["verification_status"] == "resolved"
    assert len(ledger2["tasks"]["vt-aaa"]["history"]) == 2
    # new material counter on the node's hypothesis reopens it
    ch = [{"field": "hypothesis:h1", "materiality": "material",
           "node_id": "n1", "direction": "counter",
           "change_category": "same_source_new_fact"}]
    ledger3 = update_task_ledger(str(tmp_path), "t1", [t], ch)
    assert ledger3["tasks"]["vt-aaa"]["verification_status"] == "reopened"
    assert len(ledger3["tasks"]["vt-aaa"]["history"]) == 3
    assert ledger3["tasks"]["vt-aaa"]["last_material_change"]


def test_p4_repeat_ingestion_no_new_task_no_status_reset(tmp_path):
    t = {"task_id": "vt-bbb", "status": "proposed",
         "research_gap_id": "rg-2", "node_id": "n1",
         "related_node_ids": ["n1"]}
    update_task_ledger(str(tmp_path), "t1", [t], [])
    ledger = update_task_ledger(str(tmp_path), "t1", [t], [])
    # same task re-ingested: single history entry, status untouched
    assert len(ledger["tasks"]["vt-bbb"]["history"]) == 1
    assert ledger["tasks"]["vt-bbb"]["verification_status"] == "proposed"
