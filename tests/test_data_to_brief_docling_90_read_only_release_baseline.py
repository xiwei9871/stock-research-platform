from __future__ import annotations

import csv
import json
import subprocess
from pathlib import Path


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
SCRIPT = PROJECT_ROOT / "scripts/run_data_to_brief_docling_90_read_only_release_baseline.py"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/data_to_brief_docling_90_read_only_release_baseline_v1"
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


def test_docling_90_read_only_release_baseline_outputs() -> None:
    _run_generator()

    expected = {
        "release_baseline_summary.md",
        "operator_runbook.md",
        "artifact_index.csv",
        "final_validation_audit.json",
        "suggested_tag.txt",
    }
    assert expected.issubset({path.name for path in OUTPUT_DIR.iterdir()})

    validation = json.loads((OUTPUT_DIR / "final_validation_audit.json").read_text(encoding="utf-8"))
    summary = (OUTPUT_DIR / "release_baseline_summary.md").read_text(encoding="utf-8")
    runbook = (OUTPUT_DIR / "operator_runbook.md").read_text(encoding="utf-8")
    tag = (OUTPUT_DIR / "suggested_tag.txt").read_text(encoding="utf-8").strip()

    assert validation["acceptance_decision"] == "ready_for_internal_read_only_baseline_tag"
    assert validation["strategy_file_diff_clean"] is True
    assert validation["allowed_for_signal"] is False
    assert validation["allowed_for_admission"] is False
    assert validation["production_update"] is False
    assert validation["tag_created"] is False
    assert validation["stock_count"] == 90
    assert validation["citation_claim_count"] == 1061
    assert validation["page_level_citation_count"] == 1061
    assert validation["source_level_citation_count"] == 0

    assert "90/90 local PDF coverage" in summary
    assert "ready_for_internal_read_only_baseline_tag" in summary
    assert "No git tag was created" in summary
    assert "rerunning PDF acquisition" in runbook
    assert "rerunning full cold parse batch" in runbook
    assert "using cached parser artifacts" in runbook
    assert tag == "v0.2-data-to-brief-docling-90-readonly-baseline"


def test_docling_90_read_only_release_baseline_artifact_index_and_strategy_diff() -> None:
    _run_generator()

    with (OUTPUT_DIR / "artifact_index.csv").open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    artifact_groups = {row["artifact_group"] for row in rows}
    assert {
        "pdf_acquisition",
        "full_cold_parse_batch",
        "dashboard_review_integration",
        "e2e_smoke_release_checkpoint",
    }.issubset(artifact_groups)
    assert all(row["research_only"] == "true" for row in rows)
    assert all(row["allowed_for_signal"] == "false" for row in rows)
    assert all(row["allowed_for_admission"] == "false" for row in rows)

    diff = subprocess.run(
        ["git", "diff", "--", *FORMAL_STRATEGY_FILES],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert diff.stdout == ""
