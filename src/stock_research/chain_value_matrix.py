"""CAP-02 T2: node × company value-capture matrix.

Reads finished CAP-01 company dossiers (JSON) and produces a matrix row per
member company.  Cells report *dossier verdicts*, never raw guesses: undisclosed
per-line revenue stays ``needs_evidence`` rather than being extrapolated.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Sequence

from stock_research.chain_t3_evidence import (
    order_cell,
    segment_cell,
    segment_records_for,
    validation_cell,
)

# Matrix columns → what they attest
MATRIX_COLUMNS: dict[str, str] = {
    "tech_participation": "技术与产业链参与",
    "validation_delivery": "客户认证与实际交付",
    "verified_orders": "可核实订单",
    "revenue_profit": "相关业务收入与毛利",
    "concept_only_risk": "未核实概念关联",
}


def _dim_verdict(dossier: dict[str, Any], dimension: str) -> str:
    return (dossier.get("dimensions") or {}).get(dimension, {}).get("verdict", "unknown")


# Granular commercialization evidence tiers.  Order-level proof is strictly
# separated from delivery milestones and mere mass-production claims — a
# "量产" statement never upgrades to a verified order.
_ORDER_CHECKLIST_ITEMS = {"已确认订单", "中标合同", "订单"}
_DELIVERY_CHECKLIST_ITEMS = {"实际交付", "交付里程碑", "批量交付"}
_PRODUCTION_CHECKLIST_ITEMS = {"量产阶段", "量产/订单"}


def _order_claim_state(
    dossier: dict[str, Any],
    node_product_lines: set[str] | None = None,
) -> str:
    """Commercialization cell with strict evidence tiers AND node attribution.

    ``verified_order`` — bound counted evidence explicitly about orders or
    awarded contracts; ``verified_delivery`` — explicit delivery/batch
    delivery evidence; ``production_claimed`` — mass-production statements;
    ``unverified`` — claims exist but no usable evidence; ``none_seen`` —
    no commercialization claims at all.

    When ``node_product_lines`` is provided, evidence whose ``product_line``
    is empty or belongs to another line (storage-ESS vs data-center cooling)
    can never tier up; if such unattributable evidence exists the cell reads
    ``node_attribution_unknown`` — honest, not silent exclusion.
    """
    claims = dossier.get("claims") or []
    matrix = {row["evidence_id"]: row for row in dossier.get("evidence_matrix") or []}
    order_claims = [c for c in claims if c.get("dimension") == "commercialization"]
    tier = 0  # 4 order, 3 delivery, 2 production, 1 claims-only
    unattributed = False
    for claim in order_claims:
        counted = claim.get("verdict") in {"confirmed", "partially_supported"}
        claim_tier = 0
        for eid in claim.get("evidence_ids") or []:
            row = matrix.get(eid)
            if not row or row.get("verdict_weight") != "counted":
                continue
            if node_product_lines is not None:
                if (row.get("product_line") or "") not in node_product_lines:
                    unattributed = True
                    continue
            item = row.get("checklist_item") or ""
            if item in _ORDER_CHECKLIST_ITEMS:
                claim_tier = max(claim_tier, 4)
            elif item in _DELIVERY_CHECKLIST_ITEMS:
                claim_tier = max(claim_tier, 3)
            elif item in _PRODUCTION_CHECKLIST_ITEMS:
                claim_tier = max(claim_tier, 2)
        if counted:
            tier = max(tier, claim_tier)
        elif claim_tier:
            tier = max(tier, 1)
    if tier >= 4:
        return "verified_order"
    if tier == 3:
        return "verified_delivery"
    if tier == 2:
        return "production_claimed"
    if unattributed and node_product_lines is not None:
        return "node_attribution_unknown"
    if order_claims:
        return "unverified"
    return "none_seen"


def _validation_delivery_cell(
    dossier: dict[str, Any],
    node_product_lines: set[str] | None,
) -> str:
    """认证/交付 cell, node-filtered: only evidence attributable to the node's
    product lines may tier it up; otherwise node_attribution_unknown."""
    claims = dossier.get("claims") or []
    matrix = {row["evidence_id"]: row for row in dossier.get("evidence_matrix") or []}
    comm = [c for c in claims if c.get("dimension") == "commercialization"]
    if node_product_lines is None:
        return _dim_verdict(dossier, "commercialization")
    attributable = False
    for claim in comm:
        for eid in claim.get("evidence_ids") or []:
            row = matrix.get(eid)
            if not row:
                continue
            if (row.get("product_line") or "") in node_product_lines:
                attributable = True
                if row.get("verdict_weight") == "counted" and claim.get("verdict") in {
                    "confirmed", "partially_supported"
                }:
                    return claim["verdict"]
    if attributable:
        return "needs_evidence"
    if comm:
        return "node_attribution_unknown"
    return _dim_verdict(dossier, "commercialization")


def build_value_matrix(
    *,
    node_id: str,
    node_name: str,
    as_of: str,
    member_companies: Sequence[dict[str, Any]],
    dossier_by_code: dict[str, dict[str, Any]],
    node_product_lines: set[str] | None = None,
    segment_records: Sequence[Any] = (),
    validation_records: Sequence[Any] = (),
    order_records: Sequence[Any] = (),
) -> dict[str, Any]:
    """Assemble the node × company matrix.

    ``member_companies`` rows come from the theme mapping
    (stock_code/company_name/mapping_type/priority_score); ``dossier_by_code``
    maps stock_code → CAP-01 dossier dict.
    """
    rows: list[dict[str, Any]] = []
    for member in member_companies:
        code = str(member.get("stock_code") or "")
        dossier = dossier_by_code.get(code)
        if dossier is not None and str(dossier.get("as_of") or "") > str(as_of):
            # A company dossier cut *after* the node research date is future
            # knowledge — never let it contaminate a historical matrix.
            rows.append(
                {
                    "stock_code": code,
                    "company_name": dossier.get("company_name") or member.get("company_name", ""),
                    "mapping_type": member.get("mapping_type", ""),
                    "priority_score": member.get("priority_score"),
                    "dossier": "pit_incompatible",
                    "dossier_as_of": dossier.get("as_of"),
                    "tech_participation": "excluded",
                    "validation_delivery": "excluded",
                    "verified_orders": "excluded",
                    "revenue_profit": "excluded",
                    "concept_only_risk": "unevaluated",
                    "dossier_fingerprint": dossier.get("dossier_fingerprint", ""),
                }
            )
            continue
        if dossier is None:
            # 无 CAP-01 画像的公司仍可独立呈现 T3 候选经营事实（不推六维结论）。
            rows.append(
                {
                    "stock_code": code,
                    "company_name": member.get("company_name", ""),
                    "mapping_type": member.get("mapping_type", ""),
                    "priority_score": member.get("priority_score"),
                    "dossier": "missing",
                    "tech_participation": "unknown",
                    "validation_delivery": (
                        validation_cell(validation_records, code, node_product_lines, as_of)["state"]
                        if validation_records else "unknown"
                    ),
                    "verified_orders": (
                        order_cell(order_records, code, node_product_lines, as_of)
                        if order_records else "none_seen"
                    ),
                    "revenue_profit": (
                        segment_cell(
                            segment_records_for(segment_records, code, node_product_lines), as_of
                        ) if segment_records else "unknown"
                    ),
                    "concept_only_risk": "unevaluated",
                    "dossier_fingerprint": "",
                }
            )
            continue
        dims = dossier.get("dimensions") or {}
        positive = sum(
            1
            for dim in dims.values()
            if dim.get("verdict") in {"confirmed", "partially_supported"}
        )
        gated = [dims.get(d, {}).get("verdict", "unknown") for d in ("commercialization", "financial_realization")]
        concept_only = all(v in {"unknown", "needs_evidence"} for v in gated) and positive <= 2
        rows.append(
            {
                "stock_code": code,
                "company_name": dossier.get("company_name") or member.get("company_name", ""),
                "mapping_type": member.get("mapping_type", ""),
                "priority_score": member.get("priority_score"),
                "dossier": "present",
                "overall_verdict": (dossier.get("conclusion") or {}).get("overall_verdict", ""),
                "tech_participation": _dim_verdict(dossier, "tech_moat"),
                "verified_orders": (
                    order_cell(order_records, code, node_product_lines, as_of)
                    if order_records
                    else _order_claim_state(dossier, node_product_lines)
                ),
                "revenue_profit": segment_cell(
                    segment_records_for(segment_records, code, node_product_lines), as_of
                ) if segment_records else _dim_verdict(dossier, "financial_realization"),
                "validation_delivery": (
                    validation_cell(validation_records, code, node_product_lines, as_of)["state"]
                    if validation_records
                    else _validation_delivery_cell(dossier, node_product_lines)
                ),
                "concept_only_risk": "high" if concept_only else "low",
                "dossier_fingerprint": dossier.get("dossier_fingerprint", ""),
            }
        )
    return {
        "node_id": node_id,
        "node_name": node_name,
        "as_of": as_of,
        "columns": MATRIX_COLUMNS,
        "rows": rows,
    }


def load_dossiers(dossier_dir: str | Path, codes: Sequence[str]) -> dict[str, dict[str, Any]]:
    root = Path(dossier_dir)
    out: dict[str, dict[str, Any]] = {}
    for code in codes:
        path = root / f"{code}_dossier.json"
        if path.is_file():
            out[str(code)] = json.loads(path.read_text(encoding="utf-8"))
    return out
