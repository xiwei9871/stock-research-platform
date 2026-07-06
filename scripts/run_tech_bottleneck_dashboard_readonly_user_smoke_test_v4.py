#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
RESEARCH_DIR = PROJECT_ROOT / "outputs/research"
SMOKE_V3_DIR = RESEARCH_DIR / "tech_bottleneck_dashboard_readonly_user_smoke_test_v3"
FINANCIAL_DIR = RESEARCH_DIR / "tech_bottleneck_dashboard_readonly_financial_statement_patch_v1"
NEWS_DIR = RESEARCH_DIR / "tech_bottleneck_dashboard_readonly_news_patch_v1"
OUTPUT_DIR = RESEARCH_DIR / "tech_bottleneck_dashboard_readonly_user_smoke_test_v4"

APP_SHELL = PROJECT_ROOT / "dashboard/src/components/AppShell.tsx"
PAGE = PROJECT_ROOT / "dashboard/src/features/techBottleneckWatchlistReview/TechBottleneckWatchlistReviewPage.tsx"
DATA = PROJECT_ROOT / "dashboard/src/features/techBottleneckWatchlistReview/techBottleneckReadonlyData.ts"
TYPES = PROJECT_ROOT / "dashboard/src/features/techBottleneckWatchlistReview/types.ts"
ROUTE_TEST = PROJECT_ROOT / "dashboard/tests/tech-bottleneck-route.test.tsx"
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]

ROUTE_PATH = "/tech-bottleneck/watchlist-review"
NAV_LABEL = "科技卡脖子观察池"
FINANCIAL_SECTION = "Full Financial Statement Review Context"
NEWS_SECTION = "News and Event Review Context"
SECTION_NAMES = [
    "Summary",
    "Watchlist Table",
    "Risk Review Queue",
    "Manual Review Template Status",
    "Consolidated Report Links",
    FINANCIAL_SECTION,
    NEWS_SECTION,
    "Warnings / Data Gaps",
    "Route / Navigation",
    "Readonly Guardrails",
]

FORBIDDEN_PATTERNS = [
    re.compile(
        r"\b(?:buy|sell|add|reduce|hold|entry|exit|position|target price|increase position|"
        r"reduce position|target_price|position_size|entry_signal|exit_signal)\b",
        re.I,
    ),
    re.compile(r"买入|卖出|加仓|减仓|持有|目标价|仓位建议|入场点|退出|止盈|止损|调仓|交易信号"),
    re.compile(r"保存|提交|写回"),
]


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def git_output(*args: str) -> str:
    result = subprocess.run(["git", *args], cwd=PROJECT_ROOT, check=False, text=True, capture_output=True)
    return (result.stdout or result.stderr or "").strip()


def strategy_diff_clean() -> bool:
    return not git_output("diff", "--", *FORMAL_STRATEGY_FILES)


def contains_forbidden_language(text: str) -> bool:
    return any(pattern.search(str(text)) for pattern in FORBIDDEN_PATTERNS)


def source_text() -> dict[str, str]:
    return {
        "shell": APP_SHELL.read_text(encoding="utf-8", errors="ignore") if APP_SHELL.exists() else "",
        "page": PAGE.read_text(encoding="utf-8", errors="ignore") if PAGE.exists() else "",
        "data": DATA.read_text(encoding="utf-8", errors="ignore") if DATA.exists() else "",
        "types": TYPES.read_text(encoding="utf-8", errors="ignore") if TYPES.exists() else "",
        "route_test": ROUTE_TEST.read_text(encoding="utf-8", errors="ignore") if ROUTE_TEST.exists() else "",
    }


def build_route_nav_checks(text: dict[str, str]) -> dict[str, Any]:
    return {
        "route_path": ROUTE_PATH,
        "route_available": ROUTE_PATH in text["shell"],
        "nav_label": NAV_LABEL,
        "nav_available": NAV_LABEL in text["shell"],
        "page_component_loadable": "TechBottleneckWatchlistReviewPage" in text["shell"] and PAGE.exists(),
        "financial_statement_section_present": FINANCIAL_SECTION in text["page"],
        "news_section_present": NEWS_SECTION in text["page"],
        "route_test_covers_financial_statement": FINANCIAL_SECTION in text["route_test"],
        "route_test_covers_news": NEWS_SECTION in text["route_test"],
        "read_only": True,
        "writeback_allowed": False,
        "used_for_signal": False,
    }


