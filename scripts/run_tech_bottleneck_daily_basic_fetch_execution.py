import hashlib
import json
import os
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import pandas as pd


RULE_VERSION = "tech_bottleneck_daily_basic_fetch_execution_v1"
PROJECT_ROOT = Path("/Users/xiwei/stock_research")
INPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_daily_basic_pe_pb_ps_source_adapter_v1"
FETCH_PLAN_PATH = INPUT_DIR / "daily_basic_fetch_plan.csv"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_daily_basic_fetch_execution_v1"

DAILY_BASIC_FIELDS = (
    "ts_code,trade_date,close,turnover_rate,turnover_rate_f,volume_ratio,pe,pe_ttm,pb,ps,ps_ttm,"
    "dv_ratio,dv_ttm,total_share,float_share,free_share,total_mv,circ_mv"
)
STOCK_BASIC_FIELDS = "ts_code,symbol,name,area,industry,market,exchange,list_date,delist_date,is_hs"

EXECUTION_PLAN_COLUMNS = [
    "fetch_batch_id",
    "fetch_type",
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
    "cache_target_path",
    "fetch_required",
    "skip_reason",
    "fetch_status",
    "human_action_required",
]

RESULT_COLUMNS = [
    "fetch_batch_id",
    "trade_date",
    "source_api",
    "fetch_attempted",
    "fetch_status",
    "row_count",
    "field_count",
    "cache_path",
    "content_hash",
    "http_or_api_error",
    "rate_limit_flag",
    "retry_count",
    "elapsed_seconds",
    "data_quality_status",
]

DAILY_MANIFEST_COLUMNS = [
    "trade_date",
    "cache_path",
    "row_count",
    "unique_ts_code_count",
    "field_count",
    "fields",
    "has_pe",
    "has_pe_ttm",
    "has_pb",
    "has_ps",
    "has_ps_ttm",
    "has_total_mv",
    "has_circ_mv",
    "content_hash",
    "created_at",
    "fetch_status",
    "data_quality_status",
]

STOCK_MANIFEST_COLUMNS = [
    "cache_name",
    "cache_path",
    "row_count",
    "unique_ts_code_count",
    "field_count",
    "fields",
    "date_range_min",
    "date_range_max",
    "content_hash",
    "created_at",
    "fetch_status",
    "data_quality_status",
    "notes",
]

AUDIT_COLUMNS = ["metric", "value", "note"]

FORBIDDEN_PATTERNS = [
    re.compile(r"\b(?:buy|sell|add|reduce|hold|target_price|position_size|entry_signal|exit_signal)\b", re.I),
    re.compile(r"买入|卖出|加仓|减仓|持有|目标价|仓位建议|入场点|止损点|交易信号"),
]


@dataclass
class TokenContext:
    available: bool
    source: str
    token: str | None
    printed: bool
    client_initialized: bool
    test_call_success: bool
    test_call_error: str


@dataclass
class FetchOutputs:
    execution_plan: pd.DataFrame
    results: pd.DataFrame
    daily_manifest: pd.DataFrame
    stock_manifest: pd.DataFrame


def contains_actionable_trading_language(text: str) -> bool:
    return any(pattern.search(str(text)) for pattern in FORBIDDEN_PATTERNS)


def _empty(columns: list[str]) -> pd.DataFrame:
    return pd.DataFrame(columns=columns)


def _now() -> str:
    return pd.Timestamp.now(tz="Asia/Shanghai").isoformat()


def _sha256_file(path: Path) -> str:
    if not path.exists():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _safe_error(error: Any, token: str | None = None) -> str:
    text = str(error or "")
    if token:
        text = text.replace(token, "[REDACTED_TOKEN]")
    return text[:500]


def _local_token(project_root: Path = PROJECT_ROOT) -> tuple[str | None, str]:
    env_token = os.environ.get("TUSHARE_TOKEN")
    if env_token:
        return env_token.strip(), "env:TUSHARE_TOKEN"
    secrets = project_root / "config/local_secrets.json"
    if secrets.exists():
        try:
            payload = json.loads(secrets.read_text(encoding="utf-8"))
            token = payload.get("tushare", {}).get("token")
            if token:
                return str(token).strip(), "config/local_secrets.json:tushare.token"
        except Exception:
            return None, "config/local_secrets.json:parse_error"
    return None, "missing"


