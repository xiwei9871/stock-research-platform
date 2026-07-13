#!/usr/bin/env python3
from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
RESEARCH_DIR = PROJECT_ROOT / "outputs/research"
PIT_REPLAY_DIR = RESEARCH_DIR / "tech_bottleneck_research_selection_layer_v2_pit_replay_v1"
DESIGN_DIR = RESEARCH_DIR / "tech_bottleneck_research_selection_layer_v2_design"
PIT_INPUT_DIR = RESEARCH_DIR / "tech_bottleneck_research_selection_layer_v2_pit_input_reconstruction_v1"
DASHBOARD_DIR = RESEARCH_DIR / "tech_bottleneck_watchlist_dashboard_readonly_v1"
OUTPUT_DIR = RESEARCH_DIR / "tech_bottleneck_research_selection_layer_v2_implementation_plan"
RULE_VERSION = "tech_bottleneck_research_selection_layer_v2_implementation_plan"

FORBIDDEN_PATTERNS = [
    re.compile(r"\b(?:buy|sell|add|reduce|hold|target_price|position_size|entry_signal|exit_signal)\b", re.I),
    re.compile(r"买入|卖出|加仓|减仓|持有|目标价|仓位建议|入场点|交易信号"),
]


def contains_actionable_trading_language(text: str) -> bool:
    return any(pattern.search(str(text)) for pattern in FORBIDDEN_PATTERNS)


def _read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


def _git_lines(*args: str) -> str:
    result = subprocess.run(["git", *args], cwd=PROJECT_ROOT, check=False, text=True, capture_output=True)
    return (result.stdout or result.stderr or "").strip()


def _count_output_hits(root: Path) -> int:
    hits = 0
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() in {".csv", ".md", ".txt"}:
            if contains_actionable_trading_language(path.read_text(encoding="utf-8", errors="ignore")):
                hits += 1
    return hits


def load_inputs() -> dict[str, pd.DataFrame]:
    return {
        "variant_summary": _read_csv(PIT_REPLAY_DIR / "v2_pit_replay_variant_summary.csv"),
        "ablation": _read_csv(PIT_REPLAY_DIR / "v2_pit_replay_ablation_summary.csv"),
        "audit": _read_csv(PIT_REPLAY_DIR / "v2_pit_replay_quality_audit.csv"),
        "design_rules": _read_csv(DESIGN_DIR / "research_selection_v2_rule_candidates.csv"),
        "design_filters": _read_csv(DESIGN_DIR / "research_selection_v2_dashboard_filter_plan.csv"),
        "pit_readiness": _read_csv(PIT_INPUT_DIR / "pit_rule_candidate_readiness.csv"),
        "blockers": _read_csv(PIT_INPUT_DIR / "pit_replay_blocker_report.csv"),
    }


def _variant_line(summary: pd.DataFrame, variant: str) -> str:
    row = summary[summary["variant_name"].eq(variant)]
    if row.empty:
        return "missing"
    r = row.iloc[0]
    return (
        f"events={int(r['event_count'])}; 120d_avg={float(r['avg_forward_120d_return']):.6f}; "
        f"positive_120d={float(r['positive_120d_rate']):.6f}"
    )


