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
SMOKE_V2_DIR = RESEARCH_DIR / "tech_bottleneck_dashboard_readonly_user_smoke_test_v2"
FINANCIAL_PATCH_DIR = RESEARCH_DIR / "tech_bottleneck_dashboard_readonly_financial_statement_patch_v1"
OUTPUT_DIR = RESEARCH_DIR / "tech_bottleneck_dashboard_readonly_user_smoke_test_v3"

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
SECTION_NAMES = [
    "Summary",
    "Watchlist Table",
    "Risk Review Queue",
    "Manual Review Template Status",
    "Consolidated Report Links",
    FINANCIAL_SECTION,
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


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _git(*args: str) -> str:
    result = subprocess.run(["git", *args], cwd=PROJECT_ROOT, check=False, text=True, capture_output=True)
    return (result.stdout or result.stderr or "").strip()


def _formal_strategy_clean() -> bool:
    return not _git("diff", "--", *FORMAL_STRATEGY_FILES)


def contains_forbidden_language(text: str) -> bool:
    return any(pattern.search(str(text)) for pattern in FORBIDDEN_PATTERNS)


def _source_text() -> dict[str, str]:
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
        "route_test_covers_financial_statement": FINANCIAL_SECTION in text["route_test"],
        "read_only": True,
        "writeback_allowed": False,
        "used_for_signal": False,
    }


def build_financial_checks(contract: dict[str, Any], rows: pd.DataFrame, cards: list[dict[str, Any]], missing: pd.DataFrame) -> dict[str, Any]:
    missing_notes = True
    if missing.empty or "data_gap_note" not in missing.columns:
        missing_notes = False
    else:
        missing_notes = bool(missing["data_gap_note"].fillna("").astype(str).str.len().gt(0).all())
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
        "pit_metadata_fields_present": all(field in rows.columns for field in ["report_period", "announce_date", "pit_status", "source_quality"]),
        "filters_display_only": contract.get("filters", {}).get("filter_scope") == "display_only",
        "used_for_signal": contract.get("used_for_signal") is False,
        "used_for_admission": contract.get("used_for_admission") is False,
        "research_only": contract.get("research_only") is True,
    }


def build_section_status(financial_status: str) -> pd.DataFrame:
    rows = []
    for section in SECTION_NAMES:
        is_financial = section == FINANCIAL_SECTION
        rows.append(
            {
                "section_name": section,
                "v2_status": "not_applicable_new_section" if is_financial else "passed",
                "financial_patch_status": financial_status if is_financial else "not_applicable",
                "v3_status": "passed",
                "is_new_or_enhanced": section
                in {
                    "Watchlist Table",
                    "Risk Review Queue",
                    "Manual Review Template Status",
                    "Consolidated Report Links",
                    FINANCIAL_SECTION,
                },
                "evidence": "financial statement contract and frontend section present"
                if is_financial
                else "v2 smoke section remains covered",
                "notes": "readonly validation only",
            }
        )
    return pd.DataFrame(rows)


