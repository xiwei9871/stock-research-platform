from __future__ import annotations

import asyncio
import errno
import hashlib
import os
import shutil
import threading
import time
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest
import anyio
from fastapi.testclient import TestClient

from stock_research.dashboard import app as dashboard_app
from stock_research.dashboard import theme_research_reports as reports
from stock_research.dashboard.auth_models import CurrentUser
from stock_research.theme_research_report_index import ReportScanResult
from stock_research.theme_research_report_store import ThemeResearchReportError


NOW = datetime(2026, 7, 31, tzinfo=UTC)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _record(root: Path, *, status: str = "published", pdf: bytes | None = None) -> dict:
    markdown = b"# Heading\n\n- one\n- two\n"
    version_dir = root / "theme-a" / "v1"
    version_dir.mkdir(parents=True)
    (version_dir / "report.md").write_bytes(markdown)
    (version_dir / "manifest.json").write_text("{}", encoding="utf-8")
    if pdf is not None:
        (version_dir / "report.pdf").write_bytes(pdf)
    return {
        "report_version_id": "report-id",
        "theme_id": "theme-a",
        "version": "v1",
        "title": "Safe title",
        "summary": "Safe summary",
        "status": status,
        "generated_at": NOW,
        "indexed_at": NOW,
        "published_at": NOW if status in {"published", "archived"} else None,
        "markdown_relative_path": "report.md",
        "markdown_sha256": _sha(markdown),
        "pdf_relative_path": "report.pdf" if pdf is not None else None,
        "pdf_sha256": _sha(pdf) if pdf is not None else None,
        "manifest_relative_path": "theme-a/v1/manifest.json",
        "manifest_sha256": "0" * 64,
        "generator_name": "generator",
        "generator_version": "1.2.3",
        "rejection_reason": "database secret",
        "metadata": {"private": "database secret"},
    }


def _install_store(monkeypatch: pytest.MonkeyPatch, record: dict) -> None:
    monkeypatch.setattr(
        reports.report_store,
        "get_approved_report_artifact_record",
        lambda theme_id, report_version_id, *, service: dict(record),
    )
    monkeypatch.setattr(
        reports.report_store,
        "get_approved_report_version",
        lambda theme_id, report_version_id, *, service: dict(record),
    )
    monkeypatch.setattr(
        reports.report_store,
        "get_admin_report_version",
        lambda report_version_id, *, service: dict(record),
    )


@pytest.mark.parametrize("status", ["published", "archived"])
def test_published_document_loads_safe_markdown(monkeypatch, tmp_path, status) -> None:
    record = _record(tmp_path, status=status)
    _install_store(monkeypatch, record)

    result = reports.load_published_report_document(
        "theme-a", "report-id", report_root=tmp_path, service="runtime"
    )

    assert result == {
        "report_version_id": "report-id",
        "theme_id": "theme-a",
        "version": "v1",
        "title": "Safe title",
        "summary": "Safe summary",
        "status": status,
        "generated_at": NOW,
        "indexed_at": NOW,
        "published_at": NOW,
        "has_pdf": False,
        "html": "<h1>Heading</h1>\n<ul>\n<li>one</li>\n<li>two</li>\n</ul>\n",
    }


@pytest.mark.parametrize("status", ["pending_review", "rejected"])
def test_published_document_hides_unapproved_record(monkeypatch, tmp_path, status) -> None:
    record = _record(tmp_path, status=status)

    def hidden(*args, **kwargs):
        raise ThemeResearchReportError("THEME_REPORT_NOT_FOUND", "db secret")

    monkeypatch.setattr(reports.report_store, "get_approved_report_artifact_record", hidden)

    with pytest.raises(reports.ThemeResearchReportDocumentError) as exc_info:
        reports.load_published_report_document(
            "theme-a", "report-id", report_root=tmp_path
        )

    assert exc_info.value.code == "THEME_REPORT_DOCUMENT_NOT_FOUND"
    assert "secret" not in str(exc_info.value).lower()
    assert exc_info.value.details == {}


@pytest.mark.parametrize("status", ["pending_review", "rejected", "published", "archived"])
def test_admin_document_previews_all_review_states(monkeypatch, tmp_path, status) -> None:
    record = _record(tmp_path, status=status)
    _install_store(monkeypatch, record)

    result = reports.load_admin_report_document(
        "report-id", report_root=tmp_path, service="runtime"
    )

    assert result["status"] == status
    assert result["generator_name"] == "generator"
    assert result["generator_version"] == "1.2.3"
    forbidden = {
        "markdown_relative_path",
        "markdown_sha256",
        "pdf_relative_path",
        "pdf_sha256",
        "manifest_relative_path",
        "manifest_sha256",
        "rejection_reason",
        "metadata",
    }
    assert forbidden.isdisjoint(result)
    assert "database secret" not in repr(result)


def test_renderer_supports_commonmark_tables_links_and_code(monkeypatch, tmp_path) -> None:
    record = _record(tmp_path)
    markdown = (
        b"# H\n\n| A | B |\n|---|---|\n| 1 | 2 |\n\n"
        b"[site](https://example.com) and `code`\n"
    )
    path = tmp_path / "theme-a" / "v1" / "report.md"
    path.write_bytes(markdown)
    record["markdown_sha256"] = _sha(markdown)
    _install_store(monkeypatch, record)

    html = reports.load_published_report_document(
        "theme-a", "report-id", report_root=tmp_path
    )["html"]

    assert "<table>" in html
    assert "<code>code</code>" in html
    assert 'href="https://example.com"' in html
    assert 'rel="noopener noreferrer"' in html


def test_renderer_removes_active_content_and_raw_html(monkeypatch, tmp_path) -> None:
    record = _record(tmp_path)
    markdown = b"""<script>alert(1)</script>
<img src=x onerror=alert(2)>
<div onerror=alert(9)>unsafe raw HTML</div>
<style>body{display:none}</style>
<iframe src=https://evil.test></iframe>
[js](javascript:alert(3))
[data](data:text/html,boom)
[encoded-js](jav&#x61;script:alert(4))
[encoded-data](data&#58;text/html,boom)
[ok](https://example.com)
"""
    path = tmp_path / "theme-a" / "v1" / "report.md"
    path.write_bytes(markdown)
    record["markdown_sha256"] = _sha(markdown)
    _install_store(monkeypatch, record)

    html = reports.load_published_report_document(
        "theme-a", "report-id", report_root=tmp_path
    )["html"]

    lowered = html.lower()
    for forbidden in (
        "<script",
        "<img",
        "<style",
        "<iframe",
        'href="javascript:',
        'href="data:',
    ):
        assert forbidden not in lowered


def test_renderer_preserves_dangerous_words_as_inert_text(monkeypatch, tmp_path) -> None:
    record = _record(tmp_path)
    markdown = b"""Literal javascript:alert(1), onerror, and data:text/plain are prose.

`javascript:alert(1)` and `onerror` and `data:`

```text
javascript:alert(1)
onerror
data:
```
"""
    path = tmp_path / "theme-a" / "v1" / "report.md"
    path.write_bytes(markdown)
    record["markdown_sha256"] = _sha(markdown)
    _install_store(monkeypatch, record)

    html = reports.load_published_report_document(
        "theme-a", "report-id", report_root=tmp_path
    )["html"]

    assert html.count("javascript:alert(1)") == 3
    assert html.count("onerror") == 3
    assert html.count("data:") == 3


def test_renderer_scales_linearly_for_adversarial_raw_html() -> None:
    def render(count: int) -> tuple[str, float]:
        markdown = (("<script>" * count) + ("</style>" * count)).encode()
        started = time.monotonic()
        result = reports._render_markdown(markdown)
        return result, time.monotonic() - started

    reports._render_markdown(b"warmup")
    _, small_elapsed = render(5_000)
    html, large_elapsed = render(20_000)

    assert large_elapsed < (small_elapsed * 10) + 0.05
    assert "<script" not in html.lower()


