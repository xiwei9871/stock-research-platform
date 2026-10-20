"""CAP-01 company intelligence: six-dimension evidence model + dossier engine.

Research-only layer.  Consumes curated claim/evidence inputs (assembled from
the platform's real corpora: filings, broker reports, theme mappings) and
produces a deterministic company dossier — profile, evidence matrix,
bull/bear analysis, research gaps and a guarded conclusion.  Missing or
indecisive evidence degrades a dimension to ``unknown``/``needs_evidence``;
it never upgrades a claim.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Any, Iterable, Sequence


DIMENSIONS: dict[str, str] = {
    "tech_moat": "技术壁垒",
    "chain_position": "产业链地位",
    "commercialization": "商业化能力",
    "competitive_edge": "竞争优势",
    "financial_realization": "财务兑现",
    "risk_counter": "风险与反证",
}

# Core checklist items a dimension must evidence before it can be trusted.
# A dimension with evidence but an empty checklist item keeps that item as a
# research gap instead of being assumed covered.
DIMENSION_CHECKLIST: dict[str, tuple[str, ...]] = {
    "tech_moat": ("自研技术/知识产权", "关键工艺", "性能参数对比"),
    "chain_position": ("产业链关键节点", "可替代性", "供应约束"),
    "commercialization": ("客户验证", "量产/订单", "相关收入规模"),
    "competitive_edge": ("国内外主要对手", "性能/成本/交付对比", "客户认证"),
    "financial_realization": ("相关业务收入占比", "毛利率", "现金流/资本开支"),
    "risk_counter": ("技术替代/绕开风险", "竞争对手突破", "商业化不及预期"),
}

SOURCE_TYPES = {
    "company_filing",      # 年报/半年报/公告原文
    "financial_statement", # 财务报表数据
    "announcement",        # 上市公司公告
    "broker_report",       # 券商二级研究
    "industry_data",       # 产业链/第三方数据
    "media_article",
    "unknown",
}

DIRECTIONS = {"support", "refute", "unclear"}
REVIEW_STATUSES = {"pending", "accepted", "rejected", "lead_only"}
VERDICTS = {
    "confirmed",
    "partially_supported",
    "contested",
    "contradicted",
    "needs_evidence",
    "unknown",
}

_CONFIDENCE_BY_VERDICT = {
    "confirmed": 0.8,
    "partially_supported": 0.5,
    "contested": 0.35,
    "contradicted": 0.4,
    "needs_evidence": 0.15,
    "unknown": 0.0,
}

# Dimensions that gate an overall positive conclusion: without evidence of
# real commercialization and financial delivery the dossier must not read as
# established, no matter how strong the theme linkage looks.
_GATE_DIMENSIONS = ("commercialization", "financial_realization")


@dataclass(frozen=True)
class CompanySource:
    source_id: str
    source_type: str
    title: str = ""
    publisher: str = ""
    published_at: str = ""
    available_at: str = ""
    ingested_at: str = ""
    reliability_level: str = "S3"
    uri: str = ""


@dataclass(frozen=True)
class CompanyEvidence:
    evidence_id: str
    source_id: str
    dimension: str
    direction: str                    # support | refute | unclear
    excerpt: str = ""
    page_or_section: str = ""
    confidence: str = "medium"        # high | medium | low
    review_status: str = "pending"    # pending | accepted | rejected | lead_only
    checklist_item: str = ""


@dataclass(frozen=True)
class ResearchClaim:
    claim_id: str
    dimension: str
    claim_text: str
    evidence_ids: tuple[str, ...] = ()
    review_status: str = "pending"


@dataclass(frozen=True)
class CompanyInput:
    company_code: str
    company_name: str
    as_of: str
    theme_context: dict[str, Any] = field(default_factory=dict)
    claims: tuple[ResearchClaim, ...] = ()
    evidence: tuple[CompanyEvidence, ...] = ()
    sources: tuple[CompanySource, ...] = ()
    input_snapshot: dict[str, Any] = field(default_factory=dict)


def _date_key(value: str) -> str:
    return str(value or "")[:10]


def _effective_date(source: CompanySource | None) -> str:
    if source is None:
        return ""
    return _date_key(source.available_at) or _date_key(source.published_at)


def _is_usable(ev: CompanyEvidence) -> bool:
    return ev.direction in {"support", "refute"} and ev.review_status != "rejected"


def _dimension_verdict(
    usable_support: list[CompanyEvidence],
    usable_refute: list[CompanyEvidence],
    sources_by_id: dict[str, CompanySource],
) -> str:
    if usable_support and usable_refute:
        return "contested"
    if usable_refute:
        return "contradicted"
    if usable_support:
        source_types = {
            (sources_by_id.get(ev.source_id) or CompanySource("", "unknown")).source_type
            for ev in usable_support
        }
        if len(source_types) >= 2 and len(usable_support) >= 2:
            return "confirmed"
        return "partially_supported"
    return "unknown"


def _checklist_gaps(
    dimension: str,
    covered_items: set[str],
) -> list[str]:
    return [item for item in DIMENSION_CHECKLIST[dimension] if item not in covered_items]


def build_company_dossier(
    *,
    company_code: str,
    company_name: str,
    as_of: str,
    claims: Sequence[ResearchClaim],
    evidence: Sequence[CompanyEvidence],
    sources: Sequence[CompanySource],
    theme_context: dict[str, Any] | None = None,
    input_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the six-dimension company dossier deterministically."""

    if company_code == "" or company_name == "":
        raise ValueError("company_code and company_name are required")
    as_of_key = _date_key(as_of)
    sources_by_id = {src.source_id: src for src in sources}
    evidence_by_id = {ev.evidence_id: ev for ev in evidence}

    # PIT discipline: an item whose effective availability is after as_of is
    # excluded from every verdict and recorded for the audit trail.
    in_scope: dict[str, list[CompanyEvidence]] = {d: [] for d in DIMENSIONS}
    post_asof: list[str] = []
    for ev in evidence:
        if ev.dimension not in DIMENSIONS:
            continue
        effective = _effective_date(sources_by_id.get(ev.source_id))
        if effective and effective > as_of_key:
            post_asof.append(ev.evidence_id)
            continue
        in_scope[ev.dimension].append(ev)

    claim_evidence_links: dict[str, list[str]] = {}
    claims_out: list[dict[str, Any]] = []
    for claim in claims:
        linked = [eid for eid in claim.evidence_ids if eid in evidence_by_id]
        claim_evidence_links[claim.claim_id] = linked
        linked_evs = [evidence_by_id[eid] for eid in linked]
        claims_out.append(
            {
                "claim_id": claim.claim_id,
                "dimension": claim.dimension,
                "claim_text": claim.claim_text,
                "evidence_ids": linked,
                "review_status": claim.review_status,
                "support_count": sum(1 for e in linked_evs if e.direction == "support"),
                "refute_count": sum(1 for e in linked_evs if e.direction == "refute"),
            }
        )

    dimensions_out: dict[str, dict[str, Any]] = {}
    for dimension in DIMENSIONS:
        pool = in_scope[dimension]
        usable = [ev for ev in pool if _is_usable(ev)]
        support = [ev for ev in usable if ev.direction == "support"]
        refute = [ev for ev in usable if ev.direction == "refute"]
        if not pool:
            verdict = "unknown"
        elif not usable:
            verdict = "needs_evidence"
        else:
            verdict = _dimension_verdict(support, refute, sources_by_id)
        conflicts = []
        if support and refute:
            conflicts = [
                {
                    "dimension": dimension,
                    "support_evidence_ids": [ev.evidence_id for ev in support],
                    "refute_evidence_ids": [ev.evidence_id for ev in refute],
                }
            ]
        covered = {
            ev.checklist_item for ev in usable if ev.checklist_item
        }
        dimensions_out[dimension] = {
            "label": DIMENSIONS[dimension],
            "verdict": verdict,
            "confidence": _CONFIDENCE_BY_VERDICT[verdict],
            "evidence_ids": [ev.evidence_id for ev in pool],
            "support_count": len(support),
            "refute_count": len(refute),
            "unclear_count": len(pool) - len(usable),
            "conflicts": conflicts,
            "missing_checklist_items": _checklist_gaps(dimension, covered),
        }

    bull = _collect_case(in_scope, evidence_by_id, sources_by_id, direction="support")
    bear = _collect_case(in_scope, evidence_by_id, sources_by_id, direction="refute")

    research_gaps: list[dict[str, Any]] = []
    for dimension, dim in dimensions_out.items():
        if dim["verdict"] in {"confirmed"} and not dim["missing_checklist_items"]:
            continue
        for item in dim["missing_checklist_items"]:
            research_gaps.append(
                {
                    "dimension": dimension,
                    "missing_item": item,
                    "reason": (
                        "dimension_unverified"
                        if dim["verdict"] in {"unknown", "needs_evidence"}
                        else "checklist_item_uncovered"
                    ),
                    "needed_source_types": _needed_source_types(dimension),
                    "priority": (
                        "high"
                        if dim["verdict"] in {"unknown", "needs_evidence"}
                        else "medium"
                    ),
                }
            )
        if dim["verdict"] == "contested":
            research_gaps.append(
                {
                    "dimension": dimension,
                    "missing_item": "冲突证据裁定",
                    "reason": "conflicting_evidence_unresolved",
                    "needed_source_types": ["company_filing", "announcement"],
                    "priority": "high",
                }
            )

    overall, overall_conf = _overall_verdict(dimensions_out)
    fingerprint = _input_fingerprint(claims, evidence, sources)
    snapshot = dict(input_snapshot or {})
    snapshot["evidence_set_sha256"] = fingerprint

    return {
        "company_code": company_code,
        "company_name": company_name,
        "as_of": as_of_key,
        "theme_context": theme_context or {},
        "profile": _profile(dimensions_out, claims_out),
        "dimensions": dimensions_out,
        "claims": claims_out,
        "evidence_matrix": [
            _matrix_row(ev, sources_by_id.get(ev.source_id), claim_evidence_links)
            for ev in evidence
        ],
        "bull_case": bull,
        "bear_case": bear,
        "research_gaps": research_gaps,
        "conclusion": {
            "overall_verdict": overall,
            "confidence": overall_conf,
            "main_uncertainties": _main_uncertainties(dimensions_out),
            "verification_conditions": _verification_conditions(dimensions_out),
        },
        "post_asof_excluded": sorted(post_asof),
        "guardrails": {
            "research_only": True,
            "used_for_signal": False,
            "used_for_admission": False,
            "price_inputs_used": False,
            "requires_human_review": True,
        },
        "input_snapshot": snapshot,
    }


