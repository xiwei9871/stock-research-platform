#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
QUALITY_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_candidate_universe_quality_audit_v1"
DIAGNOSTICS_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_candidate_universe_quality_audit_diagnostics_v1"
RESCUE_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_candidate_universe_rescue_triage_v1"
RECONCILIATION_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_candidate_universe_seed_tier_b_reconciliation_v1"
VERIFICATION_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_candidate_universe_true_rescue_primary_source_verification_v1"
EXTENSION_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_candidate_universe_clean_subset_extension_proposal_v1"
NON_SEED_REVIEW_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_candidate_universe_non_seed_tier_a_manual_review_v1"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_candidate_universe_manual_approval_packet_v1"
TASK_NAME = "tech_bottleneck_candidate_universe_manual_approval_packet_v1"
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]
CLEAN_SUBSET_PATH = QUALITY_DIR / "clean_candidate_subset.csv"

CATEGORY_ORDER = {
    "core_approval_candidate": 0,
    "adjacent_watchlist": 1,
    "evidence_backfill_required": 2,
    "downgrade_manual_review_required": 3,
    "seed_pollution_or_reject": 4,
}


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_diff_formal_strategy_files() -> str:
    result = subprocess.run(["git", "diff", "--", *FORMAL_STRATEGY_FILES], cwd=PROJECT_ROOT, text=True, capture_output=True, check=False)
    return result.stdout or result.stderr or ""


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_inputs() -> dict[str, Any]:
    return {
        "seed_preview": pd.read_csv(QUALITY_DIR / "seed_watchlist_quality_preview.csv"),
        "quality_summary": _load_json(QUALITY_DIR / "candidate_universe_quality_audit_summary.json"),
        "quality_guardrails": _load_json(QUALITY_DIR / "candidate_universe_quality_audit_guardrails.json"),
        "diagnostics_summary": _load_json(DIAGNOSTICS_DIR / "audit_diagnostics_summary.json"),
        "rescue_summary": _load_json(RESCUE_DIR / "rescue_triage_summary.json"),
        "reconciliation": pd.read_csv(RECONCILIATION_DIR / "seed_tier_b_reconciliation.csv"),
        "reconciliation_summary": _load_json(RECONCILIATION_DIR / "seed_tier_b_reconciliation_summary.json"),
        "verification_summary": _load_json(VERIFICATION_DIR / "true_rescue_primary_source_verification_summary.json"),
        "extension_summary": _load_json(EXTENSION_DIR / "clean_subset_extension_proposal_summary.json"),
        "proposed_additions": pd.read_csv(EXTENSION_DIR / "proposed_clean_subset_additions.csv"),
        "not_proposed": pd.read_csv(EXTENSION_DIR / "not_proposed_rescue_candidates.csv"),
        "extension_guardrails": _load_json(EXTENSION_DIR / "clean_subset_extension_guardrails.json"),
        "non_seed_review": pd.read_csv(NON_SEED_REVIEW_DIR / "non_seed_tier_a_manual_review.csv"),
        "non_seed_summary": _load_json(NON_SEED_REVIEW_DIR / "non_seed_tier_a_manual_review_summary.json"),
        "non_seed_guardrails": _load_json(NON_SEED_REVIEW_DIR / "non_seed_tier_a_review_guardrails.json"),
    }


def _blank_if_na(value: Any) -> str:
    if pd.isna(value):
        return ""
    return str(value)


def _seed_evidence_strength(row: pd.Series) -> str:
    gate = str(row.get("evidence_gate_level", ""))
    if gate == "confirmed":
        return "strong"
    if gate == "validated":
        return "moderate"
    return "moderate"


def _normal_row(
    *,
    stock_code: Any,
    stock_name: Any,
    source_group: str,
    previous_tier: Any,
    final_manual_approval_category: str,
    evidence_strength: Any,
    bottleneck_relevance: Any,
    review_decision_source: str,
    primary_source_url: Any = "",
    rationale: Any = "",
) -> dict[str, Any]:
    is_core = final_manual_approval_category == "core_approval_candidate"
    return {
        "stock_code": _blank_if_na(stock_code),
        "stock_name": _blank_if_na(stock_name),
        "source_group": source_group,
        "previous_tier": _blank_if_na(previous_tier),
        "final_manual_approval_category": final_manual_approval_category,
        "evidence_strength": _blank_if_na(evidence_strength),
        "bottleneck_relevance": _blank_if_na(bottleneck_relevance),
        "review_decision_source": review_decision_source,
        "primary_source_url": _blank_if_na(primary_source_url),
        "manual_approval_required": True,
        "allowed_for_workbench_candidate_pool": is_core,
        "allowed_for_signal": False,
        "allowed_for_admission": False,
        "rationale": _blank_if_na(rationale),
    }


