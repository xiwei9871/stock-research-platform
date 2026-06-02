from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all


def load_asset_outcome_history(
    asset_id: str,
    start_date: str,
    end_date: str,
    review_session_id: str | None = None,
    limit: int = 20,
    service: str = SETTINGS.research_service,
) -> list[dict[str, Any]]:
    params: list[Any] = [asset_id, start_date, end_date]
    session_filter = ""
    if review_session_id:
        session_filter = "AND review_session_id = %s"
        params.append(review_session_id)
    params.append(limit)
    sql = f"""
    SELECT
        outcome_event_id,
        run_id,
        decision_event_id,
        review_session_id,
        review_date::text AS review_date,
        asset_id,
        stock_code,
        stock_name,
        decision_label,
        source_context,
        outcome_status,
        available_future_bars,
        base_trade_date::text AS base_trade_date,
        base_close,
        forward_returns,
        max_high_returns,
        max_low_drawdowns,
        manual_review_required,
        auto_trade_enabled,
        source_artifact_path,
        outcome_artifact_path
    FROM ops.operator_decision_outcome_event
    WHERE asset_id = %s
      AND review_date BETWEEN %s AND %s
      {session_filter}
    ORDER BY review_date DESC, review_session_id DESC, outcome_event_id DESC
    LIMIT %s
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, params)
    return [_outcome_row(row) for row in rows]


def _outcome_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "outcome_event_id": str(row["outcome_event_id"]),
        "run_id": str(row["run_id"]),
        "decision_event_id": str(row["decision_event_id"]),
        "review_session_id": str(row["review_session_id"]),
        "review_date": str(row.get("review_date") or ""),
        "asset_id": str(row["asset_id"]),
        "stock_code": str(row.get("stock_code") or ""),
        "stock_name": str(row.get("stock_name") or ""),
        "decision_label": str(row["decision_label"]),
        "source_context": str(row.get("source_context") or ""),
        "outcome_status": str(row["outcome_status"]),
        "available_future_bars": int(row.get("available_future_bars") or 0),
        "base_trade_date": str(row.get("base_trade_date") or ""),
        "base_close": _number_or_none(row.get("base_close")),
        "forward_returns": _json_map(row.get("forward_returns")),
        "max_high_returns": _json_map(row.get("max_high_returns")),
        "max_low_drawdowns": _json_map(row.get("max_low_drawdowns")),
        "manual_review_required": bool(row.get("manual_review_required", True)),
        "auto_trade_enabled": bool(row.get("auto_trade_enabled", False)),
        "source_artifact_path": str(row.get("source_artifact_path") or ""),
        "outcome_artifact_path": str(row.get("outcome_artifact_path") or ""),
    }


def _json_map(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return {}
    if not isinstance(value, dict):
        return {}
    return {str(key): _number_or_none(item) for key, item in value.items()}


def _number_or_none(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
