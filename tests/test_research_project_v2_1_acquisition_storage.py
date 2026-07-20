from __future__ import annotations

from pathlib import Path

import pytest

from stock_research.research_project_v2.errors import ResearchProjectV2Error
from stock_research.research_project_v2_1.acquisition_contracts import (
    AcquisitionContext,
    build_acquisition_attempt,
)
from stock_research.research_project_v2_1.acquisition_storage import (
    publish_raw_bytes,
    read_acquisition_attempt,
    write_acquisition_attempt,
)
from stock_research.research_project_v2_1.layout import LayeredResearchLayout


PROVENANCE = {
    "created_by": "Codex",
    "actor_type": "codex",
    "agent_run_id": "run:storage-test",
    "created_at": "2026-07-20T08:00:00Z",
    "created_in_version": "research_version:ai_compute_pcb_industry_bottleneck:0.2.1",
    "review_status": "unreviewed",
}


def context() -> AcquisitionContext:
    return AcquisitionContext(
        project_id="research_project:ai_compute_pcb_industry_bottleneck",
        research_version_context="research_version:ai_compute_pcb_industry_bottleneck:0.2.1",
        requirement_id="requirement:ai_compute_pcb_industry_bottleneck:r2b_er01",
        candidate_id="source_candidate:" + "a" * 24,
        provenance=PROVENANCE,
    )


def test_attempt_identity_is_stable_and_content_addressed() -> None:
    first = build_acquisition_attempt(
        context=context(),
        provider="direct_http",
        request_mode="fetch",
        proxy_mode="direct",
        requested_url="https://example.com/source.pdf",
        resolved_url="https://example.com/source.pdf",
        attempted_at="2026-07-20T08:00:00Z",
        completed_at="2026-07-20T08:00:01Z",
        elapsed_ms=1000,
        status="failed",
        failure_code="http_error",
        http_status=404,
        redirect_chain=[],
        content_type="text/html",
        bytes_received=0,
        retry_count=0,
        raw_artifact_id=None,
        diagnostic_summary="HTTP 404.",
    )
    second = build_acquisition_attempt(**{**first.build_args, "context": context()})
    assert first.payload == second.payload
    assert first.payload["attempt_id"].startswith("acquisition_attempt:")
    assert len(first.payload["content_hash"]) == 64


def test_attempt_storage_is_immutable_and_duplicate_safe(tmp_path: Path) -> None:
    layout = LayeredResearchLayout((tmp_path / "v2_1").resolve())
    layout.root.mkdir(mode=0o700)
    built = build_acquisition_attempt(
        context=context(),
        provider="direct_http",
        request_mode="fetch",
        proxy_mode="direct",
        requested_url="https://example.com/source.pdf",
        resolved_url=None,
        attempted_at="2026-07-20T08:00:00Z",
        completed_at="2026-07-20T08:00:01Z",
        elapsed_ms=1000,
        status="failed",
        failure_code="connection_timeout",
        http_status=None,
        redirect_chain=[],
        content_type=None,
        bytes_received=0,
        retry_count=1,
        raw_artifact_id=None,
        diagnostic_summary="Timed out.",
    )
    first = write_acquisition_attempt(built.payload, layout=layout)
    second = write_acquisition_attempt(built.payload, layout=layout)
    assert first == second
    assert read_acquisition_attempt(built.payload["attempt_id"], layout=layout) == built.payload

    changed = dict(built.payload, diagnostic_summary="Different content.")
    with pytest.raises(ResearchProjectV2Error):
        write_acquisition_attempt(changed, layout=layout)


def test_raw_byte_storage_deduplicates_exact_content(tmp_path: Path) -> None:
    layout = LayeredResearchLayout((tmp_path / "v2_1").resolve())
    layout.root.mkdir(mode=0o700)
    first = publish_raw_bytes(b"hello", content_type="text/plain", layout=layout)
    second = publish_raw_bytes(b"hello", content_type="text/plain", layout=layout)
    assert first == second
    assert first.path.read_bytes() == b"hello"
    assert first.relative_path.startswith("evidence/raw/")
