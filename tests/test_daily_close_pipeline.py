from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime

import pytest

from stock_research import daily_close_pipeline as dcp
from stock_research import selection
from stock_research.cli import build_parser


@contextmanager
def _fake_connect(_service):
    yield object()


def _no_db(monkeypatch):
    monkeypatch.setattr(dcp, "connect", _fake_connect)
    monkeypatch.setattr(dcp, "execute", lambda *args, **kwargs: None)
    monkeypatch.setattr(dcp, "execute_many", lambda *args, **kwargs: None)


def test_daily_stage_uses_tushare_first_and_akshare_only_for_missing(monkeypatch):
    _no_db(monkeypatch)
    monkeypatch.setattr(dcp.time, "sleep", lambda _seconds: None)
    captured = {"akshare_ts_codes": None, "upserted": []}
    trade_date = date(2026, 6, 5)
    config = dcp.PipelineConfig(
        service="test",
        tushare_token="token",
        max_retries=1,
        force_non_trading_day=True,
    )

    def fake_tushare_fetcher(trade_date, token, timeout_seconds, ts_codes=None):
        return [
            {
                "ts_code": "000001.SZ",
                "trade_date": trade_date,
                "adjust_type": "raw",
                "open": 10,
                "high": 11,
                "low": 9,
                "close": 10.5,
            },
            {
                "ts_code": "000001.SZ",
                "trade_date": trade_date,
                "adjust_type": "qfq",
                "open": 10,
                "high": 11,
                "low": 9,
                "close": 10.5,
            },
            {
                "ts_code": "000001.SZ",
                "trade_date": trade_date,
                "adjust_type": "hfq",
                "open": 10,
                "high": 11,
                "low": 9,
                "close": 10.5,
            }
        ]

    def fake_akshare_fetcher(trade_date, ts_codes, timeout_seconds, adjust_types=None):
        captured["akshare_ts_codes"] = ts_codes
        assert tuple(adjust_types) == ("hfq", "qfq", "raw")
        return [
            {
                "ts_code": "600000.SH",
                "trade_date": trade_date,
                "adjust_type": "raw",
                "open": 20,
                "high": 21,
                "low": 19,
                "close": 20.5,
            },
            {
                "ts_code": "600000.SH",
                "trade_date": trade_date,
                "adjust_type": "qfq",
                "open": 20,
                "high": 21,
                "low": 19,
                "close": 20.5,
            },
            {
                "ts_code": "600000.SH",
                "trade_date": trade_date,
                "adjust_type": "hfq",
                "open": 20,
                "high": 21,
                "low": 19,
                "close": 20.5,
            }
        ]

    def fake_upsert(_service, rows):
        captured["upserted"] = rows
        return len(rows)

    result = dcp.run_daily_stage(
        trade_date,
        config=config,
        ts_codes=["000001.SZ", "600000.SH"],
        tushare_fetcher=fake_tushare_fetcher,
        akshare_fetcher=fake_akshare_fetcher,
        daily_upserter=fake_upsert,
    )

    assert result["status"] == "success"
    assert captured["akshare_ts_codes"] == ["600000.SH"]
    assert [row["adjust_type"] for row in captured["upserted"]] == [
        "raw",
        "qfq",
        "hfq",
        "raw",
        "qfq",
        "hfq",
    ]
    assert [row["source"] for row in captured["upserted"]] == [
        "tushare",
        "tushare",
        "tushare",
        "akshare",
        "akshare",
        "akshare",
    ]
    assert result["quality"]["expected_count"] == 6
    assert result["quality"]["actual_count"] == 6


def test_daily_quality_requires_raw_qfq_and_hfq_for_each_symbol():
    trade_date = date(2026, 6, 5)

    quality = dcp.inspect_daily_quality(
        [
            {
                "ts_code": "000001.SZ",
                "trade_date": trade_date,
                "adjust_type": "raw",
                "open": 10,
                "high": 11,
                "low": 9,
                "close": 10,
            },
            {
                "ts_code": "000001.SZ",
                "trade_date": trade_date,
                "adjust_type": "qfq",
                "open": 10,
                "high": 11,
                "low": 9,
                "close": 10,
            },
        ],
        ["000001.SZ"],
        trade_date,
    )

    assert quality["status"] == "warning"
    assert quality["expected_count"] == 3
    assert quality["actual_count"] == 2
    assert quality["missing_symbols"] == ["000001.SZ:hfq"]


