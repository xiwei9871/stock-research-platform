import argparse
import hashlib
import importlib
import re
import subprocess
import time
from pathlib import Path
from typing import Any, Callable

import pandas as pd


RULE_VERSION = "tech_bottleneck_baostock_pe_pb_ps_source_adapter_v1"
PROJECT_ROOT = Path("/Users/xiwei/stock_research")
WATCHLIST_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_research_input_watchlist_forward_return_v1"
VALUATION_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_valuation_source_adapter_v1"
FUNDAMENTAL_PATCH_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_watchlist_report_fundamental_patch_v1"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_baostock_pe_pb_ps_source_adapter_v1"

BAOSTOCK_FIELDS = "date,code,open,high,low,close,volume,amount,turn,tradestatus,pctChg,peTTM,pbMRQ,psTTM,pcfNcfTTM,isST"

FORBIDDEN_PATTERNS = [
    re.compile(r"\b(?:buy|sell|add|reduce|hold|target_price|position_size|entry_signal|exit_signal)\b", re.I),
    re.compile(r"买入|卖出|加仓|减仓|持有|目标价|仓位建议|入场点|止损点|交易信号"),
]

SOURCE_INVENTORY_COLUMNS = [
    "source_name",
    "source_type",
    "package_available",
    "package_version",
    "login_success",
    "login_error",
    "available_api",
    "available_fields",
    "pit_ready",
    "coverage_estimate",
    "quality_risk",
    "notes",
]

FETCH_PLAN_COLUMNS = [
    "asset_id",
    "symbol",
    "name",
    "baostock_code",
    "start_date",
    "end_date",
    "fetch_required",
    "target_fields",
    "expected_pit_use",
    "cache_path",
    "fetch_status",
    "skip_reason",
    "human_review_required",
]

FETCH_RESULT_COLUMNS = [
    "asset_id",
    "symbol",
    "name",
    "baostock_code",
    "fetch_attempted",
    "fetch_status",
    "row_count",
    "field_count",
    "cache_path",
    "content_hash",
    "api_error",
    "elapsed_seconds",
    "data_quality_status",
]

RAW_MATCH_COLUMNS = [
    "asset_id",
    "symbol",
    "name",
    "baostock_code",
    "baostock_date",
    "source_name",
    "matched_by",
    "is_pit_valid",
    "lookahead_violation",
    "available_field_count",
    "missing_required_fields",
    "data_quality_status",
]

STRUCTURED_COLUMNS = [
    "research_trade_date",
    "asset_id",
    "symbol",
    "name",
    "baostock_code",
    "baostock_date",
    "source_type",
    "is_pit_valid",
    "lookahead_violation",
    "pe_ttm",
    "pb",
    "ps_ttm",
    "pcf_ncf_ttm",
    "turnover_rate",
    "tradestatus",
    "is_st",
    "close",
    "amount",
    "valuation_data_status",
    "missing_fields",
    "conflict_flags",
    "data_quality_status",
    "rule_version",
]

PERCENTILE_COLUMNS = [
    "research_trade_date",
    "asset_id",
    "symbol",
    "name",
    "baostock_code",
    "baostock_date",
    "pe_ttm",
    "pb",
    "ps_ttm",
    "pcf_ncf_ttm",
    "pe_ttm_percentile_1y",
    "pe_ttm_percentile_3y",
    "pe_ttm_percentile_5y",
    "pb_percentile_1y",
    "pb_percentile_3y",
    "pb_percentile_5y",
    "ps_ttm_percentile_1y",
    "ps_ttm_percentile_3y",
    "ps_ttm_percentile_5y",
    "history_window_days_available",
    "history_window_quality",
    "percentile_data_status",
    "missing_fields",
]

ASSET_COVERAGE_COLUMNS = [
    "asset_id",
    "symbol",
    "name",
    "baostock_code",
    "in_standard_watchlist",
    "baostock_record_count",
    "pit_valid_record_count",
    "latest_baostock_date",
    "has_pe_ttm",
    "has_pb",
    "has_ps_ttm",
    "has_pcf_ncf_ttm",
    "has_turnover_rate",
    "has_tradestatus",
    "has_is_st",
    "has_1y_percentile",
    "has_3y_percentile",
    "has_5y_percentile",
    "valuation_support_level",
    "coverage_status",
    "human_review_required",
]

FIELD_AUDIT_COLUMNS = ["field_name", "non_missing_count", "missing_count", "coverage_ratio", "quality_note"]

GAP_PATCH_COLUMNS = [
    "asset_id",
    "symbol",
    "name",
    "previous_valuation_support",
    "new_baostock_support",
    "baostock_record_count",
    "latest_baostock_date",
    "pe_ttm",
    "pb",
    "ps_ttm",
    "pcf_ncf_ttm",
    "pe_ttm_percentile_3y",
    "pb_percentile_3y",
    "ps_ttm_percentile_3y",
    "valuation_support_level",
    "new_source_count_delta",
    "new_evidence_tags",
    "new_risk_flags",
    "report_patch_summary",
    "still_missing_baostock_valuation",
    "recommended_report_update",
    "human_review_required",
]

AUDIT_COLUMNS = ["metric", "value", "note"]


def contains_actionable_trading_language(text: str) -> bool:
    return any(pattern.search(str(text)) for pattern in FORBIDDEN_PATTERNS)


def _empty(columns: list[str]) -> pd.DataFrame:
    return pd.DataFrame(columns=columns)


def _now_date() -> str:
    return str(pd.Timestamp.now(tz="Asia/Shanghai").date())


def _sha256_file(path: Path) -> str:
    if not path.exists():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _safe_symbol(asset_id: str, symbol: Any = "") -> str:
    parts = str(asset_id).split(":")
    if len(parts) == 3:
        return parts[2]
    text = str(symbol)
    return text.zfill(6) if text.isdigit() else text


