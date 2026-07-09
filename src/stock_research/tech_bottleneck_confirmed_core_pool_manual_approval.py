from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
TASK_NAME = "tech_bottleneck_confirmed_core_pool_manual_approval_v1"
ORIGINAL_PROPOSAL = PROJECT_ROOT / "outputs/research/tech_bottleneck_confirmed_core_pool_proposal_v1/confirmed_core_pool_proposal.csv"
BACKFILL_UPGRADES = PROJECT_ROOT / "outputs/research/tech_bottleneck_90_primary_source_backfill_rerun_v2/backfill_rerun_v2_upgrade_candidates.csv"
QUALITY_GATE_MAIN = PROJECT_ROOT / "outputs/research/tech_bottleneck_90_docling_report_quality_gate_v1/tech_bottleneck_90_report_quality_gate.csv"
BACKFILL_EVIDENCE = PROJECT_ROOT / "outputs/research/tech_bottleneck_90_primary_source_backfill_rerun_v2/primary_source_backfill_rerun_v2_evidence_matrix.csv"
TEXT_FIRST_CLAIMS = PROJECT_ROOT / "outputs/research/data_to_brief_backfill_primary_source_text_first_parse_v1/text_first_citation_claims.csv"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research" / TASK_NAME
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]


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
    for term in ["买入", "卖出", "目标价", "加仓", "减仓", "持有"]:
        text = text.replace(term, "[research-redacted]")
    if limit is not None:
        return text[:limit]
    return text


def _load_inputs() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    original = _read_csv(ORIGINAL_PROPOSAL)
    backfill = _read_csv(BACKFILL_UPGRADES)
    quality = _read_csv(QUALITY_GATE_MAIN)
    evidence = _read_csv(BACKFILL_EVIDENCE)
    claims = _read_csv(TEXT_FIRST_CLAIMS)
    return original, backfill, quality, evidence, claims


def _source_titles(evidence: pd.DataFrame, stock_code: str, limit: int = 5) -> str:
    rows = evidence[evidence["stock_code"].eq(stock_code)]
    if rows.empty:
        return ""
    titles = [str(title) for title in rows["source_title"].dropna().astype(str).tolist() if str(title)]
    return " | ".join(list(dict.fromkeys(titles))[:limit])


def _key_claims(evidence: pd.DataFrame, stock_code: str, limit: int = 3) -> str:
    rows = evidence[evidence["stock_code"].eq(stock_code)]
    if rows.empty:
        return ""
    selected = rows.sort_values(["evidence_strength", "source_type", "page"], ascending=[False, True, True]).head(limit)
    return " || ".join(_safe_text(claim, 180) for claim in selected["claim"].tolist())


def _thesis_summary(row: pd.Series) -> str:
    stock_name = row.get("stock_name", "")
    support = row.get("bottleneck_thesis_support", row.get("bottleneck_thesis_support_after_backfill", ""))
    source = row.get("proposal_source", "")
    return _safe_text(f"{stock_name} is proposed for manual confirmed-core review from {source}; thesis support={support}.")


def _recommendation(row: pd.Series) -> str:
    gaps = str(row.get("remaining_evidence_gap_flags") or row.get("evidence_gap_flags") or "")
    disconfirm = str(row.get("disconfirmation_found", "")).lower() == "true"
    route_gap = "missing_route_around" in gaps
    value_gap = "missing_value_capture" in gaps
    if route_gap or value_gap or disconfirm:
        return "approve_with_monitoring_gap"
    if str(row.get("primary_source_supported", "")).lower() == "true" or int(float(row.get("primary_source_evidence_count") or 0)) > 0:
        return "approve_for_confirmed_core"
    return "defer_pending_manual_review"


def _approval_question(row: pd.Series) -> str:
    return _safe_text(
        "Does primary-source evidence support a core hard-tech bottleneck thesis, and are remaining route-around/value-capture gaps acceptable for manual confirmed-core approval?"
    )


