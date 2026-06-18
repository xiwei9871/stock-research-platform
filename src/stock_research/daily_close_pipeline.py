from __future__ import annotations

import argparse
import concurrent.futures
import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Iterable
from zoneinfo import ZoneInfo

from stock_research.assets import asset_id_from_baostock_code
from stock_research.config import SETTINGS
from stock_research.db import connect, execute, execute_many, fetch_all


JOB_STATUSES = {"pending", "running", "success", "partial_success", "failed", "skipped"}
PIPELINE_READY_STATUSES = {"READY", "DEGRADED_READY"}
PIPELINE_FINAL_STATUSES = {"READY", "DEGRADED_READY", "NOT_READY"}


DAILY_CLOSE_PIPELINE_SQL = """
CREATE SCHEMA IF NOT EXISTS ops;

CREATE TABLE IF NOT EXISTS ops.daily_pipeline_job (
    id text PRIMARY KEY,
    trade_date date NOT NULL,
    job_name text NOT NULL,
    stage text NOT NULL,
    source text NOT NULL DEFAULT '',
    status text NOT NULL CHECK (status IN ('pending', 'running', 'success', 'partial_success', 'failed', 'skipped')),
    started_at timestamptz,
    finished_at timestamptz,
    duration_seconds numeric,
    attempt_count integer NOT NULL DEFAULT 0,
    rows_inserted integer NOT NULL DEFAULT 0,
    rows_updated integer NOT NULL DEFAULT 0,
    rows_failed integer NOT NULL DEFAULT 0,
    missing_symbols_count integer NOT NULL DEFAULT 0,
    error_summary text,
    error_detail_path text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (trade_date, job_name, stage, source)
);

CREATE TABLE IF NOT EXISTS ops.daily_pipeline_quality (
    trade_date date NOT NULL,
    dataset_name text NOT NULL,
    status text NOT NULL CHECK (status IN ('pass', 'warning', 'fail')),
    expected_count integer,
    actual_count integer,
    missing_symbols jsonb NOT NULL DEFAULT '[]'::jsonb,
    abnormal_symbols jsonb NOT NULL DEFAULT '[]'::jsonb,
    check_summary text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (trade_date, dataset_name)
);

CREATE TABLE IF NOT EXISTS ops.daily_pipeline_failed_symbol (
    trade_date date NOT NULL,
    stage text NOT NULL,
    dataset_name text NOT NULL,
    ts_code text NOT NULL,
    source text NOT NULL,
    status text NOT NULL CHECK (status IN ('pending', 'running', 'success', 'failed')) DEFAULT 'pending',
    attempt_count integer NOT NULL DEFAULT 0,
    error_type text,
    error_summary text,
    last_error_at timestamptz,
    next_retry_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (trade_date, stage, dataset_name, ts_code, source)
);

CREATE TABLE IF NOT EXISTS ops.daily_pipeline_status (
    trade_date date PRIMARY KEY,
    pipeline_status text NOT NULL CHECK (pipeline_status IN ('READY', 'DEGRADED_READY', 'NOT_READY')),
    daily_status text NOT NULL,
    minute5_status text NOT NULL,
    deps_status text NOT NULL,
    latest_ready_trade_date date,
    using_fallback_trade_date boolean NOT NULL DEFAULT false,
    warnings jsonb NOT NULL DEFAULT '[]'::jsonb,
    failed_jobs jsonb NOT NULL DEFAULT '[]'::jsonb,
    updated_at timestamptz NOT NULL DEFAULT now()
);
"""


@dataclass(frozen=True)
class PipelineConfig:
    service: str = SETTINGS.research_service
    timezone: str = "Asia/Shanghai"
    tushare_token: str | None = None
    max_workers_daily: int = 8
    max_workers_minute5: int = 8
    request_timeout_seconds: int = 20
    max_retries: int = 3
    minute5_lookback_days: int = 5
    minute5_min_coverage_ratio: float = 0.98
    daily_start_time: str = "17:00"
    minute5_start_time: str = "17:30"
    deps_start_time: str = "19:00"
    finalize_time: str = "19:50"
    force_non_trading_day: bool = False

    @classmethod
    def from_env(cls) -> "PipelineConfig":
        return cls(
            service=os.getenv("DB_SERVICE", SETTINGS.research_service),
            timezone=os.getenv("PIPELINE_TIMEZONE", "Asia/Shanghai"),
            tushare_token=os.getenv("TUSHARE_TOKEN") or load_local_tushare_token(),
            max_workers_daily=int(os.getenv("MAX_WORKERS_DAILY", "8")),
            max_workers_minute5=int(os.getenv("MAX_WORKERS_MINUTE5", "8")),
            request_timeout_seconds=int(os.getenv("REQUEST_TIMEOUT_SECONDS", "20")),
            max_retries=int(os.getenv("MAX_RETRIES", "3")),
            minute5_lookback_days=int(os.getenv("MINUTE5_LOOKBACK_DAYS", "5")),
            minute5_min_coverage_ratio=float(
                os.getenv("MINUTE5_MIN_COVERAGE_RATIO", "0.98")
            ),
            daily_start_time=os.getenv("DAILY_START_TIME", "17:00"),
            minute5_start_time=os.getenv("MINUTE5_START_TIME", "17:30"),
            deps_start_time=os.getenv("DEPS_START_TIME", "19:00"),
            finalize_time=os.getenv("FINALIZE_TIME", "19:50"),
            force_non_trading_day=os.getenv("PIPELINE_FORCE_NON_TRADING_DAY", "").lower()
            in {"1", "true", "yes"},
        )


