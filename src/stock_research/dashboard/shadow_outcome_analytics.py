from __future__ import annotations

import json
import math
from decimal import Decimal
from typing import Any

from psycopg import errors as psycopg_errors

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all


def load_shadow_outcome_analytics_summary(
    start_date: str,
    end_date: str,
    limit: int = 20,
    service: str = SETTINGS.research_service,
) -> list[dict[str, Any]]:
    """Return read-only P14 analytics dashboard rows."""
    sql = """
    SELECT
        run_id,
        review_start_date::text AS review_start_date,
        review_end_date::text AS review_end_date,
        group_key,
        shadow_layer,
        shadow_status,
        sample_count,
        complete_count,
        insufficient_data_count,
        source_p12_shadow_run_count,
        source_p11_replay_run_count,
        source_p10_proposal_run_count,
        source_p9_analytics_run_count,
        horizon_metrics,
        analytics_artifact_path,
        manual_review_required,
        auto_trade_enabled,
        production_watchlist_enabled,
        production_write_enabled
    FROM ops.operator_shadow_watchlist_outcome_analytics_group
    WHERE review_end_date BETWEEN %s AND %s
    ORDER BY review_end_date DESC, sample_count DESC, group_key
    LIMIT %s
    """
    try:
        with connect(service) as conn:
            rows = fetch_all(conn, sql, [start_date, end_date, limit])
    except (psycopg_errors.UndefinedTable, psycopg_errors.InvalidSchemaName):
        rows = []
    return [_analytics_row(row) for row in rows]


def _analytics_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": str(row["run_id"]),
        "review_start_date": str(row.get("review_start_date") or ""),
        "review_end_date": str(row.get("review_end_date") or ""),
        "group_key": str(row["group_key"]),
        "shadow_layer": str(row.get("shadow_layer") or ""),
        "shadow_status": str(row.get("shadow_status") or ""),
        "sample_count": int(row.get("sample_count") or 0),
        "complete_count": int(row.get("complete_count") or 0),
        "insufficient_data_count": int(row.get("insufficient_data_count") or 0),
        "source_p12_shadow_run_count": int(row.get("source_p12_shadow_run_count") or 0),
        "source_p11_replay_run_count": int(row.get("source_p11_replay_run_count") or 0),
        "source_p10_proposal_run_count": int(row.get("source_p10_proposal_run_count") or 0),
        "source_p9_analytics_run_count": int(row.get("source_p9_analytics_run_count") or 0),
        "horizon_metrics": _horizon_metrics(row.get("horizon_metrics")),
        "analytics_artifact_path": str(row.get("analytics_artifact_path") or ""),
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
