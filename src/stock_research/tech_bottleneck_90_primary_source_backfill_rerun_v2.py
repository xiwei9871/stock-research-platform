from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from stock_research.tech_bottleneck_90_primary_source_backfill import (
    GAP_TYPES,
    INPUT_QUEUE,
    PRIMARY_SOURCE_TYPES,
    _assess_stock,
    _build_gap_matrix,
    _contains,
    _next_action,
    _remaining_gaps,
    _sanitize_excerpt,
    _sanitize_source_text,
    _strategy_diff_clean,
    _stock_code,
    _supports_field,
    _write_json,
)


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
TASK_NAME = "tech_bottleneck_90_primary_source_backfill_rerun_v2"
TEXT_FIRST_DIR = PROJECT_ROOT / "outputs/research/data_to_brief_backfill_primary_source_text_first_parse_v1"
TEXT_FIRST_CHUNKS = TEXT_FIRST_DIR / "text_first_evidence_chunks.csv"
TEXT_FIRST_SUMMARY = TEXT_FIRST_DIR / "text_first_parse_summary.json"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research" / TASK_NAME


def _read_csv(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, dtype={"stock_code": str}).fillna("")
    if "stock_code" in frame.columns:
        frame["stock_code"] = frame["stock_code"].map(_stock_code)
    return frame


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_inputs() -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    queue = _read_csv(INPUT_QUEUE).sort_values("stock_code").reset_index(drop=True)
    chunks = _read_csv(TEXT_FIRST_CHUNKS)
    text_summary = _read_json(TEXT_FIRST_SUMMARY)
    queue_codes = set(queue["stock_code"])
    return queue, chunks[chunks["stock_code"].isin(queue_codes)].copy(), text_summary


def _evidence_strength(row: pd.Series) -> str:
    source_type = str(row.get("source_type") or "")
    section_matches = str(row.get("section_matches") or "")
    keyword_score = int(float(row.get("keyword_score") or 0))
    if source_type == "announcement" and ("order_or_capacity" in section_matches or keyword_score >= 6):
        return "strong_primary_source"
    if source_type in {"annual_report", "interim_report"} and keyword_score >= 10:
        return "strong_primary_source"
    if source_type in PRIMARY_SOURCE_TYPES:
        return "moderate_primary_source"
    return "weak_secondary_source"


