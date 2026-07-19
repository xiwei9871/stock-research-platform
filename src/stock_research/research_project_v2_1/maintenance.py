from __future__ import annotations

import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any
from datetime import datetime

from stock_research.research_project_v2.canonical import content_sha256
from stock_research.research_project_v2.errors import ResearchProjectV2Error
from stock_research.research_project_v2_1.layout import LayeredResearchLayout
from stock_research.research_project_v2_1.lineage import (
    LineageError,
    collect_lineage_version_ids,
)
from stock_research.research_project_v2_1.loader import (
    layered_storage_lock,
    list_layered_project_slugs,
    load_industry_version,
    load_layered_project,
)
from stock_research.research_project_v2_1.schema import validate_v2_1_schema_payload
from stock_research.research_project_v2_1.semantic import validate_industry_version_semantics


_SEMVER = re.compile(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)")
_VERSION_FILE = re.compile(rf"v({_SEMVER.pattern})\.json")
_MANIFEST_FIELDS = {
    "version_id",
    "semantic_version",
    "parent_version_id",
    "relative_path",
    "content_hash",
    "created_at",
}


def _error(reason: str, *, path: Path | None = None, **details: object) -> ResearchProjectV2Error:
    return ResearchProjectV2Error(
        f"Layered research maintenance failed: {reason}",
        code="RESEARCH_PROJECT_V2_1_IMMUTABILITY_VIOLATION",
        details={"reason": reason, **({"path": str(path)} if path else {}), **details},
    )


def _semver_key(value: str) -> tuple[int, int, int]:
    return tuple(map(int, value.split(".")))