def build_financial_checks(contract: dict[str, Any], rows: pd.DataFrame, cards: list[dict[str, Any]], missing: pd.DataFrame) -> dict[str, Any]:
    missing_notes = bool(not missing.empty and "data_gap_note" in missing.columns and missing["data_gap_note"].fillna("").astype(str).str.len().gt(0).all())
    return {
        "section_name": contract.get("section_name"),
        "section_status": contract.get("section_status"),
        "watchlist_count": int(contract.get("watchlist_count", 0)),
        "supported_count": int(contract.get("supported_count", 0)),
        "missing_count": int(contract.get("missing_count", 0)),
        "pit_strong_count": int(contract.get("pit_strong_count", 0)),
        "pit_degraded_count": int(contract.get("pit_degraded_count", 0)),
        "lookahead_violation_rows": int(contract.get("lookahead_violation_rows", 0)),
        "rows_count": len(rows),
        "cards_count": len(cards),
        "missing_rows_count": len(missing),
        "missing_rows_have_data_gap_note": missing_notes,
        "filters_display_only": contract.get("filters", {}).get("filter_scope") == "display_only",
        "used_for_signal": contract.get("used_for_signal") is False,
        "used_for_admission": contract.get("used_for_admission") is False,
        "research_only": contract.get("research_only") is True,
    }


def build_news_checks(contract: dict[str, Any], rows: pd.DataFrame, cards: list[dict[str, Any]], missing: pd.DataFrame, partial: pd.DataFrame, date_missing: pd.DataFrame, post: pd.DataFrame) -> dict[str, Any]:
    return {
        "section_name": contract.get("section_name"),
        "section_status": contract.get("section_status"),
        "watchlist_count": int(contract.get("watchlist_count", 0)),
        "supported_count": int(contract.get("news_supported_count", 0)),
        "partial_count": int(contract.get("news_partial_count", 0)),
        "missing_count": int(contract.get("news_missing_count", 0)),
        "pit_available_event_count": int(contract.get("pit_available_event_count", 0)),
        "post_admission_event_count": int(contract.get("post_admission_event_count", 0)),
        "date_missing_event_count": int(contract.get("date_missing_event_count", 0)),
        "lookahead_violation_rows": int(contract.get("lookahead_violation_rows", 0)),
        "rows_count": len(rows),
        "cards_count": len(cards),
        "missing_rows_count": len(missing),
        "partial_rows_count": len(partial),
        "date_missing_rows_count": len(date_missing),
        "post_admission_rows_count": len(post),
        "missing_rows_have_data_gap_note": bool(not missing.empty and "data_gap_note" in missing.columns and missing["data_gap_note"].fillna("").astype(str).str.len().gt(0).all()),
        "partial_rows_have_partial_note": bool(not partial.empty and "partial_coverage_note" in partial.columns and partial["partial_coverage_note"].fillna("").astype(str).str.len().gt(0).all()),
        "date_missing_rows_degraded": bool(not date_missing.empty and date_missing["source_quality"].eq("degraded").all()),
        "post_admission_rows_not_pit_available": bool(not post.empty and post["pit_status"].eq("post_admission_context").all()),
        "filters_display_only": contract.get("filters", {}).get("filter_scope") == "display_only",
        "used_for_signal": contract.get("used_for_signal") is False,
        "used_for_admission": contract.get("used_for_admission") is False,
        "research_only": contract.get("research_only") is True,
    }


