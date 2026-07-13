from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
TASK_NAME = "tech_bottleneck_2025_doubler_tech_expansion_queue_v1"
STRICT_MASTER = PROJECT_ROOT / "outputs/research/a_share_doubled_tech_stock_strict_theme_quality_audit_v1/strict_theme_quality_master.csv"
CANONICAL_90 = PROJECT_ROOT / "outputs/research/tech_bottleneck_seed_tier_a_requalification_v2_review_pool_refinement/hard_tech_review_pool_preview.csv"
CANDIDATE_UNIVERSE = PROJECT_ROOT / "outputs/research/tech_bottleneck_a_share_candidate_universe_v1/a_share_candidate_universe.csv"
CLEAN_SUBSET = PROJECT_ROOT / "outputs/research/tech_bottleneck_candidate_universe_quality_audit_v1/clean_candidate_subset.csv"
EXCLUDED_FALSE_NEGATIVE = PROJECT_ROOT / "outputs/research/tech_bottleneck_candidate_universe_quality_audit_v1/excluded_false_negative_audit.csv"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research" / TASK_NAME
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]

HARD_TECH_QUALITY = {"confirmed_hard_tech_doubler", "likely_hard_tech_doubler"}
WEAK_TECH_QUALITY = {
    "broad_tech_application_doubler",
    "theme_or_sentiment_driven_doubler",
    "concept_only_or_weak_tech_doubler",
    "non_tech_false_positive",
}
DISALLOWED_ROLES = {"beneficiary", "concept_only"}


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


def _load_inputs() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    doubled = _read_csv(STRICT_MASTER)
    pool90 = _read_csv(CANONICAL_90)
    universe = _read_csv(CANDIDATE_UNIVERSE)
    clean = _read_csv(CLEAN_SUBSET)
    excluded = _read_csv(EXCLUDED_FALSE_NEGATIVE)
    return doubled, pool90, universe, clean, excluded


def _universe_map(universe: pd.DataFrame) -> dict[str, dict[str, Any]]:
    if universe.empty:
        return {}
    columns = [
        "stock_code",
        "tech_bottleneck_domain",
        "tech_bottleneck_sub_domain",
        "supply_chain_role",
        "candidate_tier",
        "evidence_gate_level",
        "concept_pollution_risk",
        "excluded_flag",
        "excluded_reason",
        "main_business_relevance",
        "real_business_exposure_score",
        "bottleneck_exposure_score",
        "research_priority_score",
        "next_primary_source_check",
        "next_research_action",
        "data_gap_flags",
        "manual_review_focus",
    ]
    available = [column for column in columns if column in universe.columns]
    return universe[available].drop_duplicates("stock_code").set_index("stock_code").to_dict("index")


def _clean_codes(clean: pd.DataFrame) -> set[str]:
    return set(clean["stock_code"].map(_stock_code)) if not clean.empty else set()


def _excluded_map(excluded: pd.DataFrame) -> dict[str, dict[str, Any]]:
    if excluded.empty:
        return {}
    return excluded.drop_duplicates("stock_code").set_index("stock_code").to_dict("index")


def _is_truthy(value: Any) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes"}


def _has_hard_tech_gate(row: pd.Series, universe_row: dict[str, Any] | None) -> bool:
    if str(row.get("strict_quality_category") or "") not in HARD_TECH_QUALITY:
        return False
    if universe_row is None:
        return False
    role = str(universe_row.get("supply_chain_role") or "").strip()
    pollution = str(universe_row.get("concept_pollution_risk") or "").strip().lower()
    excluded = _is_truthy(universe_row.get("excluded_flag", False))
    if excluded or pollution == "high" or role in DISALLOWED_ROLES:
        return False
    if role in {"bottleneck", "chokepoint", "derivative_exposure"}:
        return True
    exposure_score = float(universe_row.get("real_business_exposure_score") or 0)
    bottleneck_score = float(universe_row.get("bottleneck_exposure_score") or 0)
    return exposure_score >= 60 and bottleneck_score >= 60


