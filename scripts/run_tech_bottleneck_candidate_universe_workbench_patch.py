#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_candidate_universe_manual_approval_packet_v1"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_candidate_universe_workbench_patch_v1"
TASK_NAME = "tech_bottleneck_candidate_universe_workbench_patch_v1"
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]

REQUIRED_CORE_COLUMNS = [
    "stock_code",
    "stock_name",
    "source_group",
    "previous_tier",
    "final_manual_approval_category",
    "evidence_strength",
    "bottleneck_relevance",
    "review_decision_source",
    "manual_approval_required",
    "allowed_for_workbench_candidate_pool",
    "allowed_for_signal",
    "allowed_for_admission",
    "rationale",
]


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _git_diff_formal_strategy_files() -> str:
    result = subprocess.run(["git", "diff", "--", *FORMAL_STRATEGY_FILES], cwd=PROJECT_ROOT, text=True, capture_output=True, check=False)
    return result.stdout or result.stderr or ""


def _load_inputs(source_dir: Path) -> dict[str, Any]:
    return {
        "summary": _load_json(source_dir / "manual_approval_packet_summary.json"),
        "guardrails": _load_json(source_dir / "manual_approval_guardrails.json"),
        "master": pd.read_csv(source_dir / "manual_approval_master_table.csv"),
        "core": pd.read_csv(source_dir / "core_approval_candidates_preview.csv"),
        "adjacent": pd.read_csv(source_dir / "adjacent_watchlist.csv"),
        "evidence": pd.read_csv(source_dir / "evidence_backfill_queue.csv"),
        "downgrade": pd.read_csv(source_dir / "downgrade_manual_review_queue.csv"),
        "reject": pd.read_csv(source_dir / "seed_pollution_or_reject.csv"),
    }


def _validate_core_source(core: pd.DataFrame) -> None:
    missing = [column for column in REQUIRED_CORE_COLUMNS if column not in core.columns]
    if missing:
        raise ValueError(f"core_approval_candidates_preview.csv missing required columns: {missing}")
    if len(core) != 114:
        raise ValueError(f"Expected 114 workbench core candidates, found {len(core)}")
    names = set(core["stock_name"].astype(str))
    if not {"京泉华", "浙江力诺"}.issubset(names):
        raise ValueError("Verified rescue candidates 京泉华 and 浙江力诺 must be present in the workbench core source.")
    blocked = {"道恩股份", "神农集团"} & names
    if blocked:
        raise ValueError(f"Blocked candidates must not be present in workbench core source: {sorted(blocked)}")
    if not core["allowed_for_workbench_candidate_pool"].astype(bool).all():
        raise ValueError("Every workbench core candidate must be allowed_for_workbench_candidate_pool=true.")
    if core["allowed_for_signal"].astype(bool).any() or core["allowed_for_admission"].astype(bool).any():
        raise ValueError("Workbench patch cannot allow candidates for signal or admission.")


def _prepare_outputs(inputs: dict[str, Any]) -> dict[str, pd.DataFrame]:
    core = inputs["core"].copy()
    _validate_core_source(core)
    adjacent = inputs["adjacent"].copy()
    evidence = inputs["evidence"].copy()
    rejected = pd.concat([inputs["downgrade"], inputs["reject"]], ignore_index=True, sort=False)
    sort_columns = [column for column in ["stock_code", "stock_name"] if column in core.columns]
    if sort_columns:
        core = core.sort_values(sort_columns, kind="stable").reset_index(drop=True)
    for frame_name, frame in {"adjacent": adjacent, "evidence": evidence, "rejected": rejected}.items():
        sort_cols = [column for column in ["stock_code", "stock_name"] if column in frame.columns]
        if sort_cols:
            frame = frame.sort_values(sort_cols, kind="stable").reset_index(drop=True)
        if frame_name == "adjacent":
            adjacent = frame
        elif frame_name == "evidence":
            evidence = frame
        else:
            rejected = frame
    return {
        "core": core,
        "adjacent": adjacent,
        "evidence": evidence,
        "rejected": rejected,
    }


