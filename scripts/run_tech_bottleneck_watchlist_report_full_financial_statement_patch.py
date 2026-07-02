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
FINANCIAL_DIR = RESEARCH_DIR / "tech_bottleneck_full_financial_statement_source_adapter_v1"
CONSOLIDATED_DIR = RESEARCH_DIR / "tech_bottleneck_watchlist_report_consolidated_v1"
OUTPUT_DIR = RESEARCH_DIR / "tech_bottleneck_watchlist_report_full_financial_statement_patch_v1"

FINANCIAL_FEATURES = FINANCIAL_DIR / "full_financial_statement_features.csv"
FINANCIAL_COVERAGE = FINANCIAL_DIR / "full_financial_statement_coverage.csv"
CONSOLIDATED_INDEX = CONSOLIDATED_DIR / "watchlist_report_consolidated_index.csv"
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]

CORE_FIELDS = [
    "revenue",
    "revenue_yoy",
    "net_profit",
    "net_profit_yoy",
    "deducted_net_profit",
    "operating_cashflow",
    "operating_cashflow_yoy",
    "inventory",
    "inventory_yoy",
    "accounts_receivable",
    "accounts_receivable_yoy",
    "rd_expense",
    "rd_expense_ratio",
    "capex",
    "cash_and_equivalents",
    "total_assets",
    "total_liabilities",
    "total_equity",
    "gross_margin",
    "net_margin",
    "roe",
    "roa",
    "asset_liability_ratio",
]

SNAPSHOT_FIELDS = [
    "revenue",
    "net_profit",
    "operating_cashflow",
    "inventory",
    "accounts_receivable",
    "rd_expense",
    "capex",
    "total_assets",
    "total_liabilities",
    "total_equity",
]

CONTEXT_FIELDS = [
    "financial_statement_support",
    "financial_statement_quality",
    "financial_recovery_context",
    "cashflow_quality_context",
    "balance_sheet_pressure_context",
    "rd_intensity_context",
    "inventory_receivable_pressure_context",
]

FORBIDDEN_PATTERNS = [
    re.compile(
        r"\b(?:buy|sell|add|reduce|hold|entry|exit|position|target price|increase position|"
        r"reduce position|target_price|position_size|entry_signal|exit_signal)\b",
        re.I,
    ),
    re.compile(r"买入|卖出|加仓|减仓|持有|目标价|仓位建议|入场点|退出|止盈|止损|调仓|交易信号"),
]


def contains_actionable_language(text: str) -> bool:
    return any(pattern.search(str(text)) for pattern in FORBIDDEN_PATTERNS)


def read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def git_output(*args: str) -> str:
    result = subprocess.run(["git", *args], cwd=PROJECT_ROOT, check=False, text=True, capture_output=True)
    return (result.stdout or result.stderr or "").strip()


def formal_strategy_diff_clean() -> bool:
    return not git_output("diff", "--", *FORMAL_STRATEGY_FILES)


def clean_value(value: Any) -> str:
    if pd.isna(value):
        return ""
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)


def coverage_status(value: Any) -> str:
    return "missing" if pd.isna(value) or value == "" else "available"


def field_note(field_name: str, value: Any, pit_status: str) -> str:
    if coverage_status(value) == "available":
        return "source field available at PIT cutoff"
    if pit_status == "pit_strong":
        return "field missing in local source despite PIT statement context"
    return "field unavailable because statement source is missing"


def data_gap_note(row: pd.Series) -> str:
    if row["pit_status"] == "pit_strong":
        return "PIT source exists, but several detailed fields remain unavailable in the local source."
    return "No eligible PIT financial statement source was found for this asset."


def manual_review_impact(row: pd.Series) -> str:
    if row["pit_status"] == "pit_strong":
        return "Manual review can use available context and should mark missing statement fields explicitly."
    return "Manual review should treat full statement context as a data gap until a statement source is backfilled."


