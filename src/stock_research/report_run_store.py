import hashlib
import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

from stock_research.config import SETTINGS
from stock_research.db import connect


CREATE_REPORT_RUN_SQL = """
CREATE SCHEMA IF NOT EXISTS report;

CREATE TABLE IF NOT EXISTS report.report_run (
    run_id text PRIMARY KEY,
    trade_date date NOT NULL,
    report_type text NOT NULL,
    status text NOT NULL,
    report_paths jsonb NOT NULL DEFAULT '{}'::jsonb,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_report_run_trade_date
    ON report.report_run (trade_date, report_type, updated_at DESC);
"""


def apply_report_run_schema(service: str = SETTINGS.research_service) -> None:
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute(CREATE_REPORT_RUN_SQL)


def record_report_run(
    trade_date: object,
    report_type: str,
    report_paths: dict[str, Any],
    status: str = "completed",
    metadata: dict[str, Any] | None = None,
    service: str = SETTINGS.research_service,
) -> str:
    date_text = _date_text(trade_date)
    paths_json = json.dumps(_jsonable(report_paths), ensure_ascii=False, sort_keys=True)
    metadata_json = json.dumps(_jsonable(metadata or {}), ensure_ascii=False, sort_keys=True)
    run_id = _run_id(date_text, report_type, paths_json)
    sql = """
    INSERT INTO report.report_run (
        run_id, trade_date, report_type, status, report_paths, metadata
    )
    VALUES (
        %(run_id)s, %(trade_date)s, %(report_type)s, %(status)s,
        %(report_paths)s::jsonb, %(metadata)s::jsonb
    )
    ON CONFLICT (run_id)
    DO UPDATE SET
        status = EXCLUDED.status,
        report_paths = EXCLUDED.report_paths,
        metadata = EXCLUDED.metadata,
        updated_at = now()
    """
    params = {
        "run_id": run_id,
        "trade_date": date_text,
        "report_type": report_type,
        "status": status,
        "report_paths": paths_json,
        "metadata": metadata_json,
    }
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
    return run_id


def _run_id(trade_date: str, report_type: str, paths_json: str) -> str:
    digest = hashlib.sha1(paths_json.encode("utf-8")).hexdigest()[:12]
    return f"{report_type}:{trade_date}:{digest}"


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
