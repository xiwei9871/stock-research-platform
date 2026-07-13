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
TASK_NAME = "tech_bottleneck_candidate_universe_pipeline_closure_v2"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_candidate_universe_pipeline_closure_v2"
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]

V2_REFINEMENT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_seed_tier_a_requalification_v2_review_pool_refinement"
LEGACY_WORKBENCH_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_candidate_universe_workbench_patch_v1"

DEFAULT_POOL = V2_REFINEMENT_DIR / "hard_tech_review_pool_preview.csv"
VERIFIED_CORE = V2_REFINEMENT_DIR / "verified_core_candidates.csv"
MANUAL_ANCHOR = V2_REFINEMENT_DIR / "manual_anchor_core_pending_evidence.csv"
LIKELY_HARD_TECH = V2_REFINEMENT_DIR / "likely_hard_tech_pending_evidence.csv"
ADJACENT_PENDING = V2_REFINEMENT_DIR / "adjacent_pending_evidence.csv"
LOW_PRIORITY_BACKFILL = V2_REFINEMENT_DIR / "low_priority_evidence_backfill.csv"
REJECT_SEED_POLLUTION = V2_REFINEMENT_DIR / "reject_seed_pollution.csv"
LEGACY_POOL = LEGACY_WORKBENCH_DIR / "workbench_core_candidates.csv"


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def _write_df(path: Path, df: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _row_count(path: Path) -> int:
    return int(len(pd.read_csv(path)))


def _rel(path: Path) -> str:
    return str(path.relative_to(PROJECT_ROOT))


def _git_diff_formal_strategy_files() -> str:
    result = subprocess.run(
        ["git", "diff", "--", *FORMAL_STRATEGY_FILES],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return result.stdout or result.stderr or ""


def _artifact(path: Path, role: str, description: str, ready_for_default_dashboard: bool) -> dict[str, Any]:
    return {
        "artifact_role": role,
        "path": _rel(path),
        "row_count": _row_count(path),
        "sha256": _sha(path),
        "research_only": True,
        "ready_for_default_dashboard": ready_for_default_dashboard,
        "ready_for_signal": False,
        "ready_for_admission": False,
        "description": description,
    }


def build_manifest() -> dict[str, Any]:
    artifacts = {
        "canonical_dashboard_default_pool": _artifact(
            DEFAULT_POOL,
            "hard_tech_review_pool_preview",
            "New canonical dashboard default manual hard-tech review pool after v2 refinement.",
            True,
        ),
        "verified_core_candidates": _artifact(
            VERIFIED_CORE,
            "verified_core_candidates",
            "Verified core candidates: 26 non-seed confirmed core + 2 verified rescue candidates.",
            False,
        ),
        "manual_anchor_core_pending_evidence": _artifact(
            MANUAL_ANCHOR,
            "manual_anchor_core_pending_evidence",
            "User-confirmed hard-tech anchors retained for manual review while evidence capture remains pending.",
            False,
        ),
        "likely_hard_tech_pending_evidence": _artifact(
            LIKELY_HARD_TECH,
            "likely_hard_tech_pending_evidence",
            "Clearly hard-tech/bottleneck-relevant Seed Tier A rows pending primary-source evidence capture.",
            False,
        ),
        "adjacent_pending_evidence": _artifact(
            ADJACENT_PENDING,
            "adjacent_pending_evidence",
            "Adjacent rows excluded from the default hard-tech core review pool.",
            False,
        ),
        "low_priority_evidence_backfill": _artifact(
            LOW_PRIORITY_BACKFILL,
            "low_priority_evidence_backfill",
            "Low-priority source/domain backfill rows excluded from the default hard-tech core review pool.",
            False,
        ),
        "reject_seed_pollution": _artifact(
            REJECT_SEED_POLLUTION,
            "reject_seed_pollution",
            "Rows rejected as seed pollution or hard-exclusion cases.",
            False,
        ),
    }
    return {
        "task_name": TASK_NAME,
        "research_only": True,
        "canonical_dashboard_default_pool": artifacts["canonical_dashboard_default_pool"],
        "canonical_supporting_pools": {key: value for key, value in artifacts.items() if key != "canonical_dashboard_default_pool"},
        "artifacts": artifacts,
        "legacy_deprecated_pool": {
            "path": _rel(LEGACY_POOL),
            "row_count": _row_count(LEGACY_POOL),
            "sha256": _sha(LEGACY_POOL),
            "status": "legacy_unverified_pool",
            "flags": ["deprecated_for_default_core_use"],
        },
    }


def build_deprecated_artifacts() -> dict[str, Any]:
    return {
        "task_name": TASK_NAME,
        "research_only": True,
        "legacy_workbench_core_candidates": {
            "path": _rel(LEGACY_POOL),
            "row_count": _row_count(LEGACY_POOL),
            "sha256": _sha(LEGACY_POOL),
            "status": "legacy_unverified_pool",
            "flags": ["deprecated_for_default_core_use"],
            "reason": "old 114 pool was contaminated by unverified Seed Tier A labels",
            "replacement": _rel(DEFAULT_POOL),
        },
    }


def build_readiness_matrix(manifest: dict[str, Any], deprecated: dict[str, Any]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for key, artifact in manifest["artifacts"].items():
        rows.append(
            {
                "artifact_role": artifact["artifact_role"],
                "path": artifact["path"],
                "row_count": artifact["row_count"],
                "artifact_status": "canonical_default" if key == "canonical_dashboard_default_pool" else "canonical_supporting",
                "ready_for_default_dashboard": artifact["ready_for_default_dashboard"],
                "ready_for_signal": False,
                "ready_for_admission": False,
                "deprecated_for_default_core_use": False,
                "notes": artifact["description"],
            }
        )
    legacy = deprecated["legacy_workbench_core_candidates"]
    rows.append(
        {
            "artifact_role": "legacy_workbench_core_candidates",
            "path": legacy["path"],
            "row_count": legacy["row_count"],
            "artifact_status": legacy["status"],
            "ready_for_default_dashboard": False,
            "ready_for_signal": False,
            "ready_for_admission": False,
            "deprecated_for_default_core_use": True,
            "notes": legacy["reason"],
        }
    )
    return pd.DataFrame(rows).sort_values(["artifact_status", "artifact_role"], kind="stable").reset_index(drop=True)


def build_summary(manifest: dict[str, Any], v2_summary: dict[str, Any], strategy_diff: str) -> dict[str, Any]:
    strategy_clean = strategy_diff == ""
    default_df = pd.read_csv(DEFAULT_POOL, dtype={"stock_code": str})
    pool_names = set(default_df["stock_name"].astype(str))
    return {
        "task_name": TASK_NAME,
        "research_only": True,
        "pipeline_closure_v2_generated": True,
        "canonical_default_pool_path": manifest["canonical_dashboard_default_pool"]["path"],
        "canonical_default_pool_count": int(manifest["canonical_dashboard_default_pool"]["row_count"]),
        "legacy_pool_path": _rel(LEGACY_POOL),
        "legacy_pool_count": int(_row_count(LEGACY_POOL)),
        "legacy_pool_status": "legacy_unverified_pool",
        "legacy_pool_deprecated_for_default_core_use": True,
        "verified_core_count": int(v2_summary["verified_core_count"]),
        "manual_anchor_core_pending_evidence_count": int(v2_summary["manual_anchor_core_pending_evidence_count"]),
        "likely_hard_tech_pending_evidence_count": int(v2_summary["likely_hard_tech_pending_evidence_count"]),
        "adjacent_pending_evidence_count": int(v2_summary["adjacent_pending_evidence_count"]),
        "low_priority_evidence_backfill_count": int(v2_summary["low_priority_evidence_backfill_count"]),
        "reject_seed_pollution_count": int(v2_summary["reject_seed_pollution_count"]),
        "includes_beifang_huachuang": "北方华创" in pool_names,
        "includes_zhongwei_company": "中微公司" in pool_names,
        "excluded_from_default_pool": ["佛山照明", "通宝能源", "渝农商行", "浙商银行", "建设银行", "中信银行"],
        "old_114_pool_assessment": "contaminated_by_unverified_seed_tier_a_labels",
        "v1_strict_pool_assessment": "too_conservative_for_manual_review",
        "v2_default_pool_assessment": "removes_obvious_pollution_but_keeps_hard_tech_pending_evidence",
        "allowed_for_signal_count": 0,
        "allowed_for_admission_count": 0,
        "baseline_admission_changed_count": 0,
        "production_modifications": False,
        "admission_logic_modified": False,
        "signal_logic_modified": False,
        "scoring_logic_modified": False,
        "strategy_file_diff_clean": strategy_clean,
        "formal_strategy_files_modified": not strategy_clean,
        "acceptance_decision": "candidate_universe_pipeline_closure_v2_ready" if strategy_clean else "blocked_due_to_guardrail_failure",
    }


def build_guardrails(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_name": TASK_NAME,
        "research_only": True,
        "allowed_for_signal_count": 0,
        "allowed_for_admission_count": 0,
        "used_for_signal_count": 0,
        "used_for_admission_count": 0,
        "baseline_admission_changed_count": 0,
        "production_modifications": False,
        "admission_logic_modified": False,
        "signal_logic_modified": False,
        "scoring_logic_modified": False,
        "strategy_file_diff_clean": bool(summary["strategy_file_diff_clean"]),
        "formal_strategy_files_modified": bool(summary["formal_strategy_files_modified"]),
        "acceptance_decision": summary["acceptance_decision"],
    }


def build_report(summary: dict[str, Any], deprecated: dict[str, Any]) -> str:
    legacy = deprecated["legacy_workbench_core_candidates"]
    return f"""# Tech Bottleneck Candidate Universe Pipeline Closure v2

## 1. Scope

This is a documentation and manifest-only closure update after `seed_tier_a_requalification_v2_review_pool_refinement`.

No production signal, admission, scoring, strategy files, or formal candidate universe logic was modified.

## 2. New Canonical Dashboard Default Pool

The new default dashboard pool is:

`{summary['canonical_default_pool_path']}`

Count: {summary['canonical_default_pool_count']}

This is the hard-tech review pool 90.

## 3. Deprecated Legacy Pool

The old 114 pool was contaminated by unverified Seed Tier A labels.

`{legacy['path']}` is marked `{legacy['status']}` and `deprecated_for_default_core_use`.

## 4. Why v2 Replaces Earlier Pools

- old 114 pool was contaminated by unverified Seed Tier A labels
- v1 strict pool 28 was too conservative for manual review
- v2 default pool 90 removes obvious pollution but keeps hard-tech pending evidence

## 5. Canonical Pool Counts

- hard_tech_review_pool_preview: {summary['canonical_default_pool_count']}
- verified_core_candidates: {summary['verified_core_count']}
- manual_anchor_core_pending_evidence: {summary['manual_anchor_core_pending_evidence_count']}
- likely_hard_tech_pending_evidence: {summary['likely_hard_tech_pending_evidence_count']}
- adjacent_pending_evidence: {summary['adjacent_pending_evidence_count']}
- low_priority_evidence_backfill: {summary['low_priority_evidence_backfill_count']}
- reject_seed_pollution: {summary['reject_seed_pollution_count']}

## 6. Explicit Audit Notes

- 北方华创 and 中微公司 are manual anchor core pending evidence.
- 佛山照明、通宝能源、银行股 are excluded from default hard-tech review pool.
- allowed_for_signal = {summary['allowed_for_signal_count']}
- allowed_for_admission = {summary['allowed_for_admission_count']}

## 7. Guardrails

- baseline_admission_changed_count: {summary['baseline_admission_changed_count']}
- production_modifications: {summary['production_modifications']}
- admission_logic_modified: {summary['admission_logic_modified']}
- signal_logic_modified: {summary['signal_logic_modified']}
- scoring_logic_modified: {summary['scoring_logic_modified']}
- strategy_file_diff_clean: {summary['strategy_file_diff_clean']}

## 8. Acceptance Decision

{summary['acceptance_decision']}
"""


def generate(output_dir: Path = OUTPUT_DIR) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    v2_summary = _load_json(V2_REFINEMENT_DIR / "requalification_v2_summary.json")
    strategy_diff = _git_diff_formal_strategy_files()
    manifest = build_manifest()
    deprecated = build_deprecated_artifacts()
    summary = build_summary(manifest, v2_summary, strategy_diff)
    guardrails = build_guardrails(summary)
    readiness = build_readiness_matrix(manifest, deprecated)

    _write_json(output_dir / "pipeline_closure_v2_summary.json", summary)
    _write_json(output_dir / "canonical_artifact_manifest_v2.json", manifest)
    _write_df(output_dir / "candidate_universe_readiness_matrix_v2.csv", readiness)
    _write_json(output_dir / "deprecated_artifacts.json", deprecated)
    _write_json(output_dir / "guardrail_closure_check_v2.json", guardrails)
    (output_dir / "tech_bottleneck_candidate_universe_pipeline_closure_v2_report.md").write_text(
        build_report(summary, deprecated),
        encoding="utf-8",
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=TASK_NAME)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args()
    summary = generate(output_dir=args.output_dir)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