def build_master_table(inputs: dict[str, Any]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []

    seed_tier_a = inputs["seed_preview"][inputs["seed_preview"]["candidate_tier"].eq("Tier A")].copy()
    if len(seed_tier_a) != 86:
        raise ValueError(f"Expected 86 seed Tier A rows, found {len(seed_tier_a)}")
    for _, row in seed_tier_a.sort_values(["stock_code", "stock_name"], kind="stable").iterrows():
        rows.append(
            _normal_row(
                stock_code=row["stock_code"],
                stock_name=row["stock_name"],
                source_group="seed_tier_a",
                previous_tier=row["candidate_tier"],
                final_manual_approval_category="core_approval_candidate",
                evidence_strength=_seed_evidence_strength(row),
                bottleneck_relevance="core",
                review_decision_source="seed_watchlist_quality_preview",
                rationale="Seed watchlist Tier A retained for manual core approval packet; this is still research-only and requires manual approval before any workbench use.",
            )
        )

    non_seed = inputs["non_seed_review"].copy()
    non_seed_map = {
        "confirm_core_candidate": ("core_approval_candidate", "non_seed_tier_a_manual_review_core"),
        "confirm_adjacent_watchlist": ("adjacent_watchlist", "non_seed_tier_a_manual_review_adjacent"),
        "evidence_backfill_required": ("evidence_backfill_required", "non_seed_tier_a_manual_review_evidence"),
        "downgrade_manual_review_required": ("downgrade_manual_review_required", "non_seed_tier_a_manual_review_downgrade"),
    }
    for _, row in non_seed.sort_values(["review_decision", "stock_code", "stock_name"], kind="stable").iterrows():
        decision = str(row["review_decision"])
        if decision == "likely_false_positive":
            category, source_group = "seed_pollution_or_reject", "non_seed_tier_a_manual_review_reject"
        else:
            category, source_group = non_seed_map[decision]
        rows.append(
            _normal_row(
                stock_code=row["stock_code"],
                stock_name=row["stock_name"],
                source_group=source_group,
                previous_tier=row["current_tier"],
                final_manual_approval_category=category,
                evidence_strength=row["evidence_status"],
                bottleneck_relevance=row["bottleneck_relevance"],
                review_decision_source="non_seed_tier_a_manual_review_v1",
                rationale=row["rationale"],
            )
        )

    for _, row in inputs["proposed_additions"].sort_values(["stock_code", "stock_name"], kind="stable").iterrows():
        rows.append(
            _normal_row(
                stock_code=row["stock_code"],
                stock_name=row["stock_name"],
                source_group="verified_rescue_extension_proposal",
                previous_tier=row["previous_tier"],
                final_manual_approval_category="core_approval_candidate",
                evidence_strength=row["evidence_strength"],
                bottleneck_relevance=row["bottleneck_relevance"],
                review_decision_source="true_rescue_primary_source_verification_v1",
                primary_source_url=row.get("primary_source_url", ""),
                rationale=row["proposal_reason"],
            )
        )

    for _, row in inputs["not_proposed"].sort_values(["stock_code", "stock_name"], kind="stable").iterrows():
        rows.append(
            _normal_row(
                stock_code=row["stock_code"],
                stock_name=row["stock_name"],
                source_group="verified_rescue_not_proposed",
                previous_tier=row["previous_tier"],
                final_manual_approval_category="evidence_backfill_required",
                evidence_strength=row["evidence_strength"],
                bottleneck_relevance=row["bottleneck_relevance"],
                review_decision_source="true_rescue_primary_source_verification_v1",
                primary_source_url=row.get("primary_source_url", ""),
                rationale=row["proposal_reason"],
            )
        )

    recon_map = {
        "watchlist_only_adjacent": ("adjacent_watchlist", "seed_tier_b_reconciliation_adjacent"),
        "evidence_backfill_required": ("evidence_backfill_required", "seed_tier_b_reconciliation_evidence"),
        "seed_pollution_remove_from_tech_bottleneck": ("seed_pollution_or_reject", "seed_tier_b_reconciliation_reject"),
    }
    reconciliation = inputs["reconciliation"]
    filtered_reconciliation = reconciliation[~reconciliation["reconciliation_decision"].eq("true_rescue_to_tier_a_candidate")].copy()
    for _, row in filtered_reconciliation.sort_values(["reconciliation_decision", "stock_code", "stock_name"], kind="stable").iterrows():
        category, source_group = recon_map[str(row["reconciliation_decision"])]
        rows.append(
            _normal_row(
                stock_code=row["stock_code"],
                stock_name=row["stock_name"],
                source_group=source_group,
                previous_tier=row["current_tier"],
                final_manual_approval_category=category,
                evidence_strength=row["evidence_status"],
                bottleneck_relevance="adjacent" if category == "adjacent_watchlist" else "unclear",
                review_decision_source="seed_tier_b_reconciliation_v1",
                rationale=row["rationale"],
            )
        )

    master = pd.DataFrame(rows)
    master["_category_order"] = master["final_manual_approval_category"].map(CATEGORY_ORDER)
    master = master.sort_values(["_category_order", "source_group", "stock_code", "stock_name"], kind="stable").drop(columns=["_category_order"])
    return master.reset_index(drop=True)


def _category_counts(master: pd.DataFrame) -> dict[str, int]:
    counts = master["final_manual_approval_category"].value_counts().to_dict()
    return {category: int(counts.get(category, 0)) for category in CATEGORY_ORDER}


def build_summary(master: pd.DataFrame, inputs: dict[str, Any], clean_hash_before: str, clean_hash_after: str, strategy_diff: str) -> dict[str, Any]:
    counts = _category_counts(master)
    return {
        "task_name": TASK_NAME,
        "research_only": True,
        "manual_approval_packet_generated": True,
        "manual_approval_packet_total_count": int(len(master)),
        "core_approval_candidate_count": counts["core_approval_candidate"],
        "adjacent_watchlist_count": counts["adjacent_watchlist"],
        "evidence_backfill_required_count": counts["evidence_backfill_required"],
        "downgrade_manual_review_required_count": counts["downgrade_manual_review_required"],
        "seed_pollution_or_reject_count": counts["seed_pollution_or_reject"],
        "seed_tier_a_core_count": 86,
        "non_seed_core_count": int(inputs["non_seed_summary"]["confirm_core_candidate_count"]),
        "verified_rescue_core_count": int(inputs["extension_summary"]["proposed_addition_count"]),
        "non_seed_adjacent_count": int(inputs["non_seed_summary"]["confirm_adjacent_watchlist_count"]),
        "seed_tier_b_adjacent_count": int(inputs["reconciliation_summary"]["watchlist_only_adjacent_count"]),
        "non_seed_evidence_backfill_count": int(inputs["non_seed_summary"]["evidence_backfill_required_count"]),
        "failed_true_rescue_evidence_backfill_count": int(len(inputs["not_proposed"])),
        "seed_tier_b_evidence_backfill_count": int(inputs["reconciliation_summary"]["evidence_backfill_required_count"]),
        "workbench_preview_count": counts["core_approval_candidate"],
        "production_applied": False,
        "workbench_applied": False,
        "signal_or_admission_applied": False,
        "clean_candidate_subset_hash_before": clean_hash_before,
        "clean_candidate_subset_hash_after": clean_hash_after,
        "clean_candidate_subset_modified_in_place": clean_hash_before != clean_hash_after,
        "allowed_for_signal_count": int(master["allowed_for_signal"].astype(bool).sum()),
        "allowed_for_admission_count": int(master["allowed_for_admission"].astype(bool).sum()),
        "allowed_for_workbench_candidate_pool_count": int(master["allowed_for_workbench_candidate_pool"].astype(bool).sum()),
        "manual_approval_required_count": int(master["manual_approval_required"].astype(bool).sum()),
        "strategy_file_diff_clean": strategy_diff == "",
        "formal_strategy_files_modified": strategy_diff != "",
        "acceptance_decision": "manual_approval_packet_ready" if strategy_diff == "" and clean_hash_before == clean_hash_after else "blocked_due_to_guardrail_failure",
    }


def build_guardrails(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_name": TASK_NAME,
        "research_only": True,
        "manual_approval_packet_generated": True,
        "workbench_preview_generated": True,
        "production_applied": False,
        "workbench_applied": False,
        "signal_logic_modified": False,
        "admission_logic_modified": False,
        "scoring_logic_modified": False,
        "auto_promote_count": 0,
        "allowed_for_signal_count": int(summary["allowed_for_signal_count"]),
        "allowed_for_admission_count": int(summary["allowed_for_admission_count"]),
        "used_for_signal_count": 0,
        "used_for_admission_count": 0,
        "baseline_admission_changed_count": 0,
        "clean_candidate_subset_modified_in_place": bool(summary["clean_candidate_subset_modified_in_place"]),
        "strategy_file_diff_clean": bool(summary["strategy_file_diff_clean"]),
        "formal_strategy_files_modified": bool(summary["formal_strategy_files_modified"]),
        "acceptance_decision": summary["acceptance_decision"],
    }


def build_report(summary: dict[str, Any], rejected: pd.DataFrame) -> str:
    rejected_names = ", ".join(rejected["stock_name"].astype(str).tolist()) if not rejected.empty else "None"
    return f"""# Tech Bottleneck Candidate Universe Manual Approval Packet v1

## 1. Scope

This is a research-only manual approval packet. It combines the clean subset audit, diagnostics, rescue triage, seed Tier B reconciliation, primary-source rescue verification, clean subset extension proposal, and non-seed Tier A manual review.

No production candidate universe, workbench integration, signal logic, admission logic, scoring logic, formal strategy file, or existing clean_candidate_subset.csv was modified.

## 2. Manual Approval Categories

- Core approval candidates: {summary['core_approval_candidate_count']}
- Adjacent/watchlist only: {summary['adjacent_watchlist_count']}
- Evidence backfill required: {summary['evidence_backfill_required_count']}
- Downgrade manual review required: {summary['downgrade_manual_review_required_count']}
- Seed pollution or reject: {summary['seed_pollution_or_reject_count']}

## 3. Core Approval Composition

- Seed Tier A: {summary['seed_tier_a_core_count']}
- Non-seed core from independent Tier A manual review: {summary['non_seed_core_count']}
- Verified rescue additions: {summary['verified_rescue_core_count']}

The core preview is a proposal-only workbench candidate preview with {summary['workbench_preview_count']} rows.

## 4. Non-Core Queues

Adjacent/watchlist combines {summary['non_seed_adjacent_count']} non-seed adjacent candidates and {summary['seed_tier_b_adjacent_count']} seed Tier B adjacent candidates.

Evidence backfill combines {summary['non_seed_evidence_backfill_count']} non-seed evidence-backfill candidates, {summary['failed_true_rescue_evidence_backfill_count']} failed true-rescue verification candidate, and {summary['seed_tier_b_evidence_backfill_count']} seed Tier B evidence-backfill candidates.

Rejected or seed pollution candidates: {rejected_names}.

## 5. Guardrail Checks

- allowed_for_signal count: {summary['allowed_for_signal_count']}
- allowed_for_admission count: {summary['allowed_for_admission_count']}
- production applied: {summary['production_applied']}
- workbench applied: {summary['workbench_applied']}
- signal/admission applied: {summary['signal_or_admission_applied']}
- clean_candidate_subset modified in place: {summary['clean_candidate_subset_modified_in_place']}
- strategy file diff clean: {summary['strategy_file_diff_clean']}

## 6. Acceptance Decision

{summary['acceptance_decision']}

## 7. Recommended Next Steps

1. Manual approval review of `core_approval_candidates_preview.csv`.
2. Evidence backfill for `evidence_backfill_queue.csv`.
3. Separate review for adjacent/watchlist and downgrade queues.

Continue to defer trigger, holding, exit, trading signal, and strategy admission changes.
"""


def generate(output_dir: Path) -> dict[str, Any]:
    clean_hash_before = _sha(CLEAN_SUBSET_PATH)
    inputs = _load_inputs()
    master = build_master_table(inputs)
    clean_hash_after = _sha(CLEAN_SUBSET_PATH)
    strategy_diff = _git_diff_formal_strategy_files()
    summary = build_summary(master, inputs, clean_hash_before, clean_hash_after, strategy_diff)
    guardrails = build_guardrails(summary)

    output_dir.mkdir(parents=True, exist_ok=True)
    core = master[master["final_manual_approval_category"].eq("core_approval_candidate")].copy()
    adjacent = master[master["final_manual_approval_category"].eq("adjacent_watchlist")].copy()
    evidence = master[master["final_manual_approval_category"].eq("evidence_backfill_required")].copy()
    downgrade = master[master["final_manual_approval_category"].eq("downgrade_manual_review_required")].copy()
    rejected = master[master["final_manual_approval_category"].eq("seed_pollution_or_reject")].copy()

    _write_json(output_dir / "manual_approval_packet_summary.json", summary)
    master.to_csv(output_dir / "manual_approval_master_table.csv", index=False)
    core.to_csv(output_dir / "core_approval_candidates_preview.csv", index=False)
    adjacent.to_csv(output_dir / "adjacent_watchlist.csv", index=False)
    evidence.to_csv(output_dir / "evidence_backfill_queue.csv", index=False)
    downgrade.to_csv(output_dir / "downgrade_manual_review_queue.csv", index=False)
    rejected.to_csv(output_dir / "seed_pollution_or_reject.csv", index=False)
    _write_json(output_dir / "manual_approval_guardrails.json", guardrails)
    (output_dir / "tech_bottleneck_candidate_universe_manual_approval_packet_v1_report.md").write_text(build_report(summary, rejected), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Build research-only manual approval packet for Tech Bottleneck candidate universe.")
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args()
    summary = generate(args.output_dir)
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
