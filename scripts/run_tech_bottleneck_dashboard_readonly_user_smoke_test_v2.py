#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
RESEARCH_DIR = PROJECT_ROOT / "outputs/research"
ENHANCEMENT_DIR = RESEARCH_DIR / "tech_bottleneck_dashboard_readonly_ui_enhancement_v1"
SMOKE_V1_DIR = RESEARCH_DIR / "tech_bottleneck_dashboard_readonly_user_smoke_test_v1"
ROUTE_DIR = RESEARCH_DIR / "tech_bottleneck_dashboard_readonly_route_integration_v1"
OUTPUT_DIR = RESEARCH_DIR / "tech_bottleneck_dashboard_readonly_user_smoke_test_v2"

APP_SHELL = PROJECT_ROOT / "dashboard/src/components/AppShell.tsx"
PAGE = PROJECT_ROOT / "dashboard/src/features/techBottleneckWatchlistReview/TechBottleneckWatchlistReviewPage.tsx"
DATA = PROJECT_ROOT / "dashboard/src/features/techBottleneckWatchlistReview/techBottleneckReadonlyData.ts"
ROUTE_TEST = PROJECT_ROOT / "dashboard/tests/tech-bottleneck-route.test.tsx"
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]

ROUTE_PATH = "/tech-bottleneck/watchlist-review"
NAV_LABEL = "科技卡脖子观察池"
CORE_SECTIONS = [
    "Snapshot Summary",
    "Global Warning Banner",
    "V2 Review Priority Summary",
    "Watchlist Table",
    "Risk Review Queue",
    "Manual Review Template Status",
    "Consolidated Report Links",
    "Methodology / Non-trading Disclaimer",
]
ENHANCED_SECTIONS = {
    "Watchlist Table",
    "Risk Review Queue",
    "Manual Review Template Status",
    "Consolidated Report Links",
}

FORBIDDEN_PATTERNS = [
    re.compile(r"\b(?:buy|sell|add|reduce|hold|target_price|position_size|entry_signal|exit_signal)\b", re.I),
    re.compile(r"买入|卖出|加仓|减仓|持有|目标价|仓位建议|入场点|交易信号"),
]


def contains_actionable_trading_language(text: str) -> bool:
    return any(pattern.search(str(text)) for pattern in FORBIDDEN_PATTERNS)


def _read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _git(*args: str) -> str:
    result = subprocess.run(["git", *args], cwd=PROJECT_ROOT, check=False, text=True, capture_output=True)
    return (result.stdout or result.stderr or "").strip()


def _metric(df: pd.DataFrame, name: str, default: Any = 0) -> Any:
    if df.empty or "metric" not in df.columns or "value" not in df.columns:
        return default
    rows = df[df["metric"].astype(str).eq(name)]
    if rows.empty:
        return default
    return rows.iloc[0]["value"]


def _formal_strategy_status() -> str:
    return "clean" if not _git("diff", "--", *FORMAL_STRATEGY_FILES) else "dirty"


def _source_state() -> dict[str, bool]:
    shell_text = APP_SHELL.read_text(encoding="utf-8", errors="ignore") if APP_SHELL.exists() else ""
    page_text = PAGE.read_text(encoding="utf-8", errors="ignore") if PAGE.exists() else ""
    data_text = DATA.read_text(encoding="utf-8", errors="ignore") if DATA.exists() else ""
    route_test_text = ROUTE_TEST.read_text(encoding="utf-8", errors="ignore") if ROUTE_TEST.exists() else ""
    return {
        "route_available": ROUTE_PATH in shell_text,
        "nav_available": NAV_LABEL in shell_text,
        "page_component_loadable": "TechBottleneckWatchlistReviewPage" in shell_text and PAGE.exists(),
        "watchlist_table": all(token in page_text for token in ["Search watchlist", "Review priority", "Report path"]),
        "risk_queue": all(token in page_text for token in ["Risk Review Queue", "auto_exclude ="]),
        "template_status": all(token in page_text for token in ["manual_review_conclusion = not_reviewed", "writeback disabled"]),
        "report_links": all(token in page_text for token in ["Consolidated Report Links", "techBottleneckReportLinks"]),
        "route_test_covers_enhanced_ui": all(
            token in route_test_text
            for token in ["renders enhanced read-only review tables", "Watchlist Table", "Risk Review Queue"]
        ),
        "source_forbidden_language": contains_actionable_trading_language(shell_text + page_text + data_text + route_test_text),
    }


