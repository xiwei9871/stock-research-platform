from __future__ import annotations

import pytest

from stock_research.ai_pcb_yanbaoke_evidence_triage import (
    classify_relevance,
    classify_utility,
    collapse_content_identities,
    map_er_dispositions,
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


def test_traceable_standard_or_paper_reference_becomes_source_lead():
    result = classify_utility(
        title="高速材料研究",
        body_text="数据来源：IPC-TM-650；参见 DOI:10.1234/example。",
    )

    assert result.primary_classification == "primary_source_lead"
    assert result.traceable_source_types == ("doi", "standard_number")
    assert "10.1234/example" in result.traceable_source_leads
    assert "IPC-TM-650" in result.traceable_source_leads


def test_investment_recommendation_is_not_technical_evidence():
    result = classify_utility(
        title="公司深度：首次覆盖给予买入评级",
        body_text="目标价和盈利预测显示公司确定受益。",
    )

    assert result.primary_classification == "investment_opinion_non_evidence"
    assert "not_direct_evidence" in result.prohibited_use


def test_a04_requires_measurement_method_terms():
    mappings = map_er_dispositions("插损提高", body_text="高速传输需求增长。")
    assert mappings["PCB-ER-A04"] == "contextual_candidate"

    mappings = map_er_dispositions(
        "S参数测量",
        body_text="fixture removal, de-embedding, reference plane and test coupon。",
    )
    assert mappings["PCB-ER-A04"] == "source_discovery_only"


def test_er_mappings_are_denominator_aware_and_never_direct_evidence():
    mappings = map_er_dispositions(
        "铜箔粗糙度实验",
        body_text="Rz 2.1 μm，使用 VNA 在 20 GHz 测量 200 mm stripline insertion loss。",
    )

    assert mappings["PCB-ER-B02"] == "source_discovery_only"
    assert set(mappings.values()) <= {
        "source_discovery_only",
        "contextual_candidate",
        "not_relevant",
    }
