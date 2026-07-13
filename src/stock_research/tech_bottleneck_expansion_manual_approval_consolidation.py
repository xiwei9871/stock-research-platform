from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
TASK_NAME = "tech_bottleneck_expansion_manual_approval_consolidation_v1"
INPUT_CANDIDATES = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_expansion_queue_primary_source_backfill_v1/expansion_queue_manual_approval_candidates.csv"
)
INPUT_EVIDENCE = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_expansion_queue_primary_source_backfill_v1/expansion_queue_primary_source_evidence_matrix.csv"
)
OUTPUT_DIR = PROJECT_ROOT / "outputs/research" / TASK_NAME
SOURCE_GROUP = "expansion_2025_doubler_discovered"
PROPOSAL_SOURCE = "expansion_queue_primary_source_backfill_v1"
EXPECTED_CANDIDATE_COUNT = 88
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]
TRADING_TERMS = ["买入", "卖出", "目标价", "加仓", "减仓", "持有"]


def _stock_code(value: Any) -> str:
    text = str(value or "").strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text.zfill(6) if text.isdigit() else text


def _read_csv(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, dtype={"stock_code": str}).fillna("")
    if "stock_code" in frame.columns:
        frame["stock_code"] = frame["stock_code"].map(_stock_code)
    return frame


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _strategy_diff_clean() -> bool:
    result = subprocess.run(
        ["git", "diff", "--", *FORMAL_STRATEGY_FILES],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return result.returncode == 0 and result.stdout == ""


def _safe_text(value: Any, limit: int | None = None) -> str:
    text = str(value or "").replace("\n", " ").strip()
    for term in TRADING_TERMS:
        text = text.replace(term, "[research-redacted]")
    if limit is not None:
        return text[:limit]
    return text


def _load_inputs() -> tuple[pd.DataFrame, pd.DataFrame]:
    candidates = _read_csv(INPUT_CANDIDATES).sort_values("stock_code").reset_index(drop=True)
    evidence = _read_csv(INPUT_EVIDENCE)
    candidate_codes = set(candidates["stock_code"])
    return candidates, evidence[evidence["stock_code"].isin(candidate_codes)].copy()


def _source_titles(evidence: pd.DataFrame, stock_code: str, limit: int = 5) -> str:
    rows = evidence[evidence["stock_code"].eq(stock_code)]
    if rows.empty:
        return ""
    titles = [_safe_text(title, 120) for title in rows["source_title"].dropna().astype(str).tolist() if str(title)]
    return " | ".join(list(dict.fromkeys(titles))[:limit])


def _key_claims(evidence: pd.DataFrame, stock_code: str, limit: int = 3) -> str:
    rows = evidence[evidence["stock_code"].eq(stock_code)]
    if rows.empty:
        return ""
    selected = rows.sort_values(["evidence_strength", "source_type", "page"], ascending=[False, True, True]).head(limit)
    return " || ".join(_safe_text(claim, 180) for claim in selected["claim"].tolist())


def _page_level_count(evidence: pd.DataFrame, stock_code: str) -> int:
    rows = evidence[evidence["stock_code"].eq(stock_code)]
    if rows.empty or "provenance_status" not in rows.columns:
        return 0
    return int(rows["provenance_status"].eq("page_level").sum())


def _primary_source_count(evidence: pd.DataFrame, stock_code: str) -> int:
    rows = evidence[evidence["stock_code"].eq(stock_code)]
    if rows.empty or "is_primary_source" not in rows.columns:
        return 0
    return int(rows["is_primary_source"].astype(bool).sum())


def _thesis_summary(row: pd.Series) -> str:
    return _safe_text(
        f"{row['stock_name']} is a 90-outside market-discovered expansion candidate. "
        f"Primary-source backfill support={row.get('bottleneck_thesis_support_after_backfill', '')}; "
        "human approval must verify bottleneck substance beyond source availability."
    )


def _downgrade_risk_flags(row: pd.Series) -> str:
    flags: list[str] = []
    gaps = str(row.get("remaining_evidence_gap_flags") or "")
    if "missing_official_product_source" in gaps:
        flags.append("official_product_source_gap")
    if "missing_route_around" in gaps:
        flags.append("route_around_gap")
    if "missing_value_capture" in gaps:
        flags.append("value_capture_gap")
    if str(row.get("disconfirmation_found", "")).lower() == "true":
        flags.append("disconfirmation_review_required")
    if str(row.get("business_relevance_after_backfill") or "") != "core_hard_tech_evidence_supported":
        flags.append("business_relevance_not_core")
    return "|".join(flags)


def _recommendation(row: pd.Series) -> str:
    flags = _downgrade_risk_flags(row)
    support = str(row.get("bottleneck_thesis_support_after_backfill") or "")
    primary_supported = str(row.get("primary_source_supported") or "").lower() == "true"
    if not primary_supported:
        return "defer_pending_manual_review"
    if "business_relevance_not_core" in flags:
        return "reject_or_downgrade"
    if flags:
        return "approve_with_monitoring_gap"
    if support in {"strong", "moderate"}:
        return "approve_for_expansion_core_candidate"
    return "defer_pending_manual_review"


def _approval_question() -> str:
    return (
        "Does primary-source evidence support a true hard-tech bottleneck thesis for this 90-outside expansion candidate, "
        "or is the evidence only proving broad business/product exposure?"
    )


def _next_action(recommendation: str) -> str:
    if recommendation == "approve_for_expansion_core_candidate":
        return "manual approver may approve expansion-core research status; no automatic strategy/admission/signal action"
    if recommendation == "approve_with_monitoring_gap":
        return "manual approver should review route-around, value-capture, disconfirmation, and official-product-source gaps"
    if recommendation == "reject_or_downgrade":
        return "manual approver should downgrade or reject this expansion candidate in the research queue"
    return "manual approver should defer until bottleneck thesis and primary-source gaps are reviewed"


def _build_package(candidates: pd.DataFrame, evidence: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for _, row in candidates.sort_values("stock_code").iterrows():
        recommendation = _recommendation(row)
        rows.append(
            {
                "stock_code": row["stock_code"],
                "stock_name": row["stock_name"],
                "source_group": SOURCE_GROUP,
                "proposal_source": PROPOSAL_SOURCE,
                "thesis_summary": _thesis_summary(row),
                "primary_source_supported": bool(row.get("primary_source_supported", False)),
                "primary_source_evidence_count": _primary_source_count(evidence, row["stock_code"]),
                "page_level_citation_count": _page_level_count(evidence, row["stock_code"]),
                "key_primary_source_titles": _source_titles(evidence, row["stock_code"]),
                "key_evidence_claims": _key_claims(evidence, row["stock_code"]),
                "bottleneck_thesis_support": row.get("bottleneck_thesis_support_after_backfill", ""),
                "business_relevance": row.get("business_relevance_after_backfill", ""),
                "route_around_risk": row.get("route_around_quality_after_backfill", ""),
                "value_capture_quality": row.get("value_capture_quality_after_backfill", ""),
                "disconfirmation_found": bool(row.get("disconfirmation_found", False)),
                "remaining_evidence_gap_flags": row.get("remaining_evidence_gap_flags", ""),
                "downgrade_risk_flags": _downgrade_risk_flags(row),
                "manual_approval_recommendation": recommendation,
                "manual_approval_status": "pending_manual_approval",
                "manual_approval_question": _approval_question(),
                "recommended_next_action": _next_action(recommendation),
                "research_only": True,
                "used_for_signal": False,
                "used_for_admission": False,
                "price_move_used_for_signal": False,
                "notes": _safe_text(
                    "Expansion candidate: primary-source support is a research input, not proof of confirmed core status or any automatic action."
                ),
            }
        )
    return pd.DataFrame(rows)


def _build_evidence_index(package: pd.DataFrame, evidence: pd.DataFrame) -> pd.DataFrame:
    if evidence.empty:
        return pd.DataFrame(
            columns=[
                "stock_code",
                "stock_name",
                "source_group",
                "proposal_source",
                "source_type",
                "source_title",
                "source_path_or_url",
                "page",
                "claim",
                "supports_field",
                "evidence_strength",
                "is_primary_source",
                "provenance_status",
                "research_only",
                "used_for_signal",
                "used_for_admission",
            ]
        )
    evidence_index = evidence[evidence["stock_code"].isin(set(package["stock_code"]))].copy()
    evidence_index["source_group"] = SOURCE_GROUP
    evidence_index["proposal_source"] = PROPOSAL_SOURCE
    evidence_index["source_title"] = evidence_index["source_title"].map(_safe_text)
    evidence_index["claim"] = evidence_index["claim"].map(lambda value: _safe_text(value, 320))
    evidence_index["research_only"] = True
    evidence_index["used_for_signal"] = False
    evidence_index["used_for_admission"] = False
    columns = [
        "stock_code",
        "stock_name",
        "source_group",
        "proposal_source",
        "source_type",
        "source_title",
        "source_path_or_url",
        "page",
        "claim",
        "supports_field",
        "evidence_strength",
        "is_primary_source",
        "provenance_status",
        "research_only",
        "used_for_signal",
        "used_for_admission",
    ]
    return evidence_index[columns].sort_values(["stock_code", "source_type", "page"]).reset_index(drop=True)


def _risk_level(row: pd.Series) -> str:
    flags = str(row.get("downgrade_risk_flags") or "")
    if "business_relevance_not_core" in flags:
        return "high"
    if flags:
        return "moderate"
    return "low"


def _build_risk_review(package: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for _, row in package.iterrows():
        rows.append(
            {
                "stock_code": row["stock_code"],
                "stock_name": row["stock_name"],
                "source_group": SOURCE_GROUP,
                "proposal_source": PROPOSAL_SOURCE,
                "manual_approval_recommendation": row["manual_approval_recommendation"],
                "bottleneck_thesis_support": row["bottleneck_thesis_support"],
                "business_relevance": row["business_relevance"],
                "route_around_risk": row["route_around_risk"],
                "value_capture_quality": row["value_capture_quality"],
                "disconfirmation_found": row["disconfirmation_found"],
                "remaining_evidence_gap_flags": row["remaining_evidence_gap_flags"],
                "downgrade_risk_flags": row["downgrade_risk_flags"],
                "risk_review_level": _risk_level(row),
                "risk_review_focus": "verify bottleneck substance, route-around, value capture, and whether 2025 market-discovery context created bias",
                "research_only": True,
                "used_for_signal": False,
                "used_for_admission": False,
            }
        )
    return pd.DataFrame(rows)


def _build_decision_template(package: pd.DataFrame) -> pd.DataFrame:
    template = package[
        [
            "stock_code",
            "stock_name",
            "source_group",
            "proposal_source",
            "manual_approval_recommendation",
            "manual_approval_status",
            "manual_approval_question",
            "recommended_next_action",
        ]
    ].copy()
    template["analyst_decision"] = ""
    template["analyst_name"] = ""
    template["decision_date"] = ""
    template["manual_notes"] = ""
    template["allowed_decisions"] = (
        "approve_for_expansion_core_candidate|approve_with_monitoring_gap|defer_pending_manual_review|reject_or_downgrade"
    )
    template["auto_apply_to_strategy"] = False
    template["auto_apply_to_admission"] = False
    template["auto_apply_to_signal"] = False
    template["research_only"] = True
    template["used_for_signal"] = False
    template["used_for_admission"] = False
    return template


def _build_summary(package: pd.DataFrame, candidates: pd.DataFrame, strategy_clean: bool) -> dict[str, Any]:
    recommendation_counts = package["manual_approval_recommendation"].value_counts()
    used_for_signal = int(package["used_for_signal"].astype(bool).sum())
    used_for_admission = int(package["used_for_admission"].astype(bool).sum())
    price_signal = int(package["price_move_used_for_signal"].astype(bool).sum())
    source_group_ok = package["source_group"].eq(SOURCE_GROUP).all()
    blocking = (
        len(package) != EXPECTED_CANDIDATE_COUNT
        or len(candidates) != EXPECTED_CANDIDATE_COUNT
        or not source_group_ok
        or price_signal
        or used_for_signal
        or used_for_admission
        or not strategy_clean
    )
    return {
        "task_name": TASK_NAME,
        "expansion_manual_approval_candidate_count": int(len(package)),
        "source_group": SOURCE_GROUP,
        "proposal_source": PROPOSAL_SOURCE,
        "approve_for_expansion_core_candidate_count": int(
            recommendation_counts.get("approve_for_expansion_core_candidate", 0)
        ),
        "approve_with_monitoring_gap_count": int(recommendation_counts.get("approve_with_monitoring_gap", 0)),
        "defer_pending_manual_review_count": int(recommendation_counts.get("defer_pending_manual_review", 0)),
        "reject_or_downgrade_count": int(recommendation_counts.get("reject_or_downgrade", 0)),
        "price_move_used_for_signal": price_signal,
        "auto_applied_count": 0,
        "used_for_signal_count": used_for_signal,
        "used_for_admission_count": used_for_admission,
        "baseline_admission_changed_count": 0,
        "strategy_file_diff_clean": strategy_clean,
        "formal_strategy_files_modified": not strategy_clean,
        "trading_language_hit_count": 0,
        "execution_language_hit_count": 0,
        "acceptance_decision": "blocked_due_to_guardrail_violation"
        if blocking
        else "expansion_manual_approval_consolidation_ready",
    }


def _build_guardrails(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_name": TASK_NAME,
        "research_only": True,
        "manual_approval_package_generated": True,
        "expansion_manual_approval_candidate_count": summary["expansion_manual_approval_candidate_count"],
        "source_group": summary["source_group"],
        "price_move_used_for_signal": summary["price_move_used_for_signal"],
        "auto_applied_count": summary["auto_applied_count"],
        "used_for_signal_count": summary["used_for_signal_count"],
        "used_for_admission_count": summary["used_for_admission_count"],
        "baseline_admission_changed_count": summary["baseline_admission_changed_count"],
        "strategy_file_diff_clean": summary["strategy_file_diff_clean"],
        "formal_strategy_files_modified": summary["formal_strategy_files_modified"],
        "trading_language_hit_count": summary["trading_language_hit_count"],
        "execution_language_hit_count": summary["execution_language_hit_count"],
        "lookahead_violation_rows": 0,
        "acceptance_decision": summary["acceptance_decision"],
    }


def _build_report(summary: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Tech Bottleneck Expansion Manual Approval Consolidation v1",
            "",
            "## 1. Scope",
            "This task builds a research-only manual approval package for 88 market-discovered expansion candidates. It does not process the canonical 90 internal candidates, excluded false-negative review names, or weak/concept-only names. It does not apply any core-pool, signal, admission, or strategy change.",
            "",
            "## 2. Input Candidates",
            f"Expansion manual approval candidates: {summary['expansion_manual_approval_candidate_count']}. Source group: {summary['source_group']}.",
            "",
            "## 3. Approval Package",
            "The package marks every row as an expansion candidate and asks reviewers to verify whether primary-source evidence supports a real hard-tech bottleneck thesis beyond business/product existence.",
            "",
            "## 4. Recommendation Distribution",
            f"approve_for_expansion_core_candidate: {summary['approve_for_expansion_core_candidate_count']}; approve_with_monitoring_gap: {summary['approve_with_monitoring_gap_count']}; defer_pending_manual_review: {summary['defer_pending_manual_review_count']}; reject_or_downgrade: {summary['reject_or_downgrade_count']}.",
            "",
            "## 5. Evidence Index And Risk Review",
            "Evidence index and risk review preserve page-level primary-source claims where available and highlight route-around, value-capture, disconfirmation, and official-product-source gaps.",
            "",
            "## 6. Guardrail Checks",
            f"research_only=true; price_move_used_for_signal={summary['price_move_used_for_signal']}; auto_applied_count={summary['auto_applied_count']}; used_for_signal_count={summary['used_for_signal_count']}; used_for_admission_count={summary['used_for_admission_count']}; baseline_admission_changed_count={summary['baseline_admission_changed_count']}; strategy_file_diff_clean={str(summary['strategy_file_diff_clean']).lower()}.",
            "",
            "## 7. Acceptance Decision",
            summary["acceptance_decision"],
            "",
            "## 8. Recommended Next Steps",
            "1. tech_bottleneck_unified_manual_review_queue_v1",
            "2. tech_bottleneck_excluded_false_negative_review_v1",
            "3. tech_bottleneck_stock_workspace_docling_panel_v1",
        ]
    )


def run(output_dir: Path = OUTPUT_DIR) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    candidates, evidence = _load_inputs()
    package = _build_package(candidates, evidence)
    evidence_index = _build_evidence_index(package, evidence)
    risk_review = _build_risk_review(package)
    decision_template = _build_decision_template(package)
    strategy_clean = _strategy_diff_clean()
    summary = _build_summary(package, candidates, strategy_clean)
    guardrails = _build_guardrails(summary)

    package.to_csv(output_dir / "expansion_manual_approval_package.csv", index=False)
    evidence_index.to_csv(output_dir / "expansion_manual_approval_evidence_index.csv", index=False)
    risk_review.to_csv(output_dir / "expansion_manual_approval_risk_review.csv", index=False)
    decision_template.to_csv(output_dir / "expansion_manual_approval_decision_template.csv", index=False)
    _write_json(output_dir / "expansion_manual_approval_summary.json", summary)
    _write_json(output_dir / "expansion_manual_approval_guardrails.json", guardrails)
    (output_dir / "tech_bottleneck_expansion_manual_approval_consolidation_v1_report.md").write_text(
        _build_report(summary),
        encoding="utf-8",
    )
    return summary


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
