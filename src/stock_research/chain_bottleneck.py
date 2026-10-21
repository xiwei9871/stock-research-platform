"""CAP-02 T1: industry-chain node bottleneck adjudication.

Reuses the CAP-01 claim-level verdict machinery (``_claim_verdict`` /
``_dimension_verdict`` / ``_pit_status`` / fingerprints) but judges **node**
propositions, not company propositions.  The structural rule: node claims may
only bind ``evidence_scope == "node"`` evidence — company-scope evidence about
a member firm (its tech strength, its theme linkage) can never prove a
chain-level bottleneck.  Scope mismatches are reported as binding errors, the
same failure contract as cross-dimension bindings.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Sequence

from stock_research.company_intelligence import (
    CompanyEvidence,
    CompanySource,
    ResearchClaim,
    RULE_VERSION,
    _claim_verdict,
    _date_key,
    _dimension_verdict,
    _dossier_fingerprint,
    _input_fingerprint,
    _pit_status,
    _verdict_tier,
    _published_precision,
)

# Five bottleneck gates a node claim set must address.
NODE_ASPECTS: dict[str, str] = {
    "capacity_constraint": "产能供给约束",
    "process_irreplaceability": "核心工艺可替代性",
    "certification_barrier": "客户认证壁垒",
    "performance_gap": "性能技术差异",
    "hype_only": "概念炒作成分",
}

# Evidence items the aspect needs before it can be trusted.
NODE_CHECKLIST: dict[str, tuple[str, ...]] = {
    "capacity_constraint": ("供需缺口/排队", "扩产周期/壁垒"),
    "process_irreplaceability": ("工艺独有性", "替代路线存在性"),
    "certification_barrier": ("认证周期", "认证失效率/门槛"),
    "performance_gap": ("节点级性能差异", "与替代方案对比"),
    "hype_only": ("主题关联但无供给约束证据", "概念标的占比"),
}

_CONFIDENCE_BY_VERDICT = {
    "confirmed": 0.8,
    "partially_supported": 0.5,
    "contested": 0.35,
    "contradicted": 0.4,
    "mixed": 0.45,
    "needs_evidence": 0.15,
    "unknown": 0.0,
}

# Aspects whose confirmation establishes a real bottleneck; hype_only is a
# disqualifier, never a supporter.
_CORE_ASPECTS = (
    "capacity_constraint",
    "process_irreplaceability",
    "certification_barrier",
    "performance_gap",
)

# Economics roles for node claims (R2.1).  Only claims that assert an actual
# bottleneck mechanism — supply scarcity or effective non-substitutability —
# can establish or reject the node.  Descriptive market-structure facts
# (supplier counts, landscape) and generic barriers can never stand in for
# scarcity evidence.
NODE_CLAIM_ROLES = {
    "supply_scarcity",
    "non_substitutability",
    "market_structure",
    "entry_barrier",
    "hype",
}
_SCARCITY_ROLES = {"supply_scarcity", "non_substitutability"}
_BARRIER_ROLES = {"entry_barrier"}


def _claim_role(claim_row: dict[str, Any], node_claim: ResearchClaim | None) -> str:
    role = node_claim.claim_role if node_claim is not None else ""
    if role in NODE_CLAIM_ROLES:
        return role
    # Unlabeled claims default by aspect so legacy specs degrade to
    # descriptive roles rather than posing as scarcity evidence.
    default = {
        "capacity_constraint": "market_structure",
        "process_irreplaceability": "market_structure",
        "certification_barrier": "entry_barrier",
        "performance_gap": "entry_barrier",
        "hype_only": "hype",
    }
    return default.get(claim_row.get("dimension") or "", "market_structure")


def build_node_dossier(
    *,
    node_id: str,
    node_name: str,
    as_of: str,
    node_claims: Sequence[ResearchClaim],
    evidence: Sequence[CompanyEvidence],
    sources: Sequence[CompanySource],
    member_companies: Sequence[dict[str, Any]] = (),
    product_lines: set[str] | None = None,
    value_matrix: dict[str, Any] | None = None,
    t3: dict[str, Any] | None = None,
    input_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Deterministic node-level bottleneck dossier."""

    if not node_id or not node_name:
        raise ValueError("node_id and node_name are required")
    as_of_key = _date_key(as_of)
    sources_by_id = {s.source_id: s for s in sources}
    evidence_by_id = {e.evidence_id: e for e in evidence}

    # PIT: identical semantics to the company dossier.
    in_scope_ids: set[str] = set()
    pit_status_by_id: dict[str, str] = {}
    post_asof: list[str] = []
    pit_uncertain: list[str] = []
    pool_by_aspect: dict[str, list[CompanyEvidence]] = {a: [] for a in NODE_ASPECTS}
    for ev in evidence:
        if ev.dimension not in NODE_ASPECTS:
            pit_status_by_id[ev.evidence_id] = "excluded"
            continue
        status, _basis = _pit_status(sources_by_id.get(ev.source_id), as_of_key)
        pit_status_by_id[ev.evidence_id] = status
        if status == "post_asof":
            post_asof.append(ev.evidence_id)
        elif status == "uncertain":
            pit_uncertain.append(ev.evidence_id)
        else:
            in_scope_ids.add(ev.evidence_id)
            pool_by_aspect[ev.dimension].append(ev)

    # Node claims bind only node-scope evidence.  Company-scope rows produce a
    # binding error and never participate — the capability≠bottleneck rule.
    claims_out: list[dict[str, Any]] = []
    binding_warnings: list[str] = []
    claim_verdicts_by_aspect: dict[str, list[str]] = {a: [] for a in NODE_ASPECTS}
    for claim in node_claims:
        scoped_ids: list[str] = []
        scope_errors: list[str] = []
        for eid in claim.evidence_ids:
            ev = evidence_by_id.get(eid)
            if ev is None:
                continue
            if ev.evidence_scope != "node":
                scope_errors.append(eid)
                continue
            scoped_ids.append(eid)
        narrowed = ResearchClaim(
            claim_id=claim.claim_id,
            dimension=claim.dimension,
            claim_text=claim.claim_text,
            evidence_ids=tuple(scoped_ids),
            review_status=claim.review_status,
        )
        row = _claim_verdict(narrowed, evidence_by_id, in_scope_ids, sources_by_id)
        row["scope_binding_errors"] = scope_errors + row["binding_errors"]
        row["binding_errors"] = row["scope_binding_errors"]
        row["claim_role"] = _claim_role(row, claim)
        claims_out.append(row)
        binding_warnings.extend(f"{claim.claim_id}:{eid}" for eid in scope_errors)
        binding_warnings.extend(
            f"{claim.claim_id}:{eid}" for eid in row.get("binding_errors", []) if eid not in scope_errors
        )
        if claim.dimension in claim_verdicts_by_aspect:
            claim_verdicts_by_aspect[claim.dimension].append(row["verdict"])

    aspects_out: dict[str, dict[str, Any]] = {}
    for aspect in NODE_ASPECTS:
        pool = pool_by_aspect[aspect]
        counted = [ev for ev in pool if _verdict_tier(ev) == "counted"]
        covered = {ev.checklist_item for ev in counted if ev.checklist_item}
        verdict = _dimension_verdict(claim_verdicts_by_aspect[aspect], len(pool))
        aspects_out[aspect] = {
            "label": NODE_ASPECTS[aspect],
            "verdict": verdict,
            "confidence": _CONFIDENCE_BY_VERDICT[verdict],
            "claim_ids": [c["claim_id"] for c in claims_out if c["dimension"] == aspect],
            "claim_verdicts": {
                c["claim_id"]: c["verdict"] for c in claims_out if c["dimension"] == aspect
            },
            "evidence_ids": [ev.evidence_id for ev in pool],
            "support_count": sum(1 for e in counted if e.direction == "support"),
            "refute_count": sum(1 for e in counted if e.direction == "refute"),
            "unverified_count": sum(1 for e in pool if _verdict_tier(e) == "unverified"),
            "missing_checklist_items": [
                item for item in NODE_CHECKLIST[aspect] if item not in covered
            ],
        }

    node_verdict, node_conf = _node_verdict(aspects_out, claims_out)

    fingerprint = _input_fingerprint(node_claims, evidence, sources)
    snapshot = dict(input_snapshot or {})
    snapshot["evidence_set_sha256"] = fingerprint
    snapshot["rule_version"] = RULE_VERSION
    t3_sha = ""
    if t3:
        from stock_research.chain_t3_evidence import t3_fingerprint

        t3_sha = t3_fingerprint(
            t3.get("segment_records") or (),
            t3.get("rival_supply") or (),
            t3.get("customer_validation") or (),
            t3.get("orders") or (),
        )
        snapshot["t3_sha256"] = t3_sha
    dossier_fp = _dossier_fingerprint(
        as_of_key, fingerprint + (t3_sha or ""), f"node-{RULE_VERSION}"
    )

    return {
        "node_id": node_id,
        "node_name": node_name,
        "as_of": as_of_key,
        "dossier_fingerprint": dossier_fp,
        "member_companies": list(member_companies),
        "product_lines": sorted(product_lines or ()),
        "aspects": aspects_out,
        "node_claims": claims_out,
        "evidence_matrix": [
            _node_matrix_row(ev, sources_by_id.get(ev.source_id), pit_status_by_id.get(ev.evidence_id, "uncertain"))
            for ev in evidence
        ],
        "research_gaps": _node_gaps(aspects_out),
        "value_matrix": value_matrix,
        "t3_facts": (
            {
                k: [
                    (r.__dict__ if not isinstance(r, dict) else r)
                    for r in v
                ]
                for k, v in t3.items()
            }
            if t3 else None
        ),
        "conclusion": {
            "node_verdict": node_verdict,
            "confidence": node_conf,
            "main_uncertainties": _node_uncertainties(aspects_out),
        },
        "post_asof_excluded": sorted(post_asof),
        "pit_uncertain": sorted(pit_uncertain),
        "binding_warnings": sorted(set(binding_warnings)),
        "guardrails": {
            "research_only": True,
            "used_for_signal": False,
            "used_for_admission": False,
            "requires_human_review": True,
        },
        "input_snapshot": snapshot,
    }


