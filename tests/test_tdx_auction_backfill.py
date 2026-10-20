from types import SimpleNamespace

import pytest

from stock_research.tdx_auction_backfill import (
    build_tdx_market_row,
    fetch_tdx_opening_matches,
    load_tdx_auction_exclusion_count,
    load_tdx_auction_universe,
    ts_code_to_tdx_code,
    tdx_date_result_is_fatal,
    tdx_trade_to_values,
)


@pytest.mark.parametrize(
    ("ts_code", "expected"),
    [
        ("000001.SZ", "sz000001"),
        ("600000.SH", "sh600000"),
        ("830799.BJ", "bj830799"),
        ("430047.BSE", "bj430047"),
    ],
)
def test_ts_code_to_tdx_code_maps_supported_exchanges(ts_code, expected):
    assert ts_code_to_tdx_code(ts_code) == expected


def test_tdx_trade_to_values_preserves_hand_volume_and_derives_amount():
    tick = SimpleNamespace(
        time_label="09:25",
        price=11.96,
        volume=2283,
        order_count=82,
        event_kind="opening_match",
        record_hex="0x0fc6",
    )

    values = tdx_trade_to_values(tick)

    assert values["price"] == 11.96
    assert values["volume"] == 2283
    assert values["amount"] == pytest.approx(11.96 * 2283 * 100)
    assert values["order_count"] == 82
    assert values["event_kind"] == "opening_match"


def test_build_tdx_market_row_maps_formal_match_to_open_call():
    tick = SimpleNamespace(
        time_label="09:25",
        price=11.96,
        volume=2283,
        order_count=82,
        event_kind="opening_match",
        record_hex="0x0fc6",
    )

    row = build_tdx_market_row(
        asset={"asset_id": "asset-000001", "ts_code": "000001.SZ"},
        trade_date="2018-02-14",
        tick=tick,
    )

    assert row["auction_phase"] == "open_call"
    assert row["source"] == "tdx"
    assert row["volume_unit"] == "hand"
    assert row["open"] == row["close"] == 11.96
    assert row["volume"] == 2283
    assert row["order_count"] == 82


def test_fetch_tdx_opening_matches_classifies_missing_and_errors():
    class FakeTrades:
        def opening_match_history(self, code, trading_date, **kwargs):
            if code == "sz000001":
                return SimpleNamespace(price=11.96, volume=2283, order_count=82)
            if code == "sh600000":
                return None
            raise RuntimeError("server unavailable")

    client = SimpleNamespace(trades=FakeTrades())
    results = fetch_tdx_opening_matches(
        client,
        ["000001.SZ", "600000.SH", "300001.SZ"],
        "2018-02-14",
        workers=1,
        retry_attempts=0,
    )

    by_code = {result.ts_code: result for result in results}
    assert by_code["000001.SZ"].tick is not None
    assert by_code["600000.SH"].tick is None
    assert by_code["600000.SH"].error is None
    assert "server unavailable" in (by_code["300001.SZ"].error or "")


def test_fetch_tdx_opening_matches_does_not_retry_deterministic_bad_payload():
    calls = []

    class FakeTrades:
        def opening_match_history(self, code, trading_date, **kwargs):
            calls.append(code)
            raise RuntimeError("ProtocolError: invalid historical ticks payload")

    client = SimpleNamespace(trades=FakeTrades())
    results = fetch_tdx_opening_matches(
        client,
        ["000004.SZ"],
        "2018-03-01",
        workers=1,
        retry_attempts=2,
        retry_sleep_seconds=0,
    )

    assert calls == ["sz000004"]
    assert results[0].error_kind == "unsupported_payload"
    assert results[0].error is not None


def test_load_tdx_auction_universe_uses_active_symbols_with_positive_raw_daily_volume(monkeypatch):
    calls = []

    def fake_fetch_all(_conn, sql, params=None):
        calls.append((sql, params))
        return [{"asset_id": "asset-000001", "ts_code": "000001.SZ"}]

    monkeypatch.setattr("stock_research.tdx_auction_backfill.fetch_all", fake_fetch_all)

    rows = load_tdx_auction_universe(object(), "2018-03-01")

    assert rows == [{"asset_id": "asset-000001", "ts_code": "000001.SZ"}]
    assert len(calls) == 1
    sql, params = calls[0]
    normalized = " ".join(sql.lower().split())
    assert "join market_daily_bar as d on" in normalized
    assert "d.adjust_type = 'raw'" in normalized
    assert "d.volume > 0" in normalized
    assert "a.is_active is true" in normalized
    assert params == ["2018-03-01", "2018-03-01", "2018-03-01"]


