from __future__ import annotations

import hashlib
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd


RULE_VERSION = "tech_bottleneck_daily_basic_pe_pb_ps_source_adapter_v1"

OUTPUT_DIR = Path(
    "/Users/xiwei/stock_research/outputs/research/tech_bottleneck_daily_basic_pe_pb_ps_source_adapter_v1"
)
WATCHLIST_PATH = Path(
    "/Users/xiwei/stock_research/outputs/research/tech_bottleneck_research_input_watchlist_forward_return_v1/watchlist_admission_events.csv"
)
VALUATION_STRUCTURED_PATH = Path(
    "/Users/xiwei/stock_research/outputs/research/tech_bottleneck_valuation_source_adapter_v1/valuation_structured_outputs.csv"
)

DAILY_BASIC_FIELDS = [
    "pe",
    "pe_ttm",
    "pb",
    "ps",
    "ps_ttm",
    "total_mv",
    "circ_mv",
    "turnover_rate",
    "turnover_rate_f",
    "volume_ratio",
    "dv_ratio",
    "dv_ttm",
    "total_share",
    "float_share",
    "free_share",
]

INVENTORY_COLUMNS = [
    "source_name",
    "source_type",
    "existing_in_project",
    "detected_path_or_table",
    "file_or_table_type",
    "available_fields",
    "trade_date_field",
    "ts_code_field",
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

FETCH_PLAN_COLUMNS = [
    "fetch_batch_id",
    "trade_date",
    "start_date",
    "end_date",
    "asset_scope",
    "target_asset_count",
    "expected_rows",
    "source_api",
    "fields",
    "requires_token",
    "estimated_calls",
    "rate_limit_note",
    "fetch_status",
    "skip_reason",
    "human_action_required",
]

RAW_COLUMNS = [
    "asset_id",
    "symbol",
    "name",
    "ts_code",
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
    "research_trade_date",
    "asset_id",
    "symbol",
    "name",
    "ts_code",
    "daily_basic_trade_date",
    "source_type",
    "is_pit_valid",
    "lookahead_violation",
    "pe",
    "pe_ttm",
    "pb",
    "ps",
    "ps_ttm",
    "total_mv",
    "circ_mv",
    "turnover_rate",
    "turnover_rate_f",
    "volume_ratio",
    "dv_ratio",
    "dv_ttm",
    "total_share",
    "float_share",
    "free_share",
    "market_cap_source",
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
    "ts_code",
    "daily_basic_trade_date",
    "pe_ttm",
    "pb",
    "ps_ttm",
    "total_mv",
    "circ_mv",
    "pe_ttm_percentile_1y",
    "pe_ttm_percentile_3y",
    "pe_ttm_percentile_5y",
    "pb_percentile_1y",
    "pb_percentile_3y",
    "pb_percentile_5y",
    "ps_ttm_percentile_1y",
    "ps_ttm_percentile_3y",
    "ps_ttm_percentile_5y",
    "total_mv_percentile_3y",
    "circ_mv_percentile_3y",
    "history_window_days_available",
    "history_window_quality",
    "percentile_data_status",
    "missing_fields",
]

INDUSTRY_COLUMNS = [
    "research_trade_date",
    "asset_id",
    "symbol",
    "name",
    "ts_code",
    "industry",
    "industry_peer_count",
    "pe_ttm",
    "pb",
    "ps_ttm",
    "pe_ttm_industry_percentile",
    "pb_industry_percentile",
    "ps_ttm_industry_percentile",
    "market_cap_industry_percentile",
    "industry_comparison_status",
    "missing_fields",
]

COVERAGE_COLUMNS = [
    "asset_id",
    "symbol",
    "name",
    "ts_code",
    "in_standard_watchlist",
    "daily_basic_record_count",
    "pit_valid_record_count",
    "latest_daily_basic_trade_date",
    "has_pe",
    "has_pe_ttm",
    "has_pb",
    "has_ps",
    "has_ps_ttm",
    "has_total_mv",
    "has_circ_mv",
    "has_1y_percentile",
    "has_3y_percentile",
    "has_5y_percentile",
    "has_industry_percentile",
    "valuation_support_level",
    "coverage_status",
    "human_review_required",
]

FIELD_AUDIT_COLUMNS = ["field_name", "non_missing_count", "missing_count", "coverage_ratio", "quality_note"]

PATCH_COLUMNS = [
    "asset_id",
    "symbol",
    "name",
    "previous_valuation_support",
    "new_daily_basic_support",
    "daily_basic_record_count",
    "latest_daily_basic_trade_date",
    "pe_ttm",
    "pb",
    "ps_ttm",
    "total_mv",
    "circ_mv",
    "pe_ttm_percentile_3y",
    "pb_percentile_3y",
    "ps_ttm_percentile_3y",
    "pe_ttm_industry_percentile",
    "pb_industry_percentile",
    "ps_ttm_industry_percentile",
    "valuation_support_level",
    "new_source_count_delta",
    "new_evidence_tags",
    "new_risk_flags",
    "report_patch_summary",
    "still_missing_daily_basic",
    "recommended_report_update",
    "human_review_required",
]

QUALITY_AUDIT_COLUMNS = ["metric", "value", "note"]

RECOMMENDED_REPORT_UPDATES = {
    "update_report_daily_basic_valuation",
    "review_pe_pb_ps_context",
    "request_daily_basic_history",
    "request_industry_mapping",
    "no_daily_basic_support",
    "manual_review_required",
}

FORBIDDEN_PATTERNS = [
    re.compile(r"\b(?:buy|sell|add|reduce|hold|target_price|position_size|entry_signal|exit_signal)\b", re.I),
    re.compile(r"买入|卖出|加仓|减仓|持有|目标价|仓位建议|入场点|止损点|交易信号"),
]


def contains_actionable_trading_language(text: str) -> bool:
    return any(pattern.search(str(text)) for pattern in FORBIDDEN_PATTERNS)


def _empty(columns: list[str]) -> pd.DataFrame:
    return pd.DataFrame(columns=columns)


def _num(value: Any) -> float | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _fmt(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except TypeError:
        pass
    return str(value)


def _date(value: Any) -> pd.Timestamp:
    text = str(value).strip()
    if not text or text.lower() in {"nan", "nat", "none"}:
        return pd.NaT
    if re.fullmatch(r"\d{8}", text):
        return pd.to_datetime(text, format="%Y%m%d", errors="coerce")
    return pd.to_datetime(text, errors="coerce")


def _date_str(value: Any) -> str:
    ts = _date(value)
    return ts.strftime("%Y-%m-%d") if pd.notna(ts) else "missing"


def asset_id_to_ts_code(asset_id: str) -> str:
    parts = str(asset_id).split(":")
    if len(parts) == 3 and parts[0] == "CN":
        return f"{parts[2]}.{parts[1].upper()}"
    return str(asset_id)


def ts_code_to_asset_id(ts_code: str) -> str:
    symbol, exchange = str(ts_code).strip().upper().split(".", 1)
    return f"CN:{exchange}:{symbol}"


def _standard_watchlist(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    data = frame.copy()
    if "admission_variant" in data.columns:
        standard = data[data["admission_variant"].eq("standard_research_watchlist")].copy()
        if not standard.empty:
            data = standard
    data["_admission_date"] = pd.to_datetime(
        data.get("first_admission_date", data.get("trade_date", "2026-06-29")),
        errors="coerce",
    )
    data = data.sort_values(["asset_id", "_admission_date"]).drop_duplicates("asset_id", keep="first")
    for col in ["symbol", "name"]:
        if col not in data.columns:
            data[col] = ""
    if "first_admission_date" not in data.columns:
        data["first_admission_date"] = data["_admission_date"].dt.strftime("%Y-%m-%d")
    return data[["asset_id", "symbol", "name", "first_admission_date"]].reset_index(drop=True)


def load_watchlist(path: Path = WATCHLIST_PATH) -> pd.DataFrame:
    if not path.exists():
        return _empty(["asset_id", "symbol", "name", "first_admission_date"])
    return _standard_watchlist(pd.read_csv(path))


def _research_date(watchlist: pd.DataFrame) -> pd.Timestamp:
    for col in ["report_date", "first_admission_date", "trade_date"]:
        if col in watchlist.columns:
            dates = pd.to_datetime(watchlist[col], errors="coerce")
            if dates.notna().any():
                return dates.max().normalize()
    return pd.Timestamp("2026-06-29")


def _candidate_daily_basic_paths(project_root: Path) -> list[Path]:
    candidates = [
        project_root / "data/daily_basic.csv",
        project_root / "data/tushare_daily_basic.csv",
        project_root / "data/daily_basic_cache.csv",
        project_root / "outputs/research/daily_basic.csv",
        project_root / "outputs/research/tushare_daily_basic.csv",
    ]
    return [p for p in candidates if p.exists()]


def _candidate_stock_basic_paths(project_root: Path) -> list[Path]:
    candidates = [
        project_root / "data/stock_basic.csv",
        project_root / "data/tushare_stock_basic.csv",
        project_root / "outputs/research/stock_basic.csv",
        project_root / "outputs/research/tushare_stock_basic.csv",
    ]
    return [p for p in candidates if p.exists()]


def _read_first_csv(paths: list[Path], required_any: set[str]) -> tuple[pd.DataFrame, Path | None]:
    for path in paths:
        try:
            frame = pd.read_csv(path)
        except Exception:
            continue
        if required_any.intersection(frame.columns):
            return frame, path
    return pd.DataFrame(), None


def _local_token_present(project_root: Path) -> bool:
    import json
    import os

    if os.environ.get("TUSHARE_TOKEN"):
        return True
    secrets = project_root / "config/local_secrets.json"
    if not secrets.exists():
        return False
    try:
        payload = json.loads(secrets.read_text())
    except Exception:
        return False
    return bool(payload.get("tushare", {}).get("token"))


def _inspect_csv(path: Path) -> tuple[list[str], str, str]:
    try:
        frame = pd.read_csv(path, nrows=5000)
    except Exception:
        return [], "missing", "missing"
    cols = list(frame.columns)
    date_col = "trade_date" if "trade_date" in cols else "list_date" if "list_date" in cols else ""
    dates = pd.to_datetime(frame[date_col], errors="coerce") if date_col else pd.Series(dtype="datetime64[ns]")
    return cols, (str(dates.min().date()) if dates.notna().any() else "missing"), (
        str(dates.max().date()) if dates.notna().any() else "missing"
    )


def build_daily_basic_source_inventory(
    project_root: Path,
    daily_basic_paths: list[Path] | None = None,
    stock_basic_paths: list[Path] | None = None,
) -> pd.DataFrame:
    daily_paths = daily_basic_paths if daily_basic_paths is not None else _candidate_daily_basic_paths(project_root)
    stock_paths = stock_basic_paths if stock_basic_paths is not None else _candidate_stock_basic_paths(project_root)
    daily_path = daily_paths[0] if daily_paths else None
    stock_path = stock_paths[0] if stock_paths else None
    token_present = _local_token_present(project_root)
    rows: list[dict[str, Any]] = []

    def add(
        source_name: str,
        source_type: str,
        path: Path | None,
        script_only: bool = False,
        notes: str = "",
    ) -> None:
        cols: list[str] = []
        date_min = "missing"
        date_max = "missing"
        if path is not None:
            cols, date_min, date_max = _inspect_csv(path)
        existing: Any = bool(path)
        if not existing and script_only:
            existing = "script_only"
        if not existing and source_type == "source_missing":
            existing = "source_missing"
        rows.append(
            {
                "source_name": source_name,
                "source_type": source_type,
                "existing_in_project": existing,
                "detected_path_or_table": str(path) if path else ("src/stock_research/daily_close_pipeline.py" if script_only else "missing"),
                "file_or_table_type": "csv" if path else ("script" if script_only else "missing"),
                "available_fields": "|".join(cols) if cols else "missing",
                "trade_date_field": "trade_date" if "trade_date" in cols else "missing",
                "ts_code_field": "ts_code" if "ts_code" in cols else "missing",
                "asset_id_field": "asset_id" if "asset_id" in cols else "missing",
                "symbol_field": "symbol" if "symbol" in cols else "missing",
                "industry_field": "industry" if "industry" in cols else "missing",
                "pit_ready": bool(path and "trade_date" in cols and ("ts_code" in cols or "asset_id" in cols)),
                "coverage_estimate": "computed_after_load" if path else "none",
                "date_range_min": date_min,
                "date_range_max": date_max,
                "quality_risk": "usable_if_pit_dates_valid" if path else "needs_fetch_or_cache",
                "notes": notes,
            }
        )

    add("tushare_daily_basic", "tushare_daily_basic", daily_path, script_only=True, notes=f"local_token_present={token_present}")
    add("tushare_stock_basic", "tushare_stock_basic", stock_path, script_only=False, notes="Used for industry mapping if cached.")
    add("akshare_lg_indicator", "akshare_lg_indicator", None, notes="Fallback only; not the primary source for this adapter.")
    add("akshare_baidu_valuation", "akshare_baidu_valuation", None, notes="Exploration-only fallback; PIT history must be verified.")
    add("derived_market_cap_only", "derived_market_cap_only", None, notes="Previous adapter provided market-cap context only.")
    if not daily_path:
        add("daily_basic_cache_missing", "source_missing", None, notes="No local daily_basic CSV cache detected.")
    return pd.DataFrame(rows, columns=INVENTORY_COLUMNS)


def build_daily_basic_fetch_plan(watchlist: pd.DataFrame) -> pd.DataFrame:
    if watchlist.empty:
        return _empty(FETCH_PLAN_COLUMNS)
    research_dates = sorted(pd.to_datetime(watchlist["first_admission_date"], errors="coerce").dropna().dt.normalize().unique())
    if not research_dates:
        research_dates = [pd.Timestamp("2026-06-29")]
    asset_count = int(watchlist["asset_id"].nunique())
    rows = []
    fields = "ts_code,trade_date,pe,pe_ttm,pb,ps,ps_ttm,total_mv,circ_mv,turnover_rate,turnover_rate_f,volume_ratio,dv_ratio,dv_ttm,total_share,float_share,free_share"
    for idx, trade_date in enumerate(research_dates, start=1):
        start_date = (pd.Timestamp(trade_date) - pd.Timedelta(days=365 * 5)).strftime("%Y%m%d")
        end_date = pd.Timestamp(trade_date).strftime("%Y%m%d")
        rows.append(
            {
                "fetch_batch_id": f"daily_basic_{idx:04d}_{end_date}",
                "trade_date": pd.Timestamp(trade_date).strftime("%Y-%m-%d"),
                "start_date": start_date,
                "end_date": end_date,
                "asset_scope": "standard_watchlist_plus_history",
                "target_asset_count": asset_count,
                "expected_rows": asset_count * 1250,
                "source_api": "tushare.daily_basic",
                "fields": fields,
                "requires_token": True,
                "estimated_calls": 1250,
                "rate_limit_note": "Prefer full-market by trade_date batches; persist local CSV before rerunning this adapter.",
                "fetch_status": "planned_not_executed",
                "skip_reason": "research_adapter_does_not_force_download",
                "human_action_required": True,
            }
        )
    return pd.DataFrame(rows, columns=FETCH_PLAN_COLUMNS)


def _normalize_daily_basic(daily_basic: pd.DataFrame) -> pd.DataFrame:
    if daily_basic.empty:
        return daily_basic.copy()
    frame = daily_basic.copy()
    if "asset_id" not in frame.columns and "ts_code" in frame.columns:
        frame["asset_id"] = frame["ts_code"].astype(str).map(ts_code_to_asset_id)
    if "ts_code" not in frame.columns and "asset_id" in frame.columns:
        frame["ts_code"] = frame["asset_id"].astype(str).map(asset_id_to_ts_code)
    frame["_daily_date"] = frame["trade_date"].map(_date) if "trade_date" in frame.columns else pd.NaT
    for col in DAILY_BASIC_FIELDS:
        if col in frame.columns:
            frame[col] = pd.to_numeric(frame[col], errors="coerce")
    return frame


def _missing_daily_fields(row: pd.Series) -> str:
    required = ["pe", "pe_ttm", "pb", "ps", "ps_ttm", "total_mv", "circ_mv"]
    missing = [field for field in required if field not in row.index or pd.isna(row.get(field))]
    return "|".join(missing) if missing else "none"


def build_daily_basic_raw_candidate_matches(watchlist: pd.DataFrame, daily_basic: pd.DataFrame) -> pd.DataFrame:
    if watchlist.empty or daily_basic.empty:
        return _empty(RAW_COLUMNS)
    research_date = _research_date(watchlist)
    frame = _normalize_daily_basic(daily_basic)
    watch_assets = set(watchlist["asset_id"].astype(str))
    frame = frame[frame["asset_id"].astype(str).isin(watch_assets)].copy()
    if frame.empty:
        return _empty(RAW_COLUMNS)
    meta = watchlist[["asset_id", "symbol", "name"]].drop_duplicates("asset_id")
    frame = frame.merge(meta, on="asset_id", how="left", suffixes=("", "_watch"))
    lookahead = frame["_daily_date"].gt(research_date).fillna(True)
    rows = []
    for _, row in frame.iterrows():
        rows.append(
            {
                "asset_id": row.get("asset_id"),
                "symbol": row.get("symbol_watch", row.get("symbol", "")),
                "name": row.get("name_watch", row.get("name", "")),
                "ts_code": row.get("ts_code", ""),
                "trade_date": _date_str(row.get("trade_date")),
                "source_name": "local_daily_basic_cache",
                "raw_source_path_or_table": "local_cache",
                "matched_by": "asset_id_ts_code",
                "is_pit_valid": not bool(lookahead.loc[row.name]),
                "lookahead_violation": bool(lookahead.loc[row.name]),
                "available_field_count": int(pd.Series(row).notna().sum()),
                "missing_required_fields": _missing_daily_fields(row),
                "data_quality_status": "pit_valid" if not bool(lookahead.loc[row.name]) else "invalid_future_trade_date",
            }
        )
    return pd.DataFrame(rows, columns=RAW_COLUMNS)


def build_structured_daily_basic(watchlist: pd.DataFrame, daily_basic: pd.DataFrame) -> pd.DataFrame:
    if watchlist.empty or daily_basic.empty:
        return _empty(STRUCTURED_COLUMNS)
    research_date = _research_date(watchlist)
    frame = _normalize_daily_basic(daily_basic)
    watch = watchlist[["asset_id", "symbol", "name"]].drop_duplicates("asset_id").copy()
    rows = []
    for meta in watch.itertuples(index=False):
        asset_id = str(meta.asset_id)
        asset_rows = frame[(frame["asset_id"].astype(str).eq(asset_id)) & frame["_daily_date"].le(research_date)].copy()
        asset_rows = asset_rows.dropna(subset=["_daily_date"]).sort_values("_daily_date")
        if asset_rows.empty:
            continue
        latest = asset_rows.iloc[-1]
        missing = _missing_daily_fields(latest)
        gap = int((research_date - latest["_daily_date"]).days)
        has_core = all(field in latest.index and pd.notna(latest.get(field)) for field in ["pe_ttm", "pb", "ps_ttm"])
        status = "pit_valid_complete" if missing == "none" else "degraded_missing_daily_basic_fields"
        if gap > 15:
            status = "degraded_stale_daily_basic"
        rows.append(
            {
                "research_trade_date": research_date.strftime("%Y-%m-%d"),
                "asset_id": asset_id,
                "symbol": str(meta.symbol),
                "name": str(meta.name),
                "ts_code": latest.get("ts_code", asset_id_to_ts_code(asset_id)),
                "daily_basic_trade_date": latest["_daily_date"].strftime("%Y-%m-%d"),
                "source_type": "tushare_daily_basic",
                "is_pit_valid": True,
                "lookahead_violation": False,
                **{field: latest.get(field, pd.NA) for field in DAILY_BASIC_FIELDS},
                "market_cap_source": "total_mv" if pd.notna(latest.get("total_mv", pd.NA)) else "missing",
                "valuation_data_status": "pe_pb_ps_available" if has_core else "degraded_partial_daily_basic",
                "missing_fields": missing,
                "conflict_flags": "none",
                "data_quality_status": status,
                "rule_version": RULE_VERSION,
            }
        )
    return pd.DataFrame(rows, columns=STRUCTURED_COLUMNS)


def _percentile(history: pd.Series, value: Any, *, positive_only: bool = False) -> float | pd.NA:
    current = _num(value)
    if current is None:
        return pd.NA
    if positive_only and current <= 0:
        return pd.NA
    hist = pd.to_numeric(history, errors="coerce").dropna()
    if positive_only:
        hist = hist[hist > 0]
    if hist.empty:
        return pd.NA
    return float(hist.le(current).sum() / len(hist))


def _history_quality(days: int) -> str:
    if days >= 365 * 5:
        return "full_5y_window"
    if days >= 365 * 3:
        return "full_3y_partial_5y_window"
    if days >= 365:
        return "full_1y_partial_3y_window"
    if days > 0:
        return "short_available_window"
    return "missing_history"


def build_daily_basic_percentiles(
    watchlist: pd.DataFrame, daily_basic: pd.DataFrame, structured: pd.DataFrame
) -> pd.DataFrame:
    if watchlist.empty or daily_basic.empty or structured.empty:
        return _empty(PERCENTILE_COLUMNS)
    frame = _normalize_daily_basic(daily_basic)
    rows = []
    for item in structured.itertuples(index=False):
        research_date = _date(item.research_trade_date)
        asset_rows = frame[(frame["asset_id"].astype(str).eq(str(item.asset_id))) & frame["_daily_date"].le(research_date)].copy()
        asset_rows = asset_rows.dropna(subset=["_daily_date"]).sort_values("_daily_date")
        if asset_rows.empty:
            continue
        latest_date = _date(item.daily_basic_trade_date)
        if pd.isna(latest_date):
            latest_date = research_date
        def hist(days: int) -> pd.DataFrame:
            return asset_rows[asset_rows["_daily_date"].ge(research_date - pd.Timedelta(days=days))]

        window_days = int((asset_rows["_daily_date"].max() - asset_rows["_daily_date"].min()).days) if len(asset_rows) > 1 else 0
        missing = []
        row = {
            "research_trade_date": item.research_trade_date,
            "asset_id": item.asset_id,
            "symbol": item.symbol,
            "name": item.name,
            "ts_code": item.ts_code,
            "daily_basic_trade_date": item.daily_basic_trade_date,
            "pe_ttm": item.pe_ttm,
            "pb": item.pb,
            "ps_ttm": item.ps_ttm,
            "total_mv": item.total_mv,
            "circ_mv": item.circ_mv,
            "pe_ttm_percentile_1y": _percentile(hist(365).get("pe_ttm", pd.Series(dtype=float)), item.pe_ttm, positive_only=True),
            "pe_ttm_percentile_3y": _percentile(hist(365 * 3).get("pe_ttm", pd.Series(dtype=float)), item.pe_ttm, positive_only=True),
            "pe_ttm_percentile_5y": _percentile(hist(365 * 5).get("pe_ttm", pd.Series(dtype=float)), item.pe_ttm, positive_only=True),
            "pb_percentile_1y": _percentile(hist(365).get("pb", pd.Series(dtype=float)), item.pb),
            "pb_percentile_3y": _percentile(hist(365 * 3).get("pb", pd.Series(dtype=float)), item.pb),
            "pb_percentile_5y": _percentile(hist(365 * 5).get("pb", pd.Series(dtype=float)), item.pb),
            "ps_ttm_percentile_1y": _percentile(hist(365).get("ps_ttm", pd.Series(dtype=float)), item.ps_ttm),
            "ps_ttm_percentile_3y": _percentile(hist(365 * 3).get("ps_ttm", pd.Series(dtype=float)), item.ps_ttm),
            "ps_ttm_percentile_5y": _percentile(hist(365 * 5).get("ps_ttm", pd.Series(dtype=float)), item.ps_ttm),
            "total_mv_percentile_3y": _percentile(hist(365 * 3).get("total_mv", pd.Series(dtype=float)), item.total_mv),
            "circ_mv_percentile_3y": _percentile(hist(365 * 3).get("circ_mv", pd.Series(dtype=float)), item.circ_mv),
            "history_window_days_available": window_days,
            "history_window_quality": _history_quality(window_days),
            "percentile_data_status": "available_window_percentile" if window_days > 0 else "missing_history",
        }
        for col in [
            "pe_ttm_percentile_1y",
            "pe_ttm_percentile_3y",
            "pe_ttm_percentile_5y",
            "pb_percentile_3y",
            "ps_ttm_percentile_3y",
        ]:
            if pd.isna(row[col]):
                missing.append(col)
        row["missing_fields"] = "|".join(missing) if missing else "none"
        rows.append(row)
    return pd.DataFrame(rows, columns=PERCENTILE_COLUMNS)


def _normalize_stock_basic(stock_basic: pd.DataFrame) -> pd.DataFrame:
    if stock_basic.empty:
        return stock_basic.copy()
    frame = stock_basic.copy()
    if "ts_code" not in frame.columns and "symbol" in frame.columns:
        frame["ts_code"] = frame["symbol"].astype(str)
    if "industry" not in frame.columns:
        frame["industry"] = pd.NA
    return frame


def build_daily_basic_industry_outputs(
    watchlist: pd.DataFrame, daily_basic: pd.DataFrame, stock_basic: pd.DataFrame, structured: pd.DataFrame
) -> pd.DataFrame:
    if watchlist.empty or daily_basic.empty or structured.empty:
        return _empty(INDUSTRY_COLUMNS)
    stock = _normalize_stock_basic(stock_basic)
    if stock.empty or "industry" not in stock.columns:
        rows = []
        for item in structured.itertuples(index=False):
            rows.append(
                {
                    "research_trade_date": item.research_trade_date,
                    "asset_id": item.asset_id,
                    "symbol": item.symbol,
                    "name": item.name,
                    "ts_code": item.ts_code,
                    "industry": "missing",
                    "industry_peer_count": 0,
                    "pe_ttm": item.pe_ttm,
                    "pb": item.pb,
                    "ps_ttm": item.ps_ttm,
                    "pe_ttm_industry_percentile": pd.NA,
                    "pb_industry_percentile": pd.NA,
                    "ps_ttm_industry_percentile": pd.NA,
                    "market_cap_industry_percentile": pd.NA,
                    "industry_comparison_status": "missing_stock_basic_industry",
                    "missing_fields": "industry|industry_peer_daily_basic",
                }
            )
        return pd.DataFrame(rows, columns=INDUSTRY_COLUMNS)

    frame = _normalize_daily_basic(daily_basic)
    industry_by_code = stock.drop_duplicates("ts_code").set_index("ts_code")["industry"].to_dict()
    frame["industry"] = frame["ts_code"].map(industry_by_code)
    rows = []
    for item in structured.itertuples(index=False):
        industry = industry_by_code.get(str(item.ts_code), "missing")
        latest_date = _date(item.daily_basic_trade_date)
        peers = frame[(frame["_daily_date"].eq(latest_date)) & frame["industry"].eq(industry)].copy()
        peer_count = int(peers["ts_code"].nunique()) if industry != "missing" else 0
        status = "industry_comparison_available" if peer_count >= 2 else "degraded_small_or_missing_peer_set"
        rows.append(
            {
                "research_trade_date": item.research_trade_date,
                "asset_id": item.asset_id,
                "symbol": item.symbol,
                "name": item.name,
                "ts_code": item.ts_code,
                "industry": industry,
                "industry_peer_count": peer_count,
                "pe_ttm": item.pe_ttm,
                "pb": item.pb,
                "ps_ttm": item.ps_ttm,
                "pe_ttm_industry_percentile": _percentile(peers.get("pe_ttm", pd.Series(dtype=float)), item.pe_ttm, positive_only=True),
                "pb_industry_percentile": _percentile(peers.get("pb", pd.Series(dtype=float)), item.pb),
                "ps_ttm_industry_percentile": _percentile(peers.get("ps_ttm", pd.Series(dtype=float)), item.ps_ttm),
                "market_cap_industry_percentile": _percentile(peers.get("total_mv", pd.Series(dtype=float)), item.total_mv),
                "industry_comparison_status": status,
                "missing_fields": "none" if status == "industry_comparison_available" else "industry_peer_daily_basic",
            }
        )
    return pd.DataFrame(rows, columns=INDUSTRY_COLUMNS)


def classify_pe_context(pe_ttm: float | None, percentile: float | None) -> str:
    if pe_ttm is None or pd.isna(pe_ttm):
        return "valuation_missing"
    if pe_ttm <= 0:
        return "valuation_loss_making_or_not_meaningful"
    if percentile is None or pd.isna(percentile):
        return "valuation_missing"
    if percentile <= 0.35:
        return "valuation_low"
    if percentile <= 0.70:
        return "valuation_mid"
    return "valuation_high"


def _support_level(row: dict[str, Any]) -> str:
    has_core = all(bool(row.get(field)) for field in ["has_pe_ttm", "has_pb", "has_ps_ttm"])
    if has_core and row.get("has_3y_percentile") and row.get("has_industry_percentile"):
        return "pe_pb_ps_with_history_and_industry"
    if has_core and row.get("has_3y_percentile"):
        return "pe_pb_ps_with_history"
    if has_core:
        return "pe_pb_ps_current_only"
    if row.get("has_total_mv"):
        return "market_cap_only"
    return "missing"


def build_daily_basic_asset_coverage(
    watchlist: pd.DataFrame,
    daily_basic: pd.DataFrame,
    structured: pd.DataFrame,
    percentiles: pd.DataFrame,
    industry: pd.DataFrame,
) -> pd.DataFrame:
    frame = _normalize_daily_basic(daily_basic)
    by_struct = structured.set_index("asset_id").to_dict("index") if not structured.empty else {}
    by_pct = percentiles.set_index("asset_id").to_dict("index") if not percentiles.empty else {}
    by_ind = industry.set_index("asset_id").to_dict("index") if not industry.empty else {}
    rows = []
    for item in watchlist[["asset_id", "symbol", "name"]].drop_duplicates("asset_id").itertuples(index=False):
        asset_id = str(item.asset_id)
        ts_code = asset_id_to_ts_code(asset_id)
        records = frame[frame["asset_id"].astype(str).eq(asset_id)] if not frame.empty else pd.DataFrame()
        pit_records = records[records["_daily_date"].le(_research_date(watchlist))] if not records.empty else pd.DataFrame()
        struct = by_struct.get(asset_id, {})
        pct = by_pct.get(asset_id, {})
        ind = by_ind.get(asset_id, {})
        row = {
            "asset_id": asset_id,
            "symbol": str(item.symbol),
            "name": str(item.name),
            "ts_code": ts_code,
            "in_standard_watchlist": True,
            "daily_basic_record_count": int(len(records)),
            "pit_valid_record_count": int(len(pit_records)),
            "latest_daily_basic_trade_date": struct.get("daily_basic_trade_date", "missing"),
            "has_pe": pd.notna(struct.get("pe")) and struct.get("pe") != "",
            "has_pe_ttm": pd.notna(struct.get("pe_ttm")) and struct.get("pe_ttm") != "",
            "has_pb": pd.notna(struct.get("pb")) and struct.get("pb") != "",
            "has_ps": pd.notna(struct.get("ps")) and struct.get("ps") != "",
            "has_ps_ttm": pd.notna(struct.get("ps_ttm")) and struct.get("ps_ttm") != "",
            "has_total_mv": pd.notna(struct.get("total_mv")) and struct.get("total_mv") != "",
            "has_circ_mv": pd.notna(struct.get("circ_mv")) and struct.get("circ_mv") != "",
            "has_1y_percentile": pd.notna(pct.get("pe_ttm_percentile_1y")) or pd.notna(pct.get("pb_percentile_1y")) or pd.notna(pct.get("ps_ttm_percentile_1y")),
            "has_3y_percentile": pd.notna(pct.get("pe_ttm_percentile_3y")) or pd.notna(pct.get("pb_percentile_3y")) or pd.notna(pct.get("ps_ttm_percentile_3y")),
            "has_5y_percentile": pd.notna(pct.get("pe_ttm_percentile_5y")) or pd.notna(pct.get("pb_percentile_5y")) or pd.notna(pct.get("ps_ttm_percentile_5y")),
            "has_industry_percentile": pd.notna(ind.get("pb_industry_percentile")) or pd.notna(ind.get("ps_ttm_industry_percentile")),
            "coverage_status": "daily_basic_supported" if struct else "daily_basic_missing",
            "human_review_required": True,
        }
        row["valuation_support_level"] = _support_level(row)
        rows.append(row)
    return pd.DataFrame(rows, columns=COVERAGE_COLUMNS)


def build_daily_basic_field_coverage_audit(
    structured: pd.DataFrame, percentiles: pd.DataFrame, industry: pd.DataFrame, total_assets: int | None = None
) -> pd.DataFrame:
    total = total_assets or max(len(structured), len(percentiles), len(industry), 0)
    fields = [
        "pe",
        "pe_ttm",
        "pb",
        "ps",
        "ps_ttm",
        "total_mv",
        "circ_mv",
        "turnover_rate",
        "turnover_rate_f",
        "volume_ratio",
        "dv_ratio",
        "dv_ttm",
        "total_share",
        "float_share",
        "free_share",
        "pe_ttm_percentile_1y",
        "pe_ttm_percentile_3y",
        "pe_ttm_percentile_5y",
        "pb_percentile_3y",
        "ps_ttm_percentile_3y",
        "industry_percentiles",
    ]
    rows = []
    for field in fields:
        if field == "industry_percentiles":
            non = 0 if industry.empty else int(
                industry[["pe_ttm_industry_percentile", "pb_industry_percentile", "ps_ttm_industry_percentile"]]
                .notna()
                .any(axis=1)
                .sum()
            )
        elif field in structured.columns:
            non = int(structured[field].notna().sum())
        elif field in percentiles.columns:
            non = int(percentiles[field].notna().sum())
        else:
            non = 0
        missing = max(total - non, 0)
        rows.append(
            {
                "field_name": field,
                "non_missing_count": non,
                "missing_count": missing,
                "coverage_ratio": round(non / total, 6) if total else 0.0,
                "quality_note": "available" if non else "missing",
            }
        )
    return pd.DataFrame(rows, columns=FIELD_AUDIT_COLUMNS)


def _previous_support_lookup() -> dict[str, bool]:
    if not VALUATION_STRUCTURED_PATH.exists():
        return {}
    try:
        frame = pd.read_csv(VALUATION_STRUCTURED_PATH)
    except Exception:
        return {}
    return {str(row.asset_id): True for row in frame.itertuples(index=False)}


def build_watchlist_daily_basic_valuation_gap_patch(
    watchlist: pd.DataFrame,
    coverage: pd.DataFrame,
    structured: pd.DataFrame,
    percentiles: pd.DataFrame,
    industry: pd.DataFrame,
) -> pd.DataFrame:
    by_cov = coverage.set_index("asset_id").to_dict("index") if not coverage.empty else {}
    by_struct = structured.set_index("asset_id").to_dict("index") if not structured.empty else {}
    by_pct = percentiles.set_index("asset_id").to_dict("index") if not percentiles.empty else {}
    by_ind = industry.set_index("asset_id").to_dict("index") if not industry.empty else {}
    previous = _previous_support_lookup()
    rows = []
    for item in watchlist[["asset_id", "symbol", "name"]].drop_duplicates("asset_id").itertuples(index=False):
        asset_id = str(item.asset_id)
        cov = by_cov.get(asset_id, {})
        struct = by_struct.get(asset_id, {})
        pct = by_pct.get(asset_id, {})
        ind = by_ind.get(asset_id, {})
        supported = cov.get("valuation_support_level", "missing") not in {"missing", ""}
        if supported and cov.get("has_pe_ttm") and cov.get("has_pb") and cov.get("has_ps_ttm"):
            recommended = "update_report_daily_basic_valuation"
            summary = "PE/PB/PS context available for research review."
        elif supported:
            recommended = "review_pe_pb_ps_context"
            summary = "Partial daily_basic context available; missing fields remain."
        else:
            recommended = "no_daily_basic_support"
            summary = "daily_basic source missing for this asset."
        rows.append(
            {
                "asset_id": asset_id,
                "symbol": str(item.symbol),
                "name": str(item.name),
                "previous_valuation_support": bool(previous.get(asset_id, False)),
                "new_daily_basic_support": bool(supported),
                "daily_basic_record_count": cov.get("daily_basic_record_count", 0),
                "latest_daily_basic_trade_date": cov.get("latest_daily_basic_trade_date", "missing"),
                "pe_ttm": struct.get("pe_ttm", ""),
                "pb": struct.get("pb", ""),
                "ps_ttm": struct.get("ps_ttm", ""),
                "total_mv": struct.get("total_mv", ""),
                "circ_mv": struct.get("circ_mv", ""),
                "pe_ttm_percentile_3y": pct.get("pe_ttm_percentile_3y", ""),
                "pb_percentile_3y": pct.get("pb_percentile_3y", ""),
                "ps_ttm_percentile_3y": pct.get("ps_ttm_percentile_3y", ""),
                "pe_ttm_industry_percentile": ind.get("pe_ttm_industry_percentile", ""),
                "pb_industry_percentile": ind.get("pb_industry_percentile", ""),
                "ps_ttm_industry_percentile": ind.get("ps_ttm_industry_percentile", ""),
                "valuation_support_level": cov.get("valuation_support_level", "missing"),
                "new_source_count_delta": 1 if supported else 0,
                "new_evidence_tags": "daily_basic_pe_pb_ps" if supported else "missing_daily_basic",
                "new_risk_flags": "pe_not_meaningful" if classify_pe_context(_num(struct.get("pe_ttm")), _num(pct.get("pe_ttm_percentile_3y"))) == "valuation_loss_making_or_not_meaningful" else "none",
                "report_patch_summary": summary,
                "still_missing_daily_basic": not supported,
                "recommended_report_update": recommended,
                "human_review_required": True,
            }
        )
    return pd.DataFrame(rows, columns=PATCH_COLUMNS)


def build_daily_basic_quality_audit(
    inventory: pd.DataFrame,
    fetch_plan: pd.DataFrame,
    raw: pd.DataFrame,
    structured: pd.DataFrame,
    percentiles: pd.DataFrame,
    industry: pd.DataFrame,
    coverage: pd.DataFrame,
) -> pd.DataFrame:
    standard_count = int(len(coverage)) if not coverage.empty else 0
    has = lambda col: int(coverage[col].sum()) if col in coverage.columns and not coverage.empty else 0
    discovered = inventory["existing_in_project"].astype(str).isin({"True", "script_only"}) if not inventory.empty else pd.Series(dtype=bool)
    daily_basic_sources = int((inventory["source_type"].eq("tushare_daily_basic") & discovered).sum()) if not inventory.empty else 0
    stock_basic_sources = int((inventory["source_type"].eq("tushare_stock_basic") & discovered).sum()) if not inventory.empty else 0
    lookahead = int(raw["lookahead_violation"].fillna(False).astype(bool).sum()) if not raw.empty else 0
    pit_valid = float(raw["is_pit_valid"].fillna(False).astype(bool).mean()) if not raw.empty else 0.0
    negative_pe = int((pd.to_numeric(structured.get("pe_ttm", pd.Series(dtype=float)), errors="coerce") <= 0).sum()) if not structured.empty else 0
    rows = [
        ("detected_daily_basic_sources", daily_basic_sources, "local cache or script-only source inventory"),
        ("detected_stock_basic_sources", stock_basic_sources, "industry mapping inventory"),
        ("raw_daily_basic_rows", len(raw), "matched raw candidate rows"),
        ("matched_daily_basic_rows", len(raw), "matched to standard watchlist"),
        ("structured_daily_basic_rows", len(structured), "latest PIT row per asset"),
        ("standard_watchlist_asset_count", standard_count, "standard research watchlist"),
        ("assets_with_daily_basic_support", int(coverage["valuation_support_level"].ne("missing").sum()) if not coverage.empty else 0, "asset coverage"),
        ("daily_basic_coverage_ratio", round((coverage["valuation_support_level"].ne("missing").sum() / standard_count), 6) if standard_count else 0.0, "asset coverage"),
        ("PIT_valid_ratio", pit_valid, "raw matched rows"),
        ("lookahead_violation_rows", lookahead, "must remain zero"),
        ("assets_with_pe_ttm", has("has_pe_ttm"), "asset coverage"),
        ("assets_with_pb", has("has_pb"), "asset coverage"),
        ("assets_with_ps_ttm", has("has_ps_ttm"), "asset coverage"),
        ("assets_with_total_mv", has("has_total_mv"), "asset coverage"),
        ("assets_with_circ_mv", has("has_circ_mv"), "asset coverage"),
        ("assets_with_1y_percentile", has("has_1y_percentile"), "asset coverage"),
        ("assets_with_3y_percentile", has("has_3y_percentile"), "asset coverage"),
        ("assets_with_5y_percentile", has("has_5y_percentile"), "asset coverage"),
        ("assets_with_industry_comparison", has("has_industry_percentile"), "asset coverage"),
        ("negative_pe_rows", negative_pe, "not meaningful for low context"),
        ("not_meaningful_pe_rows", negative_pe, "negative or zero PE"),
        ("degraded_rows", int(structured["data_quality_status"].astype(str).str.contains("degraded").sum()) if not structured.empty else standard_count, "missing or no cache"),
        ("invalid_rows", lookahead, "future rows excluded from structured outputs"),
        ("fetch_plan_rows", len(fetch_plan), "planned batches if cache is missing"),
        ("token_required", bool(len(fetch_plan)), "Tushare token required for fetch execution"),
        ("manual_action_required", bool(fetch_plan["human_action_required"].any()) if not fetch_plan.empty else False, "download/cache step needed if no local data"),
    ]
    return pd.DataFrame(rows, columns=QUALITY_AUDIT_COLUMNS)


def _metric(audit: pd.DataFrame, name: str, default: Any = 0) -> Any:
    if audit.empty or name not in set(audit["metric"]):
        return default
    return audit.loc[audit["metric"].eq(name), "value"].iloc[0]


def _git_info(project_root: Path) -> dict[str, str]:
    def run(args: list[str]) -> str:
        try:
            return subprocess.check_output(args, cwd=project_root, text=True, stderr=subprocess.STDOUT).strip()
        except Exception as exc:
            return f"unavailable: {exc}"

    status = run(["git", "status", "--short", "src/stock_research/tech_bottleneck_v1.py", "src/stock_research/tech_bottleneck_candidates.py"])
    stat_lines = []
    for rel in ["src/stock_research/tech_bottleneck_v1.py", "src/stock_research/tech_bottleneck_candidates.py"]:
        path = project_root / rel
        stat_lines.append(f"{rel}: exists={path.exists()}")
    return {
        "repo_root": run(["git", "rev-parse", "--show-toplevel"]),
        "formal_strategy_status": status or "clean_tracked_or_absent",
        "formal_strategy_stat": "; ".join(stat_lines),
    }


def render_main_report(
    *,
    inventory: pd.DataFrame,
    fetch_plan: pd.DataFrame,
    structured: pd.DataFrame,
    percentiles: pd.DataFrame,
    industry: pd.DataFrame,
    coverage: pd.DataFrame,
    field_audit: pd.DataFrame,
    patch: pd.DataFrame,
    quality_audit: pd.DataFrame,
    git_info: dict[str, str],
) -> str:
    standard_count = int(_metric(quality_audit, "standard_watchlist_asset_count", len(coverage)))
    support = int(_metric(quality_audit, "assets_with_daily_basic_support", 0))
    ratio = _metric(quality_audit, "daily_basic_coverage_ratio", 0)
    lookahead = int(float(_metric(quality_audit, "lookahead_violation_rows", 0)))
    pe = int(_metric(quality_audit, "assets_with_pe_ttm", 0))
    pb = int(_metric(quality_audit, "assets_with_pb", 0))
    ps = int(_metric(quality_audit, "assets_with_ps_ttm", 0))
    total_mv = int(_metric(quality_audit, "assets_with_total_mv", 0))
    circ_mv = int(_metric(quality_audit, "assets_with_circ_mv", 0))
    industry_count = int(_metric(quality_audit, "assets_with_industry_comparison", 0))
    fetch_rows = int(_metric(quality_audit, "fetch_plan_rows", len(fetch_plan)))
    inventory_summary = inventory[["source_type", "existing_in_project", "pit_ready", "detected_path_or_table"]].to_markdown(index=False) if not inventory.empty else "missing"
    field_summary = field_audit.head(20).to_markdown(index=False) if not field_audit.empty else "missing"
    patch_summary = patch["recommended_report_update"].value_counts(dropna=False).reset_index()
    patch_table = patch_summary.to_markdown(index=False) if not patch_summary.empty else "missing"
    text = f"""# Tech Bottleneck Daily Basic PE/PB/PS Source Adapter v1

## 1. Executive Summary

- 本轮只做 research-only daily_basic 估值源适配，没有接入正式策略、dashboard 或任何自动执行流程。
- 可用 daily_basic cache: {bool(len(structured))}; stock_basic industry mapping: {industry_count > 0}.
- standard watchlist asset count: {standard_count}.
- PE/PB/PS support assets: {support}; daily_basic coverage ratio: {ratio}.
- pe_ttm / pb / ps_ttm / total_mv / circ_mv coverage: {pe} / {pb} / {ps} / {total_mv} / {circ_mv}.
- 1y / 3y / 5y 历史分位覆盖: {_metric(quality_audit, "assets_with_1y_percentile", 0)} / {_metric(quality_audit, "assets_with_3y_percentile", 0)} / {_metric(quality_audit, "assets_with_5y_percentile", 0)}.
- industry valuation comparison coverage: {industry_count}.
- lookahead_violation_rows: {lookahead}.
- fetch plan rows: {fetch_rows}; token_required: {_metric(quality_audit, "token_required", False)}; manual_action_required: {_metric(quality_audit, "manual_action_required", False)}.
- PE/PB/PS 字段仅用于观察池研究上下文和人工复盘，不能作为自动执行依据。

## 2. Source Inventory

{inventory_summary}

## 3. Fetch Plan

如果本地没有 daily_basic cache，本轮输出 `daily_basic_fetch_plan.csv`。推荐先按交易日拉取 Tushare `daily_basic` 全市场数据并持久化为本地 CSV，再重跑本 adapter。`stock_basic` 只用于 `ts_code / symbol / name / industry / list_date` 映射。

## 4. Matching and PIT Validation

资产映射使用 `CN:SZ:002028 -> 002028.SZ` 与 `CN:SH:600000 -> 600000.SH`。每个资产只选择 `daily_basic_trade_date <= research_trade_date` 的最近记录；未来日期只进入 raw audit，不进入 structured outputs。

## 5. Structured Daily Basic Fields

本轮目标字段包括 `pe`, `pe_ttm`, `pb`, `ps`, `ps_ttm`, `total_mv`, `circ_mv`，以及 Tushare daily_basic 的换手、股本和股息率字段。缺失字段标记为 missing，不做极端惩罚，也不使用旧的 missing penalty。

## 6. Historical Percentile Calculation

1y / 3y / 5y 分位只使用研究日以前的历史 daily_basic。窗口不足时可计算 available-window percentile，但标记 `history_window_quality`。负 PE 或缺失 PE 标记为 not meaningful，不解释为低估。

## 7. Industry Valuation Calculation

行业分位依赖 `stock_basic.industry`。如果行业 mapping 缺失或同业样本不足，输出 degraded / missing，不编造行业结论。

## 8. Standard Watchlist Coverage

- assets with daily_basic support: {support} / {standard_count}
- assets with industry comparison: {industry_count} / {standard_count}
- structured daily_basic rows: {len(structured)}
- raw matched rows: {len(patch) if len(structured) else 0}

## 9. Field Coverage and Missing Data

{field_summary}

## 10. Report Patch Candidates

{patch_table}

## 11. What This Layer Does Not Do

- 不产生自动执行提示。
- 不改变 Top5。
- 不改变正式策略。
- 不研究 trigger / holding / exit。
- 不使用 evidence multiplier。
- 不输出任何执行类指令。
- 不把 PE/PB/PS score 当作自动执行依据。

## 12. Recommended Next Step

如果本地 daily_basic 已可用且 coverage 明显提升，下一步建议 `tech_bottleneck_watchlist_report_daily_basic_valuation_patch_v1`。如果本地 daily_basic 不可用，下一步先执行 `tech_bottleneck_daily_basic_fetch_execution_v1`，把 Tushare daily_basic 和 stock_basic 持久化到本地 research cache 后重跑本 adapter。

## 13. Appendix

- generated files: 11 CSV/Markdown files under `{OUTPUT_DIR}`.
- git repo root: {git_info.get("repo_root", "unknown")}.
- formal strategy file status: {git_info.get("formal_strategy_status", "unknown")}.
- formal strategy stat: {git_info.get("formal_strategy_stat", "unknown")}.
- key assumption: this adapter does not force network download; it consumes local cache or writes a fetch plan.
- uncertainty: Tushare token exists locally only if configured; token value is never printed.
"""
    return text


def write_outputs(project_root: Path, output_dir: Path = OUTPUT_DIR) -> dict[str, pd.DataFrame]:
    output_dir.mkdir(parents=True, exist_ok=True)
    watchlist = load_watchlist()
    daily_basic, daily_path = _read_first_csv(_candidate_daily_basic_paths(project_root), {"pe_ttm", "pb", "ps_ttm", "total_mv", "circ_mv"})
    stock_basic, _stock_path = _read_first_csv(_candidate_stock_basic_paths(project_root), {"industry", "list_date"})

    inventory = build_daily_basic_source_inventory(project_root)
    fetch_plan = build_daily_basic_fetch_plan(watchlist)
    raw = build_daily_basic_raw_candidate_matches(watchlist, daily_basic)
    structured = build_structured_daily_basic(watchlist, daily_basic)
    percentiles = build_daily_basic_percentiles(watchlist, daily_basic, structured)
    industry = build_daily_basic_industry_outputs(watchlist, daily_basic, stock_basic, structured)
    coverage = build_daily_basic_asset_coverage(watchlist, daily_basic, structured, percentiles, industry)
    field_audit = build_daily_basic_field_coverage_audit(structured, percentiles, industry, total_assets=len(watchlist))
    patch = build_watchlist_daily_basic_valuation_gap_patch(watchlist, coverage, structured, percentiles, industry)
    quality_audit = build_daily_basic_quality_audit(inventory, fetch_plan, raw, structured, percentiles, industry, coverage)
    report = render_main_report(
        inventory=inventory,
        fetch_plan=fetch_plan,
        structured=structured,
        percentiles=percentiles,
        industry=industry,
        coverage=coverage,
        field_audit=field_audit,
        patch=patch,
        quality_audit=quality_audit,
        git_info=_git_info(project_root),
    )

    outputs = {
        "daily_basic_source_inventory.csv": inventory,
        "daily_basic_fetch_plan.csv": fetch_plan,
        "daily_basic_raw_candidate_matches.csv": raw,
        "daily_basic_structured_outputs.csv": structured,
        "daily_basic_percentile_outputs.csv": percentiles,
        "daily_basic_industry_valuation_outputs.csv": industry,
        "daily_basic_asset_coverage.csv": coverage,
        "daily_basic_field_coverage_audit.csv": field_audit,
        "watchlist_daily_basic_valuation_gap_patch.csv": patch,
        "daily_basic_quality_audit.csv": quality_audit,
    }
    for name, frame in outputs.items():
        frame.to_csv(output_dir / name, index=False)
    (output_dir / "daily_basic_pe_pb_ps_source_adapter_v1.md").write_text(report, encoding="utf-8")
    return outputs


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    outputs = write_outputs(project_root)
    audit = outputs["daily_basic_quality_audit.csv"]
    print(audit.to_string(index=False))


if __name__ == "__main__":
    main()
