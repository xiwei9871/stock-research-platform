#!/usr/bin/env python3
from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
RESEARCH_DIR = PROJECT_ROOT / "outputs/research"
V2_GENERATOR_DIR = RESEARCH_DIR / "tech_bottleneck_research_selection_layer_v2_generator_v1"
V2_PLAN_DIR = RESEARCH_DIR / "tech_bottleneck_research_selection_layer_v2_implementation_plan"
CONSOLIDATED_DIR = RESEARCH_DIR / "tech_bottleneck_watchlist_report_consolidated_v1"
DASHBOARD_DIR = RESEARCH_DIR / "tech_bottleneck_watchlist_dashboard_readonly_v1"
OUTPUT_DIR = RESEARCH_DIR / "tech_bottleneck_manual_review_label_schema_v1"
RULE_VERSION = "tech_bottleneck_manual_review_label_schema_v1"

FORBIDDEN_PATTERNS = [
    re.compile(r"\b(?:buy|sell|add|reduce|hold|target_price|position_size|entry_signal|exit_signal)\b", re.I),
    re.compile(r"买入|卖出|加仓|减仓|持有|目标价|仓位建议|入场点|交易信号"),
]


def contains_actionable_trading_language(text: str) -> bool:
    return any(pattern.search(str(text)) for pattern in FORBIDDEN_PATTERNS)


def _git_lines(*args: str) -> str:
    result = subprocess.run(["git", *args], cwd=PROJECT_ROOT, check=False, text=True, capture_output=True)
    return (result.stdout or result.stderr or "").strip()


def _pipe(values: list[str]) -> str:
    return "|".join(values)


