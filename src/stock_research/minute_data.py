import datetime as dt
import hashlib
import json
import os
import socket
import time
from contextlib import contextmanager
from typing import Any

import baostock as bs

from stock_research.assets import asset_id_from_baostock_code
from stock_research.config import SETTINGS
from stock_research.db import connect, execute_many, fetch_all
from stock_research.eastmoney_http import curl_eastmoney_json


MINUTE_FIELDS = ["date", "time", "code", "open", "high", "low", "close", "volume", "amount"]
SOURCE_ENDPOINT = "query_history_k_data_plus"
FREQ_TO_BAOSTOCK = {
    "1min": "1",
    "5min": "5",
    "15min": "15",
    "30min": "30",
    "60min": "60",
}
ADJUST_TO_BAOSTOCK = {
    "raw": "3",
    "qfq": "2",
    "hfq": "1",
}
FREQ_TO_EASTMONEY_KLT = {
    "1min": "1",
    "5min": "5",
    "15min": "15",
    "30min": "30",
    "60min": "60",
}
ADJUST_TO_EASTMONEY_FQT = {
    "raw": "0",
    "qfq": "1",
    "hfq": "2",
}
EASTMONEY_KLINE_URLS = [
    "https://33.push2his.eastmoney.com/api/qt/stock/kline/get",
    "https://63.push2his.eastmoney.com/api/qt/stock/kline/get",
    "https://82.push2his.eastmoney.com/api/qt/stock/kline/get",
    "https://push2his.eastmoney.com/api/qt/stock/kline/get",
]
EASTMONEY_KLINE_FIELDS1 = "f1,f2,f3,f4,f5,f6"
EASTMONEY_KLINE_FIELDS2 = "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"
BAOSTOCK_MAX_ATTEMPTS = 3
BAOSTOCK_RETRYABLE_ERROR_CODES = {"10001001", "10002007"}
BAOSTOCK_RETRY_SLEEP_SECONDS = 1.0
BAOSTOCK_LOGIN_MAX_ATTEMPTS = 5
BAOSTOCK_LOGIN_RETRY_ERROR_CODES = {"10002007"}


def _load_socks_module():
    import socks

    return socks


def _load_baostock_socket_module():
    import baostock.util.socketutil as socketutil

    return socketutil


def baostock_proxy_config() -> tuple[str, int] | None:
    host = (os.getenv("BAOSTOCK_PROXY_HOST") or "").strip()
    port = (os.getenv("BAOSTOCK_PROXY_PORT") or "").strip()
    if not host or not port:
        return None
    return host, int(port)


@contextmanager
def temporary_baostock_proxy():
    proxy = baostock_proxy_config()
    if proxy is None:
        yield
        return
    host, port = proxy
    socks = _load_socks_module()
    socketutil = _load_baostock_socket_module()
    original_socket = socketutil.socket.socket
    socks.setdefaultproxy(socks.SOCKS5, host, port, rdns=True)
    socketutil.socket.socket = socks.socksocket
    try:
        yield
    finally:
        socketutil.socket.socket = original_socket
        socks.setdefaultproxy()


@contextmanager
def temporary_socket_timeout(timeout_seconds: float | None):
    if timeout_seconds is None:
        yield
        return
    previous_timeout = socket.getdefaulttimeout()
    socket.setdefaulttimeout(timeout_seconds)
    try:
        yield
    finally:
        socket.setdefaulttimeout(previous_timeout)


