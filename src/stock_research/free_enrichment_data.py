from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from stock_research.config import SETTINGS
from stock_research.db import connect, execute_many


SOURCE = "akshare"
DATASETS = ("lhb", "holder", "repurchase", "survey", "forecast", "express", "mainbiz")
_EXCHANGES = {"SH", "SZ", "BJ"}


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


def _date_text(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, errors="coerce").dt.strftime("%Y-%m-%d")


def _first_existing(frame: pd.DataFrame, names: list[str]) -> pd.Series:
    for name in names:
        if name in frame.columns:
            return frame[name]
    return pd.Series([None] * len(frame), index=frame.index)


def normalize_shareholder_count_rows(frame: pd.DataFrame, *, endpoint: str) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame()

    data = pd.DataFrame(index=frame.index)
    data["ts_code"] = _first_existing(frame, ["代码", "股票代码", "SECURITY_CODE"]).map(normalize_ts_code)
    data["asset_id"] = data["ts_code"].map(ts_code_to_asset_id)
    data["report_date"] = _date_text(_first_existing(frame, ["截止日期", "报告期", "END_DATE"]))
    data["announcement_date"] = _date_text(_first_existing(frame, ["公告日期", "DECLAREDATE", "公告日"]))
    data["shareholder_count"] = pd.to_numeric(_first_existing(frame, ["股东户数", "HOLDER_NUM"]), errors="coerce")
    data["shareholder_count_change"] = pd.to_numeric(
        _first_existing(frame, ["股东户数增减", "较上期变化", "HOLDER_NUM_CHANGE"]),
        errors="coerce",
    )
    data["shareholder_count_change_pct"] = pd.to_numeric(
        _first_existing(frame, ["股东户数较上期变化百分比", "较上期变化百分比"]),
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
    data["holder_type"] = _first_existing(frame, ["股东类型", "HOLDER_TYPE"])
    data["hold_amount"] = pd.to_numeric(_first_existing(frame, ["持股数", "持股数量", "HOLD_NUM"]), errors="coerce")
    data["hold_ratio"] = pd.to_numeric(
        _first_existing(frame, ["占总股本持股比例", "持股比例", "HOLD_RATIO"]),
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

    data["announcement_date"] = _date_text(_first_existing(frame, ["公告日期", "ANN_DATE"]))
    data["progress_date"] = _date_text(_first_existing(frame, ["进度日期", "更新日期", "UPDATE_DATE"]))
    data["progress"] = _first_existing(frame, ["进度", "回购进度", "PROGRESS"])
    data["repurchase_amount"] = pd.to_numeric(
        _first_existing(frame, ["已回购金额", "回购金额", "REPURCHASE_AMOUNT"]),
        errors="coerce",
    )
    data["repurchase_amount_min"] = pd.to_numeric(
        _first_existing(frame, ["拟回购金额下限", "金额下限"]),
        errors="coerce",
    )
    data["repurchase_amount_max"] = pd.to_numeric(
        _first_existing(frame, ["拟回购金额上限", "金额上限"]),
        errors="coerce",
    )
    data["repurchase_price_min"] = pd.to_numeric(
        _first_existing(frame, ["回购价格下限", "价格下限"]),
        errors="coerce",
    )
    data["repurchase_price_max"] = pd.to_numeric(
        _first_existing(frame, ["回购价格上限", "价格上限"]),
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

    data["trade_date"] = _date_text(_first_existing(frame, ["变动日期", "交易日期", "TRADE_DATE"]))
    data["announcement_date"] = _date_text(_first_existing(frame, ["公告日期", "ANN_DATE"]))
    data["holder_name"] = _first_existing(frame, ["股东名称", "变动人", "HOLDER_NAME"])
    data["trade_type"] = _first_existing(frame, ["变动方向", "变动类型", "TRADE_TYPE"])
    data["trade_amount"] = pd.to_numeric(
        _first_existing(frame, ["变动数量", "成交股数", "TRADE_AMOUNT"]),
        errors="coerce",
    )
    data["trade_ratio"] = pd.to_numeric(_first_existing(frame, ["变动比例", "TRADE_RATIO"]), errors="coerce")
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
        _first_existing(frame, ["净利润下限", "FORECAST_NP_MIN"]),
        errors="coerce",
    )
    data["forecast_np_max"] = pd.to_numeric(
        _first_existing(frame, ["净利润上限", "FORECAST_NP_MAX"]),
        errors="coerce",
    )
    data["forecast_np_change_min"] = pd.to_numeric(
        _first_existing(frame, ["净利润变动幅度下限", "预增幅下限"]),
        errors="coerce",
    )
    data["forecast_np_change_max"] = pd.to_numeric(
        _first_existing(frame, ["净利润变动幅度上限", "预增幅上限"]),
        errors="coerce",
    )
    data["summary"] = _first_existing(frame, ["业绩预告摘要", "变动原因", "SUMMARY"])
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
    data["revenue"] = pd.to_numeric(_first_existing(frame, ["营业收入", "REVENUE"]), errors="coerce")
    data["revenue_yoy"] = pd.to_numeric(_first_existing(frame, ["营业收入同比", "REVENUE_YOY"]), errors="coerce")
    data["np_parent"] = pd.to_numeric(_first_existing(frame, ["归母净利润", "净利润", "NP_PARENT"]), errors="coerce")
    data["np_parent_yoy"] = pd.to_numeric(
        _first_existing(frame, ["归母净利润同比", "净利润同比", "NP_PARENT_YOY"]),
        errors="coerce",
    )
    data["eps_basic"] = pd.to_numeric(_first_existing(frame, ["基本每股收益", "EPS_BASIC"]), errors="coerce")
    data["roe_weighted"] = pd.to_numeric(_first_existing(frame, ["加权净资产收益率", "ROE_WEIGHTED"]), errors="coerce")
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
    data["report_period"] = _date_text(_first_existing(frame, ["报告期", "截止日期", "REPORT_PERIOD"]))
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
    batch_controls_applied_by_dataset = {name: False for name in requested}
    ignored_params_by_dataset = {
        name: _ignored_batch_control_params(batch_size=batch_size, sleep_seconds=sleep_seconds, limit=limit)
        for name in requested
    }
    for idx, name in enumerate(requested, start=1):
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
                message = "dataset runner not implemented"
                result = DatasetRunResult(
                    dataset=name,
                    status="not_implemented",
                    failed_requests=1,
                    message=message,
                )
                failures.append({"dataset": name, "request": "dataset", "error": message})
        except Exception as exc:
            message = str(exc)
            result = DatasetRunResult(dataset=name, status="failed", failed_requests=1, message=message)
            failures.append({"dataset": name, "request": "dataset", "error": message})

        results.append(result)
        print(
            "free_enrichment_batch|"
            f"dataset={result.dataset}|batch={idx}/{total}|dry_run={dry_run}|"
            f"status={result.status}|batch_controls_applied={batch_controls_applied_by_dataset[name]}|"
            f"ignored_params={','.join(ignored_params_by_dataset[name])}|"
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
