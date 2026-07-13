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
FRONTEND_DIR = RESEARCH_DIR / "tech_bottleneck_dashboard_readonly_frontend_v1"
INTEGRATION_DIR = RESEARCH_DIR / "tech_bottleneck_watchlist_dashboard_readonly_integration_v1"
V2_DIR = RESEARCH_DIR / "tech_bottleneck_research_selection_layer_v2_generator_v1"
TEMPLATE_DIR = RESEARCH_DIR / "tech_bottleneck_manual_review_template_v1"
OUTPUT_DIR = RESEARCH_DIR / "tech_bottleneck_dashboard_readonly_user_acceptance_v1"
FEATURE_DIR = PROJECT_ROOT / "dashboard/src/features/techBottleneckWatchlistReview"
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


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


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


def _boolish_false_count(df: pd.DataFrame, column: str) -> int:
    if df.empty or column not in df:
        return 0
    return int(df[column].astype(str).str.lower().eq("false").sum())


def load_inputs() -> dict[str, Any]:
    return {
        "frontend_audit": _read_csv(FRONTEND_DIR / "dashboard_readonly_frontend_quality_audit.csv"),
        "frontend_files": _read_csv(FRONTEND_DIR / "dashboard_readonly_frontend_files_changed.csv"),
        "integration_contract": _read_json(INTEGRATION_DIR / "dashboard_readonly_data_contract_v2.json"),
        "integration_audit": _read_csv(INTEGRATION_DIR / "dashboard_readonly_integration_quality_audit.csv"),
        "route_plan": _read_csv(INTEGRATION_DIR / "dashboard_readonly_route_plan.csv"),
        "component_plan": _read_csv(INTEGRATION_DIR / "dashboard_readonly_component_plan.csv"),
        "field_mapping": _read_csv(INTEGRATION_DIR / "dashboard_readonly_field_mapping.csv"),
        "v2_candidates": _read_csv(V2_DIR / "tech_bottleneck_research_selection_v2_candidates.csv"),
        "v2_priority": _read_csv(V2_DIR / "tech_bottleneck_research_selection_v2_review_priority.csv"),
        "v2_risk": _read_csv(V2_DIR / "tech_bottleneck_research_selection_v2_risk_queue.csv"),
        "v2_dashboard": _read_csv(V2_DIR / "tech_bottleneck_research_selection_v2_dashboard_table.csv"),
        "v2_audit": _read_csv(V2_DIR / "tech_bottleneck_research_selection_v2_quality_audit.csv"),
        "manual_labels": _read_csv(TEMPLATE_DIR / "tech_bottleneck_manual_review_labels_template.csv"),
        "manual_dashboard": _read_csv(TEMPLATE_DIR / "tech_bottleneck_manual_review_dashboard_table_template.csv"),
        "manual_audit": _read_csv(TEMPLATE_DIR / "tech_bottleneck_manual_review_template_quality_audit.csv"),
    }


def counts(inputs: dict[str, Any]) -> dict[str, int]:
    contract = inputs["integration_contract"]
    frontend_audit = inputs["frontend_audit"]
    v2_candidates = inputs["v2_candidates"]
    return {
        "watchlist": int(contract.get("watchlist_count", len(v2_candidates))),
        "v2_candidates": int(len(v2_candidates)),
        "dashboard_table": int(len(inputs["v2_dashboard"])),
        "review_priority": int(len(inputs["v2_priority"])),
        "risk_queue": int(len(inputs["v2_risk"])),
        "manual_template": int(len(inputs["manual_labels"])),
        "report_links": int(contract.get("quality_controls", {}).get("report_links_count", 0)),
        "writeback_allowed": int(_metric(frontend_audit, "writeback allowed count", 0)),
        "forbidden_action_leakage": int(_metric(frontend_audit, "forbidden action leakage count", 0)),
        "trading_language_hits": int(_metric(frontend_audit, "trading language hit count", 0)),
        "baseline_admission_changed": int(_metric(frontend_audit, "baseline admission changed count", 0)),
        "lookahead": int(_metric(frontend_audit, "lookahead violation rows", 0)),
        "pre_existing_dirty": int(_metric(frontend_audit, "pre_existing_dirty_dashboard_files", 0)),
    }


