from copy import deepcopy
import warnings

import pytest

from stock_research.research_project_v2.errors import ResearchProjectV2Error


with warnings.catch_warnings():
    warnings.filterwarnings(
        "ignore",
        message=r"jsonschema\.RefResolver is deprecated as of v4\.18\.0.*",
        category=DeprecationWarning,
    )
    from stock_research.research_project_v2.loader import (
        SCHEMA_FILES,
        validate_schema_payload,
    )


PROVENANCE = {
    "created_by": "fixture-author",
    "actor_type": "human",
    "agent_run_id": None,
    "created_at": "2026-07-17T10:00:00+08:00",
    "created_in_version": "research_version:fixture:0.1.0",
    "review_status": "unreviewed",
}


@pytest.fixture
def sample_identity():
    return {
        "project_id": "research_project:fixture",
        "project_slug": "fixture",
        "title": "Fixture research project",
        "purpose": "Exercise the versioned research-project schema.",
        "created_at": "2026-07-17T10:00:00+08:00",
        "created_by": "fixture-author",
        "current_lifecycle_state": "research_ready",
        "current_version": "research_version:fixture:0.1.0",
        "latest_reviewed_version": None,
        "latest_published_version": None,
    }


@pytest.fixture
def sample_version():
    return {
        "artifact_version": "2.0.0",
        "version_id": "research_version:fixture:0.1.0",
        "project_id": "research_project:fixture",
        "semantic_version": "0.1.0",
        "parent_version_id": None,
        "creation_stage": "research_design",
        "created_at": "2026-07-17T10:00:00+08:00",
        "created_by": "fixture-author",
        "change_summary": "Create the initial research design.",
        "change_reason": "Initialize the fixture.",
        "incorporated_event_ids": ["research_event:fixture:created"],
        "content_hash": "a" * 64,
        "snapshot": {
            "project_lifecycle_state": "research_ready",
            "evidence_stage": "requirements_defined",
            "conclusion_status": "unavailable",
            "investment_status": "not_assessed",
            "scope": {
                "primary_question": "Can the fixture thesis be validated?",
                "research_object": "Fixture technology",
                "included_scope": ["Primary system"],
                "excluded_scope": ["Unrelated systems"],
                "geography": ["Global"],
                "time_horizon": "2026-2030",
                "industry_boundary": "Fixture industry",
                "company_universe_boundary": "Public fixture companies",
                "decision_context": "Research design validation",
                "assumptions": ["Fixture data is illustrative"],
                "known_unknowns": ["Commercial timing"],
                "stop_conditions": ["Primary mechanism is disproven"],
            },
            "router_decision": {
                "primary_method": "system_architecture",
                "secondary_methods": ["manufacturing_process"],
                "routing_reasons": ["System dependencies drive outcomes"],
                "required_research_modules": ["architecture"],
                "excluded_modules": ["regulation"],
                "confidence": 0.8,
                "manual_override": False,
                "override_reason": None,
                "decided_by": "fixture-author",
                "decided_at": "2026-07-17T10:00:00+08:00",
            },
            "questions": [
                {
                    "question_id": "question:primary",
                    "question_type": "primary",
                    "question_text": "Does the primary mechanism work?",
                    "priority": 1,
                    "required_for_gate": True,
                    "answer_status": "unanswered",
                    "linked_claim_ids": ["claim:primary"],
                    "linked_requirement_ids": ["requirement:primary"],
                    "provenance": PROVENANCE,
                    "lifecycle_status": "active",
                },
                {
                    "question_id": "question:counterfactual",
                    "question_type": "counterfactual",
                    "question_text": "What would disprove the mechanism?",
                    "priority": 2,
                    "required_for_gate": True,
                    "answer_status": "unanswered",
                    "linked_claim_ids": ["claim:counter"],
                    "linked_requirement_ids": ["requirement:counter"],
                    "provenance": PROVENANCE,
                    "lifecycle_status": "active",
                },
            ],
            "question_tree_nodes": [
                {
                    "tree_node_id": "tree_node:primary",
                    "tree_id": "question_tree:fixture",
                    "question_id": "question:primary",
                    "parent_tree_node_id": None,
                    "order": 1,
                    "branch_role": "root",
                    "dependency_question_ids": [],
                },
                {
                    "tree_node_id": "tree_node:counterfactual",
                    "tree_id": "question_tree:fixture",
                    "question_id": "question:counterfactual",
                    "parent_tree_node_id": "tree_node:primary",
                    "order": 2,
                    "branch_role": "counterfactual",
                    "dependency_question_ids": ["question:primary"],
                },
            ],
            "claims": [
                {
                    "claim_id": "claim:primary",
                    "claim_kind": "primary",
                    "epistemic_type": "hypothesis",
                    "claim_text": "The primary mechanism creates value.",
                    "claim_status": "hypothesis",
                    "lifecycle_status": "active",
                    "confidence": 0.4,
                    "importance": 1.0,
                    "linked_question_ids": ["question:primary"],
                    "context_reference_ids": [],
                    "created_in_version": "research_version:fixture:0.1.0",
                    "supersedes_claim_id": None,
                    "validation_metric_ids": ["metric:primary"],
                    "invalidation_condition_ids": ["condition:primary"],
                    "provenance": PROVENANCE,
                },
                {
                    "claim_id": "claim:counter",
                    "claim_kind": "counter",
                    "epistemic_type": "hypothesis",
                    "claim_text": "A constraint prevents value creation.",
                    "claim_status": "under_test",
                    "lifecycle_status": "active",
                    "confidence": 0.3,
                    "importance": 0.8,
                    "linked_question_ids": ["question:counterfactual"],
                    "context_reference_ids": [],
                    "created_in_version": "research_version:fixture:0.1.0",
                    "supersedes_claim_id": None,
                    "validation_metric_ids": [],
                    "invalidation_condition_ids": [],
                    "provenance": PROVENANCE,
                },
            ],
            "claim_relations": [
                {
                    "relation_id": "claim_relation:counter",
                    "from_claim_id": "claim:counter",
                    "to_claim_id": "claim:primary",
                    "relation_type": "challenges",
                    "relation_summary": "The constraint challenges the primary claim.",
                    "created_in_version": "research_version:fixture:0.1.0",
                    "provenance": PROVENANCE,
                }
            ],
            "evidence_requirements": [
                {
                    "requirement_id": "requirement:primary",
                    "target_type": "research_claim",
                    "target_id": "claim:primary",
                    "question_to_resolve": "Is the mechanism observed?",
                    "requirement_type": "validation",
                    "required_source_classes": ["primary"],
                    "required_independence": "independent",
                    "required_freshness": "within_12_months",
                    "required_scope": "global",
                    "minimum_coverage": 2,
                    "conflict_search_required": True,
                    "primary_source_required": True,
                    "collection_status": "not_started",
                    "satisfaction_status": "unsatisfied",
                    "provenance": PROVENANCE,
                },
                {
                    "requirement_id": "requirement:counter",
                    "target_type": "research_claim",
                    "target_id": "claim:counter",
                    "question_to_resolve": "Does the constraint bind?",
                    "requirement_type": "counterevidence",
                    "required_source_classes": ["primary", "independent_secondary"],
                    "required_independence": "independent",
                    "required_freshness": "within_12_months",
                    "required_scope": "global",
                    "minimum_coverage": 1,
                    "conflict_search_required": True,
                    "primary_source_required": False,
                    "collection_status": "not_started",
                    "satisfaction_status": "unsatisfied",
                    "provenance": PROVENANCE,
                },
            ],
            "references": [],
            "evidence_assessments": [],
            "causal_nodes": [
                {
                    "causal_node_id": "causal_node:mechanism",
                    "node_kind": "mechanism",
                    "node_text": "Primary mechanism",
                    "lifecycle_status": "active",
                    "provenance": PROVENANCE,
                },
                {
                    "causal_node_id": "causal_node:outcome",
                    "node_kind": "outcome",
                    "node_text": "Value creation",
                    "lifecycle_status": "active",
                    "provenance": PROVENANCE,
                },
            ],
            "causal_edges": [
                {
                    "causal_edge_id": "causal_edge:primary",
                    "from_causal_node_id": "causal_node:mechanism",
                    "to_causal_node_id": "causal_node:outcome",
                    "relation_type": "causes",
                    "mechanism_text": "The mechanism improves the outcome.",
                    "effect_polarity": "positive",
                    "strength": 0.5,
                    "confidence": 0.4,
                    "time_lag": "12 months",
                    "boundary_condition": "Only at commercial scale",
                    "feedback_loop_id": None,
                    "supporting_claim_ids": ["claim:primary"],
                    "validation_metric_ids": ["metric:primary"],
                    "lifecycle_status": "active",
                    "provenance": PROVENANCE,
                }
            ],
            "validation_metrics": [
                {
                    "metric_id": "metric:primary",
                    "target_type": "research_claim",
                    "target_id": "claim:primary",
                    "metric_name": "Primary metric",
                    "metric_definition": "Measures the primary outcome.",
                    "data_source_plan": "Collect audited primary data.",
                    "unit": "percent",
                    "baseline_value": None,
                    "baseline_as_of": None,
                    "comparison_operator": ">=",
                    "observation_window": "12 months",
                    "aggregation_method": "median",
                    "expected_range": "10-20",
                    "confirmation_threshold": 10,
                    "warning_threshold": 5,
                    "data_freshness_requirement": "quarterly",
                    "observation_frequency": "quarterly",
                    "status": "planned",
                    "provenance": PROVENANCE,
                }
            ],
            "invalidation_conditions": [
                {
                    "condition_id": "condition:primary",
                    "target_type": "research_claim",
                    "target_id": "claim:primary",
                    "condition_text": "The metric remains below threshold.",
                    "observable_test": "Observe the primary metric.",
                    "comparison_operator": "<",
                    "threshold_value": 5,
                    "unit": "percent",
                    "persistence_window": "2 quarters",
                    "minimum_observations": 2,
                    "recovery_condition": "Metric exceeds threshold.",
                    "severity": "critical",
                    "status": "active",
                    "triggered_at": None,
                    "provenance": PROVENANCE,
                }
            ],
            "company_capture_assessments": [],
        },
    }


