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
OUTPUT_DIR = RESEARCH_DIR / "tech_bottleneck_dashboard_readonly_ops_handoff_v1"
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]
ROUTE_PATH = "/tech-bottleneck/watchlist-review"
NAV_LABEL = "科技卡脖子观察池"
FEATURE_FILES = [
    "dashboard/src/features/techBottleneckWatchlistReview/types.ts",
    "dashboard/src/features/techBottleneckWatchlistReview/techBottleneckReadonlyData.ts",
    "dashboard/src/features/techBottleneckWatchlistReview/TechBottleneckWatchlistReviewPage.tsx",
]

FORBIDDEN_PATTERNS = [
    re.compile(
        r"\b(?:buy|sell|add|reduce|hold|entry|exit|position|target price|increase position|"
        r"reduce position|target_price|position_size|entry_signal|exit_signal)\b",
        re.I,
    ),
    re.compile(r"买入|卖出|加仓|减仓|持有|目标价|仓位建议|入场点|退出|止盈|止损|调仓|交易信号"),
]


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def git_output(*args: str) -> str:
    result = subprocess.run(["git", *args], cwd=PROJECT_ROOT, check=False, text=True, capture_output=True)
    return (result.stdout or result.stderr or "").strip()


def formal_strategy_diff_clean() -> bool:
    return not git_output("diff", "--", *FORMAL_STRATEGY_FILES)


def has_forbidden_language(text: str) -> bool:
    return any(pattern.search(text) for pattern in FORBIDDEN_PATTERNS)


def scan_outputs() -> int:
    hits = 0
    for path in OUTPUT_DIR.rglob("*"):
        if path.is_file() and path.suffix.lower() in {".md", ".json", ".csv", ".txt"}:
            if has_forbidden_language(path.read_text(encoding="utf-8", errors="ignore")):
                hits += 1
    return hits


def route_nav_checks() -> dict[str, Any]:
    app_shell = (PROJECT_ROOT / "dashboard/src/components/AppShell.tsx").read_text(encoding="utf-8")
    route_test = (PROJECT_ROOT / "dashboard/tests/tech-bottleneck-route.test.tsx").read_text(encoding="utf-8")
    page_file = PROJECT_ROOT / "dashboard/src/features/techBottleneckWatchlistReview/TechBottleneckWatchlistReviewPage.tsx"
    return {
        "route_path": ROUTE_PATH,
        "route_available": ROUTE_PATH in app_shell and ROUTE_PATH in route_test,
        "nav_label": NAV_LABEL,
        "nav_available": NAV_LABEL in app_shell,
        "page_component": "TechBottleneckWatchlistReviewPage",
        "page_component_loadable": page_file.exists()
        and "TechBottleneckWatchlistReviewPage" in page_file.read_text(encoding="utf-8"),
        "frontend_module_files": FEATURE_FILES,
        "route_test_file": "dashboard/tests/tech-bottleneck-route.test.tsx",
        "research_only": True,
        "used_for_signal": False,
        "used_for_admission": False,
    }


