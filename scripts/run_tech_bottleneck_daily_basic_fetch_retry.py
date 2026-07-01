import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import pandas as pd


RULE_VERSION = "tech_bottleneck_daily_basic_fetch_retry_v1"
PROJECT_ROOT = Path("/Users/xiwei/stock_research")
PREVIOUS_FETCH_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_daily_basic_fetch_execution_v1"
PREVIOUS_ADAPTER_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_daily_basic_pe_pb_ps_source_adapter_v1"
PREVIOUS_EXECUTION_PLAN_PATH = PREVIOUS_FETCH_DIR / "daily_basic_fetch_execution_plan.csv"
PREVIOUS_FETCH_PLAN_PATH = PREVIOUS_ADAPTER_DIR / "daily_basic_fetch_plan.csv"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_daily_basic_fetch_retry_v1"

DEFAULT_MIN_INTERVAL_SECONDS = 70.0
DEFAULT_MAX_RETRY_PER_BATCH = 2

DAILY_BASIC_FIELDS = (
    "ts_code,trade_date,close,turnover_rate,turnover_rate_f,volume_ratio,pe,pe_ttm,pb,ps,ps_ttm,"
    "dv_ratio,dv_ttm,total_share,float_share,free_share,total_mv,circ_mv"
)
STOCK_BASIC_FIELDS = "ts_code,symbol,name,area,industry,market,exchange,list_date,delist_date,is_hs"

