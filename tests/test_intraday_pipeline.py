from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime

import pandas as pd

from stock_research import intraday_pipeline as ip
from stock_research.cli import build_parser


@contextmanager
def _fake_connect(_service):
    yield object()


def _no_db(monkeypatch):
    monkeypatch.setattr(ip, "connect", _fake_connect)
    monkeypatch.setattr(ip, "execute", lambda *args, **kwargs: None)
    monkeypatch.setattr(ip, "execute_many", lambda *args, **kwargs: None)


def test_build_intraday_universe_combines_topn_positions_and_watchlist(monkeypatch):
    _no_db(monkeypatch)
    monkeypatch.setattr(ip, "load_previous_topn", lambda **kwargs: [
        {
            "asset_id": "CN:SZ:000001",
            "ts_code": "000001.SZ",
            "stock_name": "Top",
            "rank": 1,
            "score": 9.5,
            "source_type": "previous_topn",
        }
    ])
    monkeypatch.setattr(ip, "load_current_positions", lambda **kwargs: [
        {
            "asset_id": "CN:SH:600000",
            "ts_code": "600000.SH",
            "stock_name": "Holding",
            "position_quantity": 100,
            "position_weight": 0.2,
            "source_type": "current_position",
        }
    ])
    monkeypatch.setattr(ip, "load_previous_watchlist", lambda **kwargs: [
        {
            "asset_id": "CN:SZ:000001",
            "ts_code": "000001.SZ",
            "stock_name": "Top",
            "source_type": "previous_watchlist",
            "source_detail": "default",
        }
    ])

    rows = ip.build_intraday_universe(
        run_date=date(2026, 6, 18),
        previous_trade_date=date(2026, 6, 17),
        config=ip.IntradayConfig(service="test", top_n=20),
        upserter=lambda _service, rows: len(rows),
    )

    assert {row["ts_code"] for row in rows} == {"000001.SZ", "600000.SH"}
    top = next(row for row in rows if row["ts_code"] == "000001.SZ")
    assert sorted(top["source_types"]) == ["previous_topn", "previous_watchlist"]
    holding = next(row for row in rows if row["ts_code"] == "600000.SH")
    assert holding["position_quantity"] == 100


def test_poll_universe_minute5_only_fetches_universe_symbols(monkeypatch):
    _no_db(monkeypatch)
    fetched = []
    monkeypatch.setattr(
        ip,
        "load_intraday_universe_symbols",
        lambda service, run_date: ["000001.SZ", "600000.SH"],
    )

    def fake_fetcher(ts_code, start_date, end_date, timeout_seconds):
        fetched.append(ts_code)
        return [
            {
                "asset_id": ip.ts_code_to_asset_id(ts_code),
                "ts_code": ts_code,
                "trade_time": datetime(2026, 6, 18, 9, 35),
                "trade_date": date(2026, 6, 18),
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
        ]

    result = ip.poll_universe_minute5(
        run_date=date(2026, 6, 18),
        config=ip.IntradayConfig(service="test", max_workers=1, max_retries=1),
        fetcher=fake_fetcher,
        upserter=lambda _service, rows: len(rows),
    )

    assert fetched == ["000001.SZ", "600000.SH"]
    assert result["status"] == "success"
    assert result["rows"] == 2


def test_market_sentiment_counts_snapshot_and_limit_pools(monkeypatch):
    _no_db(monkeypatch)

    class FakeAk:
        @staticmethod
        def stock_zh_a_spot_em():
            return pd.DataFrame(
                [
                    {"代码": "000001", "涨跌幅": 1.2},
                    {"代码": "000002", "涨跌幅": -0.5},
                    {"代码": "600000", "涨跌幅": 0},
                ]
            )

        @staticmethod
        def stock_zt_pool_em(date):
            return pd.DataFrame([{"代码": "000001"}])

        @staticmethod
        def stock_zt_pool_dtgc_em(date):
            return pd.DataFrame([{"代码": "000002"}])

        @staticmethod
        def stock_zt_pool_zbgc_em(date):
            return pd.DataFrame([{"代码": "000003"}, {"代码": "000004"}])

    result = ip.collect_market_sentiment(
        run_date=date(2026, 6, 18),
        config=ip.IntradayConfig(service="test"),
        ak_module=FakeAk,
        upserter=lambda _service, row: 1,
    )

    assert result["up_count"] == 1
    assert result["down_count"] == 1
    assert result["flat_count"] == 1
    assert result["limit_up_count"] == 1
    assert result["limit_down_count"] == 1
    assert result["break_limit_count"] == 2
    assert result["sentiment_state"] in {"HOT", "WARM", "NEUTRAL", "WEAK", "PANIC"}


def test_market_sentiment_failure_records_failed_job(monkeypatch):
    _no_db(monkeypatch)
    monkeypatch.setattr(ip.time, "sleep", lambda _seconds: None)
    recorded = []
    monkeypatch.setattr(ip, "record_intraday_job", lambda **kwargs: recorded.append(kwargs))

    class FailingAk:
        @staticmethod
        def stock_zh_a_spot_em():
            raise TimeoutError("spot unavailable")

    result = ip.collect_market_sentiment(
        run_date=date(2026, 6, 18),
        config=ip.IntradayConfig(service="test", max_retries=2),
        ak_module=FailingAk,
        upserter=lambda _service, row: 1,
    )

    assert result["status"] == "failed"
    assert result["attempt_count"] == 2
    assert recorded[0]["status"] == "failed"
    assert "spot unavailable" in recorded[0]["error_summary"]


def test_cli_accepts_intraday_pipeline_command():
    args = build_parser().parse_args(
        ["intraday-pipeline", "--date", "20260618", "--stage", "universe"]
    )

    assert args.command == "intraday-pipeline"
    assert args.stage == "universe"
