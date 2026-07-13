from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd

from stock_research.dashboard.tech_bottleneck_review_decisions import apply_overlay_to_row


DATA_DIR = Path("outputs/research/tech_bottleneck_review_universe_frontend_dataset_v1")
DATASET_PATH = DATA_DIR / "tech_bottleneck_review_universe_frontend_dataset.csv"
EVIDENCE_PATH = DATA_DIR / "tech_bottleneck_review_universe_frontend_evidence_index.csv"
SOURCE_PATH = DATA_DIR / "tech_bottleneck_review_universe_frontend_source_index.csv"
FILTER_OPTIONS_PATH = DATA_DIR / "tech_bottleneck_review_universe_frontend_filter_options.json"
SUMMARY_PATH = DATA_DIR / "tech_bottleneck_review_universe_frontend_dataset_summary.json"


def _normalize_stock_code(value: Any) -> str:
    raw = str(value or "").strip().split(".")[0]
    return raw.zfill(6) if raw.isdigit() else raw.upper()


def _bool_value(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _clean_value(value: Any) -> Any:
    if pd.isna(value):
        return ""
    if isinstance(value, str):
        normalized = value.strip()
        if normalized.lower() == "nan":
            return ""
        if normalized.lower() == "true":
            return True
        if normalized.lower() == "false":
            return False
        return normalized
    return value


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    frame = pd.read_csv(path, dtype=str).fillna("")
    if "stock_code" in frame.columns:
        frame["stock_code"] = frame["stock_code"].map(_normalize_stock_code)
    return frame


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    return [{key: _clean_value(value) for key, value in row.items()} for row in frame.to_dict("records")]


@lru_cache(maxsize=1)
def _dataset() -> pd.DataFrame:
    return _read_csv(DATASET_PATH)


@lru_cache(maxsize=1)
def _evidence() -> pd.DataFrame:
    return _read_csv(EVIDENCE_PATH)


@lru_cache(maxsize=1)
def _sources() -> pd.DataFrame:
    return _read_csv(SOURCE_PATH)


@lru_cache(maxsize=1)
def _summary() -> dict[str, Any]:
    if not SUMMARY_PATH.exists():
        return {}
    with SUMMARY_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


def load_review_universe_summary() -> dict[str, Any]:
    payload = dict(_summary())
    payload.update(
        {
            "readonly_page": True,
            "reviewer_decision_write_enabled": False,
            "database_write_enabled": False,
            "csv_writeback_enabled": False,
        }
    )
    return payload


def _apply_filter(frame: pd.DataFrame, column: str, value: Any) -> pd.DataFrame:
    if value in (None, "") or column not in frame.columns:
        return frame
    if column == "primary_source_supported":
        expected = _bool_value(value)
        return frame[frame[column].map(_bool_value) == expected]
    return frame[frame[column].astype(str) == str(value)]


def list_review_universe_stocks(
    *,
    review_universe_source: str | None = None,
    current_layer_status: str | None = None,
    manual_approval_status: str | None = None,
    hard_tech_domain: str | None = None,
    supply_chain_role_hint: str | None = None,
    concept_pollution_risk: str | None = None,
    route_around_or_substitution_risk: str | None = None,
    value_capture_risk: str | None = None,
    primary_source_supported: str | None = None,
    frontend_review_status: str | None = None,
    reviewer_decision: str | None = None,
    q: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    frame = _dataset().copy()
    for column, value in {
        "review_universe_source": review_universe_source,
        "current_layer_status": current_layer_status,
        "manual_approval_status": manual_approval_status,
        "hard_tech_domain": hard_tech_domain,
        "supply_chain_role_hint": supply_chain_role_hint,
        "concept_pollution_risk": concept_pollution_risk,
        "route_around_or_substitution_risk": route_around_or_substitution_risk,
        "value_capture_risk": value_capture_risk,
        "primary_source_supported": primary_source_supported,
        "frontend_review_status": frontend_review_status,
        "reviewer_decision": reviewer_decision,
    }.items():
        frame = _apply_filter(frame, column, value)

    if q:
        query = q.strip().lower()
        if query:
            frame = frame[
                frame["stock_code"].astype(str).str.lower().str.contains(query, regex=False)
                | frame["stock_name"].astype(str).str.lower().str.contains(query, regex=False)
            ]

    total = int(len(frame))
    bounded_limit = max(1, min(int(limit), 1000))
    bounded_offset = max(0, int(offset))
    page = frame.iloc[bounded_offset : bounded_offset + bounded_limit]
    return {
        "total": total,
        "limit": bounded_limit,
        "offset": bounded_offset,
        "items": [apply_overlay_to_row(row) for row in _records(page)],
    }


def get_review_universe_stock(stock_code: str) -> dict[str, Any] | None:
    normalized = _normalize_stock_code(stock_code)
    frame = _dataset()
    if frame.empty:
        return None
    match = frame[frame["stock_code"] == normalized]
    if match.empty:
        return None
    return apply_overlay_to_row(_records(match.head(1))[0])


def list_review_universe_evidence(stock_code: str) -> dict[str, Any]:
    normalized = _normalize_stock_code(stock_code)
    frame = _evidence()
    if not frame.empty:
        frame = frame[frame["stock_code"] == normalized]
    return {"stock_code": normalized, "total": int(len(frame)), "items": _records(frame)}


def list_review_universe_sources(stock_code: str) -> dict[str, Any]:
    normalized = _normalize_stock_code(stock_code)
    frame = _sources()
    if not frame.empty:
        frame = frame[frame["stock_code"] == normalized]
    return {"stock_code": normalized, "total": int(len(frame)), "items": _records(frame)}


def load_review_universe_filter_options() -> dict[str, Any]:
    if FILTER_OPTIONS_PATH.exists():
        with FILTER_OPTIONS_PATH.open(encoding="utf-8") as handle:
            return json.load(handle)
    return {}
