from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_candidate_universe_pipeline_closure_v1"
SCRIPT = PROJECT_ROOT / "scripts/run_tech_bottleneck_candidate_universe_pipeline_closure.py"
CANONICAL_CORE = PROJECT_ROOT / "outputs/research/tech_bottleneck_candidate_universe_workbench_patch_v1/workbench_core_candidates.csv"
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run_generator() -> tuple[str, str]:
    before = _sha(CANONICAL_CORE)
    result = subprocess.run(
        [str(PROJECT_ROOT / ".venv/bin/python"), str(SCRIPT)],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    after = _sha(CANONICAL_CORE)
    return before, after


def _hash_outputs() -> dict[str, str]:
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(OUTPUT_DIR.iterdir())
        if path.is_file()
    }


def test_pipeline_closure_outputs_and_canonical_artifacts() -> None:
    before, after = _run_generator()
    assert before == after
    expected_files = {
        "pipeline_closure_summary.json",
        "canonical_artifact_manifest.json",
        "candidate_universe_readiness_matrix.csv",
        "guardrail_closure_check.json",
        "next_step_recommendations.md",
        "tech_bottleneck_candidate_universe_pipeline_closure_v1_report.md",
    }
    assert OUTPUT_DIR.exists()
    assert expected_files.issubset({path.name for path in OUTPUT_DIR.iterdir()})

    summary = json.loads((OUTPUT_DIR / "pipeline_closure_summary.json").read_text(encoding="utf-8"))
    manifest = json.loads((OUTPUT_DIR / "canonical_artifact_manifest.json").read_text(encoding="utf-8"))
    guardrails = json.loads((OUTPUT_DIR / "guardrail_closure_check.json").read_text(encoding="utf-8"))
    assert Path(PROJECT_ROOT / manifest["canonical_research_workbench_core_pool"]["path"]).exists()
    assert summary["canonical_research_workbench_core_pool_ready"] is True
    assert summary["canonical_core_pool_count"] == 114
    assert summary["discovered_total"] == 3252
    assert summary["qualified_total"] == 1128
    assert summary["original_clean_subset_count"] == 126
    assert summary["manual_approval_packet_total"] == 142
    assert summary["adjacent_watchlist_count"] == 14
    assert summary["evidence_backfill_queue_count"] == 11
    assert summary["rejected_downgrade_queue_count"] == 3
    assert guardrails["allowed_for_signal_count"] == 0
    assert guardrails["allowed_for_admission_count"] == 0
    assert guardrails["baseline_admission_changed_count"] == 0
    assert guardrails["production_modifications"] is False
    assert guardrails["dashboard_or_workbench_integration_modified"] is False


def test_pipeline_closure_readiness_matrix_and_report_findings() -> None:
    _run_generator()
    matrix = pd.read_csv(OUTPUT_DIR / "candidate_universe_readiness_matrix.csv")
    report = (OUTPUT_DIR / "tech_bottleneck_candidate_universe_pipeline_closure_v1_report.md").read_text(encoding="utf-8")
    assert set(matrix["artifact_role"]) >= {
        "canonical_core_pool",
        "adjacent_watchlist",
        "evidence_backfill_queue",
        "rejected_downgrade_queue",
    }
    assert int(matrix.loc[matrix["artifact_role"].eq("canonical_core_pool"), "row_count"].iloc[0]) == 114
    assert "Tier A pass was pass-by-construction" in report
    assert "Tier B high_quality=0 was threshold/data-gap driven" in report
    assert "Lowering threshold alone does not solve Tier B" in report
    assert "京泉华 and 浙江力诺 were verified rescue candidates" in report
    assert "道恩股份 was not proposed" in report
    assert "神农集团 was classified as seed pollution/reject" in report
    assert "Dashboard/workbench integration is still pending" in report


def test_pipeline_closure_is_deterministic_and_strategy_diff_clean() -> None:
    before, after = _run_generator()
    first = _hash_outputs()
    before2, after2 = _run_generator()
    second = _hash_outputs()
    assert before == after == before2 == after2
    assert first == second
    diff = subprocess.run(
        ["git", "diff", "--", *FORMAL_STRATEGY_FILES],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert diff.stdout == ""