def test_renderer_scales_for_unterminated_unsafe_links() -> None:
    def render(count: int) -> float:
        markdown = ("[x](javascript:" * count).encode()
        started = time.monotonic()
        reports._render_markdown(markdown)
        return time.monotonic() - started

    small_elapsed = render(1_000)
    large_elapsed = render(10_000)

    assert large_elapsed < (small_elapsed * 15) + 0.05


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("manifest_relative_path", "/theme-a/v1/manifest.json"),
        ("manifest_relative_path", "theme-a/../v1/manifest.json"),
        ("manifest_relative_path", "theme-a/v1/other.json"),
        ("manifest_relative_path", "other/v1/manifest.json"),
        ("manifest_relative_path", "theme-a/other/manifest.json"),
        ("markdown_relative_path", "/report.md"),
        ("markdown_relative_path", "../report.md"),
        ("markdown_relative_path", "nested/report.md"),
        ("markdown_relative_path", "report.md\x00suffix"),
    ],
)
def test_record_paths_must_be_consistent_direct_children(
    monkeypatch, tmp_path, field, value
) -> None:
    record = _record(tmp_path)
    record[field] = value
    _install_store(monkeypatch, record)

    with pytest.raises(reports.ThemeResearchReportDocumentError) as exc_info:
        reports.load_published_report_document(
            "theme-a", "report-id", report_root=tmp_path
        )

    assert exc_info.value.code == "THEME_REPORT_DOCUMENT_INVALID"
    assert str(tmp_path) not in str(exc_info.value)


@pytest.mark.parametrize("checksum", [None, "bad", "A" * 64, "0" * 63])
def test_malformed_stored_markdown_checksum_is_artifact_unavailable(
    monkeypatch, tmp_path, checksum
) -> None:
    record = _record(tmp_path)
    record["markdown_sha256"] = checksum
    _install_store(monkeypatch, record)

    with pytest.raises(reports.ThemeResearchReportDocumentError) as exc_info:
        reports.load_published_report_document(
            "theme-a", "report-id", report_root=tmp_path
        )
    assert exc_info.value.code == "THEME_REPORT_ARTIFACT_UNAVAILABLE"


@pytest.mark.parametrize(
    "mutation", ["missing", "directory", "symlink", "checksum", "utf8", "too_large"]
)
def test_markdown_failures_are_stable(monkeypatch, tmp_path, mutation) -> None:
    record = _record(tmp_path)
    path = tmp_path / "theme-a" / "v1" / "report.md"
    if mutation == "missing":
        path.unlink()
    elif mutation == "directory":
        path.unlink()
        path.mkdir()
    elif mutation == "symlink":
        path.unlink()
        path.symlink_to(tmp_path / "outside.md")
    elif mutation == "checksum":
        path.write_bytes(b"changed")
    elif mutation == "utf8":
        path.write_bytes(b"\xff")
        record["markdown_sha256"] = _sha(b"\xff")
    else:
        data = b"x" * (10 * 1024 * 1024 + 1)
        path.write_bytes(data)
        record["markdown_sha256"] = _sha(data)
    _install_store(monkeypatch, record)

    with pytest.raises(reports.ThemeResearchReportDocumentError) as exc_info:
        reports.load_published_report_document(
            "theme-a", "report-id", report_root=tmp_path
        )

    assert exc_info.value.code == "THEME_REPORT_ARTIFACT_UNAVAILABLE"
    assert "report.md" not in str(exc_info.value)


def _call_in_thread(callable_) -> tuple[threading.Thread, dict[str, BaseException]]:
    outcome: dict[str, BaseException] = {}

    def run() -> None:
        try:
            callable_()
        except BaseException as exc:
            outcome["error"] = exc

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread, outcome


def _release_fifo_reader(path: Path) -> None:
    try:
        fd = os.open(path, os.O_WRONLY | os.O_NONBLOCK)
    except OSError:
        return
    os.close(fd)


@pytest.mark.parametrize("artifact", ["markdown", "pdf"])
def test_fifo_artifact_is_rejected_without_blocking(monkeypatch, tmp_path, artifact) -> None:
    pdf = b"%PDF" if artifact == "pdf" else None
    record = _record(tmp_path, pdf=pdf)
    path = tmp_path / "theme-a" / "v1" / (
        "report.md" if artifact == "markdown" else "report.pdf"
    )
    path.unlink()
    os.mkfifo(path)
    _install_store(monkeypatch, record)
    if artifact == "markdown":
        call = lambda: reports.load_published_report_document(
            "theme-a", "report-id", report_root=tmp_path
        )
    else:
        call = lambda: reports.resolve_published_report_pdf(
            "theme-a", "report-id", report_root=tmp_path
        )

    thread, outcome = _call_in_thread(call)
    thread.join(timeout=0.2)
    blocked = thread.is_alive()
    if blocked:
        _release_fifo_reader(path)
        thread.join(timeout=1)

    assert not blocked
    assert isinstance(outcome.get("error"), reports.ThemeResearchReportDocumentError)
    assert outcome["error"].code == "THEME_REPORT_ARTIFACT_UNAVAILABLE"


def test_stat_then_fifo_swap_is_rejected_without_blocking(monkeypatch, tmp_path) -> None:
    record = _record(tmp_path)
    _install_store(monkeypatch, record)
    path = tmp_path / "theme-a" / "v1" / "report.md"
    original_open = reports.os.open
    swapped = False

    def swap_before_open(name, flags, *args, **kwargs):
        nonlocal swapped
        if name == "report.md" and kwargs.get("dir_fd") is not None and not swapped:
            swapped = True
            path.unlink()
            os.mkfifo(path)
        return original_open(name, flags, *args, **kwargs)

    monkeypatch.setattr(reports.os, "open", swap_before_open)
    thread, outcome = _call_in_thread(
        lambda: reports.load_published_report_document(
            "theme-a", "report-id", report_root=tmp_path
        )
    )
    thread.join(timeout=0.2)
    blocked = thread.is_alive()
    if blocked:
        _release_fifo_reader(path)
        thread.join(timeout=1)

    assert not blocked
    assert isinstance(outcome.get("error"), reports.ThemeResearchReportDocumentError)
    assert outcome["error"].code == "THEME_REPORT_ARTIFACT_UNAVAILABLE"


@pytest.mark.parametrize("component", ["root", "theme", "version"])
def test_symlinked_directories_are_rejected(monkeypatch, tmp_path, component) -> None:
    real = tmp_path / "real"
    record = _record(real)
    report_root = real
    if component == "root":
        report_root = tmp_path / "root-link"
        report_root.symlink_to(real, target_is_directory=True)
    elif component == "theme":
        target = tmp_path / "theme-target"
        (real / "theme-a").rename(target)
        (real / "theme-a").symlink_to(target, target_is_directory=True)
    else:
        target = tmp_path / "version-target"
        (real / "theme-a" / "v1").rename(target)
        (real / "theme-a" / "v1").symlink_to(target, target_is_directory=True)
    _install_store(monkeypatch, record)

    with pytest.raises(reports.ThemeResearchReportDocumentError) as exc_info:
        reports.load_published_report_document(
            "theme-a", "report-id", report_root=report_root
        )
    assert exc_info.value.code == "THEME_REPORT_ARTIFACT_UNAVAILABLE"


def test_each_load_rehashes_markdown(monkeypatch, tmp_path) -> None:
    record = _record(tmp_path)
    _install_store(monkeypatch, record)
    reports.load_published_report_document("theme-a", "report-id", report_root=tmp_path)
    (tmp_path / "theme-a" / "v1" / "report.md").write_bytes(b"changed")

    with pytest.raises(reports.ThemeResearchReportDocumentError) as exc_info:
        reports.load_published_report_document("theme-a", "report-id", report_root=tmp_path)
    assert exc_info.value.code == "THEME_REPORT_ARTIFACT_UNAVAILABLE"


@pytest.mark.parametrize("admin", [False, True])
@pytest.mark.parametrize("missing", ["root", "theme", "version", "artifact"])
def test_missing_artifact_after_store_lookup_is_unavailable(
    monkeypatch, tmp_path, admin, missing
) -> None:
    report_root = tmp_path / "reports"
    record = _record(report_root)
    _install_store(monkeypatch, record)
    if missing == "root":
        shutil.rmtree(report_root)
    elif missing == "theme":
        shutil.rmtree(report_root / "theme-a")
    elif missing == "version":
        shutil.rmtree(report_root / "theme-a" / "v1")
    else:
        (report_root / "theme-a" / "v1" / "report.md").unlink()

    with pytest.raises(reports.ThemeResearchReportDocumentError) as exc_info:
        if admin:
            reports.load_admin_report_document("report-id", report_root=report_root)
        else:
            reports.load_published_report_document(
                "theme-a", "report-id", report_root=report_root
            )
    assert exc_info.value.code == "THEME_REPORT_ARTIFACT_UNAVAILABLE"
    assert str(report_root) not in str(exc_info.value)


def test_store_errors_are_mapped_without_leaking(monkeypatch, tmp_path) -> None:
    def unavailable(*args, **kwargs):
        raise ThemeResearchReportError(
            "THEME_REPORT_STORE_UNAVAILABLE", "postgres password secret", {"sql": "secret"}
        )

    monkeypatch.setattr(reports.report_store, "get_admin_report_version", unavailable)
    with pytest.raises(reports.ThemeResearchReportDocumentError) as exc_info:
        reports.load_admin_report_document("report-id", report_root=tmp_path)
    assert exc_info.value.code == "THEME_REPORT_DOCUMENT_SERVICE_UNAVAILABLE"
    assert "secret" not in str(exc_info.value).lower()
    assert exc_info.value.details == {}


