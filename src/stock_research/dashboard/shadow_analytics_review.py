from __future__ import annotations

import json
import math
from decimal import Decimal
from typing import Any

from psycopg import errors as psycopg_errors

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all


def load_shadow_analytics_review_summary(
    start_date: str,
    end_date: str,
    limit: int = 20,
    service: str = SETTINGS.research_service,
) -> list[dict[str, Any]]:
    """Return read-only P15 shadow analytics review dashboard rows."""
    sql = """
    SELECT
        review_group_id,
        run_id,
        review_start_date::text AS review_start_date,
        review_end_date::text AS review_end_date,
        source_p14_analytics_group_id,
        source_p14_analytics_run_id,
        group_key,
        shadow_layer,
        shadow_status,
        sample_count,
        complete_count,
        insufficient_data_count,
        horizon_metrics,
        review_status,
        review_bucket,
        evidence_summary,
        risk_notes,
        next_research_question,
        manual_review_required,
        auto_trade_enabled,
        production_watchlist_enabled,
        production_write_enabled
    FROM ops.operator_shadow_analytics_review_group
    WHERE review_end_date BETWEEN %s AND %s
    ORDER BY review_end_date DESC, review_status, sample_count DESC, group_key
    LIMIT %s
    """
    try:
        with connect(service) as conn:
            rows = fetch_all(conn, sql, [start_date, end_date, limit])
    except (psycopg_errors.UndefinedTable, psycopg_errors.InvalidSchemaName):
        rows = []
    return [_review_row(row) for row in rows]


def _review_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "review_group_id": str(row["review_group_id"]),
        "run_id": str(row["run_id"]),
        "review_start_date": str(row.get("review_start_date") or ""),
        "review_end_date": str(row.get("review_end_date") or ""),
        "source_p14_analytics_group_id": str(row.get("source_p14_analytics_group_id") or ""),
        "source_p14_analytics_run_id": str(row.get("source_p14_analytics_run_id") or ""),
        "group_key": str(row["group_key"]),
        "shadow_layer": str(row.get("shadow_layer") or ""),
        "shadow_status": str(row.get("shadow_status") or ""),
        "sample_count": int(row.get("sample_count") or 0),
        "complete_count": int(row.get("complete_count") or 0),
        "insufficient_data_count": int(row.get("insufficient_data_count") or 0),
        "horizon_metrics": _horizon_metrics(row.get("horizon_metrics")),
        "review_status": str(row.get("review_status") or ""),
        "review_bucket": str(row.get("review_bucket") or ""),
        "evidence_summary": str(row.get("evidence_summary") or ""),
        "risk_notes": str(row.get("risk_notes") or ""),
        "next_research_question": str(row.get("next_research_question") or ""),
        "manual_review_required": True,
        "auto_trade_enabled": False,
        "production_watchlist_enabled": False,
        "production_write_enabled": False,
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
            str(key): _metric_value(metric_value)
            for key, metric_value in horizon_values.items()
        }
    return metrics


def _metric_value(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        value = float(value)
    try:
        normalized = float(value)
    except (TypeError, ValueError):
        return None
    return normalized if math.isfinite(normalized) else None
