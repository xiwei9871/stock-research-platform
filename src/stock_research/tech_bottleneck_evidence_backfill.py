from __future__ import annotations

import json
from typing import Any

import pandas as pd

from stock_research.tech_bottleneck_readiness import (
    BOTTLENECK_KEYWORDS,
    CAPACITY_KEYWORDS,
    CUSTOMER_CERTIFICATION_KEYWORDS,
    INVALIDATION_KEYWORDS,
    TECHNICAL_BARRIER_KEYWORDS,
)


EVIDENCE_COLUMNS = [
    "run_id",
    "asset_id",
    "stock_name",
    "candidate_trade_date",
    "as_of_date",
    "evidence_date",
    "source_type",
    "source_id",
    "source_title",
    "source_url",
    "evidence_type",
    "matched_keyword",
    "evidence_snippet",
    "source_confidence",
    "is_proxy",
    "as_of_safe",
    "metadata_json",
]

TEXT_EVIDENCE_GROUPS = {
    "bottleneck_keyword": BOTTLENECK_KEYWORDS,
    "capacity": CAPACITY_KEYWORDS,
    "customer_certification": CUSTOMER_CERTIFICATION_KEYWORDS,
    "technical_barrier": TECHNICAL_BARRIER_KEYWORDS,
    "invalidation": INVALIDATION_KEYWORDS,
}


def normalize_evidence_candidates(
    candidates: pd.DataFrame,
    *,
    run_date: str,
    start_date: str | None,
    end_date: str | None,
    lookback_days: int,
) -> pd.DataFrame:
    if "asset_id" not in candidates.columns:
        raise ValueError("evidence candidates must include asset_id")

    normalized = candidates.copy()
    for column in ["stock_name", "trade_date", "candidate_source", "rank"]:
        if column not in normalized.columns:
            normalized[column] = ""

    normalized["asset_id"] = normalized["asset_id"].map(_safe_text)
    normalized = normalized[normalized["asset_id"] != ""].copy()
    normalized["stock_name"] = normalized["stock_name"].map(_safe_text)
    normalized["trade_date"] = normalized["trade_date"].map(_date_text)
    normalized["candidate_source"] = normalized["candidate_source"].map(_safe_text)
    normalized["rank"] = normalized["rank"].map(_safe_text)

    fallback_run_date = _date_text(run_date)
    normalized["as_of_date"] = normalized["trade_date"].map(lambda trade_date: trade_date or fallback_run_date)
    normalized["lookback_days"] = int(lookback_days)

    start_timestamp = _date_timestamp(start_date)
    end_timestamp = _date_timestamp(end_date)
    as_of_timestamps = normalized["as_of_date"].map(_date_timestamp)
    if start_timestamp is not None:
        normalized = normalized[as_of_timestamps.notna() & (as_of_timestamps >= start_timestamp)].copy()
        as_of_timestamps = normalized["as_of_date"].map(_date_timestamp)
    if end_timestamp is not None:
        normalized = normalized[as_of_timestamps.notna() & (as_of_timestamps <= end_timestamp)].copy()

    return normalized[
        ["asset_id", "stock_name", "trade_date", "candidate_source", "rank", "as_of_date", "lookback_days"]
    ]


def normalize_evidence_rows(rows: pd.DataFrame) -> pd.DataFrame:
    normalized = rows.copy()
    for column in EVIDENCE_COLUMNS:
        if column not in normalized.columns:
            normalized[column] = False if column in {"is_proxy", "as_of_safe"} else ""

    text_columns = [
        "run_id",
        "asset_id",
        "stock_name",
        "candidate_trade_date",
        "as_of_date",
        "evidence_date",
        "source_type",
        "source_id",
        "source_title",
        "source_url",
        "evidence_type",
        "matched_keyword",
        "evidence_snippet",
        "source_confidence",
    ]
    for column in text_columns:
        if column in {"candidate_trade_date", "as_of_date", "evidence_date"}:
            normalized[column] = normalized[column].map(_date_text)
        else:
            normalized[column] = normalized[column].map(_safe_text)

    normalized["metadata_json"] = normalized["metadata_json"].map(_metadata_json)
    normalized["is_proxy"] = normalized["is_proxy"].map(_bool_value).astype(object)
    normalized["as_of_safe"] = normalized["as_of_safe"].map(_bool_value).astype(object)

    return normalized[EVIDENCE_COLUMNS]


def classify_text_evidence(
    *,
    text: str,
    source_type: str,
    source_id: str,
    source_title: str,
    source_date: str,
) -> list[dict[str, Any]]:
    evidence_text = _safe_text(text)
    lowered = evidence_text.lower()
    matches: list[dict[str, Any]] = []

    for evidence_type, keywords in TEXT_EVIDENCE_GROUPS.items():
        for keyword in keywords:
            if keyword.lower() not in lowered:
                continue
            matches.append(
                {
                    "evidence_date": _date_text(source_date),
                    "source_type": _safe_text(source_type),
                    "source_id": _safe_text(source_id),
                    "source_title": _safe_text(source_title),
                    "source_url": "",
                    "evidence_type": evidence_type,
                    "matched_keyword": keyword,
                    "evidence_snippet": _snippet(evidence_text, keyword),
                    "source_confidence": "medium",
                    "is_proxy": evidence_type == "technical_barrier",
                    "as_of_safe": True,
                    "metadata_json": {},
                }
            )
            break

    return matches


def _safe_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    return str(value).strip()


def _date_text(value: Any) -> str:
    timestamp = _date_timestamp(value)
    if timestamp is None:
        return ""
    return timestamp.strftime("%Y-%m-%d")


def _date_timestamp(value: Any) -> pd.Timestamp | None:
    text = _safe_text(value)
    if not text:
        return None
    try:
        timestamp = pd.to_datetime(text, errors="coerce")
    except Exception:
        return None
    if pd.isna(timestamp):
        return None
    return pd.Timestamp(timestamp).normalize()


def _metadata_json(value: Any) -> str:
    if isinstance(value, str):
        text = _safe_text(value)
        if not text:
            return "{}"
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = {"value": text}
        return json.dumps(parsed, ensure_ascii=False, sort_keys=True)
    try:
        if pd.isna(value):
            return "{}"
    except Exception:
        pass
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = _safe_text(value).lower()
    if text in {"", "0", "false", "f", "no", "n"}:
        return False
    if text in {"1", "true", "t", "yes", "y"}:
        return True
    return bool(value)


def _snippet(text: str, keyword: str) -> str:
    index = text.lower().find(keyword.lower())
    if index < 0:
        return text[:120]
    start = max(0, index - 40)
    end = min(len(text), index + len(keyword) + 40)
    return text[start:end]
