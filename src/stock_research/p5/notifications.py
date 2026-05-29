from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Iterable, Any


SMOKE_STATUS_TO_SEVERITY = {
    "pass": "ok",
    "warning": "warning",
    "blocked": "critical",
}


class P5NotificationError(ValueError):
    pass


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


def _generated_at() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00",
        "Z",
    )