def load_local_tushare_token(path: str | Path = "config/local_secrets.json") -> str | None:
    secrets_path = Path(path)
    if not secrets_path.exists():
        return None
    try:
        payload = json.loads(secrets_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    token = payload.get("tushare", {}).get("token") if isinstance(payload, dict) else None
    return str(token) if token else None


def parse_trade_date(value: str | date | None, timezone: str = "Asia/Shanghai") -> date:
    if isinstance(value, date):
        return value
    if value:
        return datetime.strptime(value.replace("-", ""), "%Y%m%d").date()
    return datetime.now(ZoneInfo(timezone)).date()


def format_trade_date(value: date) -> str:
    return value.strftime("%Y%m%d")


def ts_code_to_asset_id(ts_code: str) -> str:
    symbol, exchange = ts_code.split(".", 1)
    return asset_id_from_baostock_code(f"{exchange.lower()}.{symbol}")


def ts_code_symbol(ts_code: str) -> str:
    return ts_code.split(".", 1)[0]


def setup_stage_logger(trade_date: date, stage: str) -> tuple[logging.Logger, Path]:
    log_dir = Path("logs") / "pipeline" / format_trade_date(trade_date)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{stage}.log"
    logger = logging.getLogger(f"daily_close_pipeline.{format_trade_date(trade_date)}.{stage}")
    logger.setLevel(logging.INFO)
    logger.handlers = []
    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    logger.propagate = False
    return logger, log_path


def apply_daily_close_pipeline_schema(service: str = SETTINGS.research_service) -> None:
    with connect(service) as conn:
        execute(conn, DAILY_CLOSE_PIPELINE_SQL)


def trading_calendar_status(
    service: str,
    trade_date: date,
    *,
    exchanges: tuple[str, ...] = ("SH", "SZ", "BJ"),
) -> str:
    sql = """
    SELECT
        bool_or(is_open = true) AS calendar_open,
        bool_or(is_open = false) AS calendar_closed,
        count(*)::int AS calendar_rows
    FROM market.trading_calendar
    WHERE trade_date = %s
      AND exchange = ANY(%s)
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, [trade_date, list(exchanges)])
    row = rows[0] if rows else {}
    if bool(row.get("calendar_open")):
        return "open"
    if int(row.get("calendar_rows") or 0) > 0 and bool(row.get("calendar_closed")):
        return "closed"
    return "unknown"


def should_skip_for_holiday(
    service: str,
    trade_date: date,
    *,
    force: bool = False,
) -> tuple[bool, str]:
    if force:
        return False, "forced"
    status = trading_calendar_status(service, trade_date)
    return status == "closed", status


def record_skipped_stage(
    *,
    service: str,
    trade_date: date,
    stage: str,
    job_name: str,
    source: str,
    reason: str,
) -> dict[str, Any]:
    now = datetime.now(ZoneInfo(PipelineConfig.from_env().timezone))
    upsert_job(
        service=service,
        trade_date=trade_date,
        job_name=job_name,
        stage=stage,
        source=source,
        status="skipped",
        started_at=now,
        finished_at=now,
        error_summary=reason,
    )
    return {"stage": stage, "status": "skipped", "reason": reason}


def upsert_job(
    *,
    service: str,
    trade_date: date,
    job_name: str,
    stage: str,
    source: str = "",
    status: str,
    started_at: datetime | None = None,
    finished_at: datetime | None = None,
    attempt_count: int = 0,
    rows_inserted: int = 0,
    rows_updated: int = 0,
    rows_failed: int = 0,
    missing_symbols_count: int = 0,
    error_summary: str | None = None,
    error_detail_path: str | None = None,
) -> None:
    if status not in JOB_STATUSES:
        raise ValueError(f"invalid job status: {status}")
    duration_seconds = None
    if started_at and finished_at:
        duration_seconds = (finished_at - started_at).total_seconds()
    sql = """
    INSERT INTO ops.daily_pipeline_job (
        id, trade_date, job_name, stage, source, status, started_at, finished_at,
        duration_seconds, attempt_count, rows_inserted, rows_updated, rows_failed,
        missing_symbols_count, error_summary, error_detail_path
    )
    VALUES (
        %(id)s, %(trade_date)s, %(job_name)s, %(stage)s, %(source)s, %(status)s,
        %(started_at)s, %(finished_at)s, %(duration_seconds)s, %(attempt_count)s,
        %(rows_inserted)s, %(rows_updated)s, %(rows_failed)s, %(missing_symbols_count)s,
        %(error_summary)s, %(error_detail_path)s
    )
    ON CONFLICT (trade_date, job_name, stage, source) DO UPDATE SET
        status = EXCLUDED.status,
        started_at = COALESCE(ops.daily_pipeline_job.started_at, EXCLUDED.started_at),
        finished_at = EXCLUDED.finished_at,
        duration_seconds = EXCLUDED.duration_seconds,
        attempt_count = EXCLUDED.attempt_count,
        rows_inserted = EXCLUDED.rows_inserted,
        rows_updated = EXCLUDED.rows_updated,
        rows_failed = EXCLUDED.rows_failed,
        missing_symbols_count = EXCLUDED.missing_symbols_count,
        error_summary = EXCLUDED.error_summary,
        error_detail_path = EXCLUDED.error_detail_path,
        updated_at = now()
    """
    payload = {
        "id": f"{trade_date}:{stage}:{job_name}:{source or 'default'}",
        "trade_date": trade_date,
        "job_name": job_name,
        "stage": stage,
        "source": source,
        "status": status,
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_seconds": duration_seconds,
        "attempt_count": attempt_count,
        "rows_inserted": rows_inserted,
        "rows_updated": rows_updated,
        "rows_failed": rows_failed,
        "missing_symbols_count": missing_symbols_count,
        "error_summary": error_summary,
        "error_detail_path": error_detail_path,
    }
    with connect(service) as conn:
        execute(conn, sql, payload)


def upsert_quality(
    *,
    service: str,
    trade_date: date,
    dataset_name: str,
    status: str,
    expected_count: int | None = None,
    actual_count: int | None = None,
    missing_symbols: list[str] | None = None,
    abnormal_symbols: list[str] | None = None,
    check_summary: str | None = None,
) -> None:
    sql = """
    INSERT INTO ops.daily_pipeline_quality (
        trade_date, dataset_name, status, expected_count, actual_count,
        missing_symbols, abnormal_symbols, check_summary
    )
    VALUES (
        %(trade_date)s, %(dataset_name)s, %(status)s, %(expected_count)s, %(actual_count)s,
        %(missing_symbols)s::jsonb, %(abnormal_symbols)s::jsonb, %(check_summary)s
    )
    ON CONFLICT (trade_date, dataset_name) DO UPDATE SET
        status = EXCLUDED.status,
        expected_count = EXCLUDED.expected_count,
        actual_count = EXCLUDED.actual_count,
        missing_symbols = EXCLUDED.missing_symbols,
        abnormal_symbols = EXCLUDED.abnormal_symbols,
        check_summary = EXCLUDED.check_summary,
        updated_at = now()
    """
    payload = {
        "trade_date": trade_date,
        "dataset_name": dataset_name,
        "status": status,
        "expected_count": expected_count,
        "actual_count": actual_count,
        "missing_symbols": json.dumps(missing_symbols or [], ensure_ascii=False),
        "abnormal_symbols": json.dumps(abnormal_symbols or [], ensure_ascii=False),
        "check_summary": check_summary,
    }
    with connect(service) as conn:
        execute(conn, sql, payload)


def record_failed_symbol(
    *,
    service: str,
    trade_date: date,
    stage: str,
    dataset_name: str,
    ts_code: str,
    source: str,
    error_type: str,
    error_summary: str,
    attempt_count: int,
) -> None:
    sql = """
    INSERT INTO ops.daily_pipeline_failed_symbol (
        trade_date, stage, dataset_name, ts_code, source, status, attempt_count,
        error_type, error_summary, last_error_at, next_retry_at
    )
    VALUES (
        %(trade_date)s, %(stage)s, %(dataset_name)s, %(ts_code)s, %(source)s, 'pending',
        %(attempt_count)s, %(error_type)s, %(error_summary)s, now(), now() + interval '10 minutes'
    )
    ON CONFLICT (trade_date, stage, dataset_name, ts_code, source) DO UPDATE SET
        status = 'pending',
        attempt_count = EXCLUDED.attempt_count,
        error_type = EXCLUDED.error_type,
        error_summary = EXCLUDED.error_summary,
        last_error_at = now(),
        next_retry_at = now() + interval '10 minutes',
        updated_at = now()
    """
    with connect(service) as conn:
        execute(
            conn,
            sql,
            {
                "trade_date": trade_date,
                "stage": stage,
                "dataset_name": dataset_name,
                "ts_code": ts_code,
                "source": source,
                "attempt_count": attempt_count,
                "error_type": error_type,
                "error_summary": error_summary[:1000],
            },
        )


def mark_failed_symbol_success(
    service: str, trade_date: date, stage: str, dataset_name: str, ts_code: str, source: str
) -> None:
    sql = """
    UPDATE ops.daily_pipeline_failed_symbol
    SET status = 'success', updated_at = now()
    WHERE trade_date = %s AND stage = %s AND dataset_name = %s AND ts_code = %s AND source = %s
    """
    with connect(service) as conn:
        execute(conn, sql, [trade_date, stage, dataset_name, ts_code, source])


def load_active_ts_codes(service: str, trade_date: date | None = None) -> list[str]:
    sql = """
    SELECT symbol, exchange
    FROM asset_master
    WHERE status = 'listed'
      AND exchange IN ('SH', 'SZ', 'BJ')
    ORDER BY exchange, symbol
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql)
    return [f"{row['symbol']}.{row['exchange']}" for row in rows]


