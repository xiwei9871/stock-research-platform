from copy import deepcopy
import json
from pathlib import Path
import warnings

from jsonschema import Draft202012Validator, FormatChecker
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

PROVENANCE = {
    "created_by": "fixture-author",
    "actor_type": "human",
    "agent_run_id": None,
    "created_at": "2026-07-18T10:00:00Z",
    "created_in_version": "research_version:fixture-industry:0.1.0",
    "review_status": "unreviewed",
}


def canonical_search_plan():
    return {
        "search_plan_id": "search_plan:requirement:fixture",
        "project_id": "research_project:fixture-industry",
        "version_id": "research_version:fixture-industry:0.1.0",
        "evidence_channel": "industry",
        "requirement_ids": ["requirement:fixture"],
        "queries": [
            {
                "query_id": "query:requirement:fixture:mechanism",
                "query_role": "mechanism",
                "query_text": "fixture mechanism engineering",
                "required_terms": ["fixture technology"],
                "excluded_terms": ["target price"],
                "source_classes": ["primary", "independent_secondary"],
                "priority": 1,
            },
            {
                "query_id": "query:requirement:fixture:counter",
                "query_role": "counter_evidence",
                "query_text": "fixture alternative substitution limitation",
                "required_terms": ["fixture technology"],
                "excluded_terms": ["buy rating"],
                "source_classes": ["primary", "independent_secondary"],
                "priority": 2,
            },
        ],
        "languages": ["zh-CN", "en"],
        "geography": ["CN", "global"],
        "publication_window": "within_12_months",
        "result_limit_per_query": 20,
        "deduplication_policy": "normalized_url_then_content_hash",
        "stop_conditions": [
            "all query roles executed",
            "counter-evidence query executed",
        ],
        "status": "planned",
        "provenance": PROVENANCE,
    }


def canonical_normalized_document():
    return {
        "document_id": "normalized_document:fixture",
        "artifact_id": "evidence_artifact:fixture",
        "parser": "html",
        "parser_version": "1.0.0",
        "media_type": "text/html",
        "title": "Fixture source",
        "sections": [
            {
                "section_id": "section:evidence_artifact:fixture:0001",
                "heading": "Mechanism",
                "locator": "#mechanism",
                "text": "Fixture normalized text.",
                "page_start": None,
                "page_end": None,
                "section_hash": "d" * 64,
            }
        ],
        "document_hash": "c" * 64,
        "parsed_at": "2026-07-18T10:00:00Z",
        "warnings": [],
        "provenance": PROVENANCE,
    }


def canonical_industry_evidence_assessment():
    return {
        "assessment_id": "industry_evidence_assessment:fixture",
        "evidence_channel": "industry",
        "target_type": "research_claim",
        "target_id": "claim:fixture",
        "requirement_id": "requirement:fixture",
        "artifact_id": "evidence_artifact:fixture",
        "normalized_document_id": "normalized_document:fixture",
        "evidence_role": "supports",
        "locator": "#mechanism",
        "assessment_summary": "Direct industry evidence.",
        "directness": "direct",
        "strength": "strong",
        "independence": "independent",
        "freshness": "fresh",
        "scope_match": "full",
        "conflict_status": "none",
        "review_status": "pending_review",
        "provenance": PROVENANCE,
    }


