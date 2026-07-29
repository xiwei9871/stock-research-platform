from __future__ import annotations

from datetime import date
import ipaddress
import math
from numbers import Real
from urllib.parse import urlparse

import numpy as np
import pandas as pd


EVIDENCE_COLUMNS = [
    "asset_id",
    "stock_code",
    "evidence_as_of_date",
    "repair_bucket",
    "repair_thesis",
    "leading_indicator",
    "unrepaired_metrics",
    "expected_validation_date",
    "main_risks",
    "invalidation_conditions",
    "source_title",
    "source_url",
    "source_publish_date",
    "forecast_revision_state",
    "audit_review_status",
    "pledge_debt_review_status",
    "permanent_impairment_status",
    "catalyst_verifiability_score",
    "expected_improvement_score",
    "operator_notes",
]
DERIVED_COLUMNS = [
    "evidence_complete",
    "evidence_errors",
    "hard_risk_manual_trigger",
    "hard_risk_review_unknown",
]
OUTPUT_COLUMNS = EVIDENCE_COLUMNS + DERIVED_COLUMNS

_REPAIR_BUCKETS = {"expected_repair", "early_validation"}
_RISK_STATUSES = {"clear", "triggered", "unknown"}
_RISK_FIELDS = (
    "audit_review_status",
    "pledge_debt_review_status",
    "permanent_impairment_status",
)
_SCORE_FIELDS = ("catalyst_verifiability_score", "expected_improvement_score")
_FORECAST_STATES = {
    "unknown",
    "not_available",
    "improving",
    "stable",
    "deteriorating",
    "broadly_priced",
}
_REQUIRED_TEXT_ERRORS = {
    "repair_thesis": "missing_repair_thesis",
    "leading_indicator": "missing_leading_indicator",
    "unrepaired_metrics": "missing_unrepaired_metrics",
    "main_risks": "missing_main_risks",
    "invalidation_conditions": "missing_invalidation_conditions",
    "source_title": "missing_source_title",
    "source_url": "missing_source_url",
}


