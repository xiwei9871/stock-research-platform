from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all

VALID_TIERS = {"tier1", "tier2", "tier3"}
VALID_STATUSES = {"success", "partial", "skipped", "failed", "unavailable"}
BLOCKING_STATUSES = {"failed", "unavailable"}
PARTIAL_STATUSES = {"partial", "failed", "unavailable"}

CREATE_DATA_RUN_MANIFEST_SQL = """
CREATE SCHEMA IF NOT EXISTS ops;

CREATE TABLE IF NOT EXISTS ops.data_run_manifest (
    manifest_id text PRIMARY KEY,
    run_id text NOT NULL,
    run_date date NOT NULL,
    trade_date date,
    module text NOT NULL,
    source text NOT NULL,
    tier text NOT NULL CHECK (tier IN ('tier1', 'tier2', 'tier3')),
    status text NOT NULL CHECK (status IN ('success', 'partial', 'skipped', 'failed', 'unavailable')),
    started_at timestamptz,
    ended_at timestamptz,
    duration_seconds numeric,
    row_count bigint,
    asset_count bigint,
    coverage_ratio numeric,
    latest_trade_date date,
    freshness_lag integer,
    warning_count integer NOT NULL DEFAULT 0,
    warnings jsonb NOT NULL DEFAULT '[]'::jsonb,
    error_message text,
    artifact_path text,
    code_version text,
    config_version text,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_data_run_manifest_run
    ON ops.data_run_manifest (run_id, tier, module);

CREATE INDEX IF NOT EXISTS idx_data_run_manifest_trade_date
    ON ops.data_run_manifest (trade_date DESC, tier, status);
"""


def apply_data_run_manifest_schema(service: str = SETTINGS.research_service) -> None:
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute(CREATE_DATA_RUN_MANIFEST_SQL)