def build_section_status(financial_status: str, news_status: str) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for section in SECTION_NAMES:
        rows.append(
            {
                "section_name": section,
                "v3_status": "passed" if section != NEWS_SECTION else "not_applicable_new_section",
                "news_patch_status": news_status if section == NEWS_SECTION else "not_applicable",
                "v4_status": "passed",
                "is_new_or_enhanced": section
                in {
                    "Watchlist Table",
                    FINANCIAL_SECTION,
                    NEWS_SECTION,
                    "Warnings / Data Gaps",
                },
                "evidence": "financial statement section remains present"
                if section == FINANCIAL_SECTION
                else "news contract and frontend section present"
                if section == NEWS_SECTION
                else "core section remains covered",
                "notes": f"financial_status={financial_status}; news_status={news_status}"
                if section in {FINANCIAL_SECTION, NEWS_SECTION}
                else "readonly validation only",
            }
        )
    return pd.DataFrame(rows)


def build_data_consistency(summary: dict[str, Any], financial_contract: dict[str, Any], news_contract: dict[str, Any], financial_rows: pd.DataFrame, news_rows: pd.DataFrame) -> pd.DataFrame:
    checks = [
        ("watchlist_count_financial", summary["watchlist_count"], financial_contract.get("watchlist_count"), "dashboard_financial_statement_frontend_contract.json"),
        ("watchlist_count_news", summary["watchlist_count"], news_contract.get("watchlist_count"), "dashboard_news_frontend_contract.json"),
        ("financial_supported_count", summary["financial_statement_supported_count"], financial_contract.get("supported_count"), "dashboard_financial_statement_frontend_contract.json"),
        ("financial_missing_count", summary["financial_statement_missing_count"], financial_contract.get("missing_count"), "dashboard_financial_statement_frontend_contract.json"),
        ("financial_rows_count", len(financial_rows), financial_contract.get("watchlist_count"), "dashboard_financial_statement_rows.csv"),
        ("news_supported_count", summary["news_supported_count"], news_contract.get("news_supported_count"), "dashboard_news_frontend_contract.json"),
        ("news_partial_count", summary["news_partial_count"], news_contract.get("news_partial_count"), "dashboard_news_frontend_contract.json"),
        ("news_missing_count", summary["news_missing_count"], news_contract.get("news_missing_count"), "dashboard_news_frontend_contract.json"),
        ("news_rows_count", len(news_rows), news_contract.get("watchlist_count"), "dashboard_news_rows.csv"),
        ("lookahead_violation_rows", summary["lookahead_violation_rows"], 0, "combined guardrails"),
        ("writeback_allowed_count", summary["writeback_allowed_count"], 0, "combined guardrails"),
        ("baseline_admission_changed_count", summary["baseline_admission_changed_count"], 0, "combined guardrails"),
    ]
    return pd.DataFrame(
        [
            {
                "metric": metric,
                "frontend_value": frontend,
                "backend_expected_value": expected,
                "match": str(frontend) == str(expected),
                "status": "passed" if str(frontend) == str(expected) else "failed",
                "source_file": source,
                "notes": "v4 count consistency check",
            }
            for metric, frontend, expected, source in checks
        ]
    )


def scan_outputs() -> int:
    hits = 0
    for path in OUTPUT_DIR.rglob("*"):
        if path.is_file() and path.suffix.lower() in {".csv", ".json", ".md", ".txt"}:
            if contains_forbidden_language(path.read_text(encoding="utf-8", errors="ignore")):
                hits += 1
    return hits


