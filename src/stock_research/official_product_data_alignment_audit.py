from __future__ import annotations

from dataclasses import dataclass
import datetime as dt
import json
from pathlib import Path
from typing import Any

import pandas as pd


ALIGNMENT_AUDIT_COLUMNS = [
    "run_id",
    "asset_id",
    "ts_code",
    "stock_name",
    "candidate_trade_date",
    "as_of_date",
    "alignment_status",
    "alignment_reason",
    "recommended_action",
    "has_pit_safe_product_evidence",
    "product_evidence_count",
    "safe_product_evidence_count",
    "unsafe_product_evidence_count",
    "best_report_period",
    "best_publish_date",
    "best_source_document_id",
    "best_source_document_url",
    "min_future_publish_date",
    "days_until_first_future_disclosure",
]

ALIGNMENT_STATUS_SUMMARY_COLUMNS = [
    "alignment_status",
    "candidate_rows",
    "recommended_action",
]

RECOMMENDED_ACTION_BY_STATUS = {
    "pit_safe_product_evidence_available": "use_for_readiness",
    "joinable_but_future_disclosure": "shift_test_window_later",
    "no_official_manifest_or_product_rows": "collect_official_product_data",
}

_ALIGNMENT_REASON_BY_STATUS = {
    "pit_safe_product_evidence_available": "candidate row has strict PIT-safe official product evidence",
    "joinable_but_future_disclosure": "official product evidence exists but publish_date is after candidate as_of_date",
    "no_official_manifest_or_product_rows": "no official manifest or product evidence rows found for candidate",
}


@dataclass(frozen=True)
class OfficialProductDataAlignmentAuditResult:
    audit: pd.DataFrame
    status_summary: pd.DataFrame
    output_dir: Path | None = None


def normalize_alignment_candidates(candidates: pd.DataFrame) -> pd.DataFrame:
    normalized = candidates.copy()
    for column in ["asset_id", "ts_code", "stock_name", "trade_date", "candidate_trade_date", "as_of_date"]:
        if column not in normalized.columns:
            normalized[column] = ""
    if normalized.empty:
        return pd.DataFrame(columns=["asset_id", "ts_code", "stock_name", "candidate_trade_date", "as_of_date"])

    normalized["asset_id"] = normalized["asset_id"].map(_safe_text)
    normalized["ts_code"] = normalized.apply(
        lambda row: _safe_text(row["ts_code"]) or _derive_ts_code(row["asset_id"]),
        axis=1,
    )
    normalized["stock_name"] = normalized["stock_name"].map(_safe_text)
    normalized["candidate_trade_date"] = normalized.apply(
        lambda row: _first_date_value(row["candidate_trade_date"], row["trade_date"]),
        axis=1,
    )
    normalized["as_of_date"] = normalized.apply(
        lambda row: _first_date_value(row["as_of_date"], row["candidate_trade_date"], row["trade_date"]),
        axis=1,
    )
    normalized = normalized[
        normalized["asset_id"].ne("")
        & normalized["ts_code"].ne("")
        & normalized["candidate_trade_date"].notna()
        & normalized["as_of_date"].notna()
    ].copy()
    return normalized[["asset_id", "ts_code", "stock_name", "candidate_trade_date", "as_of_date"]].reset_index(drop=True)


def build_alignment_audit(
    *,
    candidates: pd.DataFrame,
    product_evidence: pd.DataFrame,
    disclosure_manifest: pd.DataFrame,
    product_join_diagnostics: pd.DataFrame,
    manifest_query_errors: pd.DataFrame,
    run_id: str,
) -> pd.DataFrame:
    del disclosure_manifest, product_join_diagnostics, manifest_query_errors

    normalized_candidates = normalize_alignment_candidates(candidates)
    evidence = _normalize_product_evidence(product_evidence)
    evidence_by_candidate = {
        key: group.copy()
        for key, group in evidence.groupby(["asset_id", "candidate_trade_date", "as_of_date"], dropna=False)
    }

    rows: list[dict[str, Any]] = []
    for candidate in normalized_candidates.to_dict("records"):
        candidate_key = (
            candidate["asset_id"],
            candidate["candidate_trade_date"],
            candidate["as_of_date"],
        )
        candidate_evidence = evidence_by_candidate.get(candidate_key, pd.DataFrame(columns=evidence.columns))
        safe_evidence = candidate_evidence[candidate_evidence["as_of_safe"].eq(True)].copy()
        unsafe_evidence = candidate_evidence[~candidate_evidence["as_of_safe"].eq(True)].copy()
        best_evidence = _best_evidence_row(safe_evidence if not safe_evidence.empty else candidate_evidence)
        status = _alignment_status(candidate_evidence=candidate_evidence, safe_evidence=safe_evidence)
        min_future_publish_date = _min_future_publish_date(
            candidate_evidence=candidate_evidence,
            as_of_date=candidate["as_of_date"],
        )
        days_until_first_future_disclosure = (
            (min_future_publish_date - candidate["as_of_date"]).days if min_future_publish_date is not None else None
        )

        rows.append(
            {
                "run_id": _safe_text(run_id),
                "asset_id": candidate["asset_id"],
                "ts_code": candidate["ts_code"],
                "stock_name": candidate["stock_name"],
                "candidate_trade_date": candidate["candidate_trade_date"],
                "as_of_date": candidate["as_of_date"],
                "alignment_status": status,
                "alignment_reason": _ALIGNMENT_REASON_BY_STATUS[status],
                "recommended_action": RECOMMENDED_ACTION_BY_STATUS[status],
                "has_pit_safe_product_evidence": bool(not safe_evidence.empty),
                "product_evidence_count": int(len(candidate_evidence)),
                "safe_product_evidence_count": int(len(safe_evidence)),
                "unsafe_product_evidence_count": int(len(unsafe_evidence)),
                "best_report_period": best_evidence.get("report_period"),
                "best_publish_date": best_evidence.get("publish_date"),
                "best_source_document_id": best_evidence.get("source_document_id"),
                "best_source_document_url": best_evidence.get("source_document_url"),
                "min_future_publish_date": min_future_publish_date,
                "days_until_first_future_disclosure": days_until_first_future_disclosure,
            }
        )

    return pd.DataFrame(rows, columns=ALIGNMENT_AUDIT_COLUMNS)