def build_manifest_entry(
    *,
    run_id: str,
    run_date: object,
    trade_date: object | None,
    module: str,
    source: str,
    tier: str,
    status: str,
    started_at: object | None = None,
    ended_at: object | None = None,
    duration_seconds: float | None = None,
    row_count: int | None = None,
    asset_count: int | None = None,
    coverage_ratio: float | None = None,
    latest_trade_date: object | None = None,
    freshness_lag: int | None = None,
    warnings: list[str] | None = None,
    error_message: str | None = None,
    artifact_path: str | Path | None = None,
    code_version: str | None = None,
    config_version: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_tier = _validate(tier, VALID_TIERS, "tier")
    normalized_status = _validate(status, VALID_STATUSES, "status")
    normalized_warnings = [str(warning) for warning in (warnings or []) if str(warning)]
    return {
        "manifest_id": _manifest_id(run_id, module, source),
        "run_id": str(run_id),
        "run_date": _date_text(run_date),
        "trade_date": _optional_date_text(trade_date),
        "module": str(module),
        "source": str(source),
        "tier": normalized_tier,
        "status": normalized_status,
        "started_at": _optional_datetime_text(started_at),
        "ended_at": _optional_datetime_text(ended_at),
        "duration_seconds": duration_seconds,
        "row_count": row_count,
        "asset_count": asset_count,
        "coverage_ratio": coverage_ratio,
        "latest_trade_date": _optional_date_text(latest_trade_date),
        "freshness_lag": freshness_lag,
        "warning_count": len(normalized_warnings),
        "warnings": normalized_warnings,
        "error_message": error_message or "",
        "artifact_path": str(artifact_path) if artifact_path else "",
        "code_version": code_version or "",
        "config_version": config_version or "",
        "metadata": _jsonable(metadata or {}),
    }


def upsert_data_run_manifest(
    entry: dict[str, Any],
    service: str = SETTINGS.research_service,
) -> str:
    params = _db_params(entry)
    sql = """
    INSERT INTO ops.data_run_manifest (
        manifest_id, run_id, run_date, trade_date, module, source, tier, status,
        started_at, ended_at, duration_seconds, row_count, asset_count,
        coverage_ratio, latest_trade_date, freshness_lag, warning_count,
        warnings, error_message, artifact_path, code_version, config_version,
        metadata
    )
    VALUES (
        %(manifest_id)s, %(run_id)s, %(run_date)s, %(trade_date)s, %(module)s,
        %(source)s, %(tier)s, %(status)s, %(started_at)s, %(ended_at)s,
        %(duration_seconds)s, %(row_count)s, %(asset_count)s,
        %(coverage_ratio)s, %(latest_trade_date)s, %(freshness_lag)s,
        %(warning_count)s, %(warnings)s::jsonb, %(error_message)s,
        %(artifact_path)s, %(code_version)s, %(config_version)s, %(metadata)s::jsonb
    )
    ON CONFLICT (manifest_id)
    DO UPDATE SET
        status = EXCLUDED.status,
        ended_at = EXCLUDED.ended_at,
        duration_seconds = EXCLUDED.duration_seconds,
        row_count = EXCLUDED.row_count,
        asset_count = EXCLUDED.asset_count,
        coverage_ratio = EXCLUDED.coverage_ratio,
        latest_trade_date = EXCLUDED.latest_trade_date,
        freshness_lag = EXCLUDED.freshness_lag,
        warning_count = EXCLUDED.warning_count,
        warnings = EXCLUDED.warnings,
        error_message = EXCLUDED.error_message,
        artifact_path = EXCLUDED.artifact_path,
        code_version = EXCLUDED.code_version,
        config_version = EXCLUDED.config_version,
        metadata = EXCLUDED.metadata,
        updated_at = now()
    """
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
    return str(entry["manifest_id"])


def load_latest_data_run_manifest(
    *,
    trade_date: str | None = None,
    service: str = SETTINGS.research_service,
) -> list[dict[str, Any]]:
    where = "WHERE trade_date = %(trade_date)s" if trade_date else ""
    sql = f"""
    WITH latest AS (
        SELECT run_id
        FROM ops.data_run_manifest
        {where}
        ORDER BY COALESCE(ended_at, created_at) DESC
        LIMIT 1
    )
    SELECT *
    FROM ops.data_run_manifest
    WHERE run_id = (SELECT run_id FROM latest)
    ORDER BY tier, module
    """
    params = {"trade_date": trade_date} if trade_date else None
    with connect(service) as conn:
        return list(fetch_all(conn, sql, params))


def load_recent_data_run_manifest(
    *,
    trade_date: str | None = None,
    lookback_days: int = 14,
    service: str = SETTINGS.research_service,
) -> list[dict[str, Any]]:
    if trade_date:
        sql = """
        WITH ranked AS (
            SELECT
                *,
                row_number() OVER (
                    PARTITION BY module, source
                    ORDER BY COALESCE(ended_at, updated_at, created_at) DESC, run_id DESC
                ) AS rn
            FROM ops.data_run_manifest
            WHERE trade_date = %(trade_date)s
        )
        SELECT *
        FROM ranked
        WHERE rn = 1
        ORDER BY tier, module, source
        """
        with connect(service) as conn:
            return list(fetch_all(conn, sql, {"trade_date": trade_date}))
    sql = """
    WITH latest_date AS (
        SELECT max(trade_date) AS trade_date
        FROM ops.data_run_manifest
        WHERE trade_date IS NOT NULL
    )
    SELECT *
    FROM ops.data_run_manifest
    WHERE trade_date >= (
        SELECT trade_date - (%(lookback_days)s::int * INTERVAL '1 day')
        FROM latest_date
    )
    ORDER BY trade_date, run_id, tier, module, COALESCE(ended_at, created_at)
    """
    with connect(service) as conn:
        return list(fetch_all(conn, sql, {"lookback_days": int(lookback_days)}))


def summarize_manifest_modules(modules: list[dict[str, Any]]) -> dict[str, Any]:
    warnings: list[str] = []
    errors: list[str] = []
    missing_data: list[str] = []
    partial_data: list[str] = []
    tier_statuses = {"tier1": "OK", "tier2": "OK", "tier3": "OK"}

    for item in modules:
        module = str(item.get("module") or "")
        tier = str(item.get("tier") or "tier3")
        status = str(item.get("status") or "unavailable")
        warnings.extend(str(warning) for warning in item.get("warnings") or [])
        error = str(item.get("error_message") or "")
        if error:
            errors.append(f"{module}: {error}")
        if tier == "tier1" and status in BLOCKING_STATUSES:
            tier_statuses["tier1"] = "BLOCKED"
            missing_data.append(module)
        elif status in PARTIAL_STATUSES:
            partial_data.append(module)
            if tier_statuses.get(tier) != "BLOCKED":
                tier_statuses[tier] = "PARTIAL"

    overall = "BLOCKED" if tier_statuses["tier1"] == "BLOCKED" else (
        "PARTIAL" if any(value == "PARTIAL" for value in tier_statuses.values()) else "OK"
    )
    return {
        "status": overall,
        "tier1_status": tier_statuses["tier1"],
        "tier2_status": tier_statuses["tier2"],
        "tier3_status": tier_statuses["tier3"],
        "warnings": _dedupe(warnings),
        "errors": _dedupe(errors),
        "missing_data": _dedupe(missing_data),
        "partial_data": _dedupe(partial_data),
    }


def _db_params(entry: dict[str, Any]) -> dict[str, Any]:
    params = dict(entry)
    params["warnings"] = json.dumps(entry.get("warnings") or [], ensure_ascii=False)
    params["metadata"] = json.dumps(
        entry.get("metadata") or {},
        ensure_ascii=False,
        sort_keys=True,
    )
    return params


def _manifest_id(run_id: str, module: str, source: str) -> str:
    payload = f"{run_id}|{module}|{source}"
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]
    return f"{run_id}:{module}:{digest}"


def _validate(value: str, allowed: set[str], field: str) -> str:
    normalized = str(value)
    if normalized not in allowed:
        raise ValueError(f"{field} must be one of {sorted(allowed)}")
    return normalized


def _date_text(value: object) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)[:10]


def _optional_date_text(value: object | None) -> str | None:
    if value in (None, ""):
        return None
    return _date_text(value)


def _optional_datetime_text(value: object | None) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat(timespec="seconds")
    return str(value)


def _jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    return value


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
