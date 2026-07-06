from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_candidate_universe_clean_subset_extension_proposal_v1"
SCRIPT = PROJECT_ROOT / "scripts/run_tech_bottleneck_candidate_universe_clean_subset_extension_proposal.py"
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


def test_clean_subset_extension_proposal_outputs_and_guardrails() -> None:
    before, after = _run_generator()
    assert before == after
    expected_files = {
        "clean_subset_extension_proposal_summary.json",
        "proposed_clean_subset_additions.csv",
        "not_proposed_rescue_candidates.csv",
        "clean_subset_extension_diff_preview.csv",
        "clean_subset_extension_guardrails.json",
        "tech_bottleneck_candidate_universe_clean_subset_extension_proposal_v1_report.md",
    }
    assert OUTPUT_DIR.exists()
    assert expected_files.issubset({path.name for path in OUTPUT_DIR.iterdir()})
    summary = json.loads((OUTPUT_DIR / "clean_subset_extension_proposal_summary.json").read_text(encoding="utf-8"))
    guardrails = json.loads((OUTPUT_DIR / "clean_subset_extension_guardrails.json").read_text(encoding="utf-8"))
    assert summary["current_clean_subset_count"] == 126
    assert summary["proposed_addition_count"] == 2
    assert summary["net_new_count"] == 2
    assert summary["proposed_clean_subset_count"] == 128
    assert guardrails["auto_promote_count"] == 0
    assert guardrails["manual_approval_required_count"] == 2
    assert guardrails["used_for_signal_count"] == 0
    assert guardrails["used_for_admission_count"] == 0
    assert guardrails["baseline_admission_changed_count"] == 0
    assert guardrails["strategy_file_diff_clean"] is True
    assert guardrails["formal_strategy_files_modified"] is False


def test_proposed_and_not_proposed_candidates_are_correct() -> None:
    _run_generator()
    proposed = pd.read_csv(OUTPUT_DIR / "proposed_clean_subset_additions.csv")
    not_proposed = pd.read_csv(OUTPUT_DIR / "not_proposed_rescue_candidates.csv")
    diff = pd.read_csv(OUTPUT_DIR / "clean_subset_extension_diff_preview.csv")
    assert len(proposed) == 2
    assert set(proposed["stock_name"]) == {"京泉华", "浙江力诺"}
    assert proposed["proposed_clean_subset_status"].eq("proposed_addition").all()
    assert proposed["manual_approval_required"].astype(bool).all()
    assert not proposed["auto_promote"].astype(bool).any()
    assert "道恩股份" in set(not_proposed["stock_name"])
    assert not_proposed.loc[not_proposed["stock_name"].eq("道恩股份"), "proposed_clean_subset_status"].iloc[0] == "not_proposed"
    assert diff["diff_action"].isin({"existing_clean_subset", "proposed_addition"}).all()
    assert diff["diff_action"].eq("proposed_addition").sum() == 2


def test_extension_proposal_is_deterministic_and_strategy_diff_clean() -> None:
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