def _normalize_product_evidence(product_evidence: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "asset_id",
        "candidate_trade_date",
        "as_of_date",
        "as_of_safe",
        "metadata_json",
        "evidence_date",
        "source_id",
        "source_url",
    ]
    evidence = product_evidence.copy()
    for column in columns:
        if column not in evidence.columns:
            evidence[column] = ""
    if evidence.empty:
        return pd.DataFrame(
            columns=[
                "asset_id",
                "candidate_trade_date",
                "as_of_date",
                "as_of_safe",
                "report_period",
                "publish_date",
                "source_document_id",
                "source_document_url",
            ]
        )

    evidence["asset_id"] = evidence["asset_id"].map(_safe_text)
    evidence["candidate_trade_date"] = evidence["candidate_trade_date"].map(_date_value)
    evidence["as_of_date"] = evidence["as_of_date"].map(_date_value)
    evidence["as_of_safe"] = evidence["as_of_safe"].map(_bool_value)
    metadata = evidence["metadata_json"].map(_metadata_dict)
    evidence["report_period"] = metadata.map(lambda item: _date_value(item.get("report_period")))
    evidence["publish_date"] = metadata.map(lambda item: _date_value(item.get("publish_date")))
    evidence["source_document_id"] = metadata.map(lambda item: _safe_text(item.get("source_document_id")))
    evidence["source_document_url"] = metadata.map(lambda item: _safe_text(item.get("source_document_url")))
    evidence["source_document_id"] = evidence.apply(
        lambda row: row["source_document_id"] or _safe_text(row["source_id"]),
        axis=1,
    )
    evidence["source_document_url"] = evidence.apply(
        lambda row: row["source_document_url"] or _safe_text(row["source_url"]),
        axis=1,
    )
    return evidence[
        [
            "asset_id",
            "candidate_trade_date",
            "as_of_date",
            "as_of_safe",
            "report_period",
            "publish_date",
            "source_document_id",
            "source_document_url",
        ]
    ].reset_index(drop=True)


def _alignment_status(*, candidate_evidence: pd.DataFrame, safe_evidence: pd.DataFrame) -> str:
    if not safe_evidence.empty:
        return "pit_safe_product_evidence_available"
    if not candidate_evidence.empty:
        return "joinable_but_future_disclosure"
    return "no_official_manifest_or_product_rows"


def _best_evidence_row(evidence: pd.DataFrame) -> dict[str, Any]:
    if evidence.empty:
        return {}
    sortable = evidence.copy()
    sortable["_publish_sort"] = pd.to_datetime(sortable["publish_date"], errors="coerce")
    sortable["_report_sort"] = pd.to_datetime(sortable["report_period"], errors="coerce")
    sortable = sortable.sort_values(["_publish_sort", "_report_sort"], ascending=[False, False], kind="stable")
    return sortable.iloc[0].to_dict()


def _min_future_publish_date(*, candidate_evidence: pd.DataFrame, as_of_date: dt.date) -> dt.date | None:
    if candidate_evidence.empty:
        return None
    future_dates = [
        publish_date
        for publish_date in candidate_evidence["publish_date"].tolist()
        if isinstance(publish_date, dt.date) and publish_date > as_of_date
    ]
    return min(future_dates) if future_dates else None


def _metadata_dict(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    text = _safe_text(value)
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _first_date_value(*values: object) -> dt.date | None:
    for value in values:
        parsed = _date_value(value)
        if parsed is not None:
            return parsed
    return None


def _date_value(value: object) -> dt.date | None:
    if value is None or value is pd.NA:
        return None
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    if pd.isna(value):
        return None
    timestamp = pd.to_datetime(value, errors="coerce")
    if pd.isna(timestamp):
        return None
    return timestamp.date()


def _derive_ts_code(asset_id: object) -> str:
    text = _safe_text(asset_id)
    parts = text.split(":")
    if len(parts) == 3 and parts[0].upper() == "CN":
        return f"{parts[2]}.{parts[1].upper()}"
    return ""


def _safe_text(value: object) -> str:
    if value is None or value is pd.NA:
        return ""
    if pd.isna(value):
        return ""
    return str(value).strip()


def _bool_value(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if value is None or value is pd.NA:
        return False
    if isinstance(value, (int, float)) and not pd.isna(value):
        return bool(value)
    text = _safe_text(value).lower()
    return text in {"1", "true", "t", "yes", "y"}
