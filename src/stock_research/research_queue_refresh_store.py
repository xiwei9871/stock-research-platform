from __future__ import annotations

import json
from typing import Any

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all

CREATE_RESEARCH_QUEUE_REFRESH_SQL = """
CREATE SCHEMA IF NOT EXISTS ops;

CREATE TABLE IF NOT EXISTS ops.research_queue_refresh_run (
    run_id text PRIMARY KEY,
    trade_date date,
    status text NOT NULL,
    dry_run boolean NOT NULL DEFAULT false,
    started_at timestamptz,
    finished_at timestamptz,
    counts jsonb NOT NULL DEFAULT '{}'::jsonb,
    warnings jsonb NOT NULL DEFAULT '[]'::jsonb,
    artifact_paths jsonb NOT NULL DEFAULT '{}'::jsonb,
    manifest jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_rq_refresh_finished
    ON ops.research_queue_refresh_run (finished_at DESC NULLS LAST);

CREATE INDEX IF NOT EXISTS idx_rq_refresh_trade_date
    ON ops.research_queue_refresh_run (trade_date, finished_at DESC NULLS LAST);
"""


def apply_research_queue_refresh_schema(service: str = SETTINGS.research_service) -> None:
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute(CREATE_RESEARCH_QUEUE_REFRESH_SQL)


def upsert_refresh_run(
    manifest: dict[str, Any],
    *,
    service: str = SETTINGS.research_service,
) -> str:
    run_id = str(manifest.get("run_id") or "").strip()
    if not run_id:
        raise ValueError("manifest run_id required")
    apply_research_queue_refresh_schema(service=service)
    params = {
        "run_id": run_id,
        "trade_date": _date_or_none(manifest.get("trade_date")),
        "status": str(manifest.get("status") or ""),
        "dry_run": bool(manifest.get("dry_run")),
        "started_at": _datetime_or_none(manifest.get("started_at")),
        "finished_at": _datetime_or_none(manifest.get("finished_at")),
        "counts": json.dumps(manifest.get("counts") or {}, ensure_ascii=False),
        "warnings": json.dumps(manifest.get("warnings") or [], ensure_ascii=False),
        "artifact_paths": json.dumps(manifest.get("artifact_paths") or {}, ensure_ascii=False),
        "manifest": json.dumps(_jsonable(manifest), ensure_ascii=False),
    }
    sql = """
    INSERT INTO ops.research_queue_refresh_run (
        run_id, trade_date, status, dry_run, started_at, finished_at,
        counts, warnings, artifact_paths, manifest
    )
    VALUES (
        %(run_id)s, %(trade_date)s, %(status)s, %(dry_run)s, %(started_at)s,
        %(finished_at)s, %(counts)s::jsonb, %(warnings)s::jsonb,
        %(artifact_paths)s::jsonb, %(manifest)s::jsonb
    )
    ON CONFLICT (run_id)
    DO UPDATE SET
        trade_date = EXCLUDED.trade_date,
        status = EXCLUDED.status,
        dry_run = EXCLUDED.dry_run,
        started_at = EXCLUDED.started_at,
        finished_at = EXCLUDED.finished_at,
        counts = EXCLUDED.counts,
        warnings = EXCLUDED.warnings,
        artifact_paths = EXCLUDED.artifact_paths,
        manifest = EXCLUDED.manifest
    """
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
    return run_id


def load_latest_refresh_run(
    *,
    trade_date: str | None = None,
    service: str = SETTINGS.research_service,
) -> dict[str, Any] | None:
    where = "WHERE NOT dry_run"
    params: dict[str, Any] = {}
    if trade_date:
        where += " AND trade_date = %(trade_date)s"
        params["trade_date"] = trade_date
    sql = f"""
    SELECT manifest
    FROM ops.research_queue_refresh_run
    {where}
    ORDER BY finished_at DESC NULLS LAST, created_at DESC
    LIMIT 1
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, params)
    if not rows:
        return None
    manifest = rows[0].get("manifest")
    return dict(manifest) if isinstance(manifest, dict) else None


def _date_or_none(value: Any) -> str | None:
    text = str(value or "").strip()[:10]
    return text or None


def _datetime_or_none(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)
