from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
SCRIPT = PROJECT_ROOT / "scripts/run_data_to_brief_docling_metadata_recovery.py"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/data_to_brief_docling_page_table_metadata_recovery_v1"
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]
PILOT_STOCKS = {"002371", "688012", "000400", "002885", "300838"}
PARSED_STOCKS = {"002371", "688012", "000400"}
MISSING_PDF_STOCKS = {"002885", "300838"}


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


def test_docling_metadata_recovery_outputs_and_statuses() -> None:
    _run_generator()

    expected = {
        "docling_metadata_recovery_summary.json",
        "docling_raw_structure_probe.jsonl",
        "docling_text_item_provenance_probe.csv",
        "docling_table_item_provenance_probe.csv",
        "docling_page_locator_recovery_audit.csv",
        "docling_table_metadata_recovery_audit.csv",
        "docling_evidence_package_with_metadata.csv",
        "docling_claim_citation_map_with_metadata.csv",
        "docling_references_with_metadata.jsonl",
        "docling_evidence_matrix_with_metadata.csv",
        "citation_granularity_upgrade_audit.csv",
        "pilot_docling_metadata_enriched_report_status.csv",
        "citation_integrity_audit_with_metadata.csv",
        "report_quality_audit_with_metadata.csv",
        "dashboard_docling_metadata_report_manifest_preview.csv",
        "docling_metadata_recovery_report.md",
    }
    assert expected.issubset({path.name for path in OUTPUT_DIR.iterdir()})

    summary = json.loads((OUTPUT_DIR / "docling_metadata_recovery_summary.json").read_text(encoding="utf-8"))
    status = pd.read_csv(OUTPUT_DIR / "pilot_docling_metadata_enriched_report_status.csv", dtype={"stock_code": str})
    package = pd.read_csv(OUTPUT_DIR / "docling_evidence_package_with_metadata.csv", dtype={"stock_code": str})
    upgrade = pd.read_csv(OUTPUT_DIR / "citation_granularity_upgrade_audit.csv", dtype={"stock_code": str})

    assert summary["task_name"] == "data_to_brief_docling_page_table_metadata_recovery_v1"
    assert summary["pilot_stock_count"] == 5
    assert summary["parsed_stock_count"] == 3
    assert summary["missing_pdf_evidence_required_count"] == 2
    assert summary["previous_citation_count"] == 22
    assert summary["preserved_or_remapped_citation_count"] >= 22
    assert summary["allowed_for_signal"] is False
    assert summary["allowed_for_admission"] is False
    assert summary["production_update"] is False
    assert set(status["stock_code"]) == PILOT_STOCKS
    assert set(status[status["stock_code"].isin(PARSED_STOCKS)]["stock_code"]) == PARSED_STOCKS
    assert status[status["stock_code"].isin(MISSING_PDF_STOCKS)]["report_status"].eq("evidence_required").all()
    assert status[status["stock_code"].isin(MISSING_PDF_STOCKS)]["blocker_reason"].str.contains("missing").all()
    assert package["citation_granularity"].isin(["source_level", "page_level"]).all()
    assert package[package["citation_granularity"].eq("page_level")]["page_locator"].fillna("").str.len().gt(0).all()
    assert set(upgrade["upgrade_status"]).issubset({"upgraded_to_page_level", "still_source_level", "unavailable"})


def test_docling_metadata_recovery_citations_reports_and_guardrails() -> None:
    _run_generator()

    summary = json.loads((OUTPUT_DIR / "docling_metadata_recovery_summary.json").read_text(encoding="utf-8"))
    claim_map = pd.read_csv(OUTPUT_DIR / "docling_claim_citation_map_with_metadata.csv", dtype={"stock_code": str})
    refs = _read_jsonl(OUTPUT_DIR / "docling_references_with_metadata.jsonl")
    citation_audit = pd.read_csv(OUTPUT_DIR / "citation_integrity_audit_with_metadata.csv", dtype={"stock_code": str})
    quality = pd.read_csv(OUTPUT_DIR / "report_quality_audit_with_metadata.csv", dtype={"stock_code": str})
    report = (OUTPUT_DIR / "docling_metadata_recovery_report.md").read_text(encoding="utf-8")

    ref_ids = {str(row["citation_id"]) for row in refs}
    assert set(claim_map["citation_id"]).issubset(ref_ids)
    assert claim_map["citation_granularity"].isin(["source_level", "page_level"]).all()
    assert citation_audit["integrity_status"].eq("pass").all()
    assert quality["allowed_for_signal"].eq(False).all()
    assert quality["allowed_for_admission"].eq(False).all()
    assert quality["production_update"].eq(False).all()
    if summary["page_level_citation_count"] == 0:
        assert "page-level provenance could not be recovered" in report

    for stock_code in PARSED_STOCKS:
        name = {"002371": "北方华创", "688012": "中微公司", "000400": "许继电气"}[stock_code]
        md = OUTPUT_DIR / "reports_md" / f"{stock_code}_{name}_docling_metadata_enriched_report.md"
        assert md.exists()
        text = md.read_text(encoding="utf-8")
        stock_refs = _read_jsonl(OUTPUT_DIR / "evidence" / stock_code / "sources.jsonl")
        assert _inline_citations(text).issubset({str(row["citation_id"]) for row in stock_refs})
        assert "## 引用与数据源 / References" in text
        for forbidden in ["买入", "卖出", "目标价", "target price", "buy recommendation", "sell recommendation"]:
            assert forbidden.lower() not in text.lower()

    for stock_code in MISSING_PDF_STOCKS:
        name = {"002885": "京泉华", "300838": "浙江力诺"}[stock_code]
        md = OUTPUT_DIR / "reports_md" / f"{stock_code}_{name}_docling_metadata_enriched_report.md"
        assert md.exists()
        assert "evidence_required" in md.read_text(encoding="utf-8")

    diff = subprocess.run(
        ["git", "diff", "--", *FORMAL_STRATEGY_FILES],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert diff.stdout == ""
