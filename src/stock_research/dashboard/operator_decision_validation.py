from __future__ import annotations

from datetime import date
import re
from typing import Any


_ACTIONS = {"watch", "skip", "follow_up", "add_to_shadow", "remove_from_shadow", "note", "pause", "close"}
_ASSET_ID_RE = re.compile(r"^(?:CN:(?:SH|SZ|BJ):\d{6}|\d{6}\.(?:SH|SZ|BJ)|\d{6})$")
_STATUS_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


def validate_operator_decision_payload(payload: dict[str, Any]) -> None:
    if not isinstance(payload, dict):
        raise ValueError("invalid_payload")

    asset_id = _text(payload.get("asset_id") or payload.get("stock_code"))
    if not asset_id:
        raise ValueError("asset_id_or_stock_code_required")
    if not _ASSET_ID_RE.match(asset_id):
        raise ValueError("invalid_asset_id")

    operator_action = _text(payload.get("operator_action")).lower()
    if operator_action not in _ACTIONS:
        raise ValueError("invalid_operator_action")

    decision_status = _text(payload.get("decision_status") or "open")
    if not _STATUS_RE.match(decision_status):
        raise ValueError("invalid_decision_status")

    decision_date = _parse_date(payload.get("decision_date"), "decision_date") if payload.get("decision_date") else None
    follow_up_date = _parse_date(payload.get("follow_up_date"), "follow_up_date") if payload.get("follow_up_date") else None
    if decision_date and follow_up_date and follow_up_date < decision_date:
        raise ValueError("follow_up_date_before_decision_date")

    source_context = payload.get("source_context") or {}
    if not isinstance(source_context, (dict, str)):
        raise ValueError("invalid_source_context")

    tags = payload.get("tags") or []
    if not isinstance(tags, (list, str)):
        raise ValueError("invalid_tags")


def _parse_date(value: Any, field: str) -> date:
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise ValueError(f"invalid_{field}") from exc


def _text(value: Any) -> str:
    return str(value or "").strip()
