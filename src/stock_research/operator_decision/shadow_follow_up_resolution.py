from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd


RESOLUTION_STATUSES = [
    "evidence_collected",
    "research_ticket_opened",
    "continue_observing",
    "deprioritized_closed",
    "stale_unresolved",
]

DEFAULT_SHADOW_FOLLOW_UP_RESOLUTION_RULES = {
    "collect_more_evidence": "stale_unresolved",
    "open_research_ticket": "research_ticket_opened",
    "observe_shadow_group": "continue_observing",
    "deprioritized": "deprioritized_closed",
}

_RESOLUTION_BUCKETS = {
    "evidence_collected": "evidence_ready",
    "research_ticket_opened": "research_follow_up",
    "continue_observing": "observe",
    "deprioritized_closed": "closed_low_priority",
    "stale_unresolved": "needs_operator_review",
}

_RECOMMENDED_RESOLUTION_ACTION = {
    "evidence_collected": "Review collected evidence in a separately scoped research task.",
    "research_ticket_opened": "Track the separate research task outside this review-only artifact.",
    "continue_observing": "Continue shadow observation and revisit after more outcomes accrue.",
    "deprioritized_closed": "Keep the group closed unless new evidence changes the profile.",
    "stale_unresolved": "Review whether the requested evidence has been collected.",
}

_UNSAFE_EXECUTION_FIELDS = {
    "account_id",
    "broker",
    "broker_id",
    "cash",
    "execution_id",
    "fill_id",
    "limit_price",
    "order_id",
    "order_side",
    "position_id",
    "price",
    "quantity",
    "shares",
    "side",
    "stop_price",
    "trade_id",
    "notional",
}


def build_shadow_follow_up_resolution_from_rows(
    rows: list[dict[str, Any]],
    *,
    run_id: str,
    resolution_date: str,
    operator_id: str,
) -> dict[str, Any]:
    """Return the JSON-serializable P18 follow-up resolution payload."""
    normalized_rows = [_normalize_follow_up_row(row) for row in rows]
    items = [_resolution_item(row, run_id=run_id) for row in normalized_rows]
    return {
        "run_id": str(run_id),
        "resolution_date": str(resolution_date),
        "operator_id": str(operator_id),
        "status": "shadow_follow_up_resolution_ready" if items else "no_shadow_follow_up_resolution_items_recorded",
        "manual_review_required": True,
        "auto_trade_enabled": False,
        "production_watchlist_enabled": False,
        "production_write_enabled": False,
        "source_p17_follow_up_run_ids": sorted(
            {
                str(row["run_id"])
                for row in normalized_rows
                if not _is_missing(row.get("run_id")) and str(row.get("run_id")).strip()
            }
        ),
        "item_count": int(len(items)),
        "items": items,
    }


def build_shadow_follow_up_resolution(
    *,
    p17_follow_up: dict[str, Any],
    run_id: str,
    resolution_date: str,
    operator_id: str,
) -> dict[str, Any]:
    """Return a P18 resolution artifact from a P17 follow-up queue artifact."""
    _reject_unsafe_execution_fields(p17_follow_up)
    _validate_safety_fields(p17_follow_up)
    rows = _p17_artifact_rows(p17_follow_up)
    return build_shadow_follow_up_resolution_from_rows(
        rows,
        run_id=run_id,
        resolution_date=resolution_date,
        operator_id=operator_id,
    )