def test_admin_store_not_found_remains_document_not_found(monkeypatch, tmp_path) -> None:
    def missing(*args, **kwargs):
        raise ThemeResearchReportError("THEME_REPORT_NOT_FOUND", "database secret")

    monkeypatch.setattr(reports.report_store, "get_admin_report_version", missing)
    with pytest.raises(reports.ThemeResearchReportDocumentError) as exc_info:
        reports.load_admin_report_document("report-id", report_root=tmp_path)
    assert exc_info.value.code == "THEME_REPORT_DOCUMENT_NOT_FOUND"
    assert "secret" not in str(exc_info.value).lower()


def test_published_store_read_invalid_is_not_mapped_to_not_found(
    monkeypatch, tmp_path
) -> None:
    def invalid(*args, **kwargs):
        raise ThemeResearchReportError("THEME_REPORT_READ_INVALID", "database secret")

    monkeypatch.setattr(
        reports.report_store, "get_approved_report_artifact_record", invalid
    )
    with pytest.raises(reports.ThemeResearchReportDocumentError) as exc_info:
        reports.load_published_report_document(
            "theme-a", "report-id", report_root=tmp_path
        )
    assert exc_info.value.code == "THEME_REPORT_DOCUMENT_INVALID"
    assert "secret" not in str(exc_info.value).lower()


def test_unknown_store_exception_is_safe(monkeypatch, tmp_path) -> None:
    def explode(*args, **kwargs):
        raise RuntimeError("database password secret")

    monkeypatch.setattr(reports.report_store, "get_admin_report_version", explode)
    with pytest.raises(reports.ThemeResearchReportDocumentError) as exc_info:
        reports.load_admin_report_document("report-id", report_root=tmp_path)
    assert exc_info.value.code == "THEME_REPORT_DOCUMENT_SERVICE_UNAVAILABLE"
    assert "secret" not in str(exc_info.value).lower()


@pytest.mark.parametrize("exhaustion_errno", [errno.EMFILE, errno.ENFILE, errno.ENOMEM])
def test_resource_exhaustion_is_not_misreported(
    monkeypatch, tmp_path, exhaustion_errno
) -> None:
    record = _record(tmp_path)
    _install_store(monkeypatch, record)

    def exhausted(*args, **kwargs):
        raise OSError(exhaustion_errno, "resource exhausted")

    monkeypatch.setattr(reports.os, "open", exhausted)
    with pytest.raises(OSError) as exc_info:
        reports.load_published_report_document("theme-a", "report-id", report_root=tmp_path)
    assert exc_info.value.errno == exhaustion_errno


def test_memory_error_propagates(monkeypatch, tmp_path) -> None:
    record = _record(tmp_path)
    _install_store(monkeypatch, record)

    def exhausted(*args, **kwargs):
        raise MemoryError

    monkeypatch.setattr(reports.os, "open", exhausted)
    with pytest.raises(MemoryError):
        reports.load_published_report_document("theme-a", "report-id", report_root=tmp_path)


def test_required_posix_open_flag_does_not_silently_fallback(monkeypatch) -> None:
    monkeypatch.delattr(reports.os, "O_NONBLOCK")
    with pytest.raises(RuntimeError, match="O_NONBLOCK"):
        reports._required_os_flag("O_NONBLOCK")


def test_required_dir_fd_support_fails_explicitly(monkeypatch) -> None:
    monkeypatch.setattr(reports.os, "supports_dir_fd", set())
    with pytest.raises(RuntimeError, match="dir_fd"):
        reports._require_dir_fd_support(reports.os.open, "os.open")


def test_pdf_absent_is_stable(monkeypatch, tmp_path) -> None:
    record = _record(tmp_path)
    _install_store(monkeypatch, record)
    with pytest.raises(reports.ThemeResearchReportDocumentError) as exc_info:
        reports.resolve_published_report_pdf("theme-a", "report-id", report_root=tmp_path)
    assert exc_info.value.code == "THEME_REPORT_PDF_NOT_FOUND"


@pytest.mark.parametrize(
    ("relative_path", "checksum"),
    [("report.pdf", None), (None, "0" * 64), ("report.pdf", "bad")],
)
def test_inconsistent_pdf_metadata_is_artifact_unavailable(
    monkeypatch, tmp_path, relative_path, checksum
) -> None:
    record = _record(tmp_path, pdf=b"%PDF")
    record["pdf_relative_path"] = relative_path
    record["pdf_sha256"] = checksum
    _install_store(monkeypatch, record)

    with pytest.raises(reports.ThemeResearchReportDocumentError) as exc_info:
        reports.resolve_admin_report_pdf("report-id", report_root=tmp_path)
    assert exc_info.value.code == "THEME_REPORT_ARTIFACT_UNAVAILABLE"


def test_pdf_streams_verified_fd_and_closes_after_completion(monkeypatch, tmp_path) -> None:
    pdf = b"%PDF-1.7\nverified bytes\n%%EOF"
    record = _record(tmp_path, pdf=pdf)
    _install_store(monkeypatch, record)

    resolved = reports.resolve_published_report_pdf(
        "theme-a", "report-id", report_root=tmp_path
    )
    path = tmp_path / "theme-a" / "v1" / "report.pdf"
    replacement = path.with_name("replacement.pdf")
    replacement.write_bytes(b"replacement must not be served")
    os.replace(replacement, path)

    assert resolved.filename == "theme-report-v1.pdf"
    assert resolved.media_type == "application/pdf"
    assert resolved.content_length == len(pdf)
    assert b"".join(resolved.iter_chunks(chunk_size=7)) == pdf
    assert resolved.closed


def test_pdf_stream_is_immutable_after_in_place_source_change(monkeypatch, tmp_path) -> None:
    pdf = b"%PDF-1.7\nverified bytes\n%%EOF"
    record = _record(tmp_path, pdf=pdf)
    _install_store(monkeypatch, record)

    resolved = reports.resolve_published_report_pdf(
        "theme-a", "report-id", report_root=tmp_path
    )
    (tmp_path / "theme-a" / "v1" / "report.pdf").write_bytes(b"mutated in place")

    assert b"".join(resolved.iter_chunks()) == pdf
    resolved.close()
    assert resolved.closed


def test_pdf_context_manager_and_early_close_close_fd(monkeypatch, tmp_path) -> None:
    pdf = b"%PDF" + b"x" * 100
    record = _record(tmp_path, pdf=pdf)
    _install_store(monkeypatch, record)
    resolved = reports.resolve_admin_report_pdf("report-id", report_root=tmp_path)
    iterator = resolved.iter_chunks(chunk_size=10)
    assert next(iterator) == pdf[:10]
    resolved.close()
    assert resolved.closed
    with pytest.raises(ValueError):
        next(iterator)

    with reports.resolve_admin_report_pdf("report-id", report_root=tmp_path) as second:
        assert not second.closed
    assert second.closed


def test_pdf_stream_allows_only_one_consumer(monkeypatch, tmp_path) -> None:
    record = _record(tmp_path, pdf=b"%PDF-single-consumer")
    _install_store(monkeypatch, record)
    resolved = reports.resolve_admin_report_pdf("report-id", report_root=tmp_path)

    first = resolved.iter_chunks(chunk_size=4)
    with pytest.raises(ValueError, match="already been consumed"):
        resolved.iter_chunks(chunk_size=4)
    resolved.close()
    first.close()
    assert resolved.closed


def test_pdf_close_waits_for_read_and_cannot_read_reused_fd(
    monkeypatch, tmp_path
) -> None:
    safe_path = tmp_path / "safe.pdf"
    secret_path = tmp_path / "secret.pdf"
    safe_path.write_bytes(b"SAFE")
    secret_path.write_bytes(b"SECRET")
    owned_fd = os.open(safe_path, os.O_RDONLY)
    resolved = reports.ResolvedPdf(
        owned_fd, filename="theme-report.pdf", content_length=4
    )
    entered_read = threading.Event()
    release_read = threading.Event()
    close_returned = threading.Event()
    original_read = reports.os.read
    outcome: dict[str, object] = {}

    def paused_read(fd: int, size: int) -> bytes:
        entered_read.set()
        assert release_read.wait(timeout=2)
        return original_read(fd, size)

    monkeypatch.setattr(reports.os, "read", paused_read)
    iterator = resolved.iter_chunks(chunk_size=64)

    def consume() -> None:
        try:
            outcome["chunk"] = next(iterator)
        except BaseException as exc:
            outcome["error"] = exc

    reader = threading.Thread(target=consume)
    reader.start()
    assert entered_read.wait(timeout=1)

    def close() -> None:
        resolved.close()
        close_returned.set()

    closer = threading.Thread(target=close)
    closer.start()
    close_returned.wait(timeout=0.1)
    secret_fd = os.open(secret_path, os.O_RDONLY)
    try:
        release_read.set()
        reader.join(timeout=2)
        closer.join(timeout=2)
        assert outcome.get("chunk") == b"SAFE"
        assert "error" not in outcome
        assert close_returned.is_set()
        assert resolved.closed
    finally:
        os.close(secret_fd)


