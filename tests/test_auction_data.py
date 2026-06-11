import datetime as dt
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest

from stock_research import cli
from stock_research import auction_data
from stock_research.auction_data import (
    auction_market_row,
    auction_staging_row,
    build_open_auction_spot_snapshot_cron_entries,
    build_lhb_auction_enhanced_rule_scan_v1,
    build_lhb_auction_topn_rerank_comparison_v1,
    build_lhb_auction_observation_detail,
    build_lhb_auction_observation_summary,
    build_lhb_close_auction_lifecycle_detail,
    build_lhb_close_auction_trade_summary,
    build_lhb_phase18e_joint_exit_rule_scan_v1,
    build_lhb_phase18e_joint_exit_state_detail_v1,
    build_tushare_auction_full_backfill_plan,
    collect_open_auction_spot_snapshot,
    collect_open_auction_minute_bars,
    collect_open_auction_minute_bars_until_covered,
    load_open_trading_dates,
    open_auction_minute_market_row,
    open_auction_spot_snapshot_market_row,
    open_auction_spot_snapshot_staging_row,
    query_eastmoney_spot_snapshot_rows,
    query_tushare_auction_rows_for_trade_date,
    run_tushare_auction_full_backfill_plan,
    sync_tushare_stock_auction_bars,
    ts_code_from_spot_symbol,
    upsert_stock_open_auction_spot_snapshots,
    upsert_stock_open_auction_minute_bars,
    upsert_stock_auction_bars,
    write_open_auction_spot_snapshot_report,
)
from stock_research.minute_data import canonical_json


class _Context:
    def __init__(self, value):
        self.value = value

    def __enter__(self):
        return self.value

    def __exit__(self, exc_type, exc, tb):
        return False


def raw_auction_row() -> dict:
    return {
        "ts_code": "600023.SH",
        "trade_date": "20260305",
        "close": 5.45,
        "open": 5.45,
        "high": 5.45,
        "low": 5.45,
        "vol": 457800.0,
        "amount": 2495009.92,
        "vwap": 5.45,
    }


def raw_open_auction_minute_row() -> dict:
    return {
        "时间": "2026-06-09 09:24:00",
        "开盘": 10.1,
        "收盘": 10.24,
        "最高": 10.3,
        "最低": 10.0,
        "成交量": 120000,
        "成交额": 1234567.89,
        "最新价": 10.24,
    }


def raw_spot_snapshot_row() -> dict:
    return {
        "代码": "600023",
        "名称": "浙能电力",
        "最新价": 5.45,
        "今开": 5.40,
        "昨收": 5.38,
        "最高": 5.47,
        "最低": 5.39,
        "成交量": 457800,
        "成交额": 2495009.92,
        "量比": 1.23,
        "换手率": 0.56,
    }


def test_auction_market_row_normalizes_tushare_open_call_payload():
    row = auction_market_row(raw_auction_row(), auction_phase="open_call")

    assert row["asset_id"] == "CN:SH:600023"
    assert row["ts_code"] == "600023.SH"
    assert row["trade_date"] == dt.date(2026, 3, 5)
    assert row["auction_phase"] == "open_call"
    assert row["close"] == 5.45
    assert row["volume"] == 457800.0
    assert row["amount"] == 2495009.92
    assert row["vwap"] == 5.45
    assert row["source"] == "tushare"


def test_auction_staging_row_preserves_raw_payload_hash():
    row = auction_staging_row(
        raw_auction_row(),
        auction_phase="close_call",
        source_endpoint="stk_auction_c",
        params={"ts_code": "600023.SH", "trade_date": "20260305"},
    )

    assert row["source_endpoint"] == "stk_auction_c"
    assert row["ts_code"] == "600023.SH"
    assert row["trade_date"] == dt.date(2026, 3, 5)
    assert row["auction_phase"] == "close_call"
    assert row["payload"] == raw_auction_row()
    assert len(row["payload_hash"]) == 64


def test_upsert_stock_auction_bars_writes_staging_and_market(monkeypatch):
    calls = []

    def fake_execute_many(conn, sql, rows):
        calls.append((conn, sql, list(rows)))

    monkeypatch.setattr(auction_data, "connect", lambda service: _Context("conn"))
    monkeypatch.setattr(auction_data, "execute_many", fake_execute_many)

    count = upsert_stock_auction_bars(
        [raw_auction_row()],
        auction_phase="open_call",
        source_endpoint="stk_auction_o",
        params={"ts_code": "600023.SH", "trade_date": "20260305"},
    )

    assert count == 1
    assert len(calls) == 2
    assert "INSERT INTO staging.tushare_stock_auction_bar" in calls[0][1]
    assert "INSERT INTO market.stock_auction_bar" in calls[1][1]
    assert "ON CONFLICT (trade_date, asset_id, auction_phase, source)" in calls[1][1]
    assert calls[1][2][0]["auction_phase"] == "open_call"


def test_query_tushare_auction_rows_for_trade_date_uses_one_phase_endpoint_call():
    class Client:
        def stk_auction_o(self, **kwargs):
            calls.append(("stk_auction_o", kwargs))
            return _Frame([raw_auction_row()])

        def stk_auction_c(self, **kwargs):
            calls.append(("stk_auction_c", kwargs))
            return _Frame([raw_auction_row()])

    class _Frame:
        def __init__(self, rows):
            self._rows = rows

        def to_dict(self, orient):
            assert orient == "records"
            return self._rows

    calls = []

    rows = query_tushare_auction_rows_for_trade_date(
        Client(),
        trade_date=dt.date(2026, 3, 5),
        auction_phase="close_call",
    )

    assert rows == [raw_auction_row()]
    assert calls == [
        (
            "stk_auction_c",
            {"trade_date": "20260305"},
        )
    ]


def test_sync_tushare_stock_auction_bars_batches_by_trade_date_and_filters_locally(monkeypatch):
    rows = [
        raw_auction_row(),
        {
            **raw_auction_row(),
            "ts_code": "000001.SZ",
        },
    ]
    query_calls = []
    upsert_calls = []

    def fake_query(client, trade_date, auction_phase):
        query_calls.append((client, trade_date, auction_phase))
        return rows

    def fake_upsert(selected_rows, auction_phase, source_endpoint, params):
        upsert_calls.append((selected_rows, auction_phase, source_endpoint, params))
        return len(selected_rows)

    monkeypatch.setattr(auction_data, "tushare_client", lambda token=None: "client")
    monkeypatch.setattr(auction_data, "query_tushare_auction_rows_for_trade_date", fake_query)
    monkeypatch.setattr(auction_data, "upsert_stock_auction_bars", fake_upsert)
    monkeypatch.setattr(auction_data.time, "sleep", lambda seconds: None)

    counts = sync_tushare_stock_auction_bars(
        start_date="2026-03-05",
        end_date="2026-03-06",
        auction_phases=["open_call"],
        ts_codes=["600023.SH"],
        sleep_seconds=0.1,
    )

    assert counts == {"open_call": 2}
    assert len(query_calls) == 2
    assert query_calls[0] == ("client", dt.date(2026, 3, 5), "open_call")
    assert upsert_calls[0][0] == [raw_auction_row()]
    assert upsert_calls[0][3] == {
        "trade_date": "20260305",
        "auction_phase": "open_call",
        "ts_codes": ["600023.SH"],
    }


def test_sync_tushare_stock_auction_bars_uses_explicit_trade_dates_to_avoid_calendar_calls(monkeypatch):
    query_calls = []

    def fake_query(client, trade_date, auction_phase):
        query_calls.append((trade_date, auction_phase))
        return [raw_auction_row()]

    monkeypatch.setattr(auction_data, "tushare_client", lambda token=None: "client")
    monkeypatch.setattr(auction_data, "query_tushare_auction_rows_for_trade_date", fake_query)
    monkeypatch.setattr(
        auction_data,
        "upsert_stock_auction_bars",
        lambda selected_rows, auction_phase, source_endpoint, params: len(selected_rows),
    )
    monkeypatch.setattr(auction_data.time, "sleep", lambda seconds: None)

    sync_tushare_stock_auction_bars(
        start_date="2026-03-01",
        end_date="2026-03-31",
        auction_phases=["open_call", "close_call"],
        ts_codes=["600023.SH"],
        trade_dates=["2026-03-05", "2026-03-09"],
        sleep_seconds=0.1,
    )

    assert query_calls == [
        (dt.date(2026, 3, 5), "open_call"),
        (dt.date(2026, 3, 5), "close_call"),
        (dt.date(2026, 3, 9), "open_call"),
        (dt.date(2026, 3, 9), "close_call"),
    ]


