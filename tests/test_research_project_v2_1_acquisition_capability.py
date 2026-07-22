from __future__ import annotations

from copy import deepcopy

import pytest

from stock_research.research_project_v2.errors import ResearchProjectV2Error
from stock_research.research_project_v2_1.acquisition_capability import (
    build_discovery_plan,
    classify_candidate_content,
    classify_root_cause,
    collapse_document_identities,
    extract_document_identity,
    match_evidence_shape,
    plan_alternative_entry,
    validate_capability_checkpoint,
)


def _candidate(title: str, *, source_class: str = "technical_standard") -> dict:
    return {
        "candidate_id": "source_candidate:test",
        "source_title": title,
        "source_owner": "Test Organization",
        "source_class": source_class,
        "source_url": "https://example.com/2020/document.pdf",
        "authorized_er_ids": ["PCB-ER-A04"],
    }


def _attempt(*, status: str = "acquired", failure: str | None = None, http: int | None = 200) -> dict:
    return {
        "attempt_id": "acquisition_attempt:test",
        "candidate_id": "source_candidate:test",
        "status": status,
        "failure_class": failure,
        "http_status": http,
        "raw_artifact_id": "evidence_artifact:test" if status == "acquired" else None,
        "normalization_status": "normalized" if status == "acquired" else "not_applicable",
    }


def _document(title: str, text: str, *, media_type: str = "text/html") -> dict:
    return {
        "document_id": "normalized_document:test",
        "artifact_id": "evidence_artifact:test",
        "media_type": media_type,
        "title": title,
        "sections": [
            {
                "section_id": "section:test:0001",
                "heading": title,
                "locator": "page:1",
                "text": text,
                "section_hash": "1" * 64,
            }
        ],
    }


def test_candidate_content_qualification_separates_full_text_landing_overview_and_index() -> None:
    full = classify_candidate_content(
        _candidate("NIST Technical Note 1520"),
        _attempt(),
        _document(
            "NIST Technical Note 1520",
            "Chapter 1 Measurement Method. S-parameters, calibration, uncertainty and results.",
            media_type="application/pdf",
        ),
    )
    assert full["candidate_content_class"] == "full_text_pdf"

    landing = classify_candidate_content(
        _candidate("IEEE 370 standard landing page"),
        _attempt(),
        _document("IEEE 370-2020", "Standard overview. Purchase this standard. Scope and status."),
    )
    assert landing["candidate_content_class"] == "standard_landing_page"

    overview = classify_candidate_content(
        _candidate("PCI Express 6.0 specification overview"),
        _attempt(),
        _document("PCI Express 6.0 Specification", "Overview of features and specification benefits."),
    )
    assert overview["candidate_content_class"] == "overview"

    index = classify_candidate_content(
        _candidate("IEEE 802.3ck public task-force material index"),
        _attempt(),
        _document("IEEE 802.3ck Public Area", "Meeting materials index. Presentations and documents."),
    )
    assert index["candidate_content_class"] == "working_group_index"


def test_root_cause_classification_distinguishes_failures_and_content_mismatch() -> None:
    assert classify_root_cause(_candidate("missing"), _attempt(status="failed", failure="http_error", http=404))["root_cause_class"] == "http_404"
    assert classify_root_cause(_candidate("forbidden"), _attempt(status="failed", failure="http_error", http=403))["root_cause_class"] == "http_403"
    assert classify_root_cause(_candidate("slow"), _attempt(status="failed", failure="connection_timeout", http=None))["root_cause_class"] == "timeout_or_transient_network"
    assert classify_root_cause(_candidate("blocked"), _attempt(status="blocked", failure="security_policy_blocked", http=None))["root_cause_class"] == "security_policy_blocked"
    encrypted = _attempt()
    encrypted["normalization_status"] = "failed"
    assert classify_root_cause(_candidate("encrypted"), encrypted)["root_cause_class"] == "encrypted_or_unparseable"


