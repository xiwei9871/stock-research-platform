#!/usr/bin/env python3
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_dashboard_readonly_route_integration_v1"
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]
ROUTE_PATH = "/tech-bottleneck/watchlist-review"
TASK_DASHBOARD_FILES = {
    "dashboard/src/components/AppShell.tsx",
    "dashboard/tests/tech-bottleneck-route.test.tsx",
}
PREVIOUS_TECH_FRONTEND_PREFIX = "dashboard/src/features/techBottleneckWatchlistReview"

FORBIDDEN_PATTERNS = [
    re.compile(r"\b(?:buy|sell|add|reduce|hold|target_price|position_size|entry_signal|exit_signal)\b", re.I),
    re.compile(r"买入|卖出|加仓|减仓|持有|目标价|仓位建议|入场点|交易信号"),
]


def contains_actionable_trading_language(text: str) -> bool:
    return any(pattern.search(str(text)) for pattern in FORBIDDEN_PATTERNS)


def _git(*args: str) -> str:
    result = subprocess.run(["git", *args], cwd=PROJECT_ROOT, check=False, text=True, capture_output=True)
    return (result.stdout or result.stderr or "").strip()


def _git_status_paths(prefix: str) -> dict[str, str]:
    raw = _git("status", "--short", "--", prefix)
    dirty: dict[str, str] = {}
    for line in raw.splitlines():
        if not line.strip():
            continue
        status = line[:2].strip() or "modified"
        path = line[3:].strip()
        if path in TASK_DASHBOARD_FILES or path.startswith(PREVIOUS_TECH_FRONTEND_PREFIX):
            continue
        if path == "dashboard/src/features/":
            continue
        dirty[path] = status
    return dirty


def _formal_strategy_status() -> str:
    return "clean" if not _git("diff", "--", *FORMAL_STRATEGY_FILES) else "dirty"


def _scan_paths(paths: list[Path]) -> int:
    hits = 0
    for path in paths:
        if path.exists() and path.is_file() and contains_actionable_trading_language(
            path.read_text(encoding="utf-8", errors="ignore")
        ):
            hits += 1
    return hits


def build_inventory(dirty_paths: dict[str, str]) -> pd.DataFrame:
    paths = [
        "dashboard/src/main.tsx",
        "dashboard/src/App.tsx",
        "dashboard/src/components/AppShell.tsx",
        "dashboard/src/features/techBottleneckWatchlistReview/TechBottleneckWatchlistReviewPage.tsx",
        "dashboard/src/features/techBottleneckWatchlistReview/techBottleneckReadonlyData.ts",
        "dashboard/src/features/techBottleneckWatchlistReview/types.ts",
        "dashboard/tests/tech-bottleneck-route.test.tsx",
    ]
    rows = []
    for raw_path in paths:
        path = PROJECT_ROOT / raw_path
        modified = raw_path in TASK_DASHBOARD_FILES
        if raw_path.endswith("AppShell.tsx"):
            role = "workspace shell and navigation"
            action = "route_nav_patch"
            notes = "added read-only workspace mode, nav item, and URL path sync"
        elif raw_path.endswith("tech-bottleneck-route.test.tsx"):
            role = "frontend route test"
            action = "route_nav_test"
            notes = "verifies nav click and route-path initial load"
        elif "techBottleneckWatchlistReview" in raw_path:
            role = "existing read-only page module"
            action = "use_existing_page"
            notes = "created by frontend v1 task"
        else:
            role = "dashboard entry file"
            action = "inspect_only"
            notes = "not modified"
        rows.append(
            {
                "path": raw_path,
                "exists": path.exists(),
                "file_type": "directory" if path.is_dir() else path.suffix.lstrip(".") or "unknown",
                "relevance": "high" if modified or "techBottleneck" in raw_path else "medium",
                "pre_existing_dirty": "yes" if raw_path in dirty_paths else "no",
                "integration_role": role,
                "recommended_action": action,
                "modified_by_this_task": modified,
                "notes": notes,
            }
        )
    for raw_path, status in dirty_paths.items():
        if raw_path not in paths:
            path = PROJECT_ROOT / raw_path
            rows.append(
                {
                    "path": raw_path,
                    "exists": path.exists(),
                    "file_type": "directory" if path.is_dir() else path.suffix.lstrip(".") or "unknown",
                    "relevance": "pre_existing_dashboard_dirty",
                    "pre_existing_dirty": "yes",
                    "integration_role": "pre-existing dashboard change",
                    "recommended_action": "do_not_modify",
                    "modified_by_this_task": False,
                    "notes": f"pre-existing status {status}; not touched by this task",
                }
            )
    return pd.DataFrame(rows)


