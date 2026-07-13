from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


def _fake_docling_parser(pdf_path: Path) -> dict[str, Any]:
    if "bad" in pdf_path.name:
        return {
            "status": "parse_error",
            "parser": "docling",
            "markdown": "",
            "json": {},
            "tables": [],
            "error_type": "FixtureError",
            "error_message": "fixture docling failure",
        }
    text = "公司核心产品用于关键上游设备，客户验证周期长，具备国产替代和供应链安全属性。"
    return {
        "status": "parsed",
        "parser": "docling",
        "markdown": text,
        "json": {
            "texts": [
                {
                    "self_ref": "#/texts/0",
                    "label": "paragraph",
                    "text": text,
                    "prov": [{"page_no": 2, "bbox": {"l": 1, "t": 2, "r": 3, "b": 4}}],
                }
            ]
        },
        "tables": [],
        "error_type": "",
        "error_message": "",
    }


def test_targeted_docling_fallback_builds_reassessment_input(tmp_path: Path) -> None:
    from stock_research.tech_bottleneck_review_universe_report_pdf_targeted_docling_fallback import run

    previous = tmp_path / "previous"
    previous.mkdir()
    pdf = tmp_path / "fallback.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    universe = tmp_path / "universe.csv"
    out = tmp_path / "out"

    pd.DataFrame(
        [
            {"stock_code": "000001", "stock_name": "已有证据"},
            {"stock_code": "000002", "stock_name": "需回退"},
            {"stock_code": "000003", "stock_name": "缺研报"},
        ]
    ).to_csv(universe, index=False)
    pd.DataFrame(
        [
            {
                "stock_code": "000001",
                "stock_name": "已有证据",
                "source_type": "broker_report_pdf",
                "source_title": "已有研报",
                "source_path": "/tmp/a.pdf",
                "citation_id": "EX1",
                "chunk_id": "000001-EX1",
                "chunk_index": 1,
                "page_start": 1,
                "page_end": 1,
                "page_locator": "1",
                "char_count": 10,
                "chunk_text_length": 10,
                "excerpt": "已有证据",
                "chunk_text": "已有证据",
                "evidence_text": "已有证据",
                "evidence_claim_type": "broker_report_text",
                "citation_granularity": "page_level",
                "citation_ready": True,
                "research_only": True,
                "used_for_signal": False,
                "used_for_admission": False,
            }
        ]
    ).to_csv(previous / "review_universe_report_pdf_evidence_chunks.csv", index=False)
    pd.DataFrame(
        [
            {
                "stock_code": "000001",
                "stock_name": "已有证据",
                "source_file": "/tmp/a.pdf",
                "source_type": "broker_report_pdf",
                "source_title": "已有研报",
                "page": 1,
                "evidence_text": "已有证据",
                "evidence_claim_type": "broker_report_text",
                "citation_quality": "page_level",
                "research_only": True,
                "used_for_signal": False,
                "used_for_admission": False,
            }
        ]
    ).to_csv(previous / "review_universe_report_pdf_page_citations.csv", index=False)
    pd.DataFrame(
        [
            {
                "stock_code": "000002",
                "stock_name": "需回退",
                "source_type": "broker_report_pdf",
                "source_title": "失败研报",
                "source_path": str(pdf),
                "parse_status": "evidence_required",
                "error_detail": "no citation-ready report text extracted",
            },
            {
                "stock_code": "000003",
                "stock_name": "缺研报",
                "source_type": "broker_report_pdf",
                "source_title": "",
                "source_path": "",
                "parse_status": "missing_report_pdf",
                "error_detail": "missing",
            },
        ]
    ).to_csv(previous / "review_universe_report_pdf_parse_failures.csv", index=False)

    summary = run(
        universe_path=universe,
        previous_parse_dir=previous,
        output_dir=out,
        docling_parser=_fake_docling_parser,
    )

    assert summary["review_universe_total_count"] == 3
    assert summary["targeted_fallback_source_count"] == 1
    assert summary["fallback_parse_success_count"] == 1
    assert summary["fallback_page_level_citation_count"] == 1
    assert summary["existing_page_level_report_evidence_count"] == 1
    assert summary["reassessment_input_evidence_count"] == 2
    assert summary["missing_report_pdf_stock_count"] == 1
    assert summary["used_for_signal_count"] == 0
    assert summary["used_for_admission_count"] == 0
    assert summary["acceptance_decision"] == "review_universe_report_reassessment_input_ready"

    expected = {
        "targeted_docling_fallback_summary.json",
        "targeted_docling_fallback_manifest.csv",
        "targeted_docling_fallback_evidence_chunks.csv",
        "targeted_docling_fallback_page_citations.csv",
        "targeted_docling_fallback_failures.csv",
        "review_universe_report_evidence_for_reassessment.csv",
        "review_universe_reassessment_input_stock_status.csv",
        "targeted_docling_fallback_guardrails.json",
        "tech_bottleneck_review_universe_report_pdf_targeted_docling_fallback_v1_report.md",
    }
    assert expected.issubset({path.name for path in out.iterdir()})

    evidence = pd.read_csv(out / "review_universe_report_evidence_for_reassessment.csv", dtype={"stock_code": str})
    status = pd.read_csv(out / "review_universe_reassessment_input_stock_status.csv", dtype={"stock_code": str})
    guardrails = json.loads((out / "targeted_docling_fallback_guardrails.json").read_text(encoding="utf-8"))

    assert set(evidence["stock_code"]) == {"000001", "000002"}
    assert len(status) == 3
    assert dict(zip(status["stock_code"], status["report_reassessment_input_status"])) == {
        "000001": "report_evidence_ready",
        "000002": "report_evidence_ready",
        "000003": "missing_report_pdf",
    }
    assert guardrails["docling_fallback_performed"] is True
    assert guardrails["reassessment_performed"] is False
    assert guardrails["used_for_signal_count"] == 0


def test_targeted_docling_fallback_keeps_unresolved_parse_gap(tmp_path: Path) -> None:
    from stock_research.tech_bottleneck_review_universe_report_pdf_targeted_docling_fallback import run

    previous = tmp_path / "previous"
    previous.mkdir()
    pdf = tmp_path / "bad.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    universe = tmp_path / "universe.csv"
    out = tmp_path / "out"

    pd.DataFrame([{"stock_code": "000002", "stock_name": "需回退"}]).to_csv(universe, index=False)
    pd.DataFrame(columns=["stock_code", "stock_name", "citation_granularity"]).to_csv(
        previous / "review_universe_report_pdf_evidence_chunks.csv",
        index=False,
    )
    pd.DataFrame(columns=["stock_code", "stock_name"]).to_csv(
        previous / "review_universe_report_pdf_page_citations.csv",
        index=False,
    )
    pd.DataFrame(
        [
            {
                "stock_code": "000002",
                "stock_name": "需回退",
                "source_type": "broker_report_pdf",
                "source_title": "坏研报",
                "source_path": str(pdf),
                "parse_status": "evidence_required",
                "error_detail": "no text",
            }
        ]
    ).to_csv(previous / "review_universe_report_pdf_parse_failures.csv", index=False)

    summary = run(
        universe_path=universe,
        previous_parse_dir=previous,
        output_dir=out,
        docling_parser=_fake_docling_parser,
    )

    assert summary["fallback_parse_success_count"] == 0
    assert summary["unresolved_report_parse_gap_count"] == 1
    assert summary["acceptance_decision"] == "conditionally_ready_with_remaining_report_parse_gaps"
