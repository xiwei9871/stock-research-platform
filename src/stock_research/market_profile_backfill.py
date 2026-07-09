from __future__ import annotations

from collections.abc import Iterable
from contextlib import contextmanager
from typing import Any
import os

from stock_research.config import SETTINGS
from stock_research.db import connect, execute_many, fetch_all
from stock_research.loaders.akshare_finance_loader import store_finance_payload
from stock_research.loaders.baostock_finance_ingestion import upsert_income_statements


PROXY_ENV_KEYS = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
)


@contextmanager
def no_proxy_env():
    previous = {key: os.environ.get(key) for key in (*PROXY_ENV_KEYS, "NO_PROXY", "no_proxy")}
    try:
        for key in PROXY_ENV_KEYS:
            os.environ.pop(key, None)
        os.environ["NO_PROXY"] = "*"
        os.environ["no_proxy"] = "*"
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def normalize_tushare_stock_basic_region_rows(frame) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    if frame is None or frame.empty:
        return rows
    for item in frame.to_dict("records"):
        ts_code = _clean_text(item.get("ts_code"))
        region = _clean_text(item.get("area"))
        asset_id = asset_id_from_ts_code(ts_code)
        if not asset_id or not region:
            continue
        rows.append(
            {
                "asset_id": asset_id,
                "ts_code": ts_code,
                "region": region,
                "source": "tushare:stock_basic",
            }
        )
    return rows


def upsert_asset_region_rows(conn, rows: Iterable[dict[str, str]]) -> int:
    tuples = [
        (row["asset_id"], row["ts_code"], row["region"], row["source"])
        for row in rows
        if _clean_text(row.get("asset_id")) and _clean_text(row.get("region"))
    ]
    if not tuples:
        return 0
    sql = """
    UPDATE core.asset_master AS a
    SET
        region = data.region,
        ts_code = COALESCE(NULLIF(a.ts_code, ''), data.ts_code),
        updated_at = now()
    FROM (VALUES (%s, %s, %s, %s)) AS data(asset_id, ts_code, region, source)
    WHERE a.asset_id = data.asset_id
      AND NULLIF(data.region, '') IS NOT NULL
      AND (
          a.region IS DISTINCT FROM data.region
          OR NULLIF(a.ts_code, '') IS NULL
      )
    """
    execute_many(conn, sql, tuples)
    return len(tuples)


def sync_regions_from_tushare(*, service: str = SETTINGS.research_service) -> dict[str, int]:
    from stock_research.auction_data import tushare_client

    with no_proxy_env():
        client = tushare_client()
        frame = client.stock_basic(
            exchange="",
            list_status="L",
            fields="ts_code,symbol,name,area,industry,market,exchange,list_date,delist_date,is_hs",
        )
    rows = normalize_tushare_stock_basic_region_rows(frame)
    with connect(service) as conn:
        updated = upsert_asset_region_rows(conn, rows)
    return {"source_rows": int(len(frame)), "region_rows": len(rows), "updated_rows": updated}