def test_sync_tushare_stock_auction_bars_requires_selected_ts_codes():
    with pytest.raises(ValueError, match="ts_codes is required"):
        sync_tushare_stock_auction_bars(
            start_date="2026-03-05",
            end_date="2026-03-05",
            auction_phases=["open_call"],
            ts_codes=None,
        )


def test_build_tushare_auction_full_backfill_plan_skips_covered_dates():
    trade_dates = ["2026-03-05", "2026-03-06"]
    coverage = pd.DataFrame(
        [
            {"trade_date": "2026-03-05", "auction_phase": "open_call", "row_count": 5200},
            {"trade_date": "2026-03-05", "auction_phase": "close_call", "row_count": 5100},
            {"trade_date": "2026-03-06", "auction_phase": "open_call", "row_count": 2},
        ]
    )

    plan = build_tushare_auction_full_backfill_plan(
        trade_dates=trade_dates,
        auction_phases=["open_call", "close_call"],
        existing_coverage=coverage,
        min_rows_per_date=1000,
    )

    assert plan.to_dict("records") == [
        {
            "trade_date": "2026-03-06",
            "auction_phase": "open_call",
            "existing_rows": 2,
            "should_query": True,
        },
        {
            "trade_date": "2026-03-06",
            "auction_phase": "close_call",
            "existing_rows": 0,
            "should_query": True,
        },
    ]


def test_load_open_trading_dates_includes_daily_bar_dates_when_calendar_lags(monkeypatch):
    def fake_fetch_all(conn, sql, params):
        assert conn == "conn"
        assert "market.trading_calendar" in sql
        assert "market_daily_bar" in sql
        assert params == ["2026-06-08", "2026-06-10", "2026-06-08", "2026-06-10"]
        return [
            {"trade_date": "2026-06-08"},
            {"trade_date": "2026-06-09"},
        ]

    monkeypatch.setattr(auction_data, "connect", lambda service: _Context("conn"))
    monkeypatch.setattr(auction_data, "fetch_all", fake_fetch_all)

    assert load_open_trading_dates(start_date="2026-06-08", end_date="2026-06-10") == [
        "2026-06-08",
        "2026-06-09",
    ]


def test_run_tushare_auction_full_backfill_plan_queries_whole_market(monkeypatch):
    plan = pd.DataFrame(
        [
            {"trade_date": "2026-03-05", "auction_phase": "open_call"},
            {"trade_date": "2026-03-06", "auction_phase": "open_call"},
        ]
    )
    query_calls = []
    upsert_calls = []

    def fake_query(client, trade_date, auction_phase):
        query_calls.append((client, trade_date, auction_phase))
        if trade_date == dt.date(2026, 3, 6):
            raise RuntimeError("temporary tushare failure")
        return [raw_auction_row(), {**raw_auction_row(), "ts_code": "000001.SZ"}]

    def fake_upsert(rows, auction_phase, source_endpoint, params):
        upsert_calls.append((rows, auction_phase, source_endpoint, params))
        return len(rows)

    monkeypatch.setattr(auction_data, "tushare_client", lambda token=None: "client")
    monkeypatch.setattr(auction_data, "query_tushare_auction_rows_for_trade_date", fake_query)
    monkeypatch.setattr(auction_data, "upsert_stock_auction_bars", fake_upsert)
    monkeypatch.setattr(auction_data.time, "sleep", lambda seconds: None)

    result = run_tushare_auction_full_backfill_plan(
        plan=plan,
        max_calls=10,
        sleep_seconds=0,
    )

    assert query_calls == [
        ("client", dt.date(2026, 3, 5), "open_call"),
        ("client", dt.date(2026, 3, 6), "open_call"),
    ]
    assert upsert_calls[0][0] == [raw_auction_row(), {**raw_auction_row(), "ts_code": "000001.SZ"}]
    assert upsert_calls[0][3] == {
        "trade_date": "20260305",
        "auction_phase": "open_call",
        "executor": "tushare_auction_full_backfill_v1",
    }
    assert result["summary"] == {
        "executed_calls": 2,
        "failed_calls": 1,
        "remaining_calls": 0,
        "queried_rows": 2,
        "upserted_rows": 2,
    }


def test_open_auction_minute_market_row_normalizes_eastmoney_payload():
    row = open_auction_minute_market_row(raw_open_auction_minute_row(), ts_code="600023.SH")

    assert row["asset_id"] == "CN:SH:600023"
    assert row["ts_code"] == "600023.SH"
    assert row["trade_date"] == dt.date(2026, 6, 9)
    assert row["trade_time"] == dt.datetime(2026, 6, 9, 9, 24)
    assert row["auction_phase"] == "open_call"
    assert row["freq"] == "1min"
    assert row["open"] == 10.1
    assert row["close"] == 10.24
    assert row["latest"] == 10.24
    assert row["volume"] == 120000
    assert row["amount"] == 1234567.89
    assert row["source"] == "eastmoney_pre_min"


def test_ts_code_from_spot_symbol_maps_cn_exchanges():
    assert ts_code_from_spot_symbol("600023") == "600023.SH"
    assert ts_code_from_spot_symbol("000001") == "000001.SZ"
    assert ts_code_from_spot_symbol("300001") == "300001.SZ"
    assert ts_code_from_spot_symbol("830799") == "830799.BJ"


def test_ts_code_from_spot_symbol_rejects_malformed_symbols():
    for symbol in ["1", 1, "600023.SH", "sh600023", "ABCDEF", "", None]:
        with pytest.raises(ValueError):
            ts_code_from_spot_symbol(symbol)


def test_open_auction_spot_snapshot_market_row_normalizes_spot_payload():
    row = open_auction_spot_snapshot_market_row(
        raw_spot_snapshot_row(),
        trade_date=dt.date(2026, 6, 11),
        snapshot_time=dt.datetime(2026, 6, 11, 9, 17, 5),
        target_time="09:17",
    )

    assert row["asset_id"] == "CN:SH:600023"
    assert row["ts_code"] == "600023.SH"
    assert row["trade_date"] == dt.date(2026, 6, 11)
    assert row["snapshot_time"] == dt.datetime(2026, 6, 11, 9, 17, 5)
    assert row["target_time"] == dt.time(9, 17)
    assert row["auction_phase"] == "open_call"
    assert row["latest"] == 5.45
    assert row["open"] == 5.40
    assert row["prev_close"] == 5.38
    assert row["volume"] == 457800
    assert row["amount"] == 2495009.92
    assert row["volume_ratio"] == 1.23
    assert row["turnover_rate"] == 0.56
    assert row["source"] == "eastmoney_spot_snapshot"


def test_open_auction_spot_snapshot_staging_row_preserves_payload_hash():
    row = open_auction_spot_snapshot_staging_row(
        raw_spot_snapshot_row(),
        trade_date=dt.date(2026, 6, 11),
        snapshot_time=dt.datetime(2026, 6, 11, 9, 17, 5),
        target_time="09:17",
        source_endpoint="stock_zh_a_spot_em",
        params={"target_time": "09:17"},
    )

    assert row["source_endpoint"] == "stock_zh_a_spot_em"
    assert row["raw_symbol"] == "600023"
    assert row["ts_code"] == "600023.SH"
    assert row["target_time"] == dt.time(9, 17)
    assert row["payload"] == raw_spot_snapshot_row()
    assert len(row["payload_hash"]) == 64


