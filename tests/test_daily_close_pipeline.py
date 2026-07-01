from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime

import pytest

from stock_research import daily_close_pipeline as dcp
from stock_research import selection


@contextmanager
def _fake_connect(_service):
    yield object()


def _no_db(monkeypatch):
    monkeypatch.setattr(dcp, "connect", _fake_connect)
    monkeypatch.setattr(dcp, "execute", lambda *args, **kwargs: None)
    monkeypatch.setattr(dcp, "execute_many", lambda *args, **kwargs: None)


def test_daily_close_schema_migrates_market_monitor_status_column():
    assert "market_monitor_status text NOT NULL DEFAULT 'skipped'" in dcp.DAILY_CLOSE_PIPELINE_SQL
    assert "ALTER TABLE ops.daily_pipeline_status" in dcp.DAILY_CLOSE_PIPELINE_SQL


def test_load_data_status_for_dashboard_includes_market_monitor_status(monkeypatch):
    _no_db(monkeypatch)

    def fake_fetch_all(_conn, _sql, _params=None):
        return [
            {
                "trade_date": date(2026, 6, 26),
                "pipeline_status": "DEGRADED_READY",
                "daily_status": "partial_success",
                "minute5_status": "partial_success",
                "market_monitor_status": "success",
                "deps_status": "success",
                "latest_ready_trade_date": date(2026, 6, 26),
                "using_fallback_trade_date": False,
                "warnings": [],
                "failed_jobs": [],
                "updated_at": datetime(2026, 6, 26, 20, 0),
            }
        ]

    monkeypatch.setattr(dcp, "fetch_all", fake_fetch_all)

    result = dcp.load_data_status_for_dashboard("test", date(2026, 6, 26))

    assert result["market_monitor_status"] == "success"


def test_market_emotion_schema_adds_missing_columns(monkeypatch):
    captured = []
    monkeypatch.setattr(dcp, "connect", _fake_connect)
    monkeypatch.setattr(dcp, "execute", lambda _conn, sql, params=None: captured.append(sql))

    dcp.ensure_market_emotion_state_daily_table("test")

    sql = "\n".join(captured)
    assert "ALTER TABLE research.market_emotion_state_daily" in sql
    assert "ADD COLUMN IF NOT EXISTS total_amount numeric" in sql
    assert "ADD COLUMN IF NOT EXISTS emotion_state text" in sql


def test_daily_stage_does_not_fallback_to_akshare_when_tushare_has_missing_symbols(monkeypatch):
    _no_db(monkeypatch)
    monkeypatch.setattr(dcp.time, "sleep", lambda _seconds: None)
    captured = {"upserted": []}
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

    def fake_upsert(_service, rows):
        captured["upserted"] = rows
        return len(rows)

    result = dcp.run_daily_stage(
        trade_date,
        config=config,
        ts_codes=["000001.SZ", "600000.SH"],
        tushare_fetcher=fake_tushare_fetcher,
        derived_adjusted_fetcher=lambda *args, **kwargs: [],
        tushare_adjusted_fetcher=lambda *args, **kwargs: [],
        akshare_fetcher=lambda *args, **kwargs: pytest.fail("akshare fallback should not run"),
        daily_upserter=fake_upsert,
    )

    assert result["status"] == "partial_success"
    assert [row["adjust_type"] for row in captured["upserted"]] == [
        "raw",
        "qfq",
        "hfq",
    ]
    assert [row["source"] for row in captured["upserted"]] == [
        "tushare",
        "tushare",
        "tushare",
    ]
    assert result["quality"]["expected_count"] == 6
    assert result["quality"]["actual_count"] == 3
    assert result["quality"]["missing_symbols"] == [
        "600000.SH:hfq",
        "600000.SH:qfq",
        "600000.SH:raw",
    ]


