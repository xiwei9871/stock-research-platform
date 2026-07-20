from __future__ import annotations

from copy import deepcopy

import pytest

from stock_research.research_project_v2.errors import ResearchProjectV2Error
from stock_research.research_project_v2_1.schema import validate_v2_1_schema_payload


PROVENANCE = {
    "created_by": "Codex",
    "actor_type": "codex",
    "agent_run_id": "run:acquisition-schema-test",
    "created_at": "2026-07-20T08:00:00Z",
    "created_in_version": "research_version:ai_compute_pcb_industry_bottleneck:0.2.1",
    "review_status": "unreviewed",
}


def acquisition_attempt() -> dict:
    return {
        "attempt_id": "acquisition_attempt:" + "a" * 24,
        "project_id": "research_project:ai_compute_pcb_industry_bottleneck",
        "research_version_context": "research_version:ai_compute_pcb_industry_bottleneck:0.2.1",
        "requirement_id": "requirement:ai_compute_pcb_industry_bottleneck:r2b_er01",
        "candidate_id": "source_candidate:" + "b" * 24,
        "provider": "direct_http",
        "request_mode": "fetch",
        "proxy_mode": "direct",
        "requested_url": "https://example.com/source.pdf",
        "resolved_url": "https://example.com/source.pdf",
        "attempted_at": "2026-07-20T08:00:00Z",
        "completed_at": "2026-07-20T08:00:01Z",
        "elapsed_ms": 1000,
        "status": "acquired",
        "failure_code": None,
        "http_status": 200,
        "redirect_chain": [],
        "content_type": "application/pdf",
        "bytes_received": 123,
        "retry_count": 0,
        "raw_artifact_id": "evidence_artifact:" + "c" * 24,
        "diagnostic_summary": "Direct acquisition completed.",
        "failure_details": None,
        "provenance": PROVENANCE,
        "content_hash": "d" * 64,
    }


def test_schema_v2_3_accepts_standalone_acquisition_attempt() -> None:
    validate_v2_1_schema_payload(
        "acquisition_attempt_v2_3",
        {
            "schema_version": "2.3.0",
            "artifact_kind": "acquisition_attempt",
            "acquisition_attempt": acquisition_attempt(),
        },
    )


def test_schema_v2_3_requires_security_policy_details_when_blocked() -> None:
    attempt = acquisition_attempt()
    attempt.update(
        {
            "status": "blocked",
            "failure_code": "security_policy_blocked",
            "http_status": None,
            "content_type": None,
            "bytes_received": 0,
            "raw_artifact_id": None,
            "failure_details": {
                "policy_name": "public_network_only",
                "policy_stage": "peer_validation",
                "target_host": "example.com",
                "resolved_address_class": "public",
                "peer_address_class": "private",
                "redirect_hop": 0,
                "proxy_mode": "environment_proxy",
                "blocked_reason": "transport peer is private",
            },
        }
    )
    validate_v2_1_schema_payload(
        "acquisition_attempt_v2_3",
        {
            "schema_version": "2.3.0",
            "artifact_kind": "acquisition_attempt",
            "acquisition_attempt": attempt,
        },
    )

    broken = deepcopy(attempt)
    del broken["failure_details"]["policy_stage"]
    with pytest.raises(ResearchProjectV2Error):
        validate_v2_1_schema_payload(
            "acquisition_attempt_v2_3",
            {
                "schema_version": "2.3.0",
                "artifact_kind": "acquisition_attempt",
                "acquisition_attempt": broken,
            },
        )


