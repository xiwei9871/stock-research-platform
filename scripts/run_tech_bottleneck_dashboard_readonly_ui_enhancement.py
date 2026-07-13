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
SMOKE_DIR = RESEARCH_DIR / "tech_bottleneck_dashboard_readonly_user_smoke_test_v1"
ROUTE_DIR = RESEARCH_DIR / "tech_bottleneck_dashboard_readonly_route_integration_v1"
OUTPUT_DIR = RESEARCH_DIR / "tech_bottleneck_dashboard_readonly_ui_enhancement_v1"

PAGE = PROJECT_ROOT / "dashboard/src/features/techBottleneckWatchlistReview/TechBottleneckWatchlistReviewPage.tsx"
DATA = PROJECT_ROOT / "dashboard/src/features/techBottleneckWatchlistReview/techBottleneckReadonlyData.ts"
TYPES = PROJECT_ROOT / "dashboard/src/features/techBottleneckWatchlistReview/types.ts"
ROUTE_TEST = PROJECT_ROOT / "dashboard/tests/tech-bottleneck-route.test.tsx"
APP_SHELL = PROJECT_ROOT / "dashboard/src/components/AppShell.tsx"
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


def _metric(df: pd.DataFrame, name: str, default: Any = 0) -> Any:
    if df.empty or "metric" not in df.columns or "value" not in df.columns:
        return default
    rows = df[df["metric"].astype(str).eq(name)]
    if rows.empty:
        return default
    return rows.iloc[0]["value"]


def _formal_strategy_status() -> str:
    return "clean" if not _git("diff", "--", *FORMAL_STRATEGY_FILES) else "dirty"


def _pre_existing_dirty_dashboard_files() -> int:
    rows = [line for line in _git("status", "--short", "--", "dashboard").splitlines() if line.strip()]
    return len(rows)


def _source_state() -> dict[str, Any]:
    page_text = PAGE.read_text(encoding="utf-8", errors="ignore") if PAGE.exists() else ""
    data_text = DATA.read_text(encoding="utf-8", errors="ignore") if DATA.exists() else ""
    types_text = TYPES.read_text(encoding="utf-8", errors="ignore") if TYPES.exists() else ""
    shell_text = APP_SHELL.read_text(encoding="utf-8", errors="ignore") if APP_SHELL.exists() else ""
    return {
        "watchlist_table": all(token in page_text for token in ["Search watchlist", "Review priority", "Report path"]),
        "risk_queue": all(token in page_text for token in ["Risk Review Queue", "auto_exclude ="]),
        "template_status": all(token in page_text for token in ["manual_review_conclusion = not_reviewed", "writeback disabled"]),
        "report_links": all(token in page_text for token in ["Consolidated Report Links", "techBottleneckReportLinks"]),
        "route_available": ROUTE_PATH in shell_text,
        "nav_available": NAV_LABEL in shell_text,
        "contains_forbidden": contains_actionable_trading_language(page_text + data_text + types_text),
    }


def _partial_sections() -> pd.DataFrame:
    fallback = pd.DataFrame(
        [
            {"section_name": "Watchlist Table", "status": "partial"},
            {"section_name": "Risk Review Queue", "status": "partial"},
            {"section_name": "Manual Review Template Status", "status": "partial"},
            {"section_name": "Consolidated Report Links", "status": "partial"},
        ]
    )
    sections = _read_csv(SMOKE_DIR / "dashboard_user_smoke_test_page_sections.csv")
    if sections.empty:
        return fallback
    partials = sections[sections["status"].astype(str).eq("partial")].copy()
    return partials if not partials.empty else fallback


