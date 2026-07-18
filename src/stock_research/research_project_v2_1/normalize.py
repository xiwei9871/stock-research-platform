from __future__ import annotations

import errno
import os
import re
import secrets
import stat
import unicodedata
from copy import deepcopy
from hashlib import sha256
from pathlib import Path, PurePosixPath
from typing import Any

from stock_research.research_project_v2.canonical import canonical_bytes, content_sha256
from stock_research.research_project_v2.errors import ResearchProjectV2Error
from stock_research.research_project_v2_1.layout import LayeredResearchLayout
from stock_research.research_project_v2_1.parsers import ParserLimits, parse_document_bytes
from stock_research.research_project_v2_1.schema import validate_v2_1_schema_payload


_SPACE = re.compile(r"\s+")
_SHA256 = re.compile(r"^[a-f0-9]{64}$")
_DOCUMENT_ID = re.compile(r"^normalized_document:[a-f0-9]{24}$")
_EXTENSIONS = {
    "application/pdf": "pdf",
    "text/html": "html",
    "text/plain": "txt",
    "application/json": "json",
    "text/csv": "csv",
}
_DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
_FILE_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)


def normalize_text(value: str) -> str:
    """Apply NFKC and collapse all Unicode whitespace to a single space."""
    return _SPACE.sub(" ", unicodedata.normalize("NFKC", value)).strip()


def _error(reason: str, **details: object) -> ResearchProjectV2Error:
    return ResearchProjectV2Error(
        f"Document normalization failed: {reason}",
        code="RESEARCH_PROJECT_V2_1_NORMALIZE_INVALID",
        details=details,
    )


def _storage(reason: str, **details: object) -> ResearchProjectV2Error:
    return ResearchProjectV2Error(
        f"Normalized document storage failed: {reason}",
        code="RESEARCH_PROJECT_V2_1_NORMALIZE_STORAGE_FAILED",
        details=details,
    )


def _parse_limit(reason: str, **details: object) -> ResearchProjectV2Error:
    return ResearchProjectV2Error(
        f"Document parse limit exceeded: {reason}",
        code="RESEARCH_PROJECT_V2_1_PARSE_LIMIT_EXCEEDED",
        details=details,
    )


def _immutability(reason: str, **details: object) -> ResearchProjectV2Error:
    return ResearchProjectV2Error(
        f"Normalized document immutability violation: {reason}",
        code="RESEARCH_PROJECT_V2_1_NORMALIZE_IMMUTABILITY_VIOLATION",
        details=details,
    )


def _same_inode(left: os.stat_result, right: os.stat_result) -> bool:
    return left.st_dev == right.st_dev and left.st_ino == right.st_ino


def _read_fd(
    descriptor: int,
    *,
    max_bytes: int | None = None,
    digest: Any | None = None,
) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = os.read(descriptor, 64 * 1024)
        if not chunk:
            return b"".join(chunks)
        total += len(chunk)
        if max_bytes is not None and total > max_bytes:
            raise _parse_limit("document bytes", max_bytes=max_bytes)
        if digest is not None:
            digest.update(chunk)
        chunks.append(chunk)