@pytest.fixture
def sample_event():
    return {
        "event_id": "research_event:fixture:created",
        "project_id": "research_project:fixture",
        "event_type": "project_created",
        "triggered_at": "2026-07-17T10:00:00+08:00",
        "trigger_source": "fixture-author",
        "affected_object_ids": ["research_project:fixture"],
        "base_version_id": None,
        "proposed_action": "Create the initial design version.",
        "review_status": "unreviewed",
        "resolution": None,
        "incorporated_version_id": "research_version:fixture:0.1.0",
        "notes": None,
        "provenance": PROVENANCE,
    }


def test_identity_accepts_pointer_only_payload(sample_identity):
    validate_schema_payload("research_project_identity_v2", sample_identity)


def test_canonical_schema_names_are_registered():
    assert set(SCHEMA_FILES) == {
        "research_project_identity_v2",
        "research_version_v2",
        "research_event_v2",
        "research_project_index_v2",
    }


def test_research_design_rejects_supported_claim(sample_version):
    invalid_version = deepcopy(sample_version)
    invalid_version["snapshot"]["claims"][0]["claim_status"] = "supported"

    with pytest.raises(ResearchProjectV2Error) as exc_info:
        validate_schema_payload("research_version_v2", invalid_version)

    assert exc_info.value.code == "RESEARCH_PROJECT_SCHEMA_INVALID"
    assert exc_info.value.details == {
        "path": "snapshot.claims.0.claim_status",
        "schema": "research_version_v2",
    }


