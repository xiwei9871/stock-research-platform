from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_candidate_universe_workbench_patch_v1"
SCRIPT = PROJECT_ROOT / "scripts/run_tech_bottleneck_candidate_universe_workbench_patch.py"
MANUAL_PACKET_CORE = PROJECT_ROOT / "outputs/research/tech_bottleneck_candidate_universe_manual_approval_packet_v1/core_approval_candidates_preview.csv"
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run_generator() -> tuple[str, str]:
    before = _sha(MANUAL_PACKET_CORE)
    result = subprocess.run(
        [str(PROJECT_ROOT / ".venv/bin/python"), str(SCRIPT)],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    after = _sha(MANUAL_PACKET_CORE)
    return before, after


def _hash_outputs() -> dict[str, str]:
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(OUTPUT_DIR.iterdir())
        if path.is_file()
    }


def test_workbench_patch_outputs_and_guardrails() -> None:
    before, after = _run_generator()
    assert before == after
    expected_files = {
        "workbench_candidate_pool_summary.json",
        "workbench_core_candidates.csv",
        "workbench_adjacent_watchlist.csv",
        "workbench_evidence_backfill_queue.csv",
        "workbench_rejected_candidates.csv",
        "workbench_patch_guardrails.json",
        "tech_bottleneck_candidate_universe_workbench_patch_v1_report.md",
    }
    assert OUTPUT_DIR.exists()
    assert expected_files.issubset({path.name for path in OUTPUT_DIR.iterdir()})

    summary = json.loads((OUTPUT_DIR / "workbench_candidate_pool_summary.json").read_text(encoding="utf-8"))
    guardrails = json.loads((OUTPUT_DIR / "workbench_patch_guardrails.json").read_text(encoding="utf-8"))
    assert summary["workbench_core_candidate_count"] == 114
    assert summary["source_core_candidate_count"] == 114
    assert summary["research_only"] is True
    assert summary["production_candidate_universe_modified"] is False
    assert summary["signal_logic_modified"] is False
    assert summary["admission_logic_modified"] is False
    assert summary["scoring_logic_modified"] is False
    assert guardrails["allowed_for_signal_count"] == 0
    assert guardrails["allowed_for_admission_count"] == 0
    assert guardrails["used_for_signal_count"] == 0
    assert guardrails["used_for_admission_count"] == 0
    assert guardrails["baseline_admission_changed_count"] == 0
    assert guardrails["strategy_file_diff_clean"] is True
    assert guardrails["formal_strategy_files_modified"] is False


def test_workbench_core_pool_membership_and_required_columns() -> None:
    _run_generator()
    core = pd.read_csv(OUTPUT_DIR / "workbench_core_candidates.csv")
    rejected = pd.read_csv(OUTPUT_DIR / "workbench_rejected_candidates.csv")
    assert len(core) == 114
    assert {"京泉华", "浙江力诺"}.issubset(set(core["stock_name"]))
    assert "道恩股份" not in set(core["stock_name"])
    assert "神农集团" not in set(core["stock_name"])
    assert "神农集团" in set(rejected["stock_name"])
    required_columns = {
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
    }
    assert required_columns.issubset(set(core.columns))
    assert core["allowed_for_workbench_candidate_pool"].astype(bool).all()
    assert not core["allowed_for_signal"].astype(bool).any()
    assert not core["allowed_for_admission"].astype(bool).any()


def test_workbench_patch_is_deterministic_and_strategy_diff_clean() -> None:
    before, after = _run_generator()
    first = _hash_outputs()
    before2, after2 = _run_generator()
    second = _hash_outputs()
    assert before == after == before2 == after2
    assert first == second
    diff = subprocess.run(
        ["git", "diff", "--", *FORMAL_STRATEGY_FILES],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert diff.stdout == ""
