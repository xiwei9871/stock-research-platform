from __future__ import annotations

import pandas as pd
import pytest

from stock_research.research_infra.research_signals import (
    ResearchSignalValidationError,
    ResearchSignalRecord,
    build_research_signal_records_from_frame,
    export_research_signal_records,
)


def test_research_signal_record_is_jsonable_and_preserves_missingness() -> None:
    record = ResearchSignalRecord(
        asset_id="asset:000001.SZ",
        ts_code="000001.SZ",
        trade_date="2026-06-06",
        signal_name="research_support_score",
        signal_value=None,
        signal_type="numeric",
        source_type="stock_report",
        source_id="stock_report:000001.SZ:2026-06-01",
        availability_timestamp="2026-06-05T15:00:00",
        confidence="thin",
        missingness_reason="no_fresh_report",
    )

    payload = record.to_dict()
    assert payload["signal_name"] == "research_support_score"
    assert payload["signal_value"] is None
    assert payload["missingness_reason"] == "no_fresh_report"


def test_research_signal_rejects_future_availability_timestamp() -> None:
    with pytest.raises(ResearchSignalValidationError) as exc:
        ResearchSignalRecord(
            asset_id="asset:000001.SZ",
            ts_code="000001.SZ",
            trade_date="2026-06-06",
            signal_name="public_news_sentiment_score",
            signal_value=0.8,
            signal_type="numeric",
            source_type="public_news",
            source_id="news:late-item",
            availability_timestamp="2026-06-07T09:00:00",
            confidence="medium",
            missingness_reason="",
        )

    assert "availability_timestamp" in str(exc.value)
    assert "trade_date" in str(exc.value)


def test_research_signal_allows_post_close_review_when_explicit() -> None:
    record = ResearchSignalRecord(
        asset_id="asset:000001.SZ",
        ts_code="000001.SZ",
        trade_date="2026-06-06",
        signal_name="manual_review_label",
        signal_value="follow_up",
        signal_type="text",
        source_type="manual_review",
        source_id="review:2026-06-06:post-close",
        availability_timestamp="2026-06-06T20:00:00",
        confidence="medium",
        missingness_reason="",
        post_close_review=True,
    )

    assert record.post_close_review is True


def test_build_research_signal_records_from_frame_handles_missing_values() -> None:
    frame = pd.DataFrame(
        [
            {
                "asset_id": "asset:000001.SZ",
                "ts_code": "000001.SZ",
                "trade_date": "2026-06-06",
                "research_support_score": 0.72,
                "coverage_freshness_score": None,
                "source_id": "stock_report:000001.SZ:2026-06-01",
                "availability_timestamp": "2026-06-05T15:00:00",
            }
        ]
    )

    records = build_research_signal_records_from_frame(
        frame,
        signal_columns=["research_support_score", "coverage_freshness_score"],
        source_type="stock_report",
        default_confidence="medium",
        missingness_reason="no_fresh_report",
    )

    by_name = {record.signal_name: record for record in records}
    assert by_name["research_support_score"].signal_value == 0.72
    assert by_name["research_support_score"].missingness_reason == ""
    assert by_name["coverage_freshness_score"].signal_value is None
    assert by_name["coverage_freshness_score"].missingness_reason == "no_fresh_report"


def test_export_research_signal_records_returns_jsonable_rows() -> None:
    record = ResearchSignalRecord(
        asset_id="asset:000001.SZ",
        ts_code="000001.SZ",
        trade_date="2026-06-06",
        signal_name="public_news_sentiment_score",
        signal_value=-0.2,
        signal_type="numeric",
        source_type="public_news",
        source_id="news:2026-06-06:1",
        availability_timestamp="2026-06-06T10:00:00",
        confidence="medium",
        missingness_reason="",
    )

    assert export_research_signal_records([record]) == [record.to_dict()]