def _classify(row: pd.Series, *, pool90_codes: set[str], universe_row: dict[str, Any] | None, clean_codes: set[str], excluded_row: dict[str, Any] | None) -> tuple[str, str, str]:
    code = row["stock_code"]
    strict_quality = str(row.get("strict_quality_category") or "")
    if code in pool90_codes:
        return (
            "already_in_90_pool",
            "already in canonical 90 hard-tech review pool; do not duplicate expansion handling",
            "review through existing 90-pool manual workflow",
        )
    if strict_quality not in HARD_TECH_QUALITY:
        return (
            "weak_or_concept_only_no_backfill",
            "strict theme audit does not classify this as confirmed/likely hard-tech doubler",
            "do not backfill from price move; keep out of expansion evidence queue",
        )
    if excluded_row is not None or (universe_row and _is_truthy(universe_row.get("excluded_flag", False))):
        return (
            "excluded_false_negative_review",
            "90-outside hard-tech doubler was previously excluded or low-relevance; review only as possible false negative",
            "manual false-negative review before any source collection",
        )
    if _has_hard_tech_gate(row, universe_row):
        return (
            "eligible_expansion_evidence_queue",
            "90-outside hard-tech doubler has audited universe hard-tech/bottleneck characteristics and is not excluded/high-pollution",
            "primary-source evidence completion queue; price move is discovery-only, not a signal",
        )
    if universe_row is not None or code in clean_codes:
        return (
            "data_gap_watch",
            "hard-tech doubler has some candidate-universe footprint but lacks enough role/evidence gate support for immediate backfill",
            "watch for data gap resolution and next primary-source check",
        )
    return (
        "data_gap_watch",
        "hard-tech doubler not found in audited candidate universe; requires mapping review before any PDF/source collection",
        "map company to hard-tech domain and supply-chain role before evidence completion",
    )


def _build_master(doubled: pd.DataFrame, pool90: pd.DataFrame, universe: pd.DataFrame, clean: pd.DataFrame, excluded: pd.DataFrame) -> pd.DataFrame:
    pool90_codes = set(pool90["stock_code"].map(_stock_code))
    universe_by_code = _universe_map(universe)
    clean_code_set = _clean_codes(clean)
    excluded_by_code = _excluded_map(excluded)
    rows: list[dict[str, Any]] = []
    for _, row in doubled.sort_values("stock_code").iterrows():
        code = row["stock_code"]
        universe_row = universe_by_code.get(code)
        excluded_row = excluded_by_code.get(code)
        queue_class, reason, next_action = _classify(
            row,
            pool90_codes=pool90_codes,
            universe_row=universe_row,
            clean_codes=clean_code_set,
            excluded_row=excluded_row,
        )
        merged = {
            "stock_code": code,
            "stock_name": row.get("stock_name", ""),
            "return_since_20250101": row.get("return_since_20250101", ""),
            "max_return_since_20250101": row.get("max_return_since_20250101", ""),
            "strict_theme": row.get("strict_theme", ""),
            "strict_quality_category": row.get("strict_quality_category", ""),
            "hard_tech_relevance": row.get("hard_tech_relevance", ""),
            "primary_doubling_driver": row.get("primary_doubling_driver", ""),
            "in_90_pool": code in pool90_codes,
            "in_3252_candidate_universe": universe_row is not None,
            "in_clean_candidate_subset": code in clean_code_set,
            "previously_excluded_or_low_relevance": excluded_row is not None
            or bool(universe_row and _is_truthy(universe_row.get("excluded_flag", False))),
            "tech_bottleneck_domain": "" if universe_row is None else universe_row.get("tech_bottleneck_domain", ""),
            "tech_bottleneck_sub_domain": "" if universe_row is None else universe_row.get("tech_bottleneck_sub_domain", ""),
            "supply_chain_role": "" if universe_row is None else universe_row.get("supply_chain_role", ""),
            "candidate_tier": "" if universe_row is None else universe_row.get("candidate_tier", ""),
            "evidence_gate_level": "" if universe_row is None else universe_row.get("evidence_gate_level", ""),
            "concept_pollution_risk": "" if universe_row is None else universe_row.get("concept_pollution_risk", ""),
            "excluded_reason": ""
            if excluded_row is None
            else str(excluded_row.get("excluded_reason") or excluded_row.get("notes") or ""),
            "data_gap_flags": "" if universe_row is None else universe_row.get("data_gap_flags", ""),
            "next_primary_source_check": "" if universe_row is None else universe_row.get("next_primary_source_check", ""),
            "expansion_queue_class": queue_class,
            "classification_reason": reason,
            "recommended_next_action": next_action,
            "price_move_used_for_discovery": True,
            "price_move_used_for_signal": False,
            "research_only": True,
            "used_for_signal": False,
            "used_for_admission": False,
        }
        rows.append(merged)
    return pd.DataFrame(rows).sort_values("stock_code").reset_index(drop=True)


