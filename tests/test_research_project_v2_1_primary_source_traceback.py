from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import subprocess

import pytest

from stock_research.research_project_v2.canonical import content_sha256
from stock_research.research_project_v2.errors import ResearchProjectV2Error
from stock_research.research_project_v2_1.primary_source_traceback import (
    bind_claims_to_citations,
    build_source_candidates,
    build_traceback_checkpoint,
    classify_candidate_content,
    collapse_common_origin_candidates,
    extract_citations_from_pages,
    extract_claims_from_pages,
    extract_report_identity_from_pages,
    render_traceback_report,
    select_traceback_candidates,
    build_traceback_artifact,
    validate_traceback_artifact,
    validate_traceback_authorization,
    validate_traceback_checkpoint,
    validate_traceback_repository_bundle,
    verify_claim_source_support,
)


def _gate() -> dict:
    targets = [
        {
            "traceback_target_id": "traceback_target:test:tongguan:v1",
            "report_content_sha256": "a" * 64,
            "report_title": "AI铜箔领跑者",
            "report_owner": "国金证券",
            "covered_entity": "铜冠铜箔",
            "report_path": "outputs/test.pdf",
            "authorized_er_traceback_scope": ["PCB-ER-A02", "PCB-ER-B01", "PCB-ER-B02"],
            "common_origin_group": None,
        },
        {
            "traceback_target_id": "traceback_target:test:novoray1:v1",
            "report_content_sha256": "b" * 64,
            "report_title": "填料艺术家",
            "report_owner": "西南证券",
            "covered_entity": "联瑞新材",
            "report_path": "outputs/test2.pdf",
            "authorized_er_traceback_scope": ["PCB-ER-B01"],
            "common_origin_group": "common_origin:test",
        },
        {
            "traceback_target_id": "traceback_target:test:novoray2:v1",
            "report_content_sha256": "c" * 64,
            "report_title": "填料艺术家",
            "report_owner": "西南证券",
            "covered_entity": "联瑞新材",
            "report_path": "outputs/test3.pdf",
            "authorized_er_traceback_scope": ["PCB-ER-B01"],
            "common_origin_group": "common_origin:test",
        },
        {
            "traceback_target_id": "traceback_target:test:fastprint:v1",
            "report_content_sha256": "d" * 64,
            "report_title": "兴森科技深度",
            "report_owner": "浙商证券",
            "covered_entity": "兴森科技",
            "report_path": "outputs/test4.pdf",
            "authorized_er_traceback_scope": ["PCB-ER-A02", "PCB-ER-B02"],
            "common_origin_group": None,
        },
        {
            "traceback_target_id": "traceback_target:test:shennan:v1",
            "report_content_sha256": "e" * 64,
            "report_title": "AI led PCB growth",
            "report_owner": "CMBI",
            "covered_entity": "深南电路",
            "report_path": "outputs/test5.pdf",
            "authorized_er_traceback_scope": ["PCB-ER-B02"],
            "common_origin_group": None,
        },
    ]
    payload = {
        "decision_id": "primary_source_traceback_gate_decision:ai_pcb:broker_reports:v1",
        "decision_status": "frozen",
        "selected_target_count": 5,
        "selected_targets": targets,
        "per_er_traceback_policy": {"PCB-ER-A04": {"traceback_authorized": False}},
        "content_hash": "",
    }
    payload["content_hash"] = content_sha256(payload, excluded_paths={("content_hash",)})
    return payload


