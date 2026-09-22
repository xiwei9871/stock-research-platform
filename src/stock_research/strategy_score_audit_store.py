from __future__ import annotations

import json
from typing import Any

import pandas as pd

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all

CREATE_STRATEGY_SCORE_AUDIT_SQL = """
CREATE SCHEMA IF NOT EXISTS ops;

CREATE TABLE IF NOT EXISTS ops.strategy_score_audit_summary (
    trade_date date PRIMARY KEY,
    status text NOT NULL DEFAULT 'success',
    payload jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ops.strategy_score_audit_detail (
    trade_date date NOT NULL,
    strategy_id text NOT NULL,
    asset_id text NOT NULL,
    row_index integer NOT NULL,
    payload jsonb NOT NULL,
    PRIMARY KEY (trade_date, row_index)
);

CREATE INDEX IF NOT EXISTS idx_score_audit_detail_strategy
    ON ops.strategy_score_audit_detail (trade_date, strategy_id);
"""


def apply_strategy_score_audit_schema(service: str = SETTINGS.research_service) -> None:
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute(CREATE_STRATEGY_SCORE_AUDIT_SQL)


def upsert_score_audit(
    *,
    trade_date: str,
    summary: dict[str, Any],
    detail_rows: list[dict[str, Any]],
    service: str = SETTINGS.research_service,
) -> int:
    if not trade_date:
        raise ValueError("trade_date required")
    apply_strategy_score_audit_schema(service=service)
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM ops.strategy_score_audit_detail WHERE trade_date = %s",
                (trade_date,),
            )
            cur.executemany(
                """
                INSERT INTO ops.strategy_score_audit_detail
                    (trade_date, strategy_id, asset_id, row_index, payload)
                VALUES (%s, %s, %s, %s, %s::jsonb)
                """,
                [
                    (
                        trade_date,
                        str(row.get("strategy_id") or ""),
                        str(row.get("asset_id") or ""),
                        index,
                        _json(row),
                    )
                    for index, row in enumerate(detail_rows)
                ],
            )
            cur.execute(
                """
                INSERT INTO ops.strategy_score_audit_summary
                    (trade_date, status, payload)
                VALUES (%s, %s, %s::jsonb)
                ON CONFLICT (trade_date)
                DO UPDATE SET
                    status = EXCLUDED.status,
                    payload = EXCLUDED.payload,
                    updated_at = now()
                """,
                (
                    trade_date,
                    str(summary.get("status") or "success"),
                    _json(summary),
                ),
            )
    return len(detail_rows)


def upsert_score_audit_failure(
    *,
    trade_date: str,
    summary: dict[str, Any],
    service: str = SETTINGS.research_service,
) -> None:
    apply_strategy_score_audit_schema(service=service)
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO ops.strategy_score_audit_summary
                    (trade_date, status, payload)
                VALUES (%s, %s, %s::jsonb)
                ON CONFLICT (trade_date)
                DO UPDATE SET
                    status = EXCLUDED.status,
                    payload = EXCLUDED.payload,
                    updated_at = now()
                """,
                (
                    trade_date,
                    str(summary.get("status") or "failed"),
                    _json(summary),
                ),
            )


def load_score_audit_summary(
    *,
    trade_date: str,
    service: str = SETTINGS.research_service,
) -> dict[str, Any] | None:
    with connect(service) as conn:
        rows = fetch_all(
            conn,
            """
            SELECT payload
            FROM ops.strategy_score_audit_summary
            WHERE trade_date = %s
            """,
            (trade_date,),
        )
    if not rows:
        return None
    payload = rows[0].get("payload")
    return dict(payload) if isinstance(payload, dict) else None


def load_score_audit_detail_rows(
    *,
    trade_date: str,
    strategy_id: str | None = None,
    limit: int | None = None,
    service: str = SETTINGS.research_service,
) -> list[dict[str, Any]]:
    sql = """
        SELECT payload
        FROM ops.strategy_score_audit_detail
        WHERE trade_date = %s
    """
    params: list[Any] = [trade_date]
    if strategy_id:
        sql += " AND strategy_id = %s"
        params.append(strategy_id)
    sql += " ORDER BY row_index"
    if limit is not None:
        sql += " LIMIT %s"
        params.append(int(limit))
    with connect(service) as conn:
        rows = fetch_all(conn, sql, params)
    return [dict(row["payload"]) for row in rows]


def _json(value: Any) -> str:
    return json.dumps(_jsonable(value), ensure_ascii=False, sort_keys=True)


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if value is None or isinstance(value, (str, int, bool)):
        return value
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, float):
        return value
    return str(value)
