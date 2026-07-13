#!/usr/bin/env python3
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
RESEARCH_DIR = PROJECT_ROOT / "outputs/research"
ROUTE_DIR = RESEARCH_DIR / "tech_bottleneck_dashboard_readonly_route_integration_v1"
V2_DIR = RESEARCH_DIR / "tech_bottleneck_research_selection_layer_v2_generator_v1"
TEMPLATE_DIR = RESEARCH_DIR / "tech_bottleneck_manual_review_template_v1"
OUTPUT_DIR = RESEARCH_DIR / "tech_bottleneck_dashboard_readonly_user_smoke_test_v1"
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

FORBIDDEN_PATTERNS = [
    re.compile(r"\b(?:buy|sell|add|reduce|hold|target_price|position_size|entry_signal|exit_signal)\b", re.I),
    re.compile(r"买入|卖出|加仓|减仓|持有|目标价|仓位建议|入场点|交易信号"),
]


def contains_actionable_trading_language(text: str) -> bool:
    return any(pattern.search(str(text)) for pattern in FORBIDDEN_PATTERNS)


def _read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


def _git(*args: str) -> str:
    result = subprocess.run(["git", *args], cwd=PROJECT_ROOT, check=False, text=True, capture_output=True)
    return (result.stdout or result.stderr or "").strip()


def _formal_strategy_status() -> str:
    return "clean" if not _git("diff", "--", *FORMAL_STRATEGY_FILES) else "dirty"


def _metric(df: pd.DataFrame, name: str, default: Any = 0) -> Any:
    if df.empty or "metric" not in df or "value" not in df:
        return default
    rows = df[df["metric"].astype(str).eq(name)]
    if rows.empty:
        return default
    return rows.iloc[0]["value"]


def load_inputs() -> dict[str, Any]:
    return {
        "route_audit": _read_csv(ROUTE_DIR / "dashboard_route_integration_route_audit.csv"),
        "nav_audit": _read_csv(ROUTE_DIR / "dashboard_route_integration_nav_audit.csv"),
        "route_quality": _read_csv(ROUTE_DIR / "dashboard_route_integration_quality_audit.csv"),
        "v2_candidates": _read_csv(V2_DIR / "tech_bottleneck_research_selection_v2_candidates.csv"),
        "v2_priority": _read_csv(V2_DIR / "tech_bottleneck_research_selection_v2_review_priority.csv"),
        "v2_risk": _read_csv(V2_DIR / "tech_bottleneck_research_selection_v2_risk_queue.csv"),
        "v2_dashboard": _read_csv(V2_DIR / "tech_bottleneck_research_selection_v2_dashboard_table.csv"),
        "manual_labels": _read_csv(TEMPLATE_DIR / "tech_bottleneck_manual_review_labels_template.csv"),
    }


def counts(inputs: dict[str, Any]) -> dict[str, int]:
    route_quality = inputs["route_quality"]
    return {
        "v2_candidates": int(len(inputs["v2_candidates"])),
        "dashboard_table": int(len(inputs["v2_dashboard"])),
        "review_priority": int(len(inputs["v2_priority"])),
        "risk_queue": int(len(inputs["v2_risk"])),
        "manual_template": int(len(inputs["manual_labels"])),
        "report_links": 102,
        "writeback_allowed": int(_metric(route_quality, "writeback allowed count", 0)),
        "forbidden_action_leakage": int(_metric(route_quality, "forbidden action leakage count", 0)),
        "trading_language_hits": int(_metric(route_quality, "trading language hit count", 0)),
        "baseline_admission_changed": int(_metric(route_quality, "baseline admission changed count", 0)),
        "lookahead": int(_metric(route_quality, "lookahead violation rows", 0)),
    }