def _authorization(gate: dict) -> dict:
    payload = {
        "authorization_id": "primary_source_traceback_execution_authorization:ai_pcb:broker_reports:v1",
        "authorization_status": "frozen",
        "input_bindings": {
            "traceback_gate_id": gate["decision_id"],
            "traceback_gate_hash": gate["content_hash"],
        },
        "execution_authorized": True,
        "authorization_scope": "exact_report_list_only",
        "maximum_report_count": 5,
        "machine_first_traceback": True,
        "human_assistance_required": False,
        "manual_source_resolution_required": False,
        "unresolved_is_valid_terminal_state": True,
        "network_traceback_authorized": True,
        "bounded_primary_source_acquisition_authorized": True,
        "maximum_unique_primary_source_candidates": 25,
        "maximum_formal_acquisition_attempts": 30,
        "authorization_consumed": False,
        "authorized_er_ids": ["PCB-ER-A02", "PCB-ER-B01", "PCB-ER-B02"],
        "authorized_targets": [
            {
                "traceback_target_id": row["traceback_target_id"],
                "report_content_sha256": row["report_content_sha256"],
            }
            for row in gate["selected_targets"]
        ],
        "consolidated_assessment_authorized": False,
        "cognition_update_authorized": False,
        "company_mapping_authorized": False,
        "stage_a2_authorized": False,
        "stage_b_authorized": False,
        "content_hash": "",
    }
    payload["content_hash"] = content_sha256(payload, excluded_paths={("content_hash",)})
    return payload


def test_authorization_is_exact_five_report_machine_first_and_downstream_closed() -> None:
    gate = _gate()
    authorization = _authorization(gate)

    validated = validate_traceback_authorization(
        authorization, gate=gate, validate_upstreams=False
    )

    assert len(validated["authorized_targets"]) == 5
    assert validated["machine_first_traceback"] is True
    assert validated["human_assistance_required"] is False
    assert validated["authorization_consumed"] is False

    invalid = deepcopy(authorization)
    invalid["authorized_er_ids"].append("PCB-ER-A04")
    invalid["content_hash"] = content_sha256(invalid, excluded_paths={("content_hash",)})
    with pytest.raises(ResearchProjectV2Error, match="A04|scope"):
        validate_traceback_authorization(invalid, gate=gate, validate_upstreams=False)


def test_report_identity_is_extracted_without_human_confirmation() -> None:
    target = _gate()["selected_targets"][0]
    pages = [
        "证券研究报告 公司深度 铜冠铜箔 2025年8月8日\n分析师：张三 S123456\nAI铜箔领跑者",
        "正文",
    ]

    identity = extract_report_identity_from_pages(target=target, pages=pages)

    assert identity["report_title"] == "AI铜箔领跑者"
    assert identity["broker_or_research_institution"] == "国金证券"
    assert identity["publication_date_explicit"] == "2025-08-08"
    assert identity["analysts"] == ["张三"]
    assert identity["page_count"] == 2
    assert identity["human_confirmation_required"] is False


def test_claim_extraction_is_er_scoped_and_a04_is_rejected() -> None:
    pages = [
        "图表24：HVLP-2铜箔表面粗糙度Rz为1.0-1.5μm，20GHz下导体损耗更低。\n"
        "来源：《第三代超低轮廓电解铜箔V-HS3性能研究》（作者：张杰等）\n"
        "服务器升级带动PCIe 5.0，但未给出通道距离。\n"
        "采用去嵌入和夹具移除测量插损。\n"
        "我们预计公司盈利持续增长，给予买入评级。"
    ]

    claims = extract_claims_from_pages(
        report_id="report:test",
        traceback_target_id="traceback_target:test",
        report_file_hash="f" * 64,
        pages=pages,
        authorized_er_ids={"PCB-ER-A02", "PCB-ER-B01", "PCB-ER-B02"},
    )

    assert any(row["er_id"] == "PCB-ER-B02" for row in claims)
    assert any(row["er_id"] == "PCB-ER-A02" for row in claims)
    assert not any(row.get("er_id") == "PCB-ER-A04" for row in claims)
    assert any(row["claim_class"] == "investment_opinion" for row in claims)
    assert all(row["page_number"] == 1 for row in claims)
    assert all(row["claim_text_hash"] for row in claims)


