from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable

from stock_research.config import SETTINGS
from stock_research.dashboard.review_queue import build_review_queue
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
    publication_attempt_id text,
    snapshot_attempt_id text,
    source_manifest_sha256 text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (run_id, digest_key, payload_hash)
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
    publication_attempt_id text,
    snapshot_attempt_id text,
    source_manifest_sha256 text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (run_id, digest_key, payload_hash)
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

-- Current version = the latest publication batch of a run (rows sharing a
-- publication_attempt_id; legacy rows with NULL form one batch), then the
-- newest row per item inside that batch. Never mixes two publications.
CREATE OR REPLACE VIEW ops.review_item_snapshot_current AS
SELECT DISTINCT ON (s.run_id, s.digest_key) s.*
  FROM ops.review_item_snapshot s
  JOIN (
        SELECT DISTINCT ON (run_id) run_id, publication_attempt_id
          FROM ops.review_item_snapshot
         GROUP BY run_id, publication_attempt_id
         ORDER BY run_id, max(created_at) DESC
       ) cur
    ON cur.run_id = s.run_id
   AND cur.publication_attempt_id IS NOT DISTINCT FROM s.publication_attempt_id
 ORDER BY s.run_id, s.digest_key, s.created_at DESC, s.snapshot_id;

CREATE OR REPLACE VIEW ops.evidence_digest_snapshot_current AS
SELECT DISTINCT ON (s.run_id, s.digest_key) s.*
  FROM ops.evidence_digest_snapshot s
  JOIN (
        SELECT DISTINCT ON (run_id) run_id, publication_attempt_id
          FROM ops.evidence_digest_snapshot
         GROUP BY run_id, publication_attempt_id
         ORDER BY run_id, max(created_at) DESC
       ) cur
    ON cur.run_id = s.run_id
   AND cur.publication_attempt_id IS NOT DISTINCT FROM s.publication_attempt_id
 ORDER BY s.run_id, s.digest_key, s.created_at DESC, s.snapshot_id;
"""

# Gate A migration for existing installs (review before running on any
# shared database; not applied automatically). Old rows keep their
# snapshot_id; new versions get content-addressed ids.
MIGRATE_SNAPSHOT_VERSIONING_SQL = """
ALTER TABLE ops.review_item_snapshot
    ADD COLUMN IF NOT EXISTS publication_attempt_id text,
    ADD COLUMN IF NOT EXISTS snapshot_attempt_id text,
    ADD COLUMN IF NOT EXISTS source_manifest_sha256 text;
ALTER TABLE ops.evidence_digest_snapshot
    ADD COLUMN IF NOT EXISTS publication_attempt_id text,
    ADD COLUMN IF NOT EXISTS snapshot_attempt_id text,
    ADD COLUMN IF NOT EXISTS source_manifest_sha256 text;
ALTER TABLE ops.review_item_snapshot
    DROP CONSTRAINT IF EXISTS review_item_snapshot_run_id_digest_key_key;
ALTER TABLE ops.evidence_digest_snapshot
    DROP CONSTRAINT IF EXISTS evidence_digest_snapshot_run_id_digest_key_key;
CREATE UNIQUE INDEX IF NOT EXISTS uq_review_item_snapshot_version
    ON ops.review_item_snapshot (run_id, digest_key, payload_hash);
CREATE UNIQUE INDEX IF NOT EXISTS uq_evidence_digest_snapshot_version
    ON ops.evidence_digest_snapshot (run_id, digest_key, payload_hash);
-- Current version = the latest publication batch of a run (rows sharing a
-- publication_attempt_id; legacy rows with NULL form one batch), then the
-- newest row per item inside that batch. Never mixes two publications.
CREATE OR REPLACE VIEW ops.review_item_snapshot_current AS
SELECT DISTINCT ON (s.run_id, s.digest_key) s.*
  FROM ops.review_item_snapshot s
  JOIN (
        SELECT DISTINCT ON (run_id) run_id, publication_attempt_id
          FROM ops.review_item_snapshot
         GROUP BY run_id, publication_attempt_id
         ORDER BY run_id, max(created_at) DESC
       ) cur
    ON cur.run_id = s.run_id
   AND cur.publication_attempt_id IS NOT DISTINCT FROM s.publication_attempt_id
 ORDER BY s.run_id, s.digest_key, s.created_at DESC, s.snapshot_id;

