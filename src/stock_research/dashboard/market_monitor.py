from __future__ import annotations

import math
from collections.abc import Mapping
from datetime import date, timedelta
from decimal import Decimal
from functools import lru_cache
from typing import Any

from stock_research.config import SETTINGS
from stock_research.dashboard.platform import load_platform_summary
from stock_research.dashboard.reports import load_report_links
from stock_research.dashboard.scores import load_top_scores_for_dashboard
from stock_research.db import connect, fetch_all
from stock_research.market_emotion_state_v1 import (
    build_market_emotion_state_from_frames,
    load_market_emotion_source_frames,
)


_MISSING_TABLE_SQLSTATES = {"3F000", "42P01"}


def _sqlstate(exc: Exception) -> str | None:
    return getattr(exc, "sqlstate", None) or getattr(
        getattr(exc, "diag", None),
        "sqlstate",
        None,
    )


def _is_missing_optional_source(exc: Exception) -> bool:
    return _sqlstate(exc) in _MISSING_TABLE_SQLSTATES


def _number(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, Decimal):
        if not value.is_finite():
            return None
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


def load_market_emotion_row(
    trade_date: str,
    service: str = SETTINGS.research_service,
) -> dict[str, Any] | None:
    if not trade_date:
        return None
    sql = """
        SELECT *
        FROM research.market_emotion_state_daily
        WHERE trade_date = %s
        ORDER BY trade_date DESC
        LIMIT 1
    """
    try:
        with connect(service) as conn:
            rows = fetch_all(conn, sql, [trade_date])
    except Exception as exc:
        if _is_missing_optional_source(exc):
            return compute_market_emotion_row(trade_date, service=service)
        raise
    return dict(rows[0]) if rows else compute_market_emotion_row(trade_date, service=service)


def compute_market_emotion_row(
    trade_date: str,
    *,
    service: str = SETTINGS.research_service,
    lookback_days: int = 120,
) -> dict[str, Any] | None:
    row = _compute_market_emotion_row_cached(str(trade_date), service, int(lookback_days))
    return dict(row) if row else None


@lru_cache(maxsize=64)
def _compute_market_emotion_row_cached(
    trade_date: str,
    service: str,
    lookback_days: int,
) -> tuple[tuple[str, Any], ...] | None:
    try:
        end_date = date.fromisoformat(str(trade_date))
    except ValueError:
        return None
    start_date = end_date - timedelta(days=lookback_days)
    bars, status = load_market_emotion_source_frames(
        start_date.isoformat(),
        end_date.isoformat(),
        service=service,
    )
    daily = build_market_emotion_state_from_frames(bars, status)
    if daily.empty:
        return None
    selected = daily[daily["trade_date"].astype(str).eq(end_date.isoformat())]
    if selected.empty:
        selected = daily[daily["trade_date"].astype(str).le(end_date.isoformat())].tail(1)
    if selected.empty:
        return None
    row = dict(selected.iloc[0].to_dict())
    return tuple(row.items())


