from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all
from stock_research.research_objects import stable_id


DEFAULT_AUDIT_OUTPUT_ROOT = Path("outputs/research/research_external_delivery_attempt_log_v1")
ALLOWED_MODES = {"dry_run", "sandbox", "live"}
ALLOWED_CREATE_MODE = "dry_run"
ALLOWED_STATUSES = {"preview_recorded", "snapshot_not_found", "unsupported_channel", "blocked", "failed"}
FORBIDDEN_STATUSES = {"sent", "delivered", "live_success"}
SECRET_KEY_FRAGMENTS = {"webhook", "token", "secret", "authorization", "api_key", "password"}
TRADING_KEYS = {"auto_trade", "auto_trade_enabled", "trading_instruction", "trade", "buy", "sell", "order"}


def record_external_delivery_attempt(
    plan: dict[str, Any],
    *,
    created_by: str = "system",
    service: str = SETTINGS.research_service,
) -> str:
    cleaned = validate_external_delivery_attempt_plan(plan, created_by=created_by)
    delivery_attempt_id = stable_id(
        "external_delivery_attempt",
        cleaned["publication_snapshot_id"],
        cleaned["channel"],
        cleaned["status"],
        cleaned["delivery_plan_id"],
        time.time_ns(),
    )
    attempt_params = {
        "delivery_attempt_id": delivery_attempt_id,
        **cleaned,
        "metadata": _json(cleaned["metadata"]),
    }
    attempt_sql = """
    INSERT INTO research.external_delivery_attempt (
        delivery_attempt_id, publication_snapshot_id, trade_date, channel,
        mode, status, external_send_enabled, dry_run, delivery_plan_id,
        message_title, message_hash, created_by, finished_at,
        error_code, error_message, metadata
    )
    VALUES (
        %(delivery_attempt_id)s, %(publication_snapshot_id)s, %(trade_date)s,
        %(channel)s, %(mode)s, %(status)s, %(external_send_enabled)s,
        %(dry_run)s, %(delivery_plan_id)s, %(message_title)s,
        %(message_hash)s, %(created_by)s, now(), %(error_code)s,
        %(error_message)s, %(metadata)s::jsonb
    )
    """
    event_sql = """
    INSERT INTO research.external_delivery_event (
        delivery_event_id, delivery_attempt_id, event_index, event_type, status, payload
    )
    VALUES (
        %(delivery_event_id)s, %(delivery_attempt_id)s, %(event_index)s,
        %(event_type)s, %(status)s, %(payload)s::jsonb
    )
    """
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute(attempt_sql, attempt_params)
            for index, event in enumerate(_events_for_attempt(cleaned)):
                cur.execute(
                    event_sql,
                    {
                        "delivery_event_id": stable_id("external_delivery_event", delivery_attempt_id, index, event["event_type"]),
                        "delivery_attempt_id": delivery_attempt_id,
                        "event_index": index,
                        "event_type": event["event_type"],
                        "status": event["status"],
                        "payload": _json(event["payload"]),
                    },
                )
    return delivery_attempt_id