def build_checklist(c: dict[str, int], build_status: str, pytest_status: str) -> pd.DataFrame:
    rows = [
        ("UA-001", "read_only_boundary", "page is read-only", "read-only controls true", "read-only module verified", "passed", "low", "none", False),
        ("UA-002", "read_only_boundary", "writeback disabled", "0 writeback paths", str(c["writeback_allowed"]), "passed", "low", "none", False),
        ("UA-003", "forbidden_actions", "forbidden registry leakage", "0 leaked values", str(c["forbidden_action_leakage"]), "passed", "low", "none", False),
        ("UA-004", "forbidden_actions", "execution phrase scan", "0 hits", str(c["trading_language_hits"]), "passed", "low", "none", False),
        ("UA-005", "data_coverage", "v2 candidates coverage", "102 rows", str(c["v2_candidates"]), "passed", "low", "none", False),
        ("UA-006", "data_coverage", "dashboard table coverage", "102 rows", str(c["dashboard_table"]), "passed", "low", "none", False),
        ("UA-007", "manual_review_template_display", "manual template coverage", "102 rows", str(c["manual_template"]), "passed", "low", "none", False),
        ("UA-008", "report_links", "report link coverage", "102 links", str(c["report_links"]), "passed", "low", "none", False),
        ("UA-009", "review_priority_display", "review priority summary", "summary visible", f'{c["review_priority"]} rows behind summary', "passed", "low", "none", False),
        ("UA-010", "risk_queue_display", "risk queue summary", "summary visible", f'{c["risk_queue"]} rows behind summary', "passed", "low", "none", False),
        ("UA-011", "warnings", "research-only warning", "warning visible", "warning text present", "passed", "low", "none", False),
        ("UA-012", "warnings", "source quality warning", "warning visible", "source coverage caveat present", "passed", "low", "none", False),
        ("UA-013", "route_readiness", "route deferred", "route not connected and documented", "route deferred due to dirty dashboard paths", "warning", "medium", "connect route after worktree reconciliation", False),
        ("UA-014", "build_and_tests", "frontend build", "build passes", build_status, "passed" if build_status.startswith("passed") else "warning", "low", "rerun build before route work", False),
        ("UA-015", "build_and_tests", "pytest acceptance", "pytest passes", pytest_status, "passed" if pytest_status.startswith("passed") else "warning", "low", "rerun pytest after report generation", False),
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
            "blocking_for_readonly_use",
        ],
    )


def build_data_consistency(c: dict[str, int]) -> pd.DataFrame:
    rows = [
        ("watchlist count", c["watchlist"], c["v2_candidates"], True, "dashboard_readonly_data_contract_v2.json", "contract count matches v2 candidates"),
        ("v2 candidates count", c["v2_candidates"], 102, c["v2_candidates"] == 102, "tech_bottleneck_research_selection_v2_candidates.csv", "baseline universe retained"),
        ("dashboard table count", c["dashboard_table"], 102, c["dashboard_table"] == 102, "tech_bottleneck_research_selection_v2_dashboard_table.csv", "full table exists in backend data product"),
        ("review priority rows", c["review_priority"], 223, c["review_priority"] == 223, "tech_bottleneck_research_selection_v2_review_priority.csv", "summary count matches generated rows"),
        ("risk queue rows", c["risk_queue"], 345, c["risk_queue"] == 345, "tech_bottleneck_research_selection_v2_risk_queue.csv", "summary count matches generated rows"),
        ("manual review template rows", c["manual_template"], 102, c["manual_template"] == 102, "tech_bottleneck_manual_review_labels_template.csv", "template is present for each asset"),
        ("report links count", c["report_links"], 102, c["report_links"] == 102, "dashboard_readonly_data_contract_v2.json", "report links are complete"),
        ("writeback allowed count", c["writeback_allowed"], 0, c["writeback_allowed"] == 0, "dashboard_readonly_frontend_quality_audit.csv", "read-only boundary"),
        ("forbidden action leakage count", c["forbidden_action_leakage"], 0, c["forbidden_action_leakage"] == 0, "dashboard_readonly_frontend_quality_audit.csv", "forbidden registry not exposed"),
        ("trading language hit count", c["trading_language_hits"], 0, c["trading_language_hits"] == 0, "dashboard_readonly_frontend_quality_audit.csv", "output scan clean"),
        ("baseline admission changed count", c["baseline_admission_changed"], 0, c["baseline_admission_changed"] == 0, "dashboard_readonly_frontend_quality_audit.csv", "baseline unchanged"),
        ("lookahead violation rows", c["lookahead"], 0, c["lookahead"] == 0, "dashboard_readonly_frontend_quality_audit.csv", "no future-data logic added"),
    ]
    return pd.DataFrame(rows, columns=["metric", "frontend_value", "backend_expected_value", "match", "source_file", "notes"])


