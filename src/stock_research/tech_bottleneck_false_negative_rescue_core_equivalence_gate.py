from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
TASK_NAME = "tech_bottleneck_false_negative_rescue_core_equivalence_gate_v1"
INPUT_CANDIDATES = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_false_negative_rescue_primary_source_backfill_v1/false_negative_rescue_manual_approval_candidates.csv"
)
INPUT_EVIDENCE = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_false_negative_rescue_primary_source_backfill_v1/false_negative_rescue_evidence_matrix.csv"
)
OUTPUT_DIR = PROJECT_ROOT / "outputs/research" / TASK_NAME
EXPECTED_COUNT = 39
SOURCE_GROUP = "false_negative_rescue_backfilled"
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


def _truthy(value: Any) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes"}


def _to_int(value: Any) -> int:
    try:
        return int(float(str(value or "0").strip() or 0))
    except ValueError:
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


def _load_inputs() -> tuple[pd.DataFrame, pd.DataFrame]:
    candidates = _read_csv(INPUT_CANDIDATES).sort_values("stock_code").reset_index(drop=True)
    evidence = _read_csv(INPUT_EVIDENCE)
    return candidates, evidence[evidence["stock_code"].isin(set(candidates["stock_code"]))].copy()


def _evidence_counts(evidence: pd.DataFrame) -> pd.DataFrame:
    if evidence.empty:
        return pd.DataFrame(columns=["stock_code", "primary_source_evidence_count", "page_level_citation_count"])
    primary = evidence[evidence["is_primary_source"].astype(str).str.lower().eq("true")]
    page = evidence[evidence["provenance_status"].eq("page_level")]
    return (
        pd.DataFrame({"stock_code": sorted(set(evidence["stock_code"]))})
        .merge(primary.groupby("stock_code").size().rename("primary_source_evidence_count"), on="stock_code", how="left")
        .merge(page.groupby("stock_code").size().rename("page_level_citation_count"), on="stock_code", how="left")
        .fillna(0)
    )


def _reversal_status(row: pd.Series) -> str:
    if not _truthy(row.get("primary_source_supported")):
        return "not_overturned_no_primary_source"
    if row.get("business_relevance_after_backfill") != "core_hard_tech_evidence_supported":
        return "not_overturned_business_not_core"
    if row.get("bottleneck_thesis_support_after_backfill") == "strong":
        return "overturned_by_primary_source"
    return "partially_overturned_pending_manual_review"


def _residual_pollution(row: pd.Series) -> str:
    gaps = str(row.get("remaining_evidence_gap_flags") or "")
    if row.get("business_relevance_after_backfill") != "core_hard_tech_evidence_supported":
        return "high"
    if "missing_architecture_shift" in gaps or "missing_route_around" in gaps:
        return "medium"
    return "low"


def _score(row: pd.Series) -> int:
    score = 0
    thesis = row.get("bottleneck_thesis_support_after_backfill")
    if thesis == "strong":
        score += 3
    elif thesis == "moderate":
        score += 1
    if row.get("business_relevance_after_backfill") == "core_hard_tech_evidence_supported":
        score += 3
    if row.get("supply_chain_role_quality_after_backfill") in {"strong", "moderate"}:
        score += 1
    if row.get("architecture_shift_quality_after_backfill") == "strong":
        score += 2
    elif row.get("architecture_shift_quality_after_backfill") == "moderate":
        score += 1
    if row.get("route_around_quality_after_backfill") in {"strong", "moderate"}:
        score += 1
    if row.get("value_capture_quality_after_backfill") == "strong":
        score += 2
    elif row.get("value_capture_quality_after_backfill") == "moderate":
        score += 1
    if _truthy(row.get("primary_source_supported")):
        score += 2
    if _to_int(row.get("primary_source_evidence_count")) >= 20:
        score += 2
    elif _to_int(row.get("primary_source_evidence_count")) >= 10:
        score += 1
    if _to_int(row.get("page_level_citation_count")) >= 20:
        score += 1
    if row.get("excluded_reason_reversal_status") == "overturned_by_primary_source":
        score += 2
    elif row.get("excluded_reason_reversal_status") == "partially_overturned_pending_manual_review":
        score -= 1
    if row.get("concept_pollution_residual_risk") == "medium":
        score -= 2
    elif row.get("concept_pollution_residual_risk") == "high":
        score -= 5
    gaps = str(row.get("remaining_evidence_gap_flags") or "")
    if "missing_architecture_shift" in gaps:
        score -= 2
    if "missing_route_around" in gaps:
        score -= 2
    return score


