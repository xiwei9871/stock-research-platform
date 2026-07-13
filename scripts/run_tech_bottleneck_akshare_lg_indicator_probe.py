#!/usr/bin/env python3
from __future__ import annotations

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
WATCHLIST_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_research_input_watchlist_forward_return_v1"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_akshare_lg_indicator_probe_v1"
RULE_VERSION = "tech_bottleneck_akshare_lg_indicator_probe_v1"

TARGET_FIELDS = "trade_date,pe,pe_ttm,pb,ps,ps_ttm,dv_ratio,dv_ttm,total_mv"
CANDIDATE_FUNCTIONS = ["stock_a_indicator_lg", "stock_a_lg_indicator"]

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
    "probe_required",
    "target_function",
    "target_fields",
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
    "akshare_trade_date",
    "source_type",
    "is_pit_valid",
    "lookahead_violation",
    "pe",
    "pe_ttm",
    "pb",
    "ps",
    "ps_ttm",
    "dv_ratio",
    "dv_ttm",
    "total_mv",
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
    "akshare_trade_date",
    "date_gap_days",
    "baostock_pe_ttm",
    "akshare_pe_ttm",
    "pe_ttm_abs_diff",
    "pe_ttm_pct_diff",
    "baostock_pb",
    "akshare_pb",
    "pb_abs_diff",
    "pb_pct_diff",
    "baostock_ps_ttm",
    "akshare_ps_ttm",
    "ps_ttm_abs_diff",
    "ps_ttm_pct_diff",
    "baostock_total_mv",
    "akshare_total_mv",
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
    import hashlib

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


def _candidate_names(ak_module: Any) -> list[str]:
    return [name for name in dir(ak_module) if any(token in name.lower() for token in ["lg", "indicator", "valuation"]) and "stock" in name.lower()]


def inspect_akshare_source(
    *,
    importer: Callable[[], Any] | None = None,
    ak_module: Any | None = None,
    sample_symbol: str = "600000",
) -> pd.DataFrame:
    package_available = False
    version = "missing"
    target = "missing"
    function_exists = False
    sample_success = False
    sample_error = ""
    fields = "missing"
    notes = ""
    try:
        module = ak_module if ak_module is not None else (importer() if importer else importlib.import_module("akshare"))
        package_available = True
        version = getattr(module, "__version__", "unknown")
        for name in CANDIDATE_FUNCTIONS:
            if hasattr(module, name):
                target = name
                function_exists = True
                break
        if not function_exists:
            candidates = _candidate_names(module)
            notes = "stock candidate functions: " + ("|".join(candidates[:40]) if candidates else "none")
        else:
            try:
                sample = getattr(module, target)(symbol=sample_symbol)
                sample_success = isinstance(sample, pd.DataFrame) and not sample.empty
                fields = "|".join(map(str, sample.columns)) if isinstance(sample, pd.DataFrame) else "not_dataframe"
                if not sample_success:
                    sample_error = "empty_or_not_dataframe"
            except Exception as exc:  # noqa: BLE001
                sample_error = str(exc)[:500]
    except Exception as exc:  # noqa: BLE001
        sample_error = str(exc)[:500]
    quality = "usable" if package_available and function_exists and sample_success else "package_missing_or_function_missing_or_sample_failed"
    if not package_available:
        quality = "package_missing"
    row = {
        "source_name": "AKShare",
        "source_type": "akshare_lg_indicator_probe",
        "package_available": package_available,
        "package_version": version,
        "candidate_function_name": target,
        "function_exists": function_exists,
        "available_fields_from_sample": fields,
        "sample_call_success": sample_success,
        "sample_call_error": sample_error,
        "pit_ready": bool(package_available and function_exists and sample_success),
        "coverage_estimate": "to_be_verified_by_probe" if function_exists else "target_function_missing",
        "quality_risk": quality,
        "notes": notes or "AKShare is validation-only; BaoStock remains primary.",
    }
    frame = pd.DataFrame([row], columns=SOURCE_INVENTORY_COLUMNS)
    for col in ["package_available", "function_exists", "sample_call_success", "pit_ready"]:
        frame[col] = frame[col].astype(object)
    return frame