def test_open_auction_spot_snapshot_rows_normalize_nan_and_placeholders():
    raw = {
        "代码": "600023",
        "最新价": float("nan"),
        "今开": "-",
        "昨收": "",
        "最高": None,
        "最低": 5.39,
        "成交量": pd.NA,
        "成交额": 2495009.92,
    }

    market_row = open_auction_spot_snapshot_market_row(
        raw,
        trade_date=dt.date(2026, 6, 11),
        snapshot_time=dt.datetime(2026, 6, 11, 9, 17, 5),
        target_time="09:17",
    )
    staging_row = open_auction_spot_snapshot_staging_row(
        raw,
        trade_date=dt.date(2026, 6, 11),
        snapshot_time=dt.datetime(2026, 6, 11, 9, 17, 5),
        target_time="09:17",
        source_endpoint="stock_zh_a_spot_em",
    )

    assert market_row["latest"] is None
    assert market_row["open"] is None
    assert market_row["prev_close"] is None
    assert market_row["high"] is None
    assert market_row["volume"] is None
    assert market_row["low"] == 5.39
    assert market_row["amount"] == 2495009.92
    assert staging_row["payload"] == {
        "代码": "600023",
        "最新价": None,
        "今开": None,
        "昨收": None,
        "最高": None,
        "最低": 5.39,
        "成交量": None,
        "成交额": 2495009.92,
    }
    assert "NaN" not in canonical_json(staging_row["payload"])


def test_clean_spot_placeholder_double_dash_preserves_row():
    raw = {
        "代码": "600023",
        "最新价": "--",
    }

    market_row = open_auction_spot_snapshot_market_row(
        raw,
        trade_date=dt.date(2026, 6, 11),
        snapshot_time=dt.datetime(2026, 6, 11, 9, 17, 5),
        target_time="09:17",
    )
    staging_row = open_auction_spot_snapshot_staging_row(
        raw,
        trade_date=dt.date(2026, 6, 11),
        snapshot_time=dt.datetime(2026, 6, 11, 9, 17, 5),
        target_time="09:17",
        source_endpoint="stock_zh_a_spot_em",
    )

    assert market_row["latest"] is None
    assert staging_row["payload"]["最新价"] is None


def test_upsert_stock_open_auction_spot_snapshots_writes_staging_and_market(monkeypatch):
    calls = []

    def fake_execute_many(conn, sql, rows):
        calls.append((conn, sql, list(rows)))

    monkeypatch.setattr(auction_data, "connect", lambda service: _Context("conn"))
    monkeypatch.setattr(auction_data, "execute_many", fake_execute_many)

    count = upsert_stock_open_auction_spot_snapshots(
        [{**raw_spot_snapshot_row(), "最新价": float("nan")}],
        trade_date=dt.date(2026, 6, 11),
        snapshot_time=dt.datetime(2026, 6, 11, 9, 17, 5),
        target_time="09:17",
        params={"target_time": "09:17"},
    )

    assert count == 1
    assert len(calls) == 2
    assert "INSERT INTO staging.eastmoney_stock_spot_snapshot" in calls[0][1]
    assert "INSERT INTO market.stock_open_auction_snapshot" in calls[1][1]
    assert "ON CONFLICT (trade_date, asset_id, target_time, source)" in calls[1][1]
    assert calls[0][2][0]["payload"] == canonical_json({**raw_spot_snapshot_row(), "最新价": None})
    assert "NaN" not in calls[0][2][0]["payload"]
    assert calls[1][2][0]["target_time"] == dt.time(9, 17)


def test_collect_open_auction_spot_snapshot_queries_once_and_reports(monkeypatch):
    query_calls = []
    upsert_calls = []

    def fake_query():
        query_calls.append("called")
        return [raw_spot_snapshot_row()]

    def fake_upsert(rows, trade_date, snapshot_time, target_time, source_endpoint="stock_zh_a_spot_em", params=None):
        upsert_calls.append((rows, trade_date, snapshot_time, target_time, source_endpoint, params))
        return len(rows)

    monkeypatch.setattr(auction_data, "query_eastmoney_spot_snapshot_rows", fake_query)
    monkeypatch.setattr(auction_data, "upsert_stock_open_auction_spot_snapshots", fake_upsert)
    monkeypatch.setattr(auction_data, "is_open_trading_date", lambda trade_date: True)

    result = collect_open_auction_spot_snapshot(
        trade_date="2026-06-11",
        target_time="09:17",
        snapshot_time=dt.datetime(2026, 6, 11, 9, 17, 5),
    )

    assert query_calls == ["called"]
    assert upsert_calls[0][0] == [raw_spot_snapshot_row()]
    assert upsert_calls[0][1] == dt.date(2026, 6, 11)
    assert upsert_calls[0][3] == "09:17"
    assert result["summary"]["queried_rows"] == 1
    assert result["summary"]["upserted_rows"] == 1
    assert result["summary"]["skipped_rows"] == 0
    assert result["summary"]["failed"] is False


def test_collect_open_auction_spot_snapshot_skips_bad_rows_without_losing_good_rows(monkeypatch):
    upsert_calls = []
    good_row = raw_spot_snapshot_row()

    def fake_query():
        return [
            good_row,
            {**raw_spot_snapshot_row(), "代码": "bad-symbol"},
            {**raw_spot_snapshot_row(), "代码": "000001", "最新价": "--"},
        ]

    def fake_upsert(rows, trade_date, snapshot_time, target_time, source_endpoint="stock_zh_a_spot_em", params=None):
        upsert_calls.append((rows, trade_date, snapshot_time, target_time, source_endpoint, params))
        return len(rows)

    monkeypatch.setattr(auction_data, "query_eastmoney_spot_snapshot_rows", fake_query)
    monkeypatch.setattr(auction_data, "upsert_stock_open_auction_spot_snapshots", fake_upsert)
    monkeypatch.setattr(auction_data, "is_open_trading_date", lambda trade_date: True)

    result = collect_open_auction_spot_snapshot(
        trade_date="2026-06-11",
        target_time="09:17",
        snapshot_time=dt.datetime(2026, 6, 11, 9, 17, 5),
    )

    assert upsert_calls[0][0] == [good_row, {**raw_spot_snapshot_row(), "代码": "000001", "最新价": "--"}]
    assert result["summary"]["queried_rows"] == 3
    assert result["summary"]["skipped_rows"] == 1
    assert result["summary"]["upserted_rows"] == 2
    assert result["summary"]["failed"] is False
    assert result["summary"]["error"] == ""


def test_collect_open_auction_spot_snapshot_marks_empty_response_failed(monkeypatch):
    monkeypatch.setattr(auction_data, "is_open_trading_date", lambda trade_date: True)
    monkeypatch.setattr(auction_data, "query_eastmoney_spot_snapshot_rows", lambda: [])
    monkeypatch.setattr(
        auction_data,
        "upsert_stock_open_auction_spot_snapshots",
        lambda rows, trade_date, snapshot_time, target_time, source_endpoint="stock_zh_a_spot_em", params=None: len(rows),
    )

    result = collect_open_auction_spot_snapshot(
        trade_date="2026-06-11",
        target_time="09:17",
        snapshot_time=dt.datetime(2026, 6, 11, 9, 17, 5),
    )

    assert result["summary"]["failed"] is True
    assert result["summary"]["error"]
    assert result["summary"]["queried_rows"] == 0
    assert result["summary"]["upserted_rows"] == 0
    assert result["summary"]["skipped_rows"] == 0


def test_collect_open_auction_spot_snapshot_marks_all_skipped_failed(monkeypatch):
    rows = [
        {**raw_spot_snapshot_row(), "代码": "bad-symbol"},
        {**raw_spot_snapshot_row(), "代码": "bad-again"},
    ]

    monkeypatch.setattr(auction_data, "is_open_trading_date", lambda trade_date: True)
    monkeypatch.setattr(auction_data, "query_eastmoney_spot_snapshot_rows", lambda: rows)
    monkeypatch.setattr(
        auction_data,
        "upsert_stock_open_auction_spot_snapshots",
        lambda rows, trade_date, snapshot_time, target_time, source_endpoint="stock_zh_a_spot_em", params=None: len(rows),
    )

    result = collect_open_auction_spot_snapshot(
        trade_date="2026-06-11",
        target_time="09:17",
        snapshot_time=dt.datetime(2026, 6, 11, 9, 17, 5),
    )

    assert result["summary"]["queried_rows"] == 2
    assert result["summary"]["skipped_rows"] == 2
    assert result["summary"]["upserted_rows"] == 0
    assert result["summary"]["failed"] is True
    assert result["summary"]["error"]


