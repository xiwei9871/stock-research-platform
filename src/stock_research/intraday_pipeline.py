from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Callable
from zoneinfo import ZoneInfo

import pandas as pd

from stock_research.config import SETTINGS
from stock_research.daily_close_pipeline import (
    fetch_akshare_minute5_rows,
    format_trade_date,
    parse_trade_date,
    retry_call,
    ts_code_to_asset_id,
    upsert_minute5_bars,
)
from stock_research.db import connect, execute, execute_many, fetch_all


INTRADAY_SCHEMA_SQL = """
CREATE SCHEMA IF NOT EXISTS ops;

CREATE TABLE IF NOT EXISTS ops.intraday_universe_member (
    run_date date NOT NULL,
    previous_trade_date date,
    ts_code text NOT NULL,
    asset_id text NOT NULL,
    stock_name text NOT NULL DEFAULT '',
    source_types jsonb NOT NULL DEFAULT '[]'::jsonb,
    source_detail text NOT NULL DEFAULT '',
    rank integer,
    score numeric,
    position_quantity numeric,
    position_weight numeric,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (run_date, ts_code)
);

CREATE TABLE IF NOT EXISTS ops.intraday_job (
    run_date date NOT NULL,
    stage text NOT NULL,
    status text NOT NULL,
    started_at timestamptz,
    finished_at timestamptz,
    rows_upserted integer NOT NULL DEFAULT 0,
    failed_symbols jsonb NOT NULL DEFAULT '[]'::jsonb,
    error_summary text,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (run_date, stage)
);

CREATE TABLE IF NOT EXISTS ops.market_sentiment_snapshot (
    trade_date date NOT NULL,
    snapshot_time timestamptz NOT NULL,
    source text NOT NULL,
    up_count integer NOT NULL DEFAULT 0,
    down_count integer NOT NULL DEFAULT 0,
    flat_count integer NOT NULL DEFAULT 0,
    limit_up_count integer NOT NULL DEFAULT 0,
    limit_down_count integer NOT NULL DEFAULT 0,
    break_limit_count integer NOT NULL DEFAULT 0,
    total_count integer NOT NULL DEFAULT 0,
    sentiment_score numeric,
    sentiment_state text NOT NULL,
    raw_summary jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (trade_date, snapshot_time, source)
);
"""


@dataclass(frozen=True)
class IntradayConfig:
    service: str = SETTINGS.research_service
    timezone: str = "Asia/Shanghai"
    top_n: int = 20
    score_version: str = "approved_v1"
    watchlist_id: str = "default"
    portfolio_id: str | None = None
    max_workers: int = 8
    request_timeout_seconds: int = 15
    max_retries: int = 3

    @classmethod
    def from_env(cls) -> "IntradayConfig":
        return cls(
            service=os.getenv("DB_SERVICE", SETTINGS.research_service),
            timezone=os.getenv("PIPELINE_TIMEZONE", "Asia/Shanghai"),
            top_n=int(os.getenv("INTRADAY_TOP_N", "20")),
            score_version=os.getenv("INTRADAY_SCORE_VERSION", "approved_v1"),
            watchlist_id=os.getenv("INTRADAY_WATCHLIST_ID", "default"),
            portfolio_id=os.getenv("INTRADAY_PORTFOLIO_ID") or None,
            max_workers=int(os.getenv("INTRADAY_MAX_WORKERS", "8")),
            request_timeout_seconds=int(os.getenv("REQUEST_TIMEOUT_SECONDS", "15")),
            max_retries=int(os.getenv("MAX_RETRIES", "3")),
        )


def apply_intraday_schema(service: str = SETTINGS.research_service) -> None:
    with connect(service) as conn:
        execute(conn, INTRADAY_SCHEMA_SQL)


def asset_id_to_ts_code(asset_id: str) -> str:
    parts = asset_id.split(":")
    if len(parts) == 3:
        return f"{parts[2]}.{parts[1]}"
    raise ValueError(f"unsupported asset_id: {asset_id}")


