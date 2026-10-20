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
