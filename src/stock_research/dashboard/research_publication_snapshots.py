from __future__ import annotations

import json
from typing import Any

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all
from stock_research.research_publication_package import research_publication_package_read_model


def list_publication_snapshots(
    *,
    trade_date: str | None = None,
    channel: str | None = None,
    limit: int = 50,
    service: str = SETTINGS.research_service,
) -> list[dict[str, Any]]:
    clauses = ["1=1"]
    params: list[Any] = []
    if trade_date:
        clauses.append("trade_date = %s")
        params.append(trade_date)
    if channel:
        clauses.append("channel = %s")
        params.append(channel)
    params.append(_clamp_limit(limit))
    sql = f"""
    SELECT
        publication_snapshot_id,
        trade_date::text AS trade_date,
        channel,
        title,
        payload,
        created_by,
        created_at::text AS created_at
    FROM research.publication_snapshot
    WHERE {" AND ".join(clauses)}
    ORDER BY created_at DESC, publication_snapshot_id DESC
    LIMIT %s
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, params)
    return [publication_snapshot_list_item_read_model(row) for row in rows]


def get_publication_snapshot(
    publication_snapshot_id: str,
    *,
    service: str = SETTINGS.research_service,
) -> dict[str, Any] | None:
    sql = """
    SELECT
        publication_snapshot_id,
        trade_date::text AS trade_date,
        channel,
        title,
        payload,
        created_by,
        created_at::text AS created_at
    FROM research.publication_snapshot
    WHERE publication_snapshot_id = %s
    LIMIT 1
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, [publication_snapshot_id])
    if not rows:
        return None
    return publication_snapshot_detail_read_model(rows[0])


def publication_snapshot_list_item_read_model(row: dict[str, Any]) -> dict[str, Any]:
    package = _package_from_row(row)
    summary = package["summary"]
    gate = package["gate"]
    return {
        "publication_snapshot_id": str(row.get("publication_snapshot_id") or ""),
        "trade_date": str(row.get("trade_date") or ""),
        "channel": str(row.get("channel") or ""),
        "title": str(row.get("title") or ""),
        "created_by": str(row.get("created_by") or ""),
        "created_at": str(row.get("created_at") or ""),
        "package_id": package["package_id"],
        "gate_status": gate["status"],
        "research_ready_for_publication": bool(gate["research_ready_for_publication"]),
        "actual_external_delivery_enabled": bool(package.get("actual_external_delivery_enabled") or package.get("external_delivery_enabled")),
        "case_count": _int(summary.get("case_count")),
        "claim_count": _int(summary.get("claim_count")),
        "evidence_count": _int(summary.get("evidence_count")),
        "gap_count": _int(summary.get("gap_count")),
        "blocker_count": len(package["blockers"]),
    }


def publication_snapshot_detail_read_model(row: dict[str, Any]) -> dict[str, Any]:
    package = _package_from_row(row)
    payload = _payload(row.get("payload"))
    return {
        "publication_snapshot_id": str(row.get("publication_snapshot_id") or ""),
        "trade_date": str(row.get("trade_date") or ""),
        "channel": str(row.get("channel") or ""),
        "title": str(row.get("title") or ""),
        "created_by": str(row.get("created_by") or ""),
        "created_at": str(row.get("created_at") or ""),
        "package_id": package["package_id"],
        "gate": package["gate"],
        "summary": package["summary"],
        "sections": package["sections"],
        "blockers": package["blockers"],
        "warnings": package["warnings"],
        "source_trace_summary": {
            "run_id": str(payload.get("run_id") or ""),
            "channel": str(payload.get("channel") or row.get("channel") or ""),
            "package_id": package["package_id"],
        },
    }


def _package_from_row(row: dict[str, Any]) -> dict[str, Any]:
    payload = _payload(row.get("payload"))
    package_payload = payload.get("package") if isinstance(payload.get("package"), dict) else payload
    return research_publication_package_read_model(package_payload)


def _payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _clamp_limit(value: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = 50
    return max(1, min(parsed, 100))


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