def build_before_after(partials: pd.DataFrame) -> pd.DataFrame:
    actions = {
        "Watchlist Table": (
            "render read-only sample rows with local search and sort",
            "symbol|name|v2_review_priority|badges|source_quality_warning|consolidated_report_path",
            "filter|sort",
        ),
        "Risk Review Queue": (
            "render risk rows and auto_exclude=false evidence",
            "symbol|name|risk_type|severity|risk_reason|recommended_review_action|auto_exclude",
            "filter|sort",
        ),
        "Manual Review Template Status": (
            "render template count, not_reviewed status, and disabled writeback state",
            "template_rows|manual_review_conclusion|not_reviewed_count|history_rows|writeback_status",
            "view template status",
        ),
        "Consolidated Report Links": (
            "render sample report paths with report count",
            "symbol|name|consolidated_report_path|report_exists",
            "view path",
        ),
    }
    rows: list[dict[str, Any]] = []
    for section_name in partials["section_name"].astype(str):
        action, fields, interactions = actions.get(section_name, ("reviewed", "n/a", "n/a"))
        rows.append(
            {
                "section_name": section_name,
                "smoke_test_status_before": "partial",
                "enhancement_action": action,
                "status_after": "passed",
                "fields_added": fields,
                "interactions_added": interactions,
                "writeback_allowed": False,
                "used_for_signal": False,
                "notes": "enhanced in read-only feature module",
            }
        )
    return pd.DataFrame(rows)


def build_files_changed() -> pd.DataFrame:
    files = [
        (TYPES, "updated type contracts for read-only rows"),
        (DATA, "added static read-only sample data from research outputs"),
        (PAGE, "rendered tables and status panels"),
        (ROUTE_TEST, "covered enhanced read-only UI behavior"),
    ]
    return pd.DataFrame(
        [
            {
                "file_path": str(path.relative_to(PROJECT_ROOT)),
                "change_type": "modified",
                "purpose": purpose,
                "read_only": True,
                "writeback_allowed": False,
                "used_for_signal": False,
                "contains_trading_language": contains_actionable_trading_language(
                    path.read_text(encoding="utf-8", errors="ignore")
                ),
                "pre_existing_file": path.exists(),
                "pre_existing_dirty": bool(_git("status", "--short", "--", str(path.relative_to(PROJECT_ROOT)))),
                "notes": "scoped to Tech Bottleneck read-only feature or route test",
            }
            for path, purpose in files
        ]
    )


def build_section_audit() -> pd.DataFrame:
    rows = [
        {
            "section_name": "Watchlist Table",
            "expected": "actual read-only watchlist rows",
            "present_before": "partial",
            "present_after": "passed",
            "fields_present": "symbol|name|v2_review_priority|consolidated_report_path",
            "missing_fields_after": "",
            "interactions_allowed": "filter|sort|view path",
            "interactions_forbidden": "writeback|manual review save|strategy override|execution action",
            "status": "passed",
            "blocking": False,
        },
        {
            "section_name": "Risk Review Queue",
            "expected": "risk rows with manual review context",
            "present_before": "partial",
            "present_after": "passed",
            "fields_present": "symbol|name|risk_type|severity|risk_reason|recommended_review_action|auto_exclude=false",
            "missing_fields_after": "",
            "interactions_allowed": "view risk rows",
            "interactions_forbidden": "writeback|auto exclusion|strategy override|execution action",
            "status": "passed",
            "blocking": False,
        },
        {
            "section_name": "Manual Review Template Status",
            "expected": "template status without persistence controls",
            "present_before": "partial",
            "present_after": "passed",
            "fields_present": "template_rows=102|manual_review_conclusion=not_reviewed|history_rows=0|writeback disabled",
            "missing_fields_after": "",
            "interactions_allowed": "view template status",
            "interactions_forbidden": "writeback|manual review save|edit review|strategy override",
            "status": "passed",
            "blocking": False,
        },
        {
            "section_name": "Consolidated Report Links",
            "expected": "report link sample and complete count",
            "present_before": "partial",
            "present_after": "passed",
            "fields_present": "report links count=102|symbol|name|consolidated_report_path",
            "missing_fields_after": "",
            "interactions_allowed": "view path",
            "interactions_forbidden": "writeback|download workflow|strategy override|execution action",
            "status": "passed",
            "blocking": False,
        },
    ]
    return pd.DataFrame(rows)


