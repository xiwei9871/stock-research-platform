from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import shutil

import pytest

from stock_research.research_project_v2.canonical import canonical_bytes, content_sha256
from stock_research.research_project_v2.errors import ResearchProjectV2Error
from stock_research.research_project_v2.layout import ResearchProjectLayout
from stock_research.research_project_v2.loader import (
    list_project_slugs,
    list_versions,
    load_events,
    load_index,
    load_project,
    load_version,
)


CREATED_AT = "2026-07-17T10:00:00+08:00"


def _identity(slug: str = "fixture", version: str = "0.1.0") -> dict[str, object]:
    return {
        "project_id": f"research_project:{slug}",
        "project_slug": slug,
        "title": f"{slug.title()} research project",
        "purpose": "Exercise immutable research project storage.",
        "created_at": CREATED_AT,
        "created_by": "fixture-author",
        "current_lifecycle_state": "research_ready",
        "current_version": f"research_version:{slug}:{version}",
        "latest_reviewed_version": None,
        "latest_published_version": None,
    }


def _research_design_snapshot() -> dict[str, object]:
    return {
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
            "decision_context": "Storage validation",
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
            "decided_at": CREATED_AT,
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
        "company_capture_assessments": [],
    }


def _version(
    slug: str = "fixture",
    semantic_version: str = "0.1.0",
    *,
    parent_version_id: str | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "artifact_version": "2.0.0",
        "version_id": f"research_version:{slug}:{semantic_version}",
        "project_id": f"research_project:{slug}",
        "semantic_version": semantic_version,
        "parent_version_id": parent_version_id,
        "creation_stage": "research_design",
        "created_at": CREATED_AT,
        "created_by": "fixture-author",
        "change_summary": "Create the initial research design.",
        "change_reason": "Initialize the fixture.",
        "incorporated_event_ids": [f"research_event:{slug}:created"],
        "content_hash": "0" * 64,
        "snapshot": _research_design_snapshot(),
    }
    payload["content_hash"] = content_sha256(
        payload,
        excluded_paths={("content_hash",)},
    )
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


def _event(slug: str = "fixture") -> dict[str, object]:
    return {
        "event_id": f"research_event:{slug}:created",
        "project_id": f"research_project:{slug}",
        "event_type": "project_created",
        "triggered_at": CREATED_AT,
        "trigger_source": "fixture-author",
        "affected_object_ids": [f"research_project:{slug}"],
        "base_version_id": None,
        "proposed_action": "Create the initial design version.",
        "review_status": "unreviewed",
        "resolution": None,
        "incorporated_version_id": f"research_version:{slug}:0.1.0",
        "notes": None,
        "provenance": {
            "created_by": "fixture-author",
            "actor_type": "human",
            "agent_run_id": None,
            "created_at": CREATED_AT,
            "created_in_version": f"research_version:{slug}:0.1.0",
            "review_status": "unreviewed",
        },
    }


def _index() -> dict[str, object]:
    return {
        "artifact_version": "2.0.0",
        "generated_at": CREATED_AT,
        "projects": [
            {
                "project_id": "research_project:fixture",
                "project_slug": "fixture",
                "title": "Fixture research project",
                "current_lifecycle_state": "research_ready",
                "current_version": "research_version:fixture:0.1.0",
                "latest_reviewed_version": None,
                "latest_published_version": None,
                "relative_path": "projects/fixture/project.json",
            }
        ],
    }


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )


@pytest.fixture
def tmp_project_layout(tmp_path: Path) -> ResearchProjectLayout:
    layout = ResearchProjectLayout(tmp_path / "research_projects_v2")
    shutil.copytree(ResearchProjectLayout.default().schema_dir, layout.schema_dir)

    identity = _identity()
    version = _version()
    project_dir = layout.project_dir("fixture")
    _write_json(project_dir / "project.json", identity)
    _write_json(project_dir / "versions/v0.1.0.json", version)
    _write_jsonl(project_dir / "version_manifest.jsonl", [_manifest_row(version)])
    _write_jsonl(project_dir / "events/events.jsonl", [_event()])
    _write_json(layout.index_path, _index())
    return layout


def test_default_layout_points_at_versioned_artifact_root():
    layout = ResearchProjectLayout.default()
    assert layout.root.as_posix().endswith("artifacts/research_projects/v2")
    assert layout.schema_dir == layout.root / "schema"
    assert layout.projects_dir == layout.root / "projects"
    assert layout.index_path == layout.root / "index/research_project_index_v2.json"