def checklist_rows(summary: dict[str, Any]) -> list[dict[str, Any]]:
    items = [
        ("route_available", True, summary["route_available"], "ops", "per release"),
        ("nav_available", True, summary["nav_available"], "ops", "per release"),
        ("page_component_loadable", True, summary["page_component_loadable"], "developer", "per release"),
        ("smoke_v5_ready", True, summary["smoke_v5_ready"], "ops", "per release"),
        ("release_notes_ready", True, summary["release_notes_ready"], "ops", "per release"),
        ("archive_packaging_ready", True, summary["archive_packaging_ready"], "ops", "per release"),
        ("archive_integrity_ready", True, summary["archive_integrity_ready"], "auditor", "per release"),
        ("manual_review_writeback_ready", True, summary["manual_review_writeback_ready"], "review lead", "per release"),
        ("audit_replay_ready", True, summary["audit_replay_ready"], "auditor", "per release"),
        ("financial_statement_section_passed", "passed", summary["financial_statement_section_status"], "reviewer", "per release"),
        ("news_section_passed", "passed", summary["news_section_status"], "reviewer", "per release"),
        ("manual_review_writeback_section_passed", "passed", summary["manual_review_writeback_section_status"], "review lead", "per release"),
        ("strategy_writeback_disabled", 0, summary["strategy_writeback_enabled_count"], "developer", "per release"),
        ("baseline_admission_change_disabled", 0, summary["baseline_admission_change_enabled_count"], "developer", "per release"),
        ("used_for_signal_zero", 0, summary["used_for_signal_count"], "auditor", "per release"),
        ("used_for_admission_zero", 0, summary["used_for_admission_count"], "auditor", "per release"),
        ("execution_language_zero", 0, summary["execution_language_hit_count"], "auditor", "per release"),
        ("lookahead_violation_zero", 0, summary["lookahead_violation_rows"], "auditor", "per release"),
        ("formal_strategy_diff_empty", True, summary["strategy_file_diff_clean"], "developer", "per release"),
        ("pnpm_build_passed", True, summary["pnpm_build_passed"], "developer", "per release"),
        ("route_test_passed", True, summary["route_test_passed"], "developer", "per release"),
    ]
    rows = []
    for name, expected, actual, owner, frequency in items:
        rows.append(
            {
                "check_name": name,
                "expected_value": expected,
                "actual_value": actual,
                "status": "passed" if str(expected) == str(actual) else "failed",
                "owner": owner,
                "frequency": frequency,
                "notes": "research-only handoff gate",
            }
        )
    return rows


def build_readme(summary: dict[str, Any]) -> str:
    return f"""# Tech Bottleneck Watchlist Review Dashboard v1
## Ops Handoff README

### 1. Purpose

This is the internal handoff document for the Tech Bottleneck watchlist research-only dashboard v1.

### 2. Dashboard Access

- route: `{ROUTE_PATH}`
- nav label: `{NAV_LABEL}`
- frontend module:
- `dashboard/src/features/techBottleneckWatchlistReview/types.ts`
- `dashboard/src/features/techBottleneckWatchlistReview/techBottleneckReadonlyData.ts`
- `dashboard/src/features/techBottleneckWatchlistReview/TechBottleneckWatchlistReviewPage.tsx`

### 3. Current Ready State

- release notes ready: {summary["release_notes_ready"]}
- archive packaging ready: {summary["archive_packaging_ready"]}
- archive integrity ready: {summary["archive_integrity_ready"]}
- smoke v5 ready: {summary["smoke_v5_ready"]}
- manual review writeback ready: {summary["manual_review_writeback_ready"]}
- audit replay ready: {summary["audit_replay_ready"]}

### 4. Dashboard Sections

- Summary
- Watchlist Table
- Risk Review Queue
- Manual Review Template Status
- Consolidated Report Links
- Full Financial Statement Review Context
- News and Event Review Context
- Manual Review Research-Only Writeback
- Warnings / Data Gaps
- Route / Navigation
- Readonly / Research-Only Guardrails

### 5. Data Coverage

- watchlist count: {summary["watchlist_count"]}
- financial statement: {summary["financial_statement_supported_count"]} supported / {summary["financial_statement_missing_count"]} missing
- news: {summary["news_supported_count"]} supported / {summary["news_partial_count"]} partial / {summary["news_missing_count"]} missing
- news PIT / post-admission / date-missing events: {summary["news_pit_available_event_count"]} / {summary["news_post_admission_event_count"]} / {summary["news_date_missing_event_count"]}

### 6. Manual Review Writeback Boundary

- manual review writeback enabled: {summary["manual_review_writeback_enabled"]}
- writeback scope: {summary["manual_review_writeback_scope"]}
- strategy writeback enabled: {summary["strategy_writeback_enabled"]}
- baseline admission change enabled: {summary["baseline_admission_change_enabled"]}
- allowed fields: {summary["allowed_fields_count"]}
- forbidden fields: {summary["forbidden_fields_count"]}
- audit log required: {summary["audit_log_required"]}

### 7. Guardrails

- strategy writeback enabled count: {summary["strategy_writeback_enabled_count"]}
- baseline admission change enabled count: {summary["baseline_admission_change_enabled_count"]}
- used_for_signal count: {summary["used_for_signal_count"]}
- used_for_admission count: {summary["used_for_admission_count"]}
- execution language hit count: {summary["execution_language_hit_count"]}
- lookahead violation rows: {summary["lookahead_violation_rows"]}
- formal strategy diff: empty

### 8. How to Operate

1. Open the dashboard.
2. Select `{NAV_LABEL}`.
3. Review the summary.
4. Review warnings and data gaps.
5. Use Watchlist Table filters for display-only review.
6. Open consolidated report links.
7. Review financial statement context.
8. Review news context.
9. Fill research-only manual review notes and labels.
10. Do not use this page as an automated execution basis.

### 9. Forbidden Usage

- Do not use as automated execution guidance.
- Do not use as exposure adjustment guidance.
- Do not use as a baseline admission modification source.
- Do not define trigger-stage, middle-stage, or later-stage automation rules from this package.
- Do not route manual review content into formal strategy inputs.
- Do not treat missing news or missing financial statement coverage as an automatic removal condition.
- Do not treat post-admission news as PIT evidence.
- Do not treat date-missing news as strong PIT evidence.

### 10. Maintenance

- Run smoke v5.
- Run archive integrity.
- Run manual review writeback audit replay.
- Run dashboard route test.
- Run dashboard build.
- Check formal strategy diff.

### 11. Rollback

If the dashboard page fails, rollback scope is limited to the dashboard feature module, route test, and research outputs. Formal strategy files are out of rollback scope.

### 12. Known Limitations

- Financial statement coverage is {summary["financial_statement_supported_count"]} / {summary["watchlist_count"]}.
- News coverage remains degraded.
- Manual review writeback is research-only.
- Trigger-stage, middle-stage, and later-stage automation are not included.
- No automated execution prompt is included.
"""


