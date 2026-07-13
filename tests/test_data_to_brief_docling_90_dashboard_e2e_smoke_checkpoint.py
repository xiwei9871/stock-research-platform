from __future__ import annotations

import json
import subprocess
from pathlib import Path


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
SCRIPT = PROJECT_ROOT / "scripts/run_data_to_brief_docling_90_dashboard_e2e_smoke_checkpoint.py"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/data_to_brief_docling_90_dashboard_e2e_smoke_and_release_checkpoint_v1"
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


def test_docling_90_dashboard_release_checkpoint_outputs() -> None:
    _run_generator()

    expected = {
        "api_smoke_audit.json",
        "dashboard_e2e_smoke_audit.json",
        "research_only_boundary_audit.json",
        "release_checkpoint_summary.md",
    }
    assert expected.issubset({path.name for path in OUTPUT_DIR.iterdir()})

    api = json.loads((OUTPUT_DIR / "api_smoke_audit.json").read_text(encoding="utf-8"))
    dashboard = json.loads((OUTPUT_DIR / "dashboard_e2e_smoke_audit.json").read_text(encoding="utf-8"))
    boundary = json.loads((OUTPUT_DIR / "research_only_boundary_audit.json").read_text(encoding="utf-8"))
    summary = (OUTPUT_DIR / "release_checkpoint_summary.md").read_text(encoding="utf-8")

    assert api["api_status_code"] == 200
    assert api["stock_count"] == 90
    assert api["citation_claim_count"] == 1061
    assert api["page_level_citation_count"] == 1061
    assert api["source_level_citation_count"] == 0
    assert api["missing_required_field_count"] == 0
    assert dashboard["frontend_route"] == "/research/data-to-brief/docling-90"
    assert dashboard["dashboard_payload_rows"] == 90
    assert dashboard["summary_counts_match_payload"] is True
    assert dashboard["filter_controls_declared"] is True
    assert dashboard["expandable_detail_declared"] is True
    assert boundary["allowed_for_signal_count"] == 0
    assert boundary["allowed_for_admission_count"] == 0
    assert boundary["forbidden_control_hit_count"] == 0
    assert boundary["recommendation_language_hit_count"] == 0
    assert "acceptance_decision: ready_for_read_only_release_checkpoint" in summary


def test_docling_90_dashboard_release_checkpoint_strategy_diff() -> None:
    _run_generator()

    diff = subprocess.run(
        ["git", "diff", "--", *FORMAL_STRATEGY_FILES],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert diff.stdout == ""