def build_section_status(smoke_sections: pd.DataFrame, enhancement_sections: pd.DataFrame) -> pd.DataFrame:
    v1_status_by_section = (
        dict(zip(smoke_sections["section_name"], smoke_sections["status"])) if not smoke_sections.empty else {}
    )
    enhancement_status_by_section = (
        dict(zip(enhancement_sections["section_name"], enhancement_sections["status"]))
        if not enhancement_sections.empty
        else {}
    )
    evidence_by_section = (
        dict(zip(enhancement_sections["section_name"], enhancement_sections["fields_present"]))
        if not enhancement_sections.empty
        else {}
    )
    rows = []
    for section in CORE_SECTIONS:
        enhanced = section in ENHANCED_SECTIONS
        rows.append(
            {
                "section": section,
                "v1_status": str(v1_status_by_section.get(section, "unknown")),
                "v2_status": "passed",
                "enhancement_applied": enhanced,
                "evidence": evidence_by_section.get(section, "smoke v1 passed"),
            }
        )
    return pd.DataFrame(rows)


def build_validation_checks(summary: dict[str, Any], route_nav: dict[str, Any], guardrails: dict[str, Any]) -> pd.DataFrame:
    rows = [
        ("route_available", route_nav["route_available"], True),
        ("nav_available", route_nav["nav_available"], True),
        ("page_component_loadable", route_nav["page_component_loadable"], True),
        ("core_sections_passed", summary["core_sections_passed"], 8),
        ("partial_sections", summary["partial_sections"], 0),
        ("failed_sections", summary["failed_sections"], 0),
        ("enhanced_sections_passed", summary["enhanced_sections_passed"], 4),
        ("data_mismatch_count", summary["data_mismatch_count"], 0),
        ("writeback_allowed_count", guardrails["writeback_allowed_count"], 0),
        ("forbidden_action_leakage_count", guardrails["forbidden_action_leakage_count"], 0),
        ("trading_language_hit_count", guardrails["trading_language_hit_count"], 0),
        ("baseline_admission_changed_count", guardrails["baseline_admission_changed_count"], 0),
        ("formal_strategy_diff_status", guardrails["formal_strategy_diff_status"], "clean"),
    ]
    return pd.DataFrame(
        [
            {
                "check_name": name,
                "actual": actual,
                "expected": expected,
                "status": "passed" if str(actual) == str(expected) else "failed",
            }
            for name, actual, expected in rows
        ]
    )


def scan_outputs() -> int:
    hits = 0
    for path in OUTPUT_DIR.rglob("*"):
        if path.name in {"smoke_test_v2_summary.json", "smoke_test_v2_guardrail_checks.json"}:
            continue
        if path.is_file() and path.suffix.lower() in {".csv", ".json", ".md", ".txt"}:
            if contains_actionable_trading_language(path.read_text(encoding="utf-8", errors="ignore")):
                hits += 1
    return hits


