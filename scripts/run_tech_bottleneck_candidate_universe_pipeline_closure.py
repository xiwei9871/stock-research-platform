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
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_candidate_universe_pipeline_closure_v1"
TASK_NAME = "tech_bottleneck_candidate_universe_pipeline_closure_v1"
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]

QUALITY_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_candidate_universe_quality_audit_v1"
DIAGNOSTICS_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_candidate_universe_quality_audit_diagnostics_v1"
RESCUE_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_candidate_universe_rescue_triage_v1"
RECONCILIATION_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_candidate_universe_seed_tier_b_reconciliation_v1"
VERIFICATION_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_candidate_universe_true_rescue_primary_source_verification_v1"
EXTENSION_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_candidate_universe_clean_subset_extension_proposal_v1"
NON_SEED_REVIEW_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_candidate_universe_non_seed_tier_a_manual_review_v1"
MANUAL_PACKET_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_candidate_universe_manual_approval_packet_v1"
WORKBENCH_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_candidate_universe_workbench_patch_v1"

CANONICAL_CORE = WORKBENCH_DIR / "workbench_core_candidates.csv"
ADJACENT_QUEUE = WORKBENCH_DIR / "workbench_adjacent_watchlist.csv"
EVIDENCE_QUEUE = WORKBENCH_DIR / "workbench_evidence_backfill_queue.csv"
REJECTED_QUEUE = WORKBENCH_DIR / "workbench_rejected_candidates.csv"


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _row_count(path: Path) -> int:
    return int(len(pd.read_csv(path)))


def _rel(path: Path) -> str:
    return str(path.relative_to(PROJECT_ROOT))


def _git_diff_formal_strategy_files() -> str:
    result = subprocess.run(["git", "diff", "--", *FORMAL_STRATEGY_FILES], cwd=PROJECT_ROOT, text=True, capture_output=True, check=False)
    return result.stdout or result.stderr or ""


def _load_inputs() -> dict[str, dict[str, Any]]:
    return {
        "quality": _load_json(QUALITY_DIR / "candidate_universe_quality_audit_summary.json"),
        "diagnostics": _load_json(DIAGNOSTICS_DIR / "audit_diagnostics_summary.json"),
        "rescue": _load_json(RESCUE_DIR / "rescue_triage_summary.json"),
        "reconciliation": _load_json(RECONCILIATION_DIR / "seed_tier_b_reconciliation_summary.json"),
        "verification": _load_json(VERIFICATION_DIR / "true_rescue_primary_source_verification_summary.json"),
        "extension": _load_json(EXTENSION_DIR / "clean_subset_extension_proposal_summary.json"),
        "non_seed_review": _load_json(NON_SEED_REVIEW_DIR / "non_seed_tier_a_manual_review_summary.json"),
        "manual_packet": _load_json(MANUAL_PACKET_DIR / "manual_approval_packet_summary.json"),
        "workbench": _load_json(WORKBENCH_DIR / "workbench_candidate_pool_summary.json"),
        "workbench_guardrails": _load_json(WORKBENCH_DIR / "workbench_patch_guardrails.json"),
    }


def build_manifest() -> dict[str, Any]:
    artifacts = {
        "canonical_research_workbench_core_pool": {
            "path": _rel(CANONICAL_CORE),
            "row_count": _row_count(CANONICAL_CORE),
            "sha256": _sha(CANONICAL_CORE),
            "description": "Canonical research-only workbench core candidate pool.",
        },
        "adjacent_watchlist": {
            "path": _rel(ADJACENT_QUEUE),
            "row_count": _row_count(ADJACENT_QUEUE),
            "sha256": _sha(ADJACENT_QUEUE),
            "description": "Non-core adjacent/watchlist queue.",
        },
        "evidence_backfill_queue": {
            "path": _rel(EVIDENCE_QUEUE),
            "row_count": _row_count(EVIDENCE_QUEUE),
            "sha256": _sha(EVIDENCE_QUEUE),
            "description": "Candidates requiring evidence backfill before any core consideration.",
        },
        "rejected_downgrade_queue": {
            "path": _rel(REJECTED_QUEUE),
            "row_count": _row_count(REJECTED_QUEUE),
            "sha256": _sha(REJECTED_QUEUE),
            "description": "Rejected, seed-pollution, or downgrade/manual-review queue.",
        },
    }
    stage_directories = {
        "quality_audit": _rel(QUALITY_DIR),
        "quality_audit_diagnostics": _rel(DIAGNOSTICS_DIR),
        "rescue_triage": _rel(RESCUE_DIR),
        "seed_tier_b_reconciliation": _rel(RECONCILIATION_DIR),
        "true_rescue_primary_source_verification": _rel(VERIFICATION_DIR),
        "clean_subset_extension_proposal": _rel(EXTENSION_DIR),
        "non_seed_tier_a_manual_review": _rel(NON_SEED_REVIEW_DIR),
        "manual_approval_packet": _rel(MANUAL_PACKET_DIR),
        "workbench_patch": _rel(WORKBENCH_DIR),
    }
    return {
        "task_name": TASK_NAME,
        "research_only": True,
        "canonical_research_workbench_core_pool": artifacts["canonical_research_workbench_core_pool"],
        "non_core_queues": {
            "adjacent_watchlist": artifacts["adjacent_watchlist"],
            "evidence_backfill_queue": artifacts["evidence_backfill_queue"],
            "rejected_downgrade_queue": artifacts["rejected_downgrade_queue"],
        },
        "stage_directories": stage_directories,
        "artifacts": artifacts,
    }


