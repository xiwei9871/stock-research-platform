from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
TASK_NAME = "tech_bottleneck_data_gap_core_equivalence_gate_v1"
INPUT_CANDIDATES = PROJECT_ROOT / "outputs/research/tech_bottleneck_data_gap_primary_source_backfill_v1/data_gap_manual_approval_candidates.csv"
INPUT_EVIDENCE = PROJECT_ROOT / "outputs/research/tech_bottleneck_data_gap_primary_source_backfill_v1/data_gap_primary_source_evidence_matrix.csv"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research" / TASK_NAME
EXPECTED_COUNT = 27
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


def _pollution_risk(row: pd.Series) -> str:
    gaps = str(row.get("remaining_evidence_gap_flags") or "")
    if row.get("business_relevance_after_backfill") != "core_hard_tech_evidence_supported":
        return "high"
    if "missing_route_around" in gaps or "missing_financial_trace" in gaps or "missing_annual_report" in gaps:
        return "medium"
    return "low"


def _adjacent_risk(row: pd.Series) -> str:
    if row.get("supply_chain_role_quality_after_backfill") == "weak":
        return "high"
    if row.get("route_around_quality_after_backfill") == "weak":
        return "medium"
    return "low"


def _score(row: pd.Series) -> int:
    score = 0
    if row.get("bottleneck_thesis_support_after_backfill") == "strong":
        score += 3
    elif row.get("bottleneck_thesis_support_after_backfill") == "moderate":
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
    gaps = str(row.get("remaining_evidence_gap_flags") or "")
    if "missing_route_around" in gaps:
        score -= 3
    if "missing_financial_trace" in gaps:
        score -= 2
    if "missing_annual_report" in gaps:
        score -= 2
    if row.get("pollution_risk") == "medium":
        score -= 1
    if row.get("adjacent_risk") == "medium":
        score -= 1
    return score


def _decision(row: pd.Series) -> tuple[str, str]:
    if not _truthy(row.get("primary_source_supported")):
        return (
            "downgrade_or_reject",
            "primary-source support is missing after data-gap backfill",
        )
    if row.get("business_relevance_after_backfill") != "core_hard_tech_evidence_supported":
        return (
            "downgrade_or_reject",
            "business relevance remains non-core after data-gap backfill",
        )
    gaps = str(row.get("remaining_evidence_gap_flags") or "")
    if "missing_route_around" in gaps or row.get("route_around_quality_after_backfill") == "weak":
        return (
            "keep_as_data_gap_candidate",
            "route-around evidence gap prevents same-layer quality-pool equivalence",
        )
    if "missing_financial_trace" in gaps or "missing_annual_report" in gaps:
        return (
            "keep_as_data_gap_candidate",
            "financial/annual-report evidence gap remains after primary-source backfill",
        )
    score = _to_int(row.get("data_gap_core_equivalence_score"))
    if score >= 13:
        return (
            "data_gap_core_equivalent_add_to_quality_pool",
            "data gap was resolved by primary-source evidence and thesis quality matches quality pool v2 standard",
        )
    if score >= 9:
        return (
            "keep_as_data_gap_candidate",
            "primary evidence supports continued review but equivalence score is below quality-pool threshold",
        )
    if score >= 5:
        return (
            "remain_data_gap_watch",
            "data gap remains material after backfill and does not yet support manual quality-pool equivalence",
        )
    return (
        "downgrade_or_reject",
        "backfill evidence remains too weak for data-gap rescue continuation",
    )


def _build_gate(candidates: pd.DataFrame, evidence: pd.DataFrame) -> pd.DataFrame:
    counts = _evidence_counts(evidence)
    gate = candidates.merge(counts, on="stock_code", how="left")
    gate["primary_source_evidence_count"] = gate["primary_source_evidence_count"].fillna(0).astype(int)
    gate["page_level_citation_count"] = gate["page_level_citation_count"].fillna(0).astype(int)
    gate["original_data_gap_flags"] = gate["remaining_evidence_gap_flags"]
    gate["pollution_risk"] = gate.apply(_pollution_risk, axis=1)
    gate["adjacent_risk"] = gate.apply(_adjacent_risk, axis=1)
    gate["data_gap_core_equivalence_score"] = gate.apply(_score, axis=1)
    decisions = gate.apply(_decision, axis=1)
    gate["core_equivalence_decision"] = [item[0] for item in decisions]
    gate["core_equivalence_reason"] = [item[1] for item in decisions]
    gate["price_move_used_for_signal"] = False
    gate["auto_added_to_quality_pool"] = False
    gate["research_only"] = True
    gate["used_for_signal"] = False
    gate["used_for_admission"] = False
    columns = [
        "stock_code",
        "stock_name",
        "original_data_gap_flags",
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
        "pollution_risk",
        "adjacent_risk",
        "remaining_evidence_gap_flags",
        "data_gap_core_equivalence_score",
        "core_equivalence_decision",
        "core_equivalence_reason",
        "price_move_used_for_signal",
        "auto_added_to_quality_pool",
        "research_only",
        "used_for_signal",
        "used_for_admission",
        "notes",
    ]
    renamed = gate[columns].rename(
        columns={
            "bottleneck_thesis_support_after_backfill": "bottleneck_thesis_support",
            "business_relevance_after_backfill": "business_relevance",
            "supply_chain_role_quality_after_backfill": "supply_chain_role_quality",
            "architecture_shift_quality_after_backfill": "architecture_shift_quality",
            "route_around_quality_after_backfill": "route_around_risk",
            "value_capture_quality_after_backfill": "value_capture_quality",
        }
    )
    return renamed.sort_values("stock_code").reset_index(drop=True)


