from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_dashboard_readonly_user_smoke_test_v6"
PERSISTENCE_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_manual_review_writeback_persistence_adapter_v1"
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]


def test_smoke_v6_outputs_and_summary_exist() -> None:
    expected = {
        "smoke_test_v6_summary.json",
        "smoke_test_v6_section_status.csv",
        "smoke_test_v6_persistence_adapter_checks.json",
        "smoke_test_v6_manual_review_writeback_checks.json",
        "smoke_test_v6_audit_replay_checks.json",
        "smoke_test_v6_financial_statement_section_checks.json",
        "smoke_test_v6_news_section_checks.json",
        "smoke_test_v6_route_nav_checks.json",
        "smoke_test_v6_data_consistency_checks.csv",
        "smoke_test_v6_guardrail_checks.json",
        "smoke_test_v6_test_results.json",
        "tech_bottleneck_dashboard_readonly_user_smoke_test_v6_report.md",
    }
    assert OUTPUT_DIR.exists()
    assert expected.issubset({path.name for path in OUTPUT_DIR.iterdir()})

    summary = json.loads((OUTPUT_DIR / "smoke_test_v6_summary.json").read_text(encoding="utf-8"))
    assert summary["acceptance_decision"] == "dashboard_ready_with_research_only_manual_review_persistence"
    assert summary["route_available"] is True
    assert summary["nav_available"] is True
    assert summary["page_component_loadable"] is True
    assert summary["financial_statement_section_status"] == "passed"
    assert summary["news_section_status"] == "passed"
    assert summary["manual_review_writeback_section_status"] == "passed"
    assert summary["persistence_adapter_section_status"] == "passed"
    assert summary["sections_partial"] == 0
    assert summary["sections_failed"] == 0


def test_smoke_v6_persistence_adapter_checks_are_clean() -> None:
    summary = json.loads((OUTPUT_DIR / "smoke_test_v6_summary.json").read_text(encoding="utf-8"))
    checks = json.loads((OUTPUT_DIR / "smoke_test_v6_persistence_adapter_checks.json").read_text(encoding="utf-8"))
    store = pd.read_csv(PERSISTENCE_DIR / "manual_review_persistence_store.csv")
    reconstructed = pd.read_csv(PERSISTENCE_DIR / "manual_review_persistence_replay_reconstructed_store.csv")
    rejected = pd.read_csv(PERSISTENCE_DIR / "manual_review_persistence_rejected_writes.csv")

    assert summary["persistence_adapter_generated"] is True
    assert summary["storage_scope"] == "manual_review_only"
    assert summary["manual_review_writeback_enabled"] is True
    assert summary["allowed_write_count"] == 7
    assert summary["forbidden_write_attempt_count"] == 37
    assert summary["rejected_write_count"] == 37
    assert summary["rejected_write_count"] == summary["forbidden_write_attempt_count"]
    assert summary["replay_consistency_mismatch_count"] == 0
    assert summary["audit_hash_missing_count"] == 0
    assert checks["audit_log_append_only"] is True
    assert store.fillna("").astype(str).to_dict("records") == reconstructed.fillna("").astype(str).to_dict("records")
    assert not set(rejected["field_name"]).intersection(set(store.columns))


def test_smoke_v6_guardrails_route_nav_and_strategy_diff_are_clean() -> None:
    guardrails = json.loads((OUTPUT_DIR / "smoke_test_v6_guardrail_checks.json").read_text(encoding="utf-8"))
    route_nav = json.loads((OUTPUT_DIR / "smoke_test_v6_route_nav_checks.json").read_text(encoding="utf-8"))
    data_checks = pd.read_csv(OUTPUT_DIR / "smoke_test_v6_data_consistency_checks.csv")
    sections = pd.read_csv(OUTPUT_DIR / "smoke_test_v6_section_status.csv")

    assert route_nav["route_path"] == "/tech-bottleneck/watchlist-review"
    assert route_nav["route_available"] is True
    assert route_nav["nav_label"] == "科技卡脖子观察池"
    assert route_nav["nav_available"] is True
    assert route_nav["page_component_loadable"] is True
    assert set(sections["v6_status"]) == {"passed"}
    assert set(data_checks["status"]) == {"passed"}
    assert guardrails["persistence_adapter_generated"] is True
    assert guardrails["manual_review_writeback_enabled"] is True
    assert guardrails["storage_scope"] == "manual_review_only"
    assert guardrails["strategy_writeback_enabled_count"] == 0
    assert guardrails["baseline_admission_change_enabled_count"] == 0
    assert guardrails["used_for_signal_count"] == 0
    assert guardrails["used_for_admission_count"] == 0
    assert guardrails["forbidden_action_leakage_count"] == 0
    assert guardrails["trading_language_hit_count"] == 0
    assert guardrails["execution_language_hit_count"] == 0
    assert guardrails["baseline_admission_changed_count"] == 0
    assert guardrails["lookahead_violation_rows"] == 0
    assert guardrails["strategy_file_diff_clean"] is True
    assert guardrails["formal_strategy_files_modified"] is False
    assert guardrails["research_only"] is True
    assert guardrails["audit_log_required"] is True
    assert guardrails["readonly_ui_preserved"] is True

    diff = subprocess.run(
        ["git", "diff", "--", *FORMAL_STRATEGY_FILES],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert diff.stdout == ""
