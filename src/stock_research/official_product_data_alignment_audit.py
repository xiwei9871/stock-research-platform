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
    "has_pit_safe_product_evidence",
    "safe_product_evidence_count",
    "unsafe_product_evidence_count",
    "best_report_period",
    "best_publish_date",
    "best_disclosure_type",
    "best_source_document_id",
    "best_source_document_url",
    "best_source_title",
    "best_product_main_business_rows",
    "best_manifest_rows",
    "manifest_rows_for_asset",
    "product_main_business_rows_for_asset",
    "joinable_report_periods_for_asset",
    "manifest_query_error_count_for_asset",
    "max_safe_report_period",
    "min_future_publish_date",
    "days_until_first_future_disclosure",
    "recommended_action",
]

ALIGNMENT_STATUS_SUMMARY_COLUMNS = [
    "alignment_status",
    "candidate_rows",
    "recommended_action",
]

RECOMMENDED_ACTION_BY_STATUS = {
    "pit_safe_product_evidence_available": "use_for_readiness",
    "joinable_but_report_period_future": "ignore_future_period",
    "joinable_but_future_disclosure": "shift_test_window_later",
    "manifest_available_no_joinable_product_period": "backfill_historical_product_rows",
    "manifest_available_no_product_rows": "backfill_product_table_source",
    "product_rows_available_no_official_manifest": "extend_or_fix_manifest_source",
    "manifest_query_error": "rerun_manifest_source",
    "no_official_manifest_or_product_rows": "collect_official_product_data",
}

_ALIGNMENT_REASON_BY_STATUS = {
    "pit_safe_product_evidence_available": "candidate row has strict PIT-safe official product evidence",
    "pit_safe_product_diagnostic_available": (
        "join diagnostics contain a safe historical period but no candidate-scoped evidence row exists"
    ),
    "joinable_but_future_disclosure": "official product evidence exists but publish_date is after candidate as_of_date",
    "joinable_but_report_period_future": "joinable official product period is after candidate as_of_date",
    "manifest_available_no_joinable_product_period": "official manifest and product rows exist, but no matching report period joins",
    "manifest_available_no_product_rows": "official manifest rows exist, but product table rows are missing",
    "product_rows_available_no_official_manifest": "product table rows exist without supported official manifest rows",
    "manifest_query_error": "official manifest source query failed for candidate asset",
    "no_official_manifest_or_product_rows": "no official manifest or product evidence rows found for candidate",
}

_DIAGNOSTIC_FUTURE_DISCLOSURE_REASON = (
    "official manifest and product rows join, but publish_date is after candidate as_of_date"
)


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
    del disclosure_manifest

    normalized_candidates = normalize_alignment_candidates(candidates)
    evidence = _normalize_product_evidence(product_evidence)
    diagnostics = _normalize_join_diagnostics(product_join_diagnostics)
    errors = _normalize_manifest_query_errors(manifest_query_errors)
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

        row = {
            "run_id": _safe_text(run_id),
            "asset_id": candidate["asset_id"],
            "ts_code": candidate["ts_code"],
            "stock_name": candidate["stock_name"],
            "candidate_trade_date": candidate["candidate_trade_date"],
            "as_of_date": candidate["as_of_date"],
            "alignment_status": status,
            "alignment_reason": _ALIGNMENT_REASON_BY_STATUS[status],
            "has_pit_safe_product_evidence": bool(not safe_evidence.empty),
            "safe_product_evidence_count": int(len(safe_evidence)),
            "unsafe_product_evidence_count": int(len(unsafe_evidence)),
            "best_report_period": best_evidence.get("report_period"),
            "best_publish_date": best_evidence.get("publish_date"),
            "best_disclosure_type": None,
            "best_source_document_id": best_evidence.get("source_document_id"),
            "best_source_document_url": best_evidence.get("source_document_url"),
            "best_source_title": best_evidence.get("source_title"),
            "best_product_main_business_rows": None,
            "best_manifest_rows": None,
            "manifest_rows_for_asset": 0,
            "product_main_business_rows_for_asset": 0,
            "joinable_report_periods_for_asset": 0,
            "manifest_query_error_count_for_asset": 0,
            "max_safe_report_period": _max_safe_report_period(safe_evidence),
            "min_future_publish_date": min_future_publish_date,
            "days_until_first_future_disclosure": days_until_first_future_disclosure,
            "recommended_action": RECOMMENDED_ACTION_BY_STATUS[status],
        }

        if candidate_evidence.empty:
            candidate_diagnostics = _asset_rows(diagnostics, candidate)
            candidate_errors = _asset_rows(errors, candidate)
            _apply_asset_counts(row, candidate_diagnostics, candidate_errors)
            _classify_from_join_diagnostics(row, candidate_diagnostics)
            if row["alignment_status"] == "no_official_manifest_or_product_rows":
                _classify_from_manifest_query_errors(row, candidate_errors)

        rows.append(row)

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
        "source_title",
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
                "source_title",
                "source_document_id",
                "source_document_url",
            ]
        )

    evidence["asset_id"] = evidence["asset_id"].map(_safe_text)
    source_title_input = evidence["source_title"].map(_safe_text)
    evidence["candidate_trade_date"] = evidence["candidate_trade_date"].map(_date_value)
    evidence["as_of_date"] = evidence["as_of_date"].map(_date_value)
    evidence["as_of_safe"] = evidence["as_of_safe"].map(_bool_value)
    metadata = evidence["metadata_json"].map(_metadata_dict)
    evidence["report_period"] = metadata.map(lambda item: _date_value(item.get("report_period")))
    evidence["publish_date"] = metadata.map(lambda item: _date_value(item.get("publish_date")))
    evidence["source_title"] = metadata.map(lambda item: _safe_text(item.get("source_title")))
    evidence["source_title"] = evidence["source_title"].combine(
        source_title_input,
        lambda metadata_title, title: metadata_title or title,
    )
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
            "source_title",
            "source_document_id",
            "source_document_url",
        ]
    ].reset_index(drop=True)


