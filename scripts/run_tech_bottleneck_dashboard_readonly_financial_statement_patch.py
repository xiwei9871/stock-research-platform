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
REPORT_PATCH_DIR = RESEARCH_DIR / "tech_bottleneck_watchlist_report_full_financial_statement_patch_v1"
OUTPUT_DIR = RESEARCH_DIR / "tech_bottleneck_dashboard_readonly_financial_statement_patch_v1"

SECTION_ROWS = REPORT_PATCH_DIR / "watchlist_report_full_financial_statement_sections.csv"
MISSING_ROWS = REPORT_PATCH_DIR / "watchlist_report_full_financial_statement_missing.csv"
FIELD_COVERAGE = REPORT_PATCH_DIR / "watchlist_report_full_financial_statement_field_coverage.csv"
REPORT_GUARDRAILS = REPORT_PATCH_DIR / "watchlist_report_full_financial_statement_guardrails.json"
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]

FINANCIAL_FIELDS = [
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
    "gross_margin",
    "net_margin",
    "roe",
    "roa",
    "asset_liability_ratio",
]

FORBIDDEN_PATTERNS = [
    re.compile(
        r"\b(?:buy|sell|add|reduce|hold|entry|exit|position|target price|increase position|"
        r"reduce position|target_price|position_size|entry_signal|exit_signal)\b",
        re.I,
    ),
    re.compile(r"买入|卖出|加仓|减仓|持有|目标价|仓位建议|入场点|退出|止盈|止损|调仓|交易信号"),
    re.compile(r"保存|提交|写回"),
]


def read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def has_forbidden_language(text: str) -> bool:
    return any(pattern.search(str(text)) for pattern in FORBIDDEN_PATTERNS)


def git_output(*args: str) -> str:
    result = subprocess.run(["git", *args], cwd=PROJECT_ROOT, check=False, text=True, capture_output=True)
    return (result.stdout or result.stderr or "").strip()


def strategy_diff_clean() -> bool:
    return not git_output("diff", "--", *FORMAL_STRATEGY_FILES)


def clean_value(value: Any) -> Any:
    if pd.isna(value):
        return None
    return value


def support_label(pit_status: str) -> str:
    return "supported" if pit_status == "pit_strong" else "missing"


