from copy import deepcopy
import warnings

import pytest

from stock_research.research_project_v2.errors import ResearchProjectV2Error


with warnings.catch_warnings():
    warnings.filterwarnings("ignore", category=DeprecationWarning)
    from stock_research.research_project_v2.loader import validate_schema_payload

from stock_research.research_project_v2.semantic import validate_version_semantics


PROVENANCE = {
    "created_by": "fixture-author",
    "actor_type": "human",
    "agent_run_id": None,
    "created_at": "2026-07-17T10:00:00+08:00",
    "created_in_version": "research_version:fixture:0.1.0",
    "review_status": "unreviewed",
}


def _metric(metric_id="metric:primary", target_id="claim:primary"):
    return {
        "metric_id": metric_id,
        "target_type": "research_claim",
        "target_id": target_id,
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


def _causal_edge(
    edge_id,
    from_node,
    to_node,
    feedback_loop_id=None,
    metric_ids=None,
):
    return {
        "causal_edge_id": edge_id,
        "from_causal_node_id": from_node,
        "to_causal_node_id": to_node,
        "relation_type": "causes",
        "mechanism_text": "The mechanism changes the outcome.",
        "effect_polarity": "positive",
        "strength": 0.5,
        "confidence": 0.4,
        "time_lag": "12 months",
        "boundary_condition": None,
        "feedback_loop_id": feedback_loop_id,
        "supporting_claim_ids": ["claim:primary"],
        "validation_metric_ids": ["metric:primary"] if metric_ids is None else metric_ids,
        "lifecycle_status": "active",
        "provenance": PROVENANCE,
    }


@pytest.fixture
def valid_version():
    version = {
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
        "incorporated_event_ids": [],
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
                "assumptions": [],
                "known_unknowns": [],
                "stop_conditions": [],
            },
            "router_decision": {
                "primary_method": "system_architecture",
                "secondary_methods": [],
                "routing_reasons": ["System dependencies drive outcomes"],
                "required_research_modules": ["architecture"],
                "excluded_modules": [],
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
                    "requirement_id": f"requirement:{suffix}",
                    "target_type": "research_claim",
                    "target_id": f"claim:{target}",
                    "question_to_resolve": "Is the mechanism observed?",
                    "requirement_type": "validation",
                    "required_source_classes": ["primary"],
                    "required_independence": "independent",
                    "required_freshness": "within_12_months",
                    "required_scope": "global",
                    "minimum_coverage": 1,
                    "conflict_search_required": True,
                    "primary_source_required": True,
                    "collection_status": "not_started",
                    "satisfaction_status": "unsatisfied",
                    "provenance": PROVENANCE,
                }
                for suffix, target in (("primary", "primary"), ("counter", "counter"))
            ],
            "references": [],
            "evidence_assessments": [],
            "causal_nodes": [
                {
                    "causal_node_id": f"causal_node:{suffix}",
                    "node_kind": kind,
                    "node_text": suffix.title(),
                    "lifecycle_status": "active",
                    "provenance": PROVENANCE,
                }
                for suffix, kind in (("mechanism", "mechanism"), ("outcome", "outcome"))
            ],
            "causal_edges": [
                _causal_edge(
                    "causal_edge:primary",
                    "causal_node:mechanism",
                    "causal_node:outcome",
                )
            ],
            "validation_metrics": [_metric()],
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
                    "recovery_condition": None,
                    "severity": "critical",
                    "status": "active",
                    "triggered_at": None,
                    "provenance": PROVENANCE,
                }
            ],
            "company_capture_assessments": [],
        },
    }
    validate_schema_payload("research_version_v2", version)
    return version


def _assert_code(version, code):
    with pytest.raises(ResearchProjectV2Error) as exc_info:
        validate_version_semantics(version)
    assert exc_info.value.code == code


def test_valid_research_design_has_valid_semantics(valid_version):
    original = deepcopy(valid_version)
    validate_version_semantics(valid_version)
    assert valid_version == original