def load_retry_ts_codes(service: str, trade_date: date, stage: str = "minute5") -> list[str]:
    sql = """
    SELECT ts_code
    FROM ops.daily_pipeline_failed_symbol
    WHERE trade_date = %s AND stage = %s AND dataset_name = 'minute5_bar'
      AND source = 'akshare' AND status IN ('pending', 'failed')
    ORDER BY ts_code
    """
    with connect(service) as conn:
        return [str(row["ts_code"]) for row in fetch_all(conn, sql, [trade_date, stage])]


def call_with_timeout(
    func: Callable[..., Any], timeout_seconds: int, *args: Any, **kwargs: Any
) -> Any:
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(func, *args, **kwargs)
        return future.result(timeout=timeout_seconds)


def retry_call(
    func: Callable[[], list[dict[str, Any]]],
    *,
    max_retries: int,
    backoff_seconds: float = 1.0,
) -> tuple[list[dict[str, Any]], int, str | None]:
    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            rows = func()
            return rows, attempt, None
        except Exception as exc:  # noqa: BLE001 - source adapters must record parse/network failures.
            last_error = f"{type(exc).__name__}: {exc}"
            if attempt < max_retries:
                time.sleep(backoff_seconds * attempt)
    return [], max_retries, last_error


def fetch_tushare_daily_rows(
    trade_date: date, *, token: str | None, timeout_seconds: int
) -> list[dict[str, Any]]:
    if not token:
        raise RuntimeError("TUSHARE_TOKEN is not configured")

    def _fetch() -> list[dict[str, Any]]:
        import tushare as ts

        pro = ts.pro_api(token)
        daily = pro.daily(trade_date=format_trade_date(trade_date))
        try:
            basic = pro.daily_basic(trade_date=format_trade_date(trade_date))
        except Exception:  # noqa: BLE001 - daily_basic is enrichment; daily bars remain critical.
            basic = None
        basic_by_code = {
            str(row["ts_code"]): row for row in basic.to_dict("records")
        } if basic is not None and not basic.empty else {}
        rows = []
        for row in daily.to_dict("records"):
            ts_code = str(row["ts_code"])
            basic_row = basic_by_code.get(ts_code, {})
            rows.append(
                {
                    "ts_code": ts_code,
                    "asset_id": ts_code_to_asset_id(ts_code),
                    "trade_date": trade_date,
                    "open": row.get("open"),
                    "high": row.get("high"),
                    "low": row.get("low"),
                    "close": row.get("close"),
                    "preclose": row.get("pre_close"),
                    "volume": row.get("vol"),
                    "amount": row.get("amount"),
                    "turnover_rate": basic_row.get("turnover_rate"),
                    "pct_chg": row.get("pct_chg"),
                    "trade_status": "1",
                    "is_st": False,
                    "adjust_type": "raw",
                    "source": "tushare",
                }
            )
        return rows

    return call_with_timeout(_fetch, timeout_seconds)


