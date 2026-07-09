from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from stock_research.config import SETTINGS
from stock_research.dashboard.research_publication_snapshots import list_publication_snapshots


DEFAULT_OUTPUT_ROOT = Path("outputs/research/research_publication_snapshot_audit_v1")


def run_research_publication_snapshot_audit(
    *,
    trade_date: str | None = None,
    output_dir: str | Path | None = None,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    snapshots = list_publication_snapshots(
        trade_date=trade_date,
        channel="research_queue_internal",
        limit=100,
        service=service,
    )
    latest = snapshots[0] if snapshots else None
    result = {
        "trade_date": trade_date or "",
        "snapshot_count": len(snapshots),
        "latest_snapshot_id": latest["publication_snapshot_id"] if latest else None,
        "channels": sorted({item["channel"] for item in snapshots if item.get("channel")}),
        "latest_gate_status": latest["gate_status"] if latest else "",
        "latest_package_summary": _latest_package_summary(latest),
        "blocker_summary": _blocker_summary(snapshots),
        "external_delivery_enabled": any(bool(item.get("actual_external_delivery_enabled")) for item in snapshots),
        "warnings": [] if snapshots else ["snapshot_count=0"],
        "snapshots": snapshots,
    }
    return _write_outputs(result=result, output_dir=output_dir, trade_date=trade_date)


def _latest_package_summary(latest: dict[str, Any] | None) -> dict[str, int]:
    if not latest:
        return {
            "case_count": 0,
            "claim_count": 0,
            "evidence_count": 0,
            "gap_count": 0,
        }
    return {
        "case_count": _int(latest.get("case_count")),
        "claim_count": _int(latest.get("claim_count")),
        "evidence_count": _int(latest.get("evidence_count")),
        "gap_count": _int(latest.get("gap_count")),
    }


def _blocker_summary(snapshots: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "total_blocker_count": sum(_int(item.get("blocker_count")) for item in snapshots),
    }


def _write_outputs(*, result: dict[str, Any], output_dir: str | Path | None, trade_date: str | None) -> dict[str, Any]:
    resolved = Path(output_dir) if output_dir is not None else DEFAULT_OUTPUT_ROOT / (trade_date or "latest")
    resolved.mkdir(parents=True, exist_ok=True)
    json_path = resolved / "research_publication_snapshot_audit.json"
    markdown_path = resolved / "research_publication_snapshot_audit.md"
    result_with_paths = dict(result)
    result_with_paths["json_path"] = str(json_path)
    result_with_paths["markdown_path"] = str(markdown_path)
    json_path.write_text(json.dumps(result_with_paths, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(_markdown(result_with_paths), encoding="utf-8")
    return result_with_paths


def _markdown(result: dict[str, Any]) -> str:
    lines = [
        f"# Research Publication Snapshot Audit {result.get('trade_date') or 'latest'}",
        "",
        f"- snapshot_count={result['snapshot_count']}",
        f"- latest_snapshot_id={result['latest_snapshot_id'] or ''}",
        f"- channels={', '.join(result['channels']) if result['channels'] else ''}",
        f"- latest_gate_status={result['latest_gate_status']}",
        f"- external_delivery_enabled={str(result['external_delivery_enabled']).lower()}",
        "",
        "## Latest Package Summary",
    ]
    for key, value in result["latest_package_summary"].items():
        lines.append(f"- {key}={value}")
    lines.extend(["", "## Snapshots"])
    if result["snapshots"]:
        lines.extend(f"- {item['publication_snapshot_id']} · {item['channel']} · {item['gate_status']}" for item in result["snapshots"])
    else:
        lines.append("- none")
    return "\n".join(lines) + "\n"


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
