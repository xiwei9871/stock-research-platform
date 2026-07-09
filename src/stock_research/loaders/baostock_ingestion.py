import re
import json
import time
from typing import Any

import pandas as pd
import baostock as bs
import requests

from stock_research.assets import asset_id_from_baostock_code
from stock_research.config import SETTINGS
from stock_research.db import connect, execute, execute_many, fetch_all
from stock_research.eastmoney_http import curl_eastmoney_json
from stock_research.loaders.raw_payloads import canonical_json, payload_hash


INDEX_TARGETS = {
    "SSE_COMPOSITE": "sh.000001",
    "SZSE_COMPONENT": "sz.399001",
    "CSI_300": "sh.000300",
    "CSI_500": "sh.000905",
    "CSI_1000": "sh.000852",
    "CHINEXT": "sz.399006",
}

AKSHARE_INDEX_TARGETS = {
    "STAR_50": "sh000688",
    "BSE_50": "bj899050",
}

EASTMONEY_INDEX_KLINE_URLS = [
    "https://push2his.eastmoney.com/api/qt/stock/kline/get",
    "https://33.push2his.eastmoney.com/api/qt/stock/kline/get",
    "https://63.push2his.eastmoney.com/api/qt/stock/kline/get",
    "https://82.push2his.eastmoney.com/api/qt/stock/kline/get",
]
TENCENT_INDEX_KLINE_URL = "https://web.ifzq.gtimg.cn/appstock/app/kline/kline"
TENCENT_INDEX_TARGETS = {
    "STAR_50": "sh000688",
    "BSE_50": "bj899050",
}

INDEX_CONSTITUENT_TARGETS = {
    "SSE_50": bs.query_sz50_stocks,
    "CSI_300": bs.query_hs300_stocks,
    "CSI_500": bs.query_zz500_stocks,
}

BAOSTOCK_LOGIN_MAX_ATTEMPTS = 5
BAOSTOCK_LOGIN_RETRY_SECONDS = 2
BAOSTOCK_LOGIN_RETRY_ERROR_CODES = {"10002007"}
INDEX_CONSTITUENT_QUERY_MAX_ATTEMPTS = 3
INDEX_CONSTITUENT_QUERY_RETRY_ERROR_CODES = {"10001001"}
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


def _login_or_raise():
    last_error = ""
    for attempt in range(BAOSTOCK_LOGIN_MAX_ATTEMPTS):
        login = bs.login()
        if login.error_code == "0":
            return login
        last_error = f"{login.error_code} {login.error_msg}"
        if (
            login.error_code not in BAOSTOCK_LOGIN_RETRY_ERROR_CODES
            or attempt + 1 >= BAOSTOCK_LOGIN_MAX_ATTEMPTS
        ):
            break
        time.sleep(BAOSTOCK_LOGIN_RETRY_SECONDS)
    raise RuntimeError(f"baostock login failed: {last_error}")


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


def normalize_akshare_index_daily_rows(
    index_id: str,
    frame: pd.DataFrame,
    *,
    start_date: str,
    end_date: str,
) -> list[dict[str, Any]]:
    if frame.empty:
        return []
    normalized = frame.copy()
    normalized["trade_date"] = pd.to_datetime(normalized["date"], errors="coerce").dt.date.astype(str)
    normalized = normalized.sort_values("trade_date").reset_index(drop=True)
    normalized["preclose"] = pd.to_numeric(normalized["close"], errors="coerce").shift(1)
    selected = normalized[
        normalized["trade_date"].between(str(start_date), str(end_date), inclusive="both")
    ]
    rows: list[dict[str, Any]] = []
    for raw_row in selected.to_dict("records"):
        rows.append(
            {
                "index_id": index_id,
                "trade_date": str(raw_row["trade_date"]),
                "open": parse_float(raw_row.get("open")),
                "high": parse_float(raw_row.get("high")),
                "low": parse_float(raw_row.get("low")),
                "close": parse_float(raw_row.get("close")),
                "preclose": parse_float(raw_row.get("preclose")),
                "volume": parse_float(raw_row.get("volume")),
                "amount": parse_float(raw_row.get("amount")),
                "source": "akshare",
            }
        )
    return rows


def eastmoney_index_secid(symbol: str) -> str:
    market = symbol[:2].lower()
    code = symbol[2:]
    if market == "sh":
        return f"1.{code}"
    if market in {"sz", "bj"}:
        return f"0.{code}"
    raise ValueError(f"Unsupported Eastmoney index symbol: {symbol}")


def normalize_eastmoney_index_kline_row(index_id: str, kline: str) -> dict[str, Any]:
    parts = kline.split(",")
    if len(parts) < 7:
        raise ValueError(f"Eastmoney index kline row has too few fields: {kline}")
    return {
        "index_id": index_id,
        "trade_date": parts[0],
        "open": parse_float(parts[1]),
        "close": parse_float(parts[2]),
        "high": parse_float(parts[3]),
        "low": parse_float(parts[4]),
        "volume": parse_float(parts[5]),
        "amount": parse_float(parts[6]),
        "source": "eastmoney",
    }


def normalize_tencent_index_day_row(
    index_id: str,
    row: list[Any],
    *,
    amount: float | None = None,
    preclose: float | None = None,
) -> dict[str, Any]:
    if len(row) < 6:
        raise ValueError(f"Tencent index day row has too few fields: {row}")
    return {
        "index_id": index_id,
        "trade_date": str(row[0]),
        "open": parse_float(row[1]),
        "close": parse_float(row[2]),
        "high": parse_float(row[3]),
        "low": parse_float(row[4]),
        "volume": parse_float(row[5]),
        "amount": amount,
        "source": "tencent",
        "preclose": preclose,
    }