def build_final_rule_set(summary: pd.DataFrame) -> pd.DataFrame:
    rows = [
        (
            "RSV2-R001",
            "v2_fundamental_quality_review_priority",
            "review_priority",
            "recommended",
            "Prioritize baseline assets with PIT fundamental quality medium or higher.",
            "baseline; fundamental quality medium/high or recovery positive; source date valid",
            "fundamental_quality_level|fundamental_recovery_signal",
            "fundamental_derived_pit",
            "financial_as_of_date/as_of_date <= first_admission_date",
            "manual review priority",
            _variant_line(summary, "v2_baseline_plus_fundamental_quality"),
            "research_outputs",
            False,
            True,
            "strongest PIT replay uplift; not baseline filter",
        ),
        (
            "RSV2-R002",
            "v2_fundamental_recovery_review_priority",
            "review_priority",
            "recommended",
            "Prioritize assets with event-date recovery-positive fundamental context.",
            "fundamental recovery positive; source date valid",
            "fundamental_recovery_signal",
            "fundamental_derived_pit",
            "financial_as_of_date/as_of_date <= first_admission_date",
            "manual review priority",
            _variant_line(summary, "v2_fundamental_recovery_positive"),
            "research_outputs",
            False,
            True,
            "use for recovery review, not admission replacement",
        ),
        (
            "RSV2-R003",
            "v2_high_quality_review_queue",
            "review_priority",
            "recommended",
            "Create a high-quality manual review queue from assets with source coverage and no material validation conflict.",
            "baseline; announcement or fundamental source; valuation source; validation source",
            "announcement_fulltext_support|fundamental_support|baostock_valuation_support|baidu_validation_status",
            "announcement_fulltext|fundamental_derived_pit|baostock_valuation|baidu_validation",
            "all source dates <= first_admission_date",
            "manual review queue",
            _variant_line(summary, "v2_high_quality_review_candidates"),
            "manual_review",
            False,
            True,
            "moderate PIT replay improvement; keep review-only",
        ),
        (
            "RSV2-R004",
            "v2_specific_validation_thesis_review",
            "thesis_validation_queue",
            "supported_for_review",
            "Route specific validation evidence to thesis review.",
            "specific validation count > 0; announcement source date valid",
            "specific_validation_count",
            "announcement_fulltext",
            "announcement/as_of date <= first_admission_date",
            "thesis validation review",
            _variant_line(summary, "v2_specific_validation_review_priority"),
            "manual_review",
            False,
            True,
            "use as evidence review, not standalone quality enhancer",
        ),
        (
            "RSV2-R005",
            "v2_announcement_risk_review_queue",
            "risk_review_queue",
            "supported_for_review",
            "Route specific risk event assets to risk review.",
            "specific risk event count > 0; announcement source date valid",
            "specific_risk_event_count",
            "announcement_fulltext",
            "announcement/as_of date <= first_admission_date",
            "risk review queue",
            _variant_line(summary, "v2_announcement_risk_review_queue"),
            "manual_review",
            False,
            True,
            "risk context, not exclusion",
        ),
        (
            "RSV2-R006",
            "v2_valuation_context_dashboard_filter",
            "dashboard_filter",
            "filter_only",
            "Expose event-date valuation context as a read-only dashboard filter.",
            "event-date BaoStock valuation context recomputed",
            "valuation_context_level_event|pe_meaningfulness_event",
            "baostock_valuation",
            "baostock_date <= first_admission_date",
            "dashboard filter",
            _variant_line(summary, "v2_valuation_context_event_recomputed"),
            "dashboard_readonly",
            False,
            True,
            "valuation context alone did not improve baseline",
        ),
        (
            "RSV2-R007",
            "v2_baidu_validation_warning",
            "data_quality_warning",
            "warning_only",
            "Show Baidu validation differences as cross-source warning.",
            "event-date Baidu validation status available",
            "validation_status_event|discrepancy_flags_event",
            "baidu_validation",
            "Baidu dates <= first_admission_date",
            "source quality warning",
            "Baidu is auxiliary; PS not validated by Baidu",
            "dashboard_readonly",
            False,
            True,
            "does not override BaoStock source",
        ),
    ]
    return pd.DataFrame(
        rows,
        columns=[
            "rule_id",
            "rule_name",
            "rule_type",
            "status",
            "description",
            "conditions",
            "required_features",
            "source_layers",
            "pit_requirement",
            "expected_usage",
            "evidence_from_pit_replay",
            "implementation_scope",
            "used_for_signal",
            "must_not_change_baseline_admission",
            "notes",
        ],
    )


