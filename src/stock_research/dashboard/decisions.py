from __future__ import annotations

from typing import Any

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all


def load_asset_decision_history(
    asset_id: str,
    start_date: str,
    end_date: str,
    limit: int = 20,
    service: str = SETTINGS.research_service,
) -> list[dict[str, Any]]:
    sql = """
    SELECT
        review_date::text AS review_date,
        review_session_id,
        event_id,
        asset_id,
        stock_code,
        stock_name,
        decision_label,
        evidence_artifact_id,
        evidence_path,
        source_context,
        requires_follow_up,
        follow_up_note,
        notes,
        manual_review_required,
        auto_trade_enabled
    FROM ops.operator_decision_event
    WHERE asset_id = %s
      AND review_date BETWEEN %s AND %s
    ORDER BY review_date DESC, event_index DESC
    LIMIT %s
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, [asset_id, start_date, end_date, limit])
    return [_decision_row(row) for row in rows]


def _decision_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "review_date": str(row["review_date"]),
        "review_session_id": str(row["review_session_id"]),
        "event_id": str(row["event_id"]),
        "asset_id": str(row["asset_id"]),
        "stock_code": str(row.get("stock_code") or ""),
        "stock_name": str(row.get("stock_name") or ""),
        "decision_label": str(row["decision_label"]),
        "evidence_artifact_id": str(row.get("evidence_artifact_id") or ""),
        "evidence_path": str(row.get("evidence_path") or ""),
        "source_context": str(row.get("source_context") or ""),
        "requires_follow_up": bool(row.get("requires_follow_up")),
        "follow_up_note": str(row.get("follow_up_note") or ""),
        "notes": str(row.get("notes") or ""),
        "manual_review_required": bool(row.get("manual_review_required", True)),
        "auto_trade_enabled": bool(row.get("auto_trade_enabled", False)),
    }
