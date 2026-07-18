from copy import deepcopy
import json
from pathlib import Path
import warnings

from jsonschema import Draft202012Validator
import pytest

from stock_research.research_project_v2.errors import ResearchProjectV2Error


with warnings.catch_warnings():
    warnings.filterwarnings(
        "ignore",
        message=r"jsonschema\.RefResolver is deprecated as of v4\.18\.0.*",
        category=DeprecationWarning,
    )
    from stock_research.research_project_v2_1.schema import (
        SCHEMA_FILES,
        validate_v2_1_schema_payload,
    )


SCHEMA_DIR = (
    Path(__file__).resolve().parents[1]
    / "artifacts/research_projects/v2_1/schema"
)
ALL_SCHEMA_FILES = {
    "definitions_v2_1.schema.json",
    *SCHEMA_FILES.values(),
}


@pytest.fixture
def sample_identity():
    return {
        "schema_version": "2.1.0",
        "artifact_kind": "research_project_identity",
        "project_id": "research_project:fixture-industry",
        "project_slug": "fixture-industry",
        "title": "Fixture industry research project",
        "purpose": "Exercise the layered industry-research schema.",
        "research_layer": "industry_research",
        "created_at": "2026-07-18T10:00:00+08:00",
        "created_by": "fixture-author",
        "current_lifecycle_state": "research_ready",
        "current_version": "research_version:fixture-industry:0.1.0",
        "latest_reviewed_version": None,
        "latest_published_version": None,
    }


@pytest.fixture
def sample_industry_version():
    return {
        "schema_version": "2.1.0",
        "artifact_kind": "industry_research_version",
        "version_id": "research_version:fixture-industry:0.1.0",
        "project_id": "research_project:fixture-industry",
        "semantic_version": "0.1.0",
        "parent_version_id": None,
        "creation_stage": "research_design",
        "created_at": "2026-07-18T10:00:00+08:00",
        "created_by": "fixture-author",
        "change_summary": "Create the initial industry research design.",
        "change_reason": "Initialize the layered fixture.",
        "incorporated_event_ids": [],
        "content_hash": "a" * 64,
        "snapshot": {
            "research_layer": "industry_research",
            "project_lifecycle_state": "research_ready",
            "evidence_stage": "requirements_defined",
            "conclusion_status": "unavailable",
            "investment_status": "not_assessed",
            "scope": {
                "primary_question": "Can the industry mechanism be validated?",
                "research_object": "Fixture industry",
                "included_scope": ["Industry structure"],
                "excluded_scope": ["Company selection"],
                "geography": ["Global"],
                "time_horizon": "2026-2030",
                "industry_boundary": "Fixture industry",
                "company_universe_boundary": "Out of scope",
                "decision_context": "Industry research validation",
                "assumptions": [],
                "known_unknowns": [],
                "stop_conditions": [],
            },
            "router_decision": {
                "primary_method": "system_architecture",
                "secondary_methods": [],
                "routing_reasons": ["System dependencies drive outcomes"],
                "required_research_modules": ["architecture"],
                "excluded_modules": ["company_capture"],
                "confidence": 0.8,
                "manual_override": False,
                "override_reason": None,
                "decided_by": "fixture-author",
                "decided_at": "2026-07-18T10:00:00+08:00",
            },
            "questions": [],
            "question_tree_nodes": [],
            "claims": [],
            "claim_relations": [],
            "evidence_requirements": [],
            "references": [],
            "evidence_assessments": [],
            "causal_nodes": [],
            "causal_edges": [],
            "validation_metrics": [],
            "invalidation_conditions": [],
            "upstream_research_refs": [],
            "search_plans": [],
            "source_candidates": [],
            "source_relationships": [],
            "evidence_artifacts": [],
            "normalized_documents": [],
            "industry_evidence_assessments": [],
            "conflict_summaries": [],
        },
    }


def test_valid_identity_passes(sample_identity):
    validate_v2_1_schema_payload(
        "research_project_identity_v2_1", sample_identity
    )


