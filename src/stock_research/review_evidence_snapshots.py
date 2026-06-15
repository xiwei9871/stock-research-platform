from __future__ import annotations

import hashlib
import json
from typing import Any

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all

SNAPSHOT_SCHEMA_VERSION = "v1"

CREATE_REVIEW_EVIDENCE_SNAPSHOT_SQL = """
CREATE SCHEMA IF NOT EXISTS ops;

CREATE TABLE IF NOT EXISTS ops.review_item_snapshot (
    snapshot_id text PRIMARY KEY,
    run_id text NOT NULL,
    trade_date date NOT NULL,
    latest_trade_date date,
    asset_id text NOT NULL,
    stock_code text,
    stock_name text,
    digest_key text NOT NULL,
    source_type text NOT NULL,
    source_name text NOT NULL,
    source_rank integer,
    topn_rank integer,
    score_version text NOT NULL,
    score numeric,
    evidence_status text NOT NULL,
    missing_evidence_count integer NOT NULL DEFAULT 0,
    partial_evidence_count integer NOT NULL DEFAULT 0,
    warnings_count integer NOT NULL DEFAULT 0,
    review_item_payload jsonb NOT NULL,
    payload_hash text NOT NULL,
    schema_version text NOT NULL DEFAULT 'v1',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (run_id, digest_key)
);

CREATE TABLE IF NOT EXISTS ops.evidence_digest_snapshot (
    snapshot_id text PRIMARY KEY,
    run_id text NOT NULL,
    trade_date date NOT NULL,
    latest_trade_date date,
    asset_id text NOT NULL,
    stock_code text,
    stock_name text,
    digest_key text NOT NULL,
    overall_status text NOT NULL,
    missing_evidence jsonb NOT NULL DEFAULT '[]'::jsonb,
    partial_evidence jsonb NOT NULL DEFAULT '[]'::jsonb,
    sections_status jsonb NOT NULL DEFAULT '{}'::jsonb,
    digest_payload jsonb NOT NULL,
    payload_hash text NOT NULL,
    schema_version text NOT NULL DEFAULT 'v1',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (run_id, digest_key)
);

CREATE INDEX IF NOT EXISTS idx_review_item_snapshot_run
    ON ops.review_item_snapshot (run_id, trade_date DESC);

CREATE INDEX IF NOT EXISTS idx_review_item_snapshot_digest
    ON ops.review_item_snapshot (digest_key);

CREATE INDEX IF NOT EXISTS idx_review_item_snapshot_asset
    ON ops.review_item_snapshot (asset_id, trade_date DESC);

CREATE INDEX IF NOT EXISTS idx_evidence_digest_snapshot_run
    ON ops.evidence_digest_snapshot (run_id, trade_date DESC);

CREATE INDEX IF NOT EXISTS idx_evidence_digest_snapshot_digest
    ON ops.evidence_digest_snapshot (digest_key);

CREATE INDEX IF NOT EXISTS idx_evidence_digest_snapshot_asset
    ON ops.evidence_digest_snapshot (asset_id, trade_date DESC);
"""


def apply_review_evidence_snapshot_schema(service: str = SETTINGS.research_service) -> None:
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute(CREATE_REVIEW_EVIDENCE_SNAPSHOT_SQL)


