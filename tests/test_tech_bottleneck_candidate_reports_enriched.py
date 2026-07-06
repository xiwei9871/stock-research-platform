from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
SCRIPT = PROJECT_ROOT / "scripts/run_tech_bottleneck_candidate_reports_enriched.py"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_candidate_reports_enriched_v1"
CANONICAL_POOL = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_seed_tier_a_requalification_v2_review_pool_refinement/hard_tech_review_pool_preview.csv"
)
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]
PILOT_CODES = "002371,688012,002885,300838,000400"


def _run_generator(*args: str) -> None:
    result = subprocess.run(
        [str(PROJECT_ROOT / ".venv/bin/python"), str(SCRIPT), *args],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def _citations(markdown: str) -> set[str]:
    return set(re.findall(r"\[(S\d+)\]", markdown))


def test_enriched_reports_pilot_has_citations_references_and_sources() -> None:
    _run_generator("--limit", "5", "--stock-codes", PILOT_CODES)

    summary = json.loads((OUTPUT_DIR / "enriched_report_run_summary.json").read_text(encoding="utf-8"))
    manifest = pd.read_csv(OUTPUT_DIR / "enriched_report_manifest.csv", dtype={"stock_code": str})
    assert summary["canonical_scope_count"] == 90
    assert summary["legacy_pool_used_as_default"] is False
    assert summary["generated_report_count"] == 5
    assert summary["allowed_for_signal_count"] == 0
    assert summary["allowed_for_admission_count"] == 0
    assert summary["trading_language_hit_count"] == 0
    assert set(manifest["stock_name"]) == {"北方华创", "中微公司", "京泉华", "浙江力诺", "许继电气"}

    for _, row in manifest.iterrows():
        markdown_path = PROJECT_ROOT / row["report_md_path"]
        sources_path = PROJECT_ROOT / row["sources_path"]
        evidence_path = PROJECT_ROOT / row["evidence_matrix_path"]
        claim_map_path = PROJECT_ROOT / row["claim_citation_map_path"]
        markdown = markdown_path.read_text(encoding="utf-8")
        assert "## 引用与数据源 / References" in markdown
        assert (PROJECT_ROOT / row["report_html_path"]).exists()
        assert (PROJECT_ROOT / row["report_pdf_path"]).exists()
        assert sources_path.exists()
        assert evidence_path.exists()
        assert claim_map_path.exists()
        source_ids = {
            json.loads(line)["citation_id"]
            for line in sources_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        }
        assert _citations(markdown).issubset(source_ids)
        evidence = pd.read_csv(evidence_path)
        claim_map = pd.read_csv(claim_map_path)
        assert evidence["citation_id"].notna().all()
        assert claim_map["citation_id"].notna().all()
        assert "买入" not in markdown
        assert "卖出" not in markdown
        assert "目标价" not in markdown


def test_enriched_reports_full_batch_and_scope_guardrails() -> None:
    _run_generator()
    manifest = pd.read_csv(OUTPUT_DIR / "enriched_report_manifest.csv", dtype={"stock_code": str})
    scoped = pd.read_csv(OUTPUT_DIR / "hard_tech_review_pool_with_enriched_report_status.csv", dtype={"stock_code": str})
    dashboard = pd.read_csv(OUTPUT_DIR / "report_dashboard_manifest.csv", dtype={"stock_code": str})
    assert len(manifest) == 90
    assert len(scoped) == 90
    assert len(dashboard) == 90
    assert {"北方华创", "中微公司"}.issubset(set(manifest["stock_name"]))
    assert not {"佛山照明", "通宝能源"}.intersection(set(manifest["stock_name"]))
    assert manifest["report_status"].notna().all()
    assert manifest["report_md_path"].map(lambda path: (PROJECT_ROOT / path).exists()).all()
    assert manifest["report_html_path"].map(lambda path: (PROJECT_ROOT / path).exists()).all()
    assert manifest["evidence_matrix_path"].map(lambda path: (PROJECT_ROOT / path).exists()).all()


def test_enriched_reports_aggregate_outputs_and_formal_strategy_diff_clean() -> None:
    _run_generator("--limit", "5", "--stock-codes", PILOT_CODES)
    expected = {
        "enriched_report_run_summary.json",
        "enriched_report_manifest.csv",
        "enriched_report_manifest.json",
        "hard_tech_review_pool_with_enriched_report_status.csv",
        "source_coverage_by_stock.csv",
        "source_coverage_by_type.csv",
        "evidence_quality_audit.csv",
        "citation_quality_audit.csv",
        "failed_source_fetches.csv",
        "evidence_gap_queue.csv",
        "hard_tech_candidate_landscape_report.md",
        "hard_tech_candidate_landscape_report.html",
        "hard_tech_candidate_landscape_report.pdf",
        "tech_bottleneck_candidate_reports_enriched_v1_report.md",
        "report_dashboard_manifest.csv",
    }
    assert expected.issubset({path.name for path in OUTPUT_DIR.iterdir()})

    diff = subprocess.run(
        ["git", "diff", "--", *FORMAL_STRATEGY_FILES],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert diff.stdout == ""
