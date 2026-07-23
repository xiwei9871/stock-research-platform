from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pandas as pd
import pytest

from stock_research.ai_pcb_yanbaoke_evidence_triage import (
    annotate_common_origin_groups,
    classify_relevance,
    classify_utility,
    collapse_content_identities,
    map_er_dispositions,
    render_summary,
    run_triage,
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


def test_short_ascii_signals_do_not_match_inside_unrelated_english_words():
    row = {
        "report_title": "Overseas growth update",
        "stock_name": "样本公司",
        "content": "driving structural growth with resilient margins",
    }

    result = classify_relevance(row, body_text="platform diversification and rating update")

    assert result.selected is False


def test_generic_yield_without_pcb_context_is_not_selected():
    row = {
        "report_title": "先进封装良率管理研究",
        "stock_name": "半导体公司",
        "content": "晶圆制造良率持续改善",
    }

    result = classify_relevance(row, body_text="封装测试产线的良率提升")

    assert result.selected is False


def test_single_incidental_pcb_mention_in_unrelated_company_body_is_not_selected():
    row = {
        "report_title": "光模块公司深度报告",
        "stock_name": "仕佳光子",
        "content": "高速光模块需求增长",
    }

    result = classify_relevance(row, body_text="供应链也会使用 PCB。")

    assert result.selected is False


def test_pcb_focus_company_with_body_anchor_remains_selected():
    row = {
        "report_title": "年度经营回顾",
        "stock_name": "深南电路",
        "content": "",
    }

    result = classify_relevance(row, body_text="公司从事高多层 PCB 与封装基板业务。")

    assert result.selected is True
    assert "pcb_design" in result.relevance_domains


def test_incidental_queue_content_does_not_make_report_focus_relevant():
    row = {
        "report_title": "光模块公司深度报告",
        "stock_name": "光模块公司",
        "content": "供应链中使用 PCB",
    }

    result = classify_relevance(row, body_text="高速光模块需求增长。")

    assert result.selected is False


def test_pcba_in_title_is_a_strong_manufacturing_signal():
    row = {
        "report_title": "PCBA设备细分环节研究",
        "stock_name": "设备公司",
        "content": "",
    }

    result = classify_relevance(row, body_text="电子装联设备用于 PCBA 生产。")

    assert result.selected is True


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


def test_near_identical_same_broker_titles_are_flagged_as_suspected_common_origin():
    frame = pd.DataFrame(
        [
            {
                "content_identity": "sha256:a",
                "stock_name": "联瑞新材",
                "broker": "西南证券",
                "report_title": "深度报告 2026 06 15 填料艺术家 积淀深厚 充分受益于AI浪潮",
            },
            {
                "content_identity": "sha256:b",
                "stock_name": "联瑞新材",
                "broker": "西南证券",
                "report_title": "深度报告 20260614 填料艺术家 积淀深厚 充分受益于AI浪潮",
            },
            {
                "content_identity": "sha256:c",
                "stock_name": "联瑞新材",
                "broker": "西南证券",
                "report_title": "持续聚焦高端粉体 可转债项目助力成长",
            },
        ]
    )

    result = annotate_common_origin_groups(frame)

    assert result.loc[0, "suspected_common_origin_group"]
    assert (
        result.loc[0, "suspected_common_origin_group"]
        == result.loc[1, "suspected_common_origin_group"]
    )
    assert result.loc[2, "suspected_common_origin_group"] == ""


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


def test_company_announcement_reference_is_a_company_evidence_lead_even_with_rating():
    result = classify_utility(
        title="公司公告点评：维持买入评级",
        body_text="事件来源为公司公告和2025年年度报告。",
    )

    assert result.primary_classification == "company_evidence_lead"
    assert "company_filing_reference" in result.traceable_source_types


def test_pcie_version_mention_is_not_misclassified_as_formal_standard_source():
    result = classify_utility(
        title="高速PCB公司深度",
        body_text="产品支持 PCIe 4.0 和 PCIe 5.0，给予买入评级。",
    )

    assert result.primary_classification == "investment_opinion_non_evidence"
    assert result.traceable_source_leads == ()


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


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_run_triage_writes_reconciled_outputs_without_mutating_inputs(tmp_path):
    download_dir = tmp_path / "download"
    pdf_dir = download_dir / "pdfs"
    pdf_dir.mkdir(parents=True)
    relevant_a = pdf_dir / "relevant-a.pdf"
    relevant_b = pdf_dir / "relevant-b.pdf"
    generic = pdf_dir / "generic.pdf"
    relevant_a.write_bytes(b"same report bytes")
    relevant_b.write_bytes(b"same report bytes")
    generic.write_bytes(b"generic report bytes")

    queue = pd.DataFrame(
        [
            {
                "uuid": "u1",
                "report_title": "HVLP铜箔研究",
                "stock_name": "样本公司",
                "content": "Rz与20 GHz插损测试",
                "publish_date": "2026-01-01",
                "broker": "券商甲",
            },
            {
                "uuid": "u2",
                "report_title": "HVLP铜箔研究镜像",
                "stock_name": "样本公司",
                "content": "Rz与20 GHz插损测试",
                "publish_date": "2026-01-01",
                "broker": "券商甲",
            },
            {
                "uuid": "u3",
                "report_title": "AI服务器行业更新",
                "stock_name": "另一公司",
                "content": "算力需求增长",
                "publish_date": "2026-01-02",
                "broker": "券商乙",
            },
        ]
    )
    mappings = pd.DataFrame(
        [
            {"ts_code": "000001.SZ", "stock_name": "样本公司", "theme_name": "AI算力基础设施"},
            {"ts_code": "000002.SZ", "stock_name": "另一公司", "theme_name": "AI算力基础设施"},
        ]
    )
    manifest = pd.DataFrame(
        [
            {"uuid": "u1", "status": "downloaded", "pdf_path": str(relevant_a)},
            {"uuid": "u2", "status": "downloaded", "pdf_path": str(relevant_b)},
            {"uuid": "u3", "status": "downloaded", "pdf_path": str(generic)},
        ]
    )
    queue_path = tmp_path / "yanbaoke_download_queue_474.csv"
    mappings_path = tmp_path / "theme_company_mappings.csv"
    manifest_path = download_dir / "yanbaoke_direct_uuid_downloads.csv"
    queue.to_csv(queue_path, index=False)
    mappings.to_csv(mappings_path, index=False)
    manifest.to_csv(manifest_path, index=False)
    inputs = (queue_path, mappings_path, manifest_path, relevant_a, relevant_b, generic)
    before = {str(path): _file_sha256(path) for path in inputs}

    result = run_triage(input_dir=tmp_path, output_dir=tmp_path, expected_queue_rows=3)

    assert result.queue_rows_considered == 3
    assert result.selected_source_records == 2
    assert result.selected_content_identities == 1
    assert result.duplicate_source_records == 1
    assert {str(path): _file_sha256(path) for path in inputs} == before
    assert (tmp_path / "ai_pcb_evidence_triage_v1.csv").exists()
    audit = json.loads(
        (tmp_path / "ai_pcb_evidence_triage_audit_v1.json").read_text(encoding="utf-8")
    )
    assert audit["validation"]["counts_reconciled"] is True
    assert audit["evidence_assessment_updated"] is False
    assert audit["network_access_used"] is False


def test_summary_projects_manual_source_resolution_shortlist():
    audit = {
        "queue_rows_considered": 474,
        "selected_source_records": 1,
        "selected_content_identities": 1,
        "duplicate_source_records": 0,
        "primary_classification_distribution": {"company_evidence_lead": 1},
        "er_disposition_distribution": {
            "PCB-ER-A02": {"not_relevant": 1},
            "PCB-ER-A04": {"not_relevant": 1},
            "PCB-ER-B01": {"contextual_candidate": 1},
            "PCB-ER-B02": {"source_discovery_only": 1},
        },
        "selected_records": [
            {
                "stock_name": "铜冠铜箔",
                "report_title": "AI铜箔领跑者",
                "manual_review_priority": "P1",
                "primary_classification": "company_evidence_lead",
                "PCB-ER-A02": "not_relevant",
                "PCB-ER-A04": "not_relevant",
                "PCB-ER-B01": "contextual_candidate",
                "PCB-ER-B02": "source_discovery_only",
            }
        ],
    }

    summary = render_summary(audit)

    assert "Manual original-source resolution shortlist" in summary
    assert "铜冠铜箔 — AI铜箔领跑者" in summary
    assert "PCB-ER-B02=source_discovery_only" in summary


def test_script_help_uses_current_repository_source_without_pythonpath():
    repo_root = Path(__file__).resolve().parents[1]
    environment = dict(os.environ)
    environment.pop("PYTHONPATH", None)

    completed = subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / "run_ai_pcb_yanbaoke_evidence_triage.py"),
            "--help",
        ],
        cwd=repo_root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "offline, read-only AI PCB triage" in completed.stdout


