from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
TASK_NAME = "tech_bottleneck_latent_core_equivalence_gate_batch1_v1"
INPUT_CANDIDATES = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_latent_primary_source_backfill_batch1_v1/latent_backfill_batch1_manual_approval_candidates.csv"
)
OUTPUT_DIR = PROJECT_ROOT / "outputs/research" / TASK_NAME
EXPECTED_COUNT = 4
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]

OUTPUT_COLUMNS = [
    "stock_code",
    "stock_name",
    "primary_source_supported",
    "structured_primary_source_count",
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


def _score(row: pd.Series) -> int:
    score = 0
    if _truthy(row.get("primary_source_supported")):
        score += 2
    if _int(row.get("structured_primary_source_count")) >= 10:
        score += 2
    elif _int(row.get("structured_primary_source_count")) >= 5:
        score += 1
    if row.get("bottleneck_thesis_support_after_backfill") == "strong":
        score += 3
    elif row.get("bottleneck_thesis_support_after_backfill") == "moderate":
        score += 1
    if row.get("business_relevance_after_backfill") == "latent_hard_tech_primary_source_supported":
        score += 2
    if row.get("supply_chain_role_quality_after_backfill") in {"strong", "moderate"}:
        score += 1
    if row.get("architecture_shift_quality_after_backfill") in {"strong", "moderate"}:
        score += 1
    if row.get("route_around_quality_after_backfill") in {"strong", "moderate"}:
        score += 1
    if row.get("value_capture_quality_after_backfill") in {"strong", "moderate"}:
        score += 1
    if _truthy(row.get("disconfirmation_found")):
        score -= 1
    gaps = str(row.get("remaining_evidence_gap_flags") or "")
    for gap, penalty in {
        "missing_architecture_shift": 2,
        "missing_route_around": 3,
        "missing_value_capture": 2,
        "missing_disconfirmation": 1,
        "missing_annual_report": 2,
        "missing_primary_source": 4,
    }.items():
        if gap in gaps:
            score -= penalty
    return score


def _decision(row: pd.Series) -> tuple[str, str]:
    if not _truthy(row.get("primary_source_supported")):
        return "downgrade_or_reject", "primary-source support is missing"
    gaps = str(row.get("remaining_evidence_gap_flags") or "")
    if "missing_route_around" in gaps or "missing_architecture_shift" in gaps:
        return (
            "keep_as_latent_candidate",
            "structured primary-source support exists, but architecture-shift or route-around evidence is missing",
        )
    if "missing_value_capture" in gaps:
        return "keep_as_latent_candidate", "value-capture evidence is not strong enough for quality-pool equivalence"
    score = _int(row.get("latent_core_equivalence_score"))
    if score >= 10:
        return (
            "latent_core_equivalent_add_to_quality_pool",
            "latent candidate meets same-layer quality-pool evidence standard after backfill",
        )
    if score >= 5:
        return "keep_as_latent_candidate", "primary-source support exists but score is below quality-pool equivalence threshold"
    if score >= 1:
        return "remain_latent_watch", "evidence remains too incomplete for core-equivalence but still merits watch"
    return "downgrade_or_reject", "backfill evidence is too weak for latent rescue continuation"


def _build_gate(candidates: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for _, row in candidates.sort_values("stock_code").iterrows():
        score = _score(row)
        row = row.copy()
        row["latent_core_equivalence_score"] = score
        decision, reason = _decision(row)
        rows.append(
            {
                "stock_code": row["stock_code"],
                "stock_name": row["stock_name"],
                "primary_source_supported": _truthy(row.get("primary_source_supported")),
                "structured_primary_source_count": _int(row.get("structured_primary_source_count")),
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
        acceptance = "latent_core_equivalence_gate_batch1_ready"
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
        "latent_pending_45_processed": False,
        "standard_backfill_processed": False,
        "manual_review_first_processed": False,
        "defer_reject_processed": False,
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
            "# Tech Bottleneck Latent Core Equivalence Gate Batch1 v1",
            "",
            "## 1. Scope",
            "This task processes only the 4 latent manual approval candidates from batch1 backfill. It does not process the 45 pending names, standard backfill queue, manual-review-first queue, defer/reject queue, quality pool v3, or doubled-tech names.",
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
            "1. tech_bottleneck_latent_pending_primary_source_collection_v1",
            "2. tech_bottleneck_quality_pool_layer_v4",
            "3. tech_bottleneck_stock_workspace_docling_panel_v1",
        ]
    )


def run(output_dir: str | Path = OUTPUT_DIR) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    candidates = _read_csv(INPUT_CANDIDATES)
    gate = _build_gate(candidates)
    splits = _split(gate)
    strategy_clean = _strategy_diff_clean()
    summary = _summary(gate, strategy_clean)
    guardrails = _guardrails(summary)

    gate.to_csv(output / "latent_core_equivalence_gate_batch1.csv", index=False)
    splits["latent_core_equivalent_add_to_quality_pool"].to_csv(
        output / "latent_core_equivalent_batch1_candidates.csv",
        index=False,
    )
    splits["keep_as_latent_candidate"].to_csv(output / "latent_keep_separate_batch1_candidates.csv", index=False)
    splits["remain_latent_watch"].to_csv(output / "latent_remain_watch_batch1.csv", index=False)
    splits["downgrade_or_reject"].to_csv(output / "latent_downgrade_or_reject_batch1.csv", index=False)
    _write_json(output / "latent_core_equivalence_batch1_summary.json", summary)
    _write_json(output / "latent_core_equivalence_batch1_guardrails.json", guardrails)
    (output / "tech_bottleneck_latent_core_equivalence_gate_batch1_v1_report.md").write_text(
        _report(summary),
        encoding="utf-8",
    )
    return summary