def test_selected_fields_hash_scope_requires_hash_fields(sample_version):
    invalid_version = deepcopy(sample_version)
    invalid_version["snapshot"]["references"] = [
        {
            "reference_id": "reference:selected-fields",
            "reference_namespace": "external_document",
            "reference_type": "report",
            "reference_object_id": "document:fixture",
            "reference_role": "context",
            "reference_version": None,
            "reference_content_hash": "b" * 64,
            "hash_scope": "selected_fields",
            "referenced_at": "2026-07-17T10:00:00+08:00",
            "locator": "fixture://document",
            "scope_note": None,
            "resolution_status": "resolved",
            "provenance": PROVENANCE,
        }
    ]

    with pytest.raises(ResearchProjectV2Error) as exc_info:
        validate_schema_payload("research_version_v2", invalid_version)

    assert exc_info.value.code == "RESEARCH_PROJECT_SCHEMA_INVALID"


def test_selected_fields_hash_scope_accepts_non_empty_hash_fields(sample_version):
    valid_version = deepcopy(sample_version)
    valid_version["snapshot"]["references"] = [
        {
            "reference_id": "reference:selected-fields",
            "reference_namespace": "external_document",
            "reference_type": "report",
            "reference_object_id": "document:fixture",
            "reference_role": "context",
            "reference_version": None,
            "reference_content_hash": "b" * 64,
            "hash_scope": "selected_fields",
            "hash_fields": ["/sections/0/content"],
            "referenced_at": "2026-07-17T10:00:00+08:00",
            "locator": "fixture://document",
            "scope_note": None,
            "resolution_status": "resolved",
            "provenance": PROVENANCE,
        }
    ]

    validate_schema_payload("research_version_v2", valid_version)


