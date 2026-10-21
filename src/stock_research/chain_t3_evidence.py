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
    source_type: str = "company_filing"   # 如实区分：券商线索/内部摘要不得标 company_filing
    reliability_level: str = "S1"
    uri: str = ""
    page_or_section: str = ""
    published_at: str = ""
    available_at: str = ""
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
        "customer_validation": tuple(
            CustomerValidationRecord(**r) for r in spec.get("customer_validation") or []
        ),
        "orders": tuple(OrderRecord(**r) for r in spec.get("orders") or []),
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


def _pit_ok(rec: Any, as_of: str | None) -> bool:
    """Same PIT rule as evidence: a record ingestible after the cutoff is
    future knowledge and excluded.  Missing dates are excluded too (no
    silent pass)."""
    if not as_of:
        return True
    cutoff = str(as_of)
    ing = str(getattr(rec, "ingested_at", "") or "")
    pub = str(getattr(rec, "published_at", "") or "")
    # Contradictory metadata → excluded (conservative).
    if pub and ing and pub > ing and len(pub) >= 10 and len(ing) >= 10:
        return False
    if ing:
        return ing[:10] <= cutoff
    if pub:
        return pub[:10] <= cutoff
    return False


def segment_cell(
    records: Sequence[SegmentRevenueRecord],
    as_of: str | None = None,
) -> dict[str, Any]:
    """revenue_profit matrix cell from node-filtered records.

    Pending facts are *candidates only* — they display in the review queue but
    the trusted ``state`` is computed from accepted records alone.  Historical
    ``as_of`` snapshots cannot read future-ingested numbers.
    """
    in_scope = [r for r in records if _pit_ok(r, as_of)]
    pending = [r for r in in_scope if r.review_status != "accepted"]
    accepted = [r for r in in_scope if r.review_status == "accepted"]
    scoped = [r for r in accepted if r.disclosure_scope != "unextracted"]

    def _fact(r: SegmentRevenueRecord) -> dict[str, Any]:
        return {
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

    candidates = [_fact(r) for r in pending if r.disclosure_scope != "unextracted"]
    if not scoped:
        state = (
            "unextracted"
            if any(r.disclosure_scope == "unextracted" for r in accepted + pending)
            else ("pending_review" if candidates else "missing")
        )
        return {"state": state, "facts": [], "candidate_facts": candidates}
    exact = [r for r in scoped if r.disclosure_scope == "product_line"]
    if exact:
        state = "disclosed"
    elif any(r.disclosure_scope == "undisclosed" for r in scoped):
        state = "undisclosed"
    else:
        state = "disclosed_broader_scope"  # segment/board number exists, line not split
    return {"state": state, "facts": [_fact(r) for r in scoped], "candidate_facts": candidates}


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
        source_type=record.source_type,
        title=f"{record.rival_name} rival supply disclosure",
        publisher="公司披露" if record.source_type == "company_filing" else "第三方",
        published_at=record.published_at,
        available_at=record.available_at,
        ingested_at=record.ingested_at,
        uri=record.uri,
        reliability_level=record.reliability_level,
    )
    return ev, src


# ---------------------------------------------------------------------------
# T3-I2 customer validation / T3-I3 orders — same contract, stricter tiers
# ---------------------------------------------------------------------------

VALIDATION_STAGES = ("contact", "sampling", "in_validation", "validated", "mass_delivery")
ORDER_STAGES = ("intent", "framework", "awarded", "contracted", "delivered", "revenue_recognized")


@dataclass(frozen=True)
class CustomerValidationRecord:
    record_id: str
    stock_code: str
    product_line: str
    stage: str                    # VALIDATION_STAGES
    customer: str = ""            # named only when the filing names it
    report_period: str = ""
    source_id: str = ""
    uri: str = ""
    page_or_section: str = ""
    published_at: str = ""
    ingested_at: str = ""
    review_status: str = "pending"
    excerpt: str = ""


