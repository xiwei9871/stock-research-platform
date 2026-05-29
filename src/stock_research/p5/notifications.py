from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Iterable, Any
from urllib.parse import urlparse


SMOKE_STATUS_TO_SEVERITY = {
    "pass": "ok",
    "warning": "warning",
    "blocked": "critical",
}


class P5NotificationError(ValueError):
    pass


@dataclass(frozen=True)
class P5FeishuSendConfig:
    webhook_url: str | None
    dry_run: bool
    outbox_dir: str
    allow_live_send: bool
    limit: int | None
    test_mode: bool = False


def parse_p4_smoke_notification(
    lines: Iterable[str],
    *,
    source_command: str | None = None,
    source_log_path: str | None = None,
) -> dict[str, Any]:
    status_line: dict[str, str] | None = None
    checks: list[dict[str, Any]] = []

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue
        parts = line.split("|")
        if parts[0] == "p4_read_model_smoke":
            status_line = _parse_status_line(parts)
        elif parts[0] == "p4_read_model_smoke_check":
            checks.append(_parse_check_line(parts))

    if status_line is None:
        raise P5NotificationError("missing p4_read_model_smoke status line")

    status = status_line["status"]
    if status not in SMOKE_STATUS_TO_SEVERITY:
        raise P5NotificationError(f"unsupported p4 smoke status: {status}")

    notification = {
        "status": status,
        "severity": SMOKE_STATUS_TO_SEVERITY[status],
        "trade_date": status_line["trade_date"],
        "blocker_count": int(status_line["blockers"]),
        "warning_count": int(status_line["warnings"]),
        "checks": checks,
        "failed_checks": [
            check for check in checks if check["status"] in {"warning", "blocked"}
        ],
        "source_command": source_command or "",
        "source_log_path": source_log_path or "",
    }
    notification["message"] = _build_message(notification)
    return notification


