import datetime as dt
import hashlib
import json
import time
from typing import Any

import baostock as bs

from stock_research.assets import asset_id_from_baostock_code
from stock_research.config import SETTINGS
from stock_research.db import connect, execute_many, fetch_all


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
BAOSTOCK_MAX_ATTEMPTS = 3
BAOSTOCK_RETRYABLE_ERROR_CODES = {"10001001", "10002007"}
BAOSTOCK_RETRY_SLEEP_SECONDS = 1.0
BAOSTOCK_LOGIN_MAX_ATTEMPTS = 5
BAOSTOCK_LOGIN_RETRY_ERROR_CODES = {"10002007"}


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


def ts_code_from_baostock_code(code: str) -> str:
    exchange, symbol = code.split(".", 1)
    return f"{symbol}.{exchange.upper()}"


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
) -> list[dict[str, str]]:
    return run_with_baostock_retry(
        lambda: query_baostock_minute_rows_once(
            code,
            start_date,
            end_date,
            freq=freq,
            adjust_type=adjust_type,
        )
    )


def query_baostock_minute_rows_once(
    code: str,
    start_date: dt.date,
    end_date: dt.date,
    freq: str,
    adjust_type: str,
    timeout_seconds: float | None = None,
) -> list[dict[str, str]]:
    del timeout_seconds
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


def is_retryable_baostock_error(message: str) -> bool:
    return any(error_code in message for error_code in BAOSTOCK_RETRYABLE_ERROR_CODES)


def relogin_or_raise() -> None:
    try:
        bs.logout()
    except Exception:
        pass
    login_or_raise()


def run_with_baostock_retry(operation):
    last_error: RuntimeError | None = None
    for attempt in range(1, BAOSTOCK_MAX_ATTEMPTS + 1):
        try:
            return operation()
        except RuntimeError as exc:
            last_error = exc
            if attempt >= BAOSTOCK_MAX_ATTEMPTS or not is_retryable_baostock_error(str(exc)):
                raise
            relogin_or_raise()
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


def login_or_raise() -> None:
    last_error = ""
    for attempt in range(BAOSTOCK_LOGIN_MAX_ATTEMPTS):
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
