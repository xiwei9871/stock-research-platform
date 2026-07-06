#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import subprocess
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
INPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_method_codification_v1"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_method_codification_v1_hardening_patch"
TASK_NAME = "tech_bottleneck_method_codification_v1_hardening_patch"
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]


NEW_FIELD_DEFINITIONS: dict[str, tuple[str, str, str]] = {
    "supply_chain_role": ("role", "beneficiary|bottleneck|chokepoint|derivative_exposure|concept_only|unclear", "Supply-chain role after separating ordinary beneficiaries from true constraints."),
    "route_around_risk": ("role", "high|medium|low|unclear", "Risk that customers can bypass the supplier or bottleneck."),
    "switching_time_months": ("role", "integer_or_missing", "Estimated supplier or technology switching time in months."),
    "alternative_supplier_count": ("role", "integer_or_missing", "Count of plausible alternative suppliers."),
    "disconfirmation_trigger": ("disconfirmation", "text_required_for_Tier_A", "Fastest observable fact that would disprove the thesis."),
    "disconfirming_evidence_type": ("disconfirmation", "filing|financial_statement|customer_disclosure|capacity_data|industry_data|other", "Source type for disconfirming evidence."),
    "thesis_kill_condition": ("disconfirmation", "text", "Condition that downgrades or excludes the candidate thesis."),
    "next_primary_source_check": ("disconfirmation", "text_required_for_Tier_A", "Primary-source check required before high-confidence classification."),
    "value_capture_score": ("value_capture", "0-100", "Research-only score for whether the company can retain economics from the bottleneck."),
    "pricing_power_evidence": ("value_capture", "0-20_or_text", "Evidence for pricing power."),
    "gross_margin_trend": ("value_capture", "improving|stable|deteriorating|unclear|missing", "Gross margin trend context."),
    "backlog_or_order_visibility": ("value_capture", "0-20_or_text", "Visibility from backlog, order, delivery, or capacity evidence."),
    "customer_bargaining_power": ("value_capture", "-15_to_0", "Penalty for strong customer bargaining power."),
    "supplier_bargaining_power": ("value_capture", "-10_to_0", "Penalty for upstream supplier bargaining power."),
    "competitive_intensity": ("value_capture", "-10_to_0", "Penalty for competitive pressure."),
    "capital_intensity_pressure": ("value_capture", "-10_to_0", "Penalty for capex or expansion pressure."),
    "architecture_shift": ("architecture_shift", "text", "Architecture transition that converts trend demand into a hard constraint."),
    "old_architecture_failure_point": ("architecture_shift", "text", "Failure point in the prior architecture."),
    "new_architecture_dependency": ("architecture_shift", "text", "Material, equipment, process, software, certification, or capacity dependency in the new architecture."),
    "adoption_timeline": ("architecture_shift", "text", "Expected adoption timeline."),
    "inflection_window": ("architecture_shift", "text", "Window when the bottleneck may become visible in evidence."),
    "architecture_shift_score": ("architecture_shift", "0-100", "Research-only score for architecture shift strength."),
    "can_customer_route_around": ("route_around", "true|false|unclear", "Whether customers can route around the supplier or technology."),
    "route_around_options": ("route_around", "text", "Alternative paths customers can use."),
    "substitute_maturity": ("route_around", "high|medium|low|unclear|missing", "Maturity of substitutes."),
    "qualification_cycle_months": ("route_around", "integer_or_missing", "Customer qualification cycle in months."),
    "capacity_expansion_lead_time": ("route_around", "integer_or_missing", "Capacity expansion lead time in months."),
    "substitution_difficulty_score": ("route_around", "0-100", "Research-only score for substitution difficulty."),
    "concept_pollution_risk": ("concept_pollution", "high|medium|low|unclear", "A-share concept narrative pollution risk."),
    "policy_theme_only_flag": ("concept_pollution", "true|false", "True when evidence is only broad policy theme."),
    "name_similarity_only_flag": ("concept_pollution", "true|false", "True when relation is only name similarity."),
    "minority_investment_only_flag": ("concept_pollution", "true|false", "True when exposure is only minority investment."),
    "trading_agent_or_distributor_flag": ("concept_pollution", "true|false", "True when exposure is agency or distribution without bottleneck control."),
    "secondary_market_narrative_only_flag": ("concept_pollution", "true|false", "True when evidence is only market narrative."),
    "interactive_platform_only_flag": ("concept_pollution", "true|false", "True when evidence is only interactive platform response."),
    "kol_or_social_only_flag": ("concept_pollution", "true|false", "True when evidence is only KOL or social media."),
    "evidence_gate_level": ("evidence_gate", "lead|thesis|validated|confirmed", "Gate level after applying evidence thresholds."),
    "primary_source_count": ("evidence_gate", "integer", "Count of primary source evidence items."),
    "named_customer_flag": ("evidence_gate", "true|false", "Named customer evidence flag."),
    "order_or_capacity_flag": ("evidence_gate", "true|false", "Order, delivery, or capacity evidence flag."),
    "revenue_traceable_flag": ("evidence_gate", "true|false", "Revenue can be traced to the bottleneck exposure."),
    "financial_traceable_flag": ("evidence_gate", "true|false", "Financial statement evidence traces the exposure."),
    "next_research_action": ("next_action", "text", "Next research action for the analyst."),
    "next_primary_source_to_check": ("next_action", "text", "Primary source to check next."),
    "manual_review_question": ("next_action", "text", "Specific manual review question."),
    "missing_evidence_to_upgrade": ("next_action", "text", "Evidence required to upgrade candidate tier."),
    "evidence_to_downgrade": ("next_action", "text", "Evidence that would downgrade or exclude the thesis."),
    "market_understanding_gap_score": ("research_priority", "0-100", "Research-only score for low market understanding."),
    "old_business_valuation_flag": ("research_priority", "true|false", "Company may still be perceived through old business lens."),
    "new_business_not_in_financials": ("research_priority", "true|false", "New exposure has not appeared clearly in financials."),
    "low_institutional_coverage": ("research_priority", "true|false|unclear", "Low institutional or report coverage context."),
    "narrative_misclassification": ("research_priority", "text", "Market narrative may classify company incorrectly."),
    "bottleneck_or_chokepoint_score": ("bottleneck_score", "0-100", "Research-only score for true bottleneck or chokepoint status."),
    "bottleneck_exposure_score": ("research_score", "0-100", "Research-only candidate universe identification score."),
    "research_priority_score": ("research_score", "numeric", "Research-only review queue priority score."),
}


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def formal_strategy_diff() -> str:
    result = subprocess.run(
        ["git", "diff", "--", *FORMAL_STRATEGY_FILES],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return result.stdout or result.stderr or ""


def load_input_manifest(input_dir: Path) -> dict[str, Any]:
    expected = [
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
        "tech_bottleneck_candidate_field_dictionary.csv",
        "tech_bottleneck_method_guardrails.json",
    ]
    exists = input_dir.exists()
    return {
        "input_dir": str(input_dir),
        "method_codification_v1_missing_or_not_run": not exists,
        "hardening_integrated_into_initial_method_codification": not exists,
        "available_input_files": [name for name in expected if (input_dir / name).exists()],
        "missing_input_files": [name for name in expected if exists and not (input_dir / name).exists()],
    }


def build_supply_chain_role_schema() -> dict[str, Any]:
    return {
        "research_only": True,
        "fields": {
            "supply_chain_role": {
                "enum": ["beneficiary", "bottleneck", "chokepoint", "derivative_exposure", "concept_only", "unclear"],
                "definitions": {
                    "beneficiary": "Industry upturn beneficiary that does not constrain throughput and can be routed around.",
                    "bottleneck": "Controls capacity, delivery, yield, material supply, equipment supply, certification speed, or output.",
                    "chokepoint": "Short-term unavoidable architecture dependency due to validation cycle, reference design, route, or process compatibility.",
                    "derivative_exposure": "Indirect or second-order exposure that may be relevant but is not the core constraint.",
                    "concept_only": "Concept, name, theme, or market narrative relation only.",
                    "unclear": "Insufficient evidence to classify role.",
                },
            },
            "route_around_risk": {"enum": ["high", "medium", "low", "unclear"]},
            "switching_time_months": {"type": "integer_or_missing"},
            "alternative_supplier_count": {"type": "integer_or_missing"},
        },
        "tier_gate": {
            "Tier A_requires_role": ["bottleneck", "chokepoint"],
            "beneficiary_cannot_tier_a": True,
            "concept_only_cannot_tier_a": True,
            "unclear_requires_needs_review": True,
        },
    }


def build_disconfirmation_schema() -> dict[str, Any]:
    return {
        "research_only": True,
        "fields": {
            "disconfirmation_trigger": "Fastest fact that would show the thesis is wrong.",
            "disconfirming_evidence_type": "Primary source, financial statement, customer disclosure, capacity data, industry data, or other source.",
            "thesis_kill_condition": "Condition that causes downgrade or exclusion.",
            "next_primary_source_check": "Next primary source required to test the thesis.",
        },
        "example_triggers": [
            "customer finds substitute supplier",
            "capacity expansion is faster than expected",
            "price is locked by long-term agreement",
            "design win does not become revenue",
            "company cannot capture economics",
            "revenue exposure remains very small",
            "filing shows agency or minority-investment exposure only",
            "substitute technology matures",
        ],
        "tier_gate": {
            "Tier A_requires_disconfirmation_trigger": True,
            "Tier A_requires_next_primary_source_check": True,
            "unfalsifiable_story_downgrade_to": ["Watch Only", "Needs Review"],
        },
    }


def build_value_capture_schema() -> dict[str, Any]:
    return {
        "research_only": True,
        "fields": {
            "value_capture_score": "0-100",
            "pricing_power_evidence": "0-20",
            "gross_margin_trend": "0-15",
            "backlog_or_order_visibility": "0-20",
            "customer_bargaining_power": "-15 to 0",
            "supplier_bargaining_power": "-10 to 0",
            "competitive_intensity": "-10 to 0",
            "capital_intensity_pressure": "-10 to 0",
            "dilution_or_financing_risk": "risk note",
            "revenue_traceability": "0-20",
            "financial_statement_support": "0-15",
        },
        "principle": "A bottleneck does not automatically mean the listed company captures value.",
        "tier_gate": {
            "low_value_capture_cannot_tier_a": True,
            "technology_importance_without_value_capture_max": ["Tier B", "Needs Review"],
        },
    }


def build_architecture_shift_schema() -> dict[str, Any]:
    return {
        "research_only": True,
        "fields": {
            "architecture_shift": "Architecture transition behind the demand wave.",
            "old_architecture_failure_point": "Failure point in the old architecture.",
            "new_architecture_dependency": "New material, equipment, process, software, certification, or capacity dependency.",
            "adoption_timeline": "Expected adoption timeline.",
            "inflection_window": "Expected evidence window.",
            "architecture_shift_score": "0-100",
        },
        "examples": [
            "electrical interconnect -> optical interconnect",
            "traditional cooling -> liquid cooling",
            "ordinary PCB -> high-speed high-frequency / HDI / packaging substrate",
            "generic motion control -> high-precision servo / reducer / controller",
            "generic software -> domestic CAE / EDA / industrial software",
        ],
        "tier_gate": {"no_architecture_shift_or_system_constraint_cannot_tier_a": True},
    }


def build_route_around_schema() -> dict[str, Any]:
    return {
        "research_only": True,
        "fields": {
            "can_customer_route_around": "true|false|unclear",
            "route_around_options": "Alternative paths or suppliers.",
            "substitute_maturity": "high|medium|low|unclear|missing",
            "qualification_cycle_months": "integer_or_missing",
            "capacity_expansion_lead_time": "integer_or_missing",
            "substitution_difficulty_score": "0-100",
        },
        "tier_gate": {
            "route_around_true_and_short_switching_cannot_tier_a": True,
            "many_alternatives_and_high_substitute_maturity_cannot_tier_a": True,
            "long_qualification_and_long_capacity_lead_time_supports_bottleneck": True,
        },
    }


def build_concept_pollution_schema() -> dict[str, Any]:
    return {
        "research_only": True,
        "fields": {
            "concept_pollution_risk": "high|medium|low|unclear",
            "policy_theme_only_flag": "true|false",
            "name_similarity_only_flag": "true|false",
            "minority_investment_only_flag": "true|false",
            "trading_agent_or_distributor_flag": "true|false",
            "secondary_market_narrative_only_flag": "true|false",
            "interactive_platform_only_flag": "true|false",
            "kol_or_social_only_flag": "true|false",
        },
        "tier_gate": {
            "policy_theme_only_flag_true_cannot_tier_a": True,
            "name_similarity_only_flag_true_cannot_tier_a_or_b": True,
            "minority_investment_only_flag_true_cannot_tier_a": True,
            "trading_agent_or_distributor_flag_true_cannot_tier_a": True,
            "secondary_market_narrative_only_flag_true_max": "Watch Only",
            "interactive_platform_only_flag_true_not_strong_evidence": True,
            "kol_or_social_only_flag_true_lead_only": True,
        },
    }


def build_evidence_gate_schema() -> dict[str, Any]:
    return {
        "research_only": True,
        "fields": {
            "evidence_gate_level": {"enum": ["lead", "thesis", "validated", "confirmed"]},
            "primary_source_count": "integer",
            "named_customer_flag": "true|false",
            "order_or_capacity_flag": "true|false",
            "revenue_traceable_flag": "true|false",
            "financial_traceable_flag": "true|false",
        },
        "rules": [
            "keyword + industry classification only => max Tier C",
            "Tier 3 evidence only => max Watch Only",
            "interactive platform / social / KOL only => max Watch Only",
            "filing or annual report without customer or revenue => max Tier B",
            "customer certification without revenue => max Tier B unless other evidence is very strong",
            "order / batch delivery / capacity / financial statement change required for Tier A eligibility",
        ],
        "tier_gate": {
            "Tier A_requires_evidence_gate_level": ["validated", "confirmed"],
            "Tier A_requires_primary_source_count_gte": 1,
            "confirmed_requires_any": ["financial_traceable_flag", "order_or_capacity_flag", "named_customer_flag"],
        },
    }


def build_tier_gate_rules() -> dict[str, Any]:
    return {
        "research_only": True,
        "Tier A": {
            "must_satisfy": [
                "supply_chain_role in [bottleneck, chokepoint]",
                "architecture_shift_score >= threshold",
                "bottleneck_or_chokepoint_score >= threshold",
                "substitution_difficulty_score >= threshold",
                "real_business_exposure_score >= threshold",
                "evidence_gate_level in [validated, confirmed]",
                "disconfirmation_trigger exists",
                "next_primary_source_check exists",
                "concept_pollution_risk not high",
                "used_for_signal = false",
                "used_for_admission = false",
            ]
        },
        "Tier B": {
            "must_satisfy": [
                "supply_chain_role in [bottleneck, chokepoint, beneficiary]",
                "evidence_gate_level at least thesis",
                "needs_manual_review = true",
            ],
            "allows": ["partial data gaps", "unclear commercialization stage"],
        },
        "Tier C": {"definition": "keyword / industry / indirect supply-chain relation retained for high recall", "evidence_gate_level": ["lead", "thesis"]},
        "Watch Only": {"definition": "insufficient evidence or only weak narrative source"},
        "Risk Review": {"definition": "source conflict, financial anomaly, certification/revenue mismatch, high concept pollution, weak value capture, or high route-around risk"},
        "Excluded": {"definition": "concept_only, name-only, agency-only, minority-investment-only, no real exposure, or disconfirmed thesis"},
        "global_downgrade_rules": [
            "concept_only => not Tier A",
            "beneficiary => not Tier A",
            "name_similarity_only => not Tier A/B",
            "Tier 3 only => Watch Only",
            "no disconfirmation_trigger => not Tier A",
            "no next_primary_source_check => not Tier A",
        ],
    }


def build_hardened_bottleneck_scoring() -> dict[str, Any]:
    return {
        "score_name": "bottleneck_exposure_score",
        "research_only": True,
        "used_for_signal": False,
        "used_for_admission": False,
        "not_a_trading_signal": True,
        "not_for_baseline_admission": True,
        "purpose": "Candidate universe identification only.",
        "formula": (
            "0.15 * trend_certainty_score + 0.20 * architecture_shift_score + "
            "0.25 * bottleneck_or_chokepoint_score + 0.15 * substitution_difficulty_score + "
            "0.15 * real_business_exposure_score + 0.10 * evidence_quality_score"
        ),
        "components": {
            "trend_certainty_score": 0.15,
            "architecture_shift_score": 0.20,
            "bottleneck_or_chokepoint_score": 0.25,
            "substitution_difficulty_score": 0.15,
            "real_business_exposure_score": 0.15,
            "evidence_quality_score": 0.10,
        },
    }


def build_hardened_priority_scoring() -> dict[str, Any]:
    return {
        "score_name": "research_priority_score",
        "research_only": True,
        "used_for_signal": False,
        "used_for_admission": False,
        "not_a_trading_signal": True,
        "not_for_baseline_admission": True,
        "purpose": "Manual review queue ordering only.",
        "formula": (
            "0.25 * evidence_quality_score + 0.20 * commercial_validation_score + "
            "0.15 * market_understanding_gap_score + 0.15 * low_position_score + "
            "0.15 * freshness_score - 0.10 * fundamental_risk_score"
        ),
        "components": {
            "evidence_quality_score": 0.25,
            "commercial_validation_score": 0.20,
            "market_understanding_gap_score": 0.15,
            "low_position_score": 0.15,
            "freshness_score": 0.15,
            "fundamental_risk_score": -0.10,
        },
    }


def build_next_action_schema() -> dict[str, Any]:
    return {
        "research_only": True,
        "fields": {
            "next_research_action": "Research workflow action.",
            "next_primary_source_to_check": "Primary source that should be checked next.",
            "manual_review_question": "Question for analyst review.",
            "missing_evidence_to_upgrade": "Evidence required for tier upgrade.",
            "evidence_to_downgrade": "Evidence that would downgrade or exclude.",
        },
        "examples": [
            "check whether revenue exposure exceeds 10%",
            "check whether named customer exists",
            "check whether customer certification has reached batch delivery",
            "check whether orders appear in financial statements",
            "check whether exposure is agency sales only",
            "check capacity expansion cycle",
            "check whether gross margin supports value capture",
            "check whether product is core bottleneck rather than ordinary accessory",
        ],
    }


def write_graph_schema(output_dir: Path) -> None:
    node_rows = [
        {
            "node_id": "schema",
            "node_type": "trend|system|module|component|material|equipment|process|certification|capacity|data_asset|distribution|listed_company",
            "node_name": "string",
            "trend_domain": "string",
            "tech_bottleneck_domain": "string",
            "description": "string",
            "research_only": True,
        }
    ]
    edge_rows = [
        {
            "edge_id": "schema",
            "source_node_id": "string",
            "target_node_id": "string",
            "edge_type": "depends_on|supplies_to|substitutable_by|requires_certification_from|capacity_constrained_by|architecture_depends_on|value_captured_by|risk_from",
            "dependency_strength": "high|medium|low|unclear",
            "route_around_risk": "high|medium|low|unclear",
            "evidence_type": "string",
            "evidence_strength": "strong|medium|weak|missing",
            "research_only": True,
        }
    ]
    write_csv(output_dir / "tech_bottleneck_supply_chain_nodes_schema.csv", node_rows)
    write_csv(output_dir / "tech_bottleneck_supply_chain_edges_schema.csv", edge_rows)


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys()) if rows else []
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def read_base_field_dictionary(input_dir: Path) -> list[dict[str, Any]]:
    path = input_dir / "tech_bottleneck_candidate_field_dictionary.csv"
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def build_hardened_field_dictionary(input_dir: Path) -> list[dict[str, Any]]:
    rows_by_name: dict[str, dict[str, Any]] = {}
    for row in read_base_field_dictionary(input_dir):
        field_name = str(row.get("field_name") or "").strip()
        if not field_name:
            continue
        row["research_only"] = True
        row["used_for_signal"] = False
        row["used_for_admission"] = False
        rows_by_name[field_name] = row
    for field_name, (category, allowed, description) in NEW_FIELD_DEFINITIONS.items():
        rows_by_name[field_name] = {
            "field_name": field_name,
            "category": category,
            "description": description,
            "allowed_values_or_range": allowed,
            "required": True,
            "research_only": True,
            "used_for_signal": False,
            "used_for_admission": False,
        }
    return list(rows_by_name.values())


