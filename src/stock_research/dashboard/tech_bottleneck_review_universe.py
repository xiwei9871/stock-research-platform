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
QUALITY_REASSESSMENT_PATH = (
    Path("outputs/research/tech_bottleneck_review_universe_quality_reassessment_v2")
    / "review_universe_quality_reassessment_v2.csv"
)
OMISSION_RESCUE_DATASET_PATH = (
    Path("outputs/research/tech_bottleneck_omission_rescue_evidence_completion_reassessment_v1")
    / "omission_rescue_quality_reassessment.csv"
)
OMISSION_RESCUE_EVIDENCE_PATH = (
    Path("outputs/research/tech_bottleneck_omission_rescue_evidence_completion_reassessment_v1")
    / "omission_rescue_evidence_index.csv"
)
OMISSION_RESCUE_SOURCE_PATH = (
    Path("outputs/research/tech_bottleneck_omission_rescue_evidence_completion_reassessment_v1")
    / "omission_rescue_source_index.csv"
)


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


def _series_or_default(frame: pd.DataFrame, column: str, default: Any = "") -> pd.Series:
    if column in frame.columns:
        return frame[column]
    if isinstance(default, pd.Series):
        return default.reindex(frame.index).fillna("")
    return pd.Series([default] * len(frame), index=frame.index)


@lru_cache(maxsize=1)
def _dataset() -> pd.DataFrame:
    frame = _read_csv(DATASET_PATH)
    quality = _quality_reassessment()
    if frame.empty or quality.empty:
        base = frame
    else:
        quality_columns = [
            "stock_code",
            "quality_reassessment_tier",
            "overall_quality_score",
            "evidence_chain_score",
            "business_alignment_score",
            "financial_quality_score",
            "risk_penalty",
            "recommended_review_action",
            "quality_reassessment_reason",
        ]
        available = [column for column in quality_columns if column in quality.columns]
        base = frame.merge(quality[available], on="stock_code", how="left")
    omission = _omission_rescue_dataset(base_columns=list(base.columns))
    if omission.empty:
        return base
    base_codes = set(base["stock_code"].astype(str)) if "stock_code" in base.columns else set()
    omission = omission[~omission["stock_code"].astype(str).isin(base_codes)].copy()
    if omission.empty:
        return base
    return pd.concat([base, omission], ignore_index=True, sort=False).fillna("")


def _omission_rescue_dataset(*, base_columns: list[str]) -> pd.DataFrame:
    frame = _read_csv(OMISSION_RESCUE_DATASET_PATH)
    if frame.empty or "stock_code" not in frame.columns:
        return pd.DataFrame()
    frame = frame.copy()
    frame["review_universe_source"] = _series_or_default(frame, "review_universe_source", "omission_rescue").replace("", "omission_rescue")
    frame["current_layer_status"] = _series_or_default(frame, "current_layer_status", _series_or_default(frame, "recall_decision", "omission_rescue_review")).replace("", "omission_rescue_review")
    frame["manual_approval_status"] = _series_or_default(frame, "manual_approval_status", "pending_manual_review").replace("", "pending_manual_review")
    frame["frontend_review_status"] = _series_or_default(frame, "frontend_review_status", "pending_review").replace("", "pending_review")
    frame["review_status"] = _series_or_default(frame, "review_status", "pending_review").replace("", "pending_review")
    frame["reviewer_decision"] = _series_or_default(frame, "reviewer_decision", "")
    frame["reviewer_note"] = _series_or_default(frame, "reviewer_note", "")
    industry = _series_or_default(frame, "industry", "")
    domain = _series_or_default(frame, "tech_bottleneck_domain", "")
    frame["industry"] = industry.where(industry.astype(str).str.len().gt(0), domain)
    frame["concept_tags"] = _series_or_default(frame, "concept_tags", _series_or_default(frame, "db_concept_tags", _series_or_default(frame, "tech_bottleneck_domain", "")))
    frame["hard_tech_domain"] = _series_or_default(frame, "hard_tech_domain", _series_or_default(frame, "tech_bottleneck_domain", ""))
    frame["supply_chain_role_hint"] = _series_or_default(frame, "supply_chain_role_hint", _series_or_default(frame, "supply_chain_role", ""))
    frame["business_relevance_hint"] = _series_or_default(frame, "business_relevance_hint", _series_or_default(frame, "business_relevance_signal", ""))
    frame["bottleneck_or_chokepoint_hint"] = _series_or_default(frame, "bottleneck_or_chokepoint_hint", _series_or_default(frame, "bottleneck_relevance", ""))
    frame["source_group"] = _series_or_default(frame, "source_group", frame["review_universe_source"])
    frame["previous_tier"] = _series_or_default(frame, "previous_tier", _series_or_default(frame, "source_bucket", "omission_rescue"))
    frame["used_for_signal"] = False
    frame["used_for_admission"] = False
    frame["auto_added_to_quality_pool"] = False
    for column in base_columns:
        if column not in frame.columns:
            frame[column] = ""
    return frame