def build_review_priority_contract() -> pd.DataFrame:
    rows = [
        ("priority_high_fundamental_review", "fundamental_quality_or_recovery", "fundamental quality medium/high or recovery positive", "PIT replay showed strongest 120d average improvement", "review fundamental repair; request full statements; review thesis support", "fundamental_positive_badge", "derived feature warning", False, "highest review priority, not execution priority"),
        ("priority_high_quality_review", "high_quality_manual_review", "high-quality review candidates with source coverage and no material discrepancy", "PIT replay showed moderate improvement", "deep manual review queue", "high_quality_review_badge", "coverage remains partial", False, "review queue only"),
        ("priority_thesis_validation_review", "specific_validation_review", "specific validation count > 0", "helps thesis review more than standalone quality separation", "review announcement evidence against thesis", "thesis_validation_badge", "announcement source coverage partial", False, "evidence review"),
        ("priority_risk_review", "risk_and_discrepancy_review", "specific risk event, PE not interpretable, Baidu material difference, degraded data", "risk group underperformed in PIT context and needs review", "review risk event, valuation anomaly, source consistency", "risk_review_badge", "warning only", False, "not exclusion"),
        ("priority_data_gap_review", "source_gap_review", "no announcement support; no fundamental support; thesis missing; degraded source", "source gaps limit confidence", "request source completion and keep standard review cadence", "data_gap_badge", "missing data cannot imply low risk", False, "source completion queue"),
    ]
    return pd.DataFrame(
        rows,
        columns=[
            "priority_level",
            "priority_name",
            "conditions",
            "reason_from_pit_replay",
            "review_focus",
            "dashboard_badge",
            "data_quality_warning",
            "used_for_signal",
            "notes",
        ],
    )


def build_dashboard_contract_patch() -> pd.DataFrame:
    rows = [
        ("v2_review_priority", "computed_priority_level", "enum", "Watchlist Table", "V2 Review Priority", True, True, "priority badge by contract", "show source warning if degraded", True, False, "read-only field"),
        ("fundamental_quality_badge", "fundamental_quality_level", "enum", "Fundamental", "Fundamental Quality", True, True, "quality_medium/high highlighted", "derived feature warning", True, False, "not full statements"),
        ("fundamental_recovery_badge", "fundamental_recovery_signal", "enum", "Fundamental", "Fundamental Recovery", True, True, "recovery_positive highlighted", "derived feature warning", True, False, "review focus"),
        ("thesis_validation_badge", "specific_validation_count", "numeric_bucket", "Announcement", "Thesis Validation", True, True, "count > 0", "generic text not strong evidence", True, False, "review-only"),
        ("risk_review_badge", "specific_risk_event_count", "numeric_bucket", "Risk", "Risk Review", True, True, "count > 0", "risk queue only", True, False, "not exclusion"),
        ("valuation_context_badge", "valuation_context_level_event", "enum", "Valuation", "Event Valuation Context", True, True, "low/mid/high/mixed context", "context only", True, False, "not selection enhancer"),
        ("baidu_validation_badge", "validation_status_event", "enum", "Validation", "Baidu Validation", True, True, "material difference warning", "Baidu does not validate PS", True, False, "auxiliary check"),
        ("data_gap_badge", "source_gap_flags", "multi_enum", "Data Quality", "Source Gaps", True, True, "gap count badge", "missing source warning", True, False, "source completion"),
        ("pit_replay_status", "pit_replay_status", "enum", "Method", "PIT Replay Status", True, True, "ready/partial", "method warning", True, False, "audit field"),
        ("source_quality_warning", "source_quality_warning", "text", "Warnings", "Source Quality Warning", True, False, "warning banner", "always visible if degraded", True, False, "read-only warning"),
    ]
    return pd.DataFrame(
        rows,
        columns=[
            "dashboard_field",
            "source_field",
            "field_type",
            "display_section",
            "display_name",
            "filterable",
            "sortable",
            "badge_rule",
            "warning_rule",
            "default_visible",
            "used_for_signal",
            "notes",
        ],
    )