def _tencent_qt_amount(value: str | None) -> float | None:
    if not value:
        return None
    parts = str(value).split("/")
    if len(parts) >= 3:
        return parse_float(parts[2])
    return None


def _tencent_qt_trade_date(qt: list[Any]) -> str | None:
    if len(qt) <= 30 or not qt[30]:
        return None
    text = str(qt[30])
    if len(text) < 8:
        return None
    return f"{text[:4]}-{text[4:6]}-{text[6:8]}"


def normalize_tencent_index_qt_row(index_id: str, qt: list[Any]) -> dict[str, Any]:
    trade_date = _tencent_qt_trade_date(qt)
    if not trade_date or len(qt) < 36:
        raise ValueError(f"Tencent index qt row has too few fields: {qt}")
    return {
        "index_id": index_id,
        "trade_date": trade_date,
        "open": parse_float(qt[5]),
        "close": parse_float(qt[3]),
        "high": parse_float(qt[33]),
        "low": parse_float(qt[34]),
        "volume": parse_float(qt[36] if len(qt) > 36 else qt[6]),
        "amount": _tencent_qt_amount(str(qt[35])),
        "source": "tencent",
        "preclose": parse_float(qt[4]),
    }


def query_tencent_index_daily_rows(
    *,
    start_date: str,
    end_date: str,
    targets: dict[str, str] | None = None,
    timeout_seconds: int = 10,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    session = requests.Session()
    session.trust_env = False
    try:
        for index_id, symbol in (targets or TENCENT_INDEX_TARGETS).items():
            response = session.get(
                TENCENT_INDEX_KLINE_URL,
                params={
                    "param": f"{symbol},day,{start_date},{end_date},320",
                },
                timeout=timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
            data = ((payload.get("data") or {}).get(symbol) or {})
            qt = ((data.get("qt") or {}).get(symbol) or [])
            qt_row = normalize_tencent_index_qt_row(index_id, qt) if qt else None
            for row in data.get("day") or []:
                trade_date = str(row[0])
                same_day_qt = qt_row if qt_row and qt_row["trade_date"] == trade_date else None
                rows.append(
                    normalize_tencent_index_day_row(
                        index_id,
                        row,
                        amount=same_day_qt["amount"] if same_day_qt else None,
                        preclose=same_day_qt["preclose"] if same_day_qt else None,
                    )
                )
            if not data.get("day") and qt_row and start_date <= qt_row["trade_date"] <= end_date:
                rows.append(qt_row)
    finally:
        session.close()
    return rows


def query_eastmoney_index_daily_rows(
    *,
    start_date: str,
    end_date: str,
    targets: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index_id, symbol in (targets or AKSHARE_INDEX_TARGETS).items():
        payload = curl_eastmoney_json(
            EASTMONEY_INDEX_KLINE_URLS,
            params={
                "secid": eastmoney_index_secid(symbol),
                "fields1": "f1,f2,f3,f4,f5",
                "fields2": "f51,f52,f53,f54,f55,f56,f57,f58",
                "klt": "101",
                "fqt": "0",
                "beg": str(start_date).replace("-", ""),
                "end": str(end_date).replace("-", ""),
            },
            retries=3,
            retry_sleep_seconds=1.0,
            timeout_seconds=10,
        )
        data = payload.get("data") or {}
        klines = data.get("klines") or []
        normalized = [normalize_eastmoney_index_kline_row(index_id, kline) for kline in klines]
        normalized = sorted(normalized, key=lambda row: row["trade_date"])
        previous_close: float | None = None
        for row in normalized:
            row["preclose"] = previous_close
            previous_close = row["close"]
            rows.append(row)
    return rows


def query_akshare_index_daily_rows(
    *,
    start_date: str,
    end_date: str,
    targets: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    expected_count = len(targets or AKSHARE_INDEX_TARGETS)
    try:
        rows = query_eastmoney_index_daily_rows(
            start_date=start_date,
            end_date=end_date,
            targets=targets,
        )
        if len({row["index_id"] for row in rows}) >= expected_count:
            return rows
    except Exception:
        pass

    try:
        rows = query_tencent_index_daily_rows(
            start_date=start_date,
            end_date=end_date,
            targets=targets,
        )
        if len({row["index_id"] for row in rows}) >= expected_count:
            return rows
    except Exception:
        pass

    import akshare as ak

    rows: list[dict[str, Any]] = []
    for index_id, symbol in (targets or AKSHARE_INDEX_TARGETS).items():
        frame = ak.stock_zh_index_daily_em(symbol=symbol)
        rows.extend(
            normalize_akshare_index_daily_rows(
                index_id,
                frame,
                start_date=start_date,
                end_date=end_date,
            )
        )
    return rows


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
        rows.extend(query_akshare_index_daily_rows(start_date=start_date, end_date=end_date))
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
    selected = index_ids if index_ids is not None else list(INDEX_CONSTITUENT_TARGETS)
    rows = []
    for index_id in selected:
        query_fn = INDEX_CONSTITUENT_TARGETS.get(index_id)
        if query_fn is None:
            raise ValueError(f"Unsupported index constituent target: {index_id}")
        attempts = 0
        while True:
            _login_or_raise()
            try:
                rs = query_fn(date=trade_date)
            finally:
                bs.logout()
            if rs.error_code == "0":
                break
            attempts += 1
            if (
                rs.error_code not in INDEX_CONSTITUENT_QUERY_RETRY_ERROR_CODES
                or attempts >= INDEX_CONSTITUENT_QUERY_MAX_ATTEMPTS
            ):
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