@pytest.mark.parametrize("mutation", ["checksum", "symlink", "directory", "too_large"])
def test_pdf_validation_matches_markdown_boundaries(monkeypatch, tmp_path, mutation) -> None:
    pdf = b"%PDF-safe"
    record = _record(tmp_path, pdf=pdf)
    path = tmp_path / "theme-a" / "v1" / "report.pdf"
    if mutation == "checksum":
        path.write_bytes(b"changed")
    elif mutation == "symlink":
        path.unlink()
        path.symlink_to(tmp_path / "outside.pdf")
    elif mutation == "directory":
        path.unlink()
        path.mkdir()
    else:
        data = b"x" * (50 * 1024 * 1024 + 1)
        path.write_bytes(data)
        record["pdf_sha256"] = _sha(data)
    _install_store(monkeypatch, record)

    with pytest.raises(reports.ThemeResearchReportDocumentError) as exc_info:
        reports.resolve_admin_report_pdf("report-id", report_root=tmp_path)
    assert exc_info.value.code == "THEME_REPORT_ARTIFACT_UNAVAILABLE"


def test_pdf_filename_is_safe_for_hostile_version(monkeypatch, tmp_path) -> None:
    pdf = b"%PDF"
    record = _record(tmp_path, pdf=pdf)
    hostile_dir = tmp_path / "theme-a" / "v1"
    # Path identity remains v1; only presentation metadata is hostile.
    record["version"] = "bad/..\\name\r\nheader\x00"
    _install_store(monkeypatch, record)
    with pytest.raises(reports.ThemeResearchReportDocumentError):
        reports.resolve_admin_report_pdf("report-id", report_root=tmp_path)


def test_pdf_filename_sanitizes_header_punctuation(monkeypatch, tmp_path) -> None:
    pdf = b"%PDF"
    record = _record(tmp_path, pdf=pdf)
    original = tmp_path / "theme-a" / "v1"
    renamed = tmp_path / "theme-a" / 'v"1;name'
    original.rename(renamed)
    record["version"] = 'v"1;name'
    record["manifest_relative_path"] = 'theme-a/v"1;name/manifest.json'
    _install_store(monkeypatch, record)

    with reports.resolve_admin_report_pdf("report-id", report_root=tmp_path) as resolved:
        assert resolved.filename == "theme-report-v-1-name.pdf"
        assert all(character not in resolved.filename for character in '/\\\r\n\x00";')


def test_pdf_filename_uses_bounded_fallback_for_control_only_version(
    monkeypatch, tmp_path
) -> None:
    pdf = b"%PDF"
    record = _record(tmp_path, pdf=pdf)
    original = tmp_path / "theme-a" / "v1"
    renamed = tmp_path / "theme-a" / "\r\n"
    original.rename(renamed)
    record["version"] = "\r\n"
    record["manifest_relative_path"] = "theme-a/\r\n/manifest.json"
    _install_store(monkeypatch, record)

    with reports.resolve_admin_report_pdf("report-id", report_root=tmp_path) as resolved:
        assert resolved.filename == "theme-report.pdf"
        assert len(resolved.filename) <= 100


def test_file_changed_during_read_is_rejected(monkeypatch, tmp_path) -> None:
    record = _record(tmp_path)
    _install_store(monkeypatch, record)
    original_read = reports.os.read
    changed = False

    def mutate(fd: int, size: int) -> bytes:
        nonlocal changed
        data = original_read(fd, size)
        if data and not changed:
            changed = True
            (tmp_path / "theme-a" / "v1" / "report.md").write_bytes(b"replacement")
        return data

    monkeypatch.setattr(reports.os, "read", mutate)
    with pytest.raises(reports.ThemeResearchReportDocumentError) as exc_info:
        reports.load_published_report_document("theme-a", "report-id", report_root=tmp_path)
    assert exc_info.value.code == "THEME_REPORT_ARTIFACT_UNAVAILABLE"


@pytest.mark.parametrize("component", ["root", "theme", "version"])
def test_directory_aba_during_read_is_rejected(monkeypatch, tmp_path, component) -> None:
    report_root = tmp_path / "reports"
    record = _record(report_root)
    _install_store(monkeypatch, record)
    original_read = reports.os.read
    changed = False

    def replace_directory(fd: int, size: int) -> bytes:
        nonlocal changed
        data = original_read(fd, size)
        if data and not changed:
            changed = True
            if component == "root":
                report_root.rename(tmp_path / "old-root")
                report_root.mkdir()
            elif component == "theme":
                theme = report_root / "theme-a"
                theme.rename(report_root / "old-theme")
                theme.mkdir()
            else:
                version = report_root / "theme-a" / "v1"
                version.rename(report_root / "theme-a" / "old-version")
                version.mkdir()
        return data

    monkeypatch.setattr(reports.os, "read", replace_directory)
    with pytest.raises(reports.ThemeResearchReportDocumentError) as exc_info:
        reports.load_published_report_document(
            "theme-a", "report-id", report_root=report_root
        )
    assert exc_info.value.code == "THEME_REPORT_ARTIFACT_UNAVAILABLE"


def _scan_result(*, indexed: int = 1, invalid: int = 0) -> ReportScanResult:
    now = datetime.now(UTC)
    return ReportScanResult(
        discovered=indexed + invalid,
        indexed=indexed,
        unchanged=0,
        invalid=invalid,
        errors=(
            ({"code": "MANIFEST_INVALID", "theme_id": "theme-a"},)
            if invalid
            else ()
        ),
        started_at=now,
        completed_at=now,
    )


def test_theme_report_scheduler_starts_immediately_periodically_and_without_overlap(
    tmp_path,
) -> None:
    from stock_research.dashboard.theme_research_report_scheduler import (
        ThemeResearchReportScheduler,
    )

    async def exercise() -> None:
        calls = 0
        active = 0
        maximum_active = 0
        first_started = threading.Event()
        release_first = threading.Event()

        def scan(root, *, limits, service):
            nonlocal calls, active, maximum_active
            calls += 1
            active += 1
            maximum_active = max(maximum_active, active)
            first_started.set()
            if calls == 1:
                release_first.wait(timeout=2)
            time.sleep(0.01)
            active -= 1
            return _scan_result(indexed=calls)

        scheduler = ThemeResearchReportScheduler(
            tmp_path,
            object(),
            "runtime",
            0.02,
            scan_fn=scan,
        )
        scheduler.start()
        scheduler.start()
        await asyncio.to_thread(first_started.wait, 1)
        second_run = asyncio.create_task(scheduler.run_once())
        await asyncio.sleep(0.01)
        release_first.set()
        await second_run
        await asyncio.sleep(0.05)
        await scheduler.stop()
        await scheduler.stop()

        assert calls >= 2
        assert maximum_active == 1
        diagnostics = scheduler.diagnostics()
        assert diagnostics["status"] == "ok"
        assert diagnostics["running"] is False
        assert diagnostics["last_result"]["indexed"] >= 1
        assert diagnostics["last_started_at"]
        assert diagnostics["last_completed_at"]

    asyncio.run(exercise())


def test_theme_report_scheduler_recovers_from_safe_error_and_detaches_diagnostics(
    tmp_path,
) -> None:
    from stock_research.dashboard.theme_research_report_scheduler import (
        ThemeResearchReportScheduler,
    )

    async def exercise() -> None:
        calls = 0

        def scan(root, *, limits, service):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError(f"secret path: {root}")
            return _scan_result(indexed=2)

        scheduler = ThemeResearchReportScheduler(
            tmp_path, object(), "runtime", 0.01, scan_fn=scan
        )
        assert scheduler.diagnostics()["status"] == "never_run"
        await scheduler.run_once()
        failed = scheduler.diagnostics()
        assert failed["status"] == "error"
        assert failed["last_result"] == {
            "error_code": "THEME_REPORT_SCAN_FAILED"
        }
        assert str(tmp_path) not in repr(failed)

        failed["last_result"]["error_code"] = "tampered"
        assert scheduler.diagnostics()["last_result"]["error_code"] == (
            "THEME_REPORT_SCAN_FAILED"
        )

        await scheduler.run_once()
        assert scheduler.diagnostics()["status"] == "ok"
        assert calls == 2

    asyncio.run(exercise())


