from __future__ import annotations

import errno
import json
import time
from datetime import date
from pathlib import Path
from typing import Any, TextIO

import baostock as bs

from stock_research.config import SETTINGS
from stock_research.daily_close_pipeline import parse_trade_date
from stock_research.minute_data import (
    BAOSTOCK_RETRY_SLEEP_SECONDS,
    MINUTE_FIELDS,
    is_retryable_baostock_error,
    load_active_baostock_codes,
    login_or_raise,
    query_baostock_minute_rows_once,
    relogin_or_raise,
    request_params,
    upsert_stock_minute_bars,
)
from stock_research.stock_cron_guard import StockCronGuardDecision, decide_stock_cron_run


DEFAULT_MINUTE_DAILY_LOCK = Path("/tmp/stock_research_baostock_minute_daily.lock")
RELOGIN_FAILURE_THRESHOLD = 3


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
        "last_error": None,
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


def _write_daily_artifacts(result: dict[str, Any], output_dir: str | Path) -> None:
    artifact_dir = Path(output_dir) / "baostock_minute_daily" / str(result["trade_date"])
    artifact_dir.mkdir(parents=True, exist_ok=True)
    (artifact_dir / "summary.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    failed_symbols = result.get("failed_symbols") or []
    failed_text = "\n".join(failed_symbols)
    if failed_text:
        failed_text += "\n"
    (artifact_dir / "failed_symbols.txt").write_text(failed_text, encoding="utf-8")


def _fetch_symbol_with_policy(
    code: str,
    target_date: date,
    *,
    freq: str,
    adjust_type: str,
    retry_limit: int,
    timeout_seconds: float | None = None,
) -> tuple[list[dict[str, str]] | None, int, str | None]:
    del timeout_seconds

    last_error = None
    for attempt in range(retry_limit + 1):
        try:
            rows = query_baostock_minute_rows_once(
                code,
                target_date,
                target_date,
                freq=freq,
                adjust_type=adjust_type,
            )
            return rows, attempt, None
        except Exception as exc:  # noqa: BLE001 - per-symbol errors become retry queue entries.
            last_error = str(exc)
            if attempt >= retry_limit or not is_retryable_baostock_error(last_error):
                return None, attempt, last_error
            time.sleep(BAOSTOCK_RETRY_SLEEP_SECONDS)
    return None, retry_limit, last_error


def _write_symbol_rows(
    code: str,
    rows: list[dict[str, str]],
    target_date: date,
    *,
    freq: str,
    adjust_type: str,
) -> tuple[int | None, str | None]:
    try:
        params = request_params(code, target_date, target_date, freq, adjust_type)
        inserted_rows = upsert_stock_minute_bars(
            rows,
            freq=freq,
            adjust_type=adjust_type,
            params=params,
        )
    except Exception as exc:  # noqa: BLE001 - symbol-local write failures belong in partial results.
        return None, str(exc)
    return inserted_rows, None


def _run_retry_queue(
    retry_queue: list[str],
    *,
    target_date: date,
    freq: str,
    adjust_type: str,
    retry_limit: int,
    cooldown_seconds: int,
    timeout_seconds: float | None,
    result: dict[str, Any],
) -> tuple[list[str], dict[str, str]]:
    failed_symbols: list[str] = []
    failed_errors: dict[str, str] = {}
    consecutive_retryable_failures = 0
    for index, code in enumerate(retry_queue):
        rows, retry_count, error = _fetch_symbol_with_policy(
            code,
            target_date,
            freq=freq,
            adjust_type=adjust_type,
            retry_limit=retry_limit,
            timeout_seconds=timeout_seconds,
        )
        result["retry_count"] += retry_count
        if error is not None or rows is None:
            failed_symbols.append(code)
            if error is not None:
                failed_errors[code] = error
            if error is not None and is_retryable_baostock_error(error):
                consecutive_retryable_failures += 1
                has_remaining_work = index + 1 < len(retry_queue)
                if consecutive_retryable_failures >= RELOGIN_FAILURE_THRESHOLD and has_remaining_work:
                    relogin_or_raise()
                    result["relogin_count"] += 1
                    consecutive_retryable_failures = 0
                    if cooldown_seconds > 0:
                        time.sleep(cooldown_seconds)
            else:
                consecutive_retryable_failures = 0
            continue

        consecutive_retryable_failures = 0
        inserted_rows, write_error = _write_symbol_rows(
            code,
            rows,
            target_date,
            freq=freq,
            adjust_type=adjust_type,
        )
        if write_error is not None or inserted_rows is None:
            failed_symbols.append(code)
            if write_error is not None:
                failed_errors[code] = write_error
            continue

        if inserted_rows > 0:
            result["success_count"] += 1
            result["rows_written"] += inserted_rows
        else:
            result["empty_count"] += 1
    return failed_symbols, failed_errors


def run_baostock_minute_daily(
    *,
    trade_date: str | date | None = None,
    limit_assets: int | None = None,
    sleep_seconds: float = 0.0,
    lock_path: Path = DEFAULT_MINUTE_DAILY_LOCK,
    retry_limit: int = 2,
    cooldown_seconds: int = 600,
    timeout_seconds: float | None = None,
    output_dir: str | Path = "outputs/research",
) -> dict[str, Any]:
    if retry_limit < 0:
        raise ValueError("retry_limit must be >= 0")

    freq = "5min"
    adjust_type = "raw"
    target_date = parse_trade_date(trade_date, "Asia/Shanghai")
    decision = decide_stock_cron_run(
        service=SETTINGS.research_service,
        trade_date=target_date,
        exchanges=("SH", "SZ", "BJ"),
    )
    if not decision.should_run:
        result = _result_template(status="skipped_non_trading_day", trade_date=decision.trade_date)
        _write_daily_artifacts(result, output_dir)
        return result

    lock_handle = _try_acquire_daily_lock(lock_path)
    if lock_handle is None:
        result = _result_template(status="skipped_locked", trade_date=decision.trade_date)
        _write_daily_artifacts(result, output_dir)
        return result

    result = _result_template(status="success", trade_date=decision.trade_date)
    try:
        retry_queue: list[str] = []
        write_failed_symbols: list[str] = []
        write_failed_errors: dict[str, str] = {}
        consecutive_retryable_failures = 0
        codes = load_active_baostock_codes(limit_assets=limit_assets)
        result["symbol_count"] = len(codes)
        login_or_raise()
        for index, code in enumerate(codes):
            rows, retry_count, error = _fetch_symbol_with_policy(
                code,
                decision.trade_date,
                freq=freq,
                adjust_type=adjust_type,
                retry_limit=retry_limit,
                timeout_seconds=timeout_seconds,
            )
            result["retry_count"] += retry_count
            if error is not None or rows is None:
                retry_queue.append(code)
                result["last_error"] = error
                if error is not None and is_retryable_baostock_error(error):
                    consecutive_retryable_failures += 1
                    if consecutive_retryable_failures >= RELOGIN_FAILURE_THRESHOLD:
                        relogin_or_raise()
                        result["relogin_count"] += 1
                        consecutive_retryable_failures = 0
                        if cooldown_seconds > 0:
                            time.sleep(cooldown_seconds)
                else:
                    consecutive_retryable_failures = 0
            else:
                consecutive_retryable_failures = 0
                inserted_rows, write_error = _write_symbol_rows(
                    code,
                    rows,
                    decision.trade_date,
                    freq=freq,
                    adjust_type=adjust_type,
                )
                if write_error is not None or inserted_rows is None:
                    write_failed_symbols.append(code)
                    if write_error is not None:
                        write_failed_errors[code] = write_error
                        result["last_error"] = write_error
                else:
                    if inserted_rows > 0:
                        result["success_count"] += 1
                        result["rows_written"] += inserted_rows
                    else:
                        result["empty_count"] += 1
            if sleep_seconds and index + 1 < len(codes):
                time.sleep(sleep_seconds)

        if retry_queue:
            failed_symbols, retry_failed_errors = _run_retry_queue(
                retry_queue,
                target_date=decision.trade_date,
                freq=freq,
                adjust_type=adjust_type,
                retry_limit=retry_limit,
                cooldown_seconds=cooldown_seconds,
                timeout_seconds=timeout_seconds,
                result=result,
            )
            result["failed_symbols"] = write_failed_symbols + failed_symbols
            result["failed_count"] = len(result["failed_symbols"])
            unresolved_errors = {**write_failed_errors, **retry_failed_errors}
            if result["failed_symbols"]:
                result["last_error"] = unresolved_errors.get(result["failed_symbols"][-1])
            else:
                result["last_error"] = None
        elif write_failed_symbols:
            result["failed_symbols"] = write_failed_symbols
            result["failed_count"] = len(write_failed_symbols)
            result["last_error"] = write_failed_errors.get(write_failed_symbols[-1])

        if result["failed_count"] > 0:
            result["status"] = "partial"
        else:
            result["last_error"] = None
        return result
    except Exception as exc:
        result["status"] = "failed"
        result["last_error"] = str(exc)
        raise
    finally:
        try:
            bs.logout()
        except Exception:
            pass
        _release_daily_lock(lock_handle)
        _write_daily_artifacts(result, output_dir)
