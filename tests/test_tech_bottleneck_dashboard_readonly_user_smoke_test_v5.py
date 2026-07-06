from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_dashboard_readonly_user_smoke_test_v5"
WRITEBACK_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_manual_review_writeback_research_only_v1"
FRONTEND_DIR = PROJECT_ROOT / "dashboard/src/features/techBottleneckWatchlistReview"
ROUTE_TEST = PROJECT_ROOT / "dashboard/tests/tech-bottleneck-route.test.tsx"
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]

FORBIDDEN_PATTERNS = [
    re.compile(
        r"\b(?:buy|sell|add|reduce|hold|entry|exit|position|target price|increase position|"
        r"reduce position|target_price|position_size|entry_signal|exit_signal)\b",
        re.I,
    ),
    re.compile(r"买入|卖出|加仓|减仓|持有|目标价|仓位建议|入场点|退出|止盈|止损|调仓|交易信号"),
    re.compile(r"提交策略|生成信号|确认买入|确认卖出|入池调整"),
]


def _has_forbidden_language(text: str) -> bool:
    return any(pattern.search(text) for pattern in FORBIDDEN_PATTERNS)


def test_smoke_v5_outputs_summary_and_sections_are_valid() -> None:
    expected = {
        "smoke_test_v5_summary.json",
        "smoke_test_v5_section_status.csv",
        "smoke_test_v5_manual_review_writeback_checks.json",
        "smoke_test_v5_financial_statement_section_checks.json",
        "smoke_test_v5_news_section_checks.json",
        "smoke_test_v5_route_nav_checks.json",
        "smoke_test_v5_data_consistency_checks.csv",
        "smoke_test_v5_guardrail_checks.json",
        "smoke_test_v5_test_results.json",
        "tech_bottleneck_dashboard_readonly_user_smoke_test_v5_report.md",
    }
    assert OUTPUT_DIR.exists()
    assert expected.issubset({path.name for path in OUTPUT_DIR.iterdir()})

    summary = json.loads((OUTPUT_DIR / "smoke_test_v5_summary.json").read_text(encoding="utf-8"))
    sections = pd.read_csv(OUTPUT_DIR / "smoke_test_v5_section_status.csv")
    assert summary["acceptance_decision"] == "dashboard_ready_with_research_only_manual_review_writeback"
    assert summary["route_available"] is True
    assert summary["nav_available"] is True
    assert summary["page_component_loadable"] is True
    assert summary["core_sections_passed"] == 8
    assert summary["financial_statement_section_status"] == "passed"
    assert summary["news_section_status"] == "passed"
    assert summary["manual_review_writeback_section_status"] == "passed"
    assert summary["sections_passed"] == 11
    assert summary["sections_partial"] == 0
    assert summary["sections_failed"] == 0
    assert len(sections) == 11
    assert set(sections["v5_status"]) == {"passed"}
    assert "Manual Review Research-Only Writeback" in set(sections["section_name"])


def test_smoke_v5_manual_review_counts_defaults_and_data_consistency_match() -> None:
    summary = json.loads((OUTPUT_DIR / "smoke_test_v5_summary.json").read_text(encoding="utf-8"))
    manual = json.loads((OUTPUT_DIR / "smoke_test_v5_manual_review_writeback_checks.json").read_text(encoding="utf-8"))
    consistency = pd.read_csv(OUTPUT_DIR / "smoke_test_v5_data_consistency_checks.csv")
    store = pd.read_csv(WRITEBACK_DIR / "manual_review_writeback_store_template.csv")

    assert summary["watchlist_count"] == 102
    assert summary["manual_review_writeback_enabled"] is True
    assert summary["manual_review_writeback_scope"] == "manual_review_only"
    assert summary["strategy_writeback_enabled"] is False
    assert summary["baseline_admission_change_enabled"] is False
    assert summary["audit_log_required"] is True
    assert summary["allowed_fields_count"] == 11
    assert summary["forbidden_fields_count"] == 37
    assert summary["review_status_default"] == "not_reviewed"
    assert summary["manual_review_conclusion_default"] == "not_reviewed"
    assert summary["financial_statement_supported_count"] == 63
    assert summary["financial_statement_missing_count"] == 39
    assert summary["news_supported_count"] == 30
    assert summary["news_partial_count"] == 1
    assert summary["news_missing_count"] == 71
    assert summary["data_mismatch_count"] == 0
    assert summary["lookahead_violation_rows"] == 0
    assert manual["save_button_label"] == "Save Research Review"
    assert manual["save_button_label_has_forbidden_language"] is False
    assert manual["forbidden_fields_rendered_as_ui_actions"] is False
    assert manual["empty_template_has_synthetic_conclusion"] is False
    assert store["review_status"].eq("not_reviewed").all()
    assert store["manual_review_conclusion"].eq("not_reviewed").all()
    assert set(consistency["status"]) == {"passed"}


def test_smoke_v5_guardrails_frontend_and_formal_strategy_are_clean() -> None:
    summary = json.loads((OUTPUT_DIR / "smoke_test_v5_summary.json").read_text(encoding="utf-8"))
    route_nav = json.loads((OUTPUT_DIR / "smoke_test_v5_route_nav_checks.json").read_text(encoding="utf-8"))
    guardrails = json.loads((OUTPUT_DIR / "smoke_test_v5_guardrail_checks.json").read_text(encoding="utf-8"))
    assert route_nav["route_path"] == "/tech-bottleneck/watchlist-review"
    assert route_nav["route_available"] is True
    assert route_nav["nav_available"] is True
    assert route_nav["nav_label"] == "科技卡脖子观察池"
    assert route_nav["page_component_loadable"] is True
    assert route_nav["manual_review_writeback_section_present"] is True
    assert guardrails["manual_review_writeback_enabled_count"] > 0
    assert guardrails["strategy_writeback_enabled_count"] == 0
    assert guardrails["baseline_admission_change_enabled_count"] == 0
    assert guardrails["forbidden_action_leakage_count"] == 0
    assert guardrails["trading_language_hit_count"] == 0
    assert guardrails["execution_language_hit_count"] == 0
    assert guardrails["used_for_signal_count"] == 0
    assert guardrails["used_for_admission_count"] == 0
    assert guardrails["baseline_admission_changed_count"] == 0
    assert guardrails["lookahead_violation_rows"] == 0
    assert guardrails["strategy_file_diff_clean"] is True
    assert guardrails["formal_strategy_files_modified"] is False
    assert guardrails["research_only"] is True
    assert guardrails["audit_log_required"] is True
    assert guardrails["readonly_ui_preserved"] is True
    assert summary["strategy_file_diff_clean"] is True

    for path in [
        FRONTEND_DIR / "TechBottleneckWatchlistReviewPage.tsx",
        FRONTEND_DIR / "techBottleneckReadonlyData.ts",
        FRONTEND_DIR / "types.ts",
        ROUTE_TEST,
    ]:
        assert not _has_forbidden_language(path.read_text(encoding="utf-8")), path
    for path in OUTPUT_DIR.rglob("*"):
        if path.is_file() and path.suffix.lower() in {".csv", ".json", ".md", ".txt"}:
            assert not _has_forbidden_language(path.read_text(encoding="utf-8", errors="ignore")), path

    diff = subprocess.run(
        ["git", "diff", "--", *FORMAL_STRATEGY_FILES],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert diff.stdout == ""