def normalize_ts_code(value: str, asset_id: str | None = None) -> str:
    text = str(value or "").strip().upper()
    if "." in text:
        symbol, exchange = text.split(".", 1)
        return f"{symbol}.{exchange}"
    if asset_id:
        return asset_id_to_ts_code(asset_id)
    if len(text) == 6 and text[0] in {"0", "1", "2", "3"}:
        return f"{text}.SZ"
    if len(text) == 6 and text[0] in {"4", "8"}:
        return f"{text}.BJ"
    return f"{text}.SH"


def previous_open_trade_date(service: str, run_date: date) -> date | None:
    sql = """
    SELECT trade_date
    FROM market.trading_calendar
    WHERE trade_date < %s AND is_open = true
      AND exchange IN ('SH', 'SZ', 'BJ')
    GROUP BY trade_date
    ORDER BY trade_date DESC
    LIMIT 1
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, [run_date])
    if rows:
        return rows[0]["trade_date"]
    return None


def latest_available_previous_date(service: str, run_date: date) -> date:
    calendar_date = previous_open_trade_date(service, run_date)
    if calendar_date:
        return calendar_date
    sql = """
    SELECT max(trade_date) AS trade_date
    FROM (
        SELECT trade_date FROM selection_result WHERE trade_date < %s
        UNION ALL
        SELECT trade_date FROM factor.stock_score_daily WHERE trade_date < %s
        UNION ALL
        SELECT trade_date FROM watchlist.watchlist_daily_signal WHERE trade_date < %s
    ) d
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, [run_date, run_date, run_date])
    value = rows[0].get("trade_date") if rows else None
    return value or (run_date - timedelta(days=1))


def load_previous_topn(
    *,
    service: str,
    previous_trade_date: date,
    top_n: int,
    score_version: str,
) -> list[dict[str, Any]]:
    factor_sql = """
    SELECT s.asset_id, a.name AS stock_name, s.rank, s.score_total AS score
    FROM factor.stock_score_daily s
    LEFT JOIN asset_master a ON a.asset_id = s.asset_id
    WHERE s.trade_date = %s AND s.score_version = %s
    ORDER BY s.rank, s.asset_id
    LIMIT %s
    """
    selection_sql = """
    SELECT s.asset_id, a.name AS stock_name, s.rank, s.score
    FROM selection_result s
    LEFT JOIN asset_master a ON a.asset_id = s.asset_id
    WHERE s.trade_date = %s
    ORDER BY s.rank, s.asset_id
    LIMIT %s
    """
    with connect(service) as conn:
        rows = fetch_all(conn, factor_sql, [previous_trade_date, score_version, top_n])
        if not rows:
            rows = fetch_all(conn, selection_sql, [previous_trade_date, top_n])
    return [
        {
            "asset_id": str(row["asset_id"]),
            "ts_code": asset_id_to_ts_code(str(row["asset_id"])),
            "stock_name": str(row.get("stock_name") or ""),
            "rank": int(row["rank"]) if row.get("rank") is not None else None,
            "score": float(row["score"]) if row.get("score") is not None else None,
            "source_type": "previous_topn",
        }
        for row in rows
    ]


