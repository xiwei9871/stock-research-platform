from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import shutil

import pytest

from stock_research.research_project_v2.canonical import content_sha256
from stock_research.research_project_v2.errors import ResearchProjectV2Error
from stock_research.research_project_v2_1.layout import LayeredResearchLayout
from stock_research.research_project_v2_1.loader import (
    list_layered_project_slugs,
    list_layered_versions,
    load_industry_version,
    load_layered_index,
    load_layered_project,
    resolve_upstream_r1_version,
)
from stock_research.research_project_v2_1.semantic import (
    R2A_SNAPSHOT_FIELDS,
    common_r1_projection,
    validate_industry_version_semantics,
)


CREATED_AT = "2026-07-18T10:00:00+08:00"
PROVENANCE = {
    "created_by": "fixture-author",
    "actor_type": "human",
    "agent_run_id": None,
    "created_at": "2026-07-18T02:00:00Z",
    "created_in_version": "research_version:fixture-industry:0.1.0",
    "review_status": "unreviewed",
}


def _identity(slug: str = "fixture-industry", version: str = "0.1.0") -> dict[str, object]:
    return {
        "schema_version": "2.1.0",
        "artifact_kind": "research_project_identity",
        "project_id": f"research_project:{slug}",
        "project_slug": slug,
        "title": "Fixture industry project",
        "purpose": "Validate layered loading.",
        "research_layer": "industry_research",
        "created_at": CREATED_AT,
        "created_by": "fixture-author",
        "current_lifecycle_state": "research_ready",
        "current_version": f"research_version:{slug}:{version}",
        "latest_reviewed_version": None,
        "latest_published_version": None,
    }


def _scope() -> dict[str, object]:
    return {
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
    }


def _router() -> dict[str, object]:
    return {
        "primary_method": "system_architecture",
        "secondary_methods": [],
        "routing_reasons": ["System dependencies drive outcomes"],
        "required_research_modules": ["architecture"],
        "excluded_modules": ["company_capture"],
        "confidence": 0.8,
        "manual_override": False,
        "override_reason": None,
        "decided_by": "fixture-author",
        "decided_at": CREATED_AT,
    }


def _snapshot() -> dict[str, object]:
    return {
        "research_layer": "industry_research",
        "project_lifecycle_state": "research_ready",
        "evidence_stage": "requirements_defined",
        "conclusion_status": "unavailable",
        "investment_status": "not_assessed",
        "scope": _scope(),
        "router_decision": _router(),
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
    }


def _version(slug: str = "fixture-industry", semantic_version: str = "0.1.0") -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": "2.1.0",
        "artifact_kind": "industry_research_version",
        "version_id": f"research_version:{slug}:{semantic_version}",
        "project_id": f"research_project:{slug}",
        "semantic_version": semantic_version,
        "parent_version_id": None,
        "creation_stage": "research_design",
        "created_at": CREATED_AT,
        "created_by": "fixture-author",
        "change_summary": "Create the initial industry research design.",
        "change_reason": "Initialize the layered fixture.",
        "incorporated_event_ids": [],
        "content_hash": "0" * 64,
        "snapshot": _snapshot(),
    }
    payload["content_hash"] = content_sha256(payload, excluded_paths={("content_hash",)})
    return payload


def _manifest_row(version: dict[str, object]) -> dict[str, object]:
    semantic_version = str(version["semantic_version"])
    return {
        "version_id": version["version_id"],
        "semantic_version": semantic_version,
        "parent_version_id": version["parent_version_id"],
        "relative_path": f"versions/v{semantic_version}.json",
        "content_hash": version["content_hash"],
        "created_at": version["created_at"],
    }


def _index(slug: str = "fixture-industry") -> dict[str, object]:
    return {
        "schema_version": "2.1.0",
        "artifact_kind": "research_project_index",
        "generated_at": CREATED_AT,
        "projects": [
            {
                "project_id": f"research_project:{slug}",
                "project_slug": slug,
                "title": "Fixture industry project",
                "research_layer": "industry_research",
                "current_lifecycle_state": "research_ready",
                "evidence_stage": "requirements_defined",
                "conclusion_status": "unavailable",
                "current_version": f"research_version:{slug}:0.1.0",
                "latest_reviewed_version": None,
                "latest_published_version": None,
                "relative_path": f"projects/{slug}/project.json",
            }
        ],
    }


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def _install_version(layout: LayeredResearchLayout, version: dict[str, object]) -> None:
    slug = str(version["project_id"]).removeprefix("research_project:")
    semantic_version = str(version["semantic_version"])
    _write_json(layout.project_dir(slug) / f"versions/v{semantic_version}.json", version)