def load_watchlist_assets() -> pd.DataFrame:
    path = BAOSTOCK_PATCH_DIR / "watchlist_baostock_valuation_patch_summary_by_asset.csv"
    if path.exists():
        frame = pd.read_csv(path)
        return frame[["asset_id", "symbol", "name"]].drop_duplicates("asset_id").reset_index(drop=True)
    admission = WATCHLIST_DIR / "watchlist_admission_events.csv"
    frame = pd.read_csv(admission)
    frame = frame[frame["admission_variant"].eq("standard_research_watchlist")].copy()
    frame["symbol"] = frame.apply(lambda row: _safe_symbol(row["asset_id"], row.get("symbol", "")), axis=1)
    return frame[["asset_id", "symbol", "name"]].drop_duplicates("asset_id").reset_index(drop=True)


def _baostock_code(asset_id: str) -> str:
    _, exchange, symbol = str(asset_id).split(":")
    return f"{exchange.lower()}.{symbol}"


def build_probe_plan(watchlist: pd.DataFrame, output_dir: Path = OUTPUT_DIR, *, target_function: str = "missing") -> pd.DataFrame:
    rows = []
    for _, row in watchlist.iterrows():
        asset_id = str(row["asset_id"])
        symbol = _safe_symbol(asset_id, row.get("symbol", ""))
        cache_path = output_dir / "cache/akshare/lg_indicator" / f"{symbol}.csv"
        rows.append(
            {
                "asset_id": asset_id,
                "symbol": symbol,
                "name": row.get("name", ""),
                "akshare_symbol": symbol,
                "baostock_code": _baostock_code(asset_id),
                "probe_required": not cache_path.exists() and target_function != "missing",
                "target_function": target_function,
                "target_fields": TARGET_FIELDS,
                "cache_path": str(cache_path),
                "probe_status": "success_cached" if cache_path.exists() else "planned",
                "skip_reason": "cache_exists" if cache_path.exists() else ("function_missing" if target_function == "missing" else ""),
                "human_review_required": True,
            }
        )
    frame = pd.DataFrame(rows, columns=PROBE_PLAN_COLUMNS)
    if not frame.empty:
        for col in ["probe_required", "human_review_required"]:
            frame[col] = frame[col].map(bool).astype(object)
    return frame


def fetch_akshare_lg(
    plan: pd.DataFrame,
    output_dir: Path,
    inventory: pd.DataFrame,
    *,
    ak_module: Any | None = None,
    importer: Callable[[], Any] | None = None,
    stop_after_asset_count: int | None = None,
) -> pd.DataFrame:
    inv = inventory.iloc[0] if not inventory.empty else {}
    package_available = bool(inv.get("package_available", False))
    function_exists = bool(inv.get("function_exists", False))
    target = str(inv.get("candidate_function_name", "missing"))
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
        if not function_exists or module is None or not hasattr(module, target):
            rows.append(_fetch_result(row, False, "function_missing", 0, 0, "", cache_path, "target function missing", time.perf_counter() - start))
            continue
        if stop_after_asset_count is not None and attempted >= stop_after_asset_count:
            rows.append(_fetch_result(row, False, "skipped", 0, 0, "", cache_path, "skipped_after_asset_limit", time.perf_counter() - start))
            continue
        try:
            attempted += 1
            data = getattr(module, target)(symbol=str(row["akshare_symbol"]))
            if not isinstance(data, pd.DataFrame) or data.empty:
                rows.append(_fetch_result(row, True, "empty_result", 0, 0, "", cache_path, "empty_or_not_dataframe", time.perf_counter() - start))
                continue
            content_hash = _write_frame(data, cache_path)
            rows.append(_fetch_result(row, True, "success", len(data), len(data.columns), "|".join(map(str, data.columns)), cache_path, "", time.perf_counter() - start, content_hash))
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


def _normalize_columns(frame: pd.DataFrame) -> pd.DataFrame:
    mapping = {
        "日期": "trade_date",
        "date": "trade_date",
        "tradeDate": "trade_date",
        "市盈率": "pe",
        "市盈率(TTM)": "pe_ttm",
        "peTTM": "pe_ttm",
        "市净率": "pb",
        "市销率": "ps",
        "市销率(TTM)": "ps_ttm",
        "psTTM": "ps_ttm",
        "股息率": "dv_ratio",
        "股息率(TTM)": "dv_ttm",
        "总市值": "total_mv",
    }
    out = frame.copy()
    out.columns = [mapping.get(str(col), str(col)) for col in out.columns]
    return out


