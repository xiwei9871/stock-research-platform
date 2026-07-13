#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import importlib
import re
import subprocess
import time
from pathlib import Path
from typing import Any, Callable

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
BAOSTOCK_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_baostock_pe_pb_ps_source_adapter_v1"
BAOSTOCK_PATCH_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_watchlist_report_baostock_valuation_patch_v1"
AKSHARE_LG_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_akshare_lg_indicator_probe_v1"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_akshare_baidu_valuation_probe_v1"
RULE_VERSION = "tech_bottleneck_akshare_baidu_valuation_probe_v1"

TARGET_FUNCTION = "stock_zh_valuation_baidu"
BAIDU_INDICATORS = ["总市值", "市盈率(TTM)", "市盈率(静)", "市净率", "市现率"]
INDICATOR_FIELD_MAP = {
    "总市值": ("baidu_total_mv", "baidu_trade_date_market_cap"),
    "市盈率(TTM)": ("baidu_pe_ttm", "baidu_trade_date_pe_ttm"),
    "市盈率(静)": ("baidu_pe_static", "baidu_trade_date_pe_static"),
    "市净率": ("baidu_pb", "baidu_trade_date_pb"),
    "市现率": ("baidu_pcf", "baidu_trade_date_pcf"),
}

FORBIDDEN_PATTERNS = [
    re.compile(r"\b(?:buy|sell|add|reduce|hold|target_price|position_size|entry_signal|exit_signal)\b", re.I),
    re.compile(r"买入|卖出|加仓|减仓|持有|目标价|仓位建议|入场点|止损点|交易信号"),
]

SOURCE_INVENTORY_COLUMNS = [
    "source_name",
    "source_type",
    "package_available",
    "package_version",
    "candidate_function_name",
    "function_exists",
    "available_indicators",
    "available_fields_from_sample",
    "sample_call_success",
    "sample_call_error",
    "pit_ready",
    "coverage_estimate",
    "quality_risk",
    "notes",
]

PROBE_PLAN_COLUMNS = [
    "asset_id",
    "symbol",
    "name",
    "akshare_symbol",
    "baostock_code",
    "indicator",
    "probe_required",
    "target_function",
    "cache_path",
    "probe_status",
    "skip_reason",
    "human_review_required",
]

FETCH_RESULT_COLUMNS = [
    "asset_id",
    "symbol",
    "name",
    "akshare_symbol",
    "indicator",
    "target_function",
    "fetch_attempted",
    "fetch_status",
    "row_count",
    "field_count",
    "fields",
    "cache_path",
    "content_hash",
    "api_error",
    "elapsed_seconds",
    "data_quality_status",
]

STRUCTURED_COLUMNS = [
    "research_trade_date",
    "asset_id",
    "symbol",
    "name",
    "akshare_symbol",
    "source_type",
    "is_pit_valid",
    "lookahead_violation",
    "baidu_trade_date_market_cap",
    "baidu_trade_date_pe_ttm",
    "baidu_trade_date_pe_static",
    "baidu_trade_date_pb",
    "baidu_trade_date_pcf",
    "baidu_total_mv",
    "baidu_pe_ttm",
    "baidu_pe_static",
    "baidu_pb",
    "baidu_pcf",
    "baidu_ps_ttm_available",
    "valuation_data_status",
    "missing_fields",
    "conflict_flags",
    "data_quality_status",
    "rule_version",
]

CROSS_VALIDATION_COLUMNS = [
    "asset_id",
    "symbol",
    "name",
    "research_trade_date",
    "baostock_date",
    "baidu_trade_date_pe_ttm",
    "baidu_trade_date_pb",
    "date_gap_days_pe_ttm",
    "date_gap_days_pb",
    "baostock_pe_ttm",
    "baidu_pe_ttm",
    "pe_ttm_abs_diff",
    "pe_ttm_pct_diff",
    "baostock_pb",
    "baidu_pb",
    "pb_abs_diff",
    "pb_pct_diff",
    "baostock_ps_ttm",
    "baidu_ps_ttm_available",
    "baostock_total_mv",
    "baidu_total_mv",
    "total_mv_abs_diff",
    "total_mv_pct_diff",
    "validation_status",
    "discrepancy_flags",
    "recommended_action",
]