def test_run_triage_accepts_audited_one_for_one_replacement(tmp_path):
    download_dir = tmp_path / "download"
    pdf_dir = download_dir / "pdfs"
    pdf_dir.mkdir(parents=True)
    formal_pdf = pdf_dir / "formal.pdf"
    replacement_pdf = pdf_dir / "replacement.pdf"
    formal_pdf.write_bytes(b"formal bytes")
    replacement_pdf.write_bytes(b"replacement bytes")

    pd.DataFrame(
        [
            {
                "uuid": "formal-ok",
                "report_title": "AI服务器行业更新",
                "stock_name": "样本甲",
                "content": "算力增长",
            },
            {
                "uuid": "formal-missing",
                "report_title": "工业机器人研究",
                "stock_name": "样本乙",
                "content": "机器人本体",
            },
        ]
    ).to_csv(tmp_path / "yanbaoke_download_queue_474.csv", index=False)
    pd.DataFrame(
        [{"ts_code": "000001.SZ", "stock_name": "样本甲", "theme_name": "AI算力"}]
    ).to_csv(tmp_path / "theme_company_mappings.csv", index=False)
    pd.DataFrame(
        [
            {
                "uuid": "formal-ok",
                "status": "downloaded",
                "queue_kind": "formal",
                "pdf_path": str(formal_pdf),
            },
            {
                "uuid": "replacement-one",
                "status": "downloaded",
                "queue_kind": "replacement",
                "report_title": "高速PCB与HVLP铜箔研究",
                "stock_name": "兴森科技",
                "content": "Rz与20 GHz插损测试",
                "pdf_path": str(replacement_pdf),
            },
        ]
    ).to_csv(download_dir / "yanbaoke_direct_uuid_downloads.csv", index=False)
    pd.DataFrame(
        [
            {
                "uuid": "replacement-one",
                "queue_kind": "replacement",
                "report_title": "高速PCB与HVLP铜箔研究",
            }
        ]
    ).to_csv(tmp_path / "yanbaoke_replacement_queue.csv", index=False)

    result = run_triage(input_dir=tmp_path, output_dir=tmp_path, expected_queue_rows=2)

    assert result.queue_rows_considered == 2
    assert result.selected_source_records == 1
    audit = json.loads(
        (tmp_path / "ai_pcb_evidence_triage_audit_v1.json").read_text(encoding="utf-8")
    )
    assert audit["formal_queue_missing_download_count"] == 1
    assert audit["replacement_download_count"] == 1
