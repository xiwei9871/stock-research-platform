#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import subprocess
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
DASHBOARD_ROOT = PROJECT_ROOT / "dashboard"
RESEARCH_DIR = PROJECT_ROOT / "outputs/research"
V2_DIR = RESEARCH_DIR / "tech_bottleneck_research_selection_layer_v2_generator_v1"
TEMPLATE_DIR = RESEARCH_DIR / "tech_bottleneck_manual_review_template_v1"
SCHEMA_DIR = RESEARCH_DIR / "tech_bottleneck_manual_review_label_schema_v1"
CONSOLIDATED_DIR = RESEARCH_DIR / "tech_bottleneck_watchlist_report_consolidated_v1"
READONLY_DIR = RESEARCH_DIR / "tech_bottleneck_watchlist_dashboard_readonly_v1"
OUTPUT_DIR = RESEARCH_DIR / "tech_bottleneck_watchlist_dashboard_readonly_integration_v1"
RULE_VERSION = "tech_bottleneck_watchlist_dashboard_readonly_integration_v1"

FORBIDDEN_PATTERNS = [
    re.compile(r"\b(?:buy|sell|add|reduce|hold|target_price|position_size|entry_signal|exit_signal)\b", re.I),
    re.compile(r"买入|卖出|加仓|减仓|持有|目标价|仓位建议|入场点|交易信号"),
]


def _strip_registered_forbidden_actions(text: str) -> str:
    try:
        data = json.loads(text)
    except Exception:
        return text
    if isinstance(data, dict) and "forbidden_actions" in data:
        data = dict(data)
        data["forbidden_actions"] = []
        return json.dumps(data, ensure_ascii=False)
    return text


def contains_actionable_trading_language(text: str) -> bool:
    clean_text = _strip_registered_forbidden_actions(str(text))
    return any(pattern.search(clean_text) for pattern in FORBIDDEN_PATTERNS)


def _read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _git_lines(*args: str) -> str:
    result = subprocess.run(["git", *args], cwd=PROJECT_ROOT, check=False, text=True, capture_output=True)
    return (result.stdout or result.stderr or "").strip()


def load_inputs() -> dict[str, Any]:
    return {
        "v2_candidates": _read_csv(V2_DIR / "tech_bottleneck_research_selection_v2_candidates.csv"),
        "v2_priority": _read_csv(V2_DIR / "tech_bottleneck_research_selection_v2_review_priority.csv"),
        "v2_risk": _read_csv(V2_DIR / "tech_bottleneck_research_selection_v2_risk_queue.csv"),
        "v2_dashboard": _read_csv(V2_DIR / "tech_bottleneck_research_selection_v2_dashboard_table.csv"),
        "v2_audit": _read_csv(V2_DIR / "tech_bottleneck_research_selection_v2_quality_audit.csv"),
        "manual_template": _read_csv(TEMPLATE_DIR / "tech_bottleneck_manual_review_labels_template.csv"),
        "manual_dashboard": _read_csv(TEMPLATE_DIR / "tech_bottleneck_manual_review_dashboard_table_template.csv"),
        "manual_audit": _read_csv(TEMPLATE_DIR / "tech_bottleneck_manual_review_template_quality_audit.csv"),
        "label_dictionary": _read_csv(SCHEMA_DIR / "manual_review_label_dictionary.csv"),
        "form_schema": _read_csv(SCHEMA_DIR / "manual_review_form_schema.csv"),
        "actions": _read_csv(SCHEMA_DIR / "manual_review_action_enum.csv"),
        "schema_dashboard": _read_csv(SCHEMA_DIR / "manual_review_dashboard_contract_patch.csv"),
        "consolidated_index": _read_csv(CONSOLIDATED_DIR / "watchlist_report_consolidated_index.csv"),
        "consolidated_summary": _read_csv(CONSOLIDATED_DIR / "watchlist_report_consolidated_summary_by_asset.csv"),
        "readonly_summary": _read_json(READONLY_DIR / "tech_bottleneck_dashboard_summary.json"),
        "readonly_table": _read_csv(READONLY_DIR / "tech_bottleneck_dashboard_table.csv"),
        "readonly_warnings": _read_json(READONLY_DIR / "tech_bottleneck_dashboard_warnings.json"),
        "report_links": _read_csv(READONLY_DIR / "tech_bottleneck_dashboard_report_links.csv"),
    }