FIELD_AUDIT_COLUMNS = ["field_name", "non_missing_count", "missing_count", "coverage_ratio", "quality_note"]
AUDIT_COLUMNS = ["metric", "value", "note"]


def contains_actionable_trading_language(text: str) -> bool:
    return any(pattern.search(str(text)) for pattern in FORBIDDEN_PATTERNS)


def _sha256_file(path: Path) -> str:
    if not path.exists():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_frame(frame: pd.DataFrame, path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)
    return _sha256_file(path)


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


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes"}


def _safe_symbol(asset_id: str, symbol: Any = "") -> str:
    parts = str(asset_id).split(":")
    if len(parts) == 3:
        return parts[2]
    text = str(symbol)
    return text.zfill(6) if text.isdigit() else text


def _safe_filename(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z_\-\u4e00-\u9fff]+", "_", value).strip("_")


def _baostock_code(asset_id: str) -> str:
    _, exchange, symbol = str(asset_id).split(":")
    return f"{exchange.lower()}.{symbol}"


def _candidate_names(ak_module: Any) -> list[str]:
    return [name for name in dir(ak_module) if "valuation" in name.lower() or "baidu" in name.lower()]


def inspect_baidu_source(
    *,
    importer: Callable[[], Any] | None = None,
    ak_module: Any | None = None,
    sample_symbol: str = "600000",
) -> pd.DataFrame:
    package_available = False
    version = "missing"
    function_exists = False
    sample_success = False
    sample_error = ""
    fields = "missing"
    notes = ""
    try:
        module = ak_module if ak_module is not None else (importer() if importer else importlib.import_module("akshare"))
        package_available = True
        version = getattr(module, "__version__", "unknown")
        function_exists = hasattr(module, TARGET_FUNCTION)
        if function_exists:
            try:
                sample = getattr(module, TARGET_FUNCTION)(symbol=sample_symbol, indicator="总市值", period="近一年")
                sample_success = isinstance(sample, pd.DataFrame) and not sample.empty
                fields = "|".join(map(str, sample.columns)) if isinstance(sample, pd.DataFrame) else "not_dataframe"
                if not sample_success:
                    sample_error = "empty_or_not_dataframe"
            except Exception as exc:  # noqa: BLE001
                sample_error = str(exc)[:500]
        else:
            candidates = _candidate_names(module)
            notes = "valuation/baidu candidate functions: " + ("|".join(candidates[:40]) if candidates else "none")
    except Exception as exc:  # noqa: BLE001
        sample_error = str(exc)[:500]
    quality = "usable" if package_available and function_exists and sample_success else "package_missing_or_function_missing_or_sample_failed"
    if not package_available:
        quality = "package_missing"
    row = {
        "source_name": "AKShare Baidu valuation",
        "source_type": "akshare_baidu_valuation_probe",
        "package_available": package_available,
        "package_version": version,
        "candidate_function_name": TARGET_FUNCTION,
        "function_exists": function_exists,
        "available_indicators": "|".join(BAIDU_INDICATORS),
        "available_fields_from_sample": fields,
        "sample_call_success": sample_success,
        "sample_call_error": sample_error,
        "pit_ready": bool(package_available and function_exists and sample_success),
        "coverage_estimate": "to_be_verified_by_probe" if function_exists else "target_function_missing",
        "quality_risk": quality,
        "notes": notes or "Baidu validates PE/PB/PCF/market cap only; PS/PS-TTM is not validated.",
    }
    frame = pd.DataFrame([row], columns=SOURCE_INVENTORY_COLUMNS)
    for col in ["package_available", "function_exists", "sample_call_success", "pit_ready"]:
        frame[col] = frame[col].astype(object)
    return frame


def load_watchlist_assets() -> pd.DataFrame:
    path = BAOSTOCK_PATCH_DIR / "watchlist_baostock_valuation_patch_summary_by_asset.csv"
    frame = pd.read_csv(path)
    return frame[["asset_id", "symbol", "name"]].drop_duplicates("asset_id").reset_index(drop=True)