def test_load_tdx_auction_exclusion_count_tracks_currently_inactive_symbols(monkeypatch):
    calls = []

    def fake_fetch_all(_conn, sql, params=None):
        calls.append((sql, params))
        return [{"count": 11}]

    monkeypatch.setattr("stock_research.tdx_auction_backfill.fetch_all", fake_fetch_all)

    count = load_tdx_auction_exclusion_count(object(), "2018-03-01")

    assert count == 11
    normalized = " ".join(calls[0][0].lower().split())
    assert "a.is_active is not true" in normalized
    assert calls[0][1] == ["2018-03-01", "2018-03-01"]


def test_partial_symbol_errors_do_not_block_a_date_with_matches():
    assert tdx_date_result_is_fatal({"matched_rows": 12, "failed_codes": 3}) is False
    assert tdx_date_result_is_fatal({"matched_rows": 0, "failed_codes": 3}) is True
    assert tdx_date_result_is_fatal({"matched_rows": 0, "failed_codes": 0}) is False


def test_tdx_date_coverage_and_task_outcome_separate_execution_from_completeness():
    from stock_research.tdx_auction_backfill import (
        tdx_date_coverage,
        tdx_date_result_is_complete,
        tdx_task_outcome,
    )

    # request succeeded but data incomplete → partial, not success
    partial = {"matched_rows": 3100, "requested_codes": 5181, "failed_codes": 0}
    assert tdx_date_coverage(partial) == pytest.approx(3100 / 5181, abs=1e-4)
    assert tdx_date_result_is_complete(partial) is False
    assert tdx_task_outcome(partial) == "partial"

    # healthy day: ~1% normal no-match (suspensions) still meets 98%
    ok = {"matched_rows": 5141, "requested_codes": 5181, "failed_codes": 0}
    assert tdx_task_outcome(ok) == "success"

    # all-request-error day stays fatal regardless of coverage math
    assert tdx_task_outcome(
        {"matched_rows": 0, "requested_codes": 100, "failed_codes": 5}
    ) == "fatal"

    # boundary: exactly 98% passes, just below fails
    assert tdx_task_outcome({"matched_rows": 98, "requested_codes": 100}) == "success"
    assert tdx_task_outcome({"matched_rows": 97, "requested_codes": 100}) == "partial"

    # threshold is configurable
    assert tdx_task_outcome(
        {"matched_rows": 900, "requested_codes": 1000},
        min_coverage_ratio=0.85,
    ) == "success"


def test_run_once_marks_low_coverage_retriable_not_success(monkeypatch):
    from stock_research import tdx_auction_watchdog as w

    claimed = [
        {"task_id": "t1", "start_date": "2026-10-20", "partition_key": "2026-10-20"},
    ]
    monkeypatch.setattr(w, "claim_backfill_tasks_for_service", lambda **kw: claimed)
    monkeypatch.setattr(
        w, "backfill_tdx_auction_date",
        lambda *a, **kw: {
            "trade_date": "2026-10-20", "requested_codes": 5181,
            "matched_rows": 3100, "rows_written": 3100,
            "missing_codes": 2081, "failed_codes": 0,
            "unsupported_codes": 0, "excluded_codes": 0,
        },
    )
    marks = {"success": [], "failed": []}
    monkeypatch.setattr(
        w, "mark_backfill_task_success_for_service",
        lambda **kw: marks["success"].append(kw),
    )
    monkeypatch.setattr(
        w, "mark_backfill_task_failed_for_service",
        lambda **kw: marks["failed"].append(kw),
    )
    monkeypatch.setattr(
        w.TdxAuctionBackfillAdapter, "_record_task_metrics",
        lambda self, **kw: None,
    )

    adapter = w.TdxAuctionBackfillAdapter(start_date="2026-10-20", end_date="2026-10-20")
    result = adapter.run_once(
        scope={"run_id": "r1"}, max_jobs=1, workers=1, run_timeout_seconds=3600,
    )

    # partial coverage → retriable failure, NEVER success
    assert marks["success"] == []
    assert len(marks["failed"]) == 1
    assert "coverage" in marks["failed"][0]["error_message"]
    assert "3100" in marks["failed"][0]["error_message"]
    assert result["success"] == 0
    assert result["partial"] == 1