RETRY_PLAN_COLUMNS = [
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

RETRY_RESULT_COLUMNS = [
    "fetch_batch_id",
    "trade_date",
    "source_api",
    "fetch_attempted",
    "fetch_status",
    "row_count",
    "field_count",
    "cache_path",
    "content_hash",
    "api_error",
    "rate_limit_flag",
    "retry_count",
    "wait_seconds_before_call",
    "elapsed_seconds",
    "data_quality_status",
]

DAILY_RETRY_MANIFEST_COLUMNS = [
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

STOCK_RETRY_MANIFEST_COLUMNS = [
    "cache_name",
    "cache_path",
    "row_count",
    "unique_ts_code_count",
    "field_count",
    "fields",
    "industry_non_missing_count",
    "industry_coverage_ratio",
    "content_hash",
    "created_at",
    "fetch_status",
    "api_error",
    "rate_limit_flag",
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
class RetryOutputs:
    retry_plan: pd.DataFrame
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


def _is_rate_limit(error: str) -> bool:
    low = str(error).lower()
    return "rate" in low or "limit" in low or "积分" in str(error) or "频率" in str(error) or "超限" in str(error)


def _is_network_error(error: str) -> bool:
    low = str(error).lower()
    return "network" in low or "timeout" in low or "connection" in low or "连接" in str(error)


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
    run_test_call: bool = False,
) -> TokenContext:
    token, source = _local_token(project_root)
    if not token:
        return TokenContext(False, source, None, False, False, False, "token_missing")
    factory = client_factory or _client_factory
    try:
        client = factory(token)
    except Exception as exc:  # noqa: BLE001 - source adapters report external failures.
        return TokenContext(True, source, token, False, False, False, _safe_error(exc, token))
    if not run_test_call:
        return TokenContext(True, source, token, False, True, True, "")
    try:
        frame = client.stock_basic(exchange="", list_status="L", fields="ts_code,symbol,name,industry,list_date")
        ok = isinstance(frame, pd.DataFrame)
        return TokenContext(True, source, token, False, True, ok, "" if ok else "test_call_not_dataframe")
    except Exception as exc:  # noqa: BLE001
        return TokenContext(True, source, token, False, True, False, _safe_error(exc, token))


def _daily_cache_path(output_dir: Path, trade_date: Any) -> Path:
    text = str(trade_date).replace("-", "")
    return output_dir / "cache/tushare/daily_basic" / f"daily_basic_{text}.csv"


def _stock_cache_path(output_dir: Path) -> Path:
    return output_dir / "cache/tushare/stock_basic/stock_basic.csv"


def _previous_daily_cache_path(previous_cache_dir: Path, trade_date: Any) -> Path:
    text = str(trade_date).replace("-", "")
    return previous_cache_dir / "cache/tushare/daily_basic" / f"daily_basic_{text}.csv"


def _previous_stock_cache_path(previous_cache_dir: Path) -> Path:
    return previous_cache_dir / "cache/tushare/stock_basic/stock_basic.csv"


def _copy_if_needed(source: Path, target: Path) -> bool:
    if not source.exists():
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if _sha256_file(source) == _sha256_file(target):
            return True
        return True
    shutil.copy2(source, target)
    return True


def _cell(row: pd.Series, key: str, default: Any = "") -> Any:
    if key not in row.index:
        return default
    value = row[key]
    if pd.isna(value):
        return default
    return value


def _normalize_input_plan(input_plan: pd.DataFrame) -> pd.DataFrame:
    if input_plan.empty:
        return _empty(RETRY_PLAN_COLUMNS)
    rows: list[dict[str, Any]] = []
    has_stock = False
    for _, row in input_plan.iterrows():
        fetch_type = str(_cell(row, "fetch_type", "daily_basic"))
        if fetch_type == "stock_basic":
            has_stock = True
        rows.append(
            {
                "fetch_batch_id": _cell(row, "fetch_batch_id", "daily_basic_unknown"),
                "fetch_type": fetch_type,
                "trade_date": _cell(row, "trade_date", "latest" if fetch_type == "stock_basic" else ""),
                "start_date": _cell(row, "start_date", ""),
                "end_date": _cell(row, "end_date", ""),
                "asset_scope": _cell(row, "asset_scope", "all_a_share_active" if fetch_type == "stock_basic" else ""),
                "target_asset_count": _cell(row, "target_asset_count", ""),
                "expected_rows": _cell(row, "expected_rows", ""),
                "source_api": "tushare.stock_basic" if fetch_type == "stock_basic" else "tushare.daily_basic",
                "fields": STOCK_BASIC_FIELDS if fetch_type == "stock_basic" else DAILY_BASIC_FIELDS,
                "requires_token": True,
                "estimated_calls": 1,
                "rate_limit_note": _cell(row, "rate_limit_note", "single worker retry"),
                "cache_target_path": _cell(row, "cache_target_path", ""),
                "fetch_required": bool(_cell(row, "fetch_required", True)),
                "skip_reason": _cell(row, "skip_reason", ""),
                "fetch_status": _cell(row, "fetch_status", "planned"),
                "human_action_required": bool(_cell(row, "human_action_required", False)),
            }
        )
    if not has_stock:
        rows.insert(
            0,
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
                "rate_limit_note": "single worker retry",
                "cache_target_path": "",
                "fetch_required": True,
                "skip_reason": "",
                "fetch_status": "planned",
                "human_action_required": False,
            },
        )
    return pd.DataFrame(rows, columns=RETRY_PLAN_COLUMNS)


def build_retry_plan(
    input_plan: pd.DataFrame,
    output_dir: Path = OUTPUT_DIR,
    *,
    previous_cache_dir: Path = PREVIOUS_FETCH_DIR,
    resume_from_existing_cache: bool = True,
) -> pd.DataFrame:
    normalized = _normalize_input_plan(input_plan)
    rows: list[dict[str, Any]] = []
    for _, row in normalized.iterrows():
        item = row.to_dict()
        if item["fetch_type"] == "stock_basic":
            cache_path = _stock_cache_path(output_dir)
            previous_path = _previous_stock_cache_path(previous_cache_dir)
        else:
            cache_path = _daily_cache_path(output_dir, item["trade_date"])
            previous_path = _previous_daily_cache_path(previous_cache_dir, item["trade_date"])
        if resume_from_existing_cache:
            _copy_if_needed(previous_path, cache_path)
        cache_exists = cache_path.exists()
        item["cache_target_path"] = str(cache_path)
        item["fetch_required"] = not cache_exists
        item["skip_reason"] = "cache_exists" if cache_exists else ""
        item["fetch_status"] = "success_cached" if cache_exists else "planned"
        item["human_action_required"] = False
        rows.append(item)
    plan = pd.DataFrame(rows, columns=RETRY_PLAN_COLUMNS)
    plan["fetch_required"] = plan["fetch_required"].map(bool).astype(object)
    plan["requires_token"] = plan["requires_token"].map(bool).astype(object)
    plan["human_action_required"] = plan["human_action_required"].map(bool).astype(object)
    return plan


def _write_frame(frame: pd.DataFrame, path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)
    return _sha256_file(path)


def _manifest_for_daily(trade_date: str, path: Path, status: str) -> dict[str, Any]:
    frame = pd.read_csv(path) if path.exists() else pd.DataFrame()
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


def _manifest_for_stock(path: Path, status: str, error: str = "", rate_limit: bool = False) -> dict[str, Any]:
    frame = pd.read_csv(path) if path.exists() else pd.DataFrame()
    fields = list(frame.columns)
    industry_non_missing = int(frame["industry"].notna().sum()) if "industry" in frame.columns else 0
    industry_ratio = float(frame["industry"].notna().mean()) if "industry" in frame.columns and len(frame) else 0.0
    return {
        "cache_name": "stock_basic",
        "cache_path": str(path),
        "row_count": int(len(frame)),
        "unique_ts_code_count": int(frame["ts_code"].nunique()) if "ts_code" in frame.columns else 0,
        "field_count": int(len(fields)),
        "fields": "|".join(fields) if fields else "",
        "industry_non_missing_count": industry_non_missing,
        "industry_coverage_ratio": round(industry_ratio, 6),
        "content_hash": _sha256_file(path),
        "created_at": _now(),
        "fetch_status": status,
        "api_error": error,
        "rate_limit_flag": bool(rate_limit),
        "data_quality_status": "cache_available" if len(frame) else "degraded_empty_or_missing_cache",
        "notes": "research-only cache; token value not written",
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
    wait_seconds_before_call: float = 0.0,
) -> dict[str, Any]:
    get = row.get if isinstance(row, dict) else lambda key, default=None: getattr(row, key, default)
    rate_limit = _is_rate_limit(error) or status == "rate_limited"
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
        "api_error": error,
        "rate_limit_flag": bool(rate_limit),
        "retry_count": int(retry_count),
        "wait_seconds_before_call": round(float(wait_seconds_before_call), 4),
        "elapsed_seconds": round(float(elapsed), 4),
        "data_quality_status": "cache_available" if status in {"success", "success_cached"} and row_count else "degraded_fetch_not_available",
    }


