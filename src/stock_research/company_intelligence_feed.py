"""CAP-01 evidence feed: parse existing evidence corpora into case inputs.

Reuses — never re-ingests — the platform's page-cited corpora:

- ``reports_pagewise_v2/<code>_<name>_evidence_brief.md`` (yanbaoke pilot2):
  sectioned excerpts tagged ``[P<code>_<page>_<n>]`` (公司原始披露) and
  ``[B<code>_<page>_<n>]`` (券商二级研究观点).
- ``page_citation_manifest_v3.csv`` / ``download_manifest.csv`` for
  publish/availability timestamps when present.

Curated case JSON then binds claims to specific evidence_ids and supplies
source date overrides so ``published_at`` vs ``available_at`` stay explicit.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
import re
from typing import Any, Sequence

from stock_research.company_intelligence import (
    CompanyEvidence,
    CompanyInput,
    CompanySource,
    DIMENSIONS,
    ResearchClaim,
    SOURCE_TYPES,
)


_BRIEF_NAME_RE = re.compile(r"^(?P<code>\d{6})_(?P<name>.+)_evidence_brief\.md$")
_SECTION_RE = re.compile(r"^###\s+(?P<title>.+?)\s*$")
_EXCERPT_RE = re.compile(
    r"^-\s*\[(?P<kind>公司原始披露|券商二级研究观点)\]\s*"
    r"(?P<text>.*?)\s*"
    r"\[(?P<eid>[PB]\d{6}_\d+_\d+)\]"
    r"(?:（(?P<locator>[^）]*)）)?\s*$"
)

SECTION_TO_DIMENSION: dict[str, str] = {
    "主营业务与收入结构": "commercialization",
    "核心产品与产业链位置": "chain_position",
    "硬科技 / 卡脖子相关性": "tech_moat",
    "硬科技/卡脖子相关性": "tech_moat",
    "技术能力与研发投入": "tech_moat",
    "财务与经营快照": "financial_realization",
    "风险与反证": "risk_counter",
    "客户与订单": "commercialization",
    "竞争格局": "competitive_edge",
}

_CHECKLIST_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("客户验证", "客户|认证|验证|导入|定点|合格供应"),
    ("量产/订单", "订单|量产|出货|批量|中标|交付"),
    ("相关收入规模", "收入|营收|占比|亿元|销售额"),
    ("国内外主要对手", "竞争对手|竞品|对标|替代|国际|海外|进口"),
    ("性能/成本/交付对比", "性能|精度|效率|成本|良率|指标|参数"),
    ("相关业务收入占比", "收入构成|占营业收入|分产品|分行业"),
    ("毛利率", "毛利率|毛利"),
    ("现金流/资本开支", "现金流|资本开支|capex|扩产"),
    ("自研技术/知识产权", "自研|专利|研发|知识产权|核心技术"),
    ("产业链关键节点", "产业链|工序|环节|上游|下游"),
    ("技术替代/绕开风险", "替代|绕开|路线|迭代|颠覆"),
    ("商业化不及预期", "不及预期|风险|不确定|下滑"),
)

_SOURCE_TYPE_BY_TAG = {"P": "company_filing", "B": "broker_report"}
_SOURCE_KIND_LABEL = {"公司原始披露": "company_filing", "券商二级研究观点": "broker_report"}


def _checklist_item(text: str, dimension: str) -> str:
    from stock_research.company_intelligence import DIMENSION_CHECKLIST

    allowed = set(DIMENSION_CHECKLIST[dimension])
    for item, pattern in _CHECKLIST_KEYWORDS:
        if item in allowed and re.search(pattern, text):
            return item
    return ""


def parse_evidence_brief(
    path: str | Path,
    *,
    source_dates: dict[str, dict[str, str]] | None = None,
) -> CompanyInput:
    """Parse one pagewise evidence brief into normalized evidence + sources."""

    path = Path(path)
    match = _BRIEF_NAME_RE.match(path.name)
    company_code = match.group("code") if match else ""
    company_name = match.group("name") if match else path.stem

    evidence: list[CompanyEvidence] = []
    sources: dict[str, CompanySource] = {}
    section = ""
    for line in path.read_text(encoding="utf-8").splitlines():
        sec = _SECTION_RE.match(line)
        if sec:
            section = sec.group("title")
            continue
        hit = _EXCERPT_RE.match(line)
        if not hit:
            continue
        eid = hit.group("eid")
        dimension = SECTION_TO_DIMENSION.get(section, "")
        if dimension not in DIMENSIONS:
            dimension = "tech_moat" if "卡脖子" in section else "commercialization"
        direction = "refute" if dimension == "risk_counter" else "support"
        tag = eid[0]
        source_type = _SOURCE_KIND_LABEL.get(
            hit.group("kind"), _SOURCE_TYPE_BY_TAG.get(tag, "unknown")
        )
        overrides = (source_dates or {}).get(eid, {})
        sources.setdefault(
            eid,
            CompanySource(
                source_id=eid,
                source_type=source_type,
                published_at=overrides.get("published_at", ""),
                available_at=overrides.get("available_at", ""),
                ingested_at=overrides.get("ingested_at", ""),
                reliability_level="S1" if tag == "P" else "S3",
                uri=str(path),
            ),
        )
        text = hit.group("text")
        evidence.append(
            CompanyEvidence(
                evidence_id=eid,
                source_id=eid,
                dimension=dimension,
                direction=direction,
                excerpt=text,
                page_or_section=hit.group("locator") or "",
                confidence="high" if tag == "P" else "medium",
                review_status="pending",
                checklist_item=_checklist_item(text, dimension),
            )
        )

    return CompanyInput(
        company_code=company_code,
        company_name=company_name,
        as_of="",
        evidence=tuple(evidence),
        sources=tuple(sources.values()),
        input_snapshot={"brief_path": str(path)},
    )


def load_case_input(path: str | Path) -> CompanyInput:
    """Load a curated case JSON: claims + brief-derived evidence + overrides.

    Schema::

        {
          "company_code": "301200",
          "company_name": "大族数控",
          "as_of": "2026-10-20",
          "theme_context": {...},
          "brief_path": ".../evidence_brief.md",   # optional evidence pool
          "claims": [{"claim_id","dimension","claim_text","evidence_ids":[...],
                      "review_status":"pending"}],
          "extra_evidence": [...],                  # optional non-brief rows
          "extra_sources": [...],
          "source_overrides": {"<eid>": {"published_at": "...", ...}},
          "input_snapshot": {...}
        }
    """

    path = Path(path)
    spec = json.loads(path.read_text(encoding="utf-8"))
    overrides = spec.get("source_overrides") or {}

    evidence: list[CompanyEvidence] = []
    sources: dict[str, CompanySource] = {}
    snapshot = dict(spec.get("input_snapshot") or {})

    brief_path = spec.get("brief_path")
    if brief_path:
        resolved = Path(brief_path)
        if not resolved.is_absolute():
            resolved = path.parent / resolved
        parsed = parse_evidence_brief(resolved, source_dates=overrides)
        evidence.extend(parsed.evidence)
        sources.update({s.source_id: s for s in parsed.sources})
        snapshot.setdefault("brief_path", str(resolved))

    review_universe_code = spec.get("review_universe_stock_code")
    if review_universe_code:
        db_evidence, db_sources = load_review_universe_evidence(
            stock_code=review_universe_code,
            service=spec.get("service", "stock_research"),
            source_dates=overrides,
            row_indexes=spec.get("review_universe_row_indexes"),
        )
        existing_ids = {ev.evidence_id for ev in evidence}
        evidence.extend(ev for ev in db_evidence if ev.evidence_id not in existing_ids)
        for src in db_sources:
            sources.setdefault(src.source_id, src)
        snapshot.setdefault("review_universe_stock_code", review_universe_code)

    for row in spec.get("extra_sources") or []:
        sources[row["source_id"]] = CompanySource(**row)
    for row in spec.get("extra_evidence") or []:
        evidence.append(CompanyEvidence(**row))

    # Dimension-facet copies: one real excerpt can legitimately inform a claim
    # in another dimension, but R1.1 forbids cross-dimension claim bindings.
    # ``evidence_facets`` clones the excerpt under a new evidence_id tagged to
    # the target dimension, keeping source provenance (dates/publisher) intact.
    by_id = {ev.evidence_id: ev for ev in evidence}
    for facet in spec.get("evidence_facets") or []:
        base = by_id.get(facet["from"])
        if base is None:
            raise KeyError(f"evidence_facet source not found: {facet['from']}")
        clone = CompanyEvidence(
            evidence_id=facet["as_evidence_id"],
            source_id=base.source_id,
            dimension=facet["dimension"],
            direction=facet.get("direction", base.direction),
            excerpt=base.excerpt,
            page_or_section=base.page_or_section,
            confidence=facet.get("confidence", base.confidence),
            review_status=base.review_status,
            checklist_item=facet.get("checklist_item", base.checklist_item),
            evidence_scope=base.evidence_scope,
            product_line=facet.get("product_line", base.product_line),
        )
        evidence.append(clone)
        by_id[clone.evidence_id] = clone

    evidence_overrides = spec.get("evidence_overrides") or {}
    if evidence_overrides:
        evidence = [
            _apply_evidence_override(ev, evidence_overrides.get(ev.evidence_id, {}))
            for ev in evidence
        ]

    claims = tuple(
        ResearchClaim(
            claim_id=c["claim_id"],
            dimension=c["dimension"],
            claim_text=c["claim_text"],
            evidence_ids=tuple(c.get("evidence_ids") or ()),
            review_status=c.get("review_status", "pending"),
        )
        for c in spec.get("claims") or []
    )

    snapshot.setdefault("case_spec_path", str(path))
    return CompanyInput(
        company_code=spec["company_code"],
        company_name=spec.get("company_name") or spec["company_code"],
        as_of=spec["as_of"],
        theme_context=spec.get("theme_context") or {},
        claims=claims,
        evidence=tuple(evidence),
        sources=tuple(sources.values()),
        input_snapshot=snapshot,
    )


def _apply_evidence_override(
    ev: CompanyEvidence, override: dict[str, Any]
) -> CompanyEvidence:
    if not override:
        return ev
    fields = {
        "direction": override.get("direction", ev.direction),
        "checklist_item": override.get("checklist_item", ev.checklist_item),
        "review_status": override.get("review_status", ev.review_status),
        "confidence": override.get("confidence", ev.confidence),
    }
    return CompanyEvidence(
        evidence_id=ev.evidence_id,
        source_id=ev.source_id,
        dimension=override.get("dimension", ev.dimension),
        direction=fields["direction"],
        excerpt=ev.excerpt,
        page_or_section=ev.page_or_section,
        confidence=fields["confidence"],
        review_status=fields["review_status"],
        checklist_item=fields["checklist_item"],
        evidence_scope=override.get("evidence_scope", ev.evidence_scope),
        product_line=override.get("product_line", ev.product_line),
    )


def load_review_universe_evidence(
    *,
    stock_code: str,
    service: str = "stock_research",
    source_dates: dict[str, dict[str, str]] | None = None,
    row_indexes: Sequence[int] | None = None,
    limit: int = 200,
) -> tuple[list[CompanyEvidence], list[CompanySource]]:
    """Load primary-source page excerpts from the review-universe store.

    Read-only against ``research.tech_bottleneck_review_universe_evidence``
    (dataset ``tech_bottleneck_review_universe_frontend_dataset_v1``): per-page
    filing/announcement excerpts with ``source_type`` / ``source_title`` /
    ``evidence_text``.  Direction is *not* assigned here — the excerpt is
    neutral; the case JSON binds it to claims with explicit directions via
    ``evidence_overrides``.
    """

    from stock_research.db import connect, fetch_all

    sql = """
    SELECT row_index, payload, published_at
    FROM research.tech_bottleneck_review_universe_evidence
    WHERE stock_code = %s
    ORDER BY row_index
    LIMIT %s
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, [stock_code, limit])

    evidence: list[CompanyEvidence] = []
    sources: dict[str, CompanySource] = {}
    for row in rows:
        if row_indexes is not None and int(row["row_index"]) not in set(row_indexes):
            continue
        payload = row["payload"]
        if isinstance(payload, str):
            payload = json.loads(payload)
        source_type = str(payload.get("source_type") or "company_filing")
        source_title = str(payload.get("source_title") or "")
        page = payload.get("page")
        eid = f"ru_{stock_code}_{row['row_index']}"
        overrides = (source_dates or {}).get(eid, {})
        published = overrides.get("published_at") or str(payload.get("source_date") or "")
        # The table's ``published_at`` column is the dataset ingest stamp
        # (identical across the snapshot) — it is the platform's real
        # ingestion time, used as ``ingested_at`` for PIT semantics.
        ingested = overrides.get("ingested_at") or str(row.get("published_at") or "")[:10]
        sources.setdefault(
            eid,
            CompanySource(
                source_id=eid,
                source_type=source_type if source_type in SOURCE_TYPES else "company_filing",
                title=source_title,
                publisher="公司披露" if source_type in {"annual_report", "interim_report", "announcement"} else "",
                published_at=published,
                available_at=overrides.get("available_at", ""),
                ingested_at=ingested,
                reliability_level="S1",
                uri=str(payload.get("source_file") or ""),
            ),
        )
        text = str(payload.get("evidence_text") or "")
        dimension = _dimension_for_filing_text(text)
        evidence.append(
            CompanyEvidence(
                evidence_id=eid,
                source_id=eid,
                dimension=dimension,
                direction="unclear",  # neutral excerpt; claims set direction
                excerpt=text[:2000],
                page_or_section=f"第 {page} 页" if page else "",
                confidence="high",
                review_status="accepted",
                checklist_item=_checklist_item(text, dimension),
            )
        )
    return evidence, list(sources.values())