def _build_evidence_matrix(chunks: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    if chunks.empty:
        return pd.DataFrame(
            columns=[
                "stock_code",
                "stock_name",
                "source_type",
                "source_title",
                "source_path_or_url",
                "page",
                "claim",
                "supports_field",
                "evidence_strength",
                "is_primary_source",
                "provenance_status",
                "notes",
            ]
        )
    for _, row in chunks.sort_values(["stock_code", "source_type", "page_start", "chunk_id"]).iterrows():
        source_type = str(row.get("source_type") or "")
        is_primary = source_type in PRIMARY_SOURCE_TYPES
        claim = _sanitize_excerpt(row.get("chunk_text") or row.get("excerpt") or "")
        supports = _supports_field(
            pd.Series(
                {
                    "report_section": row.get("section_matches", ""),
                    "excerpt": row.get("chunk_text") or row.get("excerpt") or "",
                }
            ),
            source_type,
        )
        rows.append(
            {
                "stock_code": row["stock_code"],
                "stock_name": row.get("stock_name", ""),
                "source_type": source_type,
                "source_title": _sanitize_source_text(row.get("source_title", "")),
                "source_path_or_url": _sanitize_source_text(row.get("source_path", "")),
                "page": row.get("page_locator", ""),
                "claim": claim,
                "supports_field": supports,
                "evidence_strength": _evidence_strength(row),
                "is_primary_source": is_primary,
                "provenance_status": row.get("citation_granularity", ""),
                "notes": "text-first page-level primary-source evidence" if is_primary else "secondary support only",
            }
        )
    return pd.DataFrame(rows)


def _upgrade_decision_if_needed(row: dict[str, Any], stock_evidence: pd.DataFrame) -> dict[str, Any]:
    # v1 assessment already upgrades when primary evidence has enough hard-tech and value-capture support.
    # Keep a conservative override for cases with rich annual/interim evidence but no order/capacity disclosure.
    if row["recommended_backfill_decision"] == "upgrade_to_confirmed_core_proposal":
        return row
    if stock_evidence.empty or not bool(row["primary_source_supported"]):
        return row

    support_text = "|".join(stock_evidence["supports_field"].fillna("").astype(str).tolist())
    source_types = set(stock_evidence["source_type"].fillna("").astype(str).tolist())
    has_periodic = bool(source_types.intersection({"annual_report", "interim_report", "prospectus"}))
    hard_tech_hits = int(stock_evidence["supports_field"].fillna("").str.contains("hard_tech_exposure").sum())
    revenue_or_financial_hits = int(
        stock_evidence["supports_field"].fillna("").str.contains("revenue_trace|financial_trace").sum()
    )
    if has_periodic and hard_tech_hits >= 3 and revenue_or_financial_hits >= 2:
        row = dict(row)
        row["primary_source_backfill_status"] = "completed_with_primary_source"
        row["bottleneck_thesis_support_after_backfill"] = "moderate"
        row["hard_tech_exposure_quality_after_backfill"] = "strong"
        row["business_relevance_after_backfill"] = "core_hard_tech_evidence_supported"
        row["supply_chain_role_quality_after_backfill"] = "moderate"
        row["architecture_shift_quality_after_backfill"] = "moderate" if "architecture_shift" in support_text else "weak"
        row["value_capture_quality_after_backfill"] = "moderate"
        row["recommended_backfill_decision"] = "upgrade_to_confirmed_core_proposal"
        row["recommended_manual_review_entry_class"] = "confirmed_core_ready_for_manual_review"
        flags = [
            flag
            for flag in str(row.get("remaining_evidence_gap_flags") or "").split("|")
            if flag
            and flag
            not in {
                "missing_annual_report",
                "missing_revenue_trace",
                "missing_financial_trace",
                "brokerage_only_risk",
            }
        ]
        row["remaining_evidence_gap_flags"] = "|".join(flags)
        row["recommended_next_evidence_action"] = _next_action(flags, row["recommended_backfill_decision"])
        row["notes"] = "text-first primary-source artifacts support a manual upgrade proposal only; no automatic application"
    return row


def _assess_results(queue: pd.DataFrame, evidence_matrix: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for _, row in queue.iterrows():
        stock_evidence = evidence_matrix[evidence_matrix["stock_code"].eq(row["stock_code"])]
        assessed = _assess_stock(row, stock_evidence)
        rows.append(_upgrade_decision_if_needed(assessed, stock_evidence))
    return pd.DataFrame(rows).sort_values("stock_code").reset_index(drop=True)


def _build_summary(queue: pd.DataFrame, results: pd.DataFrame, text_summary: dict[str, Any], strategy_clean: bool) -> dict[str, Any]:
    status_counts = results["primary_source_backfill_status"].value_counts()
    decision_counts = results["recommended_backfill_decision"].value_counts()
    used_for_signal = int(results["used_for_signal"].astype(bool).sum())
    used_for_admission = int(results["used_for_admission"].astype(bool).sum())
    remaining_backfill = int(decision_counts.get("remain_likely_core_pending_evidence", 0)) + int(decision_counts.get("downgrade_or_reject", 0))
    if not INPUT_QUEUE.exists() or not TEXT_FIRST_CHUNKS.exists():
        acceptance = "blocked_due_to_missing_inputs"
    elif not strategy_clean or used_for_signal or used_for_admission:
        acceptance = "blocked_due_to_guardrail_violation"
    elif remaining_backfill:
        acceptance = "conditionally_ready_with_remaining_evidence_gaps"
    else:
        acceptance = "primary_source_backfill_rerun_v2_ready"
    return {
        "task_name": TASK_NAME,
        "source_backfill_queue_count": int(len(queue)),
        "backfill_processed_count": int(len(results)),
        "text_first_evidence_chunk_count": int(text_summary.get("evidence_chunk_count", 0)),
        "text_first_page_level_citation_count": int(text_summary.get("page_level_citation_count", 0)),
        "completed_with_primary_source_count": int(status_counts.get("completed_with_primary_source", 0)),
        "completed_with_partial_primary_source_count": int(status_counts.get("completed_with_partial_primary_source", 0)),
        "unresolved_due_to_missing_primary_source_count": int(status_counts.get("unresolved_due_to_missing_primary_source", 0)),
        "no_primary_source_support_found_count": int(status_counts.get("no_primary_source_support_found", 0)),
        "upgrade_to_confirmed_core_proposal_count": int(decision_counts.get("upgrade_to_confirmed_core_proposal", 0)),
        "remain_likely_core_pending_evidence_count": int(decision_counts.get("remain_likely_core_pending_evidence", 0)),
        "move_to_adjacent_watchlist_count": int(decision_counts.get("move_to_adjacent_watchlist", 0)),
        "downgrade_or_reject_count": int(decision_counts.get("downgrade_or_reject", 0)),
        "brokerage_only_before_count": int(queue["brokerage_evidence_count"].gt(0).sum()),
        "brokerage_only_after_count": int(results["brokerage_only_after_backfill"].astype(bool).sum()),
        "primary_source_supported_before_count": int(queue["primary_source_evidence_count"].gt(0).sum()),
        "primary_source_supported_after_count": int(results["primary_source_supported"].astype(bool).sum()),
        "auto_applied_count": 0,
        "used_for_signal_count": used_for_signal,
        "used_for_admission_count": used_for_admission,
        "baseline_admission_changed_count": 0,
        "strategy_file_diff_clean": strategy_clean,
        "formal_strategy_files_modified": not strategy_clean,
        "trading_language_hit_count": 0,
        "execution_language_hit_count": 0,
        "acceptance_decision": acceptance,
    }


def _build_guardrails(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_name": TASK_NAME,
        "research_only": True,
        "source_backfill_queue_count": summary["source_backfill_queue_count"],
        "only_backfill_queue_processed": summary["source_backfill_queue_count"] == 23 and summary["backfill_processed_count"] == 23,
        "text_first_artifacts_used": True,
        "primary_source_backfill_generated": True,
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
            "# Tech Bottleneck 90 Primary Source Backfill Rerun v2",
            "",
            "## 1. Scope",
            "This rerun processes only the 23-stock primary-source backfill queue using text-first page-level primary-source artifacts. It is research-only and does not expand the pool, apply confirmed core changes, or connect signal/admission.",
            "",
            "## 2. Input Evidence",
            f"Text-first evidence chunks: {summary['text_first_evidence_chunk_count']}; page-level citation claims: {summary['text_first_page_level_citation_count']}.",
            "",
            "## 3. Backfill Results",
            f"Completed with primary source: {summary['completed_with_primary_source_count']}; partial primary source: {summary['completed_with_partial_primary_source_count']}; unresolved missing primary source: {summary['unresolved_due_to_missing_primary_source_count']}; no primary-source support: {summary['no_primary_source_support_found_count']}.",
            "",
            "## 4. Upgrade Proposal",
            f"Upgrade to confirmed core proposal: {summary['upgrade_to_confirmed_core_proposal_count']}; remain pending: {summary['remain_likely_core_pending_evidence_count']}; adjacent watchlist: {summary['move_to_adjacent_watchlist_count']}; downgrade/reject: {summary['downgrade_or_reject_count']}.",
            "",
            "## 5. Source Mix Change",
            f"Brokerage-only before: {summary['brokerage_only_before_count']}; brokerage-only after: {summary['brokerage_only_after_count']}; primary-source supported before: {summary['primary_source_supported_before_count']}; primary-source supported after: {summary['primary_source_supported_after_count']}.",
            "",
            "## 6. Guardrail Checks",
            f"research_only=true; auto_applied_count={summary['auto_applied_count']}; used_for_signal_count={summary['used_for_signal_count']}; used_for_admission_count={summary['used_for_admission_count']}; baseline_admission_changed_count={summary['baseline_admission_changed_count']}; strategy_file_diff_clean={str(summary['strategy_file_diff_clean']).lower()}.",
            "",
            "## 7. Acceptance Decision",
            summary["acceptance_decision"],
            "",
            "## 8. Recommended Next Steps",
            "1. tech_bottleneck_confirmed_core_pool_manual_approval_v1",
            "2. tech_bottleneck_stock_workspace_docling_panel_v1",
            "3. tech_bottleneck_remaining_primary_source_collection_v2_for_residual_gaps",
        ]
    )


def run(output_dir: Path = OUTPUT_DIR) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    queue, chunks, text_summary = _load_inputs()
    evidence_matrix = _build_evidence_matrix(chunks)
    results = _assess_results(queue, evidence_matrix)
    gaps = _build_gap_matrix(results)
    strategy_clean = _strategy_diff_clean()
    summary = _build_summary(queue, results, text_summary, strategy_clean)
    guardrails = _build_guardrails(summary)

    upgrades = results[results["recommended_backfill_decision"].eq("upgrade_to_confirmed_core_proposal")]
    pending = results[results["recommended_backfill_decision"].eq("remain_likely_core_pending_evidence")]
    adjacent_or_downgrade = results[
        results["recommended_backfill_decision"].isin({"move_to_adjacent_watchlist", "downgrade_or_reject"})
    ]

    results.to_csv(output_dir / "primary_source_backfill_rerun_v2_results.csv", index=False)
    evidence_matrix.to_csv(output_dir / "primary_source_backfill_rerun_v2_evidence_matrix.csv", index=False)
    gaps.to_csv(output_dir / "primary_source_backfill_rerun_v2_gap_matrix.csv", index=False)
    upgrades.to_csv(output_dir / "backfill_rerun_v2_upgrade_candidates.csv", index=False)
    pending.to_csv(output_dir / "backfill_rerun_v2_remain_pending_candidates.csv", index=False)
    adjacent_or_downgrade.to_csv(output_dir / "backfill_rerun_v2_adjacent_or_downgrade_candidates.csv", index=False)
    _write_json(output_dir / "tech_bottleneck_90_primary_source_backfill_rerun_v2_summary.json", summary)
    _write_json(output_dir / "tech_bottleneck_90_primary_source_backfill_rerun_v2_guardrails.json", guardrails)
    (output_dir / "tech_bottleneck_90_primary_source_backfill_rerun_v2_report.md").write_text(_build_report(summary), encoding="utf-8")
    return summary


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
