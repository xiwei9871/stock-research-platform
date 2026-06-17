import datetime as dt
import json
import os
import shlex
import time
from pathlib import Path
from typing import Any

import pandas as pd
import tushare as ts

from stock_research.config import SETTINGS
from stock_research.db import connect, execute_many, fetch_all
from stock_research.minute_data import canonical_json, parse_float, payload_hash


AUCTION_PHASE_ENDPOINTS = {
    "open_call": "stk_auction_o",
    "close_call": "stk_auction_c",
}

PROJECT_ROOT = Path(__file__).resolve().parents[2]
LOCAL_SECRETS_PATH = PROJECT_ROOT / "config" / "local_secrets.json"

OPEN_AUCTION_SPOT_SNAPSHOT_TARGETS = [
    ("09:15", 15),
    ("09:17", 17),
    ("09:19", 19),
    ("09:21", 21),
    ("09:23", 23),
    ("09:25", 25),
]


def parse_tushare_trade_date(value: Any) -> dt.date:
    return dt.datetime.strptime(str(value), "%Y%m%d").date()


def asset_id_from_ts_code(ts_code: str) -> str:
    symbol, exchange = ts_code.split(".", 1)
    return f"CN:{exchange.upper()}:{symbol}"


def symbol_from_ts_code(ts_code: str) -> str:
    return str(ts_code).split(".", 1)[0]


def auction_endpoint_for_phase(auction_phase: str) -> str:
    try:
        return AUCTION_PHASE_ENDPOINTS[auction_phase]
    except KeyError as exc:
        raise ValueError(f"Unsupported auction_phase: {auction_phase}") from exc


def auction_market_row(raw: dict[str, Any], auction_phase: str) -> dict[str, Any]:
    return {
        "asset_id": asset_id_from_ts_code(str(raw["ts_code"])),
        "ts_code": str(raw["ts_code"]),
        "trade_date": parse_tushare_trade_date(raw["trade_date"]),
        "auction_phase": auction_phase,
        "open": parse_float(raw.get("open")),
        "high": parse_float(raw.get("high")),
        "low": parse_float(raw.get("low")),
        "close": parse_float(raw.get("close")),
        "volume": parse_float(raw.get("vol")),
        "amount": parse_float(raw.get("amount")),
        "vwap": parse_float(raw.get("vwap")),
        "source": "tushare",
    }