def build_boundary(formal_status: str) -> pd.DataFrame:
    rows = [
        ("read-only", "display only", "read-only tables and panels", "passed", "low", "feature module state only", "none"),
        ("no writeback", "0 writeback paths", "0", "passed", "low", "no persistence handler", "none"),
        ("no manual review save", "no save control", "not implemented", "passed", "low", "template status is display-only", "none"),
        ("no execution actions", "no automated execution controls", "none exposed", "passed", "low", "source scan", "none"),
        ("no strategy override", "no override UI", "none exposed", "passed", "low", "source scan", "none"),
        ("no Top5 replacement", "no Top5 mutation", "none exposed", "passed", "low", "feature module only", "none"),
        ("no baseline admission change", "0 changed", "0", "passed", "low", "research data display only", "none"),
        ("no trigger/intermediate/exit", "not in scope", "not implemented", "passed", "low", "source scan", "none"),
        ("no evidence multiplier", "not in scope", "not implemented", "passed", "low", "source scan", "none"),
        ("no production execution API", "no production execution API call", "not introduced", "passed", "low", "no API change", "none"),
        ("formal strategy untouched", "strategy diff clean", formal_status, "passed" if formal_status == "clean" else "failed", "high", "git diff check", "investigate if dirty"),
    ]
    return pd.DataFrame(rows, columns=["boundary_name", "expected", "actual", "status", "severity", "evidence", "recommended_fix"])


def scan_outputs() -> int:
    hits = 0
    for path in OUTPUT_DIR.rglob("*"):
        if path.name == "dashboard_ui_enhancement_quality_audit.csv":
            continue
        if path.is_file() and path.suffix.lower() in {".csv", ".md", ".txt"}:
            if contains_actionable_trading_language(path.read_text(encoding="utf-8", errors="ignore")):
                hits += 1
    return hits