def build_structured_outputs(watchlist: pd.DataFrame, fetch_results: pd.DataFrame, *, research_trade_date: str) -> pd.DataFrame:
    rows = []
    research_date = pd.to_datetime(research_trade_date)
    fetch_lookup = fetch_results.set_index("asset_id").to_dict("index") if not fetch_results.empty else {}
    for _, stock in watchlist.iterrows():
        asset_id = stock["asset_id"]
        result = fetch_lookup.get(asset_id, {})
        cache_path = Path(str(result.get("cache_path", "")))
        if result.get("fetch_status") not in {"success", "success_cached"} or not cache_path.exists():
            rows.append(_missing_structured_row(stock, research_trade_date))
            continue
        data = _normalize_columns(pd.read_csv(cache_path))
        if "trade_date" not in data.columns:
            rows.append(_missing_structured_row(stock, research_trade_date, "missing_trade_date"))
            continue
        data = data.copy()
        data["trade_dt"] = pd.to_datetime(data["trade_date"], errors="coerce")
        eligible = data[data["trade_dt"].le(research_date)]
        if eligible.empty:
            rows.append(_missing_structured_row(stock, research_trade_date, "no_pit_eligible_row"))
            continue
        latest = eligible.sort_values("trade_dt").iloc[-1]
        lookahead = bool(pd.to_datetime(latest["trade_date"]) > research_date)
        missing = [field for field in ["pe_ttm", "pb", "ps_ttm", "total_mv"] if field not in latest.index or pd.isna(latest.get(field))]
        pe_ttm = _as_float(latest.get("pe_ttm"))
        rows.append(
            {
                "research_trade_date": research_trade_date,
                "asset_id": asset_id,
                "symbol": stock["symbol"],
                "name": stock["name"],
                "akshare_symbol": str(stock["symbol"]).zfill(6),
                "akshare_trade_date": str(pd.to_datetime(latest["trade_date"]).date()),
                "source_type": "akshare_lg_indicator",
                "is_pit_valid": not lookahead,
                "lookahead_violation": lookahead,
                "pe": _as_float(latest.get("pe")),
                "pe_ttm": pe_ttm,
                "pb": _as_float(latest.get("pb")),
                "ps": _as_float(latest.get("ps")),
                "ps_ttm": _as_float(latest.get("ps_ttm")),
                "dv_ratio": _as_float(latest.get("dv_ratio")),
                "dv_ttm": _as_float(latest.get("dv_ttm")),
                "total_mv": _as_float(latest.get("total_mv")),
                "valuation_data_status": "akshare_lg_available" if not missing else "degraded_missing_fields",
                "missing_fields": "|".join(missing) if missing else "none",
                "conflict_flags": "negative_pe_not_low" if pe_ttm is not None and pe_ttm <= 0 else "none",
                "data_quality_status": "pit_valid" if not lookahead and not missing else "degraded_missing_optional_fields",
                "rule_version": RULE_VERSION,
            }
        )
    return pd.DataFrame(rows, columns=STRUCTURED_COLUMNS)


def _missing_structured_row(stock: pd.Series, research_trade_date: str, status: str = "akshare_missing") -> dict[str, Any]:
    return {
        "research_trade_date": research_trade_date,
        "asset_id": stock["asset_id"],
        "symbol": stock["symbol"],
        "name": stock["name"],
        "akshare_symbol": str(stock["symbol"]).zfill(6),
        "akshare_trade_date": "missing",
        "source_type": "akshare_lg_indicator",
        "is_pit_valid": False,
        "lookahead_violation": False,
        "pe": float("nan"),
        "pe_ttm": float("nan"),
        "pb": float("nan"),
        "ps": float("nan"),
        "ps_ttm": float("nan"),
        "dv_ratio": float("nan"),
        "dv_ttm": float("nan"),
        "total_mv": float("nan"),
        "valuation_data_status": status,
        "missing_fields": "pe_ttm|pb|ps_ttm|total_mv",
        "conflict_flags": "none",
        "data_quality_status": "degraded_akshare_unavailable",
        "rule_version": RULE_VERSION,
    }


