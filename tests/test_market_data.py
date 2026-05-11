import pytest

from stock_research import market_data
from stock_research.market_data import (
    latest_source_trade_date,
    load_market_daily_bars,
    normalize_source_row,
    raw_daily_bar_payload_row,
    raw_payload_hash,
    upsert_raw_daily_bar_payloads,
)


class _Context:
    def __init__(self, value):
        self.value = value

    def __enter__(self):
        return self.value

    def __exit__(self, exc_type, exc, tb):
        return False


def source_row() -> dict:
    return {
        "trade_date": "2026-05-06",
        "stock_code": "sh600000",
        "open_price": "10.10",
        "high_price": "10.50",
        "low_price": "10.00",
        "close_price": "10.30",
        "preclose_price": "10.00",
        "volume": "1000",
        "amount": "10300",
        "adjustflag": "1",
        "turnover": "0.5",
        "tradestatus": "1",
        "pctChg": "3.0",
        "isST": "0",
    }


def test_normalize_source_row_maps_real_source_fields():
    row = {
        "trade_date": "2026-05-06",
        "stock_code": "sh600000",
        "open_price": "10.10",
        "high_price": "10.50",
        "low_price": "10.00",
        "close_price": "10.30",
        "preclose_price": "10.00",
        "volume": "1000",
        "amount": "10300",
        "adjustflag": "1",
        "turnover": "0.5",
        "tradestatus": "1",
        "pctChg": "3.0",
        "isST": "0",
    }

    normalized = normalize_source_row(row, adjust_type="hfq")

    assert normalized["asset_id"] == "CN:SH:600000"
    assert normalized["trade_date"] == "2026-05-06"
    assert normalized["close"] == 10.30
    assert normalized["turnover_rate"] == 0.5
    assert normalized["is_st"] is False
    assert normalized["adjust_type"] == "hfq"


def test_latest_source_trade_date_rejects_invalid_table_name():
    with pytest.raises(ValueError, match="Invalid stock table name"):
        latest_source_trade_date("stock_hfq", table_name="stock_hfq.sh600000")


def test_raw_payload_hash_is_stable_for_key_order():
    assert raw_payload_hash({"b": "2", "a": "1"}) == raw_payload_hash({"a": "1", "b": "2"})


def test_raw_daily_bar_payload_row_preserves_source_payload():
    row = {"trade_date": "2026-05-06", "stock_code": "sh600000", "close_price": "10.30"}

    payload = raw_daily_bar_payload_row("stock_hfq", "sh600000", "hfq", row)

    assert payload["source_service"] == "stock_hfq"
    assert payload["source_table"] == "sh600000"
    assert payload["adjust_type"] == "hfq"
    assert payload["trade_date"] == "2026-05-06"
    assert payload["asset_id"] == "CN:SH:600000"
    assert payload["payload"] == row
    assert len(payload["payload_hash"]) == 64


def test_upsert_raw_daily_bar_payloads_writes_raw_baostock_table(monkeypatch):
    calls = []

    def fake_execute_many(conn, sql, rows):
        calls.append((conn, sql, list(rows)))

    monkeypatch.setattr(market_data, "connect", lambda service: _Context("conn"))
    monkeypatch.setattr(market_data, "execute_many", fake_execute_many, raising=False)

    row = raw_daily_bar_payload_row("stock_hfq", "sh600000", "hfq", source_row())

    assert upsert_raw_daily_bar_payloads([row], research_service="research") == 1
    assert calls
    assert calls[0][0] == "conn"
    assert "INSERT INTO raw_baostock.daily_bar_payload" in calls[0][1]
    assert calls[0][2][0]["source_service"] == "stock_hfq"
    assert calls[0][2][0]["source_table"] == "sh600000"
    assert calls[0][2][0]["payload"] == (
        '{"adjustflag":"1","amount":"10300","close_price":"10.30","high_price":"10.50",'
        '"isST":"0","low_price":"10.00","open_price":"10.10","pctChg":"3.0",'
        '"preclose_price":"10.00","stock_code":"sh600000","trade_date":"2026-05-06",'
        '"tradestatus":"1","turnover":"0.5","volume":"1000"}'
    )


def test_load_market_daily_bars_archives_raw_when_enabled(monkeypatch):
    calls = []

    monkeypatch.setattr(market_data, "discover_source_tables", lambda service: ["sh600000"])
    monkeypatch.setattr(
        market_data,
        "fetch_source_rows",
        lambda service, table_name, start_date, end_date: [source_row()],
    )
    monkeypatch.setattr(
        market_data,
        "upsert_raw_daily_bar_payloads",
        lambda rows: calls.append(("raw", rows)) or len(rows),
        raising=False,
    )
    monkeypatch.setattr(
        market_data,
        "upsert_market_rows",
        lambda rows: calls.append(("normalized", rows)) or len(rows),
    )

    count = load_market_daily_bars(
        "stock_hfq",
        "hfq",
        start_date="2026-05-06",
        end_date="2026-05-06",
        archive_raw=True,
    )

    assert count == 1
    assert calls[0][0] == "raw"
    assert calls[0][1][0]["source_table"] == "sh600000"
    assert calls[1][0] == "normalized"


def test_load_market_daily_bars_keeps_raw_archive_opt_in(monkeypatch):
    calls = []

    monkeypatch.setattr(market_data, "discover_source_tables", lambda service: ["sh600000"])
    monkeypatch.setattr(
        market_data,
        "fetch_source_rows",
        lambda service, table_name, start_date, end_date: [source_row()],
    )
    monkeypatch.setattr(
        market_data,
        "upsert_raw_daily_bar_payloads",
        lambda rows: calls.append(("raw", rows)) or len(rows),
        raising=False,
    )
    monkeypatch.setattr(
        market_data,
        "upsert_market_rows",
        lambda rows: calls.append(("normalized", rows)) or len(rows),
    )

    count = load_market_daily_bars("stock_hfq", "hfq")

    assert count == 1
    assert [name for name, _ in calls] == ["normalized"]
