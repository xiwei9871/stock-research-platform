from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from hashlib import sha256
from pathlib import Path

import pytest

import stock_research.research_project_v2_1.evidence as evidence_module
from stock_research.research_project_v2.canonical import canonical_bytes, content_sha256
from stock_research.research_project_v2.errors import ResearchProjectV2Error
from stock_research.research_project_v2_1.evidence import (
    assess_freshness,
    assess_source_relationship,
    build_conflict_summaries,
    build_industry_evidence_assessment,
    count_independent_coverage,
    validate_industry_evidence_assessments,
    write_industry_evidence_assessment,
)
from stock_research.research_project_v2_1.layout import LayeredResearchLayout


def _provenance() -> dict:
    return {
        "created_by": "test",
        "actor_type": "automated_pipeline",
        "agent_run_id": "run:test",
        "created_at": "2026-07-18T10:00:00Z",
        "created_in_version": "2.1.0",
        "review_status": "unreviewed",
    }


def _artifact(
    artifact_id: str,
    digest: str,
    *,
    publisher_family: str | None,
    upstream_source_id: str | None = None,
    section_hashes: list[str] | None = None,
) -> dict:
    return {
        "artifact_id": artifact_id,
        "candidate_id": f"candidate:{artifact_id}",
        "evidence_channel": "industry",
        "original_url": f"https://example.com/{artifact_id}",
        "final_url": f"https://cdn.example.com/{artifact_id}",
        "redirect_chain": [],
        "status_code": 200,
        "response_headers": {"content-type": "text/plain"},
        "media_type": "text/plain",
        "byte_count": 1,
        "content_sha256": digest,
        "fetched_at": "2026-07-18T10:00:00Z",
        "raw_path": f"evidence/raw/{digest[:2]}/{digest}.txt",
        "provenance": _provenance(),
        "publisher_family": publisher_family,
        "upstream_source_id": upstream_source_id,
        "section_hashes": section_hashes or [],
    }


def _document(artifact_id: str, locator: str = "section:1") -> dict:
    section = {
        "section_id": f"section:{artifact_id}:0001",
        "heading": "Evidence",
        "locator": locator,
        "text": "Observed evidence.",
        "page_start": None,
        "page_end": None,
    }
    section["section_hash"] = content_sha256(
        {key: section[key] for key in ("heading", "locator", "text")}
    )
    core = {
        "artifact_id": artifact_id,
        "parser": "text",
        "parser_version": "1.0.0",
        "media_type": "text/plain",
        "title": "Evidence",
        "sections": [section],
        "warnings": [],
        "parsed_at": "2026-07-18T10:00:00Z",
        "provenance": _provenance(),
    }
    document_hash = content_sha256(core)
    identity = sha256(f"{artifact_id}\n{document_hash}".encode()).hexdigest()[:24]
    return {
        "document_id": f"normalized_document:{identity}",
        **core,
        "document_hash": document_hash,
    }


def _requirement(minimum_coverage: int = 1) -> dict:
    return {
        "requirement_id": "requirement:test",
        "target_type": "research_claim",
        "target_id": "claim:test",
        "question_to_resolve": "Is the claim supported?",
        "requirement_type": "validation",
        "required_source_classes": ["primary"],
        "required_independence": "independent",
        "required_freshness": "within_12_months",
        "required_scope": "global",
        "minimum_coverage": minimum_coverage,
        "conflict_search_required": True,
        "primary_source_required": True,
        "collection_status": "not_started",
        "satisfaction_status": "unsatisfied",
        "provenance": _provenance(),
    }


def _claim(claim_id: str = "claim:test") -> dict:
    return {
        "claim_id": claim_id,
        "claim_kind": "primary",
        "epistemic_type": "hypothesis",
        "claim_text": "Test claim",
        "claim_status": "hypothesis",
        "lifecycle_status": "active",
        "confidence": 0.2,
        "importance": 0.8,
        "linked_question_ids": [],
        "context_reference_ids": [],
        "created_in_version": "2.1.0",
        "supersedes_claim_id": None,
        "validation_metric_ids": [],
        "invalidation_condition_ids": [],
        "provenance": _provenance(),
    }


