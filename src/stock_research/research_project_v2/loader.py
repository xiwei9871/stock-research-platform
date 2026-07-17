import json
from functools import lru_cache
from pathlib import Path
import re
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker, RefResolver

from stock_research.research_project_v2.canonical import content_sha256
from stock_research.research_project_v2.errors import ResearchProjectV2Error
from stock_research.research_project_v2.layout import ResearchProjectLayout


SCHEMA_FILES = {
    "research_project_identity_v2": "research_project_identity_v2.schema.json",
    "research_version_v2": "research_version_v2.schema.json",
    "research_event_v2": "research_event_v2.schema.json",
    "research_project_index_v2": "research_project_index_v2.schema.json",
}

_VERSION_FILE_PATTERN = re.compile(
    r"v((?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*))\.json"
)
_MANIFEST_FIELDS = {
    "version_id",
    "semantic_version",
    "parent_version_id",
    "relative_path",
    "content_hash",
    "created_at",
}


@lru_cache(maxsize=None)
def _schema_bundle(schema_name: str) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        schema_file = SCHEMA_FILES[schema_name]
    except KeyError as exc:
        raise ResearchProjectV2Error(
            f"Unknown research project schema: {schema_name}",
            code="RESEARCH_PROJECT_SCHEMA_NOT_FOUND",
            details={"schema": schema_name},
        ) from exc

    schema_dir = ResearchProjectLayout.default().schema_dir
    with (schema_dir / schema_file).open(encoding="utf-8") as handle:
        schema = json.load(handle)
    with (schema_dir / "definitions_v2.schema.json").open(encoding="utf-8") as handle:
        definitions = json.load(handle)
    return schema, definitions


def validate_schema_payload(schema_name: str, payload: dict[str, Any]) -> None:
    schema, definitions = _schema_bundle(schema_name)
    resolver = RefResolver.from_schema(
        schema,
        store={"definitions_v2.schema.json": definitions},
    )
    validator = Draft202012Validator(
        schema,
        resolver=resolver,
        format_checker=FormatChecker(),
    )
    errors = sorted(
        validator.iter_errors(payload),
        key=lambda error: tuple(str(part) for part in error.absolute_path),
    )
    if not errors:
        return

    first_error = errors[0]
    path = ".".join(str(part) for part in first_error.absolute_path)
    raise ResearchProjectV2Error(
        f"Research project payload does not match the {schema_name} schema",
        code="RESEARCH_PROJECT_SCHEMA_INVALID",
        details={"path": path, "schema": schema_name},
    )


def _layout_or_default(layout: ResearchProjectLayout | None) -> ResearchProjectLayout:
    return ResearchProjectLayout.default() if layout is None else layout


def _read_json_object(path: Path, schema_name: str) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ResearchProjectV2Error(
            f"Research project payload does not match the {schema_name} schema",
            code="RESEARCH_PROJECT_SCHEMA_INVALID",
            details={"path": "", "schema": schema_name},
        )
    validate_schema_payload(schema_name, payload)
    return payload


def _project_not_found(project_slug: str) -> ResearchProjectV2Error:
    return ResearchProjectV2Error(
        f"Research project not found: {project_slug}",
        code="RESEARCH_PROJECT_NOT_FOUND",
        details={"project": project_slug},
    )


def _require_project_path(
    project_slug: str,
    layout: ResearchProjectLayout,
) -> Path:
    project_path = layout.project_dir(project_slug) / "project.json"
    if not project_path.is_file():
        raise _project_not_found(project_slug)
    return project_path


def _version_not_found(
    project_slug: str,
    semantic_version: str | None,
) -> ResearchProjectV2Error:
    return ResearchProjectV2Error(
        f"Research project version not found: {project_slug} {semantic_version or ''}".rstrip(),
        code="RESEARCH_PROJECT_VERSION_NOT_FOUND",
        details={"project": project_slug, "version": semantic_version},
    )


def _immutability_violation(
    project_slug: str,
    semantic_version: str,
    reason: str,
) -> ResearchProjectV2Error:
    return ResearchProjectV2Error(
        f"Immutable research project version failed verification: {reason}",
        code="RESEARCH_PROJECT_IMMUTABILITY_VIOLATION",
        details={
            "project": project_slug,
            "version": semantic_version,
            "reason": reason,
        },
    )


def list_project_slugs(
    *,
    layout: ResearchProjectLayout | None = None,
) -> list[str]:
    selected_layout = _layout_or_default(layout)
    if not selected_layout.projects_dir.is_dir():
        return []
    return sorted(
        entry.name
        for entry in selected_layout.projects_dir.iterdir()
        if entry.is_dir() and (entry / "project.json").is_file()
    )


def load_project(
    project_slug: str,
    *,
    layout: ResearchProjectLayout | None = None,
) -> dict[str, Any]:
    selected_layout = _layout_or_default(layout)
    project_path = _require_project_path(project_slug, selected_layout)
    return _read_json_object(project_path, "research_project_identity_v2")


def list_versions(
    project_slug: str,
    *,
    layout: ResearchProjectLayout | None = None,
) -> list[str]:
    selected_layout = _layout_or_default(layout)
    _require_project_path(project_slug, selected_layout)
    versions_dir = selected_layout.project_dir(project_slug) / "versions"
    if not versions_dir.is_dir():
        return []
    versions = []
    for path in versions_dir.iterdir():
        match = _VERSION_FILE_PATTERN.fullmatch(path.name)
        if path.is_file() and match:
            versions.append(match.group(1))
    return sorted(versions, key=lambda version: tuple(map(int, version.split("."))))


def _semantic_version_from_pointer(pointer: str) -> str:
    return pointer.rsplit(":", 1)[-1]