def write_shadow_follow_up_resolution(resolution: dict[str, Any], output_dir: str | Path) -> dict[str, str]:
    """Write JSON, item CSV, and Markdown P18 resolution artifacts."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    resolution_date = _safe_path_part(resolution.get("resolution_date") or "unknown-date")
    stem = f"operator_shadow_follow_up_resolution_{resolution_date}"

    json_path = output_path / f"{stem}.json"
    items_csv_path = output_path / f"{stem}_items.csv"
    markdown_path = output_path / f"{stem}.md"

    payload = _json_safe(resolution)
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    pd.DataFrame(_csv_safe_rows(payload.get("items", [])), columns=_item_columns()).to_csv(
        items_csv_path,
        index=False,
    )
    markdown_path.write_text(_render_shadow_follow_up_resolution_markdown(payload), encoding="utf-8")
    return {
        "json_path": str(json_path),
        "items_csv_path": str(items_csv_path),
        "markdown_path": str(markdown_path),
    }


def _p17_artifact_rows(p17_follow_up: dict[str, Any]) -> list[dict[str, Any]]:
    p17_run_id = _text_or_empty(p17_follow_up.get("run_id"))
    rows = []
    for item in p17_follow_up.get("items") or []:
        if not isinstance(item, dict):
            raise ValueError("invalid_p17_follow_up_item")
        row = dict(item)
        if p17_run_id and (_is_missing(row.get("run_id")) or str(row.get("run_id")).strip() == ""):
            row["run_id"] = p17_run_id
        rows.append(row)
    return rows


def _normalize_follow_up_row(row: dict[str, Any]) -> dict[str, Any]:
    _reject_unsafe_execution_fields(row)
    _validate_safety_fields(row)
    normalized = dict(row)
    normalized["manual_review_required"] = True
    normalized["auto_trade_enabled"] = False
    normalized["production_watchlist_enabled"] = False
    normalized["production_write_enabled"] = False
    return normalized


def _resolution_item(row: dict[str, Any], *, run_id: str) -> dict[str, Any]:
    follow_up_status = _required_text(row, "follow_up_status")
    if follow_up_status not in DEFAULT_SHADOW_FOLLOW_UP_RESOLUTION_RULES:
        raise ValueError(f"unknown_follow_up_status: {follow_up_status}")
    resolution_status = DEFAULT_SHADOW_FOLLOW_UP_RESOLUTION_RULES[follow_up_status]
    source_item_id = _required_text(row, "follow_up_item_id")
    digest = hashlib.sha256(f"{run_id}|{source_item_id}|{resolution_status}".encode("utf-8")).hexdigest()[:16]
    return _json_safe(
        {
            "resolution_item_id": f"operator_shadow_follow_up_resolution:{run_id}:{digest}",
            "run_id": str(run_id),
            "source_p17_follow_up_item_id": source_item_id,
            "source_p17_follow_up_run_id": _required_text(row, "run_id"),
            "source_p16_decision_group_id": _text_or_empty(row.get("source_p16_decision_group_id")),
            "source_p16_decision_run_id": _text_or_empty(row.get("source_p16_decision_run_id")),
            "source_p15_review_group_id": _text_or_empty(row.get("source_p15_review_group_id")),
            "source_p15_review_run_id": _text_or_empty(row.get("source_p15_review_run_id")),
            "source_p14_analytics_group_id": _text_or_empty(row.get("source_p14_analytics_group_id")),
            "source_p14_analytics_run_id": _text_or_empty(row.get("source_p14_analytics_run_id")),
            "group_key": _text_or_empty(row.get("group_key")),
            "shadow_layer": _text_or_empty(row.get("shadow_layer")),
            "shadow_status": _text_or_empty(row.get("shadow_status")),
            "sample_count": _int_value(row.get("sample_count")),
            "complete_count": _int_value(row.get("complete_count")),
            "insufficient_data_count": _int_value(row.get("insufficient_data_count")),
            "review_status": _text_or_empty(row.get("review_status")),
            "review_bucket": _text_or_empty(row.get("review_bucket")),
            "decision_status": _text_or_empty(row.get("decision_status")),
            "decision_bucket": _text_or_empty(row.get("decision_bucket")),
            "follow_up_status": follow_up_status,
            "priority_bucket": _text_or_empty(row.get("priority_bucket")),
            "required_input": _text_or_empty(row.get("required_input")),
            "resolution_status": resolution_status,
            "resolution_bucket": _RESOLUTION_BUCKETS[resolution_status],
            "recommended_resolution_action": _RECOMMENDED_RESOLUTION_ACTION[resolution_status],
            "resolution_reason": _resolution_reason(row, resolution_status),
            "follow_up_reason": _text_or_empty(row.get("follow_up_reason")),
            "decision_reason": _text_or_empty(row.get("decision_reason")),
            "required_next_action": _text_or_empty(row.get("required_next_action")),
            "evidence_summary": _text_or_empty(row.get("evidence_summary")),
            "risk_notes": _text_or_empty(row.get("risk_notes")),
            "next_research_question": _text_or_empty(row.get("next_research_question")),
            "manual_review_required": True,
            "auto_trade_enabled": False,
            "production_watchlist_enabled": False,
            "production_write_enabled": False,
        }
    )


def _resolution_reason(row: dict[str, Any], resolution_status: str) -> str:
    follow_up_status = _text_or_empty(row.get("follow_up_status"))
    group_key = _text_or_empty(row.get("group_key"))
    return f"P17 follow-up status {follow_up_status} maps to {resolution_status} for group {group_key}."


def _validate_safety_fields(payload: dict[str, Any]) -> None:
    if payload.get("manual_review_required") is False:
        raise ValueError("manual_review_required_not_enabled")
    if payload.get("auto_trade_enabled") is True:
        raise ValueError("auto_trade_not_allowed")
    if payload.get("production_watchlist_enabled") is True:
        raise ValueError("production_watchlist_not_allowed")
    if payload.get("production_write_enabled") is True:
        raise ValueError("production_write_not_allowed")


def _reject_unsafe_execution_fields(payload: Any) -> None:
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key in _UNSAFE_EXECUTION_FIELDS and not _is_missing(value):
                raise ValueError(f"unsafe_execution_field: {key}")
            _reject_unsafe_execution_fields(value)
    elif isinstance(payload, list):
        for item in payload:
            _reject_unsafe_execution_fields(item)


def _item_columns() -> list[str]:
    return [
        "resolution_item_id",
        "run_id",
        "source_p17_follow_up_item_id",
        "source_p17_follow_up_run_id",
        "source_p16_decision_group_id",
        "source_p16_decision_run_id",
        "source_p15_review_group_id",
        "source_p15_review_run_id",
        "source_p14_analytics_group_id",
        "source_p14_analytics_run_id",
        "group_key",
        "shadow_layer",
        "shadow_status",
        "sample_count",
        "complete_count",
        "insufficient_data_count",
        "review_status",
        "review_bucket",
        "decision_status",
        "decision_bucket",
        "follow_up_status",
        "priority_bucket",
        "required_input",
        "resolution_status",
        "resolution_bucket",
        "recommended_resolution_action",
        "resolution_reason",
        "follow_up_reason",
        "decision_reason",
        "required_next_action",
        "evidence_summary",
        "risk_notes",
        "next_research_question",
        "manual_review_required",
        "auto_trade_enabled",
        "production_watchlist_enabled",
        "production_write_enabled",
    ]


def _csv_safe_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    safe_rows = []
    for row in rows:
        safe = {}
        for key in _item_columns():
            value = row.get(key)
            if isinstance(value, (dict, list)):
                value = json.dumps(value, ensure_ascii=False, sort_keys=True)
            safe[key] = value
        safe_rows.append(safe)
    return safe_rows


def _render_shadow_follow_up_resolution_markdown(resolution: dict[str, Any]) -> str:
    lines = [
        "# P18 Shadow Follow-up Resolution Review",
        "",
        f"- Run ID: `{resolution.get('run_id')}`",
        f"- Resolution date: `{resolution.get('resolution_date')}`",
        f"- Operator: `{resolution.get('operator_id')}`",
        f"- Status: `{resolution.get('status')}`",
        f"- Item count: `{resolution.get('item_count')}`",
        "",
        "## Safety",
        "",
        f"- manual_review_required: `{resolution.get('manual_review_required')}`",
        f"- auto_trade_enabled: `{resolution.get('auto_trade_enabled')}`",
        f"- production_watchlist_enabled: `{resolution.get('production_watchlist_enabled')}`",
        f"- production_write_enabled: `{resolution.get('production_write_enabled')}`",
        "",
        "## Items",
        "",
    ]
    for item in resolution.get("items", []):
        lines.extend(
            [
                f"### {item.get('group_key') or item.get('resolution_item_id')}",
                "",
                f"- P17 follow-up status: `{item.get('follow_up_status')}`",
                f"- P18 resolution status: `{item.get('resolution_status')}`",
                f"- Resolution bucket: `{item.get('resolution_bucket')}`",
                f"- Recommended action: {item.get('recommended_resolution_action')}",
                f"- Resolution reason: {item.get('resolution_reason')}",
                f"- Evidence: {item.get('evidence_summary')}",
                f"- Risk: {item.get('risk_notes')}",
                f"- Next research question: {item.get('next_research_question')}",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if pd.isna(value) if not isinstance(value, (dict, list, tuple)) else False:
        return None
    return value


def _required_text(row: dict[str, Any], key: str) -> str:
    value = row.get(key)
    if _is_missing(value) or str(value).strip() == "":
        raise ValueError(f"required_field_missing: {key}")
    return str(value)


def _text_or_empty(value: Any) -> str:
    if _is_missing(value):
        return ""
    return str(value)


def _int_value(value: Any) -> int:
    if _is_missing(value):
        return 0
    return int(value)


def _safe_path_part(value: Any) -> str:
    return "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in str(value))


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False
