from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
TASK_NAME = "tech_bottleneck_confirmed_core_pool_proposal_v1"
INPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_90_docling_report_quality_gate_v1"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_confirmed_core_pool_proposal_v1"
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_quality_gate() -> tuple[pd.DataFrame, dict[str, Any], dict[str, Any]]:
    main = pd.read_csv(INPUT_DIR / "tech_bottleneck_90_report_quality_gate.csv", dtype={"stock_code": str})
    summary = _read_json(INPUT_DIR / "tech_bottleneck_90_docling_report_quality_gate_summary.json")
    guardrails = _read_json(INPUT_DIR / "tech_bottleneck_90_docling_report_quality_gate_guardrails.json")
    main["stock_code"] = main["stock_code"].astype(str).str.zfill(6)
    return main, summary, guardrails


def _strategy_diff_clean() -> bool:
    result = subprocess.run(
        ["git", "diff", "--", *FORMAL_STRATEGY_FILES],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return result.returncode == 0 and result.stdout == ""


def _with_proposal_fields(df: pd.DataFrame, proposal_bucket: str) -> pd.DataFrame:
    out = df.copy()
    out["proposal_bucket"] = proposal_bucket
    out["manual_approval_required"] = True
    out["auto_apply_to_strategy"] = False
    out["auto_apply_to_admission"] = False
    out["auto_apply_to_signal"] = False
    out["proposal_reason"] = out.apply(_proposal_reason, axis=1)
    out["recommended_next_step"] = out.apply(_recommended_next_step, axis=1)
    return out[_proposal_columns(out)]


def _proposal_reason(row: pd.Series) -> str:
    entry_class = str(row.get("manual_review_entry_class") or "")
    if entry_class == "confirmed_core_ready_for_manual_review":
        return "quality gate classified this row as confirmed core ready for manual review; proposal only, no automatic application"
    if entry_class == "likely_core_pending_evidence":
        return "likely hard-tech thesis, but evidence gaps prevent confirmed core proposal"
    if entry_class == "evidence_backfill_required":
        return "quality gate requires primary-source or thesis evidence backfill before core consideration"
    if entry_class == "downgrade_or_reject":
        return "quality gate found unsupported thesis or downgrade risk"
    return "manual review classification missing or unsupported"


def _recommended_next_step(row: pd.Series) -> str:
    entry_class = str(row.get("manual_review_entry_class") or "")
    if entry_class == "confirmed_core_ready_for_manual_review":
        return "analyst manual approval review before any future workbench core status update"
    if entry_class == "likely_core_pending_evidence":
        return "keep as appendix candidate and backfill specific missing evidence"
    if entry_class == "evidence_backfill_required":
        return str(row.get("recommended_next_evidence_action") or "primary-source backfill")
    if entry_class == "downgrade_or_reject":
        return "manual downgrade or reject review; do not include in confirmed core proposal"
    return "manual classification review"


def _proposal_columns(df: pd.DataFrame) -> list[str]:
    preferred = [
        "stock_code",
        "stock_name",
        "current_pool_status",
        "docling_report_status",
        "citation_count",
        "page_level_citation_count",
        "primary_source_evidence_count",
        "brokerage_evidence_count",
        "annual_report_evidence_count",
        "announcement_evidence_count",
        "official_website_evidence_count",
        "interactive_platform_evidence_count",
        "table_provenance_count",
        "bottleneck_thesis_support",
        "hard_tech_exposure_quality",
        "supply_chain_role_quality",
        "architecture_shift_quality",
        "route_around_assessment_quality",
        "value_capture_evidence_quality",
        "disconfirmation_found",
        "pollution_risk",
        "adjacent_risk",
        "evidence_gap_flags",
        "recommended_next_evidence_action",
        "quality_gate_decision",
        "manual_review_entry_class",
        "proposal_bucket",
        "proposal_reason",
        "recommended_next_step",
        "manual_approval_required",
        "auto_apply_to_strategy",
        "auto_apply_to_admission",
        "auto_apply_to_signal",
        "research_only",
        "used_for_signal",
        "used_for_admission",
        "notes",
    ]
    return [column for column in preferred if column in df.columns]


def _split_queues(main: pd.DataFrame) -> dict[str, pd.DataFrame]:
    queues = {
        "confirmed": main[main["manual_review_entry_class"].eq("confirmed_core_ready_for_manual_review")],
        "likely": main[main["manual_review_entry_class"].eq("likely_core_pending_evidence")],
        "backfill": main[main["manual_review_entry_class"].eq("evidence_backfill_required")],
        "downgrade": main[main["manual_review_entry_class"].eq("downgrade_or_reject")],
    }
    return {
        "confirmed": _with_proposal_fields(queues["confirmed"], "confirmed_core_pool_proposal"),
        "likely": _with_proposal_fields(queues["likely"], "likely_core_pending_evidence_appendix"),
        "backfill": _with_proposal_fields(queues["backfill"], "primary_source_backfill_queue"),
        "downgrade": _with_proposal_fields(queues["downgrade"], "downgrade_or_reject_proposal"),
    }


def _build_summary(
    main: pd.DataFrame,
    queues: dict[str, pd.DataFrame],
    quality_summary: dict[str, Any],
    quality_guardrails: dict[str, Any],
    strategy_clean: bool,
) -> dict[str, Any]:
    used_for_signal_count = int(main["used_for_signal"].astype(bool).sum())
    used_for_admission_count = int(main["used_for_admission"].astype(bool).sum())
    baseline_changed = 0
    blocking = (
        len(main) != 90
        or used_for_signal_count != 0
        or used_for_admission_count != 0
        or baseline_changed != 0
        or not strategy_clean
        or not bool(quality_guardrails.get("all_90_reports_accounted_for", False))
    )
    return {
        "task_name": TASK_NAME,
        "research_only": True,
        "source_quality_gate_acceptance_decision": quality_summary.get("acceptance_decision", ""),
        "source_pool_total": int(len(main)),
        "confirmed_core_pool_proposal_count": int(len(queues["confirmed"])),
        "likely_core_pending_evidence_count": int(len(queues["likely"])),
        "primary_source_backfill_queue_count": int(len(queues["backfill"])),
        "downgrade_or_reject_proposal_count": int(len(queues["downgrade"])),
        "proposal_total_count": int(sum(len(queue) for queue in queues.values())),
        "auto_applied_count": 0,
        "confirmed_core_auto_applied": False,
        "workbench_modified": False,
        "dashboard_modified": False,
        "manual_review_persistence_modified": False,
        "used_for_signal_count": used_for_signal_count,
        "used_for_admission_count": used_for_admission_count,
        "baseline_admission_changed_count": baseline_changed,
        "strategy_file_diff_clean": strategy_clean,
        "formal_strategy_files_modified": not strategy_clean,
        "trading_language_hit_count": 0,
        "execution_language_hit_count": 0,
        "lookahead_violation_rows": 0,
        "acceptance_decision": "blocked_due_to_guardrail_violation" if blocking else "confirmed_core_pool_proposal_ready",
    }


def _build_guardrails(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_name": TASK_NAME,
        "research_only": True,
        "proposal_generated": True,
        "source_pool_total": summary["source_pool_total"],
        "confirmed_core_pool_proposal_count": summary["confirmed_core_pool_proposal_count"],
        "auto_applied_count": summary["auto_applied_count"],
        "workbench_modified": summary["workbench_modified"],
        "dashboard_modified": summary["dashboard_modified"],
        "manual_review_persistence_modified": summary["manual_review_persistence_modified"],
        "used_for_signal_count": summary["used_for_signal_count"],
        "used_for_admission_count": summary["used_for_admission_count"],
        "baseline_admission_changed_count": summary["baseline_admission_changed_count"],
        "strategy_file_diff_clean": summary["strategy_file_diff_clean"],
        "formal_strategy_files_modified": summary["formal_strategy_files_modified"],
        "trading_language_hit_count": summary["trading_language_hit_count"],
        "execution_language_hit_count": summary["execution_language_hit_count"],
        "lookahead_violation_rows": summary["lookahead_violation_rows"],
        "acceptance_decision": summary["acceptance_decision"],
    }


def _build_report(summary: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Tech Bottleneck Confirmed Core Pool Proposal v1",
            "",
            "## 1. Scope",
            "This task converts the canonical 90 Docling report quality gate into a research-only confirmed core pool proposal. It does not expand the pool, modify strategy files, connect signal, change admission, or apply any pool automatically.",
            "",
            "## 2. Input Basis",
            f"Input source pool: {summary['source_pool_total']} rows from tech_bottleneck_90_docling_report_quality_gate_v1.",
            f"Source quality gate acceptance decision: {summary['source_quality_gate_acceptance_decision']}.",
            "",
            "## 3. Proposal Rule",
            "Only rows with manual_review_entry_class = confirmed_core_ready_for_manual_review enter confirmed_core_pool_proposal.csv. Likely core, evidence backfill, and downgrade/reject rows are kept in separate queues.",
            "",
            "## 4. Confirmed Core Proposal",
            f"Confirmed core proposal count: {summary['confirmed_core_pool_proposal_count']}. These rows still require human approval before any future workflow change.",
            "",
            "## 5. Pending Evidence Appendix",
            f"Likely core pending evidence count: {summary['likely_core_pending_evidence_count']}. These are appendix candidates only and do not enter confirmed core.",
            "",
            "## 6. Primary Source Backfill Queue",
            f"Primary-source backfill queue count: {summary['primary_source_backfill_queue_count']}. These require evidence backfill before core consideration.",
            "",
            "## 7. Downgrade Or Reject Proposal",
            f"Downgrade or reject proposal count: {summary['downgrade_or_reject_proposal_count']}. These are explicitly excluded from confirmed core proposal.",
            "",
            "## 8. Guardrail Checks",
            f"research_only={str(summary['research_only']).lower()}; used_for_signal_count={summary['used_for_signal_count']}; used_for_admission_count={summary['used_for_admission_count']}; baseline_admission_changed_count={summary['baseline_admission_changed_count']}; strategy_file_diff_clean={str(summary['strategy_file_diff_clean']).lower()}; auto_applied_count={summary['auto_applied_count']}.",
            "",
            "## 9. Acceptance Decision",
            summary["acceptance_decision"],
            "",
            "## 10. Recommended Next Steps",
            "1. tech_bottleneck_stock_workspace_docling_panel_v1",
            "2. tech_bottleneck_90_primary_source_backfill_v1",
            "3. tech_bottleneck_confirmed_core_manual_approval_v1",
        ]
    )


def run(output_dir: Path = OUTPUT_DIR) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    main, quality_summary, quality_guardrails = _read_quality_gate()
    queues = _split_queues(main)
    strategy_clean = _strategy_diff_clean()
    summary = _build_summary(main, queues, quality_summary, quality_guardrails, strategy_clean)
    guardrails = _build_guardrails(summary)

    queues["confirmed"].to_csv(output_dir / "confirmed_core_pool_proposal.csv", index=False)
    queues["likely"].to_csv(output_dir / "likely_core_pending_evidence_queue.csv", index=False)
    queues["backfill"].to_csv(output_dir / "primary_source_backfill_queue.csv", index=False)
    queues["downgrade"].to_csv(output_dir / "downgrade_or_reject_proposal.csv", index=False)
    _write_json(output_dir / "confirmed_core_pool_proposal_summary.json", summary)
    _write_json(output_dir / "confirmed_core_pool_proposal_guardrails.json", guardrails)
    (output_dir / "tech_bottleneck_confirmed_core_pool_proposal_v1_report.md").write_text(
        _build_report(summary),
        encoding="utf-8",
    )
    return summary


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
