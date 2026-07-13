from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_method_codification_v1"
SCRIPT = PROJECT_ROOT / "scripts/run_tech_bottleneck_method_codification.py"
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


def test_method_codification_outputs_and_guardrails() -> None:
    _run_generator()
    expected = {
        "tech_bottleneck_method_summary.json",
        "tech_bottleneck_method_definition.md",
        "tech_bottleneck_supply_chain_bottleneck_framework.md",
        "tech_bottleneck_taxonomy_v1.json",
        "tech_bottleneck_evidence_hierarchy_v1.json",
        "tech_bottleneck_real_exposure_schema.json",
        "tech_bottleneck_bottleneck_exposure_scoring_rubric.json",
        "tech_bottleneck_research_priority_scoring_rubric.json",
        "tech_bottleneck_inclusion_exclusion_criteria.json",
        "tech_bottleneck_candidate_tier_schema.json",
        "tech_bottleneck_review_queue_schema.json",
        "tech_bottleneck_a_share_candidate_universe_scan_plan.md",
        "tech_bottleneck_candidate_field_dictionary.csv",
        "tech_bottleneck_method_guardrails.json",
        "tech_bottleneck_method_codification_v1_report.md",
    }
    assert OUTPUT_DIR.exists()
    assert expected.issubset({path.name for path in OUTPUT_DIR.iterdir()})

    guardrails = json.loads((OUTPUT_DIR / "tech_bottleneck_method_guardrails.json").read_text(encoding="utf-8"))
    assert guardrails["research_only"] is True
    assert guardrails["method_codified"] is True
    assert guardrails["taxonomy_generated"] is True
    assert guardrails["evidence_hierarchy_generated"] is True
    assert guardrails["real_exposure_schema_generated"] is True
    assert guardrails["bottleneck_exposure_scoring_generated"] is True
    assert guardrails["research_priority_scoring_generated"] is True
    assert guardrails["inclusion_exclusion_generated"] is True
    assert guardrails["candidate_tier_schema_generated"] is True
    assert guardrails["review_queue_schema_generated"] is True
    assert guardrails["a_share_scan_plan_generated"] is True
    assert guardrails["field_dictionary_generated"] is True
    assert guardrails["used_for_signal_count"] == 0
    assert guardrails["used_for_admission_count"] == 0
    assert guardrails["baseline_admission_changed_count"] == 0
    assert guardrails["strategy_file_diff_clean"] is True
    assert guardrails["formal_strategy_files_modified"] is False
    assert guardrails["trading_language_hit_count"] == 0
    assert guardrails["execution_language_hit_count"] == 0
    assert guardrails["lookahead_violation_rows"] == 0
    assert guardrails["acceptance_decision"] == "tech_bottleneck_method_codification_ready"


def test_scores_and_real_exposure_fields_are_research_only() -> None:
    _run_generator()
    exposure = json.loads((OUTPUT_DIR / "tech_bottleneck_real_exposure_schema.json").read_text(encoding="utf-8"))
    bottleneck_score = json.loads(
        (OUTPUT_DIR / "tech_bottleneck_bottleneck_exposure_scoring_rubric.json").read_text(encoding="utf-8")
    )
    priority_score = json.loads(
        (OUTPUT_DIR / "tech_bottleneck_research_priority_scoring_rubric.json").read_text(encoding="utf-8")
    )
    field_dictionary = pd.read_csv(OUTPUT_DIR / "tech_bottleneck_candidate_field_dictionary.csv")
    fields = set(field_dictionary["field_name"])

    for field in ["customer_certification_stage", "supplier_concentration_type", "revenue_exposure_bucket"]:
        assert field in exposure["fields"]
        assert field in fields

    assert bottleneck_score["score_name"] == "bottleneck_exposure_score"
    assert bottleneck_score["used_for_signal"] is False
    assert bottleneck_score["used_for_admission"] is False
    assert bottleneck_score["not_a_trading_signal"] is True
    assert priority_score["score_name"] == "research_candidate_score"
    assert priority_score["used_for_signal"] is False
    assert priority_score["used_for_admission"] is False
    assert priority_score["not_a_trading_signal"] is True
    assert priority_score["not_for_baseline_admission"] is True
    assert {"bottleneck_exposure_score", "research_candidate_score"}.issubset(fields)
    score_rows = field_dictionary[field_dictionary["field_name"].isin({"bottleneck_exposure_score", "research_candidate_score"})]
    assert not score_rows["used_for_signal"].astype(bool).any()
    assert not score_rows["used_for_admission"].astype(bool).any()


def test_tier_review_schema_and_formal_strategy_diff_are_clean() -> None:
    _run_generator()
    tier_schema = json.loads((OUTPUT_DIR / "tech_bottleneck_candidate_tier_schema.json").read_text(encoding="utf-8"))
    review_schema = json.loads((OUTPUT_DIR / "tech_bottleneck_review_queue_schema.json").read_text(encoding="utf-8"))

    assert {"Tier A", "Tier B", "Tier C", "Watch Only", "Risk Review", "Excluded"}.issubset(tier_schema["tiers"])
    assert {
        "high_quality_fundamental_review",
        "thesis_validation_review",
        "customer_certification_review",
        "revenue_exposure_review",
        "risk_event_review",
        "valuation_anomaly_review",
        "data_gap_review",
        "source_conflict_review",
        "watch_only",
    }.issubset(review_schema["review_queue_types"])

    diff = subprocess.run(
        ["git", "diff", "--", *FORMAL_STRATEGY_FILES],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert diff.stdout == ""