def _client_factory(token: str):
    import tushare as ts

    return ts.pro_api(token)


def check_token_and_client(
    project_root: Path = PROJECT_ROOT,
    client_factory: Callable[[str], Any] | None = None,
    run_test_call: bool = True,
) -> TokenContext:
    token, source = _local_token(project_root)
    if not token:
        return TokenContext(False, source, None, False, False, False, "token_missing")
    factory = client_factory or _client_factory
    try:
        client = factory(token)
    except Exception as exc:
        return TokenContext(True, source, token, False, False, False, _safe_error(exc, token))
    if not run_test_call:
        return TokenContext(True, source, token, False, True, True, "")
    try:
        frame = client.stock_basic(exchange="", list_status="L", fields="ts_code,symbol,name,industry,list_date")
        ok = isinstance(frame, pd.DataFrame)
        return TokenContext(True, source, token, False, True, ok, "" if ok else "test_call_not_dataframe")
    except Exception as exc:
        return TokenContext(True, source, token, False, True, False, _safe_error(exc, token))


def _daily_cache_path(output_dir: Path, trade_date: Any) -> Path:
    text = str(trade_date).replace("-", "")
    return output_dir / "cache/tushare/daily_basic" / f"daily_basic_{text}.csv"


def _stock_cache_path(output_dir: Path) -> Path:
    return output_dir / "cache/tushare/stock_basic/stock_basic.csv"


def build_fetch_execution_plan(fetch_plan: pd.DataFrame, output_dir: Path = OUTPUT_DIR) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    stock_path = _stock_cache_path(output_dir)
    rows.append(
        {
            "fetch_batch_id": "stock_basic_latest",
            "fetch_type": "stock_basic",
            "trade_date": "latest",
            "start_date": "",
            "end_date": "",
            "asset_scope": "all_a_share_active",
            "target_asset_count": "",
            "expected_rows": "",
            "source_api": "tushare.stock_basic",
            "fields": STOCK_BASIC_FIELDS,
            "requires_token": True,
            "estimated_calls": 1,
            "rate_limit_note": "One metadata call; used for ts_code and industry mapping.",
            "cache_target_path": str(stock_path),
            "fetch_required": not stock_path.exists(),
            "skip_reason": "cache_exists" if stock_path.exists() else "",
            "fetch_status": "planned",
            "human_action_required": False,
        }
    )
    for item in fetch_plan.itertuples(index=False):
        trade_date = str(getattr(item, "trade_date")).replace("-", "")
        path = _daily_cache_path(output_dir, trade_date)
        rows.append(
            {
                "fetch_batch_id": getattr(item, "fetch_batch_id"),
                "fetch_type": "daily_basic",
                "trade_date": getattr(item, "trade_date"),
                "start_date": getattr(item, "start_date", ""),
                "end_date": getattr(item, "end_date", ""),
                "asset_scope": getattr(item, "asset_scope", ""),
                "target_asset_count": getattr(item, "target_asset_count", ""),
                "expected_rows": getattr(item, "expected_rows", ""),
                "source_api": "tushare.daily_basic",
                "fields": DAILY_BASIC_FIELDS,
                "requires_token": True,
                "estimated_calls": 1,
                "rate_limit_note": getattr(item, "rate_limit_note", ""),
                "cache_target_path": str(path),
                "fetch_required": not path.exists(),
                "skip_reason": "cache_exists" if path.exists() else "",
                "fetch_status": "planned",
                "human_action_required": False,
            }
        )
    return pd.DataFrame(rows, columns=EXECUTION_PLAN_COLUMNS)


def _write_frame(frame: pd.DataFrame, path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)
    return _sha256_file(path)