@pytest.mark.parametrize(
    "fatal_error",
    [MemoryError(), OSError(errno.EMFILE, "secret resource")],
)
def test_theme_report_scheduler_stops_periodic_loop_on_fatal_resource_error(
    tmp_path, fatal_error
) -> None:
    from stock_research.dashboard.theme_research_report_scheduler import (
        ThemeResearchReportScheduler,
    )

    async def exercise() -> None:
        calls = 0

        def scan(root, *, limits, service):
            nonlocal calls
            calls += 1
            raise fatal_error

        scheduler = ThemeResearchReportScheduler(
            tmp_path, object(), "runtime", 0.01, scan_fn=scan
        )
        scheduler.start()
        await asyncio.sleep(0.05)
        await scheduler.stop()

        assert calls == 1
        assert scheduler.diagnostics()["status"] == "fatal"
        assert scheduler.diagnostics()["last_result"] == {
            "error_code": "THEME_REPORT_SCAN_RESOURCE_EXHAUSTED"
        }

    asyncio.run(exercise())


def test_theme_report_scheduler_rejects_non_positive_interval(tmp_path) -> None:
    from stock_research.dashboard.theme_research_report_scheduler import (
        ThemeResearchReportScheduler,
    )

    with pytest.raises(ValueError, match="interval_seconds"):
        ThemeResearchReportScheduler(tmp_path, object(), "runtime", 0)


def test_theme_report_scheduler_cancellation_waits_for_running_thread(tmp_path) -> None:
    from stock_research.dashboard.theme_research_report_scheduler import (
        ThemeResearchReportScheduler,
    )

    async def exercise() -> None:
        started = threading.Event()
        release = threading.Event()
        completed = threading.Event()

        def scan(root, *, limits, service):
            started.set()
            release.wait(timeout=2)
            completed.set()
            return _scan_result()

        scheduler = ThemeResearchReportScheduler(
            tmp_path, object(), "runtime", 60, scan_fn=scan
        )
        scheduler.start()
        await asyncio.to_thread(started.wait, 1)
        task = scheduler._task
        assert task is not None
        task.cancel()
        await asyncio.sleep(0.01)
        assert task.done() is False
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert completed.is_set()
        assert scheduler.diagnostics()["running"] is False
        assert scheduler._task is None

    asyncio.run(exercise())


def test_theme_report_scheduler_stop_propagates_caller_cancellation(tmp_path) -> None:
    from stock_research.dashboard.theme_research_report_scheduler import (
        ThemeResearchReportScheduler,
    )

    async def exercise() -> None:
        started = threading.Event()
        release = threading.Event()

        def scan(root, *, limits, service):
            started.set()
            release.wait(timeout=2)
            return _scan_result()

        scheduler = ThemeResearchReportScheduler(
            tmp_path, object(), "runtime", 60, scan_fn=scan
        )
        scheduler.start()
        await asyncio.to_thread(started.wait, 1)
        stopper = asyncio.create_task(scheduler.stop())
        await asyncio.sleep(0)
        stopper.cancel()
        await asyncio.sleep(0.01)
        assert stopper.done() is False
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await stopper
        assert scheduler._task is None

    asyncio.run(exercise())


def test_theme_report_scheduler_cancellation_wins_over_worker_error(tmp_path) -> None:
    from stock_research.dashboard.theme_research_report_scheduler import (
        ThemeResearchReportScheduler,
    )

    async def exercise() -> None:
        started = threading.Event()
        release = threading.Event()

        def scan(root, *, limits, service):
            started.set()
            release.wait(timeout=2)
            raise RuntimeError("secret scanner failure")

        scheduler = ThemeResearchReportScheduler(
            tmp_path, object(), "runtime", 60, scan_fn=scan
        )
        run = asyncio.create_task(scheduler.run_once())
        await asyncio.to_thread(started.wait, 1)
        run.cancel()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await run
        assert scheduler.diagnostics()["status"] == "never_run"
        assert "secret" not in repr(scheduler.diagnostics())

    asyncio.run(exercise())


def test_async_cleanup_helper_waits_through_repeated_native_cancellation() -> None:
    from stock_research.dashboard.async_cleanup import await_task_resiliently

    async def exercise() -> None:
        release = asyncio.Event()
        worker_finished = False

        async def worker() -> str:
            nonlocal worker_finished
            await release.wait()
            worker_finished = True
            return "done"

        underlying = asyncio.create_task(worker())
        waiter = asyncio.create_task(await_task_resiliently(underlying))
        await asyncio.sleep(0)
        waiter.cancel()
        await asyncio.sleep(0)
        waiter.cancel()
        waiter.cancel()
        await asyncio.sleep(0.01)
        assert waiter.done() is False
        assert worker_finished is False
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await waiter
        assert worker_finished is True
        assert underlying.done() is True

    asyncio.run(exercise())


def test_async_cleanup_helper_preserves_normal_and_underlying_outcomes() -> None:
    from stock_research.dashboard.async_cleanup import await_task_resiliently

    async def exercise() -> None:
        async def succeed() -> str:
            return "ok"

        async def fail() -> str:
            raise RuntimeError("worker failed")

        successful = asyncio.create_task(succeed())
        assert await await_task_resiliently(successful) == "ok"

        failed = asyncio.create_task(fail())
        with pytest.raises(RuntimeError, match="worker failed"):
            await await_task_resiliently(failed)

        cancelled = asyncio.create_task(asyncio.sleep(60))
        cancelled.cancel()
        with pytest.raises(asyncio.CancelledError):
            await await_task_resiliently(cancelled)

    asyncio.run(exercise())


def test_theme_report_scheduler_run_once_waits_through_repeated_task_cancel(
    tmp_path,
) -> None:
    from stock_research.dashboard.theme_research_report_scheduler import (
        ThemeResearchReportScheduler,
    )

    async def exercise() -> None:
        started = threading.Event()
        release = threading.Event()
        scan_finished = threading.Event()

        def scan(root, *, limits, service):
            started.set()
            release.wait(timeout=2)
            scan_finished.set()
            return _scan_result()

        scheduler = ThemeResearchReportScheduler(
            tmp_path, object(), "runtime", 60, scan_fn=scan
        )
        run = asyncio.create_task(scheduler.run_once())
        await asyncio.to_thread(started.wait, 1)
        run.cancel()
        await asyncio.sleep(0)
        run.cancel()
        run.cancel()
        await asyncio.sleep(0.01)
        assert run.done() is False
        assert scan_finished.is_set() is False
        assert scheduler.diagnostics()["running"] is True
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await run
        assert scan_finished.is_set() is True
        assert scheduler.diagnostics()["running"] is False

    asyncio.run(exercise())


def test_theme_report_scheduler_stop_waits_through_repeated_task_cancel(
    tmp_path,
) -> None:
    from stock_research.dashboard.theme_research_report_scheduler import (
        ThemeResearchReportScheduler,
    )

    async def exercise() -> None:
        started = threading.Event()
        release = threading.Event()
        scan_finished = threading.Event()

        def scan(root, *, limits, service):
            started.set()
            release.wait(timeout=2)
            scan_finished.set()
            return _scan_result()

        scheduler = ThemeResearchReportScheduler(
            tmp_path, object(), "runtime", 60, scan_fn=scan
        )
        scheduler.start()
        await asyncio.to_thread(started.wait, 1)
        stopper = asyncio.create_task(scheduler.stop())
        await asyncio.sleep(0)
        stopper.cancel()
        await asyncio.sleep(0)
        stopper.cancel()
        stopper.cancel()
        await asyncio.sleep(0.01)
        assert stopper.done() is False
        assert scan_finished.is_set() is False
        assert scheduler.diagnostics()["running"] is True
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await stopper
        assert scan_finished.is_set() is True
        assert scheduler.diagnostics()["running"] is False
        assert scheduler._task is None

    asyncio.run(exercise())