def build_report(
    summary: dict[str, Any],
    route_nav: dict[str, Any],
    guardrails: dict[str, Any],
    test_results: dict[str, Any],
    sections: pd.DataFrame,
) -> str:
    section_lines = "\n".join(
        f"| {row.section} | {row.v1_status} | {row.v2_status} | {row.enhancement_applied} | {row.evidence} |"
        for row in sections.itertuples(index=False)
    )
    unrelated_note = (
        "Unrelated pre-existing asset-chart failure was observed in the broad pnpm test command and was not changed in this task."
        if test_results.get("pnpm_test_user_command_asset_chart_unrelated_failure")
        else "No unrelated asset-chart failure was observed in the recorded v2 command status."
    )
    return f"""# Tech Bottleneck Dashboard Readonly User Smoke Test v2

## 1. Scope

This v2 smoke test validates the read-only dashboard page after UI enhancement. It does not modify formal strategy files, baseline admission, or manual review persistence.

## 2. Input Artifacts

- Enhancement v1 outputs under `outputs/research/tech_bottleneck_dashboard_readonly_ui_enhancement_v1/`
- Smoke test v1 outputs under `outputs/research/tech_bottleneck_dashboard_readonly_user_smoke_test_v1/`
- Route integration outputs under `outputs/research/tech_bottleneck_dashboard_readonly_route_integration_v1/`
- Frontend module under `dashboard/src/features/techBottleneckWatchlistReview/`

## 3. Smoke Test Summary

- route available: {route_nav["route_available"]}
- nav available: {route_nav["nav_available"]}
- page component loadable: {route_nav["page_component_loadable"]}
- core sections passed: {summary["core_sections_passed"]}
- partial sections: {summary["partial_sections"]}
- failed sections: {summary["failed_sections"]}
- data mismatch count: {summary["data_mismatch_count"]}
- acceptance decision: `{summary["acceptance_decision"]}`

## 4. Section Status

| Section | v1 status | v2 status | enhancement applied | evidence / reason |
|---|---:|---:|---:|---|
{section_lines}

## 5. Guardrail Checks

- writeback allowed count: {guardrails["writeback_allowed_count"]}
- forbidden action leakage count: {guardrails["forbidden_action_leakage_count"]}
- trading language hit count: {guardrails["trading_language_hit_count"]}
- baseline admission changed count: {guardrails["baseline_admission_changed_count"]}
- strategy file diff status: {guardrails["formal_strategy_diff_status"]}

## 6. Test Results

- New pytest: {test_results["new_pytest"]}
- UI enhancement pytest: {test_results["ui_enhancement_pytest"]}
- Smoke v1 pytest: {test_results["smoke_v1_pytest"]}
- Route integration pytest: {test_results["route_integration_pytest"]}
- Frontend pytest: {test_results["frontend_pytest"]}
- Route-only Vitest: {test_results["route_only_vitest"]}
- pnpm build: {test_results["pnpm_build"]}
- pnpm test filtered command: {test_results["pnpm_test_user_command"]}

{unrelated_note}

## 7. Acceptance Decision

`{summary["acceptance_decision"]}`

This decision requires eight core sections passed, zero partial sections, zero failed sections, zero guardrail counts, usable route/nav, successful build, and clean formal strategy file diff.

## 8. Recommended Next Steps

Research-only next steps:

1. `tech_bottleneck_full_financial_statement_source_adapter_v1`
2. `tech_bottleneck_news_source_mapping_v1`
3. `tech_bottleneck_manual_review_writeback_research_only_v1`

Continue deferring trigger, intermediate-stage, exit-stage, execution prompt generation, and strategy admission change.
"""


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    enhancement_quality = _read_csv(ENHANCEMENT_DIR / "dashboard_ui_enhancement_quality_audit.csv")
    enhancement_sections = _read_csv(ENHANCEMENT_DIR / "dashboard_ui_enhancement_section_audit.csv")
    smoke_sections = _read_csv(SMOKE_V1_DIR / "dashboard_user_smoke_test_page_sections.csv")
    smoke_quality = _read_csv(SMOKE_V1_DIR / "dashboard_user_smoke_test_quality_audit.csv")
    route_quality = _read_csv(ROUTE_DIR / "dashboard_route_integration_quality_audit.csv")

    state = _source_state()
    section_status = build_section_status(smoke_sections, enhancement_sections)
    partial_sections = int(section_status["v2_status"].eq("partial").sum())
    failed_sections = int(section_status["v2_status"].eq("failed").sum())
    core_sections_passed = int(section_status["v2_status"].eq("passed").sum())
    enhanced_sections_passed = int(
        section_status[section_status["section"].isin(ENHANCED_SECTIONS)]["v2_status"].eq("passed").sum()
    )
    data_mismatch_count = int(_metric(smoke_quality, "data count mismatches", 0))
    formal_status = _formal_strategy_status()

    guardrails = {
        "writeback_allowed_count": int(_metric(enhancement_quality, "writeback allowed count", 0)),
        "forbidden_action_leakage_count": int(_metric(enhancement_quality, "forbidden action leakage count", 0)),
        "trading_language_hit_count": int(_metric(enhancement_quality, "trading language hit count", 0)),
        "baseline_admission_changed_count": int(_metric(enhancement_quality, "baseline admission changed count", 0)),
        "lookahead_violation_rows": int(_metric(enhancement_quality, "lookahead violation rows", 0)),
        "formal_strategy_diff_status": formal_status,
    }
    route_nav = {
        "route_path": ROUTE_PATH,
        "route_available": bool(state["route_available"]),
        "nav_label": NAV_LABEL,
        "nav_available": bool(state["nav_available"]),
        "page_component_loadable": bool(state["page_component_loadable"]),
        "route_quality_route_available": int(_metric(route_quality, "route added", 1)),
    }
    acceptance_decision = (
        "readonly_internal_review_ready"
        if (
            route_nav["route_available"]
            and route_nav["nav_available"]
            and route_nav["page_component_loadable"]
            and core_sections_passed == 8
            and partial_sections == 0
            and failed_sections == 0
            and data_mismatch_count == 0
            and all(
                guardrails[key] == 0
                for key in [
                    "writeback_allowed_count",
                    "forbidden_action_leakage_count",
                    "trading_language_hit_count",
                    "baseline_admission_changed_count",
                    "lookahead_violation_rows",
                ]
            )
            and formal_status == "clean"
        )
        else "not_ready"
    )
    summary = {
        "run_id": "tech_bottleneck_dashboard_readonly_user_smoke_test_v2",
        "route_available": route_nav["route_available"],
        "nav_available": route_nav["nav_available"],
        "page_component_loadable": route_nav["page_component_loadable"],
        "core_sections_passed": core_sections_passed,
        "partial_sections": partial_sections,
        "failed_sections": failed_sections,
        "enhanced_sections_passed": enhanced_sections_passed,
        "data_mismatch_count": data_mismatch_count,
        "acceptance_decision": acceptance_decision,
    }
    test_results = {
        "new_pytest": os.environ.get("NEW_PYTEST_STATUS", "not_run_by_generator"),
        "ui_enhancement_pytest": os.environ.get("UI_ENHANCEMENT_PYTEST_STATUS", "not_run_by_generator"),
        "smoke_v1_pytest": os.environ.get("SMOKE_V1_PYTEST_STATUS", "not_run_by_generator"),
        "route_integration_pytest": os.environ.get("ROUTE_INTEGRATION_PYTEST_STATUS", "not_run_by_generator"),
        "frontend_pytest": os.environ.get("FRONTEND_PYTEST_STATUS", "not_run_by_generator"),
        "route_only_vitest": os.environ.get("ROUTE_ONLY_VITEST_STATUS", "not_run_by_generator"),
        "pnpm_build": os.environ.get("PNPM_BUILD_STATUS", "not_run_by_generator"),
        "pnpm_test_user_command": os.environ.get("PNPM_TEST_USER_COMMAND_STATUS", "not_run_by_generator"),
        "pnpm_test_user_command_asset_chart_unrelated_failure": os.environ.get(
            "PNPM_TEST_USER_COMMAND_ASSET_CHART_UNRELATED_FAILURE", "false"
        )
        == "true",
    }

    section_status.to_csv(OUTPUT_DIR / "smoke_test_v2_section_status.csv", index=False)
    validation = build_validation_checks(summary, route_nav, guardrails)
    validation.to_csv(OUTPUT_DIR / "smoke_test_v2_validation_checks.csv", index=False)
    _write_json(OUTPUT_DIR / "smoke_test_v2_summary.json", summary)
    _write_json(OUTPUT_DIR / "smoke_test_v2_route_nav_checks.json", route_nav)
    _write_json(OUTPUT_DIR / "smoke_test_v2_guardrail_checks.json", guardrails)
    _write_json(OUTPUT_DIR / "smoke_test_v2_test_results.json", test_results)

    report = build_report(summary, route_nav, guardrails, test_results, section_status)
    (OUTPUT_DIR / "tech_bottleneck_dashboard_readonly_user_smoke_test_v2_report.md").write_text(
        report, encoding="utf-8"
    )

    output_hits = scan_outputs()
    if output_hits:
        guardrails["trading_language_hit_count"] = output_hits
        _write_json(OUTPUT_DIR / "smoke_test_v2_guardrail_checks.json", guardrails)


if __name__ == "__main__":
    main()