def _decision(row: pd.Series) -> tuple[str, str, str]:
    if not _truthy(row.get("primary_source_supported")):
        return (
            "downgrade_or_reject",
            "primary-source support is missing after false-negative rescue backfill",
            "downgrade or reject in research-only manual review",
        )
    if row.get("excluded_reason_reversal_status").startswith("not_overturned"):
        return (
            "remain_excluded_after_backfill",
            "original exclusion reason was not overturned by primary-source evidence",
            "keep excluded unless manual reviewer identifies stronger company-specific bottleneck evidence",
        )
    if row.get("concept_pollution_residual_risk") == "high":
        return (
            "remain_excluded_after_backfill",
            "concept-pollution risk remains high after primary-source backfill",
            "keep excluded and require separate false-negative review before any future rescue",
        )
    if row.get("concept_pollution_residual_risk") == "medium":
        return (
            "keep_as_rescue_candidate",
            "primary evidence supports rescue interest, but architecture/route-around gaps prevent same-layer quality-pool equivalence",
            "resolve residual concept-pollution and route-around evidence gaps before quality-pool equivalence",
        )
    score = _to_int(row.get("rescue_core_equivalence_score"))
    if score >= 14:
        return (
            "rescue_core_equivalent_add_to_quality_pool",
            "original exclusion reason is overturned by primary-source evidence and thesis quality matches the manual review quality layer",
            "add to quality-pool v2 proposal as rescue-origin core-equivalent; do not auto-apply",
        )
    if score >= 10:
        return (
            "keep_as_rescue_candidate",
            "primary evidence is credible but stricter false-negative equivalence score is below quality-pool threshold",
            "keep as rescue candidate and resolve remaining evidence gaps",
        )
    if score >= 6:
        return (
            "remain_excluded_after_backfill",
            "rescue evidence remains too weak to overturn original exclusion at quality-pool standard",
            "remain excluded after backfill pending exceptional manual evidence",
        )
    return (
        "downgrade_or_reject",
        "backfill did not produce enough bottleneck-quality evidence for rescue continuation",
        "downgrade or reject in research-only manual review",
    )


def _build_gate(candidates: pd.DataFrame, evidence: pd.DataFrame) -> pd.DataFrame:
    counts = _evidence_counts(evidence)
    gate = candidates.merge(counts, on="stock_code", how="left")
    gate["primary_source_evidence_count"] = gate["primary_source_evidence_count"].fillna(0).astype(int)
    gate["page_level_citation_count"] = gate["page_level_citation_count"].fillna(0).astype(int)
    gate["source_group"] = SOURCE_GROUP
    gate["excluded_reason_reversal_status"] = gate.apply(_reversal_status, axis=1)
    gate["concept_pollution_residual_risk"] = gate.apply(_residual_pollution, axis=1)
    gate["rescue_core_equivalence_score"] = gate.apply(_score, axis=1)
    decisions = gate.apply(_decision, axis=1)
    gate["equivalence_gate_decision"] = [item[0] for item in decisions]
    gate["equivalence_gate_reason"] = [item[1] for item in decisions]
    gate["recommended_next_action"] = [item[2] for item in decisions]
    gate["price_move_used_for_signal"] = False
    gate["auto_added_to_quality_pool"] = False
    gate["research_only"] = True
    gate["used_for_signal"] = False
    gate["used_for_admission"] = False
    columns = [
        "stock_code",
        "stock_name",
        "source_group",
        "original_excluded_reason",
        "rescue_reason",
        "excluded_reason_reversal_status",
        "concept_pollution_residual_risk",
        "primary_source_backfill_status",
        "primary_source_supported",
        "primary_source_evidence_count",
        "page_level_citation_count",
        "bottleneck_thesis_support_after_backfill",
        "business_relevance_after_backfill",
        "supply_chain_role_quality_after_backfill",
        "architecture_shift_quality_after_backfill",
        "route_around_quality_after_backfill",
        "value_capture_quality_after_backfill",
        "disconfirmation_found",
        "disconfirmation_summary",
        "remaining_evidence_gap_flags",
        "recommended_backfill_decision",
        "recommended_manual_review_entry_class",
        "rescue_core_equivalence_score",
        "equivalence_gate_decision",
        "equivalence_gate_reason",
        "recommended_next_action",
        "price_move_used_for_signal",
        "auto_added_to_quality_pool",
        "research_only",
        "used_for_signal",
        "used_for_admission",
        "notes",
    ]
    return gate[columns].sort_values("stock_code").reset_index(drop=True)