def build_market_emotion_payload(row: Mapping[str, Any] | None) -> dict[str, Any]:
    if not row:
        return {
            "summary": {
                "score": None,
                "state": "unavailable",
                "risk_state": "unknown",
                "style_signal_hint": "",
                "position_budget_hint": "",
                "status": "pending_source",
            },
            "components": [],
            "breadth": {"status": "pending_source"},
            "liquidity": {"status": "pending_source"},
            "limit_performance": {"status": "pending_source"},
            "profit_effect": {"status": "pending_source"},
            "drawdown_pressure": {"status": "pending_source"},
            "weight_performance": {"status": "pending_source"},
        }
    return {
        "summary": {
            "score": _number(row.get("emotion_score")),
            "state": str(row.get("emotion_state") or "unknown"),
            "risk_state": str(row.get("risk_state") or "unknown"),
            "style_signal_hint": str(row.get("style_signal_hint") or ""),
            "position_budget_hint": str(row.get("position_budget_hint") or ""),
            "status": "available",
        },
        "components": [
            {"key": "breadth", "label": "涨跌家数", "score": _number(row.get("breadth_score"))},
            {"key": "limit", "label": "涨停表现", "score": _number(row.get("limit_score"))},
            {"key": "relay", "label": "连板接力", "score": _number(row.get("relay_score"))},
            {"key": "feedback", "label": "赚钱效应", "score": _number(row.get("feedback_score"))},
            {"key": "liquidity", "label": "市场量能", "score": _number(row.get("liquidity_score"))},
        ],
        "breadth": {
            "traded_count": _number(row.get("traded_count")),
            "up_count": _number(row.get("up_count")),
            "down_count": _number(row.get("down_count")),
            "strong_up_count": _number(row.get("strong_up_count")),
            "strong_down_count": _number(row.get("strong_down_count")),
            "status": "available",
        },
        "liquidity": {
            "total_amount": _number(row.get("total_amount")),
            "amount_ratio_5_20": _number(row.get("amount_ratio_5_20")),
            "status": "available",
        },
        "limit_performance": {
            "limit_up_count": _number(row.get("limit_up_count")),
            "limit_down_count": _number(row.get("limit_down_count")),
            "broken_limit_up_count": _number(row.get("broken_limit_up_count")),
            "broken_limit_up_rate": _number(row.get("broken_limit_up_rate")),
            "first_board_count": _number(row.get("first_board_count")),
            "second_board_count": _number(row.get("second_board_count")),
            "third_board_plus_count": _number(row.get("third_board_plus_count")),
            "high_board_height": _number(row.get("high_board_height")),
            "status": "available",
        },
        "profit_effect": {
            "limit_up_success_rate": _number(row.get("yesterday_limit_up_red_rate")),
            "limit_up_profit_rate": _number(row.get("yesterday_limit_up_avg_return")),
            "limit_up_limit_down_rate": _number(row.get("yesterday_limit_up_limit_down_rate")),
            "relay_profit_rate": _number(row.get("yesterday_relay_avg_return")),
            "relay_success_rate": _number(row.get("yesterday_relay_red_rate")),
            "relay_continue_rate": _number(row.get("yesterday_relay_continue_rate")),
            "broken_profit_rate": _number(row.get("yesterday_broken_avg_return")),
            "broken_success_rate": _number(row.get("yesterday_broken_red_rate")),
            "broken_limit_down_rate": _number(row.get("yesterday_broken_limit_down_rate")),
            "status": "available",
        },
        "drawdown_pressure": {
            "strong_down_count": _number(row.get("strong_down_count")),
            "limit_down_count": _number(row.get("limit_down_count")),
            "broken_limit_up_rate": _number(row.get("broken_limit_up_rate")),
            "yesterday_limit_up_limit_down_rate": _number(
                row.get("yesterday_limit_up_limit_down_rate")
            ),
            "status": "available",
        },
        "weight_performance": {"status": "pending_source"},
    }


def load_emotion_stock_lists(trade_date: str, *, limit: int = 30) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {
        "auction": [],
        "limit_up": [],
        "broken_limit_up": [],
        "limit_down": [],
    }
    if not trade_date:
        return result

    sql = """
        SELECT
            b.asset_id,
            COALESCE(a.symbol, b.asset_id) AS symbol,
            COALESCE(a.name, b.asset_id) AS name,
            b.amount,
            b.pct_chg,
            COALESCE(a.board, '') AS board,
            s.is_limit_up,
            s.is_limit_down,
            (
                b.high >= s.limit_up_price * 0.999
                AND NOT COALESCE(s.is_limit_up, false)
            ) AS is_broken_limit_up
        FROM market_daily_bar b
        JOIN core.asset_status_daily s
          ON s.trade_date = b.trade_date
         AND s.asset_id = b.asset_id
        LEFT JOIN core.asset_master a
          ON a.asset_id = b.asset_id
        WHERE b.trade_date = %s
          AND b.adjust_type = 'hfq'
          AND s.is_trade
          AND NOT s.is_suspended
          AND NOT s.is_st
          AND (
                COALESCE(s.is_limit_up, false)
                OR COALESCE(s.is_limit_down, false)
                OR (
                    b.high >= s.limit_up_price * 0.999
                    AND NOT COALESCE(s.is_limit_up, false)
                )
          )
        ORDER BY b.amount DESC NULLS LAST
    """
    with connect(SETTINGS.research_service) as conn:
        rows = fetch_all(conn, sql, [trade_date])

    per_list_limit = max(0, int(limit))
    for raw_row in rows:
        row = dict(raw_row)
        if row.get("is_limit_up") and len(result["limit_up"]) < per_list_limit:
            result["limit_up"].append(_emotion_stock_row(row, "limit_up"))
        if row.get("is_broken_limit_up") and len(result["broken_limit_up"]) < per_list_limit:
            result["broken_limit_up"].append(_emotion_stock_row(row, "broken_limit_up"))
        if row.get("is_limit_down") and len(result["limit_down"]) < per_list_limit:
            result["limit_down"].append(_emotion_stock_row(row, "limit_down"))
    return result


def _emotion_stock_row(row: Mapping[str, Any], tab: str) -> dict[str, Any]:
    asset_id = str(row.get("asset_id") or "")
    return {
        "tab": tab,
        "asset_id": asset_id,
        "symbol": str(row.get("symbol") or asset_id),
        "name": str(row.get("name") or asset_id),
        "amount": _number(row.get("amount")),
        "pct_chg": _number(row.get("pct_chg")),
        "board": str(row.get("board") or ""),
        "limit_up_streak": None,
    }


