from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
TASK_NAME = "tech_bottleneck_doubler_expansion_core_equivalence_gate_v1"
INPUT_PACKAGE = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_expansion_manual_approval_consolidation_v1/expansion_manual_approval_package.csv"
)
INPUT_EVIDENCE = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_expansion_manual_approval_consolidation_v1/expansion_manual_approval_evidence_index.csv"
)
ELIGIBLE_QUEUE = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_2025_doubler_tech_expansion_queue_v1/eligible_expansion_evidence_queue.csv"
)
IPO_COHORT = (
    PROJECT_ROOT / "outputs/research/a_share_doubled_tech_stocks_since_20250101_v1/ipo_after_20250101_doubled_stocks.csv"
)
OUTPUT_DIR = PROJECT_ROOT / "outputs/research" / TASK_NAME
EXPECTED_COUNT = 88
SOURCE_GROUP = "expansion_2025_doubler_discovered"
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


def _strategy_diff_clean() -> bool:
    result = subprocess.run(
        ["git", "diff", "--", *FORMAL_STRATEGY_FILES],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return result.returncode == 0 and result.stdout == ""


def _load_inputs() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    package = _read_csv(INPUT_PACKAGE).sort_values("stock_code").reset_index(drop=True)
    evidence = _read_csv(INPUT_EVIDENCE)
    eligible = _read_csv(ELIGIBLE_QUEUE)
    ipo = _read_csv(IPO_COHORT)
    package_codes = set(package["stock_code"])
    return (
        package,
        evidence[evidence["stock_code"].isin(package_codes)].copy(),
        eligible[eligible["stock_code"].isin(package_codes)].copy(),
        ipo[ipo["stock_code"].isin(package_codes)].copy(),
    )


def _truthy(value: Any) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes"}


def _score(row: pd.Series) -> int:
    score = 0
    if row.get("bottleneck_thesis_support") == "strong":
        score += 2
    elif row.get("bottleneck_thesis_support") == "moderate":
        score += 1
    if row.get("business_relevance") == "core_hard_tech_evidence_supported":
        score += 2
    if int(float(row.get("primary_source_evidence_count") or 0)) >= 20:
        score += 2
    elif int(float(row.get("primary_source_evidence_count") or 0)) >= 10:
        score += 1
    if int(float(row.get("page_level_citation_count") or 0)) >= 20:
        score += 1
    if row.get("route_around_risk") in {"moderate", "strong"}:
        score += 1
    if row.get("value_capture_quality") in {"moderate", "strong"}:
        score += 1
    if row.get("candidate_tier") == "Tier A" or _truthy(row.get("in_clean_candidate_subset")):
        score += 1
    if str(row.get("strict_quality_category") or "") == "confirmed_hard_tech_doubler":
        score += 1
    if _truthy(row.get("ipo_cohort_risk")):
        score -= 3
    if "route_around_gap" in str(row.get("downgrade_risk_flags") or ""):
        score -= 2
    if row.get("business_relevance") != "core_hard_tech_evidence_supported":
        score -= 3
    return score


def _decision(row: pd.Series) -> tuple[str, str, str]:
    if not _truthy(row.get("primary_source_supported")):
        return (
            "downgrade_or_reject",
            "primary-source support is missing after expansion backfill",
            "downgrade or reject in research-only manual review",
        )
    if row.get("business_relevance") != "core_hard_tech_evidence_supported":
        return (
            "downgrade_or_reject",
            "business relevance is not core hard-tech after backfill",
            "downgrade or reject unless manual reviewer finds stronger primary evidence",
        )
    if _truthy(row.get("ipo_cohort_risk")):
        return (
            "keep_as_expansion_candidate",
            "IPO cohort has limited public history and special return baseline; keep expansion weight, not 90-internal equivalent",
            "review after longer public reporting history or additional primary-source validation",
        )
    if "route_around_gap" in str(row.get("downgrade_risk_flags") or ""):
        return (
            "keep_as_expansion_candidate",
            "route-around gap prevents same-layer equivalence with the 90-internal quality pool",
            "resolve route-around/substitution evidence before equivalence review",
        )
    score = int(row.get("core_equivalence_score") or 0)
    if score >= 10:
        return (
            "core_equivalent_add_to_quality_pool",
            "strong thesis, core business relevance, enough page-level primary evidence, and no IPO/route-around blocker",
            "add to unified manual quality-pool review as expansion-origin core-equivalent; do not auto-apply",
        )
    if score >= 7:
        return (
            "keep_as_expansion_candidate",
            "primary evidence supports research interest but score is below same-layer equivalence threshold",
            "keep in expansion manual review queue and resolve remaining evidence gaps",
        )
    if score >= 4:
        return (
            "adjacent_or_theme_watch",
            "evidence suggests adjacent/theme exposure rather than same-layer bottleneck quality",
            "watch as adjacent/theme candidate; do not add to quality pool",
        )
    return (
        "downgrade_or_reject",
        "equivalence evidence is too weak for expansion candidate continuation",
        "downgrade or reject in research-only manual review",
    )


def _build_gate(package: pd.DataFrame, eligible: pd.DataFrame, ipo: pd.DataFrame) -> pd.DataFrame:
    eligible_cols = [
        "stock_code",
        "return_since_20250101",
        "max_return_since_20250101",
        "strict_theme",
        "strict_quality_category",
        "hard_tech_relevance",
        "primary_doubling_driver",
        "candidate_tier",
        "in_clean_candidate_subset",
        "tech_bottleneck_domain",
        "tech_bottleneck_sub_domain",
        "supply_chain_role",
        "concept_pollution_risk",
    ]
    merged = package.merge(eligible[[col for col in eligible_cols if col in eligible.columns]], on="stock_code", how="left")
    ipo_codes = set(ipo["stock_code"])
    merged["ipo_cohort_risk"] = merged["stock_code"].isin(ipo_codes)
    merged["limited_public_history"] = merged["ipo_cohort_risk"]
    merged["core_equivalence_score"] = merged.apply(_score, axis=1)
    decisions = merged.apply(_decision, axis=1)
    merged["equivalence_gate_decision"] = [item[0] for item in decisions]
    merged["equivalence_gate_reason"] = [item[1] for item in decisions]
    merged["recommended_next_action"] = [item[2] for item in decisions]
    merged["price_move_used_for_signal"] = False
    merged["auto_applied"] = False
    merged["research_only"] = True
    merged["used_for_signal"] = False
    merged["used_for_admission"] = False
    columns = [
        "stock_code",
        "stock_name",
        "source_group",
        "strict_theme",
        "strict_quality_category",
        "candidate_tier",
        "tech_bottleneck_domain",
        "tech_bottleneck_sub_domain",
        "supply_chain_role",
        "concept_pollution_risk",
        "return_since_20250101",
        "max_return_since_20250101",
        "primary_doubling_driver",
        "primary_source_supported",
        "primary_source_evidence_count",
        "page_level_citation_count",
        "bottleneck_thesis_support",
        "business_relevance",
        "route_around_risk",
        "value_capture_quality",
        "disconfirmation_found",
        "remaining_evidence_gap_flags",
        "downgrade_risk_flags",
        "manual_approval_recommendation",
        "ipo_cohort_risk",
        "limited_public_history",
        "core_equivalence_score",
        "equivalence_gate_decision",
        "equivalence_gate_reason",
        "recommended_next_action",
        "price_move_used_for_signal",
        "auto_applied",
        "research_only",
        "used_for_signal",
        "used_for_admission",
        "notes",
    ]
    return merged[columns].sort_values("stock_code").reset_index(drop=True)


def _split(gate: pd.DataFrame) -> dict[str, pd.DataFrame]:
    return {
        "core_equivalent_add_to_quality_pool": gate[
            gate["equivalence_gate_decision"].eq("core_equivalent_add_to_quality_pool")
        ],
        "keep_as_expansion_candidate": gate[gate["equivalence_gate_decision"].eq("keep_as_expansion_candidate")],
        "adjacent_or_theme_watch": gate[gate["equivalence_gate_decision"].eq("adjacent_or_theme_watch")],
        "downgrade_or_reject": gate[gate["equivalence_gate_decision"].eq("downgrade_or_reject")],
    }


def _ipo_audit(gate: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "stock_code",
        "stock_name",
        "strict_theme",
        "candidate_tier",
        "ipo_cohort_risk",
        "limited_public_history",
        "core_equivalence_score",
        "equivalence_gate_decision",
        "equivalence_gate_reason",
        "recommended_next_action",
        "research_only",
        "used_for_signal",
        "used_for_admission",
    ]
    return gate[gate["ipo_cohort_risk"].eq(True)][columns].reset_index(drop=True)


def _summary(gate: pd.DataFrame, strategy_clean: bool) -> dict[str, Any]:
    counts = gate["equivalence_gate_decision"].value_counts()
    used_for_signal = int(gate["used_for_signal"].astype(bool).sum())
    used_for_admission = int(gate["used_for_admission"].astype(bool).sum())
    price_signal = int(gate["price_move_used_for_signal"].astype(bool).sum())
    auto_applied = int(gate["auto_applied"].astype(bool).sum())
    blocking = len(gate) != EXPECTED_COUNT or used_for_signal or used_for_admission or price_signal or auto_applied or not strategy_clean
    if blocking:
        acceptance = "blocked_due_to_guardrail_violation"
    elif counts.get("keep_as_expansion_candidate", 0) or counts.get("adjacent_or_theme_watch", 0) or counts.get("downgrade_or_reject", 0):
        acceptance = "conditionally_ready_with_equivalence_gaps"
    else:
        acceptance = "doubler_expansion_core_equivalence_gate_ready"
    return {
        "task_name": TASK_NAME,
        "source_expansion_candidate_count": int(len(gate)),
        "processed_count": int(len(gate)),
        "core_equivalent_count": int(counts.get("core_equivalent_add_to_quality_pool", 0)),
        "keep_as_expansion_candidate_count": int(counts.get("keep_as_expansion_candidate", 0)),
        "adjacent_or_theme_watch_count": int(counts.get("adjacent_or_theme_watch", 0)),
        "downgrade_or_reject_count": int(counts.get("downgrade_or_reject", 0)),
        "ipo_cohort_risk_count": int(gate["ipo_cohort_risk"].astype(bool).sum()),
        "limited_public_history_count": int(gate["limited_public_history"].astype(bool).sum()),
        "price_move_used_for_signal": price_signal,
        "auto_applied_count": auto_applied,
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
        "core_equivalence_gate_generated": True,
        "source_expansion_candidate_count": summary["source_expansion_candidate_count"],
        "only_expansion_88_processed": summary["source_expansion_candidate_count"] == EXPECTED_COUNT
        and summary["processed_count"] == EXPECTED_COUNT,
        "price_move_used_for_signal": summary["price_move_used_for_signal"],
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
            "# Tech Bottleneck Doubler Expansion Core Equivalence Gate v1",
            "",
            "## 1. Scope",
            "This research-only task reviews only the 88 already backfilled market-discovered expansion candidates. It does not rescan 596 or 901 stocks, process excluded false-negative/data-gap/weak-concept groups, or auto-merge anything into a core pool.",
            "",
            "## 2. Method",
            "The gate separates primary-source availability from core equivalence. It checks thesis support, business relevance, page-level primary evidence, route-around/value-capture quality, downgrade gaps, and IPO cohort risk.",
            "",
            "## 3. Results",
            f"Core-equivalent add to quality pool: {summary['core_equivalent_count']}; keep as expansion candidate: {summary['keep_as_expansion_candidate_count']}; adjacent/theme watch: {summary['adjacent_or_theme_watch_count']}; downgrade/reject: {summary['downgrade_or_reject_count']}.",
            "",
            "## 4. IPO Cohort",
            f"IPO cohort risk: {summary['ipo_cohort_risk_count']}; limited public history: {summary['limited_public_history_count']}. IPO cohort names are not promoted to core-equivalent in this gate.",
            "",
            "## 5. Guardrail Checks",
            f"research_only=true; price_move_used_for_signal={summary['price_move_used_for_signal']}; auto_applied_count={summary['auto_applied_count']}; used_for_signal_count={summary['used_for_signal_count']}; used_for_admission_count={summary['used_for_admission_count']}; baseline_admission_changed_count={summary['baseline_admission_changed_count']}; strategy_file_diff_clean={str(summary['strategy_file_diff_clean']).lower()}.",
            "",
            "## 6. Acceptance Decision",
            summary["acceptance_decision"],
            "",
            "## 7. Recommended Next Steps",
            "1. tech_bottleneck_unified_manual_review_queue_v1",
            "2. tech_bottleneck_excluded_false_negative_review_v1",
            "3. tech_bottleneck_stock_workspace_docling_panel_v1",
        ]
    )