@dataclass(frozen=True)
class OrderRecord:
    record_id: str
    stock_code: str
    product_line: str
    stage: str                    # ORDER_STAGES
    amount: float | None = None
    counterparty: str = ""
    report_period: str = ""
    scope: str = "product_line"   # product_line | segment | industry_board | company_total
    source_id: str = ""
    uri: str = ""
    page_or_section: str = ""
    published_at: str = ""
    ingested_at: str = ""
    review_status: str = "pending"
    excerpt: str = ""


def t3_fingerprint(
    segment_records: Sequence["SegmentRevenueRecord"],
    rival_supply: Sequence["RivalSupplyRecord"],
    validation: Sequence["CustomerValidationRecord"] = (),
    orders: Sequence["OrderRecord"] = (),
) -> str:
    """Fingerprint over T3 inputs — content/review/product-line edits all shift it."""
    import hashlib as _h
    canonical = json.dumps(
        {
            "seg": [dict(r.__dict__) for r in segment_records],
            "rv": [dict(r.__dict__) for r in rival_supply],
            "cv": [dict(r.__dict__) for r in validation],
            "ord": [dict(r.__dict__) for r in orders],
        },
        ensure_ascii=False, sort_keys=True, default=str,
    )
    return _h.sha256(canonical.encode("utf-8")).hexdigest()


def validation_cell(
    records: Sequence[CustomerValidationRecord],
    stock_code: str,
    node_product_lines: set[str] | None,
    as_of: str | None = None,
) -> dict[str, Any]:
    """T3-I2 cell: highest verified validation stage attributable to the node."""
    rows = [
        r for r in records
        if r.stock_code == stock_code
        and (node_product_lines is None or r.product_line in node_product_lines)
        and _pit_ok(r, as_of)
    ]
    accepted = [r for r in rows if r.review_status == "accepted"]
    stage_rank = {s: i for i, s in enumerate(VALIDATION_STAGES)}
    best = max(accepted, key=lambda r: stage_rank.get(r.stage, -1), default=None)
    state = (
        best.stage if best else ("pending_review" if rows else "none_seen")
    )
    return {
        "state": state,
        "validated_by": [r.customer for r in accepted if r.customer],
        "candidates": [
            {"record_id": r.record_id, "stage": r.stage, "customer": r.customer,
             "review_status": r.review_status}
            for r in rows if r.review_status != "accepted"
        ],
    }


def order_cell(
    records: Sequence[OrderRecord],
    stock_code: str,
    node_product_lines: set[str] | None,
    as_of: str | None = None,
) -> dict[str, Any]:
    """T3-I3 cell: highest verified order stage attributable to the node.

    Board/segment-scope order growth never upgrades to product-line orders.
    """
    rows = [
        r for r in records
        if r.stock_code == stock_code
        and (node_product_lines is None or r.product_line in node_product_lines)
        and _pit_ok(r, as_of)
    ]
    accepted = [r for r in rows if r.review_status == "accepted"]
    rank = {s: i for i, s in enumerate(ORDER_STAGES)}
    if any(r.stage == "none_disclosed" for r in accepted):
        return {"state": "none_disclosed", "best": None, "candidates": []}
    best = max(accepted, key=lambda r: rank.get(r.stage, -1), default=None)
    if best and best.stage not in ORDER_STAGES:
        best = None
    if best and best.scope != "product_line":
        # 板块/更大口径订单 → 明示口径，不归因为产品线订单
        state = f"{best.stage}_at_{best.scope}"
    elif best:
        state = f"verified_{best.stage}"
    else:
        state = "pending_review" if rows else "none_seen"
    return {
        "state": state,
        "best": ({"record_id": best.record_id, "stage": best.stage,
                  "amount": best.amount, "scope": best.scope,
                  "counterparty": best.counterparty} if best else None),
        "candidates": [
            {"record_id": r.record_id, "stage": r.stage, "scope": r.scope,
             "review_status": r.review_status}
            for r in rows if r.review_status != "accepted"
        ],
    }