def test_schema_v2_3_accepts_manual_import_and_raw_artifact() -> None:
    request = {
        "import_request_id": "manual_import_request:" + "e" * 24,
        "project_id": "research_project:ai_compute_pcb_industry_bottleneck",
        "research_version_context": "research_version:ai_compute_pcb_industry_bottleneck:0.2.1",
        "requirement_id": None,
        "candidate_id": None,
        "local_path": "/tmp/source.pdf",
        "source_title": "Official architecture guide",
        "publisher": "Example Standards Body",
        "original_url": "https://example.com/source.pdf",
        "source_note": None,
        "publication_date": "2026-07-01",
        "imported_at": "2026-07-20T08:00:00Z",
        "imported_by": "Codex",
        "actor_type": "codex",
        "declared_mime_type": "application/pdf",
        "access_or_license_note": "Public technical document.",
        "locator_metadata": {"page_locators_expected": True},
        "metadata_status": "complete",
        "provenance": PROVENANCE,
        "content_hash": "f" * 64,
    }
    validate_v2_1_schema_payload(
        "manual_import_request_v2_3",
        {
            "schema_version": "2.3.0",
            "artifact_kind": "manual_import_request",
            "manual_import_request": request,
        },
    )

    artifact = {
        "evidence_artifact_id": "evidence_artifact:" + "1" * 24,
        "acquisition_attempt_id": "acquisition_attempt:" + "2" * 24,
        "source_candidate_id": None,
        "source_url": "https://example.com/source.pdf",
        "resolved_url": "https://example.com/source.pdf",
        "source_title": "Official architecture guide",
        "publisher": "Example Standards Body",
        "published_at": "2026-07-01T00:00:00Z",
        "accessed_at": "2026-07-20T08:00:00Z",
        "content_type": "application/pdf",
        "byte_size": 123,
        "content_hash": "3" * 64,
        "raw_artifact_path": "evidence/raw/33/" + "3" * 64 + ".pdf",
        "normalized_artifact_ids": [],
        "provenance": PROVENANCE,
        "access_status": "acquired",
        "license_or_access_note": "Public technical document.",
    }
    validate_v2_1_schema_payload(
        "evidence_artifact_v2_3",
        {
            "schema_version": "2.3.0",
            "artifact_kind": "evidence_artifact",
            "evidence_artifact": artifact,
        },
    )


def test_schema_v2_3_accepts_checkpoint_and_provider_diagnostic() -> None:
    checkpoint = {
        "checkpoint_id": "acquisition_checkpoint:" + "4" * 24,
        "project_id": "research_project:ai_compute_pcb_industry_bottleneck",
        "research_version_context": "research_version:ai_compute_pcb_industry_bottleneck:0.2.1",
        "created_at": "2026-07-20T08:00:00Z",
        "attempt_ids": ["acquisition_attempt:" + "a" * 24],
        "raw_artifact_ids": ["evidence_artifact:" + "c" * 24],
        "normalized_document_ids": [],
        "pending_assessment_artifact_ids": ["evidence_artifact:" + "c" * 24],
        "failed_attempt_ids": [],
        "status": "pending_assessment",
        "provenance": PROVENANCE,
        "content_hash": "5" * 64,
    }
    validate_v2_1_schema_payload(
        "acquisition_checkpoint_v2_3",
        {
            "schema_version": "2.3.0",
            "artifact_kind": "acquisition_checkpoint",
            "acquisition_checkpoint": checkpoint,
        },
    )

    diagnostic = {
        "diagnostic_id": "provider_diagnostic:" + "6" * 24,
        "generated_at": "2026-07-20T08:00:00Z",
        "dns_status": "pass",
        "tls_status": "pass",
        "direct_html_status": "pass",
        "direct_pdf_status": "pass",
        "redirect_status": "pass",
        "system_proxy_detected": True,
        "environment_proxy_detected": False,
        "proxy_endpoint_class": "private",
        "proxy_endpoint_redacted": "192.168.3.x:789x",
        "requests_trust_mode": "explicit_direct",
        "browser_runtime_status": "available",
        "search_provider_status": "unavailable",
        "available_normalizers": ["html", "pypdf", "docling"],
        "security_policy_status": "enforced",
        "checks": [],
        "provenance": PROVENANCE,
        "content_hash": "7" * 64,
    }
    validate_v2_1_schema_payload(
        "provider_diagnostic_v2_3",
        {
            "schema_version": "2.3.0",
            "artifact_kind": "provider_diagnostic",
            "provider_diagnostic": diagnostic,
        },
    )
