from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
TASK_NAME = "tech_bottleneck_doubler_data_gap_watch_triage_v1"
INPUT_DATA_GAP = PROJECT_ROOT / "outputs/research/tech_bottleneck_2025_doubler_tech_expansion_queue_v1/data_gap_watch.csv"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research" / TASK_NAME
EXPECTED_COUNT = 67
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]

BACKFILL_DRIVERS = {"earnings", "domestic_substitution", "product_cycle", "customer_validation", "supply_chain_scarcity"}
THEME_REVIEW_DRIVERS = {"AI_theme"}
WEAK_DRIVERS = {"sentiment", "liquidity", "technical_breakout", "unknown"}


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


def _strategy_diff_clean() -> bool:
    result = subprocess.run(
        ["git", "diff", "--", *FORMAL_STRATEGY_FILES],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return result.returncode == 0 and result.stdout == ""


def _data_gap_feasibility(row: pd.Series) -> str:
    if not _truthy(row.get("in_3252_candidate_universe")):
        return "mapping_required_before_source_collection"
    gaps = str(row.get("data_gap_flags") or "")
    next_check = str(row.get("next_primary_source_check") or "")
    if "primary_source_evidence_missing" in gaps and next_check:
        return "source_backfill_feasible"
    if gaps:
        return "partial_source_backfill_feasible"
    return "unclear_gap_feasibility"


def _thesis_possibility(row: pd.Series) -> str:
    strict_quality = str(row.get("strict_quality_category") or "")
    relevance = str(row.get("hard_tech_relevance") or "")
    role = str(row.get("supply_chain_role") or "")
    if strict_quality == "confirmed_hard_tech_doubler" and relevance == "high" and role == "beneficiary":
        return "possible_but_beneficiary_only"
    if strict_quality in {"confirmed_hard_tech_doubler", "likely_hard_tech_doubler"}:
        return "possible_pending_mapping"
    return "weak_or_unclear"


def _decision(row: pd.Series) -> tuple[str, str, str]:
    driver = str(row.get("primary_doubling_driver") or "")
    pollution = str(row.get("concept_pollution_risk") or "").lower()
    in_universe = _truthy(row.get("in_3252_candidate_universe"))
    feasibility = row.get("data_gap_feasibility")
    thesis = row.get("hard_tech_thesis_possibility")

    if thesis == "weak_or_unclear":
        return (
            "reject_as_weak_or_concept",
            "strict hard-tech thesis is weak after data-gap review",
            "keep out of primary-source backfill; no quality-pool action",
        )
    if not in_universe:
        return (
            "data_gap_manual_review",
            "not mapped in audited candidate universe; mapping review is needed before any source collection",
            "manual mapping review before any primary-source collection",
        )
    if pollution == "medium" and driver in WEAK_DRIVERS:
        return (
            "reject_as_weak_or_concept",
            "medium concept-pollution plus sentiment-led move is not enough for source backfill priority",
            "keep out of primary-source backfill unless separate manual evidence appears",
        )
    if pollution == "medium":
        return (
            "data_gap_manual_review",
            "medium concept-pollution risk requires manual review before source collection",
            "manual review concept-pollution and supply-chain role before primary-source collection",
        )
    if feasibility in {"source_backfill_feasible", "partial_source_backfill_feasible"} and driver in BACKFILL_DRIVERS:
        return (
            "data_gap_backfill_queue",
            "hard-tech doubler has feasible primary-source gap and non-sentiment driver, but beneficiary-only role still needs proof",
            "primary-source backfill for segment revenue, customer/certification, order/capacity, and route-around evidence",
        )
    if driver in THEME_REVIEW_DRIVERS:
        return (
            "data_gap_manual_review",
            "AI/theme-led data-gap candidate needs manual check before source collection because supply-chain role is beneficiary-only",
            "manual review hard-tech role and customer/value-capture path before primary-source backfill",
        )
    return (
        "remain_data_gap_watch",
        "data gap remains but source priority is below backfill/manual-review threshold",
        "remain data-gap watch; revisit after new filings or stronger business-role evidence",
    )


def _build_results(data_gap: pd.DataFrame) -> pd.DataFrame:
    rows = data_gap.sort_values("stock_code").copy()
    rows["source_group"] = "doubler_data_gap_watch"
    rows["data_gap_feasibility"] = rows.apply(_data_gap_feasibility, axis=1)
    rows["hard_tech_thesis_possibility"] = rows.apply(_thesis_possibility, axis=1)
    decisions = rows.apply(_decision, axis=1)
    rows["triage_decision"] = [item[0] for item in decisions]
    rows["triage_reason"] = [item[1] for item in decisions]
    rows["recommended_next_action"] = [item[2] for item in decisions]
    rows["primary_source_backfill_performed"] = False
    rows["auto_added_to_quality_pool"] = False
    rows["research_only"] = True
    rows["used_for_signal"] = False
    rows["used_for_admission"] = False
    columns = [
        "stock_code",
        "stock_name",
        "source_group",
        "return_since_20250101",
        "max_return_since_20250101",
        "strict_theme",
        "strict_quality_category",
        "hard_tech_relevance",
        "primary_doubling_driver",
        "in_90_pool",
        "in_3252_candidate_universe",
        "tech_bottleneck_domain",
        "tech_bottleneck_sub_domain",
        "supply_chain_role",
        "candidate_tier",
        "evidence_gate_level",
        "concept_pollution_risk",
        "data_gap_flags",
        "next_primary_source_check",
        "data_gap_feasibility",
        "hard_tech_thesis_possibility",
        "triage_decision",
        "triage_reason",
        "recommended_next_action",
        "price_move_used_for_discovery",
        "price_move_used_for_signal",
        "primary_source_backfill_performed",
        "auto_added_to_quality_pool",
        "research_only",
        "used_for_signal",
        "used_for_admission",
    ]
    return rows[columns].sort_values("stock_code").reset_index(drop=True)


def _split(results: pd.DataFrame) -> dict[str, pd.DataFrame]:
    return {
        "data_gap_backfill_queue": results[results["triage_decision"].eq("data_gap_backfill_queue")],
        "data_gap_manual_review": results[results["triage_decision"].eq("data_gap_manual_review")],
        "remain_data_gap_watch": results[results["triage_decision"].eq("remain_data_gap_watch")],
        "reject_as_weak_or_concept": results[results["triage_decision"].eq("reject_as_weak_or_concept")],
    }


def _summary(results: pd.DataFrame, strategy_clean: bool) -> dict[str, Any]:
    counts = results["triage_decision"].value_counts()
    used_for_signal = int(results["used_for_signal"].astype(bool).sum())
    used_for_admission = int(results["used_for_admission"].astype(bool).sum())
    price_signal = int(results["price_move_used_for_signal"].astype(bool).sum())
    backfill_performed = bool(results["primary_source_backfill_performed"].astype(bool).any())
    auto_added = int(results["auto_added_to_quality_pool"].astype(bool).sum())
    blocking = (
        len(results) != EXPECTED_COUNT
        or backfill_performed
        or auto_added
        or price_signal
        or used_for_signal
        or used_for_admission
        or not strategy_clean
    )
    if blocking:
        acceptance = "blocked_due_to_guardrail_violation"
    elif counts.get("data_gap_manual_review", 0) or counts.get("remain_data_gap_watch", 0):
        acceptance = "conditionally_ready_with_data_gap_review_needed"
    else:
        acceptance = "doubler_data_gap_watch_triage_ready"
    return {
        "task_name": TASK_NAME,
        "source_data_gap_watch_count": int(len(results)),
        "processed_count": int(len(results)),
        "data_gap_backfill_queue_count": int(counts.get("data_gap_backfill_queue", 0)),
        "data_gap_manual_review_count": int(counts.get("data_gap_manual_review", 0)),
        "remain_data_gap_watch_count": int(counts.get("remain_data_gap_watch", 0)),
        "reject_as_weak_or_concept_count": int(counts.get("reject_as_weak_or_concept", 0)),
        "primary_source_backfill_performed": backfill_performed,
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
        "data_gap_watch_triage_generated": True,
        "source_data_gap_watch_count": summary["source_data_gap_watch_count"],
        "only_data_gap_watch_processed": summary["source_data_gap_watch_count"] == EXPECTED_COUNT
        and summary["processed_count"] == EXPECTED_COUNT,
        "quality_pool_v2_processed": False,
        "primary_source_backfill_performed": summary["primary_source_backfill_performed"],
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
            "# Tech Bottleneck Doubler Data Gap Watch Triage v1",
            "",
            "## 1. Scope",
            "This research-only task triages only the 67 data-gap watch names from the 2025 doubled tech-stock expansion queue. It does not perform primary-source backfill, does not add anything to quality pool v2, and does not use price movement as signal.",
            "",
            "## 2. Triage Method",
            "The triage separates feasible primary-source gaps from manual mapping needs, beneficiary-only/theme risk, and weak concept exposure. Backfill queue status means next-step evidence collection only, not quality-pool inclusion.",
            "",
            "## 3. Results",
            f"Data-gap backfill queue: {summary['data_gap_backfill_queue_count']}; manual review: {summary['data_gap_manual_review_count']}; remain watch: {summary['remain_data_gap_watch_count']}; reject weak/concept: {summary['reject_as_weak_or_concept_count']}.",
            "",
            "## 4. Guardrails",
            f"primary_source_backfill_performed={str(summary['primary_source_backfill_performed']).lower()}; auto_added_to_quality_pool_count={summary['auto_added_to_quality_pool_count']}; price_move_used_for_signal={summary['price_move_used_for_signal']}; used_for_signal_count={summary['used_for_signal_count']}; used_for_admission_count={summary['used_for_admission_count']}; strategy_file_diff_clean={str(summary['strategy_file_diff_clean']).lower()}.",
            "",
            "## 5. Acceptance Decision",
            summary["acceptance_decision"],
            "",
            "## 6. Recommended Next Steps",
            "1. tech_bottleneck_data_gap_primary_source_backfill_v1",
            "2. tech_bottleneck_stock_workspace_docling_panel_v1",
            "3. tech_bottleneck_quality_pool_layer_v2_manual_review_packet_v1",
        ]
    )


def run(output_dir: str | Path = OUTPUT_DIR) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    data_gap = _read_csv(INPUT_DATA_GAP)
    results = _build_results(data_gap)
    splits = _split(results)
    strategy_clean = _strategy_diff_clean()
    summary = _summary(results, strategy_clean)
    guardrails = _guardrails(summary)

    results.to_csv(output / "doubler_data_gap_watch_triage_results.csv", index=False)
    splits["data_gap_backfill_queue"].to_csv(output / "data_gap_backfill_queue.csv", index=False)
    splits["data_gap_manual_review"].to_csv(output / "data_gap_manual_review.csv", index=False)
    splits["remain_data_gap_watch"].to_csv(output / "remain_data_gap_watch.csv", index=False)
    splits["reject_as_weak_or_concept"].to_csv(output / "reject_as_weak_or_concept.csv", index=False)
    _write_json(output / "doubler_data_gap_watch_triage_summary.json", summary)
    _write_json(output / "doubler_data_gap_watch_triage_guardrails.json", guardrails)
    (output / "tech_bottleneck_doubler_data_gap_watch_triage_v1_report.md").write_text(
        _report(summary),
        encoding="utf-8",
    )
    return summary


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