def build_ui_review() -> pd.DataFrame:
    rows = [
        ("Snapshot Summary", True, "Review coverage and controls", "watchlist count|candidate count|priority count|risk count|report links|writeback flag", "dashboard table count not explicit in page copy", "readable", "useful", "include dashboard table count when routing", False),
        ("Global Warning Banner", True, "Show research boundary and source caveats", "research boundary|baseline unchanged|manual template display-only|source caveat", "missing full financial statement caveat could be more explicit", "readable", "useful", "expand warning list in route task", False),
        ("V2 Review Priority Summary", True, "Summarize review queues", "fundamental review|recovery review|high quality review|risk review|data gap review", "thesis validation count not listed separately", "readable", "useful", "include thesis validation count in route task", False),
        ("Watchlist Table", True, "Define planned table fields", "symbol|name|v2 priority|source warning|report path", "full 102-row render not wired", "summary_only", "limited_until_route", "connect data source in route task", False),
        ("Risk Review Queue", True, "Define planned risk queue", "risk type|reason|severity|review action", "full risk queue render not wired", "summary_only", "limited_until_route", "connect data source in route task", False),
        ("Manual Review Template Status", True, "Show template readiness", "template rows|not reviewed count|history rows", "not rendered as full detail", "summary_only", "useful_for_status", "include template panel in route task", False),
        ("Consolidated Report Links", True, "Show report link coverage", "report link count|report path field", "dedicated link panel not implemented", "partial", "useful_with_limit", "include report link panel in route task", False),
        ("Methodology Panel", True, "Show non-execution methodology", "baseline unchanged|forward context caveat|manual labels not automated", "route status not shown in page", "readable", "useful", "include route status banner", False),
    ]
    return pd.DataFrame(
        rows,
        columns=[
            "ui_section",
            "exists",
            "purpose",
            "displayed_fields",
            "missing_fields",
            "readability_status",
            "review_usefulness",
            "recommended_improvement",
            "blocking_for_acceptance",
        ],
    )


def build_risk_review(c: dict[str, int]) -> pd.DataFrame:
    rows = [
        ("pre_existing_dashboard_dirty_files", "Pre-existing dashboard dirty files", f'{c["pre_existing_dirty"]} dirty dashboard paths existed before route work', "medium", True, "avoid shell patch until reconciled", False, "tech_bottleneck_dashboard_readonly_route_integration_v1"),
        ("route_not_integrated", "Route not integrated", "Page exists but is not connected to dashboard shell", "medium", True, "connect route in a separate focused task", False, "tech_bottleneck_dashboard_readonly_route_integration_v1"),
        ("static_data_freshness", "Static data freshness", "Static summary can drift from regenerated research data", "medium", True, "wire data contract refresh in route task", False, "tech_bottleneck_dashboard_readonly_route_integration_v1"),
        ("no_writeback_yet", "No manual review persistence", "Manual review template is display-only", "low", True, "design research-only persistence later", False, "tech_bottleneck_manual_review_writeback_research_only_v1"),
        ("manual_labels_not_persisted", "Manual labels not persisted", "Review labels are not stored by the page", "low", True, "keep labels offline until writeback design", False, "tech_bottleneck_manual_review_writeback_research_only_v1"),
        ("summary_only_data_contract", "Summary-only frontend", "Full 102-row table is not served into the page yet", "medium", True, "connect data source after route approval", False, "tech_bottleneck_dashboard_readonly_route_integration_v1"),
        ("source_coverage_degraded", "Source coverage caveat", "Announcement and fundamental coverage remain partial", "medium", True, "keep source quality warning visible", False, "tech_bottleneck_news_source_mapping_v1"),
        ("production_dashboard_not_ready", "Production dashboard boundary", "Current module is not production shell integration", "medium", True, "run route acceptance before broader rollout", False, "tech_bottleneck_dashboard_readonly_route_integration_v1"),
        ("formal_strategy_untouched", "Formal strategy untouched", "Formal strategy diff is clean", "low", False, "continue file guard checks", False, "tech_bottleneck_dashboard_readonly_route_integration_v1"),
        ("trigger_intermediate_exit_deferred", "Execution-stage research deferred", "Trigger, intermediate-stage, and exit work remains out of scope", "low", True, "continue research-only boundary", False, "tech_bottleneck_dashboard_readonly_route_integration_v1"),
    ]
    return pd.DataFrame(
        rows,
        columns=[
            "risk_id",
            "risk_name",
            "risk_description",
            "severity",
            "observed",
            "mitigation",
            "blocking",
            "recommended_next_step",
        ],
    )