def test_collect_open_auction_spot_snapshot_skips_non_trading_day_without_query(monkeypatch):
    query_calls = []
    upsert_calls = []

    def fake_query():
        query_calls.append("called")
        return [raw_spot_snapshot_row()]

    def fake_upsert(rows, trade_date, snapshot_time, target_time, source_endpoint="stock_zh_a_spot_em", params=None):
        upsert_calls.append((rows, trade_date, snapshot_time, target_time, source_endpoint, params))
        return len(rows)

    monkeypatch.setattr(auction_data, "is_open_trading_date", lambda trade_date: False)
    monkeypatch.setattr(auction_data, "query_eastmoney_spot_snapshot_rows", fake_query)
    monkeypatch.setattr(auction_data, "upsert_stock_open_auction_spot_snapshots", fake_upsert)

    result = collect_open_auction_spot_snapshot(
        trade_date="2026-06-14",
        target_time="09:17",
        snapshot_time=dt.datetime(2026, 6, 14, 9, 17, 5),
    )

    assert query_calls == []
    assert upsert_calls == []
    assert result["summary"]["non_trading_day"] is True
    assert result["summary"]["failed"] is False
    assert result["summary"]["queried_rows"] == 0
    assert result["summary"]["upserted_rows"] == 0
    assert result["summary"]["skipped_rows"] == 0
    assert result["summary"]["error"] == ""


def test_collect_open_auction_spot_snapshot_marks_bad_target_time_failure(monkeypatch):
    query_calls = []
    upsert_calls = []

    def fake_query():
        query_calls.append("called")
        return [raw_spot_snapshot_row()]

    def fake_upsert(rows, trade_date, snapshot_time, target_time, source_endpoint="stock_zh_a_spot_em", params=None):
        upsert_calls.append((rows, trade_date, snapshot_time, target_time, source_endpoint, params))
        return len(rows)

    monkeypatch.setattr(auction_data, "query_eastmoney_spot_snapshot_rows", fake_query)
    monkeypatch.setattr(auction_data, "upsert_stock_open_auction_spot_snapshots", fake_upsert)

    result = collect_open_auction_spot_snapshot(
        trade_date="2026-06-11",
        target_time="0917",
        snapshot_time=dt.datetime(2026, 6, 11, 9, 17, 5),
    )

    assert result["summary"]["failed"] is True
    assert result["summary"]["upserted_rows"] == 0
    assert result["summary"]["skipped_rows"] == 0
    assert result["summary"]["error"]
    assert query_calls == []
    assert upsert_calls == []


def test_collect_open_auction_spot_snapshot_marks_query_failure(monkeypatch):
    def fake_query():
        raise RuntimeError("spot unavailable")

    monkeypatch.setattr(auction_data, "is_open_trading_date", lambda trade_date: True)
    monkeypatch.setattr(auction_data, "query_eastmoney_spot_snapshot_rows", fake_query)

    result = collect_open_auction_spot_snapshot(
        trade_date="2026-06-11",
        target_time="09:17",
        snapshot_time=dt.datetime(2026, 6, 11, 9, 17, 5),
    )

    assert result["summary"]["failed"] is True
    assert "spot unavailable" in result["summary"]["error"]
    assert result["summary"]["queried_rows"] == 0
    assert result["summary"]["upserted_rows"] == 0


def test_collect_open_auction_spot_snapshot_marks_upsert_failure(monkeypatch):
    def fake_query():
        return [raw_spot_snapshot_row()]

    def fake_upsert(rows, trade_date, snapshot_time, target_time, source_endpoint="stock_zh_a_spot_em", params=None):
        raise RuntimeError("db down")

    monkeypatch.setattr(auction_data, "is_open_trading_date", lambda trade_date: True)
    monkeypatch.setattr(auction_data, "query_eastmoney_spot_snapshot_rows", fake_query)
    monkeypatch.setattr(auction_data, "upsert_stock_open_auction_spot_snapshots", fake_upsert)

    result = collect_open_auction_spot_snapshot(
        trade_date="2026-06-11",
        target_time="09:17",
        snapshot_time=dt.datetime(2026, 6, 11, 9, 17, 5),
    )

    assert result["summary"]["failed"] is True
    assert "db down" in result["summary"]["error"]
    assert result["summary"]["queried_rows"] == 1
    assert result["summary"]["upserted_rows"] == 0
    assert result["summary"]["skipped_rows"] == 0


def test_write_open_auction_spot_snapshot_report(tmp_path):
    result = {
        "detail": pd.DataFrame(
            [
                {
                    "trade_date": "2026-06-11",
                    "target_time": "09:17",
                    "snapshot_time": "2026-06-11T09:17:05",
                    "queried_rows": 1,
                    "upserted_rows": 1,
                    "skipped_rows": 0,
                    "failed": False,
                    "error": "",
                }
            ]
        ),
        "summary": {
            "trade_date": "2026-06-11",
            "target_time": "09:17",
            "snapshot_time": "2026-06-11T09:17:05",
            "queried_rows": 1,
            "upserted_rows": 1,
            "skipped_rows": 0,
            "failed": False,
            "error": "",
        },
    }

    report = write_open_auction_spot_snapshot_report(
        result=result,
        output_dir=tmp_path,
        trade_date="2026-06-11",
        target_time="09:17",
    )

    text = Path(report["paths"]["markdown_report"]).read_text(encoding="utf-8")
    assert "- target_time: 09:17" in text
    assert "- upserted_rows: 1" in text
    assert "- failed: False" in text


def test_build_open_auction_spot_snapshot_cron_entries_uses_requested_slots():
    entries = build_open_auction_spot_snapshot_cron_entries(
        project_dir="/Users/xiwei/stock_research",
        output_dir="outputs/research/open_auction_spot_snapshot",
        log_path="logs/open_auction_spot_snapshot.log",
    )

    assert len(entries) == 6
    assert entries[0].startswith("15 9 * * 1-5 ")
    assert "scripts/run_open_auction_spot_snapshot.sh 09:15" in entries[0]
    assert entries[1].startswith("17 9 * * 1-5 ")
    assert "scripts/run_open_auction_spot_snapshot.sh 09:17" in entries[1]
    assert entries[-1].startswith("25 9 * * 1-5 ")
    assert "scripts/run_open_auction_spot_snapshot.sh 09:25" in entries[-1]
    for target_time in ["09:15", "09:17", "09:19", "09:21", "09:23", "09:25"]:
        assert any(
            f"scripts/run_open_auction_spot_snapshot.sh {target_time}" in entry
            for entry in entries
        )


def test_build_open_auction_spot_snapshot_cron_entries_quotes_shell_paths():
    entries = build_open_auction_spot_snapshot_cron_entries(
        project_dir="/Users/xiwei/stock research",
        output_dir="outputs/research/open auction spot",
        log_path="logs/open auction spot.log",
    )

    first_entry = entries[0]
    assert "cd '/Users/xiwei/stock research' &&" in first_entry
    assert "OPEN_AUCTION_SPOT_OUTPUT_DIR='outputs/research/open auction spot'" in first_entry
    assert ">> 'logs/open auction spot.log' 2>&1" in first_entry
    assert "$(date +\\%F)" in first_entry


