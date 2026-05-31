from __future__ import annotations

import json
from typing import Any

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all


def load_experiment_proposals_summary(
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
        proposal_id,
        run_id,
        review_date::text AS review_date,
        proposal_title,
        hypothesis,
        source_p9_analytics_run_id,
        source_analytics_group_ids,
        source_diagnostic_refs,
        source_artifact_paths,
        expected_validation_method,
        risk_notes,
        reviewer_id,
        status,
        proposal_artifact_path,
        manual_review_required,
        auto_trade_enabled,
        promotion_enabled
    FROM ops.operator_experiment_proposal
    WHERE review_date BETWEEN %s AND %s
      {status_filter}
    ORDER BY review_date DESC, status, proposal_id
    LIMIT %s
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, params)
    return [_proposal_row(row) for row in rows]


def _proposal_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "proposal_id": str(row["proposal_id"]),
        "run_id": str(row["run_id"]),
        "review_date": str(row.get("review_date") or ""),
        "proposal_title": str(row.get("proposal_title") or ""),
        "hypothesis": str(row.get("hypothesis") or ""),
        "source_p9_analytics_run_id": str(row.get("source_p9_analytics_run_id") or ""),
        "source_analytics_group_ids": _list_value(row.get("source_analytics_group_ids")),
        "source_diagnostic_refs": _list_value(row.get("source_diagnostic_refs")),
        "source_artifact_paths": _list_value(row.get("source_artifact_paths")),
        "expected_validation_method": str(row.get("expected_validation_method") or ""),
        "risk_notes": str(row.get("risk_notes") or ""),
        "reviewer_id": str(row.get("reviewer_id") or ""),
        "status": str(row.get("status") or ""),
        "proposal_artifact_path": str(row.get("proposal_artifact_path") or ""),
        "manual_review_required": True,
        "auto_trade_enabled": False,
        "promotion_enabled": False,
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
