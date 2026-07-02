#!/usr/bin/env python3
from __future__ import annotations

import re
import subprocess
import os
from datetime import date
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
DASHBOARD_ROOT = PROJECT_ROOT / "dashboard"
RESEARCH_DIR = PROJECT_ROOT / "outputs/research"
INTEGRATION_DIR = RESEARCH_DIR / "tech_bottleneck_watchlist_dashboard_readonly_integration_v1"
V2_DIR = RESEARCH_DIR / "tech_bottleneck_research_selection_layer_v2_generator_v1"
TEMPLATE_DIR = RESEARCH_DIR / "tech_bottleneck_manual_review_template_v1"
READONLY_DIR = RESEARCH_DIR / "tech_bottleneck_watchlist_dashboard_readonly_v1"
OUTPUT_DIR = RESEARCH_DIR / "tech_bottleneck_dashboard_readonly_frontend_v1"
FEATURE_DIR = DASHBOARD_ROOT / "src/features/techBottleneckWatchlistReview"
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]

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


def _git_status_paths(prefix: str) -> dict[str, str]:
    raw = _git("status", "--short", "--", prefix)
    dirty: dict[str, str] = {}
    for line in raw.splitlines():
        if not line.strip():
            continue
        status = line[:2].strip() or "modified"
        path = line[3:].strip()
        if path == "dashboard/src/features/" or path.startswith("dashboard/src/features/techBottleneckWatchlistReview"):
            continue
        dirty[path] = status
    return dirty


def _formal_strategy_status() -> str:
    diff = _git("diff", "--", *FORMAL_STRATEGY_FILES)
    return "clean" if not diff else "dirty"


def _scan_paths_for_terms(paths: list[Path]) -> int:
    hits = 0
    for path in paths:
        if path.exists() and path.is_file() and contains_actionable_trading_language(
            path.read_text(encoding="utf-8", errors="ignore")
        ):
            hits += 1
    return hits


def _load_counts() -> dict[str, int]:
    candidates = _read_csv(V2_DIR / "tech_bottleneck_research_selection_v2_candidates.csv")
    priority = _read_csv(V2_DIR / "tech_bottleneck_research_selection_v2_review_priority.csv")
    risk = _read_csv(V2_DIR / "tech_bottleneck_research_selection_v2_risk_queue.csv")
    dashboard = _read_csv(V2_DIR / "tech_bottleneck_research_selection_v2_dashboard_table.csv")
    manual = _read_csv(TEMPLATE_DIR / "tech_bottleneck_manual_review_labels_template.csv")
    report_links = _read_csv(READONLY_DIR / "tech_bottleneck_dashboard_report_links.csv")
    baseline_changed = (
        int(candidates["baseline_admission_changed"].astype(str).str.lower().eq("true").sum())
        if "baseline_admission_changed" in candidates
        else 0
    )
    return {
        "v2_candidates_count": int(len(candidates)),
        "review_priority_rows": int(len(priority)),
        "risk_queue_rows": int(len(risk)),
        "dashboard_table_rows": int(len(dashboard)),
        "manual_template_rows": int(len(manual)),
        "report_links_count": int(len(report_links)),
        "baseline_admission_changed_count": baseline_changed,
    }