def fetch_akshare_daily_rows(
    trade_date: date, *, ts_codes: list[str], timeout_seconds: int
) -> list[dict[str, Any]]:
    def _fetch_one(ts_code: str) -> list[dict[str, Any]]:
        import akshare as ak

        frame = ak.stock_zh_a_hist(
            symbol=ts_code_symbol(ts_code),
            period="daily",
            start_date=format_trade_date(trade_date),
            end_date=format_trade_date(trade_date),
            adjust="",
        )
        if frame is None or frame.empty:
            return []
        row = frame.iloc[-1].to_dict()
        return [
            {
                "ts_code": ts_code,
                "asset_id": ts_code_to_asset_id(ts_code),
                "trade_date": trade_date,
                "open": row.get("开盘"),
                "high": row.get("最高"),
                "low": row.get("最低"),
                "close": row.get("收盘"),
                "preclose": None,
                "volume": row.get("成交量"),
                "amount": row.get("成交额"),
                "turnover_rate": row.get("换手率"),
                "pct_chg": row.get("涨跌幅"),
                "trade_status": "1",
                "is_st": False,
                "adjust_type": "raw",
                "source": "akshare",
            }
        ]

    rows: list[dict[str, Any]] = []
    for ts_code in ts_codes:
        rows.extend(call_with_timeout(_fetch_one, timeout_seconds, ts_code))
    return rows


def fetch_akshare_minute5_rows(
    ts_code: str, *, start_date: date, end_date: date, timeout_seconds: int
) -> list[dict[str, Any]]:
    def _fetch() -> list[dict[str, Any]]:
        import akshare as ak

        frame = ak.stock_zh_a_hist_min_em(
            symbol=ts_code_symbol(ts_code),
            period="5",
            start_date=f"{start_date:%Y-%m-%d} 09:30:00",
            end_date=f"{end_date:%Y-%m-%d} 15:00:00",
            adjust="",
        )
        if frame is None or frame.empty:
            return []
        rows = []
        for row in frame.to_dict("records"):
            trade_time = row.get("时间") or row.get("date") or row.get("datetime")
            if not trade_time:
                continue
            trade_time_dt = datetime.fromisoformat(str(trade_time).replace("/", "-"))
            rows.append(
                {
                    "asset_id": ts_code_to_asset_id(ts_code),
                    "ts_code": ts_code,
                    "trade_time": trade_time_dt,
                    "trade_date": trade_time_dt.date(),
                    "freq": "5min",
                    "adjust_type": "raw",
                    "open": row.get("开盘"),
                    "high": row.get("最高"),
                    "low": row.get("最低"),
                    "close": row.get("收盘"),
                    "volume": row.get("成交量"),
                    "amount": row.get("成交额"),
                    "source": "akshare",
                }
            )
        return rows

    return call_with_timeout(_fetch, timeout_seconds)


def normalize_daily_rows(rows: Iterable[dict[str, Any]], source: str) -> list[dict[str, Any]]:
    normalized = []
    for row in rows:
        ts_code = str(row.get("ts_code") or "")
        if not ts_code:
            continue
        item = dict(row)
        item.setdefault("asset_id", ts_code_to_asset_id(ts_code))
        item.setdefault("adjust_type", "raw")
        item.setdefault("trade_status", "1")
        item.setdefault("is_st", False)
        item["source"] = source
        normalized.append(item)
    return normalized