def build_probe_plan(watchlist: pd.DataFrame, output_dir: Path = OUTPUT_DIR, *, target_function: str = TARGET_FUNCTION) -> pd.DataFrame:
    rows = []
    for _, row in watchlist.iterrows():
        asset_id = str(row["asset_id"])
        symbol = _safe_symbol(asset_id, row.get("symbol", ""))
        for indicator in BAIDU_INDICATORS:
            cache_path = output_dir / "cache/akshare/baidu_valuation" / f"{symbol}_{_safe_filename(indicator)}.csv"
            rows.append(
                {
                    "asset_id": asset_id,
                    "symbol": symbol,
                    "name": row.get("name", ""),
                    "akshare_symbol": symbol,
                    "baostock_code": _baostock_code(asset_id),
                    "indicator": indicator,
                    "probe_required": not cache_path.exists() and target_function != "missing",
                    "target_function": target_function,
                    "cache_path": str(cache_path),
                    "probe_status": "success_cached" if cache_path.exists() else "planned",
                    "skip_reason": "cache_exists" if cache_path.exists() else ("function_missing" if target_function == "missing" else ""),
                    "human_review_required": True,
                }
            )
    frame = pd.DataFrame(rows, columns=PROBE_PLAN_COLUMNS)
    for col in ["probe_required", "human_review_required"]:
        frame[col] = frame[col].map(bool).astype(object)
    return frame


def fetch_baidu_valuation(
    plan: pd.DataFrame,
    output_dir: Path,
    inventory: pd.DataFrame,
    *,
    ak_module: Any | None = None,
    importer: Callable[[], Any] | None = None,
    stop_after_call_count: int | None = None,
    sleep_seconds: float = 0.02,
) -> pd.DataFrame:
    inv = inventory.iloc[0] if not inventory.empty else {}
    package_available = bool(inv.get("package_available", False))
    function_exists = bool(inv.get("function_exists", False))
    module = ak_module
    if module is None and package_available:
        try:
            module = importer() if importer else importlib.import_module("akshare")
        except Exception:
            module = None
    rows = []
    attempted = 0
    for _, row in plan.iterrows():
        start = time.perf_counter()
        cache_path = Path(row["cache_path"])
        if cache_path.exists():
            cached = pd.read_csv(cache_path)
            rows.append(_fetch_result(row, False, "success_cached", len(cached), len(cached.columns), "|".join(cached.columns), cache_path, "", time.perf_counter() - start))
            continue
        if not package_available:
            rows.append(_fetch_result(row, False, "package_missing", 0, 0, "", cache_path, str(inv.get("sample_call_error", "")), time.perf_counter() - start))
            continue
        if not function_exists or module is None or not hasattr(module, TARGET_FUNCTION):
            rows.append(_fetch_result(row, False, "function_missing", 0, 0, "", cache_path, "target function missing", time.perf_counter() - start))
            continue
        if stop_after_call_count is not None and attempted >= stop_after_call_count:
            rows.append(_fetch_result(row, False, "skipped", 0, 0, "", cache_path, "skipped_after_call_limit", time.perf_counter() - start))
            continue
        try:
            attempted += 1
            data = getattr(module, TARGET_FUNCTION)(symbol=str(row["akshare_symbol"]), indicator=str(row["indicator"]), period="近三年")
            if not isinstance(data, pd.DataFrame) or data.empty:
                rows.append(_fetch_result(row, True, "empty_result", 0, 0, "", cache_path, "empty_or_not_dataframe", time.perf_counter() - start))
                continue
            content_hash = _write_frame(data, cache_path)
            rows.append(_fetch_result(row, True, "success", len(data), len(data.columns), "|".join(map(str, data.columns)), cache_path, "", time.perf_counter() - start, content_hash))
            if sleep_seconds:
                time.sleep(sleep_seconds)
        except Exception as exc:  # noqa: BLE001
            error = str(exc)[:500]
            status = "network_unavailable" if "network" in error.lower() or "timeout" in error.lower() else "api_error"
            rows.append(_fetch_result(row, True, status, 0, 0, "", cache_path, error, time.perf_counter() - start))
    return pd.DataFrame(rows, columns=FETCH_RESULT_COLUMNS)


