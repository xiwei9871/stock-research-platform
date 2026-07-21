from __future__ import annotations

from copy import deepcopy

import pytest

from stock_research.research_project_v2.errors import ResearchProjectV2Error
from stock_research.research_project_v2_1.gap_review import (
    load_gap_review_artifact,
    render_gap_review_report,
    validate_gap_review_artifact,
    validate_persisted_gap_review_report,
    validate_gap_universe,
    validate_input_bindings,
    validate_research_design,
)
from stock_research.research_project_v2_1.layout import LayeredResearchLayout
from stock_research.research_project_v2_1.schema import validate_v2_1_schema_payload


PROVENANCE = {
    "created_by": "Codex",
    "actor_type": "codex",
    "agent_run_id": "gap-review-test",
    "created_at": "2026-07-21T00:00:00Z",
    "created_in_version": "research_version:ai_compute_pcb_industry_bottleneck:0.2.1",
    "review_status": "unreviewed",
}
EXPECTED_GROUPS = {
    "GAP-SIGNAL": "group_a_signal_transmission",
    "GAP-LOSS": "group_a_signal_transmission",
    "GAP-LAYERS": "group_a_signal_transmission",
    "GAP-LAMINATE": "group_b_material_capability",
    "GAP-BACKDRILL": "group_c_manufacturing_testing",
    "GAP-LAMINATION": "group_c_manufacturing_testing",
    "GAP-THERMAL": "group_c_manufacturing_testing",
    "GAP-TEST": "group_c_manufacturing_testing",
    "GAP-YIELD": "group_c_manufacturing_testing",
    "GAP-CAPACITY": "group_d_bottleneck_effective_capacity",
}


def minimal_gap_review() -> dict:
    return {
        "schema_version": "2.6.0",
        "artifact_type": "evidence_gap_review_and_targeted_research_design",
        "review_id": "evidence_gap_review:ai_pcb:v1",
        "project_id": "research_project:ai_compute_pcb_industry_bottleneck",
        "input_bindings": {},
        "execution_policy": {
            "execution_mode": "offline_read_only_research_design",
            "network_access": False,
            "new_acquisition": False,
            "evidence_assessment_of_new_sources": False,
            "framework_expansion": False,
        },
        "group_definitions": [],
        "gap_reviews": [],
        "evidence_requirements": [],
        "source_class_boundaries": [],
        "cross_level_inference_rules": [],
        "stopping_state_definitions": [],
        "governance": {
            "future_acquisition_authorized": False,
            "stage_a2_authorized": False,
            "stage_b_authorized": False,
            "company_mapping_authorized": False,
            "bottleneck_judgment_authorized": False,
            "value_migration_judgment_authorized": False,
        },
        "provenance": PROVENANCE,
        "content_hash": "0" * 64,
    }


def test_schema_v2_6_accepts_gap_review_artifact() -> None:
    validate_v2_1_schema_payload("evidence_gap_review_v2_6", minimal_gap_review())


def test_schema_v2_6_rejects_enabled_authorization() -> None:
    artifact = deepcopy(minimal_gap_review())
    artifact["governance"]["future_acquisition_authorized"] = True
    with pytest.raises(ResearchProjectV2Error):
        validate_v2_1_schema_payload("evidence_gap_review_v2_6", artifact)


def test_schema_v2_6_rejects_unknown_top_level_field() -> None:
    artifact = deepcopy(minimal_gap_review())
    artifact["company_candidates"] = []
    with pytest.raises(ResearchProjectV2Error):
        validate_v2_1_schema_payload("evidence_gap_review_v2_6", artifact)


def valid_gap_rows() -> list[dict]:
    return [
        {"gap_id": gap_id, "gap_group": gap_group}
        for gap_id, gap_group in EXPECTED_GROUPS.items()
    ]


def test_gap_universe_requires_exact_ten_upstream_gaps() -> None:
    assert validate_gap_universe(valid_gap_rows(), EXPECTED_GROUPS) == sorted(
        EXPECTED_GROUPS
    )


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "unknown", "wrong_group"])
def test_gap_universe_rejects_drift(mutation: str) -> None:
    rows = valid_gap_rows()
    if mutation == "missing":
        rows.pop()
    elif mutation == "duplicate":
        rows[-1] = deepcopy(rows[0])
    elif mutation == "unknown":
        rows[-1]["gap_id"] = "GAP-UNKNOWN"
    else:
        rows[0]["gap_group"] = "group_d_bottleneck_effective_capacity"
    with pytest.raises(ResearchProjectV2Error):
        validate_gap_universe(rows, EXPECTED_GROUPS)


