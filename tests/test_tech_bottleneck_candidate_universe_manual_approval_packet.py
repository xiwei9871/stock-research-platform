from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_candidate_universe_manual_approval_packet_v1"
SCRIPT = PROJECT_ROOT / "scripts/run_tech_bottleneck_candidate_universe_manual_approval_packet.py"
CLEAN_SUBSET = PROJECT_ROOT / "outputs/research/tech_bottleneck_candidate_universe_quality_audit_v1/clean_candidate_subset.csv"
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run_generator() -> tuple[str, str]:
    before = _sha(CLEAN_SUBSET)
    result = subprocess.run(
        [str(PROJECT_ROOT / ".venv/bin/python"), str(SCRIPT)],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    after = _sha(CLEAN_SUBSET)
    return before, after


def _hash_outputs() -> dict[str, str]:
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(OUTPUT_DIR.iterdir())
        if path.is_file()
    }


def test_manual_approval_packet_outputs_and_counts() -> None:
    before, after = _run_generator()
    assert before == after
    expected_files = {
        "manual_approval_packet_summary.json",
        "manual_approval_master_table.csv",
        "core_approval_candidates_preview.csv",
        "adjacent_watchlist.csv",
        "evidence_backfill_queue.csv",
        "downgrade_manual_review_queue.csv",
        "seed_pollution_or_reject.csv",
        "manual_approval_guardrails.json",
        "tech_bottleneck_candidate_universe_manual_approval_packet_v1_report.md",
    }
    assert OUTPUT_DIR.exists()
    assert expected_files.issubset({path.name for path in OUTPUT_DIR.iterdir()})

    summary = json.loads((OUTPUT_DIR / "manual_approval_packet_summary.json").read_text(encoding="utf-8"))
    guardrails = json.loads((OUTPUT_DIR / "manual_approval_guardrails.json").read_text(encoding="utf-8"))
    assert summary["core_approval_candidate_count"] == 114
    assert summary["adjacent_watchlist_count"] == 14
    assert summary["evidence_backfill_required_count"] == 11
    assert summary["downgrade_manual_review_required_count"] == 2
    assert summary["seed_pollution_or_reject_count"] == 1
    assert summary["manual_approval_packet_total_count"] == 142
    assert summary["workbench_preview_count"] == 114
    assert summary["production_applied"] is False
    assert summary["workbench_applied"] is False
    assert guardrails["used_for_signal_count"] == 0
    assert guardrails["used_for_admission_count"] == 0
    assert guardrails["baseline_admission_changed_count"] == 0
    assert guardrails["auto_promote_count"] == 0
    assert guardrails["clean_candidate_subset_modified_in_place"] is False
    assert guardrails["strategy_file_diff_clean"] is True
    assert guardrails["formal_strategy_files_modified"] is False


def test_manual_approval_packet_candidate_categories_and_flags() -> None:
    _run_generator()
    master = pd.read_csv(OUTPUT_DIR / "manual_approval_master_table.csv")
    core = pd.read_csv(OUTPUT_DIR / "core_approval_candidates_preview.csv")
    evidence = pd.read_csv(OUTPUT_DIR / "evidence_backfill_queue.csv")
    rejected = pd.read_csv(OUTPUT_DIR / "seed_pollution_or_reject.csv")

    assert len(core) == 114
    assert set(core["final_manual_approval_category"]) == {"core_approval_candidate"}
    assert {"京泉华", "浙江力诺"}.issubset(set(core["stock_name"]))
    assert "道恩股份" in set(evidence["stock_name"])
    assert "神农集团" in set(rejected["stock_name"])
    assert not master["allowed_for_signal"].astype(bool).any()
    assert not master["allowed_for_admission"].astype(bool).any()
    assert master.loc[
        master["final_manual_approval_category"].eq("core_approval_candidate"),
        "allowed_for_workbench_candidate_pool",
    ].astype(bool).all()
    assert not master.loc[
        ~master["final_manual_approval_category"].eq("core_approval_candidate"),
        "allowed_for_workbench_candidate_pool",
    ].astype(bool).any()
    assert master["manual_approval_required"].astype(bool).all()


def test_manual_approval_packet_is_deterministic_and_strategy_diff_clean() -> None:
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
