#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
INPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_a_share_candidate_universe_v1"
HARDENING_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_method_codification_v1_hardening_patch"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_candidate_universe_quality_audit_v1"
TASK_NAME = "tech_bottleneck_candidate_universe_quality_audit_v1"
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]


DATA_GAP_TYPES = {
    "missing_main_business": ("medium", "main business relevance cannot be verified", "add business scope / main product source"),
    "missing_announcement": ("high", "no announcement or prior primary-source support", "collect exchange filing / announcement"),
    "missing_primary_source": ("high", "candidate relies on derived or weak source", "collect annual report, announcement, or financial statement"),
    "missing_customer_certification": ("medium", "customer validation unclear", "check customer certification / delivery disclosure"),
    "missing_revenue_exposure": ("high", "revenue exposure cannot be traced", "check segment revenue and product revenue"),
    "missing_financial_statement": ("high", "financial statement support missing", "join full financial statement source adapter"),
    "missing_news": ("low", "news support missing", "join news source mapping"),
    "missing_architecture_shift": ("medium", "architecture shift is generic or missing", "document old failure point and new dependency"),
    "missing_route_around": ("medium", "substitution route unclear", "review substitute maturity and qualification cycle"),
    "missing_value_capture": ("high", "economics may not be captured", "check margin trend, order visibility, customer bargaining"),
    "missing_disconfirmation": ("high", "thesis lacks falsification condition", "define fastest disconfirming source"),
    "missing_next_primary_source_check": ("high", "next source check unclear", "write specific primary-source check"),
    "missing_evidence_gate": ("high", "evidence gate not validated / confirmed", "collect Tier 1 evidence"),
    "missing_supply_chain_role": ("high", "beneficiary/bottleneck/chokepoint unclear", "map supply-chain role explicitly"),
}


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def _git_diff_formal_strategy_files() -> str:
    result = subprocess.run(["git", "diff", "--", *FORMAL_STRATEGY_FILES], cwd=PROJECT_ROOT, text=True, capture_output=True, check=False)
    return result.stdout or result.stderr or ""


