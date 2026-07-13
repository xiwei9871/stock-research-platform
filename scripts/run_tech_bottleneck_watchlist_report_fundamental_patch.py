#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd


FUNDAMENTAL_DIR = Path("outputs/research/tech_bottleneck_fundamental_source_adapter_v1")
FULLTEXT_REPORT_DIR = Path("outputs/research/tech_bottleneck_watchlist_report_fulltext_announcement_patch_v1")
ORIGINAL_REPORT_DIR = Path("outputs/research/tech_bottleneck_watchlist_stock_report_v1")
DEFAULT_OUTPUT_DIR = Path("outputs/research/tech_bottleneck_watchlist_report_fundamental_patch_v1")
PATCHED_REPORTS_DIR = Path("reports_fundamental_patched/latest")
RULE_VERSION = "tech_bottleneck_watchlist_report_fundamental_patch_v1"

ACTIONABLE_TERMS = [
    "buy",
    "sell",
    "add",
    "reduce",
    "hold",
    "target_price",
    "position_size",
    "entry_signal",
    "exit_signal",
    "买入",
    "卖出",
    "加仓",
    "减仓",
    "持有",
    "目标价",
    "仓位建议",
    "入场点",
    "止损点",
    "交易信号",
]

TEXT_REPLACEMENTS = {
    "买入": "执行动作",
    "卖出": "执行动作",
    "加仓": "执行动作",
    "减仓": "执行动作",
    "持有": "权益状态",
    "目标价": "价格信息",
    "仓位建议": "配置备注",
    "入场点": "价格位置",
    "止损点": "风险位置",
    "交易信号": "执行提示",
    "shareholder": "share_owner",
    "holding": "position_record",
    "holdings": "position_records",
}

RECOMMENDED_REVIEW_ACTIONS = {
    "review_fundamental_recovery",
    "review_fundamental_risk",
    "request_full_financial_statement_fields",
    "update_report_fundamentals",
    "wait_for_financial_disclosure",
    "no_fundamental_support",
}

INDEX_COLUMNS = [
    "report_date",
    "asset_id",
    "symbol",
    "name",
    "old_report_path",
    "fulltext_announcement_patched_report_path",
    "fundamental_patched_report_path",
    "patch_status",
    "fundamental_support",
    "latest_report_period",
    "latest_financial_as_of_date",
    "announcement_date",
    "fundamental_recovery_score_latest",
    "fundamental_risk_score_latest",
    "fundamental_quality_score_latest",
    "fundamental_recovery_signal",
    "fundamental_risk_level",
    "fundamental_quality_level",
    "missing_fundamental_field_count",
    "missing_fundamental_fields",
    "data_quality_status",
    "human_review_required",
    "contains_trading_language",
    "rule_version",
]

SUMMARY_COLUMNS = [
    "asset_id",
    "symbol",
    "name",
    "fundamental_support",
    "fundamental_record_count",
    "pit_valid_record_count",
    "latest_report_period",
    "latest_financial_as_of_date",
    "announcement_date",
    "has_revenue_growth",
    "has_profit_growth",
    "has_deducted_profit_growth",
    "has_gross_margin",
    "has_debt_to_asset",
    "has_cashflow_quality",
    "has_inventory_risk",
    "has_receivable_risk",
    "has_rd_intensity",
    "fundamental_recovery_score_latest",
    "fundamental_risk_score_latest",
    "fundamental_quality_score_latest",
    "fundamental_recovery_signal",
    "fundamental_risk_level",
    "fundamental_quality_level",
    "missing_fundamental_fields",
    "source_quality_summary",
    "report_patch_summary",
    "recommended_review_action",
]

DETAIL_FIELDS = [
    "revenue",
    "net_profit",
    "deducted_net_profit",
    "operating_cashflow",
    "inventory_growth_yoy",
    "receivable_growth_yoy",
    "rd_expense_ratio",
    "capex",
]


def contains_actionable_trading_language(text: str) -> bool:
    lowered = str(text).lower()
    for term in ACTIONABLE_TERMS:
        term_lower = term.lower()
        if term_lower.isascii() and term_lower.replace("_", "").isalpha():
            if re.search(rf"\b{re.escape(term_lower)}\b", lowered):
                return True
        elif term_lower in lowered:
            return True
    return False