def build_label_dictionary() -> pd.DataFrame:
    rows: list[dict[str, Any]] = []

    def add(group: str, name: str, typ: str, values: list[str] | str, desc: str, required: bool, default: str, stage: str, display: bool, notes: str = "") -> None:
        rows.append(
            {
                "label_group": group,
                "label_name": name,
                "label_type": typ,
                "allowed_values": _pipe(values) if isinstance(values, list) else values,
                "description": desc,
                "required": required,
                "default_value": default,
                "review_stage": stage,
                "dashboard_display": display,
                "used_for_signal": False,
                "notes": notes,
            }
        )

    for name, typ, default in [
        ("review_id", "text", ""),
        ("asset_id", "text", ""),
        ("symbol", "text", ""),
        ("name", "text", ""),
        ("review_date", "date", ""),
        ("reviewer", "text", ""),
        ("review_round", "integer", "1"),
        ("review_status", "enum", "not_started"),
        ("source_report_path", "text", ""),
    ]:
        add("review_metadata", name, typ, "" if typ != "enum" else "not_started|in_review|reviewed|needs_more_source|risk_follow_up|deprioritized|archived_research_only", f"Metadata field {name}.", True, default, "metadata", True)

    add("thesis_review", "thesis_clarity", "enum", ["clear", "partially_clear", "unclear", "missing"], "Manual clarity review of bottleneck thesis.", True, "missing", "thesis", True)
    add("thesis_review", "thesis_source_support", "enum", ["strong_source_support", "partial_source_support", "weak_source_support", "no_source_support", "not_reviewed"], "Manual source support review.", True, "not_reviewed", "thesis", True)
    add("thesis_review", "thesis_relevance_to_bottleneck", "enum", ["high_relevance", "medium_relevance", "low_relevance", "not_reviewed"], "Relevance to technology bottleneck theme.", True, "not_reviewed", "thesis", True)
    add("thesis_review", "thesis_time_horizon", "enum", ["near_term_research", "mid_term_research", "long_term_research", "unclear", "not_reviewed"], "Research horizon for thesis review.", False, "not_reviewed", "thesis", True)
    add("thesis_review", "thesis_review_note", "textarea", "", "Free-text thesis review note.", False, "", "thesis", True)

    add("announcement_review", "announcement_evidence_quality", "enum", ["specific_and_relevant", "generic_but_relevant", "weak_or_indirect", "no_support", "not_reviewed"], "Manual announcement evidence quality.", True, "not_reviewed", "announcement", True)
    add("announcement_review", "announcement_specific_validation_quality", "enum", ["strong_validation", "partial_validation", "weak_validation", "no_validation", "not_reviewed"], "Specific validation evidence quality.", False, "not_reviewed", "announcement", True)
    add("announcement_review", "announcement_risk_event_quality", "enum", ["specific_risk", "generic_risk", "weak_risk", "no_risk_found", "not_reviewed"], "Risk event evidence quality.", False, "not_reviewed", "announcement", True)
    add("announcement_review", "announcement_generic_text_risk", "enum", ["generic_text_only", "specific_text_available", "not_applicable", "not_reviewed"], "Whether generic text is being overread.", False, "not_reviewed", "announcement", True)
    add("announcement_review", "announcement_review_note", "textarea", "", "Announcement review note.", False, "", "announcement", True)

    add("fundamental_review", "fundamental_recovery_validity", "enum", ["validated", "partially_validated", "not_validated", "contradicted", "not_reviewed"], "Manual review of recovery signal validity.", True, "not_reviewed", "fundamental", True)
    add("fundamental_review", "fundamental_quality_validity", "enum", ["validated", "partially_validated", "not_validated", "contradicted", "not_reviewed"], "Manual review of quality signal validity.", True, "not_reviewed", "fundamental", True)
    add("fundamental_review", "fundamental_risk_validity", "enum", ["validated", "partially_validated", "not_validated", "contradicted", "not_reviewed"], "Manual review of fundamental risk context.", False, "not_reviewed", "fundamental", True)
    add("fundamental_review", "financial_statement_detail_needed", "boolean", "true|false", "Whether full statements are needed.", True, "true", "fundamental", True)
    add("fundamental_review", "fundamental_review_note", "textarea", "", "Fundamental review note.", False, "", "fundamental", True)

    add("valuation_review", "valuation_context_reasonableness", "enum", ["reasonable_context", "stretched_but_explainable", "not_meaningful", "requires_cross_check", "not_reviewed"], "Manual review of valuation context reasonableness.", True, "not_reviewed", "valuation", True)
    add("valuation_review", "pe_meaningfulness_review", "enum", ["pe_meaningful", "pe_not_meaningful", "loss_making_context", "not_reviewed"], "Manual review of PE interpretability.", True, "not_reviewed", "valuation", True)
    add("valuation_review", "valuation_cross_source_consistency_review", "enum", ["consistent", "minor_difference", "material_difference", "not_comparable", "not_reviewed"], "Manual review of cross-source consistency.", True, "not_reviewed", "valuation", True)
    add("valuation_review", "valuation_review_note", "textarea", "", "Valuation review note.", False, "", "valuation", True)

    add("risk_review", "risk_level_manual", "enum", ["low_review_risk", "medium_review_risk", "high_review_risk", "unknown"], "Research risk level after manual review.", True, "unknown", "risk", True, "Research risk only.")
    add("risk_review", "risk_source_validity", "enum", ["valid_specific_source", "generic_source_only", "not_supported", "not_reviewed"], "Manual validity review of risk source.", True, "not_reviewed", "risk", True)
    add("risk_review", "risk_follow_up_needed", "boolean", "true|false", "Whether risk follow-up research is needed.", True, "false", "risk", True)
    add("risk_review", "risk_review_note", "textarea", "", "Risk review note.", False, "", "risk", True)

    add("data_quality_review", "source_coverage_quality", "enum", ["strong_coverage", "partial_coverage", "weak_coverage", "missing_coverage", "not_reviewed"], "Manual source coverage review.", True, "not_reviewed", "data_quality", True)
    add("data_quality_review", "data_consistency_quality", "enum", ["consistent", "minor_inconsistency", "material_inconsistency", "not_reviewed"], "Manual data consistency review.", True, "not_reviewed", "data_quality", True)
    add("data_quality_review", "pit_confidence_manual", "enum", ["high_pit_confidence", "medium_pit_confidence", "low_pit_confidence", "not_reviewed"], "Manual PIT confidence review.", True, "not_reviewed", "data_quality", True)
    add("data_quality_review", "data_gap_follow_up_needed", "boolean", "true|false", "Whether data gap follow-up is needed.", True, "false", "data_quality", True)
    add("data_quality_review", "data_quality_review_note", "textarea", "", "Data quality review note.", False, "", "data_quality", True)

    for name in ["needs_more_news", "needs_full_financial_statement", "needs_industry_peer_check", "needs_broker_report_review", "needs_technical_follow_up"]:
        add("follow_up_review", name, "boolean", "true|false", f"Follow-up research flag {name}.", False, "false", "follow_up", True, "Technical means research follow-up only.")
    add("follow_up_review", "follow_up_note", "textarea", "", "Follow-up research note.", False, "", "follow_up", True)

    add("review_conclusion", "manual_review_conclusion", "enum", ["thesis_supported", "thesis_partially_supported", "thesis_not_supported", "risk_requires_follow_up", "data_insufficient", "not_reviewed"], "Manual research conclusion.", True, "not_reviewed", "conclusion", True)
    add("review_conclusion", "review_priority_after_manual", "enum", ["high_review_priority", "standard_review_priority", "risk_review_priority", "data_gap_review_priority", "low_review_priority"], "Research review priority after manual review.", True, "standard_review_priority", "conclusion", True)
    add("review_conclusion", "research_status_after_manual", "enum", ["keep_in_watchlist_research", "keep_but_needs_more_source", "risk_review_required", "deprioritize_research", "ignore_until_reconfirmed", "not_reviewed"], "Research status after manual review.", True, "not_reviewed", "conclusion", True)
    add("review_conclusion", "next_review_date", "date", "", "Optional next research review date.", False, "", "conclusion", True)
    add("review_conclusion", "final_review_note", "textarea", "", "Final review note.", False, "", "conclusion", True)
    return pd.DataFrame(rows)


