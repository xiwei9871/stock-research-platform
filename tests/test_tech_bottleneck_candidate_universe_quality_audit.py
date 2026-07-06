from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_candidate_universe_quality_audit_v1"
SCRIPT = PROJECT_ROOT / "scripts/run_tech_bottleneck_candidate_universe_quality_audit.py"
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


def test_quality_audit_outputs_and_guardrails() -> None:
    _run_generator()
    expected = {
        "candidate_universe_quality_audit_summary.json",
        "tier_a_quality_audit.csv",
        "tier_b_quality_audit.csv",
        "candidate_data_gap_breakdown.csv",
        "excluded_false_negative_audit.csv",
        "candidate_field_quality_audit.csv",
        "seed_watchlist_quality_preview.csv",
        "clean_candidate_subset.csv",
        "clean_candidate_subset_summary.csv",
        "candidate_universe_quality_audit_guardrails.json",
        "tech_bottleneck_candidate_universe_quality_audit_v1_report.md",
    }
    assert OUTPUT_DIR.exists()
    assert expected.issubset({path.name for path in OUTPUT_DIR.iterdir()})

    summary = json.loads((OUTPUT_DIR / "candidate_universe_quality_audit_summary.json").read_text(encoding="utf-8"))
    guardrails = json.loads((OUTPUT_DIR / "candidate_universe_quality_audit_guardrails.json").read_text(encoding="utf-8"))
    assert guardrails["research_only"] is True
    assert guardrails["quality_audit_generated"] is True
    assert guardrails["clean_candidate_subset_generated"] is True
    assert guardrails["discovered_total"] == 3252
    assert guardrails["candidate_total_raw"] == 3252
    assert summary["discovered_total"] == 3252
    assert summary["candidate_total_raw"] == 3252
    assert guardrails["clean_candidate_subset_count"] > 0
    assert guardrails["tier_a_beneficiary_count"] == 0
    assert guardrails["tier_a_concept_only_count"] == 0
    assert guardrails["tier_a_missing_disconfirmation_count"] == 0
    assert guardrails["tier_a_missing_next_primary_source_count"] == 0
    assert guardrails["tier_a_missing_validated_or_confirmed_evidence_count"] == 0
    assert guardrails["used_for_signal_count"] == 0
    assert guardrails["used_for_admission_count"] == 0
    assert guardrails["baseline_admission_changed_count"] == 0
    assert guardrails["strategy_file_diff_clean"] is True
    assert guardrails["formal_strategy_files_modified"] is False
    assert guardrails["trading_language_hit_count"] == 0
    assert guardrails["execution_language_hit_count"] == 0
    assert guardrails["lookahead_violation_rows"] == 0
    assert guardrails["acceptance_decision"] in {
        "candidate_universe_quality_audit_ready",
        "conditionally_ready_with_high_data_gap",
    }


def test_quality_audit_tables_have_expected_scope_and_clean_subset() -> None:
    _run_generator()
    tier_a = pd.read_csv(OUTPUT_DIR / "tier_a_quality_audit.csv")
    tier_b = pd.read_csv(OUTPUT_DIR / "tier_b_quality_audit.csv")
    data_gaps = pd.read_csv(OUTPUT_DIR / "candidate_data_gap_breakdown.csv")
    excluded = pd.read_csv(OUTPUT_DIR / "excluded_false_negative_audit.csv")
    field_quality = pd.read_csv(OUTPUT_DIR / "candidate_field_quality_audit.csv")
    seed_preview = pd.read_csv(OUTPUT_DIR / "seed_watchlist_quality_preview.csv")
    clean_subset = pd.read_csv(OUTPUT_DIR / "clean_candidate_subset.csv")

    assert len(tier_a) == 126
    assert len(tier_b) == 942
    assert len(excluded) == 2124
    assert len(seed_preview) == 102
    assert len(clean_subset) > 0
    assert {"pass", "pass_with_data_gap", "downgrade_to_tier_b", "downgrade_to_risk_review", "downgrade_to_watch_only", "exclude_candidate"}.issuperset(
        set(tier_a["tier_a_quality_status"])
    )
    assert {
        "high_quality_tier_b",
        "data_gap_tier_b",
        "concept_polluted_tier_b",
        "weak_evidence_tier_b",
        "seed_overlap_tier_b",
        "new_candidate_tier_b",
    }.issuperset(set(tier_b["tier_b_quality_bucket"]))
    assert {
        "missing_main_business",
        "missing_announcement",
        "missing_primary_source",
        "missing_customer_certification",
        "missing_revenue_exposure",
        "missing_financial_statement",
        "missing_news",
        "missing_architecture_shift",
        "missing_route_around",
        "missing_value_capture",
        "missing_disconfirmation",
        "missing_next_primary_source_check",
        "missing_evidence_gate",
        "missing_supply_chain_role",
    }.issubset(set(data_gaps["data_gap_type"]))
    assert {"supply_chain_role", "architecture_shift", "value_capture_score", "evidence_gate_level", "next_research_action"}.issubset(
        set(field_quality["field_name"])
    )
    assert not clean_subset["candidate_tier"].eq("Excluded").any()
    assert not clean_subset["supply_chain_role"].eq("concept_only").any()
    assert not clean_subset["concept_pollution_risk"].eq("high").any()
    assert clean_subset["recommended_for_workbench"].astype(bool).all()
    assert clean_subset["research_only"].astype(bool).all()
    assert not clean_subset["used_for_signal"].astype(bool).any()
    assert not clean_subset["used_for_admission"].astype(bool).any()


def test_formal_strategy_diff_is_clean() -> None:
    _run_generator()
    diff = subprocess.run(
        ["git", "diff", "--", *FORMAL_STRATEGY_FILES],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert diff.stdout == ""