def asset_id_to_baostock_code(asset_id: str) -> str:
    market, exchange, symbol = str(asset_id).split(":")
    if market != "CN":
        raise ValueError(f"unsupported market for BaoStock: {asset_id}")
    exchange_lower = exchange.lower()
    if exchange_lower not in {"sh", "sz"}:
        raise ValueError(f"unsupported exchange for BaoStock: {asset_id}")
    return f"{exchange_lower}.{symbol}"


def inspect_baostock_source(
    *,
    importer: Callable[[], Any] | None = None,
    client: Any | None = None,
) -> pd.DataFrame:
    package = None
    package_available = False
    package_version = "missing"
    login_success = False
    login_error = ""
    if client is not None:
        package_available = True
        package_version = getattr(client, "__version__", "client_injected")
        try:
            login_result = client.login()
            login_success = str(getattr(login_result, "error_code", "0")) == "0"
            login_error = str(getattr(login_result, "error_msg", ""))
        except Exception as exc:  # noqa: BLE001
            login_error = str(exc)[:300]
    else:
        try:
            package = importer() if importer else importlib.import_module("baostock")
            package_available = True
            package_version = getattr(package, "__version__", "unknown")
            login_result = package.login()
            login_success = str(getattr(login_result, "error_code", "")) == "0"
            login_error = str(getattr(login_result, "error_msg", ""))
            try:
                package.logout()
            except Exception:
                pass
        except Exception as exc:  # noqa: BLE001
            login_error = str(exc)[:300]
    row = {
        "source_name": "BaoStock",
        "source_type": "baostock_history_k_data",
        "package_available": package_available,
        "package_version": package_version,
        "login_success": login_success,
        "login_error": login_error,
        "available_api": "query_history_k_data_plus" if package_available else "missing",
        "available_fields": BAOSTOCK_FIELDS if package_available else "missing",
        "pit_ready": bool(package_available and login_success),
        "coverage_estimate": "to_be_verified_by_fetch" if package_available else "source_missing",
        "quality_risk": "usable_if_login_success" if package_available and login_success else "package_missing_or_login_failed",
        "notes": "free source; research-only validation; no token required",
    }
    frame = pd.DataFrame([row], columns=SOURCE_INVENTORY_COLUMNS)
    for col in ["package_available", "login_success", "pit_ready"]:
        frame[col] = frame[col].astype(object)
    return frame


def load_standard_watchlist(path: Path = WATCHLIST_DIR / "watchlist_admission_events.csv") -> pd.DataFrame:
    if not path.exists():
        return _empty(["asset_id", "symbol", "name", "first_admission_date", "admission_variant"])
    frame = pd.read_csv(path)
    frame = frame[frame["admission_variant"].eq("standard_research_watchlist")].copy()
    if frame.empty:
        return _empty(["asset_id", "symbol", "name", "first_admission_date", "admission_variant"])
    frame["symbol"] = frame.apply(lambda row: _safe_symbol(row["asset_id"], row.get("symbol", "")), axis=1)
    frame = frame.sort_values(["asset_id", "first_admission_date"]).drop_duplicates("asset_id", keep="first")
    return frame[["asset_id", "symbol", "name", "first_admission_date", "admission_variant"]].reset_index(drop=True)


def infer_research_trade_date() -> str:
    candidates: list[pd.Timestamp] = []
    valuation_path = VALUATION_DIR / "valuation_structured_outputs.csv"
    if valuation_path.exists():
        frame = pd.read_csv(valuation_path)
        if "trade_date" in frame.columns:
            dates = pd.to_datetime(frame["trade_date"], errors="coerce")
            if dates.notna().any():
                candidates.append(dates.max())
    patch_path = FUNDAMENTAL_PATCH_DIR / "watchlist_report_fundamental_patch_index.csv"
    if patch_path.exists():
        frame = pd.read_csv(patch_path)
        if "report_date" in frame.columns:
            dates = pd.to_datetime(frame["report_date"], errors="coerce")
            if dates.notna().any():
                candidates.append(dates.max())
    watchlist_path = WATCHLIST_DIR / "watchlist_admission_events.csv"
    if watchlist_path.exists():
        frame = pd.read_csv(watchlist_path)
        if "first_admission_date" in frame.columns:
            dates = pd.to_datetime(frame["first_admission_date"], errors="coerce")
            if dates.notna().any():
                candidates.append(dates.max())
    if not candidates:
        return _now_date()
    return str(max(candidates).date())


def build_baostock_fetch_plan(
    watchlist: pd.DataFrame,
    output_dir: Path = OUTPUT_DIR,
    *,
    research_trade_date: str | None = None,
    start_date: str = "2022-01-01",
) -> pd.DataFrame:
    research_date = research_trade_date or infer_research_trade_date()
    rows: list[dict[str, Any]] = []
    for _, row in watchlist.iterrows():
        asset_id = str(row["asset_id"])
        symbol = _safe_symbol(asset_id, row.get("symbol", ""))
        code = asset_id_to_baostock_code(asset_id)
        cache_path = output_dir / "cache/baostock/history_k_data" / f"{code.replace('.', '_')}_{start_date}_{research_date}.csv"
        rows.append(
            {
                "asset_id": asset_id,
                "symbol": symbol,
                "name": row.get("name", ""),
                "baostock_code": code,
                "start_date": start_date,
                "end_date": research_date,
                "fetch_required": not cache_path.exists(),
                "target_fields": BAOSTOCK_FIELDS,
                "expected_pit_use": "baostock_date <= research_trade_date",
                "cache_path": str(cache_path),
                "fetch_status": "success_cached" if cache_path.exists() else "planned",
                "skip_reason": "cache_exists" if cache_path.exists() else "",
                "human_review_required": False,
            }
        )
    frame = pd.DataFrame(rows, columns=FETCH_PLAN_COLUMNS)
    if not frame.empty:
        for col in ["fetch_required", "human_review_required"]:
            frame[col] = frame[col].map(bool).astype(object)
    return frame