def _read_raw(artifact: dict[str, Any], layout: LayeredResearchLayout, limits: ParserLimits) -> bytes:
    media_type = artifact.get("media_type")
    digest = artifact.get("content_sha256")
    byte_count = artifact.get("byte_count")
    raw_value = artifact.get("raw_path")
    if media_type not in _EXTENSIONS or not isinstance(digest, str) or _SHA256.fullmatch(digest) is None:
        raise _error("artifact media type or digest is invalid")
    if not isinstance(byte_count, int) or isinstance(byte_count, bool) or byte_count < 0:
        raise _error("artifact byte_count is invalid")
    if not isinstance(raw_value, str):
        raise _error("artifact raw_path is invalid")
    expected = f"evidence/raw/{digest[:2]}/{digest}.{_EXTENSIONS[media_type]}"
    if raw_value != expected:
        raise _error("artifact raw_path is not canonical", raw_path=raw_value)
    relative = PurePosixPath(raw_value)
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        raise _error("artifact raw_path is unsafe")
    root = layout.root
    if not root.is_absolute():
        raise _error("layout root must be absolute", root=str(root))
    descriptors: list[int] = []
    names: list[str] = []
    file_fd: int | None = None
    live_descriptors: list[int] = []
    live_file_fd: int | None = None
    try:
        descriptors.append(os.open("/", _DIR_FLAGS))
        for component in (*root.parts[1:], *relative.parts[:-1]):
            descriptors.append(os.open(component, _DIR_FLAGS, dir_fd=descriptors[-1]))
            names.append(component)
        file_fd = os.open(relative.name, _FILE_FLAGS, dir_fd=descriptors[-1])
        opened = os.fstat(file_fd)
        entry = os.stat(relative.name, dir_fd=descriptors[-1], follow_symlinks=False)
        if not stat.S_ISREG(opened.st_mode) or not _same_inode(opened, entry):
            raise _error("raw artifact is not a bound regular file")
        if opened.st_size > limits.max_bytes:
            raise _parse_limit("document bytes", max_bytes=limits.max_bytes)
        if opened.st_size != byte_count:
            raise _error("raw artifact byte_count mismatch", expected=byte_count, actual=opened.st_size)
        held_digest = sha256()
        data = _read_fd(file_fd, max_bytes=limits.max_bytes, digest=held_digest)
        after_read = os.fstat(file_fd)
        if (
            not _same_inode(opened, after_read)
            or opened.st_size != after_read.st_size
            or opened.st_mtime_ns != after_read.st_mtime_ns
            or not _chain_bound(descriptors, names)
        ):
            raise _error("raw artifact binding changed while reading")
        live_descriptors.append(os.open("/", _DIR_FLAGS))
        for index, component in enumerate(names, start=1):
            live_descriptors.append(os.open(component, _DIR_FLAGS, dir_fd=live_descriptors[-1]))
            if not _same_inode(os.fstat(descriptors[index]), os.fstat(live_descriptors[index])):
                raise _error("raw directory binding changed while reading", component=component)
        live_file_fd = os.open(relative.name, _FILE_FLAGS, dir_fd=live_descriptors[-1])
        if not _same_inode(after_read, os.fstat(live_file_fd)):
            raise _error("raw file binding changed while reading")
        live_digest = sha256()
        live_data = _read_fd(live_file_fd, max_bytes=limits.max_bytes, digest=live_digest)
        if live_data != data or live_digest.digest() != held_digest.digest():
            raise _error("raw file content changed while verifying live binding")
        live_after = os.fstat(live_file_fd)
        live_entry_after = os.stat(
            relative.name,
            dir_fd=live_descriptors[-1],
            follow_symlinks=False,
        )
        if (
            not _chain_bound(live_descriptors, names)
            or not _same_inode(live_after, live_entry_after)
            or not _same_inode(live_after, after_read)
            or live_after.st_size != len(live_data)
        ):
            raise _error("raw live binding changed during verification")
    except ResearchProjectV2Error:
        raise
    except OSError as exc:
        raise _error("raw artifact cannot be read safely", raw_path=raw_value) from exc
    finally:
        if file_fd is not None:
            os.close(file_fd)
        if live_file_fd is not None:
            os.close(live_file_fd)
        for descriptor in reversed(live_descriptors):
            os.close(descriptor)
        for descriptor in reversed(descriptors):
            os.close(descriptor)
    if len(data) != byte_count:
        raise _error("raw artifact changed size while reading", expected=byte_count, actual=len(data))
    actual = held_digest.hexdigest()
    if actual != digest:
        raise _error("raw artifact digest mismatch", expected=digest, actual=actual)
    return data