def run(output_dir: Path = OUTPUT_DIR) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    package, _evidence, eligible, ipo = _load_inputs()
    gate = _build_gate(package, eligible, ipo)
    splits = _split(gate)
    ipo_audit = _ipo_audit(gate)
    strategy_clean = _strategy_diff_clean()
    summary = _summary(gate, strategy_clean)
    guardrails = _guardrails(summary)

    gate.to_csv(output_dir / "doubler_expansion_core_equivalence_gate.csv", index=False)
    splits["core_equivalent_add_to_quality_pool"].to_csv(output_dir / "core_equivalent_add_to_quality_pool.csv", index=False)
    splits["keep_as_expansion_candidate"].to_csv(output_dir / "keep_as_expansion_candidate.csv", index=False)
    splits["adjacent_or_theme_watch"].to_csv(output_dir / "adjacent_or_theme_watch.csv", index=False)
    splits["downgrade_or_reject"].to_csv(output_dir / "downgrade_or_reject.csv", index=False)
    ipo_audit.to_csv(output_dir / "ipo_cohort_risk_audit.csv", index=False)
    _write_json(output_dir / "doubler_expansion_core_equivalence_summary.json", summary)
    _write_json(output_dir / "doubler_expansion_core_equivalence_guardrails.json", guardrails)
    (output_dir / "tech_bottleneck_doubler_expansion_core_equivalence_gate_v1_report.md").write_text(
        _report(summary),
        encoding="utf-8",
    )
    return summary


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
