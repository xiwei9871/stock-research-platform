from __future__ import annotations

import copy
import hashlib
import hmac
import json
import os
import re
import stat
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from types import MappingProxyType
from typing import Any


_SCHEMA_VERSION = "theme_research_report_manifest_v1"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_TOP_LEVEL_FIELDS = {
    "schema_version",
    "theme_id",
    "version",
    "title",
    "summary",
    "generated_at",
    "generator",
    "artifacts",
    "metadata",
}


@dataclass(frozen=True)
class ReportArtifact:
    relative_path: str
    sha256: str
    size_bytes: int


@dataclass(frozen=True)
class ThemeResearchReportManifest:
    theme_id: str
    version: str
    title: str
    summary: str
    generated_at: datetime
    generator_name: str
    generator_version: str
    markdown: ReportArtifact
    pdf: ReportArtifact | None
    manifest_relative_path: str
    manifest_sha256: str
    metadata: Mapping[str, Any]


@dataclass(frozen=True)
class ReportManifestLimits:
    max_manifest_bytes: int
    max_markdown_bytes: int
    max_pdf_bytes: int

    def __post_init__(self) -> None:
        values = (
            self.max_manifest_bytes,
            self.max_markdown_bytes,
            self.max_pdf_bytes,
        )
        if any(
            isinstance(value, bool) or not isinstance(value, int) or value <= 0
            for value in values
        ):
            raise ValueError("all report manifest limits must be positive integers")


class ReportManifestError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = copy.deepcopy(details) if details is not None else None


def metadata_to_jsonable(metadata: Mapping[str, Any]) -> dict[str, Any]:
    """Return a detached dict/list snapshot suitable for JSON persistence."""
    return {key: _metadata_value_to_jsonable(value) for key, value in metadata.items()}


def load_report_manifest(
    manifest_path: str | os.PathLike[str],
    *,
    report_root: str | os.PathLike[str],
    limits: ReportManifestLimits,
) -> ThemeResearchReportManifest:
    root = _absolute_without_resolving(report_root)
    manifest = _absolute_without_resolving(manifest_path)
    try:
        manifest_relative = manifest.relative_to(root)
    except ValueError as exc:
        raise ReportManifestError(
            "MANIFEST_OUTSIDE_ROOT",
            "manifest must be located under the report root",
        ) from exc
    if len(manifest_relative.parts) != 3:
        raise ReportManifestError(
            "MANIFEST_OUTSIDE_ROOT",
            "manifest must be stored at <report_root>/<theme_id>/<version>/<file>",
        )

    directory_theme, directory_version, manifest_name = manifest_relative.parts
    root_fd = _open_directory(root, code="REPORT_ROOT_INVALID", label="report root")
    theme_fd: int | None = None
    version_fd: int | None = None
    try:
        theme_fd = _open_child_directory(
            root_fd,
            directory_theme,
            code="DIRECTORY_INVALID",
            label="theme directory",
        )
        version_fd = _open_child_directory(
            theme_fd,
            directory_version,
            code="DIRECTORY_INVALID",
            label="version directory",
        )
        return _load_report_manifest_from_version_directory(
            manifest_name=manifest_name,
            manifest_relative=manifest_relative,
            directory_theme=directory_theme,
            directory_version=directory_version,
            version_fd=version_fd,
            limits=limits,
        )
    finally:
        _safe_close(version_fd)
        _safe_close(theme_fd)
        _safe_close(root_fd)