def build_form_schema(labels: pd.DataFrame) -> pd.DataFrame:
    section_order = {
        "review_metadata": (1, "Review Metadata"),
        "thesis_review": (2, "Thesis Review"),
        "announcement_review": (3, "Announcement Evidence Review"),
        "fundamental_review": (4, "Fundamental Review"),
        "valuation_review": (5, "Valuation Review"),
        "risk_review": (6, "Risk Review"),
        "data_quality_review": (7, "Data Quality Review"),
        "follow_up_review": (8, "Follow-up Research"),
        "review_conclusion": (9, "Review Conclusion"),
    }
    rows: list[dict[str, Any]] = []
    counters: dict[str, int] = {}
    for _, label in labels.iterrows():
        group = str(label["label_group"])
        counters[group] = counters.get(group, 0) + 1
        order, section = section_order[group]
        field_type = str(label["label_type"])
        rows.append(
            {
                "section_order": order,
                "section_name": section,
                "field_order": counters[group],
                "field_name": label["label_name"],
                "field_label": str(label["label_name"]).replace("_", " ").title(),
                "field_type": field_type,
                "allowed_values": label["allowed_values"],
                "required": label["required"],
                "default_value": label["default_value"],
                "help_text": label["description"],
                "dashboard_component": "textarea" if field_type == "textarea" else ("select" if field_type == "enum" else field_type),
                "used_for_signal": False,
            }
        )
    return pd.DataFrame(rows)


def build_status_enum() -> pd.DataFrame:
    rows = []
    specs = {
        "review_status": ["not_started", "in_review", "reviewed", "needs_more_source", "risk_follow_up", "deprioritized", "archived_research_only"],
        "review_priority_after_manual": ["high_review_priority", "standard_review_priority", "risk_review_priority", "data_gap_review_priority", "low_review_priority"],
        "research_status_after_manual": ["keep_in_watchlist_research", "keep_but_needs_more_source", "risk_review_required", "deprioritize_research", "ignore_until_reconfirmed", "not_reviewed"],
    }
    terminal = {"reviewed", "deprioritized", "archived_research_only", "ignore_until_reconfirmed"}
    for enum_name, values in specs.items():
        for value in values:
            rows.append(
                {
                    "enum_name": enum_name,
                    "enum_value": value,
                    "description": f"Research-only enum value {value}.",
                    "terminal_state": value in terminal,
                    "dashboard_badge": value,
                    "used_for_signal": False,
                }
            )
    return pd.DataFrame(rows)


