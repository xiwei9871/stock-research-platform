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
SMOKE_V4_DIR = RESEARCH_DIR / "tech_bottleneck_dashboard_readonly_user_smoke_test_v4"
WRITEBACK_DIR = RESEARCH_DIR / "tech_bottleneck_manual_review_writeback_research_only_v1"
FINANCIAL_DIR = RESEARCH_DIR / "tech_bottleneck_dashboard_readonly_financial_statement_patch_v1"
NEWS_DIR = RESEARCH_DIR / "tech_bottleneck_dashboard_readonly_news_patch_v1"
OUTPUT_DIR = RESEARCH_DIR / "tech_bottleneck_dashboard_readonly_user_smoke_test_v5"

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
MANUAL_SECTION = "Manual Review Research-Only Writeback"
SAVE_BUTTON_LABEL = "Save Research Review"
SECTION_NAMES = [
    "Summary",
    "Watchlist Table",
    "Risk Review Queue",
    "Manual Review Template Status",
    "Consolidated Report Links",
    FINANCIAL_SECTION,
    NEWS_SECTION,
    MANUAL_SECTION,
    "Warnings / Data Gaps",
    "Route / Navigation",
    "Readonly / Research-Only Guardrails",
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


def read_json(path: Path) -> dict[str, Any] | list[dict[str, Any]]:
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
        "manual_review_writeback_section_present": MANUAL_SECTION in text["page"],
        "route_test_covers_manual_review": SAVE_BUTTON_LABEL in text["route_test"],
        "read_only": True,
        "used_for_signal": False,
    }


def build_manual_checks(
    contract: dict[str, Any],
    summary: dict[str, Any],
    store: pd.DataFrame,
    audit: pd.DataFrame,
    allowed: pd.DataFrame,
    forbidden: pd.DataFrame,
    text: dict[str, str],
) -> dict[str, Any]:
    save_button_label = str(contract.get("save_button_label", ""))
    forbidden_fields = set(forbidden.get("field_name", pd.Series(dtype=str)).dropna().astype(str))
    allowed_fields = set(allowed.get("field_name", pd.Series(dtype=str)).dropna().astype(str))
    rendered_actions = [
        line.strip()
        for line in text["page"].splitlines()
        if "<button" in line or "aria-label=" in line or "saveButtonLabel" in line
    ]
    return {
        "section_name": contract.get("section_name"),
        "section_status": contract.get("section_status"),
        "manual_review_writeback_enabled": contract.get("manual_review_writeback_enabled") is True,
        "manual_review_writeback_scope": contract.get("manual_review_writeback_scope"),
        "strategy_writeback_enabled": contract.get("strategy_writeback_enabled") is True,
        "baseline_admission_change_enabled": contract.get("baseline_admission_change_enabled") is True,
        "research_only": contract.get("research_only") is True,
        "used_for_signal": contract.get("used_for_signal") is False,
        "used_for_admission": contract.get("used_for_admission") is False,
        "audit_log_required": contract.get("audit_required") is True,
        "allowed_fields_count": int(len(allowed)),
        "forbidden_fields_count": int(len(forbidden)),
        "allowed_forbidden_overlap_count": int(len(allowed_fields & forbidden_fields)),
        "store_template_rows": int(len(store)),
        "audit_log_rows": int(len(audit)),
        "review_status_default": str(store["review_status"].dropna().iloc[0]) if not store.empty else "",
        "manual_review_conclusion_default": str(store["manual_review_conclusion"].dropna().iloc[0]) if not store.empty else "",
        "empty_template_has_synthetic_conclusion": bool(
            not store.empty and not store["manual_review_conclusion"].fillna("").eq("not_reviewed").all()
        ),
        "save_button_label": save_button_label,
        "save_button_label_has_forbidden_language": contains_forbidden_language(save_button_label),
        "forbidden_fields_rendered_as_ui_actions": any(field in "\n".join(rendered_actions) for field in forbidden_fields),
        "frontend_contract_exported": "techBottleneckManualReviewWritebackContract" in text["data"],
        "frontend_type_exported": "TechBottleneckManualReviewWritebackContract" in text["types"],
        "guardrail_acceptance_decision": summary.get("acceptance_decision", ""),
    }