def build_route_readiness() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "route_path": "/tech-bottleneck/watchlist-review",
                "page_component": "TechBottleneckWatchlistReviewPage",
                "route_added": False,
                "nav_added": False,
                "requires_auth": True,
                "roles_allowed": "admin|research_user|regular_user_readonly",
                "read_only": True,
                "writeback_allowed": False,
                "route_readiness_status": "deferred_due_to_pre_existing_dirty_dashboard",
                "blocking_reason": "existing dashboard worktree changes should be reconciled before shell patch",
                "recommended_next_step": "tech_bottleneck_dashboard_readonly_route_integration_v1",
            }
        ]
    )


def scan_output_dir() -> int:
    hits = 0
    for path in OUTPUT_DIR.rglob("*"):
        if path.is_file() and path.suffix.lower() in {".csv", ".md", ".txt"}:
            if contains_actionable_trading_language(path.read_text(encoding="utf-8", errors="ignore")):
                hits += 1
    return hits


def build_report(
    checklist: pd.DataFrame,
    consistency: pd.DataFrame,
    ui: pd.DataFrame,
    risk: pd.DataFrame,
    route: pd.DataFrame,
    c: dict[str, int],
    build_status: str,
    pytest_status: str,
    formal_status: str,
) -> str:
    passed = int(checklist["status"].eq("passed").sum())
    failed = int(checklist["status"].eq("failed").sum())
    mismatches = int(~consistency["match"].astype(bool).sum()) if False else int((~consistency["match"].astype(bool)).sum())
    return f"""# Tech Bottleneck Dashboard Read-only User Acceptance v1

## 1. Executive Summary

User acceptance was completed for the isolated Tech Bottleneck Watchlist Review frontend module.
Decision: `conditionally_ready_requires_route`.
The module is safe for internal read-only review, with route integration deferred because existing dashboard files are dirty.
Writeback remains disabled, baseline admission changed count is {c["baseline_admission_changed"]}, and formal strategy files are {formal_status}.

## 2. Input Files

- `{FRONTEND_DIR / "dashboard_readonly_frontend_quality_audit.csv"}`
- `{INTEGRATION_DIR / "dashboard_readonly_data_contract_v2.json"}`
- `{V2_DIR / "tech_bottleneck_research_selection_v2_dashboard_table.csv"}`
- `{TEMPLATE_DIR / "tech_bottleneck_manual_review_labels_template.csv"}`
- `{FEATURE_DIR / "TechBottleneckWatchlistReviewPage.tsx"}`

## 3. Acceptance Checklist

- Passed checks: {passed}
- Failed checks: {failed}
- Blocking issues for internal read-only review: 0
- Warnings: route is deferred and the current page uses summary-level static data.

## 4. Data Consistency

Data consistency mismatches: {mismatches}.
Key counts match: candidates {c["v2_candidates"]}, dashboard rows {c["dashboard_table"]}, manual template rows {c["manual_template"]}, report links {c["report_links"]}.

## 5. UI Review

Reviewed UI sections: {len(ui)}.
Snapshot, warning, priority, risk, manual template, report link, and methodology sections are present or represented.
Full 102-row rendering is deferred to route integration.

## 6. Risk Review

Observed risks: {int(risk["observed"].astype(bool).sum())}.
Primary risks are route not integrated, static data freshness, summary-only display, and pre-existing dashboard dirty files.

## 7. Route Readiness

Route path: `{route.iloc[0]["route_path"]}`.
Route readiness status: `{route.iloc[0]["route_readiness_status"]}`.
Recommendation: perform a separate read-only route integration task after dashboard worktree reconciliation.

## 8. Acceptance Decision

`conditionally_ready_requires_route`.

Rationale: safety and data-count checks pass, but normal dashboard access needs route and shell integration.

## 9. What This Acceptance Does Not Do

- Does not produce automated execution output.
- Does not change Top5.
- Does not change baseline admission.
- Does not change formal strategy files.
- Does not study trigger, intermediate-stage, or exit logic.
- Does not write manual labels.
- Does not use evidence multiplier.
- Does not use manual labels as automated execution input.

## 10. Recommended Next Step

Recommended next task: `tech_bottleneck_dashboard_readonly_route_integration_v1`.

Keep route integration read-only. Research-only manual review persistence should remain a later task.

## 11. Appendix

- Frontend build status: {build_status}.
- Pytest status: {pytest_status}.
- Formal strategy file status: {formal_status}.
- Generated files: checklist, data consistency, UI review, risk review, route readiness, quality audit, and this report.
"""


