from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
SCRIPT = PROJECT_ROOT / "scripts/run_data_to_brief_docling_90_stock_full_cold_parse_batch.py"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/data_to_brief_docling_90_stock_full_cold_parse_batch_v1"
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


def test_docling_90_stock_full_batch_outputs_and_guardrails() -> None:
    _run_generator()

    expected = {
        "batch_manifest.csv",
        "parser_artifact_audit.csv",
        "source_chunk_manifest_all.csv",
        "table_inventory_all.csv",
        "citation_audit.csv",
        "table_provenance_audit.csv",
        "report_generation_audit.csv",
        "runtime_audit.csv",
        "quality_audit.json",
        "summary.md",
    }
    assert expected.issubset({path.name for path in OUTPUT_DIR.iterdir()})

    summary = json.loads((OUTPUT_DIR / "quality_audit.json").read_text(encoding="utf-8"))
    manifest = pd.read_csv(OUTPUT_DIR / "batch_manifest.csv", dtype={"stock_code": str})
    parser = pd.read_csv(OUTPUT_DIR / "parser_artifact_audit.csv", dtype={"stock_code": str})
    reports = pd.read_csv(OUTPUT_DIR / "report_generation_audit.csv", dtype={"stock_code": str})
    citations = pd.read_csv(OUTPUT_DIR / "citation_audit.csv", dtype={"stock_code": str})

    assert summary["task_name"] == "data_to_brief_docling_90_stock_full_cold_parse_batch_v1"
    assert summary["stock_count"] == 90
    assert len(manifest) == 90
    assert summary["local_pdf_stock_count"] == 90
    assert summary["evidence_required_count"] == 0
    assert summary["cached_parser_artifact_reused_count"] >= 32
    assert summary["parser_artifact_ready_count"] >= 85
    assert summary["docling_parse_failed_count"] <= 5
    assert summary["report_success_count"] >= 85
    assert summary["source_level_citation_count"] == 0
    assert summary["allowed_for_signal"] is False
    assert summary["allowed_for_admission"] is False
    assert summary["production_update"] is False
    assert summary["strategy_file_diff_clean"] is True
    assert summary["acceptance_decision"] in {
        "ready_for_90_stock_review_and_dashboard_integration",
        "parser_hardening_required",
        "report_pipeline_hardening_required",
    }
    assert parser["parser_artifact_status"].isin(["reused_page_level", "cold_parse_page_level", "parse_failed", "invalid"]).all()
    assert reports["report_status"].isin(["page_level_docling_enriched", "partial_docling_enriched", "failed"]).all()
    assert citations["source_level_citation_count"].eq(0).all()


def test_docling_90_stock_full_batch_reports_and_strategy_diff() -> None:
    _run_generator()

    status = pd.read_csv(OUTPUT_DIR / "report_generation_audit.csv", dtype={"stock_code": str})
    report = (OUTPUT_DIR / "summary.md").read_text(encoding="utf-8")

    for _, row in status[status["report_status"].ne("failed")].head(5).iterrows():
        md_path = Path(str(row["report_md_path"]))
        html_path = Path(str(row["report_html_path"]))
        evidence_path = Path(str(row["evidence_matrix_path"]))
        assert md_path.exists()
        assert html_path.exists()
        assert evidence_path.exists()
        text = md_path.read_text(encoding="utf-8")
        assert "引用与数据源 / References" in text

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