def industry_evidence_requirement(target_type="research_claim"):
    return {
        "requirement_id": "requirement:fixture",
        "target_type": target_type,
        "target_id": "claim:fixture",
        "question_to_resolve": "Is the industry mechanism observed?",
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


def industry_causal_node(node_kind="mechanism"):
    return {
        "causal_node_id": "causal_node:fixture",
        "node_kind": node_kind,
        "node_text": "Fixture industry mechanism",
        "lifecycle_status": "active",
        "provenance": PROVENANCE,
    }


def evidence_artifact(evidence_channel="industry"):
    return {
        "evidence_artifact_id": "evidence_artifact:fixture",
        "project_id": "research_project:fixture-industry",
        "version_id": "research_version:fixture-industry:0.1.0",
        "evidence_channel": evidence_channel,
        "source_candidate_id": "source_candidate:fixture",
        "source_uri": "https://example.com/source.pdf",
        "retrieved_at": "2026-07-18T10:00:00Z",
        "content_hash": "b" * 64,
        "media_type": "application/pdf",
        "storage_path": "evidence/raw/bb/fixture.pdf",
    }


def canonical_evidence_artifact(evidence_channel="industry"):
    return {
        "artifact_id": "evidence_artifact:fixture",
        "candidate_id": "source_candidate:fixture",
        "evidence_channel": evidence_channel,
        "original_url": "https://example.com/original.pdf",
        "final_url": "https://cdn.example.com/final.pdf",
        "redirect_chain": ["https://example.com/redirect"],
        "status_code": 200,
        "response_headers": {
            "content-type": "application/pdf",
            "content-length": "1024",
        },
        "media_type": "application/pdf",
        "byte_count": 1024,
        "content_sha256": "b" * 64,
        "fetched_at": "2026-07-18T10:00:00Z",
        "raw_path": "evidence/raw/bb/" + "b" * 64 + ".pdf",
        "provenance": PROVENANCE,
        "publisher_family": "fixture-publisher-family",
        "upstream_source_id": None,
        "section_hashes": ["c" * 64],
    }


def upstream_research_ref(upstream_research_layer=None):
    return {
        "upstream_research_ref_id": "upstream_ref:fixture",
        "upstream_research_layer": upstream_research_layer,
        "upstream_project_id": "research_project:upstream-fixture",
        "upstream_version_id": "research_version:upstream-fixture:0.1.0",
        "upstream_object_type": "research_version",
        "upstream_object_id": None,
        "upstream_gate_result_id": None,
        "upstream_content_hash": "e" * 64,
        "referenced_at": "2026-07-18T10:00:00Z",
        "scope_note": "Fixture upstream reference.",
    }


def canonical_source_candidate():
    return {
        "candidate_id": "source_candidate:fixture",
        "search_plan_id": "search_plan:requirement:fixture",
        "query_id": "query:requirement:fixture:mechanism",
        "normalized_url": "https://example.com/source.pdf?a=1&b=2",
        "original_url": "https://EXAMPLE.com/source.pdf?b=2&a=1&utm_source=test",
        "title": "Fixture engineering source",
        "snippet": "Fixture mechanism and qualification evidence.",
        "publisher": "Fixture publisher",
        "publish_date": "2026-07-01",
        "source_class": "primary",
        "rank": 1,
        "exclusion_status": "included",
        "exclusion_reasons": [],
        "dedup_key": "https://example.com/source.pdf?a=1&b=2",
        "provenance": PROVENANCE,
    }


def canonical_source_relationship():
    return {
        "left_artifact_id": "evidence_artifact:left",
        "right_artifact_id": "evidence_artifact:right",
        "relationship": "independent",
        "reasons": ["publisher families and content hashes differ"],
    }


def canonical_conflict_summary():
    return {
        "conflict_summary_id": "conflict_summary:claim:fixture",
        "evidence_channel": "industry",
        "target_type": "research_claim",
        "target_id": "claim:fixture",
        "conflict_status": "material_conflict",
        "supporting_source_count": 2,
        "opposing_source_count": 1,
        "quantitative_source_count": 1,
        "independent_source_family_count": 3,
        "assessment_ids": [
            "industry_evidence_assessment:support",
            "industry_evidence_assessment:oppose",
        ],
        "summary": "Independent sources materially disagree.",
        "assessed_at": "2026-07-18T10:00:00Z",
        "provenance": PROVENANCE,
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
    ("schema_name", "artifact_kind", "body_key", "builder_payload"),
    [
        (
            "search_plan_v2_1",
            "search_plan",
            "search_plan",
            canonical_search_plan(),
        ),
        (
            "normalized_document_v2_1",
            "normalized_document",
            "normalized_document",
            canonical_normalized_document(),
        ),
        (
            "industry_evidence_assessment_v2_1",
            "industry_evidence_assessment",
            "industry_evidence_assessment",
            canonical_industry_evidence_assessment(),
        ),
    ],
)
def test_builder_shaped_payload_passes_standalone_schema(
    schema_name, artifact_kind, body_key, builder_payload
):
    validate_v2_1_schema_payload(
        schema_name,
        {
            "schema_version": "2.1.0",
            "artifact_kind": artifact_kind,
            body_key: builder_payload,
        },
    )


def test_builder_shaped_payloads_pass_industry_version_schema(
    sample_industry_version,
):
    snapshot = sample_industry_version["snapshot"]
    snapshot["search_plans"] = [canonical_search_plan()]
    snapshot["normalized_documents"] = [canonical_normalized_document()]
    snapshot["industry_evidence_assessments"] = [
        canonical_industry_evidence_assessment()
    ]
    sample_industry_version["creation_stage"] = "evidence_snapshot"

    validate_v2_1_schema_payload(
        "industry_research_version_v2_1", sample_industry_version
    )


def test_task5_builder_shaped_source_candidate_passes_industry_version(
    sample_industry_version,
):
    sample_industry_version["creation_stage"] = "evidence_snapshot"
    sample_industry_version["snapshot"]["source_candidates"] = [
        canonical_source_candidate()
    ]

    validate_v2_1_schema_payload(
        "industry_research_version_v2_1", sample_industry_version
    )


def test_task6_builder_shaped_artifact_passes_standalone_and_industry_version(
    sample_industry_version,
):
    artifact = canonical_evidence_artifact()
    artifact["response_headers"] = {
        "content-type": "application/pdf",
        "content-length": "1024",
        "content-disposition": "inline; filename=fixture.pdf",
        "etag": '"fixture-etag"',
        "last-modified": "Fri, 18 Jul 2026 02:00:00 GMT",
        "cache-control": "public, max-age=3600",
        "expires": "Fri, 18 Jul 2026 03:00:00 GMT",
        "date": "Fri, 18 Jul 2026 02:00:00 GMT",
    }
    standalone = {
        "schema_version": "2.1.0",
        "artifact_kind": "evidence_artifact",
        "evidence_artifact": artifact,
    }

    validate_v2_1_schema_payload("evidence_artifact_v2_1", standalone)

    sample_industry_version["creation_stage"] = "evidence_snapshot"
    snapshot = sample_industry_version["snapshot"]
    snapshot["evidence_artifacts"] = [artifact]
    document = canonical_normalized_document()
    assessment = canonical_industry_evidence_assessment()
    document["artifact_id"] = artifact["artifact_id"]
    assessment["artifact_id"] = artifact["artifact_id"]
    snapshot["normalized_documents"] = [document]
    snapshot["industry_evidence_assessments"] = [assessment]

    assert document["artifact_id"] == artifact["artifact_id"]
    assert assessment["artifact_id"] == artifact["artifact_id"]
    # Task 6 semantic validation must additionally prove that raw_path's
    # directory equals content_sha256[:2] and its filename hash equals
    # content_sha256; JSON Schema can only validate the canonical shape.
    validate_v2_1_schema_payload(
        "industry_research_version_v2_1", sample_industry_version
    )


def test_evidence_artifact_rejects_legacy_field_shape():
    payload = {
        "schema_version": "2.1.0",
        "artifact_kind": "evidence_artifact",
        "evidence_artifact": evidence_artifact(),
    }

    with pytest.raises(ResearchProjectV2Error) as exc_info:
        validate_v2_1_schema_payload("evidence_artifact_v2_1", payload)

    assert exc_info.value.code == "RESEARCH_PROJECT_V2_1_SCHEMA_INVALID"
    assert exc_info.value.details["path"] == ["evidence_artifact"]


@pytest.mark.parametrize(
    ("field", "invalid_value", "expected_path"),
    [
        ("content_sha256", "B" * 64, ["evidence_artifact", "content_sha256"]),
        ("raw_path", "/tmp/raw.pdf", ["evidence_artifact", "raw_path"]),
        ("raw_path", "C:\\tmp\\raw.pdf", ["evidence_artifact", "raw_path"]),
        ("raw_path", "C:/tmp/raw.pdf", ["evidence_artifact", "raw_path"]),
        ("raw_path", "C:raw.pdf", ["evidence_artifact", "raw_path"]),
        ("raw_path", "./raw.pdf", ["evidence_artifact", "raw_path"]),
        ("raw_path", "evidence/./raw.pdf", ["evidence_artifact", "raw_path"]),
        ("raw_path", "../raw.pdf", ["evidence_artifact", "raw_path"]),
        ("raw_path", "foo.txt", ["evidence_artifact", "raw_path"]),
        (
            "raw_path",
            "metadata/not-content-addressed.json",
            ["evidence_artifact", "raw_path"],
        ),
        (
            "raw_path",
            "https://example.com/raw.pdf",
            ["evidence_artifact", "raw_path"],
        ),
        (
            "raw_path",
            "evidence/raw/BB/" + "b" * 64 + ".pdf",
            ["evidence_artifact", "raw_path"],
        ),
        (
            "raw_path",
            "evidence/raw/bb/" + "b" * 63 + ".pdf",
            ["evidence_artifact", "raw_path"],
        ),
        (
            "raw_path",
            "evidence/raw/bb/" + "B" * 64 + ".pdf",
            ["evidence_artifact", "raw_path"],
        ),
        (
            "raw_path",
            "evidence/raw/bb/" + "b" * 64 + ".exe",
            ["evidence_artifact", "raw_path"],
        ),
        (
            "raw_path",
            "evidence/raw/../metadata.json",
            ["evidence_artifact", "raw_path"],
        ),
        (
            "response_headers",
            {"set-cookie": "secret=1"},
            ["evidence_artifact", "response_headers"],
        ),
        (
            "response_headers",
            {"Authorization": "Bearer secret"},
            ["evidence_artifact", "response_headers"],
        ),
        (
            "response_headers",
            {"Authorization ": "Bearer secret"},
            ["evidence_artifact", "response_headers"],
        ),
        (
            "response_headers",
            {" authorization": "Bearer secret"},
            ["evidence_artifact", "response_headers"],
        ),
        (
            "response_headers",
            {"server": "private-origin"},
            ["evidence_artifact", "response_headers"],
        ),
        (
            "response_headers",
            {"x-arbitrary-private-metadata": "private"},
            ["evidence_artifact", "response_headers"],
        ),
        (
            "response_headers",
            {"content-length": 1024},
            ["evidence_artifact", "response_headers", "content-length"],
        ),
    ],
)
def test_evidence_artifact_rejects_invalid_hash_path_and_headers(
    field, invalid_value, expected_path
):
    artifact = canonical_evidence_artifact()
    artifact[field] = invalid_value
    payload = {
        "schema_version": "2.1.0",
        "artifact_kind": "evidence_artifact",
        "evidence_artifact": artifact,
    }

    with pytest.raises(ResearchProjectV2Error) as exc_info:
        validate_v2_1_schema_payload("evidence_artifact_v2_1", payload)

    assert exc_info.value.code == "RESEARCH_PROJECT_V2_1_SCHEMA_INVALID"
    assert exc_info.value.details["path"] == expected_path


def test_source_candidate_rejects_unknown_field(sample_industry_version):
    candidate = canonical_source_candidate()
    candidate["discovered_at"] = "2026-07-18T10:00:00Z"
    sample_industry_version["snapshot"]["source_candidates"] = [candidate]

    with pytest.raises(ResearchProjectV2Error) as exc_info:
        validate_v2_1_schema_payload(
            "industry_research_version_v2_1", sample_industry_version
        )

    assert exc_info.value.code == "RESEARCH_PROJECT_V2_1_SCHEMA_INVALID"
    assert exc_info.value.details["path"] == ["snapshot", "source_candidates", 0]


def test_task8_builder_shaped_source_relationship_passes_industry_version(
    sample_industry_version,
):
    sample_industry_version["creation_stage"] = "evidence_snapshot"
    sample_industry_version["snapshot"]["source_relationships"] = [
        canonical_source_relationship()
    ]

    validate_v2_1_schema_payload(
        "industry_research_version_v2_1", sample_industry_version
    )


@pytest.mark.parametrize(
    ("field", "invalid_value", "expected_path"),
    [
        ("relationship", "same_domain", ["snapshot", "source_relationships", 0, "relationship"]),
        ("relationship_id", "relationship:extra", ["snapshot", "source_relationships", 0]),
    ],
)
def test_source_relationship_rejects_invalid_enum_and_unknown_field(
    sample_industry_version, field, invalid_value, expected_path
):
    relationship = canonical_source_relationship()
    relationship[field] = invalid_value
    sample_industry_version["snapshot"]["source_relationships"] = [relationship]

    with pytest.raises(ResearchProjectV2Error) as exc_info:
        validate_v2_1_schema_payload(
            "industry_research_version_v2_1", sample_industry_version
        )

    assert exc_info.value.code == "RESEARCH_PROJECT_V2_1_SCHEMA_INVALID"
    assert exc_info.value.details["path"] == expected_path


def test_task8_material_conflict_summary_passes_industry_version(
    sample_industry_version,
):
    sample_industry_version["creation_stage"] = "evidence_snapshot"
    sample_industry_version["snapshot"]["conflict_summaries"] = [
        canonical_conflict_summary()
    ]

    validate_v2_1_schema_payload(
        "industry_research_version_v2_1", sample_industry_version
    )


@pytest.mark.parametrize(
    "invalid_status",
    ["open", "resolved", "accepted_uncertainty", "unknown_status"],
)
def test_conflict_summary_rejects_legacy_and_unknown_statuses(
    sample_industry_version, invalid_status
):
    summary = canonical_conflict_summary()
    summary["conflict_status"] = invalid_status
    sample_industry_version["snapshot"]["conflict_summaries"] = [summary]

    with pytest.raises(ResearchProjectV2Error) as exc_info:
        validate_v2_1_schema_payload(
            "industry_research_version_v2_1", sample_industry_version
        )

    assert exc_info.value.code == "RESEARCH_PROJECT_V2_1_SCHEMA_INVALID"
    assert exc_info.value.details["path"] == [
        "snapshot",
        "conflict_summaries",
        0,
        "conflict_status",
    ]


def test_conflict_summary_rejects_unknown_field(sample_industry_version):
    summary = canonical_conflict_summary()
    summary["resolution"] = "legacy field"
    sample_industry_version["snapshot"]["conflict_summaries"] = [summary]

    with pytest.raises(ResearchProjectV2Error) as exc_info:
        validate_v2_1_schema_payload(
            "industry_research_version_v2_1", sample_industry_version
        )

    assert exc_info.value.code == "RESEARCH_PROJECT_V2_1_SCHEMA_INVALID"
    assert exc_info.value.details["path"] == ["snapshot", "conflict_summaries", 0]


def test_industry_snapshot_persists_without_company_capture_assessments(
    sample_industry_version,
):
    # Task 3 must inject company_capture_assessments=[] only into its temporary
    # R1 common-semantics projection; it is never a persisted Industry field.
    assert "company_capture_assessments" not in sample_industry_version["snapshot"]

    validate_v2_1_schema_payload(
        "industry_research_version_v2_1", sample_industry_version
    )


def test_industry_search_plan_rejects_stock_layer_escape(
    sample_industry_version,
):
    plan = canonical_search_plan()
    plan["research_layer"] = "stock_evaluation"
    sample_industry_version["snapshot"]["search_plans"] = [plan]

    with pytest.raises(ResearchProjectV2Error) as exc_info:
        validate_v2_1_schema_payload(
            "industry_research_version_v2_1", sample_industry_version
        )

    assert exc_info.value.code == "RESEARCH_PROJECT_V2_1_SCHEMA_INVALID"
    assert exc_info.value.details["path"] == ["snapshot", "search_plans", 0]


def test_industry_evidence_requirement_rejects_company_target(
    sample_industry_version,
):
    sample_industry_version["snapshot"]["evidence_requirements"] = [
        industry_evidence_requirement("company_capture")
    ]

    with pytest.raises(ResearchProjectV2Error) as exc_info:
        validate_v2_1_schema_payload(
            "industry_research_version_v2_1", sample_industry_version
        )

    assert exc_info.value.code == "RESEARCH_PROJECT_V2_1_SCHEMA_INVALID"
    assert exc_info.value.details["path"] == [
        "snapshot",
        "evidence_requirements",
        0,
        "target_type",
    ]


def test_industry_causal_node_rejects_company_capture_kind(
    sample_industry_version,
):
    sample_industry_version["snapshot"]["causal_nodes"] = [
        industry_causal_node("company_capture")
    ]

    with pytest.raises(ResearchProjectV2Error) as exc_info:
        validate_v2_1_schema_payload(
            "industry_research_version_v2_1", sample_industry_version
        )

    assert exc_info.value.code == "RESEARCH_PROJECT_V2_1_SCHEMA_INVALID"
    assert exc_info.value.details["path"] == [
        "snapshot",
        "causal_nodes",
        0,
        "node_kind",
    ]


@pytest.mark.parametrize(
    "investment_status",
    ["watchlist_candidate", "strategy_hypothesis"],
)
def test_industry_snapshot_rejects_downstream_investment_status(
    sample_industry_version, investment_status
):
    sample_industry_version["creation_stage"] = "evidence_snapshot"
    sample_industry_version["snapshot"]["investment_status"] = investment_status

    with pytest.raises(ResearchProjectV2Error) as exc_info:
        validate_v2_1_schema_payload(
            "industry_research_version_v2_1", sample_industry_version
        )

    assert exc_info.value.code == "RESEARCH_PROJECT_V2_1_SCHEMA_INVALID"
    assert exc_info.value.details["path"] == ["snapshot", "investment_status"]


@pytest.mark.parametrize(
    ("collection", "payload", "expected_path"),
    [
        (
            "source_candidates",
            {**canonical_source_candidate(), "evidence_channel": "company"},
            ["snapshot", "source_candidates", 0],
        ),
        (
            "evidence_artifacts",
            canonical_evidence_artifact("market"),
            ["snapshot", "evidence_artifacts", 0, "evidence_channel"],
        ),
        (
            "industry_evidence_assessments",
            {
                **canonical_industry_evidence_assessment(),
                "target_type": "company_capture",
            },
            [
                "snapshot",
                "industry_evidence_assessments",
                0,
                "target_type",
            ],
        ),
        (
            "upstream_research_refs",
            upstream_research_ref("stock_evaluation"),
            ["snapshot", "upstream_research_refs", 0, "upstream_research_layer"],
        ),
        (
            "conflict_summaries",
            {**canonical_conflict_summary(), "target_type": "stock_rating"},
            ["snapshot", "conflict_summaries", 0, "target_type"],
        ),
    ],
)
def test_industry_snapshot_rejects_other_company_and_market_semantic_escapes(
    sample_industry_version, collection, payload, expected_path
):
    sample_industry_version["creation_stage"] = "evidence_snapshot"
    sample_industry_version["snapshot"][collection] = [payload]

    with pytest.raises(ResearchProjectV2Error) as exc_info:
        validate_v2_1_schema_payload(
            "industry_research_version_v2_1", sample_industry_version
        )

    assert exc_info.value.code == "RESEARCH_PROJECT_V2_1_SCHEMA_INVALID"
    assert exc_info.value.details["path"] == expected_path


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


def test_freshness_assessment_accepts_task8_calculation_result():
    definitions = json.loads(
        (SCHEMA_DIR / "definitions_v2_1.schema.json").read_text()
    )
    validator = Draft202012Validator(
        definitions["$defs"]["freshness_assessment"],
        format_checker=FormatChecker(),
    )

    validator.validate(
        {
            "status": "fresh",
            "publish_date": "2026-07-01",
            "assessed_at": "2026-07-18T10:00:00Z",
            "age_days": 17,
            "maximum_age_days": 365,
        }
    )


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
            "search_plan": canonical_search_plan(),
        },
        "evidence_artifact_v2_1": {
            "schema_version": "2.1.0",
            "artifact_kind": "evidence_artifact",
            "evidence_artifact": canonical_evidence_artifact(),
        },
        "normalized_document_v2_1": {
            "schema_version": "2.1.0",
            "artifact_kind": "normalized_document",
            "normalized_document": canonical_normalized_document(),
        },
        "industry_evidence_assessment_v2_1": {
            "schema_version": "2.1.0",
            "artifact_kind": "industry_evidence_assessment",
            "industry_evidence_assessment": canonical_industry_evidence_assessment(),
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


def test_standalone_normalized_document_accepts_empty_root_locator():
    payload = deepcopy(_standalone_payloads()["normalized_document_v2_1"])
    payload["normalized_document"]["sections"][0]["locator"] = ""
    validate_v2_1_schema_payload("normalized_document_v2_1", payload)


def test_standalone_industry_assessment_accepts_empty_root_locator():
    payload = deepcopy(_standalone_payloads()["industry_evidence_assessment_v2_1"])
    payload["industry_evidence_assessment"]["locator"] = ""
    validate_v2_1_schema_payload("industry_evidence_assessment_v2_1", payload)


@pytest.mark.parametrize("evidence_channel", ["company", "market"])
def test_standalone_evidence_artifact_rejects_non_industry_channels(
    evidence_channel,
):
    payload = deepcopy(_standalone_payloads()["evidence_artifact_v2_1"])
    payload["evidence_artifact"]["evidence_channel"] = evidence_channel

    with pytest.raises(ResearchProjectV2Error) as exc_info:
        validate_v2_1_schema_payload("evidence_artifact_v2_1", payload)

    assert exc_info.value.code == "RESEARCH_PROJECT_V2_1_SCHEMA_INVALID"
    assert exc_info.value.details["path"] == [
        "evidence_artifact",
        "evidence_channel",
    ]


@pytest.mark.parametrize(
    ("schema_name", "object_key", "field", "invalid_value", "expected_path"),
    [
        (
            "search_plan_v2_1",
            "search_plan",
            "evidence_channel",
            "stock_evaluation",
            ["search_plan", "evidence_channel"],
        ),
        (
            "evidence_artifact_v2_1",
            "evidence_artifact",
            "content_sha256",
            "B" * 64,
            ["evidence_artifact", "content_sha256"],
        ),
        (
            "normalized_document_v2_1",
            "normalized_document",
            "parsed_at",
            "not-a-date",
            ["normalized_document", "parsed_at"],
        ),
        (
            "industry_evidence_assessment_v2_1",
            "industry_evidence_assessment",
            "freshness",
            "company_guidance",
            ["industry_evidence_assessment", "freshness"],
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
