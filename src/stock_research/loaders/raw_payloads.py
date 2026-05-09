import hashlib
import json
from typing import Any

import psycopg


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def payload_hash(payload: Any) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def store_raw_payload(
    conn: psycopg.Connection,
    table_name: str,
    source_endpoint: str,
    request_params: dict[str, Any],
    payload: Any,
    *,
    asset_id: str | None = None,
) -> str:
    digest = payload_hash(payload)
    sql = f"""
    INSERT INTO {table_name} (
        source_endpoint,
        request_params,
        asset_id,
        payload,
        payload_hash
    )
    VALUES (
        %(source_endpoint)s,
        %(request_params)s::jsonb,
        %(asset_id)s,
        %(payload)s::jsonb,
        %(payload_hash)s
    )
    """
    params = {
        "source_endpoint": source_endpoint,
        "request_params": canonical_json(request_params),
        "asset_id": asset_id,
        "payload": canonical_json(payload),
        "payload_hash": digest,
    }
    with conn.cursor() as cur:
        cur.execute(sql, params)
    return digest