def build_data_product_spec() -> pd.DataFrame:
    rows = [
        ("research_selection_v2_candidates", "tech_bottleneck_research_selection_v2_candidates.csv", "baseline watchlist plus v2 research fields", "asset_id", "asset_id|symbol|name|first_admission_date|v2_review_priority|source_flags", "baseline watchlist|PIT features|event-date valuation", "on research refresh", "research scripts|read-only dashboard", "row count; PIT dates; no forbidden fields", False),
        ("research_selection_v2_review_priority", "tech_bottleneck_research_selection_v2_review_priority.csv", "manual review priority queue", "asset_id", "asset_id|priority_level|review_focus|reason|source_warning", "v2 candidates", "on research refresh", "manual review", "used_for_signal false; priority enum valid", False),
        ("research_selection_v2_risk_queue", "tech_bottleneck_research_selection_v2_risk_queue.csv", "risk review queue", "asset_id", "asset_id|risk_flags|risk_review_reason|source_dates", "announcement risk|Baidu validation|valuation context", "on research refresh", "manual review", "not exclusion; source dates valid", False),
        ("research_selection_v2_dashboard_table", "tech_bottleneck_research_selection_v2_dashboard_table.csv", "read-only dashboard table", "asset_id", "asset_id|badges|filters|report_path|warnings", "v2 candidates|contracts", "on research refresh", "read-only dashboard", "no execution fields; links valid", False),
        ("research_selection_v2_quality_audit", "tech_bottleneck_research_selection_v2_quality_audit.csv", "quality audit", "metric", "metric|value|note", "all v2 outputs", "on research refresh", "research audit", "lookahead zero; forbidden scan zero", False),
        ("research_selection_v2_report", "tech_bottleneck_research_selection_v2_report.md", "research summary report", "report", "sections per plan", "all v2 outputs", "on research refresh", "research review", "boundary text present", False),
    ]
    return pd.DataFrame(
        rows,
        columns=[
            "data_product_name",
            "file_name",
            "purpose",
            "grain",
            "required_columns",
            "source_inputs",
            "refresh_frequency",
            "consumer",
            "quality_checks",
            "used_for_signal",
        ],
    )


def build_implementation_steps() -> pd.DataFrame:
    rows = [
        ("STEP-01", "create research-only v2 generator", "New generator under scripts outputs only research files.", "PIT replay outputs", "v2 research output dir", "new script and tests only", "scope creep", "script exists and writes all data products", 1),
        ("STEP-02", "read baseline watchlist", "Load standard watchlist events without changing baseline admission.", "watchlist admission events", "baseline event frame", "research script", "wrong variant filter", "102 standard rows loaded", 2),
        ("STEP-03", "merge PIT fundamental features", "Join dated fundamental quality and recovery fields.", "fundamental PIT rows", "fundamental badges", "research script", "source-date mismatch", "all joins use valid dates", 3),
        ("STEP-04", "merge event-date BaoStock valuation", "Use event-date recomputed valuation context.", "BaoStock event context", "valuation badges", "research script", "using snapshot labels", "snapshot usage count zero", 4),
        ("STEP-05", "merge event-date Baidu validation", "Use event-date validation status.", "Baidu event validation", "validation badges", "research script", "PS overclaim", "PS validation marked unavailable", 5),
        ("STEP-06", "generate review priority", "Compute review priority from final rule set.", "final rules", "review priority CSV", "research script", "priority misread as execution", "used_for_signal false", 6),
        ("STEP-07", "generate risk review queue", "Create risk queue from announcement risk and discrepancies.", "risk rules", "risk queue CSV", "research script", "auto exclusion", "no auto exclusion column true", 7),
        ("STEP-08", "generate dashboard v2 table", "Produce read-only dashboard table fields.", "dashboard contract patch", "dashboard table CSV", "research output only", "frontend coupling", "no production write", 8),
        ("STEP-09", "generate audit", "Audit source dates, lookahead, forbidden terms, formal strategy status.", "all outputs", "quality audit", "research script", "weak audit", "audit metrics complete", 9),
        ("STEP-10", "regression tests", "Run v2 generator tests and prior chain tests.", "pytest", "test results", "tests only", "missed regression", "all required tests pass", 10),
        ("STEP-11", "keep formal strategy separate", "Do not connect v2 outputs to formal logic.", "none", "no formal changes", "no production code", "boundary breach", "formal strategy diff empty", 11),
    ]
    return pd.DataFrame(
        rows,
        columns=[
            "step_id",
            "step_name",
            "description",
            "required_inputs",
            "outputs",
            "code_change_scope",
            "risk",
            "acceptance_criteria",
            "recommended_order",
        ],
    )


