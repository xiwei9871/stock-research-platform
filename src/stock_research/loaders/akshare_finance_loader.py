from typing import Any

import psycopg

from stock_research.loaders.raw_payloads import store_raw_payload


def store_finance_payload(
    conn: psycopg.Connection,
    source_endpoint: str,
    request_params: dict[str, Any],
    payload: Any,
    *,
    asset_id: str | None = None,
) -> str:
    return store_raw_payload(
        conn,
        "raw_akshare.finance_payload",
        source_endpoint,
        request_params,
        payload,
        asset_id=asset_id,
    )
