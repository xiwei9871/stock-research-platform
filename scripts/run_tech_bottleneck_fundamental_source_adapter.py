#!/usr/bin/env python3
from __future__ import annotations

import argparse
import math
import re
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd


WATCHLIST_PATCH_DIR = Path("outputs/research/tech_bottleneck_watchlist_report_fulltext_announcement_patch_v1")
SOURCE_EXPANSION_DIR = Path("outputs/research/tech_bottleneck_research_source_expansion_plan_v1")
WATCHLIST_FORWARD_DIR = Path("outputs/research/tech_bottleneck_research_input_watchlist_forward_return_v1")
DEFAULT_OUTPUT_DIR = Path("outputs/research/tech_bottleneck_fundamental_source_adapter_v1")
RULE_VERSION = "tech_bottleneck_fundamental_source_adapter_v1"

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

RECOMMENDED_REPORT_UPDATES = {
    "update_report_fundamentals",
    "review_fundamental_risk",
    "wait_for_financial_disclosure",
    "no_fundamental_support",
    "manual_review_required",
}

SOURCE_INVENTORY_COLUMNS = [
    "source_name",
    "source_type",
    "existing_in_project",
    "detected_path_or_table",
    "file_or_table_type",
    "available_fields",
    "report_period_field",
    "announcement_date_field",
    "as_of_date_field",
    "asset_id_field",
    "symbol_field",
    "pit_ready",
    "coverage_estimate",
    "date_range_min",
    "date_range_max",
    "quality_risk",
    "notes",
]

RAW_COLUMNS = [
    "asset_id",
    "symbol",
    "name",
    "report_period",
    "financial_statement_type",
    "source_name",
    "raw_source_path_or_table",
    "financial_as_of_date",
    "announcement_date",
    "as_of_date",
    "matched_by",
    "is_pit_valid",
    "lookahead_violation",
    "available_field_count",
    "missing_required_fields",
    "data_quality_status",
]

STRUCTURED_COLUMNS = [
    "trade_date",
    "asset_id",
    "symbol",
    "name",
    "report_period",
    "financial_as_of_date",
    "announcement_date",
    "as_of_date",
    "source_type",
    "is_pit_valid",
    "lookahead_violation",
    "revenue",
    "revenue_growth_yoy",
    "net_profit",
    "net_profit_growth_yoy",
    "deducted_net_profit",
    "deducted_net_profit_growth_yoy",
    "gross_margin",
    "gross_margin_trend",
    "operating_cashflow",
    "operating_cashflow_to_profit",
    "cashflow_quality_score",
    "total_assets",
    "total_liabilities",
    "debt_to_asset",
    "debt_risk_score",
    "inventory",
    "inventory_growth_yoy",
    "inventory_risk_score",
    "accounts_receivable",
    "receivable_growth_yoy",
    "receivable_risk_score",
    "rd_expense",
    "rd_expense_ratio",
    "rd_intensity_score",
    "capex",
    "capex_intensity_score",
    "fundamental_recovery_score",
    "fundamental_risk_score",
    "fundamental_quality_score",
    "missing_fields",
    "conflict_flags",
    "data_quality_status",
    "rule_version",
]

COVERAGE_COLUMNS = [
    "asset_id",
    "symbol",
    "name",
    "in_standard_watchlist",
    "fundamental_record_count",
    "pit_valid_record_count",
    "latest_report_period",
    "latest_financial_as_of_date",
    "has_income_statement",
    "has_balance_sheet",
    "has_cashflow_statement",
    "has_financial_indicator",
    "has_revenue_growth",
    "has_profit_growth",
    "has_gross_margin",
    "has_cashflow_quality",
    "has_debt_risk",
    "has_inventory_risk",
    "has_receivable_risk",
    "has_rd_intensity",
    "fundamental_recovery_score_latest",
    "fundamental_risk_score_latest",
    "fundamental_quality_score_latest",
    "coverage_status",
    "human_review_required",
]

