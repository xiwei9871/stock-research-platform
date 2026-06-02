from __future__ import annotations

import json
import math
from typing import Any

from psycopg import errors as psycopg_errors

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all


def load_shadow_outcomes_summary(
    start_date: str,
    end_date: str,
    outcome_status: str | None = None,
    limit: int = 20,
    service: str = SETTINGS.research_service,
) -> list[dict[str, Any]]:
    params: list[Any] = [start_date, end_date]
    status_filter = ""
    if outcome_status:
        status_filter = "AND outcome_status = %s"
        params.append(outcome_status)
    params.append(limit)
    sql = f"""
    SELECT
        shadow_outcome_id,
        run_id,
        shadow_candidate_id,
        source_p12_shadow_run_id,
        replay_result_id,
        source_p11_replay_run_id,
        source_p10_proposal_run_id,
        source_p9_analytics_run_id,
        candidate_date::text AS candidate_date,
        asset_id,
        stock_code,
        stock_name,
        shadow_layer,
        shadow_status,
        outcome_status,
        available_future_bars,
        base_trade_date::text AS base_trade_date,
        base_close,
        forward_returns,
        max_high_returns,
        max_low_drawdowns,
        manual_review_required,
        auto_trade_enabled,
        production_watchlist_enabled,
        production_write_enabled
    FROM ops.operator_shadow_watchlist_outcome_candidate
    WHERE candidate_date BETWEEN %s AND %s
      {status_filter}
    ORDER BY candidate_date DESC, outcome_status, shadow_outcome_id
    LIMIT %s
    """
    try:
        with connect(service) as conn:
            rows = fetch_all(conn, sql, params)
    except (psycopg_errors.UndefinedTable, psycopg_errors.InvalidSchemaName):
        rows = []
    return [_shadow_outcome_row(row) for row in rows]


def _shadow_outcome_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "shadow_outcome_id": str(row["shadow_outcome_id"]),
        "run_id": str(row["run_id"]),
        "shadow_candidate_id": str(row["shadow_candidate_id"]),
        "source_p12_shadow_run_id": str(row.get("source_p12_shadow_run_id") or ""),
        "replay_result_id": str(row.get("replay_result_id") or ""),
        "source_p11_replay_run_id": str(row.get("source_p11_replay_run_id") or ""),
        "source_p10_proposal_run_id": str(row.get("source_p10_proposal_run_id") or ""),
        "source_p9_analytics_run_id": str(row.get("source_p9_analytics_run_id") or ""),
        "candidate_date": str(row.get("candidate_date") or ""),
        "asset_id": str(row.get("asset_id") or ""),
        "stock_code": str(row.get("stock_code") or ""),
        "stock_name": str(row.get("stock_name") or ""),
        "shadow_layer": str(row.get("shadow_layer") or ""),
        "shadow_status": str(row.get("shadow_status") or ""),
        "outcome_status": str(row.get("outcome_status") or ""),
        "available_future_bars": int(row.get("available_future_bars") or 0),
        "base_trade_date": str(row.get("base_trade_date") or ""),
        "base_close": row.get("base_close"),
        "forward_returns": _json_map(row.get("forward_returns")),
        "max_high_returns": _json_map(row.get("max_high_returns")),
        "max_low_drawdowns": _json_map(row.get("max_low_drawdowns")),
        "manual_review_required": True,
        "auto_trade_enabled": False,
        "production_watchlist_enabled": False,
        "production_write_enabled": False,
    }


def _json_map(value: Any) -> dict[str, float | None]:
    if value is None:
        return {}
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return {}
    if not isinstance(value, dict):
        return {}
    return {str(key): _metric_value(item) for key, item in value.items()}


def _metric_value(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        normalized = float(value)
    except (TypeError, ValueError):
        return None
    return normalized if math.isfinite(normalized) else None