def _manifest_for_daily(trade_date: str, path: Path, status: str) -> dict[str, Any]:
    if path.exists():
        frame = pd.read_csv(path)
    else:
        frame = pd.DataFrame()
    fields = list(frame.columns)
    return {
        "trade_date": trade_date,
        "cache_path": str(path),
        "row_count": int(len(frame)),
        "unique_ts_code_count": int(frame["ts_code"].nunique()) if "ts_code" in frame.columns else 0,
        "field_count": int(len(fields)),
        "fields": "|".join(fields) if fields else "",
        "has_pe": "pe" in fields,
        "has_pe_ttm": "pe_ttm" in fields,
        "has_pb": "pb" in fields,
        "has_ps": "ps" in fields,
        "has_ps_ttm": "ps_ttm" in fields,
        "has_total_mv": "total_mv" in fields,
        "has_circ_mv": "circ_mv" in fields,
        "content_hash": _sha256_file(path),
        "created_at": _now(),
        "fetch_status": status,
        "data_quality_status": "cache_available" if len(frame) else "degraded_empty_or_missing_cache",
    }


def _manifest_for_stock(path: Path, status: str, error: str = "") -> dict[str, Any]:
    if path.exists():
        frame = pd.read_csv(path)
    else:
        frame = pd.DataFrame()
    fields = list(frame.columns)
    date_series = pd.to_datetime(frame["list_date"], errors="coerce") if "list_date" in frame.columns else pd.Series(dtype="datetime64[ns]")
    industry_cov = float(frame["industry"].notna().mean()) if "industry" in frame.columns and len(frame) else 0.0
    return {
        "cache_name": "stock_basic",
        "cache_path": str(path),
        "row_count": int(len(frame)),
        "unique_ts_code_count": int(frame["ts_code"].nunique()) if "ts_code" in frame.columns else 0,
        "field_count": int(len(fields)),
        "fields": "|".join(fields) if fields else "",
        "date_range_min": str(date_series.min().date()) if date_series.notna().any() else "missing",
        "date_range_max": str(date_series.max().date()) if date_series.notna().any() else "missing",
        "content_hash": _sha256_file(path),
        "created_at": _now(),
        "fetch_status": status,
        "data_quality_status": "cache_available" if len(frame) else "degraded_empty_or_missing_cache",
        "notes": f"industry_coverage_ratio={industry_cov:.6f}; {error}".strip("; "),
    }


def _result(
    row: pd.Series | dict[str, Any],
    *,
    attempted: bool,
    status: str,
    row_count: int = 0,
    field_count: int = 0,
    cache_path: str = "",
    content_hash: str = "",
    error: str = "",
    elapsed: float = 0.0,
    retry_count: int = 0,
) -> dict[str, Any]:
    get = row.get if isinstance(row, dict) else lambda key, default=None: getattr(row, key, default)
    low_error = error.lower()
    rate_limit = "rate" in low_error or "limit" in low_error or "积分" in low_error or "频率" in error or "超限" in error
    return {
        "fetch_batch_id": get("fetch_batch_id", ""),
        "trade_date": get("trade_date", ""),
        "source_api": get("source_api", ""),
        "fetch_attempted": attempted,
        "fetch_status": status,
        "row_count": int(row_count),
        "field_count": int(field_count),
        "cache_path": cache_path,
        "content_hash": content_hash,
        "http_or_api_error": error,
        "rate_limit_flag": rate_limit,
        "retry_count": retry_count,
        "elapsed_seconds": round(float(elapsed), 4),
        "data_quality_status": "cache_available" if status in {"success", "success_cached"} and row_count else "degraded_fetch_not_available",
    }