def normalize_em_profit_sheet_rows(payload: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in payload:
        asset_id = asset_id_from_em_secucode(_clean_text(item.get("SECUCODE")))
        report_period = _date_text(item.get("REPORT_DATE"))
        announcement_date = _date_text(item.get("NOTICE_DATE"))
        if not asset_id or not report_period or not announcement_date:
            continue
        rows.append(
            {
                "asset_id": asset_id,
                "report_period": report_period,
                "report_type": report_type_from_em(item.get("REPORT_TYPE")),
                "announcement_date": announcement_date,
                "revenue": _float_or_none(item.get("OPERATE_INCOME")),
                "operating_profit": _float_or_none(item.get("OPERATE_PROFIT")),
                "total_profit": _float_or_none(item.get("TOTAL_PROFIT")),
                "net_profit": _float_or_none(item.get("NETPROFIT")),
                "np_parent": _float_or_none(item.get("PARENT_NETPROFIT")),
                "np_parent_deducted": _float_or_none(item.get("DEDUCT_PARENT_NETPROFIT")),
                "eps_basic": _float_or_none(item.get("BASIC_EPS")),
                "source": "akshare_em_profit_sheet",
            }
        )
    return rows


def sync_em_profit_sheet_for_asset(
    asset_id: str,
    *,
    service: str = SETTINGS.research_service,
) -> dict[str, int]:
    import akshare as ak

    symbol = em_symbol_from_asset_id(asset_id)
    with no_proxy_env():
        frame = ak.stock_profit_sheet_by_report_em(symbol=symbol)
    payload = _dataframe_payload(frame)
    rows = normalize_em_profit_sheet_rows(payload)
    with connect(service) as conn:
        store_finance_payload(
            conn,
            "stock_profit_sheet_by_report_em",
            {"symbol": symbol},
            payload,
            asset_id=asset_id,
        )
        upserted = upsert_income_statements(conn, rows)
    return {"raw_payload": 1, "income_statement": upserted, "source_rows": len(payload)}


def load_np_parent_gap_assets(
    *,
    limit: int | None = None,
    offset: int = 0,
    service: str = SETTINGS.research_service,
) -> list[str]:
    sql = """
    SELECT a.asset_id
    FROM core.asset_master a
    WHERE a.is_active
      AND a.exchange IN ('SH', 'SZ')
      AND EXISTS (
          SELECT 1
          FROM finance.income_statement i
          WHERE i.asset_id = a.asset_id
      )
      AND NOT EXISTS (
          SELECT 1
          FROM finance.income_statement i
          WHERE i.asset_id = a.asset_id
            AND i.np_parent IS NOT NULL
      )
    ORDER BY a.asset_id
    """
    params: list[Any] = []
    if limit is not None:
        sql += " LIMIT %s OFFSET %s"
        params.extend([limit, offset])
    with connect(service) as conn:
        return [row["asset_id"] for row in fetch_all(conn, sql, params)]


def sync_em_profit_sheet_gap_assets(
    *,
    limit: int,
    offset: int = 0,
    service: str = SETTINGS.research_service,
) -> dict[str, int]:
    assets = load_np_parent_gap_assets(limit=limit, offset=offset, service=service)
    income_rows = 0
    raw_payloads = 0
    failed_assets = 0
    for asset_id in assets:
        try:
            counts = sync_em_profit_sheet_for_asset(asset_id, service=service)
        except Exception:  # noqa: BLE001 - vendor failures should skip a single asset.
            failed_assets += 1
            continue
        income_rows += int(counts.get("income_statement", 0))
        raw_payloads += int(counts.get("raw_payload", 0))
    return {
        "assets": len(assets),
        "income_statement": income_rows,
        "raw_payload": raw_payloads,
        "failed_assets": failed_assets,
    }


def audit_market_profile_gaps(*, service: str = SETTINGS.research_service) -> dict[str, int]:
    sql = """
    WITH active_assets AS (
        SELECT asset_id, region
        FROM core.asset_master
        WHERE is_active AND exchange IN ('SH', 'SZ', 'BJ')
    ),
    active_concepts AS (
        SELECT DISTINCT asset_id
        FROM core.concept_membership
        WHERE end_date IS NULL
    ),
    np_parent_assets AS (
        SELECT DISTINCT asset_id
        FROM finance.income_statement
        WHERE np_parent IS NOT NULL
    )
    SELECT
        count(*) AS active_assets,
        count(*) FILTER (WHERE NULLIF(trim(region), '') IS NOT NULL) AS region_present,
        count(c.asset_id) AS concept_present,
        count(n.asset_id) AS np_parent_present
    FROM active_assets a
    LEFT JOIN active_concepts c USING (asset_id)
    LEFT JOIN np_parent_assets n USING (asset_id)
    """
    with connect(service) as conn:
        row = fetch_all(conn, sql)[0]
    return {key: int(value or 0) for key, value in row.items()}


def asset_id_from_ts_code(ts_code: str) -> str | None:
    if "." not in ts_code:
        return None
    symbol, exchange = ts_code.split(".", 1)
    exchange = exchange.upper()
    if exchange not in {"SH", "SZ", "BJ"}:
        return None
    return f"CN:{exchange}:{symbol.zfill(6)}"


def asset_id_from_em_secucode(secucode: str) -> str | None:
    return asset_id_from_ts_code(secucode)


def em_symbol_from_asset_id(asset_id: str) -> str:
    _market, exchange, symbol = asset_id.split(":", 2)
    return f"{exchange}{symbol}"


def report_type_from_em(value: Any) -> str:
    text = _clean_text(value)
    return "FY" if "年" in text or text.upper() == "FY" else "Q"


def _date_text(value: Any) -> str:
    text = _clean_text(value)
    return text[:10] if len(text) >= 10 else text


def _float_or_none(value: Any) -> float | None:
    text = _clean_text(value)
    if not text:
        return None
    return float(text)


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    if value != value:
        return ""
    text = str(value).strip()
    return "" if text.lower() == "nan" else text


def _dataframe_payload(frame) -> list[dict[str, Any]]:
    records = frame.to_dict("records") if frame is not None else []
    return [_json_safe(record) for record in records]


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, float) and value != value:
        return None
    return value