def _json_bytes(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _timestamp_key(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise _error("invalid RFC3339 timestamp", value=value) from exc
    if parsed.tzinfo is None:
        raise _error("invalid RFC3339 timestamp", value=value)
    return parsed


def _validate_version_identity(
    version: dict[str, Any],
    *,
    slug: str,
    semantic_version: str,
    identity: dict[str, Any],
    path: Path,
) -> None:
    expected = {
        "semantic_version": semantic_version,
        "version_id": f"research_version:{slug}:{semantic_version}",
        "project_id": identity["project_id"],
    }
    for field, expected_value in expected.items():
        actual = version.get(field)
        if actual != expected_value:
            raise _error(
                f"version {field} mismatch",
                path=path,
                project=slug,
                version=semantic_version,
                field=field,
                expected=expected_value,
                actual=actual,
            )


def _atomic_replace_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _atomic_write(path: Path, data: bytes) -> None:
    _atomic_replace_bytes(path, data)


def _safe(path: Path, layout: LayeredResearchLayout, *, allow_missing: bool = False) -> None:
    try:
        relative = path.relative_to(layout.root)
    except ValueError as exc:
        raise _error("unsafe managed path", path=path) from exc
    current = layout.root
    if current.is_symlink():
        raise _error("unsafe managed path", path=current)
    for part in relative.parts:
        if part in {"", ".", ".."}:
            raise _error("unsafe managed path", path=path)
        current /= part
        if current.is_symlink():
            raise _error("unsafe managed path", path=current)
    try:
        path.resolve(strict=False).relative_to(layout.root.resolve(strict=False))
    except (OSError, ValueError) as exc:
        raise _error("unsafe managed path", path=path) from exc
    if not allow_missing and not path.exists():
        raise _error("managed path missing", path=path)


def _manifest(path: Path, slug: str) -> tuple[bytes, list[dict[str, Any]]]:
    prefix = path.read_bytes() if path.is_file() else b""
    try:
        lines = prefix.decode("utf-8").splitlines()
    except UnicodeError as exc:
        raise _error("invalid manifest encoding", path=path, project=slug) from exc
    rows: list[dict[str, Any]] = []
    versions: set[str] = set()
    version_ids: set[str] = set()
    for line_number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise _error("invalid manifest JSON", path=path, project=slug, line=line_number) from exc
        if not isinstance(row, dict) or set(row) != _MANIFEST_FIELDS:
            raise _error("manifest fields mismatch", path=path, project=slug, line=line_number)
        semantic_version = row.get("semantic_version")
        version_id = row.get("version_id")
        if not isinstance(semantic_version, str) or _SEMVER.fullmatch(semantic_version) is None:
            raise _error("invalid manifest semantic_version", path=path, project=slug, line=line_number)
        if not isinstance(version_id, str) or version_id != f"research_version:{slug}:{semantic_version}":
            raise _error("invalid manifest version_id", path=path, project=slug, line=line_number)
        if semantic_version in versions or version_id in version_ids:
            raise _error("duplicate manifest version", path=path, project=slug)
        versions.add(semantic_version)
        version_ids.add(version_id)
        rows.append(row)
    return prefix, rows


def _project_paths(slug: str, layout: LayeredResearchLayout) -> tuple[Path, Path, Path]:
    project_dir = layout.project_dir(slug)
    identity_path = project_dir / "project.json"
    versions_dir = project_dir / "versions"
    manifest_path = project_dir / "version_manifest.jsonl"
    for path in (project_dir, identity_path, versions_dir):
        _safe(path, layout)
    _safe(manifest_path, layout, allow_missing=True)
    expected = {"project.json", "versions", "version_manifest.jsonl"}
    actual = {entry.name for entry in project_dir.iterdir()}
    unexpected = sorted(actual - expected)
    if unexpected:
        raise _error("unexpected project entry", path=project_dir / unexpected[0], project=slug)
    return identity_path, versions_dir, manifest_path


def _version_paths(slug: str, versions_dir: Path, layout: LayeredResearchLayout) -> list[tuple[str, Path]]:
    versions: list[tuple[str, Path]] = []
    for entry in versions_dir.iterdir():
        _safe(entry, layout)
        match = _VERSION_FILE.fullmatch(entry.name)
        if match is None or not entry.is_file():
            raise _error("unexpected versions entry", path=entry, project=slug)
        versions.append((match.group(1), entry))
    return sorted(versions, key=lambda pair: _semver_key(pair[0]))


def _commit(
    targets: list[tuple[Path, bytes]],
    layout: LayeredResearchLayout,
) -> None:
    originals = {path: path.read_bytes() if path.exists() else None for path, _ in targets}
    missing_directories: set[Path] = set()
    for path, _ in targets:
        parent = path.parent
        while not parent.exists():
            missing_directories.add(parent)
            parent = parent.parent
    attempted: list[Path] = []
    try:
        for path, data in targets:
            _safe(path, layout, allow_missing=True)
            attempted.append(path)
            _atomic_write(path, data)
            _safe(path, layout)
    except Exception:
        for path in reversed(attempted):
            try:
                original = originals[path]
                if original is None:
                    path.unlink(missing_ok=True)
                else:
                    _atomic_replace_bytes(path, original)
            except Exception:
                continue
        for directory in sorted(missing_directories, key=lambda item: len(item.parts), reverse=True):
            try:
                directory.rmdir()
            except OSError:
                continue
        raise


def _rebuild_layered_index_unlocked(
    write: bool,
    layout: LayeredResearchLayout,
) -> dict[str, object]:
    """Rebuild only the V2.1 layered index and bootstrap placeholder hashes."""
    selected = layout
    allowed_root_entries = {
        ".maintenance.lock",
        "evidence",
        "fixtures",
        "index",
        "projects",
        "schema",
    }
    for entry in selected.root.iterdir():
        _safe(entry, selected)
        if entry.name not in allowed_root_entries:
            raise _error("unexpected layered root entry", path=entry)
    _safe(selected.projects_dir, selected)
    for entry in selected.projects_dir.iterdir():
        _safe(entry, selected)
        if not entry.is_dir():
            raise _error("unexpected projects entry", path=entry)
    _safe(selected.index_path.parent, selected, allow_missing=True)
    _safe(selected.index_path, selected, allow_missing=True)

    slugs = list_layered_project_slugs(layout=selected)
    actual_slugs = sorted(entry.name for entry in selected.projects_dir.iterdir())
    if not slugs or slugs != actual_slugs:
        raise _error("invalid project directory", path=selected.projects_dir)

    targets: list[tuple[Path, bytes]] = []
    planned_versions: list[str] = []
    index_rows: list[dict[str, Any]] = []
    timestamps: list[str] = []
    for slug in slugs:
        identity = load_layered_project(slug, layout=selected)
        timestamps.append(identity["created_at"])
        _, versions_dir, manifest_path = _project_paths(slug, selected)
        prefix, rows = _manifest(manifest_path, slug)
        manifested = {row["semantic_version"] for row in rows}
        version_paths = _version_paths(slug, versions_dir, selected)
        discovered = {semantic_version for semantic_version, _ in version_paths}
        missing = sorted(manifested - discovered, key=_semver_key)
        if missing:
            raise _error("manifested version missing", path=manifest_path, project=slug, versions=missing)

        append_rows: list[dict[str, Any]] = []
        loaded_versions: dict[str, dict[str, Any]] = {}
        for semantic_version, version_path in version_paths:
            if semantic_version in manifested:
                version = load_industry_version(slug, semantic_version, layout=selected)
            else:
                try:
                    version = json.loads(version_path.read_text(encoding="utf-8"))
                except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                    raise _error("invalid version JSON", path=version_path, project=slug) from exc
                if not isinstance(version, dict):
                    raise _error("version must be an object", path=version_path, project=slug)
                _validate_version_identity(
                    version,
                    slug=slug,
                    semantic_version=semantic_version,
                    identity=identity,
                    path=version_path,
                )
                calculated_hash = content_sha256(version, excluded_paths={("content_hash",)})
                embedded_hash = version.get("content_hash")
                if embedded_hash not in {"0" * 64, calculated_hash}:
                    raise _error("content hash mismatch", path=version_path, project=slug, version=semantic_version)
                version = dict(version)
                version["content_hash"] = calculated_hash
                validate_v2_1_schema_payload("industry_research_version_v2_1", version, layout=selected)
                validate_industry_version_semantics(version)
                targets.append((version_path, _json_bytes(version)))
                planned_versions.append(f"{slug}@{semantic_version}")
                append_rows.append(
                    {
                        "version_id": version["version_id"],
                        "semantic_version": semantic_version,
                        "parent_version_id": version["parent_version_id"],
                        "relative_path": f"versions/v{semantic_version}.json",
                        "content_hash": calculated_hash,
                        "created_at": version["created_at"],
                    }
                )
            loaded_versions[semantic_version] = version
            timestamps.append(version["created_at"])

        if not loaded_versions:
            raise _error("project has no versions", path=versions_dir, project=slug)
        for semantic_version, version in loaded_versions.items():
            try:
                collect_lineage_version_ids(
                    version,
                    project_slug=slug,
                    known_semantic_versions=loaded_versions,
                    load_version=lambda parent_semver: loaded_versions[parent_semver],
                )
            except LineageError as exc:
                raise _error(
                    exc.reason,
                    path=versions_dir / f"v{semantic_version}.json",
                    project=slug,
                    semantic_version=semantic_version,
                    **exc.details,
                ) from exc
        current_id = identity["current_version"]
        current_matches = [version for version in loaded_versions.values() if version["version_id"] == current_id]
        if len(current_matches) != 1:
            raise _error("identity current_version mismatch", path=selected.project_dir(slug) / "project.json", project=slug)
        known_version_ids = {version["version_id"] for version in loaded_versions.values()}
        for pointer_name in ("latest_reviewed_version", "latest_published_version"):
            pointer = identity[pointer_name]
            if pointer is not None and pointer not in known_version_ids:
                raise _error(
                    f"identity {pointer_name} mismatch",
                    path=selected.project_dir(slug) / "project.json",
                    project=slug,
                )
        current = current_matches[0]

        if append_rows:
            suffix = b"".join(
                (json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
                for row in sorted(append_rows, key=lambda row: _semver_key(row["semantic_version"]))
            )
            separator = b"" if not prefix or prefix.endswith(b"\n") else b"\n"
            targets.append((manifest_path, prefix + separator + suffix))

        index_rows.append(
            {
                "project_id": identity["project_id"],
                "project_slug": slug,
                "title": identity["title"],
                "research_layer": identity["research_layer"],
                "current_lifecycle_state": identity["current_lifecycle_state"],
                "evidence_stage": current["snapshot"]["evidence_stage"],
                "conclusion_status": current["snapshot"]["conclusion_status"],
                "current_version": current_id,
                "latest_reviewed_version": identity["latest_reviewed_version"],
                "latest_published_version": identity["latest_published_version"],
                "relative_path": f"projects/{slug}/project.json",
            }
        )

    index = {
        "schema_version": "2.1.0",
        "artifact_kind": "research_project_index",
        "generated_at": max(timestamps, key=_timestamp_key),
        "projects": index_rows,
    }
    validate_v2_1_schema_payload("research_project_index_v2_1", index, layout=selected)
    index_bytes = _json_bytes(index)
    if not selected.index_path.is_file() or selected.index_path.read_bytes() != index_bytes:
        targets.append((selected.index_path, index_bytes))
    for path, _ in targets:
        _safe(path, selected, allow_missing=True)
    if write:
        _commit(targets, selected)
    return {
        "status": "written" if write else "planned",
        "projects": slugs,
        "versions": planned_versions,
        "index": str(selected.index_path.relative_to(selected.root)),
    }


def rebuild_layered_index(
    write: bool,
    layout: LayeredResearchLayout | None = None,
) -> dict[str, object]:
    selected = LayeredResearchLayout.default() if layout is None else layout
    with layered_storage_lock(selected, exclusive=True):
        return _rebuild_layered_index_unlocked(write, selected)


__all__ = ["rebuild_layered_index"]