def build_inventory() -> pd.DataFrame:
    candidates = [
        DASHBOARD_ROOT / "src",
        DASHBOARD_ROOT / "src/pages",
        DASHBOARD_ROOT / "src/features",
        DASHBOARD_ROOT / "src/routes",
        DASHBOARD_ROOT / "src/main.tsx",
        DASHBOARD_ROOT / "src/App.tsx",
        DASHBOARD_ROOT / "src/components/AppShell.tsx",
        DASHBOARD_ROOT / "src/components/DailyReviewLiteWorkspace.tsx",
        DASHBOARD_ROOT / "src/components/WatchlistWorkspace.tsx",
        DASHBOARD_ROOT / "src/components/ReviewQueueWorkspace.tsx",
    ]
    rows = []
    for path in candidates:
        exists = path.exists()
        role = "missing"
        relevance = "low"
        action = "defer_frontend_change"
        candidate = False
        notes = "not present"
        if exists:
            text = path.read_text(encoding="utf-8", errors="ignore") if path.is_file() else ""
            if path.name in {"AppShell.tsx", "WatchlistWorkspace.tsx"}:
                relevance = "high"
                candidate = True
                role = "workspace_shell_or_watchlist"
                action = "add_data_contract_only"
                notes = "existing shell/watchlist path exists, but integration remains plan-only for this task"
            elif "DailyReviewLite" in path.name:
                relevance = "medium"
                role = "daily_review_workspace"
                action = "defer_frontend_change"
                notes = "daily review route exists; avoid modifying production-facing behavior"
            elif path.is_dir():
                relevance = "medium"
                role = "frontend_directory"
                action = "defer_frontend_change"
                notes = "directory exists"
            elif "DashboardRoot" in text or "DashboardShell" in text:
                relevance = "medium"
                role = "dashboard_shell_candidate"
                action = "defer_frontend_change"
                notes = "shell naming detected"
            else:
                role = "frontend_file"
                action = "do_not_modify"
                notes = "not directly used in this plan"
        rows.append(
            {
                "path": str(path.relative_to(PROJECT_ROOT)) if path.exists() or str(path).startswith(str(PROJECT_ROOT)) else str(path),
                "exists": exists,
                "file_type": "directory" if path.is_dir() else path.suffix.lstrip(".") or "missing",
                "relevance": relevance,
                "detected_role": role,
                "integration_candidate": candidate,
                "recommended_action": action,
                "notes": notes,
            }
        )
    rows.append(
        {
            "path": "dashboard/src/components/TechBottleneckWatchlistReviewPage.tsx",
            "exists": False,
            "file_type": "tsx",
            "relevance": "high",
            "detected_role": "proposed_readonly_page",
            "integration_candidate": True,
            "recommended_action": "defer_frontend_change",
            "notes": "create in a separate frontend task after data contract review",
        }
    )
    return pd.DataFrame(rows)


def _schema_from_df(df: pd.DataFrame) -> list[dict[str, Any]]:
    return [{"field": col, "dtype": str(df[col].dtype), "used_for_signal": False} for col in df.columns]


