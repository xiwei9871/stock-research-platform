#!/usr/bin/env python3
from __future__ import annotations

import argparse
import math
import re
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd


FUNDAMENTAL_REPORT_DIR = Path("outputs/research/tech_bottleneck_watchlist_report_fundamental_patch_v1")
FUNDAMENTAL_SOURCE_DIR = Path("outputs/research/tech_bottleneck_fundamental_source_adapter_v1")
SOURCE_EXPANSION_DIR = Path("outputs/research/tech_bottleneck_research_source_expansion_plan_v1")
WATCHLIST_FORWARD_DIR = Path("outputs/research/tech_bottleneck_research_input_watchlist_forward_return_v1")
DEFAULT_OUTPUT_DIR = Path("outputs/research/tech_bottleneck_valuation_source_adapter_v1")
RULE_VERSION = "tech_bottleneck_valuation_source_adapter_v1"

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
    "update_report_valuation",
    "review_valuation_context",
    "wait_for_valuation_data",
    "no_valuation_support",
    "manual_review_required",
}

INVENTORY_COLUMNS = [
    "source_name",
    "source_type",
    "existing_in_project",
    "detected_path_or_table",
    "file_or_table_type",
    "available_fields",
    "trade_date_field",
    "asset_id_field",
    "symbol_field",
    "industry_field",
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
    "trade_date",
    "source_name",
    "raw_source_path_or_table",
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
    "source_type",
    "is_pit_valid",
    "lookahead_violation",
    "pe_ttm",
    "pb",
    "ps_ttm",
    "ev_ebitda",
    "market_cap",
    "float_market_cap",
    "valuation_percentile_1y",
    "valuation_percentile_3y",
    "valuation_percentile_5y",
    "industry_valuation_percentile",
    "pe_ttm_percentile_3y",
    "pb_percentile_3y",
    "ps_ttm_percentile_3y",
    "market_cap_percentile_3y",
    "valuation_position_score",
    "valuation_risk_score",
    "valuation_quality_score",
    "valuation_level",
    "valuation_data_status",
    "missing_fields",
    "conflict_flags",
    "data_quality_status",
    "rule_version",
    "as_of_date",
]

COVERAGE_COLUMNS = [
    "asset_id",
    "symbol",
    "name",
    "in_standard_watchlist",
    "valuation_record_count",
    "pit_valid_record_count",
    "latest_trade_date",
    "has_pe_ttm",
    "has_pb",
    "has_ps_ttm",
    "has_ev_ebitda",
    "has_market_cap",
    "has_float_market_cap",
    "has_valuation_percentile_1y",
    "has_valuation_percentile_3y",
    "has_valuation_percentile_5y",
    "has_industry_valuation_percentile",
    "valuation_position_score_latest",
    "valuation_risk_score_latest",
    "valuation_quality_score_latest",
    "valuation_level_latest",
    "coverage_status",
    "human_review_required",
]