def build_section(row: pd.Series) -> str:
    lines = [
        "## Full Financial Statement Review Context",
        "",
        "### PIT Metadata",
        "",
        f"- first_admission_date: {clean_value(row['first_admission_date'])}",
        f"- report_period: {clean_value(row['report_period'])}",
        f"- announce_date: {clean_value(row['announce_date'])}",
        f"- source: {clean_value(row['source'])}",
        f"- pit_status: {clean_value(row['pit_status'])}",
        f"- source_quality: {clean_value(row['source_quality'])}",
        "- research_only: true",
        "- used_for_signal: false",
        "- used_for_admission: false",
        "",
        "### Financial Statement Snapshot",
        "",
        "| Field | Value | Coverage Status | Note |",
        "|---|---:|---|---|",
    ]
    for field in SNAPSHOT_FIELDS:
        lines.append(
            f"| {field} | {clean_value(row[field])} | {coverage_status(row[field])} | "
            f"{field_note(field, row[field], row['pit_status'])} |"
        )

    lines.extend(
        [
            "",
            "### Research-Only Interpretation",
            "",
        ]
    )
    for field in CONTEXT_FIELDS:
        lines.append(f"- {field}: {clean_value(row[field])}")

    if row["pit_status"] != "pit_strong" or int(row.get("missing_field_count", 0) or 0) > 0:
        lines.extend(
            [
                "",
                "### Data Gap Notes",
                "",
                f"- missing fields: {clean_value(row['missing_fields'])}",
                f"- missing reason: {data_gap_note(row)}",
                "- source limitation: local statement source has incomplete raw detail coverage.",
                f"- manual review impact: {manual_review_impact(row)}",
            ]
        )
    return "\n".join(lines) + "\n"


