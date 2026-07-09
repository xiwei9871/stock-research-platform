from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
SCRIPT = PROJECT_ROOT / "scripts/run_data_to_brief_backfill_primary_source_text_first_parse.py"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/data_to_brief_backfill_primary_source_text_first_parse_v1"
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


def test_text_first_parse_outputs_and_guardrails() -> None:
    _run_generator()

    expected = {
        "text_first_parse_summary.json",
        "text_first_parse_manifest.csv",
        "text_first_evidence_chunks.csv",
        "text_first_citation_claims.csv",
        "text_first_table_provenance.csv",
        "text_first_quality_audit.csv",
        "docling_fallback_audit.csv",
        "text_first_parse_guardrails.json",
        "data_to_brief_backfill_primary_source_text_first_parse_v1_report.md",
    }
    assert OUTPUT_DIR.exists()
    assert expected.issubset({path.name for path in OUTPUT_DIR.iterdir()})

    summary = json.loads((OUTPUT_DIR / "text_first_parse_summary.json").read_text(encoding="utf-8"))
    guardrails = json.loads((OUTPUT_DIR / "text_first_parse_guardrails.json").read_text(encoding="utf-8"))

    assert summary["source_stock_count"] == 23
    assert summary["source_pdf_count"] == 69
    assert summary["parse_attempt_count"] == 69
    assert summary["text_extract_success_count"] + summary["text_extract_failure_count"] == 69
    assert summary["page_level_citation_count"] > 0
    assert summary["source_level_citation_count"] == 0
    assert summary["docling_structured_artifact_reused_count"] >= 21
    assert summary["used_for_signal_count"] == 0
    assert summary["used_for_admission_count"] == 0
    assert summary["baseline_admission_changed_count"] == 0
    assert summary["strategy_file_diff_clean"] is True
    assert summary["formal_strategy_files_modified"] is False

    assert guardrails["research_only"] is True
    assert guardrails["only_collection_manifest_processed"] is True
    assert guardrails["source_pdf_count"] == 69
    assert guardrails["all_sources_accounted_for"] is True
    assert guardrails["auto_applied_count"] == 0
    assert guardrails["used_for_signal_count"] == 0
    assert guardrails["used_for_admission_count"] == 0
    assert guardrails["baseline_admission_changed_count"] == 0
    assert guardrails["strategy_file_diff_clean"] is True
    assert guardrails["formal_strategy_files_modified"] is False
    assert guardrails["trading_language_hit_count"] == 0
    assert guardrails["execution_language_hit_count"] == 0
    assert guardrails["lookahead_violation_rows"] == 0


def test_text_first_parse_artifact_integrity() -> None:
    _run_generator()

    manifest = pd.read_csv(OUTPUT_DIR / "text_first_parse_manifest.csv", dtype={"stock_code": str})
    chunks = pd.read_csv(OUTPUT_DIR / "text_first_evidence_chunks.csv", dtype={"stock_code": str})
    claims = pd.read_csv(OUTPUT_DIR / "text_first_citation_claims.csv", dtype={"stock_code": str})
    tables = pd.read_csv(OUTPUT_DIR / "text_first_table_provenance.csv", dtype={"stock_code": str})

    assert len(manifest) == 69
    assert manifest["stock_code"].nunique() == 23
    assert {"stock_code", "stock_name", "source_type", "source_title", "source_path", "parse_engine", "parse_status"}.issubset(manifest.columns)

    assert not chunks.empty
    assert chunks["stock_code"].isin(manifest["stock_code"]).all()
    assert chunks["citation_granularity"].eq("page_level").all()
    assert chunks["page_locator"].fillna("").astype(str).str.len().gt(0).all()

    assert not claims.empty
    assert claims["citation_granularity"].eq("page_level").all()
    assert claims["page_locator"].fillna("").astype(str).str.len().gt(0).all()

    if not tables.empty:
        assert tables["stock_code"].isin(manifest["stock_code"]).all()
        assert tables["citation_granularity"].isin(["page_level", "source_level"]).all()


def test_text_first_parse_strategy_diff_clean() -> None:
    _run_generator()

    diff = subprocess.run(
        ["git", "diff", "--", *FORMAL_STRATEGY_FILES],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert diff.stdout == ""