def canonical_payload_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(
        _jsonable(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_review_item_snapshot(
    item: dict[str, Any],
    *,
    schema_version: str = SNAPSHOT_SCHEMA_VERSION,
) -> dict[str, Any]:
    run_id = str(item.get("run_id") or "")
    digest_key = str(item.get("digest_key") or "")
    return {
        "snapshot_id": _snapshot_id("review_item_snapshot", run_id, digest_key),
        "run_id": run_id,
        "trade_date": str(item.get("trade_date") or "")[:10],
        "latest_trade_date": _optional_date_text(item.get("latest_trade_date")),
        "asset_id": str(item.get("canonical_asset_id") or item.get("asset_id") or ""),
        "stock_code": str(item.get("asset_id") or item.get("canonical_asset_id") or ""),
        "stock_name": str(item.get("display_name") or ""),
        "digest_key": digest_key,
        "source_type": str(item.get("source_type") or ""),
        "source_name": str(item.get("source_name") or ""),
        "source_rank": _optional_int(item.get("source_rank")),
        "topn_rank": _optional_int(item.get("topn_rank") or item.get("rank")),
        "score_version": str(item.get("score_version") or ""),
        "score": _optional_float(item.get("score")),
        "evidence_status": str(item.get("evidence_status") or ""),
        "missing_evidence_count": _int(item.get("missing_evidence_count")),
        "partial_evidence_count": _int(item.get("partial_evidence_count")),
        "warnings_count": _int(item.get("warnings_count") if item.get("warnings_count") is not None else item.get("warning_count")),
        "review_item_payload": _jsonable(item),
        "payload_hash": canonical_payload_hash(item),
        "schema_version": schema_version,
    }


def build_evidence_digest_snapshot(
    digest: dict[str, Any],
    *,
    schema_version: str = SNAPSHOT_SCHEMA_VERSION,
) -> dict[str, Any]:
    run_id = str(digest.get("run_id") or "")
    digest_key = str(digest.get("digest_key") or "")
    sections = digest.get("sections") if isinstance(digest.get("sections"), dict) else {}
    sections_status = {
        str(key): str(value.get("status") or "")
        for key, value in sections.items()
        if isinstance(value, dict)
    }
    asset_id = str(digest.get("canonical_asset_id") or digest.get("asset_id") or "")
    return {
        "snapshot_id": _snapshot_id("evidence_digest_snapshot", run_id, digest_key),
        "run_id": run_id,
        "trade_date": str(digest.get("trade_date") or "")[:10],
        "latest_trade_date": _optional_date_text(digest.get("latest_trade_date")),
        "asset_id": asset_id,
        "stock_code": str(digest.get("stock_code") or asset_id),
        "stock_name": str(digest.get("stock_name") or ""),
        "digest_key": digest_key,
        "overall_status": str(digest.get("overall_status") or ""),
        "missing_evidence": [str(item) for item in digest.get("missing_evidence") or []],
        "partial_evidence": [str(item) for item in digest.get("partial_evidence") or []],
        "sections_status": sections_status,
        "digest_payload": _jsonable(digest),
        "payload_hash": canonical_payload_hash(digest),
        "schema_version": schema_version,
    }


def upsert_review_item_snapshot(
    snapshot: dict[str, Any],
    service: str = SETTINGS.research_service,
) -> str:
    params = _db_params(snapshot, "review_item_payload")
    sql = """
    INSERT INTO ops.review_item_snapshot (
        snapshot_id, run_id, trade_date, latest_trade_date, asset_id, stock_code,
        stock_name, digest_key, source_type, source_name, source_rank, topn_rank,
        score_version, score, evidence_status, missing_evidence_count,
        partial_evidence_count, warnings_count, review_item_payload,
        payload_hash, schema_version
    )
    VALUES (
        %(snapshot_id)s, %(run_id)s, %(trade_date)s, %(latest_trade_date)s,
        %(asset_id)s, %(stock_code)s, %(stock_name)s, %(digest_key)s,
        %(source_type)s, %(source_name)s, %(source_rank)s, %(topn_rank)s,
        %(score_version)s, %(score)s, %(evidence_status)s,
        %(missing_evidence_count)s, %(partial_evidence_count)s,
        %(warnings_count)s, %(review_item_payload)s::jsonb,
        %(payload_hash)s, %(schema_version)s
    )
    ON CONFLICT (run_id, digest_key)
    DO UPDATE SET
        latest_trade_date = EXCLUDED.latest_trade_date,
        asset_id = EXCLUDED.asset_id,
        stock_code = EXCLUDED.stock_code,
        stock_name = EXCLUDED.stock_name,
        source_type = EXCLUDED.source_type,
        source_name = EXCLUDED.source_name,
        source_rank = EXCLUDED.source_rank,
        topn_rank = EXCLUDED.topn_rank,
        score_version = EXCLUDED.score_version,
        score = EXCLUDED.score,
        evidence_status = EXCLUDED.evidence_status,
        missing_evidence_count = EXCLUDED.missing_evidence_count,
        partial_evidence_count = EXCLUDED.partial_evidence_count,
        warnings_count = EXCLUDED.warnings_count,
        review_item_payload = EXCLUDED.review_item_payload,
        payload_hash = EXCLUDED.payload_hash,
        schema_version = EXCLUDED.schema_version,
        updated_at = now()
    """
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
    return str(snapshot["snapshot_id"])


def upsert_evidence_digest_snapshot(
    snapshot: dict[str, Any],
    service: str = SETTINGS.research_service,
) -> str:
    params = _db_params(snapshot, "digest_payload")
    sql = """
    INSERT INTO ops.evidence_digest_snapshot (
        snapshot_id, run_id, trade_date, latest_trade_date, asset_id, stock_code,
        stock_name, digest_key, overall_status, missing_evidence,
        partial_evidence, sections_status, digest_payload, payload_hash,
        schema_version
    )
    VALUES (
        %(snapshot_id)s, %(run_id)s, %(trade_date)s, %(latest_trade_date)s,
        %(asset_id)s, %(stock_code)s, %(stock_name)s, %(digest_key)s,
        %(overall_status)s, %(missing_evidence)s::jsonb,
        %(partial_evidence)s::jsonb, %(sections_status)s::jsonb,
        %(digest_payload)s::jsonb, %(payload_hash)s, %(schema_version)s
    )
    ON CONFLICT (run_id, digest_key)
    DO UPDATE SET
        latest_trade_date = EXCLUDED.latest_trade_date,
        asset_id = EXCLUDED.asset_id,
        stock_code = EXCLUDED.stock_code,
        stock_name = EXCLUDED.stock_name,
        overall_status = EXCLUDED.overall_status,
        missing_evidence = EXCLUDED.missing_evidence,
        partial_evidence = EXCLUDED.partial_evidence,
        sections_status = EXCLUDED.sections_status,
        digest_payload = EXCLUDED.digest_payload,
        payload_hash = EXCLUDED.payload_hash,
        schema_version = EXCLUDED.schema_version,
        updated_at = now()
    """
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
    return str(snapshot["snapshot_id"])


def snapshot_review_queue_payload(
    queue_payload: dict[str, Any],
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    review_ids: list[str] = []
    digest_ids: list[str] = []
    for group in queue_payload.get("groups") or []:
        for item in group.get("items") or []:
            review_snapshot = build_review_item_snapshot(item)
            review_ids.append(upsert_review_item_snapshot(review_snapshot, service=service))
            digest = item.get("digest")
            if isinstance(digest, dict):
                digest_ids.append(
                    upsert_evidence_digest_snapshot(
                        build_evidence_digest_snapshot(digest),
                        service=service,
                    )
                )
    return {
        "review_item_snapshot_count": len(review_ids),
        "evidence_digest_snapshot_count": len(digest_ids),
        "review_item_snapshot_ids": review_ids,
        "evidence_digest_snapshot_ids": digest_ids,
    }


def list_review_item_snapshots(
    *,
    run_id: str | None = None,
    trade_date: str | None = None,
    asset_id: str | None = None,
    digest_key: str | None = None,
    limit: int = 100,
    service: str = SETTINGS.research_service,
) -> list[dict[str, Any]]:
    where, params = _snapshot_filters(
        run_id=run_id,
        trade_date=trade_date,
        asset_id=asset_id,
        digest_key=digest_key,
    )
    params["limit"] = _bounded_limit(limit)
    sql = f"""
    SELECT *
    FROM ops.review_item_snapshot
    {where}
    ORDER BY trade_date DESC, created_at DESC
    LIMIT %(limit)s
    """
    with connect(service) as conn:
        return list(fetch_all(conn, sql, params))


def list_evidence_digest_snapshots(
    *,
    run_id: str | None = None,
    trade_date: str | None = None,
    asset_id: str | None = None,
    digest_key: str | None = None,
    limit: int = 100,
    service: str = SETTINGS.research_service,
) -> list[dict[str, Any]]:
    where, params = _snapshot_filters(
        run_id=run_id,
        trade_date=trade_date,
        asset_id=asset_id,
        digest_key=digest_key,
    )
    params["limit"] = _bounded_limit(limit)
    sql = f"""
    SELECT *
    FROM ops.evidence_digest_snapshot
    {where}
    ORDER BY trade_date DESC, created_at DESC
    LIMIT %(limit)s
    """
    with connect(service) as conn:
        return list(fetch_all(conn, sql, params))


def load_evidence_digest_snapshot(
    snapshot_id: str,
    service: str = SETTINGS.research_service,
) -> dict[str, Any] | None:
    sql = """
    SELECT *
    FROM ops.evidence_digest_snapshot
    WHERE snapshot_id = %(snapshot_id)s
    """
    with connect(service) as conn:
        rows = list(fetch_all(conn, sql, {"snapshot_id": snapshot_id}))
    return dict(rows[0]) if rows else None
    asset_id = str(digest.get("canonical_asset_id") or digest.get("asset_id") or "")
    return {
        "snapshot_id": _snapshot_id("evidence_digest_snapshot", run_id, digest_key),
        "run_id": run_id,
        "trade_date": str(digest.get("trade_date") or "")[:10],
        "latest_trade_date": _optional_date_text(digest.get("latest_trade_date")),
        "asset_id": asset_id,
        "stock_code": str(digest.get("stock_code") or asset_id),
        "stock_name": str(digest.get("stock_name") or ""),
        "digest_key": digest_key,
        "overall_status": str(digest.get("overall_status") or ""),
        "missing_evidence": [str(item) for item in digest.get("missing_evidence") or []],
        "partial_evidence": [str(item) for item in digest.get("partial_evidence") or []],
        "sections_status": sections_status,
        "digest_payload": _jsonable(digest),
        "payload_hash": canonical_payload_hash(digest),
        "schema_version": schema_version,
    }


def _snapshot_id(prefix: str, run_id: str, digest_key: str) -> str:
    payload = f"{run_id}|{digest_key}"
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}:{digest}"


def _db_params(snapshot: dict[str, Any], payload_key: str) -> dict[str, Any]:
    params = dict(snapshot)
    params[payload_key] = json.dumps(
        snapshot.get(payload_key) or {},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    for key in ("missing_evidence", "partial_evidence"):
        if key in params:
            params[key] = json.dumps(params.get(key) or [], ensure_ascii=False, separators=(",", ":"))
    if "sections_status" in params:
        params["sections_status"] = json.dumps(
            params.get("sections_status") or {},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    return params


def _snapshot_filters(
    *,
    run_id: str | None,
    trade_date: str | None,
    asset_id: str | None,
    digest_key: str | None,
) -> tuple[str, dict[str, Any]]:
    clauses: list[str] = []
    params: dict[str, Any] = {}
    for key, value in {
        "run_id": run_id,
        "trade_date": trade_date,
        "asset_id": asset_id,
        "digest_key": digest_key,
    }.items():
        if value not in (None, ""):
            clauses.append(f"{key} = %({key})s")
            params[key] = value
    return ("WHERE " + " AND ".join(clauses)) if clauses else "", params


def _bounded_limit(limit: int) -> int:
    try:
        parsed = int(limit)
    except (TypeError, ValueError):
        parsed = 100
    return max(1, min(parsed, 500))


def _jsonable(value: Any) -> Any:
    try:
        json.dumps(value, ensure_ascii=False)
    except TypeError:
        if isinstance(value, dict):
            return {str(key): _jsonable(item) for key, item in value.items()}
        if isinstance(value, list):
            return [_jsonable(item) for item in value]
        return str(value)
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    return value


def _optional_date_text(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value)[:10]


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int:
    parsed = _optional_int(value)
    return parsed if parsed is not None else 0


def _optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