def test_daily_stage_does_not_fallback_to_akshare_for_remaining_adjusted_gaps(monkeypatch):
    _no_db(monkeypatch)
    monkeypatch.setattr(dcp.time, "sleep", lambda _seconds: None)
    captured = {"upserted": []}
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
            }
        ]

    def fake_tushare_adjusted_fetcher(
        trade_date, token, timeout_seconds, ts_codes, adjust_types, max_workers
    ):
        assert ts_codes == ["000001.SZ", "600000.SH"]
        assert tuple(adjust_types) == ("hfq", "qfq")
        return [
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
            },
        ]

    result = dcp.run_daily_stage(
        trade_date,
        config=config,
        ts_codes=["000001.SZ", "600000.SH"],
        tushare_fetcher=fake_tushare_fetcher,
        derived_adjusted_fetcher=lambda *args, **kwargs: [],
        tushare_adjusted_fetcher=fake_tushare_adjusted_fetcher,
        akshare_fetcher=lambda *args, **kwargs: pytest.fail("akshare fallback should not run"),
        daily_upserter=lambda _service, rows: captured.update(upserted=rows) or len(rows),
    )

    assert result["status"] == "partial_success"
    assert result["quality"]["expected_count"] == 6
    assert result["quality"]["actual_count"] == 3
    assert result["quality"]["missing_symbols"] == [
        "600000.SH:hfq",
        "600000.SH:qfq",
        "600000.SH:raw",
    ]


def test_derive_adjusted_daily_rows_uses_latest_local_factors(monkeypatch):
    monkeypatch.setattr(
        dcp,
        "load_latest_adjustment_factors",
        lambda service, ts_codes, before_date: {
            "000001.SZ": {"qfq": 1.1, "hfq": 2.0}
        },
    )

    rows = dcp.derive_adjusted_daily_rows(
        "test",
        trade_date=date(2026, 6, 18),
        raw_rows=[
            {
                "ts_code": "000001.SZ",
                "asset_id": "CN:SZ:000001",
                "trade_date": date(2026, 6, 18),
                "adjust_type": "raw",
                "open": 10,
                "high": 11,
                "low": 9,
                "close": 10,
                "preclose": 9.8,
                "volume": 100,
                "amount": 1000,
                "source": "tushare",
            }
        ],
        ts_codes=["000001.SZ"],
        adjust_types=("qfq", "hfq"),
    )

    by_adjust = {row["adjust_type"]: row for row in rows}
    assert by_adjust["qfq"]["close"] == 11.0
    assert by_adjust["hfq"]["close"] == 20.0
    assert by_adjust["hfq"]["source"] == "derived:tushare_raw_latest_factor"


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


def test_tushare_adjusted_daily_rows_use_batch_adj_factor(monkeypatch):
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
                    }
                ]
            )

        def adj_factor(self, trade_date):
            return Frame([{"ts_code": "000001.SZ", "adj_factor": 2.0}])

    class Tushare:
        @staticmethod
        def pro_api(token):
            return Pro()

        @staticmethod
        def pro_bar(*args, **kwargs):
            raise AssertionError("pro_bar should not be called for daily adjusted batch")

    monkeypatch.setitem(__import__("sys").modules, "tushare", Tushare)

    rows = dcp.fetch_tushare_adjusted_daily_rows(
        date(2026, 6, 18),
        token="token",
        timeout_seconds=5,
        ts_codes=["000001.SZ"],
        adjust_types=("qfq", "hfq"),
    )

    by_adjust = {row["adjust_type"]: row for row in rows}
    assert by_adjust["qfq"]["close"] == 10.0
    assert by_adjust["hfq"]["close"] == 20.0


def test_minute5_stage_records_single_symbol_failure_without_failing_batch(monkeypatch):
    _no_db(monkeypatch)
    monkeypatch.setattr(dcp.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(dcp, "baostock_login_or_raise", lambda: None)
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
                        "source": "baostock",
                    }
                )
        return rows

    monkeypatch.setattr(dcp, "record_failed_symbol", fake_record_failed_symbol)
    result = dcp.run_minute5_stage(
        date(2026, 6, 5),
        config=config,
        ts_codes=["600001.SH", "600000.SH"],
        baostock_fetcher=fake_fetcher,
        upserter=lambda _service, rows: len(rows),
    )

    assert result["status"] == "partial_success"
    assert result["failed_symbols"] == ["600000.SH"]
    assert failed_symbols == ["600000.SH"]


def test_split_minute5_sources_routes_sh_and_sz_to_separate_baostock_workers_and_ignores_bj():
    result = dcp.split_minute5_sources(["600000.SH", "000001.SZ", "920000.BJ"])

    assert result == {
        "baostock_sh": ["600000.SH"],
        "baostock_sz": ["000001.SZ"],
    }