def test_identity_rejects_company_capture_layer(sample_identity):
    sample_identity["research_layer"] = "company_capture"

    with pytest.raises(ResearchProjectV2Error) as exc_info:
        validate_v2_1_schema_payload(
            "research_project_identity_v2_1", sample_identity
        )

    assert exc_info.value.code == "RESEARCH_PROJECT_V2_1_SCHEMA_INVALID"
    assert exc_info.value.details == {
        "schema": "research_project_identity_v2_1",
        "path": ["research_layer"],
    }


def test_valid_industry_version_passes(sample_industry_version):
    validate_v2_1_schema_payload(
        "industry_research_version_v2_1", sample_industry_version
    )


@pytest.mark.parametrize(
    "forbidden_key",
    [
        "candidate_companies",
        "company_capability_assessments",
        "company_ratings",
        "stock_ratings",
        "valuation_assessments",
        "watchlist_candidates",
        "strategy_hypotheses",
    ],
)
def test_industry_version_rejects_downstream_layer_collections(
    sample_industry_version, forbidden_key
):
    sample_industry_version["snapshot"][forbidden_key] = []

    with pytest.raises(ResearchProjectV2Error) as exc_info:
        validate_v2_1_schema_payload(
            "industry_research_version_v2_1", sample_industry_version
        )

    assert exc_info.value.code == "RESEARCH_PROJECT_V2_1_SCHEMA_INVALID"
    assert exc_info.value.details == {
        "schema": "industry_research_version_v2_1",
        "path": ["snapshot"],
    }


def test_v2_registry_rejects_r1_schema_version(sample_identity):
    sample_identity["schema_version"] = "2.0.0"

    with pytest.raises(ResearchProjectV2Error) as exc_info:
        validate_v2_1_schema_payload(
            "research_project_identity_v2_1", sample_identity
        )

    assert exc_info.value.code == "RESEARCH_PROJECT_V2_1_SCHEMA_INVALID"
    assert exc_info.value.details == {
        "schema": "research_project_identity_v2_1",
        "path": ["schema_version"],
    }


def test_unknown_schema_name_has_deterministic_error_details():
    with pytest.raises(ResearchProjectV2Error) as exc_info:
        validate_v2_1_schema_payload("not_a_schema", {})

    assert exc_info.value.code == "RESEARCH_PROJECT_V2_1_SCHEMA_NOT_FOUND"
    assert exc_info.value.details == {"schema": "not_a_schema"}


def test_validation_failure_reports_deterministic_schema_and_path(sample_identity):
    sample_identity["created_at"] = "not-a-date"

    with pytest.raises(ResearchProjectV2Error) as exc_info:
        validate_v2_1_schema_payload(
            "research_project_identity_v2_1", sample_identity
        )

    assert exc_info.value.code == "RESEARCH_PROJECT_V2_1_SCHEMA_INVALID"
    assert exc_info.value.details == {
        "schema": "research_project_identity_v2_1",
        "path": ["created_at"],
    }


def test_all_eight_v2_1_schema_files_are_valid_draft_2020_12_schemas():
    assert {path.name for path in SCHEMA_DIR.glob("*.schema.json")} == ALL_SCHEMA_FILES
    assert len(ALL_SCHEMA_FILES) == 8

    for filename in sorted(ALL_SCHEMA_FILES):
        Draft202012Validator.check_schema(
            json.loads((SCHEMA_DIR / filename).read_text())
        )


@pytest.mark.parametrize(
    ("field", "invalid_value", "expected_path"),
    [
        ("created_at", "2026-07-18", ["created_at"]),
        ("content_hash", "A" * 64, ["content_hash"]),
        ("content_hash", "a" * 63, ["content_hash"]),
    ],
)
def test_version_enforces_rfc3339_and_lowercase_sha256(
    sample_industry_version, field, invalid_value, expected_path
):
    sample_industry_version[field] = invalid_value

    with pytest.raises(ResearchProjectV2Error) as exc_info:
        validate_v2_1_schema_payload(
            "industry_research_version_v2_1", sample_industry_version
        )

    assert exc_info.value.code == "RESEARCH_PROJECT_V2_1_SCHEMA_INVALID"
    assert exc_info.value.details["path"] == expected_path


def test_common_research_layer_supports_all_three_layers():
    definitions = json.loads(
        (SCHEMA_DIR / "definitions_v2_1.schema.json").read_text()
    )

    assert definitions["$defs"]["research_layer"]["enum"] == [
        "industry_research",
        "company_capture",
        "stock_evaluation",
    ]