def _flush_outputs(output_dir: Path, outputs: RetryOutputs) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs.retry_plan.to_csv(output_dir / "daily_basic_fetch_retry_plan.csv", index=False)
    outputs.results.to_csv(output_dir / "daily_basic_fetch_retry_results.csv", index=False)
    outputs.daily_manifest.to_csv(output_dir / "daily_basic_retry_cache_manifest.csv", index=False)
    outputs.stock_manifest.to_csv(output_dir / "stock_basic_retry_cache_manifest.csv", index=False)


def execute_retry(
    input_plan: pd.DataFrame,
    output_dir: Path = OUTPUT_DIR,
    *,
    previous_cache_dir: Path = PREVIOUS_FETCH_DIR,
    token_context: TokenContext | None = None,
    client_factory: Callable[[str], Any] | None = None,
    min_interval_seconds: float = DEFAULT_MIN_INTERVAL_SECONDS,
    max_retry_per_batch: int = DEFAULT_MAX_RETRY_PER_BATCH,
    stop_after_attempt_count: int | None = None,
    stop_after_success_count: int | None = None,
    resume_from_existing_cache: bool = True,
    flush_each_batch: bool = False,
) -> RetryOutputs:
    output_dir.mkdir(parents=True, exist_ok=True)
    retry_plan = build_retry_plan(
        input_plan,
        output_dir,
        previous_cache_dir=previous_cache_dir,
        resume_from_existing_cache=resume_from_existing_cache,
    )
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
    daily_attempts = 0
    daily_successes = 0
    last_call_at: float | None = None
    stop_daily_after_rate_limit = False

    def current_outputs() -> RetryOutputs:
        return RetryOutputs(
            retry_plan=retry_plan,
            results=pd.DataFrame(results, columns=RETRY_RESULT_COLUMNS),
            daily_manifest=pd.DataFrame(daily_manifest, columns=DAILY_RETRY_MANIFEST_COLUMNS),
            stock_manifest=pd.DataFrame(stock_manifest, columns=STOCK_RETRY_MANIFEST_COLUMNS),
        )

    for idx, row in enumerate(list(retry_plan.itertuples(index=False))):
        start = time.perf_counter()
        cache_path = Path(row.cache_target_path)
        if row.fetch_type == "daily_basic" and stop_daily_after_rate_limit:
            results.append(_result(row, attempted=False, status="skipped", error="skipped_after_daily_basic_rate_limit"))
            if flush_each_batch:
                _flush_outputs(output_dir, current_outputs())
            continue
        if row.fetch_type == "daily_basic" and stop_after_attempt_count is not None and daily_attempts >= stop_after_attempt_count and not cache_path.exists():
            results.append(_result(row, attempted=False, status="skipped", error="skipped_after_attempt_limit"))
            if flush_each_batch:
                _flush_outputs(output_dir, current_outputs())
            continue
        if row.fetch_type == "daily_basic" and stop_after_success_count is not None and daily_successes >= stop_after_success_count and not cache_path.exists():
            results.append(_result(row, attempted=False, status="skipped", error="skipped_after_success_limit"))
            if flush_each_batch:
                _flush_outputs(output_dir, current_outputs())
            continue
        if cache_path.exists():
            frame = pd.read_csv(cache_path)
            if row.fetch_type == "daily_basic":
                daily_manifest.append(_manifest_for_daily(str(row.trade_date), cache_path, "success_cached"))
            else:
                stock_manifest.append(_manifest_for_stock(cache_path, "success_cached"))
            results.append(
                _result(
                    row,
                    attempted=False,
                    status="success_cached",
                    row_count=len(frame),
                    field_count=len(frame.columns),
                    cache_path=str(cache_path),
                    content_hash=_sha256_file(cache_path),
                    elapsed=time.perf_counter() - start,
                )
            )
            if flush_each_batch:
                _flush_outputs(output_dir, current_outputs())
            continue
        if not context.available or not context.token or client is None:
            status = "token_missing" if not context.available else "failed"
            results.append(_result(row, attempted=False, status=status, error=_safe_error(context.test_call_error, context.token)))
            if row.fetch_type == "stock_basic":
                stock_manifest.append(_manifest_for_stock(cache_path, status, _safe_error(context.test_call_error, context.token)))
            if flush_each_batch:
                _flush_outputs(output_dir, current_outputs())
            continue

        wait_seconds = 0.0
        if last_call_at is not None:
            elapsed_since_call = time.perf_counter() - last_call_at
            wait_seconds = max(0.0, float(min_interval_seconds) - elapsed_since_call)
            if wait_seconds > 0:
                time.sleep(wait_seconds)

        attempt_status = "failed"
        attempt_error = ""
        frame = pd.DataFrame()
        retry_count = 0
        for attempt in range(max(1, int(max_retry_per_batch))):
            retry_count = attempt
            try:
                if row.fetch_type == "stock_basic":
                    frame = client.stock_basic(exchange="", list_status="L", fields=STOCK_BASIC_FIELDS)
                else:
                    trade_date = str(row.trade_date).replace("-", "")
                    daily_attempts += 1 if attempt == 0 else 0
                    frame = client.daily_basic(trade_date=trade_date, fields=DAILY_BASIC_FIELDS)
                last_call_at = time.perf_counter()
                if not isinstance(frame, pd.DataFrame) or frame.empty:
                    attempt_status = "empty_result"
                    frame = pd.DataFrame()
                else:
                    attempt_status = "success"
                break
            except Exception as exc:  # noqa: BLE001 - external API errors are captured for audit.
                last_call_at = time.perf_counter()
                attempt_error = _safe_error(exc, context.token)
                if _is_rate_limit(attempt_error):
                    attempt_status = "rate_limited"
                    break
                if _is_network_error(attempt_error):
                    attempt_status = "network_unavailable"
                else:
                    attempt_status = "api_error"
                if attempt + 1 < max(1, int(max_retry_per_batch)):
                    backoff = 120.0 if attempt_status == "rate_limited" else min_interval_seconds
                    if backoff > 0:
                        time.sleep(backoff)

        if attempt_status == "success" and not frame.empty:
            content_hash = _write_frame(frame, cache_path)
            if row.fetch_type == "daily_basic":
                daily_successes += 1
                daily_manifest.append(_manifest_for_daily(str(row.trade_date), cache_path, "success"))
            else:
                stock_manifest.append(_manifest_for_stock(cache_path, "success"))
            results.append(
                _result(
                    row,
                    attempted=True,
                    status="success",
                    row_count=len(frame),
                    field_count=len(frame.columns),
                    cache_path=str(cache_path),
                    content_hash=content_hash,
                    elapsed=time.perf_counter() - start,
                    retry_count=retry_count,
                    wait_seconds_before_call=wait_seconds,
                )
            )
        else:
            results.append(
                _result(
                    row,
                    attempted=True,
                    status=attempt_status,
                    error=attempt_error,
                    elapsed=time.perf_counter() - start,
                    retry_count=retry_count,
                    wait_seconds_before_call=wait_seconds,
                )
            )
            if row.fetch_type == "stock_basic":
                stock_manifest.append(_manifest_for_stock(cache_path, attempt_status, attempt_error, attempt_status == "rate_limited"))
            if attempt_status == "rate_limited" and row.fetch_type == "daily_basic":
                stop_daily_after_rate_limit = True
        if flush_each_batch:
            _flush_outputs(output_dir, current_outputs())

    outputs = current_outputs()
    _flush_outputs(output_dir, outputs)
    return outputs


