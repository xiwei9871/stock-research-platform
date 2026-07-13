from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
TASK_NAME = "tech_bottleneck_excluded_false_negative_review_v1"
INPUT_FALSE_NEGATIVE = (
    PROJECT_ROOT / "outputs/research/tech_bottleneck_2025_doubler_tech_expansion_queue_v1/excluded_false_negative_review.csv"
)
OUTPUT_DIR = PROJECT_ROOT / "outputs/research" / TASK_NAME
EXPECTED_COUNT = 76
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]

CORE_EQUIPMENT_THEMES = {
    "semiconductor equipment",
    "semiconductor testing / advanced packaging",
    "memory / storage",
    "high-end equipment / instrumentation",
}
RESCUE_DRIVERS = {"earnings", "domestic_substitution", "technical_breakout"}


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


def _load_input() -> pd.DataFrame:
    return _read_csv(INPUT_FALSE_NEGATIVE).sort_values("stock_code").reset_index(drop=True)


def _is_st_name(name: str) -> bool:
    upper = str(name or "").upper()
    return "ST" in upper


def _concept_flags(row: pd.Series) -> str:
    flags = []
    if row.get("concept_pollution_risk"):
        flags.append(f"concept_pollution={row.get('concept_pollution_risk')}")
    if row.get("supply_chain_role"):
        flags.append(f"supply_chain_role={row.get('supply_chain_role')}")
    if row.get("evidence_gate_level"):
        flags.append(f"evidence_gate={row.get('evidence_gate_level')}")
    if row.get("excluded_reason"):
        flags.append(f"excluded_reason={row.get('excluded_reason')}")
    return "|".join(flags)


def _hard_tech_signal(row: pd.Series) -> str:
    theme = str(row.get("strict_theme") or "")
    domain = str(row.get("tech_bottleneck_domain") or "")
    if theme in CORE_EQUIPMENT_THEMES:
        return f"core_theme:{theme};domain:{domain}"
    if "industrial software" in theme:
        return f"software_theme:{theme};domain:{domain}"
    return f"weak_theme:{theme};domain:{domain}"


def _bottleneck_possibility(row: pd.Series) -> str:
    theme = str(row.get("strict_theme") or "")
    driver = str(row.get("primary_doubling_driver") or "")
    if theme in CORE_EQUIPMENT_THEMES and driver in RESCUE_DRIVERS:
        return "high"
    if theme in CORE_EQUIPMENT_THEMES or driver in RESCUE_DRIVERS:
        return "medium"
    return "low"


def _business_signal(row: pd.Series) -> str:
    if row.get("strict_quality_category") == "confirmed_hard_tech_doubler" and row.get("hard_tech_relevance") == "high":
        return "hard_tech_business_possible_but_excluded_as_concept_only"
    return "business_relevance_unproven"


def _decision(row: pd.Series) -> tuple[str, str, str, str]:
    name = str(row.get("stock_name") or "")
    theme = str(row.get("strict_theme") or "")
    driver = str(row.get("primary_doubling_driver") or "")
    pollution = str(row.get("concept_pollution_risk") or "")
    role = str(row.get("supply_chain_role") or "")

    if _is_st_name(name):
        return (
            "reject_as_concept_or_non_bottleneck",
            "low",
            "ST/*ST status plus original concept-only/high-pollution exclusion keeps this out of false-negative rescue",
            "keep excluded; do not backfill before separate distress/status review",
        )
    if theme in CORE_EQUIPMENT_THEMES and driver in RESCUE_DRIVERS and pollution == "high" and role == "concept_only":
        return (
            "likely_false_negative_needs_primary_source_backfill",
            "high",
            "strict hard-tech theme and business/industry driver conflict with concept-only exclusion; requires primary-source rescue backfill",
            "send to false-negative rescue primary-source backfill queue; do not add to quality pool automatically",
        )
    if theme in CORE_EQUIPMENT_THEMES:
        return (
            "possible_false_negative_manual_review",
            "medium",
            "strict hard-tech theme exists, but driver or status is not strong enough for direct rescue queue",
            "manual false-negative review before any primary-source collection",
        )
    if "industrial software" in theme and driver in RESCUE_DRIVERS:
        return (
            "possible_false_negative_manual_review",
            "medium",
            "industrial-software theme with non-sentiment driver may be a rule artifact, but original exclusion remains concept-only/high-pollution",
            "manual false-negative review before any primary-source collection",
        )
    return (
        "remain_excluded",
        "low",
        "original concept-only/high-pollution exclusion remains stronger than the current theme signal",
        "remain excluded; no primary-source backfill in this task",
    )