def write_p4_smoke_notification_artifacts(
    lines: Iterable[str],
    *,
    output_dir: str | Path,
    source_command: str | None = None,
    source_log_path: str | None = None,
) -> dict[str, Any]:
    notification = parse_p4_smoke_notification(
        lines,
        source_command=source_command,
        source_log_path=source_log_path,
    )
    resolved_output_dir = Path(output_dir)
    resolved_output_dir.mkdir(parents=True, exist_ok=True)
    preview_path = resolved_output_dir / "p5_p4_smoke_notification_preview.json"
    delivery_log_path = resolved_output_dir / "p5_p4_smoke_notification_delivery_log.jsonl"
    generated_at = _generated_at()

    preview = {
        "channel": "p5_p4_smoke_notification",
        "status": "dry_run",
        "dry_run": True,
        "generated_at": generated_at,
        "trade_date": notification["trade_date"],
        "severity": notification["severity"],
        "item_count": 1,
        "notification": notification,
    }
    preview_path.write_text(
        json.dumps(preview, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    log_record = {
        "channel": "p5_p4_smoke_notification",
        "status": "dry_run",
        "dry_run": True,
        "trade_date": notification["trade_date"],
        "severity": notification["severity"],
        "item_count": 1,
        "preview_path": str(preview_path),
    }
    delivery_log_path.write_text(
        json.dumps(log_record, ensure_ascii=True, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    return {
        "channel": "p5_p4_smoke_notification",
        "status": "dry_run",
        "dry_run": True,
        "trade_date": notification["trade_date"],
        "severity": notification["severity"],
        "item_count": 1,
        "preview_path": str(preview_path),
        "delivery_log_path": str(delivery_log_path),
        "output_dir": str(resolved_output_dir),
        "generated_at": generated_at,
    }


def write_p4_smoke_feishu_preview(
    notification_preview_path: str | Path,
    *,
    output_dir: str | Path,
) -> dict[str, Any]:
    source_path = Path(notification_preview_path)
    preview = _load_json_object(source_path, label="P5 notification preview")
    notification = preview.get("notification")
    if not isinstance(notification, dict):
        raise P5NotificationError(f"P5 notification preview missing notification object: {source_path}")

    resolved_output_dir = Path(output_dir)
    resolved_output_dir.mkdir(parents=True, exist_ok=True)
    feishu_preview_path = resolved_output_dir / "p5_p4_smoke_feishu_preview.json"
    delivery_log_path = resolved_output_dir / "p5_p4_smoke_feishu_delivery_log.jsonl"
    generated_at = _generated_at()
    item = _build_feishu_item(notification)
    feishu_preview = {
        "channel": "feishu",
        "status": "dry_run",
        "dry_run": True,
        "generated_at": generated_at,
        "trade_date": str(notification.get("trade_date", "")),
        "source_preview_path": str(source_path),
        "item_count": 1,
        "message_count": 1,
        "items": [item],
    }
    feishu_preview_path.write_text(
        json.dumps(feishu_preview, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    log_record = {
        "channel": "feishu",
        "status": "dry_run",
        "dry_run": True,
        "trade_date": str(notification.get("trade_date", "")),
        "item_count": 1,
        "preview_path": str(feishu_preview_path),
        "source_preview_path": str(source_path),
    }
    delivery_log_path.write_text(
        json.dumps(log_record, ensure_ascii=True, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {
        "channel": "feishu",
        "status": "dry_run",
        "dry_run": True,
        "trade_date": str(notification.get("trade_date", "")),
        "item_count": 1,
        "preview_path": str(feishu_preview_path),
        "delivery_log_path": str(delivery_log_path),
        "output_dir": str(resolved_output_dir),
        "generated_at": generated_at,
    }


class P5FeishuSender:
    def __init__(self, transport: Any) -> None:
        self.transport = transport

    def send_preview(
        self,
        *,
        preview_path: str | Path,
        config: P5FeishuSendConfig,
    ) -> dict[str, Any]:
        source_path = Path(preview_path)
        preview = _load_json_object(source_path, label="P5 Feishu preview")
        items = _limited_items(preview.get("items"), config.limit)
        payload = {
            "channel": "feishu",
            "dry_run": config.dry_run,
            "webhook_host": _webhook_host(config.webhook_url),
            "generated_at": _generated_at(),
            "trade_date": str(preview.get("trade_date", "")),
            "source_preview_path": str(source_path),
            "item_count": len(items),
            "message_count": len(items),
            "items": items,
            "payload": {
                "messages": [
                    item.get("feishu_payload", {})
                    for item in items
                    if isinstance(item, dict)
                ],
            },
        }
        outbox_dir = Path(config.outbox_dir)
        outbox_dir.mkdir(parents=True, exist_ok=True)
        send_preview_path = outbox_dir / "p5_feishu_send_preview.json"
        send_log_path = outbox_dir / "p5_feishu_send_log.jsonl"
        _write_json(send_preview_path, payload)

        if config.dry_run:
            _write_jsonl(
                send_log_path,
                [
                    _send_log_record(
                        status="dry_run",
                        payload=payload,
                        send_preview_path=send_preview_path,
                        sent_count=0,
                        failed_count=0,
                        skipped_count=0,
                    )
                ],
            )
            return _send_result(
                status="dry_run",
                payload=payload,
                send_preview_path=send_preview_path,
                send_log_path=send_log_path,
                sent_count=0,
                failed_count=0,
                skipped_count=0,
            )

        self._validate_live_config(config, payload)
        transport_result = self.transport.send(payload, config)
        _write_jsonl(
            send_log_path,
            [
                _send_log_record(
                    status=str(transport_result.get("status", "sent")),
                    payload=payload,
                    send_preview_path=send_preview_path,
                    sent_count=int(transport_result.get("sent_count", 0)),
                    failed_count=int(transport_result.get("failed_count", 0)),
                    skipped_count=int(transport_result.get("skipped_count", 0)),
                )
            ],
        )
        return _send_result(
            status=str(transport_result.get("status", "sent")),
            payload=payload,
            send_preview_path=send_preview_path,
            send_log_path=send_log_path,
            sent_count=int(transport_result.get("sent_count", 0)),
            failed_count=int(transport_result.get("failed_count", 0)),
            skipped_count=int(transport_result.get("skipped_count", 0)),
        )

    def _validate_live_config(
        self,
        config: P5FeishuSendConfig,
        payload: dict[str, Any],
    ) -> None:
        problems: list[str] = []
        if not config.webhook_url:
            problems.append("webhook_url must be present")
        if not config.allow_live_send:
            problems.append("allow_live_send must be True")
        if config.limit != 1:
            problems.append("limit == 1")
        if not config.test_mode:
            problems.append("test_mode must be True")
        if payload["item_count"] != 1:
            problems.append("exactly one P5 Feishu item is required")
        if problems:
            raise ValueError("live P5 Feishu send requires " + ", ".join(problems))


def _parse_status_line(parts: list[str]) -> dict[str, str]:
    if len(parts) < 9 or (len(parts) - 1) % 2 != 0:
        raise P5NotificationError("malformed p4_read_model_smoke status line")
    fields = _pairs_to_dict(parts[1:])
    required = {"status", "trade_date", "blockers", "warnings"}
    if not required.issubset(fields):
        raise P5NotificationError("malformed p4_read_model_smoke status line")
    _parse_int(fields["blockers"], field_name="blockers")
    _parse_int(fields["warnings"], field_name="warnings")
    return fields


def _parse_check_line(parts: list[str]) -> dict[str, Any]:
    if len(parts) < 3:
        raise P5NotificationError("malformed p4_read_model_smoke_check line")
    details = _pairs_to_dict(parts[3:]) if len(parts) > 3 else {}
    return {
        "name": parts[1],
        "status": parts[2],
        "details": details,
    }


def _pairs_to_dict(parts: list[str]) -> dict[str, str]:
    if len(parts) % 2 != 0:
        raise P5NotificationError("malformed key/value fields")
    return {
        str(parts[index]): str(parts[index + 1])
        for index in range(0, len(parts), 2)
    }


def _parse_int(value: str, *, field_name: str) -> int:
    try:
        return int(value)
    except ValueError as exc:
        raise P5NotificationError(f"malformed integer field: {field_name}") from exc


def _build_message(notification: dict[str, Any]) -> str:
    lines = [
        (
            f"[{notification['severity']}] P4 read-model smoke "
            f"{notification['status']} for {notification['trade_date']}"
        ),
        f"blockers: {int(notification['blocker_count'])}",
        f"warnings: {int(notification['warning_count'])}",
    ]
    for check in notification["failed_checks"]:
        detail = _format_details(check["details"])
        suffix = f" ({detail})" if detail else ""
        lines.append(f"{check['name']}: {check['status']}{suffix}")
    lines.append(f"action: {_action_for_status(notification['status'])}")
    return "\n".join(lines)


def _format_details(details: dict[str, str]) -> str:
    return ", ".join(
        f"{key}={value}"
        for key, value in sorted(details.items())
    )


def _action_for_status(status: str) -> str:
    if status == "blocked":
        return "rerun P4 orchestration and investigate blocked checks"
    if status == "warning":
        return "review warning checks before trusting the scheduled run"
    return "no immediate action"


def _build_feishu_item(notification: dict[str, Any]) -> dict[str, Any]:
    trade_date = str(notification.get("trade_date", ""))
    severity = str(notification.get("severity", "ok"))
    message = str(notification.get("message", ""))
    return {
        "artifact_id": f"p5_p4_smoke_notification:{trade_date}",
        "report_type": "p4_smoke_notification",
        "title": f"P4 read-model smoke {notification.get('status', '')}",
        "summary": _summary_for_notification(notification),
        "severity": severity,
        "operational_severity": severity,
        "requires_attention": severity in {"warning", "critical"},
        "delivery_priority": _delivery_priority(severity),
        "message": message,
        "feishu_payload": {
            "msg_type": "text",
            "content": {"text": message},
        },
        "source_paths": [
            value
            for value in [
                str(notification.get("source_log_path", "")),
            ]
            if value
        ],
    }


def _summary_for_notification(notification: dict[str, Any]) -> str:
    return (
        f"status={notification.get('status', '')}; "
        f"blockers={notification.get('blocker_count', 0)}; "
        f"warnings={notification.get('warning_count', 0)}"
    )


def _delivery_priority(severity: str) -> int:
    if severity == "critical":
        return 1
    if severity == "warning":
        return 5
    return 10


def _limited_items(value: Any, limit: int | None) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise P5NotificationError("P5 Feishu preview items must be a list")
    items = [
        dict(item)
        for item in value
        if isinstance(item, dict)
    ]
    if limit is not None:
        return items[:limit]
    return items


def _load_json_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise P5NotificationError(f"{label} not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise P5NotificationError(f"{label} is not valid JSON: {path}") from exc
    except OSError as exc:
        raise P5NotificationError(f"{label} is not readable: {path}") from exc
    if not isinstance(data, dict):
        raise P5NotificationError(f"{label} must contain a JSON object: {path}")
    return data


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=True, sort_keys=True))
            handle.write("\n")


def _send_log_record(
    *,
    status: str,
    payload: dict[str, Any],
    send_preview_path: Path,
    sent_count: int,
    failed_count: int,
    skipped_count: int,
) -> dict[str, Any]:
    return {
        "channel": "feishu",
        "status": status,
        "dry_run": bool(payload["dry_run"]),
        "trade_date": payload["trade_date"],
        "item_count": payload["item_count"],
        "sent_count": sent_count,
        "failed_count": failed_count,
        "skipped_count": skipped_count,
        "send_preview_path": str(send_preview_path),
        "source_preview_path": payload["source_preview_path"],
        "webhook_host": payload["webhook_host"],
        "generated_at": payload["generated_at"],
    }


def _send_result(
    *,
    status: str,
    payload: dict[str, Any],
    send_preview_path: Path,
    send_log_path: Path,
    sent_count: int,
    failed_count: int,
    skipped_count: int,
) -> dict[str, Any]:
    return {
        "channel": "feishu",
        "status": status,
        "dry_run": bool(payload["dry_run"]),
        "trade_date": payload["trade_date"],
        "item_count": payload["item_count"],
        "sent_count": sent_count,
        "failed_count": failed_count,
        "skipped_count": skipped_count,
        "send_preview_path": str(send_preview_path),
        "send_log_path": str(send_log_path),
        "generated_at": payload["generated_at"],
    }


def _webhook_host(webhook_url: str | None) -> str:
    if not webhook_url:
        return ""
    return urlparse(webhook_url).netloc


def _generated_at() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00",
        "Z",
    )