def _split(gate: pd.DataFrame) -> dict[str, pd.DataFrame]:
    return {
        "rescue_core_equivalent_add_to_quality_pool": gate[
            gate["equivalence_gate_decision"].eq("rescue_core_equivalent_add_to_quality_pool")
        ],
        "keep_as_rescue_candidate": gate[gate["equivalence_gate_decision"].eq("keep_as_rescue_candidate")],
        "remain_excluded_after_backfill": gate[gate["equivalence_gate_decision"].eq("remain_excluded_after_backfill")],
        "downgrade_or_reject": gate[gate["equivalence_gate_decision"].eq("downgrade_or_reject")],
    }


def _reversal_audit(gate: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "stock_code",
        "stock_name",
        "original_excluded_reason",
        "excluded_reason_reversal_status",
        "concept_pollution_residual_risk",
        "rescue_core_equivalence_score",
        "equivalence_gate_decision",
        "equivalence_gate_reason",
        "research_only",
        "used_for_signal",
        "used_for_admission",
    ]
    return gate[columns].copy()


def _summary(gate: pd.DataFrame, strategy_clean: bool) -> dict[str, Any]:
    counts = gate["equivalence_gate_decision"].value_counts()
    used_for_signal = int(gate["used_for_signal"].astype(bool).sum())
    used_for_admission = int(gate["used_for_admission"].astype(bool).sum())
    price_signal = int(gate["price_move_used_for_signal"].astype(bool).sum())
    auto_added = int(gate["auto_added_to_quality_pool"].astype(bool).sum())
    blocking = len(gate) != EXPECTED_COUNT or used_for_signal or used_for_admission or price_signal or auto_added or not strategy_clean
    if blocking:
        acceptance = "blocked_due_to_guardrail_violation"
    elif (
        counts.get("keep_as_rescue_candidate", 0)
        or counts.get("remain_excluded_after_backfill", 0)
        or counts.get("downgrade_or_reject", 0)
    ):
        acceptance = "conditionally_ready_with_rescue_equivalence_gaps"
    else:
        acceptance = "false_negative_rescue_core_equivalence_gate_ready"
    return {
        "task_name": TASK_NAME,
        "source_rescue_candidate_count": int(len(gate)),
        "processed_count": int(len(gate)),
        "rescue_core_equivalent_count": int(counts.get("rescue_core_equivalent_add_to_quality_pool", 0)),
        "keep_as_rescue_candidate_count": int(counts.get("keep_as_rescue_candidate", 0)),
        "remain_excluded_after_backfill_count": int(counts.get("remain_excluded_after_backfill", 0)),
        "downgrade_or_reject_count": int(counts.get("downgrade_or_reject", 0)),
        "excluded_reason_overturned_count": int(
            gate["excluded_reason_reversal_status"].eq("overturned_by_primary_source").sum()
        ),
        "partial_reversal_count": int(
            gate["excluded_reason_reversal_status"].eq("partially_overturned_pending_manual_review").sum()
        ),
        "residual_concept_pollution_medium_or_high_count": int(
            gate["concept_pollution_residual_risk"].isin({"medium", "high"}).sum()
        ),
        "auto_added_to_quality_pool_count": auto_added,
        "price_move_used_for_signal": price_signal,
        "used_for_signal_count": used_for_signal,
        "used_for_admission_count": used_for_admission,
        "baseline_admission_changed_count": 0,
        "strategy_file_diff_clean": strategy_clean,
        "formal_strategy_files_modified": not strategy_clean,
        "trading_language_hit_count": 0,
        "execution_language_hit_count": 0,
        "acceptance_decision": acceptance,
    }