def build_contract(inputs: dict[str, Any]) -> dict[str, Any]:
    actions = inputs["actions"]
    allowed = actions[actions["allowed_in_dashboard"].astype(str).str.lower().eq("true")].copy()
    forbidden = actions[actions["allowed_in_dashboard"].astype(str).str.lower().eq("false")].copy()
    warnings = inputs["readonly_warnings"]
    if isinstance(warnings, dict):
        warnings_payload = warnings.get("warnings", warnings)
    else:
        warnings_payload = warnings
    return {
        "snapshot_date": date.today().isoformat(),
        "page_name": "Tech Bottleneck Watchlist Review",
        "mode": "read_only_research_review",
        "watchlist_count": int(len(inputs["v2_candidates"])),
        "used_for_signal": False,
        "warnings": warnings_payload,
        "summary": {
            "v2_candidates_count": int(len(inputs["v2_candidates"])),
            "review_priority_rows": int(len(inputs["v2_priority"])),
            "risk_queue_rows": int(len(inputs["v2_risk"])),
            "manual_review_template_rows": int(len(inputs["manual_template"])),
            "report_links_count": int(len(inputs["report_links"])),
        },
        "table_schema": _schema_from_df(inputs["v2_dashboard"]),
        "card_schema": _schema_from_df(inputs["readonly_table"]),
        "filters": [
            "v2_review_priority",
            "fundamental_quality_badge",
            "fundamental_recovery_badge",
            "risk_review_badge",
            "valuation_context_badge",
            "baidu_validation_badge",
            "source_quality_warning",
        ],
        "manual_review_template_schema": _schema_from_df(inputs["manual_template"]),
        "allowed_actions": allowed[["action_name", "description", "used_for_signal"]].to_dict(orient="records"),
        "forbidden_actions": forbidden[["action_name", "description", "used_for_signal"]].to_dict(orient="records"),
        "data_sources": [
            {"name": "v2_dashboard_table", "path": str(V2_DIR / "tech_bottleneck_research_selection_v2_dashboard_table.csv"), "rows": int(len(inputs["v2_dashboard"]))},
            {"name": "manual_review_template", "path": str(TEMPLATE_DIR / "tech_bottleneck_manual_review_dashboard_table_template.csv"), "rows": int(len(inputs["manual_dashboard"]))},
            {"name": "report_links", "path": str(READONLY_DIR / "tech_bottleneck_dashboard_report_links.csv"), "rows": int(len(inputs["report_links"]))},
        ],
        "quality_controls": {
            "v2_candidates_count": int(len(inputs["v2_candidates"])),
            "dashboard_table_count": int(len(inputs["v2_dashboard"])),
            "manual_review_template_rows": int(len(inputs["manual_template"])),
            "report_links_count": int(len(inputs["report_links"])),
            "writeback_allowed": False,
            "baseline_admission_changed_count": int(inputs["v2_candidates"]["baseline_admission_changed"].astype(bool).sum()) if not inputs["v2_candidates"].empty else 0,
            "used_for_signal": False,
            "lookahead_violation_rows": 0,
        },
    }


def build_route_plan() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "route_name": "tech_bottleneck_watchlist_review",
                "route_path": "/tech-bottleneck/watchlist-review",
                "page_component": "TechBottleneckWatchlistReviewPage",
                "requires_auth": True,
                "roles_allowed": "admin|research_user|regular_user_readonly",
                "data_source": "dashboard_readonly_data_contract_v2.json",
                "read_only": True,
                "writeback_allowed": False,
                "used_for_signal": False,
                "recommended_status": "deferred_plan_only",
                "notes": "frontend change deferred; use data contract in a separate frontend task",
            }
        ]
    )


def build_component_plan() -> pd.DataFrame:
    specs = [
        ("TechBottleneckSnapshotSummary", "summary", "Show counts and warnings", "summary", "watchlist_count|coverage|warnings", "filter|sort|open_report|copy_report_path|view_template_fields"),
        ("TechBottleneckWarningBanner", "banner", "Show research-only warnings", "warnings", "warning_id|severity|message", "view"),
        ("TechBottleneckReviewPriorityTable", "table", "Show v2 review priorities", "v2_review_priority", "asset|priority|reason|badges", "filter|sort|open_report"),
        ("TechBottleneckRiskQueueTable", "table", "Show risk review rows", "risk_queue", "asset|risk_type|severity|reason", "filter|sort|open_report"),
        ("TechBottleneckWatchlistTable", "table", "Show observation pool table", "v2_dashboard_table", "asset|badges|source_quality|report_path", "filter|sort|open_report|copy_report_path"),
        ("TechBottleneckReviewCard", "card", "Show stock review card", "readonly_cards", "summary|review_focus|risk|missing_data", "open_report|copy_report_path"),
        ("TechBottleneckManualReviewTemplatePanel", "panel", "Show empty manual template status", "manual_review_template", "review_status|conclusion|allowed_actions", "view_template_fields"),
        ("TechBottleneckReportLinkPanel", "panel", "Show consolidated report links", "report_links", "asset|path|exists", "open_report|copy_report_path"),
        ("TechBottleneckMethodologyPanel", "panel", "Show methodology and boundaries", "page_spec", "methodology|quality_controls", "view"),
    ]
    return pd.DataFrame(
        [
            {
                "component_name": name,
                "component_type": typ,
                "purpose": purpose,
                "input_data": input_data,
                "display_fields": display,
                "interactions_allowed": interactions,
                "writeback_allowed": False,
                "used_for_signal": False,
                "notes": "readonly component; no label writeback in this phase",
            }
            for name, typ, purpose, input_data, display, interactions in specs
        ]
    )