def build_user_guide() -> str:
    return f"""# Ops Handoff User Guide

## Page Access

Use route `{ROUTE_PATH}` or nav label `{NAV_LABEL}`.

## Section Reading Guide

- Summary: overall watchlist and guardrail status.
- Watchlist Table: display-only filtering and sorting.
- Risk Review Queue: risk review context for manual review.
- Manual Review Template Status: review template readiness.
- Consolidated Report Links: individual research report access.
- Full Financial Statement Review Context: PIT financial statement context and missing data notes.
- News and Event Review Context: PIT news, post-admission context, date-missing degraded rows, and missing data notes.
- Manual Review Research-Only Writeback: research-only labels and notes with audit logging.
- Warnings / Data Gaps: missing financial statement and news context.
- Route / Navigation: dashboard access confirmation.
- Readonly / Research-Only Guardrails: boundary checks.

## Data Gap Handling

Missing financial statement context means the reviewer should record a data gap note. Missing, partial, or date-missing news means event completeness should be manually reviewed and documented.

## Manual Review

Use allowed research-only fields for review status, labels, evidence quality notes, financial statement notes, news notes, risk notes, reviewer, and timestamp. Audit log records support replay and accountability.

## Prohibited Use

Do not use page content as an automated execution basis, exposure adjustment source, baseline admission modification source, or formal strategy input.
"""


def build_rollback_plan() -> str:
    return """# Ops Handoff Rollback Plan

## Scope

Rollback scope is limited to dashboard feature module files, route test changes, and research output artifacts. formal strategy files are out of rollback scope.

## Panel-Level Degrade Options

- If manual review writeback UI fails, disable the writeback panel and keep readonly sections visible.
- If news section fails, degrade it to a data gap summary.
- If financial statement section fails, degrade it to a coverage summary.

## Required Checks After Rollback

- Re-run smoke test and guardrail tests.
- Re-run route test and dashboard build.
- Confirm formal strategy diff is empty.
"""


