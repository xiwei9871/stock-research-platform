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
        "minimum_coverage": minimum_coverage,
    }


def _assessment(
    artifact: dict, *, role: str, reviewed: bool = True, locator: str = "section:1"
) -> dict:
    document = _document(artifact["artifact_id"], locator=locator)
    result = build_industry_evidence_assessment(
        requirement=_requirement(),
        target={"target_type": "research_claim", "target_id": "claim:test", "claim_status": "draft", "confidence": 0.2},
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
    target = {"target_type": "research_claim", "target_id": "claim:test", "claim_status": "draft", "confidence": 0.2}
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
    assert target["claim_status"] == "draft" and target["confidence"] == 0.2

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