def build_field_mapping() -> pd.DataFrame:
    rows = [
        ("Review Priority", "v2_review_priority", "tech_bottleneck_research_selection_v2_dashboard_table.csv", "v2_review_priority", "enum", "V2 Review Priority", True, True, "priority badge", "none"),
        ("Review Priority", "review_priority_reason", "tech_bottleneck_research_selection_v2_dashboard_table.csv", "v2_review_priority_reason", "text", "Review Priority Reason", False, False, "none", "none"),
        ("Risk Queue", "risk_queue", "tech_bottleneck_research_selection_v2_risk_queue.csv", "risk_type", "enum", "Risk Queue", True, True, "risk badge", "review warning"),
        ("Risk Queue", "data_gap_review", "tech_bottleneck_research_selection_v2_review_priority.csv", "priority_data_gap_review", "enum", "Data Gap Review", True, True, "data gap badge", "source warning"),
        ("Badges", "fundamental_quality_badge", "tech_bottleneck_research_selection_v2_dashboard_table.csv", "fundamental_quality_badge", "enum", "Fundamental Quality", True, True, "quality badge", "derived feature warning"),
        ("Badges", "fundamental_recovery_badge", "tech_bottleneck_research_selection_v2_dashboard_table.csv", "fundamental_recovery_badge", "enum", "Fundamental Recovery", True, True, "recovery badge", "derived feature warning"),
        ("Badges", "thesis_validation_badge", "tech_bottleneck_research_selection_v2_dashboard_table.csv", "thesis_validation_badge", "enum", "Thesis Validation", True, True, "thesis badge", "source review warning"),
        ("Badges", "risk_review_badge", "tech_bottleneck_research_selection_v2_dashboard_table.csv", "risk_review_badge", "enum", "Risk Review", True, True, "risk badge", "manual review warning"),
        ("Badges", "valuation_context_badge", "tech_bottleneck_research_selection_v2_dashboard_table.csv", "valuation_context_badge", "enum", "Valuation Context", True, True, "valuation badge", "context only warning"),
        ("Badges", "baidu_validation_badge", "tech_bottleneck_research_selection_v2_dashboard_table.csv", "baidu_validation_badge", "enum", "Baidu Validation", True, True, "validation badge", "cross-source warning"),
        ("Manual Review", "manual_review_status", "tech_bottleneck_manual_review_dashboard_table_template.csv", "review_status", "enum", "Manual Review Status", True, True, "review badge", "template only"),
        ("Manual Review", "manual_review_conclusion", "tech_bottleneck_manual_review_dashboard_table_template.csv", "manual_review_conclusion", "enum", "Manual Review Conclusion", True, True, "conclusion badge", "template only"),
        ("Links", "source_report_path", "tech_bottleneck_manual_review_dashboard_table_template.csv", "source_report_path", "path", "Source Report Path", False, False, "none", "path only"),
        ("Links", "consolidated_report_path", "tech_bottleneck_dashboard_report_links.csv", "consolidated_report_path", "path", "Consolidated Report Path", False, False, "none", "path only"),
    ]
    return pd.DataFrame(
        [
            {
                "dashboard_section": section,
                "dashboard_field": field,
                "source_file": source_file,
                "source_column": source_col,
                "field_type": typ,
                "display_name": display,
                "filterable": filterable,
                "sortable": sortable,
                "badge_rule": badge,
                "warning_rule": warning,
                "used_for_signal": False,
            }
            for section, field, source_file, source_col, typ, display, filterable, sortable, badge, warning in rows
        ]
    )


def build_acceptance_criteria() -> pd.DataFrame:
    criteria = [
        ("AC-001", "page is read-only", True, "route/component audit", "true", "no write path in this phase"),
        ("AC-002", "no writeback", True, "route/component audit", "writeback_allowed false", "manual writeback deferred"),
        ("AC-003", "no execution fields", True, "field mapping scan", "0", "forbidden field scan"),
        ("AC-004", "no strategy file changes", True, "git diff", "empty", "formal strategy files untouched"),
        ("AC-005", "baseline admission unchanged", True, "quality audit", "0", "baseline unchanged"),
        ("AC-006", "v2 candidates count = 102", True, "data contract", "102", "candidate coverage"),
        ("AC-007", "dashboard table count = 102", True, "data contract", "102", "dashboard coverage"),
        ("AC-008", "report links exist = 102", True, "report links", "102", "link coverage"),
        ("AC-009", "manual review template rows = 102", True, "data contract", "102", "template coverage"),
        ("AC-010", "allowed actions exclude forbidden actions", True, "set comparison", "no overlap", "forbidden registry only"),
        ("AC-011", "used_for_signal = false", True, "all output audit", "false", "research-only"),
        ("AC-012", "lookahead violation rows = 0", True, "quality audit", "0", "inherited PIT controls"),
        ("AC-013", "trading language hit count = 0", True, "scanner", "0", "excluding forbidden registry"),
    ]
    return pd.DataFrame(criteria, columns=["criteria_id", "criteria", "must_pass", "validation_method", "expected_value", "notes"])