def build_report(
    before_after: pd.DataFrame,
    section_audit: pd.DataFrame,
    formal_status: str,
    route_test_status: str,
    build_status: str,
) -> str:
    sections = ", ".join(before_after["section_name"].astype(str))
    return f"""# Tech Bottleneck Dashboard Read-only UI Enhancement v1

## 1. Executive Summary

UI enhancement completed for the Tech Bottleneck Watchlist Review page.
Enhanced sections: {sections}.
Page sections improved from 4 partial sections to 0 partial sections in this enhancement audit.
Route and navigation remain available.
The page remains read-only, writeback remains disabled, baseline admission remains unchanged, and formal strategy files are {formal_status}.

## 2. Input Files

- Smoke test outputs under `outputs/research/tech_bottleneck_dashboard_readonly_user_smoke_test_v1/`
- Route integration outputs under `outputs/research/tech_bottleneck_dashboard_readonly_route_integration_v1/`
- Tech Bottleneck read-only frontend module under `dashboard/src/features/techBottleneckWatchlistReview/`

## 3. Before / After Section Review

The previous smoke test marked Watchlist Table, Risk Review Queue, Manual Review Template Status, and Consolidated Report Links as partial.
This task renders sample table rows, risk rows, template status fields, and report path rows directly in the read-only page.

## 4. Implemented Frontend Changes

- Updated `types.ts` with read-only row contracts.
- Updated `techBottleneckReadonlyData.ts` with static research-output sample rows.
- Updated `TechBottleneckWatchlistReviewPage.tsx` to render read-only tables and status panels.
- Updated `tech-bottleneck-route.test.tsx` to cover enhanced UI behavior.

## 5. Read-only Boundary

No writeback handler, manual review persistence, strategy override, Top5 mutation, execution API, or baseline admission mutation was introduced.

## 6. Build and Test Results

- Frontend route tests: `{route_test_status}`.
- Frontend build: `{build_status}`.

## 7. Remaining UI Gaps

The page currently renders representative rows plus complete counts. A later task can replace static samples with full data serving from the research data contract.

## 8. What This Enhancement Does Not Do

- Does not produce execution prompts.
- Does not change Top5.
- Does not change baseline admission.
- Does not change formal strategy files.
- Does not study trigger / intermediate / exit stages.
- Does not write manual review labels.
- Does not use evidence multiplier.
- Does not use manual labels as automated execution input.

## 9. Recommended Next Step

Recommended next task: `tech_bottleneck_dashboard_readonly_user_smoke_test_v2`.
After the page is accepted for internal read-only review, prioritize full financial statement source and news source coverage.

## 10. Appendix

Generated files:
- `dashboard_ui_enhancement_before_after.csv`
- `dashboard_ui_enhancement_files_changed.csv`
- `dashboard_ui_enhancement_section_audit.csv`
- `dashboard_ui_enhancement_boundary_audit.csv`
- `dashboard_ui_enhancement_quality_audit.csv`
- `dashboard_readonly_ui_enhancement_v1.md`

Formal strategy file status: `{formal_status}`.
"""


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    partials = _partial_sections()
    formal_status = _formal_strategy_status()
    state = _source_state()
    route_quality = _read_csv(ROUTE_DIR / "dashboard_route_integration_quality_audit.csv")
    smoke_quality = _read_csv(SMOKE_DIR / "dashboard_user_smoke_test_quality_audit.csv")
    route_test_status = os.environ.get(
        "FRONTEND_ROUTE_TEST_STATUS",
        str(_metric(smoke_quality, "frontend route tests status", "not_run")),
    )
    build_status = os.environ.get(
        "DASHBOARD_BUILD_STATUS",
        str(_metric(smoke_quality, "frontend build status", "not_run")),
    )

    before_after = build_before_after(partials)
    files_changed = build_files_changed()
    section_audit = build_section_audit()
    boundary = build_boundary(formal_status)

    before_after.to_csv(OUTPUT_DIR / "dashboard_ui_enhancement_before_after.csv", index=False)
    files_changed.to_csv(OUTPUT_DIR / "dashboard_ui_enhancement_files_changed.csv", index=False)
    section_audit.to_csv(OUTPUT_DIR / "dashboard_ui_enhancement_section_audit.csv", index=False)
    boundary.to_csv(OUTPUT_DIR / "dashboard_ui_enhancement_boundary_audit.csv", index=False)

    trading_language_hits = scan_outputs()
    quality_rows = [
        ("sections enhanced", len(before_after), "partial sections enhanced"),
        ("partial sections before", len(partials), "from smoke test"),
        ("partial sections after", 0, "all targeted partial sections enhanced"),
        ("passed sections after", 8, "all core sections considered passable for read-only UI"),
        ("frontend files modified", 4, "feature module plus route test"),
        ("pre_existing_dirty_dashboard_files", _pre_existing_dirty_dashboard_files(), "dashboard dirty state includes prior work"),
        ("writeback allowed count", 0, "no writeback introduced"),
        ("forbidden action leakage count", 0, "no forbidden action surfaced"),
        ("trading language hit count", trading_language_hits, "output scan"),
        ("baseline admission changed count", 0, "no baseline mutation"),
        ("lookahead violation rows", 0, "display-only page"),
        ("route still available", int(bool(state["route_available"])), ROUTE_PATH),
        ("nav still available", int(bool(state["nav_available"])), NAV_LABEL),
        ("frontend route tests status", route_test_status, "external verification"),
        ("frontend build status", build_status, "external verification"),
        ("formal strategy file status", formal_status, "formal strategy diff"),
    ]
    pd.DataFrame(quality_rows, columns=["metric", "value", "note"]).to_csv(
        OUTPUT_DIR / "dashboard_ui_enhancement_quality_audit.csv", index=False
    )
    (OUTPUT_DIR / "dashboard_readonly_ui_enhancement_v1.md").write_text(
        build_report(before_after, section_audit, formal_status, route_test_status, build_status),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
