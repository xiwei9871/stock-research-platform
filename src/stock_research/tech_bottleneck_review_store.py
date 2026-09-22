from __future__ import annotations

import json
from typing import Any

import pandas as pd

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all

SCHEMA_VERSION = "tech_bottleneck_review_store_v1"
META_KEYS = {"summary", "filter_options", "guardrails"}

CREATE_TECH_BOTTLENECK_REVIEW_STORE_SQL = """
CREATE SCHEMA IF NOT EXISTS research;

CREATE TABLE IF NOT EXISTS research.tech_bottleneck_review_universe_stock (
    dataset_version text NOT NULL,
    stock_code text NOT NULL,
    payload jsonb NOT NULL,
    published_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (dataset_version, stock_code)
);

CREATE TABLE IF NOT EXISTS research.tech_bottleneck_review_universe_evidence (
    dataset_version text NOT NULL,
    stock_code text NOT NULL,
    row_index integer NOT NULL,
    payload jsonb NOT NULL,
    published_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (dataset_version, stock_code, row_index)
);

CREATE TABLE IF NOT EXISTS research.tech_bottleneck_review_universe_source (
    dataset_version text NOT NULL,
    stock_code text NOT NULL,
    row_index integer NOT NULL,
    payload jsonb NOT NULL,
    published_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (dataset_version, stock_code, row_index)
);

CREATE TABLE IF NOT EXISTS research.tech_bottleneck_review_universe_meta (
    dataset_version text NOT NULL,
    meta_key text NOT NULL,
    payload jsonb NOT NULL,
    published_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (dataset_version, meta_key)
);

CREATE TABLE IF NOT EXISTS research.tech_bottleneck_review_universe_release (
    release_id integer PRIMARY KEY CHECK (release_id = 1),
    dataset_version text NOT NULL,
    published_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS research.tech_bottleneck_review_decision (
    seq bigint GENERATED ALWAYS AS IDENTITY,
    decision_id text PRIMARY KEY,
    stock_code text NOT NULL,
    reviewer_decision text NOT NULL,
    reviewer text NOT NULL,
    recorded_at timestamptz NOT NULL,
    payload jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_tbrd_stock
    ON research.tech_bottleneck_review_decision (stock_code, seq);
"""


def apply_tech_bottleneck_review_store_schema(service: str = SETTINGS.research_service) -> None:
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute(CREATE_TECH_BOTTLENECK_REVIEW_STORE_SQL)


def publish_review_universe(
    *,
    dataset_version: str,
    dataset_rows: list[dict[str, Any]],
    evidence_rows: list[dict[str, Any]],
    source_rows: list[dict[str, Any]],
    meta: dict[str, Any],
    service: str = SETTINGS.research_service,
) -> dict[str, int]:
    version = str(dataset_version or "").strip()
    if not version:
        raise ValueError("dataset_version required")
    apply_tech_bottleneck_review_store_schema(service=service)
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM research.tech_bottleneck_review_universe_stock WHERE dataset_version = %s",
                (version,),
            )
            cur.execute(
                "DELETE FROM research.tech_bottleneck_review_universe_evidence WHERE dataset_version = %s",
                (version,),
            )
            cur.execute(
                "DELETE FROM research.tech_bottleneck_review_universe_source WHERE dataset_version = %s",
                (version,),
            )
            cur.executemany(
                """
                INSERT INTO research.tech_bottleneck_review_universe_stock
                    (dataset_version, stock_code, payload)
                VALUES (%s, %s, %s::jsonb)
                """,
                [
                    (version, _stock_code(row), _json(row))
                    for row in dataset_rows
                    if _stock_code(row)
                ],
            )
            cur.executemany(
                """
                INSERT INTO research.tech_bottleneck_review_universe_evidence
                    (dataset_version, stock_code, row_index, payload)
                VALUES (%s, %s, %s, %s::jsonb)
                """,
                [
                    (version, _stock_code(row), index, _json(row))
                    for index, row in enumerate(evidence_rows)
                    if _stock_code(row)
                ],
            )
            cur.executemany(
                """
                INSERT INTO research.tech_bottleneck_review_universe_source
                    (dataset_version, stock_code, row_index, payload)
                VALUES (%s, %s, %s, %s::jsonb)
                """,
                [
                    (version, _stock_code(row), index, _json(row))
                    for index, row in enumerate(source_rows)
                    if _stock_code(row)
                ],
            )
            for meta_key, payload in (meta or {}).items():
                if meta_key not in META_KEYS:
                    continue
                cur.execute(
                    """
                    INSERT INTO research.tech_bottleneck_review_universe_meta
                        (dataset_version, meta_key, payload)
                    VALUES (%s, %s, %s::jsonb)
                    ON CONFLICT (dataset_version, meta_key)
                    DO UPDATE SET payload = EXCLUDED.payload, published_at = now()
                    """,
                    (version, meta_key, _json(payload)),
                )
            cur.execute(
                """
                INSERT INTO research.tech_bottleneck_review_universe_release
                    (release_id, dataset_version, published_at)
                VALUES (1, %s, now())
                ON CONFLICT (release_id)
                DO UPDATE SET dataset_version = EXCLUDED.dataset_version, published_at = now()
                """,
                (version,),
            )
    return {
        "dataset_rows": len(dataset_rows),
        "evidence_rows": len(evidence_rows),
        "source_rows": len(source_rows),
    }


def current_dataset_version(service: str = SETTINGS.research_service) -> str | None:
    with connect(service) as conn:
        rows = fetch_all(
            conn,
            "SELECT dataset_version FROM research.tech_bottleneck_review_universe_release WHERE release_id = 1",
        )
    if not rows:
        return None
    return str(rows[0].get("dataset_version") or "") or None


