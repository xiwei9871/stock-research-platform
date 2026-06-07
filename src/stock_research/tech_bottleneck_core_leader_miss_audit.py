from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


MISS_AUDIT_COLUMNS = [
    "asset_id",
    "stock_name",
    "top_candidate_rows",
    "first_candidate_date",
    "best_rank",
    "gate_rows",
    "gate_pass_rows",
    "first_gate_pass_date",
    "core_tech_categories",
    "quality_rows",
    "quality_decisions",
    "best_quality_decision",
    "best_product_family",
    "best_product_linkage_quality",
    "best_bottleneck_quality",
    "best_technical_quality",
    "best_customer_quality",
    "best_capacity_quality",
    "best_catalyst_quality",
    "best_evidence_quality_score",
    "fail_stage",
    "primary_reason",
    "suggested_fix",
]


APPROVED_DECISIONS = {"auto_approve"}
P2_DECISIONS = {"needs_more_evidence", "needs_product_family_mapping"}


def build_core_leader_miss_audit(
    *,
    watchlist: pd.DataFrame,
    candidates: pd.DataFrame,
    gate: pd.DataFrame,
    quality_review: pd.DataFrame,
) -> pd.DataFrame:
    watch = _normalize_watchlist(watchlist)
    candidate_rows = _normalize_candidates(candidates)
    gate_rows = _normalize_gate(gate)
    review_rows = _normalize_review(quality_review)

    rows: list[dict[str, Any]] = []
    for item in watch.to_dict("records"):
        asset_id = item["asset_id"]
        asset_candidates = candidate_rows[candidate_rows["asset_id"].eq(asset_id)].copy()
        asset_gate = gate_rows[gate_rows["asset_id"].eq(asset_id)].copy()
        asset_review = review_rows[review_rows["asset_id"].eq(asset_id)].copy()
        best_review = _best_review(asset_review)
        fail_stage, reason, suggested_fix = _stage_reason(
            asset_candidates=asset_candidates,
            asset_gate=asset_gate,
            asset_review=asset_review,
            best_review=best_review,
        )
        rows.append(
            {
                "asset_id": asset_id,
                "stock_name": _first_nonempty([item.get("stock_name", ""), _first_nonempty(asset_candidates.get("stock_name")), _first_nonempty(asset_gate.get("stock_name")), _first_nonempty(asset_review.get("stock_name"))]),
                "top_candidate_rows": int(len(asset_candidates)),
                "first_candidate_date": _first_date(asset_candidates),
                "best_rank": _best_rank(asset_candidates),
                "gate_rows": int(len(asset_gate)),
                "gate_pass_rows": int(asset_gate["core_tech_gate"].eq("pass").sum()) if not asset_gate.empty else 0,
                "first_gate_pass_date": _first_date(asset_gate[asset_gate["core_tech_gate"].eq("pass")]) if not asset_gate.empty else "",
                "core_tech_categories": _join_unique(asset_gate.get("core_tech_category")),
                "quality_rows": int(len(asset_review)),
                "quality_decisions": _join_unique(asset_review.get("p3_decision")),
                "best_quality_decision": str(best_review.get("p3_decision", "")),
                "best_product_family": str(best_review.get("product_family", "")),
                "best_product_linkage_quality": str(best_review.get("product_linkage_quality", "")),
                "best_bottleneck_quality": str(best_review.get("bottleneck_quality", "")),
                "best_technical_quality": str(best_review.get("technical_quality", "")),
                "best_customer_quality": str(best_review.get("customer_quality", "")),
                "best_capacity_quality": str(best_review.get("capacity_quality", "")),
                "best_catalyst_quality": str(best_review.get("catalyst_quality", "")),
                "best_evidence_quality_score": int(best_review.get("evidence_quality_score", 0) or 0),
                "fail_stage": fail_stage,
                "primary_reason": reason,
                "suggested_fix": suggested_fix,
            }
        )
    return pd.DataFrame(rows).reindex(columns=MISS_AUDIT_COLUMNS)


