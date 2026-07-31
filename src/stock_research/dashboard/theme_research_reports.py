from __future__ import annotations

import copy
import errno
import hashlib
import os
import re
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

import nh3
from markdown_it import MarkdownIt

from stock_research.config import SETTINGS
from stock_research import theme_research_report_store as report_store
from stock_research.theme_research_report_store import ThemeResearchReportError


_MAX_MARKDOWN_BYTES = SETTINGS.theme_research_report_max_markdown_bytes
_MAX_PDF_BYTES = SETTINGS.theme_research_report_max_pdf_bytes
_RESOURCE_EXHAUSTION_ERRNOS = {
    errno.EDQUOT,
    errno.EMFILE,
    errno.ENFILE,
    errno.ENOMEM,
    errno.ENOSPC,
}
_APPROVED_STATUSES = {"published", "archived"}
_ADMIN_STATUSES = {"pending_review", "rejected", "published", "archived"}
_SHA256_HEX_LENGTH = 64
_OPEN_DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
_OPEN_FILE_FLAGS = (
    os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | getattr(os, "O_NONBLOCK", 0)
)
_ALLOWED_TAGS = {
    "a",
    "blockquote",
    "br",
    "code",
    "em",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "hr",
    "li",
    "ol",
    "p",
    "pre",
    "s",
    "strong",
    "table",
    "tbody",
    "td",
    "th",
    "thead",
    "tr",
    "ul",
}
_CLEAN_CONTENT_TAGS = {"iframe", "img", "script", "style", "svg", "math"}
_MARKDOWN = MarkdownIt("commonmark", {"html": False, "linkify": False}).enable("table")
_DANGEROUS_RENDERED_SCHEME_RE = re.compile(
    r"\b(?:javascript|data)\s*:", re.IGNORECASE
)
_DANGEROUS_RENDERED_ATTRIBUTE_RE = re.compile(r"\bonerror\b", re.IGNORECASE)
_UNSAFE_FILENAME_CHARACTERS_RE = re.compile(r"[^A-Za-z0-9._-]+")


class ThemeResearchReportDocumentError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = copy.deepcopy(details) if details is not None else {}


@dataclass(frozen=True)
class _Snapshot:
    device: int
    inode: int
    mode: int
    size: int
    mtime_ns: int
    ctime_ns: int


class ResolvedPdf:
    def __init__(
        self,
        fd: int,
        *,
        filename: str,
        content_length: int,
    ) -> None:
        self._fd: int | None = fd
        self.filename = filename
        self.media_type = "application/pdf"
        self.content_length = content_length

    @property
    def closed(self) -> bool:
        return self._fd is None

    def iter_chunks(self, *, chunk_size: int = 64 * 1024) -> Iterator[bytes]:
        if isinstance(chunk_size, bool) or not isinstance(chunk_size, int) or chunk_size <= 0:
            raise ValueError("chunk_size must be a positive integer")

        def stream() -> Iterator[bytes]:
            try:
                while True:
                    fd = self._fd
                    if fd is None:
                        raise ValueError("PDF stream is closed")
                    chunk = os.read(fd, chunk_size)
                    if not chunk:
                        return
                    yield chunk
            finally:
                self.close()

        return stream()

    def close(self) -> None:
        fd, self._fd = self._fd, None
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass

    def __enter__(self) -> ResolvedPdf:
        if self.closed:
            raise ValueError("PDF stream is closed")
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()

    def __del__(self) -> None:
        self.close()


def load_published_report_document(
    theme_id: str,
    report_version_id: str,
    *,
    report_root: str | os.PathLike[str] = SETTINGS.theme_research_report_root,
    service: str = SETTINGS.theme_research_runtime_service,
) -> dict[str, Any]:
    try:
        artifact = report_store.get_approved_report_artifact_record(
            theme_id, report_version_id, service=service
        )
        metadata = report_store.get_approved_report_version(
            theme_id, report_version_id, service=service
        )
    except BaseException as exc:
        _raise_store_error(exc)
    record = _merge_records(artifact, metadata)
    _require_status(record, _APPROVED_STATUSES, published=True)
    markdown = _read_artifact_bytes(
        record,
        artifact_kind="markdown",
        report_root=report_root,
        max_bytes=_MAX_MARKDOWN_BYTES,
    )
    return _safe_document(record, html=_render_markdown(markdown), admin=False)