def _result_to_frame(result: Any) -> pd.DataFrame:
    rows = []
    fields = list(getattr(result, "fields", []))
    while result.next():
        rows.append(result.get_row_data())
    return pd.DataFrame(rows, columns=fields)


def _write_frame(frame: pd.DataFrame, path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)
    return _sha256_file(path)


def fetch_baostock_history(
    fetch_plan: pd.DataFrame,
    output_dir: Path = OUTPUT_DIR,
    *,
    client: Any | None = None,
    importer: Callable[[], Any] | None = None,
    stop_after_asset_count: int | None = None,
    sleep_seconds: float = 0.05,
) -> pd.DataFrame:
    package = client
    package_missing = False
    login_failed = False
    login_error = ""
    if package is None:
        try:
            package = importer() if importer else importlib.import_module("baostock")
        except Exception as exc:  # noqa: BLE001
            package_missing = True
            login_error = str(exc)[:300]
    if package is not None:
        try:
            login_result = package.login()
            login_failed = str(getattr(login_result, "error_code", "0")) != "0"
            login_error = str(getattr(login_result, "error_msg", ""))
        except Exception as exc:  # noqa: BLE001
            login_failed = True
            login_error = str(exc)[:300]
    rows: list[dict[str, Any]] = []
    attempted_count = 0
    for _, row in fetch_plan.iterrows():
        start = time.perf_counter()
        cache_path = Path(row["cache_path"])
        if cache_path.exists():
            cached = pd.read_csv(cache_path)
            rows.append(_fetch_result_row(row, False, "success_cached", len(cached), len(cached.columns), cache_path, "", time.perf_counter() - start))
            continue
        if stop_after_asset_count is not None and attempted_count >= stop_after_asset_count:
            rows.append(_fetch_result_row(row, False, "skipped", 0, 0, cache_path, "skipped_after_asset_limit", time.perf_counter() - start))
            continue
        if package_missing:
            rows.append(_fetch_result_row(row, False, "package_missing", 0, 0, cache_path, login_error, time.perf_counter() - start))
            continue
        if login_failed or package is None:
            rows.append(_fetch_result_row(row, False, "login_failed", 0, 0, cache_path, login_error, time.perf_counter() - start))
            continue
        attempted_count += 1
        try:
            rs = package.query_history_k_data_plus(
                str(row["baostock_code"]),
                BAOSTOCK_FIELDS,
                start_date=str(row["start_date"]),
                end_date=str(row["end_date"]),
                frequency="d",
                adjustflag="3",
            )
            if str(getattr(rs, "error_code", "0")) != "0":
                error = str(getattr(rs, "error_msg", ""))
                rows.append(_fetch_result_row(row, True, "api_error", 0, 0, cache_path, error, time.perf_counter() - start))
                continue
            data = _result_to_frame(rs)
            if data.empty:
                rows.append(_fetch_result_row(row, True, "empty_result", 0, len(data.columns), cache_path, "", time.perf_counter() - start))
                continue
            content_hash = _write_frame(data, cache_path)
            rows.append(_fetch_result_row(row, True, "success", len(data), len(data.columns), cache_path, "", time.perf_counter() - start, content_hash))
            if sleep_seconds:
                time.sleep(sleep_seconds)
        except Exception as exc:  # noqa: BLE001
            error = str(exc)[:300]
            status = "network_unavailable" if "network" in error.lower() or "连接" in error else "api_error"
            rows.append(_fetch_result_row(row, True, status, 0, 0, cache_path, error, time.perf_counter() - start))
    if package is not None:
        try:
            package.logout()
        except Exception:
            pass
    return pd.DataFrame(rows, columns=FETCH_RESULT_COLUMNS)


def _fetch_result_row(row: pd.Series, attempted: bool, status: str, row_count: int, field_count: int, cache_path: Path, error: str, elapsed: float, content_hash: str | None = None) -> dict[str, Any]:
    return {
        "asset_id": row["asset_id"],
        "symbol": row["symbol"],
        "name": row["name"],
        "baostock_code": row["baostock_code"],
        "fetch_attempted": attempted,
        "fetch_status": status,
        "row_count": int(row_count),
        "field_count": int(field_count),
        "cache_path": str(cache_path),
        "content_hash": content_hash if content_hash is not None else _sha256_file(cache_path),
        "api_error": error,
        "elapsed_seconds": round(float(elapsed), 4),
        "data_quality_status": "cache_available" if status in {"success", "success_cached"} and row_count else "degraded_fetch_not_available",
    }


def _read_cache(path: Any) -> pd.DataFrame:
    cache_path = Path(str(path))
    if not cache_path.exists():
        return pd.DataFrame()
    return pd.read_csv(cache_path)