def _collect_case(
    in_scope: dict[str, list[CompanyEvidence]],
    evidence_by_id: dict[str, CompanyEvidence],
    sources_by_id: dict[str, CompanySource],
    *,
    direction: str,
) -> list[dict[str, Any]]:
    del evidence_by_id
    rows: list[dict[str, Any]] = []
    for dimension, pool in in_scope.items():
        for ev in pool:
            if ev.direction != direction or ev.review_status == "rejected":
                continue
            src = sources_by_id.get(ev.source_id)
            rows.append(
                {
                    "dimension": dimension,
                    "evidence_id": ev.evidence_id,
                    "excerpt": ev.excerpt,
                    "page_or_section": ev.page_or_section,
                    "source_id": ev.source_id,
                    "source_type": src.source_type if src else "unknown",
                    "published_at": src.published_at if src else "",
                }
            )
    return rows


def _matrix_row(
    ev: CompanyEvidence,
    src: CompanySource | None,
    claim_links: dict[str, list[str]],
) -> dict[str, Any]:
    linked_claims = [
        cid for cid, eids in claim_links.items() if ev.evidence_id in eids
    ]
    return {
        "evidence_id": ev.evidence_id,
        "dimension": ev.dimension,
        "direction": ev.direction,
        "page_or_section": ev.page_or_section,
        "checklist_item": ev.checklist_item,
        "confidence": ev.confidence,
        "review_status": ev.review_status,
        "source_id": ev.source_id,
        "source_type": src.source_type if src else "unknown",
        "published_at": src.published_at if src else "",
        "available_at": src.available_at if src else "",
        "ingested_at": src.ingested_at if src else "",
        "claim_ids": linked_claims,
        "excerpt": ev.excerpt,
    }