@pytest.fixture
def layered_layout(tmp_path: Path) -> LayeredResearchLayout:
    layout = LayeredResearchLayout(tmp_path / "v2_1")
    shutil.copytree(LayeredResearchLayout.default().schema_dir, layout.schema_dir)
    identity = _identity()
    version = _version()
    _write_json(layout.project_dir("fixture-industry") / "project.json", identity)
    _install_version(layout, version)
    _write_jsonl(layout.project_dir("fixture-industry") / "version_manifest.jsonl", [_manifest_row(version)])
    _write_json(layout.index_path, _index())
    return layout


def _assert_code(exc_info: pytest.ExceptionInfo[ResearchProjectV2Error], code: str) -> None:
    assert exc_info.value.code == code
    assert exc_info.value.code.startswith("RESEARCH_PROJECT_V2_1_")


def test_list_layered_project_slugs_is_sorted_safe_and_does_not_cross_scan_r1(
    layered_layout: LayeredResearchLayout,
) -> None:
    for slug in ["zeta", "alpha"]:
        _write_json(layered_layout.project_dir(slug) / "project.json", _identity(slug))
    (layered_layout.projects_dir / "bad.slug").mkdir()
    (layered_layout.projects_dir / "plain-file").write_text("x", encoding="utf-8")
    outside = layered_layout.root.parent / "outside-project"
    _write_json(outside / "project.json", _identity("outside-project"))
    (layered_layout.projects_dir / "linked").symlink_to(outside, target_is_directory=True)
    r1_only = layered_layout.root.parent / "v2/projects/r1-only"
    _write_json(r1_only / "project.json", _identity("r1-only"))

    assert list_layered_project_slugs(layout=layered_layout) == [
        "alpha",
        "fixture-industry",
        "zeta",
    ]


def test_list_layered_project_slugs_returns_empty_when_projects_missing(tmp_path: Path) -> None:
    assert list_layered_project_slugs(layout=LayeredResearchLayout(tmp_path / "empty")) == []


def test_load_identity_current_explicit_versions_and_semver_sorting(
    layered_layout: LayeredResearchLayout,
) -> None:
    versions = [_version(semantic_version=value) for value in ["1.0.0", "0.10.0", "0.2.0"]]
    for version in versions:
        _install_version(layered_layout, version)
    rows = [_manifest_row(_version()), *[_manifest_row(version) for version in versions]]
    _write_jsonl(layered_layout.project_dir("fixture-industry") / "version_manifest.jsonl", rows)

    assert load_layered_project("fixture-industry", layout=layered_layout)["project_id"] == "research_project:fixture-industry"
    assert load_industry_version("fixture-industry", layout=layered_layout)["semantic_version"] == "0.1.0"
    assert load_industry_version("fixture-industry", "1.0.0", layout=layered_layout)["semantic_version"] == "1.0.0"
    assert list_layered_versions("fixture-industry", layout=layered_layout) == [
        "0.1.0",
        "0.2.0",
        "0.10.0",
        "1.0.0",
    ]


@pytest.mark.parametrize("slug", ["../fixture-industry", "/tmp/fixture-industry", "bad.slug"])
def test_project_slug_traversal_absolute_and_invalid_are_rejected(
    layered_layout: LayeredResearchLayout, slug: str
) -> None:
    with pytest.raises(ResearchProjectV2Error) as exc_info:
        load_layered_project(slug, layout=layered_layout)
    _assert_code(exc_info, "RESEARCH_PROJECT_V2_1_PROJECT_NOT_FOUND")


@pytest.mark.parametrize("version", ["../0.1.0", "/tmp/0.1.0", "01.0.0", "v0.1.0"])
def test_semver_traversal_absolute_and_invalid_are_rejected(
    layered_layout: LayeredResearchLayout, version: str
) -> None:
    with pytest.raises(ResearchProjectV2Error) as exc_info:
        load_industry_version("fixture-industry", version, layout=layered_layout)
    _assert_code(exc_info, "RESEARCH_PROJECT_V2_1_VERSION_NOT_FOUND")