def load_admin_report_document(
    report_version_id: str,
    *,
    report_root: str | os.PathLike[str] = SETTINGS.theme_research_report_root,
    service: str = SETTINGS.theme_research_runtime_service,
) -> dict[str, Any]:
    try:
        record = report_store.get_admin_report_version(report_version_id, service=service)
    except BaseException as exc:
        _raise_store_error(exc)
    _require_status(record, _ADMIN_STATUSES, published=False)
    markdown = _read_artifact_bytes(
        record,
        artifact_kind="markdown",
        report_root=report_root,
        max_bytes=_MAX_MARKDOWN_BYTES,
    )
    return _safe_document(record, html=_render_markdown(markdown), admin=True)


def resolve_published_report_pdf(
    theme_id: str,
    report_version_id: str,
    *,
    report_root: str | os.PathLike[str] = SETTINGS.theme_research_report_root,
    service: str = SETTINGS.theme_research_runtime_service,
) -> ResolvedPdf:
    try:
        record = report_store.get_approved_report_artifact_record(
            theme_id, report_version_id, service=service
        )
    except BaseException as exc:
        _raise_store_error(exc)
    _require_status(record, _APPROVED_STATUSES, published=True)
    return _resolve_pdf(record, report_root=report_root)


def resolve_admin_report_pdf(
    report_version_id: str,
    *,
    report_root: str | os.PathLike[str] = SETTINGS.theme_research_report_root,
    service: str = SETTINGS.theme_research_runtime_service,
) -> ResolvedPdf:
    try:
        record = report_store.get_admin_report_version(report_version_id, service=service)
    except BaseException as exc:
        _raise_store_error(exc)
    _require_status(record, _ADMIN_STATUSES, published=False)
    return _resolve_pdf(record, report_root=report_root)


