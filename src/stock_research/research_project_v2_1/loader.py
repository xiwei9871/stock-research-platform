from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
import errno
import fcntl
import json
import os
from pathlib import Path
import re
import stat
import threading
from typing import Any

from stock_research.research_project_v2.canonical import content_sha256
from stock_research.research_project_v2.errors import ResearchProjectV2Error
from stock_research.research_project_v2 import loader as r1_loader
from stock_research.research_project_v2_1.layout import LayeredResearchLayout
from stock_research.research_project_v2_1.schema import validate_v2_1_schema_payload


_PROJECT_SLUG_PATTERN = re.compile(r"[a-z0-9]+(?:[-_][a-z0-9]+)*")
_SEMANTIC_VERSION_PATTERN = re.compile(
    r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)"
)
_VERSION_FILE_PATTERN = re.compile(rf"v({_SEMANTIC_VERSION_PATTERN.pattern})\.json")
_SHA256_PATTERN = re.compile(r"[a-f0-9]{64}")
_RFC3339_PATTERN = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]+)?(?:Z|[+-][0-9]{2}:[0-9]{2})"
)
_MANIFEST_FIELDS = {
    "version_id",
    "semantic_version",
    "parent_version_id",
    "relative_path",
    "content_hash",
    "created_at",
}
_LOCK_NAME = ".maintenance.lock"
_LOCK_STATE = threading.local()


def load_r1_index() -> dict[str, Any]:
    return r1_loader.load_index()


def load_r1_version(project_slug: str, semantic_version: str) -> dict[str, Any]:
    return r1_loader.load_version(project_slug, semantic_version)


def _error(code: str, message: str, **details: object) -> ResearchProjectV2Error:
    return ResearchProjectV2Error(message, code=code, details=details)


def _layout_or_default(layout: LayeredResearchLayout | None) -> LayeredResearchLayout:
    return LayeredResearchLayout.default() if layout is None else layout


def _lock_error(layout: LayeredResearchLayout, reason: str) -> ResearchProjectV2Error:
    return _error(
        "RESEARCH_PROJECT_V2_1_STORAGE_ERROR",
        "Unsafe layered research maintenance lock",
        path=str(layout.root / _LOCK_NAME),
        reason=reason,
    )


def _open_lock_fd(layout: LayeredResearchLayout) -> int:
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    cloexec = getattr(os, "O_CLOEXEC", 0)
    directory = getattr(os, "O_DIRECTORY", 0)
    try:
        root_fd = os.open(layout.root, os.O_RDONLY | directory | nofollow | cloexec)
    except OSError as exc:
        raise _lock_error(layout, "unsafe maintenance lock") from exc
    try:
        flags = os.O_RDWR | nofollow | cloexec
        try:
            lock_fd = os.open(
                _LOCK_NAME,
                flags | os.O_CREAT | os.O_EXCL,
                0o600,
                dir_fd=root_fd,
            )
        except OSError as exc:
            if exc.errno != errno.EEXIST:
                raise
            lock_fd = os.open(_LOCK_NAME, flags, dir_fd=root_fd)
    except OSError as exc:
        raise _lock_error(layout, "unsafe maintenance lock") from exc
    finally:
        os.close(root_fd)
    lock_stat = os.fstat(lock_fd)
    if (
        not stat.S_ISREG(lock_stat.st_mode)
        or stat.S_IMODE(lock_stat.st_mode) != 0o600
        or lock_stat.st_uid != os.geteuid()
    ):
        os.close(lock_fd)
        raise _lock_error(layout, "unsafe maintenance lock")
    return lock_fd


def _verify_lock_binding(
    layout: LayeredResearchLayout,
    lock_fd: int,
) -> None:
    descriptor_stat = os.fstat(lock_fd)
    try:
        path_stat = os.lstat(layout.root / _LOCK_NAME)
    except OSError as exc:
        raise _lock_error(layout, "maintenance lock path rebound") from exc
    if (
        not stat.S_ISREG(path_stat.st_mode)
        or path_stat.st_dev != descriptor_stat.st_dev
        or path_stat.st_ino != descriptor_stat.st_ino
        or stat.S_IMODE(path_stat.st_mode) != 0o600
        or path_stat.st_uid != os.geteuid()
    ):
        raise _lock_error(layout, "maintenance lock path rebound")