def _assessment(
    artifact: dict, *, role: str, reviewed: bool = True, locator: str = "section:1"
) -> dict:
    document = _document(artifact["artifact_id"], locator=locator)
    result = build_industry_evidence_assessment(
        requirement=_requirement(),
        target=_claim(),
        artifact=artifact,
        normalized_document=document,
        locator=locator,
        evidence_role=role,
        assessment_summary=f"{role} evidence",
        directness="direct",
        strength="strong",
        independence="independent",
        freshness="fresh",
        scope_match="full",
        conflict_status="none",
        provenance=_provenance(),
    )
    if reviewed:
        result["review_status"] = "reviewed"
    return result


def test_source_relationship_priority_and_independence_require_provenance() -> None:
    same = _artifact("artifact:a", "a" * 64, publisher_family="publisher:a")
    mirror = _artifact("artifact:b", "a" * 64, publisher_family="publisher:b")
    assert assess_source_relationship(same, mirror)["relationship"] == "same_document"

    left = _artifact("artifact:c", "b" * 64, publisher_family="publisher:a", section_hashes=["1" * 64] * 0 + ["c" * 64, "d" * 64, "e" * 64, "f" * 64])
    right = _artifact("artifact:d", "c" * 64, publisher_family="publisher:b", section_hashes=["c" * 64, "d" * 64, "e" * 64, "f" * 64, "9" * 64])
    assert assess_source_relationship(left, right)["relationship"] == "republication"

    shared = deepcopy(right)
    left["section_hashes"] = []
    shared["section_hashes"] = []
    left["upstream_source_id"] = shared["upstream_source_id"] = "standard:1"
    assert assess_source_relationship(left, shared)["relationship"] == "shared_upstream_source"

    shared["upstream_source_id"] = None
    shared["publisher_family"] = left["publisher_family"]
    assert assess_source_relationship(left, shared)["relationship"] == "same_publisher_family"

    shared["publisher_family"] = "association"
    assert assess_source_relationship(left, shared)["relationship"] == "independent"
    shared["publisher_family"] = None
    assert assess_source_relationship(left, shared)["relationship"] == "unknown"


@pytest.mark.parametrize(
    ("publish_date", "maximum_age_days", "status", "age_days"),
    [(None, 30, "unknown", None), ("2026-06-18", 30, "fresh", 30), ("2026-06-17", 30, "stale", 31), ("2026-07-19", 30, "future_dated", -1), ("2024-02-29", 900, "fresh", 870)],
)
def test_freshness_is_explicit_and_deterministic(publish_date, maximum_age_days, status, age_days) -> None:
    result = assess_freshness(publish_date, assessed_at="2026-07-18T23:59:59+08:00", maximum_age_days=maximum_age_days)
    assert result == {"status": status, "publish_date": publish_date, "assessed_at": "2026-07-18T23:59:59+08:00", "age_days": age_days, "maximum_age_days": maximum_age_days}


@pytest.mark.parametrize("publish_date, assessed_at, maximum", [("2026-02-29", "2026-07-18T00:00:00Z", 30), ("2026-01-01", "not-rfc3339", 30), ("2026-01-01", "2026-07-18T00:00:00", 30), ("2026-01-01", "2026-07-18T00:00:00Z", True), ("2026-01-01", "2026-07-18T00:00:00Z", -1)])
def test_freshness_rejects_invalid_inputs_stably(publish_date, assessed_at, maximum) -> None:
    with pytest.raises(ResearchProjectV2Error) as exc:
        assess_freshness(publish_date, assessed_at=assessed_at, maximum_age_days=maximum)
    assert exc.value.code == "RESEARCH_PROJECT_V2_1_EVIDENCE_ASSESSMENT_INVALID"

