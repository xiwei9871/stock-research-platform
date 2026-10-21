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
import re
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
    "mixed",
    "needs_evidence",
    "unknown",
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

# Deterministic rule version stamped into every dossier fingerprint — bump when
# adjudication semantics change so verdicts stay reproducible.
RULE_VERSION = "cap01-r1.1"

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
    # "company" = about one firm's capability; "node" = about the industry-chain
    # link itself (capacity, queues, alternatives).  Node claims may only bind
    # node-scope evidence — a strong company never auto-proves a bottleneck.
    evidence_scope: str = "company"
    # Product-line attribution for commercialization evidence.  Empty means
    # the excerpt can't be tied to a specific product line — the value matrix
    # treats it as node_attribution_unknown instead of letting a storage-ESS
    # delivery masquerade as a data-center liquid-cooling delivery.
    product_line: str = ""


@dataclass(frozen=True)
class ResearchClaim:
    claim_id: str
    dimension: str
    claim_text: str
    evidence_ids: tuple[str, ...] = ()
    review_status: str = "pending"
    # Node-scoped economics role (supply_scarcity / non_substitutability /
    # market_structure / entry_barrier / hype).  Company dossiers leave it
    # empty; the chain-bottleneck engine uses it to keep a descriptive fact
    # (e.g. "multiple suppliers exist") from posing as scarcity evidence.
    claim_role: str = ""


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


_DATE_FULL = re.compile(r"^(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?")

_DAYS_IN_MONTH = {
    1: 31, 2: 29, 3: 31, 4: 30, 5: 31, 6: 30,
    7: 31, 8: 31, 9: 30, 10: 31, 11: 30, 12: 31,
}


def _date_bound(value: str) -> tuple[str, str, str]:
    """Parse a possibly partial date into (lower, upper, precision).

    ``"2026"`` → ``("2026-01-01", "2026-12-31", "year")`` — never guess an
    exact day inside an imprecise date.  Empty/unparseable → ``("", "", "unknown")``.
    """
    text = str(value or "").strip()
    match = _DATE_FULL.match(text)
    if not match:
        return "", "", "unknown"
    year, month, day = match.group(1), match.group(2), match.group(3)
    if day and month:
        exact = f"{year}-{month}-{day}"
        return exact, exact, "day"
    if month:
        last = _DAYS_IN_MONTH[int(month)]
        return f"{year}-{month}-01", f"{year}-{month}-{last:02d}", "month"
    return f"{year}-01-01", f"{year}-12-31", "year"


def _pit_status(source: CompanySource | None, as_of_key: str) -> tuple[str, str]:
    """Classify evidence vs the research cutoff.

    Returns ``(status, basis)``:
    - ``in_scope``: usable by the platform no later than ``as_of``.
      ``ingested_at`` is the binding constraint — a source proven ingested
      ≤ as_of was necessarily published before that; publication precision is
      reported separately and never guessed.
    - ``post_asof``: earliest possible usable time is after ``as_of``
      (including late ingestion) — excluded from all verdict math.
    - ``uncertain``: no dates, or the possible-usable window straddles the
      cutoff — excluded from verdict math, listed under ``pit_uncertain``.
    """
    if source is None:
        return "uncertain", "no_source"
    ing_lo, ing_hi, _ = _date_bound(source.ingested_at)
    pub_lo, _pub_hi, _pp = _date_bound(source.published_at)
    # Metadata contradiction: the earliest possible publication is later than
    # the latest possible ingestion — the dates cannot both be true, so mark
    # uncertain instead of guessing which one to trust.
    if pub_lo and ing_hi and pub_lo > ing_hi:
        return "uncertain", "contradictory_dates"
    if ing_lo and ing_lo > as_of_key:
        return "post_asof", "ingested_at"
    if ing_hi and ing_hi <= as_of_key:
        return "in_scope", "ingested_at"
    lowers: list[str] = []
    uppers: list[str] = []
    for field_value in (source.published_at, source.available_at, source.ingested_at):
        lo, hi, _prec = _date_bound(field_value)
        if lo:
            lowers.append(lo)
            uppers.append(hi)
    if not lowers:
        return "uncertain", "no_dates"
    usable_lo = max(lowers)
    usable_hi = max(uppers)
    if usable_lo > as_of_key:
        return "post_asof", "published_or_available"
    if usable_hi <= as_of_key:
        return "in_scope", "published_or_available"
    return "uncertain", "date_precision"