@pytest.mark.parametrize(
    "invalid_pointer",
    ["$.sections[0].content", "sections.0.content"],
)
def test_selected_fields_hash_scope_rejects_non_json_pointers(
    sample_version,
    invalid_pointer,
):
    invalid_version = deepcopy(sample_version)
    invalid_version["snapshot"]["references"] = [
        {
            "reference_id": "reference:selected-fields",
            "reference_namespace": "external_document",
            "reference_type": "report",
            "reference_object_id": "document:fixture",
            "reference_role": "context",
            "reference_version": None,
            "reference_content_hash": "b" * 64,
            "hash_scope": "selected_fields",
            "hash_fields": [invalid_pointer],
            "referenced_at": "2026-07-17T10:00:00+08:00",
            "locator": "fixture://document",
            "scope_note": None,
            "resolution_status": "resolved",
            "provenance": PROVENANCE,
        }
    ]

    with pytest.raises(ResearchProjectV2Error) as exc_info:
        validate_schema_payload("research_version_v2", invalid_version)

    assert exc_info.value.code == "RESEARCH_PROJECT_SCHEMA_INVALID"


@pytest.mark.parametrize("field_name", ["created_by", "created_in_version"])
def test_provenance_rejects_empty_identity_fields(sample_version, field_name):
    invalid_version = deepcopy(sample_version)
    invalid_version["snapshot"]["claims"][0]["provenance"][field_name] = ""

    with pytest.raises(ResearchProjectV2Error) as exc_info:
        validate_schema_payload("research_version_v2", invalid_version)

    assert exc_info.value.code == "RESEARCH_PROJECT_SCHEMA_INVALID"


def test_event_requires_event_id(sample_event):
    invalid_event = deepcopy(sample_event)
    del invalid_event["event_id"]

    with pytest.raises(ResearchProjectV2Error) as exc_info:
        validate_schema_payload("research_event_v2", invalid_event)

    assert exc_info.value.code == "RESEARCH_PROJECT_SCHEMA_INVALID"
    assert exc_info.value.details == {
        "path": "",
        "schema": "research_event_v2",
    }


def test_unknown_schema_name_uses_stable_domain_error(sample_identity):
    with pytest.raises(ResearchProjectV2Error) as exc_info:
        validate_schema_payload("missing", sample_identity)

    assert exc_info.value.code == "RESEARCH_PROJECT_SCHEMA_NOT_FOUND"
    assert exc_info.value.details == {"schema": "missing"}