def _normalize_join_diagnostics(product_join_diagnostics: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "asset_id",
        "ts_code",
        "report_period",
        "publish_date",
        "disclosure_type",
        "source_document_id",
        "source_document_url",
        "announcement_title",
        "product_main_business_rows",
        "manifest_rows",
        "join_status",
    ]
    diagnostics = product_join_diagnostics.copy()
    for column in columns:
        if column not in diagnostics.columns:
            diagnostics[column] = ""
    if diagnostics.empty:
        return pd.DataFrame(columns=columns)

    diagnostics["asset_id"] = diagnostics["asset_id"].map(_safe_text)
    diagnostics["ts_code"] = diagnostics.apply(
        lambda row: _safe_text(row["ts_code"]) or _derive_ts_code(row["asset_id"]),
        axis=1,
    )
    diagnostics["report_period"] = diagnostics["report_period"].map(_date_value)
    diagnostics["publish_date"] = diagnostics["publish_date"].map(_date_value)
    diagnostics["disclosure_type"] = diagnostics["disclosure_type"].map(_safe_text)
    diagnostics["source_document_id"] = diagnostics["source_document_id"].map(_safe_text)
    diagnostics["source_document_url"] = diagnostics["source_document_url"].map(_safe_text)
    diagnostics["announcement_title"] = diagnostics["announcement_title"].map(_safe_text)
    diagnostics["product_main_business_rows"] = diagnostics["product_main_business_rows"].map(_int_value)
    diagnostics["manifest_rows"] = diagnostics["manifest_rows"].map(_int_value)
    diagnostics["join_status"] = diagnostics["join_status"].map(_safe_text)
    return diagnostics[columns].reset_index(drop=True)


def _normalize_manifest_query_errors(manifest_query_errors: pd.DataFrame) -> pd.DataFrame:
    columns = ["asset_id", "ts_code", "error_type", "error_message"]
    errors = manifest_query_errors.copy()
    for column in columns:
        if column not in errors.columns:
            errors[column] = ""
    if errors.empty:
        return pd.DataFrame(columns=columns)

    errors["asset_id"] = errors["asset_id"].map(_safe_text)
    errors["ts_code"] = errors.apply(
        lambda row: _safe_text(row["ts_code"]) or _derive_ts_code(row["asset_id"]),
        axis=1,
    )
    errors["error_type"] = errors["error_type"].map(_safe_text)
    errors["error_message"] = errors["error_message"].map(_safe_text)
    return errors[columns].reset_index(drop=True)


def _asset_rows(frame: pd.DataFrame, candidate: dict[str, Any]) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    if "asset_id" in frame.columns and candidate.get("asset_id"):
        matched = frame[frame["asset_id"].eq(candidate["asset_id"])].copy()
        if not matched.empty:
            return matched
    if "ts_code" in frame.columns and candidate.get("ts_code"):
        return frame[frame["ts_code"].eq(candidate["ts_code"])].copy()
    return frame.iloc[0:0].copy()


def _apply_asset_counts(row: dict[str, Any], diagnostics: pd.DataFrame, errors: pd.DataFrame) -> None:
    row["manifest_rows_for_asset"] = int(diagnostics["manifest_rows"].sum()) if "manifest_rows" in diagnostics else 0
    row["product_main_business_rows_for_asset"] = (
        int(diagnostics["product_main_business_rows"].sum()) if "product_main_business_rows" in diagnostics else 0
    )
    row["joinable_report_periods_for_asset"] = _joinable_report_period_count(diagnostics)
    row["manifest_query_error_count_for_asset"] = int(len(errors))


def _apply_diagnostic_details(row: dict[str, Any], diagnostic_row: pd.Series) -> None:
    row["best_report_period"] = diagnostic_row.get("report_period")
    row["best_publish_date"] = diagnostic_row.get("publish_date")
    row["best_source_document_id"] = diagnostic_row.get("source_document_id")
    row["best_source_document_url"] = diagnostic_row.get("source_document_url")
    row["best_disclosure_type"] = diagnostic_row.get("disclosure_type")
    row["best_source_title"] = diagnostic_row.get("announcement_title")
    row["best_product_main_business_rows"] = diagnostic_row.get("product_main_business_rows")
    row["best_manifest_rows"] = diagnostic_row.get("manifest_rows")


