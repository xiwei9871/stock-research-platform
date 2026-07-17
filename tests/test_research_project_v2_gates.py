from copy import deepcopy
import json
import warnings

import pytest

from stock_research.research_project_v2.errors import ResearchProjectV2Error
from stock_research.research_project_v2.gates import GateCheck, GateResult, evaluate_gate

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

DESIGN_CODES = [
    "DESIGN_PRIMARY_QUESTION_PRESENT",
    "DESIGN_SCOPE_INCLUDED_PRESENT",
    "DESIGN_SCOPE_EXCLUDED_PRESENT",
    "DESIGN_ROUTER_COMPLETE",
    "DESIGN_QUESTION_TREE_VALID",
    "DESIGN_REQUIRED_QUESTIONS_COVERED",
    "DESIGN_CRITICAL_CLAIMS_HAVE_COUNTER",
    "DESIGN_VALIDATION_PLAN_PRESENT",
    "DESIGN_INVALIDATION_PLAN_PRESENT",
    "DESIGN_REFERENCES_AUDITABLE",
    "DESIGN_PROVENANCE_COMPLETE",
    "DESIGN_NO_PREMATURE_CONCLUSIONS",
]


def _requirement(suffix):
    return {
        "requirement_id": f"requirement:{suffix}",
        "target_type": "research_question",
        "target_id": f"question:{suffix}",
        "question_to_resolve": "Can this question be answered?",
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
                    "question_id": f"question:{suffix}",
                    "question_type": question_type,
                    "question_text": text,
                    "priority": priority,
                    "required_for_gate": True,
                    "answer_status": "unanswered",
                    "linked_claim_ids": [f"claim:{suffix}"],
                    "linked_requirement_ids": [f"requirement:{suffix}"],
                    "provenance": PROVENANCE,
                    "lifecycle_status": "active",
                }
                for suffix, question_type, text, priority in (
                    ("primary", "primary", "Can the fixture thesis be validated?", 1),
                    ("counter", "counterfactual", "What would disprove it?", 2),
                )
            ],
            "question_tree_nodes": [
                {"tree_node_id": "tree:primary", "tree_id": "tree:fixture", "question_id": "question:primary", "parent_tree_node_id": None, "order": 1, "branch_role": "root", "dependency_question_ids": []},
                {"tree_node_id": "tree:counter", "tree_id": "tree:fixture", "question_id": "question:counter", "parent_tree_node_id": "tree:primary", "order": 2, "branch_role": "counterfactual", "dependency_question_ids": ["question:primary"]},
            ],
            "claims": [
                {"claim_id": "claim:primary", "claim_kind": "primary", "epistemic_type": "hypothesis", "claim_text": "The mechanism creates value.", "claim_status": "hypothesis", "lifecycle_status": "active", "confidence": 0.4, "importance": 1.0, "linked_question_ids": ["question:primary"], "context_reference_ids": [], "created_in_version": "research_version:fixture:0.1.0", "supersedes_claim_id": None, "validation_metric_ids": ["metric:primary"], "invalidation_condition_ids": ["condition:primary"], "provenance": PROVENANCE},
                {"claim_id": "claim:counter", "claim_kind": "counter", "epistemic_type": "hypothesis", "claim_text": "A constraint prevents value creation.", "claim_status": "under_test", "lifecycle_status": "active", "confidence": 0.3, "importance": 0.8, "linked_question_ids": ["question:counter"], "context_reference_ids": [], "created_in_version": "research_version:fixture:0.1.0", "supersedes_claim_id": None, "validation_metric_ids": [], "invalidation_condition_ids": [], "provenance": PROVENANCE},
            ],
            "claim_relations": [{"relation_id": "relation:counter", "from_claim_id": "claim:counter", "to_claim_id": "claim:primary", "relation_type": "challenges", "relation_summary": "The constraint challenges the thesis.", "created_in_version": "research_version:fixture:0.1.0", "provenance": PROVENANCE}],
            "evidence_requirements": [_requirement("primary"), _requirement("counter")],
            "references": [],
            "evidence_assessments": [],
            "causal_nodes": [
                {"causal_node_id": "node:mechanism", "node_kind": "mechanism", "node_text": "Mechanism", "lifecycle_status": "active", "provenance": PROVENANCE},
                {"causal_node_id": "node:outcome", "node_kind": "outcome", "node_text": "Outcome", "lifecycle_status": "active", "provenance": PROVENANCE},
            ],
            "causal_edges": [{"causal_edge_id": "edge:primary", "from_causal_node_id": "node:mechanism", "to_causal_node_id": "node:outcome", "relation_type": "causes", "mechanism_text": "The mechanism changes the outcome.", "effect_polarity": "positive", "strength": 0.5, "confidence": 0.4, "time_lag": "12 months", "boundary_condition": None, "feedback_loop_id": None, "supporting_claim_ids": ["claim:primary"], "validation_metric_ids": ["metric:primary"], "lifecycle_status": "active", "provenance": PROVENANCE}],
            "validation_metrics": [{"metric_id": "metric:primary", "target_type": "research_claim", "target_id": "claim:primary", "metric_name": "Primary metric", "metric_definition": "Measures the outcome.", "data_source_plan": "Collect primary data.", "unit": "percent", "baseline_value": None, "baseline_as_of": None, "comparison_operator": ">=", "observation_window": "12 months", "aggregation_method": "median", "expected_range": "10-20", "confirmation_threshold": 10, "warning_threshold": 5, "data_freshness_requirement": "quarterly", "observation_frequency": "quarterly", "status": "planned", "provenance": PROVENANCE}],
            "invalidation_conditions": [{"condition_id": "condition:primary", "target_type": "research_claim", "target_id": "claim:primary", "condition_text": "Metric stays below threshold.", "observable_test": "Observe metric.", "comparison_operator": "<", "threshold_value": 5, "unit": "percent", "persistence_window": "2 quarters", "minimum_observations": 2, "recovery_condition": None, "severity": "critical", "status": "active", "triggered_at": None, "provenance": PROVENANCE}],
            "company_capture_assessments": [],
        },
    }
    validate_schema_payload("research_version_v2", version)
    validate_version_semantics(version)
    return version


