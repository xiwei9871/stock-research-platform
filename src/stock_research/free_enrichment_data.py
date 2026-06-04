from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from stock_research.config import SETTINGS


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


def payload_hash(payload: Any) -> str:
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
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