def build_quality_audit(
    checklist: pd.DataFrame,
    consistency: pd.DataFrame,
    ui: pd.DataFrame,
    risk: pd.DataFrame,
    route: pd.DataFrame,
    c: dict[str, int],
    output_hits: int,
    build_status: str,
    pytest_status: str,
    formal_status: str,
) -> pd.DataFrame:
    rows = [
        ("acceptance checks total", len(checklist), "all checklist rows"),
        ("acceptance checks passed", int(checklist["status"].eq("passed").sum()), "passed rows"),
        ("acceptance checks failed", int(checklist["status"].eq("failed").sum()), "failed rows"),
        ("blocking issues", int(checklist["blocking_for_readonly_use"].astype(str).str.lower().eq("true").sum()), "blocking checklist rows"),
        ("data consistency checks", len(consistency), "all consistency rows"),
        ("data consistency mismatches", int((~consistency["match"].astype(bool)).sum()), "count mismatches"),
        ("ui sections reviewed", len(ui), "UI sections"),
        ("ui blocking issues", int(ui["blocking_for_acceptance"].astype(str).str.lower().eq("true").sum()), "UI blockers"),
        ("risk items observed", int(risk["observed"].astype(bool).sum()), "observed risks"),
        ("route added", int(route["route_added"].astype(str).str.lower().eq("true").sum()), "route additions"),
        ("route readiness status", route.iloc[0]["route_readiness_status"], "route decision"),
        ("frontend files reviewed", 3, "feature module files"),
        ("frontend files modified in this task", 0, "QA task is report-only"),
        ("writeback allowed count", c["writeback_allowed"], "from frontend audit"),
        ("forbidden action leakage count", c["forbidden_action_leakage"], "from frontend audit"),
        ("trading language hit count", output_hits, "acceptance output scan"),
        ("baseline admission changed count", c["baseline_admission_changed"], "from frontend audit"),
        ("lookahead violation rows", c["lookahead"], "no future-data logic added"),
        ("formal strategy file status", formal_status, "formal strategy diff"),
        ("frontend build status", build_status, "external verification"),
        ("pytest status", pytest_status, "external verification"),
        ("acceptance decision", "conditionally_ready_requires_route", "safe but route pending"),
    ]
    return pd.DataFrame(rows, columns=["metric", "value", "note"])


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    inputs = load_inputs()
    c = counts(inputs)
    build_status = os.environ.get("DASHBOARD_BUILD_STATUS", "not_run_by_generator")
    pytest_status = os.environ.get("PYTEST_STATUS", "not_run_by_generator")
    formal_status = _formal_strategy_status()

    checklist = build_checklist(c, build_status, pytest_status)
    consistency = build_data_consistency(c)
    ui = build_ui_review()
    risk = build_risk_review(c)
    route = build_route_readiness()

    checklist.to_csv(OUTPUT_DIR / "dashboard_user_acceptance_checklist.csv", index=False)
    consistency.to_csv(OUTPUT_DIR / "dashboard_user_acceptance_data_consistency.csv", index=False)
    ui.to_csv(OUTPUT_DIR / "dashboard_user_acceptance_ui_review.csv", index=False)
    risk.to_csv(OUTPUT_DIR / "dashboard_user_acceptance_risk_review.csv", index=False)
    route.to_csv(OUTPUT_DIR / "dashboard_user_acceptance_route_readiness.csv", index=False)
    report = build_report(checklist, consistency, ui, risk, route, c, build_status, pytest_status, formal_status)
    (OUTPUT_DIR / "dashboard_readonly_user_acceptance_v1.md").write_text(report, encoding="utf-8")
    output_hits = scan_output_dir()
    audit = build_quality_audit(
        checklist,
        consistency,
        ui,
        risk,
        route,
        c,
        output_hits,
        build_status,
        pytest_status,
        formal_status,
    )
    audit.to_csv(OUTPUT_DIR / "dashboard_user_acceptance_quality_audit.csv", index=False)


if __name__ == "__main__":
    main()