def test_input_binding_rejects_cognition_package_hash_drift() -> None:
    artifact = minimal_gap_review()
    artifact["input_bindings"] = {
        "cognition_package_path": "analysis/ai_pcb_industry_cognition_package_v1.json",
        "cognition_package_hash": "0" * 64,
        "cognition_audit_path": "analysis/ai_pcb_industry_cognition_audit_v1.json",
        "cognition_audit_hash": "b2bade2473e8016f1f06b7d8b40cbe40c5bae60b2d8f1b685312ddbf83e717c9",
        "cognition_report_path": "reports/ai_pcb_industry_cognition_report_v1.md",
        "cognition_report_hash": "8770304b84ce5815071da52a47cd8d2da7f5ab70c70d350dde7a704eb98fabad",
        "acquisition_checkpoint_id": "acquisition_checkpoint:a5f7627d8726c9405ba67a75",
        "acquisition_checkpoint_hash": "a5f7627d8726c9405ba67a7527826edb0cff26ee777287e33cb55442bace660e",
    }
    with pytest.raises(ResearchProjectV2Error) as exc_info:
        validate_input_bindings(artifact, layout=LayeredResearchLayout.default())
    assert exc_info.value.code == "RESEARCH_PROJECT_V2_1_GAP_REVIEW_UPSTREAM_DRIFT"


def complete_design_artifact() -> dict:
    artifact = minimal_gap_review()
    artifact["group_definitions"] = [
        {"group_id": group_id, "name": group_id}
        for group_id in sorted(set(EXPECTED_GROUPS.values()))
    ]
    reviews = []
    requirements = []
    for index, (gap_id, group_id) in enumerate(EXPECTED_GROUPS.items(), 1):
        er_id = f"PCB-ER-{index:02d}"
        availability = (
            "structurally_limited"
            if gap_id in {"GAP-YIELD", "GAP-CAPACITY"}
            else "likely_publicly_available"
        )
        ceiling = (
            "structurally_limited"
            if availability == "structurally_limited"
            else "technical_understanding_only"
        )
        reviews.append(
            {
                "gap_id": gap_id,
                "gap_group": group_id,
                "original_gap_description": f"Original {gap_id}",
                "current_grounded_knowledge": ["Existing demand-side boundary only."],
                "current_unknowns": ["The PCB-side mechanism remains unknown."],
                "atomic_research_questions": [
                    {
                        "question_id": f"Q-{index:02d}",
                        "question": f"What evidence is required for {gap_id}?",
                        "target_cognition_level": "technical_understanding",
                        "evidence_requirement_ids": [er_id],
                    }
                ],
                "new_evidence_requirement_ids": [er_id],
                "required_atomic_facts": ["A scoped engineering fact."],
                "required_evidence_types": ["engineering_measurement"],
                "suggested_source_classes": ["technical_standard"],
                "suggested_search_concepts": ["scoped engineering measurement"],
                "public_evidence_availability": availability,
                "public_evidence_ceiling": ceiling,
                "source_independence_requirements": ["One supplier-independent chain."],
                "freshness_requirements": ["Match the relevant product generation."],
                "scope_and_generation_requirements": ["Record speed and topology."],
                "comparison_denominator": "per specified channel and generation",
                "minimum_sufficiency_conditions": ["Required measurement is available."],
                "contradiction_search_requirements": ["Search a conflicting measurement."],
                "stop_conditions": ["Stop at the public evidence ceiling."],
                "non_derivable_conclusions": ["Does not establish a commercial bottleneck."],
                "priority": "high",
                "priority_reason": "Blocks later cognition.",
                "dependencies": [],
                "future_acquisition_authorized": False,
            }
        )
        requirements.append(
            {
                "er_id": er_id,
                "gap_id": gap_id,
                "research_question": f"What scoped fact resolves {gap_id}?",
                "claim_scope": "atomic_engineering_fact",
                "required_fact_types": ["measured_parameter"],
                "required_source_classes": ["technical_standard"],
                "minimum_independent_evidence_chains": 1,
                "supplier_independent_source_required": True,
                "freshness_rule": "Same interface generation or explicitly comparable.",
                "comparison_scope": "Specified channel, speed and topology.",
                "denominator_rule": "Per specified channel and generation.",
                "sufficiency_rule": "A direct scoped measurement and method are present.",
                "contradiction_rule": "Search for conflicting measurements or scope limits.",
                "stop_rule": "Stop when the minimum condition or public ceiling is reached.",
                "maximum_supported_cognition_level": "technical_understanding",
                "prohibited_inferences": ["Cannot establish a manufacturing bottleneck."],
            }
        )
    artifact["gap_reviews"] = reviews
    artifact["evidence_requirements"] = requirements
    artifact["source_class_boundaries"] = [
        {
            "source_class": "technical_standard",
            "can_support": ["technical mechanism"],
            "cannot_support": ["commercial bottleneck"],
        }
    ]
    artifact["cross_level_inference_rules"] = [
        {
            "rule_id": "RULE-01",
            "from_level": "technical_understanding",
            "prohibited_target_level": "manufacturing_bottleneck",
            "reason": "Additional manufacturing evidence is required.",
        }
    ]
    artifact["stopping_state_definitions"] = [
        {"state": "resolved", "meaning": "Minimum sufficiency reached."},
        {
            "state": "stopped_due_to_structural_limit",
            "meaning": "Public evidence ceiling reached without resolution.",
        },
    ]
    return artifact