def test_run_once_marks_healthy_coverage_success(monkeypatch):
    from stock_research import tdx_auction_watchdog as w

    monkeypatch.setattr(
        w, "claim_backfill_tasks_for_service",
        lambda **kw: [{"task_id": "t1", "start_date": "2026-10-19",
                       "partition_key": "2026-10-19"}],
    )
    monkeypatch.setattr(
        w, "backfill_tdx_auction_date",
        lambda *a, **kw: {
            "trade_date": "2026-10-19", "requested_codes": 5177,
            "matched_rows": 5136, "rows_written": 5136,
            "missing_codes": 41, "failed_codes": 0,
            "unsupported_codes": 0, "excluded_codes": 0,
        },
    )
    marks = {"success": [], "failed": []}
    monkeypatch.setattr(
        w, "mark_backfill_task_success_for_service",
        lambda **kw: marks["success"].append(kw),
    )
    monkeypatch.setattr(
        w, "mark_backfill_task_failed_for_service",
        lambda **kw: marks["failed"].append(kw),
    )
    monkeypatch.setattr(
        w.TdxAuctionBackfillAdapter, "_record_task_metrics",
        lambda self, **kw: None,
    )

    adapter = w.TdxAuctionBackfillAdapter(start_date="2026-10-19", end_date="2026-10-19")
    result = adapter.run_once(
        scope={"run_id": "r1"}, max_jobs=1, workers=1, run_timeout_seconds=3600,
    )

    assert len(marks["success"]) == 1
    assert marks["success"][0]["rows_written"] == 5136
    assert marks["failed"] == []
    assert result["success"] == 1
    assert result["partial"] == 0


def test_frontier_does_not_advance_past_incomplete_date():
    from stock_research.tdx_auction_watchdog import TdxAuctionBackfillAdapter

    adapter = TdxAuctionBackfillAdapter(start_date="2026-09-08", end_date="2026-10-20")
    frontier = adapter.compute_frontier([
        {"trade_date": "2026-10-16", "status": "success"},
        {"trade_date": "2026-10-19", "status": "success"},
        {"trade_date": "2026-10-20", "status": "failed"},  # partial, retryable
    ])
    assert frontier["completed_through"] == "2026-10-19"
    assert frontier["currently_working_on"] == "2026-10-20"


def test_run_once_fatal_still_marks_failed_with_symbol_detail(monkeypatch):
    from stock_research import tdx_auction_watchdog as w

    monkeypatch.setattr(
        w, "claim_backfill_tasks_for_service",
        lambda **kw: [{"task_id": "t1", "start_date": "2026-10-20",
                       "partition_key": "2026-10-20"}],
    )
    monkeypatch.setattr(
        w, "backfill_tdx_auction_date",
        lambda *a, **kw: {
            "trade_date": "2026-10-20", "requested_codes": 5181,
            "matched_rows": 0, "rows_written": 0, "missing_codes": 0,
            "failed_codes": 50, "unsupported_codes": 0, "excluded_codes": 0,
            "failed_examples": [{"ts_code": "000001.SZ", "error": "timeout"}],
        },
    )
    marks = {"success": [], "failed": []}
    monkeypatch.setattr(
        w, "mark_backfill_task_success_for_service",
        lambda **kw: marks["success"].append(kw),
    )
    monkeypatch.setattr(
        w, "mark_backfill_task_failed_for_service",
        lambda **kw: marks["failed"].append(kw),
    )
    monkeypatch.setattr(
        w.TdxAuctionBackfillAdapter, "_record_task_metrics",
        lambda self, **kw: None,
    )

    adapter = w.TdxAuctionBackfillAdapter(start_date="2026-10-20", end_date="2026-10-20")
    result = adapter.run_once(
        scope={"run_id": "r1"}, max_jobs=1, workers=1, run_timeout_seconds=3600,
    )

    assert marks["success"] == []
    assert len(marks["failed"]) == 1
    assert result["failed"] == 1
