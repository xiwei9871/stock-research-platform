from __future__ import annotations

import pytest

from stock_research.adjustment_revision import (
    STATUS_ALREADY_CORRECT,
    STATUS_CONFIRMED_DIRTY,
    STATUS_NEEDS_REVIEW,
    assert_no_raw_rows,
    classify_asset_revision,
    diff_driven_update_rows,
    diff_stored_vs_live,
    earliest_event_date,
)


def test_diff_detects_price_changes():
    out = diff_stored_vs_live(
        {"2026-09-14": 3.71, "2026-09-15": 3.59, "2026-09-16": 3.58},
        {"2026-09-14": 3.59, "2026-09-15": 3.59, "2026-09-16": 3.58},
    )
    assert out["diff_count"] == 1
    assert out["first_diff"] == out["last_diff"] == "2026-09-14"
    assert out["missing_in_live"] == 0


def test_diff_flags_missing_live_rows():
    out = diff_stored_vs_live(
        {"2026-09-14": 3.71, "2026-09-15": 3.59},
        {"2026-09-14": 3.71},
    )
    assert out["missing_in_live"] == 1
    assert out["diff_count"] == 0


def test_classify_confirmed_dirty():
    status = classify_asset_revision(
        qfq_diff={"diff_count": 10, "missing_in_live": 0},
        hfq_diff={"diff_count": 3, "missing_in_live": 0},
        stored_rows=100,
    )
    assert status == STATUS_CONFIRMED_DIRTY


def test_classify_already_correct():
    status = classify_asset_revision(
        qfq_diff={"diff_count": 0, "missing_in_live": 0},
        hfq_diff={"diff_count": 0, "missing_in_live": 0},
        stored_rows=100,
    )
    assert status == STATUS_ALREADY_CORRECT


def test_classify_needs_review_when_diff_ratio_exceeds_threshold():
    status = classify_asset_revision(
        qfq_diff={"diff_count": 60, "missing_in_live": 0},
        hfq_diff={"diff_count": 1, "missing_in_live": 0},
        stored_rows=100,
    )
    assert status == STATUS_NEEDS_REVIEW


def test_classify_needs_review_when_live_missing():
    status = classify_asset_revision(
        qfq_diff={"diff_count": 5, "missing_in_live": 2},
        hfq_diff={"diff_count": 0, "missing_in_live": 0},
        stored_rows=100,
    )
    assert status == STATUS_NEEDS_REVIEW


def test_diff_driven_updates_only_changed_rows():
    stored = [
        {"asset_id": "A", "trade_date": "2026-09-14", "adjust_type": "qfq",
         "open": 3.69, "high": 3.73, "low": 3.69, "close": 3.71, "preclose": 3.7,
         "volume": 100.0, "amount": 10.0, "turnover_rate": 0.5, "pct_chg": 0.2},
        {"asset_id": "A", "trade_date": "2026-09-15", "adjust_type": "qfq",
         "open": 3.59, "high": 3.6, "low": 3.55, "close": 3.59, "preclose": 3.59,
         "volume": 100.0, "amount": 10.0, "turnover_rate": 0.5, "pct_chg": 0.0},
    ]
    live = [
        dict(stored[0], close=3.59000005, open=3.58),  # changed
        dict(stored[1]),  # identical → skipped
        {"asset_id": "A", "trade_date": "2026-09-16", "adjust_type": "qfq",
         "open": 3.58, "high": 3.6, "low": 3.5, "close": 3.58, "preclose": 3.59,
         "volume": 99.0, "amount": 9.9, "turnover_rate": 0.5, "pct_chg": -0.1},
    ]
    updates = diff_driven_update_rows(stored, live)
    assert len(updates) == 2
    assert updates[0]["trade_date"] == "2026-09-14"
    assert updates[1]["trade_date"] == "2026-09-16"


def test_assert_no_raw_rows():
    assert_no_raw_rows([{"adjust_type": "qfq"}, {"adjust_type": "hfq"}])
    with pytest.raises(ValueError):
        assert_no_raw_rows([{"adjust_type": "raw"}])


def test_earliest_event_date():
    events = [
        {"asset_id": "A", "event_date": "2026-09-15"},
        {"asset_id": "A", "event_date": "2026-07-02"},
        {"asset_id": "B", "event_date": "2026-08-01"},
    ]
    assert earliest_event_date(events, "A") == "2026-07-02"
    assert earliest_event_date(events, "C") is None