def build_raw_candidate_matches(fetch_plan: pd.DataFrame, fetch_results: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    plan_lookup = fetch_plan.set_index("asset_id").to_dict("index") if not fetch_plan.empty else {}
    for _, result in fetch_results.iterrows():
        if result["fetch_status"] not in {"success", "success_cached"}:
            continue
        data = _read_cache(result["cache_path"])
        plan = plan_lookup.get(result["asset_id"], {})
        research_trade_date = pd.to_datetime(plan.get("end_date"), errors="coerce")
        for _, raw in data.iterrows():
            date = pd.to_datetime(raw.get("date"), errors="coerce")
            lookahead = bool(pd.notna(date) and pd.notna(research_trade_date) and date > research_trade_date)
            required = ["date", "code", "peTTM", "pbMRQ", "psTTM"]
            missing = [field for field in required if field not in data.columns or pd.isna(raw.get(field)) or str(raw.get(field)) == ""]
            rows.append(
                {
                    "asset_id": result["asset_id"],
                    "symbol": result["symbol"],
                    "name": result["name"],
                    "baostock_code": result["baostock_code"],
                    "baostock_date": str(raw.get("date", "")),
                    "source_name": "baostock",
                    "matched_by": "asset_id_to_baostock_code",
                    "is_pit_valid": not lookahead,
                    "lookahead_violation": lookahead,
                    "available_field_count": int(raw.notna().sum()),
                    "missing_required_fields": "|".join(missing) if missing else "none",
                    "data_quality_status": "pit_valid" if not lookahead else "invalid_lookahead",
                }
            )
    frame = pd.DataFrame(rows, columns=RAW_MATCH_COLUMNS)
    frame.attrs["_fetch_results"] = fetch_results
    return frame


def _raw_rows_with_values(fetch_results: pd.DataFrame, asset_id: str) -> pd.DataFrame:
    matched = fetch_results[fetch_results["asset_id"].eq(asset_id)]
    if matched.empty:
        return pd.DataFrame()
    frames = []
    for _, row in matched.iterrows():
        if row["fetch_status"] in {"success", "success_cached"}:
            data = _read_cache(row["cache_path"])
            if not data.empty:
                data = data.copy()
                data["asset_id"] = row["asset_id"]
                data["symbol"] = row["symbol"]
                data["name"] = row["name"]
                data["baostock_code"] = row["baostock_code"]
                frames.append(data)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def _to_num(value: Any) -> float:
    number = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return float(number) if pd.notna(number) else float("nan")


def build_structured_outputs(watchlist: pd.DataFrame, raw_matches: pd.DataFrame, research_trade_date: str, fetch_results: pd.DataFrame | None = None) -> pd.DataFrame:
    if fetch_results is None:
        # Test helper path: derive cache paths from raw matches is impossible, so read sibling output cache via fetch statuses is optional.
        fetch_results = raw_matches.attrs.get("_fetch_results", pd.DataFrame())
    rows: list[dict[str, Any]] = []
    research_date = pd.to_datetime(research_trade_date)
    for _, stock in watchlist.iterrows():
        asset_id = stock["asset_id"]
        if fetch_results is not None and not fetch_results.empty:
            raw = _raw_rows_with_values(fetch_results, asset_id)
        else:
            raw = pd.DataFrame()
        if raw.empty:
            rows.append(_structured_missing_row(stock, research_trade_date))
            continue
        raw = raw.copy()
        raw["date_dt"] = pd.to_datetime(raw["date"], errors="coerce")
        eligible = raw[raw["date_dt"].le(research_date)]
        if eligible.empty:
            rows.append(_structured_missing_row(stock, research_trade_date, status="no_pit_eligible_row"))
            continue
        latest = eligible.sort_values("date_dt").iloc[-1]
        missing = []
        mapping = {
            "pe_ttm": latest.get("peTTM"),
            "pb": latest.get("pbMRQ"),
            "ps_ttm": latest.get("psTTM"),
            "pcf_ncf_ttm": latest.get("pcfNcfTTM"),
            "turnover_rate": latest.get("turn"),
            "tradestatus": latest.get("tradestatus"),
            "is_st": latest.get("isST"),
            "close": latest.get("close"),
            "amount": latest.get("amount"),
        }
        for key, value in mapping.items():
            if pd.isna(value) or str(value) == "":
                missing.append(key)
        lookahead = bool(pd.to_datetime(latest["date"]) > research_date)
        rows.append(
            {
                "research_trade_date": research_trade_date,
                "asset_id": asset_id,
                "symbol": _safe_symbol(asset_id, stock.get("symbol", "")),
                "name": stock.get("name", ""),
                "baostock_code": asset_id_to_baostock_code(asset_id),
                "baostock_date": str(latest["date"]),
                "source_type": "baostock_history_k_data",
                "is_pit_valid": not lookahead,
                "lookahead_violation": lookahead,
                "pe_ttm": _to_num(mapping["pe_ttm"]),
                "pb": _to_num(mapping["pb"]),
                "ps_ttm": _to_num(mapping["ps_ttm"]),
                "pcf_ncf_ttm": _to_num(mapping["pcf_ncf_ttm"]),
                "turnover_rate": _to_num(mapping["turnover_rate"]),
                "tradestatus": str(mapping["tradestatus"]),
                "is_st": str(mapping["is_st"]),
                "close": _to_num(mapping["close"]),
                "amount": _to_num(mapping["amount"]),
                "valuation_data_status": "baostock_pe_pb_ps_available" if not missing else "degraded_missing_fields",
                "missing_fields": "|".join(missing) if missing else "none",
                "conflict_flags": "negative_pe_not_low" if pd.notna(_to_num(mapping["pe_ttm"])) and _to_num(mapping["pe_ttm"]) <= 0 else "none",
                "data_quality_status": "pit_valid" if not lookahead else "invalid_lookahead",
                "rule_version": RULE_VERSION,
            }
        )
    return pd.DataFrame(rows, columns=STRUCTURED_COLUMNS)


def _structured_missing_row(stock: pd.Series, research_trade_date: str, status: str = "no_baostock_support") -> dict[str, Any]:
    asset_id = stock["asset_id"]
    return {
        "research_trade_date": research_trade_date,
        "asset_id": asset_id,
        "symbol": _safe_symbol(asset_id, stock.get("symbol", "")),
        "name": stock.get("name", ""),
        "baostock_code": asset_id_to_baostock_code(asset_id),
        "baostock_date": "missing",
        "source_type": "baostock_history_k_data",
        "is_pit_valid": False,
        "lookahead_violation": False,
        "pe_ttm": float("nan"),
        "pb": float("nan"),
        "ps_ttm": float("nan"),
        "pcf_ncf_ttm": float("nan"),
        "turnover_rate": float("nan"),
        "tradestatus": "missing",
        "is_st": "missing",
        "close": float("nan"),
        "amount": float("nan"),
        "valuation_data_status": status,
        "missing_fields": "pe_ttm|pb|ps_ttm|pcf_ncf_ttm",
        "conflict_flags": "none",
        "data_quality_status": "degraded_missing_baostock_data",
        "rule_version": RULE_VERSION,
    }


def build_structured_outputs_from_fetch(watchlist: pd.DataFrame, fetch_results: pd.DataFrame, research_trade_date: str) -> pd.DataFrame:
    raw_stub = pd.DataFrame()
    raw_stub.attrs["_fetch_results"] = fetch_results
    return build_structured_outputs(watchlist, raw_stub, research_trade_date, fetch_results=fetch_results)


def _percentile(current: float, values: pd.Series) -> Any:
    series = pd.to_numeric(values, errors="coerce").dropna()
    if pd.isna(current) or not len(series):
        return "not_meaningful"
    if current <= 0:
        return "not_meaningful"
    series = series[series > 0]
    if not len(series):
        return "not_meaningful"
    return round(float((series <= current).mean()), 6)


def _window_quality(days: int) -> str:
    if days >= 252 * 5:
        return "full_5y"
    if days >= 252 * 3:
        return "full_3y_partial_5y"
    if days >= 252:
        return "full_1y_partial_3y"
    if days > 0:
        return "available_window_short"
    return "missing"


def build_percentile_outputs(structured: pd.DataFrame, raw_matches: pd.DataFrame, fetch_results: pd.DataFrame | None = None) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    if fetch_results is None:
        fetch_results = raw_matches.attrs.get("_fetch_results", pd.DataFrame())
    for _, current in structured.iterrows():
        raw = _raw_rows_with_values(fetch_results, current["asset_id"]) if fetch_results is not None and not fetch_results.empty else pd.DataFrame()
        research_date = pd.to_datetime(current["research_trade_date"])
        if not raw.empty:
            raw = raw.copy()
            raw["date_dt"] = pd.to_datetime(raw["date"], errors="coerce")
            raw = raw[raw["date_dt"].le(research_date)]
        days = int(len(raw))
        missing = []
        pe = pd.to_numeric(raw.get("peTTM", pd.Series(dtype=float)), errors="coerce") if not raw.empty else pd.Series(dtype=float)
        pb = pd.to_numeric(raw.get("pbMRQ", pd.Series(dtype=float)), errors="coerce") if not raw.empty else pd.Series(dtype=float)
        ps = pd.to_numeric(raw.get("psTTM", pd.Series(dtype=float)), errors="coerce") if not raw.empty else pd.Series(dtype=float)
        if (pd.notna(current["pe_ttm"]) and float(current["pe_ttm"]) <= 0) or bool(pe.le(0).any()):
            missing.append("negative_pe_not_low")
        rows.append(
            {
                "research_trade_date": current["research_trade_date"],
                "asset_id": current["asset_id"],
                "symbol": current["symbol"],
                "name": current["name"],
                "baostock_code": current["baostock_code"],
                "baostock_date": current["baostock_date"],
                "pe_ttm": current["pe_ttm"],
                "pb": current["pb"],
                "ps_ttm": current["ps_ttm"],
                "pcf_ncf_ttm": current["pcf_ncf_ttm"],
                "pe_ttm_percentile_1y": _percentile(current["pe_ttm"], pe.tail(252)),
                "pe_ttm_percentile_3y": _percentile(current["pe_ttm"], pe.tail(252 * 3)),
                "pe_ttm_percentile_5y": _percentile(current["pe_ttm"], pe.tail(252 * 5)),
                "pb_percentile_1y": _percentile(current["pb"], pb.tail(252)),
                "pb_percentile_3y": _percentile(current["pb"], pb.tail(252 * 3)),
                "pb_percentile_5y": _percentile(current["pb"], pb.tail(252 * 5)),
                "ps_ttm_percentile_1y": _percentile(current["ps_ttm"], ps.tail(252)),
                "ps_ttm_percentile_3y": _percentile(current["ps_ttm"], ps.tail(252 * 3)),
                "ps_ttm_percentile_5y": _percentile(current["ps_ttm"], ps.tail(252 * 5)),
                "history_window_days_available": days,
                "history_window_quality": _window_quality(days),
                "percentile_data_status": "available_window" if days else "missing_history",
                "missing_fields": "|".join(missing) if missing else "none",
            }
        )
    return pd.DataFrame(rows, columns=PERCENTILE_COLUMNS)


def build_percentile_outputs_from_fetch(structured: pd.DataFrame, fetch_results: pd.DataFrame) -> pd.DataFrame:
    raw_stub = pd.DataFrame()
    raw_stub.attrs["_fetch_results"] = fetch_results
    return build_percentile_outputs(structured, raw_stub, fetch_results=fetch_results)


def build_asset_coverage(watchlist: pd.DataFrame, raw_matches: pd.DataFrame, percentiles: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for _, stock in watchlist.iterrows():
        asset_id = stock["asset_id"]
        raw = raw_matches[raw_matches["asset_id"].eq(asset_id)] if not raw_matches.empty else pd.DataFrame()
        pct = percentiles[percentiles["asset_id"].eq(asset_id)] if not percentiles.empty else pd.DataFrame()
        latest = pct.iloc[0] if not pct.empty else {}
        support = not pct.empty and pd.notna(latest.get("pe_ttm")) and pd.notna(latest.get("pb")) and pd.notna(latest.get("ps_ttm"))
        rows.append(
            {
                "asset_id": asset_id,
                "symbol": _safe_symbol(asset_id, stock.get("symbol", "")),
                "name": stock.get("name", ""),
                "baostock_code": asset_id_to_baostock_code(asset_id),
                "in_standard_watchlist": True,
                "baostock_record_count": int(len(raw)),
                "pit_valid_record_count": int(raw["is_pit_valid"].sum()) if not raw.empty else 0,
                "latest_baostock_date": str(raw["baostock_date"].max()) if not raw.empty else "missing",
                "has_pe_ttm": bool(not pct.empty and pd.notna(latest.get("pe_ttm"))),
                "has_pb": bool(not pct.empty and pd.notna(latest.get("pb"))),
                "has_ps_ttm": bool(not pct.empty and pd.notna(latest.get("ps_ttm"))),
                "has_pcf_ncf_ttm": bool(not pct.empty and pd.notna(latest.get("pcf_ncf_ttm"))),
                "has_turnover_rate": bool(len(raw)),
                "has_tradestatus": bool(len(raw)),
                "has_is_st": bool(len(raw)),
                "has_1y_percentile": bool(not pct.empty and latest.get("pe_ttm_percentile_1y") != "not_meaningful"),
                "has_3y_percentile": bool(not pct.empty and latest.get("pe_ttm_percentile_3y") != "not_meaningful"),
                "has_5y_percentile": bool(not pct.empty and latest.get("pe_ttm_percentile_5y") != "not_meaningful"),
                "valuation_support_level": "baostock_pe_pb_ps_support" if support else "baostock_support_missing_or_partial",
                "coverage_status": "covered" if support else "degraded_missing_pe_pb_ps",
                "human_review_required": True,
            }
        )
    return pd.DataFrame(rows, columns=ASSET_COVERAGE_COLUMNS)


def build_field_coverage_audit(structured: pd.DataFrame, percentiles: pd.DataFrame) -> pd.DataFrame:
    combined = structured.merge(percentiles, on=["research_trade_date", "asset_id", "symbol", "name", "baostock_code", "baostock_date", "pe_ttm", "pb", "ps_ttm", "pcf_ncf_ttm"], how="outer") if not structured.empty else percentiles
    fields = [
        "pe_ttm",
        "pb",
        "ps_ttm",
        "pcf_ncf_ttm",
        "turnover_rate",
        "tradestatus",
        "is_st",
        "close",
        "amount",
        "pe_ttm_percentile_1y",
        "pe_ttm_percentile_3y",
        "pe_ttm_percentile_5y",
        "pb_percentile_3y",
        "ps_ttm_percentile_3y",
    ]
    rows = []
    total = len(combined)
    for field in fields:
        if field not in combined.columns:
            non_missing = 0
        else:
            series = combined[field]
            non_missing = int(series.notna().sum() - series.astype(str).isin(["", "missing", "not_meaningful"]).sum())
            non_missing = max(non_missing, 0)
        missing = max(total - non_missing, 0)
        rows.append(
            {
                "field_name": field,
                "non_missing_count": non_missing,
                "missing_count": missing,
                "coverage_ratio": round(non_missing / total, 6) if total else 0.0,
                "quality_note": "available" if non_missing else "missing_or_not_meaningful",
            }
        )
    return pd.DataFrame(rows, columns=FIELD_AUDIT_COLUMNS)


def build_watchlist_gap_patch(watchlist: pd.DataFrame, structured: pd.DataFrame, percentiles: pd.DataFrame, coverage: pd.DataFrame, previous_valuation: pd.DataFrame) -> pd.DataFrame:
    previous_support = set(previous_valuation["asset_id"]) if not previous_valuation.empty and "asset_id" in previous_valuation.columns else set()
    rows = []
    for _, stock in watchlist.iterrows():
        asset_id = stock["asset_id"]
        current = structured[structured["asset_id"].eq(asset_id)]
        pct = percentiles[percentiles["asset_id"].eq(asset_id)]
        cov = coverage[coverage["asset_id"].eq(asset_id)]
        has_support = not cov.empty and cov.iloc[0]["valuation_support_level"] == "baostock_pe_pb_ps_support"
        s = current.iloc[0] if not current.empty else {}
        p = pct.iloc[0] if not pct.empty else {}
        rows.append(
            {
                "asset_id": asset_id,
                "symbol": _safe_symbol(asset_id, stock.get("symbol", "")),
                "name": stock.get("name", ""),
                "previous_valuation_support": asset_id in previous_support,
                "new_baostock_support": bool(has_support),
                "baostock_record_count": int(cov.iloc[0]["baostock_record_count"]) if not cov.empty else 0,
                "latest_baostock_date": cov.iloc[0]["latest_baostock_date"] if not cov.empty else "missing",
                "pe_ttm": s.get("pe_ttm", ""),
                "pb": s.get("pb", ""),
                "ps_ttm": s.get("ps_ttm", ""),
                "pcf_ncf_ttm": s.get("pcf_ncf_ttm", ""),
                "pe_ttm_percentile_3y": p.get("pe_ttm_percentile_3y", "not_meaningful"),
                "pb_percentile_3y": p.get("pb_percentile_3y", "not_meaningful"),
                "ps_ttm_percentile_3y": p.get("ps_ttm_percentile_3y", "not_meaningful"),
                "valuation_support_level": cov.iloc[0]["valuation_support_level"] if not cov.empty else "baostock_support_missing_or_partial",
                "new_source_count_delta": 1 if has_support else 0,
                "new_evidence_tags": "baostock_pe_pb_ps_context" if has_support else "missing",
                "new_risk_flags": "st_or_suspended_context" if str(s.get("is_st", "0")) == "1" or str(s.get("tradestatus", "1")) != "1" else "none",
                "report_patch_summary": "BaoStock PE/PB/PS context available for research review." if has_support else "BaoStock PE/PB/PS context missing or partial.",
                "still_missing_baostock_valuation": not has_support,
                "recommended_report_update": "update_report_baostock_valuation" if has_support else "no_baostock_support",
                "human_review_required": True,
            }
        )
    return pd.DataFrame(rows, columns=GAP_PATCH_COLUMNS)


def build_quality_audit(source_inventory: pd.DataFrame, fetch_plan: pd.DataFrame, fetch_results: pd.DataFrame, raw_matches: pd.DataFrame, structured: pd.DataFrame, percentiles: pd.DataFrame, coverage: pd.DataFrame) -> pd.DataFrame:
    package_available = bool(source_inventory.loc[0, "package_available"]) if not source_inventory.empty else False
    login_success = bool(source_inventory.loc[0, "login_success"]) if not source_inventory.empty else False
    pe = pd.to_numeric(structured.get("pe_ttm", pd.Series(dtype=float)), errors="coerce")
    rows = [
        ("package_available", package_available, "BaoStock import status"),
        ("login_success", login_success, "BaoStock login status"),
        ("fetch_plan_rows", len(fetch_plan), "standard watchlist assets"),
        ("fetch_attempted_rows", int(fetch_results["fetch_attempted"].fillna(False).astype(bool).sum()) if not fetch_results.empty else 0, "attempted source calls"),
        ("fetch_success_rows", int(fetch_results["fetch_status"].eq("success").sum()) if not fetch_results.empty else 0, "newly cached assets"),
        ("fetch_success_cached_rows", int(fetch_results["fetch_status"].eq("success_cached").sum()) if not fetch_results.empty else 0, "reused cache assets"),
        ("fetch_failed_rows", int(fetch_results["fetch_status"].isin(["api_error", "network_unavailable", "failed", "package_missing", "login_failed"]).sum()) if not fetch_results.empty else 0, "failed assets"),
        ("empty_result_rows", int(fetch_results["fetch_status"].eq("empty_result").sum()) if not fetch_results.empty else 0, "empty source results"),
        ("raw_baostock_rows", int(fetch_results["row_count"].sum()) if not fetch_results.empty else 0, "raw cached rows"),
        ("matched_baostock_rows", len(raw_matches), "PIT raw matches"),
        ("structured_baostock_rows", len(structured), "structured research rows"),
        ("standard_watchlist_asset_count", len(fetch_plan), "asset count"),
        ("assets_with_baostock_support", int(coverage["valuation_support_level"].eq("baostock_pe_pb_ps_support").sum()) if not coverage.empty else 0, "assets with PE/PB/PS support"),
        ("baostock_coverage_ratio", round(float(coverage["valuation_support_level"].eq("baostock_pe_pb_ps_support").mean()), 6) if not coverage.empty else 0.0, "support ratio"),
        ("PIT_valid_ratio", round(float(structured["is_pit_valid"].fillna(False).mean()), 6) if not structured.empty else 0.0, "structured PIT ratio"),
        ("lookahead_violation_rows", int(structured["lookahead_violation"].sum()) if not structured.empty else 0, "must be zero"),
        ("assets_with_pe_ttm", int(coverage["has_pe_ttm"].sum()) if not coverage.empty else 0, "field coverage"),
        ("assets_with_pb", int(coverage["has_pb"].sum()) if not coverage.empty else 0, "field coverage"),
        ("assets_with_ps_ttm", int(coverage["has_ps_ttm"].sum()) if not coverage.empty else 0, "field coverage"),
        ("assets_with_pcf_ncf_ttm", int(coverage["has_pcf_ncf_ttm"].sum()) if not coverage.empty else 0, "field coverage"),
        ("assets_with_1y_percentile", int(coverage["has_1y_percentile"].sum()) if not coverage.empty else 0, "percentile coverage"),
        ("assets_with_3y_percentile", int(coverage["has_3y_percentile"].sum()) if not coverage.empty else 0, "percentile coverage"),
        ("assets_with_5y_percentile", int(coverage["has_5y_percentile"].sum()) if not coverage.empty else 0, "percentile coverage"),
        ("negative_pe_rows", int(pe.le(0).sum()) if len(pe) else 0, "not interpreted as low valuation"),
        ("not_meaningful_pe_rows", int(pe.isna().sum() + pe.le(0).sum()) if len(pe) else 0, "PE not meaningful rows"),
        ("degraded_rows", int(structured["data_quality_status"].astype(str).str.contains("degraded|missing", regex=True).sum()) if not structured.empty else 0, "degraded structured rows"),
        ("invalid_rows", int(structured["lookahead_violation"].sum()) if not structured.empty else 0, "invalid rows"),
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


def render_report(audit: pd.DataFrame, git_info: dict[str, str], output_dir: Path) -> str:
    lookup = dict(zip(audit["metric"], audit["value"]))
    return f"""# Tech Bottleneck BaoStock PE/PB/PS Source Adapter v1

## 1. Executive Summary

- BaoStock package available: {lookup.get("package_available")}.
- BaoStock login success: {lookup.get("login_success")}.
- structured BaoStock rows: {lookup.get("structured_baostock_rows")}.
- standard watchlist assets with PE/PB/PS support: {lookup.get("assets_with_baostock_support")} / {lookup.get("standard_watchlist_asset_count")}.
- BaoStock coverage ratio: {lookup.get("baostock_coverage_ratio")}.
- pe_ttm / pb / ps_ttm / pcf_ncf_ttm coverage: {lookup.get("assets_with_pe_ttm")} / {lookup.get("assets_with_pb")} / {lookup.get("assets_with_ps_ttm")} / {lookup.get("assets_with_pcf_ncf_ttm")}.
- 1y / 3y / 5y percentile coverage: {lookup.get("assets_with_1y_percentile")} / {lookup.get("assets_with_3y_percentile")} / {lookup.get("assets_with_5y_percentile")}.
- lookahead_violation_rows: {lookup.get("lookahead_violation_rows")}.
- This layer is research-only valuation context and produces no automated execution prompt.

## 2. Source Inventory

BaoStock is checked by import and login. The target API is `query_history_k_data_plus`; target fields are `{BAOSTOCK_FIELDS}`.

## 3. Fetch Plan

The fetch plan maps standard watchlist `asset_id` values to BaoStock codes such as `CN:SH:600000 -> sh.600000` and `CN:SZ:002028 -> sz.002028`. Fetching is serial and cache-first.

## 4. Matching and PIT Validation

Structured rows use only `baostock_date <= research_trade_date`. `lookahead_violation_rows` must remain zero.

## 5. Structured BaoStock Fields

Mappings: `peTTM -> pe_ttm`, `pbMRQ -> pb`, `psTTM -> ps_ttm`, `pcfNcfTTM -> pcf_ncf_ttm`, `turn -> turnover_rate`, plus `tradestatus` and `isST`.

## 6. Historical Percentile Calculation

Historical percentiles only use rows on or before the research date. Negative or missing PE is marked not meaningful and is not treated as low valuation.

## 7. Standard Watchlist Coverage

Assets with BaoStock support: {lookup.get("assets_with_baostock_support")}. Coverage ratio: {lookup.get("baostock_coverage_ratio")}.

## 8. Field Coverage and Missing Data

Use `baostock_field_coverage_audit.csv` for field-level gaps. Missing fields remain missing; no fallback penalty is applied.

## 9. Report Patch Candidates

Use `watchlist_baostock_valuation_gap_patch.csv` to identify reports that can receive BaoStock valuation context.

## 10. Data Quality and Cross-source Validation

BaoStock is a free source and should be cross-checked with AKShare or Tushare when available. It is suitable for research context, not automatic execution decisions.

## 11. What This Layer Does Not Do

- No automated execution prompt is produced.
- It does not change Top5.
- It does not change formal strategy files.
- It does not study trigger / holding / exit.
- It does not use evidence multiplier.
- It does not use PE/PB/PS as automated execution basis.

## 12. Recommended Next Step

If coverage is meaningful, next task: `tech_bottleneck_watchlist_report_baostock_valuation_patch_v1`. If coverage is weak, next task: `tech_bottleneck_akshare_lg_indicator_probe_v1`.

## 13. Appendix

- Output directory: `{output_dir}`.
- Generated files: source inventory, fetch plan, fetch results, raw matches, structured outputs, percentiles, coverage, field audit, gap patch, quality audit, Markdown report.
- git repo root: `{git_info.get("repo_root")}`.
- formal strategy file status: `{git_info.get("formal_strategy_status")}`.
- Because untracked files are not covered by normal git diff, formal strategy immutability cannot be fully proven from git diff alone if they remain untracked.
- Rule version: `{RULE_VERSION}`.
"""


def write_outputs(
    output_dir: Path = OUTPUT_DIR,
    *,
    stop_after_asset_count: int | None = None,
    start_date: str = "2022-01-01",
    research_trade_date: str | None = None,
    client: Any | None = None,
) -> dict[str, pd.DataFrame]:
    output_dir.mkdir(parents=True, exist_ok=True)
    watchlist = load_standard_watchlist()
    research_date = research_trade_date or infer_research_trade_date()
    source_inventory = inspect_baostock_source(client=client)
    fetch_plan = build_baostock_fetch_plan(watchlist, output_dir, research_trade_date=research_date, start_date=start_date)
    fetch_results = fetch_baostock_history(fetch_plan, output_dir, client=client, stop_after_asset_count=stop_after_asset_count)
    raw_matches = build_raw_candidate_matches(fetch_plan, fetch_results)
    structured = build_structured_outputs_from_fetch(watchlist, fetch_results, research_date)
    raw_stub = pd.DataFrame()
    raw_stub.attrs["_fetch_results"] = fetch_results
    percentiles = build_percentile_outputs(structured, raw_stub, fetch_results=fetch_results)
    coverage = build_asset_coverage(watchlist, raw_matches, percentiles)
    field_audit = build_field_coverage_audit(structured, percentiles)
    previous_path = VALUATION_DIR / "valuation_structured_outputs.csv"
    previous = pd.read_csv(previous_path) if previous_path.exists() else pd.DataFrame()
    patch = build_watchlist_gap_patch(watchlist, structured, percentiles, coverage, previous)
    audit = build_quality_audit(source_inventory, fetch_plan, fetch_results, raw_matches, structured, percentiles, coverage)
    report = render_report(audit, _git_info(PROJECT_ROOT), output_dir)
    outputs = {
        "baostock_source_inventory.csv": source_inventory,
        "baostock_fetch_plan.csv": fetch_plan,
        "baostock_fetch_results.csv": fetch_results,
        "baostock_raw_candidate_matches.csv": raw_matches,
        "baostock_structured_outputs.csv": structured,
        "baostock_percentile_outputs.csv": percentiles,
        "baostock_asset_coverage.csv": coverage,
        "baostock_field_coverage_audit.csv": field_audit,
        "watchlist_baostock_valuation_gap_patch.csv": patch,
        "baostock_quality_audit.csv": audit,
    }
    for name, frame in outputs.items():
        frame.to_csv(output_dir / name, index=False)
    (output_dir / "baostock_pe_pb_ps_source_adapter_v1.md").write_text(report, encoding="utf-8")
    return outputs


def main() -> None:
    parser = argparse.ArgumentParser(description="Research-only BaoStock PE/PB/PS adapter.")
    parser.add_argument("--stop-after-asset-count", type=int, default=None)
    parser.add_argument("--start-date", default="2022-01-01")
    parser.add_argument("--research-trade-date", default=None)
    args = parser.parse_args()
    outputs = write_outputs(
        OUTPUT_DIR,
        stop_after_asset_count=args.stop_after_asset_count,
        start_date=args.start_date,
        research_trade_date=args.research_trade_date,
    )
    audit = outputs["baostock_quality_audit.csv"]
    print(audit.to_string(index=False))
    joined = "\n".join(path.read_text(errors="ignore") for path in OUTPUT_DIR.rglob("*") if path.is_file())
    if contains_actionable_trading_language(joined):
        raise SystemExit("forbidden output language detected")


if __name__ == "__main__":
    main()
