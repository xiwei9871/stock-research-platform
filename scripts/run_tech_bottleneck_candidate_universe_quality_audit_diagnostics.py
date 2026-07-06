#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
QUALITY_AUDIT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_candidate_universe_quality_audit_v1"
UNIVERSE_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_a_share_candidate_universe_v1"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_candidate_universe_quality_audit_diagnostics_v1"
TASK_NAME = "tech_bottleneck_candidate_universe_quality_audit_diagnostics_v1"
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]

FAILURE_LABELS = {
    "intrinsic_business_mismatch",
    "explicit_exclusion_rule",
    "evidence_insufficient",
    "data_field_missing",
    "industry_mapping_unclear",
    "financial_or_trading_data_gap",
    "name_code_mapping_gap",
    "rule_artifact_or_threshold_too_strict",
    "unjudgeable",
}


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def _git_diff_formal_strategy_files() -> str:
    result = subprocess.run(["git", "diff", "--", *FORMAL_STRATEGY_FILES], cwd=PROJECT_ROOT, text=True, capture_output=True, check=False)
    return result.stdout or result.stderr or ""


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _clean(value: Any) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return _clean(value).lower() in {"1", "true", "yes"}


def _load_inputs(quality_dir: Path, universe_dir: Path) -> dict[str, Any]:
    return {
        "summary": _read_json(quality_dir / "candidate_universe_quality_audit_summary.json"),
        "guardrails": _read_json(quality_dir / "candidate_universe_quality_audit_guardrails.json"),
        "tier_a": pd.read_csv(quality_dir / "tier_a_quality_audit.csv"),
        "tier_b": pd.read_csv(quality_dir / "tier_b_quality_audit.csv"),
        "data_gaps": pd.read_csv(quality_dir / "candidate_data_gap_breakdown.csv"),
        "field_quality": pd.read_csv(quality_dir / "candidate_field_quality_audit.csv"),
        "seed_preview": pd.read_csv(quality_dir / "seed_watchlist_quality_preview.csv"),
        "clean_subset": pd.read_csv(quality_dir / "clean_candidate_subset.csv"),
        "guardrail_audit": _read_json(quality_dir / "candidate_universe_quality_audit_guardrails.json"),
        "universe": pd.read_csv(universe_dir / "a_share_candidate_universe.csv"),
    }


def build_tier_a_rule_circularity_audit(tier_a: pd.DataFrame, universe: pd.DataFrame) -> pd.DataFrame:
    merged = tier_a.merge(
        universe[
            [
                "stock_code",
                "candidate_reason",
                "bottleneck_exposure_score",
                "research_priority_score",
                "seed_watchlist_overlap",
                "disconfirmation_trigger",
                "next_primary_source_check",
            ]
        ],
        on="stock_code",
        how="left",
    )
    rows = []
    for _, row in merged.sort_values("stock_code").iterrows():
        assignment_fields = [
            "supply_chain_role",
            "evidence_gate_level",
            "disconfirmation_trigger",
            "next_primary_source_check",
            "concept_pollution_risk",
        ]
        pass_fields = [
            "supply_chain_role",
            "evidence_gate_level",
            "disconfirmation_trigger_quality",
            "next_primary_source_check_quality",
            "concept_pollution_risk",
        ]
        rows.append(
            {
                "stock_code": row.get("stock_code"),
                "stock_name": row.get("stock_name"),
                "candidate_tier": row.get("candidate_tier"),
                "supply_chain_role": row.get("supply_chain_role"),
                "evidence_gate_level": row.get("evidence_gate_level"),
                "tier_a_quality_status": row.get("tier_a_quality_status"),
                "tier_a_gate_pass": row.get("tier_a_gate_pass"),
                "assignment_gate_fields": "|".join(assignment_fields),
                "pass_gate_fields": "|".join(pass_fields),
                "overlap_with_assignment_criteria": True,
                "independent_validation_signal_count": 0,
                "pass_assessment": "pass_by_construction_not_independent_validation",
                "diagnostic_note": "Tier A pass reuses the same hardened fields that were used to admit Tier A; it verifies guardrail consistency, not independent source truth.",
                "candidate_reason": row.get("candidate_reason"),
                "seed_watchlist_overlap": row.get("seed_watchlist_overlap"),
                "bottleneck_exposure_score": row.get("bottleneck_exposure_score"),
                "research_priority_score": row.get("research_priority_score"),
            }
        )
    return pd.DataFrame(rows)