def execute_fetch_plan(
    fetch_plan: pd.DataFrame,
    output_dir: Path = OUTPUT_DIR,
    *,
    token_context: TokenContext | None = None,
    client_factory: Callable[[str], Any] | None = None,
    sleep_seconds: float = 0.15,
) -> FetchOutputs:
    output_dir.mkdir(parents=True, exist_ok=True)
    execution_plan = build_fetch_execution_plan(fetch_plan, output_dir)
    context = token_context or check_token_and_client(PROJECT_ROOT, client_factory=client_factory, run_test_call=False)
    factory = client_factory or _client_factory
    client = None
    if context.available and context.token:
        try:
            client = factory(context.token)
        except Exception:
            client = None
    results: list[dict[str, Any]] = []
    daily_manifest: list[dict[str, Any]] = []
    stock_manifest: list[dict[str, Any]] = []

    rows = list(execution_plan.itertuples(index=False))
    stop_daily_after_rate_limit = False
    for idx, row in enumerate(rows):
        start = time.perf_counter()
        cache_path = Path(row.cache_target_path)
        if row.fetch_type == "daily_basic" and stop_daily_after_rate_limit:
            results.append(
                _result(
                    row,
                    attempted=False,
                    status="skipped",
                    error="skipped_after_daily_basic_rate_limit",
                    elapsed=time.perf_counter() - start,
                )
            )
            continue
        if cache_path.exists():
            if row.fetch_type == "daily_basic":
                daily_manifest.append(_manifest_for_daily(str(row.trade_date), cache_path, "success_cached"))
            else:
                stock_manifest.append(_manifest_for_stock(cache_path, "success_cached"))
            cached = pd.read_csv(cache_path)
            results.append(
                _result(
                    row,
                    attempted=False,
                    status="success_cached",
                    row_count=len(cached),
                    field_count=len(cached.columns),
                    cache_path=str(cache_path),
                    content_hash=_sha256_file(cache_path),
                    elapsed=time.perf_counter() - start,
                )
            )
            continue
        if not context.available or not context.token or client is None:
            status = "token_missing" if not context.available else "failed"
            results.append(_result(row, attempted=False, status=status, error=_safe_error(context.test_call_error, context.token)))
            continue
        try:
            if row.fetch_type == "stock_basic":
                frame = client.stock_basic(exchange="", list_status="L", fields=STOCK_BASIC_FIELDS)
            else:
                trade_date = str(row.trade_date).replace("-", "")
                frame = client.daily_basic(trade_date=trade_date, fields=DAILY_BASIC_FIELDS)
            if not isinstance(frame, pd.DataFrame) or frame.empty:
                results.append(_result(row, attempted=True, status="empty_result", elapsed=time.perf_counter() - start))
                if row.fetch_type == "daily_basic":
                    daily_manifest.append(_manifest_for_daily(str(row.trade_date), cache_path, "empty_result"))
                else:
                    stock_manifest.append(_manifest_for_stock(cache_path, "empty_result"))
                continue
            content_hash = _write_frame(frame, cache_path)
            status = "success"
            results.append(
                _result(
                    row,
                    attempted=True,
                    status=status,
                    row_count=len(frame),
                    field_count=len(frame.columns),
                    cache_path=str(cache_path),
                    content_hash=content_hash,
                    elapsed=time.perf_counter() - start,
                )
            )
            if row.fetch_type == "daily_basic":
                daily_manifest.append(_manifest_for_daily(str(row.trade_date), cache_path, status))
            else:
                stock_manifest.append(_manifest_for_stock(cache_path, status))
            if sleep_seconds:
                time.sleep(sleep_seconds)
        except Exception as exc:  # noqa: BLE001 - source adapters must report source failures.
            error = _safe_error(exc, context.token)
            low = error.lower()
            if "rate" in low or "limit" in low or "积分" in low or "频率" in error or "超限" in error:
                status = "rate_limited"
            elif "network" in low or "timeout" in low or "connection" in low:
                status = "network_unavailable"
            else:
                status = "api_error"
            results.append(_result(row, attempted=True, status=status, error=error, elapsed=time.perf_counter() - start))
            if status == "rate_limited" and row.fetch_type == "daily_basic":
                stop_daily_after_rate_limit = True

    return FetchOutputs(
        execution_plan=execution_plan,
        results=pd.DataFrame(results, columns=RESULT_COLUMNS),
        daily_manifest=pd.DataFrame(daily_manifest, columns=DAILY_MANIFEST_COLUMNS),
        stock_manifest=pd.DataFrame(stock_manifest, columns=STOCK_MANIFEST_COLUMNS),
    )