@lru_cache(maxsize=1)
def _quality_reassessment() -> pd.DataFrame:
    return _read_csv(QUALITY_REASSESSMENT_PATH)


@lru_cache(maxsize=1)
def _evidence() -> pd.DataFrame:
    base = _read_csv(EVIDENCE_PATH)
    omission = _read_csv(OMISSION_RESCUE_EVIDENCE_PATH)
    if omission.empty:
        return base
    if "source_file" not in omission.columns:
        omission["source_file"] = _series_or_default(omission, "source_path", _series_or_default(omission, "source_artifact", ""))
    if "citation_quality" not in omission.columns:
        omission["citation_quality"] = "page_level"
    if base.empty:
        return omission.fillna("")
    return pd.concat([base, omission], ignore_index=True, sort=False).fillna("")


@lru_cache(maxsize=1)
def _sources() -> pd.DataFrame:
    base = _read_csv(SOURCE_PATH)
    omission = _read_csv(OMISSION_RESCUE_SOURCE_PATH)
    if omission.empty:
        return base
    if "source_file" not in omission.columns:
        omission["source_file"] = _series_or_default(omission, "source_path", _series_or_default(omission, "source_artifact", ""))
    if base.empty:
        return omission.fillna("")
    return pd.concat([base, omission], ignore_index=True, sort=False).fillna("")


@lru_cache(maxsize=1)
def _summary() -> dict[str, Any]:
    if not SUMMARY_PATH.exists():
        return {}
    with SUMMARY_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


def load_review_universe_summary() -> dict[str, Any]:
    payload = dict(_summary())
    dataset = _dataset()
    evidence = _evidence()
    sources = _sources()
    base_count = int(len(_read_csv(DATASET_PATH)))
    omission_count = int(len(_omission_rescue_dataset(base_columns=list(dataset.columns))))
    payload.update(
        {
            "base_frontend_dataset_count": base_count,
            "omission_rescue_review_count": omission_count,
            "review_universe_total_count": int(len(dataset)),
            "frontend_dataset_count": int(len(dataset)),
            "evidence_index_row_count": int(len(evidence)),
            "source_index_row_count": int(len(sources)),
        }
    )
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
    quality_reassessment_tier: str | None = None,
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
        "quality_reassessment_tier": quality_reassessment_tier,
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
        page_level = frame[
            frame.get("citation_quality", pd.Series(index=frame.index, dtype=str)).astype(str).str.contains("page", case=False, na=False)
            | frame.get("page", pd.Series(index=frame.index, dtype=str)).astype(str).str.len().gt(0)
        ]
        if not page_level.empty:
            frame = page_level
    return {"stock_code": normalized, "total": int(len(frame)), "items": _records(frame)}


def list_review_universe_sources(stock_code: str) -> dict[str, Any]:
    normalized = _normalize_stock_code(stock_code)
    frame = _sources()
    if not frame.empty:
        frame = frame[frame["stock_code"] == normalized]
    return {"stock_code": normalized, "total": int(len(frame)), "items": _records(frame)}


def load_review_universe_filter_options() -> dict[str, Any]:
    frame = _dataset()
    if FILTER_OPTIONS_PATH.exists():
        with FILTER_OPTIONS_PATH.open(encoding="utf-8") as handle:
            payload = json.load(handle)
    else:
        payload = {}
    payload.pop("bottleneck_relevance", None)
    if not frame.empty and "quality_reassessment_tier" in frame.columns:
        payload["quality_reassessment_tier"] = sorted(
            value
            for value in frame["quality_reassessment_tier"].astype(str).unique().tolist()
            if value
        )
    return payload