@contextmanager
def layered_storage_lock(
    layout: LayeredResearchLayout,
    *,
    exclusive: bool,
):
    """Hold a stable process/thread-reentrant lock for one layered transaction."""
    if not layout.root.exists():
        if exclusive:
            raise _lock_error(layout, "layered root missing")
        yield
        return
    key = str(layout.root.absolute())
    states = getattr(_LOCK_STATE, "states", None)
    if states is None:
        states = {}
        _LOCK_STATE.states = states
    existing = states.get(key)
    if existing is not None:
        if exclusive and existing["mode"] != "exclusive":
            raise _lock_error(layout, "cannot upgrade shared maintenance lock")
        existing["depth"] += 1
        try:
            yield
        finally:
            existing["depth"] -= 1
        return

    lock_fd = _open_lock_fd(layout)
    mode = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
    try:
        fcntl.flock(lock_fd, mode)
        _verify_lock_binding(layout, lock_fd)
        states[key] = {
            "fd": lock_fd,
            "mode": "exclusive" if exclusive else "shared",
            "depth": 1,
        }
        try:
            yield
            _verify_lock_binding(layout, lock_fd)
        finally:
            states.pop(key, None)
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
    finally:
        os.close(lock_fd)


def _is_safe_managed_path(path: Path, layout: LayeredResearchLayout) -> bool:
    if layout.root.is_symlink():
        return False
    try:
        relative = path.relative_to(layout.root)
    except ValueError:
        return False
    current = layout.root
    for part in relative.parts:
        if part in {".", ".."}:
            return False
        current /= part
        if current.is_symlink():
            return False
    try:
        path.resolve(strict=False).relative_to(layout.root.resolve(strict=False))
    except (OSError, ValueError):
        return False
    return True


def _is_safe_project_dir(path: Path, layout: LayeredResearchLayout) -> bool:
    return (
        _PROJECT_SLUG_PATTERN.fullmatch(path.name) is not None
        and _is_safe_managed_path(path, layout)
        and path.is_dir()
        and _is_safe_managed_path(path / "project.json", layout)
        and (path / "project.json").is_file()
    )


def _identity_path(project_slug: str, layout: LayeredResearchLayout) -> Path:
    return layout.project_dir(project_slug) / "project.json"


def _versions_dir(project_slug: str, layout: LayeredResearchLayout) -> Path:
    return layout.project_dir(project_slug) / "versions"


def _semver_key(version: str) -> tuple[int, int, int]:
    return tuple(map(int, version.split(".")))


def _version_path(
    project_slug: str,
    semantic_version: str,
    layout: LayeredResearchLayout,
) -> Path:
    return _versions_dir(project_slug, layout) / f"v{semantic_version}.json"


def _project_not_found(project_slug: str) -> ResearchProjectV2Error:
    return _error(
        "RESEARCH_PROJECT_V2_1_PROJECT_NOT_FOUND",
        f"Layered research project not found: {project_slug}",
        project=project_slug,
    )


def _version_not_found(
    project_slug: str, semantic_version: str | None
) -> ResearchProjectV2Error:
    return _error(
        "RESEARCH_PROJECT_V2_1_VERSION_NOT_FOUND",
        f"Layered research project version not found: {project_slug} {semantic_version or ''}".rstrip(),
        project=project_slug,
        version=semantic_version,
    )


def _immutability_violation(
    project_slug: str,
    semantic_version: str,
    reason: str,
    **details: object,
) -> ResearchProjectV2Error:
    return _error(
        "RESEARCH_PROJECT_V2_1_IMMUTABILITY_VIOLATION",
        f"Immutable layered research project version failed verification: {reason}",
        project=project_slug,
        version=semantic_version,
        reason=reason,
        **details,
    )