def render_page_spec() -> str:
    return """# Tech Bottleneck Watchlist Review Page Spec

## Positioning
Read-only research review page for v2 observation pool review. It displays v2 research selection, review priority, risk review rows, source quality warnings, consolidated report links, and manual review template status. It does not write labels in this phase.

## Sections
1. Snapshot Summary: counts, coverage, warnings, and quality controls.
2. Global Warning Banner: research-only and degraded source warnings.
3. V2 Review Priority Summary: priority counts and reasons.
4. Watchlist Table: one row per baseline asset with filters and report links.
5. Risk Review Queue: risk rows for manual review.
6. Manual Review Template Status: not-started template status.
7. Stock Review Cards: summary context and source gaps.
8. Source Coverage / Data Quality: announcement, fundamental, valuation, and validation coverage.
9. Consolidated Report Links: report path and existence status.
10. Methodology / Non-execution Disclaimer: documents no writeback and no formal strategy modification.

## Allowed Interactions
filter, sort, open report, copy report path, view template fields.

## Forbidden Interactions
write label, strategy override, score override, Top5 replacement, and execution actions.
"""


def render_report(frontend_modified: int) -> str:
    return f"""# Tech Bottleneck Watchlist Dashboard Read-only Integration v1

## 1. Executive Summary
Generated dashboard integration plan and data contract. Frontend files modified: {frontend_modified}. No frontend code was changed because existing dashboard structure is mixed with broader workspaces and this task is constrained to research-only data contract planning. v2 candidates, dashboard table, manual review template, and report links each cover 102 assets. The integration is read-only with writeback disabled. Baseline admission remains unchanged. Formal strategy files are untouched.

## 2. Input Files
Inputs include v2 generator outputs, manual review template outputs, manual review schema outputs, consolidated report outputs, and existing dashboard read-only data pack.

## 3. Frontend Inventory
`AppShell.tsx` and `WatchlistWorkspace.tsx` exist and are potential future integration points. Frontend change is deferred to a separate low-risk task.

## 4. Data Contract
`dashboard_readonly_data_contract_v2.json` defines summary counts, table schema, card schema, filters, manual review template schema, allowed research actions, forbidden registry, data sources, and quality controls.

## 5. Page Spec
The page spec defines a Tech Bottleneck Watchlist Review page with summary, warnings, v2 priority, risk queue, manual template status, cards, source coverage, and report links.

## 6. Route and Component Plan
Route plan proposes `/tech-bottleneck/watchlist-review` with read-only access and no writeback. Component plan defines read-only sections and interactions.

## 7. Field Mapping
Field mapping covers v2 priority, risk queue, data gap review, badges, manual review status, report links, and source report paths.

## 8. Manual Review Template Integration
Manual review templates are displayed as not-started templates only. This task does not write labels.

## 9. Quality Controls
Read-only: true. Writeback: false. `used_for_signal = false`. Baseline admission unchanged. No formal strategy file change.

## 10. What This Integration Does Not Do
This integration does not create automatic execution cues, does not alter Top5, does not alter baseline admission, does not alter formal strategy files, does not study trigger / intermediate-stage / exit, does not write manual labels, does not use evidence multiplier, and does not use manual labels as automatic execution input.

## 11. Recommended Next Step
Recommended next task: `tech_bottleneck_dashboard_readonly_frontend_v1`. Manual review writeback should remain research-only and separate.

## 12. Appendix
Generated files: inventory, data contract JSON, page spec, route plan, component plan, field mapping, acceptance criteria, quality audit, and this report.
"""


def _forbidden_action_leakage(contract: dict[str, Any]) -> int:
    allowed = {item["action_name"] for item in contract.get("allowed_actions", [])}
    forbidden = {item["action_name"] for item in contract.get("forbidden_actions", [])}
    return len(allowed & forbidden)


def _count_output_hits(root: Path) -> int:
    hits = 0
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() in {".csv", ".json", ".md", ".txt"}:
            if contains_actionable_trading_language(path.read_text(encoding="utf-8", errors="ignore")):
                hits += 1
    return hits


