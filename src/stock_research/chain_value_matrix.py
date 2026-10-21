"""CAP-02 T2: node × company value-capture matrix.

Reads finished CAP-01 company dossiers (JSON) and produces a matrix row per
member company.  Cells report *dossier verdicts*, never raw guesses: undisclosed
per-line revenue stays ``needs_evidence`` rather than being extrapolated.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Sequence

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


def _order_claim_state(dossier: dict[str, Any]) -> str:
    """Verified-order cell: any commercialization claim bound to 量产/订单
    checklist evidence that reached at least partial support."""
    claims = dossier.get("claims") or []
    matrix = {row["evidence_id"]: row for row in dossier.get("evidence_matrix") or []}
    order_claims = [c for c in claims if c.get("dimension") == "commercialization"]
    has_verified = False
    has_any = False
    for claim in order_claims:
        for eid in claim.get("evidence_ids") or []:
            row = matrix.get(eid)
            if not row:
                continue
            if row.get("checklist_item") == "量产/订单":
                has_any = True
                if claim.get("verdict") in {"confirmed", "partially_supported"}:
                    has_verified = True
    if has_verified:
        return "verified"
    if has_any or order_claims:
        return "claimed_unverified"
    return "none_seen"


def build_value_matrix(
    *,
    node_id: str,
    node_name: str,
    as_of: str,
    member_companies: Sequence[dict[str, Any]],
    dossier_by_code: dict[str, dict[str, Any]],
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
        if dossier is None:
            rows.append(
                {
                    "stock_code": code,
                    "company_name": member.get("company_name", ""),
                    "mapping_type": member.get("mapping_type", ""),
                    "priority_score": member.get("priority_score"),
                    "dossier": "missing",
                    "tech_participation": "unknown",
                    "validation_delivery": "unknown",
                    "verified_orders": "none_seen",
                    "revenue_profit": "unknown",
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
                "validation_delivery": _dim_verdict(dossier, "commercialization"),
                "verified_orders": _order_claim_state(dossier),
                "revenue_profit": _dim_verdict(dossier, "financial_realization"),
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
