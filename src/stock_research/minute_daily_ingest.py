from __future__ import annotations

import errno
import time
from datetime import date
from pathlib import Path
from typing import Any, TextIO

import baostock as bs

from stock_research.config import SETTINGS
from stock_research.daily_close_pipeline import parse_trade_date
from stock_research.minute_data import (
    MINUTE_FIELDS,
    load_active_baostock_codes,
    login_or_raise,
    query_baostock_minute_rows_once,
    request_params,
    upsert_stock_minute_bars,
)
from stock_research.stock_cron_guard import StockCronGuardDecision, decide_stock_cron_run


DEFAULT_MINUTE_DAILY_LOCK = Path("/tmp/stock_research_baostock_minute_daily.lock")


def _result_template(*, status: str, trade_date: date) -> dict[str, Any]:
    return {
        "status": status,
        "trade_date": trade_date.isoformat(),
        "symbol_count": 0,
        "success_count": 0,
        "empty_count": 0,
        "failed_count": 0,
        "retry_count": 0,
        "relogin_count": 0,
        "rows_written": 0,
        "failed_symbols": [],
    }


def _try_acquire_daily_lock(lock_path: Path) -> TextIO | None:
    import fcntl

    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("a+", encoding="utf-8")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        handle.close()
        if exc.errno in {errno.EACCES, errno.EAGAIN}:
            return None
        raise
    return handle


def _release_daily_lock(handle: TextIO | None) -> None:
    import fcntl

    if handle is None:
        return
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    finally:
        handle.close()


def run_baostock_minute_daily(
    *,
    trade_date: str | date | None = None,
    limit_assets: int | None = None,
    sleep_seconds: float = 0.0,
    lock_path: Path = DEFAULT_MINUTE_DAILY_LOCK,
    freq: str = "5min",
    adjust_type: str = "raw",
) -> dict[str, Any]:
    target_date = parse_trade_date(trade_date, "Asia/Shanghai")
    decision = decide_stock_cron_run(
        service=SETTINGS.research_service,
        trade_date=target_date,
        exchanges=("SH", "SZ", "BJ"),
    )
    if not decision.should_run:
        return _result_template(status="skipped_non_trading_day", trade_date=decision.trade_date)

    lock_handle = _try_acquire_daily_lock(lock_path)
    if lock_handle is None:
        return _result_template(status="skipped_locked", trade_date=decision.trade_date)

    result = _result_template(status="success", trade_date=decision.trade_date)
    try:
        codes = load_active_baostock_codes(limit_assets=limit_assets)
        result["symbol_count"] = len(codes)
        login_or_raise()
        for code in codes:
            try:
                params = request_params(code, target_date, target_date, freq, adjust_type)
                rows = query_baostock_minute_rows_once(
                    code,
                    target_date,
                    target_date,
                    freq=freq,
                    adjust_type=adjust_type,
                )
                inserted_rows = upsert_stock_minute_bars(
                    rows,
                    freq=freq,
                    adjust_type=adjust_type,
                    params=params,
                )
            except Exception:
                result["failed_count"] += 1
                result["failed_symbols"].append(code)
            else:
                if inserted_rows > 0:
                    result["success_count"] += inserted_rows
                    result["rows_written"] += inserted_rows
                else:
                    result["empty_count"] += 1
            if sleep_seconds:
                time.sleep(sleep_seconds)
        if result["failed_count"] > 0:
            result["status"] = "partial_success"
        return result
    finally:
        try:
            bs.logout()
        except Exception:
            pass
        _release_daily_lock(lock_handle)
