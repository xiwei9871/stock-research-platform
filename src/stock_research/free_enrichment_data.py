from __future__ import annotations

import hashlib
import json
import math
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from stock_research.config import SETTINGS
from stock_research.db import connect, execute_many, fetch_all


SOURCE = "akshare"
DATASETS = ("lhb", "holder", "repurchase", "survey", "forecast", "express", "mainbiz")
_EXCHANGES = {"SH", "SZ", "BJ"}
_BATCH_CONTROLLED_DATASETS = {"holder", "forecast", "express", "mainbiz"}


@dataclass(frozen=True)
class DatasetRunResult:
    dataset: str
    status: str = "success"
    message: str = ""
    fetched_rows: int = 0
    normalized_rows: int = 0
    upserted_rows: int = 0
    empty_results: int = 0
    failed_requests: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset": self.dataset,
            "status": self.status,
            "message": self.message,
            "fetched_rows": self.fetched_rows,
            "normalized_rows": self.normalized_rows,
            "upserted_rows": self.upserted_rows,
            "empty_results": self.empty_results,
            "failed_requests": self.failed_requests,
        }


def normalize_ts_code(value: Any) -> str:
    if value is None:
        return ""

    if isinstance(value, float):
        if math.isnan(value):
            return ""
        if value.is_integer():
            value = int(value)

    try:
        text = str(value).strip().upper()
    except TypeError:
        return ""

    if not text or text in {"<NA>", "NAN", "NONE"}:
        return ""

    asset_match = re.fullmatch(r"CN:(SH|SZ|BJ):(\d{6})", text)
    if asset_match:
        exchange, code = asset_match.groups()
        return f"{code}.{exchange}"

    suffix_match = re.fullmatch(r"(\d{6})\.(SH|SZ|BJ)", text)
    if suffix_match:
        code, exchange = suffix_match.groups()
        return f"{code}.{exchange}"

    prefix_match = re.fullmatch(r"(SH|SZ|BJ)\.?(\d{6})", text)
    if prefix_match:
        exchange, code = prefix_match.groups()
        return f"{code}.{exchange}"

    if not re.fullmatch(r"\d+", text):
        return ""

    code = text.zfill(6)
    if len(code) != 6:
        return ""
    if code.startswith(("60", "68", "90")):
        return f"{code}.SH"
    if code.startswith(("00", "30", "20")):
        return f"{code}.SZ"
    if code.startswith(("43", "83", "87", "92")):
        return f"{code}.BJ"
    return ""


def ts_code_to_asset_id(ts_code: str) -> str:
    code = normalize_ts_code(ts_code)
    if not code or "." not in code:
        return ""
    symbol, exchange = code.split(".", 1)
    if exchange not in _EXCHANGES or not re.fullmatch(r"\d{6}", symbol):
        return ""
    return f"CN:{exchange}:{symbol}"


def _normalize_payload_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _normalize_payload_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize_payload_value(item) for item in value]
    if value is None:
        return None
    if isinstance(value, (pd.Series, pd.Index)):
        return [_normalize_payload_value(item) for item in value.tolist()]

    ndim = getattr(value, "ndim", None)
    if ndim is not None and ndim > 0 and hasattr(value, "tolist"):
        return _normalize_payload_value(value.tolist())

    item = getattr(value, "item", None)
    if callable(item) and not isinstance(value, (str, bytes, bytearray)):
        try:
            scalar = item()
        except (TypeError, ValueError):
            scalar = value
        if scalar is not value:
            return _normalize_payload_value(scalar)

    try:
        missing = pd.isna(value)
    except (TypeError, ValueError):
        missing = False
    if isinstance(missing, bool) and missing:
        return None
    if hasattr(missing, "item"):
        try:
            if bool(missing.item()):
                return None
        except (TypeError, ValueError):
            pass

    return value


