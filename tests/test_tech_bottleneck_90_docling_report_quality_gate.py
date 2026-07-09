from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
SCRIPT = PROJECT_ROOT / "scripts/run_tech_bottleneck_90_docling_report_quality_gate.py"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_90_docling_report_quality_gate_v1"
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


def test_tech_bottleneck_90_docling_report_quality_gate_outputs() -> None:
    _run_generator()

    expected = {
        "tech_bottleneck_90_docling_report_quality_gate_summary.json",
        "tech_bottleneck_90_report_quality_gate.csv",
        "tech_bottleneck_90_thesis_support_audit.csv",
        "tech_bottleneck_90_source_mix_audit.csv",
        "tech_bottleneck_90_evidence_gap_matrix.csv",
        "tech_bottleneck_90_downgrade_or_reject_candidates.csv",
        "tech_bottleneck_90_docling_report_quality_gate_guardrails.json",
        "tech_bottleneck_90_docling_report_quality_gate_v1_report.md",
    }
    assert OUTPUT_DIR.exists()
    assert expected.issubset({path.name for path in OUTPUT_DIR.iterdir()})

    summary = json.loads((OUTPUT_DIR / "tech_bottleneck_90_docling_report_quality_gate_summary.json").read_text(encoding="utf-8"))
    guardrails = json.loads((OUTPUT_DIR / "tech_bottleneck_90_docling_report_quality_gate_guardrails.json").read_text(encoding="utf-8"))
    main = pd.read_csv(OUTPUT_DIR / "tech_bottleneck_90_report_quality_gate.csv", dtype={"stock_code": str})

    assert summary["pool_total"] == 90
    assert summary["report_ready_count"] == 90
    assert summary["report_failed_count"] == 0
    assert summary["citation_total"] == 1061
    assert summary["page_level_citation_total"] == 1061
    assert summary["used_for_signal_count"] == 0
    assert summary["used_for_admission_count"] == 0
    assert summary["baseline_admission_changed_count"] == 0
    assert summary["strategy_file_diff_clean"] is True
    assert summary["formal_strategy_files_modified"] is False
    assert summary["trading_language_hit_count"] == 0
    assert summary["execution_language_hit_count"] == 0
    assert summary["acceptance_decision"] in {
        "docling_90_quality_gate_ready",
        "conditionally_ready_with_evidence_gaps",
    }

    assert guardrails["research_only"] is True
    assert guardrails["pool_total"] == 90
    assert guardrails["all_90_reports_accounted_for"] is True
    assert guardrails["docling_report_quality_gate_generated"] is True
    assert guardrails["used_for_signal_count"] == 0
    assert guardrails["used_for_admission_count"] == 0
    assert guardrails["lookahead_violation_rows"] == 0

    assert len(main) == 90
    assert main["stock_code"].str.len().eq(6).all()
    assert main["quality_gate_decision"].notna().all()
    assert main["manual_review_entry_class"].notna().all()
    assert set(main["bottleneck_thesis_support"]).issubset({"strong", "moderate", "weak", "unsupported"})
    assert set(main["quality_gate_decision"]).issubset({"pass", "pass_with_gap", "backfill_required", "adjacent_only", "downgrade", "reject"})
    assert set(main["manual_review_entry_class"]).issubset(
        {
            "confirmed_core_ready_for_manual_review",
            "likely_core_pending_evidence",
            "adjacent_watchlist",
            "evidence_backfill_required",
            "downgrade_or_reject",
        }
    )
    assert main["research_only"].eq(True).all()
    assert main["used_for_signal"].eq(False).all()
    assert main["used_for_admission"].eq(False).all()


def test_tech_bottleneck_90_docling_report_quality_gate_audits_and_strategy_diff() -> None:
    _run_generator()

    thesis = pd.read_csv(OUTPUT_DIR / "tech_bottleneck_90_thesis_support_audit.csv", dtype={"stock_code": str})
    source_mix = pd.read_csv(OUTPUT_DIR / "tech_bottleneck_90_source_mix_audit.csv", dtype={"stock_code": str})
    gaps = pd.read_csv(OUTPUT_DIR / "tech_bottleneck_90_evidence_gap_matrix.csv", dtype={"stock_code": str})
    downgrade = pd.read_csv(OUTPUT_DIR / "tech_bottleneck_90_downgrade_or_reject_candidates.csv", dtype={"stock_code": str})

    assert len(thesis) == 90
    assert len(source_mix) == 90
    assert len(gaps) >= 90
    assert {"primary_source", "brokerage_report", "unknown_source"}.issubset(set(source_mix.columns))
    assert {"missing_primary_source", "brokerage_only_risk", "adjacent_only_risk"}.issubset(set(gaps["evidence_gap_type"]))
    assert set(downgrade.columns).issuperset({"stock_code", "stock_name", "quality_gate_decision", "manual_review_entry_class", "notes"})

    diff = subprocess.run(
        ["git", "diff", "--", *FORMAL_STRATEGY_FILES],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert diff.stdout == ""
