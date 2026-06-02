from __future__ import annotations

import json
from typing import Any

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all


def load_experiment_replay_summary(
    start_date: str,
    end_date: str,
    status: str | None = None,
    limit: int = 20,
    service: str = SETTINGS.research_service,
) -> list[dict[str, Any]]:
    params: list[Any] = [start_date, end_date]
    status_filter = ""
    if status:
        status_filter = "AND replay_status = %s"
        params.append(status)
    params.append(limit)
    sql = f"""
    SELECT
        replay_result_id,
        run_id,
        proposal_id,
        source_p10_proposal_run_id,
        source_p9_analytics_run_id,
        replay_start_date::text AS replay_start_date,
        replay_end_date::text AS replay_end_date,
        replay_input_artifact_paths,
        validation_method,
        replay_status,
        sample_count,
        passed_count,
        failed_count,
        metric_summary,
        failure_reason,
        defer_reason,
        replay_artifact_path,
        manual_review_required,
        auto_trade_enabled,
        production_write_enabled
    FROM ops.operator_experiment_replay_result
    WHERE replay_end_date BETWEEN %s AND %s
      {status_filter}
    ORDER BY replay_end_date DESC, replay_status, replay_result_id
    LIMIT %s
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, params)
    return [_replay_row(row) for row in rows]


def _replay_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "replay_result_id": str(row["replay_result_id"]),
        "run_id": str(row["run_id"]),
        "proposal_id": str(row.get("proposal_id") or ""),
        "source_p10_proposal_run_id": str(row.get("source_p10_proposal_run_id") or ""),
        "source_p9_analytics_run_id": str(row.get("source_p9_analytics_run_id") or ""),
        "replay_start_date": str(row.get("replay_start_date") or ""),
        "replay_end_date": str(row.get("replay_end_date") or ""),
        "replay_input_artifact_paths": _list_value(row.get("replay_input_artifact_paths")),
        "validation_method": str(row.get("validation_method") or ""),
        "replay_status": str(row.get("replay_status") or ""),
        "sample_count": int(row.get("sample_count") or 0),
        "passed_count": int(row.get("passed_count") or 0),
        "failed_count": int(row.get("failed_count") or 0),
        "metric_summary": _dict_value(row.get("metric_summary")),
        "failure_reason": str(row.get("failure_reason") or ""),
        "defer_reason": str(row.get("defer_reason") or ""),
        "replay_artifact_path": str(row.get("replay_artifact_path") or ""),
        "manual_review_required": True,
        "auto_trade_enabled": False,
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