def _read_managed_bytes(path: Path, layout: LayeredResearchLayout) -> bytes:
    try:
        relative = path.relative_to(layout.root)
    except ValueError as exc:
        raise OSError("managed path is outside the trusted root") from exc
    parts = relative.parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise OSError("managed path contains an invalid component")

    nofollow = getattr(os, "O_NOFOLLOW", 0)
    cloexec = getattr(os, "O_CLOEXEC", 0)
    directory = getattr(os, "O_DIRECTORY", 0)
    directory_flags = os.O_RDONLY | directory | nofollow | cloexec
    file_flags = os.O_RDONLY | nofollow | cloexec
    opened_fds: list[int] = []
    final_fd: int | None = None
    try:
        parent_fd = os.open(layout.root, directory_flags)
        opened_fds.append(parent_fd)
        for component in parts[:-1]:
            child_fd = os.open(component, directory_flags, dir_fd=parent_fd)
            if not stat.S_ISDIR(os.fstat(child_fd).st_mode):
                os.close(child_fd)
                raise OSError("managed path component is not a directory")
            opened_fds.append(child_fd)
            parent_fd = child_fd
        final_fd = os.open(parts[-1], file_flags, dir_fd=parent_fd)
        if not stat.S_ISREG(os.fstat(final_fd).st_mode):
            raise OSError("managed path target is not a regular file")
        with os.fdopen(final_fd, "rb") as handle:
            final_fd = None
            return handle.read()
    finally:
        if final_fd is not None:
            os.close(final_fd)
        for fd in reversed(opened_fds):
            os.close(fd)


