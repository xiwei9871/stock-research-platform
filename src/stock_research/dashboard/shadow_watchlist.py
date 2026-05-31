from __future__ import annotations

import json
from typing import Any

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all


def load_shadow_watchlist_summary(
    start_date: str,
    end_date: str,
    status: str | None = None,
    limit: int = 20,
    service: str = SETTINGS.research_service,
) -> list[dict[str, Any]]:
    params: list[Any] = [start_date, end_date]
    status_filter = ""
    if status:
        status_filter = "AND status = %s"
        params.append(status)
    params.append(limit)
    sql = f"""
    SELECT
        shadow_candidate_id,
        run_id,
        replay_result_id,
        source_p11_replay_run_id,
        source_p10_proposal_run_id,
        source_p9_analytics_run_id,
        candidate_date::text AS candidate_date,
        asset_id,
        stock_code,
        stock_name,
        shadow_layer,
        candidate_reason,
        evidence_artifact_paths,
        metric_summary,
        reviewer_id,
        status,
        review_notes,
        shadow_artifact_path,
        manual_review_required,
        auto_trade_enabled,
        production_watchlist_enabled,
        production_write_enabled
    FROM ops.operator_shadow_watchlist_candidate
    WHERE candidate_date BETWEEN %s AND %s
      {status_filter}
    ORDER BY candidate_date DESC, status, shadow_candidate_id
    LIMIT %s
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, params)
    return [_shadow_row(row) for row in rows]


def _shadow_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "shadow_candidate_id": str(row["shadow_candidate_id"]),
        "run_id": str(row["run_id"]),
        "replay_result_id": str(row.get("replay_result_id") or ""),
        "source_p11_replay_run_id": str(row.get("source_p11_replay_run_id") or ""),
        "source_p10_proposal_run_id": str(row.get("source_p10_proposal_run_id") or ""),
        "source_p9_analytics_run_id": str(row.get("source_p9_analytics_run_id") or ""),
        "candidate_date": str(row.get("candidate_date") or ""),
        "asset_id": str(row.get("asset_id") or ""),
        "stock_code": str(row.get("stock_code") or ""),
        "stock_name": str(row.get("stock_name") or ""),
        "shadow_layer": str(row.get("shadow_layer") or ""),
        "candidate_reason": str(row.get("candidate_reason") or ""),
        "evidence_artifact_paths": _list_value(row.get("evidence_artifact_paths")),
        "metric_summary": _dict_value(row.get("metric_summary")),
        "reviewer_id": str(row.get("reviewer_id") or ""),
        "status": str(row.get("status") or ""),
        "review_notes": str(row.get("review_notes") or ""),
        "shadow_artifact_path": str(row.get("shadow_artifact_path") or ""),
        "manual_review_required": True,
        "auto_trade_enabled": False,
        "production_watchlist_enabled": False,
        "production_write_enabled": False,
    }


def _list_value(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return [value] if value else []
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]


def _dict_value(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return {}
    return value if isinstance(value, dict) else {}