def test_tushare_daily_rows_filter_to_expected_universe(monkeypatch):
    class Frame:
        empty = False

        def __init__(self, rows):
            self._rows = rows

        def to_dict(self, orient):
            assert orient == "records"
            return self._rows

    class Pro:
        def daily(self, trade_date):
            return Frame(
                [
                    {
                        "ts_code": "000001.SZ",
                        "open": 10,
                        "high": 11,
                        "low": 9,
                        "close": 10,
                        "pre_close": 9.8,
                        "vol": 100,
                        "amount": 1000,
                        "pct_chg": 1.0,
                    },
                    {
                        "ts_code": "920000.BJ",
                        "open": 20,
                        "high": 21,
                        "low": 19,
                        "close": 20,
                        "pre_close": 19.8,
                        "vol": 200,
                        "amount": 2000,
                        "pct_chg": 1.0,
                    },
                ]
            )

        def daily_basic(self, trade_date):
            return Frame([])

    class Tushare:
        @staticmethod
        def pro_api(token):
            return Pro()

    monkeypatch.setitem(__import__("sys").modules, "tushare", Tushare)

    rows = dcp.fetch_tushare_daily_rows(
        date(2026, 6, 18),
        token="token",
        timeout_seconds=5,
        ts_codes=["000001.SZ"],
    )

    assert [row["ts_code"] for row in rows] == ["000001.SZ"]


def test_minute5_stage_records_single_symbol_failure_without_failing_batch(monkeypatch):
    _no_db(monkeypatch)
    monkeypatch.setattr(dcp.time, "sleep", lambda _seconds: None)
    failed_symbols = []
    config = dcp.PipelineConfig(
        service="test",
        max_retries=2,
        max_workers_minute5=1,
        minute5_min_coverage_ratio=0.5,
        force_non_trading_day=True,
    )

    def fake_record_failed_symbol(**kwargs):
        failed_symbols.append(kwargs["ts_code"])

    def fake_fetcher(ts_code, start_date, end_date, timeout_seconds):
        if ts_code == "600000.SH":
            raise TimeoutError("source timeout")
        rows = []
        for hour in [9, 10, 11, 13, 14]:
            for minute in [0, 5, 10, 15, 20, 25, 30, 35, 40]:
                rows.append(
                    {
                        "asset_id": "CN:SZ:000001",
                        "ts_code": ts_code,
                        "trade_time": datetime(2026, 6, 5, hour, minute),
                        "trade_date": date(2026, 6, 5),
                        "freq": "5min",
                        "adjust_type": "raw",
                        "open": 1,
                        "high": 1,
                        "low": 1,
                        "close": 1,
                        "volume": 1,
                        "amount": 1,
                        "source": "akshare",
                    }
                )
        return rows

    monkeypatch.setattr(dcp, "record_failed_symbol", fake_record_failed_symbol)
    result = dcp.run_minute5_stage(
        date(2026, 6, 5),
        config=config,
        ts_codes=["000001.SZ", "600000.SH"],
        fetcher=fake_fetcher,
        upserter=lambda _service, rows: len(rows),
    )

    assert result["status"] == "partial_success"
    assert result["failed_symbols"] == ["600000.SH"]
    assert failed_symbols == ["600000.SH"]


def test_finalize_pipeline_status_degrades_for_partial_core(monkeypatch):
    _no_db(monkeypatch)
    jobs = [
        {"stage": "daily", "job_name": "daily_bar", "source": "mixed", "status": "success"},
        {
            "stage": "minute5",
            "job_name": "minute5_bar",
            "source": "akshare",
            "status": "partial_success",
            "error_summary": "one symbol failed",
        },
        {"stage": "deps", "job_name": "daily_factor_pipeline", "source": "internal", "status": "success"},
    ]
    monkeypatch.setattr(dcp, "fetch_all", lambda _conn, _sql, _params=None: jobs)
    monkeypatch.setattr(dcp, "latest_ready_trade_date", lambda _service: date(2026, 6, 4))

    result = dcp.finalize_pipeline_status(date(2026, 6, 5), config=dcp.PipelineConfig(service="test"))

    assert result["pipeline_status"] == "DEGRADED_READY"
    assert result["latest_ready_trade_date"] == date(2026, 6, 5)
    assert result["failed_jobs"][0]["job_name"] == "minute5_bar"


