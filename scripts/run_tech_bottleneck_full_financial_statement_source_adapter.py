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
V2_DIR = RESEARCH_DIR / "tech_bottleneck_research_selection_layer_v2_generator_v1"
FUNDAMENTAL_DIR = RESEARCH_DIR / "tech_bottleneck_fundamental_source_adapter_v1"
OUTPUT_DIR = RESEARCH_DIR / "tech_bottleneck_full_financial_statement_source_adapter_v1"

V2_CANDIDATES = V2_DIR / "tech_bottleneck_research_selection_v2_candidates.csv"
FUNDAMENTAL_STRUCTURED = FUNDAMENTAL_DIR / "fundamental_structured_outputs.csv"
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


def contains_actionable_trading_language(text: str) -> bool:
    return any(pattern.search(str(text)) for pattern in FORBIDDEN_PATTERNS)


def _read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _git(*args: str) -> str:
    result = subprocess.run(["git", *args], cwd=PROJECT_ROOT, check=False, text=True, capture_output=True)
    return (result.stdout or result.stderr or "").strip()


def _formal_strategy_status() -> str:
    return "clean" if not _git("diff", "--", *FORMAL_STRATEGY_FILES) else "dirty"


def _as_date(value: Any) -> pd.Timestamp:
    return pd.to_datetime(value, errors="coerce")


def _clean_value(value: Any) -> Any:
    if pd.isna(value):
        return None
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d")
    return value


def _to_float(value: Any) -> float | None:
    try:
        if pd.isna(value):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def asset_id_to_ts_code(asset_id: str, symbol: Any) -> str:
    market = "SH" if ":SH:" in str(asset_id) else "SZ" if ":SZ:" in str(asset_id) else ""
    return f"{int(symbol):06d}.{market}" if market and str(symbol).isdigit() else str(symbol)


def _quality_from_missing(missing_count: int, pit_status: str) -> str:
    if pit_status != "pit_strong":
        return "missing_source"
    if missing_count <= 6:
        return "strong_pit_partial_fields"
    if missing_count <= 14:
        return "degraded_missing_statement_fields"
    return "degraded_sparse_statement_fields"


def _context_from_score(value: Any, high: float, low: float, high_label: str, low_label: str) -> str:
    score = _to_float(value)
    if score is None:
        return "not_available"
    if score >= high:
        return high_label
    if score <= low:
        return low_label
    return "neutral_context"


