from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from stock_research.config import SETTINGS
from stock_research.dashboard.research_publication_snapshots import get_publication_snapshot
from stock_research.research_external_delivery_attempts import record_external_delivery_attempt
from stock_research.research_objects import stable_id


DEFAULT_OUTPUT_ROOT = Path("outputs/research/research_external_delivery_boundary_v1")
BOUNDARY_REPORT = "external_delivery_boundary_report.md"
SUPPORTED_CHANNELS = {"feishu_preview", "email_preview", "markdown_export"}
DRY_RUN_WARNING = "External delivery is not connected in this version."


def build_research_external_delivery_plan(
    publication_snapshot_id: str,
    *,
    channel: str = "feishu_preview",
    dry_run: bool = True,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    selected_channel = str(channel or "feishu_preview")
    if selected_channel not in SUPPORTED_CHANNELS:
        return _empty_plan(
            publication_snapshot_id=publication_snapshot_id,
            channel=selected_channel,
            status="unsupported_channel",
            dry_run=True,
            warnings=[f"Unsupported external delivery channel: {selected_channel}", DRY_RUN_WARNING],
        )

    snapshot = get_publication_snapshot(publication_snapshot_id, service=service)
    if snapshot is None:
        return _empty_plan(
            publication_snapshot_id=publication_snapshot_id,
            channel=selected_channel,
            status="snapshot_not_found",
            dry_run=True,
            warnings=[f"Publication snapshot not found: {publication_snapshot_id}", DRY_RUN_WARNING],
        )

    detail = snapshot if isinstance(snapshot, dict) else {}
    gate = detail.get("gate") if isinstance(detail.get("gate"), dict) else {}
    summary = detail.get("summary") if isinstance(detail.get("summary"), dict) else {}
    sections = [_message_section(item) for item in (detail.get("sections") if isinstance(detail.get("sections"), list) else [])]
    trade_date = str(detail.get("trade_date") or "")
    package_id = str(detail.get("package_id") or "")
    gate_status = str(gate.get("status") or "")
    plan = {
        "delivery_plan_id": stable_id(
            "research_external_delivery_plan",
            publication_snapshot_id,
            selected_channel,
            package_id,
            gate_status,
        ),
        "publication_snapshot_id": str(publication_snapshot_id or ""),
        "trade_date": trade_date,
        "channel": selected_channel,
        "dry_run": True,
        "external_send_enabled": False,
        "status": "preview_ready" if dry_run else "blocked",
        "message": {
            "title": f"Research Queue Snapshot {trade_date}".strip(),
            "summary": _message_summary(summary, gate_status),
            "sections": sections,
        },
        "source": {
            "package_id": package_id,
            "gate_status": gate_status,
            "snapshot_channel": str(detail.get("channel") or ""),
        },
        "blockers": [_notice(item) for item in detail.get("blockers") or []],
        "warnings": _warnings(detail.get("warnings")),
    }
    if not dry_run:
        plan["warnings"].append("Live external delivery is disabled; this plan remains dry-run only.")
    return delivery_plan_read_model(plan)


def delivery_plan_read_model(payload: dict[str, Any]) -> dict[str, Any]:
    message = payload.get("message") if isinstance(payload.get("message"), dict) else {}
    source = payload.get("source") if isinstance(payload.get("source"), dict) else {}
    return {
        "delivery_plan_id": str(payload.get("delivery_plan_id") or ""),
        "publication_snapshot_id": str(payload.get("publication_snapshot_id") or ""),
        "trade_date": str(payload.get("trade_date") or ""),
        "channel": str(payload.get("channel") or ""),
        "dry_run": True,
        "external_send_enabled": False,
        "status": str(payload.get("status") or "blocked"),
        "message": {
            "title": str(message.get("title") or ""),
            "summary": str(message.get("summary") or ""),
            "sections": [_message_section(item) for item in message.get("sections") or []],
        },
        "source": {
            "package_id": str(source.get("package_id") or ""),
            "gate_status": str(source.get("gate_status") or ""),
            "snapshot_channel": str(source.get("snapshot_channel") or ""),
        },
        "blockers": [_notice(item) for item in payload.get("blockers") or []],
        "warnings": [str(item) for item in payload.get("warnings") or [] if str(item)],
    }


def run_research_external_delivery_plan(
    *,
    publication_snapshot_id: str,
    channel: str = "feishu_preview",
    dry_run: bool = True,
    record_attempt: bool = False,
    output_dir: str | Path | None = None,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    plan = build_research_external_delivery_plan(
        publication_snapshot_id,
        channel=channel,
        dry_run=dry_run,
        service=service,
    )
    resolved = Path(output_dir) if output_dir is not None else DEFAULT_OUTPUT_ROOT / _path_token(publication_snapshot_id)
    resolved.mkdir(parents=True, exist_ok=True)
    json_path = resolved / "research_external_delivery_plan.json"
    markdown_path = resolved / "research_external_delivery_plan.md"
    result = dict(plan)
    delivery_attempt_id = None
    if record_attempt:
        delivery_attempt_id = record_external_delivery_attempt(plan, created_by="research_external_delivery_plan", service=service)
    result["delivery_attempt_id"] = delivery_attempt_id
    result["attempt_recorded"] = bool(delivery_attempt_id)
    result["attempt_status"] = _attempt_status_for_plan(plan["status"]) if delivery_attempt_id else ""
    result["json_path"] = str(json_path)
    result["markdown_path"] = str(markdown_path)
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(_delivery_plan_markdown(result), encoding="utf-8")
    return result


def write_external_delivery_boundary_report(output_dir: str | Path = DEFAULT_OUTPUT_ROOT) -> str:
    resolved = Path(output_dir)
    resolved.mkdir(parents=True, exist_ok=True)
    path = resolved / BOUNDARY_REPORT
    path.write_text(_boundary_report_markdown(), encoding="utf-8")
    return str(path)


def _empty_plan(
    *,
    publication_snapshot_id: str,
    channel: str,
    status: str,
    dry_run: bool,
    warnings: list[str],
) -> dict[str, Any]:
    return delivery_plan_read_model(
        {
            "delivery_plan_id": stable_id("research_external_delivery_plan", publication_snapshot_id, channel, status),
            "publication_snapshot_id": publication_snapshot_id,
            "trade_date": "",
            "channel": channel,
            "dry_run": dry_run,
            "external_send_enabled": False,
            "status": status,
            "message": {"title": "", "summary": "", "sections": []},
            "source": {"package_id": "", "gate_status": "", "snapshot_channel": ""},
            "blockers": [],
            "warnings": warnings,
        }
    )


def _message_summary(summary: dict[str, Any], gate_status: str) -> str:
    return (
        f"Cases {_int(summary.get('case_count'))}, claims {_int(summary.get('claim_count'))}, "
        f"evidence {_int(summary.get('evidence_count'))}, gaps {_int(summary.get('gap_count'))}. "
        f"Gate {gate_status or 'unknown'}."
    )


def _message_section(value: Any) -> dict[str, Any]:
    section = value if isinstance(value, dict) else {}
    items = section.get("items") if isinstance(section.get("items"), list) else []
    return {
        "section_type": str(section.get("section_type") or ""),
        "title": str(section.get("title") or ""),
        "items": [_section_item(item) for item in items],
    }


def _section_item(value: Any) -> dict[str, Any]:
    item = value if isinstance(value, dict) else {}
    allowed = (
        "case_id",
        "trade_date",
        "asset_id",
        "theme",
        "title",
        "review_status",
        "gap_reasons",
        "gap_summary",
        "case_count",
        "claim_count",
        "evidence_count",
        "evidence_link_count",
        "gap_count",
        "pending_gap_count",
        "reviewed_gap_count",
    )
    cleaned: dict[str, Any] = {}
    for key in allowed:
        if key not in item:
            continue
        if key == "gap_reasons":
            cleaned[key] = [str(reason) for reason in item.get(key) or []]
        elif key.endswith("_count") or key in {"evidence_count", "evidence_link_count", "gap_count", "claim_count"}:
            cleaned[key] = _int(item.get(key))
        else:
            cleaned[key] = str(item.get(key) or "")
    return cleaned


def _notice(value: Any) -> dict[str, Any]:
    item = value if isinstance(value, dict) else {}
    return {
        "code": str(item.get("code") or ""),
        "message": str(item.get("message") or ""),
        "count": _int(item.get("count")),
    }


def _warnings(value: Any) -> list[str]:
    warnings = [DRY_RUN_WARNING]
    for item in value or []:
        if isinstance(item, dict):
            message = str(item.get("message") or item.get("code") or "")
        else:
            message = str(item)
        if message and message not in warnings:
            warnings.append(message)
    return warnings


def _delivery_plan_markdown(plan: dict[str, Any]) -> str:
    message = plan.get("message") or {}
    lines = [
        f"# Research External Delivery Plan {plan.get('publication_snapshot_id') or ''}",
        "",
        f"- status={plan['status']}",
        f"- channel={plan['channel']}",
        f"- dry_run={str(plan['dry_run']).lower()}",
        f"- external_send_enabled={str(plan['external_send_enabled']).lower()}",
        f"- trade_date={plan.get('trade_date') or ''}",
        f"- message_title={message.get('title') or ''}",
        f"- sections={len(message.get('sections') or [])}",
        f"- attempt_recorded={str(plan.get('attempt_recorded', False)).lower()}",
        f"- delivery_attempt_id={plan.get('delivery_attempt_id') or ''}",
        "",
        "## Warnings",
    ]
    warnings = plan.get("warnings") or []
    lines.extend(f"- {item}" for item in warnings) if warnings else lines.append("- none")
    lines.extend(
        [
            "",
            "This is an external delivery dry-run plan only.",
            "It does not send Feishu, email, webhooks, or any external notification.",
            "It does not call strategy EOD publication and does not create trading instructions.",
        ]
    )
    return "\n".join(lines) + "\n"


def _attempt_status_for_plan(status: str) -> str:
    if status == "preview_ready":
        return "preview_recorded"
    return str(status or "failed")


def _boundary_report_markdown() -> str:
    return """# Research External Delivery Boundary Report

Generated: 2026-07-08

## Candidate classification

| Category | Candidate | Side effect | Dry-run support | Secret needed | Fit for research snapshot delivery |
| --- | --- | --- | --- | --- | --- |
| downstream delivery candidate | `src/stock_research/p5/notifications.py` | Yes when live send is enabled | Yes, preview/outbox paths exist | Feishu/OpenClaw webhook or token in live mode | Suitable only behind a future adapter after internal snapshot |
| external side-effect function | `P5FeishuSender.send_preview` / OpenClaw sender wrappers | Can perform network send when dry_run is false and live flags allow | Yes | Yes | Adapter target, not canonical publish boundary |
| dry-run/preview function | P5 preview writers | Local JSON/JSONL only | Yes | No | Useful pattern for future adapter previews |
| strategy-only publish | `src/stock_research/strategy_eod_publish.py` | Writes strategy artifacts and manifest rows | Not research-queue scoped | No external token by itself | Not suitable; strategy EOD is separate from research queue publication |
| read-only dashboard display | publication preview, snapshot APIs, HomeCockpit | No | Read-only | No | Display only |
| unrelated/test/legacy | scripts and tests | Mixed | Script-specific | Mixed | Not a delivery boundary |

## Recommended adapter boundary

External delivery must run after internal publication snapshot succeeds. The future adapter should accept a `publication_snapshot_id`, load the whitelisted snapshot read model, build a channel-specific message, and then call a delivery implementation only when live delivery is explicitly enabled.

This version implements only `research-external-delivery-plan`, a dry-run plan builder. It does not call `p5/notifications.py`, does not call `strategy_eod_publish.py`, does not use webhook URLs, and does not write external delivery status.

## Why not send now

- There is no reviewed external delivery adapter contract yet.
- Live Feishu/email credentials should not be exposed through research read models.
- `publication_snapshot` is an internal audit object, not proof of external release.
- Research publication is not a trading signal and must stay separate from strategy EOD publish.
"""


def _path_token(value: str) -> str:
    return str(value or "missing").replace("/", "_").replace(":", "_")


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