def _empty_emotion_stock_lists() -> dict[str, Any]:
    return {
        "auction": [],
        "limit_up": [],
        "broken_limit_up": [],
        "limit_down": [],
        "auction_status": "pending_source",
    }


def _market_breadth_from_emotion(emotion_payload: Mapping[str, Any]) -> dict[str, Any]:
    breadth = dict(emotion_payload.get("breadth") or {})
    limit_performance = dict(emotion_payload.get("limit_performance") or {})
    if breadth.get("status") != "available":
        return {
            "advancers": None,
            "decliners": None,
            "limit_up": None,
            "limit_down": None,
            "advancing_ratio": None,
            "turnover_change_pct": None,
            "status": "pending_source",
        }
    up_count = breadth.get("up_count")
    traded_count = breadth.get("traded_count")
    advancing_ratio = up_count / traded_count if up_count is not None and traded_count else None
    return {
        "advancers": up_count,
        "decliners": breadth.get("down_count"),
        "limit_up": limit_performance.get("limit_up_count"),
        "limit_down": limit_performance.get("limit_down_count"),
        "advancing_ratio": advancing_ratio,
        "turnover_change_pct": None,
        "status": breadth.get("status", "pending_source"),
    }


def build_market_monitor_eod(
    *,
    trade_date: str | None = None,
    score_version: str = "manual_v1",
    top_n: int = 5,
) -> dict[str, Any]:
    summary = load_platform_summary(score_version=score_version, top_n=top_n)
    latest_market_date = str(summary.get("latest_market_date") or "")
    latest_factor_date = str(summary.get("latest_factor_date") or "")
    latest_score_date = str(summary.get("latest_score_date") or "")
    explicit_trade_date = bool(trade_date)
    selected_trade_date = trade_date or latest_market_date
    warnings: list[str] = []
    if not latest_market_date:
        warnings.append("latest complete market date is unavailable")
    if (
        not explicit_trade_date
        and latest_score_date
        and selected_trade_date
        and latest_score_date != selected_trade_date
    ):
        warnings.append(
            f"latest score date {latest_score_date} differs from "
            f"market monitor trade date {selected_trade_date}"
        )
    if (
        not explicit_trade_date
        and latest_factor_date
        and selected_trade_date
        and latest_factor_date != selected_trade_date
    ):
        warnings.append(
            f"latest factor date {latest_factor_date} differs from "
            f"market monitor trade date {selected_trade_date}"
        )

    topn_preview = (
        load_top_scores_for_dashboard(selected_trade_date, score_version, top_n)
        if explicit_trade_date and selected_trade_date
        else list(summary.get("topn_preview") or [])
    )
    reports = load_report_links(selected_trade_date) if selected_trade_date else []
    emotion_row = load_market_emotion_row(selected_trade_date) if selected_trade_date else None
    emotion_payload = build_market_emotion_payload(emotion_row)
    emotion_stock_lists = _empty_emotion_stock_lists()
    try:
        emotion_stock_lists.update(load_emotion_stock_lists(selected_trade_date))
    except Exception as exc:
        if not _is_missing_optional_source(exc):
            raise
    for key in ("auction", "limit_up", "broken_limit_up", "limit_down"):
        emotion_stock_lists.setdefault(key, [])
    emotion_stock_lists["auction_status"] = "pending_source"

    return {
        "trade_date": selected_trade_date,
        "freshness": {
            "mode": "eod",
            "label": "Historical EOD" if explicit_trade_date else "Last Completed Trading Day",
            "is_realtime": False,
            "latest_market_date": latest_market_date,
            "latest_factor_date": latest_factor_date,
            "latest_score_date": latest_score_date,
        },
        "coverage": {
            "market_assets": int(summary.get("market_asset_count") or 0),
            "score_assets": int(summary.get("score_asset_count") or 0),
            "factor_count": int(summary.get("factor_count") or 0),
        },
        "market_breadth": _market_breadth_from_emotion(emotion_payload),
        "market_emotion": emotion_payload,
        "emotion_stock_lists": emotion_stock_lists,
        "index_snapshot": [],
        "sector_strength": {"strongest": [], "weakest": [], "status": "pending_source"},
        "unusual_moves": [],
        "watchlist_alerts": [],
        "strategy_signal_summary": {
            "topn_preview_count": len(topn_preview),
            "topn_preview": topn_preview,
            "risk_filter_counts": {},
        },
        "generated_reports": reports[:8],
        "warnings": warnings,
    }