def test_build_assessment_validates_cross_references_locator_and_does_not_mutate() -> None:
    artifact = _artifact("artifact:filing", "a" * 64, publisher_family="issuer")
    document = _document(artifact["artifact_id"], locator="")
    target = _claim()
    originals = deepcopy((_requirement(), target, artifact, document, _provenance()))
    result = build_industry_evidence_assessment(
        requirement=originals[0], target=target, artifact=artifact, normalized_document=document,
        locator="", evidence_role="supports", assessment_summary="  Direct filing evidence.  ",
        directness="direct", strength="strong", independence="independent", freshness="fresh",
        scope_match="full", conflict_status="none", provenance=originals[4],
    )
    expected = sha256(b"requirement:test\nartifact:filing\n").hexdigest()[:24]
    assert result["assessment_id"] == f"industry_evidence_assessment:{expected}"
    assert result["assessment_summary"] == "Direct filing evidence."
    assert (target, artifact, document, originals[4]) == (originals[1], originals[2], originals[3], originals[4])
    assert target["claim_status"] == "hypothesis" and target["confidence"] == 0.2

    bad_requirement = {**_requirement(), "target_type": "company_capture"}
    with pytest.raises(ResearchProjectV2Error) as exc:
        build_industry_evidence_assessment(requirement=bad_requirement, target={"target_type": "company_capture", "target_id": "claim:test"}, artifact=artifact, normalized_document=document, locator="", evidence_role="supports", assessment_summary="x", directness="direct", strength="strong", independence="independent", freshness="fresh", scope_match="full", conflict_status="none", provenance=_provenance())
    assert exc.value.code == "RESEARCH_PROJECT_V2_1_EVIDENCE_ASSESSMENT_INVALID"

def test_build_assessment_rejects_dangling_document_and_locator() -> None:
    artifact = _artifact("artifact:a", "a" * 64, publisher_family="issuer")
    document = _document("artifact:other")
    kwargs = dict(requirement=_requirement(), target={"target_type": "research_claim", "target_id": "claim:test"}, artifact=artifact, normalized_document=document, locator="missing", evidence_role="supports", assessment_summary="x", directness="direct", strength="strong", independence="independent", freshness="fresh", scope_match="full", conflict_status="none", provenance=_provenance())
    with pytest.raises(ResearchProjectV2Error) as exc:
        build_industry_evidence_assessment(**kwargs)
    assert exc.value.code == "RESEARCH_PROJECT_V2_1_EVIDENCE_ASSESSMENT_INVALID"


def test_build_assessment_requires_canonical_requirement_and_target_identity() -> None:
    artifact = _artifact("artifact:canonical", "a" * 64, publisher_family="issuer")
    document = _document(artifact["artifact_id"])
    common = dict(
        artifact=artifact,
        normalized_document=document,
        locator="section:1",
        evidence_role="supports",
        assessment_summary="evidence",
        directness="direct",
        strength="strong",
        independence="independent",
        freshness="fresh",
        scope_match="full",
        conflict_status="none",
        provenance=_provenance(),
    )
    with pytest.raises(ResearchProjectV2Error) as exc:
        build_industry_evidence_assessment(
            requirement={
                "requirement_id": "requirement:test",
                "target_type": "research_claim",
                "target_id": "claim:test",
            },
            target=_claim(),
            **common,
        )
    assert exc.value.code == "RESEARCH_PROJECT_V2_1_EVIDENCE_ASSESSMENT_INVALID"

    spoofed = {
        **_claim("claim:actual"),
        "target_type": "research_claim",
        "target_id": "claim:claimed",
    }
    requirement = {**_requirement(), "target_id": "claim:claimed"}
    with pytest.raises(ResearchProjectV2Error) as exc:
        build_industry_evidence_assessment(
            requirement=requirement, target=spoofed, **common
        )
    assert exc.value.code == "RESEARCH_PROJECT_V2_1_EVIDENCE_ASSESSMENT_INVALID"


def test_build_assessment_rejects_partial_research_project_target() -> None:
    artifact = _artifact("artifact:project-target", "a" * 64, publisher_family="issuer")
    requirement = {
        **_requirement(),
        "target_type": "research_project",
        "target_id": "research_project:test",
    }
    with pytest.raises(ResearchProjectV2Error) as exc:
        build_industry_evidence_assessment(
            requirement=requirement,
            target={"project_id": "research_project:test"},
            artifact=artifact,
            normalized_document=_document(artifact["artifact_id"]),
            locator="section:1",
            evidence_role="supports",
            assessment_summary="evidence",
            directness="direct",
            strength="strong",
            independence="independent",
            freshness="fresh",
            scope_match="full",
            conflict_status="none",
            provenance=_provenance(),
        )
    assert exc.value.code == "RESEARCH_PROJECT_V2_1_EVIDENCE_ASSESSMENT_INVALID"


