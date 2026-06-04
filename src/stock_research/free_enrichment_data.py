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
_EXCHANGES = {"SH", "SZ", "BJ"}


@dataclass(frozen=True)
class DatasetRunResult:
    dataset: str
    fetched_rows: int = 0
    normalized_rows: int = 0
    upserted_rows: int = 0
    empty_results: int = 0
    failed_requests: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset": self.dataset,
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
