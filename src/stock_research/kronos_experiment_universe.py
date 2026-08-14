"""Deterministic, provenance-carrying stock universe selection for Kronos runs."""

from __future__ import annotations

import hashlib
import json
import math
import random
import re
from collections.abc import Mapping, Sequence
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

try:
    from stock_research.db import connect, fetch_all
except ModuleNotFoundError as exc:  # pragma: no cover - permits isolated seam tests
    if exc.name != "psycopg":
        raise

    def connect(_service: str):
        raise RuntimeError("psycopg is required for database access")

    def fetch_all(_conn, _sql, _params=None):
        raise RuntimeError("psycopg is required for database access")


_ST_NAME = re.compile(r"^(\*?ST|S\*ST)", re.IGNORECASE)
_OHLC = ("open", "high", "low", "close")


@dataclass(frozen=True)
class UniverseSelection:
    asset_ids: tuple[str, ...]
    candidates: tuple[dict[str, Any], ...]
    selected_rows: tuple[dict[str, Any], ...]
    candidate_count: int
    selection_seed: int | None
    filters: Mapping[str, Any]
    candidate_fingerprint: str
    selection_fingerprint: str


def _jsonable(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


def _fingerprint(value: Any) -> str:
    payload = json.dumps(_jsonable(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@contextmanager
def _db(service: str):
    with connect(service) as conn:
        yield conn


def resolve_latest_market_date(*, adjust_type: str, service: str) -> str:
    sql = """
        SELECT MAX(trade_date) AS trade_date
        FROM market_daily_bar
        WHERE adjust_type = %(adjust_type)s
    """
    with _db(service) as conn:
        rows = fetch_all(conn, sql, {"adjust_type": adjust_type})
    dates = [str(row["trade_date"]) for row in rows if row.get("trade_date") is not None]
    if not dates:
        raise ValueError("no market dates available")
    return max(dates)


def _eligible_candidates(*, market: str, adjust_type: str, input_window: int, cutoff_date: str, service: str):
    candidate_sql = r"""
        SELECT asset_id, market, status, symbol, name, exchange, delist_date
        FROM public.asset_master
        WHERE market = %(market)s
          AND status = 'listed'
          AND delist_date IS NULL
          AND name !~* '^(\*?ST|S\*ST)'
        ORDER BY asset_id
    """
    bar_sql = """
        SELECT asset_id, trade_date, trade_status, is_st, open, high, low, close
        FROM market_daily_bar
        WHERE adjust_type = %(adjust_type)s
          AND trade_date <= %(cutoff_date)s
          AND trade_status = '1'
          AND isfinite(open) AND isfinite(high) AND isfinite(low) AND isfinite(close)
        ORDER BY asset_id, trade_date
    """
    params = {"market": market, "adjust_type": adjust_type, "cutoff_date": cutoff_date, "input_window": input_window}
    with _db(service) as conn:
        candidates = fetch_all(conn, candidate_sql, params)
        bars = fetch_all(conn, bar_sql, params)
    grouped: dict[str, list[dict[str, Any]]] = {}
    st_assets: set[str] = set()
    for row in bars:
        asset_id = str(row["asset_id"])
        if row.get("is_st") is True:
            st_assets.add(asset_id)
        if row.get("trade_status") != "1" or row.get("is_st") is True:
            continue
        if not all(isinstance(row.get(field), (int, float)) and math.isfinite(row[field]) for field in _OHLC):
            continue
        grouped.setdefault(asset_id, []).append(row)
    eligible = []
    for row in candidates:
        asset_id = str(row["asset_id"]).strip()
        if not asset_id or _ST_NAME.match(str(row.get("name") or "")):
            continue
        if asset_id in st_assets or len(grouped.get(asset_id, ())) < input_window:
            continue
        eligible.append({str(k): _jsonable(v) for k, v in row.items()})
    eligible.sort(key=lambda row: row["asset_id"])
    return eligible


def select_universe(*, mode: str, count: int, seed: int | None, market: str,
                    asset_ids: Sequence[str] | None, adjust_type: str,
                    input_window: int, cutoff_date: str, service: str) -> UniverseSelection:
    if mode not in {"random", "explicit"}:
        raise ValueError("mode must be random or explicit")
    if count <= 0 or input_window <= 0:
        raise ValueError("count and input_window must be positive")
    if mode == "random" and (asset_ids is not None or seed is None):
        raise ValueError("random mode requires asset_ids=None and a seed")
    normalized = tuple(str(asset_id).strip().lower() for asset_id in asset_ids or ())
    if mode == "explicit" and len(normalized) != count:
        raise ValueError("count must match explicit asset_ids")
    candidates = _eligible_candidates(
        market=market, adjust_type=adjust_type, input_window=input_window,
        cutoff_date=cutoff_date, service=service,
    )
    by_id = {row["asset_id"]: row for row in candidates}
    if mode == "random":
        if count > len(candidates):
            raise ValueError("count exceeds eligible candidate count")
        selected_ids = tuple(random.Random(seed).sample([row["asset_id"] for row in candidates], count))
    else:
        missing = [asset_id for asset_id in normalized if asset_id not in by_id]
        if missing:
            raise ValueError(f"explicit assets are not eligible: {missing}")
        selected_ids = normalized
    selected_rows = tuple(by_id[asset_id] for asset_id in selected_ids)
    filters = {
        "mode": mode, "count": count, "market": market, "adjust_type": adjust_type,
        "input_window": input_window, "cutoff_date": cutoff_date,
    }
    return UniverseSelection(
        asset_ids=selected_ids,
        candidates=tuple(candidates),
        selected_rows=selected_rows,
        candidate_count=len(candidates),
        selection_seed=seed,
        filters=filters,
        candidate_fingerprint=_fingerprint(candidates),
        selection_fingerprint=_fingerprint({"asset_ids": selected_ids, "seed": seed, "filters": filters}),
    )


def load_trade_calendar_dates(adjust_type: str, start_date: str, end_date: str, service: str) -> list[str]:
    calendar_sql = """
        SELECT trade_date
        FROM market.trading_calendar
        WHERE trade_date >= %(start_date)s AND trade_date <= %(end_date)s
          AND exchange IN ('SH', 'SZ', 'BJ') AND is_open = TRUE
        ORDER BY trade_date
    """
    params = {"adjust_type": adjust_type, "start_date": start_date, "end_date": end_date}
    with _db(service) as conn:
        rows = fetch_all(conn, calendar_sql, params)
        if not rows:
            fallback_sql = """
                SELECT DISTINCT trade_date
                FROM market_daily_bar
                WHERE adjust_type = %(adjust_type)s
                  AND trade_date >= %(start_date)s AND trade_date <= %(end_date)s
                ORDER BY trade_date
            """
            rows = fetch_all(conn, fallback_sql, params)
    return sorted({str(row["trade_date"]) for row in rows if row.get("trade_date") is not None})


def write_universe_selection(path: Path, selection: UniverseSelection) -> None:
    payload = _jsonable(asdict(selection))
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
