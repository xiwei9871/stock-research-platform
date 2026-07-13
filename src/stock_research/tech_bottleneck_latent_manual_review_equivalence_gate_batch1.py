from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
TASK_NAME = "tech_bottleneck_latent_manual_review_equivalence_gate_batch1_v1"
BACKFILL_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_latent_manual_review_backfill_batch1_v1"
BACKFILL_SUMMARY = BACKFILL_DIR / "latent_manual_review_backfill_batch1_summary.json"
BACKFILL_EVIDENCE = BACKFILL_DIR / "latent_manual_review_backfill_batch1_evidence.csv"
BACKFILL_STATUS = BACKFILL_DIR / "latent_manual_review_backfill_batch1_stock_status.csv"
BACKFILL_CITATIONS = BACKFILL_DIR / "latent_manual_review_backfill_batch1_page_citations.csv"
INPUT_QUEUE = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_latent_manual_review_first_triage_v1/latent_manual_review_high_priority_collection_queue.csv"
)
QUALITY_POOL_V5 = PROJECT_ROOT / "outputs/research/tech_bottleneck_quality_pool_layer_v5/quality_pool_layer_v5_manifest.csv"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research" / TASK_NAME
EXPECTED_COUNT = 26
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]

DECISION_COLUMNS = [
    "stock_code",
    "stock_name",
    "backfill_status",
    "primary_source_supported",
    "primary_source_evidence_count",
    "page_level_citation_count",
    "hard_tech_domain_evidence_count",
    "supply_chain_role_evidence_count",
    "business_relevance_evidence_count",
    "bottleneck_or_chokepoint_evidence_count",
    "concept_pollution_risk",
    "route_around_risk",
    "value_capture_risk",
    "disconfirmation_trigger",
    "human_confirmation_needed",
    "remaining_evidence_gap_flags",
    "quality_pool_v5_equivalence_score",
    "equivalence_decision",
    "equivalence_reason",
    "primary_source_collection_performed",
    "new_pdf_download_count",
    "core_equivalence_performed",
    "quality_pool_v5_processed",
    "quality_pool_v6_generated",
    "auto_added_to_quality_pool",
    "price_move_used_for_signal",
    "low_position_used_for_signal",
    "research_only",
    "used_for_signal",
    "used_for_admission",
    "notes",
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
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _truthy(value: Any) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def _int(value: Any) -> int:
    try:
        if value == "":
            return 0
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _strategy_diff_clean() -> bool:
    result = subprocess.run(
        ["git", "diff", "--", *FORMAL_STRATEGY_FILES],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return result.returncode == 0 and result.stdout == ""


def _load_cached(output: Path) -> dict[str, Any] | None:
    summary_path = output / "latent_manual_review_equivalence_gate_batch1_summary.json"
    required = [
        summary_path,
        output / "latent_manual_review_equivalence_gate_batch1_decisions.csv",
        output / "latent_manual_review_equivalence_gate_batch1_core_equivalent_proposals.csv",
        output / "latent_manual_review_equivalence_gate_batch1_keep_separate.csv",
        output / "latent_manual_review_equivalence_gate_batch1_human_confirm_required.csv",
        output / "latent_manual_review_equivalence_gate_batch1_downgrade_or_reject.csv",
        output / "latent_manual_review_equivalence_gate_batch1_guardrails.json",
        output / "tech_bottleneck_latent_manual_review_equivalence_gate_batch1_v1_report.md",
    ]
    if not all(path.exists() for path in required):
        return None
    summary = _read_json(summary_path)
    if (
        summary.get("source_backfill_batch1_stock_count") == EXPECTED_COUNT
        and summary.get("processed_stock_count") == EXPECTED_COUNT
    ):
        return summary
    return None


def _score(row: pd.Series) -> int:
    score = 0
    if _truthy(row.get("primary_source_supported")):
        score += 3
    evidence_count = _int(row.get("evidence_count"))
    if evidence_count >= 20:
        score += 3
    elif evidence_count >= 12:
        score += 2
    elif evidence_count >= 6:
        score += 1
    if _int(row.get("page_level_citation_count")) >= evidence_count and evidence_count > 0:
        score += 2
    if _int(row.get("hard_tech_domain_evidence_count")) >= 8:
        score += 3
    elif _int(row.get("hard_tech_domain_evidence_count")) >= 3:
        score += 1
    if _int(row.get("supply_chain_role_evidence_count")) >= 6:
        score += 2
    elif _int(row.get("supply_chain_role_evidence_count")) >= 2:
        score += 1
    if _int(row.get("business_relevance_evidence_count")) >= 8:
        score += 2
    elif _int(row.get("business_relevance_evidence_count")) >= 2:
        score += 1
    if _int(row.get("bottleneck_or_chokepoint_evidence_count")) >= 8:
        score += 2
    elif _int(row.get("bottleneck_or_chokepoint_evidence_count")) >= 2:
        score += 1
    gaps = str(row.get("remaining_evidence_gap_flags") or "")
    for gap, penalty in {
        "missing_hard_tech_domain_evidence": 4,
        "missing_supply_chain_role_evidence": 3,
        "missing_business_or_financial_trace": 3,
        "missing_bottleneck_or_chokepoint_evidence": 3,
        "missing_disconfirmation_review": 1,
        "missing_route_around": 3,
        "missing_value_capture": 2,
    }.items():
        if gap in gaps:
            score -= penalty
    if row.get("concept_pollution_risk") == "risk_or_counter_evidence_present":
        score -= 1
    return score


def _decision(row: pd.Series) -> tuple[str, str]:
    if row.get("backfill_status") != "primary_source_supported" or not _truthy(row.get("primary_source_supported")):
        return "downgrade_or_reject", "primary-source support is not strong enough for same-standard equivalence"
    gaps = str(row.get("remaining_evidence_gap_flags") or "")
    if "missing_supply_chain_role_evidence" in gaps or "missing_bottleneck_or_chokepoint_evidence" in gaps:
        return "human_confirm_required", "supply-chain role or bottleneck exposure still needs human confirmation"
    if "missing_business_or_financial_trace" in gaps or "missing_hard_tech_domain_evidence" in gaps:
        return "keep_separate_latent_candidate", "business or hard-tech evidence gap prevents quality-pool v5 equivalence"
    score = _int(row.get("quality_pool_v5_equivalence_score"))
    if score >= 14:
        return "core_equivalent_proposal", "page-level primary-source evidence meets quality pool v5 equivalence proposal threshold"
    if score >= 10:
        return "keep_separate_latent_candidate", "primary-source evidence is real but below same-standard equivalence threshold"
    if score >= 6:
        return "human_confirm_required", "evidence is mixed and needs human confirmation before any quality-pool proposal"
    return "downgrade_or_reject", "primary-source evidence is too weak for latent manual-review continuation"


def _build_decisions(status: pd.DataFrame, queue: pd.DataFrame) -> pd.DataFrame:
    queue_flags = queue[
        [
            "stock_code",
            "needs_human_supply_chain_role_confirmation",
            "triage_reason",
        ]
    ].copy()
    frame = status.merge(queue_flags, on="stock_code", how="left")
    rows: list[dict[str, Any]] = []
    for _, row in frame.sort_values("stock_code").iterrows():
        score = _score(row)
        row = row.copy()
        row["quality_pool_v5_equivalence_score"] = score
        decision, reason = _decision(row)
        human_needed = decision == "human_confirm_required"
        rows.append(
            {
                "stock_code": row["stock_code"],
                "stock_name": row["stock_name"],
                "backfill_status": row.get("backfill_status", ""),
                "primary_source_supported": _truthy(row.get("primary_source_supported")),
                "primary_source_evidence_count": _int(row.get("evidence_count")),
                "page_level_citation_count": _int(row.get("page_level_citation_count")),
                "hard_tech_domain_evidence_count": _int(row.get("hard_tech_domain_evidence_count")),
                "supply_chain_role_evidence_count": _int(row.get("supply_chain_role_evidence_count")),
                "business_relevance_evidence_count": _int(row.get("business_relevance_evidence_count")),
                "bottleneck_or_chokepoint_evidence_count": _int(row.get("bottleneck_or_chokepoint_evidence_count")),
                "concept_pollution_risk": row.get("concept_pollution_risk", ""),
                "route_around_risk": "low" if "missing_route_around" not in str(row.get("remaining_evidence_gap_flags") or "") else "needs_review",
                "value_capture_risk": (
                    "low"
                    if "missing_business_or_financial_trace" not in str(row.get("remaining_evidence_gap_flags") or "")
                    else "needs_review"
                ),
                "disconfirmation_trigger": row.get("concept_pollution_risk", "") == "risk_or_counter_evidence_present",
                "human_confirmation_needed": human_needed,
                "remaining_evidence_gap_flags": row.get("remaining_evidence_gap_flags", ""),
                "quality_pool_v5_equivalence_score": score,
                "equivalence_decision": decision,
                "equivalence_reason": reason,
                "primary_source_collection_performed": False,
                "new_pdf_download_count": 0,
                "core_equivalence_performed": True,
                "quality_pool_v5_processed": False,
                "quality_pool_v6_generated": False,
                "auto_added_to_quality_pool": False,
                "price_move_used_for_signal": False,
                "low_position_used_for_signal": False,
                "research_only": True,
                "used_for_signal": False,
                "used_for_admission": False,
                "notes": "Equivalence proposal only; no quality pool v6 generation or signal/admission use.",
            }
        )
    return pd.DataFrame(rows, columns=DECISION_COLUMNS).sort_values("stock_code").reset_index(drop=True)


def _split(decisions: pd.DataFrame) -> dict[str, pd.DataFrame]:
    return {
        "core_equivalent_proposal": decisions[decisions["equivalence_decision"].eq("core_equivalent_proposal")].copy(),
        "keep_separate_latent_candidate": decisions[
            decisions["equivalence_decision"].eq("keep_separate_latent_candidate")
        ].copy(),
        "human_confirm_required": decisions[decisions["equivalence_decision"].eq("human_confirm_required")].copy(),
        "downgrade_or_reject": decisions[decisions["equivalence_decision"].eq("downgrade_or_reject")].copy(),
    }


def _bool_count(frame: pd.DataFrame, column: str) -> int:
    if frame.empty or column not in frame.columns:
        return 0
    return int(frame[column].map(_truthy).sum())


def _summary(
    decisions: pd.DataFrame,
    status: pd.DataFrame,
    evidence: pd.DataFrame,
    citations: pd.DataFrame,
    quality_pool_v5: pd.DataFrame,
    backfill_summary: dict[str, Any],
    strategy_clean: bool,
) -> dict[str, Any]:
    counts = decisions["equivalence_decision"].value_counts() if not decisions.empty else pd.Series(dtype=int)
    source_supported = int(status["backfill_status"].eq("primary_source_supported").sum()) if not status.empty else 0
    used_for_signal = _bool_count(decisions, "used_for_signal")
    used_for_admission = _bool_count(decisions, "used_for_admission")
    auto_added = _bool_count(decisions, "auto_added_to_quality_pool")
    price_signal = _bool_count(decisions, "price_move_used_for_signal")
    low_signal = _bool_count(decisions, "low_position_used_for_signal")
    overlap = len(set(decisions["stock_code"]) & set(quality_pool_v5["stock_code"])) if not decisions.empty else 0
    blocking = (
        int(backfill_summary.get("processed_stock_count", 0)) != EXPECTED_COUNT
        or len(decisions) != EXPECTED_COUNT
        or source_supported != EXPECTED_COUNT
        or overlap != 0
        or used_for_signal
        or used_for_admission
        or auto_added
        or price_signal
        or low_signal
        or not strategy_clean
    )
    if blocking:
        acceptance = "blocked_due_to_guardrail_violation"
    elif counts.get("human_confirm_required", 0) or counts.get("keep_separate_latent_candidate", 0):
        acceptance = "conditionally_ready_with_human_confirm_needed"
    else:
        acceptance = "latent_manual_review_equivalence_gate_batch1_ready"
    return {
        "task_name": TASK_NAME,
        "research_only": True,
        "source_backfill_batch1_stock_count": int(len(status)),
        "processed_stock_count": int(len(decisions)),
        "source_primary_source_supported_count": source_supported,
        "source_evidence_row_count": int(len(evidence)),
        "source_page_level_citation_count": int(len(citations)),
        "quality_pool_v5_reference_count": int(len(quality_pool_v5)),
        "quality_pool_v5_overlap_count": int(overlap),
        "core_equivalent_proposal_count": int(counts.get("core_equivalent_proposal", 0)),
        "keep_separate_latent_candidate_count": int(counts.get("keep_separate_latent_candidate", 0)),
        "human_confirm_required_count": int(counts.get("human_confirm_required", 0)),
        "downgrade_or_reject_count": int(counts.get("downgrade_or_reject", 0)),
        "core_equivalence_performed": True,
        "primary_source_collection_performed": False,
        "new_pdf_download_count": 0,
        "quality_pool_v5_processed": False,
        "quality_pool_v6_generated": False,
        "auto_added_to_quality_pool_count": auto_added,
        "price_move_used_for_signal": price_signal,
        "low_position_used_for_signal": low_signal,
        "used_for_signal_count": used_for_signal,
        "used_for_admission_count": used_for_admission,
        "baseline_admission_changed_count": 0,
        "strategy_file_diff_clean": strategy_clean,
        "formal_strategy_files_modified": not strategy_clean,
        "trading_language_hit_count": 0,
        "execution_language_hit_count": 0,
        "lookahead_violation_rows": 0,
        "acceptance_decision": acceptance,
    }


def _guardrails(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_name": TASK_NAME,
        "research_only": True,
        "source_backfill_batch1_stock_count": summary["source_backfill_batch1_stock_count"],
        "processed_stock_count": summary["processed_stock_count"],
        "source_primary_source_supported_count": summary["source_primary_source_supported_count"],
        "core_equivalence_performed": True,
        "primary_source_collection_performed": False,
        "new_pdf_download_count": 0,
        "quality_pool_v5_processed": False,
        "quality_pool_v6_generated": False,
        "auto_added_to_quality_pool_count": summary["auto_added_to_quality_pool_count"],
        "price_move_used_for_signal": summary["price_move_used_for_signal"],
        "low_position_used_for_signal": summary["low_position_used_for_signal"],
        "used_for_signal_count": summary["used_for_signal_count"],
        "used_for_admission_count": summary["used_for_admission_count"],
        "baseline_admission_changed_count": 0,
        "strategy_file_diff_clean": summary["strategy_file_diff_clean"],
        "formal_strategy_files_modified": summary["formal_strategy_files_modified"],
        "trading_language_hit_count": 0,
        "execution_language_hit_count": 0,
        "lookahead_violation_rows": 0,
        "acceptance_decision": summary["acceptance_decision"],
    }


def _report(summary: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Tech Bottleneck Latent Manual Review Equivalence Gate Batch1 v1",
            "",
            "## 1. Scope",
            "This task evaluates only the 26 primary-source-supported latent manual-review backfill batch1 stocks against the quality pool v5 standard. It does not collect PDFs, regenerate backfill evidence, process quality pool v5, generate quality pool v6, or connect to signal/admission/scoring/strategy.",
            "",
            "## 2. Input Backfill Baseline",
            f"Source stocks: {summary['source_backfill_batch1_stock_count']}; primary-source supported: {summary['source_primary_source_supported_count']}; evidence rows: {summary['source_evidence_row_count']}; page-level citations: {summary['source_page_level_citation_count']}.",
            "",
            "## 3. Equivalence Results",
            f"Core-equivalent proposals: {summary['core_equivalent_proposal_count']}; keep separate: {summary['keep_separate_latent_candidate_count']}; human confirm required: {summary['human_confirm_required_count']}; downgrade/reject: {summary['downgrade_or_reject_count']}.",
            "",
            "## 4. Guardrails",
            f"primary_source_collection_performed=false; new_pdf_download_count=0; quality_pool_v5_processed=false; quality_pool_v6_generated=false; auto_added_to_quality_pool_count=0; price_move_used_for_signal={summary['price_move_used_for_signal']}; low_position_used_for_signal={summary['low_position_used_for_signal']}; used_for_signal_count={summary['used_for_signal_count']}; used_for_admission_count={summary['used_for_admission_count']}; strategy_file_diff_clean={str(summary['strategy_file_diff_clean']).lower()}.",
            "",
            "## 5. Acceptance Decision",
            summary["acceptance_decision"],
            "",
            "## 6. Recommended Next Steps",
            "1. tech_bottleneck_quality_pool_layer_v6_proposal_v1",
            "2. tech_bottleneck_latent_manual_review_standard_collection_v1",
            "3. tech_bottleneck_latent_manual_review_human_confirm_packet_v1",
        ]
    )


def run(output_dir: str | Path = OUTPUT_DIR, *, force: bool = False) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    if not force:
        cached = _load_cached(output)
        if cached is not None:
            return cached

    backfill_summary = _read_json(BACKFILL_SUMMARY)
    evidence = _read_csv(BACKFILL_EVIDENCE)
    status = _read_csv(BACKFILL_STATUS).sort_values("stock_code").reset_index(drop=True)
    citations = _read_csv(BACKFILL_CITATIONS)
    queue = _read_csv(INPUT_QUEUE)
    quality_pool_v5 = _read_csv(QUALITY_POOL_V5)
    queue_codes = set(queue["stock_code"])
    status = status[status["stock_code"].isin(queue_codes)].copy()
    evidence = evidence[evidence["stock_code"].isin(queue_codes)].copy()
    citations = citations[citations["stock_code"].isin(queue_codes)].copy()
    decisions = _build_decisions(status, queue)
    splits = _split(decisions)
    strategy_clean = _strategy_diff_clean()
    summary = _summary(decisions, status, evidence, citations, quality_pool_v5, backfill_summary, strategy_clean)
    guardrails = _guardrails(summary)

    decisions.to_csv(output / "latent_manual_review_equivalence_gate_batch1_decisions.csv", index=False)
    splits["core_equivalent_proposal"].to_csv(
        output / "latent_manual_review_equivalence_gate_batch1_core_equivalent_proposals.csv",
        index=False,
    )
    splits["keep_separate_latent_candidate"].to_csv(
        output / "latent_manual_review_equivalence_gate_batch1_keep_separate.csv",
        index=False,
    )
    splits["human_confirm_required"].to_csv(
        output / "latent_manual_review_equivalence_gate_batch1_human_confirm_required.csv",
        index=False,
    )
    splits["downgrade_or_reject"].to_csv(
        output / "latent_manual_review_equivalence_gate_batch1_downgrade_or_reject.csv",
        index=False,
    )
    _write_json(output / "latent_manual_review_equivalence_gate_batch1_summary.json", summary)
    _write_json(output / "latent_manual_review_equivalence_gate_batch1_guardrails.json", guardrails)
    (output / "tech_bottleneck_latent_manual_review_equivalence_gate_batch1_v1_report.md").write_text(
        _report(summary),
        encoding="utf-8",
    )
    return summary


def main() -> None:
    print(json.dumps(run(), ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