def test_theme_report_scheduler_run_once_waits_under_anyio_cancellation(
    tmp_path,
) -> None:
    from stock_research.dashboard.theme_research_report_scheduler import (
        ThemeResearchReportScheduler,
    )

    async def exercise() -> None:
        started = threading.Event()
        release = threading.Event()
        finished = anyio.Event()
        cancelled = False
        run_task: asyncio.Task | None = None

        def scan(root, *, limits, service):
            started.set()
            release.wait(timeout=2)
            return _scan_result()

        scheduler = ThemeResearchReportScheduler(
            tmp_path, object(), "runtime", 60, scan_fn=scan
        )

        async def run_once() -> None:
            nonlocal cancelled, run_task
            run_task = asyncio.current_task()
            try:
                await scheduler.run_once()
            except anyio.get_cancelled_exc_class():
                cancelled = True
                raise
            finally:
                finished.set()

        async with anyio.create_task_group() as task_group:
            task_group.start_soon(run_once)
            await anyio.to_thread.run_sync(started.wait, 1)
            task_group.cancel_scope.cancel()
            with anyio.CancelScope(shield=True):
                assert run_task is not None
                run_task.cancel()
                run_task.cancel()
                await anyio.sleep(0.02)
                assert finished.is_set() is False
                assert scheduler.diagnostics()["running"] is True
                release.set()

        assert cancelled is True
        assert finished.is_set() is True
        assert scheduler.diagnostics()["running"] is False

    anyio.run(exercise)


def test_theme_report_scheduler_stop_waits_under_anyio_cancellation(tmp_path) -> None:
    from stock_research.dashboard.theme_research_report_scheduler import (
        ThemeResearchReportScheduler,
    )

    async def exercise() -> None:
        started = threading.Event()
        release = threading.Event()
        stop_finished = anyio.Event()
        stop_cancelled = False

        def scan(root, *, limits, service):
            started.set()
            release.wait(timeout=2)
            return _scan_result()

        scheduler = ThemeResearchReportScheduler(
            tmp_path, object(), "runtime", 60, scan_fn=scan
        )
        scheduler.start()
        await anyio.to_thread.run_sync(started.wait, 1)

        async def stop() -> None:
            nonlocal stop_cancelled
            try:
                await scheduler.stop()
            except anyio.get_cancelled_exc_class():
                stop_cancelled = True
                raise
            finally:
                stop_finished.set()

        async with anyio.create_task_group() as task_group:
            task_group.start_soon(stop)
            await anyio.sleep(0)
            task_group.cancel_scope.cancel()
            with anyio.CancelScope(shield=True):
                await anyio.sleep(0.02)
                assert stop_finished.is_set() is False
                assert scheduler.diagnostics()["running"] is True
                release.set()

        assert stop_cancelled is True
        assert stop_finished.is_set() is True
        assert scheduler.diagnostics()["running"] is False
        assert scheduler._task is None

    anyio.run(exercise)


def _api_client(monkeypatch, *, role: str | None = "user") -> TestClient:
    monkeypatch.setenv("STOCK_RESEARCH_DASHBOARD_AUTH_REQUIRED", "false")
    user = (
        CurrentUser("user:1", "operator", "Operator", role, True)
        if role is not None
        else None
    )
    monkeypatch.setattr(
        dashboard_app,
        "load_current_user_from_session",
        lambda token: user if token == "session" else None,
    )
    return TestClient(dashboard_app.create_app())


def _session_cookies() -> dict[str, str]:
    return {
        "stock_research_session": "session",
        "stock_research_csrf": "csrf-token",
    }


def test_theme_report_api_requires_session_even_when_global_auth_is_disabled(
    monkeypatch,
) -> None:
    client = _api_client(monkeypatch, role=None)

    response = client.get("/api/research/theme-decomposition/themes/theme-a/reports")

    assert response.status_code == 401
    assert response.json()["detail"] == "not_authenticated"


def test_theme_report_api_allows_normal_reads_but_rejects_admin_for_user(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        dashboard_app.theme_research_report_store,
        "list_approved_report_versions",
        lambda theme_id, service: {"total": 1, "items": [{"theme_id": theme_id}]},
    )
    client = _api_client(monkeypatch)

    normal = client.get(
        "/api/research/theme-decomposition/themes/theme-a/reports",
        cookies=_session_cookies(),
    )
    admin = client.get(
        "/api/admin/theme-research/reports?status=pending_review",
        cookies=_session_cookies(),
    )

    assert normal.status_code == 200
    assert normal.json() == {"total": 1, "items": [{"theme_id": "theme-a"}]}
    assert admin.status_code == 403
    assert admin.json()["detail"] == "admin_required"


def test_theme_report_admin_list_and_diagnostics_are_admin_only(monkeypatch) -> None:
    monkeypatch.setattr(
        dashboard_app.theme_research_report_store,
        "list_admin_report_versions",
        lambda status, service: {"total": 0, "items": [], "status": status},
    )
    client = _api_client(monkeypatch, role="admin")
    app = client.app
    monkeypatch.setattr(
        app.state.theme_research_report_scheduler,
        "diagnostics",
        lambda: {"status": "never_run", "running": False},
    )

    listed = client.get(
        "/api/admin/theme-research/reports?status=rejected",
        cookies=_session_cookies(),
    )
    diagnostics = client.get(
        "/api/admin/theme-research/report-index/status",
        cookies=_session_cookies(),
    )

    assert listed.status_code == 200
    assert listed.json()["status"] == "rejected"
    assert diagnostics.status_code == 200
    assert diagnostics.json() == {"status": "never_run", "running": False}


@pytest.mark.parametrize(
    "path,payload",
    [
        (
            "/api/admin/theme-research/reports/report-id/publish",
            {
                "expected_row_version": 0,
                "idempotency_key": "key",
                "comment": "ok",
            },
        ),
        (
            "/api/admin/theme-research/reports/report-id/publish",
            {
                "expected_row_version": 1,
                "idempotency_key": " key ",
                "comment": "ok",
            },
        ),
        (
            "/api/admin/theme-research/reports/report-id/reject",
            {
                "expected_row_version": 1,
                "idempotency_key": "key",
                "reason": "   ",
            },
        ),
        (
            "/api/admin/theme-research/reports/report-id/reject",
            {
                "expected_row_version": 1,
                "idempotency_key": "key",
                "reason": "no",
                "actor_user_id": "attacker",
            },
        ),
    ],
)
def test_theme_report_mutation_payload_validation(monkeypatch, path, payload) -> None:
    client = _api_client(monkeypatch, role="admin")

    response = client.post(path, json=payload, cookies=_session_cookies())

    assert response.status_code == 422