def test_conflicts_use_reviewed_collapsed_source_families_and_pending_is_ignored() -> None:
    filing = _artifact("artifact:filing", "a" * 64, publisher_family="issuer")
    standard = _artifact("artifact:standard", "b" * 64, publisher_family="association")
    mirror = _artifact("artifact:mirror", "c" * 64, publisher_family="issuer")
    pending = _assessment(mirror, role="opposes", reviewed=False)
    assessments = [_assessment(filing, role="supports"), _assessment(standard, role="opposes"), pending]
    relationships = [assess_source_relationship(filing, standard), assess_source_relationship(filing, mirror)]
    summaries = build_conflict_summaries(assessments, artifacts=[filing, standard, mirror], source_relationships=relationships, assessed_at="2026-07-18T10:00:00Z", provenance=_provenance())
    assert len(summaries) == 1
    assert summaries[0]["conflict_status"] == "material_conflict"
    assert summaries[0]["supporting_source_count"] == 1
    assert summaries[0]["opposing_source_count"] == 1
    assert pending["assessment_id"] not in summaries[0]["assessment_ids"]


def test_independent_coverage_collapses_mirrors_and_duplicate_artifact_roles() -> None:
    source = _artifact("artifact:source", "a" * 64, publisher_family="issuer")
    mirror = _artifact("artifact:mirror", "b" * 64, publisher_family="issuer")
    assessments = [_assessment(source, role="supports"), _assessment(source, role="quantifies", locator="section:2"), _assessment(mirror, role="supports")]
    assert count_independent_coverage([row["assessment_id"] for row in assessments], assessments=assessments, artifacts=[source, mirror], source_relationships=[]) == 1


def test_unknown_sources_never_inflate_coverage_or_material_conflict() -> None:
    left = _artifact("artifact:unknown-a", "a" * 64, publisher_family=None)
    right = _artifact("artifact:unknown-b", "b" * 64, publisher_family=None)
    assessments = [
        _assessment(left, role="supports"),
        _assessment(right, role="opposes"),
        _assessment(right, role="quantifies", locator="section:2"),
    ]
    ids = [row["assessment_id"] for row in assessments]
    assert count_independent_coverage(
        ids,
        assessments=assessments,
        artifacts=[left, right],
        source_relationships=[],
    ) == 1
    summary = build_conflict_summaries(
        assessments,
        artifacts=[left, right],
        source_relationships=[],
        assessed_at="2026-07-18T10:00:00Z",
        provenance=_provenance(),
    )[0]
    assert summary["conflict_status"] == "limited"
    assert summary["independent_source_family_count"] == 1
    assert "Independent" not in summary["summary"]


@pytest.mark.parametrize(
    ("role", "count_field"),
    [
        ("supports", "supporting_source_count"),
        ("opposes", "opposing_source_count"),
        ("quantifies", "quantitative_source_count"),
    ],
)
@pytest.mark.parametrize(
    ("mode", "expected_count"),
    [("unknown", 1), ("explicit_independent", 2), ("same_publisher", 1)],
)
def test_conflict_role_counts_are_conservative(
    role: str, count_field: str, mode: str, expected_count: int
) -> None:
    publisher_left = "shared" if mode == "same_publisher" else None
    publisher_right = "shared" if mode == "same_publisher" else None
    left = _artifact(
        f"artifact:{mode}:{role}:a",
        "a" * 64,
        publisher_family=publisher_left,
    )
    right = _artifact(
        f"artifact:{mode}:{role}:b",
        "b" * 64,
        publisher_family=publisher_right,
    )
    relationships = []
    if mode == "explicit_independent":
        relationships = [
            {
                "left_artifact_id": left["artifact_id"],
                "right_artifact_id": right["artifact_id"],
                "relationship": "independent",
                "reasons": ["independence manually confirmed"],
            }
        ]
    summary = build_conflict_summaries(
        [_assessment(left, role=role), _assessment(right, role=role)],
        artifacts=[left, right],
        source_relationships=relationships,
        assessed_at="2026-07-18T10:00:00Z",
        provenance=_provenance(),
    )[0]
    assert summary[count_field] == expected_count