def run_core_leader_miss_audit_from_files(
    *,
    watchlist_csv: Path,
    candidates_csv: Path,
    gate_csv: Path,
    quality_review_csv: Path,
    output_dir: Path,
) -> dict[str, Path]:
    audit = build_core_leader_miss_audit(
        watchlist=pd.read_csv(watchlist_csv),
        candidates=pd.read_csv(candidates_csv),
        gate=pd.read_csv(gate_csv),
        quality_review=pd.read_csv(quality_review_csv),
    )
    return write_core_leader_miss_audit_artifacts(
        audit=audit,
        output_dir=output_dir,
        inputs={
            "watchlist_csv": str(watchlist_csv),
            "candidates_csv": str(candidates_csv),
            "gate_csv": str(gate_csv),
            "quality_review_csv": str(quality_review_csv),
        },
    )


def write_core_leader_miss_audit_artifacts(
    *,
    audit: pd.DataFrame,
    output_dir: Path,
    inputs: dict[str, str] | None = None,
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    audit_path = output_dir / "core_leader_miss_audit.csv"
    summary_path = output_dir / "summary.md"
    manifest_path = output_dir / "manifest.json"
    normalized = audit.reindex(columns=MISS_AUDIT_COLUMNS)
    normalized.to_csv(audit_path, index=False)
    payload = {
        "asset_count": int(len(normalized)),
        "fail_stage_counts": normalized["fail_stage"].value_counts().to_dict() if not normalized.empty else {},
        "inputs": inputs or {},
        "files": {
            "audit": audit_path.name,
            "summary": summary_path.name,
            "manifest": manifest_path.name,
        },
    }
    summary_path.write_text(_render_summary(normalized, payload), encoding="utf-8")
    manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"audit": audit_path, "summary": summary_path, "manifest": manifest_path}


def _stage_reason(
    *,
    asset_candidates: pd.DataFrame,
    asset_gate: pd.DataFrame,
    asset_review: pd.DataFrame,
    best_review: dict[str, Any],
) -> tuple[str, str, str]:
    if asset_candidates.empty:
        return (
            "not_in_top_candidates",
            "asset is not present in the supplied top candidate pool",
            "check score/topN coverage before changing tech-bottleneck rules",
        )
    if asset_gate.empty or not asset_gate["core_tech_gate"].eq("pass").any():
        reason = _first_nonempty(asset_gate.get("gate_reason")) or "no core technology gate pass"
        return (
            "core_tech_gate",
            reason,
            "add PIT-safe core technology/product-family terms only if source evidence supports the asset",
        )
    if asset_review.empty:
        return (
            "quality_review_missing",
            "asset passed core gate but has no quality review row",
            "rerun quality review with the post-gate candidate file and evidence inputs",
        )

    decision = str(best_review.get("p3_decision", ""))
    reason = str(best_review.get("decision_reason", "")) or "quality review did not promote the asset"
    if decision in APPROVED_DECISIONS:
        return ("p1_auto_approved", reason, "no fix needed")
    if decision in P2_DECISIONS:
        return ("p2_human_review", reason, str(best_review.get("next_evidence_need", "")) or "operator review")
    return (
        "quality_review",
        reason,
        str(best_review.get("next_evidence_need", "")) or "supplement same-product-family evidence",
    )


def _normalize_watchlist(frame: pd.DataFrame) -> pd.DataFrame:
    normalized = frame.copy()
    for column in ["asset_id", "stock_name"]:
        if column not in normalized:
            normalized[column] = ""
        normalized[column] = normalized[column].astype("string").fillna("")
    return normalized[normalized["asset_id"].ne("")].drop_duplicates("asset_id", keep="first")