def _read_identity_for_current_version(
    project_slug: str,
    layout: ResearchProjectLayout,
) -> tuple[dict[str, Any], str]:
    project_path = _require_project_path(project_slug, layout)
    with project_path.open(encoding="utf-8") as handle:
        identity = json.load(handle)
    if not isinstance(identity, dict):
        validate_schema_payload("research_project_identity_v2", identity)
    pointer = identity.get("current_version")
    if not pointer or not isinstance(pointer, str):
        raise _version_not_found(project_slug, None)
    validate_schema_payload("research_project_identity_v2", identity)
    return identity, _semantic_version_from_pointer(pointer)


def _read_manifest_rows(
    project_slug: str,
    semantic_version: str,
    manifest_path: Path,
) -> list[dict[str, Any]]:
    try:
        lines = manifest_path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise _immutability_violation(
            project_slug,
            semantic_version,
            "version manifest is missing or unreadable",
        ) from exc

    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise _immutability_violation(
                project_slug,
                semantic_version,
                f"manifest row {line_number} is not valid JSON",
            ) from exc
        if not isinstance(row, dict):
            raise _immutability_violation(
                project_slug,
                semantic_version,
                f"manifest row {line_number} is not an object",
            )
        missing_fields = sorted(_MANIFEST_FIELDS - row.keys())
        if missing_fields:
            raise _immutability_violation(
                project_slug,
                semantic_version,
                f"manifest row {line_number} is missing fields: {', '.join(missing_fields)}",
            )
        rows.append(row)
    return rows


def _verify_version_immutability(
    project_slug: str,
    semantic_version: str,
    identity: dict[str, Any],
    payload: dict[str, Any],
    manifest_path: Path,
) -> None:
    if payload.get("project_id") != identity.get("project_id"):
        raise _immutability_violation(project_slug, semantic_version, "project_id mismatch")
    if payload.get("semantic_version") != semantic_version:
        raise _immutability_violation(
            project_slug,
            semantic_version,
            "semantic_version mismatch",
        )
    calculated_hash = content_sha256(
        payload,
        excluded_paths={("content_hash",)},
    )
    if payload.get("content_hash") != calculated_hash:
        raise _immutability_violation(project_slug, semantic_version, "embedded content_hash mismatch")

    rows = _read_manifest_rows(project_slug, semantic_version, manifest_path)
    matching_rows = [row for row in rows if row["semantic_version"] == semantic_version]
    if len(matching_rows) != 1:
        raise _immutability_violation(
            project_slug,
            semantic_version,
            f"expected exactly one manifest row, found {len(matching_rows)}",
        )
    row = matching_rows[0]
    expected_values = {
        "version_id": payload.get("version_id"),
        "semantic_version": semantic_version,
        "parent_version_id": payload.get("parent_version_id"),
        "content_hash": payload.get("content_hash"),
        "relative_path": f"versions/v{semantic_version}.json",
    }
    for field, expected in expected_values.items():
        if row[field] != expected:
            raise _immutability_violation(
                project_slug,
                semantic_version,
                f"manifest {field} mismatch",
            )


def load_version(
    project_slug: str,
    semantic_version: str | None = None,
    *,
    layout: ResearchProjectLayout | None = None,
) -> dict[str, Any]:
    selected_layout = _layout_or_default(layout)
    if semantic_version is None:
        identity, semantic_version = _read_identity_for_current_version(
            project_slug,
            selected_layout,
        )
    else:
        identity = load_project(project_slug, layout=selected_layout)

    version_path = (
        selected_layout.project_dir(project_slug)
        / "versions"
        / f"v{semantic_version}.json"
    )
    if not version_path.is_file():
        raise _version_not_found(project_slug, semantic_version)
    payload = _read_json_object(version_path, "research_version_v2")
    _verify_version_immutability(
        project_slug,
        semantic_version,
        identity,
        payload,
        selected_layout.project_dir(project_slug) / "version_manifest.jsonl",
    )
    return payload


def load_events(
    project_slug: str,
    *,
    layout: ResearchProjectLayout | None = None,
) -> list[dict[str, Any]]:
    selected_layout = _layout_or_default(layout)
    _require_project_path(project_slug, selected_layout)
    events_path = selected_layout.project_dir(project_slug) / "events/events.jsonl"
    if not events_path.is_file():
        return []

    events: list[dict[str, Any]] = []
    seen_event_ids: set[str] = set()
    for line in events_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        event = json.loads(line)
        if not isinstance(event, dict):
            raise ResearchProjectV2Error(
                "Research project payload does not match the research_event_v2 schema",
                code="RESEARCH_PROJECT_SCHEMA_INVALID",
                details={"path": "", "schema": "research_event_v2"},
            )
        validate_schema_payload("research_event_v2", event)
        event_id = event["event_id"]
        if event_id in seen_event_ids:
            raise ResearchProjectV2Error(
                f"Duplicate research event id: {event_id}",
                code="RESEARCH_PROJECT_DUPLICATE_EVENT_ID",
                details={"project": project_slug, "event_id": event_id},
            )
        seen_event_ids.add(event_id)
        events.append(event)
    return events


def load_index(
    *,
    layout: ResearchProjectLayout | None = None,
) -> dict[str, Any]:
    selected_layout = _layout_or_default(layout)
    if not selected_layout.index_path.is_file():
        raise ResearchProjectV2Error(
            "Research project index not found",
            code="RESEARCH_PROJECT_NOT_FOUND",
            details={"artifact": "index"},
        )
    return _read_json_object(
        selected_layout.index_path,
        "research_project_index_v2",
    )
