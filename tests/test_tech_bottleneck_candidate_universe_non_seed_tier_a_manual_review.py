from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_candidate_universe_non_seed_tier_a_manual_review_v1"
SCRIPT = PROJECT_ROOT / "scripts/run_tech_bottleneck_candidate_universe_non_seed_tier_a_manual_review.py"
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


def test_non_seed_tier_a_manual_review_outputs_and_guardrails() -> None:
    before, after = _run_generator()
    assert before == after
    expected = {
        "non_seed_tier_a_manual_review_summary.json",
        "non_seed_tier_a_manual_review.csv",
        "non_seed_tier_a_confirm_core_candidates.csv",
        "non_seed_tier_a_adjacent_watchlist.csv",
        "non_seed_tier_a_evidence_backfill_required.csv",
        "non_seed_tier_a_likely_false_positive.csv",
        "non_seed_tier_a_review_guardrails.json",
        "tech_bottleneck_candidate_universe_non_seed_tier_a_manual_review_v1_report.md",
    }
    assert OUTPUT_DIR.exists()
    assert expected.issubset({path.name for path in OUTPUT_DIR.iterdir()})
    summary = json.loads((OUTPUT_DIR / "non_seed_tier_a_manual_review_summary.json").read_text(encoding="utf-8"))
    guardrails = json.loads((OUTPUT_DIR / "non_seed_tier_a_review_guardrails.json").read_text(encoding="utf-8"))
    assert summary["total_non_seed_tier_a_reviewed"] == 40
    assert summary["manual_approval_required_count"] == 40
    assert summary["tier_a_pass_assessment"] == "pass_by_construction_not_independent_validation"
    assert summary["current_clean_subset_count"] == 126
    assert summary["proposed_extension_count"] == 2
    assert summary["proposed_clean_subset_count"] == 128
    assert summary["extension_applied"] is False
    assert guardrails["used_for_signal_count"] == 0
    assert guardrails["used_for_admission_count"] == 0
    assert guardrails["baseline_admission_changed_count"] == 0
    assert guardrails["auto_promote_count"] == 0
    assert guardrails["strategy_file_diff_clean"] is True
    assert guardrails["formal_strategy_files_modified"] is False


def test_all_40_non_seed_tier_a_rows_have_review_fields() -> None:
    _run_generator()
    review = pd.read_csv(OUTPUT_DIR / "non_seed_tier_a_manual_review.csv")
    assert len(review) == 40
    assert not review["is_seed_watchlist"].astype(bool).any()
    assert review["review_decision"].notna().all()
    assert review["business_relevance_category"].notna().all()
    assert review["evidence_status"].notna().all()
    assert review["manual_approval_required"].astype(bool).all()
    assert review["business_relevance_category"].isin(
        {
            "core_tech_bottleneck",
            "key_component",
            "key_material",
            "industrial_equipment",
            "industrial_software",
            "process_technology",
            "supply_chain_security",
            "adjacent_industry",
            "generic_theme",
            "unclear",
            "likely_false_positive",
        }
    ).all()
    assert review["review_decision"].isin(
        {
            "confirm_core_candidate",
            "confirm_adjacent_watchlist",
            "evidence_backfill_required",
            "downgrade_manual_review_required",
            "likely_false_positive",
        }
    ).all()
    assert not review["used_for_signal"].astype(bool).any()
    assert not review["used_for_admission"].astype(bool).any()


def test_non_seed_tier_a_outputs_are_deterministic_and_strategy_diff_clean() -> None:
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