def build_action_enum() -> pd.DataFrame:
    allowed = [
        "open_consolidated_report",
        "mark_review_started",
        "save_review_labels",
        "request_more_news_source",
        "request_full_financial_statement",
        "request_broker_report_review",
        "request_industry_peer_check",
        "flag_risk_follow_up",
        "flag_data_gap",
        "mark_reviewed",
        "deprioritize_research",
        "ignore_until_reconfirmed",
    ]
    forbidden = [
        "buy",
        "sell",
        "add_position",
        "reduce_position",
        "hold_position",
        "set_target_price",
        "set_position_size",
        "create_entry_signal",
        "create_exit_signal",
        "override_strategy_score",
    ]
    rows = []
    for action in allowed:
        rows.append(
            {
                "action_name": action,
                "action_group": "allowed_research_action",
                "description": f"Allowed research-only action: {action}.",
                "allowed_in_dashboard": True,
                "requires_writeback": action not in {"open_consolidated_report"},
                "used_for_signal": False,
                "notes": "Writeback target is research-only manual review file.",
            }
        )
    for action in forbidden:
        rows.append(
            {
                "action_name": action,
                "action_group": "forbidden_execution_action",
                "description": "Forbidden action listed for UI exclusion and audit only.",
                "allowed_in_dashboard": False,
                "requires_writeback": False,
                "used_for_signal": False,
                "notes": "Must not appear in allowed dashboard actions.",
            }
        )
    return pd.DataFrame(rows)


def build_data_product_spec() -> pd.DataFrame:
    products = [
        ("manual_review_labels", "tech_bottleneck_manual_review_labels.csv", "Store latest manual review labels.", "asset_id x review_round", "review_id|asset_id|review_date|review_status|manual_review_conclusion|research_status_after_manual", "v2 candidates|manual input", True, "research dashboard", "used_for_signal false; no baseline admission mutation"),
        ("manual_review_history", "tech_bottleneck_manual_review_history.csv", "Append-only manual review history.", "review event", "review_id|asset_id|changed_field|old_value|new_value|reviewer|review_date", "manual review labels", True, "research audit", "append-only; research-only"),
        ("manual_review_dashboard_table", "tech_bottleneck_manual_review_dashboard_table.csv", "Dashboard-ready manual review table.", "asset_id", "asset_id|review_status|review_priority_after_manual|research_status_after_manual|follow_up_flags", "manual review labels|v2 dashboard", True, "read-only/manual review dashboard", "no formal strategy columns"),
        ("manual_review_quality_audit", "tech_bottleneck_manual_review_quality_audit.csv", "Manual review quality audit.", "metric", "metric|value|note", "manual review labels", False, "research audit", "forbidden action scan"),
        ("manual_review_report", "tech_bottleneck_manual_review_report.md", "Manual review summary report.", "report", "section markdown", "manual review labels|quality audit", False, "research report", "no execution language"),
    ]
    return pd.DataFrame(
        [
            {
                "data_product_name": name,
                "file_name": file_name,
                "purpose": purpose,
                "grain": grain,
                "required_columns": cols,
                "source_inputs": inputs,
                "writeback_allowed": writeback,
                "consumer": consumer,
                "quality_checks": checks,
                "used_for_signal": False,
            }
            for name, file_name, purpose, grain, cols, inputs, writeback, consumer, checks in products
        ]
    )


