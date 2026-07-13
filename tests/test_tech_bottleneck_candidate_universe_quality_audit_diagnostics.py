from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_candidate_universe_quality_audit_diagnostics_v1"
SCRIPT = PROJECT_ROOT / "scripts/run_tech_bottleneck_candidate_universe_quality_audit_diagnostics.py"
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


def _file_hashes() -> dict[str, str]:
    hashes = {}
    for path in sorted(OUTPUT_DIR.iterdir()):
        if path.is_file():
            hashes[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes


def test_diagnostics_outputs_and_summary_answers() -> None:
    _run_generator()
    expected = {
        "audit_diagnostics_summary.json",
        "tier_a_rule_circularity_audit.csv",
        "tier_b_high_quality_feasibility_audit.csv",
        "non_clean_failure_taxonomy.csv",
        "seed_tier_b_diagnostics.csv",
        "tier_a_seed_vs_nonseed_audit.csv",
        "possible_false_negative_rescue_list.csv",
        "tech_bottleneck_candidate_universe_quality_audit_diagnostics_v1_report.md",
    }
    assert OUTPUT_DIR.exists()
    assert expected.issubset({path.name for path in OUTPUT_DIR.iterdir()})

    summary = json.loads((OUTPUT_DIR / "audit_diagnostics_summary.json").read_text(encoding="utf-8"))
    assert summary["research_only"] is True
    assert summary["used_for_signal_count"] == 0
    assert summary["used_for_admission_count"] == 0
    assert summary["strategy_file_diff_clean"] is True
    assert summary["formal_strategy_files_modified"] is False
    assert summary["tier_a_total"] == 126
    assert summary["tier_a_pass_count"] == 126
    assert summary["tier_a_pass_diagnostic"] == "pass_by_construction_not_independent_validation"
    assert summary["tier_b_total"] == 942
    assert summary["tier_b_high_quality_count"] == 0
    assert summary["tier_b_high_quality_diagnostic"] == "not_structurally_impossible_threshold_and_data_gap_driven"
    assert summary["seed_watchlist_count"] == 102
    assert summary["seed_tier_b_count"] == 16
    assert summary["non_clean_total"] == 3126
    assert summary["truly_unqualified_count"] + summary["evidence_insufficient_count"] + summary["data_missing_count"] + summary["unjudgeable_count"] == 3126
    assert summary["possible_false_negative_count"] >= 0
    assert summary["rescue_review_required_count"] >= summary["possible_false_negative_count"]


def test_diagnostics_tables_cover_required_classifications() -> None:
    _run_generator()
    circularity = pd.read_csv(OUTPUT_DIR / "tier_a_rule_circularity_audit.csv")
    feasibility = pd.read_csv(OUTPUT_DIR / "tier_b_high_quality_feasibility_audit.csv")
    non_clean = pd.read_csv(OUTPUT_DIR / "non_clean_failure_taxonomy.csv")
    seed_tier_b = pd.read_csv(OUTPUT_DIR / "seed_tier_b_diagnostics.csv")
    tier_a_source = pd.read_csv(OUTPUT_DIR / "tier_a_seed_vs_nonseed_audit.csv")
    rescue = pd.read_csv(OUTPUT_DIR / "possible_false_negative_rescue_list.csv")

    assert len(circularity) == 126
    assert circularity["pass_assessment"].eq("pass_by_construction_not_independent_validation").all()
    assert circularity["overlap_with_assignment_criteria"].astype(bool).all()
    assert len(feasibility) == 942
    assert feasibility["high_quality_feasibility"].eq("feasible_but_not_met").all()
    assert len(non_clean) == 3126
    allowed = {
        "intrinsic_business_mismatch",
        "explicit_exclusion_rule",
        "evidence_insufficient",
        "data_field_missing",
        "industry_mapping_unclear",
        "financial_or_trading_data_gap",
        "name_code_mapping_gap",
        "rule_artifact_or_threshold_too_strict",
        "unjudgeable",
    }
    assert set(non_clean["primary_failure_reason"]).issubset(allowed)
    assert set(non_clean["secondary_failure_reason"]).issubset(allowed | {""})
    assert len(seed_tier_b) == 16
    assert seed_tier_b["seed_tier_b_reason_classification"].notna().all()
    assert seed_tier_b["manual_rescue_recommended"].astype(bool).all()
    assert int(tier_a_source["is_seed_watchlist"].astype(bool).sum()) == 86
    assert int((~tier_a_source["is_seed_watchlist"].astype(bool)).sum()) == 40
    assert set(rescue["primary_failure_reason"]).issubset(allowed)
    assert not non_clean["research_only"].eq(False).any()
    assert not non_clean["used_for_signal"].astype(bool).any()
    assert not non_clean["used_for_admission"].astype(bool).any()


def test_diagnostics_are_deterministic_and_strategy_diff_clean() -> None:
    _run_generator()
    first = _file_hashes()
    _run_generator()
    second = _file_hashes()
    assert first == second
    diff = subprocess.run(
        ["git", "diff", "--", *FORMAL_STRATEGY_FILES],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert diff.stdout == ""