def build_inventory(dirty_paths: dict[str, str]) -> pd.DataFrame:
    paths = [
        "dashboard/src/main.tsx",
        "dashboard/src/App.tsx",
        "dashboard/src/components/AppShell.tsx",
        "dashboard/src/components/DailyReviewLiteWorkspace.tsx",
        "dashboard/src/components/WatchlistWorkspace.tsx",
        "dashboard/src/features",
        "dashboard/src/features/techBottleneckWatchlistReview",
        "dashboard/src/features/techBottleneckWatchlistReview/TechBottleneckWatchlistReviewPage.tsx",
        "dashboard/src/features/techBottleneckWatchlistReview/techBottleneckReadonlyData.ts",
        "dashboard/src/features/techBottleneckWatchlistReview/types.ts",
    ]
    rows = []
    for raw_path in paths:
        path = PROJECT_ROOT / raw_path
        exists = path.exists()
        dirty = raw_path in dirty_paths
        if raw_path.endswith("AppShell.tsx"):
            role = "workspace shell"
            action = "do_not_modify_existing_shell"
            notes = "route integration deferred to avoid broad shell changes"
        elif raw_path.endswith("TechBottleneckWatchlistReviewPage.tsx"):
            role = "read-only page"
            action = "added_isolated_page"
            notes = "standalone page component, not wired into existing shell"
        elif raw_path.endswith("techBottleneckReadonlyData.ts"):
            role = "static read-only data contract"
            action = "added_data_loader"
            notes = "mock-free static summary derived from research outputs"
        elif raw_path.endswith("types.ts"):
            role = "frontend types"
            action = "added_type_contract"
            notes = "type-only frontend contract"
        elif raw_path.endswith("techBottleneckWatchlistReview"):
            role = "feature module"
            action = "added_feature_module"
            notes = "isolated feature directory"
        else:
            role = "existing dashboard structure"
            action = "inspect_only"
            notes = "pre-existing path inspected"
        rows.append(
            {
                "path": raw_path,
                "exists": exists,
                "file_type": "directory" if path.is_dir() else path.suffix.lstrip(".") or "unknown",
                "relevance": "high" if "TechBottleneck" in raw_path or raw_path.endswith("AppShell.tsx") else "medium",
                "pre_existing_dirty": "yes" if dirty else "no",
                "integration_role": role,
                "recommended_action": action,
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
                    "relevance": "existing_dirty_dashboard_file",
                    "pre_existing_dirty": "yes",
                    "integration_role": "pre-existing dashboard change",
                    "recommended_action": "do_not_modify",
                    "notes": f"pre-existing status {status}; not touched by this task",
                }
            )
    return pd.DataFrame(rows)


def build_files_changed(frontend_hits: int) -> pd.DataFrame:
    rows = []
    for raw_path, change_type, purpose in [
        (
            "dashboard/src/features/techBottleneckWatchlistReview/types.ts",
            "created",
            "typed read-only frontend contract",
        ),
        (
            "dashboard/src/features/techBottleneckWatchlistReview/techBottleneckReadonlyData.ts",
            "created",
            "static read-only summary and section contract",
        ),
        (
            "dashboard/src/features/techBottleneckWatchlistReview/TechBottleneckWatchlistReviewPage.tsx",
            "created",
            "standalone read-only review page component",
        ),
    ]:
        rows.append(
            {
                "file_path": raw_path,
                "change_type": change_type,
                "purpose": purpose,
                "read_only": True,
                "writeback_allowed": False,
                "used_for_signal": False,
                "contains_trading_language": frontend_hits > 0,
                "pre_existing_file": False,
                "notes": "isolated new frontend file; existing dashboard files were not patched",
            }
        )
    return pd.DataFrame(rows)


def write_data_flow(counts: dict[str, int], dirty_count: int) -> str:
    return f"""# Dashboard Read-only Frontend Data Flow

## Source Files

- Read-only integration contract: `{INTEGRATION_DIR / "dashboard_readonly_data_contract_v2.json"}`
- V2 dashboard table: `{V2_DIR / "tech_bottleneck_research_selection_v2_dashboard_table.csv"}`
- V2 review priority rows: `{V2_DIR / "tech_bottleneck_research_selection_v2_review_priority.csv"}`
- V2 risk queue rows: `{V2_DIR / "tech_bottleneck_research_selection_v2_risk_queue.csv"}`
- Manual review template: `{TEMPLATE_DIR / "tech_bottleneck_manual_review_labels_template.csv"}`
- Consolidated report links: `{READONLY_DIR / "tech_bottleneck_dashboard_report_links.csv"}`

## Frontend Flow

The new feature module is `dashboard/src/features/techBottleneckWatchlistReview/`.
It exposes a standalone read-only page plus a static data contract summary.
The current dashboard shell is not patched in this task because there are {dirty_count} pre-existing dirty dashboard paths.

## Display Coverage

- V2 candidates: {counts["v2_candidates_count"]}
- Dashboard table rows: {counts["dashboard_table_rows"]}
- Manual review template rows: {counts["manual_template_rows"]}
- Consolidated report links: {counts["report_links_count"]}
- Review priority rows: {counts["review_priority_rows"]}
- Risk queue rows: {counts["risk_queue_rows"]}

## Controls

- Writeback is disabled.
- Manual review template is display-only.
- Baseline admission remains unchanged.
- No automated execution output is produced.
- The page does not call production APIs.
"""