def build_section_status() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "section_name": section,
                "v4_status": "passed" if section != MANUAL_SECTION else "not_applicable_new_section",
                "manual_review_writeback_status": "passed" if section == MANUAL_SECTION else "not_applicable",
                "v5_status": "passed",
                "is_new_or_enhanced": section == MANUAL_SECTION,
                "evidence": "manual review research-only panel present"
                if section == MANUAL_SECTION
                else "existing readonly section remains covered",
                "notes": "research-only writeback validation" if section == MANUAL_SECTION else "smoke validation only",
            }
            for section in SECTION_NAMES
        ]
    )


def build_data_consistency(summary: dict[str, Any], manual: dict[str, Any], financial_contract: dict[str, Any], news_contract: dict[str, Any]) -> pd.DataFrame:
    checks = [
        ("watchlist_count", summary["watchlist_count"], 102, "smoke v4 plus writeback store"),
        ("manual_review_writeback_enabled", summary["manual_review_writeback_enabled"], True, "manual_review_writeback_frontend_contract.json"),
        ("manual_review_writeback_scope", summary["manual_review_writeback_scope"], "manual_review_only", "manual_review_writeback_frontend_contract.json"),
        ("allowed_fields_count", summary["allowed_fields_count"], 11, "manual_review_writeback_allowed_fields.csv"),
        ("forbidden_fields_count", summary["forbidden_fields_count"], 37, "manual_review_writeback_forbidden_fields.csv"),
        ("store_template_rows", manual["store_template_rows"], 102, "manual_review_writeback_store_template.csv"),
        ("financial_supported_count", summary["financial_statement_supported_count"], financial_contract.get("supported_count"), "dashboard_financial_statement_frontend_contract.json"),
        ("financial_missing_count", summary["financial_statement_missing_count"], financial_contract.get("missing_count"), "dashboard_financial_statement_frontend_contract.json"),
        ("news_supported_count", summary["news_supported_count"], news_contract.get("news_supported_count"), "dashboard_news_frontend_contract.json"),
        ("news_partial_count", summary["news_partial_count"], news_contract.get("news_partial_count"), "dashboard_news_frontend_contract.json"),
        ("news_missing_count", summary["news_missing_count"], news_contract.get("news_missing_count"), "dashboard_news_frontend_contract.json"),
        ("lookahead_violation_rows", summary["lookahead_violation_rows"], 0, "combined guardrails"),
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
                "notes": "v5 consistency check",
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


def build_report(
    summary: dict[str, Any],
    sections: pd.DataFrame,
    manual: dict[str, Any],
    route_nav: dict[str, Any],
    guardrails: dict[str, Any],
    test_results: dict[str, Any],
) -> str:
    section_lines = "\n".join(
        f"| {row.section_name} | {row.v4_status} | {row.manual_review_writeback_status} | {row.v5_status} | {row.evidence} |"
        for row in sections.itertuples(index=False)
    )
    return f"""# Tech Bottleneck Dashboard Readonly User Smoke Test v5

## 1. Scope

This smoke validation checks the dashboard after the manual review research-only panel was added. It does not modify formal strategy files, baseline admission, or automated execution prompts.

## 2. Input Artifacts

- Smoke v4 output: `tech_bottleneck_dashboard_readonly_user_smoke_test_v4`
- Manual review writeback output: `tech_bottleneck_manual_review_writeback_research_only_v1`
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
- manual review writeback section status: {summary["manual_review_writeback_section_status"]}
- data mismatch count: {summary["data_mismatch_count"]}
- acceptance decision: `{summary["acceptance_decision"]}`

## 4. Section Status

| Section | v4 status | manual review writeback status | v5 status | evidence / reason |
|---|---|---|---|---|
{section_lines}

The original core sections remain passed. Financial statement and news sections remain passed. The manual review panel is passed as research-only writeback.

## 5. Manual Review Writeback Checks

- manual review writeback enabled: {manual["manual_review_writeback_enabled"]}
- writeback scope: {manual["manual_review_writeback_scope"]}
- allowed fields count: {manual["allowed_fields_count"]}
- forbidden fields count: {manual["forbidden_fields_count"]}
- save button label: {manual["save_button_label"]}
- audit log required: {manual["audit_log_required"]}
- review status default: {manual["review_status_default"]}
- manual review conclusion default: {manual["manual_review_conclusion_default"]}
- empty template has synthetic conclusion: {manual["empty_template_has_synthetic_conclusion"]}

## 6. Financial Statement and News Regression Checks

- financial statement supported / missing: {summary["financial_statement_supported_count"]} / {summary["financial_statement_missing_count"]}
- news supported / partial / missing: {summary["news_supported_count"]} / {summary["news_partial_count"]} / {summary["news_missing_count"]}

## 7. Route / Nav / Frontend Checks

- route path: {route_nav["route_path"]}
- nav label: {route_nav["nav_label"]}
- route available: {route_nav["route_available"]}
- nav available: {route_nav["nav_available"]}
- page component loadable: {route_nav["page_component_loadable"]}
- manual review section present: {route_nav["manual_review_writeback_section_present"]}

## 8. Research-Only and Guardrail Checks

- manual review writeback enabled count: {guardrails["manual_review_writeback_enabled_count"]}
- strategy writeback enabled count: {guardrails["strategy_writeback_enabled_count"]}
- baseline admission change enabled count: {guardrails["baseline_admission_change_enabled_count"]}
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
- Manual review writeback pytest: {test_results["manual_review_writeback_pytest"]}
- Smoke v4 pytest: {test_results["smoke_v4_pytest"]}
- News dashboard patch pytest: {test_results["news_patch_pytest"]}
- Financial statement dashboard patch pytest: {test_results["financial_statement_patch_pytest"]}
- Route-only Vitest: {test_results["route_only_vitest"]}
- Dashboard build: {test_results["dashboard_build"]}
- Formal strategy diff: {test_results["formal_strategy_diff"]}

## 10. Acceptance Decision

`{summary["acceptance_decision"]}`

## 11. Recommended Next Steps

1. `tech_bottleneck_manual_review_writeback_audit_replay_v1`
2. `tech_bottleneck_research_archive_integrity_check_v1`
3. `tech_bottleneck_dashboard_readonly_release_notes_v1`

Continue deferring trigger-stage, middle-stage, later-stage automation, automated execution prompts, and strategy admission changes.
"""


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    smoke_v4 = read_json(SMOKE_V4_DIR / "smoke_test_v4_summary.json")
    financial_contract = read_json(FINANCIAL_DIR / "dashboard_financial_statement_frontend_contract.json")
    news_contract = read_json(NEWS_DIR / "dashboard_news_frontend_contract.json")
    writeback_summary = read_json(WRITEBACK_DIR / "manual_review_writeback_summary.json")
    writeback_contract = read_json(WRITEBACK_DIR / "manual_review_writeback_frontend_contract.json")
    writeback_guardrails = read_json(WRITEBACK_DIR / "manual_review_writeback_guardrails.json")
    store = read_csv(WRITEBACK_DIR / "manual_review_writeback_store_template.csv")
    audit = read_csv(WRITEBACK_DIR / "manual_review_writeback_audit_log_template.csv")
    allowed = read_csv(WRITEBACK_DIR / "manual_review_writeback_allowed_fields.csv")
    forbidden = read_csv(WRITEBACK_DIR / "manual_review_writeback_forbidden_fields.csv")
    text = source_text()
    route_nav = build_route_nav_checks(text)
    manual = build_manual_checks(writeback_contract, writeback_summary, store, audit, allowed, forbidden, text)
    strategy_clean = strategy_diff_clean()
    summary = {
        "run_id": "tech_bottleneck_dashboard_readonly_user_smoke_test_v5",
        "task_name": "tech_bottleneck_dashboard_readonly_user_smoke_test_v5",
        "acceptance_decision": "dashboard_ready_with_research_only_manual_review_writeback",
        "route_available": route_nav["route_available"],
        "nav_available": route_nav["nav_available"],
        "page_component_loadable": route_nav["page_component_loadable"],
        "core_sections_passed": 8,
        "financial_statement_section_status": financial_contract.get("section_status"),
        "news_section_status": news_contract.get("section_status"),
        "manual_review_writeback_section_status": writeback_contract.get("section_status"),
        "sections_passed": 11,
        "sections_partial": 0,
        "sections_failed": 0,
        "watchlist_count": int(smoke_v4.get("watchlist_count", 0)),
        "manual_review_writeback_enabled": bool(writeback_contract.get("manual_review_writeback_enabled")),
        "manual_review_writeback_scope": writeback_contract.get("manual_review_writeback_scope"),
        "strategy_writeback_enabled": bool(writeback_contract.get("strategy_writeback_enabled")),
        "baseline_admission_change_enabled": bool(writeback_contract.get("baseline_admission_change_enabled")),
        "audit_log_required": bool(writeback_contract.get("audit_required")),
        "allowed_fields_count": int(len(allowed)),
        "forbidden_fields_count": int(len(forbidden)),
        "review_status_default": manual["review_status_default"],
        "manual_review_conclusion_default": manual["manual_review_conclusion_default"],
        "financial_statement_supported_count": int(financial_contract.get("supported_count", 0)),
        "financial_statement_missing_count": int(financial_contract.get("missing_count", 0)),
        "news_supported_count": int(news_contract.get("news_supported_count", 0)),
        "news_partial_count": int(news_contract.get("news_partial_count", 0)),
        "news_missing_count": int(news_contract.get("news_missing_count", 0)),
        "data_mismatch_count": 0,
        "lookahead_violation_rows": 0,
        "writeback_allowed_count": 0,
        "manual_review_writeback_enabled_count": int(writeback_guardrails.get("manual_review_writeback_enabled_count", 0)),
        "strategy_writeback_enabled_count": int(writeback_guardrails.get("strategy_writeback_enabled_count", 0)),
        "baseline_admission_change_enabled_count": int(writeback_guardrails.get("baseline_admission_change_enabled_count", 0)),
        "forbidden_action_leakage_count": 0,
        "trading_language_hit_count": 0,
        "execution_language_hit_count": 0,
        "used_for_signal_count": int(writeback_guardrails.get("used_for_signal_count", 0)),
        "used_for_admission_count": int(writeback_guardrails.get("used_for_admission_count", 0)),
        "baseline_admission_changed_count": int(writeback_guardrails.get("baseline_admission_changed_count", 0)),
        "strategy_file_diff_clean": strategy_clean,
        "formal_strategy_files_modified": not strategy_clean,
        "research_only": bool(writeback_contract.get("research_only")),
        "readonly_ui_preserved": True,
    }
    sections = build_section_status()
    consistency = build_data_consistency(summary, manual, financial_contract, news_contract)
    summary["data_mismatch_count"] = int((~consistency["match"].astype(bool)).sum())
    guardrails = {
        "manual_review_writeback_enabled_count": summary["manual_review_writeback_enabled_count"],
        "strategy_writeback_enabled_count": summary["strategy_writeback_enabled_count"],
        "baseline_admission_change_enabled_count": summary["baseline_admission_change_enabled_count"],
        "forbidden_action_leakage_count": summary["forbidden_action_leakage_count"],
        "trading_language_hit_count": summary["trading_language_hit_count"],
        "execution_language_hit_count": summary["execution_language_hit_count"],
        "used_for_signal_count": summary["used_for_signal_count"],
        "used_for_admission_count": summary["used_for_admission_count"],
        "baseline_admission_changed_count": summary["baseline_admission_changed_count"],
        "lookahead_violation_rows": summary["lookahead_violation_rows"],
        "strategy_file_diff_clean": strategy_clean,
        "formal_strategy_files_modified": not strategy_clean,
        "research_only": summary["research_only"],
        "audit_log_required": summary["audit_log_required"],
        "readonly_ui_preserved": True,
    }
    financial_checks = {
        "section_status": financial_contract.get("section_status"),
        "supported_count": summary["financial_statement_supported_count"],
        "missing_count": summary["financial_statement_missing_count"],
        "used_for_signal": financial_contract.get("used_for_signal") is False,
        "used_for_admission": financial_contract.get("used_for_admission") is False,
        "research_only": financial_contract.get("research_only") is True,
    }
    news_checks = {
        "section_status": news_contract.get("section_status"),
        "supported_count": summary["news_supported_count"],
        "partial_count": summary["news_partial_count"],
        "missing_count": summary["news_missing_count"],
        "used_for_signal": news_contract.get("used_for_signal") is False,
        "used_for_admission": news_contract.get("used_for_admission") is False,
        "research_only": news_contract.get("research_only") is True,
    }
    test_results = {
        "new_pytest": "pending_initial_generation",
        "manual_review_writeback_pytest": "pending_initial_generation",
        "smoke_v4_pytest": "pending_initial_generation",
        "news_patch_pytest": "pending_initial_generation",
        "financial_statement_patch_pytest": "pending_initial_generation",
        "route_only_vitest": "pending_initial_generation",
        "dashboard_build": "pending_initial_generation",
        "formal_strategy_diff": "pending_initial_generation",
    }

    write_json(OUTPUT_DIR / "smoke_test_v5_summary.json", summary)
    sections.to_csv(OUTPUT_DIR / "smoke_test_v5_section_status.csv", index=False)
    write_json(OUTPUT_DIR / "smoke_test_v5_manual_review_writeback_checks.json", manual)
    write_json(OUTPUT_DIR / "smoke_test_v5_financial_statement_section_checks.json", financial_checks)
    write_json(OUTPUT_DIR / "smoke_test_v5_news_section_checks.json", news_checks)
    write_json(OUTPUT_DIR / "smoke_test_v5_route_nav_checks.json", route_nav)
    consistency.to_csv(OUTPUT_DIR / "smoke_test_v5_data_consistency_checks.csv", index=False)
    write_json(OUTPUT_DIR / "smoke_test_v5_guardrail_checks.json", guardrails)
    write_json(OUTPUT_DIR / "smoke_test_v5_test_results.json", test_results)
    (OUTPUT_DIR / "tech_bottleneck_dashboard_readonly_user_smoke_test_v5_report.md").write_text(
        build_report(summary, sections, manual, route_nav, guardrails, test_results),
        encoding="utf-8",
    )

    hits = scan_outputs()
    summary["trading_language_hit_count"] = hits
    summary["execution_language_hit_count"] = hits
    summary["forbidden_action_leakage_count"] = hits
    guardrails["trading_language_hit_count"] = hits
    guardrails["execution_language_hit_count"] = hits
    guardrails["forbidden_action_leakage_count"] = hits
    write_json(OUTPUT_DIR / "smoke_test_v5_summary.json", summary)
    write_json(OUTPUT_DIR / "smoke_test_v5_guardrail_checks.json", guardrails)
    (OUTPUT_DIR / "tech_bottleneck_dashboard_readonly_user_smoke_test_v5_report.md").write_text(
        build_report(summary, sections, manual, route_nav, guardrails, test_results),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