def _classify_from_join_diagnostics(row: dict[str, Any], diagnostics: pd.DataFrame) -> None:
    if diagnostics.empty:
        return

    joinable = diagnostics[diagnostics["join_status"].eq("joinable")].copy()
    if not joinable.empty:
        future_period = joinable[joinable["report_period"].map(lambda value: _date_after(value, row["as_of_date"]))]
        if not future_period.empty:
            _set_alignment_status(row, "joinable_but_report_period_future")
            _apply_diagnostic_details(row, _best_diagnostic_row(future_period))
            return

        future_disclosure = joinable[
            joinable["report_period"].map(lambda value: _date_on_or_before(value, row["as_of_date"]))
            & joinable["publish_date"].map(lambda value: _date_after(value, row["as_of_date"]))
        ]
        if not future_disclosure.empty:
            _set_alignment_status(
                row,
                "joinable_but_future_disclosure",
                reason=_DIAGNOSTIC_FUTURE_DISCLOSURE_REASON,
            )
            diagnostic_row = _best_diagnostic_row(future_disclosure)
            _apply_diagnostic_details(row, diagnostic_row)
            min_future_publish_date = _min_date(future_disclosure["publish_date"].tolist())
            row["min_future_publish_date"] = min_future_publish_date
            row["days_until_first_future_disclosure"] = (
                (min_future_publish_date - row["as_of_date"]).days if min_future_publish_date is not None else None
            )
            return

        safe_historical = joinable[
            joinable["report_period"].map(lambda value: _date_on_or_before(value, row["as_of_date"]))
            & joinable["publish_date"].map(lambda value: _date_on_or_before(value, row["as_of_date"]))
        ]
        if not safe_historical.empty:
            diagnostic_row = _best_diagnostic_row(safe_historical)
            _apply_diagnostic_details(row, diagnostic_row)
            row["max_safe_report_period"] = diagnostic_row.get("report_period")
            _set_alignment_status(
                row,
                "pit_safe_product_evidence_available",
                reason=_ALIGNMENT_REASON_BY_STATUS["pit_safe_product_diagnostic_available"],
            )
            return

    manifest_rows = int(diagnostics["manifest_rows"].sum())
    product_rows = int(diagnostics["product_main_business_rows"].sum())
    if manifest_rows > 0 and product_rows > 0:
        _set_alignment_status(row, "manifest_available_no_joinable_product_period")
        _apply_diagnostic_details(row, _best_diagnostic_row(diagnostics))
        return
    if manifest_rows > 0:
        _set_alignment_status(row, "manifest_available_no_product_rows")
        _apply_diagnostic_details(row, _best_diagnostic_row(diagnostics))
        return
    if product_rows > 0:
        _set_alignment_status(row, "product_rows_available_no_official_manifest")
        _apply_diagnostic_details(row, _best_diagnostic_row(diagnostics))


def _classify_from_manifest_query_errors(row: dict[str, Any], errors: pd.DataFrame) -> None:
    if not errors.empty:
        _set_alignment_status(row, "manifest_query_error")


def _set_alignment_status(row: dict[str, Any], status: str, *, reason: str | None = None) -> None:
    row["alignment_status"] = status
    row["alignment_reason"] = reason or _ALIGNMENT_REASON_BY_STATUS[status]
    row["recommended_action"] = RECOMMENDED_ACTION_BY_STATUS[status]


def _best_diagnostic_row(diagnostics: pd.DataFrame) -> pd.Series:
    sortable = diagnostics.copy()
    sortable["_publish_sort"] = pd.to_datetime(sortable["publish_date"], errors="coerce")
    sortable["_report_sort"] = pd.to_datetime(sortable["report_period"], errors="coerce")
    sortable = sortable.sort_values(["_publish_sort", "_report_sort"], ascending=[False, False], kind="stable")
    return sortable.iloc[0]


def _joinable_report_period_count(diagnostics: pd.DataFrame) -> int:
    if diagnostics.empty:
        return 0
    joinable = diagnostics[diagnostics["join_status"].eq("joinable")]
    return int(joinable["report_period"].dropna().nunique())


def _date_after(value: object, reference: dt.date) -> bool:
    return isinstance(value, dt.date) and value > reference


def _date_on_or_before(value: object, reference: dt.date) -> bool:
    return isinstance(value, dt.date) and value <= reference


def _min_date(values: list[object]) -> dt.date | None:
    dates = [value for value in values if isinstance(value, dt.date)]
    return min(dates) if dates else None


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


def _max_safe_report_period(safe_evidence: pd.DataFrame) -> dt.date | None:
    if safe_evidence.empty:
        return None
    safe_periods = [value for value in safe_evidence["report_period"].tolist() if isinstance(value, dt.date)]
    return max(safe_periods) if safe_periods else None


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


def _int_value(value: object) -> int:
    if value is None or value is pd.NA:
        return 0
    number = pd.to_numeric(value, errors="coerce")
    if pd.isna(number):
        return 0
    return int(number)