def build_dashboard_contract(labels: pd.DataFrame) -> pd.DataFrame:
    rows = []
    sections = [
        ("Manual Review Panel", "review_status", "review_status"),
        ("Thesis Review Form", "thesis_clarity", "thesis_clarity"),
        ("Source Evidence Review Form", "announcement_evidence_quality", "announcement_evidence_quality"),
        ("Source Evidence Review Form", "fundamental_recovery_validity", "fundamental_recovery_validity"),
        ("Source Evidence Review Form", "valuation_context_reasonableness", "valuation_context_reasonableness"),
        ("Risk Review Form", "risk_level_manual", "risk_level_manual"),
        ("Data Quality Review Form", "source_coverage_quality", "source_coverage_quality"),
        ("Follow-up Research Form", "needs_more_news", "needs_more_news"),
        ("Follow-up Research Form", "needs_full_financial_statement", "needs_full_financial_statement"),
        ("Review History", "review_round", "review_round"),
        ("Review History", "final_review_note", "final_review_note"),
    ]
    label_lookup = labels.set_index("label_name")
    for section, field, source in sections:
        label = label_lookup.loc[source] if source in label_lookup.index else {}
        rows.append(
            {
                "dashboard_field": field,
                "source_field": source,
                "field_type": label.get("label_type", "text") if hasattr(label, "get") else "text",
                "display_section": section,
                "display_name": field.replace("_", " ").title(),
                "editable": True,
                "required": bool(label.get("required", False)) if hasattr(label, "get") else False,
                "allowed_values": label.get("allowed_values", "") if hasattr(label, "get") else "",
                "writeback_target": "research_only_manual_review_files",
                "used_for_signal": False,
                "notes": "No formal strategy writeback; no baseline admission mutation.",
            }
        )
    return pd.DataFrame(rows)


def _count_output_hits(root: Path) -> int:
    hits = 0
    for path in root.rglob("*"):
        if path.name == "manual_review_action_enum.csv":
            continue
        if path.is_file() and path.suffix.lower() in {".csv", ".md", ".txt"}:
            if contains_actionable_trading_language(path.read_text(encoding="utf-8", errors="ignore")):
                hits += 1
    return hits


def build_quality_audit(labels: pd.DataFrame, form: pd.DataFrame, status: pd.DataFrame, actions: pd.DataFrame, products: pd.DataFrame, dashboard: pd.DataFrame) -> pd.DataFrame:
    git_status = _git_lines("status", "--short", "--", "src/stock_research/tech_bottleneck_v1.py", "src/stock_research/tech_bottleneck_candidates.py") or "clean"
    allowed_actions = actions[actions["allowed_in_dashboard"].astype(bool)]
    forbidden_actions = actions[~actions["allowed_in_dashboard"].astype(bool)]
    rows = [
        ("label groups generated", int(labels["label_group"].nunique()), "manual review label groups"),
        ("labels generated", len(labels), "label rows"),
        ("form fields generated", len(form), "form fields"),
        ("status enum rows", len(status), "status enum rows"),
        ("action enum rows", len(actions), "action enum rows"),
        ("allowed action rows", len(allowed_actions), "allowed research actions"),
        ("forbidden action rows", len(forbidden_actions), "forbidden action rows"),
        ("data products specified", len(products), "future data products"),
        ("dashboard contract rows", len(dashboard), "dashboard contract rows"),
        ("labels used_for_signal false count", int((labels["used_for_signal"].astype(str).str.lower() == "false").sum()), "labels false"),
        ("actions used_for_signal false count", int((allowed_actions["used_for_signal"].astype(str).str.lower() == "false").sum()), "allowed actions false"),
        ("trading language hit count", 0, "excludes forbidden action registry"),
        ("forbidden trading actions listed", len(forbidden_actions), "forbidden registry only"),
        ("formal strategy file status", git_status, "must remain visible"),
        ("baseline admission change count", 0, "schema does not change baseline admission"),
        ("lookahead violation rows", 0, "schema only"),
    ]
    return pd.DataFrame(rows, columns=["metric", "value", "note"])


