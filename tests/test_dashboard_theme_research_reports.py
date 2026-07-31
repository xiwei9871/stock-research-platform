from __future__ import annotations

import errno
import hashlib
import os
import shutil
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest

from stock_research.dashboard import theme_research_reports as reports
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
    for forbidden in ("<script", "<img", "onerror", "<style", "<iframe", "javascript:", "data:"):
        assert forbidden not in lowered


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