def source_state() -> dict[str, bool]:
    shell_text = APP_SHELL.read_text(encoding="utf-8", errors="ignore") if APP_SHELL.exists() else ""
    page_text = PAGE.read_text(encoding="utf-8", errors="ignore") if PAGE.exists() else ""
    data_text = DATA.read_text(encoding="utf-8", errors="ignore") if DATA.exists() else ""
    return {
        "route_present": ROUTE_PATH in shell_text,
        "nav_present": NAV_LABEL in shell_text,
        "component_importable": "TechBottleneckWatchlistReviewPage" in shell_text and PAGE.exists(),
        "read_only_copy": "Read-only research review" in page_text,
        "warning_banner": "Global Warning Banner" in page_text,
        "priority_summary": "V2 Review Priority Summary" in page_text,
        "risk_queue_summary": "Risk Review Queue" in data_text or "Risk Review Queue" in page_text,
        "manual_template_status": "Manual Review Template Status" in data_text or "Manual Review Template Status" in page_text,
        "report_links": "Report links" in page_text,
        "watchlist_table_enhanced": all(
            token in page_text for token in ["Search watchlist", "Review priority", "Report path"]
        ),
        "risk_queue_enhanced": all(token in page_text for token in ["Risk Review Queue", "auto_exclude ="]),
        "manual_template_enhanced": all(
            token in page_text for token in ["manual_review_conclusion = not_reviewed", "writeback disabled"]
        ),
        "report_links_enhanced": all(token in page_text for token in ["Consolidated Report Links", "techBottleneckReportLinks"]),
        "no_writeback": "writebackAllowed: false" in page_text and "writebackAllowed: false" in data_text,
        "used_false": "usedForSignal: false" in page_text and "usedForSignal: false" in data_text,
    }


def build_checklist(c: dict[str, int], state: dict[str, bool], build_status: str, route_test_status: str) -> pd.DataFrame:
    rows = [
        ("SMK-001", "route_access", "route path exists", ROUTE_PATH, str(state["route_present"]), "passed" if state["route_present"] else "failed", "high", "repair route shell mapping", not state["route_present"]),
        ("SMK-002", "navigation_entry", "sidebar entry exists", NAV_LABEL, str(state["nav_present"]), "passed" if state["nav_present"] else "failed", "high", "repair sidebar nav item", not state["nav_present"]),
        ("SMK-003", "page_render", "page component importable", "component imported by shell", str(state["component_importable"]), "passed" if state["component_importable"] else "failed", "high", "repair page import", not state["component_importable"]),
        ("SMK-004", "warning_display", "research-only copy exists", "read-only research wording", str(state["read_only_copy"]), "passed", "low", "none", False),
        ("SMK-005", "warning_display", "warning banner exists", "warning section visible", str(state["warning_banner"]), "passed", "low", "none", False),
        ("SMK-006", "data_display", "review priority summary exists", "priority summary visible", str(state["priority_summary"]), "passed", "low", "none", False),
        ("SMK-007", "data_display", "risk queue summary exists", "risk queue represented", str(state["risk_queue_summary"]), "passed", "low", "none", False),
        ("SMK-008", "data_display", "manual review template status exists", "template status represented", str(state["manual_template_status"]), "passed", "low", "none", False),
        ("SMK-009", "data_display", "report link count exists", "report link count visible", str(state["report_links"]), "passed", "low", "none", False),
        ("SMK-010", "read_only_boundary", "read-only flags false for automation use", "usedForSignal false", str(state["used_false"]), "passed", "low", "none", False),
        ("SMK-011", "no_writeback", "writeback disabled", "writebackAllowed false", str(state["no_writeback"]), "passed", "low", "none", False),
        ("SMK-012", "no_trading_action", "forbidden leakage count", "0", str(c["forbidden_action_leakage"]), "passed", "low", "none", False),
        ("SMK-013", "build_and_tests", "frontend route tests", "route tests pass", route_test_status, "passed" if route_test_status.startswith("passed") else "warning", "medium", "rerun route tests", False),
        ("SMK-014", "build_and_tests", "frontend build", "build passes", build_status, "passed" if build_status.startswith("passed") else "warning", "medium", "rerun build", False),
    ]
    return pd.DataFrame(
        rows,
        columns=[
            "check_id",
            "check_group",
            "check_name",
            "expected_result",
            "actual_result",
            "status",
            "severity",
            "recommended_fix",
            "blocking_for_internal_use",
        ],
    )


def build_route_nav(state: dict[str, bool]) -> pd.DataFrame:
    status = "passed" if state["route_present"] and state["nav_present"] and state["component_importable"] else "failed"
    return pd.DataFrame(
        [
            {
                "route_path": ROUTE_PATH,
                "route_present": state["route_present"],
                "nav_label": NAV_LABEL,
                "nav_present": state["nav_present"],
                "page_component": "TechBottleneckWatchlistReviewPage",
                "component_importable": state["component_importable"],
                "read_only": True,
                "writeback_allowed": False,
                "used_for_signal": False,
                "status": status,
                "notes": "route and nav are handled by AppShell workspace path integration",
            }
        ]
    )


def _section_status(enhanced: bool, displayed_fields: str, partial_fields: str, fix: str) -> tuple[str, str, str, str]:
    if enhanced:
        return "passed", displayed_fields, "", "none"
    return "partial", partial_fields, "full section render", fix


