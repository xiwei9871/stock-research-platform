from __future__ import annotations

import pytest

from stock_research.research_infra.evidence_units import (
    EvidenceUnit,
    EvidenceUnitValidationError,
    evidence_unit_from_news_record,
    evidence_unit_from_stock_report_record,
)


def test_evidence_unit_round_trips_to_dict() -> None:
    unit = EvidenceUnit(
        evidence_id="news:000001.SZ:2026-06-08:1",
        source_type="public_news",
        source_id="news:1",
        asset_id="asset:000001.SZ",
        ts_code="000001.SZ",
        available_at="2026-06-08T10:00:00",
        trade_date="2026-06-08",
        title="Public news title",
        summary="Public news summary",
        claims=["company announced a new project"],
        risks=["project revenue is not yet verified"],
        source_path="outputs/news/000001.SZ.json",
        confidence=0.6,
        metadata={"provider": "public_news"},
    )

    payload = unit.to_dict()
    restored = EvidenceUnit.from_dict(payload)

    assert payload["evidence_id"] == "news:000001.SZ:2026-06-08:1"
    assert payload["claims"] == ["company announced a new project"]
    assert restored == unit


def test_evidence_unit_rejects_unsupported_source_type() -> None:
    with pytest.raises(EvidenceUnitValidationError) as exc:
        EvidenceUnit(
            evidence_id="unsupported:1",
            source_type="blog",
            source_id="blog:1",
            asset_id="asset:000001.SZ",
            ts_code="000001.SZ",
            available_at="2026-06-08T10:00:00",
            trade_date="2026-06-08",
            title="Unsupported source",
            summary="Unsupported source summary",
            claims=[],
            risks=[],
            source_path="outputs/blog/1.json",
            confidence=0.3,
            metadata={},
        )

    assert "source_type" in str(exc.value)


def test_evidence_unit_rejects_future_availability_without_post_close_review() -> None:
    with pytest.raises(EvidenceUnitValidationError) as exc:
        EvidenceUnit(
            evidence_id="news:future",
            source_type="public_news",
            source_id="news:future",
            asset_id="asset:000001.SZ",
            ts_code="000001.SZ",
            available_at="2026-06-09T09:00:00",
            trade_date="2026-06-08",
            title="Future news",
            summary="Future news summary",
            claims=[],
            risks=[],
            source_path="outputs/news/future.json",
            confidence=0.5,
            metadata={},
        )

    assert "available_at" in str(exc.value)
    assert "trade_date" in str(exc.value)


def test_evidence_unit_allows_future_availability_for_post_close_review() -> None:
    unit = EvidenceUnit(
        evidence_id="review:post-close",
        source_type="manual_review",
        source_id="review:post-close",
        asset_id="asset:000001.SZ",
        ts_code="000001.SZ",
        available_at="2026-06-09T09:00:00",
        trade_date="2026-06-08",
        title="Post-close review",
        summary="Post-close review summary",
        claims=[],
        risks=[],
        source_path="outputs/review/post_close.json",
        confidence=0.8,
        metadata={"post_close_review": True},
    )

    assert unit.metadata["post_close_review"] is True


def test_evidence_unit_from_news_record_uses_available_timestamp() -> None:
    unit = evidence_unit_from_news_record(
        {
            "ts_code": "000001.SZ",
            "trade_date": "2026-06-08",
            "published_at": "2026-06-08T10:00:00",
            "title": "News title",
            "summary": "News summary",
            "source_path": "outputs/news/000001.SZ.json",
            "source_id": "news:000001.SZ:1",
            "claims": ["new contract signed"],
            "risks": ["contract value missing"],
            "confidence": 0.7,
        }
    )

    assert unit.source_type == "public_news"
    assert unit.available_at == "2026-06-08T10:00:00"
    assert unit.claims == ["new contract signed"]
    assert unit.metadata["missing_fields"] == []


def test_evidence_unit_from_stock_report_record_tracks_missing_optional_fields() -> None:
    unit = evidence_unit_from_stock_report_record(
        {
            "ts_code": "000002.SZ",
            "trade_date": "2026-06-08",
            "report_date": "2026-06-07",
            "source_id": "stock_report:000002.SZ:2026-06-07",
        }
    )

    assert unit.source_type == "stock_report"
    assert unit.available_at == "2026-06-07"
    assert unit.claims == []
    assert unit.risks == []
    assert unit.confidence == 0.0
    assert set(unit.metadata["missing_fields"]) == {"title", "summary", "source_path"}
