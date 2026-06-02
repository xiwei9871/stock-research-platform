from __future__ import annotations

from typing import Any

from psycopg import errors as psycopg_errors

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all


def load_shadow_follow_up_resolution_summary(
    start_date: str,
    end_date: str,
    limit: int = 20,
    service: str = SETTINGS.research_service,
) -> list[dict[str, Any]]:
    """Return read-only P18 shadow follow-up resolution dashboard rows."""
    sql = """
    SELECT
        resolution_item_id,
        run_id,
        resolution_date::text AS resolution_date,
        source_p17_follow_up_item_id,
        source_p17_follow_up_run_id,
        source_p16_decision_group_id,
        source_p16_decision_run_id,
        source_p15_review_group_id,
        source_p15_review_run_id,
        source_p14_analytics_group_id,
        source_p14_analytics_run_id,
        group_key,
        shadow_layer,
        shadow_status,
        sample_count,
        complete_count,
        insufficient_data_count,
        review_status,
        review_bucket,
        decision_status,
        decision_bucket,
        follow_up_status,
        priority_bucket,
        required_input,
        resolution_status,
        resolution_bucket,
        recommended_resolution_action,
        resolution_reason,
        follow_up_reason,
        decision_reason,
        required_next_action,
        evidence_summary,
        risk_notes,
        next_research_question,
        manual_review_required,
        auto_trade_enabled,
        production_watchlist_enabled,
        production_write_enabled
    FROM ops.operator_shadow_follow_up_resolution_item
    WHERE resolution_date BETWEEN %s AND %s
    ORDER BY resolution_date DESC, resolution_status, resolution_bucket, priority_bucket, sample_count DESC, group_key
    LIMIT %s
    """
    try:
        with connect(service) as conn:
            rows = fetch_all(conn, sql, [start_date, end_date, limit])
    except (psycopg_errors.UndefinedTable, psycopg_errors.InvalidSchemaName):
        rows = []
    return [_resolution_row(row) for row in rows]


def _resolution_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "resolution_item_id": str(row["resolution_item_id"]),
        "run_id": str(row["run_id"]),
        "resolution_date": str(row.get("resolution_date") or ""),
        "source_p17_follow_up_item_id": str(row.get("source_p17_follow_up_item_id") or ""),
        "source_p17_follow_up_run_id": str(row.get("source_p17_follow_up_run_id") or ""),
        "source_p16_decision_group_id": str(row.get("source_p16_decision_group_id") or ""),
        "source_p16_decision_run_id": str(row.get("source_p16_decision_run_id") or ""),
        "source_p15_review_group_id": str(row.get("source_p15_review_group_id") or ""),
        "source_p15_review_run_id": str(row.get("source_p15_review_run_id") or ""),
        "source_p14_analytics_group_id": str(row.get("source_p14_analytics_group_id") or ""),
        "source_p14_analytics_run_id": str(row.get("source_p14_analytics_run_id") or ""),
        "group_key": str(row.get("group_key") or ""),
        "shadow_layer": str(row.get("shadow_layer") or ""),
        "shadow_status": str(row.get("shadow_status") or ""),
        "sample_count": int(row.get("sample_count") or 0),
        "complete_count": int(row.get("complete_count") or 0),
        "insufficient_data_count": int(row.get("insufficient_data_count") or 0),
        "review_status": str(row.get("review_status") or ""),
        "review_bucket": str(row.get("review_bucket") or ""),
        "decision_status": str(row.get("decision_status") or ""),
        "decision_bucket": str(row.get("decision_bucket") or ""),
        "follow_up_status": str(row.get("follow_up_status") or ""),
        "priority_bucket": str(row.get("priority_bucket") or ""),
        "required_input": str(row.get("required_input") or ""),
        "resolution_status": str(row.get("resolution_status") or ""),
        "resolution_bucket": str(row.get("resolution_bucket") or ""),
        "recommended_resolution_action": str(row.get("recommended_resolution_action") or ""),
        "resolution_reason": str(row.get("resolution_reason") or ""),
        "follow_up_reason": str(row.get("follow_up_reason") or ""),
        "decision_reason": str(row.get("decision_reason") or ""),
        "required_next_action": str(row.get("required_next_action") or ""),
        "evidence_summary": str(row.get("evidence_summary") or ""),
        "risk_notes": str(row.get("risk_notes") or ""),
        "next_research_question": str(row.get("next_research_question") or ""),
        "manual_review_required": True,
        "auto_trade_enabled": False,
        "production_watchlist_enabled": False,
        "production_write_enabled": False,
    }