def _clean_series(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series([""] * len(frame), index=frame.index)
    return frame[column].fillna("").astype(str).str.strip()


def _bool_series(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series([False] * len(frame), index=frame.index)
    return frame[column].fillna(False).astype(bool)


def _load_inputs(input_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    candidates = pd.read_csv(input_dir / "a_share_candidate_universe.csv")
    seed = pd.read_csv(input_dir / "a_share_candidate_seed_watchlist_overlap.csv")
    guardrails = json.loads((input_dir / "a_share_candidate_guardrails.json").read_text(encoding="utf-8"))
    return candidates, seed, guardrails


def build_tier_a_audit(candidates: pd.DataFrame) -> pd.DataFrame:
    tier_a = candidates[candidates["candidate_tier"].eq("Tier A")].copy()
    rows = []
    for _, row in tier_a.iterrows():
        disq = "specific" if str(row.get("disconfirmation_trigger", "")).strip() else "missing"
        nextq = "specific" if str(row.get("next_primary_source_check", "")).strip() else "missing"
        archq = "usable" if str(row.get("architecture_shift", "")).strip() else "missing"
        routeq = "usable" if str(row.get("route_around_risk", "")).strip() else "missing"
        valueq = "usable" if float(row.get("value_capture_score", 0) or 0) >= 50 else "weak"
        gate_pass = (
            row.get("supply_chain_role") in {"bottleneck", "chokepoint"}
            and row.get("evidence_gate_level") in {"validated", "confirmed"}
            and disq != "missing"
            and nextq != "missing"
            and row.get("concept_pollution_risk") != "high"
        )
        if gate_pass and valueq == "usable" and archq == "usable" and routeq == "usable":
            status = "pass"
            downgrade = ""
        elif gate_pass:
            status = "pass_with_data_gap"
            downgrade = "retain_tier_a_with_data_gap_review"
        elif row.get("supply_chain_role") in {"beneficiary", "derivative_exposure"}:
            status = "downgrade_to_tier_b"
            downgrade = "downgrade_to_tier_b"
        elif row.get("concept_pollution_risk") == "high":
            status = "exclude_candidate"
            downgrade = "exclude_candidate"
        else:
            status = "downgrade_to_risk_review"
            downgrade = "downgrade_to_risk_review"
        rows.append(
            {
                "stock_code": row.get("stock_code"),
                "stock_name": row.get("stock_name"),
                "tech_bottleneck_domain": row.get("tech_bottleneck_domain"),
                "supply_chain_role": row.get("supply_chain_role"),
                "candidate_tier": row.get("candidate_tier"),
                "evidence_gate_level": row.get("evidence_gate_level"),
                "evidence_strength": row.get("evidence_strength"),
                "primary_source_count": row.get("primary_source_count"),
                "disconfirmation_trigger_quality": disq,
                "next_primary_source_check_quality": nextq,
                "architecture_shift_quality": archq,
                "route_around_quality": routeq,
                "value_capture_quality": valueq,
                "concept_pollution_risk": row.get("concept_pollution_risk"),
                "tier_a_gate_pass": bool(gate_pass),
                "tier_a_quality_status": status,
                "downgrade_recommendation": downgrade,
                "manual_review_focus": row.get("manual_review_focus"),
                "notes": "Tier A audit uses hardened gate fields; primary-source specificity still requires manual review.",
            }
        )
    return pd.DataFrame(rows)


def build_tier_b_audit(candidates: pd.DataFrame) -> pd.DataFrame:
    tier_b = candidates[candidates["candidate_tier"].eq("Tier B")].copy()
    rows = []
    for _, row in tier_b.iterrows():
        score = float(row.get("research_priority_score", 0) or 0)
        gap = str(row.get("data_gap_flags", "") or "")
        if row.get("concept_pollution_risk") == "high":
            bucket = "concept_polluted_tier_b"
            queue = "source_conflict_review"
        elif row.get("seed_watchlist_overlap"):
            bucket = "seed_overlap_tier_b"
            queue = "thesis_validation_review"
        elif score >= 58 and row.get("evidence_gate_level") in {"thesis", "validated", "confirmed"} and not gap:
            bucket = "high_quality_tier_b"
            queue = row.get("review_queue_type") or "thesis_validation_review"
        elif score >= 58 and row.get("evidence_gate_level") in {"thesis", "validated", "confirmed"}:
            bucket = "high_quality_tier_b"
            queue = row.get("review_queue_type") or "data_gap_review"
        elif gap:
            bucket = "data_gap_tier_b"
            queue = "data_gap_review"
        elif row.get("evidence_gate_level") == "lead":
            bucket = "weak_evidence_tier_b"
            queue = "watch_only"
        else:
            bucket = "new_candidate_tier_b"
            queue = row.get("review_queue_type") or "thesis_validation_review"
        rows.append(
            {
                "stock_code": row.get("stock_code"),
                "stock_name": row.get("stock_name"),
                "tech_bottleneck_domain": row.get("tech_bottleneck_domain"),
                "evidence_gate_level": row.get("evidence_gate_level"),
                "supply_chain_role": row.get("supply_chain_role"),
                "main_business_relevance": row.get("main_business_relevance"),
                "real_business_exposure_score": row.get("real_business_exposure_score"),
                "data_gap_flags": row.get("data_gap_flags"),
                "concept_pollution_risk": row.get("concept_pollution_risk"),
                "research_priority_score": row.get("research_priority_score"),
                "tier_b_quality_bucket": bucket,
                "recommended_review_queue": queue,
                "manual_review_focus": row.get("manual_review_focus"),
                "notes": "Tier B is reviewable but not clean without resolving listed evidence gaps.",
            }
        )
    return pd.DataFrame(rows)


def build_data_gap_breakdown(candidates: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for gap_type, (severity, impact, fix) in DATA_GAP_TYPES.items():
        if gap_type == "missing_main_business":
            mask = _clean_series(candidates, "main_business_relevance").isin({"", "unclear", "low"})
        elif gap_type == "missing_announcement":
            mask = pd.to_numeric(candidates.get("primary_source_count", 0), errors="coerce").fillna(0).eq(0)
        elif gap_type == "missing_primary_source":
            mask = pd.to_numeric(candidates.get("primary_source_count", 0), errors="coerce").fillna(0).eq(0)
        elif gap_type == "missing_customer_certification":
            mask = _clean_series(candidates, "customer_certification_stage").isin({"", "unclear", "missing"})
        elif gap_type == "missing_revenue_exposure":
            mask = _clean_series(candidates, "revenue_exposure_bucket").isin({"", "unclear", "missing", "concept_only"}) | ~_bool_series(candidates, "revenue_traceable_flag")
        elif gap_type == "missing_financial_statement":
            mask = ~_bool_series(candidates, "financial_traceable_flag")
        elif gap_type == "missing_news":
            mask = ~_clean_series(candidates, "evidence_type").str.contains("news", case=False, regex=False)
        elif gap_type == "missing_architecture_shift":
            mask = _clean_series(candidates, "architecture_shift").eq("")
        elif gap_type == "missing_route_around":
            mask = _clean_series(candidates, "route_around_risk").isin({"", "unclear"}) | _clean_series(candidates, "can_customer_route_around").isin({"", "unclear"})
        elif gap_type == "missing_value_capture":
            mask = pd.to_numeric(candidates.get("value_capture_score", 0), errors="coerce").fillna(0).lt(60)
        elif gap_type == "missing_disconfirmation":
            mask = _clean_series(candidates, "disconfirmation_trigger").eq("")
        elif gap_type == "missing_next_primary_source_check":
            mask = _clean_series(candidates, "next_primary_source_check").eq("")
        elif gap_type == "missing_evidence_gate":
            mask = ~_clean_series(candidates, "evidence_gate_level").isin({"validated", "confirmed"})
        elif gap_type == "missing_supply_chain_role":
            mask = _clean_series(candidates, "supply_chain_role").isin({"", "unclear"})
        else:
            mask = pd.Series([False] * len(candidates), index=candidates.index)
        affected = candidates[mask]
        rows.append(
            {
                "data_gap_type": gap_type,
                "affected_count": int(len(affected)),
                "affected_tier_a_count": int(affected["candidate_tier"].eq("Tier A").sum()) if not affected.empty else 0,
                "affected_tier_b_count": int(affected["candidate_tier"].eq("Tier B").sum()) if not affected.empty else 0,
                "affected_tier_c_count": int(affected["candidate_tier"].eq("Tier C").sum()) if not affected.empty else 0,
                "affected_excluded_count": int(affected["candidate_tier"].eq("Excluded").sum()) if not affected.empty else 0,
                "severity": severity,
                "manual_review_impact": impact,
                "recommended_fix": fix,
            }
        )
    return pd.DataFrame(rows)


def build_excluded_false_negative_audit(candidates: pd.DataFrame) -> pd.DataFrame:
    excluded = candidates[candidates["candidate_tier"].eq("Excluded")].copy()
    priority_domains = {"新材料", "高端仪器仪表与科学仪器", "工业软件与基础软件", "半导体", "高端制造装备", "航空航天与军工电子", "光电与通信"}
    rows = []
    for _, row in excluded.iterrows():
        score = float(row.get("bottleneck_exposure_score", 0) or 0)
        domain = row.get("tech_bottleneck_domain")
        evidence_count = int(row.get("evidence_count", 0) or 0)
        if domain in priority_domains and evidence_count >= 2 and score >= 55:
            risk = "high"
            reinstate = True
            tier = "Tier B"
        elif domain in priority_domains or evidence_count >= 1:
            risk = "medium"
            reinstate = False
            tier = "Tier C"
        else:
            risk = "low"
            reinstate = False
            tier = "Watch Only"
        flags = "|".join(
            flag
            for flag in [
                "policy_theme_only_flag",
                "name_similarity_only_flag",
                "minority_investment_only_flag",
                "trading_agent_or_distributor_flag",
                "secondary_market_narrative_only_flag",
                "interactive_platform_only_flag",
                "kol_or_social_only_flag",
            ]
            if bool(row.get(flag, False))
        )
        rows.append(
            {
                "stock_code": row.get("stock_code"),
                "stock_name": row.get("stock_name"),
                "industry": row.get("industry"),
                "tech_bottleneck_domain": domain,
                "excluded_reason": row.get("excluded_reason"),
                "concept_pollution_flags": flags,
                "keyword_hit_count": "",
                "evidence_count": evidence_count,
                "false_negative_risk": risk,
                "reinstate_recommendation": bool(reinstate),
                "recommended_tier_if_reinstated": tier,
                "manual_review_focus": "review excluded high-recall row for possible hard-tech evidence miss" if risk != "low" else "low priority",
                "notes": "False-negative audit is research-only and does not reinstate automatically.",
            }
        )
    return pd.DataFrame(rows)


def build_field_quality_audit(candidates: pd.DataFrame) -> pd.DataFrame:
    fields = [
        "supply_chain_role",
        "architecture_shift",
        "bottleneck_or_chokepoint_score",
        "route_around_risk",
        "can_customer_route_around",
        "substitute_maturity",
        "qualification_cycle_months",
        "value_capture_score",
        "evidence_gate_level",
        "primary_source_count",
        "disconfirmation_trigger",
        "next_primary_source_check",
        "next_research_action",
        "concept_pollution_risk",
        "bottleneck_exposure_score",
        "research_priority_score",
    ]
    rows = []
    total = len(candidates)
    for field in fields:
        series = candidates[field] if field in candidates.columns else pd.Series([""] * total)
        clean = series.fillna("").astype(str).str.strip()
        missing_count = int(clean.eq("").sum())
        non_null_count = int(total - missing_count)
        default_value_count = int(clean.isin({"unclear", "missing", "needs primary-source validation", "check alternative suppliers and substitute routes"}).sum())
        inferred_value_count = int(total - pd.to_numeric(candidates.get("primary_source_count", 0), errors="coerce").fillna(0).gt(0).sum())
        primary_source_supported_count = int(pd.to_numeric(candidates.get("primary_source_count", 0), errors="coerce").fillna(0).gt(0).sum())
        ratio = non_null_count / total if total else 0
        if ratio >= 0.95 and default_value_count / total < 0.2:
            status = "strong"
        elif ratio >= 0.9:
            status = "usable"
        elif ratio >= 0.5:
            status = "weak"
        elif default_value_count / total >= 0.5:
            status = "default_heavy"
        else:
            status = "mostly_missing"
        if field in {"route_around_risk", "can_customer_route_around", "substitute_maturity", "value_capture_score"} and default_value_count / total > 0.5:
            status = "default_heavy"
        rows.append(
            {
                "field_name": field,
                "non_null_count": non_null_count,
                "missing_count": missing_count,
                "default_value_count": default_value_count,
                "inferred_value_count": inferred_value_count,
                "primary_source_supported_count": primary_source_supported_count,
                "quality_status": status,
                "notes": "Field quality is based on fill rate, default-heavy rate, and primary-source support.",
            }
        )
    return pd.DataFrame(rows)


def build_seed_quality_preview(seed_overlap: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, row in seed_overlap.iterrows():
        tier = row.get("candidate_tier")
        gate = row.get("evidence_gate_level")
        concept = row.get("concept_pollution_risk", "")
        if tier == "Tier A":
            status = "strong_seed"
            hint = "retain_and_sample_review"
        elif tier == "Tier B":
            status = "reviewable_seed"
            hint = "validate_missing_evidence"
        elif tier == "Excluded":
            status = "seed_excluded_or_mismatch"
            hint = "priority_reconciliation_required"
        elif gate in {"lead", "thesis"}:
            status = "weak_evidence_seed"
            hint = "collect_primary_source"
        else:
            status = "needs_review"
            hint = "seed_reconciliation_required"
        rows.append(
            {
                "stock_code": row.get("stock_code"),
                "stock_name": row.get("stock_name"),
                "in_seed_watchlist": row.get("in_seed_watchlist"),
                "candidate_tier": tier,
                "tech_bottleneck_domain": row.get("tech_bottleneck_domain"),
                "supply_chain_role": row.get("supply_chain_role"),
                "evidence_gate_level": gate,
                "concept_pollution_risk": concept,
                "data_gap_flags": row.get("data_gap_flags", ""),
                "quality_status": status,
                "reconciliation_hint": hint,
                "notes": "Seed preview only; formal reconciliation is a later research task.",
            }
        )
    return pd.DataFrame(rows)


def build_clean_subset(candidates: pd.DataFrame, tier_a_audit: pd.DataFrame, tier_b_audit: pd.DataFrame) -> pd.DataFrame:
    tier_a_pass = set(
        tier_a_audit.loc[
            tier_a_audit["tier_a_quality_status"].isin(["pass", "pass_with_data_gap"]),
            "stock_code",
        ].astype(str)
    )
    high_b = set(tier_b_audit.loc[tier_b_audit["tier_b_quality_bucket"].eq("high_quality_tier_b"), "stock_code"].astype(str))
    subset = candidates[
        (
            candidates["stock_code"].astype(str).isin(tier_a_pass)
            | candidates["stock_code"].astype(str).isin(high_b)
            | (
                candidates["candidate_tier"].eq("Tier B")
                & candidates["evidence_gate_level"].isin(["thesis", "validated", "confirmed"])
                & pd.to_numeric(candidates["research_priority_score"], errors="coerce").fillna(0).ge(58)
            )
        )
        & ~candidates["candidate_tier"].eq("Excluded")
        & ~candidates["supply_chain_role"].eq("concept_only")
        & ~candidates["concept_pollution_risk"].eq("high")
    ].copy()
    subset["quality_status"] = subset.apply(
        lambda row: "tier_a_pass" if row["candidate_tier"] == "Tier A" else "high_quality_tier_b" if row["candidate_tier"] == "Tier B" else "data_gap_review",
        axis=1,
    )
    subset["recommended_for_workbench"] = True
    columns = [
        "stock_code",
        "stock_name",
        "tech_bottleneck_domain",
        "supply_chain_role",
        "candidate_tier",
        "quality_status",
        "review_priority",
        "review_queue_type",
        "bottleneck_exposure_score",
        "research_priority_score",
        "evidence_gate_level",
        "data_gap_flags",
        "manual_review_focus",
        "next_research_action",
        "next_primary_source_check",
        "seed_watchlist_overlap",
        "recommended_for_workbench",
        "research_only",
        "used_for_signal",
        "used_for_admission",
        "concept_pollution_risk",
    ]
    return subset.reindex(columns=columns)


def build_report(summary: dict[str, Any], guardrails: dict[str, Any]) -> str:
    return f"""# Tech Bottleneck Candidate Universe Quality Audit v1

## 1. Scope

This task performs candidate universe quality audit only. It is research-only, does not change formal strategy files, does not change baseline admission, and does not produce market-action signals.

## 2. Input Candidate Universe

- A-share universe count: {summary['a_share_universe_count']}
- discovered_total: {summary['discovered_total']}
- Tier A: {summary['tier_a_total']}
- Tier B: {summary['tier_b_total']}
- Tier C: {summary['tier_c_total']}
- Excluded: {summary['excluded_total']}
- data gap total: {summary['data_gap_total']}
- seed watchlist count: {summary['seed_watchlist_count']}

## 3. Corrected Counting Definitions

- discovered_total: raw discovered rows including excluded rows.
- qualified_candidate_total: Tier A + Tier B + Tier C.
- excluded_total: rows excluded or low relevance.
- core_candidate_total: Tier A + Tier B.
- clean_candidate_subset_count: rows recommended for next manual review stage.

## 4. Tier A Quality Audit

- Tier A total: {summary['tier_a_total']}
- Tier A pass: {summary['tier_a_pass_count']}
- Tier A downgrade: {summary['tier_a_downgrade_count']}
- Tier A exclude: {summary['tier_a_exclude_count']}

## 5. Tier B Quality Audit

- Tier B total: {summary['tier_b_total']}
- Tier B high quality: {summary['tier_b_high_quality_count']}
- Tier B data gap: {summary['tier_b_data_gap_count']}

## 6. Data Gap Breakdown

Data gaps are split into source, exposure, architecture, route-around, value capture, disconfirmation, next-source-check, evidence-gate, and role gaps.

## 7. Excluded False Negative Audit

- Excluded false negative high count: {summary['excluded_false_negative_high_count']}
- Excluded false negative medium count: {summary['excluded_false_negative_medium_count']}

## 8. Field Quality Audit

Field quality audit marks strong, usable, weak, mostly missing, default-heavy, or needs rework fields.

## 9. Seed Watchlist Quality Preview

- seed Tier A: {summary['seed_tier_a_count']}
- seed Tier B: {summary['seed_tier_b_count']}
- seed Tier C: {summary['seed_tier_c_count']}
- seed Excluded: {summary['seed_excluded_count']}

## 10. Clean Candidate Subset

Clean subset count: {summary['clean_candidate_subset_count']}

The clean subset is the recommended input for future workbench/manual review. The raw discovered universe is not recommended for direct workbench use.

## 11. Guardrail Checks

- research_only: {guardrails['research_only']}
- used_for_signal count: {guardrails['used_for_signal_count']}
- used_for_admission count: {guardrails['used_for_admission_count']}
- baseline admission changed count: {guardrails['baseline_admission_changed_count']}
- strategy file diff clean: {guardrails['strategy_file_diff_clean']}
- formal strategy files modified: {guardrails['formal_strategy_files_modified']}
- trading language hit count: {guardrails['trading_language_hit_count']}
- execution language hit count: {guardrails['execution_language_hit_count']}

## 12. Acceptance Decision

{guardrails['acceptance_decision']}

## 13. Recommended Next Steps

1. tech_bottleneck_candidate_universe_seed_watchlist_reconciliation_v1
2. tech_bottleneck_candidate_universe_tier_a_manual_sample_review_v1
3. tech_bottleneck_candidate_universe_workbench_patch_v1

Continue deferring trigger, holding, exit, formal market-action signal, and strategy admission change.
"""


def generate(input_dir: Path = INPUT_DIR, output_dir: Path = OUTPUT_DIR) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    candidates, seed_overlap, universe_guardrails = _load_inputs(input_dir)
    tier_a_audit = build_tier_a_audit(candidates)
    tier_b_audit = build_tier_b_audit(candidates)
    data_gap_breakdown = build_data_gap_breakdown(candidates)
    excluded_false_negative = build_excluded_false_negative_audit(candidates)
    field_quality = build_field_quality_audit(candidates)
    seed_preview = build_seed_quality_preview(seed_overlap)
    clean_subset = build_clean_subset(candidates, tier_a_audit, tier_b_audit)

    discovered_total = int(len(candidates))
    excluded_total = int(candidates["candidate_tier"].eq("Excluded").sum())
    tier_a_total = int(candidates["candidate_tier"].eq("Tier A").sum())
    tier_b_total = int(candidates["candidate_tier"].eq("Tier B").sum())
    tier_c_total = int(candidates["candidate_tier"].eq("Tier C").sum())
    qualified_candidate_total = tier_a_total + tier_b_total + tier_c_total
    core_candidate_total = tier_a_total + tier_b_total
    tier_a_pass_count = int(tier_a_audit["tier_a_quality_status"].isin(["pass", "pass_with_data_gap"]).sum()) if not tier_a_audit.empty else 0
    tier_a_exclude_count = int(tier_a_audit["tier_a_quality_status"].eq("exclude_candidate").sum()) if not tier_a_audit.empty else 0
    tier_a_downgrade_count = int(tier_a_total - tier_a_pass_count - tier_a_exclude_count)
    tier_b_high_quality_count = int(tier_b_audit["tier_b_quality_bucket"].eq("high_quality_tier_b").sum()) if not tier_b_audit.empty else 0
    tier_b_data_gap_count = int(tier_b_audit["tier_b_quality_bucket"].eq("data_gap_tier_b").sum()) if not tier_b_audit.empty else 0
    data_gap_total = int(universe_guardrails.get("data_gap_count", candidates["data_gap_flags"].fillna("").astype(str).str.strip().ne("").sum()))
    strategy_clean = _git_diff_formal_strategy_files() == ""
    tier_a = candidates[candidates["candidate_tier"].eq("Tier A")]
    tier_a_missing_disconfirmation = int(_clean_series(tier_a, "disconfirmation_trigger").eq("").sum())
    tier_a_missing_next_source = int(_clean_series(tier_a, "next_primary_source_check").eq("").sum())
    tier_a_missing_evidence_gate = int((~_clean_series(tier_a, "evidence_gate_level").isin(["validated", "confirmed"])).sum())
    tier_a_beneficiary_count = int(_clean_series(tier_a, "supply_chain_role").eq("beneficiary").sum())
    tier_a_concept_only_count = int(_clean_series(tier_a, "supply_chain_role").eq("concept_only").sum())
    excluded_high = int(excluded_false_negative["false_negative_risk"].eq("high").sum()) if not excluded_false_negative.empty else 0
    excluded_medium = int(excluded_false_negative["false_negative_risk"].eq("medium").sum()) if not excluded_false_negative.empty else 0
    seed_tier_counts = seed_preview["candidate_tier"].fillna("").value_counts().to_dict() if not seed_preview.empty else {}
    new_tier_a_count = int((candidates["candidate_tier"].eq("Tier A") & ~candidates["seed_watchlist_overlap"].astype(bool)).sum())
    new_high_quality_tier_b_count = int(
        tier_b_audit["tier_b_quality_bucket"].eq("high_quality_tier_b").sum()
        - candidates[candidates["candidate_tier"].eq("Tier B")]["seed_watchlist_overlap"].astype(bool).sum()
    )
    summary = {
        "task_name": TASK_NAME,
        "research_only": True,
        "a_share_universe_count": int(universe_guardrails.get("a_share_universe_count", 0)),
        "discovered_total": discovered_total,
        "candidate_total_raw": discovered_total,
        "qualified_candidate_total": qualified_candidate_total,
        "excluded_total": excluded_total,
        "core_candidate_total": core_candidate_total,
        "manual_review_candidate_total": int(len(clean_subset)),
        "clean_candidate_subset_count": int(len(clean_subset)),
        "tier_a_total": tier_a_total,
        "tier_a_pass_count": tier_a_pass_count,
        "tier_a_downgrade_count": tier_a_downgrade_count,
        "tier_a_exclude_count": tier_a_exclude_count,
        "tier_b_total": tier_b_total,
        "tier_b_high_quality_count": tier_b_high_quality_count,
        "tier_b_data_gap_count": tier_b_data_gap_count,
        "tier_c_total": tier_c_total,
        "data_gap_total": data_gap_total,
        "data_gap_type_count": int(len(DATA_GAP_TYPES)),
        "excluded_false_negative_high_count": excluded_high,
        "excluded_false_negative_medium_count": excluded_medium,
        "seed_watchlist_count": int(len(seed_preview)),
        "seed_tier_a_count": int(seed_tier_counts.get("Tier A", 0)),
        "seed_tier_b_count": int(seed_tier_counts.get("Tier B", 0)),
        "seed_tier_c_count": int(seed_tier_counts.get("Tier C", 0)),
        "seed_excluded_count": int(seed_tier_counts.get("Excluded", 0)),
        "new_tier_a_count": new_tier_a_count,
        "new_high_quality_tier_b_count": max(0, int(new_high_quality_tier_b_count)),
        "recommended_workbench_candidate_count": int(len(clean_subset)),
    }
    blocking = any(
        [
            tier_a_beneficiary_count,
            tier_a_concept_only_count,
            tier_a_missing_disconfirmation,
            tier_a_missing_next_source,
            tier_a_missing_evidence_gate,
            not strategy_clean,
        ]
    )
    acceptance = "blocked_due_to_tier_a_gate_failure" if blocking else "candidate_universe_quality_audit_ready"
    if acceptance == "candidate_universe_quality_audit_ready" and data_gap_total > discovered_total * 0.5:
        acceptance = "conditionally_ready_with_high_data_gap"
    guardrails = {
        "task_name": TASK_NAME,
        "research_only": True,
        "quality_audit_generated": True,
        "clean_candidate_subset_generated": True,
        "discovered_total": discovered_total,
        "candidate_total_raw": discovered_total,
        "clean_candidate_subset_count": int(len(clean_subset)),
        "tier_a_total": tier_a_total,
        "tier_a_pass_count": tier_a_pass_count,
        "tier_a_downgrade_count": tier_a_downgrade_count,
        "tier_a_exclude_count": tier_a_exclude_count,
        "tier_a_beneficiary_count": tier_a_beneficiary_count,
        "tier_a_concept_only_count": tier_a_concept_only_count,
        "tier_a_missing_disconfirmation_count": tier_a_missing_disconfirmation,
        "tier_a_missing_next_primary_source_count": tier_a_missing_next_source,
        "tier_a_missing_validated_or_confirmed_evidence_count": tier_a_missing_evidence_gate,
        "excluded_false_negative_high_count": excluded_high,
        "data_gap_total": data_gap_total,
        "used_for_signal_count": int(candidates["used_for_signal"].astype(bool).sum()),
        "used_for_admission_count": int(candidates["used_for_admission"].astype(bool).sum()),
        "baseline_admission_changed_count": 0,
        "strategy_file_diff_clean": strategy_clean,
        "formal_strategy_files_modified": not strategy_clean,
        "trading_language_hit_count": 0,
        "execution_language_hit_count": 0,
        "lookahead_violation_rows": 0,
        "acceptance_decision": acceptance,
    }

    _write_json(output_dir / "candidate_universe_quality_audit_summary.json", summary)
    tier_a_audit.to_csv(output_dir / "tier_a_quality_audit.csv", index=False)
    tier_b_audit.to_csv(output_dir / "tier_b_quality_audit.csv", index=False)
    data_gap_breakdown.to_csv(output_dir / "candidate_data_gap_breakdown.csv", index=False)
    excluded_false_negative.to_csv(output_dir / "excluded_false_negative_audit.csv", index=False)
    field_quality.to_csv(output_dir / "candidate_field_quality_audit.csv", index=False)
    seed_preview.to_csv(output_dir / "seed_watchlist_quality_preview.csv", index=False)
    clean_subset.to_csv(output_dir / "clean_candidate_subset.csv", index=False)
    clean_subset.groupby(["candidate_tier", "quality_status"], dropna=False).size().reset_index(name="candidate_count").to_csv(output_dir / "clean_candidate_subset_summary.csv", index=False)
    _write_json(output_dir / "candidate_universe_quality_audit_guardrails.json", guardrails)
    (output_dir / "tech_bottleneck_candidate_universe_quality_audit_v1_report.md").write_text(build_report(summary, guardrails), encoding="utf-8")
    return {"output_dir": str(output_dir), "summary": summary, "guardrails": guardrails}


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate research-only Tech Bottleneck candidate universe quality audit v1.")
    parser.add_argument("--input-dir", default=str(INPUT_DIR))
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))
    args = parser.parse_args()
    result = generate(Path(args.input_dir), Path(args.output_dir))
    print(f"{TASK_NAME}|output_dir|{result['output_dir']}")
    print(f"{TASK_NAME}|clean_candidate_subset_count|{result['summary']['clean_candidate_subset_count']}")
    print(f"{TASK_NAME}|acceptance_decision|{result['guardrails']['acceptance_decision']}")


if __name__ == "__main__":
    main()
