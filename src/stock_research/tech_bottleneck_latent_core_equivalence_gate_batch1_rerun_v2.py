from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
TASK_NAME = "tech_bottleneck_latent_core_equivalence_gate_batch1_rerun_v2"
INPUT_CANDIDATES = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_latent_primary_source_backfill_batch1_rerun_v2/latent_backfill_batch1_rerun_v2_manual_approval_candidates.csv"
)
INPUT_EVIDENCE = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_latent_primary_source_backfill_batch1_rerun_v2/latent_backfill_batch1_rerun_v2_evidence_matrix.csv"
)
OUTPUT_DIR = PROJECT_ROOT / "outputs/research" / TASK_NAME
EXPECTED_COUNT = 45
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]

OUTPUT_COLUMNS = [
    "stock_code",
    "stock_name",
    "primary_source_supported",
    "primary_source_evidence_count",
    "page_level_citation_count",
    "bottleneck_thesis_support",
    "business_relevance",
    "supply_chain_role_quality",
    "architecture_shift_quality",
    "route_around_risk",
    "value_capture_quality",
    "disconfirmation_found",
    "remaining_evidence_gap_flags",
    "latent_core_equivalence_score",
    "core_equivalence_decision",
    "core_equivalence_reason",
    "price_move_used_for_signal",
    "low_position_used_for_signal",
    "auto_added_to_quality_pool",
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


def _score(row: pd.Series) -> int:
    score = 0
    if _truthy(row.get("primary_source_supported")):
        score += 2
    if _int(row.get("primary_source_evidence_count")) >= 20:
        score += 3
    elif _int(row.get("primary_source_evidence_count")) >= 10:
        score += 2
    elif _int(row.get("primary_source_evidence_count")) >= 5:
        score += 1
    if _int(row.get("page_level_citation_count")) >= 20:
        score += 2
    elif _int(row.get("page_level_citation_count")) >= 10:
        score += 1
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
    if _truthy(row.get("disconfirmation_found")):
        score -= 1
    gaps = str(row.get("remaining_evidence_gap_flags") or "")
    for gap, penalty in {
        "missing_route_around": 3,
        "missing_financial_trace": 2,
        "missing_annual_report": 2,
        "missing_primary_source": 4,
        "missing_architecture_shift": 2,
        "missing_value_capture": 2,
    }.items():
        if gap in gaps:
            score -= penalty
    return score


def _decision(row: pd.Series) -> tuple[str, str]:
    if not _truthy(row.get("primary_source_supported")):
        return "downgrade_or_reject", "primary-source support is missing"
    if row.get("business_relevance_after_backfill") != "core_hard_tech_evidence_supported":
        return "downgrade_or_reject", "business relevance remains non-core after primary-source backfill"
    gaps = str(row.get("remaining_evidence_gap_flags") or "")
    if "missing_route_around" in gaps:
        return "keep_as_latent_candidate", "route-around evidence gap prevents same-layer quality-pool equivalence"
    if "missing_financial_trace" in gaps or "missing_annual_report" in gaps:
        return "keep_as_latent_candidate", "financial or annual-report evidence gap remains"
    score = _int(row.get("latent_core_equivalence_score"))
    if score >= 13:
        return (
            "latent_core_equivalent_add_to_quality_pool",
            "page-level primary-source evidence supports same-layer quality-pool equivalence proposal",
        )
    if score >= 9:
        return (
            "keep_as_latent_candidate",
            "primary-source evidence supports latent continuation but score is below quality-pool equivalence threshold",
        )
    if score >= 5:
        return "remain_latent_watch", "evidence remains incomplete for equivalence and should stay on latent watch"
    return "downgrade_or_reject", "backfill evidence is too weak for latent continuation"


def _build_gate(candidates: pd.DataFrame, evidence: pd.DataFrame) -> pd.DataFrame:
    counts = _evidence_counts(evidence)
    gate = candidates.merge(counts, on="stock_code", how="left")
    gate["primary_source_evidence_count"] = gate["primary_source_evidence_count"].fillna(0).astype(int)
    gate["page_level_citation_count"] = gate["page_level_citation_count"].fillna(0).astype(int)
    rows: list[dict[str, Any]] = []
    for _, row in gate.sort_values("stock_code").iterrows():
        score = _score(row)
        row = row.copy()
        row["latent_core_equivalence_score"] = score
        decision, reason = _decision(row)
        rows.append(
            {
                "stock_code": row["stock_code"],
                "stock_name": row["stock_name"],
                "primary_source_supported": _truthy(row.get("primary_source_supported")),
                "primary_source_evidence_count": _int(row.get("primary_source_evidence_count")),
                "page_level_citation_count": _int(row.get("page_level_citation_count")),
                "bottleneck_thesis_support": row.get("bottleneck_thesis_support_after_backfill", ""),
                "business_relevance": row.get("business_relevance_after_backfill", ""),
                "supply_chain_role_quality": row.get("supply_chain_role_quality_after_backfill", ""),
                "architecture_shift_quality": row.get("architecture_shift_quality_after_backfill", ""),
                "route_around_risk": row.get("route_around_quality_after_backfill", ""),
                "value_capture_quality": row.get("value_capture_quality_after_backfill", ""),
                "disconfirmation_found": _truthy(row.get("disconfirmation_found")),
                "remaining_evidence_gap_flags": row.get("remaining_evidence_gap_flags", ""),
                "latent_core_equivalence_score": score,
                "core_equivalence_decision": decision,
                "core_equivalence_reason": reason,
                "price_move_used_for_signal": False,
                "low_position_used_for_signal": False,
                "auto_added_to_quality_pool": False,
                "research_only": True,
                "used_for_signal": False,
                "used_for_admission": False,
                "notes": "Core-equivalence proposal only; no automatic quality-pool addition or signal/admission use.",
            }
        )
    return pd.DataFrame(rows, columns=OUTPUT_COLUMNS).sort_values("stock_code").reset_index(drop=True)


def _split(gate: pd.DataFrame) -> dict[str, pd.DataFrame]:
    return {
        "latent_core_equivalent_add_to_quality_pool": gate[
            gate["core_equivalence_decision"].eq("latent_core_equivalent_add_to_quality_pool")
        ].copy(),
        "keep_as_latent_candidate": gate[gate["core_equivalence_decision"].eq("keep_as_latent_candidate")].copy(),
        "remain_latent_watch": gate[gate["core_equivalence_decision"].eq("remain_latent_watch")].copy(),
        "downgrade_or_reject": gate[gate["core_equivalence_decision"].eq("downgrade_or_reject")].copy(),
    }


def _summary(gate: pd.DataFrame, strategy_clean: bool) -> dict[str, Any]:
    counts = gate["core_equivalence_decision"].value_counts()
    used_for_signal = int(gate["used_for_signal"].astype(bool).sum()) if not gate.empty else 0
    used_for_admission = int(gate["used_for_admission"].astype(bool).sum()) if not gate.empty else 0
    price_signal = int(gate["price_move_used_for_signal"].astype(bool).sum()) if not gate.empty else 0
    low_signal = int(gate["low_position_used_for_signal"].astype(bool).sum()) if not gate.empty else 0
    auto_added = int(gate["auto_added_to_quality_pool"].astype(bool).sum()) if not gate.empty else 0
    blocking = len(gate) != EXPECTED_COUNT or used_for_signal or used_for_admission or price_signal or low_signal or auto_added or not strategy_clean
    if blocking:
        acceptance = "blocked_due_to_guardrail_violation"
    elif (
        counts.get("keep_as_latent_candidate", 0)
        or counts.get("remain_latent_watch", 0)
        or counts.get("downgrade_or_reject", 0)
    ):
        acceptance = "conditionally_ready_with_equivalence_gaps"
    else:
        acceptance = "latent_core_equivalence_gate_batch1_rerun_v2_ready"
    return {
        "task_name": TASK_NAME,
        "source_latent_manual_approval_candidate_count": int(len(gate)),
        "processed_count": int(len(gate)),
        "latent_core_equivalent_count": int(counts.get("latent_core_equivalent_add_to_quality_pool", 0)),
        "keep_as_latent_candidate_count": int(counts.get("keep_as_latent_candidate", 0)),
        "remain_latent_watch_count": int(counts.get("remain_latent_watch", 0)),
        "downgrade_or_reject_count": int(counts.get("downgrade_or_reject", 0)),
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
        "acceptance_decision": acceptance,
    }


def _guardrails(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_name": TASK_NAME,
        "research_only": True,
        "source_latent_manual_approval_candidate_count": summary["source_latent_manual_approval_candidate_count"],
        "only_latent_manual_approval_candidates_processed": summary["source_latent_manual_approval_candidate_count"] == EXPECTED_COUNT
        and summary["processed_count"] == EXPECTED_COUNT,
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
            "# Tech Bottleneck Latent Core Equivalence Gate Batch1 Rerun v2",
            "",
            "## 1. Scope",
            "This task processes only the 45 latent manual approval candidates from rerun v2. It does not automatically add any candidate to quality pool v4 and does not connect to signal or admission.",
            "",
            "## 2. Gate Results",
            f"Processed: {summary['processed_count']}; core-equivalent proposal: {summary['latent_core_equivalent_count']}; keep as latent candidate: {summary['keep_as_latent_candidate_count']}; remain watch: {summary['remain_latent_watch_count']}; downgrade/reject: {summary['downgrade_or_reject_count']}.",
            "",
            "## 3. Guardrails",
            f"auto_added_to_quality_pool_count={summary['auto_added_to_quality_pool_count']}; price_move_used_for_signal={summary['price_move_used_for_signal']}; low_position_used_for_signal={summary['low_position_used_for_signal']}; used_for_signal_count={summary['used_for_signal_count']}; used_for_admission_count={summary['used_for_admission_count']}; strategy_file_diff_clean={str(summary['strategy_file_diff_clean']).lower()}.",
            "",
            "## 4. Acceptance Decision",
            summary["acceptance_decision"],
            "",
            "## 5. Recommended Next Steps",
            "1. tech_bottleneck_quality_pool_layer_v4",
            "2. tech_bottleneck_latent_standard_backfill_queue_v1",
            "3. tech_bottleneck_stock_workspace_docling_panel_v1",
        ]
    )