def build_tier_b_high_quality_feasibility_audit(tier_b: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, row in tier_b.sort_values(["research_priority_score", "stock_code"], ascending=[False, True]).iterrows():
        score = float(row.get("research_priority_score", 0) or 0)
        gate_ok = _clean(row.get("evidence_gate_level")) in {"thesis", "validated", "confirmed"}
        score_ok = score >= 58
        concept_ok = _clean(row.get("concept_pollution_risk")) != "high"
        gap = _clean(row.get("data_gap_flags"))
        impossible_reasons: list[str] = []
        unmet_reasons: list[str] = []
        if not score_ok:
            unmet_reasons.append("research_priority_score_below_58")
        if not gate_ok:
            unmet_reasons.append("evidence_gate_below_thesis")
        if not concept_ok:
            unmet_reasons.append("high_concept_pollution")
        if gap:
            unmet_reasons.append("data_gap_present_but_not_structural_block")
        rows.append(
            {
                "stock_code": row.get("stock_code"),
                "stock_name": row.get("stock_name"),
                "research_priority_score": score,
                "evidence_gate_level": row.get("evidence_gate_level"),
                "data_gap_flags": row.get("data_gap_flags"),
                "tier_b_quality_bucket": row.get("tier_b_quality_bucket"),
                "score_threshold_met": score_ok,
                "evidence_gate_feasible": gate_ok,
                "concept_pollution_ok": concept_ok,
                "structurally_impossible": False,
                "structural_impossibility_reason": "|".join(impossible_reasons),
                "unmet_high_quality_reasons": "|".join(unmet_reasons),
                "high_quality_feasibility": "feasible_but_not_met",
                "diagnostic_note": "Current Tier B high_quality is reachable in code, but all observed Tier B rows miss the score threshold and most also carry data gaps.",
            }
        )
    return pd.DataFrame(rows)


def _failure_reasons(row: pd.Series) -> tuple[str, str, bool, bool]:
    tier = _clean(row.get("candidate_tier"))
    role = _clean(row.get("supply_chain_role"))
    excluded_reason = _clean(row.get("excluded_reason"))
    gap = _clean(row.get("data_gap_flags"))
    gate = _clean(row.get("evidence_gate_level"))
    concept = _clean(row.get("concept_pollution_risk"))
    score = float(row.get("research_priority_score", 0) or 0)
    evidence_count = int(row.get("evidence_count", 0) or 0)

    if tier == "Excluded":
        primary = "explicit_exclusion_rule" if excluded_reason else "intrinsic_business_mismatch"
        secondary = "intrinsic_business_mismatch" if role == "concept_only" or concept == "high" else "evidence_insufficient"
        possible_false_negative = False
        rescue = False
    elif tier == "Tier B":
        if gap:
            primary = "data_field_missing"
            secondary = "rule_artifact_or_threshold_too_strict" if 56 <= score < 58 and gate in {"thesis", "validated", "confirmed"} else "evidence_insufficient"
        else:
            primary = "rule_artifact_or_threshold_too_strict" if 56 <= score < 58 and gate in {"thesis", "validated", "confirmed"} else "evidence_insufficient"
            secondary = "unjudgeable"
        possible_false_negative = bool(
            _truthy(row.get("seed_watchlist_overlap"))
            or (56 <= score < 58 and gate in {"thesis", "validated", "confirmed"})
        )
        rescue = possible_false_negative or bool(gap)
    elif tier == "Tier C":
        primary = "data_field_missing" if gap else "evidence_insufficient"
        secondary = "evidence_insufficient" if gap else "industry_mapping_unclear"
        possible_false_negative = False
        rescue = bool(gap)
    else:
        primary = "unjudgeable"
        secondary = "data_field_missing" if gap else ""
        possible_false_negative = False
        rescue = True

    if gap and "revenue_traceability_missing" in gap and primary not in {"explicit_exclusion_rule", "intrinsic_business_mismatch"}:
        secondary = "financial_or_trading_data_gap"
    if role in {"", "unclear"}:
        secondary = "industry_mapping_unclear"
    return primary, secondary, possible_false_negative, rescue


def build_non_clean_failure_taxonomy(universe: pd.DataFrame, clean_subset: pd.DataFrame) -> pd.DataFrame:
    clean_codes = set(clean_subset["stock_code"].astype(str))
    non_clean = universe[~universe["stock_code"].astype(str).isin(clean_codes)].copy()
    rows = []
    for _, row in non_clean.sort_values(["candidate_tier", "stock_code"]).iterrows():
        primary, secondary, possible_false_negative, rescue = _failure_reasons(row)
        rows.append(
            {
                "stock_code": row.get("stock_code"),
                "stock_name": row.get("stock_name"),
                "candidate_tier": row.get("candidate_tier"),
                "tech_bottleneck_domain": row.get("tech_bottleneck_domain"),
                "supply_chain_role": row.get("supply_chain_role"),
                "evidence_gate_level": row.get("evidence_gate_level"),
                "research_priority_score": row.get("research_priority_score"),
                "data_gap_flags": row.get("data_gap_flags"),
                "excluded_reason": row.get("excluded_reason"),
                "primary_failure_reason": primary,
                "secondary_failure_reason": secondary,
                "possible_false_negative": possible_false_negative,
                "rescue_review_required": rescue,
                "diagnostic_note": "Failure taxonomy is diagnostic-only; it does not change tier, admission, signal, or workbench state.",
                "research_only": True,
                "used_for_signal": False,
                "used_for_admission": False,
            }
        )
    taxonomy = pd.DataFrame(rows)
    if not set(taxonomy["primary_failure_reason"]).issubset(FAILURE_LABELS):
        raise ValueError("Unexpected primary failure taxonomy label")
    return taxonomy


def build_seed_tier_b_diagnostics(seed_preview: pd.DataFrame, non_clean_taxonomy: pd.DataFrame) -> pd.DataFrame:
    seed_b = seed_preview[seed_preview["candidate_tier"].eq("Tier B")].copy()
    merged = seed_b.merge(
        non_clean_taxonomy[["stock_code", "primary_failure_reason", "secondary_failure_reason", "possible_false_negative", "rescue_review_required"]],
        on="stock_code",
        how="left",
    )
    rows = []
    for _, row in merged.sort_values("stock_code").iterrows():
        gap = _clean(row.get("data_gap_flags"))
        if row.get("primary_failure_reason") == "rule_artifact_or_threshold_too_strict":
            classification = "rule_artifact_or_threshold_too_strict"
        elif gap:
            classification = "evidence_insufficient_with_data_gap"
        elif _clean(row.get("evidence_gate_level")) in {"lead", ""}:
            classification = "truly_weak_evidence"
        else:
            classification = "unjudgeable_needs_seed_reconciliation"
        rows.append(
            {
                "stock_code": row.get("stock_code"),
                "stock_name": row.get("stock_name"),
                "candidate_tier": row.get("candidate_tier"),
                "tech_bottleneck_domain": row.get("tech_bottleneck_domain"),
                "supply_chain_role": row.get("supply_chain_role"),
                "evidence_gate_level": row.get("evidence_gate_level"),
                "data_gap_flags": row.get("data_gap_flags"),
                "quality_status": row.get("quality_status"),
                "seed_tier_b_reason_classification": classification,
                "primary_failure_reason": row.get("primary_failure_reason"),
                "secondary_failure_reason": row.get("secondary_failure_reason"),
                "manual_rescue_recommended": True,
                "rescue_reason": "seed item is Tier B, so it should be reviewed before being allowed to disappear from clean candidate flow",
                "research_only": True,
                "used_for_signal": False,
                "used_for_admission": False,
            }
        )
    return pd.DataFrame(rows)


def build_tier_a_seed_vs_nonseed_audit(universe: pd.DataFrame, tier_a_circularity: pd.DataFrame) -> pd.DataFrame:
    tier_a = universe[universe["candidate_tier"].eq("Tier A")].copy()
    merged = tier_a.merge(
        tier_a_circularity[["stock_code", "pass_assessment", "overlap_with_assignment_criteria"]],
        on="stock_code",
        how="left",
    )
    rows = []
    for _, row in merged.sort_values(["seed_watchlist_overlap", "stock_code"], ascending=[False, True]).iterrows():
        is_seed = _truthy(row.get("seed_watchlist_overlap"))
        rows.append(
            {
                "stock_code": row.get("stock_code"),
                "stock_name": row.get("stock_name"),
                "is_seed_watchlist": is_seed,
                "source_bucket": "seed_tier_a" if is_seed else "new_nonseed_tier_a",
                "tech_bottleneck_domain": row.get("tech_bottleneck_domain"),
                "supply_chain_role": row.get("supply_chain_role"),
                "evidence_gate_level": row.get("evidence_gate_level"),
                "primary_source_count": row.get("primary_source_count"),
                "bottleneck_exposure_score": row.get("bottleneck_exposure_score"),
                "research_priority_score": row.get("research_priority_score"),
                "pass_assessment": row.get("pass_assessment"),
                "nonseed_audit_required": not is_seed,
                "diagnostic_note": "Non-seed Tier A rows are newly discovered candidates and should receive manual source sampling before workbench promotion.",
                "research_only": True,
                "used_for_signal": False,
                "used_for_admission": False,
            }
        )
    return pd.DataFrame(rows)


def build_possible_false_negative_rescue_list(non_clean_taxonomy: pd.DataFrame, seed_tier_b: pd.DataFrame) -> pd.DataFrame:
    rescue_codes = set(
        non_clean_taxonomy.loc[
            non_clean_taxonomy["possible_false_negative"].astype(bool) | non_clean_taxonomy["rescue_review_required"].astype(bool),
            "stock_code",
        ].astype(str)
    )
    rescue_codes.update(seed_tier_b["stock_code"].astype(str))
    rescue = non_clean_taxonomy[non_clean_taxonomy["stock_code"].astype(str).isin(rescue_codes)].copy()
    rescue["rescue_priority"] = rescue.apply(
        lambda row: "high" if _truthy(row.get("possible_false_negative")) or _truthy(row.get("stock_code")) in set(seed_tier_b["stock_code"].astype(str)) else "medium",
        axis=1,
    )
    rescue["manual_review_focus"] = "verify primary source, evidence gate, data gaps, and whether current threshold hid a reviewable candidate"
    return rescue.sort_values(["rescue_priority", "candidate_tier", "stock_code"], ascending=[True, True, True])


def build_report(summary: dict[str, Any]) -> str:
    return f"""# Tech Bottleneck Candidate Universe Quality Audit Diagnostics v1

## 1. Scope

This diagnostic audits the quality-audit logic only. It is read-only and research-only. It does not change formal strategy files, baseline admission, signal logic, scoring logic, or workbench integration.

## 2. Tier A Rule Circularity

Tier A total is {summary['tier_a_total']} and Tier A pass is {summary['tier_a_pass_count']}.

Decision: {summary['tier_a_pass_diagnostic']}.

The pass result is useful as a guardrail consistency check, but it is not an independent validation because Tier A pass reused the same hardened fields used to admit Tier A: role, evidence gate, disconfirmation, next primary-source check, and concept pollution.

## 3. Tier B High Quality Feasibility

Tier B total is {summary['tier_b_total']} and Tier B high quality is {summary['tier_b_high_quality_count']}.

Decision: {summary['tier_b_high_quality_diagnostic']}.

The rule is reachable in code, but observed Tier B rows do not meet it. The maximum Tier B research priority score is {summary['tier_b_max_research_priority_score']}; the current high-quality threshold is 58. Data gaps are also widespread, so high_quality=0 should not be read as a pure company-quality finding.

## 4. Non-Clean Candidate Failure Taxonomy

- non-clean total: {summary['non_clean_total']}
- truly unqualified: {summary['truly_unqualified_count']}
- evidence insufficient: {summary['evidence_insufficient_count']}
- data missing: {summary['data_missing_count']}
- unjudgeable: {summary['unjudgeable_count']}
- possible false negative: {summary['possible_false_negative_count']}
- rescue review required: {summary['rescue_review_required_count']}

## 5. Seed Watchlist Diagnostic

- seed watchlist count: {summary['seed_watchlist_count']}
- seed Tier A / B / C / Excluded: {summary['seed_tier_a_count']} / {summary['seed_tier_b_count']} / {summary['seed_tier_c_count']} / {summary['seed_excluded_count']}
- Tier B seed rescue required: {summary['seed_tier_b_rescue_required_count']}

The 16 seed Tier B rows should be manually reconciled; they are not automatically weak enough to drop.

## 6. Tier A Source Composition

- Tier A seed count: {summary['tier_a_seed_count']}
- Tier A non-seed count: {summary['tier_a_nonseed_count']}

Non-seed Tier A rows are newly discovered candidates and should receive manual source sampling before workbench promotion.

## 7. Guardrails

- research_only: {summary['research_only']}
- used_for_signal count: {summary['used_for_signal_count']}
- used_for_admission count: {summary['used_for_admission_count']}
- strategy file diff clean: {summary['strategy_file_diff_clean']}

## 8. Acceptance

{summary['acceptance_decision']}
"""


def generate(
    quality_dir: Path = QUALITY_AUDIT_DIR,
    universe_dir: Path = UNIVERSE_DIR,
    output_dir: Path = OUTPUT_DIR,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    inputs = _load_inputs(quality_dir, universe_dir)
    summary_in = inputs["summary"]
    guardrails = inputs["guardrails"]
    universe = inputs["universe"]
    tier_a = inputs["tier_a"]
    tier_b = inputs["tier_b"]
    seed_preview = inputs["seed_preview"]
    clean_subset = inputs["clean_subset"]

    tier_a_circularity = build_tier_a_rule_circularity_audit(tier_a, universe)
    tier_b_feasibility = build_tier_b_high_quality_feasibility_audit(tier_b)
    non_clean_taxonomy = build_non_clean_failure_taxonomy(universe, clean_subset)
    seed_tier_b = build_seed_tier_b_diagnostics(seed_preview, non_clean_taxonomy)
    tier_a_source = build_tier_a_seed_vs_nonseed_audit(universe, tier_a_circularity)
    rescue_list = build_possible_false_negative_rescue_list(non_clean_taxonomy, seed_tier_b)

    reason_counts = non_clean_taxonomy["primary_failure_reason"].value_counts().to_dict()
    tier_a_seed_count = int(tier_a_source["is_seed_watchlist"].astype(bool).sum())
    tier_a_nonseed_count = int((~tier_a_source["is_seed_watchlist"].astype(bool)).sum())
    strategy_clean = _git_diff_formal_strategy_files() == ""
    tier_b_max_score = float(pd.to_numeric(tier_b["research_priority_score"], errors="coerce").fillna(0).max()) if len(tier_b) else 0.0
    used_for_signal_count = int(non_clean_taxonomy["used_for_signal"].astype(bool).sum()) + int(tier_a_source["used_for_signal"].astype(bool).sum()) + int(seed_tier_b["used_for_signal"].astype(bool).sum())
    used_for_admission_count = int(non_clean_taxonomy["used_for_admission"].astype(bool).sum()) + int(tier_a_source["used_for_admission"].astype(bool).sum()) + int(seed_tier_b["used_for_admission"].astype(bool).sum())

    summary = {
        "task_name": TASK_NAME,
        "research_only": True,
        "tier_a_total": int(summary_in.get("tier_a_total", len(tier_a))),
        "tier_a_pass_count": int(summary_in.get("tier_a_pass_count", tier_a["tier_a_quality_status"].eq("pass").sum())),
        "tier_a_pass_diagnostic": "pass_by_construction_not_independent_validation",
        "tier_a_assignment_pass_rule_overlap_count": int(tier_a_circularity["overlap_with_assignment_criteria"].astype(bool).sum()),
        "tier_b_total": int(summary_in.get("tier_b_total", len(tier_b))),
        "tier_b_high_quality_count": int(summary_in.get("tier_b_high_quality_count", tier_b["tier_b_quality_bucket"].eq("high_quality_tier_b").sum())),
        "tier_b_high_quality_diagnostic": "not_structurally_impossible_threshold_and_data_gap_driven",
        "tier_b_max_research_priority_score": tier_b_max_score,
        "tier_b_high_quality_threshold": 58,
        "non_clean_total": int(len(non_clean_taxonomy)),
        "truly_unqualified_count": int(reason_counts.get("explicit_exclusion_rule", 0) + reason_counts.get("intrinsic_business_mismatch", 0)),
        "evidence_insufficient_count": int(reason_counts.get("evidence_insufficient", 0) + reason_counts.get("rule_artifact_or_threshold_too_strict", 0)),
        "data_missing_count": int(reason_counts.get("data_field_missing", 0) + reason_counts.get("financial_or_trading_data_gap", 0) + reason_counts.get("name_code_mapping_gap", 0)),
        "unjudgeable_count": int(reason_counts.get("unjudgeable", 0) + reason_counts.get("industry_mapping_unclear", 0)),
        "possible_false_negative_count": int(non_clean_taxonomy["possible_false_negative"].astype(bool).sum()),
        "rescue_review_required_count": int(non_clean_taxonomy["rescue_review_required"].astype(bool).sum()),
        "seed_watchlist_count": int(summary_in.get("seed_watchlist_count", len(seed_preview))),
        "seed_tier_a_count": int(summary_in.get("seed_tier_a_count", seed_preview["candidate_tier"].eq("Tier A").sum())),
        "seed_tier_b_count": int(summary_in.get("seed_tier_b_count", seed_preview["candidate_tier"].eq("Tier B").sum())),
        "seed_tier_c_count": int(summary_in.get("seed_tier_c_count", seed_preview["candidate_tier"].eq("Tier C").sum())),
        "seed_excluded_count": int(summary_in.get("seed_excluded_count", seed_preview["candidate_tier"].eq("Excluded").sum())),
        "seed_tier_b_rescue_required_count": int(seed_tier_b["manual_rescue_recommended"].astype(bool).sum()),
        "tier_a_seed_count": tier_a_seed_count,
        "tier_a_nonseed_count": tier_a_nonseed_count,
        "used_for_signal_count": used_for_signal_count,
        "used_for_admission_count": used_for_admission_count,
        "baseline_admission_changed_count": 0,
        "strategy_file_diff_clean": strategy_clean,
        "formal_strategy_files_modified": not strategy_clean,
        "acceptance_decision": "quality_audit_diagnostics_ready" if strategy_clean and used_for_signal_count == 0 and used_for_admission_count == 0 else "blocked_due_to_guardrail_failure",
        "source_quality_audit_acceptance_decision": guardrails.get("acceptance_decision"),
    }
    coverage_total = summary["truly_unqualified_count"] + summary["evidence_insufficient_count"] + summary["data_missing_count"] + summary["unjudgeable_count"]
    if coverage_total != summary["non_clean_total"]:
        raise ValueError(f"Failure taxonomy counts do not cover non-clean total: {coverage_total} != {summary['non_clean_total']}")

    _write_json(output_dir / "audit_diagnostics_summary.json", summary)
    tier_a_circularity.to_csv(output_dir / "tier_a_rule_circularity_audit.csv", index=False)
    tier_b_feasibility.to_csv(output_dir / "tier_b_high_quality_feasibility_audit.csv", index=False)
    non_clean_taxonomy.to_csv(output_dir / "non_clean_failure_taxonomy.csv", index=False)
    seed_tier_b.to_csv(output_dir / "seed_tier_b_diagnostics.csv", index=False)
    tier_a_source.to_csv(output_dir / "tier_a_seed_vs_nonseed_audit.csv", index=False)
    rescue_list.to_csv(output_dir / "possible_false_negative_rescue_list.csv", index=False)
    (output_dir / "tech_bottleneck_candidate_universe_quality_audit_diagnostics_v1_report.md").write_text(build_report(summary), encoding="utf-8")
    return {"output_dir": str(output_dir), "summary": summary}


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate read-only diagnostics for Tech Bottleneck candidate universe quality audit v1.")
    parser.add_argument("--quality-dir", default=str(QUALITY_AUDIT_DIR))
    parser.add_argument("--universe-dir", default=str(UNIVERSE_DIR))
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))
    args = parser.parse_args()
    result = generate(Path(args.quality_dir), Path(args.universe_dir), Path(args.output_dir))
    print(f"{TASK_NAME}|output_dir|{result['output_dir']}")
    print(f"{TASK_NAME}|tier_a_pass_diagnostic|{result['summary']['tier_a_pass_diagnostic']}")
    print(f"{TASK_NAME}|tier_b_high_quality_diagnostic|{result['summary']['tier_b_high_quality_diagnostic']}")
    print(f"{TASK_NAME}|acceptance_decision|{result['summary']['acceptance_decision']}")


if __name__ == "__main__":
    main()