def test_question_dependency_cycle_is_rejected(valid_version):
    valid_version["snapshot"]["question_tree_nodes"][0]["dependency_question_ids"] = [
        "question:counterfactual"
    ]
    _assert_code(valid_version, "RESEARCH_PROJECT_QUESTION_DEPENDENCY_CYCLE")


def test_missing_tree_parent_is_rejected(valid_version):
    valid_version["snapshot"]["question_tree_nodes"][1]["parent_tree_node_id"] = (
        "tree_node:missing"
    )
    _assert_code(valid_version, "RESEARCH_PROJECT_TREE_PARENT_NOT_FOUND")


def test_claim_relation_missing_target_is_rejected(valid_version):
    valid_version["snapshot"]["claim_relations"][0]["to_claim_id"] = "claim:missing"
    _assert_code(valid_version, "RESEARCH_PROJECT_CLAIM_RELATION_TARGET_NOT_FOUND")


def test_evidence_requirement_missing_target_is_rejected(valid_version):
    valid_version["snapshot"]["evidence_requirements"][0]["target_id"] = "claim:missing"
    _assert_code(valid_version, "RESEARCH_PROJECT_EVIDENCE_TARGET_NOT_FOUND")


def test_claim_context_reference_rejects_evidence_role(valid_version):
    valid_version["snapshot"]["references"].append(
        {
            "reference_id": "reference:support",
            "reference_namespace": "external_document",
            "reference_type": "report",
            "reference_object_id": "document:fixture",
            "reference_role": "supports",
            "reference_version": None,
            "reference_content_hash": None,
            "hash_scope": None,
            "referenced_at": "2026-07-17T10:00:00+08:00",
            "locator": None,
            "scope_note": None,
            "resolution_status": "resolved",
            "provenance": PROVENANCE,
        }
    )
    valid_version["snapshot"]["claims"][0]["context_reference_ids"] = [
        "reference:support"
    ]
    validate_schema_payload("research_version_v2", valid_version)
    _assert_code(valid_version, "RESEARCH_PROJECT_CONTEXT_REFERENCE_ROLE_INVALID")


def test_causal_edge_missing_node_is_rejected(valid_version):
    valid_version["snapshot"]["causal_edges"][0]["to_causal_node_id"] = (
        "causal_node:missing"
    )
    _assert_code(valid_version, "RESEARCH_PROJECT_CAUSAL_NODE_NOT_FOUND")


def test_unmarked_two_node_causal_cycle_is_rejected(valid_version):
    valid_version["snapshot"]["causal_edges"].append(
        _causal_edge("causal_edge:return", "causal_node:outcome", "causal_node:mechanism")
    )
    _assert_code(valid_version, "RESEARCH_PROJECT_UNMARKED_CAUSAL_CYCLE")


@pytest.mark.parametrize("supersedes", ["claim:primary", "claim:missing"])
def test_invalid_supersedes_claim_is_rejected(valid_version, supersedes):
    valid_version["snapshot"]["claims"][0]["supersedes_claim_id"] = supersedes
    _assert_code(valid_version, "RESEARCH_PROJECT_SUPERSEDES_CLAIM_INVALID")


def test_duplicate_claim_id_is_rejected_with_details(valid_version):
    valid_version["snapshot"]["claims"][1]["claim_id"] = "claim:primary"
    with pytest.raises(ResearchProjectV2Error) as exc_info:
        validate_version_semantics(valid_version)
    assert exc_info.value.code == "RESEARCH_PROJECT_DUPLICATE_OBJECT_ID"
    assert exc_info.value.details == {"collection": "claims", "id": "claim:primary"}


def test_same_marked_feedback_loop_is_accepted(valid_version):
    valid_version["snapshot"]["causal_edges"][0]["feedback_loop_id"] = "loop:one"
    valid_version["snapshot"]["causal_edges"].append(
        _causal_edge(
            "causal_edge:return",
            "causal_node:outcome",
            "causal_node:mechanism",
            "loop:one",
        )
    )
    validate_version_semantics(valid_version)


