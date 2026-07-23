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
    classify_relevance,
    classify_utility,
    collapse_content_identities,
    map_er_dispositions,
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
