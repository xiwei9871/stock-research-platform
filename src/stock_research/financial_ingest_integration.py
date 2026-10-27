"""M2-0-D4 — fetch-side integration of raw payload + finver events.

Design contract for production wiring (NOT enabled by default):

  * record_finance_payload() runs INSIDE the caller's existing
    transaction (the same txn that already wraps raw INSERT + the
    normalized-table UPSERT). Raw row, version events, observations
    and chain pointers therefore commit or roll back atomically —
    a raw payload can never persist without its version evidence.
  * feature is gated by `finver_enabled` (default False). Callers pass
    the deployment's switch value; with the switch OFF the function
    stores the raw payload exactly as today.
  * the raw row id is captured via RETURNING so each observation can
    cite raw_payload_id + raw_payload_hash as evidence pointers.

Failure policy: any exception propagates — the whole fetch txn rolls
back (raw + finver + upsert together). Partial success is impossible.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from stock_research.db import fetch_all


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"))


def store_finance_payload_and_version(
    conn,
    asset_id: str,
    endpoint: str,
    request_params: dict[str, Any],
    payload: Any,
    *,
    fetched_at=None,
    finver_schema: str = "finver",
    finver_enabled: bool = False,
) -> dict:
    """Store one raw payload (+ finver evidence when enabled).

    Returns {"raw_payload_id": int, "payload_hash": str,
             "finver": ingest_counters|None}.
    """
    import stock_research.financial_version_store as fvs
    digest = hashlib.sha256(
        canonical_json(payload).encode("utf-8")).hexdigest()
    row = fetch_all(conn, """
        INSERT INTO raw_akshare.finance_payload
          (source_endpoint, request_params, asset_id, payload,
           payload_hash)
        VALUES (%s, %s::jsonb, %s, %s::jsonb, %s)
        RETURNING id, fetched_at""",
                    [endpoint, canonical_json(request_params), asset_id,
                     canonical_json(payload), digest])[0]
    raw_id = row["id"]
    ts = fetched_at if fetched_at is not None else row["fetched_at"]
    fin = None
    if finver_enabled:
        fin = fvs.ingest_payload(conn, finver_schema, asset_id,
                                 endpoint, ts, payload,
                                 raw_payload_id=raw_id,
                                 raw_payload_hash=digest)
    return {"raw_payload_id": raw_id, "payload_hash": digest,
            "finver": fin}
