from __future__ import annotations

import json
from typing import Any

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all

REQUIRED_DECISION_FIELDS = {"asset_id", "decision_label"}


def validate_operator_decision_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("invalid_payload")

    normalized = dict(payload)
    missing = sorted(field for field in REQUIRED_DECISION_FIELDS if not str(normalized.get(field) or "").strip())
    if missing:
        raise ValueError(f"operator_decision_missing_fields:{','.join(missing)}")

    source_context = normalized.get("source_context") if isinstance(normalized.get("source_context"), dict) else {}
    has_evidence = bool(
        str(normalized.get("evidence_artifact_id") or "").strip()
        or str(normalized.get("evidence_digest_snapshot_id") or "").strip()
        or str(normalized.get("review_item_snapshot_id") or "").strip()
        or str(source_context.get("evidence_digest_snapshot_id") or "").strip()
        or str(source_context.get("review_item_snapshot_id") or "").strip()
    )
    if not has_evidence:
        raise ValueError("operator_decision_missing_evidence_linkage")
    if normalized.get("auto_trade_enabled") is True:
        raise ValueError("operator_decision_auto_trade_forbidden")

    normalized["manual_review_required"] = True
    normalized["auto_trade_enabled"] = False
    return normalized


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


def update_operator_decision_event(
    event_id: str,
    payload: dict[str, Any],
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    if not event_id:
        raise ValueError("event_id_required")
    if not isinstance(payload, dict):
        raise ValueError("invalid_payload")
    allowed = {"notes", "follow_up_note", "requires_follow_up"}
    updates = {key: payload[key] for key in allowed if key in payload}
    if not updates:
        raise ValueError("no_editable_fields")

    set_clauses: list[str] = []
    params: list[Any] = []
    if "notes" in updates:
        set_clauses.append("notes = %s")
        params.append(str(updates["notes"] or ""))
    if "follow_up_note" in updates:
        set_clauses.append("follow_up_note = %s")
        params.append(str(updates["follow_up_note"] or ""))
    if "requires_follow_up" in updates:
        set_clauses.append("requires_follow_up = %s")
        params.append(bool(updates["requires_follow_up"]))
    params.append(event_id)

    sql = f"""
    UPDATE ops.operator_decision_event
    SET {", ".join(set_clauses)}
    WHERE event_id = %s
    RETURNING
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
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, params)
    if not rows:
        raise ValueError("decision_event_not_found")
    return _decision_row(rows[0])


def _decision_row(row: dict[str, Any]) -> dict[str, Any]:
    linkage = _snapshot_linkage(row.get("source_context"))
    result = {
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
    if linkage:
        result.update(linkage)
    return result


def _snapshot_linkage(source_context: Any) -> dict[str, Any] | None:
    if not source_context:
        return None
    if isinstance(source_context, dict):
        context = source_context
    else:
        try:
            parsed = json.loads(str(source_context))
        except json.JSONDecodeError:
            return None
        context = parsed if isinstance(parsed, dict) else {}
    if not context:
        return None
    fields = {
        "run_id": str(context.get("run_id") or ""),
        "digest_key": str(context.get("digest_key") or ""),
        "review_item_snapshot_id": str(context.get("review_item_snapshot_id") or ""),
        "evidence_digest_snapshot_id": str(context.get("evidence_digest_snapshot_id") or ""),
        "review_item_payload_hash": str(context.get("review_item_payload_hash") or ""),
        "evidence_digest_payload_hash": str(context.get("evidence_digest_payload_hash") or ""),
        "evidence_as_of": str(context.get("evidence_as_of") or ""),
        "review_item_as_of": str(context.get("review_item_as_of") or ""),
    }
    linked = bool(fields["review_item_snapshot_id"] or fields["evidence_digest_snapshot_id"])
    warnings = context.get("snapshot_linkage_warnings")
    if not isinstance(warnings, list):
        warnings = [] if linked else ["snapshot linkage unavailable"]
    return {
        **fields,
        "snapshot_linkage_status": str(
            context.get("snapshot_linkage_status") or ("linked" if linked else "missing")
        ),
        "snapshot_linkage_warnings": [str(warning) for warning in warnings],
    }


def _missing_linkage() -> dict[str, Any]:
    return {
        "run_id": "",
        "digest_key": "",
        "review_item_snapshot_id": "",
        "evidence_digest_snapshot_id": "",
        "review_item_payload_hash": "",
        "evidence_digest_payload_hash": "",
        "evidence_as_of": "",
        "review_item_as_of": "",
        "snapshot_linkage_status": "missing",
        "snapshot_linkage_warnings": ["snapshot linkage unavailable"],
    }