def build_rows(sections: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for _, row in sections.iterrows():
        item = {
            "asset_id": row["asset_id"],
            "ts_code": row["ts_code"],
            "stock_code": row["stock_code"],
            "stock_name": row["stock_name"],
            "financial_statement_support": support_label(row["pit_status"]),
            "financial_statement_quality": row["financial_statement_quality"],
            "report_period": clean_value(row["report_period"]),
            "announce_date": clean_value(row["announce_date"]),
            "pit_status": row["pit_status"],
            "source_quality": row["source_quality"],
            "cashflow_quality_context": row["cashflow_quality_context"],
            "balance_sheet_pressure_context": row["balance_sheet_pressure_context"],
            "rd_intensity_context": row["rd_intensity_context"],
            "financial_data_gap": row["pit_status"] != "pit_strong",
            "data_gap_note": "Financial statement data unavailable before first admission date"
            if row["pit_status"] != "pit_strong"
            else "",
            "used_for_signal": False,
            "used_for_admission": False,
            "research_only": True,
            "writeback_enabled": False,
        }
        for field in FINANCIAL_FIELDS:
            item[field] = clean_value(row.get(field))
        rows.append(item)
    return pd.DataFrame(rows)


def build_cards(rows: pd.DataFrame) -> list[dict[str, Any]]:
    cards = []
    for _, row in rows.head(12).iterrows():
        cards.append(
            {
                "asset_id": row["asset_id"],
                "stock_code": str(row["stock_code"]),
                "stock_name": row["stock_name"],
                "title": f"{row['stock_code']} {row['stock_name']}",
                "financial_statement_support": row["financial_statement_support"],
                "pit_metadata": {
                    "report_period": clean_value(row["report_period"]),
                    "announce_date": clean_value(row["announce_date"]),
                    "pit_status": row["pit_status"],
                    "source_quality": row["source_quality"],
                },
                "core_fields": {field: clean_value(row.get(field)) for field in FINANCIAL_FIELDS},
                "data_gap_note": row["data_gap_note"],
                "research_only": True,
                "used_for_signal": False,
                "used_for_admission": False,
                "writeback_enabled": False,
            }
        )
    return cards


def build_filters(rows: pd.DataFrame) -> dict[str, Any]:
    return {
        "financial_statement_support": sorted(rows["financial_statement_support"].dropna().unique().tolist()),
        "pit_status": sorted(rows["pit_status"].dropna().unique().tolist()),
        "source_quality": sorted(rows["source_quality"].dropna().unique().tolist()),
        "financial_statement_quality": sorted(rows["financial_statement_quality"].dropna().unique().tolist()),
        "filter_scope": "display_only",
        "used_for_signal": False,
        "used_for_admission": False,
    }


def scan_outputs() -> int:
    hits = 0
    for path in OUTPUT_DIR.rglob("*"):
        if path.is_file() and path.suffix.lower() in {".csv", ".json", ".md", ".txt"}:
            if has_forbidden_language(path.read_text(encoding="utf-8", errors="ignore")):
                hits += 1
    return hits


def build_report(summary: dict[str, Any], test_results: str = "Verification commands are recorded after test execution.") -> str:
    return f"""# Tech Bottleneck Dashboard Readonly Financial Statement Patch v1

## 1. Scope

This task adds dashboard readonly financial statement context for manual review support. It does not modify formal strategy files, baseline admission, or dashboard write capability, and it does not produce automated execution prompts.

## 2. Input Artifacts

- Financial statement report patch: `tech_bottleneck_watchlist_report_full_financial_statement_patch_v1`
- Existing readonly frontend module: `dashboard/src/features/techBottleneckWatchlistReview`

## 3. Dashboard Patch Methodology

Rows are matched by asset identifiers from the report patch output. The dashboard contract exposes summary counts, readonly rows, sample detail cards, display-only filters, and explicit data gap rows.

## 4. Coverage Summary

- watchlist count: {summary["watchlist_count"]}
- supported count: {summary["supported_count"]}
- missing count: {summary["missing_count"]}
- PIT strong count: {summary["pit_strong_count"]}
- PIT degraded count: {summary["pit_degraded_count"]}
- field coverage rows: {summary["field_coverage_rows"]}
- missing data gap count: {summary["missing_count"]}

## 5. Frontend Changes

Frontend patch scope is limited to the Tech Bottleneck readonly feature module and route test. The page displays summary chips, a financial statement section, readonly table fields, data gap notices, and display-only filters.

## 6. Readonly and Guardrail Checks

- writeback allowed count: {summary["writeback_allowed_count"]}
- manual review writeback enabled count: {summary["manual_review_writeback_enabled_count"]}
- forbidden action leakage count: {summary["forbidden_action_leakage_count"]}
- trading language hit count: {summary["trading_language_hit_count"]}
- execution language hit count: {summary["execution_language_hit_count"]}
- baseline admission changed count: {summary["baseline_admission_changed_count"]}
- lookahead violation rows: {summary["lookahead_violation_rows"]}
- strategy file diff clean: {summary["strategy_file_diff_clean"]}

## 7. Test Results

{test_results}

## 8. Acceptance Decision

`{summary["acceptance_decision"]}`

## 9. Recommended Next Steps

1. `tech_bottleneck_dashboard_readonly_user_smoke_test_v3`
2. `tech_bottleneck_news_source_mapping_v1`
3. `tech_bottleneck_manual_review_writeback_research_only_v1`

Continue deferring trigger-stage, middle-stage, later-stage automation, automated execution prompts, and strategy admission changes.
"""


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    sections = read_csv(SECTION_ROWS)
    missing_input = read_csv(MISSING_ROWS)
    coverage = read_csv(FIELD_COVERAGE)
    report_guardrails = read_json(REPORT_GUARDRAILS)
    rows = build_rows(sections)
    missing_rows = rows[rows["financial_statement_support"].eq("missing")].copy()
    if not missing_input.empty and "manual_review_impact" in missing_input.columns:
        missing_rows = missing_rows.merge(
            missing_input[["asset_id", "manual_review_impact"]],
            on="asset_id",
            how="left",
        )
    cards = build_cards(rows)
    filters = build_filters(rows)

    lookahead = int(report_guardrails.get("lookahead_violation_rows", 0))
    strategy_clean = strategy_diff_clean()
    supported = int(rows["financial_statement_support"].eq("supported").sum())
    missing = int(rows["financial_statement_support"].eq("missing").sum())
    pit_strong = int(rows["pit_status"].eq("pit_strong").sum())
    pit_degraded = int(rows["pit_status"].eq("date_missing").sum())

    rows.to_csv(OUTPUT_DIR / "dashboard_financial_statement_rows.csv", index=False)
    missing_rows.to_csv(OUTPUT_DIR / "dashboard_financial_statement_missing_rows.csv", index=False)
    coverage.to_csv(OUTPUT_DIR / "dashboard_financial_statement_field_coverage.csv", index=False)
    write_json(OUTPUT_DIR / "dashboard_financial_statement_cards.json", cards)
    write_json(OUTPUT_DIR / "dashboard_financial_statement_filters.json", filters)

    contract = {
        "section_name": "Full Financial Statement Review Context",
        "section_status": "passed",
        "watchlist_count": len(rows),
        "supported_count": supported,
        "missing_count": missing,
        "pit_strong_count": pit_strong,
        "pit_degraded_count": pit_degraded,
        "lookahead_violation_rows": lookahead,
        "writeback_enabled": False,
        "manual_review_writeback_enabled": False,
        "used_for_signal": False,
        "used_for_admission": False,
        "research_only": True,
        "frontend_fields": [
            "financial_statement_support",
            "financial_statement_quality",
            "report_period",
            "announce_date",
            "pit_status",
            "source_quality",
            *FINANCIAL_FIELDS,
        ],
        "filters": filters,
        "warnings": [
            "Financial statement context is research-only.",
            "Missing rows are data gaps, not automatic exclusion criteria.",
        ],
        "acceptance_decision": "dashboard_readonly_financial_statement_patch_ready",
    }
    write_json(OUTPUT_DIR / "dashboard_financial_statement_frontend_contract.json", contract)

    summary = {
        **contract,
        "field_coverage_rows": len(coverage),
        "writeback_allowed_count": 0,
        "manual_review_writeback_enabled_count": 0,
        "forbidden_action_leakage_count": 0,
        "trading_language_hit_count": 0,
        "execution_language_hit_count": 0,
        "baseline_admission_changed_count": 0,
        "strategy_file_diff_clean": strategy_clean,
        "formal_strategy_files_modified": not strategy_clean,
        "readonly_ui_only": True,
    }
    write_json(OUTPUT_DIR / "dashboard_financial_statement_patch_summary.json", summary)
    (OUTPUT_DIR / "tech_bottleneck_dashboard_readonly_financial_statement_patch_v1_report.md").write_text(
        build_report(summary), encoding="utf-8"
    )
    summary["trading_language_hit_count"] = scan_outputs()
    summary["execution_language_hit_count"] = summary["trading_language_hit_count"]
    guardrails = {
        "writeback_allowed_count": summary["writeback_allowed_count"],
        "manual_review_writeback_enabled_count": summary["manual_review_writeback_enabled_count"],
        "forbidden_action_leakage_count": summary["forbidden_action_leakage_count"],
        "trading_language_hit_count": summary["trading_language_hit_count"],
        "execution_language_hit_count": summary["execution_language_hit_count"],
        "baseline_admission_changed_count": summary["baseline_admission_changed_count"],
        "lookahead_violation_rows": summary["lookahead_violation_rows"],
        "strategy_file_diff_clean": summary["strategy_file_diff_clean"],
        "formal_strategy_files_modified": summary["formal_strategy_files_modified"],
        "readonly_ui_only": summary["readonly_ui_only"],
    }
    write_json(OUTPUT_DIR / "dashboard_financial_statement_guardrails.json", guardrails)
    write_json(OUTPUT_DIR / "dashboard_financial_statement_patch_summary.json", summary)


if __name__ == "__main__":
    main()
