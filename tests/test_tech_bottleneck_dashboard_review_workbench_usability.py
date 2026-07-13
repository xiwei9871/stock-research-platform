from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_dashboard_review_workbench_usability_v1"
PAGE = PROJECT_ROOT / "dashboard/src/features/techBottleneckWatchlistReview/TechBottleneckWatchlistReviewPage.tsx"
ROUTE_TEST = PROJECT_ROOT / "dashboard/tests/tech-bottleneck-route.test.tsx"
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]


def test_review_workbench_usability_outputs_exist_and_contract_is_business_facing() -> None:
    expected = {
        "review_workbench_usability_summary.json",
        "review_workbench_usability_frontend_contract.json",
        "review_workbench_usability_section_checks.csv",
        "review_workbench_usability_guardrails.json",
        "tech_bottleneck_dashboard_review_workbench_usability_v1_report.md",
    }
    assert OUTPUT_DIR.exists()
    assert expected.issubset({path.name for path in OUTPUT_DIR.iterdir()})

    summary = json.loads((OUTPUT_DIR / "review_workbench_usability_summary.json").read_text(encoding="utf-8"))
    contract = json.loads((OUTPUT_DIR / "review_workbench_usability_frontend_contract.json").read_text(encoding="utf-8"))
    sections = pd.read_csv(OUTPUT_DIR / "review_workbench_usability_section_checks.csv")

    assert summary["acceptance_decision"] == "dashboard_review_workbench_usability_ready"
    assert summary["route_available"] is True
    assert summary["nav_available"] is True
    assert summary["page_component_loadable"] is True
    assert summary["default_first_screen_not_technical_report"] is True
    assert summary["page_sections_default_visible"] is False
    assert summary["summary_cards_count"] == 5
    assert summary["review_queue_tabs_count"] == 6
    assert summary["watchlist_default_columns_count"] <= 10
    assert summary["detail_panel_present"] is True
    assert summary["manual_review_section_present"] is True
    assert summary["manual_review_save_label"] == "保存研究复盘"
    assert summary["financial_statement_section_status"] == "passed"
    assert summary["news_section_status"] == "passed"
    assert summary["persistence_adapter_section_status"] == "passed"
    assert contract["page_title"] == "科技卡脖子观察池"
    assert contract["technical_sections_default_hidden"] is True
    assert len(contract["summary_cards"]) == 5
    assert len(contract["review_queue_tabs"]) == 6
    assert len(contract["watchlist_default_columns"]) <= 10
    assert "Manual Review 研究复盘" in contract["detail_panel_sections"]
    assert set(sections["status"]) == {"passed"}


def test_review_workbench_frontend_source_uses_workbench_language_not_technical_first_screen() -> None:
    page = PAGE.read_text(encoding="utf-8")
    route_test = ROUTE_TEST.read_text(encoding="utf-8")

    assert "科技卡脖子观察池" in page
    assert "内部研究复盘工作台" in page
    assert "观察池标的" in page
    assert "待复盘" in page
    assert "高优先复核" in page
    assert "财报缺口" in page
    assert "新闻缺口" in page
    assert "Review Queue Tabs" in page
    assert "查看详情" in page
    assert "Manual Review 研究复盘" in page
    assert "保存研究复盘" in page
    assert "Page Sections" not in page
    assert "Fields:" not in page
    assert "Allowed interactions:" not in page
    assert "Writeback allowed" not in page
    assert "Used for automated execution" not in page
    assert "科技卡脖子观察池" in route_test
    assert "保存研究复盘" in route_test


def test_review_workbench_guardrails_and_strategy_diff_are_clean() -> None:
    guardrails = json.loads((OUTPUT_DIR / "review_workbench_usability_guardrails.json").read_text(encoding="utf-8"))

    assert guardrails["workbench_usability_generated"] is True
    assert guardrails["route_available"] is True
    assert guardrails["nav_available"] is True
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

    diff = subprocess.run(
        ["git", "diff", "--", *FORMAL_STRATEGY_FILES],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert diff.stdout == ""