def _diff(baostock: Any, akshare: Any) -> tuple[Any, Any]:
    b = _as_float(baostock)
    a = _as_float(akshare)
    if b is None or a is None:
        return float("nan"), float("nan")
    abs_diff = abs(a - b)
    pct = abs_diff / abs(b) if b != 0 else float("nan")
    return round(abs_diff, 6), round(pct, 6) if pd.notna(pct) else float("nan")


def _validation_status(pcts: list[float], date_gap: int | None, ak_missing: bool, bao_missing: bool) -> str:
    if ak_missing:
        return "akshare_missing"
    if bao_missing:
        return "baostock_missing"
    if date_gap is not None and date_gap > 5:
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


def build_cross_validation(akshare_structured: pd.DataFrame, baostock_structured: pd.DataFrame) -> pd.DataFrame:
    rows = []
    baostock_lookup = baostock_structured.set_index("asset_id").to_dict("index") if not baostock_structured.empty else {}
    for _, ak in akshare_structured.iterrows():
        b = baostock_lookup.get(ak["asset_id"], {})
        ak_missing = str(ak.get("akshare_trade_date")) == "missing"
        bao_missing = not bool(b)
        if ak_missing or bao_missing:
            date_gap = None
        else:
            date_gap = abs((pd.to_datetime(ak["akshare_trade_date"]) - pd.to_datetime(b.get("baostock_date"))).days)
        pe_abs, pe_pct = _diff(b.get("pe_ttm"), ak.get("pe_ttm"))
        pb_abs, pb_pct = _diff(b.get("pb"), ak.get("pb"))
        ps_abs, ps_pct = _diff(b.get("ps_ttm"), ak.get("ps_ttm"))
        mv_abs, mv_pct = _diff(b.get("amount"), ak.get("total_mv"))
        status = _validation_status([pe_pct, pb_pct, ps_pct], date_gap, ak_missing, bao_missing)
        flags = ["no_auto_override"]
        if status == "material_difference":
            flags.append("material_difference_review_required")
        if status == "date_gap_too_large":
            flags.append("date_gap_too_large")
        action = {
            "consistent": "keep_baostock_primary",
            "minor_difference": "review_discrepancy",
            "material_difference": "review_discrepancy",
            "akshare_missing": "akshare_unavailable",
            "baostock_missing": "not_comparable",
            "not_comparable": "not_comparable",
            "date_gap_too_large": "request_third_source_validation",
        }.get(status, "not_comparable")
        rows.append(
            {
                "asset_id": ak["asset_id"],
                "symbol": ak["symbol"],
                "name": ak["name"],
                "research_trade_date": ak["research_trade_date"],
                "baostock_date": b.get("baostock_date", "missing"),
                "akshare_trade_date": ak.get("akshare_trade_date", "missing"),
                "date_gap_days": date_gap if date_gap is not None else "missing",
                "baostock_pe_ttm": b.get("pe_ttm"),
                "akshare_pe_ttm": ak.get("pe_ttm"),
                "pe_ttm_abs_diff": pe_abs,
                "pe_ttm_pct_diff": pe_pct,
                "baostock_pb": b.get("pb"),
                "akshare_pb": ak.get("pb"),
                "pb_abs_diff": pb_abs,
                "pb_pct_diff": pb_pct,
                "baostock_ps_ttm": b.get("ps_ttm"),
                "akshare_ps_ttm": ak.get("ps_ttm"),
                "ps_ttm_abs_diff": ps_abs,
                "ps_ttm_pct_diff": ps_pct,
                "baostock_total_mv": b.get("amount"),
                "akshare_total_mv": ak.get("total_mv"),
                "total_mv_abs_diff": mv_abs,
                "total_mv_pct_diff": mv_pct,
                "validation_status": status,
                "discrepancy_flags": "|".join(flags),
                "recommended_action": action,
            }
        )
    return pd.DataFrame(rows, columns=CROSS_VALIDATION_COLUMNS)


