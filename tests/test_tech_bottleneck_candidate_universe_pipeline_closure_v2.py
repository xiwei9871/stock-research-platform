from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_candidate_universe_pipeline_closure_v2"
SCRIPT = PROJECT_ROOT / "scripts/run_tech_bottleneck_candidate_universe_pipeline_closure_v2.py"
DEFAULT_POOL = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_seed_tier_a_requalification_v2_review_pool_refinement/hard_tech_review_pool_preview.csv"
)
LEGACY_POOL = PROJECT_ROOT / "outputs/research/tech_bottleneck_candidate_universe_workbench_patch_v1/workbench_core_candidates.csv"
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run_generator() -> tuple[str, str, str, str]:
    default_before = _sha(DEFAULT_POOL)
    legacy_before = _sha(LEGACY_POOL)
    result = subprocess.run(
        [str(PROJECT_ROOT / ".venv/bin/python"), str(SCRIPT)],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return default_before, _sha(DEFAULT_POOL), legacy_before, _sha(LEGACY_POOL)


def _hash_outputs() -> dict[str, str]:
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(OUTPUT_DIR.iterdir())
        if path.is_file()
    }


def test_pipeline_closure_v2_outputs_and_canonical_manifest() -> None:
    default_before, default_after, legacy_before, legacy_after = _run_generator()
    assert default_before == default_after
    assert legacy_before == legacy_after

    expected_files = {
        "pipeline_closure_v2_summary.json",
        "canonical_artifact_manifest_v2.json",
        "candidate_universe_readiness_matrix_v2.csv",
        "deprecated_artifacts.json",
        "guardrail_closure_check_v2.json",
        "tech_bottleneck_candidate_universe_pipeline_closure_v2_report.md",
    }
    assert expected_files.issubset({path.name for path in OUTPUT_DIR.iterdir()})

    summary = json.loads((OUTPUT_DIR / "pipeline_closure_v2_summary.json").read_text(encoding="utf-8"))
    manifest = json.loads((OUTPUT_DIR / "canonical_artifact_manifest_v2.json").read_text(encoding="utf-8"))
    deprecated = json.loads((OUTPUT_DIR / "deprecated_artifacts.json").read_text(encoding="utf-8"))
    guardrails = json.loads((OUTPUT_DIR / "guardrail_closure_check_v2.json").read_text(encoding="utf-8"))

    assert summary["canonical_default_pool_count"] == 90
    assert summary["verified_core_count"] == 28
    assert summary["manual_anchor_core_pending_evidence_count"] == 2
    assert summary["likely_hard_tech_pending_evidence_count"] == 60
    assert summary["adjacent_pending_evidence_count"] == 9
    assert summary["low_priority_evidence_backfill_count"] == 3
    assert summary["reject_seed_pollution_count"] == 12
    assert manifest["canonical_dashboard_default_pool"]["path"].endswith("hard_tech_review_pool_preview.csv")
    assert manifest["canonical_dashboard_default_pool"]["row_count"] == 90
    assert deprecated["legacy_workbench_core_candidates"]["status"] == "legacy_unverified_pool"
    assert "deprecated_for_default_core_use" in deprecated["legacy_workbench_core_candidates"]["flags"]
    assert guardrails["allowed_for_signal_count"] == 0
    assert guardrails["allowed_for_admission_count"] == 0
    assert guardrails["baseline_admission_changed_count"] == 0


def test_pipeline_closure_v2_default_pool_contents_and_deprecated_legacy() -> None:
    _run_generator()
    pool = pd.read_csv(DEFAULT_POOL, dtype={"stock_code": str})
    deprecated = json.loads((OUTPUT_DIR / "deprecated_artifacts.json").read_text(encoding="utf-8"))
    report = (OUTPUT_DIR / "tech_bottleneck_candidate_universe_pipeline_closure_v2_report.md").read_text(encoding="utf-8")

    pool_names = set(pool["stock_name"].astype(str))
    assert {"北方华创", "中微公司"}.issubset(pool_names)
    assert not {"佛山照明", "通宝能源", "渝农商行", "浙商银行", "建设银行", "中信银行"}.intersection(pool_names)
    assert deprecated["legacy_workbench_core_candidates"]["row_count"] == 114
    assert "old 114 pool was contaminated by unverified Seed Tier A labels" in report
    assert "v1 strict pool 28 was too conservative for manual review" in report
    assert "v2 default pool 90 removes obvious pollution but keeps hard-tech pending evidence" in report
    assert "北方华创 and 中微公司 are manual anchor core pending evidence" in report
    assert "佛山照明、通宝能源、银行股 are excluded" in report


def test_pipeline_closure_v2_is_deterministic_and_strategy_diff_clean() -> None:
    _run_generator()
    first = _hash_outputs()
    _run_generator()
    second = _hash_outputs()
    assert first == second
    diff = subprocess.run(
        ["git", "diff", "--", *FORMAL_STRATEGY_FILES],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert diff.stdout == ""