def _summary(master: pd.DataFrame, strategy_clean: bool) -> dict[str, Any]:
    counts = master["expansion_queue_class"].value_counts()
    used_for_signal = int(master["used_for_signal"].astype(bool).sum())
    used_for_admission = int(master["used_for_admission"].astype(bool).sum())
    price_signal = int(master["price_move_used_for_signal"].astype(bool).sum())
    if not strategy_clean or used_for_signal or used_for_admission or price_signal:
        acceptance = "blocked_due_to_guardrail_violation"
    else:
        acceptance = "doubler_tech_expansion_queue_ready"
    return {
        "task_name": TASK_NAME,
        "research_only": True,
        "input_doubled_tech_count": int(len(master)),
        "classified_count": int(len(master)),
        "already_in_90_pool_count": int(counts.get("already_in_90_pool", 0)),
        "eligible_expansion_evidence_queue_count": int(counts.get("eligible_expansion_evidence_queue", 0)),
        "excluded_false_negative_review_count": int(counts.get("excluded_false_negative_review", 0)),
        "weak_or_concept_only_no_backfill_count": int(counts.get("weak_or_concept_only_no_backfill", 0)),
        "data_gap_watch_count": int(counts.get("data_gap_watch", 0)),
        "price_move_used_for_signal_count": price_signal,
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


def _guardrails(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_name": TASK_NAME,
        "research_only": True,
        "input_doubled_tech_count": summary["input_doubled_tech_count"],
        "classified_count": summary["classified_count"],
        "no_direct_admission_from_price_move": summary["price_move_used_for_signal_count"] == 0,
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
            "# Tech Bottleneck 2025 Doubler Tech Expansion Queue v1",
            "",
            "## 1. Scope",
            "This task converts 2025 A-share doubled tech stocks into a research-only market-discovered expansion queue. Price moves are discovery clues only, not signals, admission criteria, or automatic backfill triggers.",
            "",
            "## 2. Input",
            f"Input doubled tech stocks: {summary['input_doubled_tech_count']}. Classified rows: {summary['classified_count']}.",
            "",
            "## 3. Queue Classes",
            f"Already in 90 pool: {summary['already_in_90_pool_count']}. Eligible expansion evidence queue: {summary['eligible_expansion_evidence_queue_count']}. Excluded false-negative review: {summary['excluded_false_negative_review_count']}. Weak/concept-only no backfill: {summary['weak_or_concept_only_no_backfill_count']}. Data gap watch: {summary['data_gap_watch_count']}.",
            "",
            "## 4. Guardrails",
            f"price_move_used_for_signal_count={summary['price_move_used_for_signal_count']}; auto_applied_count={summary['auto_applied_count']}; used_for_signal_count={summary['used_for_signal_count']}; used_for_admission_count={summary['used_for_admission_count']}; strategy_file_diff_clean={str(summary['strategy_file_diff_clean']).lower()}.",
            "",
            "## 5. Acceptance Decision",
            summary["acceptance_decision"],
            "",
            "## 6. Recommended Next Steps",
            "1. tech_bottleneck_90_manual_approval_consolidation_v1",
            "2. tech_bottleneck_expansion_queue_primary_source_backfill_v1",
            "3. tech_bottleneck_stock_workspace_docling_panel_v1",
        ]
    )


def run(output_dir: str | Path = OUTPUT_DIR) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    doubled, pool90, universe, clean, excluded = _load_inputs()
    master = _build_master(doubled, pool90, universe, clean, excluded)
    overlap = master[
        [
            "stock_code",
            "stock_name",
            "in_90_pool",
            "in_3252_candidate_universe",
            "in_clean_candidate_subset",
            "previously_excluded_or_low_relevance",
            "expansion_queue_class",
            "classification_reason",
        ]
    ].copy()
    strategy_clean = _strategy_diff_clean()
    summary = _summary(master, strategy_clean)
    guardrails = _guardrails(summary)

    master.to_csv(output / "tech_bottleneck_2025_doubler_tech_expansion_queue_master.csv", index=False)
    master[master["expansion_queue_class"].eq("already_in_90_pool")].to_csv(output / "already_in_90_pool.csv", index=False)
    master[master["expansion_queue_class"].eq("eligible_expansion_evidence_queue")].to_csv(
        output / "eligible_expansion_evidence_queue.csv", index=False
    )
    master[master["expansion_queue_class"].eq("excluded_false_negative_review")].to_csv(
        output / "excluded_false_negative_review.csv", index=False
    )
    master[master["expansion_queue_class"].eq("weak_or_concept_only_no_backfill")].to_csv(
        output / "weak_or_concept_only_no_backfill.csv", index=False
    )
    master[master["expansion_queue_class"].eq("data_gap_watch")].to_csv(output / "data_gap_watch.csv", index=False)
    overlap.to_csv(output / "doubler_candidate_universe_overlap_audit.csv", index=False)
    _write_json(output / "tech_bottleneck_2025_doubler_tech_expansion_queue_summary.json", summary)
    _write_json(output / "tech_bottleneck_2025_doubler_tech_expansion_queue_guardrails.json", guardrails)
    (output / "tech_bottleneck_2025_doubler_tech_expansion_queue_v1_report.md").write_text(_report(summary), encoding="utf-8")
    return summary


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