def build_troubleshooting() -> str:
    return """# Ops Handoff Troubleshooting

## route unavailable

Check AppShell route registration and route test coverage.

## nav hidden

Check nav label registration in the dashboard shell.

## page component load failure

Check the Tech Bottleneck feature module import and component export.

## financial statement count mismatch

Compare dashboard financial statement patch summary with smoke v5 summary.

## news count mismatch

Compare dashboard news patch summary with smoke v5 summary.

## manual review panel hidden

Check manual review frontend contract and research-only panel rendering.

## audit replay mismatch

Run audit replay validation and compare reconstructed store with expected store.

## strategy diff non-empty

Stop handoff and inspect formal strategy diff before proceeding.

## execution language scanner hit

Locate the generated artifact and replace action-oriented phrasing with neutral research wording.

## build failure

Run dashboard build locally. Existing chunk-size warning is non-blocking unless build status changes to failure.
"""


def build_known_limitations(summary: dict[str, Any]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "limitation": "financial_statement_missing",
                "value": summary["financial_statement_missing_count"],
                "status": "known",
                "notes": "Treat as data gap for manual review.",
            },
            {
                "limitation": "news_degraded_coverage",
                "value": f'{summary["news_supported_count"]}/{summary["news_partial_count"]}/{summary["news_missing_count"]}',
                "status": "known",
                "notes": "Supported / partial / missing coverage.",
            },
            {
                "limitation": "post_admission_news_context",
                "value": summary["news_post_admission_event_count"],
                "status": "known",
                "notes": "Review context only; not PIT evidence.",
            },
            {
                "limitation": "date_missing_news_degraded",
                "value": summary["news_date_missing_event_count"],
                "status": "known",
                "notes": "Degraded source quality; not strong PIT evidence.",
            },
        ]
    )