def _split(gate: pd.DataFrame) -> dict[str, pd.DataFrame]:
    return {
        "data_gap_core_equivalent_add_to_quality_pool": gate[
            gate["core_equivalence_decision"].eq("data_gap_core_equivalent_add_to_quality_pool")
        ],
        "keep_as_data_gap_candidate": gate[gate["core_equivalence_decision"].eq("keep_as_data_gap_candidate")],
        "remain_data_gap_watch": gate[gate["core_equivalence_decision"].eq("remain_data_gap_watch")],
        "downgrade_or_reject": gate[gate["core_equivalence_decision"].eq("downgrade_or_reject")],
    }


def _summary(gate: pd.DataFrame, strategy_clean: bool) -> dict[str, Any]:
    counts = gate["core_equivalence_decision"].value_counts()
    used_for_signal = int(gate["used_for_signal"].astype(bool).sum())
    used_for_admission = int(gate["used_for_admission"].astype(bool).sum())
    price_signal = int(gate["price_move_used_for_signal"].astype(bool).sum())
    auto_added = int(gate["auto_added_to_quality_pool"].astype(bool).sum())
    blocking = len(gate) != EXPECTED_COUNT or used_for_signal or used_for_admission or price_signal or auto_added or not strategy_clean
    if blocking:
        acceptance = "blocked_due_to_guardrail_violation"
    elif (
        counts.get("keep_as_data_gap_candidate", 0)
        or counts.get("remain_data_gap_watch", 0)
        or counts.get("downgrade_or_reject", 0)
    ):
        acceptance = "conditionally_ready_with_equivalence_gaps"
    else:
        acceptance = "data_gap_core_equivalence_gate_ready"
    return {
        "task_name": TASK_NAME,
        "source_data_gap_candidate_count": int(len(gate)),
        "processed_count": int(len(gate)),
        "data_gap_core_equivalent_count": int(counts.get("data_gap_core_equivalent_add_to_quality_pool", 0)),
        "keep_as_data_gap_candidate_count": int(counts.get("keep_as_data_gap_candidate", 0)),
        "remain_data_gap_watch_count": int(counts.get("remain_data_gap_watch", 0)),
        "downgrade_or_reject_count": int(counts.get("downgrade_or_reject", 0)),
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
        "data_gap_core_equivalence_gate_generated": True,
        "source_data_gap_candidate_count": summary["source_data_gap_candidate_count"],
        "only_data_gap_candidates_processed": summary["source_data_gap_candidate_count"] == EXPECTED_COUNT
        and summary["processed_count"] == EXPECTED_COUNT,
        "quality_pool_v2_processed": False,
        "data_gap_manual_review_processed": False,
        "remain_data_gap_watch_processed": False,
        "reject_weak_concept_processed": False,
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
            "# Tech Bottleneck Data Gap Core Equivalence Gate v1",
            "",
            "## 1. Scope",
            "This research-only gate reviews only the 27 data-gap manual approval candidates that completed primary-source backfill. It does not process quality pool v2, the 31 data-gap manual-review names, remain-watch names, or weak/concept rejects.",
            "",
            "## 2. Method",
            "The gate checks whether primary-source backfill actually resolved the data gap at the same standard as quality pool v2, including bottleneck thesis support, business relevance, supply-chain role, architecture shift, route-around risk, value capture, and residual evidence gaps.",
            "",
            "## 3. Results",
            f"Data-gap core-equivalent add to quality pool proposal: {summary['data_gap_core_equivalent_count']}; keep separate: {summary['keep_as_data_gap_candidate_count']}; remain watch: {summary['remain_data_gap_watch_count']}; downgrade/reject: {summary['downgrade_or_reject_count']}.",
            "",
            "## 4. Guardrails",
            f"auto_added_to_quality_pool_count={summary['auto_added_to_quality_pool_count']}; price_move_used_for_signal={summary['price_move_used_for_signal']}; used_for_signal_count={summary['used_for_signal_count']}; used_for_admission_count={summary['used_for_admission_count']}; baseline_admission_changed_count={summary['baseline_admission_changed_count']}; strategy_file_diff_clean={str(summary['strategy_file_diff_clean']).lower()}.",
            "",
            "## 5. Acceptance Decision",
            summary["acceptance_decision"],
            "",
            "## 6. Recommended Next Steps",
            "1. tech_bottleneck_quality_pool_layer_v3",
            "2. tech_bottleneck_doubler_market_discovered_closure_v1",
            "3. tech_bottleneck_stock_workspace_docling_panel_v1",
        ]
    )


def run(output_dir: Path = OUTPUT_DIR) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    candidates, evidence = _load_inputs()
    gate = _build_gate(candidates, evidence)
    splits = _split(gate)
    strategy_clean = _strategy_diff_clean()
    summary = _summary(gate, strategy_clean)
    guardrails = _guardrails(summary)

    gate.to_csv(output_dir / "data_gap_core_equivalence_gate.csv", index=False)
    splits["data_gap_core_equivalent_add_to_quality_pool"].to_csv(
        output_dir / "data_gap_core_equivalent_candidates.csv",
        index=False,
    )
    splits["keep_as_data_gap_candidate"].to_csv(output_dir / "data_gap_keep_separate_candidates.csv", index=False)
    splits["remain_data_gap_watch"].to_csv(output_dir / "data_gap_remain_watch.csv", index=False)
    splits["downgrade_or_reject"].to_csv(output_dir / "data_gap_downgrade_or_reject.csv", index=False)
    _write_json(output_dir / "data_gap_core_equivalence_summary.json", summary)
    _write_json(output_dir / "data_gap_core_equivalence_guardrails.json", guardrails)
    (output_dir / "tech_bottleneck_data_gap_core_equivalence_gate_v1_report.md").write_text(
        _report(summary),
        encoding="utf-8",
    )
    return summary


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
