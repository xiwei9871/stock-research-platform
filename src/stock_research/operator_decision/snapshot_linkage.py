from __future__ import annotations

import json
from typing import Any

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all
from stock_research.review_evidence_snapshots import (
    list_evidence_digest_snapshots,
    list_review_item_snapshots,
    load_evidence_digest_snapshot,
)


def resolve_decision_snapshot_linkage(
    context: dict[str, Any],
    *,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    base = _parse_source_context(context.get("source_context"))
    lookup = {**base, **{key: value for key, value in context.items() if value not in (None, "")}}
    run_id = str(lookup.get("run_id") or "")
    digest_key = str(lookup.get("digest_key") or "")
    asset_id = str(lookup.get("asset_id") or lookup.get("stock_code") or "")

    review = _resolve_review_snapshot(
        lookup,
        run_id=run_id,
        digest_key=digest_key,
        asset_id=asset_id,
        service=service,
    )
    if review and not digest_key:
        digest_key = str(review.get("digest_key") or "")
    digest = _resolve_digest_snapshot(
        lookup,
        run_id=run_id,
        digest_key=digest_key,
        asset_id=asset_id,
        service=service,
    )

    warnings: list[str] = []
    if review is None:
        warnings.append(_missing_warning("review_item_snapshot", run_id, digest_key, asset_id))
    if digest is None:
        warnings.append(_missing_warning("evidence_digest_snapshot", run_id, digest_key, asset_id))

    if review:
        run_id = run_id or str(review.get("run_id") or "")
        digest_key = digest_key or str(review.get("digest_key") or "")
    if digest:
        run_id = run_id or str(digest.get("run_id") or "")
        digest_key = digest_key or str(digest.get("digest_key") or "")

    linkage = {
        **base,
        "run_id": run_id,
        "digest_key": digest_key,
        "review_item_snapshot_id": str(review.get("snapshot_id") if review else ""),
        "evidence_digest_snapshot_id": str(digest.get("snapshot_id") if digest else ""),
        "review_item_payload_hash": str(review.get("payload_hash") if review else ""),
        "evidence_digest_payload_hash": str(digest.get("payload_hash") if digest else ""),
        "snapshot_linkage_status": "linked" if review or digest else "missing",
        "snapshot_linkage_warnings": warnings,
        "review_item_as_of": str(review.get("created_at") if review else ""),
        "evidence_as_of": str(digest.get("created_at") if digest else ""),
    }
    payload = review.get("review_item_payload") if isinstance(review, dict) else {}
    if isinstance(payload, dict):
        for key in ("source_type", "source_name"):
            if payload.get(key) and not linkage.get(key):
                linkage[key] = str(payload[key])
    return linkage


def merge_source_context(source_context: Any, linkage: dict[str, Any]) -> str:
    base = _parse_source_context(source_context)
    merged = {**base, **linkage}
    return json.dumps(merged, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def load_review_item_snapshot(
    snapshot_id: str,
    service: str = SETTINGS.research_service,
) -> dict[str, Any] | None:
    sql = """
    SELECT *
    FROM ops.review_item_snapshot
    WHERE snapshot_id = %(snapshot_id)s
    """
    with connect(service) as conn:
        rows = list(fetch_all(conn, sql, {"snapshot_id": snapshot_id}))
    return dict(rows[0]) if rows else None


def _resolve_review_snapshot(
    lookup: dict[str, Any],
    *,
    run_id: str,
    digest_key: str,
    asset_id: str,
    service: str,
) -> dict[str, Any] | None:
    explicit = str(lookup.get("review_item_snapshot_id") or "")
    if explicit:
        return load_review_item_snapshot(explicit, service=service)
    if run_id and digest_key:
        return _first_snapshot(
            list_review_item_snapshots(
                run_id=run_id,
                digest_key=digest_key,
                service=service,
            ),
            digest_key=digest_key,
        )
    if run_id and asset_id:
        return _first_snapshot(
            list_review_item_snapshots(
                run_id=run_id,
                asset_id=asset_id,
                service=service,
            ),
            digest_key=digest_key,
        )
    return None


def _resolve_digest_snapshot(
    lookup: dict[str, Any],
    *,
    run_id: str,
    digest_key: str,
    asset_id: str,
    service: str,
) -> dict[str, Any] | None:
    explicit = str(lookup.get("evidence_digest_snapshot_id") or "")
    if explicit:
        return load_evidence_digest_snapshot(explicit, service=service)
    if run_id and digest_key:
        return _first_snapshot(
            list_evidence_digest_snapshots(
                run_id=run_id,
                digest_key=digest_key,
                service=service,
            ),
            digest_key=digest_key,
        )
    if run_id and asset_id:
        return _first_snapshot(
            list_evidence_digest_snapshots(
                run_id=run_id,
                asset_id=asset_id,
                service=service,
            ),
            digest_key=digest_key,
        )
    return None


def _first_snapshot(rows: list[dict[str, Any]], *, digest_key: str) -> dict[str, Any] | None:
    if not rows:
        return None
    sorted_rows = sorted(
        rows,
        key=lambda row: (
            str(row.get("digest_key") or "") == digest_key if digest_key else False,
            str(row.get("created_at") or ""),
        ),
        reverse=True,
    )
    return dict(sorted_rows[0])


def _parse_source_context(source_context: Any) -> dict[str, Any]:
    if not source_context:
        return {}
    if isinstance(source_context, dict):
        return dict(source_context)
    text = str(source_context)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return {"source_context_label": text}
    return dict(parsed) if isinstance(parsed, dict) else {"source_context_label": text}


def _missing_warning(kind: str, run_id: str, digest_key: str, asset_id: str) -> str:
    if run_id and digest_key:
        return f"No {kind} found for run_id + digest_key"
    if run_id and asset_id:
        return f"No {kind} found for run_id + asset_id"
    return f"No {kind} lookup keys available"