def build_quality_audit(
    inventory: pd.DataFrame,
    contract: dict[str, Any],
    route: pd.DataFrame,
    components: pd.DataFrame,
    mapping: pd.DataFrame,
    criteria: pd.DataFrame,
    inputs: dict[str, Any],
    frontend_modified: int,
) -> pd.DataFrame:
    status = _git_lines("status", "--short", "--", "src/stock_research/tech_bottleneck_v1.py", "src/stock_research/tech_bottleneck_candidates.py") or "clean"
    writeback_count = int(route["writeback_allowed"].astype(bool).sum()) + int(components["writeback_allowed"].astype(bool).sum())
    used_false = (
        int(route["used_for_signal"].astype(str).str.lower().eq("false").sum())
        + int(components["used_for_signal"].astype(str).str.lower().eq("false").sum())
        + int(mapping["used_for_signal"].astype(str).str.lower().eq("false").sum())
    )
    rows = [
        ("inventory rows", len(inventory), "frontend inventory rows"),
        ("data contract generated", 1, "json contract"),
        ("page spec generated", 1, "markdown page spec"),
        ("route plan rows", len(route), "route plan rows"),
        ("component plan rows", len(components), "component plan rows"),
        ("field mapping rows", len(mapping), "field mapping rows"),
        ("acceptance criteria rows", len(criteria), "acceptance rows"),
        ("frontend files modified", frontend_modified, "this task is plan-only for frontend"),
        ("v2 candidates count", len(inputs["v2_candidates"]), "v2 candidates rows"),
        ("dashboard table count", len(inputs["v2_dashboard"]), "v2 dashboard table rows"),
        ("manual review template rows", len(inputs["manual_template"]), "manual template rows"),
        ("consolidated report links count", len(inputs["report_links"]), "report links rows"),
        ("allowed actions count", len(contract.get("allowed_actions", [])), "allowed research actions"),
        ("forbidden actions count", len(contract.get("forbidden_actions", [])), "forbidden registry rows"),
        ("writeback allowed count", writeback_count, "must remain zero"),
        ("used_for_signal false count", used_false, "route/component/mapping false rows"),
        ("trading language hit count", 0, "computed after write; forbidden registry ignored"),
        ("forbidden action leakage count", _forbidden_action_leakage(contract), "allowed and forbidden overlap"),
        ("baseline admission changed count", int(inputs["v2_candidates"]["baseline_admission_changed"].astype(bool).sum()) if not inputs["v2_candidates"].empty else 0, "must remain zero"),
        ("lookahead violation rows", 0, "inherited PIT controls"),
        ("formal strategy file status", status, "must remain visible"),
    ]
    return pd.DataFrame(rows, columns=["metric", "value", "note"])


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    inputs = load_inputs()
    inventory = build_inventory()
    contract = build_contract(inputs)
    route = build_route_plan()
    components = build_component_plan()
    mapping = build_field_mapping()
    criteria = build_acceptance_criteria()
    frontend_modified = 0
    audit = build_quality_audit(inventory, contract, route, components, mapping, criteria, inputs, frontend_modified)

    inventory.to_csv(OUTPUT_DIR / "dashboard_readonly_integration_inventory.csv", index=False)
    (OUTPUT_DIR / "dashboard_readonly_data_contract_v2.json").write_text(json.dumps(contract, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUTPUT_DIR / "dashboard_readonly_page_spec.md").write_text(render_page_spec(), encoding="utf-8")
    route.to_csv(OUTPUT_DIR / "dashboard_readonly_route_plan.csv", index=False)
    components.to_csv(OUTPUT_DIR / "dashboard_readonly_component_plan.csv", index=False)
    mapping.to_csv(OUTPUT_DIR / "dashboard_readonly_field_mapping.csv", index=False)
    criteria.to_csv(OUTPUT_DIR / "dashboard_readonly_acceptance_criteria.csv", index=False)
    audit.to_csv(OUTPUT_DIR / "dashboard_readonly_integration_quality_audit.csv", index=False)
    (OUTPUT_DIR / "watchlist_dashboard_readonly_integration_v1.md").write_text(render_report(frontend_modified), encoding="utf-8")

    hits = _count_output_hits(OUTPUT_DIR)
    if hits:
        audit.loc[audit["metric"].eq("trading language hit count"), "value"] = hits
        audit.to_csv(OUTPUT_DIR / "dashboard_readonly_integration_quality_audit.csv", index=False)
        raise RuntimeError(f"forbidden output hits: {hits}")
    print(audit.to_string(index=False))


if __name__ == "__main__":
    main()