def build_summary(outputs: dict[str, pd.DataFrame], inputs: dict[str, Any], strategy_diff: str) -> dict[str, Any]:
    core = outputs["core"]
    evidence_names = set(outputs["evidence"]["stock_name"].astype(str))
    rejected_names = set(outputs["rejected"]["stock_name"].astype(str))
    return {
        "task_name": TASK_NAME,
        "research_only": True,
        "source_directory": str(SOURCE_DIR.relative_to(PROJECT_ROOT)),
        "source_core_candidate_count": int(inputs["summary"]["core_approval_candidate_count"]),
        "workbench_core_candidate_count": int(len(core)),
        "workbench_adjacent_watchlist_count": int(len(outputs["adjacent"])),
        "workbench_evidence_backfill_count": int(len(outputs["evidence"])),
        "workbench_rejected_candidate_count": int(len(outputs["rejected"])),
        "jingquanhua_included": "京泉华" in set(core["stock_name"].astype(str)),
        "zhejiang_linuo_included": "浙江力诺" in set(core["stock_name"].astype(str)),
        "daoen_excluded_from_core": "道恩股份" not in set(core["stock_name"].astype(str)) and "道恩股份" in evidence_names,
        "shennong_excluded_from_core": "神农集团" not in set(core["stock_name"].astype(str)) and "神农集团" in rejected_names,
        "production_candidate_universe_modified": False,
        "workbench_integration_modified": False,
        "signal_logic_modified": False,
        "admission_logic_modified": False,
        "scoring_logic_modified": False,
        "formal_strategy_files_modified": strategy_diff != "",
        "strategy_file_diff_clean": strategy_diff == "",
        "allowed_for_signal_count": int(core["allowed_for_signal"].astype(bool).sum()),
        "allowed_for_admission_count": int(core["allowed_for_admission"].astype(bool).sum()),
        "acceptance_decision": "workbench_patch_ready" if strategy_diff == "" else "blocked_due_to_guardrail_failure",
    }


def build_guardrails(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_name": TASK_NAME,
        "research_only": True,
        "workbench_patch_generated": True,
        "uses_only_core_approval_candidates_preview": True,
        "production_candidate_universe_modified": False,
        "workbench_integration_modified": False,
        "signal_logic_modified": False,
        "admission_logic_modified": False,
        "scoring_logic_modified": False,
        "formal_strategy_files_modified": bool(summary["formal_strategy_files_modified"]),
        "strategy_file_diff_clean": bool(summary["strategy_file_diff_clean"]),
        "allowed_for_signal_count": int(summary["allowed_for_signal_count"]),
        "allowed_for_admission_count": int(summary["allowed_for_admission_count"]),
        "used_for_signal_count": 0,
        "used_for_admission_count": 0,
        "baseline_admission_changed_count": 0,
        "acceptance_decision": summary["acceptance_decision"],
    }


def build_report(summary: dict[str, Any]) -> str:
    return f"""# Tech Bottleneck Candidate Universe Workbench Patch v1

## 1. Scope

This patch creates a research-only workbench candidate pool from `core_approval_candidates_preview.csv`.

It does not modify production admission, signal generation, scoring logic, formal strategy files, or the production candidate universe.

## 2. Source

Source directory: `{summary['source_directory']}`

Only the manually approved core preview is used as the workbench core candidate source.

## 3. Workbench Candidate Pool

- Workbench core candidates: {summary['workbench_core_candidate_count']}
- Adjacent/watchlist queue: {summary['workbench_adjacent_watchlist_count']}
- Evidence backfill queue: {summary['workbench_evidence_backfill_count']}
- Rejected/downgrade queue: {summary['workbench_rejected_candidate_count']}

京泉华 included: {summary['jingquanhua_included']}

浙江力诺 included: {summary['zhejiang_linuo_included']}

道恩股份 excluded from core: {summary['daoen_excluded_from_core']}

神农集团 excluded from core: {summary['shennong_excluded_from_core']}

## 4. Guardrail Checks

- allowed_for_signal count: {summary['allowed_for_signal_count']}
- allowed_for_admission count: {summary['allowed_for_admission_count']}
- production candidate universe modified: {summary['production_candidate_universe_modified']}
- workbench integration modified: {summary['workbench_integration_modified']}
- signal logic modified: {summary['signal_logic_modified']}
- admission logic modified: {summary['admission_logic_modified']}
- scoring logic modified: {summary['scoring_logic_modified']}
- strategy file diff clean: {summary['strategy_file_diff_clean']}

## 5. Acceptance Decision

{summary['acceptance_decision']}
"""


def generate(output_dir: Path) -> dict[str, Any]:
    inputs = _load_inputs(SOURCE_DIR)
    outputs = _prepare_outputs(inputs)
    strategy_diff = _git_diff_formal_strategy_files()
    summary = build_summary(outputs, inputs, strategy_diff)
    guardrails = build_guardrails(summary)

    output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(output_dir / "workbench_candidate_pool_summary.json", summary)
    outputs["core"].to_csv(output_dir / "workbench_core_candidates.csv", index=False)
    outputs["adjacent"].to_csv(output_dir / "workbench_adjacent_watchlist.csv", index=False)
    outputs["evidence"].to_csv(output_dir / "workbench_evidence_backfill_queue.csv", index=False)
    outputs["rejected"].to_csv(output_dir / "workbench_rejected_candidates.csv", index=False)
    _write_json(output_dir / "workbench_patch_guardrails.json", guardrails)
    (output_dir / "tech_bottleneck_candidate_universe_workbench_patch_v1_report.md").write_text(build_report(summary), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Create research-only Tech Bottleneck workbench candidate pool.")
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args()
    summary = generate(args.output_dir)
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