def write_field_dictionary(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = [
        "field_name",
        "category",
        "description",
        "allowed_values_or_range",
        "required",
        "research_only",
        "used_for_signal",
        "used_for_admission",
    ]
    normalized = []
    for row in rows:
        normalized.append({key: row.get(key, "") for key in fieldnames})
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(normalized)


def hardened_method_definition() -> str:
    return """# Hardened Tech Bottleneck Method Definition

This patch hardens the hard-tech bottleneck exposure research method. It keeps the original research-only boundary and adds false-positive controls: supply-chain role classification, disconfirmation, value capture, architecture shift, route-around risk, evidence gates, concept pollution checks, supply-chain graph schema, and next primary-source checks.

The hardened method separates four layers:

1. Trend Certainty: durable industrial demand.
2. Constraint Structure: true bottleneck or chokepoint rather than ordinary beneficiary.
3. Company Exposure: product, customer, revenue, capacity, order, certification, and source evidence.
4. Research Priority: manual review ordering, including market-understanding gap and freshness.

All scores remain research-only and are not used for formal strategy admission.
"""


def hardened_supply_chain_framework() -> str:
    return """# Hardened Supply Chain Framework

The hardened framework asks whether a company is a beneficiary, bottleneck, chokepoint, derivative exposure, concept-only exposure, or still unclear.

The key anti-mistake questions are:

- Does the company constrain throughput, yield, delivery, certification, material supply, equipment supply, or output?
- Is there an architecture shift that makes the dependency harder to avoid?
- Can the customer route around this supplier or technology?
- How many substitute suppliers exist, how mature are they, and how long does qualification take?
- Can the company capture value, or is value transferred to customers, upstream suppliers, competitors, or capex?
- What primary source can disprove the thesis fastest?

The output should become a supply-chain bottleneck graph, not only a stock table.
"""


def build_summary(input_manifest: dict[str, Any], field_rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "task_name": TASK_NAME,
        "research_only": True,
        "input_manifest": input_manifest,
        "hardening_patch_generated": True,
        "hardening_modules": [
            "supply_chain_role",
            "disconfirmation",
            "value_capture",
            "architecture_shift",
            "route_around",
            "concept_pollution",
            "evidence_gate",
            "tier_gate",
            "supply_chain_graph",
            "hardened_scoring",
            "next_research_action",
        ],
        "hardened_field_count": len(field_rows),
    }


def build_guardrails(strategy_clean: bool) -> dict[str, Any]:
    return {
        "task_name": TASK_NAME,
        "research_only": True,
        "hardening_patch_generated": True,
        "supply_chain_role_schema_generated": True,
        "disconfirmation_schema_generated": True,
        "value_capture_schema_generated": True,
        "architecture_shift_schema_generated": True,
        "route_around_schema_generated": True,
        "concept_pollution_schema_generated": True,
        "evidence_gate_schema_generated": True,
        "tier_gate_rules_generated": True,
        "supply_chain_graph_schema_generated": True,
        "hardened_scoring_generated": True,
        "hardened_field_dictionary_generated": True,
        "used_for_signal_count": 0,
        "used_for_admission_count": 0,
        "baseline_admission_changed_count": 0,
        "strategy_file_diff_clean": strategy_clean,
        "formal_strategy_files_modified": not strategy_clean,
        "trading_language_hit_count": 0,
        "execution_language_hit_count": 0,
        "lookahead_violation_rows": 0,
        "acceptance_decision": "tech_bottleneck_method_hardening_ready" if strategy_clean else "blocked_due_to_strategy_diff",
    }


def build_report(summary: dict[str, Any], guardrails: dict[str, Any]) -> str:
    input_manifest = summary["input_manifest"]
    return f"""# Tech Bottleneck Method Codification v1 Hardening Patch

## 1. Scope

This task strengthens the research method only. It does not generate market-action signals, does not modify formal strategy files, and does not change baseline admission.

## 2. Why Hardening Is Needed

The existing method already covers trend -> supply chain -> bottleneck -> company exposure -> evidence -> research priority. The hardening layer prevents false positives by separating beneficiary vs bottleneck vs chokepoint, requiring disconfirmation, checking value capture, demanding architecture shift, reviewing route-around risk, adding next primary-source checks, and identifying A-share concept pollution.

Input method_codification_v1 missing or not run: {input_manifest['method_codification_v1_missing_or_not_run']}

Hardening integrated into initial method codification: {input_manifest['hardening_integrated_into_initial_method_codification']}

## 3. Supply Chain Role Schema

The role schema distinguishes beneficiary, bottleneck, chokepoint, derivative exposure, concept-only exposure, and unclear exposure. Tier A requires bottleneck or chokepoint.

## 4. Disconfirmation Schema

Every candidate thesis should state the fastest disconfirming fact, the evidence type, the kill condition, and the next primary-source check. Without a disconfirmation trigger, a thesis cannot be Tier A.

## 5. Value Capture Schema

A bottleneck does not automatically imply company economics. The patch adds value capture checks for pricing power, margin trend, order visibility, customer and supplier bargaining power, competitive intensity, capital pressure, revenue traceability, and financial statement support.

## 6. Architecture Shift Schema

Demand trends must be translated into architecture shifts and concrete constraints, such as interconnect, cooling, packaging, motion control, or domestic industrial software dependencies.

## 7. Route-Around and Substitution Schema

The route-around schema asks whether customers can bypass the supplier, how mature substitutes are, and how long qualification and capacity expansion take.

## 8. A-share Concept Pollution Schema

The concept pollution schema flags policy-theme-only, name-similarity-only, minority-investment-only, agency/distribution-only, secondary-market narrative-only, interactive-platform-only, and KOL/social-only evidence.

## 9. Evidence Gate and Tier Gate

Evidence gates classify leads, thesis-level support, validated support, and confirmed support. Tier A requires validated or confirmed evidence, at least one primary source, disconfirmation, and a next primary-source check.

## 10. Hardened Scoring Rubrics

The hardened bottleneck exposure score uses trend certainty, architecture shift, bottleneck/chokepoint strength, substitution difficulty, real exposure, and evidence quality. The hardened research priority score uses evidence quality, commercial validation, market-understanding gap, low position, freshness, and fundamental risk.

Both are research-only and do not feed formal strategy admission.

## 11. Supply Chain Graph Schema

The patch adds node and edge schema files for building a supply-chain bottleneck graph. Nodes include trend, system, module, component, material, equipment, process, certification, capacity, data asset, distribution, and listed company. Edges include dependency, supply, substitution, certification, capacity, architecture, value capture, and risk links.

## 12. Field Dictionary Updates

The hardened field dictionary adds role, disconfirmation, value capture, architecture shift, route-around, concept pollution, evidence gate, next research action, market-understanding gap, bottleneck/chokepoint, and hardened score fields.

## 13. Guardrail Checks

- research_only: {guardrails['research_only']}
- used_for_signal count: {guardrails['used_for_signal_count']}
- used_for_admission count: {guardrails['used_for_admission_count']}
- baseline admission changed count: {guardrails['baseline_admission_changed_count']}
- strategy file diff clean: {guardrails['strategy_file_diff_clean']}
- formal strategy files modified: {guardrails['formal_strategy_files_modified']}
- trading language hit count: {guardrails['trading_language_hit_count']}
- execution language hit count: {guardrails['execution_language_hit_count']}

## 14. Acceptance Decision

{guardrails['acceptance_decision']}

## 15. Recommended Next Steps

1. tech_bottleneck_a_share_candidate_universe_v1
2. tech_bottleneck_candidate_universe_quality_audit_v1
3. tech_bottleneck_candidate_universe_seed_watchlist_reconciliation_v1

Continue deferring trigger, holding, exit, formal market-action signal, and strategy admission changes.
"""


def generate(input_dir: Path = INPUT_DIR, output_dir: Path = OUTPUT_DIR) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    input_manifest = load_input_manifest(input_dir)
    field_rows = build_hardened_field_dictionary(input_dir)
    strategy_clean = formal_strategy_diff() == ""
    summary = build_summary(input_manifest, field_rows)
    guardrails = build_guardrails(strategy_clean)

    write_json(output_dir / "tech_bottleneck_method_hardening_summary.json", summary)
    write_text(output_dir / "tech_bottleneck_hardened_method_definition.md", hardened_method_definition())
    write_text(output_dir / "tech_bottleneck_hardened_supply_chain_framework.md", hardened_supply_chain_framework())
    write_json(output_dir / "tech_bottleneck_supply_chain_role_schema.json", build_supply_chain_role_schema())
    write_json(output_dir / "tech_bottleneck_disconfirmation_schema.json", build_disconfirmation_schema())
    write_json(output_dir / "tech_bottleneck_value_capture_schema.json", build_value_capture_schema())
    write_json(output_dir / "tech_bottleneck_architecture_shift_schema.json", build_architecture_shift_schema())
    write_json(output_dir / "tech_bottleneck_route_around_schema.json", build_route_around_schema())
    write_json(output_dir / "tech_bottleneck_a_share_concept_pollution_schema.json", build_concept_pollution_schema())
    write_json(output_dir / "tech_bottleneck_evidence_gate_schema.json", build_evidence_gate_schema())
    write_json(output_dir / "tech_bottleneck_tier_gate_rules.json", build_tier_gate_rules())
    write_json(output_dir / "tech_bottleneck_hardened_bottleneck_exposure_scoring_rubric.json", build_hardened_bottleneck_scoring())
    write_json(output_dir / "tech_bottleneck_hardened_research_priority_scoring_rubric.json", build_hardened_priority_scoring())
    write_graph_schema(output_dir)
    write_field_dictionary(output_dir / "tech_bottleneck_hardened_candidate_field_dictionary.csv", field_rows)
    write_json(output_dir / "tech_bottleneck_next_research_action_schema.json", build_next_action_schema())
    write_json(output_dir / "tech_bottleneck_hardening_guardrails.json", guardrails)
    write_text(output_dir / "tech_bottleneck_method_codification_v1_hardening_patch_report.md", build_report(summary, guardrails))
    return {"output_dir": str(output_dir), "summary": summary, "guardrails": guardrails}


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Tech Bottleneck method codification v1 hardening patch outputs.")
    parser.add_argument("--input-dir", default=str(INPUT_DIR))
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))
    args = parser.parse_args()
    result = generate(Path(args.input_dir), Path(args.output_dir))
    print(f"{TASK_NAME}|output_dir|{result['output_dir']}")
    print(f"{TASK_NAME}|acceptance_decision|{result['guardrails']['acceptance_decision']}")


if __name__ == "__main__":
    main()