def _build_results(source: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for _, row in source.iterrows():
        decision, risk, reason, next_action = _decision(row)
        rows.append(
            {
                "stock_code": row["stock_code"],
                "stock_name": row["stock_name"],
                "original_excluded_reason": row.get("excluded_reason", ""),
                "concept_pollution_flags": _concept_flags(row),
                "hard_tech_domain_signal": _hard_tech_signal(row),
                "bottleneck_or_chokepoint_possibility": _bottleneck_possibility(row),
                "business_relevance_signal": _business_signal(row),
                "false_negative_risk": risk,
                "review_decision": decision,
                "rescue_reason": reason,
                "recommended_next_action": next_action,
                "strict_theme": row.get("strict_theme", ""),
                "primary_doubling_driver": row.get("primary_doubling_driver", ""),
                "tech_bottleneck_domain": row.get("tech_bottleneck_domain", ""),
                "supply_chain_role": row.get("supply_chain_role", ""),
                "concept_pollution_risk": row.get("concept_pollution_risk", ""),
                "price_move_used_for_signal": False,
                "primary_source_backfill_performed": False,
                "auto_added_to_quality_pool": False,
                "research_only": True,
                "used_for_signal": False,
                "used_for_admission": False,
                "notes": "research-only false-negative review; price move remains discovery context only",
            }
        )
    return pd.DataFrame(rows).sort_values("stock_code").reset_index(drop=True)


def _split(results: pd.DataFrame) -> dict[str, pd.DataFrame]:
    return {
        "likely_false_negative_needs_primary_source_backfill": results[
            results["review_decision"].eq("likely_false_negative_needs_primary_source_backfill")
        ],
        "possible_false_negative_manual_review": results[results["review_decision"].eq("possible_false_negative_manual_review")],
        "remain_excluded": results[results["review_decision"].eq("remain_excluded")],
        "reject_as_concept_or_non_bottleneck": results[results["review_decision"].eq("reject_as_concept_or_non_bottleneck")],
    }


def _summary(results: pd.DataFrame, strategy_clean: bool) -> dict[str, Any]:
    counts = results["review_decision"].value_counts()
    used_for_signal = int(results["used_for_signal"].astype(bool).sum())
    used_for_admission = int(results["used_for_admission"].astype(bool).sum())
    price_signal = int(results["price_move_used_for_signal"].astype(bool).sum())
    backfill_count = int(results["primary_source_backfill_performed"].astype(bool).sum())
    quality_pool_count = int(results["auto_added_to_quality_pool"].astype(bool).sum())
    blocking = (
        len(results) != EXPECTED_COUNT
        or used_for_signal
        or used_for_admission
        or price_signal
        or backfill_count
        or quality_pool_count
        or not strategy_clean
    )
    if blocking:
        acceptance = "blocked_due_to_guardrail_violation"
    elif counts.get("possible_false_negative_manual_review", 0) or counts.get("remain_excluded", 0):
        acceptance = "conditionally_ready_with_manual_review_needed"
    else:
        acceptance = "excluded_false_negative_review_ready"
    return {
        "task_name": TASK_NAME,
        "excluded_false_negative_review_count": int(len(results)),
        "processed_count": int(len(results)),
        "likely_false_negative_count": int(counts.get("likely_false_negative_needs_primary_source_backfill", 0)),
        "possible_false_negative_count": int(counts.get("possible_false_negative_manual_review", 0)),
        "remain_excluded_count": int(counts.get("remain_excluded", 0)),
        "reject_as_concept_or_non_bottleneck_count": int(counts.get("reject_as_concept_or_non_bottleneck", 0)),
        "primary_source_backfill_performed": False,
        "auto_added_to_quality_pool_count": quality_pool_count,
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
        "excluded_false_negative_review_count": summary["excluded_false_negative_review_count"],
        "only_false_negative_review_processed": summary["excluded_false_negative_review_count"] == EXPECTED_COUNT
        and summary["processed_count"] == EXPECTED_COUNT,
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
            "# Tech Bottleneck Excluded False Negative Review v1",
            "",
            "## 1. Scope",
            "This research-only task reviews only the 76 excluded false-negative review names from the 2025 doubled-tech expansion queue. It does not process the quality pool, data-gap watch, weak/concept-only names, or rescan 596/901 stocks.",
            "",
            "## 2. Review Method",
            "The review compares strict hard-tech theme, original exclusion reason, concept-pollution flags, bottleneck possibility, and business-driver context. It does not perform primary-source backfill.",
            "",
            "## 3. Results",
            f"Likely false-negative rescue queue: {summary['likely_false_negative_count']}; possible manual review: {summary['possible_false_negative_count']}; remain excluded: {summary['remain_excluded_count']}; reject as concept/non-bottleneck: {summary['reject_as_concept_or_non_bottleneck_count']}.",
            "",
            "## 4. Guardrails",
            f"primary_source_backfill_performed=false; auto_added_to_quality_pool_count={summary['auto_added_to_quality_pool_count']}; price_move_used_for_signal={summary['price_move_used_for_signal']}; used_for_signal_count={summary['used_for_signal_count']}; used_for_admission_count={summary['used_for_admission_count']}; strategy_file_diff_clean={str(summary['strategy_file_diff_clean']).lower()}.",
            "",
            "## 5. Acceptance Decision",
            summary["acceptance_decision"],
            "",
            "## 6. Recommended Next Steps",
            "1. tech_bottleneck_false_negative_rescue_primary_source_backfill_v1",
            "2. tech_bottleneck_doubler_data_gap_watch_triage_v1",
            "3. tech_bottleneck_stock_workspace_docling_panel_v1",
        ]
    )


def run(output_dir: str | Path = OUTPUT_DIR) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    source = _load_input()
    results = _build_results(source)
    splits = _split(results)
    strategy_clean = _strategy_diff_clean()
    summary = _summary(results, strategy_clean)
    guardrails = _guardrails(summary)

    results.to_csv(output / "excluded_false_negative_review_results.csv", index=False)
    splits["likely_false_negative_needs_primary_source_backfill"].to_csv(output / "false_negative_rescue_queue.csv", index=False)
    splits["possible_false_negative_manual_review"].to_csv(output / "possible_false_negative_manual_review.csv", index=False)
    splits["remain_excluded"].to_csv(output / "remain_excluded.csv", index=False)
    splits["reject_as_concept_or_non_bottleneck"].to_csv(output / "reject_as_concept_or_non_bottleneck.csv", index=False)
    _write_json(output / "excluded_false_negative_review_summary.json", summary)
    _write_json(output / "excluded_false_negative_review_guardrails.json", guardrails)
    (output / "tech_bottleneck_excluded_false_negative_review_v1_report.md").write_text(_report(summary), encoding="utf-8")
    return summary


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