@pytest.mark.parametrize(
    ("field", "invalid_value"),
    [
        ("upstream_content_hash", "A" * 64),
        ("referenced_at", "2026-07-18"),
    ],
)
def test_upstream_reference_enforces_hash_and_rfc3339(
    sample_industry_version, field, invalid_value
):
    reference = {
        "upstream_research_ref_id": "upstream_ref:r1-fixture",
        "upstream_research_layer": None,
        "upstream_project_id": "research_project:r1-fixture",
        "upstream_version_id": "research_version:r1-fixture:0.1.0",
        "upstream_object_type": "research_version",
        "upstream_object_id": None,
        "upstream_gate_result_id": None,
        "upstream_content_hash": "e" * 64,
        "referenced_at": "2026-07-18T10:00:00Z",
        "scope_note": "R1 unlayered design baseline",
    }
    reference[field] = invalid_value
    sample_industry_version["snapshot"]["upstream_research_refs"] = [reference]

    with pytest.raises(ResearchProjectV2Error) as exc_info:
        validate_v2_1_schema_payload(
            "industry_research_version_v2_1", sample_industry_version
        )

    assert exc_info.value.code == "RESEARCH_PROJECT_V2_1_SCHEMA_INVALID"
    assert exc_info.value.details == {
        "schema": "industry_research_version_v2_1",
        "path": ["snapshot", "upstream_research_refs", 0, field],
    }


def test_public_registry_excludes_common_definitions():
    assert SCHEMA_FILES == {
        "research_project_identity_v2_1": "research_project_identity_v2_1.schema.json",
        "industry_research_version_v2_1": "industry_research_version_v2_1.schema.json",
        "search_plan_v2_1": "search_plan_v2_1.schema.json",
        "evidence_artifact_v2_1": "evidence_artifact_v2_1.schema.json",
        "normalized_document_v2_1": "normalized_document_v2_1.schema.json",
        "industry_evidence_assessment_v2_1": "industry_evidence_assessment_v2_1.schema.json",
        "research_project_index_v2_1": "research_project_index_v2_1.schema.json",
    }


def _standalone_payloads():
    return {
        "search_plan_v2_1": {
            "schema_version": "2.1.0",
            "artifact_kind": "search_plan",
            "search_plan": {
                "search_plan_id": "search_plan:fixture",
                "project_id": "research_project:fixture-industry",
                "version_id": "research_version:fixture-industry:0.1.0",
                "research_layer": "industry_research",
                "objective": "Find industry mechanism evidence.",
                "queries": [
                    {
                        "query_id": "query:fixture:mechanism",
                        "query_text": "fixture mechanism engineering",
                        "evidence_channel": "industry",
                        "purpose": "Validate the mechanism.",
                        "priority": 1,
                        "status": "planned",
                    }
                ],
                "created_at": "2026-07-18T10:00:00+08:00",
                "created_by": "fixture-author",
            },
        },
        "evidence_artifact_v2_1": {
            "schema_version": "2.1.0",
            "artifact_kind": "evidence_artifact",
            "evidence_artifact": {
                "evidence_artifact_id": "evidence_artifact:fixture",
                "project_id": "research_project:fixture-industry",
                "version_id": "research_version:fixture-industry:0.1.0",
                "evidence_channel": "industry",
                "source_candidate_id": "source_candidate:fixture",
                "source_uri": "https://example.com/source.pdf",
                "retrieved_at": "2026-07-18T10:00:00Z",
                "content_hash": "b" * 64,
                "media_type": "application/pdf",
                "storage_path": "evidence/raw/bb/fixture.pdf",
            },
        },
        "normalized_document_v2_1": {
            "schema_version": "2.1.0",
            "artifact_kind": "normalized_document",
            "normalized_document": {
                "normalized_document_id": "normalized_document:fixture",
                "evidence_artifact_id": "evidence_artifact:fixture",
                "project_id": "research_project:fixture-industry",
                "version_id": "research_version:fixture-industry:0.1.0",
                "title": "Fixture source",
                "normalized_at": "2026-07-18T10:00:00Z",
                "content_hash": "c" * 64,
                "sections": [
                    {
                        "section_id": "section:fixture:0001",
                        "heading": "Mechanism",
                        "ordinal": 1,
                        "text": "Fixture normalized text.",
                        "content_hash": "d" * 64,
                    }
                ],
            },
        },
        "industry_evidence_assessment_v2_1": {
            "schema_version": "2.1.0",
            "artifact_kind": "industry_evidence_assessment",
            "industry_evidence_assessment": {
                "assessment_id": "industry_evidence_assessment:fixture",
                "project_id": "research_project:fixture-industry",
                "version_id": "research_version:fixture-industry:0.1.0",
                "evidence_artifact_id": "evidence_artifact:fixture",
                "target_type": "research_claim",
                "target_id": "claim:fixture",
                "evidence_role": "supports",
                "directness": "direct",
                "strength": "strong",
                "independence": "independent",
                "freshness": {
                    "assessed_at": "2026-07-18T10:00:00Z",
                    "source_published_at": "2026-07-01T00:00:00Z",
                    "status": "current",
                    "rationale": "Published within the required window.",
                },
                "scope_match": "full",
                "conflict_status": "none",
                "assessment_summary": "Direct industry evidence.",
                "assessed_at": "2026-07-18T10:00:00Z",
                "assessed_by": "fixture-author",
            },
        },
        "research_project_index_v2_1": {
            "schema_version": "2.1.0",
            "artifact_kind": "research_project_index",
            "generated_at": "2026-07-18T10:00:00Z",
            "projects": [
                {
                    "project_id": "research_project:fixture-industry",
                    "project_slug": "fixture-industry",
                    "title": "Fixture industry research project",
                    "research_layer": "industry_research",
                    "current_lifecycle_state": "research_ready",
                    "evidence_stage": "requirements_defined",
                    "conclusion_status": "unavailable",
                    "current_version": "research_version:fixture-industry:0.1.0",
                    "latest_reviewed_version": None,
                    "latest_published_version": None,
                    "relative_path": "projects/fixture-industry",
                }
            ],
        },
    }