def test_collect_open_auction_spot_snapshot_cli_returns_zero_when_collection_succeeds(
    monkeypatch,
    tmp_path,
):
    calls = []

    def fake_collect(**kwargs):
        calls.append(("collect", kwargs))
        return {
            "detail": pd.DataFrame(),
            "summary": {
                "trade_date": kwargs["trade_date"],
                "target_time": kwargs["target_time"],
                "snapshot_time": "2026-06-11T09:17:05",
                "queried_rows": 10,
                "upserted_rows": 9,
                "skipped_rows": 1,
                "failed": False,
                "error": "",
            },
        }

    def fake_write(**kwargs):
        calls.append(("write", kwargs))
        return {
            "paths": {
                "detail": tmp_path / "detail.csv",
                "latest": tmp_path / "latest.csv",
                "markdown_report": tmp_path / "report.md",
            },
            "summary": kwargs["result"]["summary"],
        }

    monkeypatch.setattr(cli, "collect_open_auction_spot_snapshot", fake_collect)
    monkeypatch.setattr(cli, "write_open_auction_spot_snapshot_report", fake_write)

    status = cli.main(
        [
            "collect-open-auction-spot-snapshot-v1",
            "--trade-date",
            "2026-06-11",
            "--target-time",
            "09:17",
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert status == 0
    assert calls[0] == (
        "collect",
        {"trade_date": "2026-06-11", "target_time": "09:17"},
    )


def test_collect_open_auction_spot_snapshot_cli_returns_one_when_collection_fails(
    monkeypatch,
    tmp_path,
):
    def fake_collect(**kwargs):
        return {
            "detail": pd.DataFrame(),
            "summary": {
                "trade_date": kwargs["trade_date"],
                "target_time": kwargs["target_time"],
                "snapshot_time": "2026-06-11T09:17:05",
                "queried_rows": 0,
                "upserted_rows": 0,
                "skipped_rows": 0,
                "failed": True,
                "error": "query failed",
            },
        }

    def fake_write(**kwargs):
        return {
            "paths": {
                "detail": tmp_path / "detail.csv",
                "latest": tmp_path / "latest.csv",
                "markdown_report": tmp_path / "report.md",
            },
            "summary": kwargs["result"]["summary"],
        }

    monkeypatch.setattr(cli, "collect_open_auction_spot_snapshot", fake_collect)
    monkeypatch.setattr(cli, "write_open_auction_spot_snapshot_report", fake_write)

    status = cli.main(
        [
            "collect-open-auction-spot-snapshot-v1",
            "--trade-date",
            "2026-06-11",
            "--target-time",
            "09:17",
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert status == 1


def test_upsert_stock_open_auction_minute_bars_writes_staging_and_market(monkeypatch):
    calls = []

    def fake_execute_many(conn, sql, rows):
        calls.append((conn, sql, list(rows)))

    monkeypatch.setattr(auction_data, "connect", lambda service: _Context("conn"))
    monkeypatch.setattr(auction_data, "execute_many", fake_execute_many)

    count = upsert_stock_open_auction_minute_bars(
        [raw_open_auction_minute_row()],
        ts_code="600023.SH",
        params={"symbol": "600023"},
    )

    assert count == 1
    assert len(calls) == 2
    assert "INSERT INTO staging.eastmoney_stock_auction_minute_bar" in calls[0][1]
    assert "INSERT INTO market.stock_auction_minute_bar" in calls[1][1]
    assert "ON CONFLICT (trade_time, asset_id, auction_phase, freq, source)" in calls[1][1]
    assert calls[1][2][0]["trade_time"] == dt.datetime(2026, 6, 9, 9, 24)


def test_collect_open_auction_minute_bars_filters_target_date_and_upserts(monkeypatch):
    query_calls = []
    upsert_calls = []

    def fake_query(symbol, start_time, end_time):
        query_calls.append((symbol, start_time, end_time))
        return [
            raw_open_auction_minute_row(),
            {**raw_open_auction_minute_row(), "时间": "2026-06-08 09:24:00"},
        ]

    def fake_upsert(rows, ts_code, source_endpoint, params):
        upsert_calls.append((rows, ts_code, source_endpoint, params))
        return len(rows)

    monkeypatch.setattr(auction_data, "query_eastmoney_open_auction_minute_rows", fake_query)
    monkeypatch.setattr(auction_data, "upsert_stock_open_auction_minute_bars", fake_upsert)
    monkeypatch.setattr(auction_data.time, "sleep", lambda seconds: None)

    result = collect_open_auction_minute_bars(
        trade_date="2026-06-09",
        ts_codes=["600023.SH"],
        sleep_seconds=0,
    )

    assert query_calls == [("600023", "09:15:00", "09:25:00")]
    assert upsert_calls[0][0] == [raw_open_auction_minute_row()]
    assert upsert_calls[0][1] == "600023.SH"
    assert upsert_calls[0][3]["trade_date"] == "2026-06-09"
    assert result["summary"]["upserted_rows"] == 1
    assert result["detail"].to_dict("records")[0]["queried_rows"] == 2


def test_collect_open_auction_minute_bars_until_covered_retries_only_remaining(monkeypatch):
    calls = []
    covered = set()

    def fake_collect(trade_date, ts_codes, start_time, end_time, sleep_seconds, max_symbols=None):
        calls.append(list(ts_codes))
        rows = []
        for ts_code in ts_codes:
            success = ts_code == "000001.SZ" or (ts_code == "600023.SH" and len(calls) == 2)
            if success:
                covered.add(ts_code)
            rows.append(
                {
                    "trade_date": str(trade_date),
                    "ts_code": ts_code,
                    "symbol": ts_code.split(".")[0],
                    "queried_rows": 11 if success else 0,
                    "selected_rows": 11 if success else 0,
                    "upserted_rows": 11 if success else 0,
                    "error": "" if success else "temporary failure",
                }
            )
        return {
            "detail": pd.DataFrame(rows),
            "summary": {"upserted_rows": sum(row["upserted_rows"] for row in rows)},
        }

    def fake_existing(trade_date, ts_codes, source="eastmoney_pre_min"):
        return sorted(covered)

    monkeypatch.setattr(auction_data, "collect_open_auction_minute_bars", fake_collect)
    monkeypatch.setattr(auction_data, "load_existing_open_auction_minute_ts_codes", fake_existing)
    monkeypatch.setattr(auction_data.time, "sleep", lambda seconds: None)

    result = collect_open_auction_minute_bars_until_covered(
        trade_date="2026-06-10",
        ts_codes=["000001.SZ", "600023.SH"],
        max_rounds=3,
        round_sleep_seconds=0,
        sleep_seconds=0,
    )

    assert calls == [["000001.SZ", "600023.SH"], ["600023.SH"]]
    assert result["summary"]["covered_symbols"] == 2
    assert result["summary"]["remaining_symbols"] == 0


def test_write_open_auction_minute_collect_report_accepts_retry_summary(tmp_path):
    result = {
        "detail": pd.DataFrame(
            [
                {
                    "round": 1,
                    "trade_date": "2026-06-10",
                    "ts_code": "600023.SH",
                    "upserted_rows": 11,
                    "error": "",
                }
            ]
        ),
        "summary": {
            "trade_date": "2026-06-10",
            "total_symbols": 2,
            "covered_symbols": 1,
            "remaining_symbols": 1,
            "rounds_executed": 1,
            "upserted_rows": 11,
        },
    }

    report = auction_data.write_open_auction_minute_collect_report(
        result=result,
        output_dir=tmp_path,
        trade_date="2026-06-10",
    )

    text = Path(report["paths"]["markdown_report"]).read_text(encoding="utf-8")
    assert "- total_symbols: 2" in text
    assert "- covered_symbols: 1" in text
    assert "- remaining_symbols: 1" in text


def test_load_lhb_auction_backfill_universe_reads_unique_ts_codes(tmp_path):
    path = tmp_path / "lhb_candidates.csv"
    pd.DataFrame(
        [
            {"trade_date": "2025-01-02", "ts_code": "600023.SH"},
            {"trade_date": "2025-01-03", "ts_code": "600023.SH"},
            {"trade_date": "2025-01-03", "ts_code": "000001.SZ"},
            {"trade_date": "2024-12-31", "ts_code": "300001.SZ"},
            {"trade_date": "2025-01-04", "ts_code": ""},
        ]
    ).to_csv(path, index=False)

    universe = auction_data.load_lhb_auction_backfill_universe(
        candidate_paths=[path],
        start_date="2025-01-01",
        end_date="2025-01-31",
    )

    assert universe == ["000001.SZ", "600023.SH"]


def test_build_lhb_auction_backfill_plan_skips_complete_date_phase():
    trade_dates = ["2025-01-02", "2025-01-03"]
    ts_codes = ["000001.SZ", "600023.SH"]
    existing = pd.DataFrame(
        [
            {"trade_date": "2025-01-02", "ts_code": "000001.SZ", "auction_phase": "open_call"},
            {"trade_date": "2025-01-02", "ts_code": "600023.SH", "auction_phase": "open_call"},
            {"trade_date": "2025-01-02", "ts_code": "000001.SZ", "auction_phase": "close_call"},
        ]
    )

    plan = auction_data.build_lhb_auction_backfill_plan(
        trade_dates=trade_dates,
        ts_codes=ts_codes,
        auction_phases=["open_call", "close_call"],
        existing_coverage=existing,
    )

    assert plan.to_dict("records") == [
        {
            "trade_date": "2025-01-02",
            "auction_phase": "close_call",
            "selected_ts_codes": 2,
            "existing_rows": 1,
            "missing_rows": 1,
            "coverage_ratio": 0.5,
            "should_query": True,
        },
        {
            "trade_date": "2025-01-03",
            "auction_phase": "open_call",
            "selected_ts_codes": 2,
            "existing_rows": 0,
            "missing_rows": 2,
            "coverage_ratio": 0.0,
            "should_query": True,
        },
        {
            "trade_date": "2025-01-03",
            "auction_phase": "close_call",
            "selected_ts_codes": 2,
            "existing_rows": 0,
            "missing_rows": 2,
            "coverage_ratio": 0.0,
            "should_query": True,
        },
    ]


def test_build_lhb_auction_backfill_plan_accepts_coverage_threshold_for_unreturned_stocks():
    ts_codes = [f"{index:06d}.SZ" for index in range(100)]
    existing = pd.DataFrame(
        [
            {"trade_date": "2025-01-02", "ts_code": code, "auction_phase": "open_call"}
            for code in ts_codes[:96]
        ]
    )

    plan = auction_data.build_lhb_auction_backfill_plan(
        trade_dates=["2025-01-02"],
        ts_codes=ts_codes,
        auction_phases=["open_call"],
        existing_coverage=existing,
        min_coverage_ratio=0.95,
    )

    assert plan.empty


def test_load_existing_lhb_auction_coverage_queries_selected_scope(monkeypatch):
    recorded = {}

    def fake_fetch_all(conn, sql, params):
        recorded["sql"] = sql
        recorded["params"] = params
        return [
            {"trade_date": "2025-01-02", "ts_code": "600023.SH", "auction_phase": "open_call"},
        ]

    monkeypatch.setattr(auction_data, "connect", lambda service: _Context("conn"))
    monkeypatch.setattr(auction_data, "fetch_all", fake_fetch_all)

    coverage = auction_data.load_existing_lhb_auction_coverage(
        start_date="2025-01-01",
        end_date="2025-01-31",
        ts_codes=["600023.SH"],
        auction_phases=["open_call"],
    )

    assert "FROM market.stock_auction_bar" in recorded["sql"]
    assert recorded["params"] == ["2025-01-01", "2025-01-31", ["600023.SH"], ["open_call"]]
    assert coverage.to_dict("records") == [
        {"trade_date": "2025-01-02", "ts_code": "600023.SH", "auction_phase": "open_call"}
    ]


def test_write_lhb_auction_backfill_plan_report_writes_csv_markdown_and_universe(tmp_path):
    plan = pd.DataFrame(
        [
            {
                "trade_date": "2025-01-02",
                "auction_phase": "open_call",
                "selected_ts_codes": 2,
                "existing_rows": 0,
                "missing_rows": 2,
                "should_query": True,
            },
            {
                "trade_date": "2025-01-02",
                "auction_phase": "close_call",
                "selected_ts_codes": 2,
                "existing_rows": 1,
                "missing_rows": 1,
                "should_query": True,
            },
        ]
    )

    result = auction_data.write_lhb_auction_backfill_plan_report(
        plan=plan,
        output_dir=tmp_path,
        start_date="2025-01-01",
        end_date="2025-01-31",
        ts_codes=["600023.SH", "000001.SZ"],
    )

    assert result["summary"]["planned_calls"] == 2
    assert result["summary"]["planned_missing_rows"] == 3
    assert result["summary"]["ts_code_count"] == 2
    assert pd.read_csv(result["paths"]["universe"])["ts_code"].tolist() == ["000001.SZ", "600023.SH"]
    assert "This is a dry-run plan" in Path(result["paths"]["markdown_report"]).read_text(encoding="utf-8")


def test_run_lhb_auction_backfill_plan_respects_max_calls(monkeypatch):
    calls = []
    plan = pd.DataFrame(
        [
            {"trade_date": "2025-01-02", "auction_phase": "open_call"},
            {"trade_date": "2025-01-02", "auction_phase": "close_call"},
            {"trade_date": "2025-01-03", "auction_phase": "open_call"},
        ]
    )

    def fake_query(client, trade_date, auction_phase):
        calls.append((trade_date.strftime("%Y-%m-%d"), auction_phase))
        return [
            {
                **raw_auction_row(),
                "ts_code": "600023.SH",
                "trade_date": trade_date.strftime("%Y%m%d"),
            },
            {
                **raw_auction_row(),
                "ts_code": "000001.SZ",
                "trade_date": trade_date.strftime("%Y%m%d"),
            },
        ]

    monkeypatch.setattr(auction_data, "tushare_client", lambda token=None: "client")
    monkeypatch.setattr(auction_data, "query_tushare_auction_rows_for_trade_date", fake_query)
    monkeypatch.setattr(
        auction_data,
        "upsert_stock_auction_bars",
        lambda rows, auction_phase, source_endpoint, params: len(rows),
    )
    monkeypatch.setattr(auction_data.time, "sleep", lambda seconds: None)

    executed = auction_data.run_lhb_auction_backfill_plan(
        plan=plan,
        ts_codes=["600023.SH"],
        max_calls=2,
        sleep_seconds=0.1,
    )

    assert calls == [("2025-01-02", "close_call"), ("2025-01-02", "open_call")]
    assert executed["summary"]["executed_calls"] == 2
    assert executed["summary"]["remaining_calls"] == 1
    assert executed["summary"]["upserted_rows"] == 2


def test_lhb_auction_backfill_run_cli_reads_plan_and_universe(monkeypatch, tmp_path, capsys):
    plan_path = tmp_path / "plan.csv"
    universe_path = tmp_path / "universe.csv"
    pd.DataFrame([{"trade_date": "2025-01-02", "auction_phase": "open_call"}]).to_csv(
        plan_path,
        index=False,
    )
    pd.DataFrame([{"ts_code": "600023.SH"}]).to_csv(universe_path, index=False)
    recorded = {}

    def fake_run_lhb_auction_backfill_plan(**kwargs):
        recorded.update(kwargs)
        return {
            "executed": pd.DataFrame(
                [
                    {
                        "trade_date": "2025-01-02",
                        "auction_phase": "open_call",
                        "queried_rows": 2,
                        "selected_rows": 1,
                        "upserted_rows": 1,
                    }
                ]
            ),
            "summary": {"executed_calls": 1, "remaining_calls": 0, "upserted_rows": 1},
        }

    monkeypatch.setattr(cli, "run_lhb_auction_backfill_plan", fake_run_lhb_auction_backfill_plan)

    exit_code = cli.main_for_args(
        [
            "lhb-auction-backfill-run-v1",
            "--plan-path",
            str(plan_path),
            "--ts-codes-path",
            str(universe_path),
            "--max-calls",
            "1",
            "--sleep-seconds",
            "0",
            "--output-dir",
            str(tmp_path / "out"),
        ]
    )

    assert exit_code == 0
    assert recorded["ts_codes"] == ["600023.SH"]
    assert recorded["max_calls"] == 1
    assert recorded["sleep_seconds"] == 0
    assert "lhb_auction_backfill_run_v1|executed_calls|1" in capsys.readouterr().out


def test_build_lhb_auction_observation_detail_joins_signal_close_and_entry_open():
    trades = pd.DataFrame(
        [
            {
                "trade_date": "2025-01-02",
                "ts_code": "300615.SZ",
                "entry_trade_date": "2025-01-03",
                "realized_return": 0.13,
                "phase12a_rule_layer": "follow_pool_low_drawdown",
            },
            {
                "trade_date": "2025-01-02",
                "ts_code": "605080.SH",
                "entry_trade_date": "2025-01-03",
                "realized_return": -0.02,
                "phase12a_rule_layer": "follow_pool_low_drawdown",
            },
        ]
    )
    auction_bars = pd.DataFrame(
        [
            {
                "trade_date": "2025-01-02",
                "ts_code": "300615.SZ",
                "auction_phase": "close_call",
                "open": 10.0,
                "close": 10.5,
                "amount": 1000000.0,
                "vwap": 10.4,
            },
            {
                "trade_date": "2025-01-03",
                "ts_code": "300615.SZ",
                "auction_phase": "open_call",
                "open": 10.6,
                "close": 11.0,
                "amount": 2000000.0,
                "vwap": 10.8,
            },
            {
                "trade_date": "2025-01-02",
                "ts_code": "605080.SH",
                "auction_phase": "close_call",
                "open": 20.0,
                "close": 19.0,
                "amount": 500000.0,
                "vwap": 19.5,
            },
        ]
    )

    detail = build_lhb_auction_observation_detail(trades=trades, auction_bars=auction_bars)

    winner = detail[detail["ts_code"].eq("300615.SZ")].iloc[0]
    loser = detail[detail["ts_code"].eq("605080.SH")].iloc[0]
    assert round(winner["signal_close_auction_return"], 6) == 0.05
    assert round(winner["entry_open_auction_return"], 6) == round(11.0 / 10.6 - 1.0, 6)
    assert round(winner["entry_open_vs_signal_close"], 6) == round(11.0 / 10.5 - 1.0, 6)
    assert winner["auction_coverage"] == "signal_close+entry_open"
    assert round(loser["signal_close_auction_return"], 6) == -0.05
    assert loser["auction_coverage"] == "signal_close_only"


def test_build_lhb_auction_observation_summary_groups_by_auction_strength():
    detail = pd.DataFrame(
        [
            {
                "auction_bucket": "entry_open_positive",
                "realized_return": 0.13,
            },
            {
                "auction_bucket": "entry_open_positive",
                "realized_return": -0.02,
            },
            {
                "auction_bucket": "entry_open_missing",
                "realized_return": -0.04,
            },
        ]
    )

    summary = build_lhb_auction_observation_summary(detail)

    positive = summary[summary["auction_bucket"].eq("entry_open_positive")].iloc[0]
    missing = summary[summary["auction_bucket"].eq("entry_open_missing")].iloc[0]
    assert positive["trade_count"] == 2
    assert positive["win_rate"] == 0.5
    assert round(positive["avg_realized_return"], 6) == 0.055
    assert missing["trade_count"] == 1


def test_build_lhb_auction_observation_detail_accepts_database_decimal_values():
    trades = pd.DataFrame(
        [
            {
                "trade_date": "2025-01-02",
                "ts_code": "300615.SZ",
                "entry_trade_date": "2025-01-03",
                "realized_return": 0.13,
            }
        ]
    )
    auction_bars = pd.DataFrame(
        [
            {
                "trade_date": "2025-01-02",
                "ts_code": "300615.SZ",
                "auction_phase": "close_call",
                "open": Decimal("10.0"),
                "close": Decimal("10.5"),
                "amount": Decimal("1000000.0"),
                "vwap": Decimal("10.4"),
            }
        ]
    )

    detail = build_lhb_auction_observation_detail(trades=trades, auction_bars=auction_bars)

    assert round(detail.iloc[0]["signal_close_auction_return"], 6) == 0.05


def test_build_lhb_auction_enhanced_rule_scan_v1_scans_thresholds_and_robustness():
    detail = pd.DataFrame(
        [
            {
                "trade_date": "2025-01-02",
                "ts_code": "A",
                "phase12a_rule_layer": "follow_pool_core",
                "entry_open_vs_signal_close": 0.07,
                "realized_return": 0.10,
            },
            {
                "trade_date": "2025-02-02",
                "ts_code": "B",
                "phase12a_rule_layer": "follow_pool_core",
                "entry_open_vs_signal_close": 0.08,
                "realized_return": 0.20,
            },
            {
                "trade_date": "2025-03-02",
                "ts_code": "C",
                "phase12a_rule_layer": "follow_pool_core",
                "entry_open_vs_signal_close": 0.03,
                "realized_return": -0.05,
            },
            {
                "trade_date": "2025-04-02",
                "ts_code": "D",
                "phase12a_rule_layer": "follow_pool_high_confidence",
                "entry_open_vs_signal_close": 0.09,
                "realized_return": -0.02,
            },
        ]
    )

    result = build_lhb_auction_enhanced_rule_scan_v1(
        detail=detail,
        rule_layer="follow_pool_core",
        thresholds=[0.02, 0.06],
    )

    scan = result["threshold_scan"]
    strong = result["strong_detail"]
    robustness = result["robustness"]
    threshold_006 = scan[scan["threshold"].eq(0.06)].iloc[0]
    assert threshold_006["trade_count"] == 2
    assert threshold_006["win_rate"] == 1.0
    assert round(threshold_006["avg_return"], 6) == 0.15
    assert list(strong["ts_code"]) == ["B", "A"]
    assert robustness[robustness["slice"].eq("follow_pool_core_gap_gt_0_06")].iloc[0][
        "trade_count"
    ] == 2


def test_build_lhb_auction_topn_rerank_comparison_v1_compares_baseline_and_enhanced():
    detail = pd.DataFrame(
        [
            {
                "trade_date": "2025-01-02",
                "ts_code": "B",
                "phase12a_rule_layer": "follow_pool_high_confidence",
                "entry_open_vs_signal_close": 0.00,
                "realized_return": -0.05,
            },
            {
                "trade_date": "2025-01-02",
                "ts_code": "A",
                "phase12a_rule_layer": "follow_pool_core",
                "entry_open_vs_signal_close": 0.07,
                "realized_return": 0.10,
            },
            {
                "trade_date": "2025-01-02",
                "ts_code": "C",
                "phase12a_rule_layer": "retreat_hard",
                "entry_open_vs_signal_close": 0.10,
                "realized_return": 0.20,
            },
            {
                "trade_date": "2025-01-03",
                "ts_code": "D",
                "phase12a_rule_layer": "follow_pool_low_drawdown",
                "entry_open_vs_signal_close": 0.06,
                "realized_return": 0.03,
            },
        ]
    )

    result = build_lhb_auction_topn_rerank_comparison_v1(detail=detail, top_ns=[1, 2])

    summary = result["summary"]
    baseline_top1 = summary[
        summary["strategy"].eq("baseline_original_order") & summary["top_n"].eq(1)
    ].iloc[0]
    enhanced_top1 = summary[
        summary["strategy"].eq("auction_enhanced_rerank") & summary["top_n"].eq(1)
    ].iloc[0]
    assert baseline_top1["trade_count"] == 2
    assert round(baseline_top1["avg_return"], 6) == -0.01
    assert enhanced_top1["trade_count"] == 2
    assert round(enhanced_top1["avg_return"], 6) == 0.065


def test_build_lhb_close_auction_lifecycle_detail_expands_hold_period_close_calls():
    trades = pd.DataFrame(
        [
            {
                "trade_date": "2025-01-02",
                "ts_code": "300615.SZ",
                "entry_trade_date": "2025-01-03",
                "exit_trade_date": "2025-01-06",
                "realized_return": 0.10,
                "strategy": "auction_enhanced_rerank",
                "top_n": 5,
                "phase12a_rule_layer": "follow_pool_core",
            }
        ]
    )
    close_auction_bars = pd.DataFrame(
        [
            {
                "trade_date": "2025-01-02",
                "ts_code": "300615.SZ",
                "auction_phase": "close_call",
                "open": 10.0,
                "close": 10.1,
                "amount": 1000000.0,
                "vwap": 10.05,
            },
            {
                "trade_date": "2025-01-03",
                "ts_code": "300615.SZ",
                "auction_phase": "close_call",
                "open": 10.1,
                "close": 10.0,
                "amount": 800000.0,
                "vwap": 10.04,
            },
            {
                "trade_date": "2025-01-06",
                "ts_code": "300615.SZ",
                "auction_phase": "close_call",
                "open": 10.0,
                "close": 9.9,
                "amount": 1200000.0,
                "vwap": 9.95,
            },
        ]
    )

    detail = build_lhb_close_auction_lifecycle_detail(
        trades=trades,
        close_auction_bars=close_auction_bars,
    )

    assert len(detail) == 3
    assert list(detail["lifecycle_day_index"]) == [0, 1, 2]
    assert list(detail["auction_trade_date"]) == ["2025-01-02", "2025-01-03", "2025-01-06"]
    assert round(detail.iloc[0]["close_auction_return"], 6) == 0.01
    assert round(detail.iloc[2]["close_auction_return"], 6) == -0.01
    assert detail.iloc[2]["is_exit_day_close_auction"] is True


def test_build_lhb_close_auction_trade_summary_buckets_lifecycle_pressure():
    detail = pd.DataFrame(
        [
            {
                "trade_id": 0,
                "ts_code": "300615.SZ",
                "strategy": "auction_enhanced_rerank",
                "top_n": 5,
                "realized_return": 0.10,
                "close_auction_return": 0.01,
                "close_auction_amount": 1000000.0,
                "lifecycle_day_index": 0,
                "is_exit_day_close_auction": False,
            },
            {
                "trade_id": 0,
                "ts_code": "300615.SZ",
                "strategy": "auction_enhanced_rerank",
                "top_n": 5,
                "realized_return": 0.10,
                "close_auction_return": -0.01,
                "close_auction_amount": 1200000.0,
                "lifecycle_day_index": 1,
                "is_exit_day_close_auction": True,
            },
            {
                "trade_id": 1,
                "ts_code": "605080.SH",
                "strategy": "auction_enhanced_rerank",
                "top_n": 5,
                "realized_return": 0.04,
                "close_auction_return": 0.008,
                "close_auction_amount": 900000.0,
                "lifecycle_day_index": 0,
                "is_exit_day_close_auction": True,
            },
            {
                "trade_id": 2,
                "ts_code": "600023.SH",
                "strategy": "baseline_original_order",
                "top_n": 5,
                "realized_return": -0.03,
                "close_auction_return": float("nan"),
                "close_auction_amount": float("nan"),
                "lifecycle_day_index": 0,
                "is_exit_day_close_auction": False,
            },
        ]
    )

    summary = build_lhb_close_auction_trade_summary(detail)

    smashed = summary[summary["trade_id"].eq(0)].iloc[0]
    persistent = summary[summary["trade_id"].eq(1)].iloc[0]
    missing = summary[summary["trade_id"].eq(2)].iloc[0]
    assert smashed["close_lifecycle_bucket"] == "has_close_auction_smash"
    assert smashed["negative_close_auction_days"] == 1
    assert round(smashed["exit_day_close_auction_return"], 6) == -0.01
    assert persistent["close_lifecycle_bucket"] == "persistent_positive_close_auction"
    assert missing["close_lifecycle_bucket"] == "close_auction_missing"


def test_build_lhb_phase18e_joint_exit_state_detail_requires_joint_weak_evidence():
    account_trades = pd.DataFrame(
        [
            {
                "account_trade_status": "filled",
                "trade_date": "2025-01-02",
                "ts_code": "300615.SZ",
                "top_n": 5,
                "strategy": "auction_enhanced_rerank",
                "phase12a_rule_layer": "follow_pool_core",
                "entry_trade_date": "2025-01-03",
                "exit_trade_date": "2025-01-06",
                "realized_return": 0.08,
            },
            {
                "account_trade_status": "filled",
                "trade_date": "2025-01-02",
                "ts_code": "605080.SH",
                "top_n": 5,
                "strategy": "auction_enhanced_rerank",
                "phase12a_rule_layer": "follow_pool_core",
                "entry_trade_date": "2025-01-03",
                "exit_trade_date": "2025-01-06",
                "realized_return": -0.04,
            },
            {
                "account_trade_status": "filled",
                "trade_date": "2025-01-02",
                "ts_code": "600023.SH",
                "top_n": 5,
                "strategy": "auction_enhanced_rerank",
                "phase12a_rule_layer": "follow_pool_core",
                "entry_trade_date": "2025-01-03",
                "exit_trade_date": "2025-01-06",
                "realized_return": 0.02,
            },
        ]
    )
    auction_observation = pd.DataFrame(
        [
            {
                "trade_date": "2025-01-02",
                "ts_code": "300615.SZ",
                "entry_open_vs_signal_close": 0.06,
                "entry_open_auction_return": 0.01,
            },
            {
                "trade_date": "2025-01-02",
                "ts_code": "605080.SH",
                "entry_open_vs_signal_close": -0.02,
                "entry_open_auction_return": -0.01,
            },
            {
                "trade_date": "2025-01-02",
                "ts_code": "600023.SH",
                "entry_open_vs_signal_close": 0.03,
                "entry_open_auction_return": 0.01,
            },
        ]
    )
    close_lifecycle = pd.DataFrame(
        [
            {
                "trade_date": "2025-01-02",
                "ts_code": "300615.SZ",
                "top_n": 5,
                "strategy": "auction_enhanced_rerank",
                "close_lifecycle_bucket": "has_close_auction_smash",
                "last_close_auction_return": -0.02,
            },
            {
                "trade_date": "2025-01-02",
                "ts_code": "605080.SH",
                "top_n": 5,
                "strategy": "auction_enhanced_rerank",
                "close_lifecycle_bucket": "mixed_close_auction",
                "last_close_auction_return": -0.01,
            },
            {
                "trade_date": "2025-01-02",
                "ts_code": "600023.SH",
                "top_n": 5,
                "strategy": "auction_enhanced_rerank",
                "close_lifecycle_bucket": "persistent_positive_close_auction",
                "last_close_auction_return": 0.01,
            },
        ]
    )
    intraday = pd.DataFrame(
        [
            {
                "trade_date": "2025-01-02",
                "ts_code": "605080.SH",
                "exit_day_close_vs_vwap": -0.02,
                "next_morning_close_vs_vwap": -0.01,
                "exit_3d_return": -0.08,
            },
            {
                "trade_date": "2025-01-02",
                "ts_code": "600023.SH",
                "exit_day_close_vs_vwap": -0.01,
                "next_morning_close_vs_vwap": 0.02,
                "exit_day_close_position": 0.20,
                "exit_3d_return": 0.04,
            },
        ]
    )

    detail = build_lhb_phase18e_joint_exit_state_detail_v1(
        account_trades=account_trades,
        auction_observation=auction_observation,
        close_lifecycle=close_lifecycle,
        intraday_indicators=intraday,
    )

    strong = detail[detail["ts_code"].eq("300615.SZ")].iloc[0]
    hard = detail[detail["ts_code"].eq("605080.SH")].iloc[0]
    watch = detail[detail["ts_code"].eq("600023.SH")].iloc[0]
    assert strong["weak_factor_count"] == 0
    assert strong["joint_exit_state"] == "strong_hold"
    assert strong["weak_close_lifecycle"] is False
    assert hard["weak_factor_count"] == 3
    assert hard["joint_exit_state"] == "hard_exit"
    assert watch["weak_factor_count"] == 1
    assert watch["joint_exit_state"] == "watch_hold"


def test_build_lhb_phase18e_joint_exit_rule_scan_v1_prioritizes_win_rate_and_reports_sell_flying():
    detail = pd.DataFrame(
        [
            {
                "trade_date": "2025-01-02",
                "ts_code": "A",
                "strategy": "auction_enhanced_rerank",
                "top_n": 5,
                "joint_exit_state": "strong_hold",
                "close_lifecycle_bucket": "persistent_positive_close_auction",
                "weak_open_confirm": False,
                "realized_return": 0.08,
                "exit_3d_return": 0.10,
            },
            {
                "trade_date": "2025-01-03",
                "ts_code": "B",
                "strategy": "auction_enhanced_rerank",
                "top_n": 5,
                "joint_exit_state": "hard_exit",
                "close_lifecycle_bucket": "mixed_close_auction",
                "weak_open_confirm": True,
                "realized_return": -0.04,
                "exit_3d_return": -0.08,
            },
            {
                "trade_date": "2025-01-04",
                "ts_code": "C",
                "strategy": "auction_enhanced_rerank",
                "top_n": 5,
                "joint_exit_state": "soft_exit",
                "close_lifecycle_bucket": "mixed_close_auction",
                "weak_open_confirm": True,
                "realized_return": -0.02,
                "exit_3d_return": 0.03,
            },
        ]
    )

    scan = build_lhb_phase18e_joint_exit_rule_scan_v1(detail)

    baseline = scan[scan["rule_profile"].eq("baseline_all")].iloc[0]
    exclude_soft = scan[scan["rule_profile"].eq("exclude_soft_or_hard_exit")].iloc[0]
    mixed_open = scan[scan["rule_profile"].eq("exclude_mixed_close_plus_weak_open")].iloc[0]
    assert round(baseline["kept_win_rate"], 6) == round(1 / 3, 6)
    assert exclude_soft["excluded_count"] == 2
    assert exclude_soft["kept_win_rate"] == 1.0
    assert round(exclude_soft["win_rate_delta_vs_baseline"], 6) == round(2 / 3, 6)
    assert mixed_open["excluded_count"] == 2
    assert round(mixed_open["excluded_avg_missed_return_to_3d"], 6) == round((-0.04 + 0.05) / 2, 6)
