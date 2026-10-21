"""CAP-02 T3: structured segment-revenue and rival-supply evidence.

T3-I1 ``SegmentRevenueRecord`` — per-product-line revenue/margin facts extracted
from primary filings.  T3-I4 ``RivalSupplyRecord`` — node-scope rival supply
facts.  Both are *evidence-layer* artifacts: they load through the same
CompanySource/CompanyEvidence model, carry mandatory provenance (uri, page,
three timestamps), and always enter as ``pending`` — freshly extracted numbers
are never auto-accepted just because the source is a company annual report.

No parallel registry: records convert to CompanyEvidence rows and flow through
the existing claim/PIT/review machinery.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

from stock_research.company_intelligence import CompanyEvidence, CompanySource

# What the number actually covers — never let a broader segment pretend to be
# a narrower node line.
DISCLOSURE_SCOPES = {
    "product_line",   # exact product-line disclosure
    "segment",        # broader segment that contains the line (e.g. 机房温控含液冷)
    "industry_board", # business board by downstream industry (e.g. 数据服务行业)
    "company_total",  # company-level total only
    "unextracted",    # primary doc exists but the table wasn't ingested (gap, not "undisclosed")
    "undisclosed",    # verified: the filing does not break out this line
}


@dataclass(frozen=True)
class SegmentRevenueRecord:
    record_id: str
    stock_code: str
    product_line: str            # canonical line key used by node cases
    product_line_label: str      # disclosure's own wording (e.g. 机房温控节能产品)
    report_period: str           # e.g. "2025FY", "2025H1"
    disclosure_scope: str        # DISCLOSURE_SCOPES
    source_id: str
    uri: str = ""
    page_or_section: str = ""
    revenue: float | None = None
    gross_profit: float | None = None
    gross_margin: float | None = None
    revenue_share: float | None = None
    revenue_yoy: float | None = None
    currency: str = "CNY"
    unit: str = "元"
    excerpt: str = ""
    published_at: str = ""
    available_at: str = ""
    ingested_at: str = ""
    review_status: str = "pending"
    note: str = ""


@dataclass(frozen=True)
class RivalSupplyRecord:
    record_id: str
    rival_stock_code: str
    rival_name: str
    node_id: str
    supply_facts: str            # actual products / stage / capacity as disclosed
    stage: str = ""              # 量产 | 交付 | 研发 | 未知
    substitution_note: str = ""  # route-around / substitutability detail
    source_id: str = ""
    uri: str = ""
    page_or_section: str = ""
    published_at: str = ""
    ingested_at: str = ""
    review_status: str = "pending"
    excerpt: str = ""


def load_t3_records(path: str | Path) -> dict[str, Any]:
    """Load a T3 spec JSON: {"segment_records": [...], "rival_supply": [...]}"""
    spec = json.loads(Path(path).read_text(encoding="utf-8"))
    return {
        "segment_records": tuple(
            SegmentRevenueRecord(**r) for r in spec.get("segment_records") or []
        ),
        "rival_supply": tuple(
            RivalSupplyRecord(**r) for r in spec.get("rival_supply") or []
        ),
    }


def segment_records_for(
    records: Sequence[SegmentRevenueRecord],
    stock_code: str,
    node_product_lines: set[str] | None,
) -> list[SegmentRevenueRecord]:
    """Records attributable to this company's lines for the current node.

    ``node_product_lines=None`` → all records for the company (background).
    A provided set filters to exact product-line keys; broader-scope records
    (segment/industry_board covering the line) are still returned but the
    caller reads ``disclosure_scope`` — a segment that contains the line is
    not the same as the line.
    """
    rows = [r for r in records if r.stock_code == stock_code]
    if node_product_lines is None:
        return rows
    return [r for r in rows if r.product_line in node_product_lines]


def segment_cell(records: Sequence[SegmentRevenueRecord]) -> dict[str, Any]:
    """revenue_profit matrix cell from node-filtered records."""
    scoped = [r for r in records if r.disclosure_scope != "unextracted"]
    if not scoped:
        if any(r.disclosure_scope == "unextracted" for r in records):
            return {"state": "unextracted", "facts": []}
        return {"state": "missing", "facts": []}
    exact = [r for r in scoped if r.disclosure_scope == "product_line"]
    if exact:
        state = "disclosed"
    elif any(r.disclosure_scope == "undisclosed" for r in scoped):
        state = "undisclosed"
    else:
        state = "disclosed_broader_scope"  # segment/board number exists, line not split
    facts = [
        {
            "record_id": r.record_id,
            "product_line": r.product_line,
            "label": r.product_line_label,
            "period": r.report_period,
            "revenue": r.revenue,
            "gross_margin": r.gross_margin,
            "revenue_share": r.revenue_share,
            "scope": r.disclosure_scope,
            "review_status": r.review_status,
            "page": r.page_or_section,
        }
        for r in scoped
    ]
    return {"state": state, "facts": facts}


def rival_supply_as_evidence(
    record: RivalSupplyRecord,
    *,
    aspect: str = "process_irreplaceability",
    direction: str = "refute",
) -> tuple[CompanyEvidence, CompanySource]:
    """Convert a rival-supply record into node-scope evidence + source rows.

    Freshly curated records stay ``pending`` (or ``lead_only`` when the record
    itself says so) — they display in the queue but cannot swing a verdict
    until a human verifies the primary text.
    """
    ev = CompanyEvidence(
        evidence_id=record.record_id,
        source_id=record.source_id,
        dimension=aspect,
        direction=direction,
        excerpt=record.excerpt or record.supply_facts,
        page_or_section=record.page_or_section,
        confidence="medium",
        review_status=record.review_status,
        checklist_item="供应格局",
        evidence_scope="node",
        product_line="",
    )
    src = CompanySource(
        source_id=record.source_id,
        source_type="company_filing",
        title=f"{record.rival_name} rival supply disclosure",
        publisher="公司披露",
        published_at=record.published_at,
        ingested_at=record.ingested_at,
        uri=record.uri,
        reliability_level="S1",
    )
    return ev, src
