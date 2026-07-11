from __future__ import annotations

from collections.abc import Iterable
from concurrent.futures import ProcessPoolExecutor
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from typing import Any
import io
import os
import re

import requests

from stock_research.config import SETTINGS
from stock_research.db import connect, execute_many, fetch_all
from stock_research.eastmoney_http import curl_eastmoney_json
from stock_research.loaders.akshare_finance_loader import store_finance_payload
from stock_research.loaders.baostock_finance_ingestion import upsert_income_statements

try:
    import akshare as ak
except Exception:  # pragma: no cover - dependency is optional in unit tests
    ak = None


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


def normalize_cninfo_stock_profile_region_rows(frame) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    if frame is None or frame.empty:
        return rows
    for item in frame.to_dict("records"):
        symbol = _clean_text(item.get("A股代码")).zfill(6)
        address = _clean_text(item.get("注册地址")) or _clean_text(item.get("办公地址"))
        region = region_from_chinese_address(address)
        ts_code = ts_code_from_symbol(symbol)
        asset_id = asset_id_from_ts_code(ts_code) if ts_code else None
        if not asset_id or not region:
            continue
        rows.append(
            {
                "asset_id": asset_id,
                "ts_code": ts_code,
                "region": region,
                "source": "akshare:stock_profile_cninfo",
            }
        )
    return rows