def test_figure_source_note_is_bound_to_nearest_technical_claim() -> None:
    pages = [
        "图表24：高性能计算使用Rz低于2μm的HVLP铜箔\n"
        "来源：《印制电路板用高端电子铜箔及其技术新发展（上）》（作者：祝大同）\n"
        "投资建议：给予买入评级"
    ]
    claims = extract_claims_from_pages(
        report_id="report:test",
        traceback_target_id="traceback_target:test",
        report_file_hash="f" * 64,
        pages=pages,
        authorized_er_ids={"PCB-ER-B02"},
    )
    citations = extract_citations_from_pages(report_id="report:test", pages=pages)

    bound = bind_claims_to_citations(claims, citations)

    technical = next(row for row in bound if row.get("er_id") == "PCB-ER-B02")
    assert technical["figure_or_table_id"] == "图表24"
    assert technical["source_note_text"].startswith("来源：")
    assert technical["citation_ids"]


def test_source_candidate_parses_exact_title_author_and_generic_company_material() -> None:
    citations = [
        {
            "citation_id": "citation:1",
            "report_id": "report:1",
            "report_claim_ids": ["claim:1"],
            "citation_raw_text": "来源：《第三代超低轮廓电解铜箔V-HS3性能研究》（作者：张杰等）",
        },
        {
            "citation_id": "citation:2",
            "report_id": "report:1",
            "report_claim_ids": ["claim:2"],
            "citation_raw_text": "来源：公司公告，券商整理",
        },
    ]

    candidates = build_source_candidates(citations)

    exact = next(row for row in candidates if row["citation_specificity"] == "exact_document")
    generic = next(row for row in candidates if row["citation_specificity"] == "generic_company_material")
    assert exact["candidate_title"] == "第三代超低轮廓电解铜箔V-HS3性能研究"
    assert "张杰" in exact["candidate_authors"]
    assert generic["identity_status"] == "unresolved"


def test_publisher_record_is_not_full_text_primary_source() -> None:
    assert classify_candidate_content(
        content_type="text/html",
        title="Publisher record",
        text="Abstract DOI authors journal metadata",
        has_full_text=False,
    ) == "publisher_record"
    assert classify_candidate_content(
        content_type="application/pdf",
        title="Technical paper",
        text="Methods Results insertion loss Rz measurement",
        has_full_text=True,
    ) == "peer_reviewed_paper"


def test_common_origin_candidates_collapse_across_two_novoray_reports() -> None:
    candidates = [
        {
            "source_candidate_id": "source:1",
            "candidate_title": "联瑞新材招股书",
            "common_origin_group": "common_origin:test",
        },
        {
            "source_candidate_id": "source:2",
            "candidate_title": "联瑞新材招股书",
            "common_origin_group": "common_origin:test",
        },
    ]

    collapsed = collapse_common_origin_candidates(candidates)

    assert len(collapsed) == 1
    assert collapsed[0]["provisional_source_chain_count"] == 1
    assert collapsed[0]["originating_candidate_ids"] == ["source:1", "source:2"]


def test_support_verification_detects_scope_broadening() -> None:
    result = verify_claim_source_support(
        report_claim="HVLP铜箔在所有高速PCB中都能降低插损并形成行业标准。",
        source_text="在本实验的20GHz、200mm stripline条件下，低粗糙度样品插损较低。",
        required_terms={"HVLP", "插损"},
        report_denominator={},
        source_denominator={"frequency": "20GHz", "length": "200mm", "geometry": "stripline"},
    )

    assert result["support_relationship"] == "partial_support"
    assert result["broker_report_transformation"] == "scope_broadened"


def test_checkpoint_consumes_authorization_and_keeps_downstream_closed() -> None:
    gate = _gate()
    authorization = _authorization(gate)
    checkpoint = build_traceback_checkpoint(
        gate=gate,
        authorization=authorization,
        reports=[{"report_identity_status": "resolved"}] * 5,
        claims=[{"er_id": "PCB-ER-B02", "terminal_status": "citation_present_but_unresolved"}],
        citations=[{"citation_specificity": "exact_document"}],
        candidates=[{"source_candidate_id": "source:1"}],
        attempts=[],
        acquired_sources=[],
        created_at="2026-07-23T00:00:00Z",
    )

    validated = validate_traceback_checkpoint(
        checkpoint, gate=gate, authorization=authorization
    )
    assert validated["authorization_consumed"] is True
    assert validated["human_assistance_requested"] is False
    assert validated["consolidated_assessment_started"] is False


