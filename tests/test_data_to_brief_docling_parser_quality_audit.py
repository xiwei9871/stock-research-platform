from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
SCRIPT = PROJECT_ROOT / "scripts/run_data_to_brief_docling_parser_quality_audit.py"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/data_to_brief_docling_parser_quality_audit_v1"
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]


def _run_generator() -> None:
    result = subprocess.run(
        [str(PROJECT_ROOT / ".venv/bin/python"), str(SCRIPT)],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_docling_parser_quality_audit_outputs_and_stock_statuses() -> None:
    _run_generator()

    expected = {
        "docling_parser_quality_summary.json",
        "docling_source_chunk_quality_audit.csv",
        "docling_table_quality_audit.csv",
        "docling_evidence_gap_audit.csv",
        "docling_parser_quality_audit_report.md",
    }
    assert expected.issubset({path.name for path in OUTPUT_DIR.iterdir()})

    summary = json.loads((OUTPUT_DIR / "docling_parser_quality_summary.json").read_text(encoding="utf-8"))
    chunk_audit = pd.read_csv(OUTPUT_DIR / "docling_source_chunk_quality_audit.csv", dtype={"stock_code": str})
    table_audit = pd.read_csv(OUTPUT_DIR / "docling_table_quality_audit.csv", dtype={"stock_code": str})
    gap_audit = pd.read_csv(OUTPUT_DIR / "docling_evidence_gap_audit.csv", dtype={"stock_code": str})

    assert summary["task_name"] == "data_to_brief_docling_parser_quality_and_integration_test_v1"
    assert summary["pilot_stock_count"] == 5
    assert summary["parsed_stock_count"] == 3
    assert summary["evidence_required_missing_pdf_stock_count"] == 2
    assert summary["chunk_count"] >= 32
    assert summary["table_count"] >= 17
    assert summary["research_only"] is True
    assert summary["allowed_for_signal"] is False
    assert summary["allowed_for_admission"] is False
    assert summary["production_update"] is False

    assert {"002371", "688012", "000400"}.issubset(
        set(gap_audit[gap_audit["chunk_count"].gt(0)]["stock_code"])
    )
    missing_pdf = gap_audit[gap_audit["stock_code"].isin(["002885", "300838"])]
    assert len(missing_pdf) == 2
    assert missing_pdf["actual_status"].eq("evidence_required").all()
    assert missing_pdf["status_match"].eq(True).all()
    assert chunk_audit["citation_ready"].isin([True, False]).all()
    assert chunk_audit["has_non_empty_text"].all()
    assert table_audit["table_relevance"].notna().all()


def test_docling_integration_smoke_citations_and_guardrails() -> None:
    _run_generator()

    smoke_dir = OUTPUT_DIR / "integration_smoke"
    required = {
        "integration_smoke_summary.json",
        "pilot_report_evidence_fill_preview.csv",
        "claim_citation_map_preview.csv",
        "references_preview.jsonl",
        "evidence_matrix_preview.csv",
        "report_status_preview.csv",
    }
    assert required.issubset({path.name for path in smoke_dir.iterdir()})

    smoke_summary = json.loads((smoke_dir / "integration_smoke_summary.json").read_text(encoding="utf-8"))
    fill = pd.read_csv(smoke_dir / "pilot_report_evidence_fill_preview.csv", dtype={"stock_code": str})
    claim_map = pd.read_csv(smoke_dir / "claim_citation_map_preview.csv", dtype={"stock_code": str})
    references = _read_jsonl(smoke_dir / "references_preview.jsonl")
    status = pd.read_csv(smoke_dir / "report_status_preview.csv", dtype={"stock_code": str})
    report = (OUTPUT_DIR / "docling_parser_quality_audit_report.md").read_text(encoding="utf-8")

    assert smoke_summary["parsed_integration_stock_count"] == 3
    assert smoke_summary["citation_count"] == len(references)
    assert smoke_summary["allowed_for_signal"] is False
    assert smoke_summary["allowed_for_admission"] is False
    assert smoke_summary["production_update"] is False
    assert {"business_overview", "key_products", "hard_tech_bottleneck_thesis", "technology_capability", "financial_snapshot", "risks_and_counter_evidence"}.issubset(
        set(fill["report_section"])
    )
    assert {"002371", "688012", "000400"}.issubset(set(status[status["chunk_count"].gt(0)]["stock_code"]))
    assert status[status["stock_code"].isin(["002885", "300838"])]["report_status"].eq("evidence_required").all()
    reference_ids = {str(item["citation_id"]) for item in references}
    assert set(claim_map["citation_id"]).issubset(reference_ids)
    assert claim_map["excerpt"].fillna("").str.len().gt(0).all()

    for forbidden in ["买入", "卖出", "目标价", "target price", "buy recommendation", "sell recommendation"]:
        assert forbidden.lower() not in report.lower()

    diff = subprocess.run(
        ["git", "diff", "--", *FORMAL_STRATEGY_FILES],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert diff.stdout == ""