def normalize_eastmoney_company_survey_region_rows(asset_id: str, payload: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    items = payload.get("jbzl") or []
    if not items:
        return rows
    item = items[0]
    region = (
        _clean_text(item.get("PROVINCE"))
        or region_from_chinese_address(_clean_text(item.get("REG_ADDRESS")))
        or region_from_chinese_address(_clean_text(item.get("ADDRESS")))
    )
    if not region:
        return rows
    secucode = _clean_text(item.get("SECUCODE"))
    if "." in secucode:
        ts_code = secucode
    else:
        _market, exchange, symbol = asset_id.split(":", 2)
        ts_code = f"{symbol}.{exchange}"
    rows.append(
        {
            "asset_id": asset_id,
            "ts_code": ts_code,
            "region": region,
            "source": "eastmoney:PC_HSF10_CompanySurvey",
        }
    )
    return rows


def region_from_chinese_address(address: str) -> str:
    text = _clean_text(address)
    if not text:
        return ""
    for municipality in ("北京", "上海", "天津", "重庆"):
        if text.startswith(f"{municipality}市") or text.startswith(municipality):
            return municipality
    city_match = re.search(r"(?:省|自治区|特别行政区)([^省市县区盟州]{2,12}?)(?:市|地区|盟|州)", text)
    if city_match:
        return _strip_region_suffix(city_match.group(1))
    province_match = re.match(r"(.{2,12}?)(?:省|自治区|特别行政区)", text)
    if province_match:
        return _strip_region_suffix(province_match.group(1))
    city_prefix = re.match(r"(.{2,12}?)市", text)
    if city_prefix:
        return _strip_region_suffix(city_prefix.group(1))
    return ""


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


def normalize_eastmoney_core_conception_rows(
    asset_id: str,
    payload: dict[str, Any],
    *,
    trade_date: str,
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in payload.get("hxtc") or []:
        keyword = _clean_text(item.get("KEYWORD"))
        if not keyword or keyword in {"经营范围"} or _clean_text(item.get("KEY_CLASSIF_CODE")) == "002":
            continue
        if keyword in seen:
            continue
        seen.add(keyword)
        rows.append(
            {
                "asset_id": asset_id,
                "concept_system": "em_core_conception",
                "concept_code": keyword,
                "concept_name": keyword,
                "start_date": trade_date,
                "source": "eastmoney:PC_HSF10_CoreConception",
            }
        )
    return rows


def fetch_eastmoney_core_conception_payload(asset_id: str, *, timeout_seconds: int = 15) -> dict[str, Any]:
    code = eastmoney_hsf10_code_from_asset_id(asset_id)
    url = f"https://emweb.securities.eastmoney.com/PC_HSF10/CoreConception/PageAjax?code={code}"
    response = requests.get(
        url,
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=timeout_seconds,
    )
    response.raise_for_status()
    payload = response.json()
    if isinstance(payload, dict) and payload.get("status") == -1:
        raise RuntimeError(str(payload.get("message") or "eastmoney core conception failed"))
    return payload


def sync_eastmoney_core_conceptions_for_gap_assets(
    *,
    trade_date: str,
    limit: int,
    offset: int = 0,
    service: str = SETTINGS.research_service,
) -> dict[str, int]:
    assets = load_concept_gap_assets(limit=limit, offset=offset, service=service)
    rows: list[dict[str, str]] = []
    failed_assets = 0
    for asset in assets:
        try:
            payload = fetch_eastmoney_core_conception_payload(asset["asset_id"])
            rows.extend(normalize_eastmoney_core_conception_rows(asset["asset_id"], payload, trade_date=trade_date))
        except Exception:  # noqa: BLE001 - vendor failures should skip a single stock.
            failed_assets += 1
    with connect(service) as conn:
        upserted = upsert_concept_membership_rows(conn, rows)
    return {
        "assets": len(assets),
        "concepts": len({row["concept_code"] for row in rows}),
        "memberships": upserted,
        "failed_assets": failed_assets,
    }


def upsert_concept_membership_rows(conn, rows: Iterable[dict[str, str]]) -> int:
    rows = list(rows)
    if not rows:
        return 0
    board_rows = sorted(
        {
            (row["concept_system"], row["concept_code"], row["concept_name"], row["source"], True)
            for row in rows
            if _clean_text(row.get("concept_code")) and _clean_text(row.get("concept_name"))
        }
    )
    member_rows = [
        (
            row["asset_id"],
            row["concept_system"],
            row["concept_code"],
            row["concept_name"],
            row["start_date"],
            row["source"],
        )
        for row in rows
        if _clean_text(row.get("asset_id")) and _clean_text(row.get("concept_code"))
    ]
    board_sql = """
    INSERT INTO core.concept_board (
        concept_system,
        concept_code,
        concept_name,
        source,
        is_active
    )
    VALUES (%s, %s, %s, %s, %s)
    ON CONFLICT (concept_system, concept_code) DO UPDATE SET
        concept_name = EXCLUDED.concept_name,
        source = EXCLUDED.source,
        is_active = EXCLUDED.is_active,
        updated_at = now()
    """
    membership_sql = """
    INSERT INTO core.concept_membership (
        asset_id,
        concept_system,
        concept_code,
        concept_name,
        start_date,
        source
    )
    VALUES (%s, %s, %s, %s, %s, %s)
    ON CONFLICT (asset_id, concept_system, concept_code, start_date) DO UPDATE SET
        concept_name = EXCLUDED.concept_name,
        source = EXCLUDED.source,
        end_date = NULL,
        updated_at = now()
    """
    execute_many(conn, board_sql, board_rows)
    execute_many(conn, membership_sql, member_rows)
    return len(member_rows)


def tushare_client_factory():
    from stock_research.auction_data import tushare_client

    return tushare_client()


def sync_regions_from_tushare(
    *,
    service: str = SETTINGS.research_service,
    fallback_limit: int | None = 200,
    workers: int = 1,
    batch_size: int = 50,
) -> dict[str, int | str]:
    with no_proxy_env():
        try:
            client = tushare_client_factory()
            frame = client.stock_basic(
                exchange="",
                list_status="L",
                fields="ts_code,symbol,name,area,industry,market,exchange,list_date,delist_date,is_hs",
            )
        except Exception:
            return sync_regions_from_akshare_profiles(
                limit=fallback_limit,
                service=service,
                workers=workers,
                batch_size=batch_size,
            )
    rows = normalize_tushare_stock_basic_region_rows(frame)
    with connect(service) as conn:
        updated = upsert_asset_region_rows(conn, rows)
    return {
        "source": "tushare:stock_basic",
        "source_rows": int(len(frame)),
        "region_rows": len(rows),
        "updated_rows": updated,
    }


def sync_regions_from_akshare_profiles(
    *,
    limit: int | None = 200,
    offset: int = 0,
    service: str = SETTINGS.research_service,
    workers: int = 1,
    batch_size: int = 50,
    executor_factory=None,
) -> dict[str, int | str]:
    if ak is None:
        raise RuntimeError("akshare package is required for CNInfo region fallback")
    assets = load_region_gap_assets(limit=limit, offset=offset, service=service)
    source_rows = 0
    region_rows = 0
    updated = 0
    pending_rows: list[dict[str, str]] = []
    with no_proxy_env():
        if max(1, int(workers)) == 1:
            results = map(fetch_cninfo_region_rows_for_asset, assets)
            for fetched_source_rows, rows in results:
                source_rows += fetched_source_rows
                region_rows += len(rows)
                pending_rows.extend(rows)
                if len(pending_rows) >= max(1, int(batch_size)):
                    updated += upsert_region_batch(service, pending_rows)
                    pending_rows = []
        else:
            factory = executor_factory or ProcessPoolExecutor
            with factory(max_workers=max(1, int(workers))) as executor:
                for fetched_source_rows, rows in executor.map(fetch_cninfo_region_rows_for_asset, assets):
                    source_rows += fetched_source_rows
                    region_rows += len(rows)
                    pending_rows.extend(rows)
                    if len(pending_rows) >= max(1, int(batch_size)):
                        updated += upsert_region_batch(service, pending_rows)
                        pending_rows = []
    if pending_rows:
        updated += upsert_region_batch(service, pending_rows)
    return {
        "source": "akshare:stock_profile_cninfo",
        "source_rows": source_rows,
        "region_rows": region_rows,
        "updated_rows": updated,
    }


def sync_regions_from_eastmoney_company_survey(
    *,
    limit: int | None = 200,
    offset: int = 0,
    service: str = SETTINGS.research_service,
    workers: int = 1,
    batch_size: int = 50,
    executor_factory=None,
) -> dict[str, int | str]:
    assets = load_region_gap_assets(limit=limit, offset=offset, service=service)
    source_rows = 0
    region_rows = 0
    updated = 0
    pending_rows: list[dict[str, str]] = []
    if max(1, int(workers)) == 1:
        results = map(fetch_eastmoney_company_survey_region_rows_for_asset, assets)
        for fetched_source_rows, rows in results:
            source_rows += fetched_source_rows
            region_rows += len(rows)
            pending_rows.extend(rows)
            if len(pending_rows) >= max(1, int(batch_size)):
                updated += upsert_region_batch(service, pending_rows)
                pending_rows = []
    else:
        factory = executor_factory or ProcessPoolExecutor
        with factory(max_workers=max(1, int(workers))) as executor:
            for fetched_source_rows, rows in executor.map(fetch_eastmoney_company_survey_region_rows_for_asset, assets):
                source_rows += fetched_source_rows
                region_rows += len(rows)
                pending_rows.extend(rows)
                if len(pending_rows) >= max(1, int(batch_size)):
                    updated += upsert_region_batch(service, pending_rows)
                    pending_rows = []
    if pending_rows:
        updated += upsert_region_batch(service, pending_rows)
    return {
        "source": "eastmoney:PC_HSF10_CompanySurvey",
        "source_rows": source_rows,
        "region_rows": region_rows,
        "updated_rows": updated,
    }


def fetch_cninfo_region_rows_for_asset(asset: dict[str, str]) -> tuple[int, list[dict[str, str]]]:
    try:
        frame = ak.stock_profile_cninfo(symbol=asset["symbol"])
    except Exception:
        return 0, []
    return int(len(frame)), normalize_cninfo_stock_profile_region_rows(frame)


def fetch_eastmoney_company_survey_region_rows_for_asset(asset: dict[str, str]) -> tuple[int, list[dict[str, str]]]:
    try:
        payload = fetch_eastmoney_company_survey_payload(asset["asset_id"])
    except Exception:
        return 0, []
    source_rows = len(payload.get("jbzl") or [])
    return source_rows, normalize_eastmoney_company_survey_region_rows(asset["asset_id"], payload)


def fetch_eastmoney_company_survey_payload(asset_id: str) -> dict[str, Any]:
    code = eastmoney_hsf10_code_from_asset_id(asset_id)
    return curl_eastmoney_json(
        "https://emweb.securities.eastmoney.com/PC_HSF10/CompanySurvey/PageAjax",
        {"code": code},
        retries=2,
        retry_sleep_seconds=1,
        timeout_seconds=15,
    )


def upsert_region_batch(service: str, rows: list[dict[str, str]]) -> int:
    with connect(service) as conn:
        return upsert_asset_region_rows(conn, rows)


def load_region_gap_assets(
    *,
    limit: int | None = 200,
    offset: int = 0,
    service: str = SETTINGS.research_service,
) -> list[dict[str, str]]:
    sql = """
    SELECT asset_id, symbol
    FROM core.asset_master
    WHERE is_active
      AND exchange IN ('SH', 'SZ', 'BJ')
      AND NULLIF(trim(region), '') IS NULL
    ORDER BY asset_id
    """
    params: list[Any] = []
    if limit is not None:
        sql += " LIMIT %s OFFSET %s"
        params.extend([limit, offset])
    with connect(service) as conn:
        return [
            {"asset_id": row["asset_id"], "symbol": str(row["symbol"]).zfill(6)}
            for row in fetch_all(conn, sql, params)
        ]


def load_concept_gap_assets(
    *,
    limit: int | None = None,
    offset: int = 0,
    service: str = SETTINGS.research_service,
) -> list[dict[str, str]]:
    sql = """
    SELECT asset_id, symbol, exchange
    FROM core.asset_master a
    WHERE a.is_active
      AND a.exchange IN ('SH', 'SZ', 'BJ')
      AND NOT EXISTS (
          SELECT 1
          FROM core.concept_membership m
          WHERE m.asset_id = a.asset_id
            AND m.end_date IS NULL
      )
    ORDER BY a.asset_id
    """
    params: list[Any] = []
    if limit is not None:
        sql += " LIMIT %s OFFSET %s"
        params.extend([limit, offset])
    with connect(service) as conn:
        return [
            {
                "asset_id": row["asset_id"],
                "symbol": str(row["symbol"]).zfill(6),
                "exchange": row["exchange"],
            }
            for row in fetch_all(conn, sql, params)
        ]


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
    request_params = {"symbol": symbol}
    try:
        with no_proxy_env(), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            frame = ak.stock_profit_sheet_by_report_em(symbol=symbol)
        payload = _dataframe_payload(frame)
    except Exception:
        payload = fetch_eastmoney_profit_sheet_payload_direct(asset_id)
        request_params = {"symbol": symbol, "fallback": "eastmoney_direct"}
    rows = normalize_em_profit_sheet_rows(payload)
    with connect(service) as conn:
        store_finance_payload(
            conn,
            "stock_profit_sheet_by_report_em",
            request_params,
            payload,
            asset_id=asset_id,
        )
        upserted = upsert_income_statements(conn, rows)
    return {"raw_payload": 1, "income_statement": upserted, "source_rows": len(payload)}


def fetch_eastmoney_profit_sheet_payload_direct(asset_id: str) -> list[dict[str, Any]]:
    code = eastmoney_hsf10_code_from_asset_id(asset_id)
    date_payload = curl_eastmoney_json(
        "https://emweb.securities.eastmoney.com/PC_HSF10/NewFinanceAnalysis/lrbDateAjaxNew",
        {"companyType": "4", "reportDateType": "0", "code": code},
        retries=2,
        retry_sleep_seconds=1,
        timeout_seconds=15,
    )
    dates = [_clean_text(item.get("REPORT_DATE")) for item in date_payload.get("data") or []]
    dates = [date for date in dates if date]
    rows: list[dict[str, Any]] = []
    for chunk in _chunks(dates, 5):
        payload = curl_eastmoney_json(
            "https://emweb.securities.eastmoney.com/PC_HSF10/NewFinanceAnalysis/lrbAjaxNew",
            {
                "companyType": "4",
                "reportDateType": "0",
                "reportType": "1",
                "code": code,
                "dates": ",".join(chunk),
            },
            retries=2,
            retry_sleep_seconds=1,
            timeout_seconds=15,
        )
        rows.extend(payload.get("data") or [])
    return rows


def _chunks(values: list[str], size: int) -> Iterable[list[str]]:
    for index in range(0, len(values), size):
        yield values[index : index + size]


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
    workers: int = 1,
    executor_factory=None,
) -> dict[str, int]:
    assets = load_np_parent_gap_assets(limit=limit, offset=offset, service=service)
    income_rows = 0
    raw_payloads = 0
    failed_assets = 0
    if max(1, int(workers)) == 1:
        results = [sync_em_profit_sheet_for_asset_worker((asset_id, service)) for asset_id in assets]
    else:
        factory = executor_factory or ProcessPoolExecutor
        with factory(max_workers=max(1, int(workers))) as executor:
            results = list(executor.map(sync_em_profit_sheet_for_asset_worker, [(asset_id, service) for asset_id in assets]))
    for counts in results:
        failed_assets += int(counts.get("failed", 0))
        income_rows += int(counts.get("income_statement", 0))
        raw_payloads += int(counts.get("raw_payload", 0))
    return {
        "assets": len(assets),
        "income_statement": income_rows,
        "raw_payload": raw_payloads,
        "failed_assets": failed_assets,
    }


def sync_em_profit_sheet_for_asset_worker(item: tuple[str, str]) -> dict[str, int]:
    asset_id, service = item
    try:
        counts = sync_em_profit_sheet_for_asset_with_retry(asset_id, service=service)
    except Exception:  # noqa: BLE001 - vendor failures should skip a single asset.
        return {"raw_payload": 0, "income_statement": 0, "failed": 1}
    return {
        "raw_payload": int(counts.get("raw_payload", 0)),
        "income_statement": int(counts.get("income_statement", 0)),
        "failed": 0,
    }


def sync_em_profit_sheet_for_asset_with_retry(
    asset_id: str,
    *,
    service: str = SETTINGS.research_service,
) -> dict[str, int]:
    last_error: Exception | None = None
    for _attempt in range(2):
        try:
            return sync_em_profit_sheet_for_asset(asset_id, service=service)
        except Exception as exc:  # noqa: BLE001 - vendor retry boundary.
            last_error = exc
    if last_error is not None:
        raise last_error
    raise RuntimeError(f"profit sheet retry failed without an exception: {asset_id}")


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
        count(*) FILTER (WHERE NULLIF(trim(region), '') IS NULL) AS region_gap,
        count(c.asset_id) AS concept_present,
        count(*) FILTER (WHERE c.asset_id IS NULL) AS concept_gap,
        count(n.asset_id) AS np_parent_present,
        count(*) FILTER (WHERE n.asset_id IS NULL) AS np_parent_gap
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


def ts_code_from_symbol(symbol: str) -> str | None:
    symbol = _clean_text(symbol).zfill(6)
    if symbol.startswith(("600", "601", "603", "605", "688", "689")):
        return f"{symbol}.SH"
    if symbol.startswith(("000", "001", "002", "003", "300", "301", "302")):
        return f"{symbol}.SZ"
    if symbol.startswith(("43", "83", "87", "92")):
        return f"{symbol}.BJ"
    return None


def eastmoney_hsf10_code_from_asset_id(asset_id: str) -> str:
    _market, exchange, symbol = asset_id.split(":", 2)
    if exchange not in {"SH", "SZ"}:
        raise ValueError(f"unsupported EastMoney HSF10 exchange: {asset_id}")
    return f"{exchange}{symbol}"


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


def _strip_region_suffix(value: str) -> str:
    text = _clean_text(value)
    for suffix in ("维吾尔", "壮族", "回族", "藏族", "蒙古", "朝鲜族", "哈萨克", "土家族苗族", "彝族"):
        text = text.replace(suffix, "")
    return text.strip()


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