def build_acceptance_criteria() -> pd.DataFrame:
    rows = [
        ("AC-01", "formal strategy files unchanged", True, "git diff scoped to formal files", "empty", "untracked status reported"),
        ("AC-02", "no execution fields in outputs", True, "schema scan", "zero forbidden fields", "read-only research outputs"),
        ("AC-03", "no automated execution prompt generated", True, "text scan", "zero hits", "boundary requirement"),
        ("AC-04", "baseline admission unchanged", True, "row comparison", "baseline admission change count = 0", "v2 is overlay only"),
        ("AC-05", "review priority generated", True, "file exists and row count", ">= 1", "manual review contract"),
        ("AC-06", "risk queue generated", True, "file exists and rule present", "risk queue rule present", "warning only"),
        ("AC-07", "dashboard table generated", True, "data product output", "file exists", "read-only consumer"),
        ("AC-08", "used_for_signal = false", True, "CSV scan", "all rows false", "research-only"),
        ("AC-09", "lookahead violation rows = 0", True, "quality audit", "0", "PIT boundary"),
        ("AC-10", "PIT source date check passes", True, "source date audit", "all usable dates valid", "no snapshot labels"),
        ("AC-11", "forward return not used for rules", True, "conditions scan", "no forward_return", "outcome only"),
        ("AC-12", "forbidden term scan zero", True, "output scan", "0", "no execution wording"),
    ]
    return pd.DataFrame(rows, columns=["criteria_id", "criteria", "must_pass", "validation_method", "expected_value", "notes"])


def build_risks() -> pd.DataFrame:
    rows = [
        ("RISK-01", "announcement coverage only 31 / 102", "announcement coverage remains partial", "medium", "announcement", "keep source gap badge", "announcement source backfill"),
        ("RISK-02", "fundamental coverage only 63 / 102", "fundamental support remains partial", "medium", "fundamental", "data gap review", "full statement source adapter"),
        ("RISK-03", "derived fundamental features", "fundamental layer is derived features, not full statements", "high", "fundamental", "show derived warning", "full financial statement source"),
        ("RISK-04", "BaoStock and Baidu external source drift", "external source definitions can drift", "medium", "valuation", "periodic validation", "cross-source validation refresh"),
        ("RISK-05", "valuation context not standalone enhancer", "valuation context did not improve baseline alone", "medium", "valuation", "dashboard filter only", "manual review labels"),
        ("RISK-06", "announcement risk queue not exclusion", "risk queue is review context only", "high", "risk", "manual risk review", "risk label schema"),
        ("RISK-07", "research layer only", "v2 replay is observation pool research layer, not formal strategy", "high", "method", "keep output isolated", "implementation review"),
        ("RISK-08", "formal strategy files currently untracked", "formal strategy files currently untracked", "high", "git hygiene", "report status", "decide tracking policy"),
        ("RISK-09", "missing news source", "news source has not been mapped", "medium", "news", "show missing source warning", "news source mapping"),
        ("RISK-10", "missing full financial statement source", "full statement details missing", "high", "fundamental", "source warning", "full financial statement source adapter"),
    ]
    return pd.DataFrame(rows, columns=["risk_id", "risk_name", "description", "severity", "affected_layer", "mitigation", "recommended_follow_up"])