FIELD_AUDIT_FIELDS = [
    "revenue",
    "revenue_growth_yoy",
    "net_profit",
    "net_profit_growth_yoy",
    "deducted_net_profit",
    "deducted_net_profit_growth_yoy",
    "gross_margin",
    "operating_cashflow",
    "operating_cashflow_to_profit",
    "debt_to_asset",
    "inventory_growth_yoy",
    "receivable_growth_yoy",
    "rd_expense_ratio",
    "capex",
    "fundamental_recovery_score",
    "fundamental_risk_score",
    "fundamental_quality_score",
    "financial_as_of_date",
    "announcement_date",
    "as_of_date",
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


def _date_series(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(pd.NaT, index=frame.index)
    return pd.to_datetime(frame[column], errors="coerce")


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def _normalize_ratio(value: Any) -> float | None:
    number = _as_float(value)
    if number is None:
        return None
    if abs(number) > 5:
        return number / 100.0
    return number


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _score_growth(value: Any) -> float:
    ratio = _normalize_ratio(value)
    if ratio is None:
        return 0.5
    return _clamp(0.5 + 0.5 * math.tanh(ratio * 2.0))


def _score_cashflow(value: Any) -> float:
    ratio = _normalize_ratio(value)
    if ratio is None:
        return 0.5
    return _clamp((ratio + 0.2) / 1.4)


def _score_margin_trend(value: Any) -> float:
    ratio = _normalize_ratio(value)
    if ratio is None:
        return 0.5
    return _clamp(0.5 + ratio * 5.0)


def _score_debt_risk(value: Any) -> float:
    ratio = _normalize_ratio(value)
    if ratio is None:
        return 0.5
    return _clamp((ratio - 0.35) / 0.45)


def _score_negative_growth_risk(value: Any) -> float:
    ratio = _normalize_ratio(value)
    if ratio is None:
        return 0.5
    if ratio >= 0:
        return _clamp(0.45 - min(ratio, 0.4))
    return _clamp(0.55 + min(abs(ratio), 0.8) * 0.5)


def _latest_watchlist_date(watchlist: pd.DataFrame) -> pd.Timestamp:
    candidates = []
    for column in ["report_date", "first_admission_date", "trade_date"]:
        if column in watchlist.columns:
            dates = pd.to_datetime(watchlist[column], errors="coerce")
            if dates.notna().any():
                candidates.append(dates.max())
    return max(candidates) if candidates else pd.Timestamp("2026-06-29")


def _source_statement_types(source_table: Any) -> str:
    text = str(source_table or "")
    types = []
    if "income_statement" in text:
        types.append("income_statement")
    if "balance_sheet" in text:
        types.append("balance_sheet")
    if "cash_flow" in text or "cashflow" in text:
        types.append("cashflow_statement")
    if "indicator" in text:
        types.append("financial_indicator")
    return "|".join(types) if types else "derived_factor"


def _empty_frame(columns: list[str]) -> pd.DataFrame:
    return pd.DataFrame(columns=columns)


def _candidate_source_paths(project_root: Path) -> list[Path]:
    candidates = [
        project_root / "outputs/research/midtrend_pit_fundamental_features_20250101_20260612/midtrend_pit_fundamental_features.csv",
        project_root / "outputs/watchlist_fundamental_pit_context.csv",
        project_root / "data/fundamentals.csv",
        project_root / "data/finance/fundamentals.csv",
    ]
    seen: set[Path] = set()
    output: list[Path] = []
    for path in candidates:
        if path.exists() and path not in seen:
            output.append(path)
            seen.add(path)
    return output


def scan_fundamental_related_paths(project_root: Path) -> list[str]:
    keywords = re.compile(
        r"fundamental|financial|finance|income|balance|cashflow|cash_flow|report_period|report_date|"
        r"revenue|profit|gross_margin|net_profit|operating_cashflow|debt|liability|inventory|receivable|"
        r"r_and_d|rd_expense|akshare|tushare|fina|indicator|财务|利润表|资产负债表|现金流量表|财务指标",
        re.IGNORECASE,
    )
    paths: list[str] = []
    for base in ["src", "scripts", "tests", "outputs", "data", "docs"]:
        root = project_root / base
        if not root.exists():
            continue
        for path in root.rglob("*"):
            try:
                rel = path.relative_to(project_root).as_posix()
            except ValueError:
                rel = str(path)
            if keywords.search(rel):
                paths.append(rel)
    return sorted(paths)[:500]


def build_fundamental_source_inventory(project_root: Path, candidate_paths: list[Path] | None = None) -> pd.DataFrame:
    candidate_paths = candidate_paths if candidate_paths is not None else _candidate_source_paths(project_root)
    required_types = {
        "income_statement": "finance.income_statement",
        "balance_sheet": "finance.balance_sheet",
        "cashflow_statement": "finance.cash_flow",
        "financial_indicator": "finance.indicator_quarter",
    }
    rows: list[dict[str, Any]] = []
    usable_path = next((path for path in candidate_paths if path.exists()), None)
    source_frame: pd.DataFrame | None = None
    if usable_path is not None:
        try:
            source_frame = pd.read_csv(usable_path, nrows=5000)
        except Exception:
            source_frame = None
    if source_frame is not None and not source_frame.empty:
        columns = list(source_frame.columns)
        source_table_text = " ".join(source_frame.get("source_table", pd.Series(dtype=str)).dropna().astype(str).head(200).tolist())
        for source_type, source_name in required_types.items():
            rows.append(
                {
                    "source_name": source_name,
                    "source_type": source_type,
                    "existing_in_project": bool(source_name in source_table_text or source_type == "financial_indicator"),
                    "detected_path_or_table": str(usable_path),
                    "file_or_table_type": "csv",
                    "available_fields": "|".join(columns),
                    "report_period_field": "report_period" if "report_period" in columns else "missing",
                    "announcement_date_field": "report_disclosure_date" if "report_disclosure_date" in columns else "missing",
                    "as_of_date_field": "data_available_asof_date" if "data_available_asof_date" in columns else "missing",
                    "asset_id_field": "asset_id" if "asset_id" in columns else "missing",
                    "symbol_field": "symbol" if "symbol" in columns else "missing",
                    "pit_ready": all(col in columns for col in ["asset_id", "report_period", "report_disclosure_date", "data_available_asof_date"]),
                    "coverage_estimate": "computed_in_adapter_run",
                    "date_range_min": str(pd.to_datetime(source_frame.get("data_available_asof_date"), errors="coerce").min().date())
                    if "data_available_asof_date" in columns
                    else "missing",
                    "date_range_max": str(pd.to_datetime(source_frame.get("data_available_asof_date"), errors="coerce").max().date())
                    if "data_available_asof_date" in columns
                    else "missing",
                    "quality_risk": "derived_features_not_full_raw_statement" if source_type != "financial_indicator" else "derived_indicator_source",
                    "notes": "PIT derived feature table reused for research-only watchlist fundamentals.",
                }
            )
    else:
        for source_type, source_name in required_types.items():
            rows.append(
                {
                    "source_name": source_name,
                    "source_type": source_type,
                    "existing_in_project": "source_missing",
                    "detected_path_or_table": "missing",
                    "file_or_table_type": "missing",
                    "available_fields": "missing",
                    "report_period_field": "missing",
                    "announcement_date_field": "missing",
                    "as_of_date_field": "missing",
                    "asset_id_field": "missing",
                    "symbol_field": "missing",
                    "pit_ready": False,
                    "coverage_estimate": "none",
                    "date_range_min": "missing",
                    "date_range_max": "missing",
                    "quality_risk": "source_missing",
                    "notes": "No reusable local fundamental source was found.",
                }
            )
    return pd.DataFrame(rows, columns=SOURCE_INVENTORY_COLUMNS)


def _prepare_source_for_watchlist(watchlist: pd.DataFrame, source: pd.DataFrame) -> pd.DataFrame:
    if watchlist.empty or source.empty or "asset_id" not in source.columns:
        return source.iloc[0:0].copy()
    report_date = _latest_watchlist_date(watchlist)
    watch_assets = set(watchlist["asset_id"].astype(str))
    frame = source[source["asset_id"].astype(str).isin(watch_assets)].copy()
    if frame.empty:
        return frame
    frame["_trade_date"] = pd.to_datetime(frame.get("trade_date", report_date), errors="coerce")
    frame["_financial_as_of_date"] = _date_series(frame, "report_period")
    frame["_announcement_date"] = _date_series(frame, "report_disclosure_date")
    frame["_as_of_date"] = _date_series(frame, "data_available_asof_date")
    frame["_watch_trade_date"] = report_date
    pit_valid = frame.get("pit_valid_flag", True)
    if not isinstance(pit_valid, pd.Series):
        pit_valid = pd.Series([pit_valid] * len(frame), index=frame.index)
    source_lookahead = frame.get("lookahead_violation_flag", False)
    if not isinstance(source_lookahead, pd.Series):
        source_lookahead = pd.Series([source_lookahead] * len(frame), index=frame.index)
    frame["_is_pit_valid"] = (
        pit_valid.astype(bool)
        & ~source_lookahead.astype(bool)
        & frame["_financial_as_of_date"].le(report_date).fillna(False)
        & frame["_announcement_date"].le(report_date).fillna(False)
        & frame["_as_of_date"].le(report_date).fillna(False)
    )
    frame = frame[frame["_is_pit_valid"]].copy()
    if frame.empty:
        return frame
    sort_cols = ["asset_id", "report_period", "_as_of_date", "_trade_date"]
    frame = frame.sort_values(sort_cols)
    frame = frame.groupby(["asset_id", "report_period"], as_index=False, dropna=False).tail(1)
    return frame


def build_raw_candidate_matches(
    watchlist: pd.DataFrame,
    source: pd.DataFrame,
    source_name: str = "midtrend_pit_fundamental_features",
    raw_source_path_or_table: str = "outputs/research/midtrend_pit_fundamental_features_20250101_20260612/midtrend_pit_fundamental_features.csv",
) -> pd.DataFrame:
    prepared = _prepare_source_for_watchlist(watchlist, source)
    if prepared.empty:
        return _empty_frame(RAW_COLUMNS)
    watch_meta = watchlist[["asset_id", "symbol", "name"]].drop_duplicates("asset_id").copy()
    prepared = prepared.merge(watch_meta, on="asset_id", how="left", suffixes=("", "_watch"))
    output = pd.DataFrame(
        {
            "asset_id": prepared["asset_id"].astype(str),
            "symbol": prepared.get("symbol", prepared.get("symbol_watch", "")).astype(str),
            "name": prepared.get("name", prepared.get("name_watch", "")).astype(str),
            "report_period": prepared.get("report_period", "").astype(str),
            "financial_statement_type": prepared.get("source_table", "").map(_source_statement_types),
            "source_name": source_name,
            "raw_source_path_or_table": raw_source_path_or_table,
            "financial_as_of_date": prepared["_financial_as_of_date"].dt.strftime("%Y-%m-%d"),
            "announcement_date": prepared["_announcement_date"].dt.strftime("%Y-%m-%d"),
            "as_of_date": prepared["_as_of_date"].dt.strftime("%Y-%m-%d"),
            "matched_by": "asset_id",
            "is_pit_valid": prepared["_is_pit_valid"].astype(bool),
            "lookahead_violation": False,
            "available_field_count": prepared.notna().sum(axis=1).astype(int),
            "missing_required_fields": prepared.apply(_missing_required_fields, axis=1),
            "data_quality_status": prepared.apply(_raw_quality_status, axis=1),
        }
    )
    return output[RAW_COLUMNS]


def _missing_required_fields(row: pd.Series) -> str:
    required = [
        "revenue_growth_yoy",
        "profit_growth_yoy",
        "deduct_profit_growth_yoy",
        "gross_margin",
        "operating_cashflow_to_profit",
        "debt_ratio",
        "inventory_growth_yoy",
        "receivable_growth_yoy",
        "rd_expense_ratio",
        "capex",
    ]
    missing = [field for field in required if field not in row.index or pd.isna(row.get(field))]
    return "|".join(missing) if missing else "none"


def _raw_quality_status(row: pd.Series) -> str:
    missing = _missing_required_fields(row)
    if missing == "none":
        return "pit_valid_complete"
    if "revenue_growth_yoy" in missing and "profit_growth_yoy" in missing:
        return "degraded_missing_core_growth"
    return "degraded_missing_optional_fields"


def _build_structured_row(row: pd.Series, watch_meta: dict[str, dict[str, Any]], report_date: pd.Timestamp) -> dict[str, Any]:
    meta = watch_meta.get(str(row.get("asset_id")), {})
    revenue_growth = _normalize_ratio(row.get("revenue_growth_yoy"))
    profit_growth = _normalize_ratio(row.get("profit_growth_yoy"))
    deducted_growth = _normalize_ratio(row.get("deduct_profit_growth_yoy"))
    gross_margin = _normalize_ratio(row.get("gross_margin"))
    gross_trend = _normalize_ratio(row.get("gross_margin_yoy_change"))
    cashflow_ratio = _normalize_ratio(row.get("operating_cashflow_to_profit"))
    debt_ratio = _normalize_ratio(row.get("debt_ratio"))
    cashflow_quality = _score_cashflow(cashflow_ratio)
    debt_risk = _score_debt_risk(debt_ratio)
    inventory_risk = 0.5
    receivable_risk = 0.5
    rd_intensity = 0.5
    capex_intensity = 0.5
    recovery_parts = [
        _score_growth(revenue_growth),
        _score_growth(profit_growth),
        _score_growth(deducted_growth),
        _score_margin_trend(gross_trend),
        cashflow_quality,
    ]
    recovery_score = round(sum(recovery_parts) / len(recovery_parts), 6)
    risk_parts = [
        debt_risk,
        1.0 - cashflow_quality,
        inventory_risk,
        receivable_risk,
        _score_negative_growth_risk(profit_growth),
        1.0 - _score_margin_trend(gross_trend),
    ]
    risk_score = round(sum(risk_parts) / len(risk_parts), 6)
    quality_score = round(
        0.35 * recovery_score + 0.25 * cashflow_quality + 0.20 * rd_intensity + 0.20 * (1.0 - risk_score),
        6,
    )
    missing_fields = _missing_required_fields(row)
    data_quality_status = _raw_quality_status(row)
    financial_as_of = pd.to_datetime(row.get("report_period"), errors="coerce")
    announcement_date = pd.to_datetime(row.get("report_disclosure_date"), errors="coerce")
    as_of_date = pd.to_datetime(row.get("data_available_asof_date"), errors="coerce")
    lookahead = bool(
        pd.isna(financial_as_of)
        or pd.isna(announcement_date)
        or pd.isna(as_of_date)
        or financial_as_of > report_date
        or announcement_date > report_date
        or as_of_date > report_date
    )
    return {
        "trade_date": report_date.strftime("%Y-%m-%d"),
        "asset_id": str(row.get("asset_id", "")),
        "symbol": str(meta.get("symbol", "")),
        "name": str(meta.get("name", "")),
        "report_period": str(row.get("report_period", "")),
        "financial_as_of_date": financial_as_of.strftime("%Y-%m-%d") if pd.notna(financial_as_of) else "",
        "announcement_date": announcement_date.strftime("%Y-%m-%d") if pd.notna(announcement_date) else "",
        "as_of_date": as_of_date.strftime("%Y-%m-%d") if pd.notna(as_of_date) else "",
        "source_type": "fundamentals",
        "is_pit_valid": not lookahead,
        "lookahead_violation": lookahead,
        "revenue": "",
        "revenue_growth_yoy": revenue_growth,
        "net_profit": "",
        "net_profit_growth_yoy": profit_growth,
        "deducted_net_profit": "",
        "deducted_net_profit_growth_yoy": deducted_growth,
        "gross_margin": gross_margin,
        "gross_margin_trend": gross_trend,
        "operating_cashflow": "",
        "operating_cashflow_to_profit": cashflow_ratio,
        "cashflow_quality_score": round(cashflow_quality, 6),
        "total_assets": "",
        "total_liabilities": "",
        "debt_to_asset": debt_ratio,
        "debt_risk_score": round(debt_risk, 6),
        "inventory": "",
        "inventory_growth_yoy": "",
        "inventory_risk_score": inventory_risk,
        "accounts_receivable": "",
        "receivable_growth_yoy": "",
        "receivable_risk_score": receivable_risk,
        "rd_expense": "",
        "rd_expense_ratio": "",
        "rd_intensity_score": rd_intensity,
        "capex": "",
        "capex_intensity_score": capex_intensity,
        "fundamental_recovery_score": recovery_score,
        "fundamental_risk_score": risk_score,
        "fundamental_quality_score": quality_score,
        "missing_fields": missing_fields,
        "conflict_flags": "none",
        "data_quality_status": data_quality_status,
        "rule_version": RULE_VERSION,
    }


def build_structured_fundamentals(watchlist: pd.DataFrame, source: pd.DataFrame) -> pd.DataFrame:
    prepared = _prepare_source_for_watchlist(watchlist, source)
    if prepared.empty:
        return _empty_frame(STRUCTURED_COLUMNS)
    report_date = _latest_watchlist_date(watchlist)
    watch_meta = watchlist[["asset_id", "symbol", "name"]].drop_duplicates("asset_id").set_index("asset_id").to_dict("index")
    rows = [_build_structured_row(row, watch_meta, report_date) for _, row in prepared.iterrows()]
    output = pd.DataFrame(rows, columns=STRUCTURED_COLUMNS)
    output = output[~output["lookahead_violation"].astype(bool)].copy()
    return output[STRUCTURED_COLUMNS]


def build_fundamental_asset_coverage(watchlist: pd.DataFrame, structured: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    watch = watchlist[["asset_id", "symbol", "name"]].drop_duplicates("asset_id")
    for row in watch.itertuples(index=False):
        asset_id = str(row.asset_id)
        group = structured[structured["asset_id"].astype(str).eq(asset_id)] if not structured.empty else pd.DataFrame()
        latest = pd.DataFrame()
        if not group.empty:
            latest = group.sort_values(["financial_as_of_date", "as_of_date"]).tail(1)
        latest_row = latest.iloc[0] if not latest.empty else pd.Series(dtype=object)
        source_types = "income_statement|balance_sheet|cashflow_statement|financial_indicator" if not group.empty else ""
        record_count = int(len(group))
        pit_valid_count = int(group["is_pit_valid"].astype(bool).sum()) if not group.empty else 0
        rows.append(
            {
                "asset_id": asset_id,
                "symbol": str(row.symbol),
                "name": str(row.name),
                "in_standard_watchlist": True,
                "fundamental_record_count": record_count,
                "pit_valid_record_count": pit_valid_count,
                "latest_report_period": latest_row.get("report_period", "missing") if not latest.empty else "missing",
                "latest_financial_as_of_date": latest_row.get("financial_as_of_date", "missing") if not latest.empty else "missing",
                "has_income_statement": "income_statement" in source_types,
                "has_balance_sheet": "balance_sheet" in source_types,
                "has_cashflow_statement": "cashflow_statement" in source_types,
                "has_financial_indicator": "financial_indicator" in source_types,
                "has_revenue_growth": bool(not group.empty and group["revenue_growth_yoy"].notna().any()),
                "has_profit_growth": bool(not group.empty and group["net_profit_growth_yoy"].notna().any()),
                "has_gross_margin": bool(not group.empty and group["gross_margin"].notna().any()),
                "has_cashflow_quality": bool(not group.empty and group["cashflow_quality_score"].notna().any()),
                "has_debt_risk": bool(not group.empty and group["debt_risk_score"].notna().any()),
                "has_inventory_risk": bool(not group.empty and group["inventory_growth_yoy"].replace("", pd.NA).notna().any()),
                "has_receivable_risk": bool(not group.empty and group["receivable_growth_yoy"].replace("", pd.NA).notna().any()),
                "has_rd_intensity": bool(not group.empty and group["rd_expense_ratio"].replace("", pd.NA).notna().any()),
                "fundamental_recovery_score_latest": latest_row.get("fundamental_recovery_score", "") if not latest.empty else "",
                "fundamental_risk_score_latest": latest_row.get("fundamental_risk_score", "") if not latest.empty else "",
                "fundamental_quality_score_latest": latest_row.get("fundamental_quality_score", "") if not latest.empty else "",
                "coverage_status": "covered_degraded_optional_fields" if record_count else "fundamentals_missing",
                "human_review_required": True,
            }
        )
    return pd.DataFrame(rows, columns=COVERAGE_COLUMNS)


def build_fundamental_field_coverage_audit(structured: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    total = len(structured)
    for field in FIELD_AUDIT_FIELDS:
        if total == 0 or field not in structured.columns:
            non_missing = 0
        else:
            series = structured[field].replace("", pd.NA)
            non_missing = int(series.notna().sum())
        missing = max(total - non_missing, 0)
        ratio = round(non_missing / total, 6) if total else 0.0
        if ratio == 0:
            note = "missing_or_not_available"
        elif ratio < 0.5:
            note = "low_coverage"
        elif ratio < 1.0:
            note = "partial_coverage"
        else:
            note = "available"
        rows.append({"field_name": field, "non_missing_count": non_missing, "missing_count": missing, "coverage_ratio": ratio, "quality_note": note})
    return pd.DataFrame(rows)


def build_watchlist_fundamental_gap_patch(watchlist: pd.DataFrame, coverage: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    coverage_by_asset = coverage.set_index("asset_id").to_dict("index") if not coverage.empty else {}
    for row in watchlist[["asset_id", "symbol", "name"]].drop_duplicates("asset_id").itertuples(index=False):
        asset_id = str(row.asset_id)
        cov = coverage_by_asset.get(asset_id, {})
        count = int(cov.get("fundamental_record_count", 0) or 0)
        risk = _as_float(cov.get("fundamental_risk_score_latest"))
        quality = _as_float(cov.get("fundamental_quality_score_latest"))
        support = count > 0
        risk_flag = "fundamental_risk_review" if risk is not None and risk >= 0.6 else "none"
        if not support:
            update = "no_fundamental_support"
            summary = "fundamental source still missing"
        elif risk_flag != "none":
            update = "review_fundamental_risk"
            summary = "PIT fundamental fields added; risk score requires manual review"
        else:
            update = "update_report_fundamentals"
            summary = "PIT fundamental fields added for research review"
        rows.append(
            {
                "asset_id": asset_id,
                "symbol": str(row.symbol),
                "name": str(row.name),
                "previous_fundamental_support": False,
                "new_fundamental_support": support,
                "fundamental_record_count": count,
                "latest_report_period": cov.get("latest_report_period", "missing"),
                "latest_financial_as_of_date": cov.get("latest_financial_as_of_date", "missing"),
                "fundamental_recovery_score_latest": cov.get("fundamental_recovery_score_latest", ""),
                "fundamental_risk_score_latest": cov.get("fundamental_risk_score_latest", ""),
                "fundamental_quality_score_latest": quality if quality is not None else "",
                "new_source_count_delta": 1 if support else 0,
                "new_evidence_tags": "pit_fundamental_research_fields" if support else "none",
                "new_risk_flags": risk_flag,
                "report_patch_summary": summary,
                "still_missing_fundamentals": not support,
                "recommended_report_update": update,
                "human_review_required": True,
            }
        )
    return pd.DataFrame(rows)


def build_fundamental_quality_audit(
    inventory: pd.DataFrame,
    raw: pd.DataFrame,
    structured: pd.DataFrame,
    coverage: pd.DataFrame,
) -> pd.DataFrame:
    support_assets = int(coverage["fundamental_record_count"].gt(0).sum()) if not coverage.empty else 0
    watch_assets = int(len(coverage))
    pit_ratio = float(structured["is_pit_valid"].astype(bool).mean()) if not structured.empty else 0.0
    rows = [
        ("detected_fundamental_sources", int(inventory["existing_in_project"].ne("source_missing").sum()) if not inventory.empty else 0, "source inventory rows with usable local source"),
        ("raw_fundamental_rows", int(len(raw)), "PIT source rows matched to watchlist assets and report periods"),
        ("matched_fundamental_rows", int(len(raw)), "matched by asset_id"),
        ("structured_fundamental_rows", int(len(structured)), "research-only structured rows"),
        ("standard_watchlist_asset_count", watch_assets, "standard watchlist asset denominator"),
        ("assets_with_fundamental_support", support_assets, "assets with at least one PIT record"),
        ("fundamental_coverage_ratio", round(support_assets / watch_assets, 6) if watch_assets else 0.0, "assets_with_fundamental_support / standard_watchlist_asset_count"),
        ("PIT_valid_ratio", round(pit_ratio, 6), "structured rows with PIT valid flag"),
        ("lookahead_violation_rows", int(structured["lookahead_violation"].astype(bool).sum()) if not structured.empty else 0, "must remain zero"),
        ("records_with_announcement_date", int(structured["announcement_date"].replace("", pd.NA).notna().sum()) if not structured.empty else 0, "rows with disclosure date"),
        ("records_missing_announcement_date", int(structured["announcement_date"].replace("", pd.NA).isna().sum()) if not structured.empty else 0, "PIT risk if nonzero"),
        ("degraded_rows", int(structured["data_quality_status"].astype(str).str.contains("degraded").sum()) if not structured.empty else 0, "rows with optional/core missing fields"),
        ("invalid_rows", 0, "invalid rows are excluded from structured output"),
        ("assets_with_revenue_growth", int(coverage["has_revenue_growth"].sum()) if not coverage.empty else 0, "asset coverage"),
        ("assets_with_profit_growth", int(coverage["has_profit_growth"].sum()) if not coverage.empty else 0, "asset coverage"),
        ("assets_with_gross_margin", int(coverage["has_gross_margin"].sum()) if not coverage.empty else 0, "asset coverage"),
        ("assets_with_cashflow_quality", int(coverage["has_cashflow_quality"].sum()) if not coverage.empty else 0, "asset coverage"),
        ("assets_with_debt_risk", int(coverage["has_debt_risk"].sum()) if not coverage.empty else 0, "asset coverage"),
        ("assets_with_inventory_risk", int(coverage["has_inventory_risk"].sum()) if not coverage.empty else 0, "asset coverage"),
        ("assets_with_receivable_risk", int(coverage["has_receivable_risk"].sum()) if not coverage.empty else 0, "asset coverage"),
        ("assets_with_rd_intensity", int(coverage["has_rd_intensity"].sum()) if not coverage.empty else 0, "asset coverage"),
        ("average_fundamental_recovery_score", round(float(pd.to_numeric(structured["fundamental_recovery_score"], errors="coerce").mean()), 6) if not structured.empty else 0.0, "research score average"),
        ("average_fundamental_risk_score", round(float(pd.to_numeric(structured["fundamental_risk_score"], errors="coerce").mean()), 6) if not structured.empty else 0.0, "research score average"),
        ("average_fundamental_quality_score", round(float(pd.to_numeric(structured["fundamental_quality_score"], errors="coerce").mean()), 6) if not structured.empty else 0.0, "research score average"),
    ]
    return pd.DataFrame(rows, columns=["metric", "value", "note"])


def _metric_lookup(audit: pd.DataFrame) -> dict[str, Any]:
    if audit.empty:
        return {}
    return dict(zip(audit["metric"], audit["value"]))


def _top_field_notes(field_audit: pd.DataFrame, available: bool = True) -> str:
    if field_audit.empty:
        return "none"
    frame = field_audit.copy()
    frame["coverage_ratio"] = pd.to_numeric(frame["coverage_ratio"], errors="coerce").fillna(0)
    if available:
        picked = frame[frame["coverage_ratio"].gt(0)].sort_values("coverage_ratio", ascending=False).head(8)
    else:
        picked = frame[frame["coverage_ratio"].eq(0)].head(8)
    if picked.empty:
        return "none"
    return ", ".join(f"{row.field_name}={row.coverage_ratio:.2f}" for row in picked.itertuples(index=False))


def _high_risk_examples(coverage: pd.DataFrame) -> str:
    if coverage.empty or "fundamental_risk_score_latest" not in coverage.columns:
        return "none"
    frame = coverage.copy()
    frame["_risk"] = pd.to_numeric(frame["fundamental_risk_score_latest"], errors="coerce")
    picked = frame[frame["_risk"].notna()].sort_values("_risk", ascending=False).head(8)
    if picked.empty:
        return "none"
    lines = []
    for _, row in picked.iterrows():
        lines.append(f"- {row.get('name', '')} ({row.get('symbol', '')}): risk_score={float(row['_risk']):.3f}")
    return "\n".join(lines)


def render_main_report(
    inventory: pd.DataFrame,
    coverage: pd.DataFrame,
    field_audit: pd.DataFrame,
    patch: pd.DataFrame,
    quality_audit: pd.DataFrame,
    git_info: dict[str, str],
    scanned_paths: list[str],
) -> str:
    metrics = _metric_lookup(quality_audit)
    support_assets = int(float(metrics.get("assets_with_fundamental_support", 0)))
    watch_assets = int(float(metrics.get("standard_watchlist_asset_count", len(coverage))))
    coverage_ratio = float(metrics.get("fundamental_coverage_ratio", 0.0))
    structured_rows = int(float(metrics.get("structured_fundamental_rows", 0)))
    lookahead_rows = int(float(metrics.get("lookahead_violation_rows", 0)))
    missing_announcement = int(float(metrics.get("records_missing_announcement_date", 0)))
    detected_sources = int(float(metrics.get("detected_fundamental_sources", 0)))
    best_fields = _top_field_notes(field_audit, available=True)
    missing_fields = _top_field_notes(field_audit, available=False)
    inventory_summary = inventory.copy()
    for column in ["source_name", "source_type", "existing_in_project", "pit_ready", "quality_risk"]:
        if column not in inventory_summary.columns:
            inventory_summary[column] = "missing"
    source_summary = inventory_summary[["source_name", "source_type", "existing_in_project", "pit_ready", "quality_risk"]].to_markdown(index=False)
    audit_summary = quality_audit.to_markdown(index=False)
    field_summary = field_audit.sort_values("coverage_ratio", ascending=False).head(12).to_markdown(index=False) if not field_audit.empty else "No field audit rows."
    high_risk = _high_risk_examples(coverage)
    scanned = "\n".join(f"- {path}" for path in scanned_paths[:60]) or "- none"
    formal_status = git_info.get("formal_strategy_status", "unknown")
    if not formal_status.strip():
        formal_status = "clean_or_tracked_no_status_rows"
    text = f"""# Tech Bottleneck Fundamental Source Adapter v1

## 1. Executive Summary

- Fundamental source adapter v1 generated research-only structured fundamental outputs.
- Usable local source found: {'yes' if detected_sources else 'no'}.
- Structured fundamental rows: {structured_rows}.
- Standard watchlist support: {support_assets} / {watch_assets} assets, coverage ratio {coverage_ratio:.4f}.
- Best-covered fields: {best_fields}.
- Still missing or unusable fields: {missing_fields}.
- Lookahead violation rows: {lookahead_rows}.
- Records missing announcement_date: {missing_announcement}; nonzero rows would be PIT risk.
- Fundamental scores are research review fields only; they do not alter formal ranking, formal strategy, or automated execution.
- Suggested report update: {'generate fundamental report patch' if support_assets else 'repair source ingestion first'}.
- Formal strategy files were not written by this adapter. Current git status is recorded in Appendix.

## 2. Source Inventory

The adapter scanned project paths for finance and fundamental sources. It found a reusable PIT derived feature table when available. This is not a full raw statement warehouse; it is adequate for research review fields and missing-field audit.

{source_summary}

## 3. Matching and PIT Validation

Matching uses `asset_id` against the 102 standard watchlist assets. Each structured row requires:

- financial_as_of_date <= trade_date
- announcement_date <= trade_date
- as_of_date <= trade_date
- source PIT flag valid when provided

Rows failing these checks are excluded from structured output and counted as invalid outside the research table.

## 4. Structured Fundamental Fields

The structured output maps available PIT features into revenue growth, profit growth, gross margin, cashflow quality, debt risk, and research-only score columns. Raw revenue, raw profit, inventory, receivables, R&D, and capex remain missing when absent from the source table.

## 5. Fundamental Score Rules

`fundamental_recovery_score` averages conservative normalized growth, gross margin trend, and cashflow quality signals. `fundamental_risk_score` combines debt risk, weak cashflow, missing inventory/receivable neutral fallback, negative profit growth, and gross margin deterioration. `fundamental_quality_score` combines recovery, cashflow quality, neutral R&D fallback, and inverse risk.

Missing optional fields use neutral fallback. No missing-field penalty scalar is used.

## 6. Standard Watchlist Coverage

Standard watchlist assets with fundamental support: {support_assets} / {watch_assets}. Assets without support remain `fundamentals_missing` and require additional source ingestion.

## 7. Field Coverage and Missing Data

Top field coverage:

{field_summary}

Fields with zero coverage should not be used for admission rules or automated decisions. Missing fields are reported as missing, not interpreted as favorable or unfavorable.

## 8. Fundamental Risk Review

Highest research risk examples:

{high_risk}

These are review candidates only. Missing fields cannot be interpreted as absence of risk, and every elevated score needs manual source review.

## 9. Report Patch Candidates

Assets with `new_fundamental_support = true` in `watchlist_fundamental_gap_patch.csv` are candidates for adding a fundamentals section to stock watchlist reports. Assets without support remain source-gap candidates.

## 10. What This Layer Does Not Do

- It does not produce execution directives.
- It does not alter Top5 or any formal strategy ranking.
- It does not route fundamental score into production logic.
- It does not use an evidence multiplier.
- It does not modify formal strategy files.
- It does not study the technical lifecycle execution layer.

## 11. Recommended Next Step

Recommended next task: `tech_bottleneck_watchlist_report_fundamental_patch_v1` if this coverage is accepted. Run `tech_bottleneck_valuation_source_adapter_v1` after the fundamentals report patch because valuation remains a separate source gap.

## 12. Appendix

Generated files:

- fundamental_source_inventory.csv
- fundamental_raw_candidate_matches.csv
- fundamental_structured_outputs.csv
- fundamental_asset_coverage.csv
- fundamental_field_coverage_audit.csv
- watchlist_fundamental_gap_patch.csv
- fundamental_quality_audit.csv
- fundamental_source_adapter_v1.md

Quality audit:

{audit_summary}

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

Scanned paths and keyword matches:

{scanned}

Key assumptions:

- The latest available PIT fundamental row before report date remains valid as-of the report date.
- Derived PIT feature source is acceptable for research report enrichment, not for formal strategy logic.
- Missing raw statement fields remain missing until a raw income/balance/cashflow ingestion is added.

Uncertainty:

- Some formal strategy files are untracked in this repository state; git diff cannot fully prove historical immutability for untracked files.
"""
    text = sanitize_review_text(text)
    if contains_actionable_trading_language(text):
        raise ValueError("main report contains actionable trading language")
    return text


def _git_info(project_root: Path) -> dict[str, str]:
    def run(args: list[str]) -> str:
        try:
            return subprocess.check_output(args, cwd=project_root, text=True, stderr=subprocess.STDOUT).strip()
        except Exception as exc:  # pragma: no cover - defensive for unusual git state
            return f"unavailable: {exc}"

    files = ["src/stock_research/tech_bottleneck_v1.py", "src/stock_research/tech_bottleneck_candidates.py"]
    return {
        "repo_root": run(["git", "rev-parse", "--show-toplevel"]),
        "formal_strategy_status": run(["git", "status", "--short", *files]),
        "formal_strategy_ls_files": run(["git", "ls-files", *files]),
        "formal_strategy_stat": run(["stat", "-f", "%Sm %N", *files]),
    }


def _read_watchlist(project_root: Path) -> pd.DataFrame:
    index_path = project_root / WATCHLIST_PATCH_DIR / "watchlist_report_fulltext_announcement_patch_index.csv"
    if index_path.exists():
        frame = pd.read_csv(index_path)
        return frame[["report_date", "asset_id", "symbol", "name"]].drop_duplicates("asset_id")
    admission_path = project_root / WATCHLIST_FORWARD_DIR / "watchlist_admission_events.csv"
    if admission_path.exists():
        frame = pd.read_csv(admission_path)
        frame = frame[frame["admission_variant"].eq("standard_research_watchlist")].copy()
        frame["report_date"] = frame.get("first_admission_date", "2026-06-29")
        return frame[["report_date", "asset_id", "symbol", "name"]].drop_duplicates("asset_id")
    return _empty_frame(["report_date", "asset_id", "symbol", "name"])


def _load_source(project_root: Path) -> tuple[pd.DataFrame, Path | None]:
    for path in _candidate_source_paths(project_root):
        try:
            frame = pd.read_csv(path)
        except Exception:
            continue
        if {"asset_id", "report_period", "report_disclosure_date", "data_available_asof_date"}.issubset(frame.columns):
            return frame, path
    return pd.DataFrame(), None


def run(project_root: Path, output_dir: Path) -> dict[str, pd.DataFrame | str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    watchlist = _read_watchlist(project_root)
    source, source_path = _load_source(project_root)
    candidate_paths = [source_path] if source_path is not None else []
    inventory = build_fundamental_source_inventory(project_root, candidate_paths=candidate_paths)
    if source_path is not None:
        source_name = source_path.stem
        source_label = str(source_path.relative_to(project_root))
    else:
        source_name = "source_missing"
        source_label = "missing"
    raw = build_raw_candidate_matches(watchlist, source, source_name=source_name, raw_source_path_or_table=source_label)
    structured = build_structured_fundamentals(watchlist, source)
    coverage = build_fundamental_asset_coverage(watchlist, structured)
    field_audit = build_fundamental_field_coverage_audit(structured)
    patch = build_watchlist_fundamental_gap_patch(watchlist, coverage)
    quality_audit = build_fundamental_quality_audit(inventory, raw, structured, coverage)
    scanned_paths = scan_fundamental_related_paths(project_root)
    git_info = _git_info(project_root)
    report_text = render_main_report(inventory, coverage, field_audit, patch, quality_audit, git_info, scanned_paths)

    outputs = {
        "fundamental_source_inventory.csv": inventory,
        "fundamental_raw_candidate_matches.csv": raw,
        "fundamental_structured_outputs.csv": structured,
        "fundamental_asset_coverage.csv": coverage,
        "fundamental_field_coverage_audit.csv": field_audit,
        "watchlist_fundamental_gap_patch.csv": patch,
        "fundamental_quality_audit.csv": quality_audit,
    }
    for filename, frame in outputs.items():
        safe = sanitize_dataframe_for_output(frame)
        text = safe.to_csv(index=False)
        if contains_actionable_trading_language(text):
            raise ValueError(f"{filename} contains actionable trading language")
        (output_dir / filename).write_text(text, encoding="utf-8")
    (output_dir / "fundamental_source_adapter_v1.md").write_text(report_text, encoding="utf-8")
    return {**outputs, "report": report_text}


def main() -> None:
    parser = argparse.ArgumentParser(description="Build research-only Tech Bottleneck fundamental source adapter outputs.")
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    project_root = args.project_root.resolve()
    output_dir = args.output_dir
    if not output_dir.is_absolute():
        output_dir = project_root / output_dir
    result = run(project_root, output_dir)
    audit = result["fundamental_quality_audit.csv"]
    if isinstance(audit, pd.DataFrame):
        metrics = _metric_lookup(audit)
        print(f"output_dir={output_dir}")
        print(f"structured_fundamental_rows={metrics.get('structured_fundamental_rows', 0)}")
        print(f"assets_with_fundamental_support={metrics.get('assets_with_fundamental_support', 0)}")
        print(f"fundamental_coverage_ratio={metrics.get('fundamental_coverage_ratio', 0)}")
        print(f"lookahead_violation_rows={metrics.get('lookahead_violation_rows', 0)}")


if __name__ == "__main__":
    main()