def _check(result, code):
    return next(check for check in result.checks if check.code == code)


def test_valid_design_gate_passes_in_fixed_order_without_mutation(valid_version):
    original = deepcopy(valid_version)
    result = evaluate_gate(valid_version, "design")
    assert result.status == "pass"
    assert [check.code for check in result.checks] == DESIGN_CODES
    assert {check.status for check in result.checks} == {"pass"}
    assert valid_version == original


@pytest.mark.parametrize(
    ("mutate", "code"),
    [
        (lambda v: v["snapshot"]["scope"].update(excluded_scope=[]), "DESIGN_SCOPE_EXCLUDED_PRESENT"),
        (lambda v: v["snapshot"]["router_decision"].update(routing_reasons=[]), "DESIGN_ROUTER_COMPLETE"),
        (lambda v: v["snapshot"]["evidence_requirements"].pop(0), "DESIGN_REQUIRED_QUESTIONS_COVERED"),
        (lambda v: (v["snapshot"]["claims"].pop(1), v["snapshot"]["claim_relations"].clear()), "DESIGN_CRITICAL_CLAIMS_HAVE_COUNTER"),
        (lambda v: v["snapshot"]["claims"][0].update(claim_status="supported"), "DESIGN_NO_PREMATURE_CONCLUSIONS"),
        (lambda v: v["snapshot"]["evidence_assessments"].append({"assessment_id": "assessment:early"}), "DESIGN_NO_PREMATURE_CONCLUSIONS"),
        (lambda v: v["snapshot"]["company_capture_assessments"].append({"assessment_id": "capture:early"}), "DESIGN_NO_PREMATURE_CONCLUSIONS"),
    ],
)
def test_design_mutations_fail_the_expected_check(valid_version, mutate, code):
    mutate(valid_version)
    result = evaluate_gate(valid_version, "design")
    assert result.status == "fail"
    assert _check(result, code).status == "fail"