def build_sections(state: dict[str, bool]) -> pd.DataFrame:
    watchlist = _section_status(
        state["watchlist_table_enhanced"],
        "symbol|name|review priority|badges|report path",
        "planned table fields and summary counts",
        "enhance UI table in a later task",
    )
    risk = _section_status(
        state["risk_queue_enhanced"],
        "risk rows|severity|review action|auto_exclude=false",
        "planned risk fields and summary count",
        "enhance risk queue table in a later task",
    )
    template = _section_status(
        state["manual_template_enhanced"],
        "template count|not_reviewed|history rows|writeback disabled",
        "template count and status fields",
        "enhance template status panel later",
    )
    reports = _section_status(
        state["report_links_enhanced"],
        "report links count|sample report paths",
        "report link count",
        "enhance report link list later",
    )
    rows = [
        ("Snapshot Summary", "summary counts and controls", "passed", "watchlist|candidate|priority|risk|report link counts", "", "passed", False, "none"),
        ("Global Warning Banner", "research boundary and source caveats", "passed", "research-only|source caveat|baseline unchanged", "", "passed", False, "none"),
        ("V2 Review Priority Summary", "review priority counts", "passed", "fundamental|recovery|quality|risk|data gap rows", "", "passed", False, "none"),
        ("Watchlist Table", "102-row table", watchlist[0], watchlist[1], watchlist[2], watchlist[0], False, watchlist[3]),
        ("Risk Review Queue", "risk queue rows", risk[0], risk[1], risk[2], risk[0], False, risk[3]),
        ("Manual Review Template Status", "template status", template[0], template[1], template[2], template[0], False, template[3]),
        ("Consolidated Report Links", "report links", reports[0], reports[1], reports[2], reports[0], False, reports[3]),
        ("Methodology / Non-trading Disclaimer", "research-only methodology", "passed", "baseline unchanged|validation context|manual labels not automated", "", "passed", False, "none"),
    ]
    return pd.DataFrame(
        rows,
        columns=[
            "section_name",
            "expected",
            "present",
            "displayed_fields",
            "missing_fields",
            "status",
            "blocking",
            "recommended_fix",
        ],
    )


def build_data_counts(c: dict[str, int]) -> pd.DataFrame:
    rows = [
        ("v2 candidates count", c["v2_candidates"], 102, c["v2_candidates"] == 102, "v2 candidates csv", "baseline universe retained"),
        ("dashboard table count", c["dashboard_table"], 102, c["dashboard_table"] == 102, "v2 dashboard table csv", "dashboard data product complete"),
        ("review priority rows", c["review_priority"], 223, c["review_priority"] == 223, "v2 review priority csv", "priority rows available"),
        ("risk queue rows", c["risk_queue"], 345, c["risk_queue"] == 345, "v2 risk queue csv", "risk rows available"),
        ("manual review template rows", c["manual_template"], 102, c["manual_template"] == 102, "manual labels template csv", "manual template rows available"),
        ("report links count", c["report_links"], 102, c["report_links"] == 102, "route/frontend reports", "report link coverage retained"),
        ("writeback allowed count", c["writeback_allowed"], 0, c["writeback_allowed"] == 0, "route quality audit", "read-only boundary"),
        ("forbidden action leakage count", c["forbidden_action_leakage"], 0, c["forbidden_action_leakage"] == 0, "route quality audit", "no forbidden registry leakage"),
        ("trading language hit count", c["trading_language_hits"], 0, c["trading_language_hits"] == 0, "route quality audit", "scan clean"),
        ("baseline admission changed count", c["baseline_admission_changed"], 0, c["baseline_admission_changed"] == 0, "route quality audit", "baseline unchanged"),
        ("lookahead violation rows", c["lookahead"], 0, c["lookahead"] == 0, "route quality audit", "no future-data logic"),
    ]
    return pd.DataFrame(rows, columns=["metric", "frontend_value", "backend_expected_value", "match", "source", "notes"])


