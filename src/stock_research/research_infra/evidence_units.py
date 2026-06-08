from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Any


VALID_EVIDENCE_SOURCE_TYPES = {
    "stock_report",
    "pdf",
    "public_news",
    "announcement",
    "macro_series",
    "external_paper",
    "manual_review",
}


class EvidenceUnitValidationError(ValueError):
    """Raised when an evidence unit violates the local evidence contract."""


@dataclass(frozen=True)
class EvidenceUnit:
    evidence_id: str
    source_type: str
    source_id: str
    asset_id: str
    ts_code: str
    available_at: str
    trade_date: str
    title: str
    summary: str
    claims: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    source_path: str = ""
    confidence: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        missing = [
            field_name
            for field_name in ["evidence_id", "source_type", "available_at"]
            if not str(getattr(self, field_name)).strip()
        ]
        if self.source_type not in VALID_EVIDENCE_SOURCE_TYPES:
            missing.append("source_type")
        if missing:
            raise EvidenceUnitValidationError(
                "invalid evidence unit fields: " + ", ".join(sorted(set(missing)))
            )
        _validate_available_at(
            available_at=self.available_at,
            trade_date=self.trade_date,
            post_close_review=bool(self.metadata.get("post_close_review")),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> EvidenceUnit:
        return cls(
            evidence_id=str(payload.get("evidence_id", "")),
            source_type=str(payload.get("source_type", "")),
            source_id=str(payload.get("source_id", "")),
            asset_id=str(payload.get("asset_id", "")),
            ts_code=str(payload.get("ts_code", "")),
            available_at=str(payload.get("available_at", "")),
            trade_date=str(payload.get("trade_date", "")),
            title=str(payload.get("title", "")),
            summary=str(payload.get("summary", "")),
            claims=_string_list(payload.get("claims", [])),
            risks=_string_list(payload.get("risks", [])),
            source_path=str(payload.get("source_path", "")),
            confidence=float(payload.get("confidence", 0.0)),
            metadata=dict(payload.get("metadata", {})),
        )


def evidence_unit_from_news_record(record: dict[str, object]) -> EvidenceUnit:
    ts_code = _text(record.get("ts_code"))
    trade_date = _text(record.get("trade_date"))
    available_at = _text(record.get("published_at") or record.get("available_at"))
    source_id = _text(record.get("source_id")) or f"public_news:{ts_code}:{available_at}"
    missing_fields = _missing_optional_fields(record, ["title", "summary", "source_path"])
    return EvidenceUnit(
        evidence_id=source_id,
        source_type="public_news",
        source_id=source_id,
        asset_id=_text(record.get("asset_id")) or f"asset:{ts_code}",
        ts_code=ts_code,
        available_at=available_at,
        trade_date=trade_date,
        title=_text(record.get("title")),
        summary=_text(record.get("summary")),
        claims=_string_list(record.get("claims", [])),
        risks=_string_list(record.get("risks", [])),
        source_path=_text(record.get("source_path")),
        confidence=float(record.get("confidence", 0.0) or 0.0),
        metadata={"missing_fields": missing_fields, "source_converter": "news_record"},
    )


def evidence_unit_from_stock_report_record(record: dict[str, object]) -> EvidenceUnit:
    ts_code = _text(record.get("ts_code"))
    trade_date = _text(record.get("trade_date"))
    available_at = _text(record.get("available_at") or record.get("report_date"))
    source_id = _text(record.get("source_id")) or f"stock_report:{ts_code}:{available_at}"
    missing_fields = _missing_optional_fields(record, ["title", "summary", "source_path"])
    return EvidenceUnit(
        evidence_id=source_id,
        source_type="stock_report",
        source_id=source_id,
        asset_id=_text(record.get("asset_id")) or f"asset:{ts_code}",
        ts_code=ts_code,
        available_at=available_at,
        trade_date=trade_date,
        title=_text(record.get("title")),
        summary=_text(record.get("summary")),
        claims=_string_list(record.get("claims", [])),
        risks=_string_list(record.get("risks", [])),
        source_path=_text(record.get("source_path")),
        confidence=float(record.get("confidence", 0.0) or 0.0),
        metadata={"missing_fields": missing_fields, "source_converter": "stock_report_record"},
    )


def _validate_available_at(
    *,
    available_at: str,
    trade_date: str,
    post_close_review: bool,
) -> None:
    available_day = _parse_date_like(available_at)
    trade_day = _parse_date_like(trade_date)
    if available_day > trade_day and not post_close_review:
        raise EvidenceUnitValidationError(
            "available_at must be <= trade_date unless metadata.post_close_review is true"
        )


def _parse_date_like(value: str) -> date:
    text = str(value).strip()
    if not text:
        raise EvidenceUnitValidationError("date values must not be empty")
    normalized = text.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized).date()
    except ValueError:
        return date.fromisoformat(text)


def _missing_optional_fields(record: dict[str, object], fields: list[str]) -> list[str]:
    return [field_name for field_name in fields if not _text(record.get(field_name))]


def _string_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value]
    return [str(value)]


def _text(value: object) -> str:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return "" if value is None else str(value)
