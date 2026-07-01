from __future__ import annotations

import datetime as dt
import json
import re
from typing import Any

from stock_research.config import SETTINGS
from stock_research.db import connect
from stock_research.operator_decision.read_model import _event_id, _upsert_event, _upsert_session
from stock_research.operator_decision.snapshot_linkage import (
    merge_source_context,
    resolve_decision_snapshot_linkage,
)


ACTION_TO_DECISION_LABEL = {
    "watch": "observe",
    "skip": "no_action",
    "follow_up": "observe",
    "add_to_shadow": "candidate",
    "remove_from_shadow": "remove",
    "note": "observe",
    "pause": "caution",
    "close": "remove",
}

MANUAL_REVIEW_WATCHLIST_ID = "manual_review"
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def create_operator_decision(
    payload: dict[str, Any],
    *,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    request = _normalize_request(payload)
    source_context = _base_source_context(request)
    linkage = resolve_decision_snapshot_linkage(
        {
            **request,
            "source_context": source_context,
        },
        service=service,
    )
    merged_context = {
        **source_context,
        **linkage,
        "operator_action": request["operator_action"],
        "decision_status": request["decision_status"],
    }
    if request.get("follow_up_date"):
        merged_context["follow_up_date"] = request["follow_up_date"]

    source_context_text = merge_source_context(source_context, merged_context)
    session = _session_row(request)
    event = _event_row(request, source_context_text=source_context_text)
    workflow_effects = _workflow_effects(request)

    with connect(service) as conn:
        with conn.cursor() as cur:
            _upsert_session(cur, session)
            _upsert_event(cur, event)
            _apply_workflow_effects(cur, request, workflow_effects)

    warnings = _snapshot_warnings(merged_context)
    return {
        "event_id": event["event_id"],
        "asset_id": event["asset_id"],
        "stock_code": event["stock_code"],
        "stock_name": event["stock_name"],
        "decision_date": event["review_date"],
        "operator_action": request["operator_action"],
        "decision_status": request["decision_status"],
        "decision_label": event["decision_label"],
        "run_id": str(merged_context.get("run_id") or ""),
        "digest_key": str(merged_context.get("digest_key") or ""),
        "review_item_snapshot_id": str(merged_context.get("review_item_snapshot_id") or ""),
        "evidence_digest_snapshot_id": str(merged_context.get("evidence_digest_snapshot_id") or ""),
        "review_item_payload_hash": str(merged_context.get("review_item_payload_hash") or ""),
        "evidence_digest_payload_hash": str(merged_context.get("evidence_digest_payload_hash") or ""),
        "evidence_as_of": str(merged_context.get("evidence_as_of") or ""),
        "review_item_as_of": str(merged_context.get("review_item_as_of") or ""),
        "snapshot_linkage_status": str(merged_context.get("snapshot_linkage_status") or "missing"),
        "snapshot_linkage_warnings": warnings,
        "warnings": warnings,
        "source_context": source_context_text,
        "workflow_effects": workflow_effects,
    }


def _normalize_request(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("invalid_payload")

    asset_id = _text(payload.get("asset_id") or payload.get("stock_code"))
    stock_code = _text(payload.get("stock_code") or payload.get("asset_id"))
    if not asset_id and not stock_code:
        raise ValueError("asset_id_or_stock_code_required")

    operator_action = _text(payload.get("operator_action")).lower()
    if operator_action not in ACTION_TO_DECISION_LABEL:
        raise ValueError("invalid_operator_action")

    decision_date = _date_text(payload.get("decision_date") or dt.date.today().isoformat(), "decision_date")
    follow_up_date = _text(payload.get("follow_up_date"))
    if follow_up_date:
        follow_up_date = _date_text(follow_up_date, "follow_up_date")

    source_context = payload.get("source_context") or {}
    if not isinstance(source_context, (dict, str)):
        raise ValueError("invalid_source_context")

    tags = payload.get("tags") or []
    if isinstance(tags, str):
        tags = [tags]
    if not isinstance(tags, list):
        raise ValueError("invalid_tags")

    return {
        "asset_id": asset_id or stock_code,
        "stock_code": stock_code or asset_id,
        "stock_name": _text(payload.get("stock_name")),
        "decision_date": decision_date,
        "operator_action": operator_action,
        "decision_status": _text(payload.get("decision_status") or "open"),
        "decision_label": ACTION_TO_DECISION_LABEL[operator_action],
        "operator_note": _text(payload.get("operator_note") or payload.get("notes")),
        "follow_up_date": follow_up_date,
        "tags": [str(tag) for tag in tags],
        "run_id": _text(payload.get("run_id")),
        "digest_key": _text(payload.get("digest_key")),
        "review_item_snapshot_id": _text(payload.get("review_item_snapshot_id")),
        "evidence_digest_snapshot_id": _text(payload.get("evidence_digest_snapshot_id")),
        "source_type": _text(payload.get("source_type")),
        "source_name": _text(payload.get("source_name")),
        "review_session_id": _text(payload.get("review_session_id")),
        "reviewer_id": _text(payload.get("reviewer_id") or "dashboard"),
        "source_context": source_context,
    }


def _base_source_context(request: dict[str, Any]) -> dict[str, Any]:
    base = _parse_context(request["source_context"])
    for key in (
        "run_id",
        "digest_key",
        "review_item_snapshot_id",
        "evidence_digest_snapshot_id",
        "source_type",
        "source_name",
    ):
        value = request.get(key)
        if value:
            base[key] = value
    if request["tags"]:
        base["tags"] = request["tags"]
    return base


def _session_row(request: dict[str, Any]) -> dict[str, Any]:
    review_session_id = request["review_session_id"] or f"operator-decision-api-{request['decision_date']}"
    return {
        "review_session_id": review_session_id,
        "review_date": request["decision_date"],
        "reviewer_id": request["reviewer_id"],
        "status": "review_recorded",
        "decision_count": 1,
        "manual_review_required": True,
        "auto_trade_enabled": False,
        "source_artifact_root": "dashboard-api",
        "json_path": "",
        "csv_path": "",
        "markdown_path": "",
        "metadata": {"source": "dashboard_api"},
    }


def _event_row(request: dict[str, Any], *, source_context_text: str) -> dict[str, Any]:
    review_session_id = request["review_session_id"] or f"operator-decision-api-{request['decision_date']}"
    evidence_artifact_id = request["digest_key"] or f"operator_decision_api:{request['decision_date']}:{request['asset_id']}"
    evidence_path = ""
    event_index = 0
    return {
        "event_id": _event_id(
            review_session_id=review_session_id,
            index=event_index,
            asset_id=request["asset_id"],
            decision_label=request["decision_label"],
            evidence_artifact_id=evidence_artifact_id,
            evidence_path=evidence_path,
        ),
        "review_session_id": review_session_id,
        "review_date": request["decision_date"],
        "event_index": event_index,
        "asset_id": request["asset_id"],
        "stock_code": request["stock_code"],
        "stock_name": request["stock_name"],
        "decision_label": request["decision_label"],
        "evidence_artifact_id": evidence_artifact_id,
        "evidence_path": evidence_path,
        "source_context": source_context_text,
        "requires_follow_up": request["operator_action"] == "follow_up" or bool(request["follow_up_date"]),
        "follow_up_note": request["follow_up_date"],
        "notes": request["operator_note"],
        "manual_review_required": True,
        "auto_trade_enabled": False,
        "source_artifact_path": "dashboard-api",
    }


def _workflow_effects(request: dict[str, Any]) -> list[dict[str, Any]]:
    operator_action = request["operator_action"]
    if operator_action in {"watch", "follow_up"}:
        return [
            {
                "type": "watchlist_item",
                "status": "upserted",
                "watchlist_id": MANUAL_REVIEW_WATCHLIST_ID,
                "asset_id": request["asset_id"],
            }
        ]
    if operator_action == "close":
        return [
            {
                "type": "watchlist_item",
                "status": "deactivated",
                "watchlist_id": MANUAL_REVIEW_WATCHLIST_ID,
                "asset_id": request["asset_id"],
            }
        ]
    return []


def _apply_workflow_effects(cur: Any, request: dict[str, Any], workflow_effects: list[dict[str, Any]]) -> None:
    for effect in workflow_effects:
        if effect["type"] == "watchlist_item":
            _upsert_manual_review_watchlist_item(
                cur,
                request,
                active=effect["status"] == "upserted",
            )


def _upsert_manual_review_watchlist_item(cur: Any, request: dict[str, Any], *, active: bool) -> None:
    sql = """
    INSERT INTO watchlist.watchlist_item (
        watchlist_id, asset_id, stock_code, stock_name, priority, active, note, source
    )
    VALUES (
        %(watchlist_id)s, %(asset_id)s, %(stock_code)s, %(stock_name)s,
        %(priority)s, %(active)s, %(note)s, %(source)s
    )
    ON CONFLICT (watchlist_id, asset_id)
    DO UPDATE SET
        stock_code = EXCLUDED.stock_code,
        stock_name = EXCLUDED.stock_name,
        priority = EXCLUDED.priority,
        active = EXCLUDED.active,
        note = EXCLUDED.note,
        source = EXCLUDED.source,
        updated_at = now()
    """
    cur.execute(
        sql,
        {
            "watchlist_id": MANUAL_REVIEW_WATCHLIST_ID,
            "asset_id": request["asset_id"],
            "stock_code": request["stock_code"],
            "stock_name": request["stock_name"],
            "priority": 50 if active else 100,
            "active": active,
            "note": request["operator_note"],
            "source": f"operator_decision:{request['operator_action']}",
        },
    )


def _parse_context(source_context: Any) -> dict[str, Any]:
    if isinstance(source_context, dict):
        return dict(source_context)
    if isinstance(source_context, str):
        try:
            parsed = json.loads(source_context)
        except json.JSONDecodeError:
            return {"source_context_label": source_context}
        return dict(parsed) if isinstance(parsed, dict) else {"source_context_label": source_context}
    return {}


def _snapshot_warnings(context: dict[str, Any]) -> list[str]:
    warnings = context.get("snapshot_linkage_warnings") or []
    if not isinstance(warnings, list):
        return [str(warnings)]
    return [str(warning) for warning in warnings]


def _date_text(value: Any, field_name: str) -> str:
    text = _text(value)
    if not _ISO_DATE_RE.fullmatch(text):
        raise ValueError(f"invalid_{field_name}")
    try:
        dt.date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"invalid_{field_name}") from exc
    return text


def _text(value: Any) -> str:
    return str(value or "").strip()