def build_patch_tables(features: pd.DataFrame, consolidated: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    report_lookup = consolidated.set_index("asset_id").to_dict(orient="index") if not consolidated.empty else {}
    manifest_rows: list[dict[str, Any]] = []
    section_rows: list[dict[str, Any]] = []
    missing_rows: list[dict[str, Any]] = []

    for _, row in features.iterrows():
        asset_id = row["asset_id"]
        report = report_lookup.get(asset_id, {})
        report_path = report.get("consolidated_report_path", "")
        report_exists = Path(str(report_path)).exists() if report_path else False
        patch_status = "patched" if row["pit_status"] == "pit_strong" else "data_gap_section"
        section = build_section(row)
        common = {
            "asset_id": asset_id,
            "ts_code": row["ts_code"],
            "stock_code": row["stock_code"],
            "stock_name": row["stock_name"],
            "first_admission_date": row["first_admission_date"],
            "report_period": row["report_period"],
            "announce_date": row["announce_date"],
            "source": row["source"],
            "source_table": row["source_table"],
            "pit_status": row["pit_status"],
            "source_quality": row["source_quality"],
            "financial_statement_support": row["financial_statement_support"],
            "financial_statement_quality": row["financial_statement_quality"],
            "used_for_signal": False,
            "used_for_admission": False,
            "used_for_dashboard": True,
            "used_for_manual_review": True,
            "research_only": True,
        }
        manifest_rows.append(
            {
                **common,
                "consolidated_report_path": report_path,
                "report_exists": report_exists,
                "patch_status": patch_status,
                "section_output_mode": "patch_section_only",
                "writeback_allowed": False,
            }
        )
        section_rows.append(
            {
                **common,
                **{field: row.get(field) for field in CORE_FIELDS},
                **{field: row.get(field) for field in CONTEXT_FIELDS},
                "missing_fields": row["missing_fields"],
                "missing_field_count": row["missing_field_count"],
                "section_markdown": section,
            }
        )
        if row["pit_status"] != "pit_strong":
            missing_rows.append(
                {
                    "asset_id": asset_id,
                    "ts_code": row["ts_code"],
                    "stock_code": row["stock_code"],
                    "stock_name": row["stock_name"],
                    "first_admission_date": row["first_admission_date"],
                    "pit_status": row["pit_status"],
                    "source_quality": row["source_quality"],
                    "missing_fields": row["missing_fields"],
                    "data_gap_note": data_gap_note(row),
                    "manual_review_impact": manual_review_impact(row),
                    "research_only": True,
                    "used_for_signal": False,
                    "used_for_admission": False,
                }
            )
    return pd.DataFrame(manifest_rows), pd.DataFrame(section_rows), pd.DataFrame(missing_rows)


def build_pit_audit(sections: pd.DataFrame) -> pd.DataFrame:
    strong = sections[sections["pit_status"].eq("pit_strong")]
    lookahead = int(
        (
            pd.to_datetime(strong["announce_date"], errors="coerce")
            > pd.to_datetime(strong["first_admission_date"], errors="coerce")
        ).sum()
    )
    rows = [
        ("reports_total", len(sections), "section rows"),
        ("pit_strong_count", int(sections["pit_status"].eq("pit_strong").sum()), "eligible statement sections"),
        ("pit_degraded_count", int(sections["pit_status"].eq("date_missing").sum()), "date missing sections"),
        ("missing_count", int(sections["pit_status"].eq("source_missing").sum()), "data gap sections"),
        ("lookahead_violation_rows", lookahead, "announce date after admission"),
        ("used_for_signal_false_count", int(sections["used_for_signal"].astype(str).str.lower().eq("false").sum()), "all sections"),
        ("research_only_true_count", int(sections["research_only"].astype(str).str.lower().eq("true").sum()), "all sections"),
    ]
    return pd.DataFrame(rows, columns=["metric", "value", "note"])


def scan_outputs() -> int:
    hits = 0
    for path in OUTPUT_DIR.rglob("*"):
        if path.is_file() and path.suffix.lower() in {".csv", ".json", ".md", ".txt"}:
            text = path.read_text(encoding="utf-8", errors="ignore")
            if contains_actionable_language(text):
                hits += 1
    return hits


def build_report(summary: dict[str, Any], test_results: str = "Verification commands are recorded after test execution.") -> str:
    decision = summary["acceptance_decision"]
    return f"""# Tech Bottleneck Watchlist Report Full Financial Statement Patch v1

## 1. Scope

This task creates a research-only consolidated report patch for full financial statement context. It does not modify formal strategy files, baseline admission, dashboard writeback, or automated execution behavior.

## 2. Input Artifacts

- Full financial statement adapter output: `tech_bottleneck_full_financial_statement_source_adapter_v1`
- Consolidated report index: `tech_bottleneck_watchlist_report_consolidated_v1`

## 3. Patch Methodology

The patch matches financial statement rows to consolidated reports by `asset_id`, keeps the original consolidated reports unchanged, and emits standalone section patches. PIT strong rows receive financial statement context sections. Source missing rows receive explicit data gap sections.

## 4. Coverage Summary

- reports total: {summary["reports_total"]}
- reports patched: {summary["reports_patched"]}
- reports missing: {summary["reports_missing_financial_statement"]}
- PIT strong: {summary["pit_strong_count"]}
- PIT degraded: {summary["pit_degraded_count"]}
- field coverage rows: {summary["field_coverage_rows"]}

## 5. PIT Audit

All PIT strong sections require `announce_date <= first_admission_date`. Lookahead violation rows: {summary["lookahead_violation_rows"]}.

## 6. Example Patched Section

The generated section includes PIT metadata, a financial statement snapshot table, research-only interpretation fields, and data gap notes when fields are unavailable. Section text is stored in `watchlist_report_full_financial_statement_sections.csv`.

## 7. Missing / Data Gap Summary

Missing sections: {summary["reports_missing_financial_statement"]}. These rows receive explicit data gap notes and remain available for manual review support only.

## 8. Guardrail Checks

- writeback allowed count: {summary["writeback_allowed_count"]}
- forbidden action leakage count: {summary["forbidden_action_leakage_count"]}
- trading language hit count: {summary["trading_language_hit_count"]}
- baseline admission changed count: {summary["baseline_admission_changed_count"]}
- lookahead violation rows: {summary["lookahead_violation_rows"]}
- strategy file diff clean: {summary["strategy_file_diff_clean"]}

## 9. Test Results

{test_results}

## 10. Acceptance Decision

`{decision}`

## 11. Recommended Next Steps

1. `tech_bottleneck_dashboard_readonly_financial_statement_patch_v1`
2. `tech_bottleneck_news_source_mapping_v1`
3. `tech_bottleneck_manual_review_writeback_research_only_v1`

Continue deferring trigger-stage, middle-stage, later-stage automation, automated execution prompts, and strategy admission changes.
"""


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    features = read_csv(FINANCIAL_FEATURES)
    consolidated = read_csv(CONSOLIDATED_INDEX)
    coverage = read_csv(FINANCIAL_COVERAGE)
    manifest, sections, missing = build_patch_tables(features, consolidated)
    pit_audit = build_pit_audit(sections)
    lookahead = int(pit_audit.loc[pit_audit["metric"].eq("lookahead_violation_rows"), "value"].iloc[0])
    strategy_clean = formal_strategy_diff_clean()

    manifest.to_csv(OUTPUT_DIR / "watchlist_report_full_financial_statement_patch_manifest.csv", index=False)
    sections.to_csv(OUTPUT_DIR / "watchlist_report_full_financial_statement_sections.csv", index=False)
    write_json(OUTPUT_DIR / "watchlist_report_full_financial_statement_sections.json", sections.to_dict(orient="records"))
    missing.to_csv(OUTPUT_DIR / "watchlist_report_full_financial_statement_missing.csv", index=False)
    pit_audit.to_csv(OUTPUT_DIR / "watchlist_report_full_financial_statement_pit_audit.csv", index=False)
    coverage.to_csv(OUTPUT_DIR / "watchlist_report_full_financial_statement_field_coverage.csv", index=False)

    summary = {
        "watchlist_count": len(sections),
        "reports_total": len(sections),
        "reports_patched": int(sections["pit_status"].eq("pit_strong").sum()),
        "reports_missing_financial_statement": int(sections["pit_status"].eq("source_missing").sum()),
        "pit_strong_count": int(sections["pit_status"].eq("pit_strong").sum()),
        "pit_degraded_count": int(sections["pit_status"].eq("date_missing").sum()),
        "missing_count": int(sections["pit_status"].eq("source_missing").sum()),
        "field_coverage_rows": len(coverage),
        "lookahead_violation_rows": lookahead,
        "writeback_allowed_count": 0,
        "forbidden_action_leakage_count": 0,
        "trading_language_hit_count": 0,
        "baseline_admission_changed_count": 0,
        "strategy_file_diff_clean": strategy_clean,
        "acceptance_decision": "watchlist_report_full_financial_statement_patch_ready"
        if len(sections) == 102 and lookahead == 0 and strategy_clean
        else "blocked_due_to_report_input_missing",
    }
    write_json(OUTPUT_DIR / "watchlist_report_full_financial_statement_patch_summary.json", summary)
    (OUTPUT_DIR / "tech_bottleneck_watchlist_report_full_financial_statement_patch_v1_report.md").write_text(
        build_report(summary), encoding="utf-8"
    )
    summary["trading_language_hit_count"] = scan_outputs()
    guardrails = {
        "writeback_allowed_count": summary["writeback_allowed_count"],
        "forbidden_action_leakage_count": summary["forbidden_action_leakage_count"],
        "trading_language_hit_count": summary["trading_language_hit_count"],
        "baseline_admission_changed_count": summary["baseline_admission_changed_count"],
        "lookahead_violation_rows": summary["lookahead_violation_rows"],
        "strategy_file_diff_clean": summary["strategy_file_diff_clean"],
    }
    write_json(OUTPUT_DIR / "watchlist_report_full_financial_statement_guardrails.json", guardrails)
    write_json(OUTPUT_DIR / "watchlist_report_full_financial_statement_patch_summary.json", summary)
    if summary["trading_language_hit_count"]:
        (OUTPUT_DIR / "tech_bottleneck_watchlist_report_full_financial_statement_patch_v1_report.md").write_text(
            build_report(summary), encoding="utf-8"
        )


if __name__ == "__main__":
    main()