def list_external_delivery_attempts(
    *,
    publication_snapshot_id: str | None = None,
    trade_date: str | None = None,
    channel: str | None = None,
    limit: int = 50,
    service: str = SETTINGS.research_service,
) -> list[dict[str, Any]]:
    clauses = ["1=1"]
    params: list[Any] = []
    if publication_snapshot_id:
        clauses.append("publication_snapshot_id = %s")
        params.append(publication_snapshot_id)
    if trade_date:
        clauses.append("trade_date = %s")
        params.append(trade_date)
    if channel:
        clauses.append("channel = %s")
        params.append(channel)
    params.append(_clamp_limit(limit))
    sql = f"""
    SELECT
        delivery_attempt_id,
        publication_snapshot_id,
        trade_date::text AS trade_date,
        channel,
        mode,
        status,
        dry_run,
        external_send_enabled,
        delivery_plan_id,
        message_title,
        created_by,
        created_at::text AS created_at,
        error_code,
        error_message
    FROM research.external_delivery_attempt
    WHERE {" AND ".join(clauses)}
    ORDER BY created_at DESC, delivery_attempt_id DESC
    LIMIT %s
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, params)
    return [external_delivery_attempt_list_item_read_model(row) for row in rows]


def get_external_delivery_attempt(
    delivery_attempt_id: str,
    *,
    service: str = SETTINGS.research_service,
) -> dict[str, Any] | None:
    attempt_sql = """
    SELECT
        delivery_attempt_id,
        publication_snapshot_id,
        trade_date::text AS trade_date,
        channel,
        mode,
        status,
        dry_run,
        external_send_enabled,
        delivery_plan_id,
        message_title,
        created_by,
        created_at::text AS created_at,
        finished_at::text AS finished_at,
        error_code,
        error_message,
        metadata
    FROM research.external_delivery_attempt
    WHERE delivery_attempt_id = %s
    LIMIT 1
    """
    events_sql = """
    SELECT
        delivery_event_id,
        delivery_attempt_id,
        event_index,
        event_type,
        status,
        payload,
        created_at::text AS created_at
    FROM research.external_delivery_event
    WHERE delivery_attempt_id = %s
    ORDER BY event_index ASC
    """
    with connect(service) as conn:
        attempts = fetch_all(conn, attempt_sql, [delivery_attempt_id])
        if not attempts:
            return None
        events = fetch_all(conn, events_sql, [delivery_attempt_id])
    return external_delivery_attempt_detail_read_model(attempts[0], events)


def run_research_external_delivery_attempt_audit(
    *,
    publication_snapshot_id: str,
    output_dir: str | Path | None = None,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    attempts = list_external_delivery_attempts(
        publication_snapshot_id=publication_snapshot_id,
        limit=100,
        service=service,
    )
    latest = attempts[0] if attempts else None
    status_distribution: dict[str, int] = {}
    channels = sorted({item["channel"] for item in attempts if item.get("channel")})
    for item in attempts:
        status = str(item.get("status") or "")
        status_distribution[status] = status_distribution.get(status, 0) + 1
    result = {
        "publication_snapshot_id": publication_snapshot_id,
        "attempt_count": len(attempts),
        "latest_attempt_id": latest["delivery_attempt_id"] if latest else None,
        "channels": channels,
        "dry_run_count": sum(1 for item in attempts if item.get("dry_run")),
        "live_count": sum(1 for item in attempts if item.get("mode") == "live"),
        "external_send_enabled_count": sum(1 for item in attempts if item.get("external_send_enabled")),
        "status_distribution": status_distribution,
        "latest_errors": [
            {"delivery_attempt_id": item["delivery_attempt_id"], "error_code": item["error_code"], "error_message": item["error_message"]}
            for item in attempts
            if item.get("error_code") or item.get("error_message")
        ][:5],
        "warnings": [] if attempts else ["attempt_count=0"],
        "attempts": attempts,
    }
    return _write_audit_outputs(result=result, output_dir=output_dir, publication_snapshot_id=publication_snapshot_id)


def validate_external_delivery_attempt_plan(plan: dict[str, Any], *, created_by: str) -> dict[str, Any]:
    if not isinstance(plan, dict):
        raise ValueError("external_delivery_plan_required")
    _reject_forbidden_content(plan)
    mode = _text(plan.get("mode") or "dry_run")
    if mode not in ALLOWED_MODES:
        raise ValueError("invalid_external_delivery_mode")
    if mode != ALLOWED_CREATE_MODE:
        raise ValueError("external_delivery_live_mode_disabled")
    if plan.get("dry_run") is not True:
        raise ValueError("external_delivery_attempt_requires_dry_run")
    if bool(plan.get("external_send_enabled")):
        raise ValueError("external_send_must_be_disabled")
    raw_status = _text(plan.get("status") or "failed")
    if raw_status in FORBIDDEN_STATUSES:
        raise ValueError("external_delivery_status_forbidden")
    status = _attempt_status(raw_status)
    if status in FORBIDDEN_STATUSES:
        raise ValueError("external_delivery_status_forbidden")
    if status not in ALLOWED_STATUSES:
        status = "failed"
    message = plan.get("message") if isinstance(plan.get("message"), dict) else {}
    return {
        "publication_snapshot_id": _text(plan.get("publication_snapshot_id")),
        "trade_date": _optional_date(plan.get("trade_date")),
        "channel": _text(plan.get("channel")),
        "mode": "dry_run",
        "status": status,
        "external_send_enabled": False,
        "dry_run": True,
        "delivery_plan_id": _text(plan.get("delivery_plan_id")),
        "message_title": _text(message.get("title")),
        "message_hash": _hash(message),
        "created_by": _text(created_by or "system") or "system",
        "error_code": _error_code(status),
        "error_message": _error_message(status, plan),
        "metadata": _metadata(plan),
    }


def external_delivery_attempt_list_item_read_model(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "delivery_attempt_id": _text(row.get("delivery_attempt_id")),
        "publication_snapshot_id": _text(row.get("publication_snapshot_id")),
        "trade_date": _text(row.get("trade_date")),
        "channel": _text(row.get("channel")),
        "mode": _text(row.get("mode")),
        "status": _text(row.get("status")),
        "dry_run": bool(row.get("dry_run")),
        "external_send_enabled": False,
        "delivery_plan_id": _text(row.get("delivery_plan_id")),
        "message_title": _text(row.get("message_title")),
        "created_by": _text(row.get("created_by")),
        "created_at": _text(row.get("created_at")),
        "error_code": _text(row.get("error_code")),
        "error_message": _text(row.get("error_message")),
    }


def external_delivery_attempt_detail_read_model(row: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
    item = external_delivery_attempt_list_item_read_model(row)
    item["finished_at"] = _text(row.get("finished_at"))
    item["events"] = [external_delivery_event_read_model(event) for event in events]
    item["source_summary"] = {
        "delivery_plan_id": item["delivery_plan_id"],
        "message_title": item["message_title"],
    }
    metadata = _dict(row.get("metadata"))
    item["warnings"] = [str(warning) for warning in metadata.get("warnings") or []]
    return item


def external_delivery_event_read_model(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "delivery_event_id": _text(row.get("delivery_event_id")),
        "delivery_attempt_id": _text(row.get("delivery_attempt_id")),
        "event_index": _int(row.get("event_index")),
        "event_type": _text(row.get("event_type")),
        "status": _text(row.get("status")),
        "payload": _event_payload(row.get("payload")),
        "created_at": _text(row.get("created_at")),
    }


def _events_for_attempt(cleaned: dict[str, Any]) -> list[dict[str, Any]]:
    events = [
        {
            "event_type": "plan_built",
            "status": "ok",
            "payload": {
                "delivery_plan_id": cleaned["delivery_plan_id"],
                "channel": cleaned["channel"],
                "status": cleaned["status"],
            },
        },
        {"event_type": "validation_passed", "status": "ok", "payload": {"mode": "dry_run", "external_send_enabled": False}},
    ]
    if cleaned["status"] in {"snapshot_not_found", "unsupported_channel", "blocked", "failed"}:
        events.append({"event_type": cleaned["status"], "status": cleaned["status"], "payload": {"error_code": cleaned["error_code"]}})
    events.append({"event_type": "dry_run_recorded", "status": cleaned["status"], "payload": {"delivery_attempt_id_status": cleaned["status"]}})
    return events


def _attempt_status(status: str) -> str:
    if status == "preview_ready":
        return "preview_recorded"
    return status


def _metadata(plan: dict[str, Any]) -> dict[str, Any]:
    source = plan.get("source") if isinstance(plan.get("source"), dict) else {}
    return {
        "warnings": [str(warning) for warning in plan.get("warnings") or []],
        "source": {
            "package_id": _text(source.get("package_id")),
            "gate_status": _text(source.get("gate_status")),
            "snapshot_channel": _text(source.get("snapshot_channel")),
        },
    }


def _event_payload(value: Any) -> dict[str, Any]:
    payload = _dict(value)
    allowed = {"delivery_plan_id", "channel", "status", "mode", "external_send_enabled", "error_code", "delivery_attempt_id_status"}
    return {key: payload[key] for key in allowed if key in payload}


def _error_code(status: str) -> str:
    if status in {"snapshot_not_found", "unsupported_channel", "blocked", "failed"}:
        return status
    return ""


def _error_message(status: str, plan: dict[str, Any]) -> str:
    if status == "preview_recorded":
        return ""
    warnings = plan.get("warnings") if isinstance(plan.get("warnings"), list) else []
    return str(warnings[0]) if warnings else status


def _reject_forbidden_content(value: Any) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).lower()
            if any(fragment in normalized for fragment in SECRET_KEY_FRAGMENTS):
                raise ValueError("external_delivery_secret_forbidden")
            if normalized in TRADING_KEYS:
                raise ValueError("external_delivery_trading_field_forbidden")
            _reject_forbidden_content(child)
    elif isinstance(value, list):
        for item in value:
            _reject_forbidden_content(item)


def _write_audit_outputs(
    *,
    result: dict[str, Any],
    output_dir: str | Path | None,
    publication_snapshot_id: str,
) -> dict[str, Any]:
    resolved = Path(output_dir) if output_dir is not None else DEFAULT_AUDIT_OUTPUT_ROOT / _path_token(publication_snapshot_id)
    resolved.mkdir(parents=True, exist_ok=True)
    json_path = resolved / "research_external_delivery_attempt_audit.json"
    markdown_path = resolved / "research_external_delivery_attempt_audit.md"
    result_with_paths = dict(result)
    result_with_paths["json_path"] = str(json_path)
    result_with_paths["markdown_path"] = str(markdown_path)
    json_path.write_text(json.dumps(result_with_paths, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(_audit_markdown(result_with_paths), encoding="utf-8")
    return result_with_paths


def _audit_markdown(result: dict[str, Any]) -> str:
    lines = [
        f"# Research External Delivery Attempt Audit {result['publication_snapshot_id']}",
        "",
        f"- attempt_count={result['attempt_count']}",
        f"- latest_attempt_id={result['latest_attempt_id'] or ''}",
        f"- channels={', '.join(result['channels']) if result['channels'] else ''}",
        f"- dry_run_count={result['dry_run_count']}",
        f"- live_count={result['live_count']}",
        f"- external_send_enabled_count={result['external_send_enabled_count']}",
        "",
        "## Status Distribution",
    ]
    if result["status_distribution"]:
        lines.extend(f"- {status}={count}" for status, count in result["status_distribution"].items())
    else:
        lines.append("- none")
    lines.extend(["", "## Latest Errors"])
    if result["latest_errors"]:
        lines.extend(f"- {item['delivery_attempt_id']}: {item['error_code']} {item['error_message']}" for item in result["latest_errors"])
    else:
        lines.append("- none")
    return "\n".join(lines) + "\n"


def _hash(value: Any) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _json(value: Any) -> str:
    return json.dumps(value or {}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _optional_date(value: Any) -> str | None:
    text = _text(value)
    return text[:10] if text else None


def _text(value: Any) -> str:
    return str(value or "").strip()


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _clamp_limit(value: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = 50
    return max(1, min(parsed, 100))


def _path_token(value: str) -> str:
    return str(value or "missing").replace("/", "_").replace(":", "_")
