from copy import deepcopy
import json
import warnings

import pytest

from stock_research.research_project_v2.diff import OBJECT_FAMILIES, diff_versions
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


def _claim(claim_id: str, text: str) -> dict:
    return {
        "claim_id": claim_id,
        "claim_kind": "primary" if claim_id == "claim:old" else "supporting",
        "epistemic_type": "hypothesis",
        "claim_text": text,
        "claim_status": "hypothesis",
        "lifecycle_status": "active",
        "confidence": 0.4,
        "importance": 0.8,
        "linked_question_ids": ["question:primary"],
        "context_reference_ids": [],
        "created_in_version": "research_version:fixture:0.1.0",
        "supersedes_claim_id": None,
        "validation_metric_ids": [],
        "invalidation_condition_ids": [],
        "provenance": deepcopy(PROVENANCE),
    }


def _version() -> dict:
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
        "incorporated_event_ids": [],
        "content_hash": "a" * 64,
        "snapshot": {
            "project_lifecycle_state": "research_ready",
            "evidence_stage": "requirements_defined",
            "conclusion_status": "unavailable",
            "investment_status": "not_assessed",
            "scope": {
                "primary_question": "Does the primary mechanism work?",
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
                    "linked_claim_ids": ["claim:old", "claim:stable"],
                    "linked_requirement_ids": [],
                    "provenance": deepcopy(PROVENANCE),
                    "lifecycle_status": "active",
                }
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
                }
            ],
            "claims": [
                _claim("claim:old", "The original mechanism creates value."),
                _claim("claim:stable", "The stable mechanism creates value."),
            ],
            "claim_relations": [],
            "evidence_requirements": [],
            "references": [],
            "evidence_assessments": [],
            "causal_nodes": [],
            "causal_edges": [],
            "validation_metrics": [],
            "invalidation_conditions": [],
            "company_capture_assessments": [],
        },
    }


@pytest.fixture
def version_pair():
    before = _version()
    after = deepcopy(before)
    after.update(
        {
            "version_id": "research_version:fixture:0.2.0",
            "semantic_version": "0.2.0",
            "parent_version_id": before["version_id"],
            "created_at": "2026-07-17T11:00:00+08:00",
            "change_summary": "Create a direct child research design.",
            "change_reason": "Exercise stable-ID version diffing.",
            "content_hash": "b" * 64,
        }
    )
    return before, after


def _claim_by_id(version: dict, claim_id: str) -> dict:
    return next(
        claim for claim in version["snapshot"]["claims"] if claim["claim_id"] == claim_id
    )


def test_version_fixtures_are_current_schema_and_semantically_valid(version_pair):
    before, after = version_pair

    for version in (before, after):
        validate_schema_payload("research_version_v2", version)
        validate_version_semantics(version)


def test_diff_reports_metadata_added_claim_and_unchanged_question(version_pair):
    before, after = version_pair
    after["snapshot"]["claims"].append(_claim("claim:new", "A new mechanism."))

    result = diff_versions(before, after)

    assert result["project_id"] == "research_project:fixture"
    assert result["from_version"] == "0.1.0"
    assert result["to_version"] == "0.2.0"
    assert result["from_content_hash"] == "a" * 64
    assert result["to_content_hash"] == "b" * 64
    assert result["changes"]["claims"]["added"] == ["claim:new"]
    assert result["changes"]["questions"]["unchanged"] == ["question:primary"]
    json.dumps(result)


@pytest.mark.parametrize(
    ("field", "value", "category"),
    [
        ("lifecycle_status", "removed_from_scope", "removed_from_current_scope"),
        ("lifecycle_status", "superseded", "superseded"),
        ("claim_status", "under_test", "status_changed"),
        ("claim_text", "The revised mechanism creates value.", "modified"),
    ],
)
def test_diff_classifies_same_id_claim_changes(version_pair, field, value, category):
    before, after = version_pair
    _claim_by_id(after, "claim:stable")[field] = value

    result = diff_versions(before, after)

    assert result["changes"]["claims"][category] == ["claim:stable"]
    assert sum(
        "claim:stable" in ids for ids in result["changes"]["claims"].values()
    ) == 1


def test_status_and_text_change_is_modified(version_pair):
    before, after = version_pair
    claim = _claim_by_id(after, "claim:stable")
    claim["claim_status"] = "under_test"
    claim["claim_text"] = "The revised mechanism creates value."

    result = diff_versions(before, after)

    assert result["changes"]["claims"]["modified"] == ["claim:stable"]
    assert result["changes"]["claims"]["status_changed"] == []