def _merge_records(artifact: dict[str, Any], metadata: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(artifact, dict) or not isinstance(metadata, dict):
        raise _invalid()
    for key in ("report_version_id", "theme_id", "version", "status"):
        if artifact.get(key) != metadata.get(key):
            raise _invalid()
    result = dict(metadata)
    result.update(artifact)
    return result


def _safe_document(record: dict[str, Any], *, html: str, admin: bool) -> dict[str, Any]:
    result = {
        "report_version_id": record.get("report_version_id"),
        "theme_id": record.get("theme_id"),
        "version": record.get("version"),
        "title": record.get("title"),
        "summary": record.get("summary"),
        "status": record.get("status"),
        "generated_at": record.get("generated_at"),
        "indexed_at": record.get("indexed_at"),
        "published_at": record.get("published_at"),
        "has_pdf": record.get("pdf_relative_path") is not None,
        "html": html,
    }
    if admin:
        result["generator_name"] = record.get("generator_name")
        result["generator_version"] = record.get("generator_version")
    return result


def _render_markdown(data: bytes) -> str:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise _artifact_unavailable() from exc
    try:
        rendered = _MARKDOWN.render(text)
        cleaned = nh3.clean(
            rendered,
            tags=_ALLOWED_TAGS,
            clean_content_tags=_CLEAN_CONTENT_TAGS,
            attributes={"a": {"href", "title"}},
            url_schemes={"http", "https", "mailto"},
            url_relative="deny",
            link_rel="noopener noreferrer",
            strip_comments=True,
        )
        cleaned = _DANGEROUS_RENDERED_SCHEME_RE.sub("", cleaned)
        return _DANGEROUS_RENDERED_ATTRIBUTE_RE.sub("", cleaned)
    except MemoryError:
        raise
    except Exception as exc:
        raise ThemeResearchReportDocumentError(
            "THEME_REPORT_DOCUMENT_RENDER_FAILED",
            "theme research report could not be rendered",
        ) from exc


def _resolve_pdf(
    record: dict[str, Any], *, report_root: str | os.PathLike[str]
) -> ResolvedPdf:
    relative_path = record.get("pdf_relative_path")
    checksum = record.get("pdf_sha256")
    if relative_path is None and checksum is None:
        raise ThemeResearchReportDocumentError(
            "THEME_REPORT_PDF_NOT_FOUND", "theme research report PDF was not found"
        )
    if relative_path is None or checksum is None:
        raise _artifact_unavailable()
    fd, snapshot = _open_verified_artifact(
        record,
        relative_path=relative_path,
        expected_sha256=checksum,
        report_root=report_root,
        max_bytes=_MAX_PDF_BYTES,
        keep_open=True,
    )
    assert fd is not None
    try:
        return ResolvedPdf(
            fd,
            filename=_safe_pdf_filename(record["version"]),
            content_length=snapshot.size,
        )
    except BaseException:
        _safe_close(fd)
        raise


def _read_artifact_bytes(
    record: dict[str, Any],
    *,
    artifact_kind: str,
    report_root: str | os.PathLike[str],
    max_bytes: int,
) -> bytes:
    relative_path = record.get(f"{artifact_kind}_relative_path")
    checksum = record.get(f"{artifact_kind}_sha256")
    fd, _ = _open_verified_artifact(
        record,
        relative_path=relative_path,
        expected_sha256=checksum,
        report_root=report_root,
        max_bytes=max_bytes,
        keep_open=False,
    )
    assert isinstance(fd, bytes)
    return fd


def _open_verified_artifact(
    record: dict[str, Any],
    *,
    relative_path: Any,
    expected_sha256: Any,
    report_root: str | os.PathLike[str],
    max_bytes: int,
    keep_open: bool,
) -> tuple[int | bytes, _Snapshot]:
    theme, version = _validated_record_layout(record, relative_path, expected_sha256)
    root = _validated_root(report_root)
    root_fd = theme_fd = version_fd = artifact_fd = None
    snapshot_file = None
    try:
        root_fd = _open_directory_path(root)
        root_snapshot = _snapshot_fd(root_fd, directory=True)
        theme_fd = _open_child_directory(root_fd, theme)
        theme_snapshot = _snapshot_fd(theme_fd, directory=True)
        version_fd = _open_child_directory(theme_fd, version)
        version_snapshot = _snapshot_fd(version_fd, directory=True)
        artifact_fd, before = _open_child_file(version_fd, relative_path)
        if before.size > max_bytes:
            raise _too_large()
        if keep_open:
            snapshot_file = tempfile.TemporaryFile()

        digest = hashlib.sha256()
        chunks: list[bytes] | None = [] if not keep_open else None
        total = 0
        while True:
            chunk = os.read(artifact_fd, min(64 * 1024, max_bytes + 1 - total))
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                raise _too_large()
            digest.update(chunk)
            if chunks is not None:
                chunks.append(chunk)
            if snapshot_file is not None:
                _write_all(snapshot_file.fileno(), chunk)
        after = _snapshot_fd(artifact_fd, directory=False)
        if before != after or total != before.size:
            raise _artifact_unavailable()
        if digest.hexdigest() != expected_sha256:
            raise _artifact_unavailable()
        _verify_path_identity(version_fd, relative_path, after)
        _verify_path_identity(theme_fd, version, version_snapshot)
        _verify_path_identity(root_fd, theme, theme_snapshot)
        _verify_root_identity(root, root_snapshot)

        if keep_open:
            assert snapshot_file is not None
            owned_fd = os.dup(snapshot_file.fileno())
            os.lseek(owned_fd, 0, os.SEEK_SET)
            return owned_fd, after
        data = b"".join(chunks or ())
        return data, after
    except MemoryError:
        raise
    except OSError as exc:
        if exc.errno in _RESOURCE_EXHAUSTION_ERRNOS:
            raise
        raise _map_os_error(exc) from exc
    finally:
        _safe_close(artifact_fd)
        _safe_close(version_fd)
        _safe_close(theme_fd)
        _safe_close(root_fd)
        if snapshot_file is not None:
            snapshot_file.close()


def _validated_record_layout(
    record: dict[str, Any], relative_path: Any, expected_sha256: Any
) -> tuple[str, str]:
    if not isinstance(record, dict):
        raise _invalid()
    theme = _direct_name(record.get("theme_id"))
    version = _direct_name(record.get("version"))
    artifact = _direct_name(relative_path)
    if artifact != relative_path:
        raise _invalid()
    manifest_path = record.get("manifest_relative_path")
    if not isinstance(manifest_path, str) or "\x00" in manifest_path:
        raise _invalid()
    manifest_parts = Path(manifest_path).parts
    if manifest_parts != (theme, version, "manifest.json"):
        raise _invalid()
    if (
        not isinstance(expected_sha256, str)
        or len(expected_sha256) != _SHA256_HEX_LENGTH
        or any(character not in "0123456789abcdef" for character in expected_sha256)
    ):
        raise _artifact_unavailable()
    return theme, version


def _direct_name(value: Any) -> str:
    if (
        not isinstance(value, str)
        or not value
        or "\x00" in value
        or value in {".", ".."}
        or "/" in value
        or "\\" in value
    ):
        raise _invalid()
    return value


def _safe_pdf_filename(version: str) -> str:
    safe = _UNSAFE_FILENAME_CHARACTERS_RE.sub("-", version).strip(".-_")[:80]
    if not safe:
        return "theme-report.pdf"
    return f"theme-report-{safe}.pdf"


def _write_all(fd: int, data: bytes) -> None:
    offset = 0
    while offset < len(data):
        written = os.write(fd, data[offset:])
        if written <= 0:
            raise OSError(errno.EIO, "snapshot write failed")
        offset += written


def _validated_root(value: str | os.PathLike[str]) -> Path:
    try:
        raw = os.fspath(value)
    except TypeError as exc:
        raise _invalid() from exc
    if not isinstance(raw, str) or "\x00" in raw:
        raise _invalid()
    path = Path(raw)
    if not path.is_absolute():
        raise _invalid()
    return path


def _open_directory_path(path: Path) -> int:
    return os.open(path, _OPEN_DIRECTORY_FLAGS)


def _open_child_directory(parent_fd: int, name: str) -> int:
    return os.open(name, _OPEN_DIRECTORY_FLAGS, dir_fd=parent_fd)


def _open_child_file(parent_fd: int, name: str) -> tuple[int, _Snapshot]:
    before = _snapshot(os.stat(name, dir_fd=parent_fd, follow_symlinks=False))
    if not stat.S_ISREG(before.mode):
        raise _artifact_unavailable()
    fd = os.open(name, _OPEN_FILE_FLAGS, dir_fd=parent_fd)
    try:
        opened = _snapshot_fd(fd, directory=False)
        if opened != before:
            raise _artifact_unavailable()
        return fd, opened
    except BaseException:
        _safe_close(fd)
        raise


def _snapshot_fd(fd: int, *, directory: bool) -> _Snapshot:
    info = os.fstat(fd)
    if directory and not stat.S_ISDIR(info.st_mode):
        raise _artifact_unavailable()
    if not directory and not stat.S_ISREG(info.st_mode):
        raise _artifact_unavailable()
    return _snapshot(info)


def _snapshot(info: os.stat_result) -> _Snapshot:
    return _Snapshot(
        device=info.st_dev,
        inode=info.st_ino,
        mode=info.st_mode,
        size=info.st_size,
        mtime_ns=info.st_mtime_ns,
        ctime_ns=info.st_ctime_ns,
    )


def _verify_path_identity(parent_fd: int, name: str, expected: _Snapshot) -> None:
    current = _snapshot(os.stat(name, dir_fd=parent_fd, follow_symlinks=False))
    if current != expected:
        raise _artifact_unavailable()


def _verify_root_identity(path: Path, expected: _Snapshot) -> None:
    current = _snapshot(os.stat(path, follow_symlinks=False))
    if current != expected:
        raise _artifact_unavailable()


def _require_status(record: dict[str, Any], allowed: set[str], *, published: bool) -> None:
    if not isinstance(record, dict) or record.get("status") not in allowed:
        if published:
            raise _not_found()
        raise _invalid()


def _raise_store_error(exc: BaseException) -> None:
    if isinstance(exc, (MemoryError, KeyboardInterrupt, SystemExit)):
        raise exc
    if isinstance(exc, OSError) and exc.errno in _RESOURCE_EXHAUSTION_ERRNOS:
        raise exc
    if isinstance(exc, ThemeResearchReportError):
        if exc.code == "THEME_REPORT_STORE_UNAVAILABLE":
            raise ThemeResearchReportDocumentError(
                "THEME_REPORT_DOCUMENT_SERVICE_UNAVAILABLE",
                "theme research report service is unavailable",
            ) from exc
        if exc.code.endswith("NOT_FOUND"):
            raise _not_found() from exc
        if "INVALID" in exc.code:
            raise _invalid() from exc
    raise ThemeResearchReportDocumentError(
        "THEME_REPORT_DOCUMENT_SERVICE_UNAVAILABLE",
        "theme research report service is unavailable",
    ) from exc


def _map_os_error(exc: OSError) -> ThemeResearchReportDocumentError:
    del exc
    return _artifact_unavailable()


def _not_found() -> ThemeResearchReportDocumentError:
    return ThemeResearchReportDocumentError(
        "THEME_REPORT_DOCUMENT_NOT_FOUND",
        "theme research report was not found",
    )


def _invalid(
    message: str = "theme research report content is invalid",
) -> ThemeResearchReportDocumentError:
    return ThemeResearchReportDocumentError("THEME_REPORT_DOCUMENT_INVALID", message)


def _too_large() -> ThemeResearchReportDocumentError:
    return _artifact_unavailable()


def _artifact_unavailable() -> ThemeResearchReportDocumentError:
    return ThemeResearchReportDocumentError(
        "THEME_REPORT_ARTIFACT_UNAVAILABLE",
        "theme research report artifact is unavailable",
    )


def _safe_close(fd: int | None) -> None:
    if fd is not None:
        try:
            os.close(fd)
        except OSError:
            pass


__all__ = [
    "ResolvedPdf",
    "ThemeResearchReportDocumentError",
    "load_admin_report_document",
    "load_published_report_document",
    "resolve_admin_report_pdf",
    "resolve_published_report_pdf",
]