def _fetch_result(row: pd.Series, attempted: bool, status: str, row_count: int, field_count: int, fields: str, cache_path: Path, error: str, elapsed: float, content_hash: str | None = None) -> dict[str, Any]:
    return {
        "asset_id": row["asset_id"],
        "symbol": row["symbol"],
        "name": row["name"],
        "akshare_symbol": row["akshare_symbol"],
        "indicator": row["indicator"],
        "target_function": row["target_function"],
        "fetch_attempted": attempted,
        "fetch_status": status,
        "row_count": int(row_count),
        "field_count": int(field_count),
        "fields": fields,
        "cache_path": str(cache_path),
        "content_hash": content_hash or _sha256_file(cache_path),
        "api_error": error,
        "elapsed_seconds": round(float(elapsed), 4),
        "data_quality_status": "cache_available" if status in {"success", "success_cached"} and row_count else "degraded_fetch_not_available",
    }


def infer_research_trade_date() -> str:
    path = BAOSTOCK_DIR / "baostock_structured_outputs.csv"
    frame = pd.read_csv(path)
    dates = pd.to_datetime(frame["research_trade_date"], errors="coerce")
    return str(dates.max().date())


def _latest_value(cache_path: Any, research_date: pd.Timestamp) -> tuple[str, float | None]:
    path = Path(str(cache_path))
    if not path.exists():
        return "missing", None
    data = pd.read_csv(path)
    if "date" not in data.columns or "value" not in data.columns:
        return "missing", None
    data = data.copy()
    data["date_dt"] = pd.to_datetime(data["date"], errors="coerce")
    eligible = data[data["date_dt"].le(research_date)]
    if eligible.empty:
        return "missing", None
    latest = eligible.sort_values("date_dt").iloc[-1]
    return str(latest["date_dt"].date()), _as_float(latest["value"])


def build_structured_outputs(watchlist: pd.DataFrame, fetch_results: pd.DataFrame, *, research_trade_date: str) -> pd.DataFrame:
    research_date = pd.to_datetime(research_trade_date)
    grouped = {asset_id: group for asset_id, group in fetch_results.groupby("asset_id")} if not fetch_results.empty else {}
    rows = []
    for _, stock in watchlist.iterrows():
        asset_id = stock["asset_id"]
        group = grouped.get(asset_id, pd.DataFrame())
        values = {field: None for field, _ in INDICATOR_FIELD_MAP.values()}
        dates = {date_field: "missing" for _, date_field in INDICATOR_FIELD_MAP.values()}
        for _, result in group.iterrows():
            if result["fetch_status"] not in {"success", "success_cached"}:
                continue
            field, date_field = INDICATOR_FIELD_MAP[str(result["indicator"])]
            date_text, value = _latest_value(result["cache_path"], research_date)
            values[field] = value
            dates[date_field] = date_text
        missing = [field for field in ["baidu_total_mv", "baidu_pe_ttm", "baidu_pe_static", "baidu_pb", "baidu_pcf"] if values.get(field) is None]
        lookahead = False
        for date_text in dates.values():
            if date_text != "missing" and pd.to_datetime(date_text) > research_date:
                lookahead = True
        pe = values.get("baidu_pe_ttm")
        rows.append(
            {
                "research_trade_date": research_trade_date,
                "asset_id": asset_id,
                "symbol": stock["symbol"],
                "name": stock["name"],
                "akshare_symbol": str(stock["symbol"]).zfill(6),
                "source_type": "akshare_baidu_valuation",
                "is_pit_valid": not lookahead and not missing,
                "lookahead_violation": lookahead,
                "baidu_trade_date_market_cap": dates["baidu_trade_date_market_cap"],
                "baidu_trade_date_pe_ttm": dates["baidu_trade_date_pe_ttm"],
                "baidu_trade_date_pe_static": dates["baidu_trade_date_pe_static"],
                "baidu_trade_date_pb": dates["baidu_trade_date_pb"],
                "baidu_trade_date_pcf": dates["baidu_trade_date_pcf"],
                "baidu_total_mv": values["baidu_total_mv"],
                "baidu_pe_ttm": values["baidu_pe_ttm"],
                "baidu_pe_static": values["baidu_pe_static"],
                "baidu_pb": values["baidu_pb"],
                "baidu_pcf": values["baidu_pcf"],
                "baidu_ps_ttm_available": False,
                "valuation_data_status": "baidu_pe_pb_market_cap_available" if not missing else "degraded_missing_fields",
                "missing_fields": "|".join(missing + ["baidu_ps_ttm"]) if missing else "baidu_ps_ttm",
                "conflict_flags": "negative_pe_not_low" if pe is not None and pe <= 0 else "none",
                "data_quality_status": "pit_valid" if not lookahead and not missing else "degraded_missing_optional_fields",
                "rule_version": RULE_VERSION,
            }
        )
    return pd.DataFrame(rows, columns=STRUCTURED_COLUMNS)