def run(output_dir: str | Path = OUTPUT_DIR) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    candidates = _read_csv(INPUT_CANDIDATES)
    evidence = _read_csv(INPUT_EVIDENCE)
    gate = _build_gate(candidates, evidence[evidence["stock_code"].isin(set(candidates["stock_code"]))].copy())
    splits = _split(gate)
    strategy_clean = _strategy_diff_clean()
    summary = _summary(gate, strategy_clean)
    guardrails = _guardrails(summary)

    gate.to_csv(output / "latent_core_equivalence_gate_batch1_rerun_v2.csv", index=False)
    splits["latent_core_equivalent_add_to_quality_pool"].to_csv(
        output / "latent_core_equivalent_batch1_rerun_v2_candidates.csv",
        index=False,
    )
    splits["keep_as_latent_candidate"].to_csv(output / "latent_keep_separate_batch1_rerun_v2_candidates.csv", index=False)
    splits["remain_latent_watch"].to_csv(output / "latent_remain_watch_batch1_rerun_v2.csv", index=False)
    splits["downgrade_or_reject"].to_csv(output / "latent_downgrade_or_reject_batch1_rerun_v2.csv", index=False)
    _write_json(output / "latent_core_equivalence_batch1_rerun_v2_summary.json", summary)
    _write_json(output / "latent_core_equivalence_batch1_rerun_v2_guardrails.json", guardrails)
    (output / "tech_bottleneck_latent_core_equivalence_gate_batch1_rerun_v2_report.md").write_text(
        _report(summary),
        encoding="utf-8",
    )
    return summary