def render_report(audit: pd.DataFrame) -> str:
    metric = dict(zip(audit["metric"], audit["value"]))
    status = _git_lines("status", "--short", "--", "src/stock_research/tech_bottleneck_v1.py", "src/stock_research/tech_bottleneck_candidates.py") or "clean"
    diff = _git_lines("diff", "--", "src/stock_research/tech_bottleneck_v1.py", "src/stock_research/tech_bottleneck_candidates.py") or "empty"
    return f"""# Tech Bottleneck Manual Review Label Schema v1

## 1. Executive Summary
Generated manual review label schema with {metric.get('label groups generated', 0)} label groups, {metric.get('labels generated', 0)} labels, {metric.get('form fields generated', 0)} form fields, {metric.get('allowed action rows', 0)} allowed research actions, and {metric.get('forbidden action rows', 0)} forbidden UI actions. Baseline admission change count is {metric.get('baseline admission change count', 0)}. Output scan hits are {metric.get('trading language hit count', 0)}. Formal strategy status: {status}.

## 2. Input Files
- v2 generator outputs from `{V2_GENERATOR_DIR}`.
- v2 implementation plan outputs from `{V2_PLAN_DIR}`.
- consolidated reports from `{CONSOLIDATED_DIR}`.
- dashboard read-only data pack from `{DASHBOARD_DIR}`.

## 3. Label Dictionary
Label groups cover review metadata, thesis review, announcement review, fundamental review, valuation review, risk review, data quality review, follow-up review, and review conclusion.

## 4. Manual Review Form
The form schema defines dashboard sections for metadata, thesis, evidence, fundamental, valuation, risk, data quality, follow-up research, and conclusion. All fields are research-only.

## 5. Status and Action Enum
Allowed actions are limited to opening reports, saving research labels, requesting more sources, marking review progress, and flagging research follow-up. Forbidden UI actions are listed only in `manual_review_action_enum.csv` for exclusion checks.

## 6. Data Product Spec
Future writeback targets are research-only manual review files. This task does not create real manual labels.

## 7. Dashboard Contract Patch
Dashboard writeback targets are limited to research-only manual review files and do not write to formal strategy files.

## 8. Quality Controls
All labels and allowed actions have `used_for_signal = false`. Baseline admission changed count is 0. Formal strategy diff: {diff}.

## 9. What This Schema Does Not Do
This schema does not create automatic execution cues, does not alter Top5, does not alter baseline admission, does not alter formal strategy files, does not study trigger / intermediate-stage / exit, does not use evidence multiplier, and does not use manual labels as automatic execution input.

## 10. Recommended Next Step
Recommended next task: `tech_bottleneck_manual_review_template_v1`. Then consider dashboard readonly/manual review integration, full financial statement source adapter, and news source mapping.

## 11. Appendix
Generated files:
- `manual_review_label_dictionary.csv`
- `manual_review_form_schema.csv`
- `manual_review_status_enum.csv`
- `manual_review_action_enum.csv`
- `manual_review_data_product_spec.csv`
- `manual_review_dashboard_contract_patch.csv`
- `manual_review_quality_audit.csv`
- `manual_review_label_schema_v1.md`

Formal strategy file status: {status}.
"""


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    labels = build_label_dictionary()
    form = build_form_schema(labels)
    status = build_status_enum()
    actions = build_action_enum()
    products = build_data_product_spec()
    dashboard = build_dashboard_contract(labels)
    audit = build_quality_audit(labels, form, status, actions, products, dashboard)

    labels.to_csv(OUTPUT_DIR / "manual_review_label_dictionary.csv", index=False)
    form.to_csv(OUTPUT_DIR / "manual_review_form_schema.csv", index=False)
    status.to_csv(OUTPUT_DIR / "manual_review_status_enum.csv", index=False)
    actions.to_csv(OUTPUT_DIR / "manual_review_action_enum.csv", index=False)
    products.to_csv(OUTPUT_DIR / "manual_review_data_product_spec.csv", index=False)
    dashboard.to_csv(OUTPUT_DIR / "manual_review_dashboard_contract_patch.csv", index=False)
    audit.to_csv(OUTPUT_DIR / "manual_review_quality_audit.csv", index=False)
    (OUTPUT_DIR / "manual_review_label_schema_v1.md").write_text(render_report(audit), encoding="utf-8")

    hits = _count_output_hits(OUTPUT_DIR)
    if hits:
        audit.loc[audit["metric"].eq("trading language hit count"), "value"] = hits
        audit.to_csv(OUTPUT_DIR / "manual_review_quality_audit.csv", index=False)
        raise RuntimeError(f"forbidden output hits outside forbidden registry: {hits}")
    print(audit.to_string(index=False))


if __name__ == "__main__":
    main()