def _diff(baostock: Any, baidu: Any) -> tuple[Any, Any]:
    b = _as_float(baostock)
    a = _as_float(baidu)
    if b is None or a is None:
        return float("nan"), float("nan")
    abs_diff = abs(a - b)
    pct = abs_diff / abs(b) if b else float("nan")
    return round(abs_diff, 6), round(pct, 6) if pd.notna(pct) else float("nan")


def _date_gap(a: Any, b: Any) -> Any:
    if str(a) == "missing" or str(b) == "missing":
        return "missing"
    return abs((pd.to_datetime(a) - pd.to_datetime(b)).days)


def _validation_status(pcts: list[float], gaps: list[Any], baidu_missing: bool, bao_missing: bool) -> str:
    if baidu_missing:
        return "baidu_missing"
    if bao_missing:
        return "baostock_missing"
    numeric_gaps = [gap for gap in gaps if isinstance(gap, int)]
    if numeric_gaps and max(numeric_gaps) > 5:
        return "date_gap_too_large"
    valid = [pct for pct in pcts if pd.notna(pct)]
    if not valid:
        return "not_comparable"
    max_pct = max(valid)
    if max_pct <= 0.05:
        return "consistent"
    if max_pct <= 0.15:
        return "minor_difference"
    return "material_difference"


def build_cross_validation(baidu_structured: pd.DataFrame, baostock_structured: pd.DataFrame) -> pd.DataFrame:
    baostock_lookup = baostock_structured.set_index("asset_id").to_dict("index") if not baostock_structured.empty else {}
    rows = []
    for _, baidu in baidu_structured.iterrows():
        b = baostock_lookup.get(baidu["asset_id"], {})
        baidu_missing = pd.isna(baidu.get("baidu_pe_ttm")) and pd.isna(baidu.get("baidu_pb")) and pd.isna(baidu.get("baidu_total_mv"))
        bao_missing = not bool(b)
        pe_abs, pe_pct = _diff(b.get("pe_ttm"), baidu.get("baidu_pe_ttm"))
        pb_abs, pb_pct = _diff(b.get("pb"), baidu.get("baidu_pb"))
        mv_abs, mv_pct = _diff(float("nan"), baidu.get("baidu_total_mv"))
        gap_pe = _date_gap(b.get("baostock_date", "missing"), baidu.get("baidu_trade_date_pe_ttm", "missing"))
        gap_pb = _date_gap(b.get("baostock_date", "missing"), baidu.get("baidu_trade_date_pb", "missing"))
        status = _validation_status([pe_pct, pb_pct], [gap_pe, gap_pb], baidu_missing, bao_missing)
        flags = ["no_auto_override", "baidu_ps_ttm_unavailable"]
        if status == "material_difference":
            flags.append("material_difference_review_required")
        action = {
            "consistent": "keep_baostock_primary",
            "minor_difference": "review_discrepancy",
            "material_difference": "review_discrepancy",
            "baidu_missing": "baidu_unavailable",
            "baostock_missing": "not_comparable",
            "not_comparable": "not_comparable",
            "date_gap_too_large": "request_third_source_validation",
        }.get(status, "not_comparable")
        rows.append(
            {
                "asset_id": baidu["asset_id"],
                "symbol": baidu["symbol"],
                "name": baidu["name"],
                "research_trade_date": baidu["research_trade_date"],
                "baostock_date": b.get("baostock_date", "missing"),
                "baidu_trade_date_pe_ttm": baidu.get("baidu_trade_date_pe_ttm", "missing"),
                "baidu_trade_date_pb": baidu.get("baidu_trade_date_pb", "missing"),
                "date_gap_days_pe_ttm": gap_pe,
                "date_gap_days_pb": gap_pb,
                "baostock_pe_ttm": b.get("pe_ttm"),
                "baidu_pe_ttm": baidu.get("baidu_pe_ttm"),
                "pe_ttm_abs_diff": pe_abs,
                "pe_ttm_pct_diff": pe_pct,
                "baostock_pb": b.get("pb"),
                "baidu_pb": baidu.get("baidu_pb"),
                "pb_abs_diff": pb_abs,
                "pb_pct_diff": pb_pct,
                "baostock_ps_ttm": b.get("ps_ttm"),
                "baidu_ps_ttm_available": False,
                "baostock_total_mv": float("nan"),
                "baidu_total_mv": baidu.get("baidu_total_mv"),
                "total_mv_abs_diff": mv_abs,
                "total_mv_pct_diff": mv_pct,
                "validation_status": status,
                "discrepancy_flags": "|".join(flags),
                "recommended_action": action,
            }
        )
    return pd.DataFrame(rows, columns=CROSS_VALIDATION_COLUMNS)