def build_quality_audit(rules: pd.DataFrame, priority: pd.DataFrame, dashboard: pd.DataFrame, products: pd.DataFrame, steps: pd.DataFrame, criteria: pd.DataFrame, risks: pd.DataFrame) -> pd.DataFrame:
    status = _git_lines("status", "--short", "--", "src/stock_research/tech_bottleneck_v1.py", "src/stock_research/tech_bottleneck_candidates.py") or "clean"
    false_count = int((rules["used_for_signal"].astype(str).str.lower() == "false").sum())
    rows = [
        ("final rules generated", len(rules), "final rule rows"),
        ("review priority rules generated", len(priority), "priority rows"),
        ("dashboard contract patch rows", len(dashboard), "dashboard fields"),
        ("data products specified", len(products), "future data products"),
        ("implementation steps", len(steps), "steps"),
        ("acceptance criteria", len(criteria), "criteria"),
        ("risks listed", len(risks), "risk rows"),
        ("rules used_for_signal false count", false_count, "final rules false"),
        ("baseline admission change count", 0, "plan does not alter baseline admission"),
        ("trading language hit count", 0, "computed after write"),
        ("lookahead violation rows", 0, "plan only; PIT replay already zero"),
        ("formal strategy file status", status, "untracked status must remain visible"),
    ]
    return pd.DataFrame(rows, columns=["metric", "value", "note"])


def render_report(summary: pd.DataFrame, rules: pd.DataFrame, audit: pd.DataFrame) -> str:
    status = _git_lines("status", "--short", "--", "src/stock_research/tech_bottleneck_v1.py", "src/stock_research/tech_bottleneck_candidates.py") or "clean"
    diff = _git_lines("diff", "--", "src/stock_research/tech_bottleneck_v1.py", "src/stock_research/tech_bottleneck_candidates.py") or "empty"
    baseline = summary[summary["variant_name"].eq("baseline_standard_watchlist")].iloc[0] if not summary.empty else None
    fundamental = summary[summary["variant_name"].eq("v2_baseline_plus_fundamental_quality")].iloc[0] if not summary.empty and summary["variant_name"].eq("v2_baseline_plus_fundamental_quality").any() else None
    baseline_text = "missing" if baseline is None else f"{baseline['avg_forward_30d_return']:.6f} / {baseline['avg_forward_60d_return']:.6f} / {baseline['avg_forward_90d_return']:.6f} / {baseline['avg_forward_120d_return']:.6f}"
    fundamental_text = "missing" if fundamental is None else f"{fundamental['avg_forward_30d_return']:.6f} / {fundamental['avg_forward_60d_return']:.6f} / {fundamental['avg_forward_90d_return']:.6f} / {fundamental['avg_forward_120d_return']:.6f}"
    return f"""# Tech Bottleneck Research Selection Layer v2 Implementation Plan

## 1. Executive Summary

V2 implementation plan generated successfully. PIT replay supports using fundamental quality and recovery as manual review priority. High-quality candidates become a manual review queue. Announcement risk remains risk review. Valuation context remains a read-only dashboard filter. Baseline admission is not changed.

Baseline PIT replay context: {baseline_text}. Fundamental quality context: {fundamental_text}. This plan creates research outputs and dashboard contracts only. It does not create automated execution prompts. Formal strategy files were not edited; untracked status limits historical proof from diff alone.

## 2. Input Files

Inputs: v2 PIT replay outputs, v2 design outputs, PIT input reconstruction outputs, and read-only dashboard contract outputs.

## 3. PIT Replay Findings

Fundamental quality and recovery show the clearest improvement. High-quality review candidates show moderate improvement. Specific validation supports thesis review. Announcement risk is a risk review queue. Event-date valuation context improves explanation but not baseline quality by itself.

## 4. Final V2 Rule Set

Seven final research-only rules are defined. Each keeps `used_for_signal = false` and `must_not_change_baseline_admission = true`.

## 5. Review Priority Contract

Priority levels are high fundamental review, high-quality review, thesis validation review, risk review, and data gap review. These are manual review labels only.

## 6. Dashboard Contract Patch

The dashboard patch introduces badges for review priority, fundamental quality, recovery, thesis validation, risk review, valuation context, Baidu validation, data gaps, PIT replay status, and source quality warnings. All fields are read-only.

## 7. Data Product Spec

Future v2 generator should produce candidates, review priority, risk queue, dashboard table, quality audit, and report files.

## 8. Implementation Steps

Implementation steps are limited to a research-only generator, output files, audit, and tests. No formal logic integration is included.

## 9. Acceptance Criteria

Acceptance criteria require unchanged baseline admission, zero lookahead rows, `used_for_signal = false`, no forward return in rule inputs, and zero forbidden-term hits.

## 10. Risks and Limitations

Announcement and fundamental coverage remain partial. Fundamental source is derived, not full statements. External valuation sources need ongoing validation. News and full statement sources remain missing.

## 11. What This Plan Does Not Do

- no automated execution prompt
- no Top5 change
- no baseline admission change
- no formal strategy change
- no trigger / holding / exit study
- no evidence multiplier
- no forward return as rule input

## 12. Recommended Next Step

Recommended: `tech_bottleneck_research_selection_layer_v2_generator_v1`. In parallel, create `tech_bottleneck_manual_review_label_schema_v1`.

## 13. Appendix

Generated files:
- research_selection_v2_final_rule_set.csv
- research_selection_v2_review_priority_contract.csv
- research_selection_v2_dashboard_contract_patch.csv
- research_selection_v2_data_product_spec.csv
- research_selection_v2_implementation_steps.csv
- research_selection_v2_acceptance_criteria.csv
- research_selection_v2_risk_and_limitations.csv
- research_selection_v2_quality_audit.csv
- research_selection_layer_v2_implementation_plan.md

Formal strategy git status:
```text
{status}
```

Formal strategy git diff:
```text
{diff}
```
"""