@pytest.mark.parametrize("collection,field,code", [("validation_metrics", "validation_metric_ids", "DESIGN_VALIDATION_PLAN_PRESENT"), ("invalidation_conditions", "invalidation_condition_ids", "DESIGN_INVALIDATION_PLAN_PRESENT")])
def test_missing_validation_or_invalidation_plan_fails(valid_version, collection, field, code):
    valid_version["snapshot"][collection].clear()
    valid_version["snapshot"]["claims"][0][field].clear()
    assert _check(evaluate_gate(valid_version, "design"), code).status == "fail"


@pytest.mark.parametrize(
    ("collection", "target_type", "target_id", "code"),
    [
        (
            "validation_metrics",
            "research_question",
            "question:primary",
            "DESIGN_VALIDATION_PLAN_PRESENT",
        ),
        (
            "validation_metrics",
            "research_claim",
            "claim:counter",
            "DESIGN_VALIDATION_PLAN_PRESENT",
        ),
        (
            "invalidation_conditions",
            "research_question",
            "question:primary",
            "DESIGN_INVALIDATION_PLAN_PRESENT",
        ),
        (
            "invalidation_conditions",
            "research_claim",
            "claim:counter",
            "DESIGN_INVALIDATION_PLAN_PRESENT",
        ),
    ],
)
def test_plan_objects_must_target_the_linked_critical_claim(
    valid_version, collection, target_type, target_id, code
):
    valid_version["snapshot"][collection][0].update(
        target_type=target_type,
        target_id=target_id,
    )
    check = _check(evaluate_gate(valid_version, "design"), code)
    assert check.status == "fail"
    assert check.object_ids == ("claim:primary",)


def test_counter_relation_direction_cannot_be_reversed(valid_version):
    relation = valid_version["snapshot"]["claim_relations"][0]
    relation["from_claim_id"], relation["to_claim_id"] = (
        relation["to_claim_id"],
        relation["from_claim_id"],
    )
    check = _check(
        evaluate_gate(valid_version, "design"),
        "DESIGN_CRITICAL_CLAIMS_HAVE_COUNTER",
    )
    assert check.status == "fail"
    assert check.object_ids == ("claim:primary",)


def test_primary_question_must_match_scope_and_be_required(valid_version):
    valid_version["snapshot"]["questions"][0]["required_for_gate"] = False
    result = evaluate_gate(valid_version, "design")
    assert result.status == "fail"
    assert _check(result, "DESIGN_PRIMARY_QUESTION_PRESENT").status == "fail"


def test_primary_question_matching_normalizes_surrounding_whitespace(valid_version):
    valid_version["snapshot"]["scope"]["primary_question"] = (
        "  Can the fixture thesis be validated?  "
    )
    valid_version["snapshot"]["questions"][0]["question_text"] = (
        " Can the fixture thesis be validated? "
    )
    assert (
        _check(
            evaluate_gate(valid_version, "design"),
            "DESIGN_PRIMARY_QUESTION_PRESENT",
        ).status
        == "pass"
    )


def test_bad_tree_cycle_fails_with_stable_object_ids(valid_version):
    valid_version["snapshot"]["question_tree_nodes"][0]["parent_tree_node_id"] = "tree:counter"
    check = _check(evaluate_gate(valid_version, "design"), "DESIGN_QUESTION_TREE_VALID")
    assert check.status == "fail"
    assert check.object_ids == ("tree:counter", "tree:primary")