def test_domain_error_exposes_stable_code_and_details():
    error = ResearchProjectV2Error(
        "version not found",
        code="RESEARCH_PROJECT_VERSION_NOT_FOUND",
        details={"version": "0.1.0"},
    )
    assert error.code == "RESEARCH_PROJECT_VERSION_NOT_FOUND"
    assert error.details == {"version": "0.1.0"}


def test_domain_error_copies_details_for_each_instance():
    source_details = {"version": "0.1.0"}

    first_error = ResearchProjectV2Error(
        "version not found",
        code="RESEARCH_PROJECT_VERSION_NOT_FOUND",
        details=source_details,
    )
    second_error = ResearchProjectV2Error(
        "version not found",
        code="RESEARCH_PROJECT_VERSION_NOT_FOUND",
        details=source_details,
    )

    assert first_error.details is not source_details
    assert second_error.details is not source_details
    assert first_error.details is not second_error.details

    first_error.details["version"] = "0.2.0"

    assert second_error.details == {"version": "0.1.0"}
    assert source_details == {"version": "0.1.0"}


def test_canonical_hash_ignores_json_key_order_and_whitespace_with_unicode():
    compact = json.loads('{"研究主题":"可控核聚变","scope":{"b":2,"a":1}}')
    spaced = json.loads(
        '{\n  "scope": {"a": 1, "b": 2},\n  "研究主题": "可控核聚变"\n}'
    )
    assert canonical_bytes(compact) == canonical_bytes(spaced)
    assert content_sha256(compact) == content_sha256(spaced)


def test_canonical_hash_excludes_self_hash_without_mutating_payload():
    first = {"title": "研究", "content_hash": "a" * 64}
    second = {"content_hash": "b" * 64, "title": "研究"}
    original = deepcopy(first)
    excluded = {("content_hash",)}
    assert content_sha256(first, excluded_paths=excluded) == content_sha256(
        second,
        excluded_paths=excluded,
    )
    assert first == original


def test_canonical_hash_safely_ignores_missing_excluded_path():
    payload = {"nested": {"value": 1}}
    assert canonical_bytes(payload, excluded_paths={("nested", "missing")}) == canonical_bytes(
        payload
    )


def test_list_project_slugs_and_versions_are_stably_sorted(tmp_project_layout):
    for slug in ("zeta", "alpha"):
        _write_json(tmp_project_layout.project_dir(slug) / "project.json", _identity(slug))
    ignored = tmp_project_layout.projects_dir / "ignored"
    ignored.mkdir()
    versions_dir = tmp_project_layout.project_dir("fixture") / "versions"
    for semantic_version in ("0.10.0", "0.2.0"):
        _write_json(versions_dir / f"v{semantic_version}.json", {})
    _write_json(versions_dir / "notes.json", {})
    _write_json(versions_dir / "vbad.json", {})

    assert list_project_slugs(layout=tmp_project_layout) == ["alpha", "fixture", "zeta"]
    assert list_versions("fixture", layout=tmp_project_layout) == [
        "0.1.0",
        "0.2.0",
        "0.10.0",
    ]


def test_list_project_slugs_returns_empty_for_initial_repository(tmp_path):
    assert list_project_slugs(layout=ResearchProjectLayout(tmp_path)) == []


def test_layout_root_itself_may_be_a_symlink(tmp_project_layout):
    aliased_root = tmp_project_layout.root.parent / "research-projects-alias"
    aliased_root.symlink_to(tmp_project_layout.root, target_is_directory=True)
    aliased_layout = ResearchProjectLayout(aliased_root)

    assert load_project("fixture", layout=aliased_layout)["project_slug"] == "fixture"


def test_project_slug_traversal_cannot_read_outside_projects_dir(tmp_project_layout):
    _write_json(tmp_project_layout.root / "escape/project.json", _identity("escape"))

    with pytest.raises(ResearchProjectV2Error) as exc_info:
        load_project("../escape", layout=tmp_project_layout)

    assert exc_info.value.code == "RESEARCH_PROJECT_NOT_FOUND"


def test_list_project_slugs_skips_invalid_names_and_symlink_project(tmp_project_layout):
    for slug in ("Bad Name", ".hidden", "a-", "a__b", "a-_b"):
        _write_json(tmp_project_layout.projects_dir / slug / "project.json", _identity())
    outside_project = tmp_project_layout.root / "outside-project"
    _write_json(outside_project / "project.json", _identity("linked"))
    (tmp_project_layout.projects_dir / "linked").symlink_to(
        outside_project,
        target_is_directory=True,
    )

    assert list_project_slugs(layout=tmp_project_layout) == ["fixture"]


