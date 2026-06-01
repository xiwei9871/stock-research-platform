from __future__ import annotations

from typing import Any

from psycopg import errors as psycopg_errors

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all


def load_shadow_review_decision_summary(
    start_date: str,
    end_date: str,
    limit: int = 20,
    service: str = SETTINGS.research_service,
) -> list[dict[str, Any]]:
    """Return read-only P16 shadow review decision dashboard rows."""
    sql = """
    SELECT
        decision_group_id,
        run_id,
        decision_date::text AS decision_date,
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
        decision_reason,
        required_next_action,
        evidence_summary,
        risk_notes,
        next_research_question,
        manual_review_required,
        auto_trade_enabled,
        production_watchlist_enabled,
        production_write_enabled
    FROM ops.operator_shadow_review_decision_group
    WHERE decision_date BETWEEN %s AND %s
    ORDER BY decision_date DESC, decision_status, sample_count DESC, group_key
    LIMIT %s
    """
    try:
        with connect(service) as conn:
            rows = fetch_all(conn, sql, [start_date, end_date, limit])
    except (psycopg_errors.UndefinedTable, psycopg_errors.InvalidSchemaName):
        rows = []
    return [_decision_row(row) for row in rows]


def _decision_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "decision_group_id": str(row["decision_group_id"]),
        "run_id": str(row["run_id"]),
        "decision_date": str(row.get("decision_date") or ""),
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