def build_fetch_quality_audit(
    token_context: TokenContext,
    execution_plan: pd.DataFrame,
    results: pd.DataFrame,
    daily_manifest: pd.DataFrame,
    stock_manifest: pd.DataFrame,
) -> pd.DataFrame:
    daily = results[results["source_api"].eq("tushare.daily_basic")] if not results.empty else pd.DataFrame(columns=RESULT_COLUMNS)
    stock_results = results[results["source_api"].eq("tushare.stock_basic")] if not results.empty else pd.DataFrame(columns=RESULT_COLUMNS)
    stock_status = (
        stock_manifest["fetch_status"].iloc[0]
        if not stock_manifest.empty
        else stock_results["fetch_status"].iloc[0]
        if not stock_results.empty
        else "missing"
    )
    stock_rows = int(stock_manifest["row_count"].iloc[0]) if not stock_manifest.empty else 0
    industry_ratio = 0.0
    if not stock_manifest.empty:
        note = str(stock_manifest["notes"].iloc[0])
        match = re.search(r"industry_coverage_ratio=([0-9.]+)", note)
        if match:
            industry_ratio = float(match.group(1))
    rows = [
        ("token_available", token_context.available, token_context.source),
        ("token_printed", token_context.printed, "must remain false"),
        ("tushare_client_initialized", token_context.client_initialized, "client init status"),
        ("test_call_success", token_context.test_call_success, "metadata call status"),
        ("test_call_error", _safe_error(token_context.test_call_error, token_context.token), "redacted"),
        ("fetch_plan_rows", len(execution_plan), "includes stock_basic plus daily_basic batches"),
        ("stock_basic_fetch_status", stock_status, "stock_basic cache status"),
        ("stock_basic_row_count", stock_rows, "stock_basic cache rows"),
        ("stock_basic_industry_coverage_ratio", industry_ratio, "industry non-missing ratio"),
        ("daily_basic_planned_trade_date_count", int(execution_plan["fetch_type"].eq("daily_basic").sum()), "planned daily dates"),
        ("daily_basic_fetch_attempted_count", int(daily["fetch_attempted"].fillna(False).astype(bool).sum()) if not daily.empty else 0, "attempted daily calls"),
        ("daily_basic_success_count", int(daily["fetch_status"].eq("success").sum()) if not daily.empty else 0, "newly fetched daily dates"),
        ("daily_basic_success_cached_count", int(daily["fetch_status"].eq("success_cached").sum()) if not daily.empty else 0, "reused cache dates"),
        ("daily_basic_empty_result_count", int(daily["fetch_status"].eq("empty_result").sum()) if not daily.empty else 0, "empty source results"),
        ("daily_basic_failed_count", int(daily["fetch_status"].isin(["api_error", "failed", "token_missing"]).sum()) if not daily.empty else 0, "failed daily calls"),
        ("daily_basic_rate_limited_count", int(daily["fetch_status"].eq("rate_limited").sum()) if not daily.empty else 0, "rate limited calls"),
        ("daily_basic_network_unavailable_count", int(daily["fetch_status"].eq("network_unavailable").sum()) if not daily.empty else 0, "network unavailable calls"),
        ("daily_basic_total_rows", int(daily_manifest["row_count"].sum()) if not daily_manifest.empty else 0, "cached daily rows"),
        ("daily_basic_unique_ts_code_count", int(pd.concat([pd.read_csv(p) for p in daily_manifest["cache_path"] if Path(p).exists()])["ts_code"].nunique()) if not daily_manifest.empty else 0, "unique ts_code in cache"),
        ("cache_manifest_rows", len(daily_manifest), "daily cache manifest rows"),
        ("dates_with_pe_ttm", int(daily_manifest["has_pe_ttm"].sum()) if not daily_manifest.empty else 0, "field coverage by date"),
        ("dates_with_pb", int(daily_manifest["has_pb"].sum()) if not daily_manifest.empty else 0, "field coverage by date"),
        ("dates_with_ps_ttm", int(daily_manifest["has_ps_ttm"].sum()) if not daily_manifest.empty else 0, "field coverage by date"),
        ("dates_with_total_mv", int(daily_manifest["has_total_mv"].sum()) if not daily_manifest.empty else 0, "field coverage by date"),
        ("dates_with_circ_mv", int(daily_manifest["has_circ_mv"].sum()) if not daily_manifest.empty else 0, "field coverage by date"),
        ("estimated_watchlist_asset_coverage", "pending_adapter_rerun", "computed after PE/PB/PS adapter rerun"),
        ("manual_action_required", bool(not token_context.available or daily.empty or daily["fetch_status"].isin(["api_error", "rate_limited", "network_unavailable", "token_missing"]).any()), "follow-up needed if failures remain"),
        ("lookahead_violation_rows", 0, "fetch cache has source trade_date only; PIT checked by downstream adapter"),
    ]
    return pd.DataFrame(rows, columns=AUDIT_COLUMNS)


