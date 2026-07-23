from __future__ import annotations

import pytest

from stock_research.ai_pcb_yanbaoke_evidence_triage import (
    classify_relevance,
    collapse_content_identities,
    validate_er_disposition,
    validate_primary_classification,
)


def test_rejects_direct_evidence_and_er_sufficiency_states():
    validate_primary_classification("primary_source_lead")
    validate_er_disposition("source_discovery_only")

    with pytest.raises(ValueError, match="unsupported primary classification"):
        validate_primary_classification("direct_evidence")
    with pytest.raises(ValueError, match="unsupported ER disposition"):
        validate_er_disposition("sufficient")


def test_generic_ai_terms_do_not_select_a_report():
    row = {
        "report_title": "AI服务器行业更新",
        "stock_name": "样本公司",
        "content": "算力需求增长",
    }

    result = classify_relevance(row, body_text="")

    assert result.selected is False
    assert result.relevance_domains == ()


def test_specific_pcb_material_terms_select_a_report():
    row = {
        "report_title": "HVLP铜箔与高速覆铜板研究",
        "stock_name": "样本公司",
        "content": "",
    }

    result = classify_relevance(row, body_text="Rz and insertion loss are discussed")

    assert result.selected is True
    assert "copper_foil" in result.relevance_domains
    assert "laminate_materials" in result.relevance_domains


def test_same_content_hash_collapses_to_one_document_identity():
    rows = [
        {"uuid": "u1", "content_sha256": "abc", "report_title": "Report A"},
        {"uuid": "u2", "content_sha256": "abc", "report_title": "Report A mirror"},
    ]

    identities = collapse_content_identities(rows)

    assert len(identities) == 1
    assert identities[0]["content_identity"] == "sha256:abc"
    assert identities[0]["source_record_uuids"] == ["u1", "u2"]
    assert identities[0]["duplicate_record_count"] == 1
