"""TongDaXin historical 09:25 opening-match backfill.

The TDX protocol reports auction volume in hands.  This module keeps that
unit in the canonical row (and records the unit in the raw payload) instead
of silently presenting it as shares like the Tushare adapter does.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from dataclasses import dataclass
import datetime as dt
import hashlib
import json
import os
import time
from typing import Any, Callable, Iterable, Sequence

from stock_research.config import SETTINGS
from stock_research.db import connect, execute_many, fetch_all


TDX_AUCTION_SOURCE = "tdx"
TDX_AUCTION_SOURCE_VERSION = "eltdx-3.1.3"
TDX_AUCTION_ENDPOINT = "tdx:0x0fc6"
DEFAULT_TDX_HOSTS = (
    "116.205.183.150:7709",
    "116.205.171.132:7709",
    "111.230.186.52:7709",
    "129.204.230.128:7709",
)
UNSUPPORTED_PAYLOAD_MARKER = "invalid historical ticks payload"


@dataclass(frozen=True)
class TdxFetchResult:
    """Result for one symbol query; ``tick=None, error=None`` is no-match."""

    ts_code: str
    tdx_code: str
    tick: Any | None
    error: str | None = None
    error_kind: str | None = None

    @property
    def matched(self) -> bool:
        return self.tick is not None and self.error is None

    @property
    def is_unsupported_payload(self) -> bool:
        return self.error_kind == "unsupported_payload"


def ts_code_to_tdx_code(ts_code: str) -> str:
    """Convert ``000001.SZ``/``600000.SH``/``830799.BJ`` to TDX format."""

    value = str(ts_code).strip().upper()
    if "." in value:
        symbol, exchange = value.split(".", 1)
        exchange = {"BSE": "BJ"}.get(exchange, exchange)
    else:
        symbol, exchange = value, ""
    if len(symbol) != 6 or not symbol.isdigit():
        raise ValueError(f"unsupported ts_code: {ts_code!r}")
    if not exchange:
        if symbol.startswith(("6", "68", "9")):
            exchange = "SH"
        elif symbol.startswith(("4", "8")):
            exchange = "BJ"
        else:
            exchange = "SZ"
    prefix = {"SH": "sh", "SZ": "sz", "BJ": "bj"}.get(exchange)
    if prefix is None:
        raise ValueError(f"unsupported exchange in ts_code: {ts_code!r}")
    return f"{prefix}{symbol}"


def _date_text(value: str | dt.date | dt.datetime) -> str:
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()[:10]
    return str(value)[:10]


def tdx_trade_to_values(tick: Any) -> dict[str, Any]:
    """Normalize a TDX ``TradeTick`` into auction bar values.

    TDX's volume is in hands, so amount is calculated as ``price * hands *
    100`` yuan and the raw payload explicitly records that unit.
    """

    price = float(getattr(tick, "price"))
    volume = int(getattr(tick, "volume", 0) or 0)
    order_count = getattr(tick, "order_count", None)
    if order_count is not None:
        order_count = int(order_count)
    return {
        "price": price,
        "volume": volume,
        "amount": price * volume * 100.0,
        "vwap": price,
        "order_count": order_count,
        "time_label": str(getattr(tick, "time_label", "09:25")),
        "event_kind": str(getattr(tick, "event_kind", "opening_match")),
        "record_hex": str(getattr(tick, "record_hex", "")),
        "volume_unit": "hand",
    }


def _tick_payload(tick: Any, values: dict[str, Any]) -> dict[str, Any]:
    payload = dict(values)
    trade_datetime = getattr(tick, "trade_datetime", None)
    if trade_datetime is not None:
        payload["trade_datetime"] = getattr(trade_datetime, "isoformat", lambda: str(trade_datetime))()
    for name in (
        "index",
        "absolute_index",
        "time_minutes",
        "price_milli",
        "status_raw",
        "side",
        "price_delta_raw",
        "price_acc_raw",
        "auction_matched_volume",
        "auction_unmatched_signed_volume",
    ):
        value = getattr(tick, name, None)
        if value is not None:
            payload[name] = value
    return payload


def build_tdx_market_row(
    *,
    asset: dict[str, Any],
    trade_date: str | dt.date,
    tick: Any,
) -> dict[str, Any]:
    """Build the canonical row plus provenance fields used by staging."""

    values = tdx_trade_to_values(tick)
    payload = _tick_payload(tick, values)
    payload_text = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return {
        "asset_id": str(asset["asset_id"]),
        "ts_code": str(asset["ts_code"]),
        "trade_date": _date_text(trade_date),
        "auction_phase": "open_call",
        "open": values["price"],
        "high": values["price"],
        "low": values["price"],
        "close": values["price"],
        "volume": values["volume"],
        "amount": values["amount"],
        "vwap": values["vwap"],
        "order_count": values["order_count"],
        "volume_unit": "hand",
        "source": TDX_AUCTION_SOURCE,
        "source_endpoint": TDX_AUCTION_ENDPOINT,
        "request_params": {
            "tdx_code": ts_code_to_tdx_code(str(asset["ts_code"])),
            "trade_date": _date_text(trade_date),
            "record": "0x0fc6",
        },
        "payload": payload,
        "payload_hash": hashlib.sha256(payload_text.encode("utf-8")).hexdigest(),
    }


def fetch_tdx_opening_matches(
    client: Any,
    ts_codes: Sequence[str],
    trade_date: str | dt.date,
    *,
    workers: int = 8,
    retry_attempts: int = 2,
    retry_sleep_seconds: float = 0.25,
    max_pages: int = 100,
) -> list[TdxFetchResult]:
    """Fetch one formal 09:25 match per symbol with isolated retries."""

    if workers <= 0:
        raise ValueError("workers must be positive")
    if retry_attempts < 0:
        raise ValueError("retry_attempts must be non-negative")

    requested = list(dict.fromkeys(str(code) for code in ts_codes))
    date_text = _date_text(trade_date)

    def fetch_one(ts_code: str) -> TdxFetchResult:
        tdx_code = ts_code_to_tdx_code(ts_code)
        last_error: str | None = None
        for attempt in range(retry_attempts + 1):
            try:
                tick = client.trades.opening_match_history(
                    tdx_code,
                    date_text,
                    max_pages=max_pages,
                )
                return TdxFetchResult(ts_code, tdx_code, tick, None)
            except Exception as exc:  # noqa: BLE001 - preserve per-symbol failure
                last_error = f"{exc.__class__.__name__}: {exc}"
                # A malformed historical payload is deterministic for a small
                # set of retired securities on the TDX main site. Retrying the
                # same response only adds latency and cannot repair the data.
                if UNSUPPORTED_PAYLOAD_MARKER in str(exc).lower():
                    return TdxFetchResult(
                        ts_code,
                        tdx_code,
                        None,
                        last_error,
                        "unsupported_payload",
                    )
                if attempt < retry_attempts and retry_sleep_seconds > 0:
                    time.sleep(retry_sleep_seconds)
        return TdxFetchResult(ts_code, tdx_code, None, last_error)

    if not requested:
        return []
    with ThreadPoolExecutor(max_workers=min(workers, len(requested))) as executor:
        return list(executor.map(fetch_one, requested))


def load_tdx_auction_universe(
    conn: Any,
    trade_date: str | dt.date,
) -> list[dict[str, Any]]:
    """Load historically listed A-share assets with positive raw daily volume.

    Querying every historically listed symbol produces a large, misleading
    no-match bucket for suspended/non-trading securities.  The existing raw
    daily-bar table is used only as a cheap scope filter; the auction values
    themselves still come exclusively from TDX.  If the daily table has no
    rows for a date, fall back to the active listed universe so a source-data
    gap does not silently skip an entire trading day.
    """

    date_text = _date_text(trade_date)
    sql = """
    SELECT a.asset_id, a.ts_code, a.exchange, a.symbol
    FROM core.asset_master AS a
    JOIN market_daily_bar AS d
      ON d.asset_id = a.asset_id
     AND d.trade_date = %s
     AND d.adjust_type = 'raw'
     AND d.volume > 0
    WHERE a.exchange IN ('SH', 'SZ', 'BJ')
      AND a.symbol ~ '^[0-9]{6}$'
      AND a.is_active IS TRUE
      AND a.list_date <= %s
      AND (a.delist_date IS NULL OR a.delist_date >= %s)
    ORDER BY a.ts_code
    """
    assets = fetch_all(conn, sql, [date_text, date_text, date_text])
    if assets:
        return assets

    fallback_sql = """
    SELECT asset_id, ts_code, exchange, symbol
    FROM core.asset_master
    WHERE exchange IN ('SH', 'SZ', 'BJ')
      AND symbol ~ '^[0-9]{6}$'
      AND is_active IS TRUE
      AND list_date <= %s
      AND (delist_date IS NULL OR delist_date >= %s)
    ORDER BY ts_code
    """
    return fetch_all(conn, fallback_sql, [date_text, date_text])


def load_tdx_auction_exclusion_count(
    conn: Any,
    trade_date: str | dt.date,
) -> int:
    """Count historically eligible symbols currently retired on the TDX list.

    TDX returns a malformed historical-ticks payload for these symbols.  They
    are excluded from the request scope, but the count is persisted so the
    resulting historical coverage gap remains visible and auditable.
    """

    date_text = _date_text(trade_date)
    sql = """
    SELECT count(*) AS count
    FROM core.asset_master AS a
    WHERE a.exchange IN ('SH', 'SZ', 'BJ')
      AND a.symbol ~ '^[0-9]{6}$'
      AND a.is_active IS NOT TRUE
      AND a.list_date <= %s
      AND (a.delist_date IS NULL OR a.delist_date >= %s)
    """
    rows = fetch_all(conn, sql, [date_text, date_text])
    return int(rows[0]["count"] or 0) if rows else 0


def tdx_date_result_is_fatal(result: dict[str, Any]) -> bool:
    """Only an all-error date is fatal; individual no-data symbols are common."""

    return int(result.get("failed_codes", 0) or 0) > 0 and int(result.get("matched_rows", 0) or 0) == 0


def upsert_tdx_auction_rows(conn: Any, rows: Iterable[dict[str, Any]]) -> int:
    """Write raw TDX payloads and canonical rows idempotently."""

    rows = list(rows)
    if not rows:
        return 0
    staging_sql = """
    INSERT INTO staging.tdx_stock_auction_bar (
        source_endpoint, request_params, ts_code, raw_trade_date, trade_date,
        auction_phase, open, high, low, close, volume, amount, vwap,
        order_count, payload, payload_hash
    ) VALUES (
        %s, %s::jsonb, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
        %s, %s::jsonb, %s
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
        order_count = EXCLUDED.order_count,
        payload = EXCLUDED.payload,
        payload_hash = EXCLUDED.payload_hash,
        fetched_at = now()
    """
    staging_rows = [
        (
            row["source_endpoint"],
            json.dumps(row["request_params"], ensure_ascii=False, sort_keys=True),
            row["ts_code"],
            row["trade_date"],
            row["trade_date"],
            row["auction_phase"],
            row["open"],
            row["high"],
            row["low"],
            row["close"],
            row["volume"],
            row["amount"],
            row["vwap"],
            row["order_count"],
            json.dumps(row["payload"], ensure_ascii=False, sort_keys=True, default=str),
            row["payload_hash"],
        )
        for row in rows
    ]
    execute_many(conn, staging_sql, staging_rows)

    market_sql = """
    INSERT INTO market.stock_auction_bar (
        asset_id, ts_code, trade_date, auction_phase, open, high, low, close,
        volume, amount, vwap, volume_unit, source, order_count
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
        order_count = EXCLUDED.order_count,
        volume_unit = EXCLUDED.volume_unit,
        updated_at = now()
    """
    execute_many(
        conn,
        market_sql,
        [
            (
                row["asset_id"],
                row["ts_code"],
                row["trade_date"],
                row["auction_phase"],
                row["open"],
                row["high"],
                row["low"],
                row["close"],
                row["volume"],
                row["amount"],
                row["vwap"],
                row["volume_unit"],
                row["source"],
                row["order_count"],
            )
            for row in rows
        ],
    )
    return len(rows)


def _make_tdx_client(
    *,
    hosts: Sequence[str] | None,
    timeout_seconds: float,
    server_count: int,
    connections_per_server: int,
) -> Any:
    try:
        from eltdx import TdxClient
    except ImportError as exc:  # pragma: no cover - dependency install failure
        raise RuntimeError("eltdx==3.1.3 is required for TDX auction backfill") from exc
    selected_hosts = tuple(hosts or _hosts_from_environment())
    return TdxClient.from_hosts(
        list(selected_hosts),
        timeout=timeout_seconds,
        server_count=server_count,
        connections_per_server=connections_per_server,
        probe_hosts=False,
    )


def _hosts_from_environment() -> tuple[str, ...]:
    value = os.environ.get("TDX_AUCTION_HOSTS", "")
    hosts = tuple(item.strip() for item in value.split(",") if item.strip())
    return hosts or DEFAULT_TDX_HOSTS


def backfill_tdx_auction_date(
    trade_date: str | dt.date,
    *,
    service: str = SETTINGS.research_service,
    client: Any | None = None,
    hosts: Sequence[str] | None = None,
    timeout_seconds: float = 8.0,
    server_count: int = 4,
    connections_per_server: int = 1,
    workers: int = 8,
    retry_attempts: int = 2,
    retry_sleep_seconds: float = 0.25,
    max_pages: int = 100,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Fetch and persist one trading date; no-match symbols are not failures."""

    date_text = _date_text(trade_date)
    with connect(service) as conn:
        excluded_codes = load_tdx_auction_exclusion_count(conn, date_text)
        assets = load_tdx_auction_universe(conn, date_text)
        if not assets:
            return {
                "trade_date": date_text,
                "requested_codes": 0,
                "matched_rows": 0,
                "missing_codes": 0,
                "failed_codes": 0,
                "unsupported_codes": 0,
                "excluded_codes": excluded_codes,
                "rows_written": 0,
            }
        asset_by_code = {str(row["ts_code"]): row for row in assets}
        managed_client = _make_tdx_client(
            hosts=hosts,
            timeout_seconds=timeout_seconds,
            server_count=server_count,
            connections_per_server=connections_per_server,
        ) if client is None else nullcontext(client)
        with managed_client as active_client:
            results = fetch_tdx_opening_matches(
                active_client,
                list(asset_by_code),
                date_text,
                workers=workers,
                retry_attempts=retry_attempts,
                retry_sleep_seconds=retry_sleep_seconds,
                max_pages=max_pages,
            )
        rows = [
            build_tdx_market_row(
                asset=asset_by_code[result.ts_code],
                trade_date=date_text,
                tick=result.tick,
            )
            for result in results
            if result.matched
        ]
        rows_written = 0 if dry_run else upsert_tdx_auction_rows(conn, rows)
    return {
        "trade_date": date_text,
        "requested_codes": len(results),
        "matched_rows": len(rows),
        "missing_codes": sum(
            result.tick is None and result.error is None for result in results
        ),
        "failed_codes": sum(
            result.error is not None and not result.is_unsupported_payload
            for result in results
        ),
        "unsupported_codes": sum(result.is_unsupported_payload for result in results),
        "excluded_codes": excluded_codes,
        "rows_written": rows_written,
        "failed_examples": [
            {
                "ts_code": result.ts_code,
                "error": result.error,
                "error_kind": result.error_kind,
            }
            for result in results
            if result.error
        ][:20],
        "unsupported_examples": [
            {"ts_code": result.ts_code, "error": result.error}
            for result in results
            if result.is_unsupported_payload
        ][:20],
    }