def test_total_independent_count_is_not_smaller_than_role_subset_count() -> None:
    artifacts = [
        _artifact(f"artifact:{name}", digest * 64, publisher_family=None)
        for name, digest in zip("abcd", "abcd", strict=True)
    ]
    assessments = [
        _assessment(artifacts[0], role="quantifies"),
        *[_assessment(artifact, role="supports") for artifact in artifacts[1:]],
    ]
    relationships = [
        {
            "left_artifact_id": artifacts[left]["artifact_id"],
            "right_artifact_id": artifacts[right]["artifact_id"],
            "relationship": "independent",
            "reasons": ["independence manually confirmed"],
        }
        for left, right in [(0, 1), (1, 2), (1, 3), (2, 3)]
    ]
    summary = build_conflict_summaries(
        assessments,
        artifacts=artifacts,
        source_relationships=relationships,
        assessed_at="2026-07-18T10:00:00Z",
        provenance=_provenance(),
    )[0]
    assert summary["supporting_source_count"] == 3
    assert summary["independent_source_family_count"] >= summary["supporting_source_count"]


def test_dependency_transitivity_downgrades_weak_auto_independence() -> None:
    left = _artifact("artifact:left", "a" * 64, publisher_family="publisher:x")
    bridge = _artifact("artifact:bridge", "a" * 64, publisher_family="publisher:y")
    right = _artifact("artifact:right", "b" * 64, publisher_family="publisher:y")
    assessments = [_assessment(left, role="supports"), _assessment(right, role="supports")]
    assert count_independent_coverage(
        [row["assessment_id"] for row in assessments],
        assessments=assessments,
        artifacts=[left, bridge, right],
        source_relationships=[],
    ) == 1


def test_explicit_independent_enriches_auto_unknown() -> None:
    left = _artifact("artifact:explicit-a", "a" * 64, publisher_family=None)
    right = _artifact("artifact:explicit-b", "b" * 64, publisher_family=None)
    assessments = [_assessment(left, role="supports"), _assessment(right, role="opposes")]
    relationship = {
        "left_artifact_id": left["artifact_id"],
        "right_artifact_id": right["artifact_id"],
        "relationship": "independent",
        "reasons": ["independence was manually confirmed"],
    }
    assert count_independent_coverage(
        [row["assessment_id"] for row in assessments],
        assessments=assessments,
        artifacts=[left, right],
        source_relationships=[relationship],
    ) == 2
    summary = build_conflict_summaries(
        assessments,
        artifacts=[left, right],
        source_relationships=[relationship],
        assessed_at="2026-07-18T10:00:00Z",
        provenance=_provenance(),
    )[0]
    assert summary["conflict_status"] == "material_conflict"


def test_explicit_unknown_vetoes_publisher_independence_inference() -> None:
    left = _artifact("artifact:veto-a", "a" * 64, publisher_family="publisher:a")
    right = _artifact("artifact:veto-b", "b" * 64, publisher_family="publisher:b")
    assessments = [_assessment(left, role="supports"), _assessment(right, role="opposes")]
    relationship = {
        "left_artifact_id": left["artifact_id"],
        "right_artifact_id": right["artifact_id"],
        "relationship": "unknown",
        "reasons": ["publisher provenance is insufficient for confirmation"],
    }
    ids = [row["assessment_id"] for row in assessments]
    assert count_independent_coverage(
        ids,
        assessments=assessments,
        artifacts=[left, right],
        source_relationships=[relationship],
    ) == 1
    summary = build_conflict_summaries(
        assessments,
        artifacts=[left, right],
        source_relationships=[relationship],
        assessed_at="2026-07-18T10:00:00Z",
        provenance=_provenance(),
    )[0]
    assert summary["conflict_status"] == "limited"


def test_explicit_independent_rejects_objective_dependency_evidence() -> None:
    left = _artifact("artifact:objective-a", "a" * 64, publisher_family="left")
    right = _artifact("artifact:objective-b", "a" * 64, publisher_family="right")
    relationship = {
        "left_artifact_id": left["artifact_id"],
        "right_artifact_id": right["artifact_id"],
        "relationship": "independent",
        "reasons": ["incorrect manual classification"],
    }
    with pytest.raises(ResearchProjectV2Error) as exc:
        validate_industry_evidence_assessments(
            [], artifacts=[left, right], source_relationships=[relationship]
        )
    assert exc.value.code == "RESEARCH_PROJECT_V2_1_EVIDENCE_ASSESSMENT_INVALID"