def auction_staging_row(
    raw: dict[str, Any],
    auction_phase: str,
    source_endpoint: str,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {str(key): value for key, value in raw.items()}
    return {
        "source_endpoint": source_endpoint,
        "request_params": params or {},
        "ts_code": str(raw["ts_code"]),
        "raw_trade_date": str(raw["trade_date"]),
        "trade_date": parse_tushare_trade_date(raw["trade_date"]),
        "auction_phase": auction_phase,
        "open": parse_float(raw.get("open")),
        "high": parse_float(raw.get("high")),
        "low": parse_float(raw.get("low")),
        "close": parse_float(raw.get("close")),
        "volume": parse_float(raw.get("vol")),
        "amount": parse_float(raw.get("amount")),
        "vwap": parse_float(raw.get("vwap")),
        "payload": payload,
        "payload_hash": payload_hash(payload),
    }


def query_tushare_auction_rows_for_trade_date(
    client: Any,
    trade_date: dt.date,
    auction_phase: str,
) -> list[dict[str, Any]]:
    endpoint = auction_endpoint_for_phase(auction_phase)
    frame = getattr(client, endpoint)(
        trade_date=trade_date.strftime("%Y%m%d"),
    )
    return list(frame.to_dict("records"))


def upsert_stock_auction_bars(
    rows: list[dict[str, Any]],
    auction_phase: str,
    source_endpoint: str,
    research_service: str = SETTINGS.research_service,
    params: dict[str, Any] | None = None,
) -> int:
    if not rows:
        return 0

    staging_rows = [
        auction_staging_row(
            row,
            auction_phase=auction_phase,
            source_endpoint=source_endpoint,
            params=params,
        )
        for row in rows
    ]
    market_rows = [auction_market_row(row, auction_phase=auction_phase) for row in rows]

    staging_sql = """
    INSERT INTO staging.tushare_stock_auction_bar (
        source_endpoint, request_params, ts_code, raw_trade_date, trade_date,
        auction_phase, open, high, low, close, volume, amount, vwap, payload, payload_hash
    )
    VALUES (
        %(source_endpoint)s, %(request_params)s::jsonb, %(ts_code)s, %(raw_trade_date)s,
        %(trade_date)s, %(auction_phase)s, %(open)s, %(high)s, %(low)s, %(close)s,
        %(volume)s, %(amount)s, %(vwap)s, %(payload)s::jsonb, %(payload_hash)s
    )
    ON CONFLICT (source_endpoint, ts_code, trade_date, auction_phase)
    DO UPDATE SET
        request_params = EXCLUDED.request_params,
        raw_trade_date = EXCLUDED.raw_trade_date,
        open = EXCLUDED.open,
        high = EXCLUDED.high,
        low = EXCLUDED.low,
        close = EXCLUDED.close,
        volume = EXCLUDED.volume,
        amount = EXCLUDED.amount,
        vwap = EXCLUDED.vwap,
        payload = EXCLUDED.payload,
        payload_hash = EXCLUDED.payload_hash,
        fetched_at = now()
    """
    market_sql = """
    INSERT INTO market.stock_auction_bar (
        asset_id, ts_code, trade_date, auction_phase, open, high, low, close,
        volume, amount, vwap, source
    )
    VALUES (
        %(asset_id)s, %(ts_code)s, %(trade_date)s, %(auction_phase)s, %(open)s,
        %(high)s, %(low)s, %(close)s, %(volume)s, %(amount)s, %(vwap)s, %(source)s
    )
    ON CONFLICT (trade_date, asset_id, auction_phase, source)
    DO UPDATE SET
        ts_code = EXCLUDED.ts_code,
        open = EXCLUDED.open,
        high = EXCLUDED.high,
        low = EXCLUDED.low,
        close = EXCLUDED.close,
        volume = EXCLUDED.volume,
        amount = EXCLUDED.amount,
        vwap = EXCLUDED.vwap,
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


def parse_eastmoney_minute_time(value: Any) -> dt.datetime:
    timestamp = pd.to_datetime(value, errors="raise")
    return timestamp.to_pydatetime().replace(tzinfo=None)


def _first_present(raw: dict[str, Any], keys: list[str]) -> Any:
    for key in keys:
        if key in raw:
            return raw[key]
    return None


def ts_code_from_spot_symbol(symbol: Any) -> str:
    if symbol is None:
        raise ValueError(f"Unsupported spot symbol: {symbol}")
    code = str(symbol).strip()
    if len(code) != 6 or not code.isdigit():
        raise ValueError(f"Unsupported spot symbol: {symbol}")
    if code.startswith("6"):
        return f"{code}.SH"
    if code.startswith(("0", "3")):
        return f"{code}.SZ"
    if code.startswith(("4", "8", "9")):
        return f"{code}.BJ"
    raise ValueError(f"Unsupported spot symbol: {symbol}")


def _clean_spot_payload_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        if text in {"", "-", "--", "—"} or text.lower() in {"n/a", "nan", "none", "null"}:
            return None
    if isinstance(value, (dict, list, tuple, set)):
        return value
    try:
        is_missing = pd.isna(value)
    except (TypeError, ValueError):
        return value
    try:
        if bool(is_missing):
            return None
    except (TypeError, ValueError):
        return value
    return value


def _parse_spot_float(value: Any) -> float | None:
    return parse_float(_clean_spot_payload_value(value))


def parse_target_time(value: str | dt.time) -> dt.time:
    if isinstance(value, dt.time):
        return value
    return dt.datetime.strptime(str(value), "%H:%M").time()


def is_open_trading_date(
    trade_date: str | dt.date,
    research_service: str = SETTINGS.research_service,
) -> bool:
    return open_trading_date_status(trade_date, research_service=research_service) == "open"


def open_trading_date_status(
    trade_date: str | dt.date,
    research_service: str = SETTINGS.research_service,
) -> str:
    target_date = dt.date.fromisoformat(str(trade_date)) if not isinstance(trade_date, dt.date) else trade_date
    sql = """
    SELECT
        bool_or(is_open = true) AS calendar_open,
        bool_or(is_open = false) AS calendar_closed,
        EXISTS (
            SELECT 1
            FROM market_daily_bar
            WHERE trade_date = %s
              AND adjust_type = 'qfq'
        ) AS has_daily_bar
    FROM market.trading_calendar
    WHERE trade_date = %s
    """
    with connect(research_service) as conn:
        rows = fetch_all(conn, sql, [target_date.isoformat(), target_date.isoformat()])
    row = rows[0] if rows else {}
    if bool(row.get("calendar_open")) or bool(row.get("has_daily_bar")):
        return "open"
    if bool(row.get("calendar_closed")):
        return "closed"
    return "unknown"


def open_auction_spot_snapshot_market_row(
    raw: dict[str, Any],
    *,
    trade_date: dt.date,
    snapshot_time: dt.datetime,
    target_time: str | dt.time,
    source: str = "eastmoney_spot_snapshot",
) -> dict[str, Any]:
    ts_code = ts_code_from_spot_symbol(_first_present(raw, ["代码", "symbol", "raw_symbol"]))
    return {
        "asset_id": asset_id_from_ts_code(ts_code),
        "ts_code": ts_code,
        "trade_date": trade_date,
        "snapshot_time": snapshot_time.replace(tzinfo=None),
        "target_time": parse_target_time(target_time),
        "auction_phase": "open_call",
        "latest": _parse_spot_float(_first_present(raw, ["最新价", "latest"])),
        "open": _parse_spot_float(_first_present(raw, ["今开", "open"])),
        "prev_close": _parse_spot_float(_first_present(raw, ["昨收", "prev_close"])),
        "high": _parse_spot_float(_first_present(raw, ["最高", "high"])),
        "low": _parse_spot_float(_first_present(raw, ["最低", "low"])),
        "volume": _parse_spot_float(_first_present(raw, ["成交量", "volume", "vol"])),
        "amount": _parse_spot_float(_first_present(raw, ["成交额", "amount"])),
        "volume_ratio": _parse_spot_float(_first_present(raw, ["量比", "volume_ratio"])),
        "turnover_rate": _parse_spot_float(_first_present(raw, ["换手率", "turnover_rate"])),
        "source": source,
    }


def open_auction_spot_snapshot_staging_row(
    raw: dict[str, Any],
    *,
    trade_date: dt.date,
    snapshot_time: dt.datetime,
    target_time: str | dt.time,
    source_endpoint: str,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {str(key): _clean_spot_payload_value(value) for key, value in raw.items()}
    market_row = open_auction_spot_snapshot_market_row(
        payload,
        trade_date=trade_date,
        snapshot_time=snapshot_time,
        target_time=target_time,
    )
    return {
        "source_endpoint": source_endpoint,
        "request_params": params or {},
        "raw_symbol": str(_first_present(payload, ["代码", "symbol", "raw_symbol"])),
        "ts_code": market_row["ts_code"],
        "trade_date": trade_date,
        "snapshot_time": market_row["snapshot_time"],
        "target_time": market_row["target_time"],
        "latest": market_row["latest"],
        "open": market_row["open"],
        "prev_close": market_row["prev_close"],
        "high": market_row["high"],
        "low": market_row["low"],
        "volume": market_row["volume"],
        "amount": market_row["amount"],
        "volume_ratio": market_row["volume_ratio"],
        "turnover_rate": market_row["turnover_rate"],
        "payload": payload,
        "payload_hash": payload_hash(payload),
    }


def query_eastmoney_spot_snapshot_rows(
    retries: int = 3,
    retry_sleep_seconds: float = 2.0,
) -> list[dict[str, Any]]:
    import akshare as ak

    last_error: Exception | None = None
    attempts = max(1, retries)
    for attempt in range(1, attempts + 1):
        try:
            frame = ak.stock_zh_a_spot_em()
            return list(frame.to_dict("records"))
        except Exception as exc:
            last_error = exc
            if attempt < attempts and retry_sleep_seconds:
                time.sleep(retry_sleep_seconds)
    if last_error is None:
        raise RuntimeError(f"AKShare spot snapshot failed after {attempts} attempts")
    raise RuntimeError(f"AKShare spot snapshot failed after {attempts} attempts: {last_error}") from last_error


def upsert_stock_open_auction_spot_snapshots(
    rows: list[dict[str, Any]],
    *,
    trade_date: dt.date,
    snapshot_time: dt.datetime,
    target_time: str | dt.time,
    source_endpoint: str = "stock_zh_a_spot_em",
    research_service: str = SETTINGS.research_service,
    params: dict[str, Any] | None = None,
) -> int:
    if not rows:
        return 0

    staging_rows = [
        open_auction_spot_snapshot_staging_row(
            row,
            trade_date=trade_date,
            snapshot_time=snapshot_time,
            target_time=target_time,
            source_endpoint=source_endpoint,
            params=params,
        )
        for row in rows
    ]
    market_rows = [
        open_auction_spot_snapshot_market_row(
            row["payload"],
            trade_date=trade_date,
            snapshot_time=snapshot_time,
            target_time=target_time,
        )
        for row in staging_rows
    ]

    staging_sql = """
    INSERT INTO staging.eastmoney_stock_spot_snapshot (
        source_endpoint, request_params, raw_symbol, ts_code, trade_date, snapshot_time,
        target_time, latest, open, prev_close, high, low, volume, amount,
        volume_ratio, turnover_rate, payload, payload_hash
    )
    VALUES (
        %(source_endpoint)s, %(request_params)s::jsonb, %(raw_symbol)s, %(ts_code)s,
        %(trade_date)s, %(snapshot_time)s, %(target_time)s, %(latest)s, %(open)s,
        %(prev_close)s, %(high)s, %(low)s, %(volume)s, %(amount)s,
        %(volume_ratio)s, %(turnover_rate)s, %(payload)s::jsonb, %(payload_hash)s
    )
    ON CONFLICT (source_endpoint, ts_code, trade_date, target_time)
    DO UPDATE SET
        request_params = EXCLUDED.request_params,
        snapshot_time = EXCLUDED.snapshot_time,
        latest = EXCLUDED.latest,
        open = EXCLUDED.open,
        prev_close = EXCLUDED.prev_close,
        high = EXCLUDED.high,
        low = EXCLUDED.low,
        volume = EXCLUDED.volume,
        amount = EXCLUDED.amount,
        volume_ratio = EXCLUDED.volume_ratio,
        turnover_rate = EXCLUDED.turnover_rate,
        payload = EXCLUDED.payload,
        payload_hash = EXCLUDED.payload_hash,
        fetched_at = now()
    """
    market_sql = """
    INSERT INTO market.stock_open_auction_snapshot (
        asset_id, ts_code, trade_date, snapshot_time, target_time, auction_phase,
        latest, open, prev_close, high, low, volume, amount, volume_ratio,
        turnover_rate, source
    )
    VALUES (
        %(asset_id)s, %(ts_code)s, %(trade_date)s, %(snapshot_time)s, %(target_time)s,
        %(auction_phase)s, %(latest)s, %(open)s, %(prev_close)s, %(high)s, %(low)s,
        %(volume)s, %(amount)s, %(volume_ratio)s, %(turnover_rate)s, %(source)s
    )
    ON CONFLICT (trade_date, asset_id, target_time, source)
    DO UPDATE SET
        ts_code = EXCLUDED.ts_code,
        snapshot_time = EXCLUDED.snapshot_time,
        latest = EXCLUDED.latest,
        open = EXCLUDED.open,
        prev_close = EXCLUDED.prev_close,
        high = EXCLUDED.high,
        low = EXCLUDED.low,
        volume = EXCLUDED.volume,
        amount = EXCLUDED.amount,
        volume_ratio = EXCLUDED.volume_ratio,
        turnover_rate = EXCLUDED.turnover_rate,
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


def collect_open_auction_spot_snapshot(
    *,
    trade_date: str | dt.date,
    target_time: str,
    snapshot_time: dt.datetime | None = None,
    skip_non_trading_day: bool = True,
) -> dict[str, Any]:
    target_date = dt.date.fromisoformat(str(trade_date)) if not isinstance(trade_date, dt.date) else trade_date
    captured_at = (snapshot_time or dt.datetime.now()).replace(tzinfo=None)
    rows: list[dict[str, Any]] = []
    valid_rows: list[dict[str, Any]] = []
    upserted = 0
    skipped = 0
    error = ""
    failed = False
    params = {
        "trade_date": target_date.isoformat(),
        "target_time": target_time,
        "snapshot_time": captured_at.isoformat(timespec="seconds"),
    }
    try:
        parsed_target_time = parse_target_time(target_time)
        trading_status = open_trading_date_status(target_date) if skip_non_trading_day else "open"
        if trading_status == "closed":
            detail_row = {
                "trade_date": target_date.isoformat(),
                "target_time": target_time,
                "snapshot_time": captured_at.isoformat(timespec="seconds"),
                "queried_rows": 0,
                "upserted_rows": 0,
                "skipped_rows": 0,
                "non_trading_day": True,
                "failed": False,
                "error": "",
            }
            return {
                "detail": pd.DataFrame([detail_row]),
                "summary": detail_row,
            }
        rows = query_eastmoney_spot_snapshot_rows()
        for row in rows:
            try:
                open_auction_spot_snapshot_staging_row(
                    row,
                    trade_date=target_date,
                    snapshot_time=captured_at,
                    target_time=parsed_target_time,
                    source_endpoint="stock_zh_a_spot_em",
                    params=params,
                )
                valid_rows.append(row)
            except (ValueError, TypeError):
                skipped += 1
        if valid_rows:
            upserted = upsert_stock_open_auction_spot_snapshots(
                valid_rows,
                trade_date=target_date,
                snapshot_time=captured_at,
                target_time=target_time,
                params=params,
            )
        if len(rows) == 0:
            failed = True
            error = "AKShare spot snapshot returned no rows for open trading date"
        elif not valid_rows:
            failed = True
            error = "AKShare spot snapshot returned rows but none were valid"
    except Exception as exc:  # pragma: no cover - integration safety path.
        failed = True
        error = str(exc)

    detail_row = {
        "trade_date": target_date.isoformat(),
        "target_time": target_time,
        "snapshot_time": captured_at.isoformat(timespec="seconds"),
        "queried_rows": len(rows),
        "upserted_rows": upserted,
        "skipped_rows": skipped,
        "non_trading_day": False,
        "failed": failed,
        "error": error,
    }
    detail = pd.DataFrame([detail_row])
    return {
        "detail": detail,
        "summary": detail_row,
    }


def write_open_auction_spot_snapshot_report(
    *,
    result: dict[str, Any],
    output_dir: str | Path,
    trade_date: str | dt.date,
    target_time: str,
) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    date_text = str(trade_date)
    safe_target = str(target_time).replace(":", "")
    detail_path = output / f"open_auction_spot_snapshot_{date_text}_{safe_target}.csv"
    latest_path = output / "open_auction_spot_snapshot_latest.csv"
    report_path = output / f"open_auction_spot_snapshot_{date_text}_{safe_target}.md"
    result["detail"].to_csv(detail_path, index=False)
    result["detail"].to_csv(latest_path, index=False)
    summary = result["summary"]
    lines = [
        f"# Open Auction Spot Snapshot {date_text} {target_time}",
        "",
        f"- trade_date: {summary['trade_date']}",
        f"- target_time: {summary['target_time']}",
        f"- snapshot_time: {summary['snapshot_time']}",
        f"- queried_rows: {summary['queried_rows']}",
        f"- upserted_rows: {summary['upserted_rows']}",
        f"- skipped_rows: {summary['skipped_rows']}",
        f"- failed: {summary.get('failed', False)}",
        f"- error: {summary['error']}",
        "",
    ]
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return {
        "paths": {
            "detail": detail_path,
            "latest": latest_path,
            "markdown_report": report_path,
        },
        "summary": summary,
    }


def build_open_auction_spot_snapshot_cron_entries(
    *,
    project_dir: str = "/Users/xiwei/stock_research",
    output_dir: str = "outputs/research/open_auction_spot_snapshot",
    log_path: str = "logs/open_auction_spot_snapshot.log",
) -> list[str]:
    quoted_project_dir = shlex.quote(project_dir)
    quoted_output_dir = shlex.quote(output_dir)
    quoted_log_path = shlex.quote(log_path)
    entries = []
    for target_time, minute in OPEN_AUCTION_SPOT_SNAPSHOT_TARGETS:
        entries.append(
            " ".join(
                [
                    str(minute),
                    "9",
                    "*",
                    "*",
                    "1-5",
                    f"cd {quoted_project_dir} &&",
                    f"OPEN_AUCTION_SPOT_OUTPUT_DIR={quoted_output_dir}",
                    f"scripts/run_open_auction_spot_snapshot.sh {target_time} $(date +\\%F)",
                    f">> {quoted_log_path} 2>&1",
                ]
            )
        )
    return entries


def open_auction_minute_market_row(
    raw: dict[str, Any],
    ts_code: str,
    source: str = "eastmoney_pre_min",
) -> dict[str, Any]:
    trade_time = parse_eastmoney_minute_time(_first_present(raw, ["时间", "trade_time"]))
    return {
        "asset_id": asset_id_from_ts_code(ts_code),
        "ts_code": ts_code,
        "trade_date": trade_time.date(),
        "trade_time": trade_time,
        "auction_phase": "open_call",
        "freq": "1min",
        "open": parse_float(_first_present(raw, ["开盘", "open"])),
        "high": parse_float(_first_present(raw, ["最高", "high"])),
        "low": parse_float(_first_present(raw, ["最低", "low"])),
        "close": parse_float(_first_present(raw, ["收盘", "close"])),
        "latest": parse_float(_first_present(raw, ["最新价", "latest", "close", "收盘"])),
        "volume": parse_float(_first_present(raw, ["成交量", "volume", "vol"])),
        "amount": parse_float(_first_present(raw, ["成交额", "amount"])),
        "source": source,
    }


def open_auction_minute_staging_row(
    raw: dict[str, Any],
    ts_code: str,
    source_endpoint: str,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {str(key): value for key, value in raw.items()}
    trade_time = parse_eastmoney_minute_time(_first_present(payload, ["时间", "trade_time"]))
    market_row = open_auction_minute_market_row(payload, ts_code=ts_code)
    return {
        "source_endpoint": source_endpoint,
        "request_params": params or {},
        "ts_code": ts_code,
        "raw_trade_time": str(_first_present(payload, ["时间", "trade_time"])),
        "trade_date": trade_time.date(),
        "trade_time": trade_time,
        "auction_phase": "open_call",
        "freq": "1min",
        "open": market_row["open"],
        "high": market_row["high"],
        "low": market_row["low"],
        "close": market_row["close"],
        "latest": market_row["latest"],
        "volume": market_row["volume"],
        "amount": market_row["amount"],
        "payload": payload,
        "payload_hash": payload_hash(payload),
    }


def query_eastmoney_open_auction_minute_rows(
    symbol: str,
    start_time: str,
    end_time: str,
) -> list[dict[str, Any]]:
    import akshare as ak

    frame = ak.stock_zh_a_hist_pre_min_em(
        symbol=symbol,
        start_time=start_time,
        end_time=end_time,
    )
    return list(frame.to_dict("records"))


def upsert_stock_open_auction_minute_bars(
    rows: list[dict[str, Any]],
    ts_code: str,
    source_endpoint: str = "stock_zh_a_hist_pre_min_em",
    research_service: str = SETTINGS.research_service,
    params: dict[str, Any] | None = None,
) -> int:
    if not rows:
        return 0

    staging_rows = [
        open_auction_minute_staging_row(
            row,
            ts_code=ts_code,
            source_endpoint=source_endpoint,
            params=params,
        )
        for row in rows
    ]
    market_rows = [open_auction_minute_market_row(row, ts_code=ts_code) for row in rows]
    staging_sql = """
    INSERT INTO staging.eastmoney_stock_auction_minute_bar (
        source_endpoint, request_params, ts_code, raw_trade_time, trade_date, trade_time,
        auction_phase, freq, open, high, low, close, latest, volume, amount, payload, payload_hash
    )
    VALUES (
        %(source_endpoint)s, %(request_params)s::jsonb, %(ts_code)s, %(raw_trade_time)s,
        %(trade_date)s, %(trade_time)s, %(auction_phase)s, %(freq)s, %(open)s, %(high)s,
        %(low)s, %(close)s, %(latest)s, %(volume)s, %(amount)s, %(payload)s::jsonb, %(payload_hash)s
    )
    ON CONFLICT (source_endpoint, ts_code, trade_time, auction_phase, freq)
    DO UPDATE SET
        request_params = EXCLUDED.request_params,
        raw_trade_time = EXCLUDED.raw_trade_time,
        trade_date = EXCLUDED.trade_date,
        open = EXCLUDED.open,
        high = EXCLUDED.high,
        low = EXCLUDED.low,
        close = EXCLUDED.close,
        latest = EXCLUDED.latest,
        volume = EXCLUDED.volume,
        amount = EXCLUDED.amount,
        payload = EXCLUDED.payload,
        payload_hash = EXCLUDED.payload_hash,
        fetched_at = now()
    """
    market_sql = """
    INSERT INTO market.stock_auction_minute_bar (
        asset_id, ts_code, trade_date, trade_time, auction_phase, freq,
        open, high, low, close, latest, volume, amount, source
    )
    VALUES (
        %(asset_id)s, %(ts_code)s, %(trade_date)s, %(trade_time)s, %(auction_phase)s, %(freq)s,
        %(open)s, %(high)s, %(low)s, %(close)s, %(latest)s, %(volume)s, %(amount)s, %(source)s
    )
    ON CONFLICT (trade_time, asset_id, auction_phase, freq, source)
    DO UPDATE SET
        ts_code = EXCLUDED.ts_code,
        trade_date = EXCLUDED.trade_date,
        open = EXCLUDED.open,
        high = EXCLUDED.high,
        low = EXCLUDED.low,
        close = EXCLUDED.close,
        latest = EXCLUDED.latest,
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


def load_open_auction_minute_universe(universe_path: str | Path) -> list[str]:
    frame = pd.read_csv(universe_path, low_memory=False)
    if "ts_code" in frame.columns:
        series = frame["ts_code"]
    elif "symbol" in frame.columns:
        raise ValueError("universe_path must include ts_code for exchange-safe collection")
    else:
        raise ValueError("universe_path must include ts_code")
    codes = series.dropna().astype(str).str.strip().str.upper()
    return sorted(code for code in codes.unique() if code and code != "NAN")


def collect_open_auction_minute_bars(
    trade_date: str | dt.date,
    ts_codes: list[str],
    start_time: str = "09:15:00",
    end_time: str = "09:25:00",
    sleep_seconds: float = 0.2,
    max_symbols: int | None = None,
) -> dict[str, Any]:
    target_date = dt.date.fromisoformat(str(trade_date)) if not isinstance(trade_date, dt.date) else trade_date
    selected_codes = sorted(ts_codes)[:max_symbols] if max_symbols else sorted(ts_codes)
    detail_rows: list[dict[str, Any]] = []
    total_upserted = 0
    for ts_code in selected_codes:
        symbol = symbol_from_ts_code(ts_code)
        error = ""
        rows: list[dict[str, Any]] = []
        selected_rows: list[dict[str, Any]] = []
        upserted = 0
        try:
            rows = query_eastmoney_open_auction_minute_rows(
                symbol=symbol,
                start_time=start_time,
                end_time=end_time,
            )
            selected_rows = [
                row
                for row in rows
                if parse_eastmoney_minute_time(_first_present(row, ["时间", "trade_time"])).date() == target_date
            ]
            params = {
                "symbol": symbol,
                "ts_code": ts_code,
                "trade_date": target_date.isoformat(),
                "start_time": start_time,
                "end_time": end_time,
            }
            upserted = upsert_stock_open_auction_minute_bars(
                selected_rows,
                ts_code=ts_code,
                source_endpoint="stock_zh_a_hist_pre_min_em",
                params=params,
            )
            total_upserted += upserted
        except Exception as exc:  # pragma: no cover - exercised in integration runs.
            error = str(exc)
        detail_rows.append(
            {
                "trade_date": target_date.isoformat(),
                "ts_code": ts_code,
                "symbol": symbol,
                "queried_rows": len(rows),
                "selected_rows": len(selected_rows),
                "upserted_rows": upserted,
                "error": error,
            }
        )
        if sleep_seconds:
            time.sleep(sleep_seconds)
    detail = pd.DataFrame(detail_rows)
    return {
        "detail": detail,
        "summary": {
            "trade_date": target_date.isoformat(),
            "symbols_requested": len(selected_codes),
            "symbols_failed": int((detail["error"] != "").sum()) if not detail.empty else 0,
            "upserted_rows": total_upserted,
        },
    }


def load_existing_open_auction_minute_ts_codes(
    trade_date: str | dt.date,
    ts_codes: list[str],
    source: str = "eastmoney_pre_min",
    research_service: str = SETTINGS.research_service,
) -> list[str]:
    if not ts_codes:
        return []
    target_date = dt.date.fromisoformat(str(trade_date)) if not isinstance(trade_date, dt.date) else trade_date
    sql = """
    SELECT ts_code
    FROM market.stock_auction_minute_bar
    WHERE trade_date = %s
      AND source = %s
      AND ts_code = ANY(%s)
    GROUP BY ts_code
    HAVING count(*) >= 1
    ORDER BY ts_code
    """
    with connect(research_service) as conn:
        rows = fetch_all(conn, sql, [target_date.isoformat(), source, list(ts_codes)])
    return [str(row["ts_code"]) for row in rows]


def collect_open_auction_minute_bars_until_covered(
    trade_date: str | dt.date,
    ts_codes: list[str],
    start_time: str = "09:15:00",
    end_time: str = "09:25:00",
    sleep_seconds: float = 5.0,
    max_rounds: int = 6,
    round_sleep_seconds: float = 300.0,
    max_symbols: int | None = None,
) -> dict[str, Any]:
    selected_codes = sorted(ts_codes)[:max_symbols] if max_symbols else sorted(ts_codes)
    all_details: list[pd.DataFrame] = []
    for round_index in range(1, max_rounds + 1):
        covered = set(load_existing_open_auction_minute_ts_codes(trade_date, selected_codes))
        remaining = [code for code in selected_codes if code not in covered]
        if not remaining:
            break
        result = collect_open_auction_minute_bars(
            trade_date=trade_date,
            ts_codes=remaining,
            start_time=start_time,
            end_time=end_time,
            sleep_seconds=sleep_seconds,
        )
        detail = result["detail"].copy()
        detail.insert(0, "round", round_index)
        all_details.append(detail)
        covered_after = set(load_existing_open_auction_minute_ts_codes(trade_date, selected_codes))
        if len(covered_after) == len(selected_codes):
            break
        if round_index < max_rounds and round_sleep_seconds:
            time.sleep(round_sleep_seconds)
    final_covered = set(load_existing_open_auction_minute_ts_codes(trade_date, selected_codes))
    combined = pd.concat(all_details, ignore_index=True) if all_details else pd.DataFrame()
    return {
        "detail": combined,
        "summary": {
            "trade_date": str(trade_date),
            "total_symbols": len(selected_codes),
            "covered_symbols": len(final_covered),
            "remaining_symbols": len(selected_codes) - len(final_covered),
            "rounds_executed": int(combined["round"].nunique()) if not combined.empty else 0,
            "upserted_rows": int(combined["upserted_rows"].sum()) if not combined.empty else 0,
        },
    }


def write_open_auction_minute_collect_report(
    result: dict[str, Any],
    output_dir: str | Path,
    trade_date: str | dt.date,
) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    date_text = str(trade_date)
    detail_path = output / f"open_auction_minute_collect_{date_text}.csv"
    latest_path = output / "open_auction_minute_collect_latest.csv"
    report_path = output / f"open_auction_minute_collect_{date_text}.md"
    result["detail"].to_csv(detail_path, index=False)
    result["detail"].to_csv(latest_path, index=False)
    summary = result["summary"]
    summary_keys = [
        "symbols_requested",
        "symbols_failed",
        "total_symbols",
        "covered_symbols",
        "remaining_symbols",
        "rounds_executed",
        "upserted_rows",
    ]
    summary_lines = [f"- {key}: {summary[key]}" for key in summary_keys if key in summary]
    report_path.write_text(
        "\n".join(
            [
                f"# Open Auction Minute Collect {date_text}",
                "",
                *summary_lines,
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return {
        "paths": {
            "detail": detail_path,
            "latest": latest_path,
            "markdown_report": report_path,
        },
        "summary": summary,
    }


def local_tushare_token(secrets_path: str | Path | None = None) -> str | None:
    path = Path(secrets_path or LOCAL_SECRETS_PATH)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    token = payload.get("tushare", {}).get("token")
    return str(token).strip() if token else None


def tushare_client(token: str | None = None) -> Any:
    selected_token = token or os.environ.get("TUSHARE_TOKEN") or local_tushare_token()
    if not selected_token:
        raise RuntimeError("TUSHARE_TOKEN or config/local_secrets.json:tushare.token is required for Tushare auction sync")
    return ts.pro_api(selected_token)


def sync_tushare_stock_auction_bars(
    start_date: str,
    end_date: str,
    auction_phases: list[str] | None = None,
    ts_codes: list[str] | None = None,
    trade_dates: list[str] | None = None,
    token: str | None = None,
    sleep_seconds: float = 1.3,
) -> dict[str, int]:
    if not ts_codes:
        raise ValueError("ts_codes is required for scoped Tushare auction sync")
    parsed_start = dt.date.fromisoformat(start_date)
    parsed_end = dt.date.fromisoformat(end_date)
    selected_phases = auction_phases or ["open_call", "close_call"]
    selected_ts_codes = set(ts_codes)
    client = tushare_client(token=token)
    counts = {phase: 0 for phase in selected_phases}
    if trade_dates:
        dates_to_query = [
            dt.date.fromisoformat(value)
            for value in sorted(set(trade_dates))
            if parsed_start <= dt.date.fromisoformat(value) <= parsed_end
        ]
    else:
        dates_to_query = []
        current_date = parsed_start
        while current_date <= parsed_end:
            dates_to_query.append(current_date)
            current_date += dt.timedelta(days=1)
    for current_date in dates_to_query:
        for phase in selected_phases:
            endpoint = auction_endpoint_for_phase(phase)
            rows = query_tushare_auction_rows_for_trade_date(
                client,
                trade_date=current_date,
                auction_phase=phase,
            )
            if selected_ts_codes:
                rows = [row for row in rows if str(row.get("ts_code")) in selected_ts_codes]
            params = {
                "trade_date": current_date.strftime("%Y%m%d"),
                "auction_phase": phase,
            }
            if ts_codes is not None:
                params["ts_codes"] = list(ts_codes)
            counts[phase] += upsert_stock_auction_bars(
                rows,
                auction_phase=phase,
                source_endpoint=endpoint,
                params=params,
            )
            if sleep_seconds:
                time.sleep(sleep_seconds)
    return counts


def load_lhb_auction_backfill_universe(
    *,
    candidate_paths: list[str | Path],
    start_date: str,
    end_date: str,
) -> list[str]:
    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date)
    values: set[str] = set()
    for path_value in candidate_paths:
        path = Path(path_value)
        frame = pd.read_csv(path, low_memory=False)
        if frame.empty or "ts_code" not in frame.columns:
            continue
        data = frame.copy()
        if "trade_date" in data.columns:
            dates = pd.to_datetime(data["trade_date"], errors="coerce")
            data = data[dates.between(start, end)]
        codes = data["ts_code"].dropna().astype(str).str.strip().str.upper()
        values.update(code for code in codes if code and code != "NAN")
    return sorted(values)


def build_lhb_auction_backfill_plan(
    *,
    trade_dates: list[str],
    ts_codes: list[str],
    auction_phases: list[str],
    existing_coverage: pd.DataFrame,
    min_coverage_ratio: float = 1.0,
) -> pd.DataFrame:
    selected_codes = sorted({str(code).strip().upper() for code in ts_codes if str(code).strip()})
    coverage = existing_coverage.copy()
    if coverage.empty:
        coverage = pd.DataFrame(columns=["trade_date", "ts_code", "auction_phase"])
    coverage["trade_date"] = pd.to_datetime(coverage["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    coverage["ts_code"] = coverage["ts_code"].astype(str).str.strip().str.upper()
    coverage["auction_phase"] = coverage["auction_phase"].astype(str).str.strip()

    rows: list[dict[str, object]] = []
    for trade_date in sorted(set(trade_dates)):
        normalized_date = pd.Timestamp(trade_date).strftime("%Y-%m-%d")
        for phase in auction_phases:
            existing_rows = coverage[
                coverage["trade_date"].eq(normalized_date)
                & coverage["auction_phase"].eq(phase)
                & coverage["ts_code"].isin(selected_codes)
            ]["ts_code"].nunique()
            coverage_ratio = float(existing_rows / len(selected_codes)) if selected_codes else 0.0
            missing_rows = max(len(selected_codes) - int(existing_rows), 0)
            if missing_rows <= 0 or coverage_ratio >= min_coverage_ratio:
                continue
            rows.append(
                {
                    "trade_date": normalized_date,
                    "auction_phase": phase,
                    "selected_ts_codes": len(selected_codes),
                    "existing_rows": int(existing_rows),
                    "missing_rows": missing_rows,
                    "coverage_ratio": coverage_ratio,
                    "should_query": True,
                }
            )
    return pd.DataFrame(
        rows,
        columns=[
            "trade_date",
            "auction_phase",
            "selected_ts_codes",
            "existing_rows",
            "missing_rows",
            "coverage_ratio",
            "should_query",
        ],
    )


def load_existing_lhb_auction_coverage(
    *,
    start_date: str,
    end_date: str,
    ts_codes: list[str],
    auction_phases: list[str],
    research_service: str = SETTINGS.research_service,
) -> pd.DataFrame:
    sql = """
    SELECT trade_date::text AS trade_date, ts_code, auction_phase
    FROM market.stock_auction_bar
    WHERE trade_date BETWEEN %s AND %s
      AND ts_code = ANY(%s)
      AND auction_phase = ANY(%s)
      AND source = 'tushare'
    ORDER BY trade_date, auction_phase, ts_code
    """
    with connect(research_service) as conn:
        rows = fetch_all(conn, sql, [start_date, end_date, ts_codes, auction_phases])
    return pd.DataFrame(rows, columns=["trade_date", "ts_code", "auction_phase"])


def write_lhb_auction_backfill_plan_report(
    *,
    plan: pd.DataFrame,
    output_dir: str | Path,
    start_date: str,
    end_date: str,
    ts_codes: list[str],
) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    suffix = f"{start_date.replace('-', '')}_{end_date.replace('-', '')}"
    selected_codes = sorted({str(code).strip().upper() for code in ts_codes if str(code).strip()})
    plan_path = output / f"lhb_auction_backfill_plan_{suffix}.csv"
    universe_path = output / f"lhb_auction_backfill_universe_{suffix}.csv"
    report_path = output / f"lhb_auction_backfill_plan_{suffix}.md"

    plan.to_csv(plan_path, index=False)
    pd.DataFrame({"ts_code": selected_codes}).to_csv(universe_path, index=False)

    missing_series = pd.to_numeric(plan.get("missing_rows", pd.Series(dtype=float)), errors="coerce").fillna(0)
    planned_calls = int(len(plan))
    planned_missing_rows = int(missing_series.sum())
    phase_counts = plan["auction_phase"].value_counts().to_dict() if "auction_phase" in plan.columns else {}
    lines = [
        "# LHB Auction Backfill Plan",
        "",
        f"- Window: `{start_date}` to `{end_date}`",
        f"- Universe size: `{len(selected_codes)}`",
        f"- Planned calls: `{planned_calls}`",
        f"- Planned missing rows: `{planned_missing_rows}`",
        f"- Phase counts: `{phase_counts}`",
        "",
        "This is a dry-run plan. It does not call Tushare.",
        "",
    ]
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return {
        "plan": plan,
        "summary": {
            "planned_calls": planned_calls,
            "planned_missing_rows": planned_missing_rows,
            "phase_counts": phase_counts,
            "ts_code_count": len(selected_codes),
        },
        "paths": {
            "plan": str(plan_path),
            "universe": str(universe_path),
            "markdown_report": str(report_path),
        },
    }


def run_lhb_auction_backfill_plan(
    *,
    plan: pd.DataFrame,
    ts_codes: list[str],
    max_calls: int,
    token: str | None = None,
    sleep_seconds: float = 1.3,
) -> dict[str, Any]:
    selected_ts_codes = {str(code).strip().upper() for code in ts_codes if str(code).strip()}
    client = tushare_client(token=token)
    executed_rows: list[dict[str, Any]] = []
    ordered_plan = plan.sort_values(["trade_date", "auction_phase"]).head(max_calls)
    for _, task in ordered_plan.iterrows():
        phase = str(task["auction_phase"])
        trade_date = dt.date.fromisoformat(str(task["trade_date"]))
        endpoint = auction_endpoint_for_phase(phase)
        raw_rows = query_tushare_auction_rows_for_trade_date(
            client,
            trade_date=trade_date,
            auction_phase=phase,
        )
        selected_rows = [
            row for row in raw_rows if str(row.get("ts_code")).strip().upper() in selected_ts_codes
        ]
        params = {
            "trade_date": trade_date.strftime("%Y%m%d"),
            "auction_phase": phase,
            "ts_codes": sorted(selected_ts_codes),
            "executor": "lhb_auction_backfill_plan_v1",
        }
        upserted = upsert_stock_auction_bars(
            selected_rows,
            auction_phase=phase,
            source_endpoint=endpoint,
            params=params,
        )
        executed_rows.append(
            {
                "trade_date": trade_date.strftime("%Y-%m-%d"),
                "auction_phase": phase,
                "queried_rows": len(raw_rows),
                "selected_rows": len(selected_rows),
                "upserted_rows": upserted,
            }
        )
        if sleep_seconds:
            time.sleep(sleep_seconds)

    executed_calls = len(executed_rows)
    return {
        "executed": pd.DataFrame(
            executed_rows,
            columns=["trade_date", "auction_phase", "queried_rows", "selected_rows", "upserted_rows"],
        ),
        "summary": {
            "executed_calls": executed_calls,
            "remaining_calls": max(len(plan) - executed_calls, 0),
            "upserted_rows": int(sum(row["upserted_rows"] for row in executed_rows)),
        },
    }


def load_open_trading_dates(
    *,
    start_date: str,
    end_date: str,
    research_service: str = SETTINGS.research_service,
) -> list[str]:
    sql = """
    SELECT DISTINCT trade_date::text AS trade_date
    FROM (
        SELECT trade_date
        FROM market.trading_calendar
        WHERE trade_date BETWEEN %s AND %s
          AND is_open = true
        UNION
        SELECT trade_date
        FROM market_daily_bar
        WHERE trade_date BETWEEN %s AND %s
          AND adjust_type = 'qfq'
    ) AS dates
    ORDER BY trade_date
    """
    with connect(research_service) as conn:
        rows = fetch_all(conn, sql, [start_date, end_date, start_date, end_date])
    return [str(row["trade_date"]) for row in rows]


def load_tushare_auction_full_coverage(
    *,
    start_date: str,
    end_date: str,
    auction_phases: list[str],
    research_service: str = SETTINGS.research_service,
) -> pd.DataFrame:
    sql = """
    SELECT trade_date::text AS trade_date, auction_phase, count(*)::int AS row_count
    FROM market.stock_auction_bar
    WHERE trade_date BETWEEN %s AND %s
      AND auction_phase = ANY(%s)
      AND source = 'tushare'
    GROUP BY trade_date, auction_phase
    ORDER BY trade_date, auction_phase
    """
    with connect(research_service) as conn:
        rows = fetch_all(conn, sql, [start_date, end_date, auction_phases])
    return pd.DataFrame(rows, columns=["trade_date", "auction_phase", "row_count"])


def build_tushare_auction_full_backfill_plan(
    *,
    trade_dates: list[str],
    auction_phases: list[str],
    existing_coverage: pd.DataFrame,
    min_rows_per_date: int = 1000,
) -> pd.DataFrame:
    coverage = existing_coverage.copy()
    if coverage.empty:
        coverage = pd.DataFrame(columns=["trade_date", "auction_phase", "row_count"])
    coverage["trade_date"] = pd.to_datetime(coverage["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    coverage["auction_phase"] = coverage["auction_phase"].astype(str).str.strip()
    coverage["row_count"] = pd.to_numeric(coverage["row_count"], errors="coerce").fillna(0).astype(int)
    row_counts = {
        (str(row.trade_date), str(row.auction_phase)): int(row.row_count)
        for row in coverage.itertuples(index=False)
    }

    rows: list[dict[str, Any]] = []
    for trade_date in sorted({pd.Timestamp(value).strftime("%Y-%m-%d") for value in trade_dates}):
        for phase in auction_phases:
            existing_rows = row_counts.get((trade_date, phase), 0)
            if existing_rows >= min_rows_per_date:
                continue
            rows.append(
                {
                    "trade_date": trade_date,
                    "auction_phase": phase,
                    "existing_rows": existing_rows,
                    "should_query": True,
                }
            )
    return pd.DataFrame(
        rows,
        columns=["trade_date", "auction_phase", "existing_rows", "should_query"],
    )


def run_tushare_auction_full_backfill_plan(
    *,
    plan: pd.DataFrame,
    max_calls: int,
    token: str | None = None,
    sleep_seconds: float = 1.3,
) -> dict[str, Any]:
    client = tushare_client(token=token)
    executed_rows: list[dict[str, Any]] = []
    ordered_plan = plan.sort_values(["trade_date", "auction_phase"]).head(max_calls)
    for _, task in ordered_plan.iterrows():
        phase = str(task["auction_phase"])
        trade_date = dt.date.fromisoformat(str(task["trade_date"]))
        endpoint = auction_endpoint_for_phase(phase)
        error = ""
        raw_rows: list[dict[str, Any]] = []
        upserted = 0
        try:
            raw_rows = query_tushare_auction_rows_for_trade_date(
                client,
                trade_date=trade_date,
                auction_phase=phase,
            )
            params = {
                "trade_date": trade_date.strftime("%Y%m%d"),
                "auction_phase": phase,
                "executor": "tushare_auction_full_backfill_v1",
            }
            upserted = upsert_stock_auction_bars(
                raw_rows,
                auction_phase=phase,
                source_endpoint=endpoint,
                params=params,
            )
        except Exception as exc:  # pragma: no cover - integration safety path.
            error = str(exc)
        executed_rows.append(
            {
                "trade_date": trade_date.strftime("%Y-%m-%d"),
                "auction_phase": phase,
                "queried_rows": len(raw_rows),
                "upserted_rows": upserted,
                "error": error,
            }
        )
        if sleep_seconds:
            time.sleep(sleep_seconds)

    executed_calls = len(executed_rows)
    failed_calls = sum(1 for row in executed_rows if row["error"])
    return {
        "executed": pd.DataFrame(
            executed_rows,
            columns=["trade_date", "auction_phase", "queried_rows", "upserted_rows", "error"],
        ),
        "summary": {
            "executed_calls": executed_calls,
            "failed_calls": failed_calls,
            "remaining_calls": max(len(plan) - executed_calls, 0),
            "queried_rows": int(sum(row["queried_rows"] for row in executed_rows)),
            "upserted_rows": int(sum(row["upserted_rows"] for row in executed_rows)),
        },
    }


def write_tushare_auction_full_backfill_report(
    *,
    plan: pd.DataFrame,
    executed: pd.DataFrame | None,
    output_dir: str | Path,
    start_date: str,
    end_date: str,
) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    suffix = f"{start_date.replace('-', '')}_{end_date.replace('-', '')}"
    plan_path = output / f"tushare_auction_full_backfill_plan_{suffix}.csv"
    latest_plan_path = output / "tushare_auction_full_backfill_plan_latest.csv"
    report_path = output / f"tushare_auction_full_backfill_{suffix}.md"
    plan.to_csv(plan_path, index=False)
    plan.to_csv(latest_plan_path, index=False)
    paths = {
        "plan": str(plan_path),
        "latest_plan": str(latest_plan_path),
        "markdown_report": str(report_path),
    }
    executed_calls = 0
    failed_calls = 0
    upserted_rows = 0
    if executed is not None:
        executed_path = output / f"tushare_auction_full_backfill_executed_{suffix}.csv"
        latest_executed_path = output / "tushare_auction_full_backfill_executed_latest.csv"
        executed.to_csv(executed_path, index=False)
        executed.to_csv(latest_executed_path, index=False)
        paths["executed"] = str(executed_path)
        paths["latest_executed"] = str(latest_executed_path)
        executed_calls = len(executed)
        failed_calls = int((executed["error"].astype(str) != "").sum()) if "error" in executed else 0
        upserted_rows = int(pd.to_numeric(executed.get("upserted_rows", pd.Series(dtype=float)), errors="coerce").fillna(0).sum())

    phase_counts = plan["auction_phase"].value_counts().to_dict() if "auction_phase" in plan else {}
    lines = [
        "# Tushare Auction Full Backfill",
        "",
        f"- Window: `{start_date}` to `{end_date}`",
        f"- Planned calls: `{len(plan)}`",
        f"- Phase counts: `{phase_counts}`",
        f"- Executed calls: `{executed_calls}`",
        f"- Failed calls: `{failed_calls}`",
        f"- Upserted rows: `{upserted_rows}`",
        "",
    ]
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return {
        "summary": {
            "planned_calls": int(len(plan)),
            "executed_calls": int(executed_calls),
            "failed_calls": int(failed_calls),
            "upserted_rows": int(upserted_rows),
            "phase_counts": phase_counts,
        },
        "paths": paths,
    }


def safe_divide(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    num = pd.to_numeric(numerator, errors="coerce")
    den = pd.to_numeric(denominator, errors="coerce")
    return (num / den - 1.0).where(den.ne(0))


def _phase_frame(auction_bars: pd.DataFrame, auction_phase: str, prefix: str) -> pd.DataFrame:
    if auction_bars.empty:
        return pd.DataFrame(columns=["trade_date", "ts_code"])
    frame = auction_bars[auction_bars["auction_phase"].eq(auction_phase)].copy()
    keep = ["trade_date", "ts_code", "open", "close", "amount", "vwap"]
    frame = frame[[column for column in keep if column in frame.columns]]
    rename = {
        "trade_date": f"{prefix}_trade_date",
        "open": f"{prefix}_open",
        "close": f"{prefix}_close",
        "amount": f"{prefix}_amount",
        "vwap": f"{prefix}_vwap",
    }
    return frame.rename(columns=rename)


def build_lhb_auction_observation_detail(
    *,
    trades: pd.DataFrame,
    auction_bars: pd.DataFrame,
) -> pd.DataFrame:
    detail = trades.copy()
    if detail.empty:
        return detail

    detail["trade_date"] = pd.to_datetime(detail["trade_date"]).dt.strftime("%Y-%m-%d")
    detail["entry_trade_date"] = pd.to_datetime(detail["entry_trade_date"]).dt.strftime("%Y-%m-%d")
    auction = auction_bars.copy()
    if not auction.empty:
        auction["trade_date"] = pd.to_datetime(auction["trade_date"]).dt.strftime("%Y-%m-%d")

    signal_close = _phase_frame(auction, "close_call", "signal_close")
    entry_open = _phase_frame(auction, "open_call", "entry_open")

    detail = detail.merge(
        signal_close,
        left_on=["trade_date", "ts_code"],
        right_on=["signal_close_trade_date", "ts_code"],
        how="left",
    )
    detail = detail.merge(
        entry_open,
        left_on=["entry_trade_date", "ts_code"],
        right_on=["entry_open_trade_date", "ts_code"],
        how="left",
    )

    detail["signal_close_auction_return"] = safe_divide(
        detail["signal_close_close"], detail["signal_close_open"]
    )
    detail["entry_open_auction_return"] = safe_divide(
        detail["entry_open_close"], detail["entry_open_open"]
    )
    detail["entry_open_vs_signal_close"] = safe_divide(
        detail["entry_open_close"], detail["signal_close_close"]
    )
    has_signal = detail["signal_close_close"].notna()
    has_entry = detail["entry_open_close"].notna()
    detail["auction_coverage"] = "missing"
    detail.loc[has_signal & ~has_entry, "auction_coverage"] = "signal_close_only"
    detail.loc[~has_signal & has_entry, "auction_coverage"] = "entry_open_only"
    detail.loc[has_signal & has_entry, "auction_coverage"] = "signal_close+entry_open"
    detail["auction_bucket"] = "entry_open_missing"
    detail.loc[
        detail["entry_open_auction_return"].ge(0),
        "auction_bucket",
    ] = "entry_open_positive"
    detail.loc[
        detail["entry_open_auction_return"].lt(0),
        "auction_bucket",
    ] = "entry_open_negative"
    return detail


def build_lhb_auction_observation_summary(detail: pd.DataFrame) -> pd.DataFrame:
    if detail.empty:
        return pd.DataFrame(
            columns=[
                "auction_bucket",
                "trade_count",
                "win_rate",
                "avg_realized_return",
                "median_realized_return",
            ]
        )
    grouped = detail.groupby("auction_bucket", dropna=False)["realized_return"]
    summary = grouped.agg(
        trade_count="count",
        avg_realized_return="mean",
        median_realized_return="median",
    ).reset_index()
    wins = detail.assign(is_win=detail["realized_return"].gt(0)).groupby("auction_bucket")[
        "is_win"
    ].mean()
    summary["win_rate"] = summary["auction_bucket"].map(wins)
    return summary[
        [
            "auction_bucket",
            "trade_count",
            "win_rate",
            "avg_realized_return",
            "median_realized_return",
        ]
    ].sort_values(["trade_count", "auction_bucket"], ascending=[False, True])


def load_stock_auction_bars(
    *,
    ts_codes: list[str],
    start_date: str,
    end_date: str,
    research_service: str = SETTINGS.research_service,
) -> pd.DataFrame:
    sql = """
    SELECT trade_date::text AS trade_date, ts_code, auction_phase, open, high, low, close,
           volume, amount, vwap
    FROM market.stock_auction_bar
    WHERE ts_code = ANY(%s)
      AND trade_date BETWEEN %s AND %s
    ORDER BY trade_date, ts_code, auction_phase
    """
    with connect(research_service) as conn:
        return pd.DataFrame(fetch_all(conn, sql, [ts_codes, start_date, end_date]))


def load_stock_close_auction_bars(
    *,
    ts_codes: list[str],
    start_date: str,
    end_date: str,
    research_service: str = SETTINGS.research_service,
) -> pd.DataFrame:
    bars = load_stock_auction_bars(
        ts_codes=ts_codes,
        start_date=start_date,
        end_date=end_date,
        research_service=research_service,
    )
    if bars.empty:
        return bars
    return bars[bars["auction_phase"].eq("close_call")].copy()


def _lhb_auction_observation_markdown(
    *,
    detail: pd.DataFrame,
    summary: pd.DataFrame,
    start_date: str,
    end_date: str,
) -> str:
    lines = [
        "# LHB Auction Sample Observation V1",
        "",
        f"- Date range: `{start_date}` to `{end_date}`",
        f"- Trades observed: `{len(detail)}`",
        f"- Auction coverage: `{detail['auction_coverage'].value_counts().to_dict() if not detail.empty else {}}`",
        "",
        "## Bucket Summary",
        "",
    ]
    if summary.empty:
        lines.append("No matched trades.")
    else:
        lines.append(summary.to_markdown(index=False))
    lines.extend(
        [
            "",
            "## Early Read",
            "",
            "- This is a smoke-size sample only; use it to inspect behavior, not to promote rules.",
            "- `signal_close_auction_return` describes signal-day closing auction pressure.",
            "- `entry_open_auction_return` describes next entry-day opening auction pressure.",
        ]
    )
    return "\n".join(lines) + "\n"


def build_lhb_auction_observation_report_v1(
    *,
    trades_path: str,
    start_date: str,
    end_date: str,
    ts_codes: list[str],
    output_dir: str,
    research_service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    trades = pd.read_csv(trades_path)
    trades = trades[
        trades["ts_code"].isin(ts_codes)
        & trades["trade_date"].between(start_date, end_date)
    ].copy()
    auction_bars = load_stock_auction_bars(
        ts_codes=ts_codes,
        start_date=start_date,
        end_date=end_date,
        research_service=research_service,
    )
    detail = build_lhb_auction_observation_detail(trades=trades, auction_bars=auction_bars)
    summary = build_lhb_auction_observation_summary(detail)

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = {
        "detail": str(out / "lhb_auction_observation_detail_v1.csv"),
        "summary": str(out / "lhb_auction_observation_summary_v1.csv"),
        "markdown_report": str(out / "lhb_auction_observation_v1.md"),
    }
    detail.to_csv(paths["detail"], index=False)
    summary.to_csv(paths["summary"], index=False)
    Path(paths["markdown_report"]).write_text(
        _lhb_auction_observation_markdown(
            detail=detail,
            summary=summary,
            start_date=start_date,
            end_date=end_date,
        ),
        encoding="utf-8",
    )
    return {
        "paths": paths,
        "summary": {
            "trades_observed": int(len(detail)),
            "auction_rows_loaded": int(len(auction_bars)),
        },
    }


def _trade_stats(frame: pd.DataFrame) -> dict[str, Any]:
    if frame.empty:
        return {
            "trade_count": 0,
            "win_rate": float("nan"),
            "avg_return": float("nan"),
            "median_return": float("nan"),
            "worst_return": float("nan"),
            "best_return": float("nan"),
        }
    returns = pd.to_numeric(frame["realized_return"], errors="coerce")
    return {
        "trade_count": int(len(frame)),
        "win_rate": float(returns.gt(0).mean()),
        "avg_return": float(returns.mean()),
        "median_return": float(returns.median()),
        "worst_return": float(returns.min()),
        "best_return": float(returns.max()),
    }


def build_lhb_auction_enhanced_rule_scan_v1(
    *,
    detail: pd.DataFrame,
    rule_layer: str = "follow_pool_core",
    thresholds: list[float] | None = None,
) -> dict[str, pd.DataFrame]:
    selected_thresholds = thresholds or [0.0, 0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07]
    frame = detail.copy()
    frame["trade_date"] = pd.to_datetime(frame["trade_date"])
    frame["trade_month"] = frame["trade_date"].dt.to_period("M").astype(str)
    frame["trade_quarter"] = frame["trade_date"].dt.to_period("Q").astype(str)
    frame["entry_open_vs_signal_close"] = pd.to_numeric(
        frame["entry_open_vs_signal_close"], errors="coerce"
    )
    frame["realized_return"] = pd.to_numeric(frame["realized_return"], errors="coerce")
    frame["is_win"] = frame["realized_return"].gt(0)
    layer = frame[frame["phase12a_rule_layer"].eq(rule_layer)].copy()

    scan_rows: list[dict[str, Any]] = []
    for threshold in selected_thresholds:
        subset = layer[layer["entry_open_vs_signal_close"].gt(threshold)]
        stats = _trade_stats(subset)
        if not subset.empty:
            returns = pd.to_numeric(subset["realized_return"], errors="coerce")
            top1_removed = subset.drop(returns.idxmax()) if len(subset) > 1 else subset.iloc[0:0]
            stats["trimmed_avg_ex_top1"] = _trade_stats(top1_removed)["avg_return"]
        else:
            stats["trimmed_avg_ex_top1"] = float("nan")
        scan_rows.append({"threshold": threshold, **stats})
    threshold_scan = pd.DataFrame(scan_rows)

    primary_threshold = 0.06 if 0.06 in selected_thresholds else max(selected_thresholds)
    strong_detail = layer[layer["entry_open_vs_signal_close"].gt(primary_threshold)].sort_values(
        "realized_return", ascending=False
    )

    robustness_rows = [
        {"slice": "all_phase15", **_trade_stats(frame)},
        {f"slice": f"{rule_layer}_all", **_trade_stats(layer)},
        {
            "slice": f"{rule_layer}_gap_gt_{str(primary_threshold).replace('.', '_')}",
            **_trade_stats(strong_detail),
        },
    ]
    if len(strong_detail) > 1:
        top1_removed = strong_detail.drop(strong_detail["realized_return"].idxmax())
        robustness_rows.append(
            {
                "slice": f"{rule_layer}_gap_gt_{str(primary_threshold).replace('.', '_')}_ex_top1",
                **_trade_stats(top1_removed),
            }
        )
    if len(strong_detail) > 3:
        top3_removed = strong_detail.drop(strong_detail["realized_return"].nlargest(3).index)
        robustness_rows.append(
            {
                "slice": f"{rule_layer}_gap_gt_{str(primary_threshold).replace('.', '_')}_ex_top3",
                **_trade_stats(top3_removed),
            }
        )
    robustness = pd.DataFrame(robustness_rows)

    quarterly = (
        strong_detail.groupby("trade_quarter", dropna=False)
        .apply(lambda group: pd.Series(_trade_stats(group)), include_groups=False)
        .reset_index()
        if not strong_detail.empty
        else pd.DataFrame()
    )
    monthly = (
        strong_detail.groupby("trade_month", dropna=False)
        .apply(lambda group: pd.Series(_trade_stats(group)), include_groups=False)
        .reset_index()
        if not strong_detail.empty
        else pd.DataFrame()
    )
    return {
        "threshold_scan": threshold_scan,
        "strong_detail": strong_detail,
        "robustness": robustness,
        "quarterly": quarterly,
        "monthly": monthly,
    }


def _lhb_auction_enhanced_rule_scan_markdown(
    *,
    result: dict[str, pd.DataFrame],
    rule_layer: str,
) -> str:
    lines = [
        "# LHB Auction Enhanced Rule Scan V1",
        "",
        f"- Rule layer: `{rule_layer}`",
        "- Primary signal: `entry_open_vs_signal_close`",
        "",
        "## Robustness",
        "",
        result["robustness"].to_markdown(index=False),
        "",
        "## Threshold Scan",
        "",
        result["threshold_scan"].to_markdown(index=False),
        "",
        "## Quarterly Stability",
        "",
        result["quarterly"].to_markdown(index=False) if not result["quarterly"].empty else "No rows.",
        "",
        "## Monthly Distribution",
        "",
        result["monthly"].to_markdown(index=False) if not result["monthly"].empty else "No rows.",
    ]
    return "\n".join(lines) + "\n"


def build_lhb_auction_enhanced_rule_scan_report_v1(
    *,
    detail_path: str,
    output_dir: str,
    rule_layer: str = "follow_pool_core",
    thresholds: list[float] | None = None,
) -> dict[str, Any]:
    detail = pd.read_csv(detail_path)
    result = build_lhb_auction_enhanced_rule_scan_v1(
        detail=detail,
        rule_layer=rule_layer,
        thresholds=thresholds,
    )
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = {
        "threshold_scan": str(out / "lhb_phase18_auction_threshold_scan_v1.csv"),
        "strong_detail": str(out / "lhb_phase18_auction_strong_detail_v1.csv"),
        "robustness": str(out / "lhb_phase18_auction_robustness_v1.csv"),
        "quarterly": str(out / "lhb_phase18_auction_quarterly_v1.csv"),
        "monthly": str(out / "lhb_phase18_auction_monthly_v1.csv"),
        "markdown_report": str(out / "lhb_phase18_auction_enhanced_rule_scan_v1.md"),
    }
    for key, frame in result.items():
        if key in paths:
            frame.to_csv(paths[key], index=False)
    Path(paths["markdown_report"]).write_text(
        _lhb_auction_enhanced_rule_scan_markdown(result=result, rule_layer=rule_layer),
        encoding="utf-8",
    )
    return {"paths": paths, **result}


LHB_RULE_LAYER_BASE_SCORE = {
    "follow_pool_core": 100.0,
    "follow_pool_low_drawdown": 80.0,
    "follow_pool_high_confidence": 70.0,
    "pending_intraday": 20.0,
    "watch_pool": 10.0,
    "chase_control": -20.0,
    "retreat_hard": -100.0,
}


def _auction_enhanced_score(frame: pd.DataFrame) -> pd.Series:
    layer_score = frame["phase12a_rule_layer"].map(LHB_RULE_LAYER_BASE_SCORE).fillna(0.0)
    gap = pd.to_numeric(frame["entry_open_vs_signal_close"], errors="coerce").fillna(0.0)
    signal_close = pd.to_numeric(frame["signal_close_auction_return"], errors="coerce").fillna(0.0)
    score = layer_score.copy()
    score += gap.gt(0.02).astype(float) * 10.0
    score += gap.gt(0.04).astype(float) * 15.0
    score += gap.gt(0.06).astype(float) * 25.0
    score += gap.lt(-0.02).astype(float) * -15.0
    score += signal_close.gt(0.02).astype(float) * 10.0
    score += signal_close.lt(-0.005).astype(float) * -10.0
    return score


def _topn_summary(frame: pd.DataFrame, *, strategy: str, top_n: int) -> dict[str, Any]:
    selected = frame.groupby("trade_date", group_keys=False).head(top_n)
    stats = _trade_stats(selected)
    return {
        "strategy": strategy,
        "top_n": top_n,
        **stats,
        "active_dates": int(selected["trade_date"].nunique()) if not selected.empty else 0,
    }


def build_lhb_auction_topn_rerank_comparison_v1(
    *,
    detail: pd.DataFrame,
    top_ns: list[int] | None = None,
) -> dict[str, pd.DataFrame]:
    selected_top_ns = top_ns or [5, 10]
    frame = detail.copy()
    frame["trade_date"] = pd.to_datetime(frame["trade_date"]).dt.strftime("%Y-%m-%d")
    frame["realized_return"] = pd.to_numeric(frame["realized_return"], errors="coerce")
    frame["entry_open_vs_signal_close"] = pd.to_numeric(
        frame["entry_open_vs_signal_close"], errors="coerce"
    )
    frame["signal_close_auction_return"] = pd.to_numeric(
        frame.get("signal_close_auction_return", pd.Series(index=frame.index)),
        errors="coerce",
    )
    frame = frame.reset_index(names="original_order")
    frame["auction_enhanced_score"] = _auction_enhanced_score(frame)

    baseline = frame.sort_values(["trade_date", "original_order"], ascending=[True, True])
    enhanced = frame.sort_values(
        ["trade_date", "auction_enhanced_score", "original_order"],
        ascending=[True, False, True],
    )

    rows = []
    selections = []
    for top_n in selected_top_ns:
        rows.append(_topn_summary(baseline, strategy="baseline_original_order", top_n=top_n))
        rows.append(_topn_summary(enhanced, strategy="auction_enhanced_rerank", top_n=top_n))
        base_sel = baseline.groupby("trade_date", group_keys=False).head(top_n).copy()
        base_sel["strategy"] = "baseline_original_order"
        base_sel["top_n"] = top_n
        enhanced_sel = enhanced.groupby("trade_date", group_keys=False).head(top_n).copy()
        enhanced_sel["strategy"] = "auction_enhanced_rerank"
        enhanced_sel["top_n"] = top_n
        selections.extend([base_sel, enhanced_sel])

    return {
        "summary": pd.DataFrame(rows),
        "selected": pd.concat(selections, ignore_index=True) if selections else pd.DataFrame(),
        "scored": frame,
    }


def _lhb_auction_topn_rerank_markdown(result: dict[str, pd.DataFrame]) -> str:
    return "\n".join(
        [
            "# LHB Auction TopN Rerank Comparison V1",
            "",
            "## Summary",
            "",
            result["summary"].to_markdown(index=False),
            "",
            "## Notes",
            "",
            "- Baseline keeps the original candidate order within each trade date.",
            "- Enhanced rerank uses rule-layer base score plus auction confirmation bonuses.",
            "- This is a ranking diagnostic; it does not yet model account capital or changed exits.",
        ]
    ) + "\n"


def build_lhb_auction_topn_rerank_comparison_report_v1(
    *,
    detail_path: str,
    output_dir: str,
    top_ns: list[int] | None = None,
) -> dict[str, Any]:
    detail = pd.read_csv(detail_path)
    result = build_lhb_auction_topn_rerank_comparison_v1(detail=detail, top_ns=top_ns)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = {
        "summary": str(out / "lhb_phase18b_auction_topn_rerank_summary_v1.csv"),
        "selected": str(out / "lhb_phase18b_auction_topn_rerank_selected_v1.csv"),
        "scored": str(out / "lhb_phase18b_auction_topn_rerank_scored_v1.csv"),
        "markdown_report": str(out / "lhb_phase18b_auction_topn_rerank_comparison_v1.md"),
    }
    result["summary"].to_csv(paths["summary"], index=False)
    result["selected"].to_csv(paths["selected"], index=False)
    result["scored"].to_csv(paths["scored"], index=False)
    Path(paths["markdown_report"]).write_text(
        _lhb_auction_topn_rerank_markdown(result),
        encoding="utf-8",
    )
    return {"paths": paths, **result}


def _normalize_date_string(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, errors="coerce").dt.strftime("%Y-%m-%d")


def build_lhb_close_auction_lifecycle_detail(
    *,
    trades: pd.DataFrame,
    close_auction_bars: pd.DataFrame,
) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame()

    trade_frame = trades.copy().reset_index(drop=True).reset_index(names="trade_id")
    for column in ["trade_date", "entry_trade_date", "exit_trade_date"]:
        if column in trade_frame.columns:
            trade_frame[column] = _normalize_date_string(trade_frame[column])
    if "exit_trade_date" not in trade_frame.columns:
        trade_frame["exit_trade_date"] = trade_frame.get("entry_trade_date")

    bars = close_auction_bars.copy()
    if bars.empty:
        bars = pd.DataFrame(
            columns=[
                "trade_date",
                "ts_code",
                "auction_phase",
                "open",
                "close",
                "amount",
                "vwap",
            ]
        )
    bars["trade_date"] = _normalize_date_string(bars["trade_date"])
    if "auction_phase" in bars.columns:
        bars = bars[bars["auction_phase"].eq("close_call")].copy()
    for column in ["open", "close", "amount", "vwap"]:
        if column in bars.columns:
            bars[column] = pd.to_numeric(bars[column], errors="coerce")

    rows: list[dict[str, Any]] = []
    trade_columns = [
        column
        for column in [
            "trade_id",
            "trade_date",
            "entry_trade_date",
            "exit_trade_date",
            "ts_code",
            "strategy",
            "top_n",
            "phase12a_rule_layer",
            "realized_return",
            "account_trade_status",
        ]
        if column in trade_frame.columns
    ]
    for trade in trade_frame.to_dict("records"):
        start = trade.get("trade_date")
        end = trade.get("exit_trade_date") or trade.get("entry_trade_date") or start
        matched = bars[
            bars["ts_code"].eq(trade["ts_code"])
            & bars["trade_date"].ge(start)
            & bars["trade_date"].le(end)
        ].sort_values("trade_date")
        if matched.empty:
            row = {column: trade.get(column) for column in trade_columns}
            row.update(
                {
                    "signal_trade_date": trade.get("trade_date"),
                    "auction_trade_date": pd.NA,
                    "lifecycle_day_index": 0,
                    "close_auction_open": pd.NA,
                    "close_auction_close": pd.NA,
                    "close_auction_amount": pd.NA,
                    "close_auction_vwap": pd.NA,
                    "close_auction_return": pd.NA,
                    "close_auction_close_change": pd.NA,
                    "is_exit_day_close_auction": False,
                }
            )
            rows.append(row)
            continue
        previous_close = None
        for day_index, bar in enumerate(matched.to_dict("records")):
            close_price = bar.get("close")
            row = {column: trade.get(column) for column in trade_columns}
            row.update(
                {
                    "signal_trade_date": trade.get("trade_date"),
                    "auction_trade_date": bar.get("trade_date"),
                    "lifecycle_day_index": day_index,
                    "close_auction_open": bar.get("open"),
                    "close_auction_close": close_price,
                    "close_auction_amount": bar.get("amount"),
                    "close_auction_vwap": bar.get("vwap"),
                    "close_auction_return": (
                        close_price / bar.get("open") - 1.0
                        if pd.notna(close_price) and pd.notna(bar.get("open")) and bar.get("open") != 0
                        else pd.NA
                    ),
                    "close_auction_close_change": (
                        close_price / previous_close - 1.0
                        if pd.notna(close_price)
                        and pd.notna(previous_close)
                        and previous_close not in (0, None)
                        else pd.NA
                    ),
                    "is_exit_day_close_auction": bool(bar.get("trade_date") == end),
                }
            )
            rows.append(row)
            previous_close = close_price

    detail = pd.DataFrame(rows)
    for column in ["realized_return", "close_auction_return", "close_auction_amount"]:
        if column in detail.columns:
            detail[column] = pd.to_numeric(detail[column], errors="coerce")
    if "is_exit_day_close_auction" in detail.columns:
        detail["is_exit_day_close_auction"] = detail["is_exit_day_close_auction"].astype(object)
    return detail


def _close_lifecycle_bucket(row: pd.Series) -> str:
    if row["close_auction_days"] == 0:
        return "close_auction_missing"
    if row["smash_close_auction_days"] > 0:
        return "has_close_auction_smash"
    if row["negative_close_auction_days"] > 0:
        return "mixed_close_auction"
    if row["strong_close_auction_days"] > 0 and row["last_close_auction_return"] >= 0:
        return "persistent_positive_close_auction"
    return "flat_or_weak_close_auction"


def build_lhb_close_auction_trade_summary(detail: pd.DataFrame) -> pd.DataFrame:
    if detail.empty:
        return pd.DataFrame()

    frame = detail.copy()
    frame["close_auction_return"] = pd.to_numeric(frame["close_auction_return"], errors="coerce")
    frame["close_auction_amount"] = pd.to_numeric(frame["close_auction_amount"], errors="coerce")
    base_columns = [
        column
        for column in [
            "trade_id",
            "ts_code",
            "signal_trade_date",
            "trade_date",
            "entry_trade_date",
            "exit_trade_date",
            "strategy",
            "top_n",
            "phase12a_rule_layer",
            "realized_return",
        ]
        if column in frame.columns
    ]
    rows = []
    for trade_id, group in frame.groupby("trade_id", dropna=False):
        valid_returns = group["close_auction_return"].dropna()
        base = group.iloc[0][base_columns].to_dict()
        exit_rows = group[group["is_exit_day_close_auction"].eq(True)]
        exit_return = (
            pd.to_numeric(exit_rows["close_auction_return"], errors="coerce").dropna().iloc[-1]
            if not exit_rows.empty
            and not pd.to_numeric(exit_rows["close_auction_return"], errors="coerce").dropna().empty
            else float("nan")
        )
        base.update(
            {
                "trade_id": trade_id,
                "close_auction_days": int(valid_returns.count()),
                "mean_close_auction_return": float(valid_returns.mean()) if not valid_returns.empty else float("nan"),
                "min_close_auction_return": float(valid_returns.min()) if not valid_returns.empty else float("nan"),
                "last_close_auction_return": float(valid_returns.iloc[-1]) if not valid_returns.empty else float("nan"),
                "exit_day_close_auction_return": float(exit_return) if pd.notna(exit_return) else float("nan"),
                "negative_close_auction_days": int(valid_returns.lt(0).sum()),
                "strong_close_auction_days": int(valid_returns.ge(0.005).sum()),
                "smash_close_auction_days": int(valid_returns.le(-0.005).sum()),
                "max_close_auction_amount": float(group["close_auction_amount"].max())
                if group["close_auction_amount"].notna().any()
                else float("nan"),
            }
        )
        rows.append(base)
    summary = pd.DataFrame(rows)
    summary["close_lifecycle_bucket"] = summary.apply(_close_lifecycle_bucket, axis=1)
    return summary


def build_lhb_close_auction_bucket_summary(summary: pd.DataFrame) -> pd.DataFrame:
    if summary.empty:
        return pd.DataFrame()
    frame = summary.copy()
    frame["realized_return"] = pd.to_numeric(frame["realized_return"], errors="coerce")
    rows = []
    group_columns = [
        column for column in ["strategy", "top_n", "close_lifecycle_bucket"] if column in frame.columns
    ]
    for keys, group in frame.groupby(group_columns, dropna=False):
        if not isinstance(keys, tuple):
            keys = (keys,)
        row = dict(zip(group_columns, keys))
        returns = group["realized_return"].dropna()
        row.update(
            {
                "trade_count": int(len(group)),
                "win_rate": float(returns.gt(0).mean()) if not returns.empty else float("nan"),
                "avg_return": float(returns.mean()) if not returns.empty else float("nan"),
                "median_return": float(returns.median()) if not returns.empty else float("nan"),
                "worst_return": float(returns.min()) if not returns.empty else float("nan"),
                "best_return": float(returns.max()) if not returns.empty else float("nan"),
                "avg_close_auction_days": float(group["close_auction_days"].mean()),
            }
        )
        rows.append(row)
    return pd.DataFrame(rows).sort_values(
        [column for column in ["strategy", "top_n", "trade_count"] if column in group_columns or column == "trade_count"],
        ascending=[True, True, False][: len([column for column in ["strategy", "top_n", "trade_count"] if column in group_columns or column == "trade_count"])],
    )


def _lhb_close_auction_lifecycle_markdown(
    *,
    trade_summary: pd.DataFrame,
    bucket_summary: pd.DataFrame,
    detail: pd.DataFrame,
) -> str:
    coverage = (
        trade_summary["close_lifecycle_bucket"].value_counts(dropna=False).to_dict()
        if not trade_summary.empty
        else {}
    )
    lines = [
        "# LHB Phase18D Close Auction Lifecycle V1",
        "",
        f"- Filled trades observed: `{len(trade_summary)}`",
        f"- Lifecycle close-auction rows: `{len(detail)}`",
        f"- Bucket coverage: `{coverage}`",
        "",
        "## Bucket Summary",
        "",
        bucket_summary.to_markdown(index=False) if not bucket_summary.empty else "No rows.",
        "",
        "## Interpretation",
        "",
        "- `has_close_auction_smash`: at least one lifecycle close call return <= -0.5%.",
        "- `persistent_positive_close_auction`: covered lifecycle has no negative close call and at least one close call return >= +0.5%.",
        "- This diagnostic reads cached `market.stock_auction_bar` close-call rows only; it does not call Tushare.",
    ]
    return "\n".join(lines) + "\n"


def build_lhb_phase18d_close_auction_lifecycle_report_v1(
    *,
    trades_path: str,
    output_dir: str,
    strategy: str | None = None,
    top_n: int | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    research_service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    trades = pd.read_csv(trades_path)
    if "account_trade_status" in trades.columns:
        trades = trades[trades["account_trade_status"].eq("filled")].copy()
    if strategy:
        trades = trades[trades["strategy"].eq(strategy)].copy()
    if top_n is not None and "top_n" in trades.columns:
        trades = trades[pd.to_numeric(trades["top_n"], errors="coerce").eq(top_n)].copy()
    if start_date:
        trades = trades[_normalize_date_string(trades["trade_date"]).ge(start_date)].copy()
    if end_date:
        trades = trades[_normalize_date_string(trades["trade_date"]).le(end_date)].copy()

    if trades.empty:
        auction_bars = pd.DataFrame()
        detail = pd.DataFrame()
        trade_summary = pd.DataFrame()
        bucket_summary = pd.DataFrame()
    else:
        trades["trade_date"] = _normalize_date_string(trades["trade_date"])
        trades["exit_trade_date"] = _normalize_date_string(trades["exit_trade_date"])
        load_start = start_date or str(trades["trade_date"].min())
        load_end = end_date or str(trades["exit_trade_date"].dropna().max())
        auction_bars = load_stock_close_auction_bars(
            ts_codes=sorted(trades["ts_code"].dropna().unique().tolist()),
            start_date=load_start,
            end_date=load_end,
            research_service=research_service,
        )
        detail = build_lhb_close_auction_lifecycle_detail(
            trades=trades,
            close_auction_bars=auction_bars,
        )
        trade_summary = build_lhb_close_auction_trade_summary(detail)
        bucket_summary = build_lhb_close_auction_bucket_summary(trade_summary)

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = {
        "detail": str(out / "lhb_phase18d_close_auction_lifecycle_detail_v1.csv"),
        "trade_summary": str(out / "lhb_phase18d_close_auction_trade_summary_v1.csv"),
        "bucket_summary": str(out / "lhb_phase18d_close_auction_bucket_summary_v1.csv"),
        "markdown_report": str(out / "lhb_phase18d_close_auction_lifecycle_v1.md"),
    }
    detail.to_csv(paths["detail"], index=False)
    trade_summary.to_csv(paths["trade_summary"], index=False)
    bucket_summary.to_csv(paths["bucket_summary"], index=False)
    Path(paths["markdown_report"]).write_text(
        _lhb_close_auction_lifecycle_markdown(
            trade_summary=trade_summary,
            bucket_summary=bucket_summary,
            detail=detail,
        ),
        encoding="utf-8",
    )
    return {
        "paths": paths,
        "summary": {
            "trades_observed": int(len(trade_summary)),
            "auction_rows_loaded": int(len(auction_bars)),
            "lifecycle_rows": int(len(detail)),
        },
    }


def _phase18e_key_dates(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    if "trade_date" in result.columns:
        result["trade_date"] = _normalize_date_string(result["trade_date"])
    if "ts_code" in result.columns:
        result["ts_code"] = result["ts_code"].astype(str)
    if "top_n" in result.columns:
        result["top_n"] = pd.to_numeric(result["top_n"], errors="coerce")
    return result


def _phase18e_first_by_trade_stock(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=["trade_date", "ts_code", *columns])
    keep = [column for column in ["trade_date", "ts_code", *columns] if column in frame.columns]
    result = _phase18e_key_dates(frame[keep]).drop_duplicates(["trade_date", "ts_code"])
    return result


def build_lhb_phase18e_joint_exit_state_detail_v1(
    *,
    account_trades: pd.DataFrame,
    auction_observation: pd.DataFrame,
    close_lifecycle: pd.DataFrame,
    intraday_indicators: pd.DataFrame | None = None,
) -> pd.DataFrame:
    base = _phase18e_key_dates(account_trades)
    if "account_trade_status" in base.columns:
        base = base[base["account_trade_status"].eq("filled")].copy()
    if base.empty:
        return pd.DataFrame()

    auction_cols = [
        "entry_open_vs_signal_close",
        "entry_open_auction_return",
        "signal_close_auction_return",
        "entry_open_amount",
        "signal_close_amount",
    ]
    auction = _phase18e_first_by_trade_stock(auction_observation, auction_cols)
    detail = base.merge(auction, on=["trade_date", "ts_code"], how="left")

    close = _phase18e_key_dates(close_lifecycle)
    close_cols = [
        "trade_date",
        "ts_code",
        "top_n",
        "strategy",
        "close_lifecycle_bucket",
        "last_close_auction_return",
        "min_close_auction_return",
        "negative_close_auction_days",
        "smash_close_auction_days",
    ]
    close = close[[column for column in close_cols if column in close.columns]]
    if not close.empty:
        detail = detail.merge(
            close.drop_duplicates(["trade_date", "ts_code", "top_n", "strategy"]),
            on=["trade_date", "ts_code", "top_n", "strategy"],
            how="left",
        )

    indicators = intraday_indicators if intraday_indicators is not None else pd.DataFrame()
    indicator_cols = [
        "exit_day_close_vs_vwap",
        "next_morning_close_vs_vwap",
        "exit_day_close_position",
        "exit_day_high_to_close_drawdown",
        "exit_3d_return",
        "exit_5d_return",
        "selection_score",
        "lhb_net_buy_ratio",
    ]
    indicators = _phase18e_first_by_trade_stock(indicators, indicator_cols)
    if not indicators.empty:
        detail = detail.merge(indicators, on=["trade_date", "ts_code"], how="left")

    for column in [
        "realized_return",
        "entry_open_vs_signal_close",
        "entry_open_auction_return",
        "signal_close_auction_return",
        "last_close_auction_return",
        "min_close_auction_return",
        "exit_day_close_vs_vwap",
        "next_morning_close_vs_vwap",
        "exit_day_close_position",
        "exit_3d_return",
        "exit_5d_return",
        "lhb_net_buy_ratio",
    ]:
        if column not in detail.columns:
            detail[column] = pd.NA
        if column in detail.columns:
            detail[column] = pd.to_numeric(detail[column], errors="coerce")

    detail["weak_open_confirm"] = (
        detail["entry_open_vs_signal_close"].lt(0)
        | detail["entry_open_auction_return"].lt(0)
    ).fillna(False)
    detail["weak_close_lifecycle"] = detail["close_lifecycle_bucket"].eq("mixed_close_auction")
    detail["weak_intraday_acceptance"] = (
        detail["exit_day_close_vs_vwap"].lt(0)
        & detail["next_morning_close_vs_vwap"].lt(0)
    ).fillna(False)
    detail.loc[detail["exit_day_close_position"].lt(0.35).fillna(False), "weak_intraday_acceptance"] = True

    detail["strong_open_confirm"] = detail["entry_open_vs_signal_close"].ge(0.04).fillna(False)
    detail["strong_close_lifecycle"] = detail["close_lifecycle_bucket"].isin(
        ["persistent_positive_close_auction", "flat_or_weak_close_auction"]
    )
    detail["strong_intraday_acceptance"] = (
        detail["exit_day_close_vs_vwap"].ge(0)
        & detail["next_morning_close_vs_vwap"].ge(0)
    ).fillna(False)
    detail["strong_lhb_capital"] = detail["lhb_net_buy_ratio"].ge(0.20).fillna(False)

    weak_columns = ["weak_open_confirm", "weak_close_lifecycle", "weak_intraday_acceptance"]
    strong_columns = [
        "strong_open_confirm",
        "strong_close_lifecycle",
        "strong_intraday_acceptance",
        "strong_lhb_capital",
    ]
    detail["weak_factor_count"] = detail[weak_columns].sum(axis=1).astype(int)
    detail["strong_factor_count"] = detail[strong_columns].sum(axis=1).astype(int)
    detail["joint_exit_state"] = "watch_hold"
    detail.loc[detail["weak_factor_count"].ge(3), "joint_exit_state"] = "hard_exit"
    detail.loc[detail["weak_factor_count"].eq(2), "joint_exit_state"] = "soft_exit"
    detail.loc[
        detail["weak_factor_count"].eq(0) & detail["strong_factor_count"].gt(0),
        "joint_exit_state",
    ] = "strong_hold"
    detail["mixed_close_plus_weak_open"] = (
        detail["close_lifecycle_bucket"].eq("mixed_close_auction")
        & detail["weak_open_confirm"]
    )
    detail["missed_return_to_3d"] = (
        pd.to_numeric(detail.get("exit_3d_return", pd.Series(index=detail.index)), errors="coerce")
        - pd.to_numeric(detail["realized_return"], errors="coerce")
    )
    for column in [
        "weak_open_confirm",
        "weak_close_lifecycle",
        "weak_intraday_acceptance",
        "strong_open_confirm",
        "strong_close_lifecycle",
        "strong_intraday_acceptance",
        "strong_lhb_capital",
        "mixed_close_plus_weak_open",
    ]:
        detail[column] = detail[column].astype(object)
    return detail.reset_index(drop=True)


def _phase18e_rule_summary_row(
    *,
    profile: str,
    description: str,
    detail: pd.DataFrame,
    exclude_mask: pd.Series,
    baseline_win_rate: float,
) -> dict[str, Any]:
    excluded = detail[exclude_mask.fillna(False)]
    kept = detail[~exclude_mask.fillna(False)]
    kept_returns = pd.to_numeric(kept.get("realized_return", pd.Series(dtype="float64")), errors="coerce").dropna()
    excluded_returns = pd.to_numeric(excluded.get("realized_return", pd.Series(dtype="float64")), errors="coerce").dropna()
    missed = pd.to_numeric(excluded.get("missed_return_to_3d", pd.Series(dtype="float64")), errors="coerce").dropna()
    kept_win_rate = float(kept_returns.gt(0).mean()) if len(kept_returns) else float("nan")
    return {
        "rule_profile": profile,
        "description": description,
        "trade_count": int(len(detail)),
        "kept_count": int(len(kept)),
        "excluded_count": int(len(excluded)),
        "kept_win_rate": kept_win_rate,
        "excluded_win_rate": float(excluded_returns.gt(0).mean()) if len(excluded_returns) else float("nan"),
        "win_rate_delta_vs_baseline": kept_win_rate - baseline_win_rate
        if pd.notna(kept_win_rate) and pd.notna(baseline_win_rate)
        else float("nan"),
        "kept_avg_return": float(kept_returns.mean()) if len(kept_returns) else float("nan"),
        "kept_median_return": float(kept_returns.median()) if len(kept_returns) else float("nan"),
        "kept_worst_return": float(kept_returns.min()) if len(kept_returns) else float("nan"),
        "excluded_avg_return": float(excluded_returns.mean()) if len(excluded_returns) else float("nan"),
        "excluded_avg_missed_return_to_3d": float(missed.mean()) if len(missed) else float("nan"),
    }


def build_lhb_phase18e_joint_exit_rule_scan_v1(detail: pd.DataFrame) -> pd.DataFrame:
    if detail.empty:
        return pd.DataFrame()
    frame = detail.copy()
    frame["realized_return"] = pd.to_numeric(frame["realized_return"], errors="coerce")
    if "mixed_close_plus_weak_open" not in frame.columns:
        frame["mixed_close_plus_weak_open"] = (
            frame.get("close_lifecycle_bucket", pd.Series(index=frame.index)).eq("mixed_close_auction")
            & frame.get("weak_open_confirm", pd.Series(False, index=frame.index)).eq(True)
        )
    if "strong_close_lifecycle" not in frame.columns:
        frame["strong_close_lifecycle"] = frame.get(
            "close_lifecycle_bucket", pd.Series(index=frame.index)
        ).isin(["persistent_positive_close_auction", "flat_or_weak_close_auction"])
    if "missed_return_to_3d" not in frame.columns:
        frame["missed_return_to_3d"] = (
            pd.to_numeric(frame.get("exit_3d_return", pd.Series(index=frame.index)), errors="coerce")
            - frame["realized_return"]
        )
    baseline_returns = frame["realized_return"].dropna()
    baseline_win_rate = float(baseline_returns.gt(0).mean()) if len(baseline_returns) else float("nan")
    profiles = [
        (
            "baseline_all",
            "All filled trades, no joint-factor exclusion",
            pd.Series(False, index=frame.index),
        ),
        (
            "exclude_hard_exit",
            "Exclude hard_exit only: three weak factors in agreement",
            frame["joint_exit_state"].eq("hard_exit"),
        ),
        (
            "exclude_soft_or_hard_exit",
            "Exclude soft_exit and hard_exit: at least two weak factors in agreement",
            frame["joint_exit_state"].isin(["soft_exit", "hard_exit"]),
        ),
        (
            "exclude_mixed_close_plus_weak_open",
            "Exclude mixed close-auction lifecycle only when opening auction is also weak",
            frame["mixed_close_plus_weak_open"].eq(True),
        ),
        (
            "exclude_weak_open_without_strong_close",
            "Exclude weak opening auction when close-auction lifecycle is not strong",
            frame["weak_open_confirm"].eq(True) & ~frame["strong_close_lifecycle"].eq(True),
        ),
        (
            "keep_strong_hold_only_upper_bound",
            "Upper-bound diagnostic: keep only rows with zero weak factors and at least one strong factor",
            ~frame["joint_exit_state"].eq("strong_hold"),
        ),
    ]
    rows = [
        _phase18e_rule_summary_row(
            profile=profile,
            description=description,
            detail=frame,
            exclude_mask=mask,
            baseline_win_rate=baseline_win_rate,
        )
        for profile, description, mask in profiles
    ]
    return pd.DataFrame(rows).sort_values(
        ["kept_win_rate", "kept_avg_return"], ascending=[False, False], na_position="last"
    )


def _lhb_phase18e_joint_exit_markdown(
    *,
    detail: pd.DataFrame,
    scan: pd.DataFrame,
) -> str:
    lines = [
        "# LHB Phase18E Joint Exit Diagnostics V1",
        "",
        "Priority: improve win rate first, then measure sell-flying risk.",
        "",
        f"- Trades observed: `{len(detail)}`",
        f"- State distribution: `{detail['joint_exit_state'].value_counts().to_dict() if not detail.empty else {}}`",
        "",
        "## Rule Scan",
        "",
        scan.to_markdown(index=False) if not scan.empty else "No rows.",
        "",
        "## Notes",
        "",
        "- This is a joint-factor diagnostic, not a single-factor close-auction rule.",
        "- `has_close_auction_smash` is not treated as weak by itself; Phase18D showed it can still belong to strong recoveries.",
        "- Sell-flying risk uses `exit_3d_return - realized_return` where Phase16D indicator coverage is available.",
    ]
    return "\n".join(lines) + "\n"


def build_lhb_phase18e_joint_exit_diagnostics_report_v1(
    *,
    account_trades_path: str,
    auction_observation_path: str,
    close_lifecycle_path: str,
    output_dir: str,
    intraday_indicator_path: str | None = None,
    strategy: str | None = None,
    top_n: int | None = None,
) -> dict[str, Any]:
    account_trades = pd.read_csv(account_trades_path)
    if strategy:
        account_trades = account_trades[account_trades["strategy"].eq(strategy)].copy()
    if top_n is not None and "top_n" in account_trades.columns:
        account_trades = account_trades[pd.to_numeric(account_trades["top_n"], errors="coerce").eq(top_n)].copy()
    auction_observation = pd.read_csv(auction_observation_path)
    close_lifecycle = pd.read_csv(close_lifecycle_path)
    intraday = pd.read_csv(intraday_indicator_path) if intraday_indicator_path else pd.DataFrame()

    detail = build_lhb_phase18e_joint_exit_state_detail_v1(
        account_trades=account_trades,
        auction_observation=auction_observation,
        close_lifecycle=close_lifecycle,
        intraday_indicators=intraday,
    )
    scan = build_lhb_phase18e_joint_exit_rule_scan_v1(detail)

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = {
        "state_detail": str(out / "lhb_phase18e_joint_exit_state_detail_v1.csv"),
        "rule_scan": str(out / "lhb_phase18e_joint_exit_rule_scan_v1.csv"),
        "markdown_report": str(out / "lhb_phase18e_joint_exit_diagnostics_v1.md"),
    }
    detail.to_csv(paths["state_detail"], index=False)
    scan.to_csv(paths["rule_scan"], index=False)
    Path(paths["markdown_report"]).write_text(
        _lhb_phase18e_joint_exit_markdown(detail=detail, scan=scan),
        encoding="utf-8",
    )
    return {
        "paths": paths,
        "summary": {
            "trades_observed": int(len(detail)),
            "state_distribution": detail["joint_exit_state"].value_counts().to_dict()
            if not detail.empty
            else {},
        },
    }