def test_closed_trading_calendar_skips_daily_stage(monkeypatch):
    _no_db(monkeypatch)
    monkeypatch.setattr(
        dcp,
        "trading_calendar_status",
        lambda service, trade_date: "closed",
    )
    recorded = []
    monkeypatch.setattr(dcp, "upsert_job", lambda **kwargs: recorded.append(kwargs))

    result = dcp.run_daily_stage(
        date(2026, 6, 6),
        config=dcp.PipelineConfig(service="test"),
        ts_codes=["000001.SZ"],
        tushare_fetcher=lambda *args, **kwargs: pytest.fail("source should not run"),
        akshare_fetcher=lambda *args, **kwargs: pytest.fail("fallback should not run"),
        daily_upserter=lambda *args, **kwargs: pytest.fail("upsert should not run"),
    )

    assert result == {
        "stage": "daily",
        "status": "skipped",
        "reason": "non_trading_day:closed",
    }
    assert recorded[0]["status"] == "skipped"
    assert recorded[0]["source"] == "calendar"


def test_finalize_closed_trading_day_keeps_platform_ready_with_previous_date(monkeypatch):
    _no_db(monkeypatch)
    monkeypatch.setattr(
        dcp,
        "trading_calendar_status",
        lambda service, trade_date: "closed",
    )
    monkeypatch.setattr(
        dcp,
        "fetch_all",
        lambda _conn, _sql, _params=None: [
            {
                "stage": "daily",
                "job_name": "daily_bar",
                "source": "calendar",
                "status": "skipped",
                "error_summary": "non_trading_day:closed",
            }
        ],
    )
    monkeypatch.setattr(dcp, "latest_ready_trade_date", lambda _service: date(2026, 6, 5))

    result = dcp.finalize_pipeline_status(date(2026, 6, 6), config=dcp.PipelineConfig(service="test"))

    assert result["pipeline_status"] == "READY"
    assert result["latest_ready_trade_date"] == date(2026, 6, 5)
    assert result["using_fallback_trade_date"] is True
    assert "non_trading_day_skipped" in result["warnings"]


def test_strategy_trade_date_falls_back_to_latest_ready(monkeypatch):
    calls = []

    @contextmanager
    def fake_connect(_service):
        yield object()

    def fake_fetch_all(_conn, sql, params=None):
        calls.append(params)
        if "WHERE trade_date" in sql:
            return [{"pipeline_status": "NOT_READY"}]
        return [{"trade_date": date(2026, 6, 4)}]

    monkeypatch.setattr(dcp, "connect", fake_connect)
    monkeypatch.setattr(dcp, "fetch_all", fake_fetch_all)

    assert dcp.resolve_strategy_trade_date("20260605", service="test") == "2026-06-04"


def test_selection_resolves_pipeline_ready_date(monkeypatch):
    monkeypatch.setattr(selection, "resolve_strategy_trade_date", lambda trade_date: "2026-06-04")
    monkeypatch.setattr(
        selection,
        "load_feature_matrix",
        lambda trade_date: {
            "CN:SZ:000001": {
                "ret_20d": 0.1,
                "ret_60d": 0.1,
                "amount_20d_avg": 100000000,
                "volatility_20d": 0.01,
                "max_drawdown_20d": -0.01,
            }
        },
    )
    monkeypatch.setattr(
        selection,
        "load_trade_status",
        lambda trade_date: {"CN:SZ:000001": {"is_st": False, "trade_status": "1"}},
    )

    rows = selection.generate_selection("2026-06-05", top_n=1)

    assert rows[0]["trade_date"] == "2026-06-04"


def test_cli_accepts_daily_pipeline_status_command():
    args = build_parser().parse_args(
        ["daily-pipeline", "--date", "20260605", "--stage", "status", "--force"]
    )

    assert args.command == "daily-pipeline"
    assert args.stage == "status"
    assert args.force is True
