from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
SCRIPT = PROJECT_ROOT / "scripts/run_data_to_brief_docling_90_stock_batch_precheck.py"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/data_to_brief_docling_90_stock_batch_precheck_v1"
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


def test_docling_90_stock_precheck_outputs_and_readiness() -> None:
    _run_generator()

    expected = {
        "batch_manifest.csv",
        "pdf_discovery_audit.csv",
        "parser_artifact_readiness_audit.csv",
        "citation_readiness_audit.csv",
        "table_provenance_readiness_audit.csv",
        "runtime_audit.csv",
        "quality_audit.json",
        "summary.md",
    }
    assert expected.issubset({path.name for path in OUTPUT_DIR.iterdir()})

    summary = json.loads((OUTPUT_DIR / "quality_audit.json").read_text(encoding="utf-8"))
    manifest = pd.read_csv(OUTPUT_DIR / "batch_manifest.csv", dtype={"stock_code": str})
    parser = pd.read_csv(OUTPUT_DIR / "parser_artifact_readiness_audit.csv", dtype={"stock_code": str})
    citation = pd.read_csv(OUTPUT_DIR / "citation_readiness_audit.csv", dtype={"stock_code": str})
    table = pd.read_csv(OUTPUT_DIR / "table_provenance_readiness_audit.csv", dtype={"stock_code": str})
    runtime = pd.read_csv(OUTPUT_DIR / "runtime_audit.csv")

    assert summary["task_name"] == "data_to_brief_docling_90_stock_batch_precheck_v1"
    assert summary["stock_count"] == 90
    assert len(manifest) == 90
    assert summary["local_pdf_stock_count"] + summary["missing_pdf_stock_count"] == 90
    assert summary["evidence_required_count"] == summary["missing_pdf_stock_count"]
    assert summary["cached_parser_artifact_count"] == int(manifest["cached_parser_artifact_available"].eq(True).sum())
    assert summary["cold_parse_required_count"] == int(manifest["cold_parse_required"].eq(True).sum())
    assert summary["expected_source_level_citation_count"] == 0
    assert set(["local_pdf_available", "cached_parser_artifact_available", "pdf_missing", "cold_parse_required"]).issubset(manifest.columns)
    assert parser["parser_artifact_status"].isin(["valid_page_level", "missing", "invalid", "stale_or_unmatched"]).all()
    assert citation["expected_source_level_citation_count"].eq(0).all()
    assert table["table_provenance_ready"].isin([True, False]).all()
    assert set(runtime["runtime_metric"]).issuperset(
        {"measured_cold_parse_runtime_sample", "measured_cached_postprocess_runtime", "estimated_full_cold_runtime"}
    )
    assert summary["allowed_for_signal"] is False
    assert summary["allowed_for_admission"] is False
    assert summary["production_update"] is False
    assert summary["strategy_file_diff_clean"] is True
    assert summary["acceptance_decision"] in {
        "ready_for_90_stock_batch",
        "pdf_discovery_required_before_90_batch",
        "parser_hardening_required",
    }
    if summary["local_pdf_coverage_ratio"] < 0.85:
        assert summary["acceptance_decision"] == "pdf_discovery_required_before_90_batch"


def test_docling_90_stock_precheck_missing_pdf_and_strategy_diff() -> None:
    _run_generator()

    summary = json.loads((OUTPUT_DIR / "quality_audit.json").read_text(encoding="utf-8"))
    manifest = pd.read_csv(OUTPUT_DIR / "batch_manifest.csv", dtype={"stock_code": str})
    source = pd.read_csv(OUTPUT_DIR / "pdf_discovery_audit.csv", dtype={"stock_code": str})
    report = (OUTPUT_DIR / "summary.md").read_text(encoding="utf-8")

    missing = manifest[manifest["pdf_missing"].eq(True)]
    assert missing["evidence_status"].eq("evidence_required").all()
    assert set(summary["known_missing_pdf_symbols"]) == set(missing["stock_code"])
    assert set(summary["known_missing_pdf_names"]) == set(missing["stock_name"])
    for code in ["002121", "002176"]:
        if code in set(manifest["stock_code"]):
            row = source[source["stock_code"].eq(code)]
            assert not row.empty
            assert row.iloc[0]["source_discovery_status"] in {
                "local_pdf_found",
                "cached_download_found",
                "yanbaoke_candidate_found",
                "yanbaoke_no_candidate_found",
                "yanbaoke_search_error",
            }

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
