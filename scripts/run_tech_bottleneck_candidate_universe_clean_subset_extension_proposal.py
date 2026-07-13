#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
VERIFICATION_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_candidate_universe_true_rescue_primary_source_verification_v1"
RECONCILIATION_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_candidate_universe_seed_tier_b_reconciliation_v1"
QUALITY_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_candidate_universe_quality_audit_v1"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_candidate_universe_clean_subset_extension_proposal_v1"
TASK_NAME = "tech_bottleneck_candidate_universe_clean_subset_extension_proposal_v1"
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def _git_diff_formal_strategy_files() -> str:
    result = subprocess.run(["git", "diff", "--", *FORMAL_STRATEGY_FILES], cwd=PROJECT_ROOT, text=True, capture_output=True, check=False)
    return result.stdout or result.stderr or ""


def _load_inputs(verification_dir: Path, reconciliation_dir: Path, quality_dir: Path) -> dict[str, Any]:
    return {
        "verification_summary": json.loads((verification_dir / "true_rescue_primary_source_verification_summary.json").read_text(encoding="utf-8")),
        "evidence_matrix": pd.read_csv(verification_dir / "true_rescue_primary_source_evidence_matrix.csv"),
        "verified": pd.read_csv(verification_dir / "verified_rescue_candidates.csv"),
        "insufficient": pd.read_csv(verification_dir / "evidence_insufficient_rescue_candidates.csv"),
        "adjacent": pd.read_csv(verification_dir / "downgrade_to_adjacent_watchlist.csv"),
        "rejected": pd.read_csv(verification_dir / "rejected_seed_pollution_candidates.csv"),
        "reconciliation": pd.read_csv(reconciliation_dir / "seed_tier_b_reconciliation.csv"),
        "true_rescue": pd.read_csv(reconciliation_dir / "seed_tier_b_true_rescue_candidates.csv"),
        "evidence_backfill": pd.read_csv(reconciliation_dir / "seed_tier_b_evidence_backfill_required.csv"),
        "clean_subset": pd.read_csv(quality_dir / "clean_candidate_subset.csv"),
        "tier_a_quality": pd.read_csv(quality_dir / "tier_a_quality_audit.csv"),
        "tier_b_quality": pd.read_csv(quality_dir / "tier_b_quality_audit.csv"),
        "field_quality": pd.read_csv(quality_dir / "candidate_field_quality_audit.csv"),
        "gap_breakdown": pd.read_csv(quality_dir / "candidate_data_gap_breakdown.csv"),
        "quality_summary": json.loads((quality_dir / "candidate_universe_quality_audit_summary.json").read_text(encoding="utf-8")),
        "quality_guardrails": json.loads((quality_dir / "candidate_universe_quality_audit_guardrails.json").read_text(encoding="utf-8")),
    }


def build_proposed_additions(verified: pd.DataFrame, tier_b_quality: pd.DataFrame, clean_subset: pd.DataFrame) -> pd.DataFrame:
    clean_codes = set(clean_subset["stock_code"].astype(str))
    tier_b_lookup = tier_b_quality.set_index(tier_b_quality["stock_code"].astype(str), drop=False)
    rows = []
    for _, row in verified.sort_values("stock_code").iterrows():
        code = str(row["stock_code"])
        quality = tier_b_lookup.loc[code] if code in tier_b_lookup.index else {}
        duplicate = code in clean_codes
        rows.append(
            {
                "stock_code": row.get("stock_code"),
                "stock_name": row.get("stock_name"),
                "previous_tier": "Tier B",
                "original_failure_reason": quality.get("tier_b_quality_bucket", "seed_true_rescue_verified"),
                "original_data_gap_type": quality.get("data_gap_flags", ""),
                "research_priority_score": quality.get("research_priority_score", ""),
                "verification_decision": row.get("verification_decision"),
                "evidence_strength": row.get("evidence_strength"),
                "bottleneck_relevance": row.get("bottleneck_relevance"),
                "evidence_category": row.get("evidence_category"),
                "primary_source_title": row.get("primary_source_title"),
                "primary_source_type": row.get("primary_source_type"),
                "primary_source_url": row.get("source_location_or_url"),
                "exact_supporting_excerpt": row.get("exact_supporting_excerpt"),
                "proposed_clean_subset_status": "proposed_addition",
                "proposal_reason": "Primary-source verification upgraded this seed Tier B rescue candidate to proposal-only clean-subset extension review.",
                "remaining_risk": "manual approval, source sampling, revenue traceability, substitution difficulty, and value-capture checks remain required",
                "manual_approval_required": True,
                "duplicate_with_current_clean_subset": duplicate,
                "auto_promote": False,
                "research_only": True,
                "used_for_signal": False,
                "used_for_admission": False,
            }
        )
    return pd.DataFrame(rows)


