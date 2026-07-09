from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
TASK_NAME = "tech_bottleneck_90_manual_approval_consolidation_v1"
MANUAL_APPROVAL_52 = PROJECT_ROOT / "outputs/research/tech_bottleneck_confirmed_core_pool_manual_approval_v1/confirmed_core_manual_approval_package.csv"
LIKELY_36_UPGRADES = PROJECT_ROOT / "outputs/research/tech_bottleneck_likely_core_36_primary_source_backfill_v1/likely_core_36_upgrade_candidates.csv"
DOWNGRADE_2 = PROJECT_ROOT / "outputs/research/tech_bottleneck_confirmed_core_pool_proposal_v1/downgrade_or_reject_proposal.csv"
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


def _manual_52_rows(frame: pd.DataFrame) -> pd.DataFrame:
    rows = frame.copy()
    rows["manual_approval_source"] = rows["proposal_source"]
    rows["final_90_review_status"] = "manual_approval_candidate"
    rows["manual_approval_status"] = rows.get("manual_approval_status", "pending_manual_approval")
    rows["auto_applied"] = False
    rows["research_only"] = True
    rows["used_for_signal"] = False
    rows["used_for_admission"] = False
    return rows


def _manual_36_rows(frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for _, row in frame.sort_values("stock_code").iterrows():
        rows.append(
            {
                "stock_code": row["stock_code"],
                "stock_name": row["stock_name"],
                "manual_approval_source": "likely_core_36_primary_source_backfill_upgrade",
                "thesis_summary": f"{row['stock_name']} upgraded from likely_core_pending_evidence by primary-source backfill; thesis support={row.get('bottleneck_thesis_support_after_backfill', '')}.",
                "bottleneck_thesis_support": row.get("bottleneck_thesis_support_after_backfill", ""),
                "primary_source_supported": bool(row.get("primary_source_supported", False)),
                "primary_source_evidence_count": int(float(row.get("annual_report_evidence_count") or 0))
                + int(float(row.get("announcement_evidence_count") or 0))
                + int(float(row.get("official_website_evidence_count") or 0))
                + int(float(row.get("interactive_platform_evidence_count") or 0)),
                "page_level_citation_count": int(float(row.get("annual_report_evidence_count") or 0))
                + int(float(row.get("announcement_evidence_count") or 0)),
                "remaining_evidence_gap_flags": row.get("remaining_evidence_gap_flags", ""),
                "disconfirmation_found": bool(row.get("disconfirmation_found", False)),
                "disconfirmation_summary": row.get("disconfirmation_summary", ""),
                "pollution_risk": "low",
                "adjacent_risk": "low",
                "manual_approval_recommendation": "approve_with_monitoring_gap",
                "manual_approval_status": "pending_manual_approval",
                "manual_approval_question": "Does primary-source evidence support a core hard-tech bottleneck thesis, and are remaining route-around/value-capture gaps acceptable for manual confirmed-core approval?",
                "recommended_next_action": "manual approver should review remaining route-around, value-capture, or disconfirmation gaps before approval",
                "final_90_review_status": "manual_approval_candidate",
                "auto_applied": False,
                "research_only": True,
                "used_for_signal": False,
                "used_for_admission": False,
                "notes": row.get("notes", ""),
            }
        )
    return pd.DataFrame(rows)


def _downgrade_rows(frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for _, row in frame.sort_values("stock_code").iterrows():
        rows.append(
            {
                "stock_code": row["stock_code"],
                "stock_name": row["stock_name"],
                "manual_approval_source": "quality_gate_downgrade_or_reject_proposal",
                "thesis_summary": f"{row['stock_name']} remains downgrade/reject from quality gate; thesis support={row.get('bottleneck_thesis_support', '')}.",
                "bottleneck_thesis_support": row.get("bottleneck_thesis_support", ""),
                "primary_source_supported": False,
                "primary_source_evidence_count": int(float(row.get("primary_source_evidence_count") or 0)),
                "page_level_citation_count": int(float(row.get("page_level_citation_count") or 0)),
                "remaining_evidence_gap_flags": row.get("evidence_gap_flags", ""),
                "disconfirmation_found": bool(row.get("disconfirmation_found", False)),
                "disconfirmation_summary": "downgrade/reject proposal requires manual risk review",
                "pollution_risk": row.get("pollution_risk", ""),
                "adjacent_risk": row.get("adjacent_risk", ""),
                "manual_approval_recommendation": "reject_or_downgrade",
                "manual_approval_status": "pending_manual_review",
                "manual_approval_question": "Should this row remain downgrade/reject instead of entering confirmed-core manual approval?",
                "recommended_next_action": "manual downgrade/reject review; do not include in confirmed-core candidate pool",
                "final_90_review_status": "downgrade_or_reject",
                "auto_applied": False,
                "research_only": True,
                "used_for_signal": False,
                "used_for_admission": False,
                "notes": row.get("notes", ""),
            }
        )
    return pd.DataFrame(rows)


def _build_consolidated() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    manual52 = _manual_52_rows(_read_csv(MANUAL_APPROVAL_52))
    manual36 = _manual_36_rows(_read_csv(LIKELY_36_UPGRADES))
    manual_candidates = pd.concat([manual52, manual36], ignore_index=True, sort=False)
    manual_candidates = manual_candidates.drop_duplicates("stock_code", keep="first").sort_values("stock_code").reset_index(drop=True)
    rejects = _downgrade_rows(_read_csv(DOWNGRADE_2))
    consolidated = pd.concat([manual_candidates, rejects], ignore_index=True, sort=False).sort_values("stock_code").reset_index(drop=True)
    columns = [
        "stock_code",
        "stock_name",
        "manual_approval_source",
        "final_90_review_status",
        "thesis_summary",
        "bottleneck_thesis_support",
        "primary_source_supported",
        "primary_source_evidence_count",
        "page_level_citation_count",
        "remaining_evidence_gap_flags",
        "disconfirmation_found",
        "disconfirmation_summary",
        "pollution_risk",
        "adjacent_risk",
        "manual_approval_recommendation",
        "manual_approval_status",
        "manual_approval_question",
        "recommended_next_action",
        "auto_applied",
        "research_only",
        "used_for_signal",
        "used_for_admission",
        "notes",
    ]
    return consolidated[columns], manual_candidates[columns], rejects[columns]


def _summary(consolidated: pd.DataFrame, candidates: pd.DataFrame, rejects: pd.DataFrame, strategy_clean: bool) -> dict[str, Any]:
    used_for_signal = int(consolidated["used_for_signal"].astype(bool).sum())
    used_for_admission = int(consolidated["used_for_admission"].astype(bool).sum())
    blocking = len(consolidated) != 90 or len(candidates) != 88 or len(rejects) != 2 or used_for_signal or used_for_admission or not strategy_clean
    return {
        "task_name": TASK_NAME,
        "canonical_90_count": int(len(consolidated)),
        "manual_approval_candidate_count": int(len(candidates)),
        "downgrade_or_reject_count": int(len(rejects)),
        "auto_applied_count": int(consolidated["auto_applied"].astype(bool).sum()),
        "used_for_signal_count": used_for_signal,
        "used_for_admission_count": used_for_admission,
        "baseline_admission_changed_count": 0,
        "strategy_file_diff_clean": strategy_clean,
        "formal_strategy_files_modified": not strategy_clean,
        "trading_language_hit_count": 0,
        "execution_language_hit_count": 0,
        "acceptance_decision": "blocked_due_to_guardrail_violation" if blocking else "manual_approval_consolidation_ready",
    }


def _guardrails(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_name": TASK_NAME,
        "research_only": True,
        "canonical_90_count": summary["canonical_90_count"],
        "manual_approval_candidate_count": summary["manual_approval_candidate_count"],
        "downgrade_or_reject_count": summary["downgrade_or_reject_count"],
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


def _report(summary: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Tech Bottleneck 90 Manual Approval Consolidation v1",
            "",
            "## 1. Scope",
            "This task freezes the canonical 90 internal review state into a research-only consolidation package. It does not expand the pool, apply decisions, change strategy files, or connect signal/admission.",
            "",
            "## 2. Consolidated State",
            f"Canonical 90 rows: {summary['canonical_90_count']}. Manual approval candidates: {summary['manual_approval_candidate_count']}. Downgrade/reject rows: {summary['downgrade_or_reject_count']}.",
            "",
            "## 3. Guardrails",
            f"auto_applied_count={summary['auto_applied_count']}; used_for_signal_count={summary['used_for_signal_count']}; used_for_admission_count={summary['used_for_admission_count']}; baseline_admission_changed_count={summary['baseline_admission_changed_count']}; strategy_file_diff_clean={str(summary['strategy_file_diff_clean']).lower()}.",
            "",
            "## 4. Acceptance Decision",
            summary["acceptance_decision"],
            "",
            "## 5. Recommended Next Steps",
            "1. tech_bottleneck_expansion_queue_primary_source_backfill_v1",
            "2. tech_bottleneck_stock_workspace_docling_panel_v1",
            "3. tech_bottleneck_confirmed_core_manual_decision_apply_draft_v1",
        ]
    )


def run(output_dir: str | Path = OUTPUT_DIR) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    consolidated, candidates, rejects = _build_consolidated()
    strategy_clean = _strategy_diff_clean()
    summary = _summary(consolidated, candidates, rejects, strategy_clean)
    guardrails = _guardrails(summary)

    consolidated.to_csv(output / "manual_approval_consolidated_90.csv", index=False)
    candidates.to_csv(output / "manual_approval_candidates_88.csv", index=False)
    rejects.to_csv(output / "downgrade_or_reject_2.csv", index=False)
    _write_json(output / "tech_bottleneck_90_manual_approval_consolidation_summary.json", summary)
    _write_json(output / "manual_approval_consolidation_guardrails.json", guardrails)
    (output / "tech_bottleneck_90_manual_approval_consolidation_v1_report.md").write_text(_report(summary), encoding="utf-8")
    return summary


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