def _combine_daily_cache(manifest: pd.DataFrame) -> pd.DataFrame:
    frames = []
    for path in manifest.get("cache_path", []):
        cache_path = Path(str(path))
        if cache_path.exists():
            frames.append(pd.read_csv(cache_path))
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def build_retry_quality_audit(token_context: TokenContext, outputs: RetryOutputs) -> pd.DataFrame:
    results = outputs.results
    daily_results = results[results["source_api"].eq("tushare.daily_basic")] if not results.empty else pd.DataFrame(columns=RETRY_RESULT_COLUMNS)
    stock_results = results[results["source_api"].eq("tushare.stock_basic")] if not results.empty else pd.DataFrame(columns=RETRY_RESULT_COLUMNS)
    stock_status = (
        outputs.stock_manifest["fetch_status"].iloc[0]
        if not outputs.stock_manifest.empty
        else stock_results["fetch_status"].iloc[0]
        if not stock_results.empty
        else "missing"
    )
    stock_rows = int(outputs.stock_manifest["row_count"].iloc[0]) if not outputs.stock_manifest.empty else 0
    industry_ratio = float(outputs.stock_manifest["industry_coverage_ratio"].iloc[0]) if not outputs.stock_manifest.empty else 0.0
    cached_daily = outputs.daily_manifest
    combined = _combine_daily_cache(cached_daily)
    success_count = int(daily_results["fetch_status"].eq("success").sum()) if not daily_results.empty else 0
    cached_count = int(daily_results["fetch_status"].eq("success_cached").sum()) if not daily_results.empty else 0
    skipped_or_failed = int(daily_results["fetch_status"].isin(["skipped", "rate_limited", "api_error", "failed", "token_missing", "network_unavailable", "empty_result"]).sum()) if not daily_results.empty else 0
    rows = [
        ("token_available", token_context.available, token_context.source),
        ("token_printed", token_context.printed, "must remain false"),
        ("tushare_client_initialized", token_context.client_initialized, "client init status"),
        ("fetch_retry_plan_rows", len(outputs.retry_plan), "includes stock_basic plus daily_basic batches"),
        ("stock_basic_fetch_status", stock_status, "stock_basic cache status"),
        ("stock_basic_row_count", stock_rows, "stock_basic cache rows"),
        ("stock_basic_industry_coverage_ratio", industry_ratio, "industry non-missing ratio"),
        ("planned_daily_basic_trade_date_count", int(outputs.retry_plan["fetch_type"].eq("daily_basic").sum()), "planned daily dates"),
        ("already_cached_daily_basic_date_count", cached_count, "reused cache dates"),
        ("daily_basic_fetch_attempted_count", int(daily_results["fetch_attempted"].fillna(False).astype(bool).sum()) if not daily_results.empty else 0, "attempted daily calls"),
        ("daily_basic_success_count", success_count, "newly fetched daily dates"),
        ("daily_basic_success_cached_count", cached_count, "reused cache dates"),
        ("daily_basic_empty_result_count", int(daily_results["fetch_status"].eq("empty_result").sum()) if not daily_results.empty else 0, "empty source results"),
        ("daily_basic_failed_count", int(daily_results["fetch_status"].isin(["api_error", "failed", "token_missing"]).sum()) if not daily_results.empty else 0, "failed daily calls"),
        ("daily_basic_rate_limited_count", int(daily_results["fetch_status"].eq("rate_limited").sum()) if not daily_results.empty else 0, "rate limited calls"),
        ("daily_basic_network_unavailable_count", int(daily_results["fetch_status"].eq("network_unavailable").sum()) if not daily_results.empty else 0, "network unavailable calls"),
        ("daily_basic_total_cached_date_count", int(len(cached_daily)), "available daily cache dates"),
        ("daily_basic_total_rows", int(cached_daily["row_count"].sum()) if not cached_daily.empty else 0, "cached daily rows"),
        ("daily_basic_unique_ts_code_count", int(combined["ts_code"].nunique()) if "ts_code" in combined.columns else 0, "unique ts_code in cache"),
        ("dates_with_pe_ttm", int(cached_daily["has_pe_ttm"].sum()) if not cached_daily.empty else 0, "field coverage by date"),
        ("dates_with_pb", int(cached_daily["has_pb"].sum()) if not cached_daily.empty else 0, "field coverage by date"),
        ("dates_with_ps_ttm", int(cached_daily["has_ps_ttm"].sum()) if not cached_daily.empty else 0, "field coverage by date"),
        ("dates_with_total_mv", int(cached_daily["has_total_mv"].sum()) if not cached_daily.empty else 0, "field coverage by date"),
        ("dates_with_circ_mv", int(cached_daily["has_circ_mv"].sum()) if not cached_daily.empty else 0, "field coverage by date"),
        ("remaining_unfetched_dates", skipped_or_failed, "daily dates not available in retry output"),
        ("estimated_watchlist_asset_coverage", "pending_adapter_rerun", "computed after PE/PB/PS adapter rerun"),
        ("manual_action_required", bool(skipped_or_failed or stock_status not in {"success", "success_cached"}), "follow-up needed if failures remain"),
        ("lookahead_violation_rows", 0, "fetch cache only records source dates; PIT checked downstream"),
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


def _metric(audit: pd.DataFrame, name: str, default: Any = "") -> Any:
    matched = audit[audit["metric"].eq(name)]
    if matched.empty:
        return default
    return matched["value"].iloc[0]


def render_report(
    token_context: TokenContext,
    outputs: RetryOutputs,
    audit: pd.DataFrame,
    git_info: dict[str, str],
    output_dir: Path,
) -> str:
    return f"""# Tech Bottleneck Daily Basic Fetch Retry v1

## 1. Executive Summary

- Low-speed retry executed with single-worker sequencing.
- Tushare token available: {_metric(audit, "token_available")}; token source: {token_context.source}; token value was not printed or written.
- stock_basic status: {_metric(audit, "stock_basic_fetch_status")}; stock_basic rows: {_metric(audit, "stock_basic_row_count")}.
- daily_basic planned dates: {_metric(audit, "planned_daily_basic_trade_date_count")}.
- newly fetched daily dates: {_metric(audit, "daily_basic_success_count")}; reused daily cache dates: {_metric(audit, "daily_basic_success_cached_count")}.
- total cached daily dates: {_metric(audit, "daily_basic_total_cached_date_count")}; total rows: {_metric(audit, "daily_basic_total_rows")}.
- PE/PB/PS/total_mv/circ_mv available dates: {_metric(audit, "dates_with_pe_ttm")} / {_metric(audit, "dates_with_pb")} / {_metric(audit, "dates_with_ps_ttm")} / {_metric(audit, "dates_with_total_mv")} / {_metric(audit, "dates_with_circ_mv")}.
- rate-limited / network-unavailable counts: {_metric(audit, "daily_basic_rate_limited_count")} / {_metric(audit, "daily_basic_network_unavailable_count")}.
- remaining unfetched dates: {_metric(audit, "remaining_unfetched_dates")}.
- lookahead_violation_rows: {_metric(audit, "lookahead_violation_rows")}.
- This output is research-only cache material and contains no automated execution prompt.

## 2. Input Files

- `{PREVIOUS_FETCH_DIR / "daily_basic_fetch_execution_plan.csv"}`
- `{PREVIOUS_FETCH_DIR / "daily_basic_fetch_execution_results.csv"}`
- `{PREVIOUS_FETCH_DIR / "daily_basic_cache_manifest.csv"}`
- `{PREVIOUS_ADAPTER_DIR / "daily_basic_fetch_plan.csv"}`

## 3. Retry Strategy

Retry uses one worker only. Existing cache is copied into this task output and marked `success_cached`. New API calls are sequential, with configurable interval and retry limit.

## 4. Stock Basic Retry Result

stock_basic status: `{_metric(audit, "stock_basic_fetch_status")}`. Industry coverage ratio: `{_metric(audit, "stock_basic_industry_coverage_ratio")}`.

## 5. Daily Basic Retry Result

Planned dates: `{_metric(audit, "planned_daily_basic_trade_date_count")}`. New success: `{_metric(audit, "daily_basic_success_count")}`. Cached reuse: `{_metric(audit, "daily_basic_success_cached_count")}`. Rate-limited calls: `{_metric(audit, "daily_basic_rate_limited_count")}`. Remaining dates: `{_metric(audit, "remaining_unfetched_dates")}`.

## 6. Cache Manifest

Daily cache manifest: `{output_dir / "daily_basic_retry_cache_manifest.csv"}`. stock_basic manifest: `{output_dir / "stock_basic_retry_cache_manifest.csv"}`.

## 7. Data Quality and Limitations

Tushare rate limits may still restrict progress. Partial cache is useful only as degraded research input until the PE/PB/PS adapter reruns and validates PIT coverage.

## 8. Recommended Usage

If total cached date count is still low, continue the same retry task later. If cached dates become sufficient, rerun `tech_bottleneck_daily_basic_pe_pb_ps_source_adapter_v1`.

## 9. What This Layer Does Not Do

- No automated execution prompt is produced.
- It does not change Top5.
- It does not change formal strategy files.
- It does not study trigger / holding / exit.
- It does not use evidence multiplier.
- It does not use PE/PB/PS as automated execution basis.

## 10. Recommended Next Step

Recommended next task: `tech_bottleneck_daily_basic_fetch_retry_v1_continue` if remaining dates are high; otherwise `tech_bottleneck_daily_basic_pe_pb_ps_source_adapter_v1_rerun`.

## 11. Appendix

- Generated files: retry plan, retry results, daily cache manifest, stock_basic manifest, audit, Markdown report.
- git repo root: `{git_info.get("repo_root")}`.
- formal strategy file status: `{git_info.get("formal_strategy_status")}`.
- Because untracked files are not covered by normal git diff, formal strategy immutability cannot be fully proven from git diff alone if they remain untracked.
- Rule version: `{RULE_VERSION}`.
"""


def write_outputs(
    input_plan: pd.DataFrame,
    output_dir: Path = OUTPUT_DIR,
    *,
    previous_cache_dir: Path = PREVIOUS_FETCH_DIR,
    token_context: TokenContext | None = None,
    client_factory: Callable[[str], Any] | None = None,
    min_interval_seconds: float = DEFAULT_MIN_INTERVAL_SECONDS,
    max_retry_per_batch: int = DEFAULT_MAX_RETRY_PER_BATCH,
    stop_after_attempt_count: int | None = None,
    stop_after_success_count: int | None = None,
    resume_from_existing_cache: bool = True,
) -> RetryOutputs:
    context = token_context or check_token_and_client(PROJECT_ROOT, client_factory=client_factory, run_test_call=False)
    outputs = execute_retry(
        input_plan,
        output_dir,
        previous_cache_dir=previous_cache_dir,
        token_context=context,
        client_factory=client_factory,
        min_interval_seconds=min_interval_seconds,
        max_retry_per_batch=max_retry_per_batch,
        stop_after_attempt_count=stop_after_attempt_count,
        stop_after_success_count=stop_after_success_count,
        resume_from_existing_cache=resume_from_existing_cache,
        flush_each_batch=True,
    )
    audit = build_retry_quality_audit(context, outputs)
    report = render_report(context, outputs, audit, _git_info(PROJECT_ROOT), output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs.retry_plan.to_csv(output_dir / "daily_basic_fetch_retry_plan.csv", index=False)
    outputs.results.to_csv(output_dir / "daily_basic_fetch_retry_results.csv", index=False)
    outputs.daily_manifest.to_csv(output_dir / "daily_basic_retry_cache_manifest.csv", index=False)
    outputs.stock_manifest.to_csv(output_dir / "stock_basic_retry_cache_manifest.csv", index=False)
    audit.to_csv(output_dir / "daily_basic_fetch_retry_quality_audit.csv", index=False)
    (output_dir / "daily_basic_fetch_retry_v1.md").write_text(report, encoding="utf-8")
    return outputs


def load_input_plan() -> pd.DataFrame:
    if PREVIOUS_EXECUTION_PLAN_PATH.exists():
        return pd.read_csv(PREVIOUS_EXECUTION_PLAN_PATH)
    if PREVIOUS_FETCH_PLAN_PATH.exists():
        return pd.read_csv(PREVIOUS_FETCH_PLAN_PATH)
    return _empty(RETRY_PLAN_COLUMNS)


def main() -> None:
    parser = argparse.ArgumentParser(description="Research-only single-worker Tushare daily_basic retry.")
    parser.add_argument("--min-interval-seconds", type=float, default=DEFAULT_MIN_INTERVAL_SECONDS)
    parser.add_argument("--max-retry-per-batch", type=int, default=DEFAULT_MAX_RETRY_PER_BATCH)
    parser.add_argument("--resume", action="store_true", default=True)
    parser.add_argument("--stop-after-attempt-count", type=int, default=None)
    parser.add_argument("--stop-after-success-count", type=int, default=None)
    args = parser.parse_args()
    input_plan = load_input_plan()
    outputs = write_outputs(
        input_plan,
        OUTPUT_DIR,
        previous_cache_dir=PREVIOUS_FETCH_DIR,
        min_interval_seconds=args.min_interval_seconds,
        max_retry_per_batch=args.max_retry_per_batch,
        stop_after_attempt_count=args.stop_after_attempt_count,
        stop_after_success_count=args.stop_after_success_count,
        resume_from_existing_cache=args.resume,
    )
    audit = pd.read_csv(OUTPUT_DIR / "daily_basic_fetch_retry_quality_audit.csv")
    print(audit.to_string(index=False))
    if contains_actionable_trading_language((OUTPUT_DIR / "daily_basic_fetch_retry_v1.md").read_text(encoding="utf-8")):
        raise SystemExit("forbidden output language detected")


if __name__ == "__main__":
    main()