def test_document_identity_extracts_formal_identifiers_without_inferring_url_date() -> None:
    identity = extract_document_identity(
        _candidate("NIST document"),
        _document(
            "Dielectric and Conductor-Loss Characterization",
            "NIST Technical Note 1520\nAuthors: Jane Doe and John Roe\nDocument number TN 1520",
            media_type="application/pdf",
        ),
    )
    assert identity["document_number"] == "NIST Technical Note 1520"
    assert identity["document_identity_confidence"] == "resolved"
    assert identity["publication_date_status"] == "unknown"
    assert identity["publication_date_explicit"] is None

    provisional = extract_document_identity(
        _candidate("roughness paper", source_class="academic_research"),
        _document(
            "Signal transmission loss due to copper surface roughness",
            "Signal transmission loss due to copper surface roughness\nAuthors: A. Example, B. Example\nExample University",
            media_type="application/pdf",
        ),
    )
    assert provisional["document_identity_confidence"] == "provisional"


def test_discovery_plans_are_er_aware_and_denominator_aware() -> None:
    a04 = build_discovery_plan("PCB-ER-A04")
    assert {"S-parameter", "fixture removal", "de-embedding", "reference plane", "test coupon"} <= set(a04["exact_phrases"])
    assert "measurement uncertainty" in a04["required_denominator_terms"]

    b02 = build_discovery_plan("PCB-ER-B02")
    assert {"Rz", "Ra", "Rq", "measured insertion loss", "stripline", "VNA"} <= set(b02["exact_phrases"])
    assert b02["stop_rules"]


def test_safe_alternative_plans_never_authorize_or_bypass() -> None:
    for root_cause in ("http_404", "http_403", "timeout_or_transient_network", "security_policy_blocked", "encrypted_or_unparseable"):
        plan = plan_alternative_entry(
            original_candidate_id="source_candidate:test",
            original_failure_class=root_cause,
            source_owner="IPC",
            title="IPC-TM-650 2.5.5.5",
        )
        assert plan["formal_acquisition_authorized"] is False
        assert plan["security_eligibility"] == "safe_plan_only"
        assert "bypass" not in " ".join(map(str, plan.values())).lower()


def test_evidence_shape_matching_does_not_promote_overview_index_or_context() -> None:
    assert match_evidence_shape(
        "PCB-ER-A02", "overview", [], "technical_standard_context"
    )["target_evidence_match"] == "context_only"
    assert match_evidence_shape(
        "PCB-ER-A02", "working_group_index", [], "standards_working_group"
    )["target_evidence_match"] == "source_discovery_only"
    assert match_evidence_shape(
        "PCB-ER-B01", "full_text_pdf", ["test_method", "frequency"], "national_metrology"
    )["target_evidence_match"] == "context_only"


def test_duplicate_raw_hash_collapses_to_one_document_identity() -> None:
    collapsed = collapse_document_identities([
        {"artifact_id": "a1", "content_hash": "1" * 64, "authorized_er_ids": ["PCB-ER-A04"]},
        {"artifact_id": "a2", "content_hash": "1" * 64, "authorized_er_ids": ["PCB-ER-B01"]},
        {"artifact_id": "a3", "content_hash": "2" * 64, "authorized_er_ids": ["PCB-ER-B02"]},
    ])
    assert len(collapsed) == 2
    assert collapsed[0]["artifact_ids"] == ["a1", "a2"]


def test_capability_checkpoint_rejects_research_coverage_or_downstream_authorization() -> None:
    checkpoint = {
        "formal_research_coverage_change": 0,
        "security_policy_violations": 0,
        "landing_or_index_false_positive_count": 0,
        "recovery_acquisition_authorized": False,
        "wave_1b_assessment_authorized": False,
        "cognition_update_authorized": False,
        "company_mapping_authorized": False,
        "stage_a2_authorized": False,
        "stage_b_authorized": False,
        "content_hash": "",
    }
    from stock_research.research_project_v2.canonical import content_sha256

    checkpoint["content_hash"] = content_sha256(checkpoint, excluded_paths=(("content_hash",),))
    validate_capability_checkpoint(checkpoint, validate_schema=False)

    invalid = deepcopy(checkpoint)
    invalid["formal_research_coverage_change"] = 1
    invalid["content_hash"] = content_sha256(invalid, excluded_paths=(("content_hash",),))
    with pytest.raises(ResearchProjectV2Error, match="coverage"):
        validate_capability_checkpoint(invalid, validate_schema=False)
