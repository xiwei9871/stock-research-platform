from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_dashboard_readonly_user_smoke_test_v7"
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]


def test_smoke_v7_outputs_exist_and_summary_is_ready() -> None:
    expected = {
        "smoke_test_v7_summary.json",
        "smoke_test_v7_usability_checks.json",
        "smoke_test_v7_section_status.csv",
        "smoke_test_v7_route_nav_checks.json",
        "smoke_test_v7_guardrail_checks.json",
        "smoke_test_v7_test_results.json",
        "tech_bottleneck_dashboard_readonly_user_smoke_test_v7_report.md",
    }
    assert OUTPUT_DIR.exists()
    assert expected.issubset({path.name for path in OUTPUT_DIR.iterdir()})

    summary = json.loads((OUTPUT_DIR / "smoke_test_v7_summary.json").read_text(encoding="utf-8"))
    assert summary["acceptance_decision"] == "dashboard_review_workbench_user_smoke_ready"
    assert summary["route_available"] is True
    assert summary["nav_available"] is True
    assert summary["page_component_loadable"] is True
    assert summary["page_title"] == "科技卡脖子观察池"
    assert summary["subtitle_research_only"] is True
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
    assert summary["data_mismatch_count"] == 0


def test_smoke_v7_usability_checks_match_workbench_requirements() -> None:
    checks = json.loads((OUTPUT_DIR / "smoke_test_v7_usability_checks.json").read_text(encoding="utf-8"))
    sections = pd.read_csv(OUTPUT_DIR / "smoke_test_v7_section_status.csv")
    route_nav = json.loads((OUTPUT_DIR / "smoke_test_v7_route_nav_checks.json").read_text(encoding="utf-8"))

    assert checks["summary_cards"] == {
        "观察池标的": 102,
        "待复盘": 102,
        "高优先复核": 64,
        "财报缺口": 39,
        "新闻缺口": 71,
    }
    assert checks["review_queue_tabs"] == ["全部", "未复盘", "高优先复核", "财报缺口", "新闻缺口", "风险复核"]
    assert checks["watchlist_default_columns"] == [
        "股票代码",
        "股票名称",
        "复核优先级",
        "财报状态",
        "新闻状态",
        "风险提示",
        "复盘状态",
        "报告链接",
        "操作",
    ]
    assert checks["forbidden_ui_phrase_count"] == 0
    assert checks["system_guardrails_default_collapsed_or_weak"] is True
    assert route_nav["route_path"] == "/tech-bottleneck/watchlist-review"
    assert route_nav["nav_label"] == "科技卡脖子观察池"
    assert route_nav["route_available"] is True
    assert route_nav["nav_available"] is True
    assert route_nav["page_component_loadable"] is True
    assert set(sections["v7_status"]) == {"passed"}


def test_smoke_v7_guardrails_and_formal_strategy_diff_are_clean() -> None:
    guardrails = json.loads((OUTPUT_DIR / "smoke_test_v7_guardrail_checks.json").read_text(encoding="utf-8"))
    summary = json.loads((OUTPUT_DIR / "smoke_test_v7_summary.json").read_text(encoding="utf-8"))

    for payload in (guardrails, summary):
        assert payload["lookahead_violation_rows"] == 0
        assert payload["strategy_writeback_enabled_count"] == 0
        assert payload["baseline_admission_change_enabled_count"] == 0
        assert payload["used_for_signal_count"] == 0
        assert payload["used_for_admission_count"] == 0
        assert payload["forbidden_action_leakage_count"] == 0
        assert payload["trading_language_hit_count"] == 0
        assert payload["execution_language_hit_count"] == 0
        assert payload["baseline_admission_changed_count"] == 0
        assert payload["strategy_file_diff_clean"] is True
        assert payload["formal_strategy_files_modified"] is False
        assert payload["research_only"] is True

    diff = subprocess.run(
        ["git", "diff", "--", *FORMAL_STRATEGY_FILES],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert diff.stdout == ""
