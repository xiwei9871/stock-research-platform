from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_method_codification_v1_hardening_patch"
SCRIPT = PROJECT_ROOT / "scripts/run_tech_bottleneck_method_codification_hardening_patch.py"
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


def test_hardening_patch_outputs_and_guardrails() -> None:
    _run_generator()
    expected = {
        "tech_bottleneck_method_hardening_summary.json",
        "tech_bottleneck_hardened_method_definition.md",
        "tech_bottleneck_hardened_supply_chain_framework.md",
        "tech_bottleneck_supply_chain_role_schema.json",
        "tech_bottleneck_disconfirmation_schema.json",
        "tech_bottleneck_value_capture_schema.json",
        "tech_bottleneck_architecture_shift_schema.json",
        "tech_bottleneck_route_around_schema.json",
        "tech_bottleneck_a_share_concept_pollution_schema.json",
        "tech_bottleneck_evidence_gate_schema.json",
        "tech_bottleneck_tier_gate_rules.json",
        "tech_bottleneck_hardened_bottleneck_exposure_scoring_rubric.json",
        "tech_bottleneck_hardened_research_priority_scoring_rubric.json",
        "tech_bottleneck_supply_chain_nodes_schema.csv",
        "tech_bottleneck_supply_chain_edges_schema.csv",
        "tech_bottleneck_hardened_candidate_field_dictionary.csv",
        "tech_bottleneck_next_research_action_schema.json",
        "tech_bottleneck_hardening_guardrails.json",
        "tech_bottleneck_method_codification_v1_hardening_patch_report.md",
    }
    assert OUTPUT_DIR.exists()
    assert expected.issubset({path.name for path in OUTPUT_DIR.iterdir()})

    guardrails = json.loads((OUTPUT_DIR / "tech_bottleneck_hardening_guardrails.json").read_text(encoding="utf-8"))
    assert guardrails["research_only"] is True
    assert guardrails["hardening_patch_generated"] is True
    assert guardrails["supply_chain_role_schema_generated"] is True
    assert guardrails["disconfirmation_schema_generated"] is True
    assert guardrails["value_capture_schema_generated"] is True
    assert guardrails["architecture_shift_schema_generated"] is True
    assert guardrails["route_around_schema_generated"] is True
    assert guardrails["concept_pollution_schema_generated"] is True
    assert guardrails["evidence_gate_schema_generated"] is True
    assert guardrails["tier_gate_rules_generated"] is True
    assert guardrails["supply_chain_graph_schema_generated"] is True
    assert guardrails["hardened_scoring_generated"] is True
    assert guardrails["hardened_field_dictionary_generated"] is True
    assert guardrails["used_for_signal_count"] == 0
    assert guardrails["used_for_admission_count"] == 0
    assert guardrails["baseline_admission_changed_count"] == 0
    assert guardrails["strategy_file_diff_clean"] is True
    assert guardrails["formal_strategy_files_modified"] is False
    assert guardrails["trading_language_hit_count"] == 0
    assert guardrails["execution_language_hit_count"] == 0
    assert guardrails["lookahead_violation_rows"] == 0
    assert guardrails["acceptance_decision"] == "tech_bottleneck_method_hardening_ready"


def test_hardening_tier_gates_prevent_common_false_positives() -> None:
    _run_generator()
    role_schema = json.loads((OUTPUT_DIR / "tech_bottleneck_supply_chain_role_schema.json").read_text(encoding="utf-8"))
    evidence_gate = json.loads((OUTPUT_DIR / "tech_bottleneck_evidence_gate_schema.json").read_text(encoding="utf-8"))
    tier_rules = json.loads((OUTPUT_DIR / "tech_bottleneck_tier_gate_rules.json").read_text(encoding="utf-8"))
    tier_a = tier_rules["Tier A"]["must_satisfy"]

    assert {"beneficiary", "bottleneck", "chokepoint", "derivative_exposure", "concept_only", "unclear"}.issubset(
        set(role_schema["fields"]["supply_chain_role"]["enum"])
    )
    assert role_schema["tier_gate"]["Tier A_requires_role"] == ["bottleneck", "chokepoint"]
    assert role_schema["tier_gate"]["beneficiary_cannot_tier_a"] is True
    assert role_schema["tier_gate"]["concept_only_cannot_tier_a"] is True

    assert evidence_gate["fields"]["evidence_gate_level"]["enum"] == ["lead", "thesis", "validated", "confirmed"]
    assert evidence_gate["tier_gate"]["Tier A_requires_evidence_gate_level"] == ["validated", "confirmed"]
    assert "supply_chain_role in [bottleneck, chokepoint]" in tier_a
    assert "disconfirmation_trigger exists" in tier_a
    assert "next_primary_source_check exists" in tier_a
    assert "evidence_gate_level in [validated, confirmed]" in tier_a
    assert "concept_pollution_risk not high" in tier_a
    assert "used_for_signal = false" in tier_a
    assert "used_for_admission = false" in tier_a
    assert "concept_only => not Tier A" in tier_rules["global_downgrade_rules"]
    assert "beneficiary => not Tier A" in tier_rules["global_downgrade_rules"]