def load_current_positions(
    *,
    service: str,
    run_date: date,
    portfolio_id: str | None = None,
) -> list[dict[str, Any]]:
    portfolio_filter = "AND portfolio_id = %s" if portfolio_id else ""
    params: list[Any] = [run_date]
    if portfolio_id:
        params.append(portfolio_id)
    sql = f"""
    WITH latest_date AS (
        SELECT max(trade_date) AS trade_date
        FROM simulation.virtual_portfolio_position_daily
        WHERE trade_date <= %s
        {portfolio_filter}
    )
    SELECT p.asset_id, p.stock_code, p.stock_name, p.quantity, p.weight, p.portfolio_id
    FROM simulation.virtual_portfolio_position_daily p
    JOIN latest_date d ON d.trade_date = p.trade_date
    WHERE (coalesce(p.quantity, 0) > 0 OR coalesce(p.market_value, 0) > 0)
    {portfolio_filter}
    ORDER BY p.portfolio_id, p.stock_code
    """
    query_params = [*params, *( [portfolio_id] if portfolio_id else [] )]
    with connect(service) as conn:
        rows = fetch_all(conn, sql, query_params)
    result = []
    for row in rows:
        asset_id = str(row.get("asset_id") or "")
        ts_code = normalize_ts_code(str(row["stock_code"]), asset_id or None)
        result.append(
            {
                "asset_id": asset_id or ts_code_to_asset_id(ts_code),
                "ts_code": ts_code,
                "stock_name": str(row.get("stock_name") or ""),
                "position_quantity": float(row["quantity"]) if row.get("quantity") is not None else None,
                "position_weight": float(row["weight"]) if row.get("weight") is not None else None,
                "source_type": "current_position",
                "source_detail": str(row.get("portfolio_id") or ""),
            }
        )
    return result


def load_previous_watchlist(
    *,
    service: str,
    previous_trade_date: date,
    watchlist_id: str,
) -> list[dict[str, Any]]:
    sql = """
    SELECT asset_id, stock_code, stock_name, watchlist_id, priority, signal_score
    FROM watchlist.watchlist_daily_signal
    WHERE trade_date = %s
      AND (%s = '' OR watchlist_id = %s)
    ORDER BY must_watch DESC, priority ASC, signal_score DESC NULLS LAST, asset_id
    """
    selected_watchlist_id = watchlist_id or ""
    with connect(service) as conn:
        rows = fetch_all(conn, sql, [previous_trade_date, selected_watchlist_id, selected_watchlist_id])
    return [
        {
            "asset_id": str(row["asset_id"]),
            "ts_code": normalize_ts_code(str(row["stock_code"]), str(row["asset_id"])),
            "stock_name": str(row.get("stock_name") or ""),
            "rank": int(row["priority"]) if row.get("priority") is not None else None,
            "score": float(row["signal_score"]) if row.get("signal_score") is not None else None,
            "source_type": "previous_watchlist",
            "source_detail": str(row.get("watchlist_id") or ""),
        }
        for row in rows
    ]


def merge_universe_rows(
    rows: list[dict[str, Any]],
    *,
    run_date: date,
    previous_trade_date: date,
) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for row in rows:
        ts_code = normalize_ts_code(str(row["ts_code"]), row.get("asset_id"))
        item = merged.setdefault(
            ts_code,
            {
                "run_date": run_date,
                "previous_trade_date": previous_trade_date,
                "ts_code": ts_code,
                "asset_id": row.get("asset_id") or ts_code_to_asset_id(ts_code),
                "stock_name": row.get("stock_name") or "",
                "source_types": [],
                "source_detail": "",
                "rank": None,
                "score": None,
                "position_quantity": None,
                "position_weight": None,
                "metadata": {},
            },
        )
        source_type = str(row.get("source_type") or "unknown")
        if source_type not in item["source_types"]:
            item["source_types"].append(source_type)
        source_detail = str(row.get("source_detail") or "")
        if source_detail and source_detail not in item["source_detail"].split(","):
            item["source_detail"] = ",".join(
                [value for value in [item["source_detail"], source_detail] if value]
            )
        for field in ["stock_name", "rank", "score", "position_quantity", "position_weight"]:
            if item.get(field) in (None, "") and row.get(field) not in (None, ""):
                item[field] = row[field]
    return sorted(merged.values(), key=lambda row: (min(row["rank"] or 999999, 999999), row["ts_code"]))


