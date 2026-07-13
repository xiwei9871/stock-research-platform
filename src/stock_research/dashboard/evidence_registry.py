from __future__ import annotations

from typing import Any

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all


def list_evidence_artifacts(
    *,
    asset_id: str | None = None,
    source_type: str | None = None,
    limit: int = 50,
    service: str = SETTINGS.research_service,
) -> list[dict[str, Any]]:
    clauses = ["1=1"]
    params: list[Any] = []
    if asset_id:
        clauses.append("asset_id = %s")
        params.append(asset_id)
    if source_type:
        clauses.append("source_type = %s")
        params.append(source_type)
    params.append(_clamp_limit(limit))
    sql = f"""
    SELECT
        evidence_id,
        source_type,
        source_id,
        asset_id,
        trade_date::text AS trade_date,
        title,
        uri,
        content_hash,
        metadata AS allowed_metadata
    FROM research.evidence_artifact
    WHERE {" AND ".join(clauses)}
    ORDER BY trade_date DESC NULLS LAST, created_at DESC
    LIMIT %s
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, params)
    return [evidence_artifact_read_model(row) for row in rows]


def evidence_artifact_read_model(row: dict[str, Any]) -> dict[str, Any]:
    metadata = row.get("allowed_metadata") if isinstance(row.get("allowed_metadata"), dict) else {}
    return {
        "evidence_id": str(row.get("evidence_id") or ""),
        "source_type": str(row.get("source_type") or ""),
        "source_id": str(row.get("source_id") or ""),
        "asset_id": str(row.get("asset_id") or ""),
        "trade_date": str(row.get("trade_date") or ""),
        "title": str(row.get("title") or ""),
        "uri": str(row.get("uri") or ""),
        "content_hash": str(row.get("content_hash") or ""),
        "allowed_metadata": dict(metadata),
    }


def _clamp_limit(value: int) -> int:
    return max(1, min(100, int(value or 50)))