def _dimension_for_filing_text(text: str) -> str:
    """Heuristic dimension for a neutral filing excerpt; case JSON may retag."""

    if re.search("毛利率|营业收入|营业成本|现金流|资本开支|研发费用", text):
        return "financial_realization"
    if re.search("客户|订单|中标|量产|交付|收入", text):
        return "commercialization"
    if re.search("竞争|对手|市场份额|替代|进口", text):
        return "competitive_edge"
    if re.search("产业链|供应链|上游|下游|工序", text):
        return "chain_position"
    if re.search("研发|专利|核心技术|知识产权|自研", text):
        return "tech_moat"
    if re.search("风险|不确定|依赖|下滑", text):
        return "risk_counter"
    return "commercialization"


def load_citation_dates(manifest_path: str | Path) -> dict[str, dict[str, str]]:
    """Map citation/source ids -> publish/ingest dates from a CSV manifest.

    Tolerates the several column names used across the yanbaoke corpora.
    """

    path = Path(manifest_path)
    if not path.exists():
        return {}
    out: dict[str, dict[str, str]] = {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            key = (
                row.get("citation_id")
                or row.get("evidence_id")
                or row.get("source_id")
                or row.get("report_id")
                or ""
            )
            if not key:
                continue
            out[key] = {
                "published_at": (
                    row.get("publish_date")
                    or row.get("report_date")
                    or row.get("published_at")
                    or ""
                ),
                "available_at": (
                    row.get("available_at")
                    or row.get("download_date")
                    or row.get("fetched_at")
                    or ""
                ),
                "ingested_at": (
                    row.get("ingested_at") or row.get("download_date") or ""
                ),
            }
    return out