def payload_hash(payload: Any) -> str:
    text = json.dumps(_normalize_payload_value(payload), ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _stable_part_text(part: Any) -> str:
    if part is None:
        return ""
    if isinstance(part, float) and math.isnan(part):
        return ""
    text = str(part).strip()
    if text.upper() in {"<NA>", "NAN", "NONE"}:
        return ""
    return text


def build_event_id(prefix: str, parts: list[Any]) -> str:
    normalized = [_stable_part_text(part) for part in parts]
    digest = payload_hash({"prefix": prefix, "parts": normalized})[:24]
    return f"{prefix}:{digest}"


def build_akshare_client() -> Any:
    import akshare as ak

    return ak


def _date_text(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, errors="coerce").dt.strftime("%Y-%m-%d")


def _first_existing(frame: pd.DataFrame, names: list[str]) -> pd.Series:
    for name in names:
        if name in frame.columns:
            return frame[name]
    return pd.Series([None] * len(frame), index=frame.index)


def ts_code_to_akshare_symbol(ts_code: str) -> str:
    normalized = normalize_ts_code(ts_code)
    if not normalized or "." not in normalized:
        return ""
    symbol, exchange = normalized.split(".", 1)
    if exchange not in _EXCHANGES:
        return ""
    return f"{exchange}{symbol}"


def _ts_code_to_plain_symbol(ts_code: str) -> str:
    normalized = normalize_ts_code(ts_code)
    if not normalized or "." not in normalized:
        return ""
    return normalized.split(".", 1)[0]


def _compact_date(value: Any) -> str:
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return ""
    return parsed.strftime("%Y%m%d")


def _compact_previous_date(value: Any) -> str:
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return ""
    return (parsed - pd.Timedelta(days=1)).strftime("%Y%m%d")


def _display_date(value: Any) -> str:
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return ""
    return parsed.strftime("%Y-%m-%d")


def report_quarter_ends_between(start_date: str, end_date: str) -> list[str]:
    start = pd.to_datetime(start_date, errors="raise")
    end = pd.to_datetime(end_date, errors="raise")
    periods: list[str] = []
    for year in range(start.year, end.year + 1):
        for month_day in ("0331", "0630", "0930", "1231"):
            parsed = pd.to_datetime(f"{year}{month_day}", format="%Y%m%d")
            if start <= parsed <= end:
                periods.append(parsed.strftime("%Y%m%d"))
    return periods


def _filter_frame_by_date_range(
    frame: pd.DataFrame,
    *,
    columns: list[str],
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    if frame.empty:
        return frame
    start = pd.to_datetime(start_date, errors="coerce")
    end = pd.to_datetime(end_date, errors="coerce")
    mask = pd.Series([False] * len(frame), index=frame.index)
    found = False
    for column in columns:
        if column not in frame.columns:
            continue
        found = True
        values = pd.to_datetime(frame[column], errors="coerce")
        mask = mask | ((values >= start) & (values <= end))
    if not found:
        return frame.reset_index(drop=True)
    return frame[mask].reset_index(drop=True)


def _limited(items: list[str], limit: int | None) -> list[str]:
    if limit is None:
        return items
    return items[: max(0, int(limit))]


def _iter_batches(items: list[str], batch_size: int | None) -> list[list[str]]:
    if not items:
        return []
    size = max(1, int(batch_size or len(items)))
    return [items[idx : idx + size] for idx in range(0, len(items), size)]


def _sleep_after_batch(batch_index: int, total_batches: int, sleep_seconds: float | None) -> None:
    if batch_index >= total_batches:
        return
    if sleep_seconds is None or sleep_seconds <= 0:
        return
    time.sleep(sleep_seconds)


def _concat_frames(frames: list[pd.DataFrame]) -> pd.DataFrame:
    frames = [frame for frame in frames if frame is not None and not frame.empty]
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def _run_status(*, normalized_rows: int, upserted_rows: int, failed_requests: int) -> str:
    useful_rows = normalized_rows if upserted_rows == 0 else upserted_rows
    if failed_requests and useful_rows:
        return "partial_failed"
    if failed_requests:
        return "failed"
    return "success"


def _normalize_ts_code_list(values: list[Any], *, limit: int | None = None) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        code = normalize_ts_code(value)
        if not code or code in seen:
            continue
        seen.add(code)
        normalized.append(code)
        if limit is not None and len(normalized) >= limit:
            break
    return normalized


def load_free_enrichment_ts_codes(
    *,
    service: str = SETTINGS.research_service,
    limit: int | None = None,
) -> list[str]:
    sql = """
        SELECT ts_code, asset_id, symbol, exchange
        FROM core.asset_master
        WHERE exchange IN ('SH', 'SZ', 'BJ')
          AND is_active IS TRUE
          AND delist_date IS NULL
        ORDER BY exchange, symbol
    """
    params: list[Any] = []
    if limit is not None:
        sql += "\n        LIMIT %s"
        params.append(limit)
    with connect(service) as conn:
        rows = fetch_all(conn, sql, params)

    values: list[Any] = []
    for row in rows:
        ts_code = row.get("ts_code")
        if not ts_code and row.get("asset_id"):
            ts_code = row["asset_id"]
        if not ts_code and row.get("symbol") and row.get("exchange"):
            ts_code = f"{row['symbol']}.{row['exchange']}"
        values.append(ts_code)
    return _normalize_ts_code_list(values, limit=limit)


def _stock_jgdy_detail_params(date: str, page_number: int) -> dict[str, Any]:
    return {
        "sortColumns": "NOTICE_DATE,RECEIVE_START_DATE,SECURITY_CODE,NUMBERNEW",
        "sortTypes": "-1,-1,1,-1",
        "pageSize": "50",
        "pageNumber": str(page_number),
        "reportName": "RPT_ORG_SURVEY",
        "columns": "SECUCODE,SECURITY_CODE,SECURITY_NAME_ABBR,NOTICE_DATE,RECEIVE_START_DATE,"
        "RECEIVE_OBJECT,RECEIVE_PLACE,RECEIVE_WAY_EXPLAIN,INVESTIGATORS,RECEPTIONIST,ORG_TYPE",
        "quoteColumns": "f2~01~SECURITY_CODE~CLOSE_PRICE,f3~01~SECURITY_CODE~CHANGE_RATE",
        "quoteType": "0",
        "source": "WEB",
        "client": "WEB",
        "filter": f"""(IS_SOURCE="1")(RECEIVE_START_DATE>'{"-".join([date[:4], date[4:6], date[6:]])}')""",
    }


def _request_json_with_retries(
    *,
    url: str,
    params: dict[str, Any],
    request_get: Any,
    max_retries: int,
    retry_sleep_seconds: float,
) -> dict[str, Any]:
    attempts = max(1, int(max_retries))
    last_exc: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            response = request_get(url, params=params, timeout=30)
            raise_for_status = getattr(response, "raise_for_status", None)
            if callable(raise_for_status):
                raise_for_status()
            return response.json()
        except Exception as exc:
            last_exc = exc
            if attempt >= attempts:
                break
            page = params.get("pageNumber", "")
            print(
                "free_enrichment_request_retry|"
                f"dataset=survey|page={page}|attempt={attempt + 1}/{attempts}|error={exc}"
            )
            if retry_sleep_seconds > 0:
                time.sleep(retry_sleep_seconds)
    if last_exc is None:
        raise RuntimeError("request failed without exception")
    raise last_exc


def _fetch_stock_jgdy_detail_em_robust(
    *,
    date: str,
    request_get: Any = None,
    max_retries: int = 5,
    retry_sleep_seconds: float = 2.0,
) -> pd.DataFrame:
    if request_get is None:
        import requests

        request_get = requests.get

    url = "https://datacenter-web.eastmoney.com/api/data/v1/get"
    first_json = _request_json_with_retries(
        url=url,
        params=_stock_jgdy_detail_params(date, 1),
        request_get=request_get,
        max_retries=max_retries,
        retry_sleep_seconds=retry_sleep_seconds,
    )
    total_page = int((first_json.get("result") or {}).get("pages") or 0)
    frames: list[pd.DataFrame] = []
    for page in range(1, total_page + 1):
        data_json = _request_json_with_retries(
            url=url,
            params=_stock_jgdy_detail_params(date, page),
            request_get=request_get,
            max_retries=max_retries,
            retry_sleep_seconds=retry_sleep_seconds,
        )
        data = (data_json.get("result") or {}).get("data") or []
        frames.append(pd.DataFrame(data))
        if page == 1 or page == total_page or page % 100 == 0:
            print(f"free_enrichment_request_page|dataset=survey|page={page}/{total_page}")

    big_df = _concat_frames(frames)
    if big_df.empty:
        return pd.DataFrame()
    big_df.reset_index(inplace=True)
    big_df["index"] = list(range(1, len(big_df) + 1))
    big_df.columns = [
        "序号",
        "_",
        "代码",
        "名称",
        "公告日期",
        "调研日期",
        "调研机构",
        "接待地点",
        "接待方式",
        "调研人员",
        "接待人员",
        "机构类型",
        "最新价",
        "涨跌幅",
    ]
    big_df = big_df[
        [
            "序号",
            "代码",
            "名称",
            "最新价",
            "涨跌幅",
            "调研机构",
            "机构类型",
            "调研人员",
            "接待方式",
            "接待人员",
            "接待地点",
            "调研日期",
            "公告日期",
        ]
    ]
    big_df["最新价"] = pd.to_numeric(big_df["最新价"], errors="coerce")
    big_df["涨跌幅"] = pd.to_numeric(big_df["涨跌幅"], errors="coerce")
    big_df["调研日期"] = pd.to_datetime(big_df["调研日期"], errors="coerce").dt.date
    big_df["公告日期"] = pd.to_datetime(big_df["公告日期"], errors="coerce").dt.date
    return big_df


def normalize_shareholder_count_rows(frame: pd.DataFrame, *, endpoint: str) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame()

    data = pd.DataFrame(index=frame.index)
    data["ts_code"] = _first_existing(frame, ["代码", "股票代码", "SECURITY_CODE"]).map(normalize_ts_code)
    data["asset_id"] = data["ts_code"].map(ts_code_to_asset_id)
    data["report_date"] = _date_text(_first_existing(frame, ["股东户数统计截止日", "截止日期", "报告期", "END_DATE"]))
    data["announcement_date"] = _date_text(
        _first_existing(frame, ["股东户数公告日期", "公告日期", "DECLAREDATE", "公告日"])
    )
    data["shareholder_count"] = pd.to_numeric(
        _first_existing(frame, ["股东户数-本次", "股东户数", "HOLDER_NUM"]),
        errors="coerce",
    )
    data["shareholder_count_change"] = pd.to_numeric(
        _first_existing(frame, ["股东户数-增减", "股东户数增减", "较上期变化", "HOLDER_NUM_CHANGE"]),
        errors="coerce",
    )
    data["shareholder_count_change_pct"] = pd.to_numeric(
        _first_existing(frame, ["股东户数-增减比例", "股东户数较上期变化百分比", "较上期变化百分比"]),
        errors="coerce",
    )
    data["source"] = SOURCE
    data["source_endpoint"] = endpoint
    data["payload_hash"] = frame.apply(lambda row: payload_hash(row.to_dict()), axis=1)
    return data[data["asset_id"].ne("") & data["report_date"].notna()].reset_index(drop=True)


def normalize_top_holder_rows(frame: pd.DataFrame, *, endpoint: str) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame()

    data = pd.DataFrame(index=frame.index)
    data["ts_code"] = _first_existing(frame, ["代码", "股票代码", "SECURITY_CODE"]).map(normalize_ts_code)
    data["asset_id"] = data["ts_code"].map(ts_code_to_asset_id)
    data["report_period"] = _date_text(_first_existing(frame, ["报告期", "截止日期", "END_DATE"]))
    data["holder_name"] = _first_existing(frame, ["股东名称", "HOLDER_NAME"]).fillna("").astype(str)
    data["holder_type"] = _first_existing(frame, ["股东类型", "股东性质", "股份类型", "HOLDER_TYPE"])
    data["hold_amount"] = pd.to_numeric(_first_existing(frame, ["持股数", "持股数量", "HOLD_NUM"]), errors="coerce")
    data["hold_ratio"] = pd.to_numeric(
        _first_existing(frame, ["占总股本持股比例", "占总流通股本持股比例", "持股比例", "HOLD_RATIO"]),
        errors="coerce",
    )
    data["hold_change"] = pd.to_numeric(_first_existing(frame, ["增减", "持股变动", "HOLD_CHANGE"]), errors="coerce")
    data["rank"] = pd.to_numeric(_first_existing(frame, ["名次", "排名", "RANK"]), errors="coerce")
    data["source"] = SOURCE
    data["source_endpoint"] = endpoint
    data["payload_hash"] = frame.apply(lambda row: payload_hash(row.to_dict()), axis=1)
    return data[
        data["asset_id"].ne("") & data["report_period"].notna() & data["holder_name"].ne("")
    ].reset_index(drop=True)


def _base_event_frame(frame: pd.DataFrame, *, endpoint: str) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame()

    data = pd.DataFrame(index=frame.index)
    data["ts_code"] = _first_existing(frame, ["代码", "股票代码", "SECURITY_CODE"]).map(normalize_ts_code)
    data["asset_id"] = data["ts_code"].map(ts_code_to_asset_id)
    data["source"] = SOURCE
    data["source_endpoint"] = endpoint
    data["payload_hash"] = frame.apply(lambda row: payload_hash(row.to_dict()), axis=1)
    return data


def normalize_repurchase_rows(frame: pd.DataFrame, *, endpoint: str) -> pd.DataFrame:
    data = _base_event_frame(frame, endpoint=endpoint)
    if data.empty:
        return data

    data["announcement_date"] = _date_text(_first_existing(frame, ["最新公告日期", "公告日期", "ANN_DATE"]))
    data["progress_date"] = _date_text(_first_existing(frame, ["回购起始时间", "进度日期", "更新日期", "UPDATE_DATE"]))
    data["progress"] = _first_existing(frame, ["实施进度", "进度", "回购进度", "PROGRESS"])
    data["repurchase_amount"] = pd.to_numeric(
        _first_existing(frame, ["已回购金额", "回购金额", "REPURCHASE_AMOUNT"]),
        errors="coerce",
    )
    data["repurchase_amount_min"] = pd.to_numeric(
        _first_existing(frame, ["计划回购金额区间-下限", "拟回购金额下限", "金额下限"]),
        errors="coerce",
    )
    data["repurchase_amount_max"] = pd.to_numeric(
        _first_existing(frame, ["计划回购金额区间-上限", "拟回购金额上限", "金额上限"]),
        errors="coerce",
    )
    data["repurchase_price_min"] = pd.to_numeric(
        _first_existing(frame, ["已回购股份价格区间-下限", "回购价格下限", "价格下限"]),
        errors="coerce",
    )
    data["repurchase_price_max"] = pd.to_numeric(
        _first_existing(frame, ["已回购股份价格区间-上限", "回购价格上限", "价格上限"]),
        errors="coerce",
    )
    data["event_id"] = data.apply(
        lambda row: build_event_id(
            "repurchase",
            [row["ts_code"], row["announcement_date"], row["progress"], row["payload_hash"]],
        ),
        axis=1,
    )
    return data[data["asset_id"].ne("")].reset_index(drop=True)


def normalize_institution_survey_rows(frame: pd.DataFrame, *, endpoint: str) -> pd.DataFrame:
    data = _base_event_frame(frame, endpoint=endpoint)
    if data.empty:
        return data

    data["survey_date"] = _date_text(_first_existing(frame, ["调研日期", "接待日期", "SURVEY_DATE"]))
    data["announcement_date"] = _date_text(_first_existing(frame, ["公告日期", "ANN_DATE"]))
    data["institution_count"] = pd.to_numeric(
        _first_existing(frame, ["机构数量", "调研机构数量"]),
        errors="coerce",
    )
    data["institution_names"] = _first_existing(frame, ["调研机构", "机构名称", "ORG_NAMES"])
    data["survey_type"] = _first_existing(frame, ["调研类型", "接待方式", "SURVEY_TYPE"])
    data["summary"] = _first_existing(frame, ["调研内容", "主要内容", "SUMMARY"])
    data["event_id"] = data.apply(
        lambda row: build_event_id("survey", [row["ts_code"], row["survey_date"], row["summary"], row["payload_hash"]]),
        axis=1,
    )
    return data[data["asset_id"].ne("")].reset_index(drop=True)


def normalize_shareholder_trade_rows(frame: pd.DataFrame, *, endpoint: str) -> pd.DataFrame:
    data = _base_event_frame(frame, endpoint=endpoint)
    if data.empty:
        return data

    data["trade_date"] = _date_text(_first_existing(frame, ["变动截止日", "变动日期", "交易日期", "TRADE_DATE"]))
    data["announcement_date"] = _date_text(_first_existing(frame, ["公告日", "公告日期", "ANN_DATE"]))
    data["holder_name"] = _first_existing(frame, ["股东名称", "变动人", "HOLDER_NAME"])
    data["trade_type"] = _first_existing(frame, ["持股变动信息-增减", "变动方向", "变动类型", "TRADE_TYPE"])
    data["trade_amount"] = pd.to_numeric(
        _first_existing(frame, ["持股变动信息-变动数量", "变动数量", "成交股数", "TRADE_AMOUNT"]),
        errors="coerce",
    )
    data["trade_ratio"] = pd.to_numeric(
        _first_existing(frame, ["持股变动信息-占总股本比例", "变动比例", "TRADE_RATIO"]),
        errors="coerce",
    )
    data["trade_price"] = pd.to_numeric(_first_existing(frame, ["成交均价", "TRADE_PRICE"]), errors="coerce")
    data["event_id"] = data.apply(
        lambda row: build_event_id(
            "shareholder_trade",
            [row["ts_code"], row["trade_date"], row["holder_name"], row["trade_type"], row["payload_hash"]],
        ),
        axis=1,
    )
    return data[data["asset_id"].ne("")].reset_index(drop=True)


def normalize_earnings_forecast_rows(frame: pd.DataFrame, *, endpoint: str) -> pd.DataFrame:
    data = _base_event_frame(frame, endpoint=endpoint)
    if data.empty:
        return data

    data["announcement_date"] = _date_text(_first_existing(frame, ["公告日期", "ANN_DATE"]))
    data["report_period"] = _date_text(_first_existing(frame, ["报告期", "预测报告期", "REPORT_PERIOD"]))
    data["forecast_type"] = _first_existing(frame, ["预告类型", "业绩变动类型", "FORECAST_TYPE"])
    data["forecast_np_min"] = pd.to_numeric(
        _first_existing(frame, ["预测数值", "净利润下限", "FORECAST_NP_MIN"]),
        errors="coerce",
    )
    data["forecast_np_max"] = pd.to_numeric(
        _first_existing(frame, ["净利润上限", "FORECAST_NP_MAX"]),
        errors="coerce",
    )
    data["forecast_np_change_min"] = pd.to_numeric(
        _first_existing(frame, ["业绩变动幅度", "净利润变动幅度下限", "预增幅下限"]),
        errors="coerce",
    )
    data["forecast_np_change_max"] = pd.to_numeric(
        _first_existing(frame, ["净利润变动幅度上限", "预增幅上限"]),
        errors="coerce",
    )
    data["summary"] = _first_existing(frame, ["业绩变动原因", "业绩预告摘要", "变动原因", "SUMMARY"])
    data["event_id"] = data.apply(
        lambda row: build_event_id(
            "earnings_forecast",
            [
                row["ts_code"],
                row["announcement_date"],
                row["report_period"],
                row["forecast_type"],
                row["payload_hash"],
            ],
        ),
        axis=1,
    )
    return data[data["asset_id"].ne("") & data["announcement_date"].notna()].reset_index(drop=True)


def normalize_earnings_express_rows(frame: pd.DataFrame, *, endpoint: str) -> pd.DataFrame:
    data = _base_event_frame(frame, endpoint=endpoint)
    if data.empty:
        return data

    data["announcement_date"] = _date_text(_first_existing(frame, ["公告日期", "ANN_DATE"]))
    data["report_period"] = _date_text(_first_existing(frame, ["报告期", "REPORT_PERIOD"]))
    data["revenue"] = pd.to_numeric(_first_existing(frame, ["营业收入-营业收入", "营业收入", "REVENUE"]), errors="coerce")
    data["revenue_yoy"] = pd.to_numeric(
        _first_existing(frame, ["营业收入-同比增长", "营业收入同比", "REVENUE_YOY"]),
        errors="coerce",
    )
    data["np_parent"] = pd.to_numeric(
        _first_existing(frame, ["净利润-净利润", "归母净利润", "净利润", "NP_PARENT"]),
        errors="coerce",
    )
    data["np_parent_yoy"] = pd.to_numeric(
        _first_existing(frame, ["净利润-同比增长", "归母净利润同比", "净利润同比", "NP_PARENT_YOY"]),
        errors="coerce",
    )
    data["eps_basic"] = pd.to_numeric(_first_existing(frame, ["每股收益", "基本每股收益", "EPS_BASIC"]), errors="coerce")
    data["roe_weighted"] = pd.to_numeric(
        _first_existing(frame, ["净资产收益率", "加权净资产收益率", "ROE_WEIGHTED"]),
        errors="coerce",
    )
    data["event_id"] = data.apply(
        lambda row: build_event_id(
            "earnings_express",
            [row["ts_code"], row["announcement_date"], row["report_period"], row["payload_hash"]],
        ),
        axis=1,
    )
    return data[data["asset_id"].ne("") & data["announcement_date"].notna()].reset_index(drop=True)


def normalize_main_business_rows(frame: pd.DataFrame, *, endpoint: str) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame()

    data = pd.DataFrame(index=frame.index)
    data["ts_code"] = _first_existing(frame, ["代码", "股票代码", "SECURITY_CODE"]).map(normalize_ts_code)
    data["asset_id"] = data["ts_code"].map(ts_code_to_asset_id)
    data["report_period"] = _date_text(_first_existing(frame, ["报告日期", "报告期", "截止日期", "REPORT_PERIOD"]))
    data["classify_type"] = (
        _first_existing(frame, ["分类方向", "分类类型", "CLASSIFY_TYPE"]).fillna("").astype(str).str.strip()
    )
    data["item_name"] = _first_existing(frame, ["主营构成", "项目名称", "ITEM_NAME"]).fillna("").astype(str).str.strip()
    data["revenue"] = pd.to_numeric(_first_existing(frame, ["主营收入", "营业收入", "REVENUE"]), errors="coerce")
    data["revenue_ratio"] = pd.to_numeric(
        _first_existing(frame, ["收入比例", "主营收入占比", "REVENUE_RATIO"]),
        errors="coerce",
    )
    data["cost"] = pd.to_numeric(_first_existing(frame, ["主营成本", "营业成本", "COST"]), errors="coerce")
    data["gross_profit"] = pd.to_numeric(_first_existing(frame, ["主营利润", "毛利", "GROSS_PROFIT"]), errors="coerce")
    data["gross_margin"] = pd.to_numeric(_first_existing(frame, ["毛利率", "GROSS_MARGIN"]), errors="coerce")
    data["source"] = SOURCE
    data["source_endpoint"] = endpoint
    data["payload_hash"] = frame.apply(lambda row: payload_hash(row.to_dict()), axis=1)
    columns = [
        "asset_id",
        "ts_code",
        "report_period",
        "classify_type",
        "item_name",
        "revenue",
        "revenue_ratio",
        "cost",
        "gross_profit",
        "gross_margin",
        "source",
        "source_endpoint",
        "payload_hash",
    ]
    return data[
        data["asset_id"].ne("")
        & data["report_period"].notna()
        & data["classify_type"].ne("")
        & data["item_name"].ne("")
    ][columns].reset_index(drop=True)


def _value_or_none(value: Any) -> Any:
    return _normalize_payload_value(value)


def _frame_rows(frame: pd.DataFrame, columns: list[str]) -> list[tuple[Any, ...]]:
    return [tuple(_value_or_none(row[column]) for column in columns) for row in frame.to_dict("records")]


def upsert_shareholder_count_rows(
    frame: pd.DataFrame,
    service: str = SETTINGS.research_service,
) -> int:
    if frame.empty:
        return 0

    columns = [
        "asset_id",
        "ts_code",
        "report_date",
        "announcement_date",
        "shareholder_count",
        "shareholder_count_change",
        "shareholder_count_change_pct",
        "source",
        "source_endpoint",
        "payload_hash",
    ]
    sql = """
        INSERT INTO fundamental.shareholder_count (
            asset_id,
            ts_code,
            report_date,
            announcement_date,
            shareholder_count,
            shareholder_count_change,
            shareholder_count_change_pct,
            source,
            source_endpoint,
            payload_hash
        ) VALUES (
            %s, %s, %s::date, %s::date, %s, %s, %s, %s, %s, %s
        )
        ON CONFLICT (asset_id, report_date, source) DO UPDATE SET
            ts_code = EXCLUDED.ts_code,
            announcement_date = EXCLUDED.announcement_date,
            shareholder_count = EXCLUDED.shareholder_count,
            shareholder_count_change = EXCLUDED.shareholder_count_change,
            shareholder_count_change_pct = EXCLUDED.shareholder_count_change_pct,
            source_endpoint = EXCLUDED.source_endpoint,
            payload_hash = EXCLUDED.payload_hash,
            updated_at = now()
    """
    rows = _frame_rows(frame, columns)
    with connect(service) as conn:
        execute_many(conn, sql, rows)
    return len(rows)


def upsert_top_holder_rows(
    frame: pd.DataFrame,
    *,
    table: str,
    service: str = SETTINGS.research_service,
) -> int:
    allowed_tables = {"fundamental.top10_holder", "fundamental.top10_float_holder"}
    if table not in allowed_tables:
        raise ValueError(f"Unsupported holder table: {table}")
    if frame.empty:
        return 0

    columns = [
        "asset_id",
        "ts_code",
        "report_period",
        "holder_name",
        "holder_type",
        "hold_amount",
        "hold_ratio",
        "hold_change",
        "rank",
        "source",
        "source_endpoint",
        "payload_hash",
    ]
    sql = f"""
        INSERT INTO {table} (
            asset_id,
            ts_code,
            report_period,
            holder_name,
            holder_type,
            hold_amount,
            hold_ratio,
            hold_change,
            rank,
            source,
            source_endpoint,
            payload_hash
        ) VALUES (
            %s, %s, %s::date, %s, %s, %s, %s, %s, %s, %s, %s, %s
        )
        ON CONFLICT (asset_id, report_period, holder_name, source) DO UPDATE SET
            ts_code = EXCLUDED.ts_code,
            holder_type = EXCLUDED.holder_type,
            hold_amount = EXCLUDED.hold_amount,
            hold_ratio = EXCLUDED.hold_ratio,
            hold_change = EXCLUDED.hold_change,
            rank = EXCLUDED.rank,
            source_endpoint = EXCLUDED.source_endpoint,
            payload_hash = EXCLUDED.payload_hash,
            updated_at = now()
    """
    rows = _frame_rows(frame, columns)
    with connect(service) as conn:
        execute_many(conn, sql, rows)
    return len(rows)


def upsert_main_business_rows(
    frame: pd.DataFrame,
    service: str = SETTINGS.research_service,
) -> int:
    if frame.empty:
        return 0

    columns = [
        "asset_id",
        "ts_code",
        "report_period",
        "classify_type",
        "item_name",
        "revenue",
        "revenue_ratio",
        "cost",
        "gross_profit",
        "gross_margin",
        "source",
        "source_endpoint",
        "payload_hash",
    ]
    sql = """
        INSERT INTO finance.main_business_composition (
            asset_id,
            ts_code,
            report_period,
            classify_type,
            item_name,
            revenue,
            revenue_ratio,
            cost,
            gross_profit,
            gross_margin,
            source,
            source_endpoint,
            payload_hash
        ) VALUES (
            %s, %s, %s::date, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
        )
        ON CONFLICT (asset_id, report_period, classify_type, item_name, source) DO UPDATE SET
            revenue = EXCLUDED.revenue,
            revenue_ratio = EXCLUDED.revenue_ratio,
            cost = EXCLUDED.cost,
            gross_profit = EXCLUDED.gross_profit,
            gross_margin = EXCLUDED.gross_margin,
            source_endpoint = EXCLUDED.source_endpoint,
            payload_hash = EXCLUDED.payload_hash,
            updated_at = now()
    """
    rows = _frame_rows(frame, columns)
    with connect(service) as conn:
        execute_many(conn, sql, rows)
    return len(rows)


_EVENT_TABLE_COLUMNS = {
    "event.stock_repurchase": [
        "event_id",
        "asset_id",
        "ts_code",
        "announcement_date",
        "progress_date",
        "progress",
        "repurchase_amount",
        "repurchase_amount_min",
        "repurchase_amount_max",
        "repurchase_price_min",
        "repurchase_price_max",
        "source",
        "source_endpoint",
        "payload_hash",
    ],
    "event.institution_survey": [
        "event_id",
        "asset_id",
        "ts_code",
        "survey_date",
        "announcement_date",
        "institution_count",
        "institution_names",
        "survey_type",
        "summary",
        "source",
        "source_endpoint",
        "payload_hash",
    ],
    "event.shareholder_trade": [
        "event_id",
        "asset_id",
        "ts_code",
        "trade_date",
        "announcement_date",
        "holder_name",
        "trade_type",
        "trade_amount",
        "trade_ratio",
        "trade_price",
        "source",
        "source_endpoint",
        "payload_hash",
    ],
    "event.earnings_forecast": [
        "event_id",
        "asset_id",
        "ts_code",
        "announcement_date",
        "report_period",
        "forecast_type",
        "forecast_np_min",
        "forecast_np_max",
        "forecast_np_change_min",
        "forecast_np_change_max",
        "summary",
        "source",
        "source_endpoint",
        "payload_hash",
    ],
    "event.earnings_express": [
        "event_id",
        "asset_id",
        "ts_code",
        "announcement_date",
        "report_period",
        "revenue",
        "revenue_yoy",
        "np_parent",
        "np_parent_yoy",
        "eps_basic",
        "roe_weighted",
        "source",
        "source_endpoint",
        "payload_hash",
    ],
}

_EVENT_DATE_COLUMNS = {
    "announcement_date",
    "progress_date",
    "report_period",
    "survey_date",
    "trade_date",
}


def upsert_event_rows(
    frame: pd.DataFrame,
    *,
    table: str,
    service: str = SETTINGS.research_service,
) -> int:
    if table not in _EVENT_TABLE_COLUMNS:
        raise ValueError(f"Unsupported event table: {table}")
    if frame.empty:
        return 0

    columns = _EVENT_TABLE_COLUMNS[table]
    insert_columns = ",\n            ".join(columns)
    placeholders = ", ".join("%s::date" if column in _EVENT_DATE_COLUMNS else "%s" for column in columns)
    updates = ",\n            ".join(
        f"{column} = EXCLUDED.{column}" for column in columns if column not in {"event_id", "source"}
    )
    sql = f"""
        INSERT INTO {table} (
            {insert_columns}
        ) VALUES (
            {placeholders}
        )
        ON CONFLICT (event_id) DO UPDATE SET
            {updates},
            updated_at = now()
    """
    rows = _frame_rows(frame.reindex(columns=columns), columns)
    with connect(service) as conn:
        execute_many(conn, sql, rows)
    return len(rows)


def _safe_len(value: Any) -> int:
    if value is None:
        return 0
    try:
        return len(value)
    except TypeError:
        return 0


def run_lhb_backfill(
    *,
    start_date: str,
    end_date: str,
    output_dir: str | Path,
    dry_run: bool = False,
    service: str = SETTINGS.research_service,
    runner: Any = None,
) -> DatasetRunResult:
    if dry_run:
        return DatasetRunResult(dataset="lhb")

    if runner is None:
        from stock_research.lhb_data import run_lhb_sample_import as actual_runner
    else:
        actual_runner = runner

    result = actual_runner(
        start_date=start_date,
        end_date=end_date,
        ts_codes=None,
        provider="akshare",
        output_dir=output_dir,
        service=service,
    )
    normalized_rows = _safe_len(result.get("top_list")) + _safe_len(result.get("top_inst"))
    return DatasetRunResult(
        dataset="lhb",
        fetched_rows=normalized_rows,
        normalized_rows=normalized_rows,
        upserted_rows=normalized_rows,
        empty_results=1 if normalized_rows == 0 else 0,
    )


def run_shareholder_trade_backfill(
    *,
    start_date: str,
    end_date: str,
    dry_run: bool = False,
    service: str = SETTINGS.research_service,
    client: Any = None,
) -> DatasetRunResult:
    client = client or build_akshare_client()
    try:
        raw = client.stock_ggcg_em(symbol="全部")
    except Exception as exc:
        return DatasetRunResult(dataset="shareholder_trade", status="failed", failed_requests=1, message=str(exc))

    fetched_rows = _safe_len(raw)
    normalized = normalize_shareholder_trade_rows(pd.DataFrame(raw), endpoint="stock_ggcg_em")
    normalized = _filter_frame_by_date_range(
        normalized,
        columns=["trade_date", "announcement_date"],
        start_date=start_date,
        end_date=end_date,
    )
    upserted = 0 if dry_run else upsert_event_rows(normalized, table="event.shareholder_trade", service=service)
    return DatasetRunResult(
        dataset="shareholder_trade",
        status=_run_status(normalized_rows=len(normalized), upserted_rows=upserted, failed_requests=0),
        fetched_rows=fetched_rows,
        normalized_rows=len(normalized),
        upserted_rows=upserted,
        empty_results=1 if fetched_rows == 0 or normalized.empty else 0,
    )


def run_holder_backfill(
    *,
    start_date: str,
    end_date: str,
    batch_size: int = 100,
    sleep_seconds: float = 1.0,
    limit: int | None = None,
    dry_run: bool = False,
    service: str = SETTINGS.research_service,
    client: Any = None,
    ts_codes: list[str] | None = None,
) -> DatasetRunResult:
    client = client or build_akshare_client()
    if ts_codes is None:
        try:
            universe_values = load_free_enrichment_ts_codes(service=service, limit=limit)
        except Exception as exc:
            return DatasetRunResult(
                dataset="holder",
                status="failed",
                failed_requests=1,
                message=f"universe loader failed: {exc}",
            )
    else:
        universe_values = ts_codes
    universe = _normalize_ts_code_list(universe_values, limit=limit)
    periods = report_quarter_ends_between(start_date, end_date)

    fetched_rows = 0
    empty_results = 0
    failed_requests = 0
    errors: list[str] = []
    shareholder_frames: list[pd.DataFrame] = []
    top_frames: list[pd.DataFrame] = []
    float_frames: list[pd.DataFrame] = []
    batches = _iter_batches(universe, batch_size)

    for batch_index, batch in enumerate(batches, start=1):
        print(
            "free_enrichment_request_batch|"
            f"dataset=holder|batch={batch_index}/{len(batches)}|requests={len(batch)}"
        )
        for ts_code in batch:
            plain_symbol = _ts_code_to_plain_symbol(ts_code)
            ak_symbol = ts_code_to_akshare_symbol(ts_code)
            if plain_symbol:
                try:
                    raw = pd.DataFrame(client.stock_zh_a_gdhs_detail_em(symbol=plain_symbol))
                    fetched_rows += len(raw)
                    if raw.empty:
                        empty_results += 1
                    normalized = normalize_shareholder_count_rows(raw, endpoint="stock_zh_a_gdhs_detail_em")
                    normalized = _filter_frame_by_date_range(
                        normalized,
                        columns=["report_date"],
                        start_date=start_date,
                        end_date=end_date,
                    )
                    shareholder_frames.append(normalized)
                except Exception as exc:
                    failed_requests += 1
                    errors.append(f"stock_zh_a_gdhs_detail_em:{ts_code}:{exc}")

            if not ak_symbol:
                continue
            for period in periods:
                for endpoint, target in (
                    ("stock_gdfx_top_10_em", top_frames),
                    ("stock_gdfx_free_top_10_em", float_frames),
                ):
                    try:
                        func = getattr(client, endpoint)
                        raw = pd.DataFrame(func(symbol=ak_symbol, date=period))
                        fetched_rows += len(raw)
                        if raw.empty:
                            empty_results += 1
                            continue
                        raw = raw.copy()
                        raw["股票代码"] = ts_code
                        raw["报告期"] = _display_date(period)
                        target.append(normalize_top_holder_rows(raw, endpoint=endpoint))
                    except Exception as exc:
                        failed_requests += 1
                        errors.append(f"{endpoint}:{ts_code}:{period}:{exc}")
        _sleep_after_batch(batch_index, len(batches), sleep_seconds)

    try:
        trade_raw = pd.DataFrame(client.stock_ggcg_em(symbol="全部"))
        fetched_rows += len(trade_raw)
        if trade_raw.empty:
            empty_results += 1
        trade_frame = normalize_shareholder_trade_rows(trade_raw, endpoint="stock_ggcg_em")
        trade_frame = _filter_frame_by_date_range(
            trade_frame,
            columns=["trade_date", "announcement_date"],
            start_date=start_date,
            end_date=end_date,
        )
    except Exception as exc:
        trade_frame = pd.DataFrame()
        failed_requests += 1
        errors.append(f"stock_ggcg_em:全部:{exc}")

    shareholder_frame = _concat_frames(shareholder_frames)
    top_frame = _concat_frames(top_frames)
    float_frame = _concat_frames(float_frames)
    normalized_rows = len(shareholder_frame) + len(top_frame) + len(float_frame) + len(trade_frame)
    if dry_run:
        upserted_rows = 0
    else:
        upserted_rows = (
            upsert_shareholder_count_rows(shareholder_frame, service=service)
            + upsert_top_holder_rows(top_frame, table="fundamental.top10_holder", service=service)
            + upsert_top_holder_rows(float_frame, table="fundamental.top10_float_holder", service=service)
            + upsert_event_rows(trade_frame, table="event.shareholder_trade", service=service)
        )

    return DatasetRunResult(
        dataset="holder",
        status=_run_status(
            normalized_rows=normalized_rows,
            upserted_rows=upserted_rows,
            failed_requests=failed_requests,
        ),
        message="; ".join(errors[:3]),
        fetched_rows=fetched_rows,
        normalized_rows=normalized_rows,
        upserted_rows=upserted_rows,
        empty_results=empty_results,
        failed_requests=failed_requests,
    )


def run_repurchase_backfill(
    *,
    start_date: str,
    end_date: str,
    batch_size: int = 100,
    sleep_seconds: float = 1.0,
    limit: int | None = None,
    dry_run: bool = False,
    service: str = SETTINGS.research_service,
    client: Any = None,
) -> DatasetRunResult:
    del batch_size, sleep_seconds, limit
    client = client or build_akshare_client()
    try:
        raw = pd.DataFrame(client.stock_repurchase_em())
    except Exception as exc:
        return DatasetRunResult(dataset="repurchase", status="failed", failed_requests=1, message=str(exc))

    normalized = normalize_repurchase_rows(raw, endpoint="stock_repurchase_em")
    normalized = _filter_frame_by_date_range(
        normalized,
        columns=["announcement_date", "progress_date"],
        start_date=start_date,
        end_date=end_date,
    )
    upserted = 0 if dry_run else upsert_event_rows(normalized, table="event.stock_repurchase", service=service)
    return DatasetRunResult(
        dataset="repurchase",
        status=_run_status(normalized_rows=len(normalized), upserted_rows=upserted, failed_requests=0),
        fetched_rows=len(raw),
        normalized_rows=len(normalized),
        upserted_rows=upserted,
        empty_results=1 if raw.empty or normalized.empty else 0,
    )


def run_survey_backfill(
    *,
    start_date: str,
    end_date: str,
    batch_size: int = 100,
    sleep_seconds: float = 1.0,
    limit: int | None = None,
    dry_run: bool = False,
    service: str = SETTINGS.research_service,
    client: Any = None,
) -> DatasetRunResult:
    del batch_size, sleep_seconds, limit
    query_date = _compact_previous_date(start_date)
    try:
        if client is None:
            raw = _fetch_stock_jgdy_detail_em_robust(date=query_date)
        else:
            raw = pd.DataFrame(client.stock_jgdy_detail_em(date=query_date))
    except Exception as exc:
        return DatasetRunResult(dataset="survey", status="failed", failed_requests=1, message=str(exc))

    normalized = normalize_institution_survey_rows(raw, endpoint="stock_jgdy_detail_em")
    normalized = _filter_frame_by_date_range(
        normalized,
        columns=["survey_date", "announcement_date"],
        start_date=start_date,
        end_date=end_date,
    )
    upserted = 0 if dry_run else upsert_event_rows(normalized, table="event.institution_survey", service=service)
    return DatasetRunResult(
        dataset="survey",
        status=_run_status(normalized_rows=len(normalized), upserted_rows=upserted, failed_requests=0),
        fetched_rows=len(raw),
        normalized_rows=len(normalized),
        upserted_rows=upserted,
        empty_results=1 if raw.empty or normalized.empty else 0,
    )


def _run_period_event_backfill(
    *,
    dataset: str,
    endpoint: str,
    table: str,
    start_date: str,
    end_date: str,
    batch_size: int,
    sleep_seconds: float,
    limit: int | None,
    dry_run: bool,
    service: str,
    client: Any,
) -> DatasetRunResult:
    periods = _limited(report_quarter_ends_between(start_date, end_date), limit)
    frames: list[pd.DataFrame] = []
    fetched_rows = 0
    empty_results = 0
    failed_requests = 0
    errors: list[str] = []
    batches = _iter_batches(periods, batch_size)
    for batch_index, batch in enumerate(batches, start=1):
        print(
            "free_enrichment_request_batch|"
            f"dataset={dataset}|batch={batch_index}/{len(batches)}|requests={len(batch)}"
        )
        for period in batch:
            try:
                raw = pd.DataFrame(getattr(client, endpoint)(date=period))
                fetched_rows += len(raw)
                if raw.empty:
                    empty_results += 1
                    continue
                raw = raw.copy()
                raw["报告期"] = _display_date(period)
                if dataset == "forecast":
                    frames.append(normalize_earnings_forecast_rows(raw, endpoint=endpoint))
                else:
                    frames.append(normalize_earnings_express_rows(raw, endpoint=endpoint))
            except Exception as exc:
                failed_requests += 1
                errors.append(f"{endpoint}:{period}:{exc}")
        _sleep_after_batch(batch_index, len(batches), sleep_seconds)

    normalized = _concat_frames(frames)
    upserted = 0 if dry_run else upsert_event_rows(normalized, table=table, service=service)
    return DatasetRunResult(
        dataset=dataset,
        status=_run_status(normalized_rows=len(normalized), upserted_rows=upserted, failed_requests=failed_requests),
        message="; ".join(errors[:3]),
        fetched_rows=fetched_rows,
        normalized_rows=len(normalized),
        upserted_rows=upserted,
        empty_results=empty_results,
        failed_requests=failed_requests,
    )


def run_forecast_backfill(
    *,
    start_date: str,
    end_date: str,
    batch_size: int = 100,
    sleep_seconds: float = 1.0,
    limit: int | None = None,
    dry_run: bool = False,
    service: str = SETTINGS.research_service,
    client: Any = None,
) -> DatasetRunResult:
    return _run_period_event_backfill(
        dataset="forecast",
        endpoint="stock_yjyg_em",
        table="event.earnings_forecast",
        start_date=start_date,
        end_date=end_date,
        batch_size=batch_size,
        sleep_seconds=sleep_seconds,
        limit=limit,
        dry_run=dry_run,
        service=service,
        client=client or build_akshare_client(),
    )


def run_express_backfill(
    *,
    start_date: str,
    end_date: str,
    batch_size: int = 100,
    sleep_seconds: float = 1.0,
    limit: int | None = None,
    dry_run: bool = False,
    service: str = SETTINGS.research_service,
    client: Any = None,
) -> DatasetRunResult:
    return _run_period_event_backfill(
        dataset="express",
        endpoint="stock_yjkb_em",
        table="event.earnings_express",
        start_date=start_date,
        end_date=end_date,
        batch_size=batch_size,
        sleep_seconds=sleep_seconds,
        limit=limit,
        dry_run=dry_run,
        service=service,
        client=client or build_akshare_client(),
    )


def run_mainbiz_backfill(
    *,
    start_date: str,
    end_date: str,
    batch_size: int = 100,
    sleep_seconds: float = 1.0,
    limit: int | None = None,
    dry_run: bool = False,
    service: str = SETTINGS.research_service,
    client: Any = None,
    ts_codes: list[str] | None = None,
) -> DatasetRunResult:
    client = client or build_akshare_client()
    if ts_codes is None:
        try:
            universe_values = load_free_enrichment_ts_codes(service=service, limit=limit)
        except Exception as exc:
            return DatasetRunResult(
                dataset="mainbiz",
                status="failed",
                failed_requests=1,
                message=f"universe loader failed: {exc}",
            )
    else:
        universe_values = ts_codes
    universe = _normalize_ts_code_list(universe_values, limit=limit)
    frames: list[pd.DataFrame] = []
    fetched_rows = 0
    empty_results = 0
    failed_requests = 0
    errors: list[str] = []
    batches = _iter_batches(universe, batch_size)

    for batch_index, batch in enumerate(batches, start=1):
        print(
            "free_enrichment_request_batch|"
            f"dataset=mainbiz|batch={batch_index}/{len(batches)}|requests={len(batch)}"
        )
        for ts_code in batch:
            ak_symbol = ts_code_to_akshare_symbol(ts_code)
            if not ak_symbol:
                continue
            try:
                raw = pd.DataFrame(client.stock_zygc_em(symbol=ak_symbol))
                fetched_rows += len(raw)
                if raw.empty:
                    empty_results += 1
                    continue
                raw = raw.copy()
                if "股票代码" not in raw.columns:
                    raw["股票代码"] = ts_code
                normalized = normalize_main_business_rows(raw, endpoint="stock_zygc_em")
                normalized = _filter_frame_by_date_range(
                    normalized,
                    columns=["report_period"],
                    start_date=start_date,
                    end_date=end_date,
                )
                frames.append(normalized)
            except Exception as exc:
                failed_requests += 1
                errors.append(f"stock_zygc_em:{ts_code}:{exc}")
        _sleep_after_batch(batch_index, len(batches), sleep_seconds)

    normalized = _concat_frames(frames)
    upserted = 0 if dry_run else upsert_main_business_rows(normalized, service=service)
    return DatasetRunResult(
        dataset="mainbiz",
        status=_run_status(normalized_rows=len(normalized), upserted_rows=upserted, failed_requests=failed_requests),
        message="; ".join(errors[:3]),
        fetched_rows=fetched_rows,
        normalized_rows=len(normalized),
        upserted_rows=upserted,
        empty_results=empty_results,
        failed_requests=failed_requests,
    )


def coverage_row(result: DatasetRunResult, *, start_date: str, end_date: str) -> dict[str, Any]:
    return {
        "dataset": result.dataset,
        "start_date": start_date,
        "end_date": end_date,
        "asset_count_total": 0,
        "asset_count_covered": 0,
        "coverage_ratio": 0.0,
        "row_count": result.upserted_rows,
        "empty_result_count": result.empty_results,
        "failed_request_count": result.failed_requests,
        "status": result.status,
        "message": result.message,
        "source": SOURCE,
    }


def _ignored_batch_control_params(*, batch_size: int, sleep_seconds: float, limit: int | None) -> list[str]:
    ignored = []
    if batch_size is not None:
        ignored.append("batch_size")
    if sleep_seconds is not None:
        ignored.append("sleep_seconds")
    if limit is not None:
        ignored.append("limit")
    return ignored


def _batch_controls_applied(dataset: str) -> bool | str:
    if dataset == "holder":
        return "partial"
    return dataset in _BATCH_CONTROLLED_DATASETS


def _uncontrolled_request_units(dataset: str) -> list[str]:
    if dataset == "holder":
        return ["stock_ggcg_em(symbol=全部)"]
    return []


def _ignored_batch_control_params_for_dataset(
    dataset: str,
    *,
    batch_size: int,
    sleep_seconds: float,
    limit: int | None,
) -> list[str]:
    if dataset == "holder":
        return _ignored_batch_control_params(batch_size=batch_size, sleep_seconds=sleep_seconds, limit=limit)
    if _batch_controls_applied(dataset):
        return []
    return _ignored_batch_control_params(batch_size=batch_size, sleep_seconds=sleep_seconds, limit=limit)


def run_free_enrichment_backfill(
    *,
    dataset: str,
    start_date: str,
    end_date: str,
    output_dir: str | Path,
    batch_size: int = 100,
    sleep_seconds: float = 1.0,
    limit: int | None = None,
    dry_run: bool = False,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    requested = list(DATASETS) if dataset == "all" else [dataset]
    invalid = [name for name in requested if name not in DATASETS]
    if invalid:
        raise ValueError(f"Unsupported free enrichment dataset: {invalid[0]}")

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    summary_path = out / "run_summary.json"
    coverage_path = out / "dataset_coverage.csv"
    failures_path = out / "dataset_failures.csv"

    results: list[DatasetRunResult] = []
    failures: list[dict[str, str]] = []
    total = len(requested)
    batch_controls_applied_by_dataset = {name: _batch_controls_applied(name) for name in requested}
    ignored_params_by_dataset = {
        name: _ignored_batch_control_params_for_dataset(
            name,
            batch_size=batch_size,
            sleep_seconds=sleep_seconds,
            limit=limit,
        )
        for name in requested
    }
    uncontrolled_request_units_by_dataset = {name: _uncontrolled_request_units(name) for name in requested}
    runners = {
        "holder": run_holder_backfill,
        "repurchase": run_repurchase_backfill,
        "survey": run_survey_backfill,
        "forecast": run_forecast_backfill,
        "express": run_express_backfill,
        "mainbiz": run_mainbiz_backfill,
    }
    for idx, name in enumerate(requested, start=1):
        captured_exception = False
        try:
            if name == "lhb":
                result = run_lhb_backfill(
                    start_date=start_date,
                    end_date=end_date,
                    output_dir=out,
                    dry_run=dry_run,
                    service=service,
                )
            else:
                result = runners[name](
                    start_date=start_date,
                    end_date=end_date,
                    batch_size=batch_size,
                    sleep_seconds=sleep_seconds,
                    limit=limit,
                    dry_run=dry_run,
                    service=service,
                )
        except Exception as exc:
            message = str(exc)
            result = DatasetRunResult(dataset=name, status="failed", failed_requests=1, message=message)
            failures.append({"dataset": name, "request": "dataset", "error": message})
            captured_exception = True

        if result.status in {"failed", "partial_failed"} and result.message and not captured_exception:
            failures.append({"dataset": name, "request": "dataset", "error": result.message})
        results.append(result)
        print(
            "free_enrichment_batch|"
            f"dataset={result.dataset}|batch={idx}/{total}|dry_run={dry_run}|"
            f"status={result.status}|batch_controls_applied={batch_controls_applied_by_dataset[name]}|"
            f"ignored_params={','.join(ignored_params_by_dataset[name])}|"
            f"uncontrolled_request_units={','.join(uncontrolled_request_units_by_dataset[name])}|"
            f"batch_size={batch_size}|sleep_seconds={sleep_seconds}|"
            f"limit={limit}|limit_applies_to_placeholders=False|fetched={result.fetched_rows}|"
            f"normalized={result.normalized_rows}|upserted={result.upserted_rows}|"
            f"empty={result.empty_results}|failed={result.failed_requests}|failure_sample={failures_path}"
        )

    params = {
        "dataset": dataset,
        "requested_datasets": requested,
        "start_date": start_date,
        "end_date": end_date,
        "output_dir": str(out),
        "batch_size": batch_size,
        "sleep_seconds": sleep_seconds,
        "limit": limit,
        "limit_applies_to_placeholders": False,
        "batch_controls_applied_by_dataset": batch_controls_applied_by_dataset,
        "ignored_params_by_dataset": ignored_params_by_dataset,
        "uncontrolled_request_units_by_dataset": uncontrolled_request_units_by_dataset,
        "dry_run": dry_run,
        "service": service,
    }
    summary_path.write_text(
        json.dumps({"params": params, "results": [item.to_dict() for item in results]}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    pd.DataFrame([coverage_row(item, start_date=start_date, end_date=end_date) for item in results]).to_csv(
        coverage_path,
        index=False,
    )
    pd.DataFrame(failures, columns=["dataset", "request", "error"]).to_csv(failures_path, index=False)

    return {
        "results": results,
        "summary_path": str(summary_path),
        "coverage_path": str(coverage_path),
        "failures_path": str(failures_path),
    }