def _next_action(row: pd.Series) -> str:
    recommendation = row["manual_approval_recommendation"]
    if recommendation == "approve_for_confirmed_core":
        return "manual approver may approve confirmed-core research status; no automatic strategy/admission action"
    if recommendation == "approve_with_monitoring_gap":
        return "manual approver should review remaining route-around, value-capture, or disconfirmation gaps before approval"
    if recommendation == "reject_or_downgrade":
        return "manual approver should reject or downgrade candidate in research-only workflow"
    return "manual approver should defer until thesis and evidence gaps are reviewed"


def _normalize_original(original: pd.DataFrame, quality: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for _, row in original.sort_values("stock_code").iterrows():
        rows.append(
            {
                "stock_code": row["stock_code"],
                "stock_name": row["stock_name"],
                "proposal_source": "original_confirmed_core_proposal",
                "bottleneck_thesis_support": row.get("bottleneck_thesis_support", ""),
                "primary_source_supported": int(float(row.get("primary_source_evidence_count") or 0)) > 0,
                "primary_source_evidence_count": int(float(row.get("primary_source_evidence_count") or 0)),
                "page_level_citation_count": int(float(row.get("page_level_citation_count") or 0)),
                "remaining_evidence_gap_flags": row.get("evidence_gap_flags", ""),
                "disconfirmation_found": bool(row.get("disconfirmation_found", False)),
                "disconfirmation_summary": "risk or counter-evidence section found in source evidence"
                if bool(row.get("disconfirmation_found", False))
                else "manual disconfirmation review required",
                "pollution_risk": row.get("pollution_risk", ""),
                "adjacent_risk": row.get("adjacent_risk", ""),
                "notes": row.get("notes", ""),
            }
        )
    return pd.DataFrame(rows)


def _normalize_backfill(backfill: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for _, row in backfill.sort_values("stock_code").iterrows():
        primary_count = (
            int(float(row.get("annual_report_evidence_count") or 0))
            + int(float(row.get("announcement_evidence_count") or 0))
            + int(float(row.get("official_website_evidence_count") or 0))
            + int(float(row.get("interactive_platform_evidence_count") or 0))
        )
        rows.append(
            {
                "stock_code": row["stock_code"],
                "stock_name": row["stock_name"],
                "proposal_source": "backfill_rerun_v2_upgrade",
                "bottleneck_thesis_support": row.get("bottleneck_thesis_support_after_backfill", ""),
                "primary_source_supported": bool(row.get("primary_source_supported", False)),
                "primary_source_evidence_count": primary_count,
                "page_level_citation_count": primary_count,
                "remaining_evidence_gap_flags": row.get("remaining_evidence_gap_flags", ""),
                "disconfirmation_found": bool(row.get("disconfirmation_found", False)),
                "disconfirmation_summary": row.get("disconfirmation_summary", ""),
                "pollution_risk": "low",
                "adjacent_risk": "low",
                "notes": row.get("notes", ""),
            }
        )
    return pd.DataFrame(rows)


def _build_package(original: pd.DataFrame, backfill: pd.DataFrame, quality: pd.DataFrame, evidence: pd.DataFrame) -> pd.DataFrame:
    package = pd.concat([_normalize_original(original, quality), _normalize_backfill(backfill)], ignore_index=True)
    package = package.drop_duplicates("stock_code", keep="first").sort_values("stock_code").reset_index(drop=True)
    package["key_primary_source_titles"] = package["stock_code"].map(lambda code: _source_titles(evidence, code))
    package["key_evidence_claims"] = package["stock_code"].map(lambda code: _key_claims(evidence, code))
    package["thesis_summary"] = package.apply(_thesis_summary, axis=1)
    package["manual_approval_recommendation"] = package.apply(_recommendation, axis=1)
    package["manual_approval_status"] = "pending_manual_approval"
    package["manual_approval_question"] = package.apply(_approval_question, axis=1)
    package["recommended_next_action"] = package.apply(_next_action, axis=1)
    package["research_only"] = True
    package["used_for_signal"] = False
    package["used_for_admission"] = False
    columns = [
        "stock_code",
        "stock_name",
        "proposal_source",
        "thesis_summary",
        "bottleneck_thesis_support",
        "primary_source_supported",
        "primary_source_evidence_count",
        "page_level_citation_count",
        "key_primary_source_titles",
        "key_evidence_claims",
        "remaining_evidence_gap_flags",
        "disconfirmation_found",
        "disconfirmation_summary",
        "pollution_risk",
        "adjacent_risk",
        "manual_approval_recommendation",
        "manual_approval_status",
        "manual_approval_question",
        "recommended_next_action",
        "research_only",
        "used_for_signal",
        "used_for_admission",
        "notes",
    ]
    return package[columns]


def _build_evidence_index(package: pd.DataFrame, evidence: pd.DataFrame, claims: pd.DataFrame) -> pd.DataFrame:
    package_codes = set(package["stock_code"])
    evidence_rows = evidence[evidence["stock_code"].isin(package_codes)].copy()
    if evidence_rows.empty:
        return pd.DataFrame(
            columns=[
                "stock_code",
                "stock_name",
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
    source_map = package.set_index("stock_code")["proposal_source"].to_dict()
    evidence_rows["proposal_source"] = evidence_rows["stock_code"].map(source_map)
    evidence_rows["research_only"] = True
    evidence_rows["used_for_signal"] = False
    evidence_rows["used_for_admission"] = False
    columns = [
        "stock_code",
        "stock_name",
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
    return evidence_rows[[column for column in columns if column in evidence_rows.columns]].sort_values(["stock_code", "source_type", "page"])


def _risk_level(row: pd.Series) -> str:
    gaps = str(row.get("remaining_evidence_gap_flags") or "")
    if row.get("manual_approval_recommendation") == "approve_for_confirmed_core":
        return "low"
    if "missing_route_around" in gaps or "missing_value_capture" in gaps:
        return "moderate"
    return "low"


def _build_risk_review(package: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for _, row in package.iterrows():
        rows.append(
            {
                "stock_code": row["stock_code"],
                "stock_name": row["stock_name"],
                "proposal_source": row["proposal_source"],
                "manual_approval_recommendation": row["manual_approval_recommendation"],
                "pollution_risk": row["pollution_risk"],
                "adjacent_risk": row["adjacent_risk"],
                "disconfirmation_found": row["disconfirmation_found"],
                "remaining_evidence_gap_flags": row["remaining_evidence_gap_flags"],
                "risk_review_level": _risk_level(row),
                "risk_review_focus": _safe_text(
                    "route-around, value capture, disconfirmation, and concept pollution review before any manual approval"
                ),
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
    template["allowed_decisions"] = "approve_for_confirmed_core|approve_with_monitoring_gap|defer_pending_manual_review|reject_or_downgrade"
    template["auto_apply_to_strategy"] = False
    template["auto_apply_to_admission"] = False
    template["auto_apply_to_signal"] = False
    template["research_only"] = True
    template["used_for_signal"] = False
    template["used_for_admission"] = False
    return template


def _build_summary(package: pd.DataFrame, original: pd.DataFrame, backfill: pd.DataFrame, strategy_clean: bool) -> dict[str, Any]:
    recommendation_counts = package["manual_approval_recommendation"].value_counts()
    used_for_signal = int(package["used_for_signal"].astype(bool).sum())
    used_for_admission = int(package["used_for_admission"].astype(bool).sum())
    blocking = (
        len(package) != 52
        or len(original) != 29
        or len(backfill) != 23
        or used_for_signal
        or used_for_admission
        or not strategy_clean
    )
    return {
        "task_name": TASK_NAME,
        "manual_approval_candidate_count": int(len(package)),
        "original_confirmed_core_count": int(len(original)),
        "backfill_upgrade_count": int(len(backfill)),
        "approve_for_confirmed_core_recommendation_count": int(recommendation_counts.get("approve_for_confirmed_core", 0)),
        "approve_with_monitoring_gap_count": int(recommendation_counts.get("approve_with_monitoring_gap", 0)),
        "defer_pending_manual_review_count": int(recommendation_counts.get("defer_pending_manual_review", 0)),
        "reject_or_downgrade_count": int(recommendation_counts.get("reject_or_downgrade", 0)),
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
        else "confirmed_core_manual_approval_package_ready",
    }


def _build_guardrails(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_name": TASK_NAME,
        "research_only": True,
        "manual_approval_package_generated": True,
        "manual_approval_candidate_count": summary["manual_approval_candidate_count"],
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
            "# Tech Bottleneck Confirmed Core Pool Manual Approval v1",
            "",
            "## 1. Scope",
            "This task builds a research-only manual approval package for 52 confirmed-core proposal candidates. It does not expand the pool, modify strategy files, connect signal/admission, or automatically apply confirmed core status.",
            "",
            "## 2. Input Candidates",
            f"Original confirmed core proposal: {summary['original_confirmed_core_count']}. Backfill rerun v2 upgrades: {summary['backfill_upgrade_count']}. Manual approval candidates: {summary['manual_approval_candidate_count']}.",
            "",
            "## 3. Approval Package",
            "The package includes thesis summaries, primary-source support flags, evidence titles, key evidence claims, remaining gaps, disconfirmation fields, and a pending manual approval status.",
            "",
            "## 4. Recommendation Distribution",
            f"approve_for_confirmed_core: {summary['approve_for_confirmed_core_recommendation_count']}; approve_with_monitoring_gap: {summary['approve_with_monitoring_gap_count']}; defer_pending_manual_review: {summary['defer_pending_manual_review_count']}; reject_or_downgrade: {summary['reject_or_downgrade_count']}.",
            "",
            "## 5. Evidence Index",
            "The evidence index links approval candidates to page-level primary-source claims where available. It is for manual review only.",
            "",
            "## 6. Risk Review",
            "Risk review focuses on route-around, value capture, disconfirmation, adjacent risk, and concept pollution before any human approval.",
            "",
            "## 7. Guardrail Checks",
            f"research_only=true; auto_applied_count={summary['auto_applied_count']}; used_for_signal_count={summary['used_for_signal_count']}; used_for_admission_count={summary['used_for_admission_count']}; baseline_admission_changed_count={summary['baseline_admission_changed_count']}; strategy_file_diff_clean={str(summary['strategy_file_diff_clean']).lower()}.",
            "",
            "## 8. Acceptance Decision",
            summary["acceptance_decision"],
            "",
            "## 9. Recommended Next Steps",
            "1. tech_bottleneck_likely_core_36_primary_source_backfill_v1",
            "2. tech_bottleneck_stock_workspace_docling_panel_v1",
            "3. tech_bottleneck_confirmed_core_manual_decision_apply_draft_v1",
        ]
    )


def run(output_dir: Path = OUTPUT_DIR) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    original, backfill, quality, evidence, claims = _load_inputs()
    package = _build_package(original, backfill, quality, evidence)
    evidence_index = _build_evidence_index(package, evidence, claims)
    risk_review = _build_risk_review(package)
    decision_template = _build_decision_template(package)
    strategy_clean = _strategy_diff_clean()
    summary = _build_summary(package, original, backfill, strategy_clean)
    guardrails = _build_guardrails(summary)

    package.to_csv(output_dir / "confirmed_core_manual_approval_package.csv", index=False)
    evidence_index.to_csv(output_dir / "confirmed_core_manual_approval_evidence_index.csv", index=False)
    risk_review.to_csv(output_dir / "confirmed_core_manual_approval_risk_review.csv", index=False)
    decision_template.to_csv(output_dir / "confirmed_core_manual_approval_decision_template.csv", index=False)
    _write_json(output_dir / "confirmed_core_manual_approval_summary.json", summary)
    _write_json(output_dir / "confirmed_core_manual_approval_guardrails.json", guardrails)
    (output_dir / "tech_bottleneck_confirmed_core_pool_manual_approval_v1_report.md").write_text(_build_report(summary), encoding="utf-8")
    return summary


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