def load_dataset_rows(
    *,
    dataset_version: str | None = None,
    service: str = SETTINGS.research_service,
) -> list[dict[str, Any]]:
    version = dataset_version or current_dataset_version(service=service)
    if not version:
        return []
    with connect(service) as conn:
        rows = fetch_all(
            conn,
            """
            SELECT payload
            FROM research.tech_bottleneck_review_universe_stock
            WHERE dataset_version = %s
            ORDER BY stock_code
            """,
            (version,),
        )
    return [dict(row["payload"]) for row in rows]


def load_evidence_rows(
    *,
    stock_code: str | None = None,
    dataset_version: str | None = None,
    service: str = SETTINGS.research_service,
) -> list[dict[str, Any]]:
    version = dataset_version or current_dataset_version(service=service)
    if not version:
        return []
    sql = """
        SELECT payload
        FROM research.tech_bottleneck_review_universe_evidence
        WHERE dataset_version = %s
    """
    params: list[Any] = [version]
    if stock_code:
        sql += " AND stock_code = %s"
        params.append(stock_code)
    sql += " ORDER BY stock_code, row_index"
    with connect(service) as conn:
        rows = fetch_all(conn, sql, params)
    return [dict(row["payload"]) for row in rows]


def load_source_rows(
    *,
    stock_code: str | None = None,
    dataset_version: str | None = None,
    service: str = SETTINGS.research_service,
) -> list[dict[str, Any]]:
    version = dataset_version or current_dataset_version(service=service)
    if not version:
        return []
    sql = """
        SELECT payload
        FROM research.tech_bottleneck_review_universe_source
        WHERE dataset_version = %s
    """
    params: list[Any] = [version]
    if stock_code:
        sql += " AND stock_code = %s"
        params.append(stock_code)
    sql += " ORDER BY stock_code, row_index"
    with connect(service) as conn:
        rows = fetch_all(conn, sql, params)
    return [dict(row["payload"]) for row in rows]


def load_meta(
    meta_key: str,
    *,
    dataset_version: str | None = None,
    service: str = SETTINGS.research_service,
) -> dict[str, Any] | None:
    version = dataset_version or current_dataset_version(service=service)
    if not version:
        return None
    with connect(service) as conn:
        rows = fetch_all(
            conn,
            """
            SELECT payload
            FROM research.tech_bottleneck_review_universe_meta
            WHERE dataset_version = %s AND meta_key = %s
            """,
            (version, meta_key),
        )
    if not rows:
        return None
    payload = rows[0].get("payload")
    return dict(payload) if isinstance(payload, dict) else None


def list_universe_stock_codes(
    *,
    dataset_version: str | None = None,
    service: str = SETTINGS.research_service,
) -> set[str]:
    version = dataset_version or current_dataset_version(service=service)
    if not version:
        return set()
    with connect(service) as conn:
        rows = fetch_all(
            conn,
            """
            SELECT stock_code
            FROM research.tech_bottleneck_review_universe_stock
            WHERE dataset_version = %s
            """,
            (version,),
        )
    return {str(row["stock_code"]) for row in rows}


def insert_decision(
    payload: dict[str, Any],
    *,
    service: str = SETTINGS.research_service,
) -> str:
    apply_tech_bottleneck_review_store_schema(service=service)
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO research.tech_bottleneck_review_decision
                    (decision_id, stock_code, reviewer_decision, reviewer, recorded_at, payload)
                VALUES (%s, %s, %s, %s, %s, %s::jsonb)
                """,
                (
                    str(payload.get("decision_id") or ""),
                    str(payload.get("stock_code") or ""),
                    str(payload.get("reviewer_decision") or ""),
                    str(payload.get("reviewer") or ""),
                    str(payload.get("recorded_at") or ""),
                    _json(payload),
                ),
            )
    return str(payload.get("decision_id") or "")


def list_decisions(
    *,
    stock_code: str | None = None,
    service: str = SETTINGS.research_service,
) -> list[dict[str, Any]]:
    sql = """
        SELECT payload
        FROM research.tech_bottleneck_review_decision
    """
    params: list[Any] = []
    if stock_code:
        sql += " WHERE stock_code = %s"
        params.append(stock_code)
    sql += " ORDER BY seq"
    with connect(service) as conn:
        rows = fetch_all(conn, sql, params or None)
    return [dict(row["payload"]) for row in rows]


def load_decision_overlay(*, service: str = SETTINGS.research_service) -> dict[str, dict[str, Any]]:
    overlay: dict[str, dict[str, Any]] = {}
    with connect(service) as conn:
        rows = fetch_all(
            conn,
            """
            SELECT DISTINCT ON (stock_code) stock_code, payload
            FROM research.tech_bottleneck_review_decision
            ORDER BY stock_code, seq DESC
            """,
        )
    for row in rows:
        overlay[str(row["stock_code"])] = dict(row["payload"])
    return overlay


def decision_exists(decision_id: str, *, service: str = SETTINGS.research_service) -> bool:
    with connect(service) as conn:
        rows = fetch_all(
            conn,
            """
            SELECT 1 AS present
            FROM research.tech_bottleneck_review_decision
            WHERE decision_id = %s
            """,
            (decision_id,),
        )
    return bool(rows)


def _stock_code(row: dict[str, Any]) -> str:
    raw = str(row.get("stock_code") or "").strip().split(".")[0]
    return raw.zfill(6) if raw.isdigit() else raw.upper()


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
