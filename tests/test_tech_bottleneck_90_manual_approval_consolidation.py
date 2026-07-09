from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
SCRIPT = PROJECT_ROOT / "scripts/run_tech_bottleneck_90_manual_approval_consolidation.py"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_90_manual_approval_consolidation_v1"
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]


def _run_generator() -> None:
    result = subprocess.run(
        [str(PROJECT_ROOT / ".venv/bin/python"), str(SCRIPT)],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_90_manual_approval_consolidation_outputs_and_guardrails() -> None:
    _run_generator()

    expected = {
        "tech_bottleneck_90_manual_approval_consolidation_summary.json",
        "manual_approval_consolidated_90.csv",
        "manual_approval_candidates_88.csv",
        "downgrade_or_reject_2.csv",
        "manual_approval_consolidation_guardrails.json",
        "tech_bottleneck_90_manual_approval_consolidation_v1_report.md",
    }
    assert OUTPUT_DIR.exists()
    assert expected.issubset({path.name for path in OUTPUT_DIR.iterdir()})

    summary = json.loads((OUTPUT_DIR / "tech_bottleneck_90_manual_approval_consolidation_summary.json").read_text(encoding="utf-8"))
    guardrails = json.loads((OUTPUT_DIR / "manual_approval_consolidation_guardrails.json").read_text(encoding="utf-8"))

    assert summary["canonical_90_count"] == 90
    assert summary["manual_approval_candidate_count"] == 88
    assert summary["downgrade_or_reject_count"] == 2
    assert summary["auto_applied_count"] == 0
    assert summary["used_for_signal_count"] == 0
    assert summary["used_for_admission_count"] == 0
    assert summary["baseline_admission_changed_count"] == 0
    assert summary["strategy_file_diff_clean"] is True
    assert summary["formal_strategy_files_modified"] is False
    assert summary["trading_language_hit_count"] == 0
    assert summary["execution_language_hit_count"] == 0
    assert summary["acceptance_decision"] == "manual_approval_consolidation_ready"

    assert guardrails["research_only"] is True
    assert guardrails["canonical_90_count"] == 90
    assert guardrails["manual_approval_candidate_count"] == 88
    assert guardrails["downgrade_or_reject_count"] == 2
    assert guardrails["auto_applied_count"] == 0
    assert guardrails["used_for_signal_count"] == 0
    assert guardrails["used_for_admission_count"] == 0
    assert guardrails["baseline_admission_changed_count"] == 0
    assert guardrails["strategy_file_diff_clean"] is True
    assert guardrails["formal_strategy_files_modified"] is False
    assert guardrails["trading_language_hit_count"] == 0
    assert guardrails["execution_language_hit_count"] == 0
    assert guardrails["lookahead_violation_rows"] == 0


def test_90_manual_approval_consolidation_integrity() -> None:
    _run_generator()

    consolidated = pd.read_csv(OUTPUT_DIR / "manual_approval_consolidated_90.csv", dtype={"stock_code": str})
    candidates = pd.read_csv(OUTPUT_DIR / "manual_approval_candidates_88.csv", dtype={"stock_code": str})
    rejects = pd.read_csv(OUTPUT_DIR / "downgrade_or_reject_2.csv", dtype={"stock_code": str})

    assert len(consolidated) == 90
    assert consolidated["stock_code"].nunique() == 90
    assert len(candidates) == 88
    assert len(rejects) == 2
    assert set(candidates["stock_code"]).isdisjoint(set(rejects["stock_code"]))
    assert set(consolidated["stock_code"]) == set(candidates["stock_code"]).union(set(rejects["stock_code"]))
    assert candidates["final_90_review_status"].eq("manual_approval_candidate").all()
    assert rejects["final_90_review_status"].eq("downgrade_or_reject").all()
    assert consolidated["research_only"].eq(True).all()
    assert consolidated["used_for_signal"].eq(False).all()
    assert consolidated["used_for_admission"].eq(False).all()
    assert consolidated["auto_applied"].eq(False).all()


def test_90_manual_approval_consolidation_strategy_diff_clean() -> None:
    _run_generator()

    diff = subprocess.run(
        ["git", "diff", "--", *FORMAL_STRATEGY_FILES],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert diff.stdout == ""