def upsert_intraday_universe(service: str, rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    sql = """
    INSERT INTO ops.intraday_universe_member (
        run_date, previous_trade_date, ts_code, asset_id, stock_name, source_types,
        source_detail, rank, score, position_quantity, position_weight, metadata
    )
    VALUES (
        %(run_date)s, %(previous_trade_date)s, %(ts_code)s, %(asset_id)s, %(stock_name)s,
        %(source_types)s::jsonb, %(source_detail)s, %(rank)s, %(score)s,
        %(position_quantity)s, %(position_weight)s, %(metadata)s::jsonb
    )
    ON CONFLICT (run_date, ts_code) DO UPDATE SET
        previous_trade_date = EXCLUDED.previous_trade_date,
        asset_id = EXCLUDED.asset_id,
        stock_name = EXCLUDED.stock_name,
        source_types = EXCLUDED.source_types,
        source_detail = EXCLUDED.source_detail,
        rank = EXCLUDED.rank,
        score = EXCLUDED.score,
        position_quantity = EXCLUDED.position_quantity,
        position_weight = EXCLUDED.position_weight,
        metadata = EXCLUDED.metadata,
        updated_at = now()
    """
    payload = []
    for row in rows:
        item = dict(row)
        item["source_types"] = json.dumps(item.get("source_types") or [], ensure_ascii=False)
        item["metadata"] = json.dumps(item.get("metadata") or {}, ensure_ascii=False)
        payload.append(item)
    with connect(service) as conn:
        execute_many(conn, sql, payload)
    return len(rows)


def record_intraday_job(
    *,
    service: str,
    run_date: date,
    stage: str,
    status: str,
    started_at: datetime | None = None,
    finished_at: datetime | None = None,
    rows_upserted: int = 0,
    failed_symbols: list[str] | None = None,
    error_summary: str | None = None,
) -> None:
    sql = """
    INSERT INTO ops.intraday_job (
        run_date, stage, status, started_at, finished_at, rows_upserted,
        failed_symbols, error_summary
    )
    VALUES (
        %(run_date)s, %(stage)s, %(status)s, %(started_at)s, %(finished_at)s,
        %(rows_upserted)s, %(failed_symbols)s::jsonb, %(error_summary)s
    )
    ON CONFLICT (run_date, stage) DO UPDATE SET
        status = EXCLUDED.status,
        started_at = EXCLUDED.started_at,
        finished_at = EXCLUDED.finished_at,
        rows_upserted = EXCLUDED.rows_upserted,
        failed_symbols = EXCLUDED.failed_symbols,
        error_summary = EXCLUDED.error_summary,
        updated_at = now()
    """
    with connect(service) as conn:
        execute(
            conn,
            sql,
            {
                "run_date": run_date,
                "stage": stage,
                "status": status,
                "started_at": started_at,
                "finished_at": finished_at,
                "rows_upserted": rows_upserted,
                "failed_symbols": json.dumps(failed_symbols or [], ensure_ascii=False),
                "error_summary": error_summary,
            },
        )


def build_intraday_universe(
    *,
    run_date: date,
    previous_trade_date: date | None,
    config: IntradayConfig,
    upserter: Callable[[str, list[dict[str, Any]]], int] = upsert_intraday_universe,
) -> list[dict[str, Any]]:
    started = datetime.now(ZoneInfo(config.timezone))
    previous_date = previous_trade_date or latest_available_previous_date(config.service, run_date)
    rows = [
        *load_previous_topn(
            service=config.service,
            previous_trade_date=previous_date,
            top_n=config.top_n,
            score_version=config.score_version,
        ),
        *load_previous_watchlist(
            service=config.service,
            previous_trade_date=previous_date,
            watchlist_id=config.watchlist_id,
        ),
        *load_current_positions(
            service=config.service,
            run_date=run_date,
            portfolio_id=config.portfolio_id,
        ),
    ]
    merged = merge_universe_rows(rows, run_date=run_date, previous_trade_date=previous_date)
    count = upserter(config.service, merged)
    record_intraday_job(
        service=config.service,
        run_date=run_date,
        stage="universe",
        status="success",
        started_at=started,
        finished_at=datetime.now(ZoneInfo(config.timezone)),
        rows_upserted=count,
    )
    return merged


def load_intraday_universe_symbols(service: str, run_date: date) -> list[str]:
    sql = """
    SELECT ts_code
    FROM ops.intraday_universe_member
    WHERE run_date = %s
    ORDER BY ts_code
    """
    with connect(service) as conn:
        return [str(row["ts_code"]) for row in fetch_all(conn, sql, [run_date])]


def poll_universe_minute5(
    *,
    run_date: date,
    config: IntradayConfig,
    fetcher: Callable[..., list[dict[str, Any]]] = fetch_akshare_minute5_rows,
    upserter: Callable[[str, list[dict[str, Any]]], int] = upsert_minute5_bars,
) -> dict[str, Any]:
    started = datetime.now(ZoneInfo(config.timezone))
    ts_codes = load_intraday_universe_symbols(config.service, run_date)
    failures: dict[str, str] = {}
    rows_by_symbol: dict[str, list[dict[str, Any]]] = {}

    def _one(ts_code: str) -> tuple[str, list[dict[str, Any]], str | None]:
        rows, _attempts, error = retry_call(
            lambda: fetcher(
                ts_code,
                start_date=run_date,
                end_date=run_date,
                timeout_seconds=config.request_timeout_seconds,
            ),
            max_retries=config.max_retries,
        )
        return ts_code, rows, error

    with concurrent.futures.ThreadPoolExecutor(max_workers=config.max_workers) as executor:
        for ts_code, rows, error in executor.map(_one, ts_codes):
            if error:
                failures[ts_code] = error
            else:
                rows_by_symbol[ts_code] = rows
    all_rows = [row for rows in rows_by_symbol.values() for row in rows]
    rows_upserted = upserter(config.service, all_rows)
    status = "success" if not failures else ("partial_success" if rows_upserted else "failed")
    record_intraday_job(
        service=config.service,
        run_date=run_date,
        stage="minute5",
        status=status,
        started_at=started,
        finished_at=datetime.now(ZoneInfo(config.timezone)),
        rows_upserted=rows_upserted,
        failed_symbols=sorted(failures),
        error_summary="; ".join(f"{code}:{err}" for code, err in list(failures.items())[:5]) or None,
    )
    return {
        "stage": "minute5",
        "status": status,
        "symbols": len(ts_codes),
        "rows": rows_upserted,
        "failed_symbols": sorted(failures),
    }


def _safe_len(func: Callable[..., Any], *args: Any, **kwargs: Any) -> int:
    try:
        frame = func(*args, **kwargs)
    except Exception:
        return 0
    return 0 if frame is None else len(frame)


def _safe_pool_len(ak_module: Any, function_name: str, *, date_text: str) -> int:
    func = getattr(ak_module, function_name, None)
    if func is None:
        return 0
    return _safe_len(func, date=date_text)


def classify_sentiment(
    *,
    up_count: int,
    down_count: int,
    limit_up_count: int,
    limit_down_count: int,
    break_limit_count: int,
) -> tuple[float, str]:
    breadth = (up_count + 1.0) / (down_count + 1.0)
    limit_ratio = (limit_up_count + 1.0) / (limit_down_count + 1.0)
    break_penalty = break_limit_count / max(limit_up_count + break_limit_count, 1)
    score = breadth * 35.0 + limit_ratio * 35.0 + limit_up_count * 0.5 - break_penalty * 30.0
    if score >= 120:
        state = "HOT"
    elif score >= 75:
        state = "WARM"
    elif score >= 45:
        state = "NEUTRAL"
    elif score >= 25:
        state = "WEAK"
    else:
        state = "PANIC"
    return round(score, 4), state


def upsert_market_sentiment(service: str, row: dict[str, Any]) -> int:
    sql = """
    INSERT INTO ops.market_sentiment_snapshot (
        trade_date, snapshot_time, source, up_count, down_count, flat_count,
        limit_up_count, limit_down_count, break_limit_count, total_count,
        sentiment_score, sentiment_state, raw_summary
    )
    VALUES (
        %(trade_date)s, %(snapshot_time)s, %(source)s, %(up_count)s, %(down_count)s,
        %(flat_count)s, %(limit_up_count)s, %(limit_down_count)s, %(break_limit_count)s,
        %(total_count)s, %(sentiment_score)s, %(sentiment_state)s, %(raw_summary)s::jsonb
    )
    ON CONFLICT (trade_date, snapshot_time, source) DO UPDATE SET
        up_count = EXCLUDED.up_count,
        down_count = EXCLUDED.down_count,
        flat_count = EXCLUDED.flat_count,
        limit_up_count = EXCLUDED.limit_up_count,
        limit_down_count = EXCLUDED.limit_down_count,
        break_limit_count = EXCLUDED.break_limit_count,
        total_count = EXCLUDED.total_count,
        sentiment_score = EXCLUDED.sentiment_score,
        sentiment_state = EXCLUDED.sentiment_state,
        raw_summary = EXCLUDED.raw_summary
    """
    payload = dict(row)
    payload["raw_summary"] = json.dumps(payload.get("raw_summary") or {}, ensure_ascii=False)
    with connect(service) as conn:
        execute(conn, sql, payload)
    return 1


def collect_market_sentiment(
    *,
    run_date: date,
    config: IntradayConfig,
    ak_module: Any | None = None,
    upserter: Callable[[str, dict[str, Any]], int] = upsert_market_sentiment,
) -> dict[str, Any]:
    started = datetime.now(ZoneInfo(config.timezone))
    if ak_module is None:
        import akshare as ak_module

    spot_rows, attempts, error = retry_call(
        lambda: [ak_module.stock_zh_a_spot_em()],
        max_retries=config.max_retries,
    )
    if error or not spot_rows:
        record_intraday_job(
            service=config.service,
            run_date=run_date,
            stage="sentiment",
            status="failed",
            started_at=started,
            finished_at=datetime.now(ZoneInfo(config.timezone)),
            rows_upserted=0,
            error_summary=error or "empty spot snapshot",
        )
        return {
            "stage": "sentiment",
            "status": "failed",
            "attempt_count": attempts,
            "error_summary": error or "empty spot snapshot",
        }
    spot = spot_rows[0]
    pct = spot["涨跌幅"] if "涨跌幅" in spot.columns else spot.get("pct_chg")
    pct_numeric = pd.to_numeric(pct, errors="coerce").fillna(0)
    up_count = int((pct_numeric > 0).sum())
    down_count = int((pct_numeric < 0).sum())
    flat_count = int((pct_numeric == 0).sum())
    trade_date_text = format_trade_date(run_date)
    limit_up_count = _safe_pool_len(ak_module, "stock_zt_pool_em", date_text=trade_date_text)
    limit_down_count = _safe_pool_len(
        ak_module, "stock_zt_pool_dtgc_em", date_text=trade_date_text
    )
    break_limit_count = _safe_pool_len(
        ak_module, "stock_zt_pool_zbgc_em", date_text=trade_date_text
    )
    score, state = classify_sentiment(
        up_count=up_count,
        down_count=down_count,
        limit_up_count=limit_up_count,
        limit_down_count=limit_down_count,
        break_limit_count=break_limit_count,
    )
    row = {
        "trade_date": run_date,
        "snapshot_time": started,
        "source": "akshare_em",
        "up_count": up_count,
        "down_count": down_count,
        "flat_count": flat_count,
        "limit_up_count": limit_up_count,
        "limit_down_count": limit_down_count,
        "break_limit_count": break_limit_count,
        "total_count": int(len(spot)),
        "sentiment_score": score,
        "sentiment_state": state,
        "raw_summary": {
            "spot_rows": int(len(spot)),
            "source": "akshare",
        },
    }
    upserter(config.service, row)
    record_intraday_job(
        service=config.service,
        run_date=run_date,
        stage="sentiment",
        status="success",
        started_at=started,
        finished_at=datetime.now(ZoneInfo(config.timezone)),
        rows_upserted=1,
    )
    return row


def load_intraday_status(service: str, run_date: date) -> dict[str, Any]:
    sql_jobs = """
    SELECT stage, status, rows_upserted, failed_symbols, error_summary, updated_at
    FROM ops.intraday_job
    WHERE run_date = %s
    ORDER BY stage
    """
    sql_universe = """
    SELECT ts_code, asset_id, stock_name, source_types, rank, score, position_quantity, position_weight
    FROM ops.intraday_universe_member
    WHERE run_date = %s
    ORDER BY coalesce(rank, 999999), ts_code
    """
    sql_sentiment = """
    SELECT trade_date, snapshot_time, up_count, down_count, flat_count,
           limit_up_count, limit_down_count, break_limit_count,
           sentiment_score, sentiment_state
    FROM ops.market_sentiment_snapshot
    WHERE trade_date = %s
    ORDER BY snapshot_time DESC
    LIMIT 1
    """
    with connect(service) as conn:
        jobs = fetch_all(conn, sql_jobs, [run_date])
        universe = fetch_all(conn, sql_universe, [run_date])
        sentiment = fetch_all(conn, sql_sentiment, [run_date])
    return {
        "run_date": run_date.isoformat(),
        "jobs": jobs,
        "universe_count": len(universe),
        "universe": universe,
        "market_sentiment": sentiment[0] if sentiment else None,
    }


def run_intraday_stage(
    stage: str,
    *,
    run_date: date,
    previous_trade_date: date | None,
    config: IntradayConfig,
) -> dict[str, Any] | list[dict[str, Any]]:
    apply_intraday_schema(config.service)
    if stage == "universe":
        return build_intraday_universe(
            run_date=run_date,
            previous_trade_date=previous_trade_date,
            config=config,
        )
    if stage == "minute5":
        return poll_universe_minute5(run_date=run_date, config=config)
    if stage == "sentiment":
        return collect_market_sentiment(run_date=run_date, config=config)
    if stage == "status":
        return load_intraday_status(config.service, run_date)
    if stage == "all":
        return {
            "universe": build_intraday_universe(
                run_date=run_date,
                previous_trade_date=previous_trade_date,
                config=config,
            ),
            "minute5": poll_universe_minute5(run_date=run_date, config=config),
            "sentiment": collect_market_sentiment(run_date=run_date, config=config),
        }
    raise ValueError(f"unsupported stage: {stage}")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m scripts.intraday_signal_pipeline")
    parser.add_argument("--date")
    parser.add_argument("--previous-date")
    parser.add_argument(
        "--stage",
        choices=["all", "universe", "minute5", "sentiment", "status"],
        default="all",
    )
    parser.add_argument("--top-n", type=int)
    parser.add_argument("--score-version")
    parser.add_argument("--watchlist-id")
    parser.add_argument("--portfolio-id")
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_arg_parser().parse_args(argv)
    config = IntradayConfig.from_env()
    config = IntradayConfig(
        **{
            **config.__dict__,
            **{key: value for key, value in {
                "top_n": args.top_n,
                "score_version": args.score_version,
                "watchlist_id": args.watchlist_id,
                "portfolio_id": args.portfolio_id,
            }.items() if value is not None},
        }
    )
    run_date = parse_trade_date(args.date, config.timezone)
    previous_date = parse_trade_date(args.previous_date, config.timezone) if args.previous_date else None
    result = run_intraday_stage(
        args.stage,
        run_date=run_date,
        previous_trade_date=previous_date,
        config=config,
    )
    print(json.dumps(result, ensure_ascii=False, default=str, indent=2))


if __name__ == "__main__":
    main()