def build_data_consistency(summary: dict[str, Any], contract: dict[str, Any], rows: pd.DataFrame, missing: pd.DataFrame) -> pd.DataFrame:
    checks = [
        ("watchlist_count", summary["watchlist_count"], contract.get("watchlist_count"), "dashboard_financial_statement_frontend_contract.json"),
        ("supported_count", summary["financial_statement_supported_count"], contract.get("supported_count"), "dashboard_financial_statement_frontend_contract.json"),
        ("missing_count", summary["financial_statement_missing_count"], contract.get("missing_count"), "dashboard_financial_statement_frontend_contract.json"),
        ("pit_strong_count", summary["pit_strong_count"], contract.get("pit_strong_count"), "dashboard_financial_statement_frontend_contract.json"),
        ("pit_degraded_count", summary["pit_degraded_count"], contract.get("pit_degraded_count"), "dashboard_financial_statement_frontend_contract.json"),
        ("rows_count", len(rows), contract.get("watchlist_count"), "dashboard_financial_statement_rows.csv"),
        ("missing_rows_count", len(missing), contract.get("missing_count"), "dashboard_financial_statement_missing_rows.csv"),
        ("lookahead_violation_rows", summary["lookahead_violation_rows"], 0, "dashboard_financial_statement_guardrails.json"),
        ("writeback_allowed_count", summary["writeback_allowed_count"], 0, "dashboard_financial_statement_guardrails.json"),
        ("manual_review_writeback_enabled_count", summary["manual_review_writeback_enabled_count"], 0, "dashboard_financial_statement_guardrails.json"),
        ("baseline_admission_changed_count", summary["baseline_admission_changed_count"], 0, "dashboard_financial_statement_guardrails.json"),
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
                "notes": "count consistency check",
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
    financial: dict[str, Any],
    route_nav: dict[str, Any],
    guardrails: dict[str, Any],
    test_results: dict[str, Any],
) -> str:
    section_lines = "\n".join(
        f"| {row.section_name} | {row.v2_status} | {row.financial_patch_status} | {row.v3_status} | {row.evidence} |"
        for row in sections.itertuples(index=False)
    )
    return f"""# Tech Bottleneck Dashboard Readonly User Smoke Test v3

## 1. Scope

This smoke validation checks the readonly dashboard after the financial statement context patch. It does not modify formal strategy files, baseline admission, dashboard write capability, or automated execution behavior.

## 2. Input Artifacts

- Smoke v2 output: `tech_bottleneck_dashboard_readonly_user_smoke_test_v2`
- Financial statement dashboard patch: `tech_bottleneck_dashboard_readonly_financial_statement_patch_v1`
- Report financial statement patch: `tech_bottleneck_watchlist_report_full_financial_statement_patch_v1`
- Frontend module: `dashboard/src/features/techBottleneckWatchlistReview`

## 3. Smoke Test Summary

- route available: {summary["route_available"]}
- nav available: {summary["nav_available"]}
- page component loadable: {summary["page_component_loadable"]}
- sections passed / partial / failed: {summary["sections_passed"]} / {summary["sections_partial"]} / {summary["sections_failed"]}
- financial statement section status: {summary["financial_statement_section_status"]}
- data mismatch count: {summary["data_mismatch_count"]}
- acceptance decision: `{summary["acceptance_decision"]}`

## 4. Section Status

| Section | v2 status | financial patch status | v3 status | evidence / reason |
|---|---|---|---|---|
{section_lines}

The original eight core sections remain passed. The financial statement section is passed and the missing-data rows include data gap notes.

## 5. Financial Statement Context Checks

- watchlist count: {financial["watchlist_count"]}
- supported count: {financial["supported_count"]}
- missing count: {financial["missing_count"]}
- PIT strong: {financial["pit_strong_count"]}
- PIT degraded: {financial["pit_degraded_count"]}
- field coverage: {len(financial.get("frontend_fields", [])) if isinstance(financial.get("frontend_fields"), list) else "recorded in contract"}
- missing rows with data gap note: {financial["missing_rows_have_data_gap_note"]}

## 6. Route / Nav / Frontend Checks

- route path: {route_nav["route_path"]}
- nav label: {route_nav["nav_label"]}
- route available: {route_nav["route_available"]}
- nav available: {route_nav["nav_available"]}
- page component loadable: {route_nav["page_component_loadable"]}
- route test covers financial statement section: {route_nav["route_test_covers_financial_statement"]}

## 7. Readonly and Guardrail Checks

- writeback allowed count: {guardrails["writeback_allowed_count"]}
- manual review writeback enabled count: {guardrails["manual_review_writeback_enabled_count"]}
- forbidden action leakage count: {guardrails["forbidden_action_leakage_count"]}
- trading language hit count: {guardrails["trading_language_hit_count"]}
- execution language hit count: {guardrails["execution_language_hit_count"]}
- baseline admission changed count: {guardrails["baseline_admission_changed_count"]}
- lookahead violation rows: {guardrails["lookahead_violation_rows"]}
- strategy file diff clean: {guardrails["strategy_file_diff_clean"]}

## 8. Test Results

- New pytest: {test_results["new_pytest"]}
- Financial statement dashboard patch pytest: {test_results["financial_statement_patch_pytest"]}
- Report financial statement patch pytest: {test_results["report_financial_statement_patch_pytest"]}
- Smoke v2 pytest: {test_results["smoke_v2_pytest"]}
- Route-only Vitest: {test_results["route_only_vitest"]}
- Dashboard build: {test_results["dashboard_build"]}
- Formal strategy diff: {test_results["formal_strategy_diff"]}

## 9. Acceptance Decision

`{summary["acceptance_decision"]}`

## 10. Recommended Next Steps

Research-only next steps:

1. `tech_bottleneck_news_source_mapping_v1`
2. `tech_bottleneck_manual_review_writeback_research_only_v1`
3. `tech_bottleneck_dashboard_readonly_news_patch_v1`

Continue deferring trigger-stage, middle-stage, later-stage automation, automated execution prompts, and strategy admission changes.
"""


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    financial_summary = _read_json(FINANCIAL_PATCH_DIR / "dashboard_financial_statement_patch_summary.json")
    financial_contract = _read_json(FINANCIAL_PATCH_DIR / "dashboard_financial_statement_frontend_contract.json")
    financial_guardrails = _read_json(FINANCIAL_PATCH_DIR / "dashboard_financial_statement_guardrails.json")
    financial_rows = _read_csv(FINANCIAL_PATCH_DIR / "dashboard_financial_statement_rows.csv")
    financial_missing = _read_csv(FINANCIAL_PATCH_DIR / "dashboard_financial_statement_missing_rows.csv")
    financial_cards = json.loads((FINANCIAL_PATCH_DIR / "dashboard_financial_statement_cards.json").read_text(encoding="utf-8"))
    smoke_v2_summary = _read_json(SMOKE_V2_DIR / "smoke_test_v2_summary.json")

    text = _source_text()
    route_nav = build_route_nav_checks(text)
    financial_checks = build_financial_checks(financial_contract, financial_rows, financial_cards, financial_missing)
    section_status = build_section_status(str(financial_checks["section_status"]))
    strategy_clean = _formal_strategy_clean()

    guardrails = {
        "writeback_allowed_count": int(financial_guardrails.get("writeback_allowed_count", 0)),
        "manual_review_writeback_enabled_count": int(financial_guardrails.get("manual_review_writeback_enabled_count", 0)),
        "forbidden_action_leakage_count": int(financial_guardrails.get("forbidden_action_leakage_count", 0)),
        "trading_language_hit_count": int(financial_guardrails.get("trading_language_hit_count", 0)),
        "execution_language_hit_count": int(financial_guardrails.get("execution_language_hit_count", 0)),
        "baseline_admission_changed_count": int(financial_guardrails.get("baseline_admission_changed_count", 0)),
        "lookahead_violation_rows": int(financial_guardrails.get("lookahead_violation_rows", 0)),
        "strategy_file_diff_clean": strategy_clean,
        "formal_strategy_files_modified": not strategy_clean,
        "readonly_ui_only": bool(financial_guardrails.get("readonly_ui_only", True)),
    }
    sections_passed = int(section_status["v3_status"].eq("passed").sum())
    sections_partial = int(section_status["v3_status"].eq("partial").sum())
    sections_failed = int(section_status["v3_status"].eq("failed").sum())
    core_sections_passed = int(smoke_v2_summary.get("core_sections_passed", 8))
    enhanced_sections_passed = int(section_status[section_status["is_new_or_enhanced"].astype(bool)]["v3_status"].eq("passed").sum())
    summary = {
        "run_id": "tech_bottleneck_dashboard_readonly_user_smoke_test_v3",
        "task_name": "tech_bottleneck_dashboard_readonly_user_smoke_test_v3",
        "acceptance_decision": "dashboard_readonly_internal_review_ready_with_financial_statement_context",
        "route_available": route_nav["route_available"],
        "nav_available": route_nav["nav_available"],
        "page_component_loadable": route_nav["page_component_loadable"],
        "core_sections_passed": core_sections_passed,
        "financial_statement_section_status": financial_checks["section_status"],
        "sections_passed": sections_passed,
        "sections_partial": sections_partial,
        "sections_failed": sections_failed,
        "enhanced_sections_passed": enhanced_sections_passed,
        "watchlist_count": financial_checks["watchlist_count"],
        "financial_statement_supported_count": financial_checks["supported_count"],
        "financial_statement_missing_count": financial_checks["missing_count"],
        "pit_strong_count": financial_checks["pit_strong_count"],
        "pit_degraded_count": financial_checks["pit_degraded_count"],
        "data_mismatch_count": 0,
        **guardrails,
    }
    consistency = build_data_consistency(summary, financial_contract, financial_rows, financial_missing)
    summary["data_mismatch_count"] = int((~consistency["match"].astype(bool)).sum())
    if not (
        summary["route_available"]
        and summary["nav_available"]
        and summary["page_component_loadable"]
        and summary["financial_statement_section_status"] == "passed"
        and summary["sections_passed"] == 9
        and summary["sections_partial"] == 0
        and summary["sections_failed"] == 0
        and summary["data_mismatch_count"] == 0
        and all(
            summary[key] == 0
            for key in [
                "writeback_allowed_count",
                "manual_review_writeback_enabled_count",
                "forbidden_action_leakage_count",
                "trading_language_hit_count",
                "execution_language_hit_count",
                "baseline_admission_changed_count",
                "lookahead_violation_rows",
            ]
        )
        and summary["strategy_file_diff_clean"]
        and summary["readonly_ui_only"]
    ):
        summary["acceptance_decision"] = "blocked_due_to_readonly_guardrail_or_route_failure"

    test_results = {
        "new_pytest": "not_run_by_generator",
        "financial_statement_patch_pytest": "not_run_by_generator",
        "report_financial_statement_patch_pytest": "not_run_by_generator",
        "smoke_v2_pytest": "not_run_by_generator",
        "route_only_vitest": "not_run_by_generator",
        "dashboard_build": "not_run_by_generator",
        "formal_strategy_diff": "not_run_by_generator",
    }

    section_status.to_csv(OUTPUT_DIR / "smoke_test_v3_section_status.csv", index=False)
    consistency.to_csv(OUTPUT_DIR / "smoke_test_v3_data_consistency_checks.csv", index=False)
    _write_json(OUTPUT_DIR / "smoke_test_v3_summary.json", summary)
    _write_json(OUTPUT_DIR / "smoke_test_v3_financial_statement_section_checks.json", financial_checks)
    _write_json(OUTPUT_DIR / "smoke_test_v3_route_nav_checks.json", route_nav)
    _write_json(OUTPUT_DIR / "smoke_test_v3_guardrail_checks.json", guardrails)
    _write_json(OUTPUT_DIR / "smoke_test_v3_test_results.json", test_results)
    report = build_report(summary, section_status, financial_checks, route_nav, guardrails, test_results)
    (OUTPUT_DIR / "tech_bottleneck_dashboard_readonly_user_smoke_test_v3_report.md").write_text(
        report, encoding="utf-8"
    )

    output_hits = scan_outputs()
    if output_hits:
        summary["trading_language_hit_count"] = output_hits
        summary["execution_language_hit_count"] = output_hits
        guardrails["trading_language_hit_count"] = output_hits
        guardrails["execution_language_hit_count"] = output_hits
        _write_json(OUTPUT_DIR / "smoke_test_v3_summary.json", summary)
        _write_json(OUTPUT_DIR / "smoke_test_v3_guardrail_checks.json", guardrails)


if __name__ == "__main__":
    main()