def test_fetch_baostock_minute5_rows_uses_call_with_timeout(monkeypatch):
    calls = {}

    def fake_query(code, start_date, end_date, freq, adjust_type, timeout_seconds=None):
        calls["query"] = {
            "code": code,
            "start_date": start_date,
            "end_date": end_date,
            "freq": freq,
            "adjust_type": adjust_type,
            "timeout_seconds": timeout_seconds,
        }
        return [{"ts_code": "600000.SH"}]

    def fake_timeout(func, timeout_value, *args, **kwargs):
        calls["timeout_seconds"] = timeout_value
        return func(*args, **kwargs)

    monkeypatch.setattr(dcp, "query_baostock_minute_rows", fake_query)
    monkeypatch.setattr(
        dcp,
        "baostock_minute_market_row",
        lambda row, freq, adjust_type: {
            "asset_id": "CN:SH:600000",
            "ts_code": "600000.SH",
            "trade_time": datetime(2026, 6, 5, 9, 35),
            "trade_date": date(2026, 6, 5),
            "freq": freq,
            "adjust_type": adjust_type,
            "open": 1,
            "high": 1,
            "low": 1,
            "close": 1,
            "volume": 1,
            "amount": 1,
            "source": "baostock",
        },
    )
    monkeypatch.setattr(dcp, "call_with_timeout", fake_timeout)

    rows = dcp.fetch_baostock_minute5_rows(
        "600000.SH",
        start_date=date(2026, 6, 1),
        end_date=date(2026, 6, 5),
        timeout_seconds=7,
    )

    assert calls["timeout_seconds"] == 7
    assert calls["query"]["code"] == "sh.600000"
    assert calls["query"]["timeout_seconds"] == 7
    assert rows[0]["source"] == "baostock"


def test_call_with_timeout_shuts_down_executor_without_waiting_on_timeout(monkeypatch):
    calls = {}

    class FakeFuture:
        def result(self, timeout):
            calls["timeout"] = timeout
            raise TimeoutError("timed out")

        def cancel(self):
            calls["cancelled"] = True
            return True

    class FakeExecutor:
        def submit(self, func, *args, **kwargs):
            calls["submitted"] = (func, args, kwargs)
            return FakeFuture()

        def shutdown(self, wait=True, cancel_futures=False):
            calls["shutdown"] = (wait, cancel_futures)

    monkeypatch.setattr(
        dcp.concurrent.futures,
        "ThreadPoolExecutor",
        lambda max_workers=1: FakeExecutor(),
    )

    with pytest.raises(TimeoutError):
        dcp.call_with_timeout(lambda: None, 7)

    assert calls["timeout"] == 7
    assert calls["cancelled"] is True
    assert calls["shutdown"] == (False, True)


def test_retry_failed_source_plan_uses_baostock_for_all_missing_symbols():
    config = dcp.PipelineConfig(
        max_workers_akshare_minute5=2,
        max_workers_baostock_minute5=2,
    )

    plan = dcp.build_retry_failed_source_plan(
        ["600000.SH", "000001.SZ"],
        config=config,
    )

    assert plan == [
        ("baostock_sh", ["600000.SH"], 1),
        ("baostock_sz", ["000001.SZ"], 1),
    ]