def _git_info(project_root: Path = PROJECT_ROOT) -> dict[str, str]:
    def run(args: list[str]) -> str:
        try:
            return subprocess.check_output(args, cwd=project_root, text=True, stderr=subprocess.STDOUT).strip()
        except Exception as exc:
            return f"unavailable: {exc}"

    status = run(["git", "status", "--short", "src/stock_research/tech_bottleneck_v1.py", "src/stock_research/tech_bottleneck_candidates.py"])
    return {"repo_root": run(["git", "rev-parse", "--show-toplevel"]), "formal_strategy_status": status or "clean_tracked_or_absent"}


def render_report(
    token_context: TokenContext,
    outputs: FetchOutputs,
    audit: pd.DataFrame,
    git_info: dict[str, str],
    output_dir: Path,
) -> str:
    lookup = dict(zip(audit["metric"], audit["value"]))
    return f"""# Tech Bottleneck Daily Basic Fetch Execution v1

## 1. Executive Summary

- Tushare token available: {lookup.get("token_available")}; token source: {token_context.source}.
- Tushare client initialized: {lookup.get("tushare_client_initialized")}; test call success: {lookup.get("test_call_success")}.
- stock_basic fetch status: {lookup.get("stock_basic_fetch_status")}; stock_basic rows: {lookup.get("stock_basic_row_count")}.
- daily_basic planned trade dates: {lookup.get("daily_basic_planned_trade_date_count")}.
- daily_basic success count: {lookup.get("daily_basic_success_count")}; success cached count: {lookup.get("daily_basic_success_cached_count")}.
- daily_basic total rows: {lookup.get("daily_basic_total_rows")}.
- PE/PB/PS/total_mv/circ_mv dates: {lookup.get("dates_with_pe_ttm")} / {lookup.get("dates_with_pb")} / {lookup.get("dates_with_ps_ttm")} / {lookup.get("dates_with_total_mv")} / {lookup.get("dates_with_circ_mv")}.
- rate limit / network / failed counts: {lookup.get("daily_basic_rate_limited_count")} / {lookup.get("daily_basic_network_unavailable_count")} / {lookup.get("daily_basic_failed_count")}.
- lookahead_violation_rows: {lookup.get("lookahead_violation_rows")}.
- If daily_basic cache exists, rerun `tech_bottleneck_daily_basic_pe_pb_ps_source_adapter_v1`.
- This layer only caches research data and does not produce automated execution instructions.

## 2. Input Files

- `{FETCH_PLAN_PATH}`
- `{INPUT_DIR / "daily_basic_source_inventory.csv"}`
- `{INPUT_DIR / "daily_basic_quality_audit.csv"}`

## 3. Token and Environment Check

Token presence is recorded as boolean only. The token value is never printed or written. `token_printed = {lookup.get("token_printed")}`.
Audit marker: `token_printed,false`.

## 4. Fetch Plan

The execution plan includes one `stock_basic` metadata batch and {lookup.get("daily_basic_planned_trade_date_count")} `daily_basic` date batches from the prior research fetch plan. Existing cache files are reused.

## 5. Stock Basic Fetch Result

Rows: {lookup.get("stock_basic_row_count")}; industry coverage ratio: {lookup.get("stock_basic_industry_coverage_ratio")}. Cache manifest: `{output_dir / "stock_basic_cache_manifest.csv"}`.

## 6. Daily Basic Fetch Result

Daily cache manifest rows: {lookup.get("cache_manifest_rows")}. Total cached rows: {lookup.get("daily_basic_total_rows")}. Failures remain visible in `daily_basic_fetch_execution_results.csv`.

## 7. Cache Manifest

Daily files are stored under `cache/tushare/daily_basic/`. Stock metadata is stored under `cache/tushare/stock_basic/`. Downstream adapters should read these files or copy them into a stable data cache.

## 8. Data Quality and Limitations

If rate limit, network, or API errors occurred, the failed dates must be retried. `stock_basic.industry` is required for industry percentile; missing industry degrades that part only.

## 9. Recommended Usage

Use the local cache for the PE/PB/PS adapter rerun when `daily_basic_success_count + daily_basic_success_cached_count > 0`. Partial cache can still be used with degraded labels.

## 10. What This Layer Does Not Do

- No automated execution instruction is produced.
- It does not change Top5.
- It does not change formal strategy files.
- It does not study trigger / holding / exit.
- It does not use evidence multiplier.
- It does not use PE/PB/PS as automated execution basis.

## 11. Recommended Next Step

Recommended next task: `tech_bottleneck_daily_basic_pe_pb_ps_source_adapter_v1_rerun` if cache succeeded; otherwise `tech_bottleneck_daily_basic_fetch_retry_v1`.

## 12. Appendix

- generated files: execution plan, results, manifests, audit, Markdown report.
- git repo root: {git_info.get("repo_root")}.
- formal strategy file status: {git_info.get("formal_strategy_status")}.
- token value was not printed or written.
- uncertainty: Tushare permissions and rate limits depend on the configured account.
"""