@pytest.mark.parametrize("project_slug", ["a-", "a__b", "a-_b"])
def test_load_project_rejects_schema_invalid_slug_components(
    tmp_project_layout,
    project_slug,
):
    _write_json(
        tmp_project_layout.projects_dir / project_slug / "project.json",
        _identity(),
    )

    with pytest.raises(ResearchProjectV2Error) as exc_info:
        load_project(project_slug, layout=tmp_project_layout)

    assert exc_info.value.code == "RESEARCH_PROJECT_NOT_FOUND"


def test_load_project_rejects_symlink_project_directory(tmp_project_layout):
    outside_project = tmp_project_layout.root / "outside-project"
    _write_json(outside_project / "project.json", _identity("linked"))
    (tmp_project_layout.projects_dir / "linked").symlink_to(
        outside_project,
        target_is_directory=True,
    )

    with pytest.raises(ResearchProjectV2Error) as exc_info:
        load_project("linked", layout=tmp_project_layout)

    assert exc_info.value.code == "RESEARCH_PROJECT_NOT_FOUND"


def test_load_project_rejects_symlink_project_json(tmp_project_layout):
    outside_identity = tmp_project_layout.root / "outside-project.json"
    _write_json(outside_identity, _identity("linked"))
    linked_project_dir = tmp_project_layout.project_dir("linked")
    linked_project_dir.mkdir()
    (linked_project_dir / "project.json").symlink_to(outside_identity)

    with pytest.raises(ResearchProjectV2Error) as exc_info:
        load_project("linked", layout=tmp_project_layout)

    assert exc_info.value.code == "RESEARCH_PROJECT_NOT_FOUND"


def test_load_project_index_and_events_validate_and_return_payloads(tmp_project_layout):
    assert load_project("fixture", layout=tmp_project_layout)["project_slug"] == "fixture"
    assert load_index(layout=tmp_project_layout)["artifact_version"] == "2.0.0"
    assert [row["event_id"] for row in load_events("fixture", layout=tmp_project_layout)] == [
        "research_event:fixture:created"
    ]


@pytest.mark.parametrize(
    ("loader", "path", "field"),
    [
        (lambda layout: load_project("fixture", layout=layout), "projects/fixture/project.json", "title"),
        (lambda layout: load_index(layout=layout), "index/research_project_index_v2.json", "generated_at"),
        (lambda layout: load_events("fixture", layout=layout), "projects/fixture/events/events.jsonl", "provenance"),
    ],
)
def test_project_index_and_events_use_schema_validation(
    tmp_project_layout,
    loader,
    path,
    field,
):
    artifact_path = tmp_project_layout.root / path
    if artifact_path.suffix == ".jsonl":
        payload = _event()
        payload.pop(field)
        _write_jsonl(artifact_path, [payload])
    else:
        payload = json.loads(artifact_path.read_text(encoding="utf-8"))
        payload.pop(field)
        _write_json(artifact_path, payload)

    with pytest.raises(ResearchProjectV2Error) as exc_info:
        loader(tmp_project_layout)
    assert exc_info.value.code == "RESEARCH_PROJECT_SCHEMA_INVALID"


def test_load_version_uses_current_pointer_and_accepts_explicit_version(tmp_project_layout):
    current = load_version("fixture", layout=tmp_project_layout)
    explicit = load_version("fixture", "0.1.0", layout=tmp_project_layout)
    assert current == explicit
    assert current["version_id"] == "research_version:fixture:0.1.0"


def test_load_version_rejects_non_semver_before_building_path(tmp_project_layout):
    with pytest.raises(ResearchProjectV2Error) as exc_info:
        load_version("fixture", "x/../../../escape", layout=tmp_project_layout)

    assert exc_info.value.code == "RESEARCH_PROJECT_VERSION_NOT_FOUND"


def test_load_version_prioritizes_invalid_project_slug_error(tmp_project_layout):
    with pytest.raises(ResearchProjectV2Error) as exc_info:
        load_version("../escape", "not-semver", layout=tmp_project_layout)

    assert exc_info.value.code == "RESEARCH_PROJECT_NOT_FOUND"


def test_load_version_rejects_symlink_version_file(tmp_project_layout):
    version_path = tmp_project_layout.project_dir("fixture") / "versions/v0.1.0.json"
    outside_version = tmp_project_layout.root / "outside-version.json"
    version_path.replace(outside_version)
    version_path.symlink_to(outside_version)

    with pytest.raises(ResearchProjectV2Error) as exc_info:
        load_version("fixture", "0.1.0", layout=tmp_project_layout)

    assert exc_info.value.code == "RESEARCH_PROJECT_VERSION_NOT_FOUND"


