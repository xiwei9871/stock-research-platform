from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all


def load_outcome_analytics_summary(
    start_date: str,
    end_date: str,
    review_session_id: str | None = None,
    limit: int = 20,
    service: str = SETTINGS.research_service,
) -> list[dict[str, Any]]:
    params: list[Any] = [start_date, end_date]
    session_filter = ""
    if review_session_id:
        session_filter = "AND review_session_id = %s"
        params.append(review_session_id)
    params.append(limit)
    sql = f"""
    SELECT
        run_id,
        review_start_date::text AS review_start_date,
        review_end_date::text AS review_end_date,
        analytics_level,
        group_value,
        sample_count,
        complete_count,
        insufficient_data_count,
        follow_up_required_rate,
        horizon_metrics,
        analytics_artifact_path
    FROM ops.operator_decision_outcome_analytics_group
    WHERE review_end_date BETWEEN %s AND %s
      AND analytics_level IN ('decision_label', 'source_context')
      {session_filter}
    ORDER BY review_end_date DESC, analytics_level, sample_count DESC, group_value
    LIMIT %s
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, params)
    return [_analytics_row(row) for row in rows]


def _analytics_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": str(row["run_id"]),
        "review_start_date": str(row.get("review_start_date") or ""),
        "review_end_date": str(row.get("review_end_date") or ""),
        "analytics_level": str(row["analytics_level"]),
        "group_value": str(row["group_value"]),
        "sample_count": int(row.get("sample_count") or 0),
        "complete_count": int(row.get("complete_count") or 0),
        "insufficient_data_count": int(row.get("insufficient_data_count") or 0),
        "follow_up_required_rate": _number_or_none(row.get("follow_up_required_rate")),
        "horizon_metrics": _horizon_metrics(row.get("horizon_metrics")),
        "analytics_artifact_path": str(row.get("analytics_artifact_path") or ""),
        "manual_review_required": True,
        "auto_trade_enabled": False,
    }


def _horizon_metrics(value: Any) -> dict[str, dict[str, float | None]]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return {}
    if not isinstance(value, dict):
        return {}
    metrics: dict[str, dict[str, float | None]] = {}
    for horizon, horizon_values in value.items():
        if not isinstance(horizon_values, dict):
            continue
        metrics[str(horizon)] = {
            str(key): _number_or_none(item)
            for key, item in horizon_values.items()
        }
    return metrics


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
