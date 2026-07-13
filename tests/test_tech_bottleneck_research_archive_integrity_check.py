from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_research_archive_integrity_check_v1"
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]


def test_archive_integrity_outputs_exist_and_latest_tasks_are_ready() -> None:
    expected = {
        "research_archive_integrity_summary.json",
        "research_archive_artifact_manifest.csv",
        "research_archive_artifact_checksums.csv",
        "research_archive_task_dependency_graph.json",
        "research_archive_required_artifact_checks.csv",
        "research_archive_metric_consistency_checks.csv",
        "research_archive_guardrail_consistency_checks.csv",
        "research_archive_missing_or_stale_artifacts.csv",
        "research_archive_integrity_guardrails.json",
        "tech_bottleneck_research_archive_integrity_check_v1_report.md",
    }
    assert OUTPUT_DIR.exists()
    assert expected.issubset({path.name for path in OUTPUT_DIR.iterdir()})

    summary = json.loads((OUTPUT_DIR / "research_archive_integrity_summary.json").read_text(encoding="utf-8"))
    assert summary["latest_smoke_v5_ready"] is True
    assert summary["manual_review_writeback_ready"] is True
    assert summary["audit_replay_ready"] is True
    assert summary["blocking_issue_count"] == 0
    assert summary["metric_mismatch_count"] == 0
    assert summary["guardrail_mismatch_count"] == 0
    assert summary["acceptance_decision"] in {
        "research_archive_integrity_ready",
        "conditionally_ready_with_non_blocking_archive_warnings",
    }


def test_manifest_checksums_required_artifacts_and_metrics_are_valid() -> None:
    manifest = pd.read_csv(OUTPUT_DIR / "research_archive_artifact_manifest.csv")
    checksums = pd.read_csv(OUTPUT_DIR / "research_archive_artifact_checksums.csv")
    required = pd.read_csv(OUTPUT_DIR / "research_archive_required_artifact_checks.csv")
    metrics = pd.read_csv(OUTPUT_DIR / "research_archive_metric_consistency_checks.csv")
    missing = pd.read_csv(OUTPUT_DIR / "research_archive_missing_or_stale_artifacts.csv")
    graph = json.loads((OUTPUT_DIR / "research_archive_task_dependency_graph.json").read_text(encoding="utf-8"))

    assert len(manifest) > 0
    assert len(checksums) > 0
    assert checksums["sha256"].fillna("").str.len().eq(64).all()
    assert required[required["severity"].eq("blocking")]["status"].eq("passed").all()
    assert metrics["status"].eq("passed").all()
    assert not missing["severity"].eq("blocking").any()
    assert "nodes" in graph and "edges" in graph
    assert len(graph["nodes"]) >= 10
    assert len(graph["edges"]) >= 5

    expected_metrics = {
        "watchlist_count": 102,
        "consolidated_report_count": 102,
        "dashboard_report_links": 102,
        "financial_statement_supported": 63,
        "financial_statement_missing": 39,
        "financial_statement_pit_strong": 63,
        "financial_statement_pit_degraded": 0,
        "news_supported": 30,
        "news_partial": 1,
        "news_missing": 71,
        "news_pit_available_events": 189,
        "news_post_admission_events": 11,
        "news_date_missing_events": 71,
        "dashboard_v5_sections_partial": 0,
        "dashboard_v5_sections_failed": 0,
        "manual_review_allowed_fields": 11,
        "manual_review_forbidden_fields": 37,
        "audit_replay_mismatch_count": 0,
        "audit_hash_missing_count": 0,
    }
    metric_values = dict(zip(metrics["metric"], metrics["actual_value"]))
    for metric, expected_value in expected_metrics.items():
        assert str(metric_values[metric]) == str(expected_value)


def test_guardrails_and_formal_strategy_diff_are_clean() -> None:
    guardrails = json.loads((OUTPUT_DIR / "research_archive_integrity_guardrails.json").read_text(encoding="utf-8"))
    guardrail_checks = pd.read_csv(OUTPUT_DIR / "research_archive_guardrail_consistency_checks.csv")

    assert guardrails["strategy_writeback_enabled_count"] == 0
    assert guardrails["baseline_admission_change_enabled_count"] == 0
    assert guardrails["baseline_admission_changed_count"] == 0
    assert guardrails["used_for_signal_count"] == 0
    assert guardrails["used_for_admission_count"] == 0
    assert guardrails["trading_language_hit_count"] == 0
    assert guardrails["execution_language_hit_count"] == 0
    assert guardrails["forbidden_action_leakage_count"] == 0
    assert guardrails["lookahead_violation_rows"] == 0
    assert guardrails["strategy_file_diff_clean"] is True
    assert guardrails["formal_strategy_files_modified"] is False
    assert guardrails["research_only"] is True
    assert guardrail_checks["status"].eq("passed").all()

    diff = subprocess.run(
        ["git", "diff", "--", *FORMAL_STRATEGY_FILES],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert diff.stdout == ""