@pytest.mark.parametrize("target", ["project", "versions", "version", "manifest"])
def test_symlinked_managed_paths_are_rejected(
    layered_layout: LayeredResearchLayout, tmp_path: Path, target: str
) -> None:
    project_dir = layered_layout.project_dir("fixture-industry")
    outside = tmp_path / f"outside-{target}"
    if target == "project":
        project_dir.rename(outside)
        project_dir.symlink_to(outside, target_is_directory=True)
        action = lambda: load_layered_project("fixture-industry", layout=layered_layout)
    elif target == "versions":
        versions = project_dir / "versions"
        versions.rename(outside)
        versions.symlink_to(outside, target_is_directory=True)
        action = lambda: load_industry_version("fixture-industry", layout=layered_layout)
    else:
        name = "versions/v0.1.0.json" if target == "version" else "version_manifest.jsonl"
        path = project_dir / name
        path.rename(outside)
        path.symlink_to(outside)
        action = lambda: load_industry_version("fixture-industry", layout=layered_layout)

    with pytest.raises(ResearchProjectV2Error) as exc_info:
        action()
    assert exc_info.value.code.startswith("RESEARCH_PROJECT_V2_1_")


@pytest.mark.parametrize("kind", ["missing", "array", "broken"])
def test_json_storage_and_read_failures_have_stable_errors(
    layered_layout: LayeredResearchLayout, kind: str
) -> None:
    path = layered_layout.project_dir("fixture-industry") / "project.json"
    if kind == "missing":
        path.unlink()
        expected = "RESEARCH_PROJECT_V2_1_PROJECT_NOT_FOUND"
    elif kind == "array":
        path.write_text("[]", encoding="utf-8")
        expected = "RESEARCH_PROJECT_V2_1_READ_ERROR"
    else:
        path.write_text("{", encoding="utf-8")
        expected = "RESEARCH_PROJECT_V2_1_READ_ERROR"
    with pytest.raises(ResearchProjectV2Error) as exc_info:
        load_layered_project("fixture-industry", layout=layered_layout)
    _assert_code(exc_info, expected)


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        (lambda version, row: version.update(content_hash="f" * 64), "embedded content_hash mismatch"),
        (lambda version, row: row.update(version_id="wrong"), "manifest version_id mismatch"),
        (lambda version, row: row.update(relative_path="wrong"), "manifest relative_path mismatch"),
        (lambda version, row: row.update(created_at="2020-01-01T00:00:00Z"), "manifest created_at mismatch"),
        (lambda version, row: row.update(extra="forbidden"), "manifest fields mismatch"),
        (lambda version, row: row.pop("content_hash"), "manifest fields mismatch"),
    ],
)
def test_content_hash_and_exact_manifest_row_are_verified(
    layered_layout: LayeredResearchLayout, mutation, reason: str
) -> None:
    version = _version()
    row = _manifest_row(version)
    mutation(version, row)
    _write_json(layered_layout.project_dir("fixture-industry") / "versions/v0.1.0.json", version)
    _write_jsonl(layered_layout.project_dir("fixture-industry") / "version_manifest.jsonl", [row])

    with pytest.raises(ResearchProjectV2Error) as exc_info:
        load_industry_version("fixture-industry", layout=layered_layout)
    _assert_code(exc_info, "RESEARCH_PROJECT_V2_1_IMMUTABILITY_VIOLATION")
    assert reason in str(exc_info.value.details["reason"])


@pytest.mark.parametrize("rows", [[], None])
def test_manifest_requires_exactly_one_matching_row(
    layered_layout: LayeredResearchLayout, rows: list[dict[str, object]] | None
) -> None:
    row = _manifest_row(_version())
    actual_rows = [row, deepcopy(row)] if rows is None else rows
    _write_jsonl(layered_layout.project_dir("fixture-industry") / "version_manifest.jsonl", actual_rows)
    with pytest.raises(ResearchProjectV2Error) as exc_info:
        load_industry_version("fixture-industry", layout=layered_layout)
    _assert_code(exc_info, "RESEARCH_PROJECT_V2_1_IMMUTABILITY_VIOLATION")


@pytest.mark.parametrize(
    "mutation",
    [
        lambda row: row.update(extra="forbidden"),
        lambda row: row.pop("content_hash"),
    ],
)
def test_every_manifest_row_requires_exact_fields_even_for_other_versions(
    layered_layout: LayeredResearchLayout, mutation
) -> None:
    target_row = _manifest_row(_version())
    other_row = _manifest_row(_version(semantic_version="9.9.9"))
    mutation(other_row)
    _write_jsonl(
        layered_layout.project_dir("fixture-industry") / "version_manifest.jsonl",
        [target_row, other_row],
    )

    with pytest.raises(ResearchProjectV2Error) as exc_info:
        load_industry_version("fixture-industry", layout=layered_layout)
    _assert_code(exc_info, "RESEARCH_PROJECT_V2_1_IMMUTABILITY_VIOLATION")
    assert "manifest fields mismatch" in str(exc_info.value.details["reason"])