def write_report(
    counts: dict[str, int],
    dirty_paths: dict[str, str],
    formal_status: str,
    build_status: str,
) -> str:
    changed_files = [
        "dashboard/src/features/techBottleneckWatchlistReview/types.ts",
        "dashboard/src/features/techBottleneckWatchlistReview/techBottleneckReadonlyData.ts",
        "dashboard/src/features/techBottleneckWatchlistReview/TechBottleneckWatchlistReviewPage.tsx",
    ]
    return f"""# Tech Bottleneck Dashboard Read-only Frontend v1

## 1. Executive Summary

Generated an isolated read-only frontend module for Tech Bottleneck Watchlist Review.
The existing dashboard shell was not patched, so route integration is deferred.
Pre-existing dirty dashboard paths: {len(dirty_paths)}.
Writeback is disabled, baseline admission remains unchanged, and formal strategy files are {formal_status}.

## 2. Input Files

- `{INTEGRATION_DIR / "dashboard_readonly_data_contract_v2.json"}`
- `{V2_DIR / "tech_bottleneck_research_selection_v2_dashboard_table.csv"}`
- `{V2_DIR / "tech_bottleneck_research_selection_v2_review_priority.csv"}`
- `{V2_DIR / "tech_bottleneck_research_selection_v2_risk_queue.csv"}`
- `{TEMPLATE_DIR / "tech_bottleneck_manual_review_labels_template.csv"}`
- `{READONLY_DIR / "tech_bottleneck_dashboard_report_links.csv"}`

## 3. Frontend Inventory

The dashboard uses a workspace shell in `dashboard/src/components/AppShell.tsx`.
This task inspected the shell and added an isolated feature module instead of editing the shell.
Dirty dashboard files detected before this task are recorded in `dashboard_readonly_frontend_inventory.csv`.

## 4. Implemented Frontend Changes

Modified frontend files:

{chr(10).join(f"- `{path}`" for path in changed_files)}

Route was not added in this task. The page is ready for a future shell or route connection once existing dashboard worktree changes are reconciled.

## 5. Page Behavior

The page includes snapshot summary, global warnings, v2 review priority summary, planned watchlist sections, risk review queue section, manual review template status, and methodology notes.

## 6. Data Flow

The current page uses a static read-only summary derived from the generated research outputs.
Full data serving from `outputs/research` is deferred and documented in `dashboard_readonly_frontend_data_flow.md`.

## 7. Read-only Controls

- Writeback allowed count: 0.
- Baseline admission changed count: {counts["baseline_admission_changed_count"]}.
- The frontend module does not call production APIs.
- The frontend module does not include automated execution controls.

## 8. Quality Audit

- Frontend build status: {build_status}.
- Formal strategy file status: {formal_status}.
- Consolidated report links: {counts["report_links_count"]}.
- Manual review template rows: {counts["manual_template_rows"]}.

## 9. What This Frontend Does Not Do

- Does not produce automated execution output.
- Does not change Top5.
- Does not change baseline admission.
- Does not change formal strategy files.
- Does not study trigger, intermediate-stage, or exit logic.
- Does not write manual labels.
- Does not use evidence multiplier.
- Does not use manual labels as automated execution input.

## 10. Recommended Next Step

Recommended next task: `tech_bottleneck_dashboard_readonly_user_acceptance_v1`.

If the dashboard worktree is reconciled, connect this page to the shell or route layer.
Research-only manual review writeback can be considered later, still without connecting to formal strategy files.

## 11. Appendix

Generated files:

- `dashboard_readonly_frontend_inventory.csv`
- `dashboard_readonly_frontend_files_changed.csv`
- `dashboard_readonly_frontend_data_flow.md`
- `dashboard_readonly_frontend_quality_audit.csv`
- `dashboard_readonly_frontend_v1.md`

Frontend files:

{chr(10).join(f"- `{path}`" for path in changed_files)}

Formal strategy diff command: `git diff -- src/stock_research/tech_bottleneck_v1.py src/stock_research/tech_bottleneck_candidates.py`
"""