def test_hardened_scores_graph_and_field_dictionary_are_research_only() -> None:
    _run_generator()
    exposure_score = json.loads(
        (OUTPUT_DIR / "tech_bottleneck_hardened_bottleneck_exposure_scoring_rubric.json").read_text(encoding="utf-8")
    )
    priority_score = json.loads(
        (OUTPUT_DIR / "tech_bottleneck_hardened_research_priority_scoring_rubric.json").read_text(encoding="utf-8")
    )
    fields = pd.read_csv(OUTPUT_DIR / "tech_bottleneck_hardened_candidate_field_dictionary.csv")
    nodes = pd.read_csv(OUTPUT_DIR / "tech_bottleneck_supply_chain_nodes_schema.csv")
    edges = pd.read_csv(OUTPUT_DIR / "tech_bottleneck_supply_chain_edges_schema.csv")
    field_names = set(fields["field_name"])

    required_new_fields = {
        "supply_chain_role",
        "route_around_risk",
        "switching_time_months",
        "alternative_supplier_count",
        "disconfirmation_trigger",
        "disconfirming_evidence_type",
        "thesis_kill_condition",
        "next_primary_source_check",
        "value_capture_score",
        "pricing_power_evidence",
        "gross_margin_trend",
        "backlog_or_order_visibility",
        "customer_bargaining_power",
        "supplier_bargaining_power",
        "competitive_intensity",
        "capital_intensity_pressure",
        "architecture_shift",
        "old_architecture_failure_point",
        "new_architecture_dependency",
        "adoption_timeline",
        "inflection_window",
        "architecture_shift_score",
        "can_customer_route_around",
        "route_around_options",
        "substitute_maturity",
        "qualification_cycle_months",
        "capacity_expansion_lead_time",
        "substitution_difficulty_score",
        "concept_pollution_risk",
        "policy_theme_only_flag",
        "name_similarity_only_flag",
        "minority_investment_only_flag",
        "trading_agent_or_distributor_flag",
        "secondary_market_narrative_only_flag",
        "interactive_platform_only_flag",
        "kol_or_social_only_flag",
        "evidence_gate_level",
        "primary_source_count",
        "named_customer_flag",
        "order_or_capacity_flag",
        "revenue_traceable_flag",
        "financial_traceable_flag",
        "next_research_action",
        "next_primary_source_to_check",
        "manual_review_question",
        "missing_evidence_to_upgrade",
        "evidence_to_downgrade",
        "market_understanding_gap_score",
        "old_business_valuation_flag",
        "new_business_not_in_financials",
        "low_institutional_coverage",
        "narrative_misclassification",
        "bottleneck_or_chokepoint_score",
        "bottleneck_exposure_score",
        "research_priority_score",
    }
    assert required_new_fields.issubset(field_names)

    for payload in (exposure_score, priority_score):
        assert payload["research_only"] is True
        assert payload["used_for_signal"] is False
        assert payload["used_for_admission"] is False
        assert payload["not_a_trading_signal"] is True
        assert payload["not_for_baseline_admission"] is True
    assert exposure_score["score_name"] == "bottleneck_exposure_score"
    assert priority_score["score_name"] == "research_priority_score"

    score_rows = fields[fields["field_name"].isin({"bottleneck_exposure_score", "research_priority_score"})]
    assert not score_rows["used_for_signal"].astype(bool).any()
    assert not score_rows["used_for_admission"].astype(bool).any()
    assert {"node_id", "node_type", "node_name", "trend_domain", "tech_bottleneck_domain", "description", "research_only"} <= set(nodes.columns)
    assert {"edge_id", "source_node_id", "target_node_id", "edge_type", "dependency_strength", "route_around_risk", "evidence_type", "evidence_strength", "research_only"} <= set(edges.columns)


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