def normalize_artifact(
    artifact: dict[str, Any],
    *,
    layout: LayeredResearchLayout | None = None,
    parsed_at: str,
    provenance: dict[str, Any],
    parser_version: str = "1.0.0",
    limits: ParserLimits | None = None,
    warnings: list[str] | tuple[str, ...] = (),
) -> dict[str, Any]:
    copied = deepcopy(artifact)
    wrapper = {
        "schema_version": "2.1.0",
        "artifact_kind": "evidence_artifact",
        "evidence_artifact": copied,
    }
    validate_v2_1_schema_payload("evidence_artifact_v2_1", wrapper)
    effective_layout = LayeredResearchLayout.default() if layout is None else layout
    effective_limits = ParserLimits() if limits is None else limits
    data = _read_raw(copied, effective_layout, effective_limits)
    parsed = parse_document_bytes(
        data,
        media_type=copied["media_type"],
        limits=effective_limits,
    )
    artifact_id = copied["artifact_id"]
    sections: list[dict[str, Any]] = []
    seen_locators: set[str] = set()
    for index, section in enumerate(parsed.sections, start=1):
        heading = normalize_text(section.heading) if section.heading is not None else None
        text = normalize_text(section.text)
        locator = section.locator
        if not isinstance(locator, str) or locator in seen_locators:
            raise _error("parser emitted an invalid or duplicate locator", locator=locator)
        seen_locators.add(locator)
        section_core = {"heading": heading, "locator": locator, "text": text}
        sections.append(
            {
                "section_id": f"section:{artifact_id}:{index:04d}",
                **section_core,
                "page_start": section.page_start,
                "page_end": section.page_end,
                "section_hash": content_sha256(section_core),
            }
        )
    normalized_warnings = sorted(
        {normalize_text(item) for item in warnings if isinstance(item, str) and normalize_text(item)}
    )
    core = {
        "artifact_id": artifact_id,
        "parser": parsed.parser,
        "parser_version": parser_version,
        "media_type": parsed.media_type,
        "title": normalize_text(parsed.title) if parsed.title is not None else None,
        "sections": sections,
        "warnings": normalized_warnings,
    }
    hash_payload = {
        **core,
        "parsed_at": parsed_at,
        "provenance": deepcopy(provenance),
    }
    document_hash = content_sha256(hash_payload)
    identity = sha256(f"{artifact_id}\n{document_hash}".encode("utf-8")).hexdigest()[:24]
    document = {
        "document_id": f"normalized_document:{identity}",
        **hash_payload,
        "document_hash": document_hash,
    }
    validate_v2_1_schema_payload(
        "normalized_document_v2_1",
        {
            "schema_version": "2.1.0",
            "artifact_kind": "normalized_document",
            "normalized_document": document,
        },
    )
    return document


def _validated_document(document: dict[str, Any]) -> tuple[dict[str, Any], bytes]:
    copied = deepcopy(document)
    raw_id = copied.get("document_id") if isinstance(copied, dict) else None
    if not isinstance(raw_id, str) or _DOCUMENT_ID.fullmatch(raw_id) is None:
        raise _error("unsafe document_id", document_id=raw_id)
    hash_payload = {
        key: deepcopy(copied.get(key))
        for key in (
            "artifact_id",
            "parser",
            "parser_version",
            "media_type",
            "title",
            "sections",
            "warnings",
            "parsed_at",
            "provenance",
        )
    }
    expected_hash = content_sha256(hash_payload)
    if copied.get("document_hash") != expected_hash:
        raise _immutability("document_hash mismatch")
    expected_identity = sha256(f"{copied.get('artifact_id')}\n{expected_hash}".encode("utf-8")).hexdigest()[:24]
    if raw_id != f"normalized_document:{expected_identity}":
        raise _immutability("document_id mismatch")
    wrapper = {
        "schema_version": "2.1.0",
        "artifact_kind": "normalized_document",
        "normalized_document": copied,
    }
    validate_v2_1_schema_payload("normalized_document_v2_1", wrapper)
    return copied, canonical_bytes(wrapper)


def _open_absolute_directory(path: Path) -> tuple[list[int], list[str]]:
    if not path.is_absolute():
        raise _storage("normalized directory must be absolute", path=str(path))
    descriptors = [os.open("/", _DIR_FLAGS)]
    names: list[str] = []
    try:
        for component in path.parts[1:]:
            if component in {"", ".", ".."}:
                raise _storage("unsafe normalized directory component", component=component)
            try:
                os.mkdir(component, mode=0o700, dir_fd=descriptors[-1])
                os.fsync(descriptors[-1])
            except FileExistsError:
                pass
            descriptors.append(os.open(component, _DIR_FLAGS, dir_fd=descriptors[-1]))
            names.append(component)
        return descriptors, names
    except BaseException:
        for descriptor in reversed(descriptors):
            os.close(descriptor)
        raise


def _chain_bound(descriptors: list[int], names: list[str]) -> bool:
    try:
        return all(
            _same_inode(
                os.fstat(descriptors[index + 1]),
                os.stat(name, dir_fd=descriptors[index], follow_symlinks=False),
            )
            for index, name in enumerate(names)
        )
    except OSError:
        return False


def _require_private_directory(descriptor: int, *, component: str) -> None:
    opened = os.fstat(descriptor)
    mode = stat.S_IMODE(opened.st_mode)
    if (
        not stat.S_ISDIR(opened.st_mode)
        or opened.st_uid != os.geteuid()
        or mode & 0o700 != 0o700
        or mode & 0o077 != 0
    ):
        raise _storage(
            "managed directory is not owner-only",
            component=component,
            mode=oct(mode),
        )