def build_not_proposed(evidence_matrix: pd.DataFrame, tier_b_quality: pd.DataFrame) -> pd.DataFrame:
    not_proposed = evidence_matrix[~evidence_matrix["verification_decision"].eq("verified_rescue_candidate")].copy()
    tier_b_lookup = tier_b_quality.set_index(tier_b_quality["stock_code"].astype(str), drop=False)
    rows = []
    for _, row in not_proposed.sort_values("stock_code").iterrows():
        code = str(row["stock_code"])
        quality = tier_b_lookup.loc[code] if code in tier_b_lookup.index else {}
        if row.get("verification_decision") == "evidence_insufficient":
            decision = "evidence_backfill_required"
        else:
            decision = row.get("verification_decision")
        rows.append(
            {
                "stock_code": row.get("stock_code"),
                "stock_name": row.get("stock_name"),
                "previous_tier": "Tier B",
                "original_failure_reason": quality.get("tier_b_quality_bucket", "seed_true_rescue_not_verified"),
                "original_data_gap_type": quality.get("data_gap_flags", ""),
                "research_priority_score": quality.get("research_priority_score", ""),
                "verification_decision": row.get("verification_decision"),
                "evidence_strength": row.get("evidence_strength"),
                "bottleneck_relevance": row.get("bottleneck_relevance"),
                "evidence_category": row.get("evidence_category"),
                "primary_source_title": row.get("primary_source_title"),
                "primary_source_type": row.get("primary_source_type"),
                "primary_source_url": row.get("source_location_or_url"),
                "exact_supporting_excerpt": row.get("exact_supporting_excerpt"),
                "proposal_decision": decision,
                "proposed_clean_subset_status": "not_proposed",
                "proposal_reason": "Primary-source verification did not establish enough bottleneck evidence for clean-subset extension proposal.",
                "remaining_risk": "requires additional primary-source evidence before reconsideration",
                "manual_approval_required": False,
                "auto_promote": False,
                "research_only": True,
                "used_for_signal": False,
                "used_for_admission": False,
            }
        )
    return pd.DataFrame(rows)


def build_diff_preview(clean_subset: pd.DataFrame, proposed: pd.DataFrame) -> pd.DataFrame:
    existing = clean_subset.copy()
    existing["diff_action"] = "existing_clean_subset"
    for col in ["manual_approval_required", "auto_promote", "used_for_signal", "used_for_admission"]:
        if col not in existing.columns:
            existing[col] = False
    existing["manual_approval_required"] = False
    existing["auto_promote"] = False
    existing["research_only"] = True
    proposed_preview = proposed.copy()
    proposed_preview["candidate_tier"] = proposed_preview["previous_tier"]
    proposed_preview["quality_status"] = "verified_rescue_extension_proposal"
    proposed_preview["review_priority"] = "manual_approval_required"
    proposed_preview["review_queue_type"] = "primary_source_verified_rescue_review"
    proposed_preview["seed_watchlist_overlap"] = True
    proposed_preview["recommended_for_workbench"] = False
    proposed_preview["diff_action"] = "proposed_addition"
    preview_columns = [
        "stock_code",
        "stock_name",
        "candidate_tier",
        "quality_status",
        "review_priority",
        "review_queue_type",
        "seed_watchlist_overlap",
        "recommended_for_workbench",
        "manual_approval_required",
        "auto_promote",
        "research_only",
        "used_for_signal",
        "used_for_admission",
        "diff_action",
    ]
    return pd.concat([existing.reindex(columns=preview_columns), proposed_preview.reindex(columns=preview_columns)], ignore_index=True)


def build_report(summary: dict[str, Any], proposed: pd.DataFrame, not_proposed: pd.DataFrame) -> str:
    proposed_names = ", ".join(proposed["stock_name"].astype(str)) if not proposed.empty else "none"
    not_names = ", ".join(not_proposed["stock_name"].astype(str)) if not not_proposed.empty else "none"
    return f"""# Tech Bottleneck Candidate Universe Clean Subset Extension Proposal v1

## 1. Scope

This is a research-only proposal. It does not modify formal strategy files, admission logic, signal logic, scoring logic, production candidate universe, or the existing clean_candidate_subset.csv.

## 2. Proposed Additions

Verified rescue candidates proposed for future clean-subset extension: {proposed_names}.

## 3. Not Proposed

True-rescue candidates not proposed after primary-source verification: {not_names}.

## 4. Count Impact

- current clean subset count: {summary['current_clean_subset_count']}
- proposed addition count: {summary['proposed_addition_count']}
- duplicate count: {summary['duplicate_count']}
- net new count: {summary['net_new_count']}
- proposed clean subset count: {summary['proposed_clean_subset_count']}

## 5. Promotion Policy

Auto-promote count: {summary['auto_promote_count']}. Expected answer: no.

Manual approval required count: {summary['manual_approval_required_count']}. Expected answer: yes for all proposed additions.

## 6. Guardrails

- used_for_signal count: {summary['used_for_signal_count']}
- used_for_admission count: {summary['used_for_admission_count']}
- baseline admission changed count: {summary['baseline_admission_changed_count']}
- strategy file diff clean: {summary['strategy_file_diff_clean']}

## 7. Acceptance

{summary['acceptance_decision']}
"""


