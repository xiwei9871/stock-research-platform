from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import datetime as dt
from contextlib import contextmanager
import signal
import threading
import time
from typing import Any

import akshare as ak
import pandas as pd

from stock_research.config import SETTINGS
from stock_research.db import connect, execute_many, fetch_all
from stock_research.minute_data import parse_float, ts_code_from_baostock_code


AKSHARE_SINA_MINUTE_SOURCE = "akshare"
FREQ_TO_AKSHARE_PERIOD = {
    "1min": "1",
    "5min": "5",
    "15min": "15",
    "30min": "30",
    "60min": "60",
}
ADJUST_TO_AKSHARE = {
    "raw": "",
    "qfq": "qfq",
    "hfq": "hfq",
}


def akshare_sina_symbol_from_baostock_code(baostock_code: str) -> str:
    exchange, symbol = baostock_code.split(".", 1)
    return f"{exchange.lower()}{symbol}"


def akshare_period(freq: str) -> str:
    try:
        return FREQ_TO_AKSHARE_PERIOD[freq]
    except KeyError as exc:
        raise ValueError(f"Unsupported minute frequency: {freq}") from exc


def akshare_adjust(adjust_type: str) -> str:
    try:
        return ADJUST_TO_AKSHARE[adjust_type]
    except KeyError as exc:
        raise ValueError(f"Unsupported adjust_type: {adjust_type}") from exc


def normalize_akshare_sina_minute_frame(
    frame: pd.DataFrame,
    *,
    asset_id: str,
    baostock_code: str,
    trade_date: dt.date,
    freq: str,
    adjust_type: str,
) -> list[dict[str, Any]]:
    if frame.empty:
        return []

    normalized = frame.copy()
    normalized["trade_time"] = pd.to_datetime(normalized["day"])
    normalized = normalized[normalized["trade_time"].dt.date == trade_date]
    normalized = normalized.sort_values("trade_time")

    ts_code = ts_code_from_baostock_code(baostock_code)
    rows: list[dict[str, Any]] = []
    for row in normalized.to_dict("records"):
        trade_time = row["trade_time"]
        if hasattr(trade_time, "to_pydatetime"):
            trade_time = trade_time.to_pydatetime()
        rows.append(
            {
                "asset_id": asset_id,
                "ts_code": ts_code,
                "trade_time": trade_time,
                "trade_date": trade_date,
                "freq": freq,
                "adjust_type": adjust_type,
                "open": parse_float(row.get("open")),
                "high": parse_float(row.get("high")),
                "low": parse_float(row.get("low")),
                "close": parse_float(row.get("close")),
                "volume": parse_float(row.get("volume")),
                "amount": parse_float(row.get("amount")),
                "source": AKSHARE_SINA_MINUTE_SOURCE,
            }
        )
    return rows


