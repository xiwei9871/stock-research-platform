from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, time
from typing import Any

import pandas as pd


VALID_SIGNAL_TYPES = {
    "numeric",
    "text",
    "label",
    "boolean",
}

VALID_SOURCE_TYPES = {
    "stock_report",
    "pdf",
    "public_news",
    "fallback_news",
    "announcement",
    "manual_review",
}


class ResearchSignalValidationError(ValueError):
    """Raised when a research signal record violates the signal contract."""


@dataclass(frozen=True)
class ResearchSignalRecord:
    asset_id: str
    ts_code: str
    trade_date: str
    signal_name: str
    signal_value: Any
    signal_type: str
    source_type: str
    source_id: str
    availability_timestamp: str
    confidence: str
    missingness_reason: str
    post_close_review: bool = False

    def __post_init__(self) -> None:
        missing = [
            field_name
            for field_name in [
                "asset_id",
                "ts_code",
                "trade_date",
                "signal_name",
                "signal_type",
                "source_type",
                "source_id",
                "availability_timestamp",
                "confidence",
            ]
            if not str(getattr(self, field_name)).strip()
        ]
        if self.signal_type not in VALID_SIGNAL_TYPES:
            missing.append("signal_type")
        if self.source_type not in VALID_SOURCE_TYPES:
            missing.append("source_type")
        if missing:
            raise ResearchSignalValidationError(
                "invalid research signal fields: " + ", ".join(sorted(set(missing)))
            )
        _validate_availability(
            trade_date=self.trade_date,
            availability_timestamp=self.availability_timestamp,
            post_close_review=self.post_close_review,
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["signal_value"] = _jsonable_signal_value(payload["signal_value"])
        return payload


def build_research_signal_records_from_frame(
    frame: pd.DataFrame,
    *,
    signal_columns: list[str] | tuple[str, ...],
    source_type: str,
    default_confidence: str,
    missingness_reason: str,
    signal_type: str = "numeric",
    post_close_review: bool = False,
) -> list[ResearchSignalRecord]:
    records: list[ResearchSignalRecord] = []
    for _, row in frame.iterrows():
        for column in signal_columns:
            value = row.get(column)
            is_missing = _is_missing_value(value)
            records.append(
                ResearchSignalRecord(
                    asset_id=str(row.get("asset_id", "")),
                    ts_code=str(row.get("ts_code", "")),
                    trade_date=_date_text(row.get("trade_date")),
                    signal_name=str(column),
                    signal_value=None if is_missing else _jsonable_signal_value(value),
                    signal_type=signal_type,
                    source_type=source_type,
                    source_id=str(row.get("source_id", "")),
                    availability_timestamp=str(row.get("availability_timestamp", "")),
                    confidence=str(row.get("confidence", default_confidence)),
                    missingness_reason=str(missingness_reason if is_missing else ""),
                    post_close_review=post_close_review,
                )
            )
    return records


def export_research_signal_records(
    records: list[ResearchSignalRecord] | tuple[ResearchSignalRecord, ...],
) -> list[dict[str, Any]]:
    return [record.to_dict() for record in records]


def _validate_availability(
    *,
    trade_date: str,
    availability_timestamp: str,
    post_close_review: bool,
) -> None:
    trade_day = pd.to_datetime(trade_date, errors="raise").date()
    available_at = pd.to_datetime(
        availability_timestamp,
        errors="raise",
    ).to_pydatetime()
    cutoff = datetime.combine(trade_day, time(15, 0))
    if post_close_review:
        cutoff = datetime.combine(trade_day, time(23, 59, 59))
    if available_at > cutoff:
        raise ResearchSignalValidationError(
            "availability_timestamp must be <= trade_date close "
            "unless post_close_review is true"
        )


def _is_missing_value(value: Any) -> bool:
    return bool(pd.isna(value))


def _jsonable_signal_value(value: Any) -> Any:
    if _is_missing_value(value):
        return None
    if hasattr(value, "item"):
        return value.item()
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def _date_text(value: Any) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)