def _open_private_retired_directory(directory_fd: int) -> int:
    try:
        os.mkdir(".retired", mode=0o700, dir_fd=directory_fd)
        os.fsync(directory_fd)
    except FileExistsError:
        pass
    except OSError as exc:
        raise _storage("retired directory cannot be created safely") from exc
    try:
        descriptor = os.open(".retired", _DIR_FLAGS, dir_fd=directory_fd)
        _require_private_directory(descriptor, component=".retired")
        entry = os.stat(".retired", dir_fd=directory_fd, follow_symlinks=False)
        if not _same_inode(os.fstat(descriptor), entry):
            raise OSError(errno.EIO, "retired directory binding mismatch")
        return descriptor
    except ResearchProjectV2Error:
        if "descriptor" in locals():
            os.close(descriptor)
        raise
    except OSError as exc:
        if "descriptor" in locals():
            os.close(descriptor)
        raise _storage("retired directory cannot be opened safely") from exc


def _read_named_regular(directory_fd: int, name: str) -> tuple[bytes, os.stat_result]:
    descriptor = os.open(name, _FILE_FLAGS, dir_fd=directory_fd)
    try:
        before = os.fstat(descriptor)
        entry_before = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        if not stat.S_ISREG(before.st_mode) or not _same_inode(before, entry_before):
            raise OSError(errno.EIO, "unbound final normalized document")
        data = _read_fd(descriptor)
        after = os.fstat(descriptor)
        entry_after = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        if (
            not stat.S_ISREG(after.st_mode)
            or not _same_inode(before, after)
            or not _same_inode(after, entry_after)
            or before.st_size != after.st_size
            or before.st_mtime_ns != after.st_mtime_ns
            or after.st_size != len(data)
        ):
            raise OSError(errno.EIO, "final normalized document changed during read")
        return data, after
    finally:
        os.close(descriptor)


def _write_all(descriptor: int, data: bytes) -> None:
    offset = 0
    while offset < len(data):
        written = os.write(descriptor, data[offset:])
        if written <= 0:
            raise OSError(errno.EIO, "short normalized document write")
        offset += written
    os.fsync(descriptor)


def _name_matches_inode(directory_fd: int, name: str, expected: os.stat_result) -> bool:
    try:
        entry = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        return stat.S_ISREG(entry.st_mode) and _same_inode(entry, expected)
    except OSError:
        return False


def _unlink_if_inode(
    directory_fd: int,
    retired_fd: int,
    name: str,
    expected: os.stat_result,
) -> bool:
    if not _name_matches_inode(directory_fd, name, expected):
        return False
    retired = f"entry-{secrets.token_hex(16)}"
    os.rename(
        name,
        retired,
        src_dir_fd=directory_fd,
        dst_dir_fd=retired_fd,
    )
    os.fsync(directory_fd)
    os.fsync(retired_fd)
    if not _name_matches_inode(retired_fd, retired, expected):
        return False
    os.unlink(retired, dir_fd=retired_fd)
    os.fsync(retired_fd)
    return True