def _load_report_manifest_from_version_directory(
    *,
    manifest_name: str,
    manifest_relative: Path,
    directory_theme: str,
    directory_version: str,
    version_fd: int,
    limits: ReportManifestLimits,
) -> ThemeResearchReportManifest:
    manifest_bytes = _read_regular_file_limited(
        manifest_name,
        parent_fd=version_fd,
        max_bytes=limits.max_manifest_bytes,
        invalid_code="MANIFEST_INVALID",
        missing_code="MANIFEST_INVALID",
        too_large_code="MANIFEST_TOO_LARGE",
        label="manifest",
    )
    manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()

    try:
        manifest_text = manifest_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ReportManifestError(
            "MANIFEST_INVALID_UTF8",
            "manifest must contain valid UTF-8",
        ) from exc
    try:
        payload = json.loads(manifest_text, parse_constant=_reject_json_constant)
    except (json.JSONDecodeError, ValueError, RecursionError) as exc:
        raise ReportManifestError(
            "MANIFEST_INVALID_JSON",
            "manifest must contain valid JSON",
        ) from exc
    _validate_json_depth(payload)
    if not isinstance(payload, dict):
        raise ReportManifestError(
            "MANIFEST_INVALID_SHAPE",
            "manifest JSON must be an object",
        )

    unknown_fields = sorted(set(payload) - _TOP_LEVEL_FIELDS)
    if unknown_fields:
        raise ReportManifestError(
            "UNKNOWN_TOP_LEVEL_FIELD",
            "manifest contains unsupported top-level fields",
            {"fields": unknown_fields},
        )
    if payload.get("schema_version") != _SCHEMA_VERSION:
        raise ReportManifestError(
            "UNSUPPORTED_SCHEMA_VERSION",
            "manifest schema_version is unsupported",
            {"schema_version": payload.get("schema_version")},
        )

    theme_id = _required_text(payload, "theme_id")
    version = _required_text(payload, "version")
    title = _required_text(payload, "title")
    summary = _text(payload, "summary")
    generated_at = _generated_at(payload.get("generated_at"))
    generator_name, generator_version = _generator(payload.get("generator"))
    metadata = payload.get("metadata")
    if not isinstance(metadata, dict):
        raise ReportManifestError("METADATA_INVALID", "metadata must be an object")
    if theme_id != directory_theme or version != directory_version:
        raise ReportManifestError(
            "DIRECTORY_MISMATCH",
            "manifest theme_id and version must match their directory names",
            {
                "directory_theme_id": directory_theme,
                "directory_version": directory_version,
                "manifest_theme_id": theme_id,
                "manifest_version": version,
            },
        )

    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, dict):
        raise ReportManifestError("ARTIFACT_ENTRY_INVALID", "artifacts must be an object")
    if "markdown" not in artifacts:
        raise ReportManifestError("MARKDOWN_REQUIRED", "a markdown artifact is required")
    if set(artifacts) - {"markdown", "pdf"}:
        raise ReportManifestError(
            "ARTIFACT_ENTRY_INVALID",
            "artifacts contains unsupported entries",
        )

    markdown = _load_artifact(
        artifacts["markdown"],
        version_fd=version_fd,
        max_bytes=limits.max_markdown_bytes,
        label="markdown",
    )
    pdf = None
    if "pdf" in artifacts:
        pdf = _load_artifact(
            artifacts["pdf"],
            version_fd=version_fd,
            max_bytes=limits.max_pdf_bytes,
            label="pdf",
        )
    return ThemeResearchReportManifest(
        theme_id=theme_id,
        version=version,
        title=title,
        summary=summary,
        generated_at=generated_at,
        generator_name=generator_name,
        generator_version=generator_version,
        markdown=markdown,
        pdf=pdf,
        manifest_relative_path=manifest_relative.as_posix(),
        manifest_sha256=manifest_sha256,
        metadata=_freeze_json_object(metadata),
    )


def _absolute_without_resolving(path: str | os.PathLike[str]) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"invalid JSON constant: {value}")


def _validate_json_depth(payload: Any, *, max_depth: int = 64) -> None:
    pending = [(payload, 0)]
    while pending:
        value, depth = pending.pop()
        if depth > max_depth:
            raise ReportManifestError(
                "MANIFEST_TOO_DEEPLY_NESTED",
                "manifest JSON exceeds the supported nesting depth",
            )
        if isinstance(value, dict):
            pending.extend((child, depth + 1) for child in value.values())
        elif isinstance(value, list):
            pending.extend((child, depth + 1) for child in value)


def _freeze_json_object(value: dict[str, Any]) -> Mapping[str, Any]:
    return MappingProxyType({key: _freeze_json_value(child) for key, child in value.items()})


def _freeze_json_value(value: Any) -> Any:
    if isinstance(value, dict):
        return _freeze_json_object(value)
    if isinstance(value, list):
        return tuple(_freeze_json_value(child) for child in value)
    return value


def _metadata_value_to_jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _metadata_value_to_jsonable(child) for key, child in value.items()}
    if isinstance(value, tuple):
        return [_metadata_value_to_jsonable(child) for child in value]
    return value


def _open_directory(path: Path, *, code: str, label: str) -> int:
    try:
        expected_stat = path.lstat()
    except OSError as exc:
        raise ReportManifestError(code, f"{label} is unavailable") from exc
    if stat.S_ISLNK(expected_stat.st_mode) or not stat.S_ISDIR(expected_stat.st_mode):
        raise ReportManifestError(code, f"{label} must be a real directory")
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
        opened_stat = os.fstat(descriptor)
    except OSError as exc:
        if "descriptor" in locals():
            _safe_close(descriptor)
        raise ReportManifestError(code, f"{label} could not be opened safely") from exc
    if not stat.S_ISDIR(opened_stat.st_mode) or not _same_file(expected_stat, opened_stat):
        _safe_close(descriptor)
        raise ReportManifestError(code, f"{label} changed during validation")
    return descriptor