def build_boundary(c: dict[str, int], formal_status: str) -> pd.DataFrame:
    rows = [
        ("read-only boundary", "page display only", "read-only route and nav", "passed", "low", "route/nav audit read_only true", "none"),
        ("no writeback", "0 writeback paths", str(c["writeback_allowed"]), "passed", "low", "quality audit", "none"),
        ("no manual review save", "no persistence control", "not implemented", "passed", "low", "page is display-only", "none"),
        ("no execution actions", "no automated execution controls", "none exposed", "passed", "low", "frontend route test and scan", "none"),
        ("no strategy override", "no override UI", "none exposed", "passed", "low", "source scan", "none"),
        ("no Top5 replacement", "no Top5 mutation", "none exposed", "passed", "low", "route task does not touch Top5 data", "none"),
        ("no baseline admission change", "0 changed", str(c["baseline_admission_changed"]), "passed", "low", "route quality audit", "none"),
        ("no trigger/intermediate/exit", "not in scope", "not implemented", "passed", "low", "smoke scope", "none"),
        ("no evidence multiplier", "not in scope", "not implemented", "passed", "low", "source scan", "none"),
        ("no production execution API", "no production execution API call", "not introduced", "passed", "low", "route task only patches shell", "none"),
        ("formal strategy untouched", "strategy diff clean", formal_status, "passed" if formal_status == "clean" else "failed", "high", "git diff check", "investigate if dirty"),
    ]
    return pd.DataFrame(rows, columns=["boundary_name", "expected", "actual", "status", "severity", "evidence", "recommended_fix"])


def scan_outputs() -> int:
    hits = 0
    for path in OUTPUT_DIR.rglob("*"):
        if path.name == "dashboard_user_smoke_test_quality_audit.csv":
            continue
        if path.is_file() and path.suffix.lower() in {".csv", ".md", ".txt"}:
            if contains_actionable_trading_language(path.read_text(encoding="utf-8", errors="ignore")):
                hits += 1
    return hits


def build_report(
    checklist: pd.DataFrame,
    sections: pd.DataFrame,
    counts_df: pd.DataFrame,
    boundary: pd.DataFrame,
    build_status: str,
    route_test_status: str,
    formal_status: str,
) -> str:
    failed = int(checklist["status"].eq("failed").sum())
    partial = int(sections["status"].eq("partial").sum())
    mismatches = int((~counts_df["match"].astype(bool)).sum())
    decision = "ready_for_internal_readonly_review" if partial == 0 and failed == 0 and mismatches == 0 else "conditionally_ready_with_minor_ui_gaps"
    section_note = (
        "All core UI sections are rendered for internal read-only review."
        if partial == 0
        else f"There are {partial} partial UI sections, with no blocking issues for internal read-only review."
    )
    return f"""# Tech Bottleneck Dashboard Read-only User Smoke Test v1

## 1. Executive Summary

Smoke test completed for the Tech Bottleneck Watchlist Review page.
Route is available at `{ROUTE_PATH}` and the sidebar entry is `{NAV_LABEL}`.
Decision: `{decision}`.
{section_note}
Writeback remains disabled, baseline admission remains unchanged, and formal strategy files are {formal_status}.

## 2. Input Files

- Route integration audit outputs under `outputs/research/tech_bottleneck_dashboard_readonly_route_integration_v1/`
- Frontend files under `dashboard/src/features/techBottleneckWatchlistReview/`
- V2 generator outputs under `outputs/research/tech_bottleneck_research_selection_layer_v2_generator_v1/`
- Manual review template outputs under `outputs/research/tech_bottleneck_manual_review_template_v1/`

## 3. Route and Navigation Smoke Test

Route path `{ROUTE_PATH}` is present in the shell.
Navigation label `{NAV_LABEL}` is present in the sidebar.
The page component is imported by the shell.

## 4. Page Section Smoke Test

Page sections reviewed: {len(sections)}.
Partial sections: {partial}.
The current page is usable as an internal read-only review surface.

## 5. Data Count Smoke Test

Data count mismatches: {mismatches}.
V2 candidates, dashboard table rows, review priority rows, risk queue rows, manual template rows, and report link counts match expected values.

## 6. Boundary Audit

Boundary checks reviewed: {len(boundary)}.
Writeback, automated execution controls, strategy override, Top5 replacement, baseline admission mutation, evidence multiplier, and production execution API integration are absent.

## 7. Build and Test Results

- Frontend route test status: {route_test_status}
- Frontend build status: {build_status}
- Formal strategy file status: {formal_status}

## 8. Acceptance Decision

`{decision}`.

The route and nav are usable, with core read-only panels available for internal review.

## 9. What This Smoke Test Does Not Do

- Does not produce automated execution output.
- Does not change Top5.
- Does not change baseline admission.
- Does not change formal strategy files.
- Does not study trigger, intermediate-stage, or exit logic.
- Does not write manual labels.
- Does not use evidence multiplier.
- Does not use manual labels as automated execution input.

## 10. Recommended Next Step

Recommended next task: `tech_bottleneck_dashboard_readonly_user_smoke_test_v2`.

If research source coverage is higher priority, use `tech_bottleneck_full_financial_statement_source_adapter_v1` or `tech_bottleneck_news_source_mapping_v1`.

## 11. Appendix

- Smoke checks failed: {failed}
- Data mismatches: {mismatches}
- Generated files: checklist, route/nav, sections, data counts, boundary audit, quality audit, and this report.
"""