def _read_json_object(
    path: Path,
    schema_name: str,
    *,
    layout: LayeredResearchLayout,
) -> dict[str, Any]:
    if not _is_safe_managed_path(path, layout):
        raise _error(
            "RESEARCH_PROJECT_V2_1_STORAGE_ERROR",
            "Unsafe layered research storage path",
            path=str(path),
            reason="unsafe managed path",
        )
    try:
        payload = json.loads(_read_managed_bytes(path, layout).decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise _error(
            "RESEARCH_PROJECT_V2_1_READ_ERROR",
            "Layered research JSON is missing, unreadable, or invalid",
            path=str(path),
            reason=type(exc).__name__,
        ) from exc
    if not isinstance(payload, dict):
        raise _error(
            "RESEARCH_PROJECT_V2_1_READ_ERROR",
            "Layered research JSON must contain an object",
            path=str(path),
            reason="payload is not an object",
        )
    validate_v2_1_schema_payload(schema_name, payload, layout=layout)
    return payload


def _require_identity_path(project_slug: str, layout: LayeredResearchLayout) -> Path:
    if not _PROJECT_SLUG_PATTERN.fullmatch(project_slug):
        raise _project_not_found(project_slug)
    path = _identity_path(project_slug, layout)
    if not _is_safe_managed_path(path, layout) or not path.is_file():
        raise _project_not_found(project_slug)
    return path


def _discover_semantic_versions(
    project_slug: str, layout: LayeredResearchLayout
) -> list[str]:
    directory = _versions_dir(project_slug, layout)
    if not _is_safe_managed_path(directory, layout) or not directory.is_dir():
        return []
    versions: list[str] = []
    try:
        entries = directory.iterdir()
        for path in entries:
            match = _VERSION_FILE_PATTERN.fullmatch(path.name)
            if match and _is_safe_managed_path(path, layout) and path.is_file():
                versions.append(match.group(1))
    except OSError:
        return []
    return sorted(versions, key=_semver_key)


def _list_layered_project_slugs_unlocked(
    *, layout: LayeredResearchLayout | None = None
) -> list[str]:
    selected = _layout_or_default(layout)
    if not _is_safe_managed_path(selected.projects_dir, selected) or not selected.projects_dir.is_dir():
        return []
    try:
        return sorted(
            path.name for path in selected.projects_dir.iterdir() if _is_safe_project_dir(path, selected)
        )
    except OSError:
        return []


def list_layered_project_slugs(
    *, layout: LayeredResearchLayout | None = None
) -> list[str]:
    selected = _layout_or_default(layout)
    with layered_storage_lock(selected, exclusive=False):
        return _list_layered_project_slugs_unlocked(layout=selected)


def _load_layered_project_unlocked(
    project_slug: str, *, layout: LayeredResearchLayout | None = None
) -> dict[str, Any]:
    selected = _layout_or_default(layout)
    path = _require_identity_path(project_slug, selected)
    identity = _read_json_object(
        path, "research_project_identity_v2_1", layout=selected
    )
    expected_values = {
        "project_slug": project_slug,
        "project_id": f"research_project:{project_slug}",
    }
    for field, expected in expected_values.items():
        actual = identity.get(field)
        if actual != expected:
            raise _error(
                "RESEARCH_PROJECT_V2_1_IDENTITY_INVALID",
                f"Layered research identity {field} is not canonically bound",
                project=project_slug,
                field=field,
                expected=expected,
                actual=actual,
            )
    return identity


def load_layered_project(
    project_slug: str, *, layout: LayeredResearchLayout | None = None
) -> dict[str, Any]:
    selected = _layout_or_default(layout)
    with layered_storage_lock(selected, exclusive=False):
        return _load_layered_project_unlocked(project_slug, layout=selected)


def list_layered_versions(
    project_slug: str, *, layout: LayeredResearchLayout | None = None
) -> list[str]:
    selected = _layout_or_default(layout)
    with layered_storage_lock(selected, exclusive=False):
        _load_layered_project_unlocked(project_slug, layout=selected)
        return _discover_semantic_versions(project_slug, selected)


def _current_semantic_version(identity: dict[str, Any], project_slug: str) -> str:
    pointer = identity.get("current_version")
    prefix = f"research_version:{project_slug}:"
    if not isinstance(pointer, str) or not pointer.startswith(prefix):
        raise _version_not_found(project_slug, None)
    semantic_version = pointer.removeprefix(prefix)
    if not _SEMANTIC_VERSION_PATTERN.fullmatch(semantic_version):
        raise _version_not_found(project_slug, semantic_version)
    return semantic_version


def _read_manifest_rows(
    project_slug: str,
    semantic_version: str,
    path: Path,
    layout: LayeredResearchLayout,
) -> list[dict[str, Any]]:
    try:
        lines = _read_managed_bytes(path, layout).decode("utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise _immutability_violation(
            project_slug, semantic_version, "version manifest is missing or unreadable"
        ) from exc
    rows: list[dict[str, Any]] = []
    seen_semantic_versions: set[object] = set()
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise _immutability_violation(
                project_slug, semantic_version, f"manifest row {line_number} is not valid JSON"
            ) from exc
        if not isinstance(row, dict):
            raise _immutability_violation(
                project_slug, semantic_version, f"manifest row {line_number} is not an object"
            )
        if set(row) != _MANIFEST_FIELDS:
            raise _immutability_violation(
                project_slug,
                semantic_version,
                f"manifest fields mismatch at row {line_number}",
            )
        row_semantic_version = row["semantic_version"]
        if (
            not isinstance(row_semantic_version, str)
            or not _SEMANTIC_VERSION_PATTERN.fullmatch(row_semantic_version)
        ):
            raise _immutability_violation(
                project_slug,
                semantic_version,
                f"manifest semantic_version is invalid at row {line_number}",
            )
        if row_semantic_version in seen_semantic_versions:
            raise _immutability_violation(
                project_slug,
                semantic_version,
                f"duplicate manifest semantic_version at row {line_number}",
            )
        seen_semantic_versions.add(row_semantic_version)
        expected_version_id = (
            f"research_version:{project_slug}:{row_semantic_version}"
        )
        if (
            not isinstance(row["version_id"], str)
            or row["version_id"] != expected_version_id
        ):
            raise _immutability_violation(
                project_slug,
                semantic_version,
                f"manifest version_id mismatch at row {line_number}",
                expected=expected_version_id,
                actual=row["version_id"],
            )
        if row["parent_version_id"] is not None and not isinstance(
            row["parent_version_id"], str
        ):
            raise _immutability_violation(
                project_slug,
                semantic_version,
                f"manifest parent_version_id is invalid at row {line_number}",
            )
        expected_relative_path = f"versions/v{row_semantic_version}.json"
        if row["relative_path"] != expected_relative_path:
            raise _immutability_violation(
                project_slug,
                semantic_version,
                f"manifest relative_path mismatch at row {line_number}",
                expected=expected_relative_path,
                actual=row["relative_path"],
            )
        if not isinstance(row["content_hash"], str) or not _SHA256_PATTERN.fullmatch(
            row["content_hash"]
        ):
            raise _immutability_violation(
                project_slug,
                semantic_version,
                f"manifest content_hash is invalid at row {line_number}",
            )
        created_at = row["created_at"]
        if not isinstance(created_at, str) or not _RFC3339_PATTERN.fullmatch(
            created_at
        ):
            raise _immutability_violation(
                project_slug,
                semantic_version,
                f"manifest created_at is invalid at row {line_number}",
            )
        try:
            datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise _immutability_violation(
                project_slug,
                semantic_version,
                f"manifest created_at is invalid at row {line_number}",
            ) from exc
        rows.append(row)
    return rows


def _verify_manifest_and_hash(
    project_slug: str,
    semantic_version: str,
    identity: dict[str, Any],
    version: dict[str, Any],
    manifest_path: Path,
    layout: LayeredResearchLayout,
) -> None:
    if version.get("project_id") != identity.get("project_id"):
        raise _immutability_violation(
            project_slug,
            semantic_version,
            "project_id mismatch",
            expected=identity.get("project_id"),
            actual=version.get("project_id"),
        )
    expected_version_id = f"research_version:{project_slug}:{semantic_version}"
    if version.get("version_id") != expected_version_id:
        raise _immutability_violation(
            project_slug,
            semantic_version,
            "version_id mismatch",
            expected=expected_version_id,
            actual=version.get("version_id"),
        )
    if version.get("semantic_version") != semantic_version:
        raise _immutability_violation(project_slug, semantic_version, "semantic_version mismatch")
    expected_hash = content_sha256(version, excluded_paths={("content_hash",)})
    if version.get("content_hash") != expected_hash:
        raise _immutability_violation(project_slug, semantic_version, "embedded content_hash mismatch")
    if not _is_safe_managed_path(manifest_path, layout):
        raise _immutability_violation(project_slug, semantic_version, "unsafe manifest path")
    rows = _read_manifest_rows(
        project_slug, semantic_version, manifest_path, layout
    )
    matching = [row for row in rows if row.get("semantic_version") == semantic_version]
    if len(matching) != 1:
        raise _immutability_violation(
            project_slug,
            semantic_version,
            f"expected exactly one manifest row, found {len(matching)}",
        )
    row = matching[0]
    expected = {
        "version_id": version.get("version_id"),
        "semantic_version": semantic_version,
        "parent_version_id": version.get("parent_version_id"),
        "relative_path": f"versions/v{semantic_version}.json",
        "content_hash": version.get("content_hash"),
        "created_at": version.get("created_at"),
    }
    for field, value in expected.items():
        if row[field] != value:
            raise _immutability_violation(
                project_slug,
                semantic_version,
                f"manifest {field} mismatch",
                expected=value,
                actual=row[field],
            )


def _load_industry_version_unlocked(
    project_slug: str,
    semantic_version: str | None = None,
    *,
    layout: LayeredResearchLayout | None = None,
) -> dict[str, Any]:
    selected = _layout_or_default(layout)
    if not _PROJECT_SLUG_PATTERN.fullmatch(project_slug):
        raise _project_not_found(project_slug)
    identity = _load_layered_project_unlocked(project_slug, layout=selected)
    if semantic_version is None:
        semantic_version = _current_semantic_version(identity, project_slug)
    elif not _SEMANTIC_VERSION_PATTERN.fullmatch(semantic_version):
        raise _version_not_found(project_slug, semantic_version)
    path = _version_path(project_slug, semantic_version, selected)
    if not _is_safe_managed_path(path, selected) or not path.is_file():
        raise _version_not_found(project_slug, semantic_version)
    version = _read_json_object(path, "industry_research_version_v2_1", layout=selected)
    _verify_manifest_and_hash(
        project_slug,
        semantic_version,
        identity,
        version,
        selected.project_dir(project_slug) / "version_manifest.jsonl",
        selected,
    )
    from stock_research.research_project_v2_1.semantic import validate_industry_version_semantics

    validate_industry_version_semantics(version)
    return version


def load_industry_version(
    project_slug: str,
    semantic_version: str | None = None,
    *,
    layout: LayeredResearchLayout | None = None,
) -> dict[str, Any]:
    selected = _layout_or_default(layout)
    with layered_storage_lock(selected, exclusive=False):
        return _load_industry_version_unlocked(
            project_slug,
            semantic_version,
            layout=selected,
        )


def _load_layered_index_unlocked(
    *, layout: LayeredResearchLayout | None = None
) -> dict[str, Any]:
    selected = _layout_or_default(layout)
    path = selected.index_path
    if not _is_safe_managed_path(path, selected) or not path.is_file():
        raise _error(
            "RESEARCH_PROJECT_V2_1_INDEX_NOT_FOUND",
            "Layered research project index not found",
            artifact="index",
        )
    return _read_json_object(path, "research_project_index_v2_1", layout=selected)


def load_layered_index(
    *, layout: LayeredResearchLayout | None = None
) -> dict[str, Any]:
    selected = _layout_or_default(layout)
    with layered_storage_lock(selected, exclusive=False):
        return _load_layered_index_unlocked(layout=selected)


def _upstream_invalid(reference: dict[str, Any], reason: str) -> ResearchProjectV2Error:
    return _error(
        "RESEARCH_PROJECT_V2_1_UPSTREAM_REFERENCE_INVALID",
        f"Upstream R1 research reference is invalid: {reason}",
        reference=reference.get("upstream_research_ref_id"),
        reason=reason,
        upstream_project_id=reference.get("upstream_project_id"),
        upstream_version_id=reference.get("upstream_version_id"),
    )


def resolve_upstream_r1_version(reference: dict[str, Any]) -> dict[str, Any]:
    if reference.get("upstream_research_layer") is not None:
        raise _upstream_invalid(reference, "upstream_research_layer must be null for R1")
    project_id = reference.get("upstream_project_id")
    version_id = reference.get("upstream_version_id")
    if not isinstance(project_id, str) or not isinstance(version_id, str):
        raise _upstream_invalid(reference, "project or version identity is missing")
    try:
        index = load_r1_index()
        rows = [row for row in index.get("projects", []) if row.get("project_id") == project_id]
        if len(rows) != 1:
            raise _upstream_invalid(reference, f"expected one project row, found {len(rows)}")
        slug = rows[0].get("project_slug")
        prefix = f"research_version:{slug}:"
        if not isinstance(slug, str) or not version_id.startswith(prefix):
            raise _upstream_invalid(reference, "upstream version identity does not match project")
        semantic_version = version_id.removeprefix(prefix)
        if not _SEMANTIC_VERSION_PATTERN.fullmatch(semantic_version):
            raise _upstream_invalid(reference, "upstream version semantic version is invalid")
        version = load_r1_version(slug, semantic_version)
    except ResearchProjectV2Error as exc:
        if exc.code == "RESEARCH_PROJECT_V2_1_UPSTREAM_REFERENCE_INVALID":
            raise
        raise _upstream_invalid(reference, f"version could not be loaded: {exc.code}") from exc
    except (OSError, KeyError, TypeError, ValueError) as exc:
        raise _upstream_invalid(reference, f"version could not be loaded: {type(exc).__name__}") from exc
    if version.get("version_id") != version_id:
        raise _upstream_invalid(reference, "version_id mismatch")
    if version.get("content_hash") != reference.get("upstream_content_hash"):
        raise _upstream_invalid(reference, "content_hash mismatch")
    return version