def build_field_coverage_audit(structured: pd.DataFrame, cross: pd.DataFrame) -> pd.DataFrame:
    fields = [
        "baidu_total_mv",
        "baidu_pe_ttm",
        "baidu_pe_static",
        "baidu_pb",
        "baidu_pcf",
        "baidu_trade_date_market_cap",
        "baidu_trade_date_pe_ttm",
        "baidu_trade_date_pb",
    ]
    rows = []
    total = len(structured)
    for field in fields:
        series = structured[field] if field in structured.columns else pd.Series(dtype=object)
        non_missing = int(series.notna().sum() - series.astype(str).isin(["missing", "nan", ""]).sum())
        non_missing = max(non_missing, 0)
        rows.append({"field_name": field, "non_missing_count": non_missing, "missing_count": max(total - non_missing, 0), "coverage_ratio": round(non_missing / total, 6) if total else 0.0, "quality_note": "available" if non_missing else "missing"})
    comparable = int(cross["validation_status"].isin(["consistent", "minor_difference", "material_difference"]).sum()) if not cross.empty else 0
    rows.append({"field_name": "cross_validation_status", "non_missing_count": comparable, "missing_count": max(len(cross) - comparable, 0), "coverage_ratio": round(comparable / len(cross), 6) if len(cross) else 0.0, "quality_note": "comparison status"})
    return pd.DataFrame(rows, columns=FIELD_AUDIT_COLUMNS)


