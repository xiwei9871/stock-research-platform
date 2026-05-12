import hashlib
import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

from stock_research.config import SETTINGS
from stock_research.db import connect

CREATE_DAILY_JOB_RUN_SQL = """
CREATE SCHEMA IF NOT EXISTS ops;

CREATE TABLE IF NOT EXISTS ops.daily_job_run (
    run_id text PRIMARY KEY,
    trade_date date NOT NULL,
    step text NOT NULL,
    status text NOT NULL,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    error_message text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_daily_job_run_trade_date
    ON ops.daily_job_run (trade_date, step, updated_at DESC);
"""


def apply_daily_job_run_schema(service: str = SETTINGS.research_service) -> None:
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute(CREATE_DAILY_JOB_RUN_SQL)


def record_daily_job_run(
    trade_date: object,
    step: str,
    status: str,
    metadata: dict[str, Any] | None = None,
    error_message: str | None = None,
    service: str = SETTINGS.research_service,
) -> str:
    date_text = _date_text(trade_date)
    metadata_json = json.dumps(
        _jsonable(metadata or {}),
        ensure_ascii=False,
        sort_keys=True,
    )
    run_id = _run_id(date_text, step, status, metadata_json, error_message)
    sql = """
    INSERT INTO ops.daily_job_run (
        run_id, trade_date, step, status, metadata, error_message
    )
    VALUES (
        %(run_id)s, %(trade_date)s, %(step)s, %(status)s,
        %(metadata)s::jsonb, %(error_message)s
    )
    ON CONFLICT (run_id)
    DO UPDATE SET
        status = EXCLUDED.status,
        metadata = EXCLUDED.metadata,
        error_message = EXCLUDED.error_message,
        updated_at = now()
    """
    params = {
        "run_id": run_id,
        "trade_date": date_text,
        "step": step,
        "status": status,
        "metadata": metadata_json,
        "error_message": error_message,
    }
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
    return run_id


def _run_id(
    trade_date: str,
    step: str,
    status: str,
    metadata_json: str,
    error_message: str | None,
) -> str:
    payload = "|".join([trade_date, step, status, metadata_json, error_message or ""])
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]
    return f"daily_job:{trade_date}:{step}:{digest}"


def _date_text(value: object) -> str:
    if isinstance(value, pd_timestamp_types()):
        return value.date().isoformat()
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)[:10]


def _jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    return value


def pd_timestamp_types() -> tuple[type, ...]:
    try:
        import pandas as pd

        return (pd.Timestamp,)
    except Exception:
        return ()