def test_complete_atomic_research_design_is_valid() -> None:
    result = validate_research_design(complete_design_artifact())
    assert result["gap_count"] == 10
    assert result["evidence_requirement_count"] == 10


@pytest.mark.parametrize(
    ("target", "field"),
    [
        ("gap", "atomic_research_questions"),
        ("gap", "stop_conditions"),
        ("gap", "non_derivable_conclusions"),
        ("er", "required_fact_types"),
        ("er", "denominator_rule"),
        ("er", "stop_rule"),
        ("er", "prohibited_inferences"),
    ],
)
def test_research_design_rejects_missing_required_boundary(target: str, field: str) -> None:
    artifact = complete_design_artifact()
    row = artifact["gap_reviews"][0] if target == "gap" else artifact["evidence_requirements"][0]
    row[field] = [] if isinstance(row[field], list) else ""
    with pytest.raises(ResearchProjectV2Error):
        validate_research_design(artifact)


def test_structurally_limited_gap_cannot_promise_full_resolution() -> None:
    artifact = complete_design_artifact()
    yield_gap = next(row for row in artifact["gap_reviews"] if row["gap_id"] == "GAP-YIELD")
    yield_gap["public_evidence_ceiling"] = "fully_resolvable"
    with pytest.raises(ResearchProjectV2Error):
        validate_research_design(artifact)


def test_future_acquisition_and_stage_authorization_are_rejected() -> None:
    artifact = complete_design_artifact()
    artifact["gap_reviews"][0]["future_acquisition_authorized"] = True
    with pytest.raises(ResearchProjectV2Error):
        validate_research_design(artifact)


def test_group_a_er_cannot_claim_manufacturing_or_capacity_cognition() -> None:
    artifact = complete_design_artifact()
    artifact["evidence_requirements"][0][
        "maximum_supported_cognition_level"
    ] = "effective_capacity_bounded"
    with pytest.raises(ResearchProjectV2Error):
        validate_research_design(artifact)


def test_gap_review_report_is_deterministic_under_array_reordering() -> None:
    artifact = complete_design_artifact()
    expected = render_gap_review_report(artifact)
    artifact["gap_reviews"].reverse()
    artifact["evidence_requirements"].reverse()
    artifact["group_definitions"].reverse()
    assert render_gap_review_report(artifact) == expected


def test_gap_review_report_marks_design_ceiling_and_non_derivable_boundaries() -> None:
    report = render_gap_review_report(complete_design_artifact()).decode("utf-8")
    assert "[RESEARCH DESIGN — NOT EVIDENCE]" in report
    assert "Public evidence ceiling" in report
    assert "Non-derivable conclusions" in report
    assert "Future acquisition authorized: False" in report


def test_persisted_gap_review_report_rejects_added_content() -> None:
    artifact = complete_design_artifact()
    report = render_gap_review_report(artifact) + b"\nUnregistered conclusion.\n"
    with pytest.raises(ResearchProjectV2Error):
        validate_persisted_gap_review_report(artifact, report)


def test_repository_gap_review_artifact_and_report_are_valid() -> None:
    layout = LayeredResearchLayout.default()
    artifact = load_gap_review_artifact(
        layout.analysis_dir
        / "ai_pcb_evidence_gap_review_and_targeted_research_design_v1.json",
        layout=layout,
    )
    result = validate_gap_review_artifact(artifact, layout=layout)
    report = (
        layout.reports_dir
        / "ai_pcb_evidence_gap_review_and_targeted_research_design_v1.md"
    ).read_bytes()
    validate_persisted_gap_review_report(artifact, report)
    assert result == {
        "gap_count": 10,
        "atomic_question_count": 32,
        "evidence_requirement_count": 32,
        "scope_leakage": [],
    }
