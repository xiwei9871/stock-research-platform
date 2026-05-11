import re
import json
from typing import Any

import baostock as bs

from stock_research.assets import asset_id_from_baostock_code
from stock_research.config import SETTINGS
from stock_research.db import connect, execute, execute_many, fetch_all
from stock_research.loaders.raw_payloads import canonical_json, payload_hash


INDEX_TARGETS = {
    "SSE_COMPOSITE": "sh.000001",
    "SZSE_COMPONENT": "sz.399001",
    "CSI_300": "sh.000300",
    "CSI_500": "sh.000905",
    "CSI_1000": "sh.000852",
    "CHINEXT": "sz.399006",
}

INDEX_CONSTITUENT_TARGETS = {
    "SSE_50": bs.query_sz50_stocks,
    "CSI_300": bs.query_hs300_stocks,
    "CSI_500": bs.query_zz500_stocks,
}

INDUSTRY_SNAPSHOT_ENDPOINT = "query_stock_industry"
INDUSTRY_QUERY_MAX_ATTEMPTS = 3
INDUSTRY_QUERY_RETRY_ERROR_CODES = {"10001001"}


def parse_float(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if text == "":
        return None
    return float(text)


def normalize_industry_system(value: str) -> str:
    if value == "证监会行业分类":
        return "csrc"
    return value.strip().lower() or "unknown"


def split_industry(value: str) -> tuple[str, str]:
    text = value.strip()
    if not text:
        return "", ""
    match = re.match(r"^([A-Z]\d{2})(.+)$", text)
    if match:
        return match.group(1), match.group(2)
    return text, text


def normalize_industry_row(
    row: dict[str, Any],
    effective_date: str | None = None,
) -> dict[str, Any]:
    industry_code, industry_name = split_industry(str(row.get("industry", "")))
    return {
        "asset_id": asset_id_from_baostock_code(str(row["code"])),
        "industry_system": normalize_industry_system(
            str(row.get("industryClassification", ""))
        ),
        "industry_code": industry_code,
        "industry_name": industry_name,
        "level": 1,
        "start_date": effective_date or str(row["updateDate"]),
        "end_date": None,
        "source": "baostock",
    }


def upsert_industry_memberships(conn, rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    sql = """
    INSERT INTO core.industry_membership (
        asset_id,
        industry_system,
        industry_code,
        industry_name,
        level,
        start_date,
        end_date,
        source
    )
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (asset_id, industry_system, industry_code, level, start_date)
    DO UPDATE SET
        industry_name = EXCLUDED.industry_name,
        end_date = EXCLUDED.end_date,
        source = EXCLUDED.source,
        updated_at = now()
    """
    execute_many(
        conn,
        sql,
        [
            (
                row["asset_id"],
                row["industry_system"],
                row["industry_code"],
                row["industry_name"],
                row["level"],
                row["start_date"],
                row["end_date"],
                row["source"],
            )
            for row in rows
        ],
    )
    return len(rows)


def store_industry_snapshot_payload(
    conn,
    snapshot_date: str,
    rows: list[dict[str, Any]],
) -> str:
    payload = rows
    digest = payload_hash(payload)
    sql = """
    INSERT INTO raw_baostock.industry_snapshot_payload (
        snapshot_date,
        source_endpoint,
        request_params,
        payload,
        payload_hash,
        row_count
    )
    VALUES (
        %(snapshot_date)s,
        %(source_endpoint)s,
        %(request_params)s::jsonb,
        %(payload)s::jsonb,
        %(payload_hash)s,
        %(row_count)s
    )
    ON CONFLICT (snapshot_date, source_endpoint) DO UPDATE SET
        request_params = EXCLUDED.request_params,
        payload = EXCLUDED.payload,
        payload_hash = EXCLUDED.payload_hash,
        row_count = EXCLUDED.row_count,
        fetched_at = now()
    """
    execute(
        conn,
        sql,
        {
            "snapshot_date": snapshot_date,
            "source_endpoint": INDUSTRY_SNAPSHOT_ENDPOINT,
            "request_params": canonical_json({"date": snapshot_date}),
            "payload": canonical_json(payload),
            "payload_hash": digest,
            "row_count": len(rows),
        },
    )
    return digest


def load_cached_industry_snapshot_payload(
    conn,
    snapshot_date: str,
) -> list[dict[str, Any]] | None:
    sql = """
    SELECT payload
    FROM raw_baostock.industry_snapshot_payload
    WHERE snapshot_date = %s
      AND source_endpoint = %s
    """
    rows = fetch_all(conn, sql, [snapshot_date, INDUSTRY_SNAPSHOT_ENDPOINT])
    if not rows:
        return None
    payload = rows[0]["payload"]
    if isinstance(payload, str):
        return json.loads(payload)
    return list(payload)


def normalize_index_row(index_id: str, row: dict[str, Any]) -> dict[str, Any]:
    return {
        "index_id": index_id,
        "trade_date": str(row["date"]),
        "open": parse_float(row.get("open")),
        "high": parse_float(row.get("high")),
        "low": parse_float(row.get("low")),
        "close": parse_float(row.get("close")),
        "preclose": parse_float(row.get("preclose")),
        "volume": parse_float(row.get("volume")),
        "amount": parse_float(row.get("amount")),
        "source": "baostock",
    }


def upsert_index_daily_bars(conn, rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    sql = """
    INSERT INTO market.index_daily_bar (
        index_id,
        trade_date,
        open,
        high,
        low,
        close,
        preclose,
        volume,
        amount,
        source
    )
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (index_id, trade_date) DO UPDATE SET
        open = EXCLUDED.open,
        high = EXCLUDED.high,
        low = EXCLUDED.low,
        close = EXCLUDED.close,
        preclose = EXCLUDED.preclose,
        volume = EXCLUDED.volume,
        amount = EXCLUDED.amount,
        source = EXCLUDED.source,
        updated_at = now()
    """
    execute_many(
        conn,
        sql,
        [
            (
                row["index_id"],
                row["trade_date"],
                row["open"],
                row["high"],
                row["low"],
                row["close"],
                row["preclose"],
                row["volume"],
                row["amount"],
                row["source"],
            )
            for row in rows
        ],
    )
    return len(rows)


def normalize_index_constituent_row(
    index_id: str,
    trade_date: str,
    row: dict[str, Any],
    source_version: str,
) -> dict[str, Any]:
    return {
        "index_id": index_id,
        "asset_id": asset_id_from_baostock_code(str(row["code"])),
        "start_date": trade_date,
        "end_date": None,
        "weight": parse_float(row.get("weight")),
        "source": "baostock",
        "source_version": source_version,
    }


def upsert_index_constituents(conn, rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    sql = """
    INSERT INTO market.index_constituent (
        index_id,
        asset_id,
        start_date,
        end_date,
        weight,
        source,
        source_version
    )
    VALUES (%s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (index_id, asset_id, start_date, source_version) DO UPDATE SET
        end_date = EXCLUDED.end_date,
        weight = EXCLUDED.weight,
        source = EXCLUDED.source,
        updated_at = now()
    """
    execute_many(
        conn,
        sql,
        [
            (
                row["index_id"],
                row["asset_id"],
                row["start_date"],
                row["end_date"],
                row["weight"],
                row["source"],
                row["source_version"],
            )
            for row in rows
        ],
    )
    return len(rows)


def _rows_from_result(rs) -> list[dict[str, str]]:
    rows = []
    while rs.next():
        rows.append(dict(zip(rs.fields, rs.get_row_data(), strict=True)))
    return rows


def _query_industry_snapshot_rows(trade_date: str) -> list[dict[str, str]]:
    for attempt in range(1, INDUSTRY_QUERY_MAX_ATTEMPTS + 1):
        login = bs.login()
        if login.error_code != "0":
            raise RuntimeError(f"baostock login failed: {login.error_code} {login.error_msg}")
        try:
            rs = bs.query_stock_industry(date=trade_date)
            if rs.error_code == "0":
                return _rows_from_result(rs)
            if (
                rs.error_code not in INDUSTRY_QUERY_RETRY_ERROR_CODES
                or attempt == INDUSTRY_QUERY_MAX_ATTEMPTS
            ):
                raise RuntimeError(
                    f"baostock industry query failed: {rs.error_code} {rs.error_msg}"
                )
        finally:
            bs.logout()
    raise RuntimeError("baostock industry query failed after retries")


def sync_industry_memberships(
    trade_date: str,
    service: str = SETTINGS.research_service,
    use_cache: bool = True,
) -> int:
    if use_cache:
        with connect(service) as conn:
            cached_rows = load_cached_industry_snapshot_payload(conn, trade_date)
            if cached_rows is not None:
                rows = [
                    normalize_industry_row(row, effective_date=trade_date)
                    for row in cached_rows
                    if str(row.get("industry", "")).strip()
                ]
                return upsert_industry_memberships(conn, rows)

    raw_rows = _query_industry_snapshot_rows(trade_date)
    rows = [
        normalize_industry_row(row, effective_date=trade_date)
        for row in raw_rows
        if str(row.get("industry", "")).strip()
    ]
    with connect(service) as conn:
        store_industry_snapshot_payload(conn, trade_date, raw_rows)
        return upsert_industry_memberships(conn, rows)


def sync_index_daily_bars(
    start_date: str,
    end_date: str,
    service: str = SETTINGS.research_service,
) -> int:
    login = bs.login()
    if login.error_code != "0":
        raise RuntimeError(f"baostock login failed: {login.error_code} {login.error_msg}")
    try:
        rows = []
        for index_id, code in INDEX_TARGETS.items():
            rs = bs.query_history_k_data_plus(
                code,
                "date,code,open,high,low,close,preclose,volume,amount,pctChg",
                start_date=start_date,
                end_date=end_date,
                frequency="d",
            )
            if rs.error_code != "0":
                raise RuntimeError(
                    f"baostock index query failed for {code}: "
                    f"{rs.error_code} {rs.error_msg}"
                )
            rows.extend(normalize_index_row(index_id, row) for row in _rows_from_result(rs))
        with connect(service) as conn:
            return upsert_index_daily_bars(conn, rows)
    finally:
        bs.logout()


def sync_index_constituents(
    trade_date: str,
    index_ids: list[str] | None = None,
    source_version: str = "baostock_snapshot_v1",
    service: str = SETTINGS.research_service,
) -> int:
    login = bs.login()
    if login.error_code != "0":
        raise RuntimeError(f"baostock login failed: {login.error_code} {login.error_msg}")
    try:
        selected = index_ids if index_ids is not None else list(INDEX_CONSTITUENT_TARGETS)
        rows = []
        for index_id in selected:
            query_fn = INDEX_CONSTITUENT_TARGETS.get(index_id)
            if query_fn is None:
                raise ValueError(f"Unsupported index constituent target: {index_id}")
            rs = query_fn(date=trade_date)
            if rs.error_code != "0":
                raise RuntimeError(
                    f"baostock constituent query failed for {index_id}: "
                    f"{rs.error_code} {rs.error_msg}"
                )
            rows.extend(
                normalize_index_constituent_row(index_id, trade_date, row, source_version)
                for row in _rows_from_result(rs)
            )
        with connect(service) as conn:
            return upsert_index_constituents(conn, rows)
    finally:
        bs.logout()
