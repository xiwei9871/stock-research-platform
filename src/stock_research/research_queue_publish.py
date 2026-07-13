from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from stock_research.config import SETTINGS
from stock_research.research_objects import record_publication_snapshot, stable_id
from stock_research.research_publication_package import build_research_publication_package, research_publication_package_read_model


DEFAULT_OUTPUT_ROOT = Path("outputs/research/research_queue_publish_v1")
INTERNAL_PUBLICATION_CHANNEL = "research_queue_internal"


def publish_research_queue(
    trade_date: str,
    *,
    dry_run: bool = True,
    commit_snapshot: bool = False,
    confirm_internal_publication: bool = False,
    output_dir: str | Path | None = None,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    if commit_snapshot and not confirm_internal_publication:
        raise ValueError("confirm_internal_publication_required")

    package = research_publication_package_read_model(build_research_publication_package(trade_date, service=service))
    gate_status = str((package.get("gate") or {}).get("status") or "empty")
    publishable = bool(package.get("publishable"))
    mode = "snapshot_commit" if commit_snapshot else "dry_run"
    run_id = stable_id("research_queue_publish", trade_date, mode, package.get("package_id"), package.get("summary"))

    status = _status_for_gate(gate_status, publishable=publishable, commit_snapshot=commit_snapshot)
    snapshot_id: str | None = None
    snapshot_written = False

    if publishable and commit_snapshot and confirm_internal_publication:
        snapshot_id = record_publication_snapshot(
            _snapshot_payload(package=package, run_id=run_id),
            service=service,
        )
        snapshot_written = True
        status = "snapshot_recorded"

    result = _result_read_model(
        {
            "trade_date": trade_date,
            "run_id": run_id,
            "mode": mode,
            "status": status,
            "publishable": publishable,
            "snapshot_written": snapshot_written,
            "publication_snapshot_id": snapshot_id,
            "gate_status": gate_status,
            "actual_external_delivery_enabled": False,
            "internal_snapshot_enabled": publishable,
            "package_id": str(package.get("package_id") or ""),
            "blockers": package.get("blockers") or [],
            "warnings": package.get("warnings") or [],
            "artifact_paths": {},
        }
    )
    return _write_outputs(result=result, output_dir=output_dir, trade_date=trade_date)


def write_research_queue_publish_entrypoint_scaffold_doc(output_dir: str | Path) -> str:
    resolved = Path(output_dir)
    resolved.mkdir(parents=True, exist_ok=True)
    path = resolved / "research_queue_publish_entrypoint_scaffold.md"
    path.write_text(_scaffold_markdown(), encoding="utf-8")
    return str(path)


def _snapshot_payload(*, package: dict[str, Any], run_id: str) -> dict[str, Any]:
    snapshot_payload = dict(package)
    snapshot_payload.update(
        {
            "run_id": run_id,
            "channel": INTERNAL_PUBLICATION_CHANNEL,
            "external_delivery_enabled": False,
        }
    )
    return {
        "trade_date": package["trade_date"],
        "channel": INTERNAL_PUBLICATION_CHANNEL,
        "title": f"Research Queue Internal Snapshot {package['trade_date']}",
        "payload": snapshot_payload,
        "created_by": "research_queue_publish",
    }


def _status_for_gate(gate_status: str, *, publishable: bool, commit_snapshot: bool) -> str:
    if gate_status == "empty":
        return "empty"
    if gate_status == "failed":
        return "failed"
    if not publishable:
        return "blocked"
    return "snapshot_ready" if commit_snapshot else "dry_run_ready"


def _write_outputs(*, result: dict[str, Any], output_dir: str | Path | None, trade_date: str) -> dict[str, Any]:
    resolved = Path(output_dir) if output_dir is not None else DEFAULT_OUTPUT_ROOT / trade_date
    resolved.mkdir(parents=True, exist_ok=True)
    json_path = resolved / "research_queue_publish_result.json"
    markdown_path = resolved / "research_queue_publish_summary.md"
    result_with_paths = dict(result)
    result_with_paths["artifact_paths"] = {
        "result_json": str(json_path),
        "summary_markdown": str(markdown_path),
    }
    json_path.write_text(json.dumps(result_with_paths, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(_result_markdown(result_with_paths), encoding="utf-8")
    return result_with_paths


def _result_read_model(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "trade_date": str(payload.get("trade_date") or ""),
        "run_id": str(payload.get("run_id") or ""),
        "mode": str(payload.get("mode") or "dry_run"),
        "status": str(payload.get("status") or "blocked"),
        "publishable": bool(payload.get("publishable")),
        "snapshot_written": bool(payload.get("snapshot_written")),
        "publication_snapshot_id": payload.get("publication_snapshot_id") if payload.get("publication_snapshot_id") else None,
        "gate_status": str(payload.get("gate_status") or "empty"),
        "actual_external_delivery_enabled": False,
        "internal_snapshot_enabled": bool(payload.get("internal_snapshot_enabled")),
        "package_id": str(payload.get("package_id") or ""),
        "blockers": [_notice(item) for item in payload.get("blockers") or []],
        "warnings": [_notice(item) for item in payload.get("warnings") or []],
        "artifact_paths": _artifact_paths(payload.get("artifact_paths")),
    }


def _notice(value: Any) -> dict[str, Any]:
    item = value if isinstance(value, dict) else {}
    return {
        "code": str(item.get("code") or ""),
        "message": str(item.get("message") or ""),
        "count": _int(item.get("count")),
    }


def _artifact_paths(value: Any) -> dict[str, str]:
    paths = value if isinstance(value, dict) else {}
    return {str(key): str(val) for key, val in paths.items() if val}


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _result_markdown(result: dict[str, Any]) -> str:
    lines = [
        f"# Research Queue Publish {result['trade_date']}",
        "",
        f"- run_id={result['run_id']}",
        f"- mode={result['mode']}",
        f"- status={result['status']}",
        f"- publishable={str(result['publishable']).lower()}",
        f"- snapshot_written={str(result['snapshot_written']).lower()}",
        f"- publication_snapshot_id={result['publication_snapshot_id'] or ''}",
        f"- gate_status={result['gate_status']}",
        f"- actual_external_delivery_enabled={str(result['actual_external_delivery_enabled']).lower()}",
        "",
        "## Blockers",
    ]
    blockers = result.get("blockers") or []
    if blockers:
        lines.extend(f"- {item['code']}: {item['message']} ({item['count']})" for item in blockers)
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
            "This command never sends external notifications and never calls strategy EOD publication.",
            "Internal publication snapshots require commit-snapshot, explicit confirmation, and a passing research gate.",
        ]
    )
    return "\n".join(lines) + "\n"


def _scaffold_markdown() -> str:
    return """# Research Queue Publish Entrypoint Scaffold

Canonical entrypoint: `stock-research research-queue-publish` backed by `stock_research.research_queue_publish.publish_research_queue`.

## Boundaries

- `p5/notifications.py` remains downstream delivery. It is not called by this entrypoint.
- `strategy_eod_publish.py` remains strategy EOD publication. It is not called by this entrypoint.
- This entrypoint does not send Feishu, email, OpenClaw, or any external notification.
- This entrypoint does not create trading signals and does not touch the trading chain.

## Three layers

1. Dry-run: default mode. Builds a research publication package and writes local result artifacts only.
2. Internal snapshot commit: requires `--commit-snapshot --confirm-internal-publication` and a `research_ready` gate.
3. External delivery: not connected in this scaffold.

## `publication_snapshot` write conditions

The entrypoint writes `research.publication_snapshot` only when all are true:

- research publish gate is `research_ready`;
- `commit_snapshot=True`;
- `confirm_internal_publication=True`;
- channel is fixed to `research_queue_internal`;
- payload is the whitelisted research publication package.

Blocked, empty, or failed gates never write a snapshot. The reason is audit integrity: a blocked queue is not an internal publication decision.

## Future external delivery

Future delivery should run after the internal snapshot succeeds, and should receive the snapshot/package id rather than rebuilding state independently.
"""