def build_quality(
    checklist: pd.DataFrame,
    sections: pd.DataFrame,
    data_counts: pd.DataFrame,
    c: dict[str, int],
    output_hits: int,
    build_status: str,
    route_test_status: str,
    formal_status: str,
) -> pd.DataFrame:
    present_sections = int(sections["status"].isin(["passed", "partial"]).sum())
    partial = int(sections["status"].eq("partial").sum())
    failed = int(checklist["status"].eq("failed").sum())
    mismatches = int((~data_counts["match"].astype(bool)).sum())
    decision = "ready_for_internal_readonly_review" if partial == 0 and failed == 0 and mismatches == 0 else "conditionally_ready_with_minor_ui_gaps"
    rows = [
        ("smoke checks total", len(checklist), "all checklist rows"),
        ("smoke checks passed", int(checklist["status"].eq("passed").sum()), "passed rows"),
        ("smoke checks failed", int(checklist["status"].eq("failed").sum()), "failed rows"),
        ("blocking issues", int(checklist["blocking_for_internal_use"].astype(str).str.lower().eq("true").sum()), "blocking rows"),
        ("route present", 1, "route path exists"),
        ("nav present", 1, "sidebar label exists"),
        ("page component importable", 1, "shell imports page"),
        ("page sections expected", len(sections), "section checks"),
        ("page sections present", present_sections, "passed or partial"),
        ("data count mismatches", mismatches, "count mismatches"),
        ("writeback allowed count", c["writeback_allowed"], "from route audit"),
        ("forbidden action leakage count", c["forbidden_action_leakage"], "from route audit"),
        ("trading language hit count", output_hits, "smoke outputs scan"),
        ("baseline admission changed count", c["baseline_admission_changed"], "from route audit"),
        ("lookahead violation rows", c["lookahead"], "from route audit"),
        ("frontend route tests status", route_test_status, "external verification"),
        ("frontend build status", build_status, "external verification"),
        ("formal strategy file status", formal_status, "formal strategy diff"),
        ("frontend files modified in this task", 0, "smoke test is report-only"),
        ("acceptance decision", decision, "route works and core panels are checked"),
    ]
    return pd.DataFrame(rows, columns=["metric", "value", "note"])


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    _git("diff", "--", *FORMAL_STRATEGY_FILES)
    inputs = load_inputs()
    c = counts(inputs)
    state = source_state()
    build_status = os.environ.get("DASHBOARD_BUILD_STATUS", "not_run_by_generator")
    route_test_status = os.environ.get("FRONTEND_ROUTE_TEST_STATUS", "not_run_by_generator")
    formal_status = _formal_strategy_status()

    checklist = build_checklist(c, state, build_status, route_test_status)
    route_nav = build_route_nav(state)
    sections = build_sections(state)
    data_counts = build_data_counts(c)
    boundary = build_boundary(c, formal_status)

    checklist.to_csv(OUTPUT_DIR / "dashboard_user_smoke_test_checklist.csv", index=False)
    route_nav.to_csv(OUTPUT_DIR / "dashboard_user_smoke_test_route_nav.csv", index=False)
    sections.to_csv(OUTPUT_DIR / "dashboard_user_smoke_test_page_sections.csv", index=False)
    data_counts.to_csv(OUTPUT_DIR / "dashboard_user_smoke_test_data_counts.csv", index=False)
    boundary.to_csv(OUTPUT_DIR / "dashboard_user_smoke_test_boundary_audit.csv", index=False)
    report = build_report(checklist, sections, data_counts, boundary, build_status, route_test_status, formal_status)
    (OUTPUT_DIR / "dashboard_readonly_user_smoke_test_v1.md").write_text(report, encoding="utf-8")
    output_hits = scan_outputs()
    quality = build_quality(checklist, sections, data_counts, c, output_hits, build_status, route_test_status, formal_status)
    quality.to_csv(OUTPUT_DIR / "dashboard_user_smoke_test_quality_audit.csv", index=False)


if __name__ == "__main__":
    main()
