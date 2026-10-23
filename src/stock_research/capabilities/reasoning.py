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
    """support / counter / excluded split for one claim's evidence_ids."""
    sup, ref, exc = [], [], []
    sids: set[str] = set()
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
        else:
            sup.append(eid)
            if ev.get("source_id"):
                sids.add(ev["source_id"])
    return {
        "support": sup, "counter": ref, "excluded": exc,
        "source_ids": sorted(sids), "independent_source_count": len(sids),
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
        table[code] = {
            "company_name": row.get("company_name"),
            "scope_class": row.get("mapping_type") or "unknown",
            "overall_verdict": row.get("overall_verdict") or "no_dossier",
            "tech_participation": row.get("tech_participation"),
            "product_maturity": _cell_state(row.get("validation_delivery")),
            "certification_customer_validation": _cell_state(
                row.get("validation_delivery")),
            "delivery_capability": _cell_state(row.get("validation_delivery")),
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