def _published_precision(source: CompanySource | None) -> str:
    if source is None:
        return "unknown"
    return _date_bound(source.published_at)[2]


def _verdict_tier(ev: CompanyEvidence) -> str:
    """Review-status tier for verdict math.

    Only ``accepted`` evidence can confirm or contradict a claim.  ``pending``
    and ``lead_only`` material stays visible (matrix / unverified list) but
    carries no verdict weight.
    """
    if ev.review_status == "rejected":
        return "excluded"
    if ev.review_status == "accepted":
        return "counted"
    if ev.direction in {"support", "refute"}:
        return "unverified"
    return "unclear"


def _is_independent(
    support: list[CompanyEvidence],
    sources_by_id: dict[str, CompanySource],
) -> bool:
    """Confirmed requires ≥2 independent accepted supports: distinct source ids,
    distinct source types and distinct non-empty publishers."""
    if len({ev.source_id for ev in support}) < 2:
        return False
    source_types = {
        (sources_by_id.get(ev.source_id) or CompanySource("", "unknown")).source_type
        for ev in support
    }
    if len(source_types) < 2:
        return False
    publishers = {
        (sources_by_id.get(ev.source_id) or CompanySource("", "unknown")).publisher
        for ev in support
    }
    publishers.discard("")
    return len(publishers) >= 2


def _claim_verdict(
    claim: ResearchClaim,
    evidence_by_id: dict[str, CompanyEvidence],
    in_scope_ids: set[str],
    sources_by_id: dict[str, CompanySource],
) -> dict[str, Any]:
    linked: list[str] = []
    binding_errors: list[str] = []
    for eid in claim.evidence_ids:
        if eid not in evidence_by_id or eid not in in_scope_ids:
            continue
        if evidence_by_id[eid].dimension != claim.dimension:
            binding_errors.append(eid)
            continue
        linked.append(eid)
    linked_evs = [evidence_by_id[eid] for eid in linked]
    counted = [ev for ev in linked_evs if _verdict_tier(ev) == "counted"]
    support = [ev for ev in counted if ev.direction == "support"]
    refute = [ev for ev in counted if ev.direction == "refute"]
    unverified = [
        ev.evidence_id for ev in linked_evs if _verdict_tier(ev) == "unverified"
    ]
    if support and refute:
        verdict = "contested"
    elif refute:
        verdict = "contradicted"
    elif support:
        verdict = (
            "confirmed"
            if _is_independent(support, sources_by_id)
            else "partially_supported"
        )
    elif linked:
        verdict = "needs_evidence"
    else:
        verdict = "unknown"
    return {
        "claim_id": claim.claim_id,
        "dimension": claim.dimension,
        "claim_text": claim.claim_text,
        "evidence_ids": linked,
        "review_status": claim.review_status,
        "verdict": verdict,
        "confidence": _CONFIDENCE_BY_VERDICT[verdict],
        "support_count": len(support),
        "refute_count": len(refute),
        "unclear_count": len(linked) - len(support) - len(refute),
        "unverified_evidence_ids": unverified,
        "binding_errors": binding_errors,
    }