def _text(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def _strict_iso_date(value: str, *, field: str, asset_id: str | None = None) -> date:
    try:
        parsed = date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        context = f" for asset {asset_id}" if asset_id is not None else ""
        raise ValueError(f"{field} must be a real strict ISO date{context}: {value!r}") from exc
    if parsed.isoformat() != value:
        context = f" for asset {asset_id}" if asset_id is not None else ""
        raise ValueError(f"{field} must be a real strict ISO date{context}: {value!r}")
    return parsed


def _stock_code(value: object, *, asset_id: str) -> str:
    if pd.isna(value) or isinstance(value, (bool, np.bool_)):
        raise ValueError(f"invalid stock_code for asset {asset_id}: {value!r}")
    if isinstance(value, Real):
        numeric = float(value)
        if not math.isfinite(numeric) or numeric < 0 or not numeric.is_integer():
            raise ValueError(f"invalid stock_code for asset {asset_id}: {value!r}")
        normalized = str(int(numeric))
    else:
        normalized = _text(value)
    if not normalized or not normalized.isdigit() or len(normalized) > 6:
        raise ValueError(f"invalid stock_code for asset {asset_id}: {value!r}")
    return normalized.zfill(6)


def _validated_score(value: object, *, field: str, asset_id: str) -> float | None:
    if pd.isna(value):
        return None
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
        raise ValueError(f"invalid {field} for asset {asset_id}: {value!r}")
    numeric = float(value)
    if not math.isfinite(numeric) or not 0 <= numeric <= 100:
        raise ValueError(f"invalid {field} for asset {asset_id}: {value!r}")
    return numeric


def _normalize_score_dtypes(frame: pd.DataFrame) -> None:
    for field in _SCORE_FIELDS:
        frame[field] = pd.to_numeric(frame[field], errors="coerce").astype("Float64")


def _valid_source_url(value: str) -> bool:
    try:
        parsed = urlparse(value)
        hostname = parsed.hostname
        parsed.port
    except ValueError:
        return False
    if (
        parsed.scheme not in {"http", "https"}
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        return False

    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        try:
            ascii_hostname = hostname.encode("idna").decode("ascii")
        except UnicodeError:
            return False
        if len(ascii_hostname) > 253 or "." not in ascii_hostname:
            return False
        labels = ascii_hostname.split(".")
        for label in labels:
            valid_characters = all(
                character.isascii() and (character.isalnum() or character == "-")
                for character in label
            )
            if (
                not 1 <= len(label) <= 63
                or label.startswith("-")
                or label.endswith("-")
                or not valid_characters
            ):
                return False
    else:
        if (
            not address.is_global
            or address.is_loopback
            or address.is_private
            or address.is_link_local
            or address.is_multicast
            or address.is_reserved
            or address.is_unspecified
        ):
            return False
    return True


def _validate_source_url(value: str, *, asset_id: str) -> None:
    if not _valid_source_url(value):
        raise ValueError(f"invalid source_url for asset {asset_id}: {value!r}")


def validate_repair_evidence(frame: pd.DataFrame, *, trade_date: str) -> pd.DataFrame:
    """Validate and normalize operator-supplied consumer repair evidence."""
    parsed_trade_date = _strict_iso_date(trade_date, field="trade_date")
    missing_columns = [column for column in EVIDENCE_COLUMNS if column not in frame.columns]
    if missing_columns:
        raise ValueError(f"repair evidence missing required columns: {', '.join(missing_columns)}")

    if frame.empty:
        result = frame.loc[:, EVIDENCE_COLUMNS].copy()
        _normalize_score_dtypes(result)
        result["evidence_complete"] = pd.Series(dtype=bool)
        result["evidence_errors"] = pd.Series(dtype=object)
        result["hard_risk_manual_trigger"] = pd.Series(dtype=bool)
        result["hard_risk_review_unknown"] = pd.Series(dtype=bool)
        return result.loc[:, OUTPUT_COLUMNS]

    result = frame.loc[:, EVIDENCE_COLUMNS].copy()
    for column in EVIDENCE_COLUMNS:
        if column not in _SCORE_FIELDS:
            result[column] = result[column].astype(object)
    result["asset_id"] = result["asset_id"].map(_text)
    if result["asset_id"].eq("").any():
        raise ValueError("asset_id must be non-empty")
    duplicate_ids = sorted(result.loc[result["asset_id"].duplicated(keep=False), "asset_id"].unique())
    if duplicate_ids:
        raise ValueError(f"duplicate asset_id: {', '.join(duplicate_ids)}")

    complete_values: list[bool] = []
    error_values: list[str] = []
    trigger_values: list[bool] = []
    unknown_values: list[bool] = []

    for index, row in result.iterrows():
        asset_id = row["asset_id"]
        errors: list[str] = []

        result.at[index, "stock_code"] = _stock_code(row["stock_code"], asset_id=asset_id)

        bucket = _text(row["repair_bucket"])
        if bucket not in _REPAIR_BUCKETS:
            raise ValueError(f"invalid repair_bucket for asset {asset_id}: {row['repair_bucket']!r}")
        result.at[index, "repair_bucket"] = bucket

        for field, error in _REQUIRED_TEXT_ERRORS.items():
            normalized = _text(row[field])
            result.at[index, field] = normalized
            if not normalized:
                errors.append(error)
        source_url = result.at[index, "source_url"]
        if source_url:
            _validate_source_url(source_url, asset_id=asset_id)

        parsed_dates: dict[str, date | None] = {}
        for field, missing_error in (
            ("evidence_as_of_date", "missing_evidence_as_of_date"),
            ("source_publish_date", "missing_source_publish_date"),
            ("expected_validation_date", "missing_expected_validation_date"),
        ):
            normalized = _text(row[field])
            result.at[index, field] = normalized
            if not normalized:
                errors.append(missing_error)
                parsed_dates[field] = None
                continue
            parsed_dates[field] = _strict_iso_date(normalized, field=field, asset_id=asset_id)

        for field in ("evidence_as_of_date", "source_publish_date"):
            parsed = parsed_dates[field]
            if parsed is not None and parsed > parsed_trade_date:
                raise ValueError(f"future {field} for asset {asset_id}: {result.at[index, field]}")
        evidence_date = parsed_dates["evidence_as_of_date"]
        source_date = parsed_dates["source_publish_date"]
        validation_date = parsed_dates["expected_validation_date"]
        if evidence_date is not None and source_date is not None and source_date > evidence_date:
            raise ValueError(
                f"asset {asset_id} source_publish_date cannot follow evidence_as_of_date"
            )
        if evidence_date is not None and validation_date is not None and validation_date < evidence_date:
            raise ValueError(
                f"expected_validation_date cannot precede evidence_as_of_date for asset {asset_id}"
            )

        statuses: list[str] = []
        for field in _RISK_FIELDS:
            normalized = _text(row[field]).lower() or "unknown"
            if normalized not in _RISK_STATUSES:
                raise ValueError(f"invalid {field} for asset {asset_id}: {row[field]!r}")
            result.at[index, field] = normalized
            statuses.append(normalized)

        forecast_state = _text(row["forecast_revision_state"]).lower() or "unknown"
        if forecast_state not in _FORECAST_STATES:
            raise ValueError(
                f"invalid forecast_revision_state for asset {asset_id}: {row['forecast_revision_state']!r}"
            )
        result.at[index, "forecast_revision_state"] = forecast_state

        for field in _SCORE_FIELDS:
            score = _validated_score(row[field], field=field, asset_id=asset_id)
            if score is None:
                errors.append(f"missing_{field}")
            else:
                result.at[index, field] = score

        result.at[index, "operator_notes"] = _text(row["operator_notes"])
        stable_errors = "|".join(sorted(set(errors)))
        complete_values.append(not errors)
        error_values.append(stable_errors)
        trigger_values.append("triggered" in statuses)
        unknown_values.append("unknown" in statuses)

    _normalize_score_dtypes(result)
    result["evidence_complete"] = pd.Series(complete_values, index=result.index, dtype=bool)
    result["evidence_errors"] = error_values
    result["hard_risk_manual_trigger"] = pd.Series(trigger_values, index=result.index, dtype=bool)
    result["hard_risk_review_unknown"] = pd.Series(unknown_values, index=result.index, dtype=bool)
    return result.loc[:, OUTPUT_COLUMNS].sort_values("asset_id", kind="stable").reset_index(drop=True)