def build_quality_audit(inventory: pd.DataFrame, plan: pd.DataFrame, fetch: pd.DataFrame, structured: pd.DataFrame, cross: pd.DataFrame) -> pd.DataFrame:
    inv = inventory.iloc[0] if not inventory.empty else {}
    rows = [
        ("akshare_package_available", bool(inv.get("package_available", False)), "AKShare import status"),
        ("akshare_package_version", inv.get("package_version", "missing"), "package version"),
        ("target_function_exists", bool(inv.get("function_exists", False)), "Baidu target function status"),
        ("sample_call_success", bool(inv.get("sample_call_success", False)), "sample call status"),
        ("probe plan rows", len(plan), "asset indicator plans"),
        ("fetch attempted rows", int(fetch["fetch_attempted"].fillna(False).astype(bool).sum()) if not fetch.empty else 0, "attempted calls"),
        ("fetch success rows", int(fetch["fetch_status"].eq("success").sum()) if not fetch.empty else 0, "new source rows"),
        ("fetch success_cached rows", int(fetch["fetch_status"].eq("success_cached").sum()) if not fetch.empty else 0, "cached source rows"),
        ("fetch failed rows", int(fetch["fetch_status"].isin(["package_missing", "function_missing", "api_error", "network_unavailable", "failed"]).sum()) if not fetch.empty else 0, "failed rows"),
        ("empty_result rows", int(fetch["fetch_status"].eq("empty_result").sum()) if not fetch.empty else 0, "empty rows"),
        ("raw baidu valuation rows", int(fetch["row_count"].sum()) if not fetch.empty else 0, "raw rows"),
        ("structured baidu rows", len(structured), "structured rows"),
        ("standard watchlist asset count", int(structured["asset_id"].nunique()) if not structured.empty else 0, "asset count"),
        ("assets with baidu support", int(structured["valuation_data_status"].eq("baidu_pe_pb_market_cap_available").sum()) if not structured.empty else 0, "support rows"),
        ("baidu coverage ratio", round(float(structured["valuation_data_status"].eq("baidu_pe_pb_market_cap_available").mean()), 6) if len(structured) else 0.0, "support ratio"),
        ("PIT valid ratio", round(float(structured["is_pit_valid"].fillna(False).astype(bool).mean()), 6) if len(structured) else 0.0, "PIT ratio"),
        ("lookahead violation rows", int(structured["lookahead_violation"].fillna(False).astype(bool).sum()) if len(structured) else 0, "must be zero"),
        ("assets with baidu_pe_ttm", int(structured["baidu_pe_ttm"].notna().sum()) if len(structured) else 0, "field coverage"),
        ("assets with baidu_pb", int(structured["baidu_pb"].notna().sum()) if len(structured) else 0, "field coverage"),
        ("assets with baidu_total_mv", int(structured["baidu_total_mv"].notna().sum()) if len(structured) else 0, "field coverage"),
        ("assets with baidu_pcf", int(structured["baidu_pcf"].notna().sum()) if len(structured) else 0, "field coverage"),
        ("assets with baidu_ps_ttm", 0, "Baidu source does not validate PS/PS-TTM"),
        ("cross_validation comparable rows", int(cross["validation_status"].isin(["consistent", "minor_difference", "material_difference"]).sum()) if len(cross) else 0, "comparable rows"),
        ("cross_validation consistent rows", int(cross["validation_status"].eq("consistent").sum()) if len(cross) else 0, "status"),
        ("cross_validation minor_difference rows", int(cross["validation_status"].eq("minor_difference").sum()) if len(cross) else 0, "status"),
        ("cross_validation material_difference rows", int(cross["validation_status"].eq("material_difference").sum()) if len(cross) else 0, "status"),
        ("cross_validation date_gap_too_large rows", int(cross["validation_status"].eq("date_gap_too_large").sum()) if len(cross) else 0, "status"),
        ("degraded rows", int(structured["data_quality_status"].astype(str).str.contains("degraded", regex=False).sum()) if len(structured) else 0, "degraded rows"),
        ("invalid rows", int(structured["lookahead_violation"].fillna(False).astype(bool).sum()) if len(structured) else 0, "invalid rows"),
    ]
    return pd.DataFrame(rows, columns=AUDIT_COLUMNS)


def _git_info(project_root: Path = PROJECT_ROOT) -> dict[str, str]:
    def run(args: list[str]) -> str:
        try:
            return subprocess.check_output(args, cwd=project_root, text=True, stderr=subprocess.STDOUT).strip()
        except Exception as exc:  # noqa: BLE001
            return f"unavailable: {exc}"

    status = run(["git", "status", "--short", "src/stock_research/tech_bottleneck_v1.py", "src/stock_research/tech_bottleneck_candidates.py"])
    return {"repo_root": run(["git", "rev-parse", "--show-toplevel"]), "formal_strategy_status": status or "clean_tracked_or_absent"}