def test_removed_claim_explicitly_superseded_by_new_claim_is_superseded_and_added(
    version_pair,
):
    before, after = version_pair
    after["snapshot"]["claims"] = [
        claim for claim in after["snapshot"]["claims"] if claim["claim_id"] != "claim:old"
    ]
    new_claim = _claim("claim:new", "The replacement mechanism creates value.")
    new_claim["supersedes_claim_id"] = "claim:old"
    after["snapshot"]["claims"].append(new_claim)

    result = diff_versions(before, after)

    assert result["changes"]["claims"]["superseded"] == ["claim:old"]
    assert result["changes"]["claims"]["added"] == ["claim:new"]


def test_absent_non_superseded_claim_is_removed_from_current_scope(version_pair):
    before, after = version_pair
    after["snapshot"]["claims"] = [
        claim for claim in after["snapshot"]["claims"] if claim["claim_id"] != "claim:old"
    ]

    result = diff_versions(before, after)

    assert result["changes"]["claims"]["removed_from_current_scope"] == ["claim:old"]


def test_only_provenance_review_status_change_is_status_changed(version_pair):
    before, after = version_pair
    _claim_by_id(after, "claim:stable")["provenance"]["review_status"] = "reviewed"

    result = diff_versions(before, after)

    assert result["changes"]["claims"]["status_changed"] == ["claim:stable"]


def test_non_status_provenance_change_is_modified(version_pair):
    before, after = version_pair
    _claim_by_id(after, "claim:stable")["provenance"]["created_at"] = (
        "2026-07-17T12:00:00+08:00"
    )

    result = diff_versions(before, after)

    assert result["changes"]["claims"]["modified"] == ["claim:stable"]


def test_family_array_reordering_does_not_modify_objects(version_pair):
    before, after = version_pair
    after["snapshot"]["claims"].reverse()

    result = diff_versions(before, after)

    assert result["changes"]["claims"]["modified"] == []
    assert result["changes"]["claims"]["unchanged"] == ["claim:old", "claim:stable"]


def test_all_families_and_categories_are_present_in_fixed_order_and_sorted(version_pair):
    before, after = version_pair
    after["snapshot"]["claims"].extend(
        [_claim("claim:z", "Z"), _claim("claim:a", "A")]
    )

    result = diff_versions(before, after)

    assert list(result["changes"]) == list(OBJECT_FAMILIES)
    assert all(
        list(categories)
        == [
            "added",
            "removed_from_current_scope",
            "modified",
            "status_changed",
            "superseded",
            "unchanged",
        ]
        for categories in result["changes"].values()
    )
    assert all(
        ids == sorted(ids)
        for categories in result["changes"].values()
        for ids in categories.values()
    )
    assert result["changes"]["claims"]["added"] == ["claim:a", "claim:z"]


def test_project_mismatch_uses_stable_domain_error(version_pair):
    before, after = version_pair
    after["project_id"] = "research_project:other"

    with pytest.raises(ResearchProjectV2Error) as exc_info:
        diff_versions(before, after)

    assert exc_info.value.code == "RESEARCH_PROJECT_DIFF_PROJECT_MISMATCH"
    assert exc_info.value.details == {
        "before": "research_project:fixture",
        "after": "research_project:other",
    }


@pytest.mark.parametrize("same_version", [False, True])
def test_invalid_direct_parent_uses_stable_domain_error(version_pair, same_version):
    before, after = version_pair
    if same_version:
        after["version_id"] = before["version_id"]
    else:
        after["parent_version_id"] = "research_version:fixture:0.0.0"

    with pytest.raises(ResearchProjectV2Error) as exc_info:
        diff_versions(before, after)

    assert exc_info.value.code == "RESEARCH_PROJECT_DIFF_ANCESTRY_INVALID"
    assert exc_info.value.details == {
        "expected": before["version_id"],
        "actual": after["parent_version_id"],
    }


def test_duplicate_object_id_uses_stable_domain_error(version_pair):
    before, after = version_pair
    after["snapshot"]["claims"].append(deepcopy(after["snapshot"]["claims"][0]))

    with pytest.raises(ResearchProjectV2Error) as exc_info:
        diff_versions(before, after)

    assert exc_info.value.code == "RESEARCH_PROJECT_DIFF_DUPLICATE_OBJECT_ID"


def test_diff_does_not_mutate_inputs(version_pair):
    before, after = version_pair
    original_before = deepcopy(before)
    original_after = deepcopy(after)

    diff_versions(before, after)

    assert before == original_before
    assert after == original_after