def _profile(
    dimensions: dict[str, dict[str, Any]],
    claims: list[dict[str, Any]],
) -> dict[str, Any]:
    evidenced = [d for d, dim in dimensions.items() if dim["verdict"] not in {"unknown"}]
    return {
        "dimension_verdicts": {
            d: {"label": DIMENSIONS[d], "verdict": dim["verdict"], "confidence": dim["confidence"]}
            for d, dim in dimensions.items()
        },
        "evidenced_dimensions": evidenced,
        "claim_count": len(claims),
        "open_claims": sum(1 for c in claims if c["review_status"] == "pending"),
    }


def _overall_verdict(dimensions: dict[str, dict[str, Any]]) -> tuple[str, float]:
    verdicts = {d: dim["verdict"] for d, dim in dimensions.items()}
    confirmed = sum(1 for v in verdicts.values() if v == "confirmed")
    contested_or_contra = any(
        v in {"contested", "contradicted"} for v in verdicts.values()
    )
    gates_unmet = any(
        verdicts[d] in {"unknown", "needs_evidence"} for d in _GATE_DIMENSIONS
    )
    if all(v == "confirmed" for v in verdicts.values()):
        return "established", 0.8
    if contested_or_contra:
        return "contested", 0.35
    if gates_unmet:
        if all(v == "unknown" for v in verdicts.values()):
            return "unknown", 0.0
        return "needs_evidence", 0.2
    if confirmed >= 3:
        return "partially_supported", 0.55
    return "unverified", 0.25