def test_manifest_rejects_duplicate_rows_for_other_versions(
    layered_layout: LayeredResearchLayout,
) -> None:
    target_row = _manifest_row(_version())
    other_row = _manifest_row(_version(semantic_version="9.9.9"))
    _write_jsonl(
        layered_layout.project_dir("fixture-industry") / "version_manifest.jsonl",
        [target_row, other_row, deepcopy(other_row)],
    )

    with pytest.raises(ResearchProjectV2Error) as exc_info:
        load_industry_version("fixture-industry", layout=layered_layout)
    _assert_code(exc_info, "RESEARCH_PROJECT_V2_1_IMMUTABILITY_VIOLATION")
    assert "duplicate manifest semantic_version" in str(
        exc_info.value.details["reason"]
    )


def test_load_layered_index_validates_v2_1_schema(layered_layout: LayeredResearchLayout) -> None:
    assert load_layered_index(layout=layered_layout)["schema_version"] == "2.1.0"
    invalid = _index()
    invalid["schema_version"] = "2.0.0"
    _write_json(layered_layout.index_path, invalid)
    with pytest.raises(ResearchProjectV2Error) as exc_info:
        load_layered_index(layout=layered_layout)
    _assert_code(exc_info, "RESEARCH_PROJECT_V2_1_SCHEMA_INVALID")


def _upstream_reference(**changes: object) -> dict[str, object]:
    reference: dict[str, object] = {
        "upstream_research_ref_id": "upstream_ref:fixture",
        "upstream_research_layer": None,
        "upstream_project_id": "research_project:upstream",
        "upstream_version_id": "research_version:upstream:1.2.3",
        "upstream_object_type": "research_version",
        "upstream_object_id": None,
        "upstream_gate_result_id": None,
        "upstream_content_hash": "e" * 64,
        "referenced_at": "2026-07-18T02:00:00Z",
        "scope_note": "Use the immutable upstream version.",
    }
    reference.update(changes)
    return reference


def test_resolve_upstream_r1_version_uses_unique_project_version_and_hash(monkeypatch) -> None:
    index = {"projects": [{"project_id": "research_project:upstream", "project_slug": "upstream"}]}
    upstream = {
        "version_id": "research_version:upstream:1.2.3",
        "semantic_version": "1.2.3",
        "content_hash": "e" * 64,
    }
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr("stock_research.research_project_v2_1.loader.load_r1_index", lambda: index)
    monkeypatch.setattr(
        "stock_research.research_project_v2_1.loader.load_r1_version",
        lambda slug, version: calls.append((slug, version)) or upstream,
    )

    assert resolve_upstream_r1_version(_upstream_reference()) is upstream
    assert calls == [("upstream", "1.2.3")]


def test_resolve_upstream_can_use_monkeypatched_r1_loader_module(monkeypatch) -> None:
    index = {"projects": [{"project_id": "research_project:upstream", "project_slug": "upstream"}]}
    upstream = {
        "version_id": "research_version:upstream:1.2.3",
        "content_hash": "e" * 64,
    }
    monkeypatch.setattr(
        "stock_research.research_project_v2.loader.load_index", lambda: index
    )
    monkeypatch.setattr(
        "stock_research.research_project_v2.loader.load_version",
        lambda slug, version: upstream,
    )

    assert resolve_upstream_r1_version(_upstream_reference()) is upstream


