from __future__ import annotations

import importlib.util
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


def _load_script_module():
    spec = importlib.util.spec_from_file_location("tech_bottleneck_candidate_reports_enriched", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_classification_scores_are_not_flat_buckets() -> None:
    module = _load_script_module()

    likely_semiconductor = pd.Series(
        {
            "review_pool_category": "likely_hard_tech_pending_evidence",
            "requalification_v2_category": "likely_hard_tech_pending_evidence",
            "evidence_strength": "pending_primary_source",
            "business_relevance_category": "semiconductor_equipment_or_material",
            "source_group": "seed_tier_a",
            "previous_tier": "Tier A",
            "primary_source_url": "",
            "primary_source_evidence_available": False,
        }
    )
    likely_grid = pd.Series(
        {
            "review_pool_category": "likely_hard_tech_pending_evidence",
            "requalification_v2_category": "likely_hard_tech_pending_evidence",
            "evidence_strength": "pending_primary_source",
            "business_relevance_category": "power_electronics_or_grid_equipment",
            "source_group": "seed_tier_a",
            "previous_tier": "Tier A",
            "primary_source_url": "",
            "primary_source_evidence_available": False,
        }
    )
    verified_moderate = pd.Series(
        {
            "review_pool_category": "verified_core",
            "requalification_v2_category": "verified_core",
            "evidence_strength": "moderate",
            "business_relevance_category": "",
            "source_group": "non_seed_tier_a_manual_review_core",
            "previous_tier": "Tier A",
            "primary_source_url": "",
            "primary_source_evidence_available": False,
        }
    )
    verified_strong_primary = pd.Series(
        {
            "review_pool_category": "verified_core",
            "requalification_v2_category": "verified_core",
            "evidence_strength": "strong",
            "business_relevance_category": "",
            "source_group": "verified_rescue_extension_proposal",
            "previous_tier": "Tier B",
            "primary_source_url": "https://example.com/source.pdf",
            "primary_source_evidence_available": True,
        }
    )

    likely_semiconductor_classification = module._classification(likely_semiconductor)
    likely_grid_classification = module._classification(likely_grid)
    verified_moderate_classification = module._classification(verified_moderate)
    verified_strong_primary_classification = module._classification(verified_strong_primary)

    assert (
        likely_semiconductor_classification["bottleneck_confidence_score"]
        > likely_grid_classification["bottleneck_confidence_score"]
    )
    assert likely_semiconductor_classification["evidence_quality_score"] > likely_grid_classification["evidence_quality_score"]
    assert (
        verified_strong_primary_classification["bottleneck_confidence_score"]
        > verified_moderate_classification["bottleneck_confidence_score"]
    )
    assert verified_strong_primary_classification["evidence_quality_score"] > verified_moderate_classification["evidence_quality_score"]


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
    assert dashboard["bottleneck_confidence_score"].nunique() >= 8
    assert dashboard["evidence_quality_score"].nunique() >= 8


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