def test_report_renderer_does_not_upgrade_traceback_to_evidence_admission() -> None:
    artifact = {
        "artifact_id": "primary_source_traceback:1",
        "artifact_role": "primary_source_traceback",
        "direct_er_evidence_admission": False,
        "report_identities": [],
        "claims": [],
        "source_candidates": [],
        "trace_links": [],
        "checkpoint_summary": {"processed_report_count": 5},
    }

    rendered = render_traceback_report(artifact)

    assert "Direct ER evidence admission: no" in rendered
    assert "Consolidated Assessment started: no" in rendered


def test_candidate_selection_is_bounded_and_prefers_specific_identity() -> None:
    candidates = [
        {
            "source_candidate_id": f"source:{index}",
            "candidate_title": f"source {index}",
            "citation_specificity": specificity,
            "originating_claim_ids": [f"claim:{index}"],
        }
        for index, specificity in enumerate(
            ["unattributed"] * 20 + ["generic_company_material"] * 5 + ["exact_document"] * 5
        )
    ]

    selected = select_traceback_candidates(candidates, maximum_count=25)

    assert len(selected) == 25
    assert sum(row["citation_specificity"] == "exact_document" for row in selected) == 5
    assert sum(row["citation_specificity"] == "generic_company_material" for row in selected) == 5
    assert sum(row["citation_specificity"] == "unattributed" for row in selected) == 15


def test_traceback_artifact_is_hashed_and_keeps_new_sources_unadmitted() -> None:
    artifact = build_traceback_artifact(
        authorization_hash="a" * 64,
        gate_hash="b" * 64,
        report_identities=[{"report_id": "report:1"}],
        claims=[
            {
                "claim_id": "claim:1",
                "er_id": "PCB-ER-B01",
                "terminal_status": "citation_present_but_unresolved",
            }
        ],
        citations=[],
        source_candidates=[],
        trace_links=[],
        acquired_sources=[
            {
                "source_candidate_id": "source:1",
                "eligible_for_future_assessment_candidate": True,
                "admitted_to_evidence_assessment": False,
                "er_sufficient": False,
                "cognition_update_eligible": False,
            }
        ],
        checkpoint_summary={"processed_report_count": 5},
        created_at="2026-07-23T00:00:00Z",
    )

    validated = validate_traceback_artifact(artifact)

    assert validated["artifact_role"] == "primary_source_traceback"
    assert validated["direct_er_evidence_admission"] is False
    assert validated["content_hash"]


def test_repository_bundle_validates_without_human_or_downstream_transition() -> None:
    root = Path(__file__).resolve().parents[1]
    result = validate_traceback_repository_bundle(
        layout_root=root / "artifacts/research_projects/v2_1",
        source_repository_root=Path("/Users/xiwei/stock_research"),
    )

    assert result["valid"] is True
    assert result["processed_report_count"] == 5
    assert result["human_assistance_requested"] is False
    assert result["consolidated_assessment_started"] is False


def test_primary_source_traceback_exact_allowlist_contains_task_changes() -> None:
    root = Path(__file__).resolve().parents[1]
    allowlist = json.loads(
        (
            root
            / "artifacts/research_projects/v2_1/acquisition/primary_source_traceback_v1/exact_allowlist.json"
        ).read_text(encoding="utf-8")
    )
    changed = set(
        subprocess.check_output(
            ["git", "diff", "--name-only", allowlist["baseline_commit"]],
            cwd=root,
            text=True,
        ).splitlines()
    )
    for line in subprocess.check_output(
        ["git", "status", "--porcelain=v1", "-uall"], cwd=root, text=True
    ).splitlines():
        changed.add(line[3:].split(" -> ", 1)[-1])
    assert changed <= set(allowlist["allowed_paths"])