def parse_float(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if text == "":
        return None
    return float(text)


def canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def payload_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def parse_baostock_trade_time(value: str) -> dt.datetime:
    return dt.datetime.strptime(value[:14], "%Y%m%d%H%M%S")


def baostock_frequency(freq: str) -> str:
    try:
        return FREQ_TO_BAOSTOCK[freq]
    except KeyError as exc:
        raise ValueError(f"Unsupported minute frequency: {freq}") from exc


def adjustflag_for_adjust_type(adjust_type: str) -> str:
    try:
        return ADJUST_TO_BAOSTOCK[adjust_type]
    except KeyError as exc:
        raise ValueError(f"Unsupported adjust_type: {adjust_type}") from exc


def eastmoney_kline_frequency(freq: str) -> str:
    try:
        return FREQ_TO_EASTMONEY_KLT[freq]
    except KeyError as exc:
        raise ValueError(f"Unsupported minute frequency: {freq}") from exc


def eastmoney_adjust_flag(adjust_type: str) -> str:
    try:
        return ADJUST_TO_EASTMONEY_FQT[adjust_type]
    except KeyError as exc:
        raise ValueError(f"Unsupported adjust_type: {adjust_type}") from exc


def ts_code_from_baostock_code(code: str) -> str:
    exchange, symbol = code.split(".", 1)
    return f"{symbol}.{exchange.upper()}"


def baostock_code_from_ts_code(ts_code: str) -> str:
    symbol, exchange = ts_code.split(".", 1)
    return f"{exchange.lower()}.{symbol}"


def eastmoney_secid_from_ts_code(ts_code: str) -> str:
    symbol, exchange = ts_code.split(".", 1)
    exchange_id = {
        "SH": "1",
        "SZ": "0",
        "BJ": "0",
    }.get(exchange.upper())
    if exchange_id is None:
        raise ValueError(f"Unsupported Eastmoney exchange: {exchange}")
    return f"{exchange_id}.{symbol}"


def request_params(
    code: str,
    start_date: dt.date,
    end_date: dt.date,
    freq: str,
    adjust_type: str,
) -> dict[str, Any]:
    return {
        "code": code,
        "fields": MINUTE_FIELDS,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "frequency": baostock_frequency(freq),
        "adjustflag": adjustflag_for_adjust_type(adjust_type),
    }


def minute_market_row(raw: dict[str, Any], freq: str, adjust_type: str) -> dict[str, Any]:
    trade_time = parse_baostock_trade_time(str(raw["time"]))
    return {
        "asset_id": asset_id_from_baostock_code(str(raw["code"])),
        "ts_code": ts_code_from_baostock_code(str(raw["code"])),
        "trade_time": trade_time,
        "trade_date": dt.date.fromisoformat(str(raw["date"])),
        "freq": freq,
        "adjust_type": adjust_type,
        "open": parse_float(raw.get("open")),
        "high": parse_float(raw.get("high")),
        "low": parse_float(raw.get("low")),
        "close": parse_float(raw.get("close")),
        "volume": parse_float(raw.get("volume")),
        "amount": parse_float(raw.get("amount")),
        "source": "baostock",
    }


def minute_staging_row(
    raw: dict[str, Any],
    freq: str,
    adjust_type: str,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {str(key): value for key, value in raw.items()}
    trade_time = parse_baostock_trade_time(str(raw["time"]))
    return {
        "source_endpoint": SOURCE_ENDPOINT,
        "request_params": params or {},
        "baostock_code": str(raw["code"]),
        "raw_date": str(raw["date"]),
        "raw_time": str(raw["time"]),
        "trade_time": trade_time,
        "trade_date": dt.date.fromisoformat(str(raw["date"])),
        "freq": freq,
        "adjust_type": adjust_type,
        "open": parse_float(raw.get("open")),
        "high": parse_float(raw.get("high")),
        "low": parse_float(raw.get("low")),
        "close": parse_float(raw.get("close")),
        "volume": parse_float(raw.get("volume")),
        "amount": parse_float(raw.get("amount")),
        "payload": payload,
        "payload_hash": payload_hash(payload),
    }


def query_baostock_minute_rows(
    code: str,
    start_date: dt.date,
    end_date: dt.date,
    freq: str,
    adjust_type: str,
    timeout_seconds: float | None = None,
) -> list[dict[str, str]]:
    def operation() -> list[dict[str, str]]:
        with temporary_baostock_proxy(), temporary_socket_timeout(timeout_seconds):
            rs = bs.query_history_k_data_plus(
                code,
                ",".join(MINUTE_FIELDS),
                start_date=start_date.isoformat(),
                end_date=end_date.isoformat(),
                frequency=baostock_frequency(freq),
                adjustflag=adjustflag_for_adjust_type(adjust_type),
            )
        if rs.error_code != "0":
            raise RuntimeError(
                f"baostock minute query failed for {code}: {rs.error_code} {rs.error_msg}"
            )

        rows: list[dict[str, str]] = []
        while rs.next():
            rows.append(dict(zip(rs.fields, rs.get_row_data(), strict=True)))
        return rows

    return run_with_baostock_retry(operation, timeout_seconds=timeout_seconds)


def query_eastmoney_kline_minute_rows(
    ts_code: str,
    start_date: dt.date,
    end_date: dt.date,
    *,
    freq: str,
    adjust_type: str,
    retries: int = 3,
    retry_sleep_seconds: float = 1.0,
) -> list[dict[str, str]]:
    params = {
        "secid": eastmoney_secid_from_ts_code(ts_code),
        "ut": "7eea3edcaed734bea9cbfc24409ed989",
        "fields1": EASTMONEY_KLINE_FIELDS1,
        "fields2": EASTMONEY_KLINE_FIELDS2,
        "klt": eastmoney_kline_frequency(freq),
        "fqt": eastmoney_adjust_flag(adjust_type),
        "beg": start_date.strftime("%Y%m%d"),
        "end": end_date.strftime("%Y%m%d"),
    }
    payload = curl_eastmoney_json(
        EASTMONEY_KLINE_URLS,
        params,
        retries=retries,
        retry_sleep_seconds=retry_sleep_seconds,
    )
    data = payload.get("data") or {}
    return [
        _eastmoney_kline_row_to_minute_row(kline, ts_code=ts_code)
        for kline in data.get("klines") or []
    ]


def _eastmoney_kline_row_to_minute_row(kline: str, *, ts_code: str) -> dict[str, str]:
    parts = kline.split(",")
    if len(parts) < 7:
        raise ValueError(f"Eastmoney kline row has too few fields: {kline}")
    trade_time = dt.datetime.strptime(parts[0], "%Y-%m-%d %H:%M")
    return {
        "date": trade_time.date().isoformat(),
        "time": trade_time.strftime("%Y%m%d%H%M%S") + "000",
        "code": baostock_code_from_ts_code(ts_code),
        "open": parts[1],
        "close": parts[2],
        "high": parts[3],
        "low": parts[4],
        "volume": parts[5],
        "amount": parts[6],
    }


def is_retryable_baostock_error(message: str) -> bool:
    return any(error_code in message for error_code in BAOSTOCK_RETRYABLE_ERROR_CODES)


def relogin_or_raise(timeout_seconds: float | None = None) -> None:
    try:
        bs.logout()
    except Exception:
        pass
    login_or_raise(timeout_seconds=timeout_seconds)


def run_with_baostock_retry(operation, timeout_seconds: float | None = None):
    last_error: RuntimeError | None = None
    for attempt in range(1, BAOSTOCK_MAX_ATTEMPTS + 1):
        try:
            return operation()
        except RuntimeError as exc:
            last_error = exc
            if attempt >= BAOSTOCK_MAX_ATTEMPTS or not is_retryable_baostock_error(str(exc)):
                raise
            relogin_or_raise(timeout_seconds=timeout_seconds)
            time.sleep(BAOSTOCK_RETRY_SLEEP_SECONDS)
    assert last_error is not None
    raise last_error


def load_active_baostock_codes(
    research_service: str = SETTINGS.research_service,
    limit_assets: int | None = None,
) -> list[str]:
    sql = """
    SELECT baostock_code
    FROM core.asset_master
    WHERE is_active = true
      AND baostock_code IS NOT NULL
      AND baostock_code <> ''
    ORDER BY baostock_code
    """
    if limit_assets is not None:
        sql += "\nLIMIT %s"
        params: list[Any] = [limit_assets]
    else:
        params = []
    with connect(research_service) as conn:
        return [row["baostock_code"] for row in fetch_all(conn, sql, params)]


def upsert_stock_minute_bars(
    rows: list[dict[str, Any]],
    freq: str,
    adjust_type: str,
    research_service: str = SETTINGS.research_service,
    params: dict[str, Any] | None = None,
) -> int:
    if not rows:
        return 0

    staging_rows = [
        minute_staging_row(row, freq=freq, adjust_type=adjust_type, params=params)
        for row in rows
    ]
    market_rows = [minute_market_row(row, freq=freq, adjust_type=adjust_type) for row in rows]

    staging_sql = """
    INSERT INTO staging.baostock_stock_minute_bar (
        source_endpoint, request_params, baostock_code, raw_date, raw_time,
        trade_time, trade_date, freq, adjust_type, open, high, low, close,
        volume, amount, payload, payload_hash
    )
    VALUES (
        %(source_endpoint)s, %(request_params)s::jsonb, %(baostock_code)s, %(raw_date)s,
        %(raw_time)s, %(trade_time)s, %(trade_date)s, %(freq)s, %(adjust_type)s,
        %(open)s, %(high)s, %(low)s, %(close)s, %(volume)s, %(amount)s,
        %(payload)s::jsonb, %(payload_hash)s
    )
    ON CONFLICT (source_endpoint, baostock_code, trade_time, freq, adjust_type)
    DO UPDATE SET
        request_params = EXCLUDED.request_params,
        raw_date = EXCLUDED.raw_date,
        raw_time = EXCLUDED.raw_time,
        trade_date = EXCLUDED.trade_date,
        open = EXCLUDED.open,
        high = EXCLUDED.high,
        low = EXCLUDED.low,
        close = EXCLUDED.close,
        volume = EXCLUDED.volume,
        amount = EXCLUDED.amount,
        payload = EXCLUDED.payload,
        payload_hash = EXCLUDED.payload_hash,
        fetched_at = now()
    """
    market_sql = """
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
    staging_params = [
        {
            **row,
            "request_params": canonical_json(row["request_params"]),
            "payload": canonical_json(row["payload"]),
        }
        for row in staging_rows
    ]
    with connect(research_service) as conn:
        execute_many(conn, staging_sql, staging_params)
        execute_many(conn, market_sql, market_rows)
    return len(market_rows)


def login_or_raise(timeout_seconds: float | None = None) -> None:
    last_error = ""
    for attempt in range(BAOSTOCK_LOGIN_MAX_ATTEMPTS):
        with temporary_baostock_proxy(), temporary_socket_timeout(timeout_seconds):
            login = bs.login()
        if login.error_code == "0":
            return
        last_error = f"{login.error_code} {login.error_msg}"
        if (
            login.error_code not in BAOSTOCK_LOGIN_RETRY_ERROR_CODES
            or attempt + 1 >= BAOSTOCK_LOGIN_MAX_ATTEMPTS
        ):
            break
        time.sleep(BAOSTOCK_RETRY_SLEEP_SECONDS)
    raise RuntimeError(f"baostock login failed: {last_error}")


def sync_baostock_stock_minute_bars(
    start_date: str,
    end_date: str,
    freq: str = "5min",
    adjust_types: list[str] | None = None,
    limit_assets: int | None = None,
    sleep_seconds: float = 0.0,
) -> dict[str, int]:
    parsed_start = dt.date.fromisoformat(start_date)
    parsed_end = dt.date.fromisoformat(end_date)
    selected_adjust_types = adjust_types or ["raw", "qfq"]
    codes = load_active_baostock_codes(limit_assets=limit_assets)
    counts = {adjust_type: 0 for adjust_type in selected_adjust_types}

    login_or_raise()
    try:
        for adjust_type in selected_adjust_types:
            for code in codes:
                params = request_params(code, parsed_start, parsed_end, freq, adjust_type)
                rows = query_baostock_minute_rows(
                    code,
                    parsed_start,
                    parsed_end,
                    freq=freq,
                    adjust_type=adjust_type,
                )
                counts[adjust_type] += upsert_stock_minute_bars(
                    rows,
                    freq=freq,
                    adjust_type=adjust_type,
                    params=params,
                )
                if sleep_seconds:
                    time.sleep(sleep_seconds)
    finally:
        try:
            bs.logout()
        except Exception:
            pass
    return counts