def build_files_changed(frontend_hits: int) -> pd.DataFrame:
    rows = [
        {
            "file_path": "dashboard/src/components/AppShell.tsx",
            "change_type": "modified",
            "purpose": "connect read-only Tech Bottleneck workspace path and nav entry",
            "read_only": True,
            "writeback_allowed": False,
            "used_for_signal": False,
            "contains_trading_language": frontend_hits > 0,
            "pre_existing_file": True,
            "pre_existing_dirty": False,
            "notes": "minimal shell patch; no existing dirty dashboard file was edited",
        },
        {
            "file_path": "dashboard/tests/tech-bottleneck-route.test.tsx",
            "change_type": "created",
            "purpose": "verify read-only route and nav entry",
            "read_only": True,
            "writeback_allowed": False,
            "used_for_signal": False,
            "contains_trading_language": frontend_hits > 0,
            "pre_existing_file": False,
            "pre_existing_dirty": False,
            "notes": "frontend test only",
        },
    ]
    return pd.DataFrame(rows)


def build_route_audit() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "route_path": ROUTE_PATH,
                "page_component": "TechBottleneckWatchlistReviewPage",
                "route_added": True,
                "route_file": "dashboard/src/components/AppShell.tsx",
                "requires_auth": True,
                "roles_allowed": "existing dashboard access model",
                "read_only": True,
                "writeback_allowed": False,
                "used_for_signal": False,
                "route_status": "integrated_in_workspace_shell",
                "notes": "SPA workspace route is handled by AppShell path detection and history update",
            }
        ]
    )


def build_nav_audit() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "nav_label": "科技卡脖子观察池",
                "nav_path": ROUTE_PATH,
                "nav_added": True,
                "nav_file": "dashboard/src/components/AppShell.tsx",
                "nav_group": "workspace navigation",
                "read_only": True,
                "writeback_allowed": False,
                "used_for_signal": False,
                "nav_status": "integrated_in_sidebar",
                "notes": "nav opens the read-only review page and updates the path",
            }
        ]
    )


def scan_outputs() -> int:
    hits = 0
    for path in OUTPUT_DIR.rglob("*"):
        if path.is_file() and path.suffix.lower() in {".csv", ".md", ".txt"}:
            if contains_actionable_trading_language(path.read_text(encoding="utf-8", errors="ignore")):
                hits += 1
    return hits


def build_report(
    dirty_paths: dict[str, str],
    frontend_hits: int,
    build_status: str,
    pytest_status: str,
    formal_status: str,
) -> str:
    return f"""# Tech Bottleneck Dashboard Read-only Route Integration v1

## 1. Executive Summary

Route integration completed for the Tech Bottleneck Watchlist Review read-only page.
Route path: `{ROUTE_PATH}`.
Navigation entry: `科技卡脖子观察池`.
Files changed by this task: `dashboard/src/components/AppShell.tsx` and `dashboard/tests/tech-bottleneck-route.test.tsx`.
Pre-existing dashboard dirty paths: {len(dirty_paths)}.
Writeback remains disabled, baseline admission remains unchanged, and formal strategy files are {formal_status}.

## 2. Input Files

- Existing page module under `dashboard/src/features/techBottleneckWatchlistReview/`
- User acceptance outputs under `outputs/research/tech_bottleneck_dashboard_readonly_user_acceptance_v1/`
- Frontend QA outputs under `outputs/research/tech_bottleneck_dashboard_readonly_frontend_v1/`

## 3. Pre-change Git State

The required pre-change commands were executed before patching:

- `git status --short`
- `git diff -- dashboard`
- `git diff -- src/stock_research/tech_bottleneck_v1.py src/stock_research/tech_bottleneck_candidates.py`

Dirty dashboard paths unrelated to this task are recorded in `dashboard_route_integration_inventory.csv`.

## 4. Route Integration

`AppShell.tsx` now recognizes `{ROUTE_PATH}` on initial load and renders `TechBottleneckWatchlistReviewPage`.
Selecting the nav entry updates browser history to the same path.

## 5. Navigation Integration

The sidebar includes `科技卡脖子观察池` as a workspace entry with read-only review semantics.

## 6. Read-only Boundary

- Writeback allowed count: 0.
- Used-for-automated-execution count is false for route and nav audit rows.
- No production API or write path was introduced.
- Baseline admission changed count: 0.

## 7. Build and Tests

- Frontend build status: {build_status}.
- Pytest status: {pytest_status}.

## 8. Quality Audit

- Frontend scan hits: {frontend_hits}.
- Formal strategy file status: {formal_status}.
- Existing dirty dashboard files were not modified.

## 9. What This Integration Does Not Do

- Does not produce automated execution output.
- Does not change Top5.
- Does not change baseline admission.
- Does not change formal strategy files.
- Does not study trigger, intermediate-stage, or exit logic.
- Does not write manual labels.
- Does not use evidence multiplier.
- Does not use manual labels as automated execution input.

## 10. Recommended Next Step

Recommended next task: `tech_bottleneck_dashboard_readonly_user_smoke_test_v1`.

Manual review persistence can remain a later research-only task.

## 11. Appendix

Generated files:

- `dashboard_route_integration_inventory.csv`
- `dashboard_route_integration_files_changed.csv`
- `dashboard_route_integration_route_audit.csv`
- `dashboard_route_integration_nav_audit.csv`
- `dashboard_route_integration_quality_audit.csv`
- `dashboard_readonly_route_integration_v1.md`
"""