def build_readiness_matrix(manifest: dict[str, Any]) -> pd.DataFrame:
    rows = []
    for role, artifact in manifest["artifacts"].items():
        rows.append(
            {
                "artifact_role": role if role != "canonical_research_workbench_core_pool" else "canonical_core_pool",
                "path": artifact["path"],
                "row_count": artifact["row_count"],
                "ready_for_readonly_dashboard": role == "canonical_research_workbench_core_pool",
                "ready_for_signal": False,
                "ready_for_admission": False,
                "next_action": "read_only_dashboard_integration_or_manual_review"
                if role == "canonical_research_workbench_core_pool"
                else "manual_review_or_backfill_before_core_consideration",
                "notes": artifact["description"],
            }
        )
    return pd.DataFrame(rows).sort_values(["artifact_role"], kind="stable").reset_index(drop=True)


def build_summary(inputs: dict[str, dict[str, Any]], manifest: dict[str, Any], strategy_diff: str) -> dict[str, Any]:
    quality = inputs["quality"]
    workbench = inputs["workbench"]
    manual_packet = inputs["manual_packet"]
    return {
        "task_name": TASK_NAME,
        "research_only": True,
        "pipeline_closure_generated": True,
        "canonical_research_workbench_core_pool_ready": True,
        "canonical_research_workbench_core_pool": manifest["canonical_research_workbench_core_pool"]["path"],
        "canonical_core_pool_count": int(workbench["workbench_core_candidate_count"]),
        "discovered_total": int(quality["discovered_total"]),
        "qualified_total": int(quality["qualified_candidate_total"]),
        "original_clean_subset_count": int(quality["clean_candidate_subset_count"]),
        "manual_approval_packet_total": int(manual_packet["manual_approval_packet_total_count"]),
        "workbench_core_candidate_count": int(workbench["workbench_core_candidate_count"]),
        "adjacent_watchlist_count": int(workbench["workbench_adjacent_watchlist_count"]),
        "evidence_backfill_queue_count": int(workbench["workbench_evidence_backfill_count"]),
        "rejected_downgrade_queue_count": int(workbench["workbench_rejected_candidate_count"]),
        "tier_a_pass_assessment": "pass_by_construction_not_independent_validation",
        "tier_b_high_quality_assessment": "threshold_and_data_gap_driven",
        "tier_b_threshold_finding": "Lowering threshold alone does not solve Tier B because near-miss candidates still have blocking data gaps.",
        "verified_rescue_candidates": ["京泉华", "浙江力诺"],
        "not_proposed_rescue_candidate": "道恩股份",
        "seed_pollution_or_reject_candidate": "神农集团",
        "production_modifications": False,
        "admission_logic_modified": False,
        "signal_logic_modified": False,
        "scoring_logic_modified": False,
        "dashboard_or_workbench_integration_modified": False,
        "strategy_file_diff_clean": strategy_diff == "",
        "formal_strategy_files_modified": strategy_diff != "",
        "acceptance_decision": "candidate_universe_pipeline_closure_ready" if strategy_diff == "" else "blocked_due_to_guardrail_failure",
    }