def test_retry_failed_stage_runs_baostock_exchange_rescue_inline(monkeypatch):
    _no_db(monkeypatch)
    monkeypatch.setattr(dcp.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        dcp,
        "load_latest_minute5_missing_symbols",
        lambda _service, _trade_date: ["600000.SH", "000001.SZ"],
    )
    calls = []
    monkeypatch.setattr(
        dcp,
        "fetch_baostock_minute5_rows",
        lambda ts_code, start_date, end_date, timeout_seconds: calls.append(ts_code) or [
            {
                "asset_id": f"asset:{ts_code}",
                "ts_code": ts_code,
                "trade_time": datetime(2026, 6, 5, 9, 35),
                "trade_date": date(2026, 6, 5),
                "freq": "5min",
                "adjust_type": "raw",
                "open": 1,
                "high": 1,
                "low": 1,
                "close": 1,
                "volume": 1,
                "amount": 1,
                "source": "baostock",
            }
        ],
    )
    monkeypatch.setattr(
        dcp,
        "inspect_minute5_quality_from_db",
        lambda _service, expected_ts_codes, _trade_date: {
            "status": "pass",
            "expected_count": len(expected_ts_codes),
            "actual_count": len(expected_ts_codes),
            "missing_symbols": [],
            "abnormal_symbols": [],
            "check_summary": "minute5 covered",
        },
    )
    monkeypatch.setattr(dcp, "upsert_quality", lambda **_kwargs: None)
    monkeypatch.setattr(dcp, "upsert_job", lambda **_kwargs: None)
    monkeypatch.setattr(dcp, "mark_failed_symbol_success", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(dcp, "load_active_ts_codes", lambda _service, _trade_date: ["600000.SH", "000001.SZ"])

    class RaisingExecutor:
        def __init__(self, *args, **kwargs):
            raise AssertionError("thread pool should not be used for single-worker exchange rescue")

    monkeypatch.setattr(dcp.concurrent.futures, "ThreadPoolExecutor", RaisingExecutor)

    result = dcp.run_retry_failed_stage(
        date(2026, 6, 5),
        config=dcp.PipelineConfig(
            service="test",
            max_retries=1,
            max_workers_baostock_minute5=2,
        ),
        upserter=lambda _service, rows: len(rows),
    )

    assert result["status"] == "success"
    assert result["rows"] == 2
    assert calls == ["600000.SH", "000001.SZ"]


def test_minute5_stage_runs_exchange_split_sources(monkeypatch):
    _no_db(monkeypatch)
    monkeypatch.setattr(dcp.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(dcp, "baostock_login_or_raise", lambda: None)
    recorded_jobs = []
    monkeypatch.setattr(dcp, "upsert_job", lambda **kwargs: recorded_jobs.append(kwargs))
    monkeypatch.setattr(dcp, "record_failed_symbol", lambda **_kwargs: None)
    config = dcp.PipelineConfig(
        service="test",
        max_retries=1,
        max_workers_baostock_minute5=2,
        minute5_min_coverage_ratio=0.5,
        force_non_trading_day=True,
    )

    def rows_for(ts_code: str, source: str):
        rows = []
        for hour in [9, 10, 11, 13, 14]:
            for minute in [0, 5, 10, 15, 20, 25, 30, 35, 40]:
                rows.append(
                    {
                        "asset_id": f"asset:{ts_code}",
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
                        "source": source,
                    }
                )
        return rows

    def fake_baostock(ts_code, start_date, end_date, timeout_seconds):
        return rows_for(ts_code, "baostock")

    result = dcp.run_minute5_stage(
        date(2026, 6, 5),
        config=config,
        ts_codes=["600000.SH", "000001.SZ"],
        baostock_fetcher=fake_baostock,
        upserter=lambda _service, rows: len(rows),
    )

    finished = [job for job in recorded_jobs if job["status"] == "success"]
    assert result["status"] == "success"
    assert result["source_symbols"] == {"baostock_sh": 1, "baostock_sz": 1}
    assert {job["source"] for job in finished} == {"baostock_sh", "baostock_sz"}


def test_minute5_stage_runs_baostock_globally_serial_without_parallel_source_executors(monkeypatch):
    _no_db(monkeypatch)
    monkeypatch.setattr(dcp.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(dcp, "baostock_login_or_raise", lambda: None)
    monkeypatch.setattr(dcp, "upsert_job", lambda **_kwargs: None)
    monkeypatch.setattr(dcp, "record_failed_symbol", lambda **_kwargs: None)

    class RaisingProcessPool:
        def __init__(self, *args, **kwargs):
            raise AssertionError("process pool should not be used for global serial baostock minute5")

    class SelectiveThreadPool:
        def __init__(self, max_workers=1, *args, **kwargs):
            if max_workers != 1:
                raise AssertionError("thread pool >1 should not be used for global serial baostock minute5")
            self.max_workers = max_workers

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def submit(self, fn, *args, **kwargs):
            class ImmediateFuture:
                def result(self_inner):
                    return fn(*args, **kwargs)

            return ImmediateFuture()

    monkeypatch.setattr(dcp.concurrent.futures, "ProcessPoolExecutor", RaisingProcessPool)
    monkeypatch.setattr(dcp.concurrent.futures, "ThreadPoolExecutor", SelectiveThreadPool)
    monkeypatch.setattr(
        dcp.concurrent.futures,
        "as_completed",
        lambda futures: futures,
    )

    seen = []

    def fake_baostock(ts_code, start_date, end_date, timeout_seconds):
        seen.append(ts_code)
        return [
            {
                "asset_id": f"asset:{ts_code}",
                "ts_code": ts_code,
                "trade_time": datetime(2026, 6, 5, 9, 35),
                "trade_date": date(2026, 6, 5),
                "freq": "5min",
                "adjust_type": "raw",
                "open": 1,
                "high": 1,
                "low": 1,
                "close": 1,
                "volume": 1,
                "amount": 1,
                "source": "baostock",
            }
        ]

    result = dcp.run_minute5_stage(
        date(2026, 6, 5),
        config=dcp.PipelineConfig(service="test", max_retries=1, force_non_trading_day=True),
        ts_codes=["600000.SH", "000001.SZ"],
        baostock_fetcher=fake_baostock,
        upserter=lambda _service, rows: len(rows),
    )

    assert result["status"] == "success"
    assert seen == ["600000.SH", "000001.SZ"]


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


def test_finalize_pipeline_status_uses_quality_threshold_over_old_failed_jobs(monkeypatch):
    _no_db(monkeypatch)
    jobs = [
        {
            "stage": "daily",
            "job_name": "daily_bar",
            "source": "tushare",
            "status": "failed",
            "error_summary": "old source failure",
        },
        {
            "stage": "minute5",
            "job_name": "minute5_bar",
            "source": "akshare",
            "status": "failed",
            "error_summary": "old source failure",
        },
        {"stage": "deps", "job_name": "daily_factor_pipeline", "source": "internal", "status": "success"},
    ]
    quality = [
        {
            "dataset_name": "daily_bar",
            "expected_count": 15627,
            "actual_count": 15564,
            "missing_count": 63,
            "abnormal_count": 0,
        },
        {
            "dataset_name": "minute5_bar",
            "expected_count": 5209,
            "actual_count": 5188,
            "missing_count": 21,
            "abnormal_count": 0,
        },
    ]

    def fake_fetch_all(_conn, sql, _params=None):
        if "FROM ops.daily_pipeline_quality" in sql:
            return quality
        return jobs

    monkeypatch.setattr(dcp, "fetch_all", fake_fetch_all)
    monkeypatch.setattr(dcp, "latest_ready_trade_date", lambda _service: date(2026, 6, 17))

    result = dcp.finalize_pipeline_status(
        date(2026, 6, 18),
        config=dcp.PipelineConfig(service="test", external_data_max_quality_gap_ratio=0.01),
    )

    assert result["pipeline_status"] == "DEGRADED_READY"
    assert result["daily_status"] == "partial_success"
    assert result["minute5_status"] == "partial_success"
    assert result["latest_ready_trade_date"] == date(2026, 6, 18)


def test_finalize_pipeline_status_blocks_ready_when_market_monitor_failed(monkeypatch):
    _no_db(monkeypatch)
    jobs = [
        {"stage": "daily", "job_name": "daily_bar", "source": "mixed", "status": "success"},
        {"stage": "minute5", "job_name": "minute5_bar", "source": "baostock_sh", "status": "success"},
        {"stage": "minute5", "job_name": "minute5_bar", "source": "baostock_sz", "status": "success"},
        {"stage": "market_monitor", "job_name": "market_monitor_eod", "source": "internal", "status": "failed"},
        {"stage": "deps", "job_name": "daily_factor_pipeline", "source": "internal", "status": "success"},
    ]

    def fake_fetch_all(_conn, sql, _params=None):
        if "FROM ops.daily_pipeline_quality" in sql:
            return []
        return jobs

    monkeypatch.setattr(dcp, "fetch_all", fake_fetch_all)
    monkeypatch.setattr(dcp, "latest_ready_trade_date", lambda _service: date(2026, 6, 25))

    result = dcp.finalize_pipeline_status(
        date(2026, 6, 26),
        config=dcp.PipelineConfig(service="test"),
    )

    assert result["pipeline_status"] == "NOT_READY"
    assert result["latest_ready_trade_date"] == date(2026, 6, 25)
    assert result["using_fallback_trade_date"] is True
    assert result["failed_jobs"][0]["stage"] == "market_monitor"


def test_upsert_market_emotion_state_daily_persists_computed_row(monkeypatch):
    captured = []
    monkeypatch.setattr(dcp, "connect", _fake_connect)
    monkeypatch.setattr(dcp, "execute", lambda _conn, sql, params=None: captured.append((sql, params)))

    from stock_research.dashboard import market_monitor

    def fake_compute_market_emotion_row(trade_date, service):
        assert trade_date == "2026-06-26"
        assert service == "test"
        row = {}
        for column in dcp.DAILY_OUTPUT_COLUMNS:
            if column == "trade_date":
                row[column] = trade_date
            elif column in {"emotion_state", "risk_state", "style_signal_hint", "position_budget_hint"}:
                row[column] = "ok"
            else:
                row[column] = 1
        return row

    monkeypatch.setattr(
        market_monitor,
        "compute_market_emotion_row",
        fake_compute_market_emotion_row,
    )

    rows = dcp.upsert_market_emotion_state_daily("2026-06-26", service="test")

    assert rows == 1
    assert any("CREATE TABLE IF NOT EXISTS research.market_emotion_state_daily" in sql for sql, _ in captured)
    insert_payload = captured[-1][1]
    assert insert_payload["trade_date"] == "2026-06-26"
    assert insert_payload["total_amount"] == 1
    assert insert_payload["emotion_state"] == "ok"


def test_market_monitor_stage_builds_sources_and_records_job(monkeypatch):
    _no_db(monkeypatch)
    calls = []
    recorded = []
    trade_date = date(2026, 6, 26)

    monkeypatch.setattr(
        dcp,
        "should_skip_for_holiday",
        lambda service, trade_date, force=False: (False, "open"),
    )
    monkeypatch.setattr(
        dcp,
        "sync_index_daily_bars",
        lambda start_date, end_date, service: calls.append(
            ("sync_index_daily_bars", start_date, end_date, service)
        ) or 7,
    )
    monkeypatch.setattr(
        dcp,
        "build_asset_status_daily_for_service",
        lambda start_date, end_date, adjust_type, service: calls.append(
            ("build_asset_status_daily_for_service", start_date, end_date, adjust_type, service)
        ),
    )
    monkeypatch.setattr(
        dcp,
        "build_industry_daily_bars_for_service",
        lambda start_date, end_date, industry_system, adjust_type, service: calls.append(
            (
                "build_industry_daily_bars_for_service",
                start_date,
                end_date,
                industry_system,
                adjust_type,
                service,
            )
        ),
    )
    monkeypatch.setattr(
        dcp,
        "build_concept_daily_bars_for_service",
        lambda start_date, end_date, concept_system, adjust_type, service: calls.append(
            (
                "build_concept_daily_bars_for_service",
                start_date,
                end_date,
                concept_system,
                adjust_type,
                service,
            )
        ),
    )
    monkeypatch.setattr(
        dcp,
        "upsert_market_emotion_state_daily",
        lambda trade_date, service: calls.append(("upsert_market_emotion_state_daily", trade_date, service)) or 1,
    )
    monkeypatch.setattr(
        dcp,
        "check_market_monitor_sources",
        lambda trade_date, service: {
            "status": "success",
            "emotion_rows": 1,
            "index_rows": 5,
            "industry_rows": 85,
            "fund_flow_rows": 85,
        },
    )
    monkeypatch.setattr(dcp, "upsert_job", lambda **kwargs: recorded.append(kwargs))

    result = dcp.run_market_monitor_stage(
        trade_date,
        config=dcp.PipelineConfig(service="test", force_non_trading_day=True),
    )

    assert result == {
        "stage": "market_monitor",
        "status": "success",
        "rows": 178,
        "sources": {
            "emotion_rows": 1,
            "fund_flow_rows": 85,
            "index_rows": 5,
            "industry_rows": 85,
            "status": "success",
        },
    }
    assert calls == [
        ("sync_index_daily_bars", "2026-06-26", "2026-06-26", "test"),
        ("build_asset_status_daily_for_service", "2026-06-26", "2026-06-26", "qfq", "test"),
        ("build_industry_daily_bars_for_service", "2026-06-26", "2026-06-26", "csrc", "qfq", "test"),
        ("build_concept_daily_bars_for_service", "2026-06-26", "2026-06-26", "ths", "qfq", "test"),
        ("upsert_market_emotion_state_daily", "2026-06-26", "test"),
    ]
    assert recorded[0]["stage"] == "market_monitor"
    assert recorded[0]["job_name"] == "market_monitor_eod"
    assert recorded[0]["status"] == "success"
    assert recorded[0]["rows_inserted"] == 178


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


def test_daily_pipeline_parser_accepts_status_command():
    args = dcp.build_arg_parser().parse_args(
        ["--date", "20260605", "--stage", "status", "--force"]
    )

    assert args.stage == "status"
    assert args.force is True


def test_daily_pipeline_parser_accepts_market_monitor_stage():
    args = dcp.build_arg_parser().parse_args(
        ["--date", "20260605", "--stage", "market_monitor", "--force"]
    )

    assert args.stage == "market_monitor"
    assert args.force is True