def test_list_versions_does_not_follow_symlink_versions_directory(tmp_project_layout):
    versions_dir = tmp_project_layout.project_dir("fixture") / "versions"
    outside_versions = tmp_project_layout.root / "outside-versions"
    versions_dir.replace(outside_versions)
    versions_dir.symlink_to(outside_versions, target_is_directory=True)

    assert list_versions("fixture", layout=tmp_project_layout) == []


def test_load_version_rejects_symlink_manifest(tmp_project_layout):
    manifest_path = tmp_project_layout.project_dir("fixture") / "version_manifest.jsonl"
    outside_manifest = tmp_project_layout.root / "outside-manifest.jsonl"
    manifest_path.replace(outside_manifest)
    manifest_path.symlink_to(outside_manifest)

    with pytest.raises(ResearchProjectV2Error) as exc_info:
        load_version("fixture", "0.1.0", layout=tmp_project_layout)

    assert exc_info.value.code == "RESEARCH_PROJECT_IMMUTABILITY_VIOLATION"
    assert "unsafe manifest path" in exc_info.value.details["reason"]


def test_tampered_version_content_is_an_immutability_violation(tmp_project_layout):
    version_path = tmp_project_layout.project_dir("fixture") / "versions/v0.1.0.json"
    version = json.loads(version_path.read_text(encoding="utf-8"))
    version["change_summary"] = "Tampered after creation."
    _write_json(version_path, version)

    with pytest.raises(ResearchProjectV2Error) as exc_info:
        load_version("fixture", "0.1.0", layout=tmp_project_layout)
    assert exc_info.value.code == "RESEARCH_PROJECT_IMMUTABILITY_VIOLATION"
    assert exc_info.value.details["project"] == "fixture"
    assert exc_info.value.details["version"] == "0.1.0"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("content_hash", "f" * 64),
        ("relative_path", "versions/../v0.1.0.json"),
        ("version_id", "research_version:fixture:changed"),
        ("parent_version_id", "research_version:fixture:0.0.1"),
    ],
)
def test_manifest_mismatch_is_an_immutability_violation(
    tmp_project_layout,
    field,
    value,
):
    manifest_path = tmp_project_layout.project_dir("fixture") / "version_manifest.jsonl"
    row = _manifest_row(_version())
    row[field] = value
    _write_jsonl(manifest_path, [row])

    with pytest.raises(ResearchProjectV2Error) as exc_info:
        load_version("fixture", "0.1.0", layout=tmp_project_layout)
    assert exc_info.value.code == "RESEARCH_PROJECT_IMMUTABILITY_VIOLATION"
    assert exc_info.value.details["reason"]


@pytest.mark.parametrize("manifest_rows", [[], [_manifest_row(_version()), _manifest_row(_version())]])
def test_missing_or_duplicate_manifest_row_is_an_immutability_violation(
    tmp_project_layout,
    manifest_rows,
):
    manifest_path = tmp_project_layout.project_dir("fixture") / "version_manifest.jsonl"
    _write_jsonl(manifest_path, manifest_rows)
    with pytest.raises(ResearchProjectV2Error) as exc_info:
        load_version("fixture", "0.1.0", layout=tmp_project_layout)
    assert exc_info.value.code == "RESEARCH_PROJECT_IMMUTABILITY_VIOLATION"


def test_manifest_missing_required_field_is_an_immutability_violation(tmp_project_layout):
    manifest_path = tmp_project_layout.project_dir("fixture") / "version_manifest.jsonl"
    row = _manifest_row(_version())
    row.pop("version_id")
    _write_jsonl(manifest_path, [row])
    with pytest.raises(ResearchProjectV2Error) as exc_info:
        load_version("fixture", "0.1.0", layout=tmp_project_layout)
    assert exc_info.value.code == "RESEARCH_PROJECT_IMMUTABILITY_VIOLATION"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("content_hash", "f" * 64),
        ("semantic_version", "0.2.0"),
        ("project_id", "research_project:other"),
    ],
)
def test_embedded_version_identity_or_hash_mismatch_is_an_immutability_violation(
    tmp_project_layout,
    field,
    value,
):
    version_path = tmp_project_layout.project_dir("fixture") / "versions/v0.1.0.json"
    version = json.loads(version_path.read_text(encoding="utf-8"))
    version[field] = value
    _write_json(version_path, version)
    with pytest.raises(ResearchProjectV2Error) as exc_info:
        load_version("fixture", "0.1.0", layout=tmp_project_layout)
    assert exc_info.value.code == "RESEARCH_PROJECT_IMMUTABILITY_VIOLATION"