def _open_child_directory(
    parent_fd: int,
    name: str,
    *,
    code: str,
    label: str,
) -> int:
    try:
        expected_stat = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except OSError as exc:
        raise ReportManifestError(code, f"{label} is unavailable") from exc
    if stat.S_ISLNK(expected_stat.st_mode) or not stat.S_ISDIR(expected_stat.st_mode):
        raise ReportManifestError(code, f"{label} must be a real directory")
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(name, flags, dir_fd=parent_fd)
        opened_stat = os.fstat(descriptor)
    except OSError as exc:
        if "descriptor" in locals():
            _safe_close(descriptor)
        raise ReportManifestError(code, f"{label} could not be opened safely") from exc
    if not stat.S_ISDIR(opened_stat.st_mode) or not _same_file(expected_stat, opened_stat):
        _safe_close(descriptor)
        raise ReportManifestError(code, f"{label} changed during validation")
    return descriptor


def _read_regular_file_limited(
    name: str,
    *,
    parent_fd: int,
    max_bytes: int,
    invalid_code: str,
    missing_code: str,
    too_large_code: str,
    label: str,
) -> bytes:
    try:
        expected_stat = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError as exc:
        raise ReportManifestError(missing_code, f"{label} file is missing") from exc
    except OSError as exc:
        raise ReportManifestError(invalid_code, f"{label} file is unavailable") from exc
    if stat.S_ISLNK(expected_stat.st_mode) or not stat.S_ISREG(expected_stat.st_mode):
        raise ReportManifestError(invalid_code, f"{label} must be a regular non-symlink file")
    if expected_stat.st_size > max_bytes:
        raise ReportManifestError(too_large_code, f"{label} exceeds its byte limit")

    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(name, flags, dir_fd=parent_fd)
    except OSError as exc:
        raise ReportManifestError(invalid_code, f"{label} file could not be opened safely") from exc
    try:
        try:
            opened_stat = os.fstat(descriptor)
        except OSError as exc:
            raise ReportManifestError(invalid_code, f"{label} file could not be inspected") from exc
        if not stat.S_ISREG(opened_stat.st_mode) or not _same_file(expected_stat, opened_stat):
            raise ReportManifestError(invalid_code, f"{label} must be a regular file")
        if opened_stat.st_size > max_bytes:
            raise ReportManifestError(too_large_code, f"{label} exceeds its byte limit")
        try:
            data = _read_fd_limited(descriptor, max_bytes)
        except OSError as exc:
            raise ReportManifestError(invalid_code, f"{label} file could not be read") from exc
    finally:
        _safe_close(descriptor)
    if len(data) > max_bytes:
        raise ReportManifestError(too_large_code, f"{label} exceeds its byte limit")
    return data