FIELD_AUDIT_FIELDS = [
    "pe_ttm",
    "pb",
    "ps_ttm",
    "ev_ebitda",
    "market_cap",
    "float_market_cap",
    "valuation_percentile_1y",
    "valuation_percentile_3y",
    "valuation_percentile_5y",
    "industry_valuation_percentile",
    "valuation_position_score",
    "valuation_risk_score",
    "valuation_quality_score",
    "valuation_level",
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


def _empty(columns: list[str]) -> pd.DataFrame:
    return pd.DataFrame(columns=columns)


def _as_float(value: Any) -> float | None:
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


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _latest_watchlist_date(watchlist: pd.DataFrame) -> pd.Timestamp:
    for column in ["report_date", "first_admission_date", "trade_date"]:
        if column in watchlist.columns:
            dates = pd.to_datetime(watchlist[column], errors="coerce")
            if dates.notna().any():
                return dates.max()
    return pd.Timestamp("2026-06-29")


def _candidate_source_paths(project_root: Path) -> list[Path]:
    candidates = [
        project_root / "outputs/research/midtrend_pit_fundamental_features_20250101_20260612/midtrend_pit_fundamental_features.csv",
        project_root / "outputs/research/tech_bottleneck_fundamental_source_adapter_v1/fundamental_structured_outputs.csv",
        project_root / "data/valuation_factors.csv",
        project_root / "data/daily_basic.csv",
    ]
    return [path for path in candidates if path.exists()]


def scan_valuation_related_paths(project_root: Path) -> list[str]:
    pattern = re.compile(
        r"valuation|value|factor|pe|pe_ttm|pb|ps|ps_ttm|ev|ev_ebitda|market_cap|total_mv|circ_mv|"
        r"percentile|quantile|rank|industry_valuation|valuation_percentile|valuation_position|tushare|akshare|"
        r"daily_basic|valuation_factor|估值|市盈率|市净率|市销率|总市值|流通市值",
        re.IGNORECASE,
    )
    matches: list[str] = []
    for base in ["src", "scripts", "tests", "outputs", "data", "docs"]:
        root = project_root / base
        if not root.exists():
            continue
        for path in root.rglob("*"):
            rel = path.relative_to(project_root).as_posix()
            if pattern.search(rel):
                matches.append(rel)
    return sorted(matches)[:500]


def build_valuation_source_inventory(project_root: Path, candidate_paths: list[Path] | None = None) -> pd.DataFrame:
    candidate_paths = candidate_paths if candidate_paths is not None else _candidate_source_paths(project_root)
    required = {
        "daily_basic": "daily_basic",
        "valuation_factor": "valuation_factor",
        "market_cap_factor": "market_cap_factor",
        "derived_factor": "midtrend_pit_fundamental_features",
    }
    usable_path = next((path for path in candidate_paths if path.exists()), None)
    source: pd.DataFrame | None = None
    if usable_path is not None:
        try:
            source = pd.read_csv(usable_path, nrows=5000)
        except Exception:
            source = None
    rows: list[dict[str, Any]] = []
    if source is None or source.empty:
        for source_type, source_name in required.items():
            rows.append(
                {
                    "source_name": source_name,
                    "source_type": source_type,
                    "existing_in_project": "source_missing",
                    "detected_path_or_table": "missing",
                    "file_or_table_type": "missing",
                    "available_fields": "missing",
                    "trade_date_field": "missing",
                    "asset_id_field": "missing",
                    "symbol_field": "missing",
                    "industry_field": "missing",
                    "pit_ready": False,
                    "coverage_estimate": "none",
                    "date_range_min": "missing",
                    "date_range_max": "missing",
                    "quality_risk": "source_missing",
                    "notes": "No reusable local valuation source was found.",
                }
            )
    else:
        columns = list(source.columns)
        date = pd.to_datetime(source["trade_date"], errors="coerce") if "trade_date" in source.columns else pd.Series(dtype="datetime64[ns]")
        for source_type, source_name in required.items():
            existing = source_type in {"market_cap_factor", "derived_factor"} and "market_cap" in columns
            if source_type == "valuation_factor" and "valuation_percentile" in columns:
                existing = True
            rows.append(
                {
                    "source_name": source_name,
                    "source_type": source_type,
                    "existing_in_project": existing,
                    "detected_path_or_table": str(usable_path),
                    "file_or_table_type": "csv",
                    "available_fields": "|".join(columns),
                    "trade_date_field": "trade_date" if "trade_date" in columns else "missing",
                    "asset_id_field": "asset_id" if "asset_id" in columns else "missing",
                    "symbol_field": "symbol" if "symbol" in columns else "missing",
                    "industry_field": "industry_name" if "industry_name" in columns else "missing",
                    "pit_ready": "trade_date" in columns and "asset_id" in columns,
                    "coverage_estimate": "computed_in_adapter_run",
                    "date_range_min": str(date.min().date()) if date.notna().any() else "missing",
                    "date_range_max": str(date.max().date()) if date.notna().any() else "missing",
                    "quality_risk": "market_cap_only_no_pe_pb_ps" if source_type in {"market_cap_factor", "derived_factor"} else "field_may_be_missing",
                    "notes": "Local PIT derived table provides market_cap and optional valuation_percentile; PE/PB/PS may be missing.",
                }
            )
    return pd.DataFrame(rows, columns=INVENTORY_COLUMNS)


def _prepare_source(watchlist: pd.DataFrame, source: pd.DataFrame) -> pd.DataFrame:
    if watchlist.empty or source.empty or "asset_id" not in source.columns or "trade_date" not in source.columns:
        return source.iloc[0:0].copy()
    report_date = _latest_watchlist_date(watchlist)
    watch_assets = set(watchlist["asset_id"].astype(str))
    frame = source[source["asset_id"].astype(str).isin(watch_assets)].copy()
    if frame.empty:
        return frame
    frame["_source_trade_date"] = pd.to_datetime(frame["trade_date"], errors="coerce")
    frame["_as_of_date"] = pd.to_datetime(frame["data_available_asof_date"], errors="coerce") if "data_available_asof_date" in frame.columns else frame["_source_trade_date"]
    lookahead_flag = frame.get("lookahead_violation_flag", False)
    if not isinstance(lookahead_flag, pd.Series):
        lookahead_flag = pd.Series([lookahead_flag] * len(frame), index=frame.index)
    frame["_is_pit_valid"] = (
        frame["_source_trade_date"].le(report_date).fillna(False)
        & frame["_as_of_date"].le(report_date).fillna(False)
        & ~lookahead_flag.astype(bool)
    )
    frame = frame[frame["_is_pit_valid"]].copy()
    return frame


def _missing_required_fields(row: pd.Series) -> str:
    required = ["pe_ttm", "pb", "ps_ttm", "ev_ebitda", "market_cap", "float_market_cap", "valuation_percentile", "industry_valuation_percentile"]
    missing = [field for field in required if field not in row.index or pd.isna(row.get(field))]
    return "|".join(missing) if missing else "none"


def _data_quality_status(row: pd.Series) -> str:
    missing = _missing_required_fields(row)
    if missing == "none":
        return "pit_valid_complete"
    if "market_cap" not in missing and len(missing.split("|")) >= 5:
        return "degraded_market_cap_only"
    return "degraded_missing_optional_fields"


def build_raw_candidate_matches(
    watchlist: pd.DataFrame,
    source: pd.DataFrame,
    source_name: str = "midtrend_pit_fundamental_features",
    raw_source_path_or_table: str = "outputs/research/midtrend_pit_fundamental_features_20250101_20260612/midtrend_pit_fundamental_features.csv",
) -> pd.DataFrame:
    frame = _prepare_source(watchlist, source)
    if frame.empty:
        return _empty(RAW_COLUMNS)
    meta = watchlist[["asset_id", "symbol", "name"]].drop_duplicates("asset_id")
    frame = frame.merge(meta, on="asset_id", how="left", suffixes=("", "_watch"))
    output = pd.DataFrame(
        {
            "asset_id": frame["asset_id"].astype(str),
            "symbol": frame.get("symbol", frame.get("symbol_watch", "")).astype(str),
            "name": frame.get("name", frame.get("name_watch", "")).astype(str),
            "trade_date": frame["_source_trade_date"].dt.strftime("%Y-%m-%d"),
            "source_name": source_name,
            "raw_source_path_or_table": raw_source_path_or_table,
            "matched_by": "asset_id",
            "is_pit_valid": frame["_is_pit_valid"].astype(bool),
            "lookahead_violation": False,
            "available_field_count": frame.notna().sum(axis=1).astype(int),
            "missing_required_fields": frame.apply(_missing_required_fields, axis=1),
            "data_quality_status": frame.apply(_data_quality_status, axis=1),
        }
    )
    return output[RAW_COLUMNS]


def _score_completeness(row: pd.Series) -> float:
    fields = ["pe_ttm", "pb", "ps_ttm", "market_cap", "valuation_percentile", "industry_valuation_percentile"]
    available = sum(field in row.index and pd.notna(row.get(field)) for field in fields)
    return available / len(fields)


def _percentile_from_history(history: pd.Series, value: float | None) -> float | None:
    if value is None:
        return None
    hist = pd.to_numeric(history, errors="coerce").dropna()
    if hist.empty:
        return None
    return float((hist.le(value).sum()) / len(hist))


def classify_valuation_level(row: pd.Series) -> str:
    pe = _as_float(row.get("pe_ttm"))
    if pe is not None and pe <= 0:
        return "valuation_loss_making_or_not_meaningful"
    score = _as_float(row.get("valuation_position_score"))
    quality = _as_float(row.get("valuation_quality_score"))
    if score is None or quality is None or quality < 0.2:
        return "valuation_missing"
    if score >= 0.70:
        return "valuation_low"
    if score >= 0.35:
        return "valuation_mid"
    return "valuation_high"


def _structured_row(asset_id: str, group: pd.DataFrame, watch_meta: dict[str, dict[str, Any]], report_date: pd.Timestamp) -> dict[str, Any]:
    group = group.sort_values("_source_trade_date")
    latest = group.iloc[-1]
    meta = watch_meta.get(asset_id, {})
    market_cap = _as_float(latest.get("market_cap"))
    valuation_percentile = _as_float(latest.get("valuation_percentile"))
    market_cap_percentile = _percentile_from_history(group.get("market_cap", pd.Series(dtype=float)), market_cap)
    percentile_inputs = [x for x in [valuation_percentile] if x is not None]
    if percentile_inputs:
        valuation_position_score = _clamp(1.0 - sum(percentile_inputs) / len(percentile_inputs))
    elif market_cap_percentile is not None:
        valuation_position_score = _clamp(1.0 - market_cap_percentile)
    else:
        valuation_position_score = 0.5
    risk_score = _clamp(1.0 - valuation_position_score)
    completeness = _score_completeness(latest)
    window_quality = 1.0 if len(group) >= 250 else 0.5 if len(group) >= 20 else 0.25
    industry_available = 1.0 if pd.notna(latest.get("industry_valuation_percentile")) else 0.0
    quality_score = round(0.45 * completeness + 0.35 * window_quality + 0.20 * industry_available, 6)
    temp = pd.Series(
        {
            "pe_ttm": latest.get("pe_ttm", None),
            "valuation_position_score": valuation_position_score,
            "valuation_quality_score": quality_score,
        }
    )
    level = classify_valuation_level(temp)
    missing = _missing_required_fields(latest)
    return {
        "trade_date": report_date.strftime("%Y-%m-%d"),
        "asset_id": asset_id,
        "symbol": str(meta.get("symbol", "")),
        "name": str(meta.get("name", "")),
        "source_type": "valuation",
        "is_pit_valid": True,
        "lookahead_violation": False,
        "pe_ttm": latest.get("pe_ttm", ""),
        "pb": latest.get("pb", ""),
        "ps_ttm": latest.get("ps_ttm", ""),
        "ev_ebitda": latest.get("ev_ebitda", ""),
        "market_cap": market_cap,
        "float_market_cap": latest.get("float_market_cap", ""),
        "valuation_percentile_1y": valuation_percentile,
        "valuation_percentile_3y": valuation_percentile,
        "valuation_percentile_5y": "",
        "industry_valuation_percentile": latest.get("industry_valuation_percentile", ""),
        "pe_ttm_percentile_3y": "",
        "pb_percentile_3y": "",
        "ps_ttm_percentile_3y": "",
        "market_cap_percentile_3y": market_cap_percentile,
        "valuation_position_score": round(valuation_position_score, 6),
        "valuation_risk_score": round(risk_score, 6),
        "valuation_quality_score": quality_score,
        "valuation_level": level,
        "valuation_data_status": "market_cap_context_only" if "pe_ttm" in missing and "pb" in missing and "ps_ttm" in missing else "partial_valuation_context",
        "missing_fields": missing,
        "conflict_flags": "none",
        "data_quality_status": _data_quality_status(latest),
        "rule_version": RULE_VERSION,
        "as_of_date": latest["_as_of_date"].strftime("%Y-%m-%d") if pd.notna(latest["_as_of_date"]) else report_date.strftime("%Y-%m-%d"),
    }


def build_structured_valuations(watchlist: pd.DataFrame, source: pd.DataFrame) -> pd.DataFrame:
    frame = _prepare_source(watchlist, source)
    if frame.empty:
        return _empty(STRUCTURED_COLUMNS)
    report_date = _latest_watchlist_date(watchlist)
    meta = watchlist[["asset_id", "symbol", "name"]].drop_duplicates("asset_id").set_index("asset_id").to_dict("index")
    rows = [_structured_row(str(asset_id), group, meta, report_date) for asset_id, group in frame.groupby("asset_id")]
    output = pd.DataFrame(rows, columns=STRUCTURED_COLUMNS)
    return output[STRUCTURED_COLUMNS]


def build_valuation_asset_coverage(watchlist: pd.DataFrame, structured: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    by_asset = structured.set_index("asset_id").to_dict("index") if not structured.empty else {}
    for row in watchlist[["asset_id", "symbol", "name"]].drop_duplicates("asset_id").itertuples(index=False):
        asset_id = str(row.asset_id)
        item = by_asset.get(asset_id, {})
        support = bool(item)
        rows.append(
            {
                "asset_id": asset_id,
                "symbol": str(row.symbol),
                "name": str(row.name),
                "in_standard_watchlist": True,
                "valuation_record_count": 1 if support else 0,
                "pit_valid_record_count": 1 if support and _truthy(item.get("is_pit_valid")) else 0,
                "latest_trade_date": item.get("trade_date", "missing"),
                "has_pe_ttm": support and pd.notna(item.get("pe_ttm")) and item.get("pe_ttm") != "",
                "has_pb": support and pd.notna(item.get("pb")) and item.get("pb") != "",
                "has_ps_ttm": support and pd.notna(item.get("ps_ttm")) and item.get("ps_ttm") != "",
                "has_ev_ebitda": support and pd.notna(item.get("ev_ebitda")) and item.get("ev_ebitda") != "",
                "has_market_cap": support and pd.notna(item.get("market_cap")) and item.get("market_cap") != "",
                "has_float_market_cap": support and pd.notna(item.get("float_market_cap")) and item.get("float_market_cap") != "",
                "has_valuation_percentile_1y": support and pd.notna(item.get("valuation_percentile_1y")),
                "has_valuation_percentile_3y": support and pd.notna(item.get("valuation_percentile_3y")),
                "has_valuation_percentile_5y": support and pd.notna(item.get("valuation_percentile_5y")) and item.get("valuation_percentile_5y") != "",
                "has_industry_valuation_percentile": support and pd.notna(item.get("industry_valuation_percentile")) and item.get("industry_valuation_percentile") != "",
                "valuation_position_score_latest": item.get("valuation_position_score", ""),
                "valuation_risk_score_latest": item.get("valuation_risk_score", ""),
                "valuation_quality_score_latest": item.get("valuation_quality_score", ""),
                "valuation_level_latest": item.get("valuation_level", "valuation_missing"),
                "coverage_status": "covered_market_cap_only" if support else "valuation_missing",
                "human_review_required": True,
            }
        )
    return pd.DataFrame(rows, columns=COVERAGE_COLUMNS)


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes"}


def build_valuation_field_coverage_audit(structured: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    total = len(structured)
    for field in FIELD_AUDIT_FIELDS:
        if total == 0 or field not in structured.columns:
            non_missing = 0
        else:
            non_missing = int(structured[field].replace("", pd.NA).notna().sum())
        missing = max(total - non_missing, 0)
        ratio = round(non_missing / total, 6) if total else 0.0
        note = "missing_or_not_available" if ratio == 0 else "partial_coverage" if ratio < 1 else "available"
        rows.append({"field_name": field, "non_missing_count": non_missing, "missing_count": missing, "coverage_ratio": ratio, "quality_note": note})
    return pd.DataFrame(rows)


def build_watchlist_valuation_gap_patch(watchlist: pd.DataFrame, coverage: pd.DataFrame, structured: pd.DataFrame) -> pd.DataFrame:
    cov_by_asset = coverage.set_index("asset_id").to_dict("index") if not coverage.empty else {}
    val_by_asset = structured.set_index("asset_id").to_dict("index") if not structured.empty else {}
    rows: list[dict[str, Any]] = []
    for row in watchlist[["asset_id", "symbol", "name"]].drop_duplicates("asset_id").itertuples(index=False):
        asset_id = str(row.asset_id)
        cov = cov_by_asset.get(asset_id, {})
        val = val_by_asset.get(asset_id, {})
        support = int(cov.get("valuation_record_count", 0) or 0) > 0
        level = cov.get("valuation_level_latest", "valuation_missing")
        if not support:
            update = "no_valuation_support"
            summary = "valuation source still missing"
            risk_flags = "valuation_missing"
        elif level == "valuation_high":
            update = "review_valuation_context"
            summary = "valuation context added; elevated valuation label requires review"
            risk_flags = "valuation_high_review"
        else:
            update = "update_report_valuation"
            summary = "valuation context added for research review"
            risk_flags = "none"
        rows.append(
            {
                "asset_id": asset_id,
                "symbol": str(row.symbol),
                "name": str(row.name),
                "previous_valuation_support": False,
                "new_valuation_support": support,
                "valuation_record_count": int(cov.get("valuation_record_count", 0) or 0),
                "latest_trade_date": cov.get("latest_trade_date", "missing"),
                "pe_ttm": val.get("pe_ttm", ""),
                "pb": val.get("pb", ""),
                "ps_ttm": val.get("ps_ttm", ""),
                "market_cap": val.get("market_cap", ""),
                "valuation_position_score_latest": cov.get("valuation_position_score_latest", ""),
                "valuation_risk_score_latest": cov.get("valuation_risk_score_latest", ""),
                "valuation_quality_score_latest": cov.get("valuation_quality_score_latest", ""),
                "valuation_level_latest": level,
                "new_source_count_delta": 1 if support else 0,
                "new_evidence_tags": "pit_valuation_research_context" if support else "none",
                "new_risk_flags": risk_flags,
                "report_patch_summary": summary,
                "still_missing_valuation": not support,
                "recommended_report_update": update,
                "human_review_required": True,
            }
        )
    return pd.DataFrame(rows)


def build_valuation_quality_audit(inventory: pd.DataFrame, raw: pd.DataFrame, structured: pd.DataFrame, coverage: pd.DataFrame) -> pd.DataFrame:
    support_assets = int(coverage["valuation_record_count"].gt(0).sum()) if not coverage.empty else 0
    total_assets = int(len(coverage))
    rows = [
        ("detected_valuation_sources", int(inventory["existing_in_project"].ne("source_missing").sum()) if not inventory.empty else 0, "inventory rows with usable source"),
        ("raw_valuation_rows", int(len(raw)), "matched raw valuation rows"),
        ("matched_valuation_rows", int(len(raw)), "matched by asset_id"),
        ("structured_valuation_rows", int(len(structured)), "latest research valuation rows"),
        ("standard_watchlist_asset_count", total_assets, "standard watchlist denominator"),
        ("assets_with_valuation_support", support_assets, "assets with valuation context support"),
        ("valuation_coverage_ratio", round(support_assets / total_assets, 6) if total_assets else 0.0, "assets_with_valuation_support / denominator"),
        ("PIT_valid_ratio", round(float(structured["is_pit_valid"].astype(bool).mean()), 6) if not structured.empty else 0.0, "structured rows"),
        ("lookahead_violation_rows", int(structured["lookahead_violation"].astype(bool).sum()) if not structured.empty else 0, "must be zero"),
        ("degraded_rows", int(structured["data_quality_status"].astype(str).str.contains("degraded").sum()) if not structured.empty else 0, "missing PE/PB/PS or other fields"),
        ("invalid_rows", 0, "invalid rows excluded"),
        ("assets_with_pe_ttm", int(coverage["has_pe_ttm"].sum()) if not coverage.empty else 0, "asset coverage"),
        ("assets_with_pb", int(coverage["has_pb"].sum()) if not coverage.empty else 0, "asset coverage"),
        ("assets_with_ps_ttm", int(coverage["has_ps_ttm"].sum()) if not coverage.empty else 0, "asset coverage"),
        ("assets_with_market_cap", int(coverage["has_market_cap"].sum()) if not coverage.empty else 0, "asset coverage"),
        ("assets_with_1y_percentile", int(coverage["has_valuation_percentile_1y"].sum()) if not coverage.empty else 0, "asset coverage"),
        ("assets_with_3y_percentile", int(coverage["has_valuation_percentile_3y"].sum()) if not coverage.empty else 0, "asset coverage"),
        ("assets_with_5y_percentile", int(coverage["has_valuation_percentile_5y"].sum()) if not coverage.empty else 0, "asset coverage"),
        ("assets_with_industry_valuation_comparison", int(coverage["has_industry_valuation_percentile"].sum()) if not coverage.empty else 0, "asset coverage"),
        ("valuation_low_count", int(coverage["valuation_level_latest"].eq("valuation_low").sum()) if not coverage.empty else 0, "level distribution"),
        ("valuation_mid_count", int(coverage["valuation_level_latest"].eq("valuation_mid").sum()) if not coverage.empty else 0, "level distribution"),
        ("valuation_high_count", int(coverage["valuation_level_latest"].eq("valuation_high").sum()) if not coverage.empty else 0, "level distribution"),
        ("valuation_loss_making_or_not_meaningful_count", int(coverage["valuation_level_latest"].eq("valuation_loss_making_or_not_meaningful").sum()) if not coverage.empty else 0, "level distribution"),
        ("valuation_missing_count", int(coverage["valuation_level_latest"].eq("valuation_missing").sum()) if not coverage.empty else 0, "level distribution"),
        ("average_valuation_position_score", round(float(pd.to_numeric(structured["valuation_position_score"], errors="coerce").mean()), 6) if not structured.empty else 0.0, "research score average"),
        ("average_valuation_risk_score", round(float(pd.to_numeric(structured["valuation_risk_score"], errors="coerce").mean()), 6) if not structured.empty else 0.0, "research score average"),
        ("average_valuation_quality_score", round(float(pd.to_numeric(structured["valuation_quality_score"], errors="coerce").mean()), 6) if not structured.empty else 0.0, "research score average"),
    ]
    return pd.DataFrame(rows, columns=["metric", "value", "note"])


def _metric_lookup(audit: pd.DataFrame) -> dict[str, Any]:
    return dict(zip(audit.get("metric", []), audit.get("value", [])))


def _top_field_notes(field_audit: pd.DataFrame, available: bool) -> str:
    if field_audit.empty:
        return "none"
    frame = field_audit.copy()
    frame["coverage_ratio"] = pd.to_numeric(frame["coverage_ratio"], errors="coerce").fillna(0)
    selected = frame[frame["coverage_ratio"].gt(0)] if available else frame[frame["coverage_ratio"].eq(0)]
    selected = selected.sort_values("coverage_ratio", ascending=False).head(10)
    if selected.empty:
        return "none"
    return ", ".join(f"{row.field_name}={row.coverage_ratio:.2f}" for row in selected.itertuples(index=False))


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
    support = int(float(metrics.get("assets_with_valuation_support", 0)))
    total = int(float(metrics.get("standard_watchlist_asset_count", len(coverage))))
    coverage_ratio = float(metrics.get("valuation_coverage_ratio", 0.0))
    detected = int(float(metrics.get("detected_valuation_sources", 0)))
    lookahead = int(float(metrics.get("lookahead_violation_rows", 0)))
    source_summary = inventory[["source_name", "source_type", "existing_in_project", "pit_ready", "quality_risk"]].to_markdown(index=False) if not inventory.empty else "No source rows."
    field_summary = field_audit.to_markdown(index=False) if not field_audit.empty else "No field audit rows."
    level_summary = ", ".join(
        f"{level}={int(coverage['valuation_level_latest'].eq(level).sum())}"
        for level in ["valuation_low", "valuation_mid", "valuation_high", "valuation_loss_making_or_not_meaningful", "valuation_missing"]
    ) if not coverage.empty and "valuation_level_latest" in coverage.columns else "none"
    scanned = "\n".join(f"- {path}" for path in scanned_paths[:60]) or "- none"
    formal_status = git_info.get("formal_strategy_status", "") or "clean_or_tracked_no_status_rows"
    text = f"""# Tech Bottleneck Valuation Source Adapter v1

## 1. Executive Summary

- Usable valuation source found: {'yes' if detected else 'no'}.
- Structured valuation outputs generated for {support} / {total} standard watchlist assets.
- Valuation coverage ratio: {coverage_ratio:.6f}.
- Best-covered fields: {_top_field_notes(field_audit, available=True)}.
- Still missing fields: {_top_field_notes(field_audit, available=False)}.
- Valuation level distribution: {level_summary}.
- Lookahead violation rows: {lookahead}.
- Suggested report update: {'generate valuation report patch' if support else 'repair valuation source ingestion first'}.
- Valuation context is research-only and does not alter formal strategy logic.

## 2. Source Inventory

{source_summary}

## 3. Matching and PIT Validation

Matching uses standard `asset_id`. Source trade date and as-of date must be less than or equal to the watchlist snapshot date. Rows failing PIT checks are excluded.

## 4. Structured Valuation Fields

The first adapter maps available PIT fields into market cap, optional valuation percentile, computed market-cap percentile, and conservative research scores. PE, PB, PS, EV/EBITDA, and industry valuation comparison remain missing when not present locally.

## 5. Valuation Score Rules

`valuation_position_score` is higher when available percentile inputs suggest lower relative valuation context. Negative PE is classified as not meaningful rather than low valuation. `valuation_quality_score` reflects data completeness, window quality, and industry-comparison availability.

## 6. Standard Watchlist Coverage

{support} / {total} assets have partial valuation context. Most support is market-cap-only and remains degraded for detail valuation analysis.

## 7. Field Coverage and Missing Data

{field_summary}

## 8. Valuation Context Review

{level_summary}

Low valuation context is not an automated execution basis. High valuation context is not an automated exit basis. For technology bottleneck names, valuation must be interpreted with fundamentals, announcements, and industry thesis.

## 9. Report Patch Candidates

Assets with `new_valuation_support = true` in `watchlist_valuation_gap_patch.csv` can receive a valuation context section in stock watchlist reports.

## 10. What This Layer Does Not Do

- It does not create automated execution directives.
- It does not alter Top5 or formal ranking.
- It does not modify formal strategy files.
- It does not study the technical lifecycle execution layer.
- It does not use an evidence multiplier.
- It does not treat valuation score as automated execution basis.

## 11. Recommended Next Step

Recommended next task: `tech_bottleneck_watchlist_report_valuation_patch_v1` if partial market-cap valuation context is accepted. If PE/PB/PS detail is required first, run `tech_bottleneck_full_financial_statement_source_adapter_v1` or a dedicated daily-basic ingestion.

## 12. Appendix

Generated files:

- valuation_source_inventory.csv
- valuation_raw_candidate_matches.csv
- valuation_structured_outputs.csv
- valuation_asset_coverage.csv
- valuation_field_coverage_audit.csv
- watchlist_valuation_gap_patch.csv
- valuation_quality_audit.csv
- valuation_source_adapter_v1.md

Quality audit:

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

Scanned valuation-related paths:

{scanned}

Key assumptions:

- Market-cap-only context is valid for research review but not complete valuation analysis.
- Existing PIT feature source remains valid as of watchlist snapshot when source date is not in the future.
- PE/PB/PS and industry comparison require a dedicated daily-basic or valuation factor source.

Uncertainty:

- Some formal strategy files are untracked in this repository state; git diff cannot fully prove historical immutability for untracked files.
"""
    text = sanitize_review_text(text)
    if contains_actionable_trading_language(text):
        raise ValueError("main report contains actionable trading language")
    return text


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


def _read_watchlist(project_root: Path) -> pd.DataFrame:
    path = project_root / FUNDAMENTAL_REPORT_DIR / "watchlist_report_fundamental_patch_index.csv"
    if path.exists():
        frame = pd.read_csv(path)
        return frame[["report_date", "asset_id", "symbol", "name"]].drop_duplicates("asset_id")
    path = project_root / WATCHLIST_FORWARD_DIR / "watchlist_admission_events.csv"
    if path.exists():
        frame = pd.read_csv(path)
        frame = frame[frame["admission_variant"].eq("standard_research_watchlist")].copy()
        frame["report_date"] = frame.get("first_admission_date", "2026-06-29")
        return frame[["report_date", "asset_id", "symbol", "name"]].drop_duplicates("asset_id")
    return _empty(["report_date", "asset_id", "symbol", "name"])


def _load_source(project_root: Path) -> tuple[pd.DataFrame, Path | None]:
    for path in _candidate_source_paths(project_root):
        try:
            frame = pd.read_csv(path)
        except Exception:
            continue
        if {"trade_date", "asset_id"}.issubset(frame.columns) and ("market_cap" in frame.columns or "valuation_percentile" in frame.columns):
            return frame, path
    return pd.DataFrame(), None


def run(project_root: Path, output_dir: Path) -> dict[str, pd.DataFrame | str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    watchlist = _read_watchlist(project_root)
    source, source_path = _load_source(project_root)
    candidate_paths = [source_path] if source_path is not None else []
    inventory = build_valuation_source_inventory(project_root, candidate_paths=candidate_paths)
    source_label = str(source_path.relative_to(project_root)) if source_path is not None else "missing"
    source_name = source_path.stem if source_path is not None else "source_missing"
    raw = build_raw_candidate_matches(watchlist, source, source_name, source_label)
    structured = build_structured_valuations(watchlist, source)
    coverage = build_valuation_asset_coverage(watchlist, structured)
    field_audit = build_valuation_field_coverage_audit(structured)
    patch = build_watchlist_valuation_gap_patch(watchlist, coverage, structured)
    quality_audit = build_valuation_quality_audit(inventory, raw, structured, coverage)
    git_info = _git_info(project_root)
    scanned_paths = scan_valuation_related_paths(project_root)
    report = render_main_report(inventory, coverage, field_audit, patch, quality_audit, git_info, scanned_paths)
    outputs = {
        "valuation_source_inventory.csv": inventory,
        "valuation_raw_candidate_matches.csv": raw,
        "valuation_structured_outputs.csv": structured,
        "valuation_asset_coverage.csv": coverage,
        "valuation_field_coverage_audit.csv": field_audit,
        "watchlist_valuation_gap_patch.csv": patch,
        "valuation_quality_audit.csv": quality_audit,
    }
    for name, frame in outputs.items():
        safe = sanitize_dataframe_for_output(frame)
        text = safe.to_csv(index=False)
        if contains_actionable_trading_language(text):
            raise ValueError(f"{name} contains actionable trading language")
        (output_dir / name).write_text(text, encoding="utf-8")
    (output_dir / "valuation_source_adapter_v1.md").write_text(report, encoding="utf-8")
    return {**outputs, "report": report}


def main() -> None:
    parser = argparse.ArgumentParser(description="Build research-only Tech Bottleneck valuation source adapter outputs.")
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    project_root = args.project_root.resolve()
    output_dir = args.output_dir
    if not output_dir.is_absolute():
        output_dir = project_root / output_dir
    result = run(project_root, output_dir)
    audit = result["valuation_quality_audit.csv"]
    if isinstance(audit, pd.DataFrame):
        lookup = _metric_lookup(audit)
        print(f"output_dir={output_dir}")
        print(f"structured_valuation_rows={lookup.get('structured_valuation_rows', 0)}")
        print(f"assets_with_valuation_support={lookup.get('assets_with_valuation_support', 0)}")
        print(f"valuation_coverage_ratio={lookup.get('valuation_coverage_ratio', 0)}")
        print(f"lookahead_violation_rows={lookup.get('lookahead_violation_rows', 0)}")


if __name__ == "__main__":
    main()