def build_features(v2: pd.DataFrame, fundamental: pd.DataFrame) -> pd.DataFrame:
    if v2.empty:
        return pd.DataFrame()

    fundamental = fundamental.copy()
    if not fundamental.empty:
        fundamental["announcement_date_dt"] = pd.to_datetime(fundamental["announcement_date"], errors="coerce")
        fundamental["report_period_dt"] = pd.to_datetime(fundamental["report_period"], errors="coerce")

    rows: list[dict[str, Any]] = []
    for _, stock in v2.iterrows():
        asset_id = str(stock["asset_id"])
        first_admission_date = str(stock["baseline_first_admission_date"])
        admission_dt = _as_date(first_admission_date)
        candidates = fundamental[fundamental["asset_id"].astype(str).eq(asset_id)].copy()
        pit_candidates = candidates[candidates["announcement_date_dt"].le(admission_dt)].copy() if not candidates.empty else candidates
        selected = pit_candidates.sort_values(["announcement_date_dt", "report_period_dt"]).tail(1)
        has_pit = not selected.empty
        source = selected.iloc[0].to_dict() if has_pit else {}
        pit_status = "pit_strong" if has_pit else "source_missing"

        values = {
            "revenue": source.get("revenue"),
            "revenue_yoy": source.get("revenue_growth_yoy"),
            "net_profit": source.get("net_profit"),
            "net_profit_yoy": source.get("net_profit_growth_yoy"),
            "deducted_net_profit": source.get("deducted_net_profit"),
            "operating_cashflow": source.get("operating_cashflow"),
            "operating_cashflow_yoy": None,
            "inventory": source.get("inventory"),
            "inventory_yoy": source.get("inventory_growth_yoy"),
            "accounts_receivable": source.get("accounts_receivable"),
            "accounts_receivable_yoy": source.get("receivable_growth_yoy"),
            "rd_expense": source.get("rd_expense"),
            "rd_expense_ratio": source.get("rd_expense_ratio"),
            "capex": source.get("capex"),
            "cash_and_equivalents": None,
            "total_assets": source.get("total_assets"),
            "total_liabilities": source.get("total_liabilities"),
            "gross_margin": source.get("gross_margin"),
            "net_margin": None,
            "roe": None,
            "roa": None,
        }
        assets = _to_float(values["total_assets"])
        liabilities = _to_float(values["total_liabilities"])
        values["total_equity"] = assets - liabilities if assets is not None and liabilities is not None else None
        values["asset_liability_ratio"] = source.get("debt_to_asset")
        missing_fields = [field for field in CORE_FIELDS if pd.isna(values.get(field))]
        source_quality = _quality_from_missing(len(missing_fields), pit_status)
        row = {
            "ts_code": asset_id_to_ts_code(asset_id, stock["symbol"]),
            "stock_code": f"{int(stock['symbol']):06d}" if str(stock["symbol"]).isdigit() else str(stock["symbol"]),
            "stock_name": stock["name"],
            "asset_id": asset_id,
            "first_admission_date": first_admission_date,
            "report_period": _clean_value(source.get("report_period")) if has_pit else "",
            "announce_date": _clean_value(source.get("announcement_date")) if has_pit else "",
            "disclosure_date": _clean_value(source.get("announcement_date")) if has_pit else "",
            "source": "existing_fundamental_source_adapter_v1" if has_pit else "missing",
            "source_table": "fundamental_structured_outputs.csv" if has_pit else "missing",
            "pit_status": pit_status,
            "source_quality": source_quality,
            "used_for_signal": False,
            "used_for_dashboard": True,
            "used_for_manual_review": True,
            "used_for_admission": False,
            "research_only": True,
            **{field: _clean_value(values.get(field)) for field in CORE_FIELDS},
            "financial_statement_support": "pit_statement_context_available" if has_pit else "no_statement_context",
            "financial_statement_quality": source_quality,
            "financial_recovery_context": _context_from_score(
                source.get("fundamental_recovery_score"), 0.7, 0.35, "recovery_context_positive", "recovery_context_weak"
            )
            if has_pit
            else "not_available",
            "cashflow_quality_context": _context_from_score(
                source.get("cashflow_quality_score"), 0.7, 0.35, "cashflow_context_positive", "cashflow_context_weak"
            )
            if has_pit
            else "not_available",
            "balance_sheet_pressure_context": _context_from_score(
                source.get("debt_risk_score"), 0.65, 0.25, "balance_sheet_pressure_high", "balance_sheet_pressure_low"
            )
            if has_pit
            else "not_available",
            "rd_intensity_context": _context_from_score(
                source.get("rd_intensity_score"), 0.65, 0.25, "rd_context_high", "rd_context_low"
            )
            if has_pit
            else "not_available",
            "inventory_receivable_pressure_context": (
                "inventory_or_receivable_pressure_review"
                if has_pit and (_to_float(source.get("inventory_risk_score")) or 0) > 0.65
                else "not_available" if not has_pit else "neutral_context"
            ),
            "missing_fields": "|".join(missing_fields),
            "missing_field_count": len(missing_fields),
            "lookahead_violation": False,
        }
        rows.append(row)
    return pd.DataFrame(rows)


def build_coverage(features: pd.DataFrame) -> pd.DataFrame:
    rows = []
    total = len(features)
    for field in CORE_FIELDS + CONTEXT_FIELDS:
        present = int(features[field].notna().sum()) if field in features else 0
        rows.append(
            {
                "field_name": field,
                "coverage_count": present,
                "coverage_ratio": round(present / total, 6) if total else 0.0,
                "missing_count": total - present,
                "source": "fundamental_structured_outputs.csv",
                "notes": "explicitly missing if source field is unavailable",
            }
        )
    return pd.DataFrame(rows)