def write_normalized_document(
    document: dict[str, Any], *, layout: LayeredResearchLayout | None = None
) -> Path:
    copied, data = _validated_document(document)
    effective_layout = LayeredResearchLayout.default() if layout is None else layout
    directory = effective_layout.evidence_normalized_dir
    final_name = f"{copied['document_id']}.json"
    target = directory / final_name
    descriptors: list[int] = []
    names: list[str] = []
    temporary_fd: int | None = None
    temporary_name: str | None = None
    temporary_stat: os.stat_result | None = None
    held_final_fd: int | None = None
    retired_fd: int | None = None
    try:
        try:
            descriptors, names = _open_absolute_directory(directory)
        except ResearchProjectV2Error:
            raise
        except OSError as exc:
            raise _storage("unsafe normalized directory", path=str(directory)) from exc
        if not _chain_bound(descriptors, names):
            raise _storage("normalized directory binding changed", path=str(directory))
        directory_fd = descriptors[-1]
        _require_private_directory(directory_fd, component="normalized")
        retired_fd = _open_private_retired_directory(directory_fd)
        for _ in range(128):
            temporary_name = f".tmp-{secrets.token_hex(16)}"
            try:
                temporary_fd = os.open(
                    temporary_name,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0),
                    0o600,
                    dir_fd=directory_fd,
                )
                break
            except FileExistsError:
                continue
        if temporary_fd is None:
            raise _storage("temporary filename collisions")
        _write_all(temporary_fd, data)
        temporary_stat = os.fstat(temporary_fd)
        if not _name_matches_inode(directory_fd, temporary_name, temporary_stat):
            raise _storage("temporary normalized document binding changed")
        try:
            os.link(
                temporary_name,
                final_name,
                src_dir_fd=directory_fd,
                dst_dir_fd=directory_fd,
                follow_symlinks=False,
            )
            created_stat: os.stat_result | None = temporary_stat
            os.fsync(directory_fd)
        except FileExistsError:
            created_stat = None
            try:
                existing, _ = _read_named_regular(directory_fd, final_name)
            except OSError as exc:
                raise _storage("unsafe existing normalized document", path=str(target)) from exc
            if existing != data:
                raise _immutability("immutable normalized path conflict", path=str(target))
        if not _chain_bound(descriptors, names):
            raise _storage("normalized directory binding changed", path=str(directory))
        try:
            verified, final_stat = _read_named_regular(directory_fd, final_name)
        except OSError as exc:
            raise _storage("published normalized document cannot be verified", path=str(target)) from exc
        if verified != data or (created_stat is not None and not _same_inode(final_stat, created_stat)):
            raise _immutability("published normalized document changed", path=str(target))
        if not _unlink_if_inode(
            directory_fd, retired_fd, temporary_name, temporary_stat
        ):
            raise _storage("temporary normalized document binding changed during cleanup")
        temporary_name = None
        os.close(temporary_fd)
        temporary_fd = None
        held_final_fd = os.open(final_name, _FILE_FLAGS, dir_fd=directory_fd)
        held_before = os.fstat(held_final_fd)
        held_entry_before = os.stat(
            final_name, dir_fd=directory_fd, follow_symlinks=False
        )
        if (
            not stat.S_ISREG(held_before.st_mode)
            or not _same_inode(held_before, final_stat)
            or not _same_inode(held_before, held_entry_before)
        ):
            raise _storage("held normalized document changed", path=str(target))
        held_data = _read_fd(held_final_fd)
        held = os.fstat(held_final_fd)
        held_entry_after = os.stat(
            final_name, dir_fd=directory_fd, follow_symlinks=False
        )
        if (
            held_data != data
            or not stat.S_ISREG(held.st_mode)
            or not _same_inode(held_before, held)
            or not _same_inode(held, held_entry_after)
            or held_before.st_size != held.st_size
            or held_before.st_mtime_ns != held.st_mtime_ns
            or held.st_size != len(held_data)
        ):
            raise _storage("held normalized document changed", path=str(target))
        live_descriptors, live_names = _open_absolute_directory(directory)
        try:
            if not _chain_bound(live_descriptors, live_names):
                raise _storage("live normalized directory is unsafe", path=str(directory))
            _require_private_directory(
                live_descriptors[-1], component="normalized"
            )
            for old, live in zip(descriptors, live_descriptors, strict=True):
                if not _same_inode(os.fstat(old), os.fstat(live)):
                    raise _storage("live normalized directory was rebound", path=str(directory))
            live_data, live_stat = _read_named_regular(live_descriptors[-1], final_name)
            if live_data != data or not _same_inode(live_stat, held):
                raise _storage("live normalized document was replaced", path=str(target))
            live_entry = os.stat(
                final_name,
                dir_fd=live_descriptors[-1],
                follow_symlinks=False,
            )
            if (
                not _chain_bound(live_descriptors, live_names)
                or not stat.S_ISREG(live_stat.st_mode)
                or not _same_inode(live_stat, live_entry)
                or live_stat.st_size != len(live_data)
            ):
                raise _storage(
                    "live normalized document changed before return", path=str(target)
                )
            for old, live in zip(descriptors, live_descriptors, strict=True):
                if not _same_inode(os.fstat(old), os.fstat(live)):
                    raise _storage(
                        "live normalized directory was rebound", path=str(directory)
                    )
        finally:
            for descriptor in reversed(live_descriptors):
                os.close(descriptor)
        return target
    except ResearchProjectV2Error:
        raise
    except OSError as exc:
        raise _storage("normalized document write failed", path=str(target)) from exc
    finally:
        if held_final_fd is not None:
            os.close(held_final_fd)
        if temporary_fd is not None:
            os.close(temporary_fd)
        if (
            temporary_name is not None
            and temporary_stat is not None
            and descriptors
            and retired_fd is not None
        ):
            try:
                _unlink_if_inode(
                    descriptors[-1], retired_fd, temporary_name, temporary_stat
                )
            except OSError:
                pass
        if retired_fd is not None:
            os.close(retired_fd)
        for descriptor in reversed(descriptors):
            os.close(descriptor)