def _dimension_verdict(
    claim_verdicts: list[str],
    pool_size: int,
) -> str:
    """Aggregate claim verdicts into the dimension verdict.

    ``contested`` is reserved for a *real* conflict: a single claim carrying
    both support and refute evidence.  Different claims landing on opposite
    sides (e.g. capability supported, uniqueness refuted) is a **mixed**
    outcome, not an evidence conflict.
    """
    if not claim_verdicts:
        return "needs_evidence" if pool_size else "unknown"
    if all(v == "unknown" for v in claim_verdicts):
        return "needs_evidence" if pool_size else "unknown"
    supported = {"confirmed", "partially_supported"}
    if any(v == "contradicted" for v in claim_verdicts):
        if all(v == "contradicted" for v in claim_verdicts):
            return "contradicted"
        if any(v in supported for v in claim_verdicts):
            return "mixed"
        return "contradicted"
    if any(v == "contested" for v in claim_verdicts):
        return "contested"
    if all(v == "confirmed" for v in claim_verdicts):
        return "confirmed"
    if any(v in supported for v in claim_verdicts):
        return "partially_supported"
    return "needs_evidence"


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

    # PIT discipline: ingestion time is the binding constraint (a source proven
    # ingested ≤ as_of was necessarily published earlier); without ingestion
    # proof, publication/availability bounds decide.  Anything definitely later
    # or temporally indeterminate is excluded from all verdict math.
    in_scope: dict[str, list[CompanyEvidence]] = {d: [] for d in DIMENSIONS}
    in_scope_ids: set[str] = set()
    pit_status_by_id: dict[str, str] = {}
    post_asof: list[str] = []
    pit_uncertain: list[str] = []
    for ev in evidence:
        if ev.dimension not in DIMENSIONS:
            pit_status_by_id[ev.evidence_id] = "excluded"
            continue
        status, _basis = _pit_status(sources_by_id.get(ev.source_id), as_of_key)
        pit_status_by_id[ev.evidence_id] = status
        if status == "post_asof":
            post_asof.append(ev.evidence_id)
            continue
        if status == "uncertain":
            pit_uncertain.append(ev.evidence_id)
            continue
        in_scope_ids.add(ev.evidence_id)
        in_scope[ev.dimension].append(ev)

    claim_evidence_links: dict[str, list[str]] = {}
    claims_out: list[dict[str, Any]] = []
    binding_warnings: list[str] = []
    claim_verdicts_by_dim: dict[str, list[str]] = {d: [] for d in DIMENSIONS}
    for claim in claims:
        row = _claim_verdict(claim, evidence_by_id, in_scope_ids, sources_by_id)
        claim_evidence_links[claim.claim_id] = row["evidence_ids"]
        claims_out.append(row)
        binding_warnings.extend(
            f"{claim.claim_id}:{eid}" for eid in row["binding_errors"]
        )
        if claim.dimension in claim_verdicts_by_dim:
            claim_verdicts_by_dim[claim.dimension].append(row["verdict"])

    dimensions_out: dict[str, dict[str, Any]] = {}
    for dimension in DIMENSIONS:
        pool = in_scope[dimension]
        counted = [ev for ev in pool if _verdict_tier(ev) == "counted"]
        support = [ev for ev in counted if ev.direction == "support"]
        refute = [ev for ev in counted if ev.direction == "refute"]
        unverified = [ev for ev in pool if _verdict_tier(ev) == "unverified"]
        verdict = _dimension_verdict(claim_verdicts_by_dim[dimension], len(pool))
        conflicts = []
        if support and refute:
            conflicts = [
                {
                    "dimension": dimension,
                    "support_evidence_ids": [ev.evidence_id for ev in support],
                    "refute_evidence_ids": [ev.evidence_id for ev in refute],
                }
            ]
        covered = {ev.checklist_item for ev in counted if ev.checklist_item}
        dimensions_out[dimension] = {
            "label": DIMENSIONS[dimension],
            "verdict": verdict,
            "confidence": _CONFIDENCE_BY_VERDICT[verdict],
            "evidence_ids": [ev.evidence_id for ev in pool],
            "claim_ids": [
                c["claim_id"] for c in claims_out if c["dimension"] == dimension
            ],
            "claim_verdicts": {
                c["claim_id"]: c["verdict"]
                for c in claims_out
                if c["dimension"] == dimension
            },
            "support_count": len(support),
            "refute_count": len(refute),
            "unverified_count": len(unverified),
            "unclear_count": len(pool) - len(counted) - len(unverified),
            "conflicts": conflicts,
            "missing_checklist_items": _checklist_gaps(dimension, covered),
        }

    bull = _collect_case(in_scope, sources_by_id, direction="support")
    bear = _collect_case(in_scope, sources_by_id, direction="refute")
    pending_verification = _collect_case(
        in_scope, sources_by_id, direction=None
    )

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
    snapshot["rule_version"] = RULE_VERSION
    dossier_fingerprint = _dossier_fingerprint(
        as_of_key, fingerprint, RULE_VERSION
    )

    return {
        "company_code": company_code,
        "company_name": company_name,
        "as_of": as_of_key,
        "dossier_fingerprint": dossier_fingerprint,
        "binding_warnings": binding_warnings,
        "theme_context": theme_context or {},
        "profile": _profile(dimensions_out, claims_out),
        "dimensions": dimensions_out,
        "claims": claims_out,
        "evidence_matrix": [
            _matrix_row(
                ev,
                sources_by_id.get(ev.source_id),
                claim_evidence_links,
                pit_status_by_id.get(ev.evidence_id, "uncertain"),
            )
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
        "pit_uncertain": sorted(pit_uncertain),
        "pending_verification": pending_verification,
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
    sources_by_id: dict[str, CompanySource],
    *,
    direction: str | None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for dimension, pool in in_scope.items():
        for ev in pool:
            if direction is None:
                if _verdict_tier(ev) != "unverified":
                    continue
            elif ev.direction != direction or ev.review_status != "accepted":
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
    pit_status: str,
) -> dict[str, Any]:
    linked_claims = [
        cid for cid, eids in claim_links.items() if ev.evidence_id in eids
    ]
    if pit_status in {"post_asof", "uncertain"}:
        verdict_weight = "excluded"
    else:
        verdict_weight = _verdict_tier(ev)
    return {
        "evidence_id": ev.evidence_id,
        "dimension": ev.dimension,
        "direction": ev.direction,
        "page_or_section": ev.page_or_section,
        "checklist_item": ev.checklist_item,
        "evidence_scope": ev.evidence_scope,
        "product_line": ev.product_line,
        "confidence": ev.confidence,
        "review_status": ev.review_status,
        "verdict_weight": verdict_weight,
        "pit_status": pit_status,
        "published_precision": _published_precision(src),
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
    gates_unmet = any(
        verdicts[d] in {"unknown", "needs_evidence"} for d in _GATE_DIMENSIONS
    )
    if all(v == "confirmed" for v in verdicts.values()):
        return "established", 0.8
    # A true same-proposition conflict marks the whole dossier contested; a
    # fully contradicted dimension marks it contradicted.  ``mixed`` (distinct
    # propositions landing on different sides) does neither.
    if any(v == "contested" for v in verdicts.values()):
        return "contested", 0.35
    if any(v == "contradicted" for v in verdicts.values()):
        return "contradicted", 0.3
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
            items.append(f"{DIMENSIONS[dimension]}:同一论点正反证据冲突待裁定")
        elif dim["verdict"] == "contradicted":
            items.append(f"{DIMENSIONS[dimension]}:存在反驳证据")
        elif dim["verdict"] == "mixed":
            items.append(f"{DIMENSIONS[dimension]}:不同论点结论分化")
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
                (
                    c.claim_id,
                    c.dimension,
                    c.claim_text,
                    tuple(sorted(c.evidence_ids)),
                    c.review_status,
                    c.claim_role,
                )
                for c in claims
            ),
            "evidence": sorted(
                (
                    e.evidence_id,
                    e.dimension,
                    e.direction,
                    e.source_id,
                    e.page_or_section,
                    e.excerpt,
                    e.confidence,
                    e.review_status,
                    e.checklist_item,
                    e.evidence_scope,
                    e.product_line,
                )
                for e in evidence
            ),
            "sources": sorted(
                (
                    s.source_id,
                    s.source_type,
                    s.title,
                    s.publisher,
                    s.published_at,
                    s.available_at,
                    s.ingested_at,
                    s.reliability_level,
                    s.uri,
                )
                for s in sources
            ),
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _dossier_fingerprint(as_of_key: str, evidence_sha256: str, rule_version: str) -> str:
    """Version fingerprint of the dossier *result*: evidence set + research
    cutoff + adjudication rule version.  Same evidence under a different
    ``as_of`` yields a different dossier fingerprint."""
    canonical = json.dumps(
        {
            "as_of": as_of_key,
            "evidence_set_sha256": evidence_sha256,
            "rule_version": rule_version,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