@pytest.mark.parametrize("current_version", ["", None])
def test_empty_current_pointer_is_version_not_found(tmp_project_layout, current_version):
    project_path = tmp_project_layout.project_dir("fixture") / "project.json"
    identity = _identity()
    identity["current_version"] = current_version
    _write_json(project_path, identity)
    with pytest.raises(ResearchProjectV2Error) as exc_info:
        load_version("fixture", layout=tmp_project_layout)
    assert exc_info.value.code == "RESEARCH_PROJECT_VERSION_NOT_FOUND"


def test_duplicate_event_id_has_stable_error_code(tmp_project_layout):
    events_path = tmp_project_layout.project_dir("fixture") / "events/events.jsonl"
    event = _event()
    _write_jsonl(events_path, [event, event])
    with pytest.raises(ResearchProjectV2Error) as exc_info:
        load_events("fixture", layout=tmp_project_layout)
    assert exc_info.value.code == "RESEARCH_PROJECT_DUPLICATE_EVENT_ID"
    assert exc_info.value.details["event_id"] == "research_event:fixture:created"


def test_events_preserve_jsonl_file_order(tmp_project_layout):
    events_path = tmp_project_layout.project_dir("fixture") / "events/events.jsonl"
    first = _event()
    second = _event()
    second["event_id"] = "research_event:fixture:reviewed"
    second["event_type"] = "review_requested"
    _write_jsonl(events_path, [second, first])

    assert [event["event_id"] for event in load_events("fixture", layout=tmp_project_layout)] == [
        "research_event:fixture:reviewed",
        "research_event:fixture:created",
    ]


@pytest.mark.parametrize("contents", ["", "\n\n"])
def test_empty_event_file_returns_empty_list(tmp_project_layout, contents):
    events_path = tmp_project_layout.project_dir("fixture") / "events/events.jsonl"
    events_path.write_text(contents, encoding="utf-8")
    assert load_events("fixture", layout=tmp_project_layout) == []


def test_missing_event_file_returns_empty_list_for_existing_project(tmp_project_layout):
    events_path = tmp_project_layout.project_dir("fixture") / "events/events.jsonl"
    events_path.unlink()
    assert load_events("fixture", layout=tmp_project_layout) == []


def test_load_events_rejects_symlink_event_file(tmp_project_layout):
    events_path = tmp_project_layout.project_dir("fixture") / "events/events.jsonl"
    outside_events = tmp_project_layout.root / "outside-events.jsonl"
    events_path.replace(outside_events)
    events_path.symlink_to(outside_events)

    with pytest.raises(ResearchProjectV2Error) as exc_info:
        load_events("fixture", layout=tmp_project_layout)

    assert exc_info.value.code == "RESEARCH_PROJECT_NOT_FOUND"


@pytest.mark.parametrize(
    ("call", "code"),
    [
        (lambda layout: load_project("missing", layout=layout), "RESEARCH_PROJECT_NOT_FOUND"),
        (lambda layout: list_versions("missing", layout=layout), "RESEARCH_PROJECT_NOT_FOUND"),
        (lambda layout: load_events("missing", layout=layout), "RESEARCH_PROJECT_NOT_FOUND"),
        (
            lambda layout: load_version("fixture", "9.9.9", layout=layout),
            "RESEARCH_PROJECT_VERSION_NOT_FOUND",
        ),
    ],
)
def test_missing_project_or_version_has_stable_error_code(tmp_project_layout, call, code):
    with pytest.raises(ResearchProjectV2Error) as exc_info:
        call(tmp_project_layout)
    assert exc_info.value.code == code


def test_missing_index_has_stable_not_found_code(tmp_project_layout):
    tmp_project_layout.index_path.unlink()
    with pytest.raises(ResearchProjectV2Error) as exc_info:
        load_index(layout=tmp_project_layout)
    assert exc_info.value.code == "RESEARCH_PROJECT_NOT_FOUND"
    assert exc_info.value.details["artifact"] == "index"


def test_load_index_rejects_symlink_index_file(tmp_project_layout):
    outside_index = tmp_project_layout.root / "outside-index.json"
    tmp_project_layout.index_path.replace(outside_index)
    tmp_project_layout.index_path.symlink_to(outside_index)

    with pytest.raises(ResearchProjectV2Error) as exc_info:
        load_index(layout=tmp_project_layout)

    assert exc_info.value.code == "RESEARCH_PROJECT_NOT_FOUND"
