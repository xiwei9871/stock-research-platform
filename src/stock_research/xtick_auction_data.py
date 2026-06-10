import datetime as dt
import gzip
import io
import json
import os
import time
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

import pandas as pd

from stock_research.config import SETTINGS
from stock_research.db import connect, execute_many
from stock_research.minute_data import canonical_json, parse_float, payload_hash


XTICK_BASE_URL = "http://api.xtick.top"
XTICK_DAYUPDATE_SYMBOLS = ["szm", "shm", "cyb", "kcb", "bj"]


def xtick_token(token: str | None = None, token_env: str = "XTICK_TOKEN") -> str:
    selected = token or os.environ.get(token_env)
    if not selected:
        raise RuntimeError(f"{token_env} is required for XTick auction collection")
    return selected


def decode_xtick_response(raw: bytes) -> Any:
    if raw.startswith(b"PK"):
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            name = archive.namelist()[0]
            text = archive.read(name).decode("utf-8")
    elif raw.startswith(b"\x1f\x8b"):
        text = gzip.decompress(raw).decode("utf-8")
    else:
        text = raw.decode("utf-8")
    return json.loads(text)


def request_xtick_json(
    endpoint: str,
    params: dict[str, Any],
    token: str | None = None,
    token_env: str = "XTICK_TOKEN",
    base_url: str = XTICK_BASE_URL,
    timeout: int = 60,
) -> Any:
    request_params = {**params, "token": xtick_token(token=token, token_env=token_env)}
    url = f"{base_url}{endpoint}?{urllib.parse.urlencode(request_params)}"
    with urllib.request.urlopen(url, timeout=timeout) as response:
        payload = decode_xtick_response(response.read())
    if isinstance(payload, dict) and payload.get("code") == -1:
        raise RuntimeError(str(payload.get("message") or payload))
    return payload


def xtick_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, list):
            return [row for row in data if isinstance(row, dict)]
        if isinstance(data, dict):
            for key in ["list", "rows", "data"]:
                if isinstance(data.get(key), list):
                    return [row for row in data[key] if isinstance(row, dict)]
            return [data]
    return []


def query_xtick_bid_detail_rows(
    code: str,
    trade_date: str,
    token: str | None = None,
    token_env: str = "XTICK_TOKEN",
) -> list[dict[str, Any]]:
    payload = request_xtick_json(
        "/doc/hot/biddetail",
        {"type": 1, "code": code, "tradeDate": trade_date},
        token=token,
        token_env=token_env,
    )
    return xtick_rows(payload)


def query_xtick_dayupdate_bid_rows(
    symbol: str,
    trade_date: str,
    token: str | None = None,
    token_env: str = "XTICK_TOKEN",
) -> list[dict[str, Any]]:
    payload = request_xtick_json(
        "/doc/hot/dayupdate",
        {"dataType": "bid", "symbol": symbol, "tradeDate": trade_date},
        token=token,
        token_env=token_env,
        timeout=120,
    )
    return xtick_rows(payload)


def parse_xtick_time_ms(value: Any) -> dt.datetime:
    return dt.datetime.fromtimestamp(int(value) / 1000).replace(tzinfo=None)


def ts_code_from_xtick_code(code: str) -> str:
    value = str(code).zfill(6)
    if value.startswith(("6", "9")):
        exchange = "SH"
    elif value.startswith(("4", "8")):
        exchange = "BJ"
    else:
        exchange = "SZ"
    return f"{value}.{exchange}"


def asset_id_from_ts_code(ts_code: str) -> str:
    symbol, exchange = ts_code.split(".", 1)
    return f"CN:{exchange.upper()}:{symbol}"


def xtick_auction_detail_market_row(
    raw: dict[str, Any],
    source: str = "xtick_biddetail",
) -> dict[str, Any]:
    code = str(raw["code"]).zfill(6)
    ts_code = ts_code_from_xtick_code(code)
    trade_time = parse_xtick_time_ms(raw["time"])
    return {
        "asset_id": asset_id_from_ts_code(ts_code),
        "ts_code": ts_code,
        "code": code,
        "raw_time": int(raw["time"]),
        "trade_date": trade_time.date(),
        "trade_time": trade_time,
        "auction_phase": "open_call",
        "price": parse_float(raw.get("price")),
        "close": parse_float(raw.get("close")),
        "jjzf": parse_float(raw.get("jjzf")),
        "jjl": parse_float(raw.get("jjl")),
        "jje": parse_float(raw.get("jje")),
        "nol": parse_float(raw.get("nol")),
        "noe": parse_float(raw.get("noe")),
        "trend": int(raw["trend"]) if raw.get("trend") is not None else None,
        "source": source,
    }