def test_tree_cycle_reports_only_true_cycle_members_not_downstream_nodes(valid_version):
    snapshot = valid_version["snapshot"]
    snapshot["questions"].append(
        {
            "question_id": "question:downstream",
            "question_type": "secondary",
            "question_text": "What follows from the counterfactual?",
            "priority": 3,
            "required_for_gate": False,
            "answer_status": "unanswered",
            "linked_claim_ids": [],
            "linked_requirement_ids": [],
            "provenance": PROVENANCE,
            "lifecycle_status": "active",
        }
    )
    snapshot["question_tree_nodes"][0]["dependency_question_ids"] = [
        "question:counter"
    ]
    snapshot["question_tree_nodes"].append(
        {
            "tree_node_id": "tree:downstream",
            "tree_id": "tree:fixture",
            "question_id": "question:downstream",
            "parent_tree_node_id": "tree:counter",
            "order": 3,
            "branch_role": "supporting",
            "dependency_question_ids": ["question:counter"],
        }
    )
    check = _check(evaluate_gate(valid_version, "design"), "DESIGN_QUESTION_TREE_VALID")
    assert check.status == "fail"
    assert check.object_ids == ("tree:counter", "tree:primary")


def test_reference_audit_failure_reports_reference_ids(valid_version):
    valid_version["snapshot"]["references"] = [{"reference_id": "reference:missing", "reference_namespace": "theme_research_v1", "reference_type": "v1_theme", "reference_object_id": "missing-theme", "reference_role": "background", "reference_version": None, "reference_content_hash": None, "hash_scope": None, "referenced_at": "2026-07-17T10:00:00+08:00", "locator": None, "scope_note": None, "resolution_status": "unresolved", "provenance": PROVENANCE}]
    check = _check(evaluate_gate(valid_version, "design"), "DESIGN_REFERENCES_AUDITABLE")
    assert check.status == "fail"
    assert check.object_ids == ("reference:missing",)


def test_missing_provenance_fails_with_object_id(valid_version):
    del valid_version["snapshot"]["claims"][0]["provenance"]
    check = _check(evaluate_gate(valid_version, "design"), "DESIGN_PROVENANCE_COMPLETE")
    assert check.status == "fail"
    assert check.object_ids == ("claim:primary",)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("agent_run_id", 42),
        ("created_at", None),
        ("created_at", ""),
        ("created_at", "not-a-timestamp"),
    ],
)
def test_provenance_validates_field_values_without_schema(valid_version, field, value):
    valid_version["snapshot"]["claims"][0]["provenance"] = {
        **PROVENANCE,
        field: value,
    }
    check = _check(
        evaluate_gate(valid_version, "design"),
        "DESIGN_PROVENANCE_COMPLETE",
    )
    assert check.status == "fail"
    assert check.object_ids == ("claim:primary",)


def test_manual_override_requires_reason(valid_version):
    valid_version["snapshot"]["router_decision"].update(manual_override=True, override_reason="")
    assert _check(evaluate_gate(valid_version, "design"), "DESIGN_ROUTER_COMPLETE").status == "fail"


@pytest.mark.parametrize("gate", ["evidence", "publication"])
def test_later_gate_is_not_applicable_to_design_snapshot(valid_version, gate):
    result = evaluate_gate(valid_version, gate)
    assert result.status == "not_applicable"
    assert [(c.code, c.status) for c in result.checks] == [("GATE_CREATION_STAGE_NOT_APPLICABLE", "not_applicable")]


def test_applicable_r1_later_gate_never_passes_unimplemented(valid_version):
    valid_version["creation_stage"] = "evidence_snapshot"
    result = evaluate_gate(valid_version, "evidence")
    assert result.status == "fail"
    assert [(c.code, c.status) for c in result.checks] == [("GATE_R1_NOT_IMPLEMENTED", "fail")]


def test_unknown_gate_raises_stable_domain_error(valid_version):
    with pytest.raises(ResearchProjectV2Error) as exc_info:
        evaluate_gate(valid_version, "unknown")
    assert exc_info.value.code == "RESEARCH_PROJECT_GATE_UNKNOWN"


def test_gate_result_as_dict_is_stable_and_json_serializable():
    result = GateResult("design", "pass", (GateCheck("CHECK", "pass", "ok", ("object:1",)),))
    assert result.as_dict() == {"gate": "design", "status": "pass", "checks": [{"code": "CHECK", "status": "pass", "message": "ok", "object_ids": ("object:1",)}]}
    json.dumps(result.as_dict())
