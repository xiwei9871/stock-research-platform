from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
SCRIPT = PROJECT_ROOT / "scripts/run_tech_bottleneck_candidate_reports.py"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_candidate_reports_v1"
CANONICAL_POOL = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_seed_tier_a_requalification_v2_review_pool_refinement/hard_tech_review_pool_preview.csv"
)
LEGACY_POOL = PROJECT_ROOT / "outputs/research/tech_bottleneck_candidate_universe_workbench_patch_v1/workbench_core_candidates.csv"
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]
PILOT_CODES = "002371,688012,002885,300838,000400"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run_generator(*args: str) -> tuple[str, str, str, str]:
    canonical_before = _sha(CANONICAL_POOL)
    legacy_before = _sha(LEGACY_POOL)
    result = subprocess.run(
        [str(PROJECT_ROOT / ".venv/bin/python"), str(SCRIPT), *args],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return canonical_before, _sha(CANONICAL_POOL), legacy_before, _sha(LEGACY_POOL)


def test_candidate_reports_pilot_generates_five_research_only_reports() -> None:
    before, after, legacy_before, legacy_after = _run_generator("--limit", "5", "--stock-codes", PILOT_CODES)
    assert before == after
    assert legacy_before == legacy_after

    summary = json.loads((OUTPUT_DIR / "report_run_summary.json").read_text(encoding="utf-8"))
    manifest = pd.read_csv(OUTPUT_DIR / "report_manifest.csv", dtype={"stock_code": str})
    assert summary["canonical_scope_count"] == 90
    assert summary["generated_report_count"] == 5
    assert summary["legacy_pool_used_as_default"] is False
    assert summary["allowed_for_signal_count"] == 0
    assert summary["allowed_for_admission_count"] == 0
    assert set(manifest["stock_name"]) == {"北方华创", "中微公司", "京泉华", "浙江力诺", "许继电气"}
    assert {"北方华创", "中微公司"}.issubset(set(manifest["stock_name"]))
    assert manifest["report_status"].notna().all()

    for _, row in manifest.iterrows():
        for column in ["report_md_path", "report_html_path", "evidence_matrix_path"]:
            assert (PROJECT_ROOT / row[column]).exists(), row[column]
        evidence = pd.read_csv(PROJECT_ROOT / row["evidence_matrix_path"])
        assert not evidence.empty
        markdown = (PROJECT_ROOT / row["report_md_path"]).read_text(encoding="utf-8")
        assert "Research-only" in markdown
        assert "买入" not in markdown
        assert "卖出" not in markdown
        assert "buy recommendation" not in markdown.lower()
        assert "sell recommendation" not in markdown.lower()


def test_candidate_reports_full_batch_manifest_uses_canonical_90_scope() -> None:
    _run_generator()
    summary = json.loads((OUTPUT_DIR / "report_run_summary.json").read_text(encoding="utf-8"))
    manifest = pd.read_csv(OUTPUT_DIR / "report_manifest.csv", dtype={"stock_code": str})
    scoped = pd.read_csv(OUTPUT_DIR / "hard_tech_review_pool_with_report_status.csv", dtype={"stock_code": str})

    assert summary["canonical_scope_count"] == 90
    assert summary["generated_report_count"] == 90
    assert len(manifest) == 90
    assert len(scoped) == 90
    assert "佛山照明" not in set(scoped["stock_name"])
    assert "通宝能源" not in set(scoped["stock_name"])
    assert not {"渝农商行", "浙商银行", "建设银行", "中信银行"}.intersection(set(scoped["stock_name"]))
    assert {"北方华创", "中微公司", "京泉华", "浙江力诺"}.issubset(set(scoped["stock_name"]))
    assert manifest["report_md_path"].map(lambda path: (PROJECT_ROOT / path).exists()).all()
    assert manifest["report_html_path"].map(lambda path: (PROJECT_ROOT / path).exists()).all()
    assert manifest["evidence_matrix_path"].map(lambda path: (PROJECT_ROOT / path).exists()).all()
    assert set(manifest["used_for_signal"]) == {False}
    assert set(manifest["used_for_admission"]) == {False}


def test_candidate_reports_aggregate_outputs_and_strategy_diff_clean() -> None:
    _run_generator("--limit", "5", "--stock-codes", PILOT_CODES)
    expected_files = {
        "report_run_summary.json",
        "report_manifest.csv",
        "report_manifest.json",
        "hard_tech_review_pool_with_report_status.csv",
        "report_quality_audit.csv",
        "evidence_coverage_summary.csv",
        "hard_tech_candidate_landscape_report.md",
        "hard_tech_candidate_landscape_report.pdf",
    }
    assert expected_files.issubset({path.name for path in OUTPUT_DIR.iterdir()})

    diff = subprocess.run(
        ["git", "diff", "--", *FORMAL_STRATEGY_FILES],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert diff.stdout == ""