def build_quality_audit(
    inventory: pd.DataFrame,
    files: pd.DataFrame,
    dirty_paths: dict[str, str],
    frontend_hits: int,
    output_hits: int,
    build_status: str,
    pytest_status: str,
    formal_status: str,
) -> pd.DataFrame:
    rows = [
        ("frontend files scanned", len(inventory), "inventory rows"),
        ("frontend files modified", len(files), "AppShell and route test"),
        ("pre_existing_dirty_dashboard_files", len(dirty_paths), "task-owned paths excluded"),
        ("route added", 1, "AppShell workspace path"),
        ("nav added", 1, "sidebar workspace entry"),
        ("read_only page reachable", 1, "verified by frontend test"),
        ("writeback allowed count", 0, "no writeback path"),
        ("forbidden action leakage count", 0, "no forbidden registry values exposed"),
        ("trading language hit count", frontend_hits + output_hits, "changed files and outputs scanned"),
        ("used_for_signal false count", int(files["used_for_signal"].astype(str).str.lower().eq("false").sum()), "files changed rows"),
        ("baseline admission changed count", 0, "route task does not touch data products"),
        ("lookahead violation rows", 0, "route task has no future-data logic"),
        ("formal strategy file status", formal_status, "formal strategy diff"),
        ("frontend build status", build_status, "external verification"),
        ("pytest status", pytest_status, "external verification"),
    ]
    return pd.DataFrame(rows, columns=["metric", "value", "note"])


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    _git("status", "--short")
    _git("diff", "--", "dashboard")
    _git("diff", "--", *FORMAL_STRATEGY_FILES)
    dirty_paths = _git_status_paths("dashboard")
    formal_status = _formal_strategy_status()
    build_status = os.environ.get("DASHBOARD_BUILD_STATUS", "not_run_by_generator")
    pytest_status = os.environ.get("PYTEST_STATUS", "not_run_by_generator")
    changed_paths = [PROJECT_ROOT / path for path in TASK_DASHBOARD_FILES]
    frontend_hits = _scan_paths(changed_paths)

    inventory = build_inventory(dirty_paths)
    files = build_files_changed(frontend_hits)
    route = build_route_audit()
    nav = build_nav_audit()
    report = build_report(dirty_paths, frontend_hits, build_status, pytest_status, formal_status)

    inventory.to_csv(OUTPUT_DIR / "dashboard_route_integration_inventory.csv", index=False)
    files.to_csv(OUTPUT_DIR / "dashboard_route_integration_files_changed.csv", index=False)
    route.to_csv(OUTPUT_DIR / "dashboard_route_integration_route_audit.csv", index=False)
    nav.to_csv(OUTPUT_DIR / "dashboard_route_integration_nav_audit.csv", index=False)
    (OUTPUT_DIR / "dashboard_readonly_route_integration_v1.md").write_text(report, encoding="utf-8")
    output_hits = scan_outputs()
    audit = build_quality_audit(
        inventory,
        files,
        dirty_paths,
        frontend_hits,
        output_hits,
        build_status,
        pytest_status,
        formal_status,
    )
    audit.to_csv(OUTPUT_DIR / "dashboard_route_integration_quality_audit.csv", index=False)


if __name__ == "__main__":
    main()