@pytest.mark.parametrize(
    ("index_projects", "loaded", "changes", "reason"),
    [
        ([], None, {}, "project"),
        ([{"project_id": "research_project:upstream", "project_slug": "one"}, {"project_id": "research_project:upstream", "project_slug": "two"}], None, {}, "project"),
        ([{"project_id": "research_project:upstream", "project_slug": "upstream"}], ResearchProjectV2Error("missing", code="RESEARCH_PROJECT_VERSION_NOT_FOUND"), {}, "version"),
        ([{"project_id": "research_project:upstream", "project_slug": "upstream"}], {"version_id": "changed", "content_hash": "e" * 64}, {}, "version_id"),
        ([{"project_id": "research_project:upstream", "project_slug": "upstream"}], {"version_id": "research_version:upstream:1.2.3", "content_hash": "f" * 64}, {}, "content_hash"),
        ([{"project_id": "research_project:upstream", "project_slug": "upstream"}], {}, {"upstream_research_layer": "industry_research"}, "upstream_research_layer"),
    ],
)
def test_invalid_upstream_reference_is_wrapped_with_reason(
    monkeypatch, index_projects, loaded, changes, reason: str
) -> None:
    monkeypatch.setattr(
        "stock_research.research_project_v2_1.loader.load_r1_index",
        lambda: {"projects": index_projects},
    )

    def load_version(*_args):
        if isinstance(loaded, Exception):
            raise loaded
        return loaded

    monkeypatch.setattr("stock_research.research_project_v2_1.loader.load_r1_version", load_version)
    with pytest.raises(ResearchProjectV2Error) as exc_info:
        resolve_upstream_r1_version(_upstream_reference(**changes))
    _assert_code(exc_info, "RESEARCH_PROJECT_V2_1_UPSTREAM_REFERENCE_INVALID")
    assert exc_info.value.details["reference"] == "upstream_ref:fixture"
    assert reason in str(exc_info.value.details["reason"])


def _question() -> dict[str, object]:
    return {
        "question_id": "question:fixture",
        "question_type": "mechanism",
        "question_text": "Does the mechanism work?",
        "priority": 1,
        "required_for_gate": True,
        "answer_status": "unanswered",
        "linked_claim_ids": ["claim:fixture"],
        "linked_requirement_ids": ["requirement:fixture"],
        "lifecycle_status": "active",
        "provenance": PROVENANCE,
    }


def _claim() -> dict[str, object]:
    return {
        "claim_id": "claim:fixture",
        "claim_kind": "primary",
        "epistemic_type": "hypothesis",
        "claim_text": "The mechanism works.",
        "claim_status": "hypothesis",
        "lifecycle_status": "active",
        "confidence": 0.5,
        "importance": 0.8,
        "linked_question_ids": ["question:fixture"],
        "context_reference_ids": [],
        "created_in_version": "research_version:fixture-industry:0.1.0",
        "supersedes_claim_id": None,
        "validation_metric_ids": [],
        "invalidation_condition_ids": [],
        "provenance": PROVENANCE,
    }