def test_mixed_feedback_loop_ids_are_rejected(valid_version):
    valid_version["snapshot"]["causal_edges"][0]["feedback_loop_id"] = "loop:one"
    valid_version["snapshot"]["causal_edges"].append(
        _causal_edge(
            "causal_edge:return",
            "causal_node:outcome",
            "causal_node:mechanism",
            "loop:two",
        )
    )
    _assert_code(valid_version, "RESEARCH_PROJECT_UNMARKED_CAUSAL_CYCLE")


@pytest.mark.parametrize("feedback_loop_id,valid", [(None, False), ("loop:self", True)])
def test_causal_self_loop_requires_marker(valid_version, feedback_loop_id, valid):
    valid_version["snapshot"]["causal_edges"] = [
        _causal_edge(
            "causal_edge:self",
            "causal_node:mechanism",
            "causal_node:mechanism",
            feedback_loop_id,
        )
    ]
    if valid:
        validate_version_semantics(valid_version)
    else:
        _assert_code(valid_version, "RESEARCH_PROJECT_UNMARKED_CAUSAL_CYCLE")


def test_causal_cycle_error_details_choose_first_component_deterministically(valid_version):
    valid_version["snapshot"]["causal_nodes"].extend(
        [
            {
                "causal_node_id": f"causal_node:{suffix}",
                "node_kind": "mechanism",
                "node_text": suffix,
                "lifecycle_status": "active",
                "provenance": PROVENANCE,
            }
            for suffix in ("zeta", "alpha")
        ]
    )
    valid_version["snapshot"]["causal_edges"] = [
        _causal_edge(
            f"causal_edge:{suffix}",
            f"causal_node:{suffix}",
            f"causal_node:{suffix}",
        )
        for suffix in ("zeta", "alpha")
    ]
    with pytest.raises(ResearchProjectV2Error) as exc_info:
        validate_version_semantics(valid_version)
    assert exc_info.value.code == "RESEARCH_PROJECT_UNMARKED_CAUSAL_CYCLE"
    assert exc_info.value.details["causal_node_ids"] == ["causal_node:alpha"]


def test_deep_causal_cycle_uses_domain_validation_without_recursion_error(valid_version):
    node_ids = [f"causal_node:deep:{index:04d}" for index in range(1100)]
    valid_version["snapshot"]["causal_nodes"] = [
        {
            "causal_node_id": node_id,
            "node_kind": "mechanism",
            "node_text": node_id,
            "lifecycle_status": "active",
            "provenance": PROVENANCE,
        }
        for node_id in node_ids
    ]
    valid_version["snapshot"]["causal_edges"] = [
        _causal_edge(
            f"causal_edge:deep:{index:04d}",
            node_id,
            node_ids[(index + 1) % len(node_ids)],
            "loop:deep",
        )
        for index, node_id in enumerate(node_ids)
    ]
    validate_version_semantics(valid_version)


def test_question_links_must_resolve(valid_version):
    valid_version["snapshot"]["questions"][0]["linked_requirement_ids"] = [
        "requirement:missing"
    ]
    _assert_code(valid_version, "RESEARCH_PROJECT_QUESTION_REQUIREMENT_NOT_FOUND")


def test_metric_target_must_resolve(valid_version):
    valid_version["snapshot"]["validation_metrics"][0]["target_id"] = "claim:missing"
    _assert_code(valid_version, "RESEARCH_PROJECT_VALIDATION_TARGET_NOT_FOUND")


def test_research_project_target_must_match_version_project(valid_version):
    requirement = valid_version["snapshot"]["evidence_requirements"][0]
    requirement["target_type"] = "research_project"
    requirement["target_id"] = "research_project:other"
    _assert_code(valid_version, "RESEARCH_PROJECT_EVIDENCE_TARGET_NOT_FOUND")


def test_design_snapshot_semantics_defend_against_invalid_stage_payload(valid_version):
    valid_version["snapshot"]["evidence_stage"] = "collection_in_progress"
    _assert_code(valid_version, "RESEARCH_PROJECT_DESIGN_SNAPSHOT_INVALID")