def build_field_coverage_audit(structured: pd.DataFrame, cross: pd.DataFrame) -> pd.DataFrame:
    fields = ["pe", "pe_ttm", "pb", "ps", "ps_ttm", "dv_ratio", "dv_ttm", "total_mv", "akshare_trade_date"]
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
        ("target_function_exists", bool(inv.get("function_exists", False)), "LG target function status"),
        ("sample_call_success", bool(inv.get("sample_call_success", False)), "sample call status"),
        ("probe plan rows", len(plan), "standard watchlist assets"),
        ("fetch attempted rows", int(fetch["fetch_attempted"].fillna(False).astype(bool).sum()) if not fetch.empty else 0, "attempted calls"),
        ("fetch success rows", int(fetch["fetch_status"].eq("success").sum()) if not fetch.empty else 0, "new source rows"),
        ("fetch success_cached rows", int(fetch["fetch_status"].eq("success_cached").sum()) if not fetch.empty else 0, "cached source rows"),
        ("fetch failed rows", int(fetch["fetch_status"].isin(["package_missing", "function_missing", "api_error", "network_unavailable", "failed"]).sum()) if not fetch.empty else 0, "failed rows"),
        ("empty_result rows", int(fetch["fetch_status"].eq("empty_result").sum()) if not fetch.empty else 0, "empty rows"),
        ("raw akshare rows", int(fetch["row_count"].sum()) if not fetch.empty else 0, "raw rows"),
        ("structured akshare rows", len(structured), "structured rows"),
        ("standard watchlist asset count", len(plan), "asset count"),
        ("assets with akshare support", int(structured["valuation_data_status"].eq("akshare_lg_available").sum()) if not structured.empty else 0, "support rows"),
        ("akshare coverage ratio", round(float(structured["valuation_data_status"].eq("akshare_lg_available").mean()), 6) if len(structured) else 0.0, "support ratio"),
        ("PIT valid ratio", round(float(structured["is_pit_valid"].fillna(False).astype(bool).mean()), 6) if len(structured) else 0.0, "PIT ratio"),
        ("lookahead violation rows", int(structured["lookahead_violation"].fillna(False).astype(bool).sum()) if len(structured) else 0, "must be zero"),
        ("assets with pe_ttm", int(structured["pe_ttm"].notna().sum()) if len(structured) else 0, "field coverage"),
        ("assets with pb", int(structured["pb"].notna().sum()) if len(structured) else 0, "field coverage"),
        ("assets with ps_ttm", int(structured["ps_ttm"].notna().sum()) if len(structured) else 0, "field coverage"),
        ("assets with total_mv", int(structured["total_mv"].notna().sum()) if len(structured) else 0, "field coverage"),
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
    inv = inventory.iloc[0].to_dict() if not inventory.empty else {}
    return f"""# Tech Bottleneck AKShare LG Indicator Probe v1

## 1. Executive Summary

- AKShare package available: {lookup.get("akshare_package_available")}; version: {lookup.get("akshare_package_version")}.
- Target function exists: {lookup.get("target_function_exists")}; candidate function: {inv.get("candidate_function_name")}.
- Sample call success: {lookup.get("sample_call_success")}.
- Fetch success rows: {lookup.get("fetch success rows")}; structured AKShare rows: {lookup.get("structured akshare rows")}.
- AKShare PE/PB/PS support coverage: {lookup.get("assets with akshare support")} / {lookup.get("standard watchlist asset count")}.
- BaoStock comparable rows: {lookup.get("cross_validation comparable rows")}.
- consistent / minor / material: {lookup.get("cross_validation consistent rows")} / {lookup.get("cross_validation minor_difference rows")} / {lookup.get("cross_validation material_difference rows")}.
- BaoStock remains the primary valuation source; AKShare is validation-only in this probe.
- This probe creates no automated execution prompt and does not modify formal strategy files.

## 2. Source Inventory

Candidate functions checked: `stock_a_indicator_lg`, `stock_a_lg_indicator`. If both are missing, candidate names from `dir(akshare)` are recorded in `notes`.

## 3. Probe Plan

The plan maps 102 standard watchlist assets to six-digit AKShare symbols and per-asset cache paths.

## 4. Fetch Results

Fetch status is recorded per asset. Missing package, missing function, API errors, and empty results degrade outputs without stopping the task.

## 5. Structured AKShare Outputs

Structured rows select only `akshare_trade_date <= research_trade_date`. Negative or missing PE is not interpreted as low valuation.

## 6. BaoStock Cross Validation

AKShare only validates BaoStock. Differences never automatically override BaoStock. Material discrepancy rows are marked for review or third-source validation.

## 7. Data Quality and Limitations

AKShare web interfaces can be renamed or removed. Current target function status is `{lookup.get("target_function_exists")}`. If unavailable, use BaoStock primary and consider a Baidu / Eastmoney / Tushare fallback probe.

## 8. Recommended Usage

Keep BaoStock as primary. Use AKShare only when the target interface is available and comparable. Large differences require manual review.

## 9. What This Probe Does Not Do

- No automated execution prompt is produced.
- It does not change Top5.
- It does not change formal strategy files.
- It does not study trigger / holding / exit.
- It does not use evidence multiplier.
- It does not automatically replace BaoStock.

## 10. Recommended Next Step

If AKShare LG remains unavailable, use `tech_bottleneck_watchlist_report_consolidated_v1` with BaoStock primary plus AKShare unavailable status, or start `tech_bottleneck_akshare_baidu_valuation_probe_v1`.

## 11. Appendix

- generated files: source inventory, probe plan, fetch results, structured outputs, cross validation, field coverage audit, quality audit, Markdown report.
- git repo root: `{git_info.get("repo_root")}`.
- formal strategy file status: `{git_info.get("formal_strategy_status")}`.
- 如果正式策略文件仍是 untracked，无法仅靠 `git diff` 完整证明历史未变更；本任务没有写入这些文件。
"""


