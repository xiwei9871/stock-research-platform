"""CAP-R2A research reasoning layer — pure functions over node dossiers.

Three P0 upgrades share this module:

- ``assess_technical`` (CAP-04): structured bottleneck assessment —
  supply constraint / non-substitutability / entry barrier sub-checks
  with explicit evidence boundaries.  Never overwrites the frozen
  CAP-02 ``node_verdict``.
- ``compare_competition`` (CAP-06): same-scope comparison with
  ``comparison_scope`` labels — component suppliers are never ranked
  against full-system makers.
- ``assess_hypotheses`` (CAP-08): per-claim hypothesis records with
  contested / unresolved / refuted states, alternative explanations,
  decisive gaps and revision triggers.

Honest-degradation rules wired into every function:

- demand growth alone never implies shortage;
- an existing alternative supplier never implies cost-free substitution;
- product certification (Intel/UL tests) never implies customer
  certification or a certification barrier;
- delivery never implies recognized revenue;
- pending_review / lead_only / out-of-PIT evidence never promotes a
  conclusion and is reported under ``excluded_evidence`` instead;
- the same underlying source (e.g. one annual report) counts once —
  ``independent_source_count`` dedupes by ``source_id``.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable


# ---------------------------------------------------------------------------
# evidence eligibility
# ---------------------------------------------------------------------------

_ELIGIBLE_REVIEW = {"accepted", "verified"}
_ELIGIBLE_PIT = {"in_scope", None, ""}


def _eligible(ev: dict[str, Any]) -> bool:
    return (ev.get("review_status") in _ELIGIBLE_REVIEW
            and ev.get("pit_status") in _ELIGIBLE_PIT
            and ev.get("verdict_weight", "counted") == "counted")


def _exclusion_reason(ev: dict[str, Any]) -> str:
    if ev.get("review_status") not in _ELIGIBLE_REVIEW:
        return f"review_status={ev.get('review_status') or 'missing'}"
    if ev.get("pit_status") not in _ELIGIBLE_PIT:
        return f"pit_status={ev.get('pit_status')}"
    return f"verdict_weight={ev.get('verdict_weight')}"


def _ev_index(dossier: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {e["evidence_id"]: e for e in dossier.get("evidence_matrix", [])}


def _split_claim_evidence(
    claim: dict[str, Any], ev_index: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """support / counter / excluded split for one claim's evidence_ids.

    R2B: sources are counted per direction AND as a deduped union —
    supporting and counter evidence never silently merge, and the same
    underlying filing counts once across all citations."""
    sup, ref, exc = [], [], []
    sup_sids: set[str] = set()
    ref_sids: set[str] = set()
    for eid in claim.get("evidence_ids") or []:
        ev = ev_index.get(eid)
        if ev is None:
            exc.append({"evidence_id": eid, "reason": "not_in_matrix"})
            continue
        if not _eligible(ev):
            exc.append({"evidence_id": eid, "reason": _exclusion_reason(ev)})
            continue
        if ev.get("direction") == "refute":
            ref.append(eid)
            if ev.get("source_id"):
                ref_sids.add(ev["source_id"])
        else:
            sup.append(eid)
            if ev.get("source_id"):
                sup_sids.add(ev["source_id"])
    all_sids = sup_sids | ref_sids
    return {
        "support": sup, "counter": ref, "excluded": exc,
        "source_ids": sorted(all_sids),
        "support_source_ids": sorted(sup_sids),
        "counter_source_ids": sorted(ref_sids),
        "supporting_source_count": len(sup_sids),
        "counter_source_count": len(ref_sids),
        "independent_source_count": len(all_sids),
    }


def evidence_boundary(
    claim: dict[str, Any], ev_index: dict[str, dict[str, Any]], as_of: str,
) -> dict[str, Any]:
    """Per-claim evidence boundary — hypothesis, both directions, source
    & review status, research PIT, and unmet necessary conditions."""
    role = claim.get("claim_role") or "market_structure"
    split = _split_claim_evidence(claim, ev_index)
    satisfied = _satisfied_conditions(claim, split, ev_index)
    required = _REQUIRED_EVIDENCE.get(role, [])
    return {
        "claim_id": claim.get("claim_id"),
        "hypothesis": claim.get("claim_text"),
        "role": role,
        "verdict": claim.get("verdict"),
        "as_of": as_of,
        "support_evidence_ids": split["support"],
        "counter_evidence_ids": split["counter"],
        "excluded_evidence": split["excluded"],
        "source_ids": split["source_ids"],
        "support_source_ids": split["support_source_ids"],
        "counter_source_ids": split["counter_source_ids"],
        "supporting_source_count": split["supporting_source_count"],
        "counter_source_count": split["counter_source_count"],
        "independent_source_count": split["independent_source_count"],
        "required_evidence": [
            {"item": r, "met": r in satisfied} for r in required
        ],
        "unmet_conditions": [r for r in required if r not in satisfied],
    }


# necessary evidence per claim role — a claim cannot be positively
# established without these kinds of facts
_REQUIRED_EVIDENCE: dict[str, list[str]] = {
    "supply_scarcity": ["capacity_or_leadtime", "delivery_shortfall",
                        "supplier_count"],
    "non_substitutability": ["alternative_function_check",
                             "performance_parity", "switching_cost"],
    "entry_barrier": ["customer_cert_cycle_cost",
                      "line_validation", "switching_cost"],
    "market_structure": [],
    "hype": [],
}


def _satisfied_conditions(
    claim: dict[str, Any], split: dict[str, Any],
    ev_index: dict[str, dict[str, Any]],
) -> set[str]:
    """Which required-evidence items are satisfied by eligible evidence.

    Conservative keyword mapping — a condition only counts as met when
    an eligible evidence row actually addresses it; absence stays unmet.
    """
    got: set[str] = set()
    dims = {ev_index[e].get("aspect") or ev_index[e].get("dimension")
            for e in split["support"] + split["counter"] if e in ev_index}
    ex = " ".join(str(ev_index[e].get("excerpt") or "")
                  for e in split["support"] if e in ev_index)
    role = claim.get("claim_role")
    if role == "supply_scarcity":
        if dims & {"capacity_constraint"}:
            got.add("supplier_count") if "多" in ex or "供应商" in ex else None
            got.add("capacity_or_leadtime")
        if "交付" in ex or "delivery" in ex.lower():
            got.add("delivery_shortfall")
    elif role == "non_substitutability":
        if dims & {"process_irreplaceability"}:
            got.add("alternative_function_check")
        if "性能" in ex or "performance" in ex.lower():
            got.add("performance_parity")
        if "切换" in ex or "认证" in ex:
            got.add("switching_cost")
    elif role == "entry_barrier":
        if "客户" in ex and ("认证" in ex or "验证" in ex):
            got.add("customer_cert_cycle_cost")
        if "产线" in ex or "量产" in ex:
            got.add("line_validation")
        if "切换" in ex:
            got.add("switching_cost")
    return got


# ---------------------------------------------------------------------------
# CAP-04 structured technical assessment
# ---------------------------------------------------------------------------

def _claim_state(claims: Iterable[dict[str, Any]]) -> str:
    """Aggregate a claim subset into an honest sub-check state."""
    vs = [c.get("verdict") for c in claims]
    if not vs:
        return "no_evidence"
    if any(v == "refuted" for v in vs):
        return "contradicted"
    if any(v in {"confirmed"} for v in vs):
        return "support_seen"
    if any(v == "partially_supported" for v in vs):
        return "partial"
    if any(v == "contested" for v in vs):
        return "contested"
    return "unverified"


def _subcheck(claims: list[dict[str, Any]], note: str,
              extra: dict[str, Any] | None = None) -> dict[str, Any]:
    out = {
        "state": _claim_state(claims),
        "claim_ids": [c["claim_id"] for c in claims],
        "evidence_ids": sorted({e for c in claims
                                for e in (c.get("evidence_ids") or [])}),
        "note": note,
    }
    if extra:
        out.update(extra)
    return out


def assess_technical(dossier: dict[str, Any]) -> dict[str, Any]:
    """CAP-04 R2: structured bottleneck assessment over a node dossier.

    Returns supply_constraint / non_substitutability / entry_barrier
    sub-checks plus per-claim evidence boundaries.  Rollups stay honest:
    every area reports ``unverified`` unless its *specific* conditions
    are evidenced — and descriptive facts never masquerade as verdicts.
    """
    claims = list(dossier.get("node_claims") or [])
    ev_index = _ev_index(dossier)
    by_role: dict[str, list[dict[str, Any]]] = {}
    for c in claims:
        by_role.setdefault(c.get("claim_role") or "market_structure",
                           []).append(c)

    def _by_dim(dim: str) -> list[dict[str, Any]]:
        return [c for c in claims if c.get("dimension") == dim]

    def _kw(*words: str) -> list[dict[str, Any]]:
        return [c for c in claims
                if any(w in str(c.get("claim_text") or "") for w in words)]

    scarcity = by_role.get("supply_scarcity", [])
    structure = by_role.get("market_structure", [])
    barriers = by_role.get("entry_barrier", [])
    nonsub = by_role.get("non_substitutability", [])

    # --- A. supply constraint -------------------------------------------------
    demand_claims = _kw("需求", "增长", "扩产", "景气")
    capacity = [c for c in scarcity if c.get("dimension") == "capacity_constraint"]
    supplier_count = [c for c in structure
                      if "供应商" in str(c.get("claim_text") or "")
                      or "格局" in str(c.get("claim_text") or "")]
    cert_gated = [c for c in barriers if c.get("dimension") == "certification_barrier"]

    rows = (dossier.get("value_matrix") or {}).get("rows") or []
    delivery_states = {
        r["stock_code"]: _cell_state(r.get("validation_delivery"))
        for r in rows
    }
    deliverable = [c for c, s in delivery_states.items()
                   if s in {"validated", "mass_delivery", "verified_delivered"}]
    supply_checks = {
        "demand_growth": _subcheck(
            demand_claims,
            "需求增长为事实描述——本身不证明供给短缺"),
        "capacity_limited": _subcheck(
            capacity, "有效产能/供给约束证据"),
        "effective_delivery_limited": _subcheck(
            [], "交付能力受限观察（矩阵交付格）",
            {"delivery_states": delivery_states,
             "deliverable_companies": deliverable}),
        "supplier_count_limited": _subcheck(
            supplier_count,
            "已验证供应商数量——多供应商是格局事实，不自动否定紧缺也不证明紧缺"),
        "cert_gated_supply": _subcheck(
            cert_gated, "认证门槛造成的有效供给受限（需客户认证证据）"),
    }
    if _claim_state(capacity) in {"support_seen", "partial"} and not (
            _claim_state(supplier_count) in {"support_seen", "partial"}):
        supply_assessment = "plausibly_constrained"
    elif _claim_state(capacity) in {"support_seen", "partial"}:
        supply_assessment = "partially_supported"  # 有产能证据但多供应商并存
    elif _claim_state(supplier_count) in {"support_seen", "partial"} and not scarcity:
        supply_assessment = "unverified"
    else:
        supply_assessment = "unverified"

    # --- B. non-substitutability ----------------------------------------------
    alt_evidence = [e for e in ev_index.values()
                    if e.get("direction") == "refute"
                    and _eligible(e)
                    and (e.get("aspect") or e.get("dimension"))
                    in {"process_irreplaceability"}]
    perf = _by_dim("performance_gap") or [
        c for c in nonsub if "性能" in str(c.get("claim_text") or "")]
    switch_cert = [c for c in claims
                   if c.get("dimension") == "certification_barrier"]
    sub_checks = {
        "functional_alternative_exists": _subcheck(
            supplier_count + [c for c in nonsub
                              if "替代" in str(c.get("claim_text") or "")],
            "存在功能相近替代——存在替代供应商不等于可无成本替代",
            {"alt_evidence_ids": [e["evidence_id"] for e in alt_evidence]}),
        "performance_meets_requirement": _subcheck(
            perf, "替代方案性能是否达标"),
        "switching_cost_cert": _subcheck(
            switch_cert, "替代所需认证与切换成本证据"),
        "switching_time": _subcheck(
            _kw("切换周期", "切换时间", "替代周期"), "替代所需时间证据"),
        "alternative_commercialized": _subcheck(
            [c for c in structure if "量产" in str(c.get("claim_text") or "")
             or "交付" in str(c.get("claim_text") or "")],
            "替代方案是否已实际商业化",
            {"alt_evidence_ids": [e["evidence_id"] for e in alt_evidence
                                  if "量产" in str(e.get("excerpt") or "")
                                  or "交付" in str(e.get("excerpt") or "")]}),
    }
    sub_assessment = (
        "partially_supported" if _claim_state(nonsub) in
        {"support_seen", "partial"} else
        "contradicted" if _claim_state(nonsub) == "contradicted" else
        "unverified"
    )

    # --- C. entry barrier -------------------------------------------------------
    # product certification rows stay product facts; they never feed the
    # customer-certification sub-checks.
    cert_ev = [e for e in ev_index.values()
               if (e.get("aspect") or e.get("dimension"))
               == "certification_barrier"]
    product_cert_ids = [
        e["evidence_id"] for e in cert_ev
        if any(k in str(e.get("excerpt") or "")
               for k in ("Intel", "英特尔", "UL", "测试", "认证", "验证"))
        and "客户" not in str(e.get("excerpt") or "")
    ]
    customer_cert_claims = [c for c in barriers
                            if "客户" in str(c.get("claim_text") or "")]
    barrier_checks = {
        "product_certification": _subcheck(
            cert_gated, "产品级测试/认证事实（Intel/UL 等）——不证明客户认证",
            {"evidence_ids": product_cert_ids}),
        "customer_validation": _subcheck(
            customer_cert_claims, "特定客户认证通过证据（周期/成本/失效率）"),
        "mass_production_line_validation": _subcheck(
            _kw("产线", "量产验证"), "量产线验证证据"),
        "long_term_supply_qualification": _subcheck(
            _kw("长期供应", "供应资格"), "长期供应资格证据"),
        "yield_reliability": _subcheck(
            _kw("良率", "可靠性"), "工艺良率与可靠性证据"),
    }
    barrier_assessment = (
        "partially_supported" if _claim_state(barriers) in
        {"support_seen", "partial"} else "unverified"
    )

    return {
        "supply_constraint": {
            "assessment": supply_assessment,
            "sub_checks": supply_checks,
            "caveat": "需求增长本身不得推导短缺；多供应商格局不自动否定也不证明紧缺",
        },
        "non_substitutability": {
            "assessment": sub_assessment,
            "sub_checks": sub_checks,
            "caveat": "存在替代供应商不等于可无成本替代",
        },
        "entry_barrier": {
            "assessment": barrier_assessment,
            "sub_checks": barrier_checks,
            "caveat": "产品认证（Intel/UL）不证明客户认证壁垒",
        },
        "evidence_boundaries": [
            evidence_boundary(c, ev_index, dossier.get("as_of") or "")
            for c in claims
        ],
    }


# ---------------------------------------------------------------------------
# CAP-06 same-scope competition comparison
# ---------------------------------------------------------------------------

_SCOPE_COMPARABLE: dict[tuple[str, str], tuple[str, str]] = {}

# Validation-ladder stages that attest customer validation progress.
# R2B.1: ``ecosystem`` and ``mass_delivery`` are NOT in this ladder —
# ecosystem membership is not named-customer validation, and
# mass_delivery is a *delivery* fact, never a certification one.
_CUSTOMER_LADDER = ("contact", "sampling", "in_validation", "validated")
_CERT_STAGES = set(_CUSTOMER_LADDER) | {"ecosystem"}
_ALL_CV_STAGES = set(_CUSTOMER_LADDER) | {"ecosystem", "mass_delivery"}
_DELIVERY_ORDER_STAGES = {"delivered", "revenue_recognized"}
_CERT_KEYWORDS = ("认证", "验证", "送样", "测试", "定点")
_DELIVERY_CHECKLIST = {"实际交付", "交付里程碑", "批量交付"}
_PRODUCTION_CHECKLIST = {"量产阶段", "量产/订单"}


def _t3_rows(dossier: dict[str, Any], kind: str,
             code: str) -> list[dict[str, Any]]:
    facts = (dossier.get("t3_facts") or {}).get(kind) or []
    return [r for r in facts
            if str(r.get("stock_code") or "") == str(code)
            and isinstance(r, dict)]


def _accepted(r: dict[str, Any]) -> bool:
    return r.get("review_status") in {"accepted", "verified"}


def _in_node_pl(r: dict[str, Any], pls: set[str]) -> bool:
    """The record's product_line key must match the node's product-line
    set — a sibling line's record never attests THIS node's facts.
    ``mass_delivery`` on a pump-components line is not a CDU-system
    delivery."""
    return not pls or (r.get("product_line") or "") in pls


def _rec_pit_ok(r: dict[str, Any], as_of: str | None) -> bool:
    """Dict-form twin of ``chain_t3_evidence._pit_ok`` — CAP-05/06
    re-verify PIT on consumption; upstream filtering is never trusted
    blindly."""
    if not as_of:
        return True
    cutoff = str(as_of)[:10]
    ing = str(r.get("ingested_at") or "")
    pub = str(r.get("published_at") or "")
    avl = str(r.get("available_at") or "")
    if pub and ing and pub > ing and len(pub) >= 10 and len(ing) >= 10:
        return False
    dates = [d for d in (pub, avl, ing) if len(d) >= 10]
    if not dates:
        return False
    return all(d[:10] <= cutoff for d in dates)


def _trace(rr: Iterable[dict[str, Any]],
           scope_field: str = "scope") -> list[dict[str, Any]]:
    """Stage evidence traceability chain — every confirmed stage must
    cite record → source → review → scope → effective date."""
    return [{
        "record_id": r.get("record_id") or r.get("evidence_id"),
        "source_id": r.get("source_id"),
        "review_status": r.get("review_status"),
        "scope": r.get(scope_field) or r.get("scope")
        or r.get("disclosure_scope"),
        "effective_as_of": r.get("published_at") or r.get("report_period"),
    } for r in rr]


def _cert_delivery_split(
    dossier: dict[str, Any], dossier_by_code: dict[str, dict[str, Any]],
    code: str,
) -> dict[str, Any]:
    """Four INDEPENDENT commercial facts — no stage label moonlights in a
    lane it doesn't belong to (R2B.1 P0-B):

    - ``product_certification``: non-ladder product-level records
      (e.g. ``product_certified`` UL/Intel test facts), plus dossier
      certification-keyword claims as ``claims_only``.
    - ``ecosystem_participation``: ``ecosystem`` records only — ecosystem
      membership never counts as named-customer validation.
    - ``customer_validation``: ladder stages contact/sampling/
      in_validation/validated; ``validated`` requires a named customer —
      an unnamed "validated" record reads ``validated_unspecified``.
    - ``commercial_delivery``: ``mass_delivery`` records, delivered /
      revenue_recognized orders, or dossier delivery-checklist claims.

    All T3 lanes additionally require the record's ``product_line`` key
    to match the node's product lines — parent/sibling node facts never
    promote this node.
    """
    vrows = _t3_rows(dossier, "customer_validation", code)
    orows = _t3_rows(dossier, "orders", code)
    pls = set(dossier.get("product_lines") or [])
    as_of = dossier.get("as_of")
    acc_v = [r for r in vrows if _accepted(r)
             and _in_node_pl(r, pls) and _rec_pit_ok(r, as_of)]
    acc_o = [r for r in orows if _accepted(r)
             and _in_node_pl(r, pls) and _rec_pit_ok(r, as_of)]
    rank = {s: i for i, s in enumerate(_CUSTOMER_LADDER)}

    def _fallback(raw: list[dict[str, Any]], pred,
                  none_state: str = "none_seen") -> str:
        """Lane state when nothing accepted+in-scope+in-PIT exists:
        out_of_node_scope (records exist for OTHER lines — never promote
        them), out_of_pit, pending_review, or the empty state."""
        cand = [r for r in raw if pred(r)]
        if not cand:
            return none_state
        eligible = [r for r in cand if _accepted(r)]
        if eligible and not any(_in_node_pl(r, pls) for r in eligible):
            return "out_of_node_scope"
        if not any(_rec_pit_ok(r, as_of) for r in cand):
            return "out_of_pit"
        return "pending_review"

    def _ladder_state(rows: list[dict[str, Any]]) -> str:
        pl_rows = [r for r in rows if r.get("scope") == "product_line"]
        pool = pl_rows or rows
        if not pool:
            return ""
        best = max(pool, key=lambda r: rank.get(r.get("stage"), -1))
        stage = best["stage"]
        if stage == "validated" and not (best.get("customer") or "").strip():
            stage = "validated_unspecified_customer"
        return stage if pl_rows else f"{stage}_at_{best.get('scope')}"

    # --- product certification (non-ladder product facts) ---------------
    prod_recs = [r for r in acc_v
                 if r.get("stage") not in _ALL_CV_STAGES
                 and r.get("stage") != "customer_relationship"]
    prod_pl = [r for r in prod_recs if r.get("scope") == "product_line"]
    if prod_pl:
        product_cert = prod_pl[0].get("stage") or "product_certified"
    elif prod_recs:
        product_cert = (f"{prod_recs[0].get('stage')}"
                        f"_at_{prod_recs[0].get('scope')}")
    else:
        product_cert = _fallback(
            vrows,
            lambda r: r.get("stage") not in _ALL_CV_STAGES
            and r.get("stage") != "customer_relationship",
            none_state="unknown")

    # --- ecosystem participation ----------------------------------------
    eco_recs = [r for r in acc_v if r.get("stage") == "ecosystem"]
    if [r for r in eco_recs if r.get("scope") == "product_line"]:
        ecosystem = "participating"
    elif eco_recs:
        ecosystem = f"participating_at_{eco_recs[0].get('scope')}"
    else:
        ecosystem = _fallback(vrows, lambda r: r.get("stage") == "ecosystem")

    # --- customer validation (ladder only) --------------------------------
    ladder = [r for r in acc_v if r.get("stage") in _CUSTOMER_LADDER]
    rel = [r for r in acc_v if r.get("stage") == "customer_relationship"]
    if ladder:
        cust_state = _ladder_state(ladder)
    elif rel:
        cust_state = f"customer_relationship_at_{rel[0].get('scope')}"
    else:
        cust_state = _fallback(
            vrows,
            lambda r: r.get("stage") in _CUSTOMER_LADDER
            or r.get("stage") == "customer_relationship",
            none_state="unknown" if not (acc_v or acc_o) else "none_seen")

    # --- commercial delivery ------------------------------------------------
    mass = [r for r in acc_v if r.get("stage") == "mass_delivery"]
    mass_pl = [r for r in mass if r.get("scope") == "product_line"]
    del_orders = [r for r in acc_o
                  if r.get("stage") in _DELIVERY_ORDER_STAGES]
    del_pl = [r for r in del_orders if r.get("scope") == "product_line"]
    # dossier delivery-tier claims (node product-line attributable)
    dsr = dossier_by_code.get(code) or {}
    delivery_claim_seen = False
    if dsr:
        m = {e["evidence_id"]: e for e in dsr.get("evidence_matrix") or []}
        for c in dsr.get("claims") or []:
            if c.get("dimension") != "commercialization":
                continue
            for eid in c.get("evidence_ids") or []:
                row = m.get(eid)
                if not row or row.get("verdict_weight") != "counted":
                    continue
                if pls and (row.get("product_line") or "") not in pls:
                    continue
                item = row.get("checklist_item") or ""
                if item in _DELIVERY_CHECKLIST | _PRODUCTION_CHECKLIST:
                    delivery_claim_seen = True
    if mass_pl or del_pl:
        delivery_state = "verified_delivered"
    elif mass or del_orders:
        delivery_state = "delivered_at_broader_scope"
    elif delivery_claim_seen:
        delivery_state = "production_claimed"
    elif any(_accepted(r) and r.get("stage") == "mass_delivery"
             for r in vrows) or any(
                 _accepted(r) and r.get("stage") in _DELIVERY_ORDER_STAGES
                 for r in orows):
        # 合格交付记录存在但全在其他产品线 → 非本节点交付事实
        delivery_state = "out_of_node_scope"
    elif vrows or orows:
        delivery_state = "none_seen"
    else:
        delivery_state = "unknown"
    return {
        # R2B.1: four independent facts — no stage label moonlights.
        "product_certification": product_cert,
        "ecosystem_participation": ecosystem,
        "customer_validation": cust_state,
        "commercial_delivery": delivery_state,
        # legacy fields keep working — now strictly lane-corrected
        "certification_customer_validation": cust_state,
        "delivery_capability": delivery_state,
        "evidence_record_ids": sorted(
            r.get("record_id") for r in acc_v + del_orders
            if r.get("record_id")),
    }


def _pair_scope(a: str, b: str) -> tuple[str, str]:
    """Comparability of two mapping types.  Component suppliers are never
    directly comparable to full-system makers."""
    if a == b:
        return "directly_comparable", "同一节点同一产品口径"
    pair = {a, b}
    if pair == {"direct_product", "subsidiary"}:
        return ("partially_comparable",
                "同一集团/母子公司口径，产品线归属需注意")
    if "dependency" in pair:
        return ("insufficient_evidence",
                "dependency 映射为链条依赖关系，非直接同业竞争")
    if {"direct_product", "direct_component"} & pair and pair != {
            "direct_product", "subsidiary"}:
        return ("not_comparable",
                "组件/部件口径与系统级口径不可直接比较")
    return "insufficient_evidence", "映射口径不足以判定可比性"


def compare_competition(
    dossier: dict[str, Any],
    dossier_by_code: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """CAP-06 R2: same-scope, same-product-line comparison table.

    Outputs difference facts + evidence coverage + explicit
    non-comparability reasons.  No scores, no ranking — higher disclosure
    volume never means stronger competitiveness.
    """
    rows = (dossier.get("value_matrix") or {}).get("rows") or []
    table: dict[str, dict[str, Any]] = {}
    coverage: dict[str, int] = {}
    for row in rows:
        code = row["stock_code"]
        dims = (dossier_by_code.get(code) or {}).get("dimensions") or {}
        cov = sum(1 for k in ("tech_participation", "validation_delivery",
                              "revenue_profit", "verified_orders")
                  if _cell_state(row.get(k)) not in
                  {"missing", "none_seen", "excluded"})
        coverage[code] = cov + (1 if row.get("dossier") == "present" else 0)
        split = _cert_delivery_split(dossier, dossier_by_code, code)
        table[code] = {
            "company_name": row.get("company_name"),
            "scope_class": row.get("mapping_type") or "unknown",
            "overall_verdict": row.get("overall_verdict") or "no_dossier",
            "tech_participation": row.get("tech_participation"),
            # R2B-A1: maturity follows DELIVERY evidence; certification and
            # delivery read their own lanes — the combined
            # validation_delivery cell never doubles as either one.
            "product_maturity": (
                "mass_delivery" if split["delivery_capability"]
                == "verified_delivered" else
                "production_claimed" if split["delivery_capability"]
                in {"production_claimed", "delivered_at_broader_scope"}
                else split["delivery_capability"]),
            "certification_customer_validation":
                split["certification_customer_validation"],
            "delivery_capability": split["delivery_capability"],
            # R2B.1: four independent facts — product cert, ecosystem,
            # customer validation, delivery never share a stage label.
            "cert_facts": {
                "product_certification": split["product_certification"],
                "ecosystem_participation": split["ecosystem_participation"],
                "customer_validation": split["customer_validation"],
                "commercial_delivery": split["commercial_delivery"],
            },
            "cert_delivery_record_ids": split["evidence_record_ids"],
            "revenue_identifiability": {
                "revenue": _cell_state(row.get("revenue_profit")),
                "margin_known": bool(
                    (row.get("revenue_profit") or {}).get("facts")
                    and any(f.get("gross_margin") is not None
                            for f in (row.get("revenue_profit") or {})
                            .get("facts") or [])),
            },
            "order_visibility": _cell_state(row.get("verified_orders")),
            "advantage_substitutability": {
                d: dims.get(d, {}).get("verdict")
                for d in ("tech_moat", "competitive_edge")
            },
            "concept_only_risk": row.get("concept_only_risk"),
            "evidence_coverage": coverage[code],
        }
    codes = list(table)
    pairwise = []
    for i, a in enumerate(codes):
        for b in codes[i + 1:]:
            scope, reason = _pair_scope(table[a]["scope_class"],
                                        table[b]["scope_class"])
            cov_gap = abs(coverage[a] - coverage[b])
            if scope == "directly_comparable" and cov_gap >= 3:
                scope, reason = ("insufficient_evidence",
                                 f"证据覆盖差距过大({cov_gap})，不判强弱")
            pairwise.append({"a": a, "b": b, "comparison_scope": scope,
                             "reason": reason})
    for code in codes:
        table[code]["comparable_with"] = [
            p["b"] if p["a"] == code else p["a"]
            for p in pairwise
            if code in (p["a"], p["b"])
            and p["comparison_scope"] == "directly_comparable"
        ]
    return {
        "comparison": table,
        "pairwise_scope": pairwise,
        "scope_classes": {
            s: sorted(c for c in codes if table[c]["scope_class"] == s)
            for s in {t["scope_class"] for t in table.values()}
        },
        "note": ("同口径比较：组件 vs 系统不直接排名；"
                 "披露更多≠竞争力更强；无评分无推荐"),
    }


# ---------------------------------------------------------------------------
# CAP-08 hypothesis assessment + theme synthesis
# ---------------------------------------------------------------------------

_ASSESSMENT_BY_VERDICT = {
    "confirmed": "supported",
    "partially_supported": "supported",
    "contested": "contested",
    "refuted": "refuted",
}


def _alt_explanations(role: str, claim: dict[str, Any],
                      checks: dict[str, Any] | None) -> list[str]:
    """Deterministic alternative explanations per role — the more
    parsimonious reading of the same evidence."""
    alts: list[str] = []
    if role == "supply_scarcity":
        alts.append("多供应商格局可吸收需求增长——供给紧缺未证实")
    elif role == "non_substitutability":
        alts.append("存在已商业化或可认证替代方案——不可替代未证实")
    elif role == "entry_barrier":
        alts.append("产品级测试认证≠客户认证周期/成本壁垒")
    elif role == "hype":
        alts.append("主题映射与概念热度驱动，非供给/交付证据")
    elif role == "market_structure":
        alts.append("描述性格局事实，不构成稀缺或壁垒的正反证据")
    return alts


def _revision_triggers(role: str) -> list[str]:
    return {
        "supply_scarcity": [
            "获得产能利用率/交期/订单排队的合格证据 → 升级",
            "新进入者实现规模交付或第二供应商放量 → 弱化",
        ],
        "non_substitutability": [
            "替代方案通过同等级客户认证并量产 → 弱化",
            "切换成本/良率差距证据出现 → 强化",
        ],
        "entry_barrier": [
            "客户认证周期、失效率或切换成本的披露 → 升级",
            "多家厂商通过同一客户认证 → 弱化",
        ],
        "hype": ["主题映射之外的订单/交付/收入证据出现 → 重新评估"],
        "market_structure": ["供应商数量或验证状态变化 → 更新格局事实"],
    }.get(role, [])


def hypothesis_state_map(
    claims: Iterable[dict[str, Any]],
    ev_index: dict[str, dict[str, Any]],
) -> dict[str, str]:
    """Compact {claim_id: assessment_state} — used by CAP-07 snapshots so
    hypothesis-state changes version as research facts."""
    out: dict[str, str] = {}
    for c in claims:
        split = _split_claim_evidence(c, ev_index)
        verdict = c.get("verdict")
        role = c.get("claim_role") or "market_structure"
        state = _ASSESSMENT_BY_VERDICT.get(verdict, "unresolved")
        if state == "supported" and split["counter"]:
            state = "contested"  # 有支持也有合格反证 → contested
        if state == "supported" and role == "hype":
            state = "risk_flagged"
        out[c["claim_id"]] = state
    return out


def assess_hypotheses(
    claims: Iterable[dict[str, Any]],
    ev_index: dict[str, dict[str, Any]],
    node_id: str,
    as_of: str,
) -> list[dict[str, Any]]:
    """CAP-08 R2: per-claim hypothesis assessment records.  Accepts the
    flattened claim list + evidence index (works from a dossier OR from
    CAP-04 envelope findings — same semantics)."""
    claims = list(claims)
    states = hypothesis_state_map(claims, ev_index)
    records = []
    for c in claims:
        role = c.get("claim_role") or "market_structure"
        split = _split_claim_evidence(c, ev_index)
        boundary = evidence_boundary(c, ev_index, as_of)
        records.append({
            "hypothesis_id": c["claim_id"],
            "subject_scope": f"{node_id}/{role}",
            "claim_role": role,
            "verdict": c.get("verdict"),
            "assessment_state": states[c["claim_id"]],
            "supporting_claim_ids": [c["claim_id"]]
            if split["support"] else [],
            "counter_claim_ids": [c["claim_id"]] if split["counter"] else [],
            "alternative_explanations": _alt_explanations(role, c, None),
            "decisive_gaps": boundary["unmet_conditions"],
            "revision_triggers": _revision_triggers(role),
            "evidence_refs": split["support"] + split["counter"],
            "excluded_evidence": split["excluded"],
            "support_source_ids": split["support_source_ids"],
            "counter_source_ids": split["counter_source_ids"],
            "supporting_source_count": split["supporting_source_count"],
            "counter_source_count": split["counter_source_count"],
            "independent_source_count": split["independent_source_count"],
            "as_of": as_of,
        })
    return records


def theme_synthesis(
    per_node: dict[str, dict[str, Any]],
    cap03_findings: dict[str, Any],
) -> dict[str, Any]:
    """Theme-level research summary across node results — structured, not
    a rating or recommendation.  Cross-node evidence dedupes by
    evidence_id so parent/child cases never double-count a source."""
    findings, hypos, unresolved, next_verify = [], [], [], []
    seen_ev: set[str] = set()
    for node_id, envs in per_node.items():
        if node_id.endswith("__error"):
            continue
        env4 = (envs.get("CAP-04") or {}).get("findings") or {}
        env8 = (envs.get("CAP-08") or {}).get("findings") or {}
        nv = env4.get("node_verdict") or "?"
        n_fav = len(env8.get("favorable_support") or [])
        n_risk = len(env8.get("hype_risks") or [])
        n_unres = len(env8.get("unresolved") or [])
        findings.append(
            f"{node_id}: {nv}（正向 {n_fav} · 风险 {n_risk} · 未决 {n_unres}）")
        for h in env8.get("hypothesis_assessment") or []:
            if h["assessment_state"] in {"supported", "contested",
                                        "refuted", "risk_flagged"}:
                new_ev = [e for e in h.get("evidence_refs") or []
                          if e not in seen_ev]
                seen_ev.update(new_ev)
                hypos.append({
                    "node_id": node_id,
                    "hypothesis_id": h["hypothesis_id"],
                    "state": h["assessment_state"],
                    "independent_source_count": h.get(
                        "independent_source_count"),
                    "new_evidence_refs": new_ev,
                })
        for u in env8.get("unresolved") or []:
            unresolved.append({"node_id": node_id,
                               "claim_id": u["claim_id"],
                               "verdict": u.get("verdict")})
        next_verify.extend(env8.get("research_priority") or [])
    nodes = cap03_findings.get("nodes") or []
    covered = sum(1 for n in nodes if n.get("runnable_cases"))
    return {
        "key_findings": findings,
        "competing_hypotheses": hypos,
        "core_unresolved": unresolved[:20],
        "next_verification": sorted(set(next_verify))[:15],
        "coverage": {
            "theme_nodes": len(nodes) or None,
            "nodes_with_cases": covered or None,
            "coverage_gap_nodes": cap03_findings.get("coverage_gap_nodes")
            or [],
            "read_source": cap03_findings.get("read_source"),
        },
        "note": "结构化研究摘要——非主题评级、非买卖建议",
    }


def _cell_state(v: Any) -> str:
    if isinstance(v, dict):
        return str(v.get("state") or "missing")
    return str(v or "missing")


# ---------------------------------------------------------------------------
# CAP-05 R2B: commercial-realization stage assessment
# ---------------------------------------------------------------------------

# Evidence-gated stages.  Each stage is confirmed ONLY by its own qualified
# evidence — a later stage never back-proves an earlier one, and a generic
# narrative never counts as stage evidence.  Stages describe proven facts;
# companies are NOT assumed to progress in order.
_COMMERCIALIZATION_STAGES = (
    "technology_demonstrated",
    "customer_validated",
    "commercial_delivery",
    "revenue_attributed",
    "profitability_visible",
    "cash_realization_visible",
)


def _seg_rows(dossier: dict[str, Any], code: str) -> list[dict[str, Any]]:
    return _t3_rows(dossier, "segment_records", code)


def _stage(
    confirmed: bool, evidence: list[str], sources: set[str], note: str,
    trace: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    out = {
        "confirmed": confirmed,
        "evidence_ids": sorted(evidence),
        "source_ids": sorted(sources),
        "note": note,
    }
    if trace is not None:
        out["trace"] = trace
    return out


def _dossier_tech_evidence(
    dsr: dict[str, Any], pls: set[str],
) -> tuple[list[str], set[str], list[dict[str, Any]], list[str]]:
    """Traceable tech-capability evidence from company-dossier claims —
    counted, review-eligible rows on tech dimensions.  Rows pinned to a
    different product line don't count for this node, but they are
    returned as ``out_of_scope`` so the demotion reason stays honest."""
    ev_ids: list[str] = []
    oos_ids: list[str] = []
    srcs: set[str] = set()
    trace: list[dict[str, Any]] = []
    m = {e["evidence_id"]: e for e in dsr.get("evidence_matrix") or []}
    for c in dsr.get("claims") or []:
        if c.get("dimension") not in {"tech_moat", "competitive_edge",
                                      "tech_participation"}:
            continue
        if c.get("verdict") not in {"confirmed", "partially_supported"}:
            continue
        for eid in c.get("evidence_ids") or []:
            row = m.get(eid)
            if not row or row.get("verdict_weight") != "counted":
                continue
            if row.get("review_status") not in {"accepted", "verified"}:
                continue
            rpl = row.get("product_line") or ""
            if pls and rpl and rpl not in pls:
                oos_ids.append(eid)
                continue
            ev_ids.append(eid)
            if row.get("source_id"):
                srcs.add(row["source_id"])
            trace.append({
                "record_id": eid,
                "source_id": row.get("source_id"),
                "review_status": row.get("review_status"),
                "scope": row.get("evidence_scope") or rpl or "company",
                "effective_as_of": row.get("published_at"),
            })
    return ev_ids, srcs, trace, oos_ids


def assess_commercialization(
    dossier: dict[str, Any],
    dossier_by_code: dict[str, dict[str, Any]],
    as_of: str,
    theme_node_id: str = "",
) -> dict[str, dict[str, Any]]:
    """CAP-05 R2B.1: per-company commercial-realization stage table with
    dual attribution and a strict stage-evidence gate.

    Six stages with independent evidence gates:
      technology_demonstrated — credible product/tech capability evidence
      customer_validated      — named-customer ``validated`` record at
                                product_line scope on a node line
                                (ecosystem ≠ customer validation;
                                mass_delivery is a delivery fact)
      commercial_delivery     — mass_delivery record, order delivered/
                                revenue_recognized, or delivery-checklist
                                dossier evidence — all on a node line
      revenue_attributed      — product_line-scope segment revenue ON A
                                NODE product line
      profitability_visible   — node-line revenue + gross margin
      cash_realization_visible— cash-collection attribution record
                                (no such T3 kind today → always missing)

    Dual attribution (P0-A): a company product-line fact is not a theme
    fact.  ``product_line_attribution`` reports whether revenue maps to
    ANY disclosed company product line; ``theme_application_attribution``
    reports whether qualified evidence ties to THIS node's lines;
    ``theme_specific_revenue`` stays ``not_evaluated`` without
    theme-scoped revenue.  Out-of-line records are preserved under
    ``related_company_facts`` — kept, never promoted.

    Evidence gate (P0-C): a confirmed stage must trace
    record → source → review → scope → effective date; a confirmed stage
    with an empty trace is demoted and listed in ``demoted_stages``.
    """
    rows = (dossier.get("value_matrix") or {}).get("rows") or []
    pls = set(dossier.get("product_lines") or [])
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        code = str(row.get("stock_code") or "")
        dsr = dossier_by_code.get(code) or {}
        vrows = _t3_rows(dossier, "customer_validation", code)
        orows = _t3_rows(dossier, "orders", code)
        srows = _seg_rows(dossier, code)
        crows = _t3_rows(dossier, "cash_collections", code)
        # consumption-side PIT + node-line scope re-verified here —
        # upstream filtering is never trusted blindly.
        acc_v = [r for r in vrows if _accepted(r)
                 and _in_node_pl(r, pls) and _rec_pit_ok(r, as_of)]
        acc_o = [r for r in orows if _accepted(r)
                 and _in_node_pl(r, pls) and _rec_pit_ok(r, as_of)]
        acc_s_node = [r for r in srows if _accepted(r)
                      and _in_node_pl(r, pls) and _rec_pit_ok(r, as_of)]
        acc_s_all = [r for r in srows if _accepted(r)
                     and _rec_pit_ok(r, as_of)]
        acc_c = [r for r in crows if _accepted(r)
                 and _in_node_pl(r, pls) and _rec_pit_ok(r, as_of)]

        def _ids(rr: Iterable[dict[str, Any]]) -> list[str]:
            return [r["record_id"] for r in rr if r.get("record_id")]

        def _srcs(rr: Iterable[dict[str, Any]]) -> set[str]:
            return {r["source_id"] for r in rr if r.get("source_id")}

        # --- technology_demonstrated ------------------------------------
        tech_state = _cell_state(row.get("tech_participation"))
        tech_ok = tech_state in {"confirmed", "partially_supported"}
        if not tech_ok and dsr:
            dv = ((dsr.get("dimensions") or {}).get("tech_moat") or {}) \
                .get("verdict")
            tech_ok = dv in {"confirmed", "partially_supported"}
        tech_ev, tech_srcs, tech_trace, tech_oos = \
            _dossier_tech_evidence(dsr, pls)
        s_tech = _stage(
            tech_ok, tech_ev, tech_srcs,
            "产品/技术能力可信证据（矩阵 tech_participation 或 dossier "
            "tech_moat claim 证据）",
            tech_trace)
        if tech_oos:
            s_tech["out_of_scope_evidence_ids"] = sorted(tech_oos)
            s_tech["note"] += (
                f"；{len(tech_oos)} 条技术证据仅覆盖其他产品线"
                "——非本主题场景")

        # --- customer_validated ------------------------------------------
        # Named-customer ``validated`` records only — ecosystem is not
        # customer validation; mass_delivery lives in the delivery lane.
        cust_ok_rows = [r for r in acc_v
                        if r.get("scope") == "product_line"
                        and r.get("stage") == "validated"
                        and (r.get("customer") or "").strip()]
        cust_unnamed = [r for r in acc_v
                        if r.get("scope") == "product_line"
                        and r.get("stage") == "validated"
                        and not (r.get("customer") or "").strip()]
        cust_broad = [r for r in acc_v
                      if r.get("scope") != "product_line"
                      and r.get("stage") in _CERT_STAGES]
        cust_note = "具名客户验证通过证据（产品线口径）"
        if not cust_ok_rows:
            if cust_unnamed:
                cust_note = "验证记录未具名客户——narrower-scope，不确认"
            elif cust_broad:
                cust_note = (f"仅{cust_broad[0].get('scope')}口径客户验证"
                             "披露——不冒产品线认证")
            elif any(r.get("stage") == "ecosystem" for r in acc_v):
                cust_note = "生态成员≠具名客户验证——不确认"
        s_cust = _stage(bool(cust_ok_rows), _ids(cust_ok_rows),
                        _srcs(cust_ok_rows), cust_note,
                        _trace(cust_ok_rows))

        # --- commercial_delivery ------------------------------------------
        del_mass = [r for r in acc_v if r.get("stage") == "mass_delivery"]
        del_ord = [r for r in acc_o
                   if r.get("stage") in _DELIVERY_ORDER_STAGES]
        del_pl = [r for r in del_mass + del_ord
                  if r.get("scope") == "product_line"]
        claim_delivery = _cert_delivery_split(
            dossier, dossier_by_code, code)["delivery_capability"]
        del_ok = bool(del_pl) or claim_delivery == "verified_delivered"
        if not del_ok and (del_mass or del_ord):
            s_del = _stage(False, _ids(del_mass + del_ord),
                           _srcs(del_mass + del_ord),
                           "交付证据仅为非产品线口径——不冒产品线交付",
                           _trace(del_mass + del_ord))
        elif del_ok:
            s_del = _stage(True, _ids(del_pl), _srcs(del_pl),
                           "商业交付合格证据（mass_delivery/订单交付，"
                           "产品线口径）",
                           _trace(del_pl))
        elif claim_delivery == "production_claimed":
            s_del = _stage(False, [], set(),
                           "量产声明≠商业交付——缺交付里程碑证据")
        else:
            s_del = _stage(False, [], set(), "无商业交付证据")

        # --- revenue_attributed -------------------------------------------
        rev_pl = [r for r in acc_s_node
                  if r.get("disclosure_scope") == "product_line"
                  and r.get("revenue") is not None]
        rev_broad = [r for r in acc_s_all
                     if r.get("disclosure_scope")
                     in {"segment", "industry_board", "company_total"}
                     and r.get("revenue") is not None]
        rev_other_line = [r for r in acc_s_all
                          if r.get("disclosure_scope") == "product_line"
                          and r.get("revenue") is not None
                          and r not in rev_pl]
        if rev_pl:
            rev_note = "可归属节点产品线收入（theme-scoped）"
        elif rev_other_line:
            rev_note = ("收入归属公司其他产品线——非本主题场景，"
                        "不确认本阶段")
        elif rev_broad:
            rev_note = "仅板块/更大口径收入——不冒产品线收入"
        else:
            rev_note = "无收入归属证据"
        s_rev = _stage(bool(rev_pl), _ids(rev_pl), _srcs(rev_pl),
                       rev_note, _trace(rev_pl))

        # --- profitability_visible ----------------------------------------
        prof_pl = [r for r in rev_pl if r.get("gross_margin") is not None]
        s_prof = _stage(bool(prof_pl), _ids(prof_pl), _srcs(prof_pl),
                        "节点产品线收入+毛利可识别" if prof_pl else
                        "节点产品线毛利证据缺失",
                        _trace(prof_pl))

        # --- cash_realization_visible -------------------------------------
        s_cash = _stage(bool(acc_c), _ids(acc_c), _srcs(acc_c),
                        "可归属回款证据" if acc_c else
                        "T3 无回款归属记录类型——不可用财务三表现金流推定",
                        _trace(acc_c))

        stage_evidence = {
            "technology_demonstrated": s_tech,
            "customer_validated": s_cust,
            "commercial_delivery": s_del,
            "revenue_attributed": s_rev,
            "profitability_visible": s_prof,
            "cash_realization_visible": s_cash,
        }
        # P0-C evidence gate: a confirmed stage with no traceable evidence
        # (record → source → review → scope → date) is demoted — an
        # upstream verdict never stands in for evidence.
        demoted: list[str] = []
        for sname, sev in stage_evidence.items():
            if sev["confirmed"] and not (
                    sev["evidence_ids"] or sev.get("trace")):
                sev["confirmed"] = False
                sev["note"] = (sev["note"]
                               + "（R2B.1 Gate：confirmed 缺可追溯证据→降级）")
                demoted.append(sname)
        confirmed = [s for s in _COMMERCIALIZATION_STAGES
                     if stage_evidence[s]["confirmed"]]
        missing = [s for s in _COMMERCIALIZATION_STAGES
                   if not stage_evidence[s]["confirmed"]]

        # --- dual attribution ----------------------------------------------
        pl_seg_any = [r for r in acc_s_all
                      if r.get("disclosure_scope") == "product_line"
                      and r.get("revenue") is not None]
        product_line_attribution = (
            "confirmed" if pl_seg_any else
            "broader_scope_only" if rev_broad else "missing")
        theme_scoped = [r.get("record_id") for r in
                        cust_ok_rows + del_pl + rev_pl + prof_pl
                        if r.get("record_id")]
        theme_application_attribution = (
            "confirmed" if theme_scoped else
            "unknown" if (pl_seg_any or rev_broad or acc_v or acc_o)
            else "not_evaluated")
        theme_specific_revenue = (
            "confirmed" if rev_pl else "not_evaluated")
        related = [{
            "record_id": r.get("record_id"),
            "product_line": r.get("product_line"),
            "disclosure_scope": r.get("disclosure_scope"),
            "revenue": r.get("revenue"),
            "source_id": r.get("source_id"),
            "note": "公司其他产品线/口径事实——非本主题场景，不提升本节点阶段",
        } for r in rev_other_line]

        scopes = {r.get("disclosure_scope") for r in acc_s_node
                  if r.get("disclosure_scope")}
        attribution = (
            "product_line" if "product_line" in scopes else
            "segment" if scopes & {"segment", "industry_board",
                                   "company_total"} else
            "unattributed")
        out[code] = {
            "company_code": code,
            "theme_node_id": theme_node_id or dossier.get("node_id"),
            "product_lines": sorted(pls),
            "stage_evidence": stage_evidence,
            "confirmed_stages": confirmed,
            "missing_stages": missing,
            "demoted_stages": demoted,
            "highest_confirmed_stage": confirmed[-1] if confirmed else None,
            "attribution_scope": attribution,
            # R2B.1 dual attribution
            "product_line_attribution": product_line_attribution,
            "theme_application_attribution":
                theme_application_attribution,
            "theme_specific_revenue": theme_specific_revenue,
            "related_company_facts": related,
            "source_ids": sorted({
                s for st in stage_evidence.values()
                for s in st["source_ids"]}),
            "as_of": as_of,
            "note": "阶段描述已证实事实——不假设顺序推进、不跳级、非评级",
        }
    return out


# ---------------------------------------------------------------------------
# CAP-07 R2B: change classification + materiality
# ---------------------------------------------------------------------------

_CATEGORY_BY_PREFIX = {
    "node": "hypothesis_state_changed",
    "claim": "hypothesis_state_changed",
    "hypothesis": "hypothesis_state_changed",
    "econ": "economic_fact_changed",
    "evidence_ref": "new_evidence",
    "cap_status": "metadata_only",
}

_HYPO_MATERIAL_TO = {"supported", "refuted", "contested"}
_HYPO_NOTABLE_TO = {"risk_flagged", "unresolved"}


_UNRESOLVED_FAMILY = {None, "", "unresolved", "unknown", "needs_evidence"}


def _hypo_materiality(before: Any, after: Any) -> tuple[str, str]:
    if before in _UNRESOLVED_FAMILY and after in _HYPO_MATERIAL_TO:
        return "material", "未决假设获得合格支持/反证"
    if before in _HYPO_MATERIAL_TO and after in _HYPO_MATERIAL_TO \
            and before != after:
        return "material", "假设在支持/反证/contested 间翻转"
    if before in _HYPO_MATERIAL_TO and after in _HYPO_NOTABLE_TO:
        return "material", "已成立假设失去支持/被反证推翻"
    if after in _HYPO_NOTABLE_TO:
        return "notable", "假设状态变化但未触及核心结论"
    return "minor", "假设状态微调"


def _econ_materiality(field: str, before: Any, after: Any) -> tuple[str, str]:
    cell = field.split(".")[-1]
    if cell == "stages" or cell in {"delivery", "order"}:
        cat = "commercialization_stage_changed"
    else:
        cat = "economic_fact_changed"
    a, b = str(before or ""), str(after or "")
    # product-line revenue/margin materializing (or disappearing)
    if cell in {"revenue", "revenue_facts"}:
        if ("missing" in a or "unknown" in a or a in {"None", ""}) \
                and ("disclosed" in b or b not in {"missing", "unknown"}):
            if "broader" not in b and "segment" not in b:
                return "material", cat
            return "notable", cat
        return "notable", cat
    if cell == "stages":
        # ``stages`` is an R2B-introduced tracked field: its first
        # appearance (before=None) is schema-tracking onset, not a
        # world change — notable, never material.  A real set difference
        # between two tracked snapshots IS material.
        if before in (None, [], "") and after not in (None, [], ""):
            return "notable", cat
        return ("material" if a != b else "minor"), cat
    if cell in {"delivery", "order"}:
        promoted = any(k in b for k in ("delivered", "mass_delivery",
                                        "verified", "revenue_recognized"))
        if promoted and not any(k in a for k in
                                ("delivered", "verified",
                                 "revenue_recognized")):
            return "material", cat
        return "notable", cat
    return "minor", cat


def _norm_ev_sig(v: Any) -> dict[str, Any]:
    """Legacy flat ``source_id`` values normalize to a src-only signature
    (older baselines degrade gracefully — a src-only prev can only prove
    duplication, never newness)."""
    return v if isinstance(v, dict) else {"src": v}


def _evidence_materiality(
    change: dict[str, Any],
    prev_map: dict[str, Any], cur_map: dict[str, Any],
) -> tuple[str, str]:
    """R2B.1: same ``source_id`` ≠ meaningless repeat.  Compare the fact
    signature (direction / dimension / scope / review status / content
    hash) — a new fact under an old source can still overturn a call."""
    if change["kind"] == "removed":
        return "notable", "source_revision"
    ev_id = change["field"].split(":", 1)[1]
    cur = _norm_ev_sig(cur_map.get(ev_id))
    if change["kind"] == "changed":
        prev = _norm_ev_sig(prev_map.get(ev_id))
        if cur.get("dir") == "refute" and prev.get("dir") != "refute":
            return "material", "source_revision"   # 方向翻转为反证
        content_same = all(prev.get(k) == cur.get(k)
                           for k in ("sig", "dir", "scope", "dim"))
        if content_same and prev.get("rev") != cur.get("rev"):
            return "minor", "source_revision"      # 仅审核状态变化
        if content_same and prev.get("src") != cur.get("src"):
            return "notable", "source_revision"    # 来源更正（同事实换源）
        return "notable", "source_revision"        # 事实范围/内容变化
    src = cur.get("src")
    src_seen = any(_norm_ev_sig(v).get("src") == src
                   for v in prev_map.values())
    if src and src_seen:
        prev_sigs_same_src = {
            _norm_ev_sig(v).get("sig") for v in prev_map.values()
            if _norm_ev_sig(v).get("src") == src}
        if cur.get("sig") in prev_sigs_same_src:
            return "non_substantive", "duplicate_ingestion"  # 同源同事重采
        if cur.get("dir") == "refute":
            return "material", "same_source_new_fact"  # 同来源新增合格反证
        return "notable", "same_source_new_fact"       # 同来源新事实
    return "notable", "new_evidence"


def classify_changes(
    changes: list[dict[str, Any]],
    current: dict[str, Any],
    prev: dict[str, Any],
) -> list[dict[str, Any]]:
    """Annotate each raw diff entry with change_category / materiality /
    affected_hypothesis_ids / before-after / evidence_delta /
    explanation / action_required.  Auditable rules only — a re-fetched
    old source or a display-field touch never manufactures a research
    event."""
    hypo_ids = sorted((current.get("hypotheses") or {}).keys())
    prev_map = (prev or {}).get("evidence_sources") or {}
    cur_map = (current.get("evidence_sources") or {})
    out: list[dict[str, Any]] = []
    for ch in changes:
        prefix = ch["field"].split(":", 1)[0]
        before, after = ch.get("from"), ch.get("to")
        category = _CATEGORY_BY_PREFIX.get(prefix, "metadata_only")
        materiality = "non_substantive"
        explanation = ""
        affected: list[str] = []
        evidence_delta: list[str] = []

        if prefix in {"hypothesis", "claim", "node"}:
            # claim fields carry raw verdicts — normalize to assessment
            # states so identical semantics grade identically.
            if prefix in {"claim", "node"}:
                before = _ASSESSMENT_BY_VERDICT.get(before, before)
                after = _ASSESSMENT_BY_VERDICT.get(after, after)
            materiality, explanation = _hypo_materiality(before, after)
            target = ch["field"].split(":", 1)[1]
            affected = [] if target == "node_verdict" else [target]
            category = "hypothesis_state_changed"
        elif prefix == "econ":
            materiality, category = _econ_materiality(
                ch["field"], before, after)
            affected = list(hypo_ids)
            explanation = (
                "商业兑现/经营事实变化，可能影响假设"
                if materiality == "material" else "经营事实更新")
        elif prefix == "evidence_ref":
            materiality, category = _evidence_materiality(
                ch, prev_map, cur_map)
            evidence_delta = [ch["field"].split(":", 1)[1]]
            affected = list(hypo_ids)
            explanation = {
                "duplicate_ingestion":
                    "同一底层来源同一事实重复采集——不触发实质变化",
                "same_source_new_fact": (
                    "同来源新增合格反证——可能推翻既有判断"
                    if materiality == "material"
                    else "同来源新事实——需人工判断是否实质"),
                "new_evidence": "新增合格证据引用",
                "source_revision": "证据引用被移除/修订或事实口径变化",
            }[category]
        elif prefix == "cap_status":
            explanation = "运行/状态元数据——非研究事件"
        action = ("re_review_hypothesis" if materiality == "material"
                  else "note_for_next_review" if materiality == "notable"
                  else "none")
        out.append({
            **ch,
            "change_category": category,
            "materiality": materiality,
            "affected_hypothesis_ids": affected,
            "before": before,
            "after": after,
            "evidence_delta": evidence_delta,
            "explanation": explanation,
            "action_required": action,
        })
    return out


def materiality_summary(classified: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {"material": 0, "notable": 0, "minor": 0, "non_substantive": 0}
    for c in classified:
        counts[c["materiality"]] = counts.get(c["materiality"], 0) + 1
    return {
        "counts": counts,
        "requires_re_review": counts["material"] > 0,
        "note": "重要性=对研究判断的影响程度，非价格预测",
    }


# ---------------------------------------------------------------------------
# CAP-09 R2B: verification task derivation (read-only, proposed only)
# ---------------------------------------------------------------------------

_GAP_OWNER = {
    "missing_source": "DATA",
    "unparsed": "DATA",
    "attribution_unknown": "DATA",
}


def verification_tasks(
    per_node: dict[str, dict[str, Any]],
    cap03_findings: dict[str, Any],
    theme_id: str,
) -> list[dict[str, Any]]:
    """Derive proposed verification tasks from CAP-04/05/07/08 outputs.

    Read-only list — status is always ``proposed``; nothing triggers
    collection, crawlers, production workflows, or review-state changes.
    Priority reflects *research* value (blocking a core hypothesis,
    discriminating competing explanations, gating commercialization),
    never expected price moves or concept heat.
    """
    # R2B.1 P1-E: stable task identity — content-derived hash of
    # (theme, company, question/hypothesis, required evidence).  The same
    # verification need re-run or re-sorted gets the SAME id; an
    # identical need arising on parent/child nodes merges into ONE task
    # carrying every related node, never duplicate undifferentiated rows.
    tasks: dict[tuple[str, str, tuple[str, ...]], dict[str, Any]] = {}

    def _add(node_id: str, company: str, question: str, hypothesis: str,
             required: list[str], owner: str, priority: str,
             reason: str, caps: list[str]) -> None:
        qkey = hypothesis or question
        key = (company or "", qkey, tuple(sorted(required)))
        if key in tasks:
            t = tasks[key]
            if node_id and node_id not in t["related_node_ids"]:
                t["related_node_ids"].append(node_id)
            return
        tid_raw = json.dumps(
            [theme_id or "", company or "", qkey, sorted(required)],
            ensure_ascii=False)
        tasks[key] = {
            "task_id": "vt-" + hashlib.sha1(
                tid_raw.encode("utf-8")).hexdigest()[:10],
            "theme_id": theme_id,
            "node_id": node_id,
            "related_node_ids": [node_id] if node_id else [],
            "company_code": company or None,
            "question": question,
            "hypothesis_id": hypothesis or None,
            "required_evidence": required,
            "owner": owner,
            "priority": priority,
            "priority_reason": reason,
            "source_capabilities": caps,
            "status": "proposed",
        }

    for node_id, envs in per_node.items():
        if node_id.endswith("__error"):
            continue
        f8 = (envs.get("CAP-08") or {}).get("findings") or {}
        f5 = (envs.get("CAP-05") or {}).get("findings") or {}
        f7 = (envs.get("CAP-07") or {}).get("findings") or {}
        hypo_texts = {}
        for h in f8.get("hypothesis_assessment") or []:
            hypo_texts[h["hypothesis_id"]] = h
            state = h.get("assessment_state")
            gaps = [g for g in h.get("decisive_gaps") or []]
            text = h.get("hypothesis") or ""
            if state == "unresolved" and gaps:
                _add(node_id, "", f"核实假设：{text or h['hypothesis_id']}",
                     h["hypothesis_id"], gaps, "DATA", "high",
                     "阻断核心研究假设（未决且有决定性缺口）",
                     ["CAP-04", "CAP-08"])
            elif state == "contested":
                _add(node_id, "", f"区分竞争解释：{text or h['hypothesis_id']}",
                     h["hypothesis_id"], gaps or ["adjudicating_evidence"],
                     "DATA", "high",
                     "存在合格反证——需能区分相互竞争解释的证据",
                     ["CAP-08"])
            elif state == "risk_flagged":
                _add(node_id, "", f"核实炒作风险边界：{text or h['hypothesis_id']}",
                     h["hypothesis_id"],
                     ["theme_mapping_independent_evidence"],
                     "DATA", "medium",
                     "主题映射之外的独立证据方可解除风险标记",
                     ["CAP-08"])
        # CAP-05: delivery confirmed but revenue missing → value gate
        for code, eco in (f5.get("economics") or {}).items():
            ca = eco.get("commercialization_assessment") or {}
            confirmed = set(ca.get("confirmed_stages") or [])
            if "commercial_delivery" in confirmed \
                    and "revenue_attributed" not in confirmed:
                _add(node_id, code,
                     f"{code} 已有交付证据但产品线收入未归属——核实收入确认",
                     "", ["product_line_attributed_revenue"], "DATA",
                     "medium", "影响商业兑现判断：交付≠收入",
                     ["CAP-05"])
            if "revenue_attributed" in confirmed \
                    and "profitability_visible" not in confirmed:
                _add(node_id, code,
                     f"{code} 产品线收入已归属但毛利不可见——核实毛利披露",
                     "", ["product_line_gross_margin"], "DATA",
                     "medium", "影响商业兑现判断：收入≠盈利",
                     ["CAP-05"])
        # CAP-07 material changes → re-review task
        for ch in f7.get("changes") or []:
            if ch.get("materiality") == "material":
                _add(node_id, "",
                     f"复核实质变化：{ch['field']} {ch.get('from')}→{ch.get('to')}",
                     (ch.get("affected_hypothesis_ids") or [""])[0] or "",
                     ["re_review"], "CAP-09", "high",
                     "新证据实质改变研究判断——需人工复核",
                     ["CAP-07"])
        # external data gaps → DATA tasks (deduped by backlog owner)
        for g in (envs.get("CAP-05") or {}).get("data_gaps") or []:
            item = g.get("item") or ""
            _add(node_id, item.split(":")[-1] if ":" in item else "",
                 f"补齐数据缺口：{item}", "", [item],
                 _GAP_OWNER.get(g.get("kind"), "DATA"), "low",
                 f"外部数据缺口（{g.get('kind')}）", ["CAP-05"])

    # coverage gaps → CAP-02 capability tasks
    for nid in cap03_findings.get("coverage_gap_nodes") or []:
        _add(nid, "", f"节点 {nid} 无研究案例——需补能力覆盖", "",
             ["node_case"], "CAP-02", "low",
             "能力覆盖缺口（非外部数据缺失）", ["CAP-03"])

    rank = {"high": 0, "medium": 1, "low": 2}
    out = sorted(tasks.values(),
                 key=lambda t: (rank.get(t["priority"], 3), t["task_id"]))
    for t in out:
        t["related_node_ids"] = sorted(t["related_node_ids"])
    return out