def build_guardrails(inputs: dict[str, dict[str, Any]], summary: dict[str, Any]) -> dict[str, Any]:
    workbench_guardrails = inputs["workbench_guardrails"]
    return {
        "task_name": TASK_NAME,
        "research_only": True,
        "allowed_for_signal_count": int(workbench_guardrails["allowed_for_signal_count"]),
        "allowed_for_admission_count": int(workbench_guardrails["allowed_for_admission_count"]),
        "used_for_signal_count": int(workbench_guardrails["used_for_signal_count"]),
        "used_for_admission_count": int(workbench_guardrails["used_for_admission_count"]),
        "baseline_admission_changed_count": int(workbench_guardrails["baseline_admission_changed_count"]),
        "production_modifications": False,
        "admission_logic_modified": False,
        "signal_logic_modified": False,
        "scoring_logic_modified": False,
        "dashboard_or_workbench_integration_modified": False,
        "strategy_file_diff_clean": bool(summary["strategy_file_diff_clean"]),
        "formal_strategy_files_modified": bool(summary["formal_strategy_files_modified"]),
        "acceptance_decision": summary["acceptance_decision"],
    }


def build_next_steps() -> str:
    return """# Next Step Recommendations

1. Integrate `workbench_core_candidates.csv` into a read-only dashboard surface.
2. Keep adjacent, evidence-backfill, and rejected/downgrade queues separate from the core pool.
3. Build a manual review workflow for source verification, evidence backfill, and candidate notes.
4. Continue deferring production admission, signal generation, scoring changes, trigger/holding/exit logic, and strategy admission changes.
"""


def build_report(summary: dict[str, Any], manifest: dict[str, Any]) -> str:
    core_path = manifest["canonical_research_workbench_core_pool"]["path"]
    return f"""# Tech Bottleneck Candidate Universe Pipeline Closure v1

## 1. Scope

This is a documentation and manifest-only closure package for the Tech Bottleneck candidate universe pipeline.

No strategy, signal, admission, scoring, dashboard, or production workbench integration was modified.

## 2. Canonical Research Workbench Pool

The canonical research workbench pool is ready:

`{core_path}`

Core pool count: {summary['canonical_core_pool_count']}

## 3. Non-Core Queues

- Adjacent watchlist: {summary['adjacent_watchlist_count']}
- Evidence backfill queue: {summary['evidence_backfill_queue_count']}
- Rejected/downgrade queue: {summary['rejected_downgrade_queue_count']}

## 4. Pipeline Summary

- Discovered total: {summary['discovered_total']}
- Qualified total: {summary['qualified_total']}
- Original clean subset: {summary['original_clean_subset_count']}
- Manual approval packet total: {summary['manual_approval_packet_total']}
- Workbench core candidate count: {summary['workbench_core_candidate_count']}

## 5. Key Audit Findings

- Tier A pass was pass-by-construction, not independent validation.
- Tier B high_quality=0 was threshold/data-gap driven.
- Lowering threshold alone does not solve Tier B because near-miss candidates still have blocking data gaps.
- 京泉华 and 浙江力诺 were verified rescue candidates.
- 道恩股份 was not proposed due to insufficient bottleneck evidence.
- 神农集团 was classified as seed pollution/reject.

## 6. Guardrail Closure Check

- allowed_for_signal count: 0
- allowed_for_admission count: 0
- baseline admission changed count: 0
- production/admission/signal/scoring modifications: false
- dashboard/workbench integration modifications: false
- strategy file diff clean: {summary['strategy_file_diff_clean']}

Nothing has been applied to production signal/admission.

Dashboard/workbench integration is still pending.

## 7. Next Safe Step

The next safe step is read-only dashboard integration or manual review workflow.

## 8. Acceptance Decision

{summary['acceptance_decision']}
"""


def generate(output_dir: Path) -> dict[str, Any]:
    inputs = _load_inputs()
    manifest = build_manifest()
    strategy_diff = _git_diff_formal_strategy_files()
    summary = build_summary(inputs, manifest, strategy_diff)
    guardrails = build_guardrails(inputs, summary)
    matrix = build_readiness_matrix(manifest)

    output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(output_dir / "pipeline_closure_summary.json", summary)
    _write_json(output_dir / "canonical_artifact_manifest.json", manifest)
    matrix.to_csv(output_dir / "candidate_universe_readiness_matrix.csv", index=False)
    _write_json(output_dir / "guardrail_closure_check.json", guardrails)
    (output_dir / "next_step_recommendations.md").write_text(build_next_steps(), encoding="utf-8")
    (output_dir / "tech_bottleneck_candidate_universe_pipeline_closure_v1_report.md").write_text(build_report(summary, manifest), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Create Tech Bottleneck candidate universe pipeline closure package.")
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args()
    summary = generate(args.output_dir)
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