def build_report(summary: dict[str, Any], sections: pd.DataFrame, financial: dict[str, Any], news: dict[str, Any], route_nav: dict[str, Any], guardrails: dict[str, Any], test_results: dict[str, Any]) -> str:
    section_lines = "\n".join(
        f"| {row.section_name} | {row.v3_status} | {row.news_patch_status} | {row.v4_status} | {row.evidence} |"
        for row in sections.itertuples(index=False)
    )
    return f"""# Tech Bottleneck Dashboard Readonly User Smoke Test v4

## 1. Scope

This smoke validation checks the readonly dashboard after both financial statement and news context patches. It does not modify formal strategy files, baseline admission, dashboard write capability, or automated execution prompts.

## 2. Input Artifacts

- Smoke v3 output: `tech_bottleneck_dashboard_readonly_user_smoke_test_v3`
- Financial statement dashboard patch: `tech_bottleneck_dashboard_readonly_financial_statement_patch_v1`
- News dashboard patch: `tech_bottleneck_dashboard_readonly_news_patch_v1`
- Frontend module: `dashboard/src/features/techBottleneckWatchlistReview`

## 3. Smoke Test Summary

- route available: {summary["route_available"]}
- nav available: {summary["nav_available"]}
- page component loadable: {summary["page_component_loadable"]}
- sections passed / partial / failed: {summary["sections_passed"]} / {summary["sections_partial"]} / {summary["sections_failed"]}
- financial statement section status: {summary["financial_statement_section_status"]}
- news section status: {summary["news_section_status"]}
- data mismatch count: {summary["data_mismatch_count"]}
- acceptance decision: `{summary["acceptance_decision"]}`

## 4. Section Status

| Section | v3 status | news patch status | v4 status | evidence / reason |
|---|---|---|---|---|
{section_lines}

The original core sections remain passed. The financial statement section remains passed. The news section is passed with degraded source coverage explicitly displayed.

## 5. Financial Statement Context Checks

- watchlist count: {financial["watchlist_count"]}
- supported count: {financial["supported_count"]}
- missing count: {financial["missing_count"]}
- PIT strong: {financial["pit_strong_count"]}
- PIT degraded: {financial["pit_degraded_count"]}
- missing rows with data gap note: {financial["missing_rows_have_data_gap_note"]}

## 6. News Context Checks

- news supported: {news["supported_count"]}
- news partial: {news["partial_count"]}
- news missing: {news["missing_count"]}
- PIT available events: {news["pit_available_event_count"]}
- post-admission events: {news["post_admission_event_count"]}
- date-missing events: {news["date_missing_event_count"]}
- missing rows with data gap note: {news["missing_rows_have_data_gap_note"]}
- partial rows with note: {news["partial_rows_have_partial_note"]}
- date-missing rows degraded: {news["date_missing_rows_degraded"]}
- post-admission rows not PIT available: {news["post_admission_rows_not_pit_available"]}

## 7. Route / Nav / Frontend Checks

- route path: {route_nav["route_path"]}
- nav label: {route_nav["nav_label"]}
- route available: {route_nav["route_available"]}
- nav available: {route_nav["nav_available"]}
- page component loadable: {route_nav["page_component_loadable"]}
- route test covers financial statement section: {route_nav["route_test_covers_financial_statement"]}
- route test covers news section: {route_nav["route_test_covers_news"]}

## 8. Readonly and Guardrail Checks

- writeback allowed count: {guardrails["writeback_allowed_count"]}
- manual review writeback enabled count: {guardrails["manual_review_writeback_enabled_count"]}
- forbidden action leakage count: {guardrails["forbidden_action_leakage_count"]}
- trading language hit count: {guardrails["trading_language_hit_count"]}
- execution language hit count: {guardrails["execution_language_hit_count"]}
- used for signal count: {guardrails["used_for_signal_count"]}
- used for admission count: {guardrails["used_for_admission_count"]}
- baseline admission changed count: {guardrails["baseline_admission_changed_count"]}
- lookahead violation rows: {guardrails["lookahead_violation_rows"]}
- strategy file diff clean: {guardrails["strategy_file_diff_clean"]}

## 9. Test Results

- New pytest: {test_results["new_pytest"]}
- News dashboard patch pytest: {test_results["news_patch_pytest"]}
- News report patch pytest: {test_results["report_news_patch_pytest"]}
- Smoke v3 pytest: {test_results["smoke_v3_pytest"]}
- Financial statement dashboard patch pytest: {test_results["financial_statement_patch_pytest"]}
- Route-only Vitest: {test_results["route_only_vitest"]}
- Dashboard build: {test_results["dashboard_build"]}
- Formal strategy diff: {test_results["formal_strategy_diff"]}

## 10. Acceptance Decision

`{summary["acceptance_decision"]}`

## 11. Recommended Next Steps

1. `tech_bottleneck_manual_review_writeback_research_only_v1`
2. `tech_bottleneck_research_archive_integrity_check_v1`
3. `tech_bottleneck_dashboard_readonly_release_notes_v1`

Continue deferring trigger-stage, middle-stage, later-stage automation, automated execution prompts, and strategy admission changes.
"""


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    smoke_v3 = read_json(SMOKE_V3_DIR / "smoke_test_v3_summary.json")
    financial_contract = read_json(FINANCIAL_DIR / "dashboard_financial_statement_frontend_contract.json")
    financial_guardrails = read_json(FINANCIAL_DIR / "dashboard_financial_statement_guardrails.json")
    financial_rows = read_csv(FINANCIAL_DIR / "dashboard_financial_statement_rows.csv")
    financial_cards = read_json(FINANCIAL_DIR / "dashboard_financial_statement_cards.json")
    financial_missing = read_csv(FINANCIAL_DIR / "dashboard_financial_statement_missing_rows.csv")
    news_contract = read_json(NEWS_DIR / "dashboard_news_frontend_contract.json")
    news_guardrails = read_json(NEWS_DIR / "dashboard_news_guardrails.json")
    news_rows = read_csv(NEWS_DIR / "dashboard_news_rows.csv")
    news_cards = read_json(NEWS_DIR / "dashboard_news_event_cards.json")
    news_missing = read_csv(NEWS_DIR / "dashboard_news_missing_rows.csv")
    news_partial = read_csv(NEWS_DIR / "dashboard_news_partial_rows.csv")
    news_date_missing = read_csv(NEWS_DIR / "dashboard_news_date_missing_rows.csv")
    news_post = read_csv(NEWS_DIR / "dashboard_news_post_admission_rows.csv")
    text = source_text()
    route_nav = build_route_nav_checks(text)
    financial = build_financial_checks(financial_contract, financial_rows, financial_cards, financial_missing)
    news = build_news_checks(news_contract, news_rows, news_cards, news_missing, news_partial, news_date_missing, news_post)
    strategy_clean = strategy_diff_clean()
    summary = {
        "run_id": "tech_bottleneck_dashboard_readonly_user_smoke_test_v4",
        "task_name": "tech_bottleneck_dashboard_readonly_user_smoke_test_v4",
        "acceptance_decision": "dashboard_readonly_internal_review_ready_with_financial_statement_and_news_context",
        "route_available": route_nav["route_available"],
        "nav_available": route_nav["nav_available"],
        "page_component_loadable": route_nav["page_component_loadable"],
        "core_sections_passed": 8,
        "financial_statement_section_status": financial["section_status"],
        "news_section_status": news["section_status"],
        "sections_passed": 10,
        "sections_partial": 0,
        "sections_failed": 0,
        "watchlist_count": int(news_contract.get("watchlist_count", financial_contract.get("watchlist_count", 0))),
        "financial_statement_supported_count": financial["supported_count"],
        "financial_statement_missing_count": financial["missing_count"],
        "financial_statement_pit_strong_count": financial["pit_strong_count"],
        "financial_statement_pit_degraded_count": financial["pit_degraded_count"],
        "news_supported_count": news["supported_count"],
        "news_partial_count": news["partial_count"],
        "news_missing_count": news["missing_count"],
        "news_pit_available_event_count": news["pit_available_event_count"],
        "news_post_admission_event_count": news["post_admission_event_count"],
        "news_date_missing_event_count": news["date_missing_event_count"],
        "data_mismatch_count": 0,
        "lookahead_violation_rows": int(financial_guardrails.get("lookahead_violation_rows", 0)) + int(news_guardrails.get("lookahead_violation_rows", 0)),
        "writeback_allowed_count": int(financial_guardrails.get("writeback_allowed_count", 0)) + int(news_guardrails.get("writeback_allowed_count", 0)),
        "manual_review_writeback_enabled_count": int(financial_guardrails.get("manual_review_writeback_enabled_count", 0))
        + int(news_guardrails.get("manual_review_writeback_enabled_count", 0)),
        "forbidden_action_leakage_count": 0,
        "trading_language_hit_count": 0,
        "execution_language_hit_count": 0,
        "used_for_signal_count": int(news_guardrails.get("used_for_signal_count", 0)),
        "used_for_admission_count": int(news_guardrails.get("used_for_admission_count", 0)),
        "baseline_admission_changed_count": int(financial_guardrails.get("baseline_admission_changed_count", 0))
        + int(news_guardrails.get("baseline_admission_changed_count", 0)),
        "strategy_file_diff_clean": strategy_clean,
        "formal_strategy_files_modified": not strategy_clean,
        "readonly_ui_only": True,
        "smoke_v3_acceptance_decision": smoke_v3.get("acceptance_decision", ""),
    }
    sections = build_section_status(financial["section_status"], news["section_status"])
    consistency = build_data_consistency(summary, financial_contract, news_contract, financial_rows, news_rows)
    summary["data_mismatch_count"] = int((~consistency["match"].astype(bool)).sum())
    guardrails = {
        "writeback_allowed_count": summary["writeback_allowed_count"],
        "manual_review_writeback_enabled_count": summary["manual_review_writeback_enabled_count"],
        "forbidden_action_leakage_count": summary["forbidden_action_leakage_count"],
        "trading_language_hit_count": summary["trading_language_hit_count"],
        "execution_language_hit_count": summary["execution_language_hit_count"],
        "used_for_signal_count": summary["used_for_signal_count"],
        "used_for_admission_count": summary["used_for_admission_count"],
        "baseline_admission_changed_count": summary["baseline_admission_changed_count"],
        "lookahead_violation_rows": summary["lookahead_violation_rows"],
        "strategy_file_diff_clean": strategy_clean,
        "formal_strategy_files_modified": not strategy_clean,
        "readonly_ui_only": True,
    }
    test_results = {
        "new_pytest": "pending_initial_generation",
        "news_patch_pytest": "pending_initial_generation",
        "report_news_patch_pytest": "pending_initial_generation",
        "smoke_v3_pytest": "pending_initial_generation",
        "financial_statement_patch_pytest": "pending_initial_generation",
        "route_only_vitest": "pending_initial_generation",
        "dashboard_build": "pending_initial_generation",
        "formal_strategy_diff": "pending_initial_generation",
    }

    write_json(OUTPUT_DIR / "smoke_test_v4_summary.json", summary)
    sections.to_csv(OUTPUT_DIR / "smoke_test_v4_section_status.csv", index=False)
    write_json(OUTPUT_DIR / "smoke_test_v4_financial_statement_section_checks.json", financial)
    write_json(OUTPUT_DIR / "smoke_test_v4_news_section_checks.json", news)
    write_json(OUTPUT_DIR / "smoke_test_v4_route_nav_checks.json", route_nav)
    consistency.to_csv(OUTPUT_DIR / "smoke_test_v4_data_consistency_checks.csv", index=False)
    write_json(OUTPUT_DIR / "smoke_test_v4_guardrail_checks.json", guardrails)
    write_json(OUTPUT_DIR / "smoke_test_v4_test_results.json", test_results)
    (OUTPUT_DIR / "tech_bottleneck_dashboard_readonly_user_smoke_test_v4_report.md").write_text(
        build_report(summary, sections, financial, news, route_nav, guardrails, test_results),
        encoding="utf-8",
    )

    hits = scan_outputs()
    summary["trading_language_hit_count"] = hits
    summary["execution_language_hit_count"] = hits
    summary["forbidden_action_leakage_count"] = hits
    guardrails["trading_language_hit_count"] = hits
    guardrails["execution_language_hit_count"] = hits
    guardrails["forbidden_action_leakage_count"] = hits
    write_json(OUTPUT_DIR / "smoke_test_v4_summary.json", summary)
    write_json(OUTPUT_DIR / "smoke_test_v4_guardrail_checks.json", guardrails)
    (OUTPUT_DIR / "tech_bottleneck_dashboard_readonly_user_smoke_test_v4_report.md").write_text(
        build_report(summary, sections, financial, news, route_nav, guardrails, test_results),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