def render_report(inventory: pd.DataFrame, audit: pd.DataFrame, git_info: dict[str, str]) -> str:
    lookup = dict(zip(audit["metric"], audit["value"]))
    return f"""# Tech Bottleneck AKShare Baidu Valuation Probe v1

## 1. Executive Summary

- AKShare package available: {lookup.get("akshare_package_available")}; version: {lookup.get("akshare_package_version")}.
- `stock_zh_valuation_baidu` exists: {lookup.get("target_function_exists")}.
- Sample call success: {lookup.get("sample_call_success")}.
- Fetch success rows: {lookup.get("fetch success rows")}; structured Baidu rows: {lookup.get("structured baidu rows")}.
- Baidu PE/PB/market cap support: {lookup.get("assets with baidu support")} / {lookup.get("standard watchlist asset count")}.
- Baidu does not validate PS/PS-TTM in this probe.
- BaoStock comparable rows: {lookup.get("cross_validation comparable rows")}.
- consistent / minor / material: {lookup.get("cross_validation consistent rows")} / {lookup.get("cross_validation minor_difference rows")} / {lookup.get("cross_validation material_difference rows")}.
- BaoStock remains primary; Baidu is auxiliary validation only.
- This probe creates no automated execution prompt and does not modify formal strategy files.

## 2. Source Inventory

The target function is `stock_zh_valuation_baidu`. Indicators probed: {", ".join(BAIDU_INDICATORS)}.

## 3. Probe Plan

The plan covers 102 standard watchlist assets times five indicators. Each asset-indicator pair has its own cache path.

## 4. Fetch Results

Fetch results record success, cached reuse, empty results, API errors, and network failures per indicator.

## 5. Structured Baidu Outputs

Structured rows include PE-TTM, static PE, PB, PCF, and market cap context. Baidu does not validate PS/PS-TTM.

## 6. BaoStock Cross Validation

Baidu is validation-only. Differences do not automatically override BaoStock. Material discrepancies require review or third-source validation.

## 7. Data Quality and Limitations

AKShare web endpoints may change. Baidu indicator definitions and units require review before using them in consolidated reports.

## 8. Recommended Usage

Keep BaoStock as primary. Use Baidu as auxiliary PE/PB/market-cap validation when available. Do not use this probe for automated execution.

## 9. What This Probe Does Not Do

- No automated execution prompt is produced.
- It does not change Top5.
- It does not change formal strategy files.
- It does not study trigger / holding / exit.
- It does not use evidence multiplier.
- It does not automatically replace BaoStock.

## 10. Recommended Next Step

If Baidu validation is usable, next task: `tech_bottleneck_watchlist_report_consolidated_v1`. If discrepancies are high, consider `tech_bottleneck_akshare_baidu_cross_validation_patch_v1`.

## 11. Appendix

- generated files: source inventory, probe plan, fetch results, structured outputs, cross validation, field coverage audit, quality audit, Markdown report.
- git repo root: `{git_info.get("repo_root")}`.
- formal strategy file status: `{git_info.get("formal_strategy_status")}`.
- 如果正式策略文件仍是 untracked，无法仅靠 `git diff` 完整证明历史未变更；本任务没有写入这些文件。
"""


def write_outputs(output_dir: Path = OUTPUT_DIR) -> dict[str, pd.DataFrame]:
    output_dir.mkdir(parents=True, exist_ok=True)
    watchlist = load_watchlist_assets()
    inventory = inspect_baidu_source()
    target = TARGET_FUNCTION if bool(inventory.loc[0, "function_exists"]) else "missing"
    plan = build_probe_plan(watchlist, output_dir, target_function=target)
    fetch = fetch_baidu_valuation(plan, output_dir, inventory)
    research_date = infer_research_trade_date()
    structured = build_structured_outputs(watchlist, fetch, research_trade_date=research_date)
    baostock = pd.read_csv(BAOSTOCK_DIR / "baostock_structured_outputs.csv")
    cross = build_cross_validation(structured, baostock)
    field_audit = build_field_coverage_audit(structured, cross)
    audit = build_quality_audit(inventory, plan, fetch, structured, cross)
    report = render_report(inventory, audit, _git_info(PROJECT_ROOT))
    outputs = {
        "akshare_baidu_source_inventory.csv": inventory,
        "akshare_baidu_probe_plan.csv": plan,
        "akshare_baidu_fetch_results.csv": fetch,
        "akshare_baidu_structured_outputs.csv": structured,
        "akshare_baidu_baostock_cross_validation.csv": cross,
        "akshare_baidu_field_coverage_audit.csv": field_audit,
        "akshare_baidu_quality_audit.csv": audit,
    }
    for name, frame in outputs.items():
        frame.to_csv(output_dir / name, index=False)
    (output_dir / "akshare_baidu_valuation_probe_v1.md").write_text(report, encoding="utf-8")
    return outputs


def main() -> None:
    outputs = write_outputs(OUTPUT_DIR)
    audit = outputs["akshare_baidu_quality_audit.csv"]
    print(audit.to_string(index=False))
    joined = "\n".join(path.read_text(errors="ignore") for path in OUTPUT_DIR.rglob("*") if path.is_file())
    if contains_actionable_trading_language(joined):
        raise SystemExit("forbidden output language detected")


if __name__ == "__main__":
    main()
