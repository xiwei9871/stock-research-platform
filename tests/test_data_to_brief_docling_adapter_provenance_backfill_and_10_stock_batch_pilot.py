from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
SCRIPT = PROJECT_ROOT / "scripts/run_data_to_brief_docling_adapter_provenance_backfill_and_10_stock_batch_pilot.py"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/data_to_brief_docling_adapter_provenance_backfill_and_10_stock_batch_pilot_v1"
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]
PILOT_STOCKS = {
    "002371": "北方华创",
    "688012": "中微公司",
    "000400": "许继电气",
    "002885": "京泉华",
    "300838": "浙江力诺",
    "300476": "胜宏科技",
    "300308": "中际旭创",
    "300502": "新易盛",
    "688256": "寒武纪",
    "688120": "华海清科",
}


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
    return set(re.findall(r"\[(S\d+)\]", markdown))


def test_docling_adapter_backfill_10_stock_outputs_and_statuses() -> None:
    _run_generator()

    expected = {
        "docling_adapter_provenance_backfill_summary.json",
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
        "dashboard_docling_10_stock_manifest_preview.csv",
        "data_to_brief_docling_adapter_provenance_backfill_and_10_stock_batch_pilot_v1_report.md",
    }
    assert expected.issubset({path.name for path in OUTPUT_DIR.iterdir()})

    summary = json.loads((OUTPUT_DIR / "docling_adapter_provenance_backfill_summary.json").read_text(encoding="utf-8"))
    status = pd.read_csv(OUTPUT_DIR / "batch_report_status.csv", dtype={"stock_code": str})
    chunks = pd.read_csv(OUTPUT_DIR / "batch_source_chunk_manifest.csv", dtype={"stock_code": str})
    tables = pd.read_csv(OUTPUT_DIR / "batch_table_inventory.csv", dtype={"stock_code": str})

    assert summary["task_name"] == "data_to_brief_docling_adapter_provenance_backfill_and_10_stock_batch_pilot_v1"
    assert summary["pilot_stock_count"] == 10
    assert summary["status_row_count"] == 10
    assert summary["page_level_citation_count"] >= 22
    assert summary["allowed_for_signal"] is False
    assert summary["allowed_for_admission"] is False
    assert summary["production_update"] is False
    assert summary["acceptance_decision"] == "ready_for_30_stock_batch"
    assert len(status) == 10
    assert set(status["stock_code"]) == set(PILOT_STOCKS)
    assert status[status["has_local_pdf"].eq(False)]["report_status"].eq("evidence_required").all()
    assert chunks["citation_granularity"].isin(["page_level", "source_level", "unknown"]).all()
    assert chunks[chunks["citation_granularity"].eq("page_level")]["page_locator"].fillna("").astype(str).str.len().gt(0).all()
    if not tables.empty:
        assert {"page_locator", "row_count", "column_count", "table_relevance", "citation_granularity"}.issubset(tables.columns)

    for stock_code, stock_name in PILOT_STOCKS.items():
        md = OUTPUT_DIR / "reports_md" / f"{stock_code}_{stock_name}_docling_10_stock_pilot_report.md"
        html = OUTPUT_DIR / "reports_html" / f"{stock_code}_{stock_name}_docling_10_stock_pilot_report.html"
        pdf = OUTPUT_DIR / "reports_pdf" / f"{stock_code}_{stock_name}_docling_10_stock_pilot_report.pdf"
        evidence_dir = OUTPUT_DIR / "evidence" / stock_code
        assert md.exists()
        assert html.exists()
        assert pdf.exists()
        assert (evidence_dir / "sources.jsonl").exists()
        assert (evidence_dir / "evidence_matrix.csv").exists()
        assert (evidence_dir / "claim_citation_map.csv").exists()
        assert (evidence_dir / "report_status.json").exists()
        assert "## 引用与数据源 / References" in md.read_text(encoding="utf-8")


def test_docling_adapter_backfill_10_stock_citations_and_guardrails() -> None:
    _run_generator()

    claim_map = pd.read_csv(OUTPUT_DIR / "batch_claim_citation_map.csv", dtype={"stock_code": str})
    references = _read_jsonl(OUTPUT_DIR / "batch_references.jsonl")
    citation_audit = pd.read_csv(OUTPUT_DIR / "batch_citation_integrity_audit.csv", dtype={"stock_code": str})
    quality = pd.read_csv(OUTPUT_DIR / "batch_report_quality_audit.csv", dtype={"stock_code": str})
    report = (OUTPUT_DIR / "data_to_brief_docling_adapter_provenance_backfill_and_10_stock_batch_pilot_v1_report.md").read_text(encoding="utf-8")

    ref_ids = {str(row["citation_id"]) for row in references}
    assert set(claim_map["citation_id"]).issubset(ref_ids)
    assert claim_map["source_id"].fillna("").str.len().gt(0).all()
    assert claim_map["citation_granularity"].isin(["page_level", "source_level"]).all()
    assert claim_map[claim_map["citation_granularity"].eq("page_level")]["page_locator"].fillna("").astype(str).str.len().gt(0).all()
    assert citation_audit["integrity_status"].eq("pass").all()
    assert quality["allowed_for_signal"].eq(False).all()
    assert quality["allowed_for_admission"].eq(False).all()
    assert quality["production_update"].eq(False).all()

    for stock_code, stock_name in PILOT_STOCKS.items():
        text = (OUTPUT_DIR / "reports_md" / f"{stock_code}_{stock_name}_docling_10_stock_pilot_report.md").read_text(encoding="utf-8")
        refs = _read_jsonl(OUTPUT_DIR / "evidence" / stock_code / "sources.jsonl")
        assert _inline_citations(text).issubset({str(row["citation_id"]) for row in refs})
        for forbidden in ["买入", "卖出", "目标价", "target price", "buy recommendation", "sell recommendation"]:
            assert forbidden.lower() not in text.lower()

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