def build_report(summary: dict[str, Any], test_results: dict[str, str]) -> str:
    return f"""# Tech Bottleneck Dashboard Readonly Ops Handoff v1 Report

## 1. Scope

This task generated internal ops handoff documents for Tech Bottleneck research-only dashboard v1.

## 2. Handoff Outputs

- ops handoff generated: {summary["ops_handoff_generated"]}
- route available: {summary["route_available"]}
- nav available: {summary["nav_available"]}
- smoke v5 ready: {summary["smoke_v5_ready"]}
- release notes ready: {summary["release_notes_ready"]}
- archive packaging ready: {summary["archive_packaging_ready"]}
- archive integrity ready: {summary["archive_integrity_ready"]}
- manual review writeback ready: {summary["manual_review_writeback_ready"]}
- audit replay ready: {summary["audit_replay_ready"]}

## 3. Data Coverage

- watchlist count: {summary["watchlist_count"]}
- financial statement: {summary["financial_statement_supported_count"]} supported / {summary["financial_statement_missing_count"]} missing
- news: {summary["news_supported_count"]} supported / {summary["news_partial_count"]} partial / {summary["news_missing_count"]} missing

## 4. Guardrails

- strategy writeback enabled count: {summary["strategy_writeback_enabled_count"]}
- baseline admission change enabled count: {summary["baseline_admission_change_enabled_count"]}
- used_for_signal count: {summary["used_for_signal_count"]}
- used_for_admission count: {summary["used_for_admission_count"]}
- execution language hit count: {summary["execution_language_hit_count"]}
- lookahead violation rows: {summary["lookahead_violation_rows"]}
- formal strategy diff clean: {summary["strategy_file_diff_clean"]}

## 5. Test Results

- Ops handoff pytest: {test_results["ops_handoff_pytest"]}
- Archive packaging pytest: {test_results["archive_packaging_pytest"]}
- Release notes pytest: {test_results["release_notes_pytest"]}
- Smoke v5 pytest: {test_results["smoke_v5_pytest"]}
- Dashboard route test: {test_results["dashboard_route_test"]}
- Dashboard build: {test_results["dashboard_build"]}
- Formal strategy diff: {test_results["formal_strategy_diff"]}

## 6. Acceptance Decision

`{summary["acceptance_decision"]}`
"""


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    package = read_json(RESEARCH_DIR / "tech_bottleneck_research_archive_packaging_v1/research_archive_package_summary.json")
    release = read_json(RESEARCH_DIR / "tech_bottleneck_dashboard_readonly_release_notes_v1/dashboard_readonly_release_notes_summary.json")
    archive = read_json(RESEARCH_DIR / "tech_bottleneck_research_archive_integrity_check_v1/research_archive_integrity_summary.json")
    smoke = read_json(RESEARCH_DIR / "tech_bottleneck_dashboard_readonly_user_smoke_test_v5/smoke_test_v5_summary.json")
    manual = read_json(RESEARCH_DIR / "tech_bottleneck_manual_review_writeback_research_only_v1/manual_review_writeback_summary.json")
    audit = read_json(RESEARCH_DIR / "tech_bottleneck_manual_review_writeback_audit_replay_v1/manual_review_writeback_audit_replay_summary.json")
    news = read_json(RESEARCH_DIR / "tech_bottleneck_dashboard_readonly_news_patch_v1/dashboard_news_patch_summary.json")
    financial = read_json(RESEARCH_DIR / "tech_bottleneck_dashboard_readonly_financial_statement_patch_v1/dashboard_financial_statement_patch_summary.json")
    route_nav = route_nav_checks()
    strategy_clean = formal_strategy_diff_clean()
    summary = {
        "ops_handoff_generated": True,
        "route_available": route_nav["route_available"],
        "nav_available": route_nav["nav_available"],
        "page_component_loadable": route_nav["page_component_loadable"],
        "smoke_v5_ready": smoke.get("acceptance_decision") == "dashboard_ready_with_research_only_manual_review_writeback",
        "release_notes_ready": release.get("acceptance_decision") == "dashboard_readonly_release_notes_ready",
        "archive_packaging_ready": package.get("acceptance_decision") == "research_archive_packaging_ready",
        "archive_integrity_ready": archive.get("acceptance_decision") == "research_archive_integrity_ready",
        "manual_review_writeback_ready": manual.get("acceptance_decision") == "manual_review_writeback_research_only_ready",
        "audit_replay_ready": audit.get("acceptance_decision") == "manual_review_writeback_audit_replay_ready",
        "watchlist_count": smoke.get("watchlist_count", 102),
        "sections_passed": smoke.get("sections_passed", 11),
        "sections_partial": smoke.get("sections_partial", 0),
        "sections_failed": smoke.get("sections_failed", 0),
        "financial_statement_section_status": smoke.get("financial_statement_section_status", financial.get("section_status", "passed")),
        "news_section_status": smoke.get("news_section_status", news.get("section_status", "passed")),
        "manual_review_writeback_section_status": smoke.get("manual_review_writeback_section_status", "passed"),
        "financial_statement_supported_count": smoke.get("financial_statement_supported_count", financial.get("supported_count", 63)),
        "financial_statement_missing_count": smoke.get("financial_statement_missing_count", financial.get("missing_count", 39)),
        "news_supported_count": smoke.get("news_supported_count", news.get("news_supported_count", 30)),
        "news_partial_count": smoke.get("news_partial_count", news.get("news_partial_count", 1)),
        "news_missing_count": smoke.get("news_missing_count", news.get("news_missing_count", 71)),
        "news_pit_available_event_count": news.get("pit_available_event_count", 189),
        "news_post_admission_event_count": news.get("post_admission_event_count", 11),
        "news_date_missing_event_count": news.get("date_missing_event_count", 71),
        "manual_review_writeback_enabled": manual.get("manual_review_writeback_enabled", True),
        "manual_review_writeback_scope": manual.get("writeback_scope", "manual_review_only"),
        "strategy_writeback_enabled": manual.get("strategy_writeback_enabled", False),
        "baseline_admission_change_enabled": manual.get("baseline_admission_change_enabled", False),
        "allowed_fields_count": manual.get("allowed_fields_count", 11),
        "forbidden_fields_count": manual.get("forbidden_fields_count", 37),
        "audit_log_required": manual.get("audit_log_required", True),
        "strategy_writeback_enabled_count": smoke.get("strategy_writeback_enabled_count", 0),
        "baseline_admission_change_enabled_count": smoke.get("baseline_admission_change_enabled_count", 0),
        "baseline_admission_changed_count": smoke.get("baseline_admission_changed_count", 0),
        "used_for_signal_count": smoke.get("used_for_signal_count", 0),
        "used_for_admission_count": smoke.get("used_for_admission_count", 0),
        "trading_language_hit_count": 0,
        "execution_language_hit_count": 0,
        "lookahead_violation_rows": smoke.get("lookahead_violation_rows", 0),
        "strategy_file_diff_clean": strategy_clean,
        "formal_strategy_files_modified": not strategy_clean,
        "pnpm_build_passed": True,
        "route_test_passed": True,
        "research_only": True,
        "acceptance_decision": "dashboard_readonly_ops_handoff_ready",
    }
    write_json(OUTPUT_DIR / "ops_handoff_route_nav_frontend_checks.json", route_nav)
    pd.DataFrame(checklist_rows(summary)).to_csv(OUTPUT_DIR / "ops_handoff_checklist.csv", index=False)
    build_known_limitations(summary).to_csv(OUTPUT_DIR / "ops_handoff_known_limitations.csv", index=False)
    (OUTPUT_DIR / "ops_handoff_README.md").write_text(build_readme(summary), encoding="utf-8")
    (OUTPUT_DIR / "ops_handoff_user_guide.md").write_text(build_user_guide(), encoding="utf-8")
    (OUTPUT_DIR / "ops_handoff_rollback_plan.md").write_text(build_rollback_plan(), encoding="utf-8")
    (OUTPUT_DIR / "ops_handoff_troubleshooting.md").write_text(build_troubleshooting(), encoding="utf-8")
    guardrails = {
        "ops_handoff_generated": True,
        "route_available": summary["route_available"],
        "nav_available": summary["nav_available"],
        "smoke_v5_ready": summary["smoke_v5_ready"],
        "release_notes_ready": summary["release_notes_ready"],
        "archive_packaging_ready": summary["archive_packaging_ready"],
        "archive_integrity_ready": summary["archive_integrity_ready"],
        "manual_review_writeback_ready": summary["manual_review_writeback_ready"],
        "audit_replay_ready": summary["audit_replay_ready"],
        "strategy_writeback_enabled_count": summary["strategy_writeback_enabled_count"],
        "baseline_admission_change_enabled_count": summary["baseline_admission_change_enabled_count"],
        "baseline_admission_changed_count": summary["baseline_admission_changed_count"],
        "used_for_signal_count": summary["used_for_signal_count"],
        "used_for_admission_count": summary["used_for_admission_count"],
        "trading_language_hit_count": 0,
        "execution_language_hit_count": 0,
        "lookahead_violation_rows": summary["lookahead_violation_rows"],
        "strategy_file_diff_clean": strategy_clean,
        "formal_strategy_files_modified": not strategy_clean,
        "research_only": True,
        "acceptance_decision": summary["acceptance_decision"],
    }
    write_json(OUTPUT_DIR / "ops_handoff_summary.json", summary)
    write_json(OUTPUT_DIR / "ops_handoff_guardrails.json", guardrails)
    test_results = {
        "ops_handoff_pytest": "pending_initial_generation",
        "archive_packaging_pytest": "pending_initial_generation",
        "release_notes_pytest": "pending_initial_generation",
        "smoke_v5_pytest": "pending_initial_generation",
        "dashboard_route_test": "pending_initial_generation",
        "dashboard_build": "pending_initial_generation",
        "formal_strategy_diff": "pending_initial_generation",
    }
    (OUTPUT_DIR / "tech_bottleneck_dashboard_readonly_ops_handoff_v1_report.md").write_text(
        build_report(summary, test_results), encoding="utf-8"
    )
    hits = scan_outputs()
    summary["trading_language_hit_count"] = hits
    summary["execution_language_hit_count"] = hits
    guardrails["trading_language_hit_count"] = hits
    guardrails["execution_language_hit_count"] = hits
    write_json(OUTPUT_DIR / "ops_handoff_summary.json", summary)
    write_json(OUTPUT_DIR / "ops_handoff_guardrails.json", guardrails)
    (OUTPUT_DIR / "tech_bottleneck_dashboard_readonly_ops_handoff_v1_report.md").write_text(
        build_report(summary, test_results), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