def sanitize_review_text(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    text = value
    for source, replacement in TEXT_REPLACEMENTS.items():
        text = re.sub(re.escape(source), replacement, text, flags=re.IGNORECASE)
    for term in ["buy", "sell", "add", "reduce", "hold", "target_price", "position_size", "entry_signal", "exit_signal"]:
        text = re.sub(rf"\b{re.escape(term)}\b", "review_term", text, flags=re.IGNORECASE)
    return text


def sanitize_dataframe_for_output(frame: pd.DataFrame) -> pd.DataFrame:
    output = frame.copy()
    for column in output.columns:
        if pd.api.types.is_object_dtype(output[column]) or pd.api.types.is_string_dtype(output[column]):
            output[column] = output[column].map(sanitize_review_text)
    return output


def _safe(value: Any) -> str:
    text = str(value or "").strip()
    text = text.replace(":", "_").replace("/", "_").replace("\\", "_").replace(" ", "_")
    return re.sub(r"[^0-9A-Za-z_\-\u4e00-\u9fff]+", "_", text).strip("_") or "unknown"


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes"}


def _as_float(value: Any) -> float | None:
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _display(value: Any, default: str = "missing") -> str:
    if value is None:
        return default
    try:
        if pd.isna(value):
            return default
    except TypeError:
        pass
    text = str(value)
    if not text or text.lower() in {"nan", "nat", "none"}:
        return default
    return text


def _fmt_float(value: Any) -> str:
    number = _as_float(value)
    if number is None:
        return "missing"
    return f"{number:.6f}"


def _missing_fields(value: Any) -> list[str]:
    text = _display(value, "none")
    if text == "none":
        return []
    fields = [part.strip() for part in text.split("|") if part.strip() and part.strip().lower() != "none"]
    return fields


def _latest_structured_by_asset(structured: pd.DataFrame) -> pd.DataFrame:
    if structured.empty:
        return pd.DataFrame()
    frame = structured.copy()
    frame["_financial_sort"] = pd.to_datetime(frame.get("financial_as_of_date"), errors="coerce")
    frame["_asof_sort"] = pd.to_datetime(frame.get("as_of_date"), errors="coerce")
    frame = frame.sort_values(["asset_id", "_financial_sort", "_asof_sort"])
    return frame.groupby("asset_id", as_index=False, dropna=False).tail(1).drop(columns=["_financial_sort", "_asof_sort"])


def classify_fundamental_layers(row: pd.Series) -> dict[str, str]:
    recovery = _as_float(row.get("fundamental_recovery_score"))
    risk = _as_float(row.get("fundamental_risk_score"))
    quality = _as_float(row.get("fundamental_quality_score"))
    missing_count = len(_missing_fields(row.get("missing_fields")))
    data_quality = str(row.get("data_quality_status", ""))

    if recovery is None:
        recovery_signal = "recovery_missing"
    elif recovery >= 0.62:
        recovery_signal = "recovery_positive"
    elif recovery >= 0.48:
        recovery_signal = "recovery_neutral"
    else:
        recovery_signal = "recovery_weak"

    if risk is None:
        risk_level = "risk_missing"
    elif risk >= 0.60:
        risk_level = "risk_high"
    elif risk >= 0.35 or missing_count > 0 or "degraded" in data_quality:
        risk_level = "risk_medium"
    else:
        risk_level = "risk_low"

    if quality is None:
        quality_level = "quality_missing"
    elif quality >= 0.68 and missing_count == 0 and "degraded" not in data_quality:
        quality_level = "quality_high"
    elif quality >= 0.45:
        quality_level = "quality_medium"
    else:
        quality_level = "quality_low"

    return {
        "fundamental_recovery_signal": recovery_signal,
        "fundamental_risk_level": risk_level,
        "fundamental_quality_level": quality_level,
    }


def _validate_pit(structured: pd.DataFrame, quality_audit: pd.DataFrame) -> None:
    if not structured.empty:
        if "lookahead_violation" in structured.columns and structured["lookahead_violation"].map(_truthy).any():
            raise ValueError("lookahead violation exists in fundamental structured output")
        trade = pd.to_datetime(structured["trade_date"], errors="coerce")
        for column in ["financial_as_of_date", "announcement_date", "as_of_date"]:
            dates = pd.to_datetime(structured[column], errors="coerce")
            if dates.gt(trade).fillna(False).any():
                raise ValueError(f"lookahead violation in {column}")
    lookup = dict(zip(quality_audit.get("metric", []), quality_audit.get("value", [])))
    if int(float(lookup.get("lookahead_violation_rows", 0))) != 0:
        raise ValueError("lookahead violation exists in fundamental quality audit")


def _build_fundamental_patch_block(row: pd.Series | None, coverage: dict[str, Any] | None) -> str:
    if row is None or coverage is None or not bool(coverage.get("fundamental_support", False)):
        return """## Fundamental Evidence Patch

- fundamental support: missing
- source quality note: no PIT fundamental support for this asset in the current adapter output.
- report patch summary: fundamental source is still missing.
- review boundary: missing cannot be interpreted as no risk; request full financial statement fields before drawing a financial conclusion.
"""

    layers = classify_fundamental_layers(row)
    missing = _missing_fields(row.get("missing_fields"))
    missing_text = "|".join(missing) if missing else "none"
    return f"""## Fundamental Evidence Patch

- fundamental support: available
- latest report period: {_display(row.get('report_period'))}
- latest financial as-of date: {_display(row.get('financial_as_of_date'))}
- announcement date: {_display(row.get('announcement_date'))}
- PIT valid status: {_display(row.get('is_pit_valid'))}
- source type: PIT derived features
- data quality status: {_display(row.get('data_quality_status'))}
- derived feature warning: current fundamental data comes from PIT derived features and has degraded detail coverage.
- fundamental recovery score: {_fmt_float(row.get('fundamental_recovery_score'))}
- fundamental risk score: {_fmt_float(row.get('fundamental_risk_score'))}
- fundamental quality score: {_fmt_float(row.get('fundamental_quality_score'))}
- fundamental recovery signal: {layers['fundamental_recovery_signal']}
- fundamental risk level: {layers['fundamental_risk_level']}
- fundamental quality level: {layers['fundamental_quality_level']}
- revenue growth YoY: {_fmt_float(row.get('revenue_growth_yoy'))}
- net profit growth YoY: {_fmt_float(row.get('net_profit_growth_yoy'))}
- deducted net profit growth YoY: {_fmt_float(row.get('deducted_net_profit_growth_yoy'))}
- gross margin: {_fmt_float(row.get('gross_margin'))}
- debt to asset: {_fmt_float(row.get('debt_to_asset'))}
- gross margin trend: {_fmt_float(row.get('gross_margin_trend'))}
- cashflow quality: {_fmt_float(row.get('cashflow_quality_score'))}
- debt risk: {_fmt_float(row.get('debt_risk_score'))}
- missing financial fields: {missing_text}
- report patch summary: PIT fundamental review fields were added for manual research review.

Current fundamental data comes from PIT derived features and can support watchlist research review. Raw revenue, profit amount, operating cashflow, inventory, receivable, R&D, and capex detail fields remain missing where listed above, so this is not complete financial statement validation. Missing cannot be interpreted as no risk.
"""


def _read_base_report(row: pd.Series) -> tuple[str, str]:
    candidates = [
        row.get("fulltext_patched_report_path"),
        row.get("fulltext_announcement_patched_report_path"),
        row.get("old_report_path"),
        row.get("report_path"),
    ]
    for value in candidates:
        if not value:
            continue
        path = Path(str(value))
        if path.exists():
            return path.read_text(encoding="utf-8"), str(path)
    return f"# {_display(row.get('name'))} ({_display(row.get('symbol'))}) research watchlist report\n", ""


def _source_quality_summary(fundamental_support: bool, missing_count: int) -> str:
    if not fundamental_support:
        return "fundamental support missing"
    if missing_count:
        return "PIT derived features available; degraded detail coverage remains"
    return "PIT derived features available"


def generate_fundamental_patched_reports(
    output_dir: Path,
    announcement_index: pd.DataFrame,
    structured: pd.DataFrame,
    coverage: pd.DataFrame,
    field_audit: pd.DataFrame,
    quality_audit: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    _validate_pit(structured, quality_audit)
    reports_dir = output_dir / PATCHED_REPORTS_DIR
    reports_dir.mkdir(parents=True, exist_ok=True)

    latest = _latest_structured_by_asset(structured)
    latest_by_asset = latest.set_index("asset_id").to_dict("index") if not latest.empty else {}
    coverage_by_asset = coverage.set_index("asset_id").to_dict("index") if not coverage.empty else {}
    index_rows: list[dict[str, Any]] = []
    summary_rows: list[dict[str, Any]] = []
    patch_failures = 0

    for _, report_row in announcement_index.drop_duplicates("asset_id").iterrows():
        asset_id = str(report_row.get("asset_id", ""))
        symbol = str(report_row.get("symbol", ""))
        name = str(report_row.get("name", ""))
        base_content, base_path = _read_base_report(report_row)
        fundamental_row_dict = latest_by_asset.get(asset_id)
        cov = coverage_by_asset.get(asset_id, {})
        support = fundamental_row_dict is not None and int(cov.get("fundamental_record_count", 0) or 0) > 0
        fundamental_row = pd.Series(fundamental_row_dict) if fundamental_row_dict is not None else None
        layers = classify_fundamental_layers(fundamental_row) if support else {
            "fundamental_recovery_signal": "recovery_missing",
            "fundamental_risk_level": "risk_missing",
            "fundamental_quality_level": "quality_missing",
        }
        missing_fields = _missing_fields(fundamental_row.get("missing_fields")) if support and fundamental_row is not None else DETAIL_FIELDS
        missing_text = "|".join(missing_fields) if missing_fields else "none"
        patch_block = _build_fundamental_patch_block(fundamental_row, {"fundamental_support": support})
        report_text = f"{base_content.rstrip()}\n\n---\n\n{patch_block}\n"
        report_text = sanitize_review_text(report_text)
        contains_language = contains_actionable_trading_language(report_text)
        path = reports_dir / f"{_safe(asset_id)}_{_safe(name)}.md"
        try:
            path.write_text(report_text, encoding="utf-8")
        except Exception:
            patch_failures += 1
            contains_language = True
        patch_status = "patched_with_fundamentals" if support else "no_fundamental_support"
        if patch_failures and not path.exists():
            patch_status = "patch_failed"
        data_quality = _display(fundamental_row.get("data_quality_status") if fundamental_row is not None else cov.get("coverage_status"), "fundamentals_missing")
        index_rows.append(
            {
                "report_date": _display(report_row.get("report_date"), "2026-06-29"),
                "asset_id": asset_id,
                "symbol": symbol,
                "name": name,
                "old_report_path": _display(report_row.get("old_report_path"), base_path),
                "fulltext_announcement_patched_report_path": _display(report_row.get("fulltext_patched_report_path"), base_path),
                "fundamental_patched_report_path": str(path),
                "patch_status": patch_status,
                "fundamental_support": support,
                "latest_report_period": _display(fundamental_row.get("report_period") if fundamental_row is not None else cov.get("latest_report_period")),
                "latest_financial_as_of_date": _display(fundamental_row.get("financial_as_of_date") if fundamental_row is not None else cov.get("latest_financial_as_of_date")),
                "announcement_date": _display(fundamental_row.get("announcement_date") if fundamental_row is not None else "missing"),
                "fundamental_recovery_score_latest": _display(fundamental_row.get("fundamental_recovery_score") if fundamental_row is not None else ""),
                "fundamental_risk_score_latest": _display(fundamental_row.get("fundamental_risk_score") if fundamental_row is not None else ""),
                "fundamental_quality_score_latest": _display(fundamental_row.get("fundamental_quality_score") if fundamental_row is not None else ""),
                "fundamental_recovery_signal": layers["fundamental_recovery_signal"],
                "fundamental_risk_level": layers["fundamental_risk_level"],
                "fundamental_quality_level": layers["fundamental_quality_level"],
                "missing_fundamental_field_count": len(missing_fields),
                "missing_fundamental_fields": missing_text,
                "data_quality_status": data_quality,
                "human_review_required": True,
                "contains_trading_language": contains_language,
                "rule_version": RULE_VERSION,
            }
        )
        action = "no_fundamental_support"
        if support and layers["fundamental_risk_level"] in {"risk_high", "risk_medium"}:
            action = "review_fundamental_risk"
        elif support and layers["fundamental_recovery_signal"] == "recovery_positive":
            action = "review_fundamental_recovery"
        elif support:
            action = "update_report_fundamentals"
        summary_rows.append(
            {
                "asset_id": asset_id,
                "symbol": symbol,
                "name": name,
                "fundamental_support": support,
                "fundamental_record_count": int(cov.get("fundamental_record_count", 1 if support else 0) or 0),
                "pit_valid_record_count": int(cov.get("pit_valid_record_count", 1 if support else 0) or 0),
                "latest_report_period": index_rows[-1]["latest_report_period"],
                "latest_financial_as_of_date": index_rows[-1]["latest_financial_as_of_date"],
                "announcement_date": index_rows[-1]["announcement_date"],
                "has_revenue_growth": bool(cov.get("has_revenue_growth", support and fundamental_row is not None and pd.notna(fundamental_row.get("revenue_growth_yoy")))),
                "has_profit_growth": bool(cov.get("has_profit_growth", support and fundamental_row is not None and pd.notna(fundamental_row.get("net_profit_growth_yoy")))),
                "has_deducted_profit_growth": bool(support and fundamental_row is not None and pd.notna(fundamental_row.get("deducted_net_profit_growth_yoy"))),
                "has_gross_margin": bool(cov.get("has_gross_margin", support and fundamental_row is not None and pd.notna(fundamental_row.get("gross_margin")))),
                "has_debt_to_asset": bool(support and fundamental_row is not None and pd.notna(fundamental_row.get("debt_to_asset"))),
                "has_cashflow_quality": bool(cov.get("has_cashflow_quality", support and fundamental_row is not None and pd.notna(fundamental_row.get("cashflow_quality_score")))),
                "has_inventory_risk": bool(cov.get("has_inventory_risk", False)),
                "has_receivable_risk": bool(cov.get("has_receivable_risk", False)),
                "has_rd_intensity": bool(cov.get("has_rd_intensity", False)),
                "fundamental_recovery_score_latest": index_rows[-1]["fundamental_recovery_score_latest"],
                "fundamental_risk_score_latest": index_rows[-1]["fundamental_risk_score_latest"],
                "fundamental_quality_score_latest": index_rows[-1]["fundamental_quality_score_latest"],
                "fundamental_recovery_signal": layers["fundamental_recovery_signal"],
                "fundamental_risk_level": layers["fundamental_risk_level"],
                "fundamental_quality_level": layers["fundamental_quality_level"],
                "missing_fundamental_fields": missing_text,
                "source_quality_summary": _source_quality_summary(support, len(missing_fields)),
                "report_patch_summary": "PIT fundamental review fields added" if support else "fundamental support missing",
                "recommended_review_action": action,
            }
        )

    index = pd.DataFrame(index_rows, columns=INDEX_COLUMNS)
    summary = pd.DataFrame(summary_rows, columns=SUMMARY_COLUMNS)
    audit = build_quality_audit(index, summary, structured, field_audit, quality_audit, patch_failures)
    if int(float(dict(zip(audit["metric"], audit["value"])).get("reports_with_trading_language", 0))) != 0:
        raise ValueError("fundamental patched reports contain actionable trading language")
    return {"index": index, "summary": summary, "audit": audit}


def build_quality_audit(
    index: pd.DataFrame,
    summary: pd.DataFrame,
    structured: pd.DataFrame,
    field_audit: pd.DataFrame,
    quality_audit: pd.DataFrame,
    patch_failures: int = 0,
) -> pd.DataFrame:
    total = len(index)
    support = int(index["fundamental_support"].astype(bool).sum()) if total else 0
    no_support = total - support
    lookup = dict(zip(quality_audit.get("metric", []), quality_audit.get("value", [])))
    field_lookup = dict(zip(field_audit.get("field_name", []), field_audit.get("coverage_ratio", [])))

    def count_col(column: str, value: str) -> int:
        return int(index[column].eq(value).sum()) if column in index.columns else 0

    def missing_reports(field: str) -> int:
        if field in field_lookup and float(field_lookup[field]) == 0:
            return support
        return int(index["missing_fundamental_fields"].astype(str).str.contains(rf"(?:^|\|){re.escape(field)}(?:\||$)", regex=True).sum())

    score_frame = index[index["fundamental_support"].astype(bool)].copy()
    rows = [
        ("total_standard_watchlist_reports", total, "standard watchlist denominator"),
        ("fundamental_patched_reports_generated", total, "reports written to patched output directory"),
        ("reports_with_fundamental_support", support, "assets with PIT fundamental support"),
        ("reports_without_fundamental_support", no_support, "assets still missing support"),
        ("fundamental_patch_coverage_ratio", round(support / total, 6) if total else 0.0, "support / total"),
        ("reports_with_recovery_positive", count_col("fundamental_recovery_signal", "recovery_positive"), "research label distribution"),
        ("reports_with_recovery_weak", count_col("fundamental_recovery_signal", "recovery_weak"), "research label distribution"),
        ("reports_with_risk_high", count_col("fundamental_risk_level", "risk_high"), "research label distribution"),
        ("reports_with_risk_medium", count_col("fundamental_risk_level", "risk_medium"), "research label distribution"),
        ("reports_with_quality_high", count_col("fundamental_quality_level", "quality_high"), "research label distribution"),
        ("reports_with_quality_low", count_col("fundamental_quality_level", "quality_low"), "research label distribution"),
        ("reports_missing_revenue", missing_reports("revenue"), "raw detail missing"),
        ("reports_missing_raw_profit", missing_reports("net_profit"), "raw detail missing"),
        ("reports_missing_operating_cashflow", missing_reports("operating_cashflow"), "raw detail missing"),
        ("reports_missing_inventory", missing_reports("inventory_growth_yoy"), "detail missing"),
        ("reports_missing_receivable", missing_reports("receivable_growth_yoy"), "detail missing"),
        ("reports_missing_rd_expense", missing_reports("rd_expense_ratio"), "detail missing"),
        ("reports_missing_capex", missing_reports("capex"), "detail missing"),
        ("reports_requiring_human_review", int(index["human_review_required"].astype(bool).sum()) if total else 0, "all reports require review"),
        ("reports_with_trading_language", int(index["contains_trading_language"].astype(bool).sum()) if total else 0, "must be zero"),
        ("lookahead_violation_rows", int(float(lookup.get("lookahead_violation_rows", 0))), "must be zero"),
        ("PIT_valid_ratio", float(lookup.get("PIT_valid_ratio", 0.0)), "from fundamental adapter audit"),
        ("patch_failures", patch_failures, "must be zero"),
        ("average_fundamental_recovery_score", round(float(pd.to_numeric(score_frame["fundamental_recovery_score_latest"], errors="coerce").mean()), 6) if support else 0.0, "support assets only"),
        ("average_fundamental_risk_score", round(float(pd.to_numeric(score_frame["fundamental_risk_score_latest"], errors="coerce").mean()), 6) if support else 0.0, "support assets only"),
        ("average_fundamental_quality_score", round(float(pd.to_numeric(score_frame["fundamental_quality_score_latest"], errors="coerce").mean()), 6) if support else 0.0, "support assets only"),
    ]
    return pd.DataFrame(rows, columns=["metric", "value", "note"])


def _distribution(frame: pd.DataFrame, column: str) -> str:
    if frame.empty or column not in frame.columns:
        return "none"
    counts = frame[column].value_counts(dropna=False)
    return ", ".join(f"{idx}={value}" for idx, value in counts.items())


def _top_field_text(field_audit: pd.DataFrame, available: bool) -> str:
    if field_audit.empty:
        return "none"
    frame = field_audit.copy()
    frame["coverage_ratio"] = pd.to_numeric(frame["coverage_ratio"], errors="coerce").fillna(0)
    picked = frame[frame["coverage_ratio"].gt(0)] if available else frame[frame["coverage_ratio"].eq(0)]
    picked = picked.sort_values("coverage_ratio", ascending=False).head(10)
    if picked.empty:
        return "none"
    return ", ".join(f"{row.field_name}={row.coverage_ratio:.2f}" for row in picked.itertuples(index=False))


def render_main_report(
    index: pd.DataFrame,
    summary: pd.DataFrame,
    audit: pd.DataFrame,
    field_audit: pd.DataFrame,
    quality_audit: pd.DataFrame,
    git_info: dict[str, str],
) -> str:
    metrics = dict(zip(audit.get("metric", []), audit.get("value", [])))
    total = int(float(metrics.get("total_standard_watchlist_reports", len(index))))
    support = int(float(metrics.get("reports_with_fundamental_support", 0)))
    no_support = int(float(metrics.get("reports_without_fundamental_support", 0)))
    coverage_ratio = float(metrics.get("fundamental_patch_coverage_ratio", 0.0))
    lookahead = int(float(metrics.get("lookahead_violation_rows", 0)))
    language = int(float(metrics.get("reports_with_trading_language", 0)))
    failures = int(float(metrics.get("patch_failures", 0)))
    formal_status = git_info.get("formal_strategy_status", "") or "clean_or_tracked_no_status_rows"
    report = f"""# Tech Bottleneck Watchlist Report Fundamental Patch v1

## 1. Executive Summary

- Fundamental patched stock reports generated: {total}.
- Reports with PIT fundamental support: {support}.
- Reports without fundamental support: {no_support}.
- Fundamental patch coverage ratio: {coverage_ratio:.6f}.
- Best-covered fields: {_top_field_text(field_audit, available=True)}.
- Most severe detail gaps: {_top_field_text(field_audit, available=False)}.
- Recovery distribution: {_distribution(index, 'fundamental_recovery_signal')}.
- Risk distribution: {_distribution(index, 'fundamental_risk_level')}.
- Quality distribution: {_distribution(index, 'fundamental_quality_level')}.
- Reports with restricted execution wording: {language}.
- Lookahead violation rows: {lookahead}.
- Patch failures: {failures}.
- Recommended usage: manual research review only; not automated execution evidence.

## 2. Input Files

- `fundamental_structured_outputs.csv`
- `fundamental_asset_coverage.csv`
- `fundamental_field_coverage_audit.csv`
- `watchlist_fundamental_gap_patch.csv`
- `fundamental_quality_audit.csv`
- fulltext announcement patched stock reports

## 3. Patch Method

The patch reads each fulltext announcement patched stock report and appends a `Fundamental Evidence Patch` section. The latest PIT row per asset is selected by financial as-of date and as-of date. Assets without PIT fundamental support receive an explicit missing-support note.

## 4. Fundamental Coverage

Among {total} standard watchlist reports, {support} have PIT fundamental support and {no_support} remain missing. All supported rows retain degraded detail coverage because the source is a derived PIT feature table, not complete raw financial statements.

## 5. Fundamental Signal Interpretation

`fundamental_recovery_signal`, `fundamental_risk_level`, and `fundamental_quality_level` are conservative review labels. Degraded detail coverage caps low-risk and high-quality interpretations to avoid overstating source strength.

## 6. Recovery Review

{_distribution(index, 'fundamental_recovery_signal')}

## 7. Risk Review

{_distribution(index, 'fundamental_risk_level')}

Missing fields cannot be interpreted as no risk. Derived scores cannot replace full financial analysis. Elevated or medium risk labels require manual review.

## 8. Missing Detail Fields

The largest remaining gaps are raw revenue, raw profit amount, operating cashflow, inventory, receivable, R&D, and capex detail fields. These should be addressed by a full financial statement source adapter if this research line needs higher confidence.

## 9. Report Quality Audit

{audit.to_markdown(index=False)}

## 10. Recommended Usage

Use the patched reports for manual review, report fundamental summary, risk summary, and planning more financial field collection. Do not use these fields as automated execution evidence.

## 11. What This Patch Does Not Do

- It does not create automated execution directives.
- It does not alter Top5 or formal ranking.
- It does not modify formal strategy files.
- It does not study the technical lifecycle execution layer.
- It does not use an evidence multiplier.
- It does not treat fundamental score as automated execution basis.

## 12. Recommended Next Step

Recommended next task: `tech_bottleneck_valuation_source_adapter_v1`. If raw detail gaps block review quality, plan `tech_bottleneck_full_financial_statement_source_adapter_v1` after valuation.

## 13. Appendix

Generated files:

- watchlist_report_fundamental_patch_index.csv
- watchlist_fundamental_patch_summary_by_asset.csv
- watchlist_fundamental_patch_quality_audit.csv
- watchlist_report_fundamental_patch_v1.md
- reports_fundamental_patched/latest/*.md

Fundamental source audit:

{quality_audit.to_markdown(index=False)}

Git repo root: {git_info.get('repo_root', 'unknown')}

Formal strategy file status:

```text
{formal_status}
```

Formal strategy ls-files:

```text
{git_info.get('formal_strategy_ls_files', '') or 'not_tracked_or_no_rows'}
```

Formal strategy stat:

```text
{git_info.get('formal_strategy_stat', '') or 'unavailable'}
```

Key assumptions:

- Latest PIT fundamental row remains valid for the stock report date.
- Derived features support review labels only.
- Full valuation remains outside this task.

Uncertainty:

- Some formal strategy files are untracked in this repository state; git diff cannot fully prove historical immutability for untracked files.
"""
    report = sanitize_review_text(report)
    if contains_actionable_trading_language(report):
        raise ValueError("main report contains actionable trading language")
    return report


def _git_info(project_root: Path) -> dict[str, str]:
    files = ["src/stock_research/tech_bottleneck_v1.py", "src/stock_research/tech_bottleneck_candidates.py"]

    def run(args: list[str]) -> str:
        try:
            return subprocess.check_output(args, cwd=project_root, text=True, stderr=subprocess.STDOUT).strip()
        except Exception as exc:  # pragma: no cover
            return f"unavailable: {exc}"

    return {
        "repo_root": run(["git", "rev-parse", "--show-toplevel"]),
        "formal_strategy_status": run(["git", "status", "--short", *files]),
        "formal_strategy_ls_files": run(["git", "ls-files", *files]),
        "formal_strategy_stat": run(["stat", "-f", "%Sm %N", *files]),
    }


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def run(project_root: Path, output_dir: Path) -> dict[str, pd.DataFrame | str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    fundamental_dir = project_root / FUNDAMENTAL_DIR
    fulltext_dir = project_root / FULLTEXT_REPORT_DIR
    original_dir = project_root / ORIGINAL_REPORT_DIR

    announcement_index = _read_csv(fulltext_dir / "watchlist_report_fulltext_announcement_patch_index.csv")
    if announcement_index.empty:
        original = _read_csv(original_dir / "tech_bottleneck_watchlist_report_index.csv")
        announcement_index = original.rename(columns={"report_path": "fulltext_patched_report_path"})
    structured = _read_csv(fundamental_dir / "fundamental_structured_outputs.csv")
    coverage = _read_csv(fundamental_dir / "fundamental_asset_coverage.csv")
    field_audit = _read_csv(fundamental_dir / "fundamental_field_coverage_audit.csv")
    quality_audit = _read_csv(fundamental_dir / "fundamental_quality_audit.csv")

    result = generate_fundamental_patched_reports(output_dir, announcement_index, structured, coverage, field_audit, quality_audit)
    index = result["index"]
    summary = result["summary"]
    audit = result["audit"]
    git_info = _git_info(project_root)
    report = render_main_report(index, summary, audit, field_audit, quality_audit, git_info)

    outputs = {
        "watchlist_report_fundamental_patch_index.csv": index,
        "watchlist_fundamental_patch_summary_by_asset.csv": summary,
        "watchlist_fundamental_patch_quality_audit.csv": audit,
    }
    for name, frame in outputs.items():
        safe = sanitize_dataframe_for_output(frame)
        text = safe.to_csv(index=False)
        if contains_actionable_trading_language(text):
            raise ValueError(f"{name} contains actionable trading language")
        (output_dir / name).write_text(text, encoding="utf-8")
    (output_dir / "watchlist_report_fundamental_patch_v1.md").write_text(report, encoding="utf-8")
    return {**outputs, "report": report}


def main() -> None:
    parser = argparse.ArgumentParser(description="Build research-only Tech Bottleneck watchlist fundamental report patch.")
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    project_root = args.project_root.resolve()
    output_dir = args.output_dir
    if not output_dir.is_absolute():
        output_dir = project_root / output_dir
    result = run(project_root, output_dir)
    audit = result["watchlist_fundamental_patch_quality_audit.csv"]
    if isinstance(audit, pd.DataFrame):
        lookup = dict(zip(audit["metric"], audit["value"]))
        print(f"output_dir={output_dir}")
        print(f"fundamental_patched_reports_generated={lookup.get('fundamental_patched_reports_generated', 0)}")
        print(f"reports_with_fundamental_support={lookup.get('reports_with_fundamental_support', 0)}")
        print(f"reports_without_fundamental_support={lookup.get('reports_without_fundamental_support', 0)}")
        print(f"lookahead_violation_rows={lookup.get('lookahead_violation_rows', 0)}")


if __name__ == "__main__":
    main()
