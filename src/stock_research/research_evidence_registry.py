from __future__ import annotations

import json
from typing import Any

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all


def evidence_from_digest_snapshot(row: dict[str, Any]) -> dict[str, Any]:
    payload = row.get("digest_payload") if isinstance(row.get("digest_payload"), dict) else {}
    snapshot_id = _text(row.get("snapshot_id"))
    return {
        "evidence_id": f"evidence_artifact:{snapshot_id}",
        "source_type": "evidence_digest_snapshot",
        "source_id": snapshot_id,
        "asset_id": _text(row.get("asset_id")),
        "trade_date": _optional_date(row.get("trade_date")),
        "title": _text(payload.get("title") or payload.get("bucket") or payload.get("stock_name")),
        "uri": "",
        "content_hash": _text(row.get("payload_hash")),
        "payload": payload,
        "metadata": {"digest_key": _text(row.get("digest_key"))},
    }


def evidence_from_review_item_snapshot(row: dict[str, Any]) -> dict[str, Any]:
    payload = row.get("review_item_payload") if isinstance(row.get("review_item_payload"), dict) else {}
    snapshot_id = _text(row.get("snapshot_id"))
    return {
        "evidence_id": f"evidence_artifact:{snapshot_id}",
        "source_type": "review_item_snapshot",
        "source_id": snapshot_id,
        "asset_id": _text(row.get("asset_id")),
        "trade_date": _optional_date(row.get("trade_date")),
        "title": _text(payload.get("display_name") or payload.get("stock_name") or row.get("stock_name")),
        "uri": "",
        "content_hash": _text(row.get("payload_hash")),
        "payload": payload,
        "metadata": {"digest_key": _text(row.get("digest_key"))},
    }


def register_snapshot_evidence(
    *,
    asset_id: str | None = None,
    trade_date: str | None = None,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    evidence_ids: list[str] = []
    for evidence in _load_digest_snapshot_evidence(asset_id=asset_id, trade_date=trade_date, service=service):
        evidence_ids.append(upsert_evidence_artifact(evidence, service=service))
    for evidence in _load_review_item_snapshot_evidence(asset_id=asset_id, trade_date=trade_date, service=service):
        evidence_ids.append(upsert_evidence_artifact(evidence, service=service))
    return {"registered_count": len(evidence_ids), "evidence_ids": evidence_ids}


def upsert_evidence_artifact(evidence: dict[str, Any], *, service: str = SETTINGS.research_service) -> str:
    evidence_id = _text(evidence.get("evidence_id"))
    params = {
        "evidence_id": evidence_id,
        "source_type": _text(evidence.get("source_type")),
        "source_id": _text(evidence.get("source_id")),
        "asset_id": _optional_text(evidence.get("asset_id")),
        "trade_date": _optional_date(evidence.get("trade_date")),
        "title": _text(evidence.get("title")),
        "uri": _text(evidence.get("uri")),
        "content_hash": _text(evidence.get("content_hash")),
        "payload": _json(evidence.get("payload") or {}),
        "metadata": _json(evidence.get("metadata") or {}),
    }
    sql = """
    INSERT INTO research.evidence_artifact (
        evidence_id, source_type, source_id, asset_id, trade_date,
        title, uri, content_hash, payload, metadata
    )
    VALUES (
        %(evidence_id)s, %(source_type)s, %(source_id)s, %(asset_id)s,
        %(trade_date)s, %(title)s, %(uri)s, %(content_hash)s,
        %(payload)s::jsonb, %(metadata)s::jsonb
    )
    ON CONFLICT (source_type, source_id)
    DO UPDATE SET
        asset_id = EXCLUDED.asset_id,
        trade_date = EXCLUDED.trade_date,
        title = EXCLUDED.title,
        uri = EXCLUDED.uri,
        content_hash = EXCLUDED.content_hash,
        payload = EXCLUDED.payload,
        metadata = EXCLUDED.metadata
    """
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
    return evidence_id


def _load_digest_snapshot_evidence(
    *,
    asset_id: str | None,
    trade_date: str | None,
    service: str,
) -> list[dict[str, Any]]:
    clauses, params = _snapshot_filters(asset_id=asset_id, trade_date=trade_date)
    sql = f"""
    SELECT
        snapshot_id,
        asset_id,
        trade_date::text AS trade_date,
        digest_key,
        payload_hash,
        digest_payload
    FROM ops.evidence_digest_snapshot
    WHERE {" AND ".join(clauses)}
    ORDER BY trade_date DESC, updated_at DESC
    LIMIT 100
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, params)
    return [evidence_from_digest_snapshot(dict(row)) for row in rows]


def _load_review_item_snapshot_evidence(
    *,
    asset_id: str | None,
    trade_date: str | None,
    service: str,
) -> list[dict[str, Any]]:
    clauses, params = _snapshot_filters(asset_id=asset_id, trade_date=trade_date)
    sql = f"""
    SELECT
        snapshot_id,
        asset_id,
        stock_name,
        trade_date::text AS trade_date,
        digest_key,
        payload_hash,
        review_item_payload
    FROM ops.review_item_snapshot
    WHERE {" AND ".join(clauses)}
    ORDER BY trade_date DESC, updated_at DESC
    LIMIT 100
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, params)
    return [evidence_from_review_item_snapshot(dict(row)) for row in rows]


def _snapshot_filters(*, asset_id: str | None, trade_date: str | None) -> tuple[list[str], list[Any]]:
    clauses = ["1=1"]
    params: list[Any] = []
    if asset_id:
        clauses.append("asset_id = %s")
        params.append(asset_id)
    if trade_date:
        clauses.append("trade_date = %s")
        params.append(trade_date)
    return clauses, params


def _optional_date(value: Any) -> str | None:
    text = str(value or "").strip()
    return text[:10] if text else None


def _optional_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _text(value: Any) -> str:
    return str(value or "").strip()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