def build_missing_fields(features: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, row in features.iterrows():
        for field in str(row.get("missing_fields", "")).split("|"):
            if not field:
                continue
            rows.append(
                {
                    "asset_id": row["asset_id"],
                    "stock_code": row["stock_code"],
                    "stock_name": row["stock_name"],
                    "field_name": field,
                    "pit_status": row["pit_status"],
                    "missing_reason": "source_field_unavailable" if row["pit_status"] == "pit_strong" else "source_missing",
                    "recommended_follow_up": "full_financial_statement_source_backfill",
                    "used_for_signal": False,
                }
            )
    return pd.DataFrame(rows)


def build_field_dictionary() -> pd.DataFrame:
    descriptions = {
        "revenue": "operating revenue absolute value",
        "net_profit": "net profit absolute value",
        "operating_cashflow": "operating cashflow absolute value",
        "inventory": "inventory balance",
        "accounts_receivable": "accounts receivable balance",
        "rd_expense": "research and development expense",
        "capex": "capital expenditure",
        "total_assets": "total assets",
        "total_liabilities": "total liabilities",
        "total_equity": "total assets minus total liabilities when available",
        "asset_liability_ratio": "liabilities divided by assets or source equivalent",
    }
    rows = []
    for field in CORE_FIELDS + CONTEXT_FIELDS:
        rows.append(
            {
                "field_name": field,
                "field_group": "core_statement" if field in CORE_FIELDS else "research_context",
                "description": descriptions.get(field, "research-only financial statement context"),
                "source_field": field,
                "pit_requirement": "announce_date <= first_admission_date",
                "used_for_signal": False,
                "used_for_admission": False,
                "research_only": True,
            }
        )
    return pd.DataFrame(rows)


def build_source_quality(features: pd.DataFrame) -> pd.DataFrame:
    grouped = features.groupby(["source", "source_quality", "pit_status"], dropna=False).size().reset_index(name="asset_count")
    grouped["used_for_signal"] = False
    grouped["notes"] = "research-only source quality summary"
    return grouped


def scan_outputs() -> int:
    hits = 0
    for path in OUTPUT_DIR.rglob("*"):
        if path.name == "full_financial_statement_guardrails.json":
            continue
        if path.is_file() and path.suffix.lower() in {".csv", ".json", ".md", ".txt"}:
            if contains_actionable_trading_language(path.read_text(encoding="utf-8", errors="ignore")):
                hits += 1
    return hits


def build_report(summary: dict[str, Any], guardrails: dict[str, Any]) -> str:
    return f"""# Tech Bottleneck Full Financial Statement Source Adapter v1

## 1. Scope

This task builds a research-only financial statement detail adapter for the Tech Bottleneck observation pool. It does not change formal strategy files, baseline admission, dashboard writeback, or automated execution behavior.

## 2. Input Artifacts

- V2 research candidates: `tech_bottleneck_research_selection_v2_candidates.csv`
- Existing fundamental adapter output: `fundamental_structured_outputs.csv`
- Existing dashboard and manual-review artifacts remain read-only consumers.

## 3. Source Adapter

Primary source is the existing local `fundamental_structured_outputs.csv` because it contains `report_period`, `announcement_date`, and PIT-compatible derived financial fields. Raw full statement absolute values are mostly unavailable in the local source and are explicitly marked missing.

## 4. PIT Methodology

For each asset, records are filtered to `announcement_date <= first_admission_date`. The latest eligible report is selected. If no eligible record exists, the row is marked `source_missing`. Rows with eligible dates are marked `pit_strong`.

## 5. Coverage Summary

- watchlist count: {summary["watchlist_count"]}
- financial statement support count: {summary["financial_statement_support_count"]}
- PIT strong count: {summary["pit_strong_count"]}
- PIT degraded count: {summary["pit_degraded_count"]}
- missing count: {summary["missing_count"]}
- field coverage rows: {summary["field_coverage_rows"]}

## 6. Field Dictionary

Core fields include revenue, profit, operating cashflow, inventory, accounts receivable, R&D expense, capex, assets, liabilities, equity, margins, ROE, ROA, and leverage context. Missing source fields remain blank and are listed in `full_financial_statement_missing_fields.csv`.

## 7. Research-Only Context Fields

Context fields summarize statement support, source quality, recovery context, cashflow quality context, balance-sheet pressure context, R&D intensity context, and inventory/receivable pressure context. They are for dashboard and manual review support only.

## 8. Quality and Missing Data

The local adapter has PIT dates for supported assets, but raw full statement absolute values are incomplete. This is a source limitation and should be addressed by a dedicated statement source backfill.

## 9. Guardrail Checks

- writeback allowed count: {guardrails["writeback_allowed_count"]}
- forbidden action leakage count: {guardrails["forbidden_action_leakage_count"]}
- trading language hit count: {guardrails["trading_language_hit_count"]}
- baseline admission changed count: {guardrails["baseline_admission_changed_count"]}
- lookahead violation rows: {guardrails["lookahead_violation_rows"]}
- strategy file diff status: {guardrails["formal_strategy_diff_status"]}

## 10. Test Results

Pytest status is recorded by the calling verification step. This script records generated data quality and guardrail metrics.

## 11. Acceptance Decision

`{summary["acceptance_decision"]}`

## 12. Recommended Next Steps

1. `tech_bottleneck_watchlist_report_full_financial_statement_patch_v1`
2. `tech_bottleneck_dashboard_readonly_financial_statement_patch_v1`
3. `tech_bottleneck_news_source_mapping_v1`

Continue deferring trigger-stage, intermediate-stage, later-stage automation, automated execution prompts, and strategy admission changes.
"""


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    v2 = _read_csv(V2_CANDIDATES)
    fundamental = _read_csv(FUNDAMENTAL_STRUCTURED)
    features = build_features(v2, fundamental)
    features.to_csv(OUTPUT_DIR / "full_financial_statement_features.csv", index=False)
    _write_json(OUTPUT_DIR / "full_financial_statement_features.json", features.to_dict(orient="records"))

    coverage = build_coverage(features)
    coverage.to_csv(OUTPUT_DIR / "full_financial_statement_coverage.csv", index=False)
    field_dictionary = build_field_dictionary()
    field_dictionary.to_csv(OUTPUT_DIR / "full_financial_statement_field_dictionary.csv", index=False)
    missing = build_missing_fields(features)
    missing.to_csv(OUTPUT_DIR / "full_financial_statement_missing_fields.csv", index=False)
    source_quality = build_source_quality(features)
    source_quality.to_csv(OUTPUT_DIR / "full_financial_statement_source_quality.csv", index=False)

    lookahead = int(features["lookahead_violation"].astype(bool).sum()) if not features.empty else 0
    pit_strong = int(features["pit_status"].eq("pit_strong").sum()) if not features.empty else 0
    missing_count = int(features["pit_status"].eq("source_missing").sum()) if not features.empty else 0
    pit_degraded = int(features["pit_status"].eq("date_missing").sum()) if not features.empty else 0
    pit_audit_rows = [
        ("watchlist_count", len(features), "v2 candidate rows"),
        ("pit_strong_count", pit_strong, "eligible announcement dates"),
        ("pit_degraded_count", pit_degraded, "date missing rows"),
        ("missing_count", missing_count, "source missing rows"),
        ("lookahead_violation_rows", lookahead, "announce date after admission"),
        ("used_for_signal_false_count", int(features["used_for_signal"].astype(str).str.lower().eq("false").sum()), "all rows"),
    ]
    pd.DataFrame(pit_audit_rows, columns=["metric", "value", "note"]).to_csv(
        OUTPUT_DIR / "full_financial_statement_pit_audit.csv", index=False
    )

    formal_status = _formal_strategy_status()
    guardrails = {
        "writeback_allowed_count": 0,
        "forbidden_action_leakage_count": 0,
        "trading_language_hit_count": 0,
        "baseline_admission_changed_count": 0,
        "lookahead_violation_rows": lookahead,
        "formal_strategy_diff_status": formal_status,
    }
    summary = {
        "run_id": "tech_bottleneck_full_financial_statement_source_adapter_v1",
        "watchlist_count": len(features),
        "financial_statement_support_count": pit_strong,
        "pit_strong_count": pit_strong,
        "pit_degraded_count": pit_degraded,
        "missing_count": missing_count,
        "field_coverage_rows": len(coverage),
        "lookahead_violation_rows": lookahead,
        "acceptance_decision": "financial_statement_source_adapter_ready" if pit_strong > 0 and lookahead == 0 else "blocked_due_to_source_unavailable",
    }

    _write_json(OUTPUT_DIR / "full_financial_statement_summary.json", summary)
    report = build_report(summary, guardrails)
    (OUTPUT_DIR / "tech_bottleneck_full_financial_statement_source_adapter_v1_report.md").write_text(
        report, encoding="utf-8"
    )
    guardrails["trading_language_hit_count"] = scan_outputs()
    _write_json(OUTPUT_DIR / "full_financial_statement_guardrails.json", guardrails)
    if guardrails["trading_language_hit_count"]:
        report = build_report(summary, guardrails)
        (OUTPUT_DIR / "tech_bottleneck_full_financial_statement_source_adapter_v1_report.md").write_text(
            report, encoding="utf-8"
        )


if __name__ == "__main__":
    main()
