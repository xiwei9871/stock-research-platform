from __future__ import annotations

from pathlib import Path

import pytest

from stock_research.research_project_v2_1.acquisition_import import (
    LocalFileProvider,
    build_manual_import_request,
)
from stock_research.research_project_v2_1.acquisition_storage import read_acquisition_attempt
from stock_research.research_project_v2_1.layout import LayeredResearchLayout


PROVENANCE = {
    "created_by": "Codex",
    "actor_type": "codex",
    "agent_run_id": "run:manual-import-test",
    "created_at": "2026-07-20T08:00:00Z",
    "created_in_version": "research_version:ai_compute_pcb_industry_bottleneck:0.2.1",
    "review_status": "unreviewed",
}


def request(path: Path, declared_mime_type: str, **overrides) -> dict:
    values = {
        "project_id": "research_project:ai_compute_pcb_industry_bottleneck",
        "research_version_context": "research_version:ai_compute_pcb_industry_bottleneck:0.2.1",
        "requirement_id": "requirement:ai_compute_pcb_industry_bottleneck:r2b_er01",
        "candidate_id": None,
        "local_path": str(path),
        "source_title": "Imported official document",
        "publisher": "Example Standards Body",
        "original_url": "https://example.com/document",
        "source_note": None,
        "publication_date": "2026-07-01",
        "imported_at": "2026-07-20T08:00:00Z",
        "imported_by": "Codex",
        "actor_type": "codex",
        "declared_mime_type": declared_mime_type,
        "access_or_license_note": "Public technical document.",
        "locator_metadata": {"page_locators_expected": declared_mime_type == "application/pdf"},
        "provenance": PROVENANCE,
    }
    values.update(overrides)
    return build_manual_import_request(**values)


@pytest.mark.parametrize(
    ("filename", "data", "mime_type"),
    [
        ("source.pdf", b"%PDF-1.4\nfixture", "application/pdf"),
        ("source.html", b"<html><body>fixture</body></html>", "text/html"),
        ("source.txt", b"fixture text", "text/plain"),
        ("source.md", b"# Fixture\n", "text/markdown"),
        ("source.json", b'{"fixture":true}', "application/json"),
        ("source.csv", b"name,value\nfixture,1\n", "text/csv"),
        ("docling.json", b'{"schema_name":"DoclingDocument"}', "application/vnd.docling+json"),
    ],
)
def test_local_provider_imports_supported_files(
    tmp_path: Path, filename: str, data: bytes, mime_type: str
) -> None:
    source = tmp_path / filename
    source.write_bytes(data)
    layout = LayeredResearchLayout((tmp_path / "v2_1").resolve())
    layout.root.mkdir(mode=0o700)
    provider = LocalFileProvider(
        now=lambda: "2026-07-20T08:00:01Z",
        monotonic_ms=iter([0, 10]).__next__,
    )
    result = provider.acquire(request(source, mime_type), layout=layout)
    assert result.attempt["provider"] == "local_file"
    assert result.attempt["status"] == "acquired"
    assert result.artifact is not None
    assert result.artifact["content_type"] == mime_type
    assert (layout.root / result.artifact["raw_artifact_path"]).read_bytes() == data
    assert read_acquisition_attempt(result.attempt["attempt_id"], layout=layout) == result.attempt


def test_local_provider_marks_incomplete_metadata_without_inventing_values(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    source.write_text("fixture", encoding="utf-8")
    layout = LayeredResearchLayout((tmp_path / "v2_1").resolve())
    layout.root.mkdir(mode=0o700)
    import_request = request(
        source,
        "text/plain",
        publisher=None,
        original_url=None,
        source_note="Provided by a human reviewer.",
        publication_date=None,
    )
    assert import_request["metadata_status"] == "incomplete_metadata"
    result = LocalFileProvider(
        now=lambda: "2026-07-20T08:00:01Z",
        monotonic_ms=iter([0, 10]).__next__,
    ).acquire(import_request, layout=layout)
    assert result.artifact["publisher"] is None
    assert result.artifact["published_at"] is None
    assert result.artifact["access_status"] == "incomplete_metadata"


def test_local_provider_records_missing_file_as_failed_attempt(tmp_path: Path) -> None:
    missing = tmp_path / "missing.pdf"
    layout = LayeredResearchLayout((tmp_path / "v2_1").resolve())
    layout.root.mkdir(mode=0o700)
    result = LocalFileProvider(
        now=lambda: "2026-07-20T08:00:01Z",
        monotonic_ms=iter([0, 10]).__next__,
    ).acquire(request(missing, "application/pdf"), layout=layout)
    assert result.artifact is None
    assert result.attempt["status"] == "failed"
    assert result.attempt["failure_code"] == "manually_unavailable"


def test_local_provider_rejects_declared_mime_mismatch(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    source.write_text("not a pdf", encoding="utf-8")
    layout = LayeredResearchLayout((tmp_path / "v2_1").resolve())
    layout.root.mkdir(mode=0o700)
    result = LocalFileProvider(
        now=lambda: "2026-07-20T08:00:01Z",
        monotonic_ms=iter([0, 10]).__next__,
    ).acquire(request(source, "application/pdf"), layout=layout)
    assert result.artifact is None
    assert result.attempt["failure_code"] == "invalid_mime_type"