def test_theme_report_publish_requires_csrf(monkeypatch) -> None:
    def reject_csrf(**kwargs):
        raise PermissionError("csrf_invalid")

    monkeypatch.setattr(dashboard_app, "validate_csrf", reject_csrf)
    client = _api_client(monkeypatch, role="admin")

    response = client.post(
        "/api/admin/theme-research/reports/report-id/publish",
        json={
            "expected_row_version": 1,
            "idempotency_key": "key",
            "comment": "approved",
        },
        cookies=_session_cookies(),
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "csrf_invalid"


@pytest.mark.parametrize(
    "action,text_field",
    [("publish", "comment"), ("reject", "reason")],
)
def test_theme_report_mutations_use_authenticated_actor_and_request_id(
    monkeypatch, action, text_field
) -> None:
    calls = []

    def mutate(report_version_id, **kwargs):
        calls.append((report_version_id, kwargs))
        return {"report_version_id": report_version_id, "status": action}

    monkeypatch.setattr(
        dashboard_app.theme_research_report_store,
        f"{action}_report_version",
        mutate,
    )
    client = _api_client(monkeypatch, role="admin")
    payload = {
        "expected_row_version": 2,
        "idempotency_key": "request-key",
        text_field: "review text",
    }

    response = client.post(
        f"/api/admin/theme-research/reports/report-id/{action}",
        json=payload,
        cookies=_session_cookies(),
        headers={"x-csrf-token": "csrf-token", "x-request-id": "req-123"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "report": {"report_version_id": "report-id", "status": action}
    }
    assert calls == [
        (
            "report-id",
            {
                "expected_row_version": 2,
                "actor_user_id": "user:1",
                "actor_role": "admin",
                text_field: "review text",
                "request_id": "req-123",
                "idempotency_key": "request-key",
                "service": dashboard_app.SETTINGS.theme_research_runtime_service,
            },
        )
    ]


class _UntrustedNotFoundError(RuntimeError):
    code = "PRIVATE_NOT_FOUND"


@pytest.mark.parametrize(
    "error,status_code",
    [
        (ThemeResearchReportError("THEME_REPORT_NOT_FOUND", "db secret"), 404),
        (ThemeResearchReportError("THEME_REPORT_THEME_NOT_FOUND", "db secret"), 404),
        (
            reports.ThemeResearchReportDocumentError(
                "THEME_REPORT_DOCUMENT_NOT_FOUND", "filesystem secret"
            ),
            404,
        ),
        (ThemeResearchReportError("THEME_REPORT_READ_INVALID", "db secret"), 400),
        (ThemeResearchReportError("THEME_REPORT_STATE_CONFLICT", "db secret"), 409),
        (ThemeResearchReportError("THEME_REPORT_STORE_UNAVAILABLE", "db secret"), 503),
        (_UntrustedNotFoundError("secret"), 503),
        (MemoryError("secret"), 503),
        (RuntimeError("secret"), 503),
    ],
)
def test_theme_report_api_maps_errors_without_internal_text(
    monkeypatch, error, status_code
) -> None:
    def fail(theme_id, *, service):
        raise error

    monkeypatch.setattr(
        dashboard_app.theme_research_report_store,
        "list_approved_report_versions",
        fail,
    )
    client = _api_client(monkeypatch)

    response = client.get(
        "/api/research/theme-decomposition/themes/theme-a/reports",
        cookies=_session_cookies(),
    )

    assert response.status_code == status_code
    body = response.json()
    assert body["detail"]["error_code"]
    assert "secret" not in repr(body)


class _FakeResolvedPdf:
    filename = 'report\r\n"unsafe.pdf'
    media_type = "application/pdf"
    content_length = 8

    def __init__(self) -> None:
        self.closed = False

    def iter_chunks(self):
        try:
            yield b"%PDF"
            yield b"body"
        finally:
            self.close()

    def close(self) -> None:
        self.closed = True


def test_theme_report_pdf_streams_safe_headers_and_closes(monkeypatch) -> None:
    resolved = _FakeResolvedPdf()
    monkeypatch.setattr(
        dashboard_app.theme_research_reports,
        "resolve_published_report_pdf",
        lambda theme_id, report_version_id, **kwargs: resolved,
    )
    client = _api_client(monkeypatch)

    response = client.get(
        "/api/research/theme-decomposition/themes/theme-a/reports/report-id/pdf",
        cookies=_session_cookies(),
    )

    assert response.status_code == 200
    assert response.content == b"%PDFbody"
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-length"] == "8"
    assert "\r" not in response.headers["content-disposition"]
    assert "\n" not in response.headers["content-disposition"]
    assert response.headers["content-disposition"].count('"') == 2
    assert resolved.closed is True


def test_theme_report_pdf_response_closes_on_early_iterator_close() -> None:
    resolved = _FakeResolvedPdf()
    response = dashboard_app._theme_report_pdf_response(resolved)

    async def consume_one_chunk() -> None:
        assert await anext(response.body_iterator) == b"%PDF"
        await response.body_iterator.aclose()

    asyncio.run(consume_one_chunk())

    assert resolved.closed is True


def test_theme_report_pdf_response_closes_before_first_chunk_is_read() -> None:
    resolved = _FakeResolvedPdf()
    response = dashboard_app._theme_report_pdf_response(resolved)

    asyncio.run(response.body_iterator.aclose())

    assert resolved.closed is True


def test_theme_report_pdf_response_closes_after_normal_async_iteration() -> None:
    resolved = _FakeResolvedPdf()
    response = dashboard_app._theme_report_pdf_response(resolved)

    async def consume() -> list[bytes]:
        return [chunk async for chunk in response.body_iterator]

    assert asyncio.run(consume()) == [b"%PDF", b"body"]
    assert resolved.closed is True


class _FailingPdfIterator:
    def __init__(self, resolved) -> None:
        self.resolved = resolved
        self.closed = False

    def __iter__(self):
        return self

    def __next__(self):
        raise OSError(errno.EIO, "secret read failure")

    def close(self) -> None:
        self.closed = True


class _FailingResolvedPdf(_FakeResolvedPdf):
    def __init__(self) -> None:
        super().__init__()
        self.iterator = _FailingPdfIterator(self)

    def iter_chunks(self):
        return self.iterator


def test_theme_report_pdf_response_closes_on_async_read_error() -> None:
    resolved = _FailingResolvedPdf()
    response = dashboard_app._theme_report_pdf_response(resolved)

    async def consume() -> None:
        with pytest.raises(OSError, match="secret read failure"):
            await anext(response.body_iterator)

    asyncio.run(consume())

    assert resolved.iterator.closed is True
    assert resolved.closed is True


class _BlockingPdfIterator:
    def __init__(self) -> None:
        self.entered = threading.Event()
        self.release = threading.Event()
        self.executing = False
        self.closed = False
        self.closed_while_executing = False

    def __iter__(self):
        return self

    def __next__(self):
        self.executing = True
        self.entered.set()
        self.release.wait(timeout=2)
        self.executing = False
        return b"chunk"

    def close(self) -> None:
        self.closed_while_executing = self.executing
        self.closed = True


class _BlockingResolvedPdf(_FakeResolvedPdf):
    def __init__(self) -> None:
        super().__init__()
        self.iterator = _BlockingPdfIterator()

    def iter_chunks(self):
        return self.iterator


def test_theme_report_pdf_async_close_waits_for_threaded_read() -> None:
    resolved = _BlockingResolvedPdf()
    response = dashboard_app._theme_report_pdf_response(resolved)

    async def exercise() -> None:
        read = asyncio.create_task(anext(response.body_iterator))
        await asyncio.to_thread(resolved.iterator.entered.wait, 1)
        close = asyncio.create_task(response.body_iterator.aclose())
        await asyncio.sleep(0.01)
        assert close.done() is False
        resolved.iterator.release.set()
        assert await read == b"chunk"
        await close

    asyncio.run(exercise())

    assert resolved.iterator.closed is True
    assert resolved.iterator.closed_while_executing is False
    assert resolved.closed is True


def test_theme_report_pdf_cancelled_read_waits_then_closes() -> None:
    resolved = _BlockingResolvedPdf()
    response = dashboard_app._theme_report_pdf_response(resolved)

    async def exercise() -> None:
        read = asyncio.create_task(anext(response.body_iterator))
        await asyncio.to_thread(resolved.iterator.entered.wait, 1)
        read.cancel()
        await asyncio.sleep(0.01)
        assert read.done() is False
        resolved.iterator.release.set()
        with pytest.raises(asyncio.CancelledError):
            await read

    asyncio.run(exercise())

    assert resolved.iterator.closed is True
    assert resolved.iterator.closed_while_executing is False
    assert resolved.closed is True


def test_theme_report_pdf_repeated_cancel_waits_then_closes() -> None:
    resolved = _BlockingResolvedPdf()
    response = dashboard_app._theme_report_pdf_response(resolved)

    async def exercise() -> None:
        read = asyncio.create_task(anext(response.body_iterator))
        await asyncio.to_thread(resolved.iterator.entered.wait, 1)
        read.cancel()
        await asyncio.sleep(0)
        read.cancel()
        read.cancel()
        await asyncio.sleep(0.01)
        assert read.done() is False
        assert resolved.iterator.closed is False
        resolved.iterator.release.set()
        with pytest.raises(asyncio.CancelledError):
            await read

    asyncio.run(exercise())

    assert resolved.iterator.closed is True
    assert resolved.iterator.closed_while_executing is False
    assert resolved.closed is True


def test_theme_report_pdf_anyio_and_native_cancel_wait_then_close() -> None:
    resolved = _BlockingResolvedPdf()
    response = dashboard_app._theme_report_pdf_response(resolved)

    async def exercise() -> None:
        finished = anyio.Event()
        cancelled = False
        read_task: asyncio.Task | None = None

        async def read() -> None:
            nonlocal cancelled, read_task
            read_task = asyncio.current_task()
            try:
                await anext(response.body_iterator)
            except anyio.get_cancelled_exc_class():
                cancelled = True
                raise
            finally:
                finished.set()

        async with anyio.create_task_group() as task_group:
            task_group.start_soon(read)
            await anyio.to_thread.run_sync(resolved.iterator.entered.wait, 1)
            task_group.cancel_scope.cancel()
            with anyio.CancelScope(shield=True):
                assert read_task is not None
                read_task.cancel()
                read_task.cancel()
                await anyio.sleep(0.02)
                assert finished.is_set() is False
                assert resolved.iterator.closed is False
                resolved.iterator.release.set()

        assert cancelled is True
        assert finished.is_set() is True

    anyio.run(exercise)

    assert resolved.iterator.closed is True
    assert resolved.iterator.closed_while_executing is False
    assert resolved.closed is True


def test_theme_report_pdf_response_closes_when_client_send_fails() -> None:
    resolved = _FakeResolvedPdf()
    response = dashboard_app._theme_report_pdf_response(resolved)

    async def send(message) -> None:
        if message["type"] == "http.response.body":
            raise OSError(errno.EPIPE, "client disconnected")

    async def exercise() -> None:
        with pytest.raises(OSError, match="client disconnected"):
            await response.stream_response(send)

    asyncio.run(exercise())

    assert resolved.closed is True


def test_theme_report_pdf_asgi_disconnect_waits_for_real_threaded_read(
    monkeypatch,
) -> None:
    read_fd, write_fd = os.pipe()
    resolved = reports.ResolvedPdf(
        read_fd,
        filename="theme-report.pdf",
        content_length=4,
    )
    entered = threading.Event()
    original_next = dashboard_app._next_pdf_chunk

    def observed_next(iterator):
        entered.set()
        return original_next(iterator)

    monkeypatch.setattr(dashboard_app, "_next_pdf_chunk", observed_next)
    response = dashboard_app._theme_report_pdf_response(resolved)
    timer: threading.Timer | None = None

    async def exercise() -> tuple[list[BaseException], int, int]:
        heartbeat_count = 0
        heartbeat_at_disconnect = 0
        done = anyio.Event()
        errors: list[BaseException] = []

        async def heartbeat() -> None:
            nonlocal heartbeat_count
            while not done.is_set():
                heartbeat_count += 1
                await anyio.sleep(0)

        async def receive():
            nonlocal heartbeat_at_disconnect, timer
            await anyio.to_thread.run_sync(entered.wait, 1)
            heartbeat_at_disconnect = heartbeat_count
            timer = threading.Timer(0.1, os.write, args=(write_fd, b"%PDF"))
            timer.start()
            return {"type": "http.disconnect"}

        async def send(message) -> None:
            return None

        async def call_response() -> None:
            try:
                await response(
                    {
                        "type": "http",
                        "asgi": {"version": "3.0", "spec_version": "2.3"},
                        "http_version": "1.1",
                        "method": "GET",
                        "scheme": "http",
                        "path": "/report.pdf",
                        "raw_path": b"/report.pdf",
                        "query_string": b"",
                        "headers": [],
                        "client": ("test", 1),
                        "server": ("test", 80),
                        "root_path": "",
                    },
                    receive,
                    send,
                )
            except BaseException as exc:
                errors.append(exc)
            finally:
                done.set()

        async with anyio.create_task_group() as task_group:
            task_group.start_soon(heartbeat)
            task_group.start_soon(call_response)
            await done.wait()
            task_group.cancel_scope.cancel()
        return errors, heartbeat_at_disconnect, heartbeat_count

    try:
        errors, heartbeat_at_disconnect, heartbeat_count = anyio.run(exercise)
    finally:
        if timer is not None:
            timer.join(timeout=1)
        os.close(write_fd)
        resolved.close()

    assert errors == []
    assert heartbeat_count > heartbeat_at_disconnect
    assert resolved.closed is True


def test_theme_report_pdf_response_closes_if_response_construction_fails(
    monkeypatch,
) -> None:
    resolved = _FakeResolvedPdf()

    def fail(*args, **kwargs):
        raise RuntimeError("response failure")

    monkeypatch.setattr(dashboard_app, "_ResolvedPdfStreamingResponse", fail)

    with pytest.raises(RuntimeError, match="response failure"):
        dashboard_app._theme_report_pdf_response(resolved)
    assert resolved.closed is True


def test_pending_report_document_is_hidden_normally_but_available_to_admin(
    monkeypatch,
) -> None:
    def hidden(*args, **kwargs):
        raise reports.ThemeResearchReportDocumentError(
            "THEME_REPORT_NOT_FOUND", "filesystem secret"
        )

    monkeypatch.setattr(
        dashboard_app.theme_research_reports,
        "load_published_report_document",
        hidden,
    )
    monkeypatch.setattr(
        dashboard_app.theme_research_reports,
        "load_admin_report_document",
        lambda report_version_id, **kwargs: {
            "report_version_id": report_version_id,
            "status": "pending_review",
        },
    )
    client = _api_client(monkeypatch, role="admin")

    normal = client.get(
        "/api/research/theme-decomposition/themes/theme-a/reports/report-id",
        cookies=_session_cookies(),
    )
    admin = client.get(
        "/api/admin/theme-research/reports/report-id",
        cookies=_session_cookies(),
    )

    assert normal.status_code == 404
    assert normal.json()["detail"]["error_code"] == "THEME_REPORT_NOT_FOUND"
    assert admin.status_code == 200
    assert admin.json()["status"] == "pending_review"


def test_pending_report_pdf_is_hidden_normally_but_available_to_admin(
    monkeypatch,
) -> None:
    admin_resolved = _FakeResolvedPdf()

    def hidden(*args, **kwargs):
        raise reports.ThemeResearchReportDocumentError(
            "THEME_REPORT_NOT_FOUND", "filesystem secret"
        )

    monkeypatch.setattr(
        dashboard_app.theme_research_reports,
        "resolve_published_report_pdf",
        hidden,
    )
    monkeypatch.setattr(
        dashboard_app.theme_research_reports,
        "resolve_admin_report_pdf",
        lambda report_version_id, **kwargs: admin_resolved,
    )
    client = _api_client(monkeypatch, role="admin")

    normal = client.get(
        "/api/research/theme-decomposition/themes/theme-a/reports/report-id/pdf",
        cookies=_session_cookies(),
    )
    admin = client.get(
        "/api/admin/theme-research/reports/report-id/pdf",
        cookies=_session_cookies(),
    )

    assert normal.status_code == 404
    assert admin.status_code == 200
    assert admin.content == b"%PDFbody"
    assert admin_resolved.closed is True


def test_theme_report_scheduler_runs_once_and_stops_with_app_lifespan(
    monkeypatch, tmp_path
) -> None:
    calls = []

    def scan(root, *, limits, service):
        calls.append((root, limits, service))
        return _scan_result()

    monkeypatch.setattr(dashboard_app, "scan_theme_research_report_root", scan)
    monkeypatch.setattr(
        dashboard_app,
        "SETTINGS",
        replace(
            dashboard_app.SETTINGS,
            theme_research_report_root=tmp_path,
            theme_research_report_scan_interval_seconds=60,
        ),
    )
    app = dashboard_app.create_app()

    with TestClient(app):
        deadline = time.monotonic() + 1
        while not calls and time.monotonic() < deadline:
            time.sleep(0.01)

    assert len(calls) == 1
    assert app.state.theme_research_report_scheduler.diagnostics()["running"] is False


def test_theme_report_scheduler_start_failure_does_not_block_app_lifespan(
    monkeypatch, caplog
) -> None:
    app = dashboard_app.create_app()
    app.state.public_news_scheduler.enabled = False

    def fail_start():
        raise RuntimeError("secret scheduler path")

    monkeypatch.setattr(app.state.theme_research_report_scheduler, "start", fail_start)

    with TestClient(app) as client:
        response = client.get("/openapi.json")

    assert response.status_code == 200
    assert "secret scheduler path" not in caplog.text
    assert "theme research report scheduler failed to start" in caplog.text


def test_dashboard_lifespan_cancellation_stops_both_schedulers(tmp_path) -> None:
    from stock_research.dashboard.theme_research_report_scheduler import (
        ThemeResearchReportScheduler,
    )

    scan_started = threading.Event()
    scan_release = threading.Event()
    scan_finished = threading.Event()

    def scan(root, *, limits, service):
        scan_started.set()
        scan_release.wait(timeout=2)
        scan_finished.set()
        return _scan_result()

    class PublicScheduler:
        enabled = True

        def __init__(self) -> None:
            self.started = False
            self.stopped = False

        def start(self) -> None:
            self.started = True

        async def stop(self) -> None:
            self.stopped = True

    app = dashboard_app.create_app()
    public_scheduler = PublicScheduler()
    report_scheduler = ThemeResearchReportScheduler(
        tmp_path, object(), "runtime", 60, scan_fn=scan
    )
    app.state.public_news_scheduler = public_scheduler
    app.state.theme_research_report_scheduler = report_scheduler

    async def exercise() -> bool:
        entered = anyio.Event()
        cancelled = False

        async def serve() -> None:
            nonlocal cancelled
            try:
                async with app.router.lifespan_context(app):
                    entered.set()
                    await anyio.sleep_forever()
            except anyio.get_cancelled_exc_class():
                cancelled = True
                raise

        async with anyio.create_task_group() as task_group:
            task_group.start_soon(serve)
            await entered.wait()
            await anyio.to_thread.run_sync(scan_started.wait, 1)
            task_group.cancel_scope.cancel()
            with anyio.CancelScope(shield=True):
                await anyio.sleep(0.02)
                assert public_scheduler.stopped is False
                assert report_scheduler.diagnostics()["running"] is True
                scan_release.set()
        return cancelled

    assert anyio.run(exercise) is True
    assert scan_finished.is_set() is True
    assert report_scheduler.diagnostics()["running"] is False
    assert public_scheduler.started is True
    assert public_scheduler.stopped is True
