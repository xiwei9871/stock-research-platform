from __future__ import annotations

import json
import time
from typing import Any

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all
from stock_research.research_objects import stable_id


ALLOWED_REVIEW_ACTION_TYPES = {
    "acknowledge_gap",
    "request_more_evidence",
    "mark_reviewed",
    "defer",
}

SOURCE_CONTEXT_ALLOWED_KEYS = {
    "from",
    "case_source_type",
    "case_source_id",
    "case_id",
    "trade_date",
    "asset_id",
}

FORBIDDEN_REVIEW_ACTION_FIELDS = {
    "auto_trade_enabled",
    "publish",
    "publication_snapshot",
    "operator_decision",
    "trade",
}


def record_review_action(payload: dict[str, Any], *, service: str = SETTINGS.research_service) -> str:
    cleaned = validate_review_action_payload(payload)
    review_action_id = stable_id(
        "review_action",
        cleaned["case_id"],
        cleaned["action_type"],
        cleaned["gap_reasons"],
        cleaned["comment"],
        cleaned["source_context"],
        time.time_ns(),
    )
    params = {
        "review_action_id": review_action_id,
        **cleaned,
        "gap_reasons": _json_list(cleaned["gap_reasons"]),
        "source_context": _json_object(cleaned["source_context"]),
        "metadata": _json_object(cleaned["metadata"]),
    }
    sql = """
    INSERT INTO research.review_action (
        review_action_id, case_id, trade_date, asset_id, action_type,
        gap_reasons, reviewer, comment, source_context, metadata
    )
    VALUES (
        %(review_action_id)s, %(case_id)s, %(trade_date)s, %(asset_id)s,
        %(action_type)s, %(gap_reasons)s::jsonb, %(reviewer)s, %(comment)s,
        %(source_context)s::jsonb, %(metadata)s::jsonb
    )
    """
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
    return review_action_id


def list_review_actions(
    *,
    case_id: str | None = None,
    trade_date: str | None = None,
    limit: int = 50,
    service: str = SETTINGS.research_service,
) -> list[dict[str, Any]]:
    clauses = ["1=1"]
    params: list[Any] = []
    if case_id:
        clauses.append("case_id = %s")
        params.append(case_id)
    if trade_date:
        clauses.append("trade_date = %s")
        params.append(trade_date)
    params.append(_clamp_limit(limit))
    sql = f"""
    SELECT
        review_action_id,
        case_id,
        trade_date::text AS trade_date,
        asset_id,
        action_type,
        gap_reasons,
        reviewer,
        comment,
        created_at::text AS created_at,
        source_context
    FROM research.review_action
    WHERE {" AND ".join(clauses)}
    ORDER BY created_at DESC, review_action_id DESC
    LIMIT %s
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, params)
    return [review_action_read_model(row) for row in rows]


def validate_review_action_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("review_action_payload_required")
    for key in FORBIDDEN_REVIEW_ACTION_FIELDS:
        value = payload.get(key)
        if value is True or (isinstance(value, str) and value.strip()):
            raise ValueError("review_action_forbidden_field")
    case_id = _text(payload.get("case_id"))
    if not case_id:
        raise ValueError("case_id_required")
    action_type = _text(payload.get("action_type"))
    if action_type not in ALLOWED_REVIEW_ACTION_TYPES:
        raise ValueError("invalid_review_action_type")
    gap_reasons = payload.get("gap_reasons", [])
    if not isinstance(gap_reasons, list):
        raise ValueError("gap_reasons_must_be_list")
    return {
        "case_id": case_id,
        "trade_date": _optional_date(payload.get("trade_date")),
        "asset_id": _optional_text(payload.get("asset_id")),
        "action_type": action_type,
        "gap_reasons": [str(reason) for reason in gap_reasons],
        "reviewer": _text(payload.get("reviewer") or "operator") or "operator",
        "comment": _text(payload.get("comment")),
        "source_context": _clean_source_context(payload.get("source_context")),
        "metadata": _clean_metadata(payload.get("metadata")),
    }


def review_action_read_model(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(row, dict):
        return None
    return {
        "review_action_id": _text(row.get("review_action_id")),
        "case_id": _text(row.get("case_id")),
        "trade_date": _text(row.get("trade_date")),
        "asset_id": _text(row.get("asset_id")),
        "action_type": _text(row.get("action_type")),
        "gap_reasons": _list(row.get("gap_reasons")),
        "reviewer": _text(row.get("reviewer") or "operator") or "operator",
        "comment": _text(row.get("comment")),
        "created_at": _text(row.get("created_at")),
        "source_context": _clean_source_context(row.get("source_context")),
    }


def review_status_from_action(action_type: str | None) -> str:
    action = _text(action_type)
    if action in {"acknowledge_gap", "mark_reviewed"}:
        return "reviewed"
    if action == "request_more_evidence":
        return "request_more_evidence"
    if action == "defer":
        return "deferred"
    return "pending"


def _clean_source_context(value: Any) -> dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    return {
        key: source[key]
        for key in SOURCE_CONTEXT_ALLOWED_KEYS
        if key in source and source[key] is not None and source[key] != ""
    }


def _clean_metadata(value: Any) -> dict[str, Any]:
    metadata = value if isinstance(value, dict) else {}
    allowed_keys = {"request_id", "agent_run_id"}
    return {key: metadata[key] for key in allowed_keys if key in metadata and metadata[key] is not None}


def _json_object(value: dict[str, Any]) -> str:
    return json.dumps(value or {}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _json_list(value: list[Any]) -> str:
    return json.dumps(value or [], ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        if isinstance(parsed, list):
            return [str(item) for item in parsed]
    return []


def _optional_date(value: Any) -> str | None:
    text = _text(value)
    return text[:10] if text else None


def _optional_text(value: Any) -> str | None:
    text = _text(value)
    return text or None


def _text(value: Any) -> str:
    return str(value or "").strip()


def _clamp_limit(value: int) -> int:
    return max(1, min(100, int(value or 50)))