def xtick_auction_detail_staging_row(
    raw: dict[str, Any],
    source_endpoint: str,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {str(key): value for key, value in raw.items()}
    market_row = xtick_auction_detail_market_row(payload)
    return {
        "source_endpoint": source_endpoint,
        "request_params": params or {},
        "code": market_row["code"],
        "raw_time": market_row["raw_time"],
        "trade_date": market_row["trade_date"],
        "trade_time": market_row["trade_time"],
        "auction_phase": "open_call",
        "price": market_row["price"],
        "close": market_row["close"],
        "jjzf": market_row["jjzf"],
        "jjl": market_row["jjl"],
        "jje": market_row["jje"],
        "nol": market_row["nol"],
        "noe": market_row["noe"],
        "trend": market_row["trend"],
        "payload": payload,
        "payload_hash": payload_hash(payload),
    }


def upsert_xtick_open_auction_detail_rows(
    rows: list[dict[str, Any]],
    source_endpoint: str,
    source: str,
    research_service: str = SETTINGS.research_service,
    params: dict[str, Any] | None = None,
) -> int:
    if not rows:
        return 0

    staging_rows = [
        xtick_auction_detail_staging_row(row, source_endpoint=source_endpoint, params=params)
        for row in rows
    ]
    market_rows = [xtick_auction_detail_market_row(row, source=source) for row in rows]
    staging_sql = """
    INSERT INTO staging.xtick_stock_auction_detail (
        source_endpoint, request_params, code, raw_time, trade_date, trade_time, auction_phase,
        price, close, jjzf, jjl, jje, nol, noe, trend, payload, payload_hash
    )
    VALUES (
        %(source_endpoint)s, %(request_params)s::jsonb, %(code)s, %(raw_time)s, %(trade_date)s,
        %(trade_time)s, %(auction_phase)s, %(price)s, %(close)s, %(jjzf)s, %(jjl)s, %(jje)s,
        %(nol)s, %(noe)s, %(trend)s, %(payload)s::jsonb, %(payload_hash)s
    )
    ON CONFLICT (source_endpoint, code, raw_time)
    DO UPDATE SET
        request_params = EXCLUDED.request_params,
        trade_date = EXCLUDED.trade_date,
        trade_time = EXCLUDED.trade_time,
        price = EXCLUDED.price,
        close = EXCLUDED.close,
        jjzf = EXCLUDED.jjzf,
        jjl = EXCLUDED.jjl,
        jje = EXCLUDED.jje,
        nol = EXCLUDED.nol,
        noe = EXCLUDED.noe,
        trend = EXCLUDED.trend,
        payload = EXCLUDED.payload,
        payload_hash = EXCLUDED.payload_hash,
        fetched_at = now()
    """
    market_sql = """
    INSERT INTO market.stock_auction_detail (
        asset_id, ts_code, code, raw_time, trade_date, trade_time, auction_phase,
        price, close, jjzf, jjl, jje, nol, noe, trend, source
    )
    VALUES (
        %(asset_id)s, %(ts_code)s, %(code)s, %(raw_time)s, %(trade_date)s, %(trade_time)s,
        %(auction_phase)s, %(price)s, %(close)s, %(jjzf)s, %(jjl)s, %(jje)s,
        %(nol)s, %(noe)s, %(trend)s, %(source)s
    )
    ON CONFLICT (trade_time, asset_id, source)
    DO UPDATE SET
        ts_code = EXCLUDED.ts_code,
        code = EXCLUDED.code,
        raw_time = EXCLUDED.raw_time,
        trade_date = EXCLUDED.trade_date,
        price = EXCLUDED.price,
        close = EXCLUDED.close,
        jjzf = EXCLUDED.jjzf,
        jjl = EXCLUDED.jjl,
        jje = EXCLUDED.jje,
        nol = EXCLUDED.nol,
        noe = EXCLUDED.noe,
        trend = EXCLUDED.trend,
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


def filter_rows_for_trade_date(rows: list[dict[str, Any]], trade_date: str | dt.date) -> list[dict[str, Any]]:
    target = dt.date.fromisoformat(str(trade_date)) if not isinstance(trade_date, dt.date) else trade_date
    return [row for row in rows if parse_xtick_time_ms(row["time"]).date() == target]


def collect_xtick_dayupdate_bid(
    trade_date: str,
    symbols: list[str] | None = None,
    token: str | None = None,
    token_env: str = "XTICK_TOKEN",
    sleep_seconds: float = 1.0,
) -> dict[str, Any]:
    selected_symbols = symbols or XTICK_DAYUPDATE_SYMBOLS
    detail_rows = []
    total_upserted = 0
    for symbol in selected_symbols:
        error = ""
        rows: list[dict[str, Any]] = []
        selected_rows: list[dict[str, Any]] = []
        upserted = 0
        try:
            rows = query_xtick_dayupdate_bid_rows(
                symbol=symbol,
                trade_date=trade_date,
                token=token,
                token_env=token_env,
            )
            selected_rows = filter_rows_for_trade_date(rows, trade_date)
            upserted = upsert_xtick_open_auction_detail_rows(
                selected_rows,
                source_endpoint="dayupdate",
                source="xtick_dayupdate_bid",
                params={"dataType": "bid", "symbol": symbol, "tradeDate": trade_date},
            )
            total_upserted += upserted
        except Exception as exc:  # pragma: no cover - exercised in integration runs.
            error = str(exc)
        detail_rows.append(
            {
                "trade_date": trade_date,
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
            "trade_date": trade_date,
            "symbols_requested": len(selected_symbols),
            "symbols_failed": int((detail["error"] != "").sum()) if not detail.empty else 0,
            "upserted_rows": total_upserted,
        },
    }


def write_xtick_auction_collect_report(
    result: dict[str, Any],
    output_dir: str | Path,
    trade_date: str | dt.date,
) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    date_text = str(trade_date)
    detail_path = output / f"xtick_auction_detail_collect_{date_text}.csv"
    latest_path = output / "xtick_auction_detail_collect_latest.csv"
    report_path = output / f"xtick_auction_detail_collect_{date_text}.md"
    result["detail"].to_csv(detail_path, index=False)
    result["detail"].to_csv(latest_path, index=False)
    summary = result["summary"]
    report_path.write_text(
        "\n".join(
            [
                f"# XTick Auction Detail Collect {date_text}",
                "",
                f"- symbols_requested: {summary['symbols_requested']}",
                f"- symbols_failed: {summary['symbols_failed']}",
                f"- upserted_rows: {summary['upserted_rows']}",
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