@pytest.mark.parametrize("schema_name", sorted(_standalone_payloads()))
def test_standalone_schema_resolves_common_refs_and_accepts_valid_payload(
    schema_name,
):
    validate_v2_1_schema_payload(schema_name, _standalone_payloads()[schema_name])


@pytest.mark.parametrize(
    ("schema_name", "object_key", "field", "invalid_value", "expected_path"),
    [
        (
            "search_plan_v2_1",
            "search_plan",
            "created_at",
            "2026-07-18",
            ["search_plan", "created_at"],
        ),
        (
            "evidence_artifact_v2_1",
            "evidence_artifact",
            "content_hash",
            "B" * 64,
            ["evidence_artifact", "content_hash"],
        ),
        (
            "normalized_document_v2_1",
            "normalized_document",
            "normalized_at",
            "not-a-date",
            ["normalized_document", "normalized_at"],
        ),
        (
            "industry_evidence_assessment_v2_1",
            "industry_evidence_assessment",
            "assessed_at",
            "not-a-date",
            ["industry_evidence_assessment", "assessed_at"],
        ),
        (
            "research_project_index_v2_1",
            None,
            "generated_at",
            "2026-07-18",
            ["generated_at"],
        ),
    ],
)
def test_standalone_schemas_enforce_nested_formats_and_hashes(
    schema_name, object_key, field, invalid_value, expected_path
):
    payload = deepcopy(_standalone_payloads()[schema_name])
    target = payload if object_key is None else payload[object_key]
    target[field] = invalid_value

    with pytest.raises(ResearchProjectV2Error) as exc_info:
        validate_v2_1_schema_payload(schema_name, payload)

    assert exc_info.value.code == "RESEARCH_PROJECT_V2_1_SCHEMA_INVALID"
    assert exc_info.value.details == {
        "schema": schema_name,
        "path": expected_path,
    }


def test_every_declared_object_schema_is_strict():
    def walk(node):
        if isinstance(node, dict):
            if node.get("type") == "object":
                assert node.get("additionalProperties") is False
            for child in node.values():
                walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    for filename in sorted(ALL_SCHEMA_FILES):
        walk(json.loads((SCHEMA_DIR / filename).read_text()))