def test_relationship_integrity_rejects_self_and_duplicate_pairs() -> None:
    artifact = _artifact("artifact:self", "a" * 64, publisher_family="publisher")
    with pytest.raises(ResearchProjectV2Error):
        assess_source_relationship(artifact, artifact)

    other = _artifact("artifact:other", "b" * 64, publisher_family="other")
    relationship = assess_source_relationship(artifact, other)
    reverse = {
        **relationship,
        "left_artifact_id": relationship["right_artifact_id"],
        "right_artifact_id": relationship["left_artifact_id"],
    }
    with pytest.raises(ResearchProjectV2Error) as exc:
        validate_industry_evidence_assessments(
            [], artifacts=[artifact, other], source_relationships=[relationship, reverse]
        )
    assert exc.value.code == "RESEARCH_PROJECT_V2_1_EVIDENCE_ASSESSMENT_INVALID"


@pytest.mark.parametrize(
    ("relationship", "left_overrides", "right_overrides"),
    [
        ("same_document", {}, {"content_sha256": "a" * 64}),
        (
            "republication",
            {"section_hashes": ["1" * 64, "2" * 64, "3" * 64, "4" * 64]},
            {"section_hashes": ["1" * 64, "2" * 64, "3" * 64, "4" * 64, "5" * 64]},
        ),
        (
            "shared_upstream_source",
            {"upstream_source_id": "upstream:shared"},
            {"upstream_source_id": "upstream:shared"},
        ),
        (
            "same_publisher_family",
            {"publisher_family": "publisher:shared"},
            {"publisher_family": "publisher:shared"},
        ),
    ],
)
def test_explicit_collapsing_relationship_accepts_objective_invariant(
    relationship: str, left_overrides: dict, right_overrides: dict
) -> None:
    left = _artifact("artifact:valid-left", "a" * 64, publisher_family="left")
    right_digest = "b" * 64 if relationship != "same_document" else "a" * 64
    right = _artifact("artifact:valid-right", right_digest, publisher_family="right")
    left.update(left_overrides)
    right.update(right_overrides)
    row = {
        "left_artifact_id": left["artifact_id"],
        "right_artifact_id": right["artifact_id"],
        "relationship": relationship,
        "reasons": ["objective invariant confirmed"],
    }
    validate_industry_evidence_assessments(
        [], artifacts=[left, right], source_relationships=[row]
    )


@pytest.mark.parametrize(
    ("relationship", "left_overrides", "right_overrides"),
    [
        ("same_document", {}, {}),
        (
            "republication",
            {"content_sha256": "a" * 64, "section_hashes": ["1" * 64]},
            {"content_sha256": "a" * 64, "section_hashes": ["1" * 64]},
        ),
        (
            "republication",
            {"section_hashes": ["1" * 64]},
            {"section_hashes": ["2" * 64]},
        ),
        (
            "shared_upstream_source",
            {"upstream_source_id": "upstream:left"},
            {"upstream_source_id": "upstream:right"},
        ),
        (
            "shared_upstream_source",
            {"upstream_source_id": None},
            {"upstream_source_id": None},
        ),
        (
            "same_publisher_family",
            {"publisher_family": "publisher:left"},
            {"publisher_family": "publisher:right"},
        ),
        (
            "same_publisher_family",
            {"publisher_family": None},
            {"publisher_family": None},
        ),
    ],
)
def test_explicit_collapsing_relationship_rejects_false_invariant_before_union(
    relationship: str, left_overrides: dict, right_overrides: dict
) -> None:
    left = _artifact("artifact:invalid-left", "a" * 64, publisher_family="left")
    right = _artifact("artifact:invalid-right", "b" * 64, publisher_family="right")
    left.update(left_overrides)
    right.update(right_overrides)
    for artifact in (left, right):
        digest = artifact["content_sha256"]
        artifact["raw_path"] = f"evidence/raw/{digest[:2]}/{digest}.txt"
    row = {
        "left_artifact_id": left["artifact_id"],
        "right_artifact_id": right["artifact_id"],
        "relationship": relationship,
        "reasons": ["false explicit classification"],
    }
    with pytest.raises(ResearchProjectV2Error) as exc:
        validate_industry_evidence_assessments(
            [], artifacts=[left, right], source_relationships=[row]
        )
    assert exc.value.code == "RESEARCH_PROJECT_V2_1_EVIDENCE_RELATIONSHIP_INVALID"
    assert exc.value.details["pair"] == sorted(
        [left["artifact_id"], right["artifact_id"]]
    )
    assert exc.value.details["expected_invariant"]
    assert "actual" in exc.value.details