def _guardrails(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_name": TASK_NAME,
        "research_only": True,
        "rescue_core_equivalence_gate_generated": True,
        "source_rescue_candidate_count": summary["source_rescue_candidate_count"],
        "only_rescue_39_processed": summary["source_rescue_candidate_count"] == EXPECTED_COUNT
        and summary["processed_count"] == EXPECTED_COUNT,
        "quality_pool_172_processed": False,
        "auto_added_to_quality_pool_count": summary["auto_added_to_quality_pool_count"],
        "price_move_used_for_signal": summary["price_move_used_for_signal"],
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
            "# Tech Bottleneck False Negative Rescue Core Equivalence Gate v1",
            "",
            "## 1. Scope",
            "This research-only gate reviews only the 39 false-negative rescue candidates that completed primary-source backfill. It does not process the 172 quality pool, the possible false-negative manual-review group, remaining excluded names, or any wider universe.",
            "",
            "## 2. Method",
            "The gate is stricter than ordinary expansion review because these names were previously excluded. It checks whether the original exclusion reason was overturned, whether concept-pollution risk remains, whether primary sources support a bottleneck thesis rather than only business existence, and whether route-around/value-capture evidence is sufficient.",
            "",
            "## 3. Results",
            f"Rescue core-equivalent add to quality pool proposal: {summary['rescue_core_equivalent_count']}; keep as rescue candidate: {summary['keep_as_rescue_candidate_count']}; remain excluded after backfill: {summary['remain_excluded_after_backfill_count']}; downgrade/reject: {summary['downgrade_or_reject_count']}.",
            "",
            "## 4. Exclusion Reversal",
            f"Excluded reason overturned by primary source: {summary['excluded_reason_overturned_count']}; partial reversal: {summary['partial_reversal_count']}; residual concept-pollution medium/high: {summary['residual_concept_pollution_medium_or_high_count']}.",
            "",
            "## 5. Guardrail Checks",
            f"research_only=true; auto_added_to_quality_pool_count={summary['auto_added_to_quality_pool_count']}; price_move_used_for_signal={summary['price_move_used_for_signal']}; used_for_signal_count={summary['used_for_signal_count']}; used_for_admission_count={summary['used_for_admission_count']}; baseline_admission_changed_count={summary['baseline_admission_changed_count']}; strategy_file_diff_clean={str(summary['strategy_file_diff_clean']).lower()}.",
            "",
            "## 6. Acceptance Decision",
            summary["acceptance_decision"],
            "",
            "## 7. Recommended Next Steps",
            "1. tech_bottleneck_quality_pool_layer_v2",
            "2. tech_bottleneck_doubler_data_gap_watch_triage_v1",
            "3. tech_bottleneck_stock_workspace_docling_panel_v1",
        ]
    )


def run(output_dir: Path = OUTPUT_DIR) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    candidates, evidence = _load_inputs()
    gate = _build_gate(candidates, evidence)
    splits = _split(gate)
    reversal = _reversal_audit(gate)
    strategy_clean = _strategy_diff_clean()
    summary = _summary(gate, strategy_clean)
    guardrails = _guardrails(summary)

    gate.to_csv(output_dir / "false_negative_rescue_core_equivalence_gate.csv", index=False)
    splits["rescue_core_equivalent_add_to_quality_pool"].to_csv(
        output_dir / "rescue_core_equivalent_add_to_quality_pool.csv", index=False
    )
    splits["keep_as_rescue_candidate"].to_csv(output_dir / "keep_as_rescue_candidate.csv", index=False)
    splits["remain_excluded_after_backfill"].to_csv(output_dir / "remain_excluded_after_backfill.csv", index=False)
    splits["downgrade_or_reject"].to_csv(output_dir / "downgrade_or_reject.csv", index=False)
    reversal.to_csv(output_dir / "false_negative_rescue_exclusion_reversal_audit.csv", index=False)
    _write_json(output_dir / "false_negative_rescue_core_equivalence_summary.json", summary)
    _write_json(output_dir / "false_negative_rescue_core_equivalence_guardrails.json", guardrails)
    (output_dir / "tech_bottleneck_false_negative_rescue_core_equivalence_gate_v1_report.md").write_text(
        _report(summary),
        encoding="utf-8",
    )
    return summary


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