def infer_research_trade_date() -> str:
    path = BAOSTOCK_DIR / "baostock_structured_outputs.csv"
    if path.exists():
        frame = pd.read_csv(path)
        dates = pd.to_datetime(frame["research_trade_date"], errors="coerce")
        if dates.notna().any():
            return str(dates.max().date())
    return str(pd.Timestamp.now(tz="Asia/Shanghai").date())


def write_outputs(output_dir: Path = OUTPUT_DIR) -> dict[str, pd.DataFrame]:
    output_dir.mkdir(parents=True, exist_ok=True)
    watchlist = load_watchlist_assets()
    inventory = inspect_akshare_source()
    target = str(inventory.loc[0, "candidate_function_name"]) if not inventory.empty else "missing"
    plan = build_probe_plan(watchlist, output_dir, target_function=target)
    fetch = fetch_akshare_lg(plan, output_dir, inventory)
    research_date = infer_research_trade_date()
    structured = build_structured_outputs(watchlist, fetch, research_trade_date=research_date)
    baostock_path = BAOSTOCK_DIR / "baostock_structured_outputs.csv"
    baostock = pd.read_csv(baostock_path) if baostock_path.exists() else pd.DataFrame()
    cross = build_cross_validation(structured, baostock)
    field_audit = build_field_coverage_audit(structured, cross)
    audit = build_quality_audit(inventory, plan, fetch, structured, cross)
    report = render_report(inventory, audit, _git_info(PROJECT_ROOT))
    outputs = {
        "akshare_lg_source_inventory.csv": inventory,
        "akshare_lg_probe_plan.csv": plan,
        "akshare_lg_fetch_results.csv": fetch,
        "akshare_lg_structured_outputs.csv": structured,
        "akshare_lg_baostock_cross_validation.csv": cross,
        "akshare_lg_field_coverage_audit.csv": field_audit,
        "akshare_lg_quality_audit.csv": audit,
    }
    for name, frame in outputs.items():
        frame.to_csv(output_dir / name, index=False)
    (output_dir / "akshare_lg_indicator_probe_v1.md").write_text(report, encoding="utf-8")
    return outputs


def main() -> None:
    outputs = write_outputs(OUTPUT_DIR)
    audit = outputs["akshare_lg_quality_audit.csv"]
    print(audit.to_string(index=False))
    joined = "\n".join(path.read_text(errors="ignore") for path in OUTPUT_DIR.rglob("*") if path.is_file())
    if contains_actionable_trading_language(joined):
        raise SystemExit("forbidden output language detected")


if __name__ == "__main__":
    main()