def _main_uncertainties(dimensions: dict[str, dict[str, Any]]) -> list[str]:
    items: list[str] = []
    for dimension, dim in dimensions.items():
        if dim["verdict"] in {"unknown", "needs_evidence"}:
            items.append(f"{DIMENSIONS[dimension]}:证据不足({dim['verdict']})")
        elif dim["verdict"] == "contested":
            items.append(f"{DIMENSIONS[dimension]}:正反证据冲突待裁定")
        elif dim["verdict"] == "contradicted":
            items.append(f"{DIMENSIONS[dimension]}:存在反驳证据")
    return items


def _verification_conditions(dimensions: dict[str, dict[str, Any]]) -> list[str]:
    conditions: list[str] = []
    for dimension, dim in dimensions.items():
        for item in dim["missing_checklist_items"]:
            conditions.append(f"补证:{DIMENSIONS[dimension]}->{item}")
    return conditions


def _needed_source_types(dimension: str) -> list[str]:
    if dimension in {"commercialization", "financial_realization"}:
        return ["company_filing", "financial_statement", "announcement"]
    if dimension in {"competitive_edge", "chain_position"}:
        return ["company_filing", "broker_report", "industry_data"]
    return ["company_filing", "announcement", "broker_report"]


def _input_fingerprint(
    claims: Iterable[ResearchClaim],
    evidence: Iterable[CompanyEvidence],
    sources: Iterable[CompanySource],
) -> str:
    canonical = json.dumps(
        {
            "claims": sorted(
                (c.claim_id, c.dimension, c.claim_text) for c in claims
            ),
            "evidence": sorted(
                (e.evidence_id, e.dimension, e.direction, e.source_id, e.page_or_section)
                for e in evidence
            ),
            "sources": sorted(
                (s.source_id, s.source_type, s.published_at, s.available_at)
                for s in sources
            ),
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