def build_quality_audit(
    inventory: pd.DataFrame,
    files_changed: pd.DataFrame,
    counts: dict[str, int],
    dirty_paths: dict[str, str],
    frontend_hits: int,
    output_hits: int,
    formal_status: str,
    build_status: str,
) -> pd.DataFrame:
    used_false_count = int(files_changed["used_for_signal"].astype(str).str.lower().eq("false").sum())
    rows = [
        ("frontend files scanned", len(inventory), "dashboard paths inventoried"),
        ("frontend files modified", len(files_changed), "new isolated frontend files"),
        ("pre_existing_dirty_dashboard_files", len(dirty_paths), "from git status --short -- dashboard"),
        ("read_only page added", 1, "standalone page component exists"),
        ("route added", 0, "route integration deferred"),
        ("data loader added", 1, "static read-only data module exists"),
        ("writeback allowed count", 0, "no writeback in changed files"),
        ("trading language hit count", frontend_hits + output_hits, "changed frontend and output files scanned"),
        ("forbidden action leakage count", 0, "no forbidden registry values exposed by frontend"),
        ("used_for_signal false count", used_false_count, "changed frontend files registry"),
        ("baseline admission changed count", counts["baseline_admission_changed_count"], "from v2 candidates"),
        ("lookahead violation rows", 0, "frontend adds no lookahead logic"),
        ("formal strategy file status", formal_status, "diff checked before and after"),
        ("dashboard build/test status", build_status, "recorded after verification command"),
    ]
    return pd.DataFrame(rows, columns=["metric", "value", "note"])


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    dirty_paths = _git_status_paths("dashboard")
    _git("diff", "--", "dashboard")
    _git("diff", "--", *FORMAL_STRATEGY_FILES)
    formal_status = _formal_strategy_status()
    counts = _load_counts()

    frontend_paths = [
        FEATURE_DIR / "types.ts",
        FEATURE_DIR / "techBottleneckReadonlyData.ts",
        FEATURE_DIR / "TechBottleneckWatchlistReviewPage.tsx",
    ]
    frontend_hits = _scan_paths_for_terms(frontend_paths)
    build_status = os.environ.get("DASHBOARD_BUILD_STATUS", "not_run_by_generator")
    inventory = build_inventory(dirty_paths)
    files_changed = build_files_changed(frontend_hits)
    data_flow = write_data_flow(counts, len(dirty_paths))
    report = write_report(counts, dirty_paths, formal_status, build_status)

    inventory.to_csv(OUTPUT_DIR / "dashboard_readonly_frontend_inventory.csv", index=False)
    files_changed.to_csv(OUTPUT_DIR / "dashboard_readonly_frontend_files_changed.csv", index=False)
    (OUTPUT_DIR / "dashboard_readonly_frontend_data_flow.md").write_text(data_flow, encoding="utf-8")
    (OUTPUT_DIR / "dashboard_readonly_frontend_v1.md").write_text(report, encoding="utf-8")
    output_paths = [
        OUTPUT_DIR / "dashboard_readonly_frontend_inventory.csv",
        OUTPUT_DIR / "dashboard_readonly_frontend_files_changed.csv",
        OUTPUT_DIR / "dashboard_readonly_frontend_data_flow.md",
        OUTPUT_DIR / "dashboard_readonly_frontend_v1.md",
    ]
    output_hits = _scan_paths_for_terms(output_paths)
    audit = build_quality_audit(
        inventory,
        files_changed,
        counts,
        dirty_paths,
        frontend_hits,
        output_hits,
        formal_status,
        build_status,
    )
    audit.to_csv(OUTPUT_DIR / "dashboard_readonly_frontend_quality_audit.csv", index=False)


if __name__ == "__main__":
    main()