def generate(
    verification_dir: Path = VERIFICATION_DIR,
    reconciliation_dir: Path = RECONCILIATION_DIR,
    quality_dir: Path = QUALITY_DIR,
    output_dir: Path = OUTPUT_DIR,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    inputs = _load_inputs(verification_dir, reconciliation_dir, quality_dir)
    proposed = build_proposed_additions(inputs["verified"], inputs["tier_b_quality"], inputs["clean_subset"])
    not_proposed = build_not_proposed(inputs["evidence_matrix"], inputs["tier_b_quality"])
    diff_preview = build_diff_preview(inputs["clean_subset"], proposed)
    current_count = int(len(inputs["clean_subset"]))
    duplicate_count = int(proposed["duplicate_with_current_clean_subset"].astype(bool).sum()) if not proposed.empty else 0
    net_new_count = int(len(proposed) - duplicate_count)
    strategy_clean = _git_diff_formal_strategy_files() == ""
    used_for_signal_count = int(proposed["used_for_signal"].astype(bool).sum() + not_proposed["used_for_signal"].astype(bool).sum())
    used_for_admission_count = int(proposed["used_for_admission"].astype(bool).sum() + not_proposed["used_for_admission"].astype(bool).sum())
    auto_promote_count = int(proposed["auto_promote"].astype(bool).sum() + not_proposed["auto_promote"].astype(bool).sum())
    manual_approval_required_count = int(proposed["manual_approval_required"].astype(bool).sum()) if not proposed.empty else 0

    summary = {
        "task_name": TASK_NAME,
        "research_only": True,
        "current_clean_subset_count": current_count,
        "proposed_addition_count": int(len(proposed)),
        "proposed_clean_subset_count": current_count + net_new_count,
        "duplicate_count": duplicate_count,
        "net_new_count": net_new_count,
        "not_proposed_count": int(len(not_proposed)),
        "auto_promote_count": auto_promote_count,
        "manual_approval_required_count": manual_approval_required_count,
        "used_for_signal_count": used_for_signal_count,
        "used_for_admission_count": used_for_admission_count,
        "baseline_admission_changed_count": 0,
        "strategy_file_diff_clean": strategy_clean,
        "formal_strategy_files_modified": not strategy_clean,
        "acceptance_decision": "clean_subset_extension_proposal_ready" if strategy_clean and auto_promote_count == 0 else "blocked_due_to_guardrail_failure",
    }
    guardrails = {
        "task_name": TASK_NAME,
        "research_only": True,
        "used_for_signal_count": used_for_signal_count,
        "used_for_admission_count": used_for_admission_count,
        "baseline_admission_changed_count": 0,
        "auto_promote_count": auto_promote_count,
        "manual_approval_required_count": manual_approval_required_count,
        "strategy_file_diff_clean": strategy_clean,
        "formal_strategy_files_modified": not strategy_clean,
        "existing_clean_subset_modified_in_place": False,
        "acceptance_decision": summary["acceptance_decision"],
    }

    _write_json(output_dir / "clean_subset_extension_proposal_summary.json", summary)
    proposed.to_csv(output_dir / "proposed_clean_subset_additions.csv", index=False)
    not_proposed.to_csv(output_dir / "not_proposed_rescue_candidates.csv", index=False)
    diff_preview.to_csv(output_dir / "clean_subset_extension_diff_preview.csv", index=False)
    _write_json(output_dir / "clean_subset_extension_guardrails.json", guardrails)
    (output_dir / "tech_bottleneck_candidate_universe_clean_subset_extension_proposal_v1_report.md").write_text(build_report(summary, proposed, not_proposed), encoding="utf-8")
    return {"output_dir": str(output_dir), "summary": summary}


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate research-only clean subset extension proposal.")
    parser.add_argument("--verification-dir", default=str(VERIFICATION_DIR))
    parser.add_argument("--reconciliation-dir", default=str(RECONCILIATION_DIR))
    parser.add_argument("--quality-dir", default=str(QUALITY_DIR))
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))
    args = parser.parse_args()
    result = generate(Path(args.verification_dir), Path(args.reconciliation_dir), Path(args.quality_dir), Path(args.output_dir))
    print(f"{TASK_NAME}|output_dir|{result['output_dir']}")
    print(f"{TASK_NAME}|proposed_addition_count|{result['summary']['proposed_addition_count']}")
    print(f"{TASK_NAME}|auto_promote_count|{result['summary']['auto_promote_count']}")
    print(f"{TASK_NAME}|acceptance_decision|{result['summary']['acceptance_decision']}")


if __name__ == "__main__":
    main()
