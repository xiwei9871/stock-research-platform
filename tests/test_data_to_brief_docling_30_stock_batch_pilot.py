from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
SCRIPT = PROJECT_ROOT / "scripts/run_data_to_brief_docling_30_stock_batch_pilot.py"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/data_to_brief_docling_30_stock_batch_pilot_v1"
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


def _inline_citations(markdown: str) -> set[str]:
    return set(re.findall(r"\[(S[^\]]+)\]", markdown))


def test_docling_30_stock_batch_outputs_and_guardrails() -> None:
    _run_generator()

    expected = {
        "docling_30_stock_batch_pilot_summary.json",
        "batch_source_chunk_manifest.csv",
        "batch_table_inventory.csv",
        "batch_evidence_matrix.csv",
        "batch_claim_citation_map.csv",
        "batch_references.jsonl",
        "batch_report_status.csv",
        "batch_citation_integrity_audit.csv",
        "batch_report_quality_audit.csv",
        "batch_table_quality_audit.csv",
        "batch_parser_quality_audit.csv",
        "dashboard_docling_30_stock_manifest_preview.csv",
        "data_to_brief_docling_30_stock_batch_pilot_v1_report.md",
    }
    assert expected.issubset({path.name for path in OUTPUT_DIR.iterdir()})

    summary = json.loads((OUTPUT_DIR / "docling_30_stock_batch_pilot_summary.json").read_text(encoding="utf-8"))
    status = pd.read_csv(OUTPUT_DIR / "batch_report_status.csv", dtype={"stock_code": str})
    chunks = pd.read_csv(OUTPUT_DIR / "batch_source_chunk_manifest.csv", dtype={"stock_code": str})
    tables = pd.read_csv(OUTPUT_DIR / "batch_table_inventory.csv", dtype={"stock_code": str})
    citation_audit = pd.read_csv(OUTPUT_DIR / "batch_citation_integrity_audit.csv", dtype={"stock_code": str})
    quality = pd.read_csv(OUTPUT_DIR / "batch_report_quality_audit.csv", dtype={"stock_code": str})

    assert summary["task_name"] == "data_to_brief_docling_30_stock_batch_pilot_v1"
    assert summary["stock_count"] == 30
    assert len(status) == 30
    assert summary["local_pdf_stock_count"] + summary["missing_pdf_stock_count"] == 30
    assert summary["evidence_required_count"] == int(status["report_status"].eq("evidence_required").sum())
    assert summary["docling_parse_success_count"] >= 24
    assert summary["source_chunk_count"] == len(chunks)
    assert summary["table_row_count"] == len(tables)
    assert summary["source_level_citation_count"] == 0
    assert summary["citations_with_page_locator_count"] == summary["citation_claim_count"]
    assert summary["allowed_for_signal"] is False
    assert summary["allowed_for_admission"] is False
    assert summary["production_update"] is False
    assert summary["strategy_file_diff_clean"] is True
    assert summary["acceptance_decision"] in {
        "ready_for_90_stock_batch_precheck",
        "conditional_pdf_discovery_required",
        "conditional_parser_tuning_required",
    }

    assert status[status["has_local_pdf"].eq(False)]["report_status"].eq("evidence_required").all()
    assert chunks["citation_granularity"].isin(["page_level", "source_level", "unknown"]).all()
    assert chunks[chunks["citation_granularity"].eq("page_level")]["page_locator"].fillna("").astype(str).str.len().gt(0).all()
    assert citation_audit["integrity_status"].eq("pass").all()
    assert quality["allowed_for_signal"].eq(False).all()
    assert quality["allowed_for_admission"].eq(False).all()
    assert quality["production_update"].eq(False).all()


def test_docling_30_stock_batch_reports_citations_and_strategy_diff() -> None:
    _run_generator()

    status = pd.read_csv(OUTPUT_DIR / "batch_report_status.csv", dtype={"stock_code": str})
    for _, row in status.iterrows():
        stock_code = row["stock_code"]
        stock_name = row["stock_name"]
        md = OUTPUT_DIR / "reports_md" / f"{stock_code}_{stock_name}_docling_30_stock_pilot_report.md"
        html = OUTPUT_DIR / "reports_html" / f"{stock_code}_{stock_name}_docling_30_stock_pilot_report.html"
        pdf = OUTPUT_DIR / "reports_pdf" / f"{stock_code}_{stock_name}_docling_30_stock_pilot_report.pdf"
        evidence_dir = OUTPUT_DIR / "evidence" / stock_code
        assert md.exists()
        assert html.exists()
        assert pdf.exists()
        assert (evidence_dir / "sources.jsonl").exists()
        assert (evidence_dir / "evidence_matrix.csv").exists()
        assert (evidence_dir / "claim_citation_map.csv").exists()
        text = md.read_text(encoding="utf-8")
        assert "## 引用与数据源 / References" in text
        refs = _read_jsonl(evidence_dir / "sources.jsonl")
        assert _inline_citations(text).issubset({str(ref["citation_id"]) for ref in refs})
        for forbidden in ["买入", "卖出", "目标价", "target price", "buy recommendation", "sell recommendation"]:
            assert forbidden.lower() not in text.lower()

    report = (OUTPUT_DIR / "data_to_brief_docling_30_stock_batch_pilot_v1_report.md").read_text(encoding="utf-8")
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
