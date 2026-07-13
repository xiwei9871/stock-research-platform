from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
SCRIPT = PROJECT_ROOT / "scripts/run_tech_bottleneck_review_universe_report_pdf_docling_parse.py"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_review_universe_report_pdf_docling_parse_v1"
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]


def _fake_extract_pages(pdf_path: Path, max_pages_per_source: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if "fail" in pdf_path.name:
        return [], {
            "page_count": 1,
            "pages_examined": 1,
            "non_empty_page_count": 0,
            "extract_error_count": 1,
            "extract_errors": "fixture_parse_failure",
            "runtime_seconds": 0.0,
        }
    return [
        {
            "page": 1,
            "text": "公司主营核心设备，具备关键材料和国产替代能力，收入来自核心产品。",
            "char_count": 34,
            "keyword_score": 5,
            "section_matches": ["business_overview", "hard_tech_bottleneck_thesis"],
        }
    ], {
        "page_count": 1,
        "pages_examined": 1,
        "non_empty_page_count": 1,
        "extract_error_count": 0,
        "extract_errors": "",
        "runtime_seconds": 0.0,
    }


def test_review_universe_report_pdf_parse_fixture_outputs(tmp_path: Path) -> None:
    from stock_research.tech_bottleneck_review_universe_report_pdf_docling_parse import run

    pdf_a = tmp_path / "000001-report.pdf"
    pdf_b = tmp_path / "000002-fail.pdf"
    pdf_a.write_bytes(b"%PDF-1.4\n")
    pdf_b.write_bytes(b"%PDF-1.4\n")

    universe = tmp_path / "review_universe.csv"
    coverage = tmp_path / "coverage.csv"
    out = tmp_path / "out"

    pd.DataFrame(
        [
            {"stock_code": "000001", "stock_name": "测试一"},
            {"stock_code": "000002", "stock_name": "测试二"},
            {"stock_code": "000003", "stock_name": "测试三"},
        ]
    ).to_csv(universe, index=False)
    pd.DataFrame(
        [
            {
                "stock_code": "000001",
                "stock_name": "测试一",
                "has_report_pdf": True,
                "report_pdf_count": 1,
                "report_pdf_paths": str(pdf_a),
                "report_titles": "测试研报一.pdf",
            },
            {
                "stock_code": "000002",
                "stock_name": "测试二",
                "has_report_pdf": True,
                "report_pdf_count": 1,
                "report_pdf_paths": str(pdf_b),
                "report_titles": "测试研报二.pdf",
            },
            {
                "stock_code": "000003",
                "stock_name": "测试三",
                "has_report_pdf": False,
                "report_pdf_count": 0,
                "report_pdf_paths": "",
                "report_titles": "",
            },
        ]
    ).to_csv(coverage, index=False)

    summary = run(
        universe_path=universe,
        coverage_path=coverage,
        output_dir=out,
        max_pdfs_per_stock=1,
        extract_pages_func=_fake_extract_pages,
    )

    expected = {
        "review_universe_report_pdf_parse_summary.json",
        "review_universe_report_pdf_parse_manifest.csv",
        "review_universe_report_pdf_parse_audit.csv",
        "review_universe_report_pdf_evidence_chunks.csv",
        "review_universe_report_pdf_page_citations.csv",
        "review_universe_report_pdf_parse_failures.csv",
        "review_universe_report_pdf_docling_guardrails.json",
        "tech_bottleneck_review_universe_report_pdf_docling_parse_v1_report.md",
    }
    assert expected.issubset({path.name for path in out.iterdir()})
    assert summary["review_universe_total_count"] == 3
    assert summary["report_pdf_covered_stock_count"] == 2
    assert summary["missing_report_pdf_stock_count"] == 1
    assert summary["parse_attempt_count"] == 2
    assert summary["parse_success_count"] == 1
    assert summary["parse_failure_count"] == 1
    assert summary["page_level_citation_count"] == 1
    assert summary["used_for_signal_count"] == 0
    assert summary["used_for_admission_count"] == 0
    assert summary["acceptance_decision"] == "conditionally_ready_with_parse_failures"

    manifest = pd.read_csv(out / "review_universe_report_pdf_parse_manifest.csv", dtype={"stock_code": str})
    chunks = pd.read_csv(out / "review_universe_report_pdf_evidence_chunks.csv", dtype={"stock_code": str})
    citations = pd.read_csv(out / "review_universe_report_pdf_page_citations.csv", dtype={"stock_code": str})
    failures = pd.read_csv(out / "review_universe_report_pdf_parse_failures.csv", dtype={"stock_code": str})
    guardrails = json.loads((out / "review_universe_report_pdf_docling_guardrails.json").read_text(encoding="utf-8"))

    assert len(manifest) == 2
    assert set(manifest["stock_code"]) == {"000001", "000002"}
    assert len(chunks) == 1
    assert chunks.iloc[0]["citation_granularity"] == "page_level"
    assert len(citations) == 1
    assert len(failures) == 2
    assert set(failures["stock_code"]) == {"000002", "000003"}
    assert set(failures["parse_status"]) == {"evidence_required", "missing_report_pdf"}
    assert guardrails["research_only"] is True
    assert guardrails["broker_report_parse_performed"] is True
    assert guardrails["primary_source_collection_performed"] is False
    assert guardrails["evidence_backfill_performed"] is False
    assert guardrails["core_equivalence_performed"] is False
    assert guardrails["reassessment_performed"] is False


def test_review_universe_report_pdf_parse_real_outputs_and_strategy_diff() -> None:
    result = subprocess.run(
        [str(PROJECT_ROOT / ".venv/bin/python"), str(SCRIPT), "--max-pdfs-per-stock", "1"],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    summary = json.loads((OUTPUT_DIR / "review_universe_report_pdf_parse_summary.json").read_text(encoding="utf-8"))
    guardrails = json.loads((OUTPUT_DIR / "review_universe_report_pdf_docling_guardrails.json").read_text(encoding="utf-8"))
    manifest = pd.read_csv(OUTPUT_DIR / "review_universe_report_pdf_parse_manifest.csv", dtype={"stock_code": str})
    chunks = pd.read_csv(OUTPUT_DIR / "review_universe_report_pdf_evidence_chunks.csv", dtype={"stock_code": str})

    assert summary["research_only"] is True
    assert summary["review_universe_total_count"] == 378
    assert summary["report_pdf_covered_stock_count"] == 367
    assert summary["missing_report_pdf_stock_count"] == 11
    assert summary["parse_attempt_count"] == len(manifest)
    assert summary["parse_success_count"] + summary["parse_failure_count"] == len(manifest)
    assert summary["broker_report_parse_performed"] is True
    assert summary["primary_source_collection_performed"] is False
    assert summary["evidence_backfill_performed"] is False
    assert summary["core_equivalence_performed"] is False
    assert summary["reassessment_performed"] is False
    assert summary["used_for_signal_count"] == 0
    assert summary["used_for_admission_count"] == 0
    assert summary["strategy_file_diff_clean"] is True
    assert guardrails["strategy_file_diff_clean"] is True
    if not chunks.empty:
        assert chunks["citation_granularity"].eq("page_level").all()
        assert chunks["used_for_signal"].eq(False).all()
        assert chunks["used_for_admission"].eq(False).all()

    diff = subprocess.run(
        ["git", "diff", "--", *FORMAL_STRATEGY_FILES],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert diff.stdout == ""