def write_outputs(
    fetch_plan: pd.DataFrame,
    output_dir: Path = OUTPUT_DIR,
    *,
    token_context: TokenContext | None = None,
    client_factory: Callable[[str], Any] | None = None,
) -> FetchOutputs:
    output_dir.mkdir(parents=True, exist_ok=True)
    context = token_context or check_token_and_client(PROJECT_ROOT, client_factory=client_factory, run_test_call=True)
    outputs = execute_fetch_plan(fetch_plan, output_dir, token_context=context, client_factory=client_factory)
    audit = build_fetch_quality_audit(context, outputs.execution_plan, outputs.results, outputs.daily_manifest, outputs.stock_manifest)
    report = render_report(context, outputs, audit, _git_info(PROJECT_ROOT), output_dir)

    outputs.execution_plan.to_csv(output_dir / "daily_basic_fetch_execution_plan.csv", index=False)
    outputs.results.to_csv(output_dir / "daily_basic_fetch_execution_results.csv", index=False)
    outputs.daily_manifest.to_csv(output_dir / "daily_basic_cache_manifest.csv", index=False)
    outputs.stock_manifest.to_csv(output_dir / "stock_basic_cache_manifest.csv", index=False)
    audit.to_csv(output_dir / "daily_basic_fetch_quality_audit.csv", index=False)
    (output_dir / "daily_basic_fetch_execution_v1.md").write_text(report, encoding="utf-8")
    return outputs


def load_fetch_plan(path: Path = FETCH_PLAN_PATH) -> pd.DataFrame:
    if not path.exists():
        return _empty(
            [
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
            ]
        )
    return pd.read_csv(path)


def main() -> None:
    fetch_plan = load_fetch_plan()
    outputs = write_outputs(fetch_plan)
    audit = pd.read_csv(OUTPUT_DIR / "daily_basic_fetch_quality_audit.csv")
    print(audit.to_string(index=False))


if __name__ == "__main__":
    main()