def test_relationship_indexing_does_not_call_public_pair_assessor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifacts = [
        _artifact(
            f"artifact:scale-{index}",
            f"{index + 1:064x}",
            publisher_family=f"publisher:{index}",
        )
        for index in range(100)
    ]

    def forbidden(*args, **kwargs):
        raise AssertionError("public pair assessor must not be used by indexing")

    original_validate = evidence_module.validate_v2_1_schema_payload
    artifact_validations = 0

    def count_validations(schema_name, payload, **kwargs):
        nonlocal artifact_validations
        if schema_name == "evidence_artifact_v2_1":
            artifact_validations += 1
        return original_validate(schema_name, payload, **kwargs)

    monkeypatch.setattr(evidence_module, "assess_source_relationship", forbidden)
    monkeypatch.setattr(
        evidence_module, "validate_v2_1_schema_payload", count_validations
    )
    validate_industry_evidence_assessments(
        [], artifacts=artifacts, source_relationships=[]
    )
    assert artifact_validations == len(artifacts)


def test_write_assessment_is_canonical_hashed_idempotent_and_immutable(tmp_path: Path) -> None:
    layout = LayeredResearchLayout(tmp_path / "v2_1")
    artifact = _artifact("artifact:a", "a" * 64, publisher_family="issuer")
    assessment = _assessment(artifact, role="supports", reviewed=False)
    with ThreadPoolExecutor(max_workers=4) as pool:
        paths = list(pool.map(lambda _: write_industry_evidence_assessment(assessment, layout=layout), range(8)))
    assert len(set(paths)) == 1
    wrapper = json.loads(paths[0].read_text())
    assert paths[0].read_bytes() == canonical_bytes(wrapper)
    assert wrapper["content_hash"] == content_sha256(wrapper, excluded_paths={("content_hash",)})
    assert set(wrapper) == {"schema_version", "artifact_kind", "industry_evidence_assessment", "content_hash"}
    changed = deepcopy(assessment)
    changed["assessment_summary"] = "changed"
    with pytest.raises(ResearchProjectV2Error) as exc:
        write_industry_evidence_assessment(changed, layout=layout)
    assert exc.value.code == "RESEARCH_PROJECT_V2_1_IMMUTABILITY_VIOLATION"


def test_writer_detects_replacement_during_last_live_read(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    layout = LayeredResearchLayout(tmp_path / "v2_1")
    artifact = _artifact("artifact:race", "a" * 64, publisher_family="issuer")
    assessment = _assessment(artifact, role="supports", reviewed=False)
    final = layout.evidence_assessments_dir / f"{assessment['assessment_id']}.json"
    original_read = evidence_module._read_fd
    calls = 0

    def replace_after_live_read(descriptor: int) -> bytes:
        nonlocal calls
        calls += 1
        data = original_read(descriptor)
        if calls == 3:
            final.rename(final.with_suffix(".old"))
            final.write_bytes(b"replacement")
            final.chmod(0o600)
        return data

    monkeypatch.setattr(evidence_module, "_read_fd", replace_after_live_read)
    with pytest.raises(ResearchProjectV2Error):
        write_industry_evidence_assessment(assessment, layout=layout)
    assert final.read_bytes() == b"replacement"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"assessments": [[]], "artifacts": [], "source_relationships": []},
        {"assessments": [], "artifacts": None, "source_relationships": []},
        {"assessments": [], "artifacts": [], "source_relationships": None},
    ],
)
def test_coverage_rejects_malformed_collections_stably(kwargs) -> None:
    with pytest.raises(ResearchProjectV2Error) as exc:
        count_independent_coverage([], **kwargs)
    assert exc.value.code == "RESEARCH_PROJECT_V2_1_EVIDENCE_ASSESSMENT_INVALID"


