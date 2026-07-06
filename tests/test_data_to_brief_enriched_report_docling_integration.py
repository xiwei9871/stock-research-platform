from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
SCRIPT = PROJECT_ROOT / "scripts/run_data_to_brief_enriched_report_docling_integration.py"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/data_to_brief_enriched_report_docling_integration_v1"
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


def test_docling_enriched_integration_generates_pilot_reports_and_status() -> None:
    _run_generator()

    expected = {
        "docling_integration_summary.json",
        "docling_evidence_package.csv",
        "docling_claim_citation_map.csv",
        "docling_references.jsonl",
        "docling_evidence_matrix.csv",
        "pilot_docling_enriched_report_status.csv",
        "citation_integrity_audit.csv",
        "report_quality_audit.csv",
        "dashboard_docling_report_manifest_preview.csv",
        "docling_metadata_improvement_attempt.csv",
        "data_to_brief_enriched_report_docling_integration_v1_report.md",
    }
    assert expected.issubset({path.name for path in OUTPUT_DIR.iterdir()})

    summary = json.loads((OUTPUT_DIR / "docling_integration_summary.json").read_text(encoding="utf-8"))
    status = pd.read_csv(OUTPUT_DIR / "pilot_docling_enriched_report_status.csv", dtype={"stock_code": str})
    manifest = pd.read_csv(OUTPUT_DIR / "dashboard_docling_report_manifest_preview.csv", dtype={"stock_code": str})
    package = pd.read_csv(OUTPUT_DIR / "docling_evidence_package.csv", dtype={"stock_code": str})

    assert summary["task_name"] == "data_to_brief_enriched_report_docling_integration_v1"
    assert summary["pilot_stock_count"] == 5
    assert summary["parsed_stock_count"] == 3
    assert summary["missing_pdf_evidence_required_count"] == 2
    assert summary["allowed_for_signal"] is False
    assert summary["allowed_for_admission"] is False
    assert summary["production_update"] is False
    assert summary["acceptance_decision"] in {
        "docling_enriched_report_integration_ready",
        "partial_docling_enriched_report_integration_ready",
    }
    assert len(status) == 5
    assert set(status["stock_code"]) == set(PILOT_STOCKS)
    parsed = status[status["stock_code"].isin(["002371", "688012", "000400"])]
    missing = status[status["stock_code"].isin(["002885", "300838"])]
    assert parsed["report_status"].isin(["docling_enriched_ready", "partial_docling_enriched"]).all()
    assert missing["report_status"].eq("evidence_required").all()
    assert missing["blocker_reason"].str.contains("missing local PDF").all()
    assert len(manifest) == 5
    assert package["citation_granularity"].isin(["page_level", "source_level", "unknown"]).all()
    assert package["citation_granularity"].eq("source_level").any()

    for stock_code, stock_name in PILOT_STOCKS.items():
        md = OUTPUT_DIR / "reports_md" / f"{stock_code}_{stock_name}_docling_enriched_report.md"
        html = OUTPUT_DIR / "reports_html" / f"{stock_code}_{stock_name}_docling_enriched_report.html"
        pdf = OUTPUT_DIR / "reports_pdf" / f"{stock_code}_{stock_name}_docling_enriched_report.pdf"
        evidence_dir = OUTPUT_DIR / "evidence" / stock_code
        assert md.exists()
        assert html.exists()
        assert pdf.exists()
        assert (evidence_dir / "sources.jsonl").exists()
        assert (evidence_dir / "evidence_matrix.csv").exists()
        assert (evidence_dir / "claim_citation_map.csv").exists()
        assert (evidence_dir / "report_status.json").exists()
        text = md.read_text(encoding="utf-8")
        assert "## 引用与数据源 / References" in text
        if stock_code in {"002885", "300838"}:
            assert "evidence_required" in text


def test_docling_enriched_integration_citation_integrity_and_guardrails() -> None:
    _run_generator()

    citations = pd.read_csv(OUTPUT_DIR / "docling_claim_citation_map.csv", dtype={"stock_code": str})
    references = _read_jsonl(OUTPUT_DIR / "docling_references.jsonl")
    citation_audit = pd.read_csv(OUTPUT_DIR / "citation_integrity_audit.csv", dtype={"stock_code": str})
    quality = pd.read_csv(OUTPUT_DIR / "report_quality_audit.csv", dtype={"stock_code": str})
    report = (OUTPUT_DIR / "data_to_brief_enriched_report_docling_integration_v1_report.md").read_text(encoding="utf-8")

    reference_ids = {str(item["citation_id"]) for item in references}
    assert set(citations["citation_id"]).issubset(reference_ids)
    assert citations["source_id"].fillna("").str.len().gt(0).all()
    assert citations["citation_granularity"].isin(["page_level", "source_level", "unknown"]).all()
    assert citation_audit["integrity_status"].eq("pass").all()
    assert quality["allowed_for_signal"].eq(False).all()
    assert quality["allowed_for_admission"].eq(False).all()
    assert quality["production_update"].eq(False).all()

    for stock_code, stock_name in PILOT_STOCKS.items():
        text = (OUTPUT_DIR / "reports_md" / f"{stock_code}_{stock_name}_docling_enriched_report.md").read_text(encoding="utf-8")
        refs = _read_jsonl(OUTPUT_DIR / "evidence" / stock_code / "sources.jsonl")
        ref_ids = {str(item["citation_id"]) for item in refs}
        assert _inline_citations(text).issubset(ref_ids)
        assert "## 引用与数据源 / References" in text
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