def upsert_daily_bars(service: str, rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    sql = """
    INSERT INTO market_daily_bar (
        asset_id, trade_date, open, high, low, close, preclose, volume, amount,
        turnover_rate, pct_chg, trade_status, is_st, adjust_type, source
    )
    VALUES (
        %(asset_id)s, %(trade_date)s, %(open)s, %(high)s, %(low)s, %(close)s,
        %(preclose)s, %(volume)s, %(amount)s, %(turnover_rate)s, %(pct_chg)s,
        %(trade_status)s, %(is_st)s, %(adjust_type)s, %(source)s
    )
    ON CONFLICT (asset_id, trade_date, adjust_type) DO UPDATE SET
        open = EXCLUDED.open,
        high = EXCLUDED.high,
        low = EXCLUDED.low,
        close = EXCLUDED.close,
        preclose = EXCLUDED.preclose,
        volume = EXCLUDED.volume,
        amount = EXCLUDED.amount,
        turnover_rate = EXCLUDED.turnover_rate,
        pct_chg = EXCLUDED.pct_chg,
        trade_status = EXCLUDED.trade_status,
        is_st = EXCLUDED.is_st,
        source = EXCLUDED.source,
        updated_at = now()
    """
    with connect(service) as conn:
        execute_many(conn, sql, rows)
    return len(rows)


def upsert_minute5_bars(service: str, rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    sql = """
    INSERT INTO market.stock_minute_bar (
        asset_id, ts_code, trade_time, trade_date, freq, adjust_type,
        open, high, low, close, volume, amount, source
    )
    VALUES (
        %(asset_id)s, %(ts_code)s, %(trade_time)s, %(trade_date)s, %(freq)s,
        %(adjust_type)s, %(open)s, %(high)s, %(low)s, %(close)s, %(volume)s,
        %(amount)s, %(source)s
    )
    ON CONFLICT (trade_date, asset_id, trade_time, freq, adjust_type, source) DO UPDATE SET
        open = EXCLUDED.open,
        high = EXCLUDED.high,
        low = EXCLUDED.low,
        close = EXCLUDED.close,
        volume = EXCLUDED.volume,
        amount = EXCLUDED.amount,
        updated_at = now()
    """
    with connect(service) as conn:
        execute_many(conn, sql, rows)
    return len(rows)


def inspect_daily_quality(
    rows: list[dict[str, Any]], expected_ts_codes: list[str], trade_date: date
) -> dict[str, Any]:
    by_code = {str(row["ts_code"]): row for row in rows if row.get("trade_date") == trade_date}
    missing = sorted(set(expected_ts_codes) - set(by_code))
    abnormal = []
    for ts_code, row in by_code.items():
        open_, high, low, close = row.get("open"), row.get("high"), row.get("low"), row.get("close")
        if any(value in (None, 0) for value in [open_, high, low, close]):
            abnormal.append(ts_code)
            continue
        try:
            if not (float(low) <= float(close) <= float(high)):
                abnormal.append(ts_code)
        except (TypeError, ValueError):
            abnormal.append(ts_code)
    status = "pass"
    if missing or abnormal:
        status = "warning" if by_code else "fail"
    return {
        "status": status,
        "expected_count": len(expected_ts_codes),
        "actual_count": len(by_code),
        "missing_symbols": missing,
        "abnormal_symbols": sorted(set(abnormal)),
        "check_summary": f"daily rows={len(by_code)} missing={len(missing)} abnormal={len(set(abnormal))}",
    }


def inspect_minute5_quality(
    rows_by_symbol: dict[str, list[dict[str, Any]]],
    expected_ts_codes: list[str],
    target_date: date,
) -> dict[str, Any]:
    missing, abnormal = [], []
    covered = 0
    for ts_code in expected_ts_codes:
        bars = [row for row in rows_by_symbol.get(ts_code, []) if row.get("trade_date") == target_date]
        if not bars:
            missing.append(ts_code)
            continue
        covered += 1
        bar_count = len(bars)
        times = {row["trade_time"].time() for row in bars if row.get("trade_time")}
        has_morning = any("09:" <= str(value) <= "11:35:00" for value in times)
        has_afternoon = any("13:" <= str(value) <= "15:05:00" for value in times)
        if bar_count < 40 or not has_morning or not has_afternoon:
            abnormal.append(ts_code)
    status = "pass"
    if missing or abnormal:
        status = "warning" if covered else "fail"
    return {
        "status": status,
        "expected_count": len(expected_ts_codes),
        "actual_count": covered,
        "missing_symbols": missing,
        "abnormal_symbols": sorted(set(abnormal)),
        "check_summary": f"minute5 covered={covered} missing={len(missing)} abnormal={len(set(abnormal))}",
    }


def run_daily_stage(
    trade_date: date,
    *,
    config: PipelineConfig,
    ts_codes: list[str] | None = None,
    tushare_fetcher: Callable[..., list[dict[str, Any]]] = fetch_tushare_daily_rows,
    akshare_fetcher: Callable[..., list[dict[str, Any]]] = fetch_akshare_daily_rows,
    daily_upserter: Callable[[str, list[dict[str, Any]]], int] = upsert_daily_bars,
) -> dict[str, Any]:
    skip, calendar_status = should_skip_for_holiday(
        config.service, trade_date, force=config.force_non_trading_day
    )
    if skip:
        return record_skipped_stage(
            service=config.service,
            trade_date=trade_date,
            stage="daily",
            job_name="daily_bar",
            source="calendar",
            reason=f"non_trading_day:{calendar_status}",
        )
    logger, log_path = setup_stage_logger(trade_date, "daily")
    started = datetime.now(ZoneInfo(config.timezone))
    upsert_job(
        service=config.service,
        trade_date=trade_date,
        job_name="daily_bar",
        stage="daily",
        source="mixed",
        status="running",
        started_at=started,
    )
    expected_ts_codes = ts_codes or load_active_ts_codes(config.service, trade_date)
    logger.info("daily stage started source=tushare expected=%s", len(expected_ts_codes))
    tushare_rows, tushare_attempts, tushare_error = retry_call(
        lambda: tushare_fetcher(
            trade_date, token=config.tushare_token, timeout_seconds=config.request_timeout_seconds
        ),
        max_retries=config.max_retries,
    )
    normalized_tushare = normalize_daily_rows(tushare_rows, "tushare")
    tushare_codes = {row["ts_code"] for row in normalized_tushare}
    missing_after_tushare = sorted(set(expected_ts_codes) - tushare_codes)
    akshare_rows: list[dict[str, Any]] = []
    akshare_attempts = 0
    akshare_error = None
    if missing_after_tushare:
        logger.info("daily fallback source=akshare missing=%s", len(missing_after_tushare))
        akshare_rows, akshare_attempts, akshare_error = retry_call(
            lambda: akshare_fetcher(
                trade_date,
                ts_codes=missing_after_tushare,
                timeout_seconds=config.request_timeout_seconds,
            ),
            max_retries=config.max_retries,
        )
    normalized_akshare = normalize_daily_rows(akshare_rows, "akshare")
    akshare_rows_by_code = {row["ts_code"]: row for row in normalized_akshare}
    final_rows = normalized_tushare + [
        row for code, row in akshare_rows_by_code.items() if code not in tushare_codes
    ]
    rows_upserted = daily_upserter(config.service, final_rows)
    quality = inspect_daily_quality(final_rows, expected_ts_codes, trade_date)
    upsert_quality(service=config.service, trade_date=trade_date, dataset_name="daily_bar", **quality)
    finished = datetime.now(ZoneInfo(config.timezone))
    status = "success" if quality["status"] in {"pass", "warning"} and final_rows else "failed"
    if status == "success" and (quality["missing_symbols"] or quality["abnormal_symbols"]):
        status = "partial_success"
    error_summary = tushare_error or akshare_error
    upsert_job(
        service=config.service,
        trade_date=trade_date,
        job_name="daily_bar",
        stage="daily",
        source="mixed" if normalized_tushare and normalized_akshare else ("tushare" if normalized_tushare else "akshare"),
        status=status,
        started_at=started,
        finished_at=finished,
        attempt_count=max(tushare_attempts, akshare_attempts),
        rows_inserted=rows_upserted,
        rows_failed=len(quality["missing_symbols"]),
        missing_symbols_count=len(quality["missing_symbols"]),
        error_summary=error_summary,
        error_detail_path=str(log_path) if error_summary else None,
    )
    logger.info(
        "daily stage finished status=%s rows=%s missing=%s abnormal=%s",
        status,
        rows_upserted,
        len(quality["missing_symbols"]),
        len(quality["abnormal_symbols"]),
    )
    return {"stage": "daily", "status": status, "rows": rows_upserted, "quality": quality}


def run_minute5_stage(
    trade_date: date,
    *,
    config: PipelineConfig,
    ts_codes: list[str] | None = None,
    fetcher: Callable[..., list[dict[str, Any]]] = fetch_akshare_minute5_rows,
    upserter: Callable[[str, list[dict[str, Any]]], int] = upsert_minute5_bars,
) -> dict[str, Any]:
    skip, calendar_status = should_skip_for_holiday(
        config.service, trade_date, force=config.force_non_trading_day
    )
    if skip:
        return record_skipped_stage(
            service=config.service,
            trade_date=trade_date,
            stage="minute5",
            job_name="minute5_bar",
            source="calendar",
            reason=f"non_trading_day:{calendar_status}",
        )
    logger, log_path = setup_stage_logger(trade_date, "minute5")
    started = datetime.now(ZoneInfo(config.timezone))
    upsert_job(
        service=config.service,
        trade_date=trade_date,
        job_name="minute5_bar",
        stage="minute5",
        source="akshare",
        status="running",
        started_at=started,
    )
    expected_ts_codes = ts_codes or load_active_ts_codes(config.service, trade_date)
    lookback_start = trade_date - timedelta(days=max(config.minute5_lookback_days - 1, 0))
    rows_by_symbol: dict[str, list[dict[str, Any]]] = {}
    failures: dict[str, str] = {}
    attempts: dict[str, int] = {}

    def _one(ts_code: str) -> tuple[str, list[dict[str, Any]], int, str | None]:
        rows, attempt_count, error = retry_call(
            lambda: fetcher(
                ts_code,
                start_date=lookback_start,
                end_date=trade_date,
                timeout_seconds=config.request_timeout_seconds,
            ),
            max_retries=config.max_retries,
        )
        return ts_code, rows, attempt_count, error

    with concurrent.futures.ThreadPoolExecutor(max_workers=config.max_workers_minute5) as executor:
        for ts_code, rows, attempt_count, error in executor.map(_one, expected_ts_codes):
            attempts[ts_code] = attempt_count
            if error:
                failures[ts_code] = error
                record_failed_symbol(
                    service=config.service,
                    trade_date=trade_date,
                    stage="minute5",
                    dataset_name="minute5_bar",
                    ts_code=ts_code,
                    source="akshare",
                    error_type=error.split(":", 1)[0],
                    error_summary=error,
                    attempt_count=attempt_count,
                )
            else:
                rows_by_symbol[ts_code] = rows
    all_rows = [row for rows in rows_by_symbol.values() for row in rows]
    rows_upserted = upserter(config.service, all_rows)
    quality = inspect_minute5_quality(rows_by_symbol, expected_ts_codes, trade_date)
    upsert_quality(service=config.service, trade_date=trade_date, dataset_name="minute5_bar", **quality)
    coverage = quality["actual_count"] / quality["expected_count"] if quality["expected_count"] else 1.0
    if not all_rows:
        status = "failed"
    elif failures or coverage < 1.0:
        status = "partial_success" if coverage >= config.minute5_min_coverage_ratio else "failed"
    else:
        status = "success"
    finished = datetime.now(ZoneInfo(config.timezone))
    upsert_job(
        service=config.service,
        trade_date=trade_date,
        job_name="minute5_bar",
        stage="minute5",
        source="akshare",
        status=status,
        started_at=started,
        finished_at=finished,
        attempt_count=max(attempts.values(), default=0),
        rows_inserted=rows_upserted,
        rows_failed=len(failures),
        missing_symbols_count=len(quality["missing_symbols"]),
        error_summary="; ".join(f"{code}:{err}" for code, err in list(failures.items())[:5]) or None,
        error_detail_path=str(log_path) if failures else None,
    )
    logger.info(
        "minute5 stage finished status=%s rows=%s failures=%s coverage=%.4f",
        status,
        rows_upserted,
        len(failures),
        coverage,
    )
    return {
        "stage": "minute5",
        "status": status,
        "rows": rows_upserted,
        "failed_symbols": sorted(failures),
        "quality": quality,
    }


def run_retry_failed_stage(
    trade_date: date,
    *,
    config: PipelineConfig,
    fetcher: Callable[..., list[dict[str, Any]]] = fetch_akshare_minute5_rows,
    upserter: Callable[[str, list[dict[str, Any]]], int] = upsert_minute5_bars,
) -> dict[str, Any]:
    ts_codes = load_retry_ts_codes(config.service, trade_date, "minute5")
    if not ts_codes:
        return {"stage": "retry_failed", "status": "skipped", "rows": 0, "failed_symbols": []}
    result = run_minute5_stage(
        trade_date, config=config, ts_codes=ts_codes, fetcher=fetcher, upserter=upserter
    )
    for ts_code in ts_codes:
        if ts_code not in result.get("failed_symbols", []):
            mark_failed_symbol_success(
                config.service, trade_date, "minute5", "minute5_bar", ts_code, "akshare"
            )
    return {"stage": "retry_failed", **result}


@dataclass(frozen=True)
class DependencyTask:
    name: str
    critical: bool
    runner: Callable[[date], dict[str, Any]]


def default_dependency_tasks(config: PipelineConfig) -> list[DependencyTask]:
    def _factor_task(trade_date: date) -> dict[str, Any]:
        from stock_research.daily_pipeline import run_daily_factor_pipeline

        result = run_daily_factor_pipeline(
            trade_date=format_trade_date(trade_date),
            score_version="approved_v1",
        )
        rows = int(result.get("factor_rows", 0)) + int(result.get("score_rows", 0))
        return {"status": "success", "rows": rows}

    return [DependencyTask(name="daily_factor_pipeline", critical=True, runner=_factor_task)]


def run_deps_stage(
    trade_date: date,
    *,
    config: PipelineConfig,
    tasks: list[DependencyTask] | None = None,
) -> dict[str, Any]:
    skip, calendar_status = should_skip_for_holiday(
        config.service, trade_date, force=config.force_non_trading_day
    )
    if skip:
        return record_skipped_stage(
            service=config.service,
            trade_date=trade_date,
            stage="deps",
            job_name="deps",
            source="calendar",
            reason=f"non_trading_day:{calendar_status}",
        )
    logger, _log_path = setup_stage_logger(trade_date, "deps")
    task_list = tasks if tasks is not None else default_dependency_tasks(config)
    failures, optional_failures = [], []
    for task in task_list:
        started = datetime.now(ZoneInfo(config.timezone))
        status = "success"
        error_summary = None
        rows = 0
        try:
            result = task.runner(trade_date)
            rows = int(result.get("rows", 0))
            if result.get("status") in {"failed", "error"}:
                raise RuntimeError(str(result))
        except Exception as exc:  # noqa: BLE001 - dependency failure must be recorded, not swallowed.
            status = "failed"
            error_summary = f"{type(exc).__name__}: {exc}"
            (failures if task.critical else optional_failures).append(task.name)
            logger.exception("dependency task failed name=%s critical=%s", task.name, task.critical)
        finished = datetime.now(ZoneInfo(config.timezone))
        upsert_job(
            service=config.service,
            trade_date=trade_date,
            job_name=task.name,
            stage="deps",
            source="internal",
            status=status,
            started_at=started,
            finished_at=finished,
            attempt_count=1,
            rows_inserted=rows,
            rows_failed=1 if status == "failed" else 0,
            error_summary=error_summary,
        )
    stage_status = "failed" if failures else ("partial_success" if optional_failures else "success")
    return {
        "stage": "deps",
        "status": stage_status,
        "critical_failures": failures,
        "optional_failures": optional_failures,
    }


def latest_ready_trade_date(service: str) -> date | None:
    sql = """
    SELECT trade_date
    FROM ops.daily_pipeline_status
    WHERE pipeline_status IN ('READY', 'DEGRADED_READY')
    ORDER BY trade_date DESC
    LIMIT 1
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql)
    return rows[0]["trade_date"] if rows else None


def _stage_status_from_jobs(rows: list[dict[str, Any]], stage: str) -> str:
    stage_rows = [row for row in rows if row["stage"] == stage]
    if not stage_rows:
        return "skipped"
    statuses = {row["status"] for row in stage_rows}
    if "failed" in statuses:
        return "failed"
    if "partial_success" in statuses:
        return "partial_success"
    if statuses <= {"success", "skipped"}:
        return "success"
    return "running"


def finalize_pipeline_status(trade_date: date, *, config: PipelineConfig) -> dict[str, Any]:
    calendar_status = trading_calendar_status(config.service, trade_date)
    sql = """
    SELECT job_name, stage, source, status, error_summary, missing_symbols_count, updated_at
    FROM ops.daily_pipeline_job
    WHERE trade_date = %s
    ORDER BY stage, job_name, source
    """
    with connect(config.service) as conn:
        rows = fetch_all(conn, sql, [trade_date])
    daily_status = _stage_status_from_jobs(rows, "daily")
    minute5_status = _stage_status_from_jobs(rows, "minute5")
    deps_status = _stage_status_from_jobs(rows, "deps")
    failed_jobs = [
        {
            "stage": row["stage"],
            "job_name": row["job_name"],
            "source": row["source"],
            "status": row["status"],
            "error_summary": row.get("error_summary"),
        }
        for row in rows
        if row["status"] in {"failed", "partial_success"}
    ]
    non_trading_day = calendar_status == "closed"
    critical_ok = daily_status in {"success", "partial_success"} and minute5_status in {
        "success",
        "partial_success",
    } and deps_status in {"success", "partial_success", "skipped"}
    if non_trading_day:
        pipeline_status = "READY"
    elif not critical_ok or daily_status == "failed" or minute5_status == "failed":
        pipeline_status = "NOT_READY"
    elif any(row["status"] == "partial_success" for row in rows):
        pipeline_status = "DEGRADED_READY"
    else:
        pipeline_status = "READY"
    current_latest_ready = latest_ready_trade_date(config.service)
    visible_trade_date = (
        current_latest_ready
        if non_trading_day
        else trade_date
        if pipeline_status in PIPELINE_READY_STATUSES
        else current_latest_ready
    )
    warnings = []
    if non_trading_day:
        warnings.append("non_trading_day_skipped")
    if pipeline_status == "NOT_READY":
        warnings.append("using_previous_ready_trade_date" if visible_trade_date else "no_ready_trade_date")
    if pipeline_status == "DEGRADED_READY":
        warnings.append("optional_or_partial_data_failed")
    payload = {
        "trade_date": trade_date,
        "pipeline_status": pipeline_status,
        "daily_status": daily_status,
        "minute5_status": minute5_status,
        "deps_status": deps_status,
        "latest_ready_trade_date": visible_trade_date,
        "using_fallback_trade_date": pipeline_status == "NOT_READY" or non_trading_day,
        "warnings": warnings,
        "failed_jobs": failed_jobs,
    }
    sql_upsert = """
    INSERT INTO ops.daily_pipeline_status (
        trade_date, pipeline_status, daily_status, minute5_status, deps_status,
        latest_ready_trade_date, using_fallback_trade_date, warnings, failed_jobs
    )
    VALUES (
        %(trade_date)s, %(pipeline_status)s, %(daily_status)s, %(minute5_status)s,
        %(deps_status)s, %(latest_ready_trade_date)s, %(using_fallback_trade_date)s,
        %(warnings)s::jsonb, %(failed_jobs)s::jsonb
    )
    ON CONFLICT (trade_date) DO UPDATE SET
        pipeline_status = EXCLUDED.pipeline_status,
        daily_status = EXCLUDED.daily_status,
        minute5_status = EXCLUDED.minute5_status,
        deps_status = EXCLUDED.deps_status,
        latest_ready_trade_date = EXCLUDED.latest_ready_trade_date,
        using_fallback_trade_date = EXCLUDED.using_fallback_trade_date,
        warnings = EXCLUDED.warnings,
        failed_jobs = EXCLUDED.failed_jobs,
        updated_at = now()
    """
    db_payload = dict(payload)
    db_payload["warnings"] = json.dumps(warnings, ensure_ascii=False)
    db_payload["failed_jobs"] = json.dumps(failed_jobs, ensure_ascii=False, default=str)
    with connect(config.service) as conn:
        execute(conn, sql_upsert, db_payload)
    return payload


def load_data_status_for_dashboard(
    service: str = SETTINGS.research_service, current_trade_date: date | None = None
) -> dict[str, Any]:
    sql = """
    SELECT trade_date, pipeline_status, daily_status, minute5_status, deps_status,
           latest_ready_trade_date, using_fallback_trade_date, warnings, failed_jobs, updated_at
    FROM ops.daily_pipeline_status
    ORDER BY trade_date DESC
    LIMIT 1
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql)
    if not rows:
        return {
            "latest_ready_trade_date": None,
            "current_trade_date": current_trade_date.isoformat() if current_trade_date else None,
            "pipeline_status": "NOT_READY",
            "daily_status": "skipped",
            "minute5_status": "skipped",
            "deps_status": "skipped",
            "failed_jobs": [],
            "warnings": ["pipeline_status_not_initialized"],
            "last_updated_at": None,
        }
    row = rows[0]
    return {
        "latest_ready_trade_date": row["latest_ready_trade_date"].isoformat()
        if row["latest_ready_trade_date"]
        else None,
        "current_trade_date": current_trade_date.isoformat()
        if current_trade_date
        else row["trade_date"].isoformat(),
        "pipeline_status": row["pipeline_status"],
        "daily_status": row["daily_status"],
        "minute5_status": row["minute5_status"],
        "deps_status": row["deps_status"],
        "failed_jobs": row["failed_jobs"] or [],
        "warnings": row["warnings"] or [],
        "last_updated_at": row["updated_at"].isoformat() if row.get("updated_at") else None,
    }


def resolve_strategy_trade_date(
    requested_trade_date: str | date | None,
    *,
    service: str = SETTINGS.research_service,
    require_ready: bool = False,
) -> str:
    requested = parse_trade_date(requested_trade_date) if requested_trade_date else None
    if requested:
        sql = "SELECT pipeline_status FROM ops.daily_pipeline_status WHERE trade_date = %s"
        try:
            with connect(service) as conn:
                rows = fetch_all(conn, sql, [requested])
        except Exception:  # noqa: BLE001 - keep legacy strategy calls usable before schema bootstrap.
            return requested.isoformat()
        if rows and rows[0]["pipeline_status"] in PIPELINE_READY_STATUSES:
            return requested.isoformat()
        if require_ready:
            raise RuntimeError(f"trade_date {requested.isoformat()} is not pipeline ready")
    latest = latest_ready_trade_date(service)
    if latest is None:
        if requested:
            return requested.isoformat()
        raise RuntimeError("no pipeline ready trade date is available")
    return latest.isoformat()


def run_pipeline_stage(stage: str, trade_date: date, config: PipelineConfig) -> dict[str, Any]:
    apply_daily_close_pipeline_schema(config.service)
    if stage == "daily":
        return run_daily_stage(trade_date, config=config)
    if stage == "minute5":
        return run_minute5_stage(trade_date, config=config)
    if stage == "deps":
        return run_deps_stage(trade_date, config=config)
    if stage == "retry_failed":
        return run_retry_failed_stage(trade_date, config=config)
    if stage in {"health", "finalize"}:
        return finalize_pipeline_status(trade_date, config=config)
    if stage == "status":
        return load_data_status_for_dashboard(config.service, trade_date)
    if stage == "all":
        results = {
            "daily": run_daily_stage(trade_date, config=config),
            "minute5": run_minute5_stage(trade_date, config=config),
            "deps": run_deps_stage(trade_date, config=config),
        }
        results["health"] = finalize_pipeline_status(trade_date, config=config)
        return results
    raise ValueError(f"unsupported stage: {stage}")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m scripts.daily_pipeline")
    parser.add_argument("--date", help="Trade date in YYYYMMDD or YYYY-MM-DD")
    parser.add_argument(
        "--stage",
        choices=["all", "daily", "minute5", "deps", "health", "retry_failed", "status"],
        default="all",
    )
    parser.add_argument("--apply-schema", action="store_true", default=True)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Run even when market.trading_calendar marks the date as closed.",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_arg_parser().parse_args(argv)
    config = PipelineConfig.from_env()
    if args.force:
        config = PipelineConfig(**{**config.__dict__, "force_non_trading_day": True})
    trade_date = parse_trade_date(args.date, config.timezone)
    result = run_pipeline_stage(args.stage, trade_date, config)
    print(json.dumps(result, ensure_ascii=False, default=str, indent=2))


if __name__ == "__main__":
    main()
