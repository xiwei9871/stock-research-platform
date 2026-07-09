from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
SCRIPT = PROJECT_ROOT / "scripts/run_tech_bottleneck_confirmed_core_pool_manual_approval.py"
ORIGINAL_PROPOSAL = PROJECT_ROOT / "outputs/research/tech_bottleneck_confirmed_core_pool_proposal_v1/confirmed_core_pool_proposal.csv"
BACKFILL_UPGRADES = PROJECT_ROOT / "outputs/research/tech_bottleneck_90_primary_source_backfill_rerun_v2/backfill_rerun_v2_upgrade_candidates.csv"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_confirmed_core_pool_manual_approval_v1"
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run_generator() -> None:
    result = subprocess.run(
        [str(PROJECT_ROOT / ".venv/bin/python"), str(SCRIPT)],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def _output_hashes() -> dict[str, str]:
    return {
        path.name: _sha(path)
        for path in sorted(OUTPUT_DIR.iterdir())
        if path.is_file()
    }


def test_confirmed_core_manual_approval_outputs_and_guardrails() -> None:
    original_hash_before = _sha(ORIGINAL_PROPOSAL)
    upgrades_hash_before = _sha(BACKFILL_UPGRADES)
    _run_generator()
    original_hash_after = _sha(ORIGINAL_PROPOSAL)
    upgrades_hash_after = _sha(BACKFILL_UPGRADES)

    expected = {
        "confirmed_core_manual_approval_package.csv",
        "confirmed_core_manual_approval_summary.json",
        "confirmed_core_manual_approval_evidence_index.csv",
        "confirmed_core_manual_approval_risk_review.csv",
        "confirmed_core_manual_approval_decision_template.csv",
        "confirmed_core_manual_approval_guardrails.json",
        "tech_bottleneck_confirmed_core_pool_manual_approval_v1_report.md",
    }
    assert OUTPUT_DIR.exists()
    assert expected.issubset({path.name for path in OUTPUT_DIR.iterdir()})
    assert original_hash_before == original_hash_after
    assert upgrades_hash_before == upgrades_hash_after

    summary = json.loads((OUTPUT_DIR / "confirmed_core_manual_approval_summary.json").read_text(encoding="utf-8"))
    guardrails = json.loads((OUTPUT_DIR / "confirmed_core_manual_approval_guardrails.json").read_text(encoding="utf-8"))

    assert summary["manual_approval_candidate_count"] == 52
    assert summary["original_confirmed_core_count"] == 29
    assert summary["backfill_upgrade_count"] == 23
    assert summary["auto_applied_count"] == 0
    assert summary["used_for_signal_count"] == 0
    assert summary["used_for_admission_count"] == 0
    assert summary["baseline_admission_changed_count"] == 0
    assert summary["strategy_file_diff_clean"] is True
    assert summary["formal_strategy_files_modified"] is False
    assert summary["trading_language_hit_count"] == 0
    assert summary["execution_language_hit_count"] == 0
    assert summary["acceptance_decision"] in {
        "confirmed_core_manual_approval_package_ready",
        "conditionally_ready_with_manual_review_gaps",
    }

    assert guardrails["research_only"] is True
    assert guardrails["manual_approval_package_generated"] is True
    assert guardrails["manual_approval_candidate_count"] == 52
    assert guardrails["auto_applied_count"] == 0
    assert guardrails["used_for_signal_count"] == 0
    assert guardrails["used_for_admission_count"] == 0
    assert guardrails["baseline_admission_changed_count"] == 0
    assert guardrails["strategy_file_diff_clean"] is True
    assert guardrails["formal_strategy_files_modified"] is False
    assert guardrails["trading_language_hit_count"] == 0
    assert guardrails["execution_language_hit_count"] == 0
    assert guardrails["lookahead_violation_rows"] == 0


def test_confirmed_core_manual_approval_package_integrity() -> None:
    _run_generator()

    package = pd.read_csv(OUTPUT_DIR / "confirmed_core_manual_approval_package.csv", dtype={"stock_code": str})
    evidence = pd.read_csv(OUTPUT_DIR / "confirmed_core_manual_approval_evidence_index.csv", dtype={"stock_code": str})
    risk = pd.read_csv(OUTPUT_DIR / "confirmed_core_manual_approval_risk_review.csv", dtype={"stock_code": str})
    template = pd.read_csv(OUTPUT_DIR / "confirmed_core_manual_approval_decision_template.csv", dtype={"stock_code": str})

    assert len(package) == 52
    assert package["stock_code"].nunique() == 52
    assert set(package["proposal_source"]) == {"original_confirmed_core_proposal", "backfill_rerun_v2_upgrade"}
    assert package["manual_approval_status"].eq("pending_manual_approval").all()
    assert package["research_only"].eq(True).all()
    assert package["used_for_signal"].eq(False).all()
    assert package["used_for_admission"].eq(False).all()
    assert package["manual_approval_recommendation"].notna().all()
    assert package["manual_approval_question"].notna().all()
    assert set(evidence["stock_code"]).issubset(set(package["stock_code"]))
    assert set(risk["stock_code"]) == set(package["stock_code"])
    assert set(template["stock_code"]) == set(package["stock_code"])
    assert template["manual_approval_status"].eq("pending_manual_approval").all()


def test_confirmed_core_manual_approval_deterministic_and_strategy_diff_clean() -> None:
    _run_generator()
    first = _output_hashes()
    _run_generator()
    second = _output_hashes()
    assert first == second

    diff = subprocess.run(
        ["git", "diff", "--", *FORMAL_STRATEGY_FILES],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert diff.stdout == ""