def test_writer_opens_existing_final_nonblocking(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    layout = LayeredResearchLayout(tmp_path / "v2_1")
    artifact = _artifact("artifact:nonblock", "a" * 64, publisher_family="issuer")
    assessment = _assessment(artifact, role="supports", reviewed=False)
    write_industry_evidence_assessment(assessment, layout=layout)
    original_open = evidence_module.os.open
    checked = False

    def require_nonblocking(path, flags, *args, **kwargs):
        nonlocal checked
        if path == f"{assessment['assessment_id']}.json":
            checked = True
            assert flags & os.O_NONBLOCK
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(evidence_module.os, "open", require_nonblocking)
    write_industry_evidence_assessment(assessment, layout=layout)
    assert checked


def test_writer_preserves_primary_error_and_reports_retire_cleanup_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    layout = LayeredResearchLayout(tmp_path / "v2_1")
    artifact = _artifact("artifact:cleanup-primary", "a" * 64, publisher_family="issuer")
    assessment = _assessment(artifact, role="supports", reviewed=False)
    write_industry_evidence_assessment(assessment, layout=layout)
    changed = deepcopy(assessment)
    changed["assessment_summary"] = "immutable conflict"

    def fail_retire(*args, **kwargs):
        raise OSError("retire cleanup failed")

    monkeypatch.setattr(evidence_module, "_retire_temporary", fail_retire)
    with pytest.raises(ResearchProjectV2Error) as exc:
        write_industry_evidence_assessment(changed, layout=layout)
    assert exc.value.code == "RESEARCH_PROJECT_V2_1_IMMUTABILITY_VIOLATION"
    assert exc.value.details["cleanup_errors"]
    assert any("cleanup" in note.lower() for note in exc.value.__notes__)


def test_writer_reports_pure_retire_cleanup_failure_as_storage_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    layout = LayeredResearchLayout(tmp_path / "v2_1")
    artifact = _artifact("artifact:cleanup-only", "a" * 64, publisher_family="issuer")
    assessment = _assessment(artifact, role="supports", reviewed=False)

    def fail_retire(*args, **kwargs):
        raise OSError("retire cleanup failed")

    monkeypatch.setattr(evidence_module, "_retire_temporary", fail_retire)
    with pytest.raises(ResearchProjectV2Error) as exc:
        write_industry_evidence_assessment(assessment, layout=layout)
    assert exc.value.code == "RESEARCH_PROJECT_V2_1_EVIDENCE_STORAGE_FAILED"
    assert exc.value.details["cleanup_errors"]
    assert exc.value.__cause__ is not None


def test_writer_continues_closing_live_descriptors_after_close_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    layout = LayeredResearchLayout(tmp_path / "v2_1")
    artifact = _artifact("artifact:close-loop", "a" * 64, publisher_family="issuer")
    assessment = _assessment(artifact, role="supports", reviewed=False)
    original_open_directory = evidence_module._open_directory
    original_close = evidence_module.os.close
    open_calls = 0
    live_descriptors: list[int] = []
    close_attempts: list[int] = []

    def capture_live(path):
        nonlocal open_calls, live_descriptors
        open_calls += 1
        result = original_open_directory(path)
        if open_calls == 2:
            live_descriptors = list(result[0])
        return result

    def fail_first_live_close(descriptor):
        close_attempts.append(descriptor)
        if live_descriptors and descriptor == live_descriptors[-1]:
            raise OSError("live close failed")
        return original_close(descriptor)

    monkeypatch.setattr(evidence_module, "_open_directory", capture_live)
    monkeypatch.setattr(evidence_module.os, "close", fail_first_live_close)
    with pytest.raises(ResearchProjectV2Error) as exc:
        write_industry_evidence_assessment(assessment, layout=layout)
    assert exc.value.code == "RESEARCH_PROJECT_V2_1_EVIDENCE_STORAGE_FAILED"
    assert exc.value.details["cleanup_errors"]
    assert live_descriptors[-2] in close_attempts