def _requirement() -> dict[str, object]:
    return {
        "requirement_id": "requirement:fixture",
        "target_type": "research_claim",
        "target_id": "claim:fixture",
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


def _search_plan() -> dict[str, object]:
    return {
        "search_plan_id": "search_plan:fixture",
        "project_id": "research_project:fixture-industry",
        "version_id": "research_version:fixture-industry:0.1.0",
        "evidence_channel": "industry",
        "requirement_ids": ["requirement:fixture"],
        "queries": [{
            "query_id": "query:fixture",
            "query_role": "mechanism",
            "query_text": "fixture mechanism",
            "required_terms": ["fixture"],
            "excluded_terms": [],
            "source_classes": ["primary"],
            "priority": 1,
        }],
        "languages": ["en"],
        "geography": ["global"],
        "publication_window": "within_12_months",
        "result_limit_per_query": 10,
        "deduplication_policy": "normalized_url_then_content_hash",
        "stop_conditions": ["primary source found"],
        "status": "planned",
        "provenance": PROVENANCE,
    }


def _candidate() -> dict[str, object]:
    return {
        "candidate_id": "candidate:fixture",
        "search_plan_id": "search_plan:fixture",
        "query_id": "query:fixture",
        "normalized_url": "https://example.com/source.pdf",
        "original_url": "https://example.com/source.pdf",
        "title": "Fixture source",
        "snippet": "Fixture mechanism.",
        "publisher": "Fixture publisher",
        "publish_date": "2026-07-01",
        "source_class": "primary",
        "rank": 1,
        "exclusion_status": "included",
        "exclusion_reasons": [],
        "dedup_key": "https://example.com/source.pdf",
        "provenance": PROVENANCE,
    }


def _artifact(artifact_id: str = "artifact:fixture") -> dict[str, object]:
    digest = "b" * 64 if artifact_id == "artifact:fixture" else "c" * 64
    return {
        "artifact_id": artifact_id,
        "candidate_id": "candidate:fixture",
        "evidence_channel": "industry",
        "original_url": "https://example.com/source.pdf",
        "final_url": "https://example.com/source.pdf",
        "redirect_chain": [],
        "status_code": 200,
        "response_headers": {"content-type": "application/pdf"},
        "media_type": "application/pdf",
        "byte_count": 1024,
        "content_sha256": digest,
        "fetched_at": "2026-07-18T02:00:00Z",
        "raw_path": f"evidence/raw/{digest[:2]}/{digest}.pdf",
        "provenance": PROVENANCE,
        "publisher_family": None,
        "upstream_source_id": None,
        "section_hashes": [],
    }


def _document() -> dict[str, object]:
    return {
        "document_id": "document:fixture",
        "artifact_id": "artifact:fixture",
        "parser": "pdf",
        "parser_version": "1.0.0",
        "media_type": "application/pdf",
        "title": "Fixture source",
        "sections": [{
            "section_id": "section:fixture",
            "heading": "Mechanism",
            "locator": "p.1",
            "text": "The fixture mechanism works.",
            "page_start": 1,
            "page_end": 1,
            "section_hash": "d" * 64,
        }],
        "document_hash": "e" * 64,
        "parsed_at": "2026-07-18T02:00:00Z",
        "warnings": [],
        "provenance": PROVENANCE,
    }


def _assessment(assessment_id: str = "assessment:fixture") -> dict[str, object]:
    return {
        "assessment_id": assessment_id,
        "evidence_channel": "industry",
        "target_type": "research_claim",
        "target_id": "claim:fixture",
        "requirement_id": "requirement:fixture",
        "artifact_id": "artifact:fixture",
        "normalized_document_id": "document:fixture",
        "evidence_role": "supports",
        "locator": "p.1",
        "assessment_summary": "Direct evidence.",
        "directness": "direct",
        "strength": "strong",
        "independence": "independent",
        "freshness": "fresh",
        "scope_match": "full",
        "conflict_status": "none",
        "review_status": "pending_review",
        "provenance": PROVENANCE,
    }


def _conflict() -> dict[str, object]:
    return {
        "conflict_summary_id": "conflict:fixture",
        "evidence_channel": "industry",
        "target_type": "research_claim",
        "target_id": "claim:fixture",
        "conflict_status": "none",
        "supporting_source_count": 1,
        "opposing_source_count": 0,
        "quantitative_source_count": 0,
        "independent_source_family_count": 1,
        "assessment_ids": ["assessment:fixture"],
        "summary": "No material conflict.",
        "assessed_at": "2026-07-18T02:00:00Z",
        "provenance": PROVENANCE,
    }


def _semantic_version() -> dict[str, object]:
    version = _version()
    version["creation_stage"] = "evidence_snapshot"
    snapshot = version["snapshot"]
    assert isinstance(snapshot, dict)
    snapshot.update(
        questions=[_question()],
        claims=[_claim()],
        evidence_requirements=[_requirement()],
        search_plans=[_search_plan()],
        source_candidates=[_candidate()],
        evidence_artifacts=[_artifact(), _artifact("artifact:other")],
        normalized_documents=[_document()],
        industry_evidence_assessments=[_assessment()],
        source_relationships=[{
            "left_artifact_id": "artifact:fixture",
            "right_artifact_id": "artifact:other",
            "relationship": "independent",
            "reasons": ["Different content hashes"],
        }],
        conflict_summaries=[_conflict()],
    )
    return version


def test_common_projection_is_deep_copy_and_only_adapts_r1_contract(monkeypatch) -> None:
    version = _version()
    original = deepcopy(version)
    observed: list[dict[str, object]] = []
    monkeypatch.setattr(
        "stock_research.research_project_v2_1.semantic.validate_r1_version_semantics",
        lambda projected: observed.append(projected),
    )

    projected = common_r1_projection(version)

    assert version == original
    assert projected is observed[0]
    assert projected["artifact_version"] == "2.0.0"
    assert projected["schema_version"] == "2.1.0"
    projected_snapshot = projected["snapshot"]
    assert isinstance(projected_snapshot, dict)
    assert projected_snapshot["company_capture_assessments"] == []
    assert not (R2A_SNAPSHOT_FIELDS & projected_snapshot.keys())
    assert "company_capture_assessments" not in version["snapshot"]


def test_empty_industry_snapshot_passes_common_and_industry_semantics() -> None:
    version = _version()
    validate_industry_version_semantics(version)
    assert "company_capture_assessments" not in version["snapshot"]


@pytest.mark.parametrize("malformed", [{"snapshot": {}}, {"snapshot": []}])
def test_semantic_entrypoint_wraps_structural_errors(
    malformed: dict[str, object],
) -> None:
    with pytest.raises(ResearchProjectV2Error) as exc_info:
        validate_industry_version_semantics(malformed)
    _assert_code(exc_info, "RESEARCH_PROJECT_V2_1_SEMANTIC_INVALID")
    assert exc_info.value.details["exception_type"] in {
        "KeyError",
        "TypeError",
        "IndexError",
    }
    assert exc_info.value.__cause__ is not None


def test_semantic_entrypoint_preserves_existing_research_project_errors(
    monkeypatch,
) -> None:
    original = ResearchProjectV2Error(
        "existing semantic failure",
        code="RESEARCH_PROJECT_EXISTING_SEMANTIC_FAILURE",
        details={"path": "snapshot.claims"},
    )
    monkeypatch.setattr(
        "stock_research.research_project_v2_1.semantic.validate_r1_version_semantics",
        lambda _projected: (_ for _ in ()).throw(original),
    )

    with pytest.raises(ResearchProjectV2Error) as exc_info:
        validate_industry_version_semantics(_version())
    assert exc_info.value is original


def test_complete_industry_relationship_graph_passes() -> None:
    validate_industry_version_semantics(_semantic_version())


@pytest.mark.parametrize(
    ("mutate", "reason"),
    [
        (lambda s: s["search_plans"][0]["requirement_ids"].__setitem__(0, "missing"), "requirement_ids"),
        (lambda s: s["source_candidates"][0].update(search_plan_id="missing"), "search_plan_id"),
        (lambda s: s["source_candidates"][0].update(query_id="missing"), "query_id"),
        (lambda s: s["evidence_artifacts"][0].update(candidate_id="missing"), "candidate_id"),
        (lambda s: s["normalized_documents"][0].update(artifact_id="missing"), "artifact_id"),
        (lambda s: s["industry_evidence_assessments"][0].update(requirement_id="missing"), "requirement_id"),
        (lambda s: s["industry_evidence_assessments"][0].update(artifact_id="missing"), "artifact_id"),
        (lambda s: s["industry_evidence_assessments"][0].update(normalized_document_id="missing"), "normalized_document_id"),
        (lambda s: s["industry_evidence_assessments"][0].update(target_id="missing"), "target_id"),
        (lambda s: s["industry_evidence_assessments"][0].update(locator="missing"), "locator"),
        (lambda s: s["source_relationships"][0].update(left_artifact_id="missing"), "left_artifact_id"),
        (lambda s: s["source_relationships"][0].update(right_artifact_id="missing"), "right_artifact_id"),
        (lambda s: s["conflict_summaries"][0]["assessment_ids"].__setitem__(0, "missing"), "assessment_ids"),
        (lambda s: s["conflict_summaries"][0].update(target_id="missing"), "target_id"),
    ],
)
def test_dangling_industry_relationships_are_rejected(mutate, reason: str) -> None:
    version = _semantic_version()
    snapshot = version["snapshot"]
    assert isinstance(snapshot, dict)
    mutate(snapshot)
    with pytest.raises(ResearchProjectV2Error) as exc_info:
        validate_industry_version_semantics(version)
    _assert_code(exc_info, "RESEARCH_PROJECT_V2_1_SEMANTIC_INVALID")
    assert reason in str(exc_info.value.details.get("field", exc_info.value.details.get("reason", "")))


@pytest.mark.parametrize(
    ("collection", "id_field"),
    [
        ("search_plans", "search_plan_id"),
        ("source_candidates", "candidate_id"),
        ("evidence_artifacts", "artifact_id"),
        ("normalized_documents", "document_id"),
        ("industry_evidence_assessments", "assessment_id"),
        ("conflict_summaries", "conflict_summary_id"),
    ],
)
def test_duplicate_industry_ids_are_rejected(collection: str, id_field: str) -> None:
    version = _semantic_version()
    snapshot = version["snapshot"]
    assert isinstance(snapshot, dict)
    snapshot[collection].append(deepcopy(snapshot[collection][0]))
    with pytest.raises(ResearchProjectV2Error) as exc_info:
        validate_industry_version_semantics(version)
    _assert_code(exc_info, "RESEARCH_PROJECT_V2_1_SEMANTIC_INVALID")
    assert exc_info.value.details["id"] == snapshot[collection][0][id_field]


def test_duplicate_query_ids_and_upstream_reference_identity_are_rejected() -> None:
    version = _semantic_version()
    snapshot = version["snapshot"]
    assert isinstance(snapshot, dict)
    snapshot["search_plans"].append(deepcopy(snapshot["search_plans"][0]))
    snapshot["search_plans"][1]["search_plan_id"] = "search_plan:other"
    with pytest.raises(ResearchProjectV2Error) as query_exc:
        validate_industry_version_semantics(version)
    _assert_code(query_exc, "RESEARCH_PROJECT_V2_1_SEMANTIC_INVALID")

    version = _version()
    snapshot = version["snapshot"]
    assert isinstance(snapshot, dict)
    first = _upstream_reference()
    second = deepcopy(first)
    second["upstream_research_ref_id"] = "upstream_ref:other"
    snapshot["upstream_research_refs"] = [first, second]
    with pytest.raises(ResearchProjectV2Error) as upstream_exc:
        validate_industry_version_semantics(version)
    _assert_code(upstream_exc, "RESEARCH_PROJECT_V2_1_SEMANTIC_INVALID")
    assert upstream_exc.value.details["reason"] == "duplicate upstream reference"


def test_layered_ids_cannot_duplicate_common_r1_object_ids() -> None:
    version = _semantic_version()
    snapshot = version["snapshot"]
    assert isinstance(snapshot, dict)
    snapshot["source_candidates"][0]["candidate_id"] = "claim:fixture"
    snapshot["evidence_artifacts"][0]["candidate_id"] = "claim:fixture"
    snapshot["evidence_artifacts"][1]["candidate_id"] = "claim:fixture"
    with pytest.raises(ResearchProjectV2Error) as exc_info:
        validate_industry_version_semantics(version)
    _assert_code(exc_info, "RESEARCH_PROJECT_V2_1_SEMANTIC_INVALID")
    assert exc_info.value.details["id"] == "claim:fixture"


def test_assessment_target_must_match_requirement_target() -> None:
    version = _semantic_version()
    snapshot = version["snapshot"]
    assert isinstance(snapshot, dict)
    snapshot["evidence_requirements"][0].update(
        target_type="research_question", target_id="question:fixture"
    )
    with pytest.raises(ResearchProjectV2Error) as exc_info:
        validate_industry_version_semantics(version)
    _assert_code(exc_info, "RESEARCH_PROJECT_V2_1_SEMANTIC_INVALID")
    assert exc_info.value.details["reason"] == "assessment target does not match requirement target"


def test_conflict_target_must_match_referenced_assessment_targets() -> None:
    version = _semantic_version()
    snapshot = version["snapshot"]
    assert isinstance(snapshot, dict)
    snapshot["conflict_summaries"][0].update(
        target_type="research_question", target_id="question:fixture"
    )
    with pytest.raises(ResearchProjectV2Error) as exc_info:
        validate_industry_version_semantics(version)
    _assert_code(exc_info, "RESEARCH_PROJECT_V2_1_SEMANTIC_INVALID")
    assert exc_info.value.details["reason"] == "conflict target does not match assessment target"


@pytest.mark.parametrize("field", ["research_layer", "evidence_channel"])
@pytest.mark.parametrize("value", ["company_capture", "stock_evaluation", "company", "market"])
def test_downstream_layer_and_channel_escape_is_rejected(field: str, value: str) -> None:
    version = _semantic_version()
    snapshot = version["snapshot"]
    assert isinstance(snapshot, dict)
    if field == "research_layer":
        snapshot["search_plans"][0][field] = value
    else:
        snapshot["evidence_artifacts"][0][field] = value
    with pytest.raises(ResearchProjectV2Error) as exc_info:
        validate_industry_version_semantics(version)
    _assert_code(exc_info, "RESEARCH_PROJECT_V2_1_SEMANTIC_INVALID")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("raw_path", "evidence/raw/aa/" + "b" * 64 + ".pdf"),
        ("raw_path", "evidence/raw/bb/" + "c" * 64 + ".pdf"),
        ("raw_path", "evidence/raw/bb/" + "b" * 64 + ".html"),
        ("media_type", "text/html"),
    ],
)
def test_evidence_artifact_content_address_and_media_extension_are_semantic(
    field: str, value: str
) -> None:
    version = _semantic_version()
    snapshot = version["snapshot"]
    assert isinstance(snapshot, dict)
    snapshot["evidence_artifacts"][0][field] = value
    with pytest.raises(ResearchProjectV2Error) as exc_info:
        validate_industry_version_semantics(version)
    _assert_code(exc_info, "RESEARCH_PROJECT_V2_1_SEMANTIC_INVALID")
    assert "raw_path" in str(exc_info.value.details["reason"])