CREATE OR REPLACE VIEW ops.evidence_digest_snapshot_current AS
SELECT DISTINCT ON (s.run_id, s.digest_key) s.*
  FROM ops.evidence_digest_snapshot s
  JOIN (
        SELECT DISTINCT ON (run_id) run_id, publication_attempt_id
          FROM ops.evidence_digest_snapshot
         GROUP BY run_id, publication_attempt_id
         ORDER BY run_id, max(created_at) DESC
       ) cur
    ON cur.run_id = s.run_id
   AND cur.publication_attempt_id IS NOT DISTINCT FROM s.publication_attempt_id
 ORDER BY s.run_id, s.digest_key, s.created_at DESC, s.snapshot_id;
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
    provenance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    run_id = str(item.get("run_id") or "")
    digest_key = str(item.get("digest_key") or "")
    payload_hash = canonical_payload_hash(item)
    return {
        "snapshot_id": _snapshot_id("review_item_snapshot", run_id, digest_key, payload_hash),
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
        "payload_hash": payload_hash,
        "schema_version": schema_version,
        **_provenance(provenance),
    }


def build_evidence_digest_snapshot(
    digest: dict[str, Any],
    *,
    schema_version: str = SNAPSHOT_SCHEMA_VERSION,
    provenance: dict[str, Any] | None = None,
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
    payload_hash = canonical_payload_hash(digest)
    return {
        "snapshot_id": _snapshot_id("evidence_digest_snapshot", run_id, digest_key, payload_hash),
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
        "payload_hash": payload_hash,
        "schema_version": schema_version,
        **_provenance(provenance),
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
        payload_hash, schema_version, publication_attempt_id,
        snapshot_attempt_id, source_manifest_sha256
    )
    VALUES (
        %(snapshot_id)s, %(run_id)s, %(trade_date)s, %(latest_trade_date)s,
        %(asset_id)s, %(stock_code)s, %(stock_name)s, %(digest_key)s,
        %(source_type)s, %(source_name)s, %(source_rank)s, %(topn_rank)s,
        %(score_version)s, %(score)s, %(evidence_status)s,
        %(missing_evidence_count)s, %(partial_evidence_count)s,
        %(warnings_count)s, %(review_item_payload)s::jsonb,
        %(payload_hash)s, %(schema_version)s, %(publication_attempt_id)s,
        %(snapshot_attempt_id)s, %(source_manifest_sha256)s
    )
    ON CONFLICT (run_id, digest_key, payload_hash) DO NOTHING
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
        schema_version, publication_attempt_id, snapshot_attempt_id,
        source_manifest_sha256
    )
    VALUES (
        %(snapshot_id)s, %(run_id)s, %(trade_date)s, %(latest_trade_date)s,
        %(asset_id)s, %(stock_code)s, %(stock_name)s, %(digest_key)s,
        %(overall_status)s, %(missing_evidence)s::jsonb,
        %(partial_evidence)s::jsonb, %(sections_status)s::jsonb,
        %(digest_payload)s::jsonb, %(payload_hash)s, %(schema_version)s,
        %(publication_attempt_id)s, %(snapshot_attempt_id)s,
        %(source_manifest_sha256)s
    )
    ON CONFLICT (run_id, digest_key, payload_hash) DO NOTHING
    """
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
    return str(snapshot["snapshot_id"])


def snapshot_review_queue_payload(
    queue_payload: dict[str, Any],
    service: str = SETTINGS.research_service,
    *,
    provenance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    review_ids: list[str] = []
    digest_ids: list[str] = []
    for group in queue_payload.get("groups") or []:
        for item in group.get("items") or []:
            review_snapshot = build_review_item_snapshot(item, provenance=provenance)
            review_ids.append(upsert_review_item_snapshot(review_snapshot, service=service))
            digest = item.get("digest")
            if isinstance(digest, dict):
                digest_ids.append(
                    upsert_evidence_digest_snapshot(
                        build_evidence_digest_snapshot(digest, provenance=provenance),
                        service=service,
                    )
                )
    return {
        "review_item_snapshot_count": len(review_ids),
        "evidence_digest_snapshot_count": len(digest_ids),
        "review_item_snapshot_ids": review_ids,
        "evidence_digest_snapshot_ids": digest_ids,
    }


def run_eod_review_evidence_snapshots(
    *,
    run_id: str,
    trade_date: str,
    output_dir: str | Path | None = None,
    score_version: str = "manual_v1",
    limit: int = 30,
    asset_id: str | None = None,
    dry_run: bool = False,
    service: str = SETTINGS.research_service,
    strategy_output_root: str | Path | None = None,
    provenance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    warnings: list[str] = []
    errors: list[str] = []
    artifact_path = ""
    queue_payload = build_review_queue(
        trade_date=trade_date,
        score_version=score_version,
        limit=limit,
        use_strategy_snapshots=False,
        strategy_output_root=strategy_output_root,
    )
    warnings.extend(str(warning) for warning in queue_payload.get("warnings") or [])
    queue_payload = _queue_payload_with_run_context(
        queue_payload,
        run_id=run_id,
        trade_date=trade_date,
    )
    if asset_id:
        queue_payload = _filter_queue_payload(queue_payload, asset_id=asset_id)

    item_count = _queue_item_count(queue_payload)
    result_counts = {
        "review_item_snapshot_count": item_count if dry_run else 0,
        "evidence_digest_snapshot_count": 0,
        "review_item_snapshot_ids": [],
        "evidence_digest_snapshot_ids": [],
    }
    failed_count = 0
    skipped_count = 0
    if item_count == 0:
        skipped_count = 1
        warnings.append("review queue empty; snapshot step skipped")
        status = "skipped"
    elif dry_run:
        warnings.append("dry_run enabled; snapshots were not persisted")
        status = "partial" if warnings else "success"
    else:
        try:
            result_counts = snapshot_review_queue_payload(
                queue_payload, service=service, provenance=provenance
            )
            status = "partial" if warnings else "success"
        except Exception as exc:
            failed_count = 1
            errors.append(str(exc))
            warnings.append(f"snapshot generation failed: {exc}")
            status = "partial"

    review_count = int(result_counts.get("review_item_snapshot_count") or 0)
    digest_count = int(result_counts.get("evidence_digest_snapshot_count") or 0)
    result = {
        "run_id": run_id,
        "trade_date": trade_date,
        "latest_trade_date": trade_date,
        "score_version": score_version,
        "status": status,
        "snapshot_status": status,
        "review_item_snapshot_count": review_count,
        "evidence_digest_snapshot_count": digest_count,
        "row_count": review_count + digest_count,
        "asset_count": item_count,
        "skipped_count": skipped_count,
        "failed_count": failed_count,
        "warning_count": len(warnings),
        "warnings": warnings,
        "errors": errors,
        "review_item_snapshot_ids": list(result_counts.get("review_item_snapshot_ids") or []),
        "evidence_digest_snapshot_ids": list(result_counts.get("evidence_digest_snapshot_ids") or []),
        "artifact_path": artifact_path,
        "dry_run": dry_run,
    }
    if output_dir:
        resolved_output_dir = Path(output_dir)
        resolved_output_dir.mkdir(parents=True, exist_ok=True)
        artifact = resolved_output_dir / "review_evidence_snapshots_summary.json"
        result["artifact_path"] = str(artifact)
        artifact.write_text(
            json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
    return result


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
    FROM ops.review_item_snapshot_current
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
    FROM ops.evidence_digest_snapshot_current
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


def _queue_payload_with_run_context(
    queue_payload: dict[str, Any],
    *,
    run_id: str,
    trade_date: str,
) -> dict[str, Any]:
    updated = dict(queue_payload)
    updated_groups: list[dict[str, Any]] = []
    for group in queue_payload.get("groups") or []:
        updated_group = dict(group)
        items: list[dict[str, Any]] = []
        for item in group.get("items") or []:
            updated_item = dict(item)
            updated_item["run_id"] = str(updated_item.get("run_id") or run_id)
            updated_item["trade_date"] = str(updated_item.get("trade_date") or trade_date)
            updated_item["latest_trade_date"] = str(
                updated_item.get("latest_trade_date") or trade_date
            )
            digest = updated_item.get("digest")
            if isinstance(digest, dict):
                updated_digest = dict(digest)
                updated_digest["run_id"] = str(updated_digest.get("run_id") or run_id)
                updated_digest["trade_date"] = str(updated_digest.get("trade_date") or trade_date)
                updated_digest["latest_trade_date"] = str(
                    updated_digest.get("latest_trade_date") or trade_date
                )
                updated_item["digest"] = updated_digest
            items.append(updated_item)
        updated_group["items"] = items
        updated_groups.append(updated_group)
    updated["groups"] = updated_groups
    return updated


def _filter_queue_payload(queue_payload: dict[str, Any], *, asset_id: str) -> dict[str, Any]:
    filtered = dict(queue_payload)
    groups: list[dict[str, Any]] = []
    for group in queue_payload.get("groups") or []:
        updated_group = dict(group)
        updated_group["items"] = [
            item for item in group.get("items") or []
            if str(item.get("canonical_asset_id") or item.get("asset_id") or "") == asset_id
        ]
        groups.append(updated_group)
    filtered["groups"] = groups
    return filtered


def _queue_item_count(queue_payload: dict[str, Any]) -> int:
    return sum(len(group.get("items") or []) for group in queue_payload.get("groups") or [])


def _snapshot_id(prefix: str, run_id: str, digest_key: str, payload_hash: str) -> str:
    """One id per (run, item, content version); a changed payload gets a new id."""
    payload = f"{run_id}|{digest_key}|{payload_hash}"
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}:{digest}"


def _provenance(value: dict[str, Any] | None) -> dict[str, Any]:
    value = value or {}
    return {
        "publication_attempt_id": value.get("publication_attempt_id"),
        "snapshot_attempt_id": value.get("snapshot_attempt_id"),
        "source_manifest_sha256": value.get("source_manifest_sha256"),
    }


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


REVIEW_QUEUE_MANIFEST_FILENAME = "review_queue_strategy_manifest.csv"
SNAPSHOT_MODULE = "review_evidence_snapshots"
_ATTEMPT_STATUS = {"success": "succeeded", "partial": "failed", "skipped": "skipped", "failed": "failed"}


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _manifest_row_count(path: Path) -> int:
    import csv

    with open(path, newline="", encoding="utf-8") as handle:
        return sum(1 for _ in csv.DictReader(handle))


def run_post_publish_snapshots(
    *,
    run_id: str,
    trade_date: str,
    strategy_output_root: str | Path,
    publication_attempt_id: str | None,
    trigger: str,
    attempt_store: Any,
    expected_manifest_sha256: str | None = None,
    output_dir: str | Path | None = None,
    limit: int = 30,
    git_sha: str | None = None,
    service: str = SETTINGS.research_service,
    snapshot_runner: Callable[..., dict[str, Any]] | None = None,
    manifest_writer: Callable[[dict[str, Any]], Any] | None = None,
) -> dict[str, Any]:
    """Snapshot exactly the review queue version that was just published.

    Must run after the publication commit. The source is pinned to the
    canonical ``review_queue_strategy_manifest.csv`` of ``trade_date`` and its
    sha256; a missing file or a hash change (another publication replaced it)
    fails instead of snapshotting a different version. The result, not the
    caller, decides the status; the manifest row is written back for both
    normal and repair runs.
    """
    from stock_research.data_run_manifest import build_manifest_entry, upsert_data_run_manifest
    from stock_research.run_attempts import new_attempt_id

    runner = snapshot_runner or run_eod_review_evidence_snapshots

    def _default_writer(entry: dict[str, Any]) -> Any:
        return upsert_data_run_manifest(entry, service=service)

    writer = manifest_writer or _default_writer
    source = Path(strategy_output_root) / trade_date / REVIEW_QUEUE_MANIFEST_FILENAME
    attempt_id = new_attempt_id()
    started = attempt_store.start({
        "attempt_id": attempt_id, "run_id": run_id, "trade_date": trade_date,
        "module": SNAPSHOT_MODULE, "trigger": trigger,
        "parent_attempt_id": publication_attempt_id, "git_sha": git_sha,
        "input_refs": {"source_manifest_path": str(source)},
    })
    warnings: list[str] = []
    errors: list[str] = []
    source_sha = None
    expected_rows = 0
    result: dict[str, Any] = {}
    if not source.is_file():
        status, failure = "failed", "source_manifest_missing"
    else:
        source_sha = file_sha256(source)
        expected_rows = _manifest_row_count(source)
        if expected_manifest_sha256 and source_sha != expected_manifest_sha256:
            status, failure = "failed", "source_manifest_mismatch"
        else:
            provenance = {
                "publication_attempt_id": publication_attempt_id,
                "snapshot_attempt_id": attempt_id,
                "source_manifest_sha256": source_sha,
            }
            try:
                result = dict(runner(
                    run_id=run_id, trade_date=trade_date, output_dir=output_dir, limit=limit,
                    strategy_output_root=strategy_output_root, provenance=provenance,
                    service=service,
                ) or {})
                status, failure = str(result.get("status") or "failed"), None
            except Exception as exc:  # noqa: BLE001
                status, failure = "failed", f"snapshot_error: {type(exc).__name__}: {exc}"
            if source.is_file() and file_sha256(source) != source_sha:
                status, failure = "failed", "source_manifest_changed_during_snapshot"
    written = int(result.get("review_item_snapshot_count") or 0)
    warnings.extend(str(w) for w in result.get("warnings") or [])
    errors.extend(str(e) for e in result.get("errors") or [])
    if failure:
        errors.append(failure)
    if status == "success" and written != expected_rows:
        status = "partial"
        warnings.append(f"reconciliation: wrote {written} review snapshots, source has {expected_rows} rows")
    finished = attempt_store.finish(
        attempt_id, status=_ATTEMPT_STATUS.get(status, "failed"),
        failure_class=None if status in {"success", "skipped"} else "publish",
        error_message="; ".join(errors) or None,
        input_refs={"source_manifest_path": str(source), "source_manifest_sha256": source_sha},
        output_refs={"review_item_snapshot_count": written,
                     "evidence_digest_snapshot_count": int(result.get("evidence_digest_snapshot_count") or 0)},
    )
    entry = build_manifest_entry(
        run_id=run_id, run_date=trade_date, trade_date=trade_date, module=SNAPSHOT_MODULE,
        source="review_queue/evidence_digest", tier="tier2",
        status=status if status in {"success", "partial", "skipped", "failed"} else "failed",
        started_at=started.get("started_at"), ended_at=finished.get("ended_at"),
        row_count=written + int(result.get("evidence_digest_snapshot_count") or 0),
        asset_count=int(result.get("asset_count") or 0), latest_trade_date=trade_date,
        warnings=warnings, error_message="; ".join(errors),
        artifact_path=str(result.get("artifact_path") or ""),
        config_version="review_queue_evidence_digest_snapshot_v2",
        metadata={"last_attempt_id": attempt_id, "trigger": trigger,
                  "publication_attempt_id": publication_attempt_id,
                  "source_manifest_sha256": source_sha, "expected_review_rows": expected_rows,
                  "review_item_snapshot_count": written},
    )
    manifest_written = True
    try:
        writer(entry)
    except Exception as exc:  # noqa: BLE001 - attempt record keeps the outcome
        manifest_written = False
        warnings.append(f"manifest write-back failed: {type(exc).__name__}: {exc}")
    return {"status": status, "attempt_id": attempt_id, "source_manifest_sha256": source_sha,
            "expected_review_rows": expected_rows, "review_item_snapshot_count": written,
            "manifest_written": manifest_written, "warnings": warnings, "errors": errors,
            "manifest_entry": entry}


def snapshot_official_status(
    snapshot: dict[str, Any],
    *,
    eod_status: dict[str, Any] | None,
    publication_attempt: dict[str, Any] | None,
    published_manifest_sha256: str | None,
) -> dict[str, Any]:
    """Classify a snapshot row; 'official' needs version proof, not timing.

    Separate dimensions: publication (official / derived_after_publish /
    not_published) and verification (verified / unverified) with reasons.
    """
    reasons: list[str] = []
    published = bool(eod_status and str(eod_status.get("status")) == "success")
    if not published:
        return {"publication": "not_published", "verification": "unverified",
                "reasons": ["eod_status_not_success"]}
    pub_id = snapshot.get("publication_attempt_id")
    if not pub_id:
        reasons.append("no_publication_attempt_id")
    elif not publication_attempt or publication_attempt.get("attempt_id") != pub_id:
        reasons.append("publication_attempt_not_found")
    elif publication_attempt.get("status") != "published":
        reasons.append("publication_attempt_not_published")
    src = snapshot.get("source_manifest_sha256")
    if not src:
        reasons.append("no_source_manifest_sha256")
    elif not published_manifest_sha256 or src != published_manifest_sha256:
        reasons.append("source_manifest_sha256_mismatch")
    if reasons:
        return {"publication": "derived_after_publish", "verification": "unverified", "reasons": reasons}
    return {"publication": "official", "verification": "verified", "reasons": []}