def _normalize_candidates(frame: pd.DataFrame) -> pd.DataFrame:
    normalized = frame.copy()
    for column in ["asset_id", "stock_name", "trade_date", "rank"]:
        if column not in normalized:
            normalized[column] = ""
    normalized["asset_id"] = normalized["asset_id"].astype("string").fillna("")
    normalized["stock_name"] = normalized["stock_name"].astype("string").fillna("")
    normalized["trade_date"] = pd.to_datetime(normalized["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d").fillna("")
    normalized["rank"] = pd.to_numeric(normalized["rank"], errors="coerce")
    return normalized[normalized["asset_id"].ne("")].copy()


def _normalize_gate(frame: pd.DataFrame) -> pd.DataFrame:
    normalized = frame.copy()
    for column in ["asset_id", "stock_name", "trade_date", "core_tech_gate", "core_tech_category", "gate_reason", "matched_terms"]:
        if column not in normalized:
            normalized[column] = ""
    normalized["asset_id"] = normalized["asset_id"].astype("string").fillna("")
    normalized["stock_name"] = normalized["stock_name"].astype("string").fillna("")
    normalized["trade_date"] = pd.to_datetime(normalized["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d").fillna("")
    for column in ["core_tech_gate", "core_tech_category", "gate_reason", "matched_terms"]:
        normalized[column] = normalized[column].astype("string").fillna("")
    return normalized[normalized["asset_id"].ne("")].copy()


def _normalize_review(frame: pd.DataFrame) -> pd.DataFrame:
    normalized = frame.copy()
    for column in [
        "asset_id",
        "stock_name",
        "trade_date",
        "p3_decision",
        "product_family",
        "product_linkage_quality",
        "bottleneck_quality",
        "technical_quality",
        "customer_quality",
        "capacity_quality",
        "catalyst_quality",
        "decision_reason",
        "next_evidence_need",
    ]:
        if column not in normalized:
            normalized[column] = ""
    if "evidence_quality_score" not in normalized:
        normalized["evidence_quality_score"] = 0
    normalized["asset_id"] = normalized["asset_id"].astype("string").fillna("")
    normalized["stock_name"] = normalized["stock_name"].astype("string").fillna("")
    normalized["trade_date"] = pd.to_datetime(normalized["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d").fillna("")
    text_columns = [column for column in normalized.columns if column != "evidence_quality_score"]
    for column in text_columns:
        normalized[column] = normalized[column].astype("string").fillna("")
    normalized["evidence_quality_score"] = pd.to_numeric(normalized["evidence_quality_score"], errors="coerce").fillna(0).astype(int)
    return normalized[normalized["asset_id"].ne("")].copy()


def _best_review(frame: pd.DataFrame) -> dict[str, Any]:
    if frame.empty:
        return {}
    ranked = frame.copy()
    ranked["_decision_rank"] = ranked["p3_decision"].map({"auto_approve": 0, "needs_more_evidence": 1, "needs_product_family_mapping": 2}).fillna(9)
    ranked = ranked.sort_values(["_decision_rank", "evidence_quality_score", "trade_date"], ascending=[True, False, True])
    return ranked.iloc[0].to_dict()


def _first_date(frame: pd.DataFrame) -> str:
    if frame.empty or "trade_date" not in frame:
        return ""
    dates = sorted(value for value in frame["trade_date"].astype("string").fillna("").tolist() if value)
    return dates[0] if dates else ""


def _best_rank(frame: pd.DataFrame) -> int:
    if frame.empty or "rank" not in frame:
        return 0
    rank = pd.to_numeric(frame["rank"], errors="coerce").min()
    return int(rank) if pd.notna(rank) else 0


def _join_unique(values: pd.Series | None) -> str:
    if values is None:
        return ""
    return "|".join(sorted({str(value) for value in values.dropna().astype(str) if str(value)}))


def _first_nonempty(values: Any) -> str:
    if values is None:
        return ""
    if isinstance(values, pd.Series):
        iterable = values.astype("string").fillna("").tolist()
    elif isinstance(values, list):
        iterable = values
    else:
        iterable = [values]
    for value in iterable:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _render_summary(audit: pd.DataFrame, payload: dict[str, Any]) -> str:
    lines = [
        "# Core Leader Miss Audit",
        "",
        f"- Assets: {payload['asset_count']}",
        "",
        "## Fail Stages",
    ]
    counts = payload.get("fail_stage_counts", {})
    if counts:
        for stage, count in counts.items():
            lines.append(f"- {stage}: {count}")
    else:
        lines.append("- none: 0")
    if not audit.empty:
        lines.extend(["", "## Assets"])
        for row in audit.to_dict("records"):
            lines.append(f"- {row['stock_name']} {row['asset_id']}: {row['fail_stage']} - {row['primary_reason']}")
    return "\n".join(lines) + "\n"