def upsert_akshare_sina_minute_rows(
    rows: list[dict[str, Any]],
    research_service: str = SETTINGS.research_service,
) -> int:
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
    ON CONFLICT (trade_date, asset_id, trade_time, freq, adjust_type, source)
    DO UPDATE SET
        ts_code = EXCLUDED.ts_code,
        trade_date = EXCLUDED.trade_date,
        open = EXCLUDED.open,
        high = EXCLUDED.high,
        low = EXCLUDED.low,
        close = EXCLUDED.close,
        volume = EXCLUDED.volume,
        amount = EXCLUDED.amount,
        updated_at = now()
    """
    with connect(research_service) as conn:
        execute_many(conn, sql, rows)
    return len(rows)


def query_akshare_sina_minute_rows(
    *,
    asset_id: str,
    baostock_code: str,
    trade_date: dt.date,
    freq: str,
    adjust_type: str,
    timeout_seconds: int = 15,
) -> list[dict[str, Any]]:
    with timeout_after(timeout_seconds):
        frame = ak.stock_zh_a_minute(
            symbol=akshare_sina_symbol_from_baostock_code(baostock_code),
            period=akshare_period(freq),
            adjust=akshare_adjust(adjust_type),
        )
    return normalize_akshare_sina_minute_frame(
        frame,
        asset_id=asset_id,
        baostock_code=baostock_code,
        trade_date=trade_date,
        freq=freq,
        adjust_type=adjust_type,
    )


def load_akshare_sina_gap_assets(
    *,
    trade_date: dt.date,
    freq: str,
    adjust_type: str,
    expected_rows: int = 48,
    max_assets: int | None = None,
    research_service: str = SETTINGS.research_service,
) -> list[dict[str, Any]]:
    params: list[Any] = [trade_date, freq, adjust_type, expected_rows]
    limit_sql = ""
    if max_assets is not None:
        limit_sql = "\nLIMIT %s"
        params.append(max_assets)
    sql = f"""
    WITH coverage AS (
        SELECT asset_id, COUNT(DISTINCT trade_time) AS row_count
        FROM market.stock_minute_bar
        WHERE trade_date = %s
          AND freq = %s
          AND adjust_type = %s
        GROUP BY asset_id
    )
    SELECT
        a.asset_id,
        a.baostock_code,
        COALESCE(c.row_count, 0)::int AS existing_rows
    FROM core.asset_master a
    LEFT JOIN coverage c ON c.asset_id = a.asset_id
    WHERE a.is_active = true
      AND a.baostock_code IS NOT NULL
      AND a.baostock_code <> ''
      AND COALESCE(c.row_count, 0) < %s
    ORDER BY a.baostock_code
    {limit_sql}
    """
    with connect(research_service) as conn:
        return fetch_all(conn, sql, params)


def run_akshare_sina_minute_backfill(
    *,
    trade_date: str,
    freq: str = "5min",
    adjust_types: list[str] | None = None,
    expected_rows: int = 48,
    max_assets: int | None = None,
    sleep_seconds: float = 0.2,
    timeout_seconds: int = 15,
    workers: int = 1,
) -> dict[str, int]:
    if workers <= 0:
        raise ValueError("workers must be positive")
    parsed_trade_date = dt.date.fromisoformat(trade_date)
    selected_adjust_types = adjust_types or ["raw", "qfq"]
    result = {
        "assets_attempted": 0,
        "adjust_attempted": 0,
        "success": 0,
        "failed": 0,
        "rows": 0,
        "skipped_empty": 0,
    }
    attempted_assets: set[str] = set()

    for adjust_type in selected_adjust_types:
        assets = load_akshare_sina_gap_assets(
            trade_date=parsed_trade_date,
            freq=freq,
            adjust_type=adjust_type,
            expected_rows=expected_rows,
            max_assets=max_assets,
        )
        if workers > 1:
            result["adjust_attempted"] += len(assets)
            for asset in assets:
                attempted_assets.add(str(asset["asset_id"]))
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = [
                    executor.submit(
                        query_akshare_sina_minute_rows,
                        asset_id=str(asset["asset_id"]),
                        baostock_code=str(asset["baostock_code"]),
                        trade_date=parsed_trade_date,
                        freq=freq,
                        adjust_type=adjust_type,
                        timeout_seconds=timeout_seconds,
                    )
                    for asset in assets
                ]
                for future in as_completed(futures):
                    try:
                        rows = future.result()
                        if not rows:
                            result["skipped_empty"] += 1
                            continue
                        result["rows"] += upsert_akshare_sina_minute_rows(rows)
                        result["success"] += 1
                    except Exception:
                        result["failed"] += 1
            continue
        for asset in assets:
            asset_id = str(asset["asset_id"])
            attempted_assets.add(asset_id)
            result["adjust_attempted"] += 1
            try:
                rows = query_akshare_sina_minute_rows(
                    asset_id=asset_id,
                    baostock_code=str(asset["baostock_code"]),
                    trade_date=parsed_trade_date,
                    freq=freq,
                    adjust_type=adjust_type,
                    timeout_seconds=timeout_seconds,
                )
                if not rows:
                    result["skipped_empty"] += 1
                    continue
                result["rows"] += upsert_akshare_sina_minute_rows(rows)
                result["success"] += 1
            except Exception:
                result["failed"] += 1
            if sleep_seconds:
                time.sleep(sleep_seconds)

    result["assets_attempted"] = len(attempted_assets)
    return result


@contextmanager
def timeout_after(seconds: int):
    if seconds <= 0 or threading.current_thread() is not threading.main_thread():
        yield
        return

    def raise_timeout(signum, frame):
        raise TimeoutError(f"akshare minute request timed out after {seconds}s")

    old_handler = signal.signal(signal.SIGALRM, raise_timeout)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old_handler)