def _node_verdict(
    aspects: dict[str, dict[str, Any]],
    claims: list[dict[str, Any]],
) -> tuple[str, float]:
    """Conservative overall node call — three distinct propositions are kept
    separate: (a) supply scarcity (capacity_constraint claims), (b) effective
    substitutability limit (process_irreplaceability claims), (c) generic
    barriers (certification/performance).  Refuting one mechanism never
    refutes the node.

    - ``bottleneck_rejected`` only when a *capacity/supply* claim is
      contradicted by counted node-scope evidence — affirmative refutation of
      the actual bottleneck proposition.
    - ``bottleneck_established`` needs real scarcity evidence: ≥1 supported
      capacity **or** process claim, ≥2 supported core claims overall, and no
      verified hype.  Two generic partials can never establish it.
    """
    supported = {"confirmed", "partially_supported"}
    core_claims = [c for c in claims if c["dimension"] in _CORE_ASPECTS]
    core = [c["verdict"] for c in core_claims]
    hype = aspects["hype_only"]["verdict"]

    if any(v == "contested" for v in core):
        return "contested", 0.35
    # Rejection needs the *bottleneck proposition itself* (supply_scarcity or
    # non_substitutability role) contradicted — a local market-structure or
    # generic capacity claim being refuted never kills the node.
    scarcity_claims = [c for c in core_claims if c.get("claim_role") in _SCARCITY_ROLES]
    # Only an affirmed refutation of the *supply-constraint* proposition
    # rejects the node.  A refuted non-substitutability claim kills that one
    # mechanism but capacity may still bind — surface it, don't reject.
    if any(
        c["verdict"] == "contradicted" and c.get("claim_role") == "supply_scarcity"
        for c in core_claims
    ):
        return "bottleneck_rejected", 0.3
    scarcity_support = any(c["verdict"] in supported for c in scarcity_claims)
    # Established: real scarcity/non-substitutability support plus at least
    # one additional supported barrier/scarcity claim, and no verified hype.
    n_supported = sum(
        1
        for c in core_claims
        if c["verdict"] in supported and c.get("claim_role") in _SCARCITY_ROLES | _BARRIER_ROLES
    )
    if scarcity_support and n_supported >= 2 and hype not in supported:
        return "bottleneck_established", 0.7
    if all(v == "unknown" for v in core):
        return "unknown" if not core else "needs_evidence", 0.0 if not core else 0.15
    if any(v in supported | {"contradicted", "mixed"} for v in core):
        return "bottleneck_unverified", 0.3
    return "needs_evidence", 0.15