def write_outputs() -> dict[str, pd.DataFrame]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    inputs = load_inputs()
    summary = inputs["variant_summary"]
    rules = build_final_rule_set(summary)
    priority = build_review_priority_contract()
    dashboard = build_dashboard_contract_patch()
    products = build_data_product_spec()
    steps = build_implementation_steps()
    criteria = build_acceptance_criteria()
    risks = build_risks()
    audit = build_quality_audit(rules, priority, dashboard, products, steps, criteria, risks)

    rules.to_csv(OUTPUT_DIR / "research_selection_v2_final_rule_set.csv", index=False)
    priority.to_csv(OUTPUT_DIR / "research_selection_v2_review_priority_contract.csv", index=False)
    dashboard.to_csv(OUTPUT_DIR / "research_selection_v2_dashboard_contract_patch.csv", index=False)
    products.to_csv(OUTPUT_DIR / "research_selection_v2_data_product_spec.csv", index=False)
    steps.to_csv(OUTPUT_DIR / "research_selection_v2_implementation_steps.csv", index=False)
    criteria.to_csv(OUTPUT_DIR / "research_selection_v2_acceptance_criteria.csv", index=False)
    risks.to_csv(OUTPUT_DIR / "research_selection_v2_risk_and_limitations.csv", index=False)
    audit.to_csv(OUTPUT_DIR / "research_selection_v2_quality_audit.csv", index=False)
    (OUTPUT_DIR / "research_selection_layer_v2_implementation_plan.md").write_text(render_report(summary, rules, audit), encoding="utf-8")
    hit_count = _count_output_hits(OUTPUT_DIR)
    audit.loc[audit["metric"].eq("trading language hit count"), "value"] = hit_count
    audit.to_csv(OUTPUT_DIR / "research_selection_v2_quality_audit.csv", index=False)
    return {
        "rules": rules,
        "priority": priority,
        "dashboard": dashboard,
        "products": products,
        "steps": steps,
        "criteria": criteria,
        "risks": risks,
        "audit": audit,
    }


def main() -> pd.DataFrame:
    outputs = write_outputs()
    audit = outputs["audit"]
    print(audit.to_string(index=False))
    return audit


if __name__ == "__main__":
    main()
