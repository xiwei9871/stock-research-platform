from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd


DECISION_STATUSES = [
    "continue_shadow_observation",
    "request_more_data",
    "open_research_follow_up",
    "deprioritize_shadow_group",
]

DEFAULT_SHADOW_REVIEW_DECISION_RULES = {
    "continue_observing": "continue_shadow_observation",
    "needs_more_data": "request_more_data",
    "investigate_data_quality": "request_more_data",
    "deprioritize_review": "deprioritize_shadow_group",
    "research_follow_up_candidate": "open_research_follow_up",
}

_DECISION_BUCKETS = {
    "continue_shadow_observation": "observe",
    "request_more_data": "data_needed",
    "open_research_follow_up": "research_follow_up",
    "deprioritize_shadow_group": "deprioritize",
}

_REQUIRED_NEXT_ACTION = {
    "continue_shadow_observation": "Continue shadow observation and review again after more outcomes accrue.",
    "request_more_data": "Collect additional outcome or data-quality evidence before changing the research state.",
    "open_research_follow_up": "Create a separately scoped research follow-up before any production consideration.",
    "deprioritize_shadow_group": "Reduce review priority unless new evidence changes the group profile.",
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


def build_shadow_review_decisions_from_rows(
    rows: list[dict[str, Any]],
    *,
    run_id: str,
    decision_date: str,
    operator_id: str,
) -> dict[str, Any]:
    """Return the JSON-serializable P16 shadow review decision payload."""
    normalized_rows = [_normalize_review_row(row) for row in rows]
    groups = [
        _decision_group(row, run_id=run_id)
        for row in normalized_rows
    ]
    return {
        "run_id": str(run_id),
        "decision_date": str(decision_date),
        "operator_id": str(operator_id),
        "status": "shadow_review_decisions_ready" if groups else "no_shadow_review_groups_recorded",
        "manual_review_required": True,
        "auto_trade_enabled": False,
        "production_watchlist_enabled": False,
        "production_write_enabled": False,
        "source_p15_review_run_ids": sorted(
            {
                str(row["run_id"])
                for row in normalized_rows
                if not _is_missing(row.get("run_id")) and str(row.get("run_id")).strip()
            }
        ),
        "group_count": int(len(groups)),
        "groups": groups,
    }


def build_shadow_review_decisions(
    *,
    p15_review: dict[str, Any],
    run_id: str,
    decision_date: str,
    operator_id: str,
) -> dict[str, Any]:
    """Return a P16 decision artifact from a P15 review artifact."""
    _reject_unsafe_execution_fields(p15_review)
    _validate_safety_fields(p15_review)
    rows = _p15_artifact_rows(p15_review)
    return build_shadow_review_decisions_from_rows(
        rows,
        run_id=run_id,
        decision_date=decision_date,
        operator_id=operator_id,
    )


def write_shadow_review_decisions(decisions: dict[str, Any], output_dir: str | Path) -> dict[str, str]:
    """Write JSON, group CSV, and Markdown P16 decision artifacts."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    decision_date = _safe_path_part(decisions.get("decision_date") or "unknown-date")
    stem = f"operator_shadow_review_decisions_{decision_date}"

    json_path = output_path / f"{stem}.json"
    groups_csv_path = output_path / f"{stem}_groups.csv"
    markdown_path = output_path / f"{stem}.md"

    payload = _json_safe(decisions)
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    pd.DataFrame(_csv_safe_rows(payload.get("groups", [])), columns=_group_columns()).to_csv(
        groups_csv_path,
        index=False,
    )
    markdown_path.write_text(_render_shadow_review_decisions_markdown(payload), encoding="utf-8")
    return {
        "json_path": str(json_path),
        "groups_csv_path": str(groups_csv_path),
        "markdown_path": str(markdown_path),
    }


def _p15_artifact_rows(p15_review: dict[str, Any]) -> list[dict[str, Any]]:
    p15_run_id = _text_or_empty(p15_review.get("run_id"))
    rows = []
    for item in p15_review.get("groups") or []:
        if not isinstance(item, dict):
            raise ValueError("invalid_p15_review_group")
        row = dict(item)
        if p15_run_id and (_is_missing(row.get("run_id")) or str(row.get("run_id")).strip() == ""):
            row["run_id"] = p15_run_id
        rows.append(row)
    return rows


def _normalize_review_row(row: dict[str, Any]) -> dict[str, Any]:
    _reject_unsafe_execution_fields(row)
    _validate_safety_fields(row)
    normalized = dict(row)
    normalized["manual_review_required"] = True
    normalized["auto_trade_enabled"] = False
    normalized["production_watchlist_enabled"] = False
    normalized["production_write_enabled"] = False
    return normalized


def _decision_group(row: dict[str, Any], *, run_id: str) -> dict[str, Any]:
    review_status = _required_text(row, "review_status")
    if review_status not in DEFAULT_SHADOW_REVIEW_DECISION_RULES:
        raise ValueError(f"unknown_review_status: {review_status}")
    decision_status = DEFAULT_SHADOW_REVIEW_DECISION_RULES[review_status]
    source_group_id = _required_text(row, "review_group_id")
    digest = hashlib.sha256(f"{run_id}|{source_group_id}|{decision_status}".encode("utf-8")).hexdigest()[:16]
    return _json_safe(
        {
            "decision_group_id": f"operator_shadow_review_decision:{run_id}:{digest}",
            "run_id": str(run_id),
            "source_p15_review_group_id": source_group_id,
            "source_p15_review_run_id": _required_text(row, "run_id"),
            "source_p14_analytics_group_id": _text_or_empty(row.get("source_p14_analytics_group_id")),
            "source_p14_analytics_run_id": _text_or_empty(row.get("source_p14_analytics_run_id")),
            "group_key": _text_or_empty(row.get("group_key")),
            "shadow_layer": _text_or_empty(row.get("shadow_layer")),
            "shadow_status": _text_or_empty(row.get("shadow_status")),
            "sample_count": _int_value(row.get("sample_count")),
            "complete_count": _int_value(row.get("complete_count")),
            "insufficient_data_count": _int_value(row.get("insufficient_data_count")),
            "review_status": review_status,
            "review_bucket": _text_or_empty(row.get("review_bucket")),
            "decision_status": decision_status,
            "decision_bucket": _DECISION_BUCKETS[decision_status],
            "decision_reason": _decision_reason(row, decision_status),
            "required_next_action": _REQUIRED_NEXT_ACTION[decision_status],
            "evidence_summary": _text_or_empty(row.get("evidence_summary")),
            "risk_notes": _text_or_empty(row.get("risk_notes")),
            "next_research_question": _text_or_empty(row.get("next_research_question")),
            "manual_review_required": True,
            "auto_trade_enabled": False,
            "production_watchlist_enabled": False,
            "production_write_enabled": False,
        }
    )


def _decision_reason(row: dict[str, Any], decision_status: str) -> str:
    review_status = _text_or_empty(row.get("review_status"))
    review_bucket = _text_or_empty(row.get("review_bucket"))
    group_key = _text_or_empty(row.get("group_key"))
    return (
        f"P15 review status {review_status} in bucket {review_bucket} maps to "
        f"{decision_status} for group {group_key}."
    )


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


def _group_columns() -> list[str]:
    return [
        "decision_group_id",
        "run_id",
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
        for key in _group_columns():
            value = row.get(key)
            if isinstance(value, (dict, list)):
                value = json.dumps(value, ensure_ascii=False, sort_keys=True)
            safe[key] = value
        safe_rows.append(safe)
    return safe_rows


def _render_shadow_review_decisions_markdown(decisions: dict[str, Any]) -> str:
    lines = [
        "# P16 Shadow Review Decisions",
        "",
        f"- Run ID: `{decisions.get('run_id')}`",
        f"- Decision date: `{decisions.get('decision_date')}`",
        f"- Operator: `{decisions.get('operator_id')}`",
        f"- Status: `{decisions.get('status')}`",
        f"- Group count: `{decisions.get('group_count')}`",
        "",
        "## Safety",
        "",
        f"- manual_review_required: `{decisions.get('manual_review_required')}`",
        f"- auto_trade_enabled: `{decisions.get('auto_trade_enabled')}`",
        f"- production_watchlist_enabled: `{decisions.get('production_watchlist_enabled')}`",
        f"- production_write_enabled: `{decisions.get('production_write_enabled')}`",
        "",
        "## Groups",
        "",
    ]
    for group in decisions.get("groups", []):
        lines.extend(
            [
                f"### {group.get('group_key') or group.get('decision_group_id')}",
                "",
                f"- P15 review status: `{group.get('review_status')}`",
                f"- P16 decision status: `{group.get('decision_status')}`",
                f"- Decision bucket: `{group.get('decision_bucket')}`",
                f"- Required next action: {group.get('required_next_action')}",
                f"- Decision reason: {group.get('decision_reason')}",
                f"- Evidence: {group.get('evidence_summary')}",
                f"- Risk: {group.get('risk_notes')}",
                f"- Next research question: {group.get('next_research_question')}",
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