def _node_gaps(aspects: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    for aspect, dim in aspects.items():
        if dim["verdict"] == "confirmed" and not dim["missing_checklist_items"]:
            continue
        for item in dim["missing_checklist_items"]:
            gaps.append(
                {
                    "aspect": aspect,
                    "missing_item": item,
                    "reason": (
                        "aspect_unverified"
                        if dim["verdict"] in {"unknown", "needs_evidence"}
                        else "checklist_item_uncovered"
                    ),
                    "priority": (
                        "high" if dim["verdict"] in {"unknown", "needs_evidence"} else "medium"
                    ),
                }
            )
    return gaps


def _node_uncertainties(aspects: dict[str, dict[str, Any]]) -> list[str]:
    items: list[str] = []
    for aspect, dim in aspects.items():
        if dim["verdict"] in {"unknown", "needs_evidence"}:
            items.append(f"{NODE_ASPECTS[aspect]}:证据不足")
        elif dim["verdict"] in {"contested", "mixed", "contradicted"}:
            items.append(f"{NODE_ASPECTS[aspect]}:{dim['verdict']}")
    return items


def _node_matrix_row(
    ev: CompanyEvidence,
    src: CompanySource | None,
    pit_status: str,
) -> dict[str, Any]:
    if pit_status in {"post_asof", "uncertain"}:
        weight = "excluded"
    else:
        weight = _verdict_tier(ev)
    return {
        "evidence_id": ev.evidence_id,
        "aspect": ev.dimension,
        "direction": ev.direction,
        "evidence_scope": ev.evidence_scope,
        "product_line": ev.product_line,
        "page_or_section": ev.page_or_section,
        "checklist_item": ev.checklist_item,
        "confidence": ev.confidence,
        "review_status": ev.review_status,
        "verdict_weight": weight,
        "pit_status": pit_status,
        "published_precision": _published_precision(src),
        "source_id": ev.source_id,
        "source_type": src.source_type if src else "unknown",
        "published_at": src.published_at if src else "",
        "available_at": src.available_at if src else "",
        "ingested_at": src.ingested_at if src else "",
        "excerpt": ev.excerpt,
    }


# --------------------------------------------------------------------------
# Case loading
# --------------------------------------------------------------------------


def load_node_case(path: str | Path) -> dict[str, Any]:
    """Load a node case JSON.

    Schema::

        {
          "node_id": "...", "node_name": "...", "as_of": "2026-10-20",
          "member_companies": [{"stock_code","company_name","mapping_type"}],
          "node_claims": [{"claim_id","dimension"(aspect),"claim_text","evidence_ids"}],
          "evidence": [{CompanyEvidence fields + evidence_scope}],
          "sources": [{CompanySource fields}],
          "input_snapshot": {...}
        }
    """
    spec = json.loads(Path(path).read_text(encoding="utf-8"))
    return {
        "node_id": spec["node_id"],
        "node_name": spec.get("node_name") or spec["node_id"],
        "as_of": spec["as_of"],
        "member_companies": spec.get("member_companies") or [],
        "product_lines": set(spec.get("product_lines") or ()),
        "node_claims": tuple(
            ResearchClaim(
                claim_id=c["claim_id"],
                dimension=c["dimension"],
                claim_text=c["claim_text"],
                evidence_ids=tuple(c.get("evidence_ids") or ()),
                review_status=c.get("review_status", "pending"),
                claim_role=c.get("claim_role", ""),
            )
            for c in spec.get("node_claims") or []
        ),
        "evidence": tuple(CompanyEvidence(**row) for row in spec.get("evidence") or []),
        "sources": tuple(CompanySource(**row) for row in spec.get("sources") or []),
        "input_snapshot": spec.get("input_snapshot") or {},
        "t3_records_path": spec.get("t3_records_path") or "",
    }