def _read_fd_limited(descriptor: int, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while total <= max_bytes:
        chunk = os.read(descriptor, min(64 * 1024, max_bytes + 1 - total))
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
    return b"".join(chunks)


def _same_file(expected: os.stat_result, opened: os.stat_result) -> bool:
    return (expected.st_dev, expected.st_ino) == (opened.st_dev, opened.st_ino)


def _safe_close(descriptor: int | None) -> None:
    if descriptor is None:
        return
    try:
        os.close(descriptor)
    except OSError:
        pass


def _required_text(payload: dict[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ReportManifestError("FIELD_INVALID", f"{field} must be a non-empty string")
    return value


def _text(payload: dict[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str):
        raise ReportManifestError("FIELD_INVALID", f"{field} must be a string")
    return value


def _generated_at(value: Any) -> datetime:
    if not isinstance(value, str) or not value:
        raise ReportManifestError(
            "GENERATED_AT_INVALID",
            "generated_at must be a timezone-aware ISO 8601 string",
        )
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ReportManifestError(
            "GENERATED_AT_INVALID",
            "generated_at must be a timezone-aware ISO 8601 string",
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ReportManifestError(
            "GENERATED_AT_INVALID",
            "generated_at must include a timezone offset",
        )
    return parsed


def _generator(value: Any) -> tuple[str, str]:
    if not isinstance(value, dict):
        raise ReportManifestError("FIELD_INVALID", "generator must be an object")
    name = value.get("name")
    version = value.get("version")
    if not isinstance(name, str) or not name.strip():
        raise ReportManifestError("FIELD_INVALID", "generator.name must be a non-empty string")
    if not isinstance(version, str) or not version.strip():
        raise ReportManifestError(
            "FIELD_INVALID", "generator.version must be a non-empty string"
        )
    return name, version


def _load_artifact(
    entry: Any,
    *,
    version_fd: int,
    max_bytes: int,
    label: str,
) -> ReportArtifact:
    if not isinstance(entry, dict) or set(entry) != {"path", "sha256"}:
        raise ReportManifestError(
            "ARTIFACT_ENTRY_INVALID",
            f"{label} artifact must contain only path and sha256",
        )
    relative_path = entry.get("path")
    expected_sha256 = entry.get("sha256")
    if not isinstance(relative_path, str) or not isinstance(expected_sha256, str):
        raise ReportManifestError(
            "ARTIFACT_ENTRY_INVALID",
            f"{label} path and sha256 must be strings",
        )
    if not _SHA256_RE.fullmatch(expected_sha256):
        raise ReportManifestError(
            "ARTIFACT_ENTRY_INVALID",
            f"{label} sha256 must be 64 lowercase hexadecimal characters",
        )
    if (
        not relative_path
        or relative_path in {".", ".."}
        or relative_path.startswith("/")
        or "/" in relative_path
        or "\\" in relative_path
        or "\x00" in relative_path
    ):
        raise ReportManifestError(
            "ARTIFACT_PATH_INVALID",
            f"{label} path must name a direct child of the version directory",
        )

    try:
        expected_stat = os.stat(relative_path, dir_fd=version_fd, follow_symlinks=False)
    except FileNotFoundError as exc:
        raise ReportManifestError(
            "ARTIFACT_MISSING",
            f"declared {label} artifact is missing",
        ) from exc
    except OSError as exc:
        raise ReportManifestError(
            "ARTIFACT_FILE_INVALID",
            f"declared {label} artifact is unavailable",
        ) from exc
    if stat.S_ISLNK(expected_stat.st_mode) or not stat.S_ISREG(expected_stat.st_mode):
        raise ReportManifestError(
            "ARTIFACT_FILE_INVALID",
            f"declared {label} artifact must be a regular non-symlink file",
        )
    if expected_stat.st_size > max_bytes:
        raise ReportManifestError(
            "ARTIFACT_TOO_LARGE",
            f"declared {label} artifact exceeds its byte limit",
        )

    digest = hashlib.sha256()
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(relative_path, flags, dir_fd=version_fd)
    except OSError as exc:
        raise ReportManifestError(
            "ARTIFACT_FILE_INVALID",
            f"declared {label} artifact could not be opened safely",
        ) from exc
    try:
        try:
            opened_stat = os.fstat(descriptor)
        except OSError as exc:
            raise ReportManifestError(
                "ARTIFACT_FILE_INVALID",
                f"declared {label} artifact could not be inspected",
            ) from exc
        if not stat.S_ISREG(opened_stat.st_mode) or not _same_file(expected_stat, opened_stat):
            raise ReportManifestError(
                "ARTIFACT_FILE_INVALID",
                f"declared {label} artifact must be a regular file",
            )
        if opened_stat.st_size > max_bytes:
            raise ReportManifestError(
                "ARTIFACT_TOO_LARGE",
                f"declared {label} artifact exceeds its byte limit",
            )
        size_bytes = 0
        try:
            while chunk := os.read(descriptor, 1024 * 1024):
                size_bytes += len(chunk)
                if size_bytes > max_bytes:
                    raise ReportManifestError(
                        "ARTIFACT_TOO_LARGE",
                        f"declared {label} artifact exceeds its byte limit",
                    )
                digest.update(chunk)
        except OSError as exc:
            raise ReportManifestError(
                "ARTIFACT_FILE_INVALID",
                f"declared {label} artifact could not be read",
            ) from exc
    finally:
        _safe_close(descriptor)
    actual_sha256 = digest.hexdigest()
    if not hmac.compare_digest(actual_sha256, expected_sha256):
        raise ReportManifestError(
            "ARTIFACT_CHECKSUM_MISMATCH",
            f"declared {label} artifact checksum does not match",
            {"artifact": label, "path": relative_path},
        )
    return ReportArtifact(
        relative_path=relative_path,
        sha256=actual_sha256,
        size_bytes=size_bytes,
    )
