import json
from contextlib import contextmanager
from decimal import Decimal

import pandas as pd
import pytest

from stock_research.dashboard import market_monitor


def test_build_market_monitor_eod_uses_latest_complete_date(monkeypatch):
    monkeypatch.setattr(
        market_monitor,
        "load_platform_summary",
        lambda score_version="manual_v1", top_n=5: {
            "latest_market_date": "2026-06-10",
            "latest_factor_date": "2026-06-10",
            "latest_score_date": "2026-06-10",
            "market_asset_count": 5300,
            "score_asset_count": 3100,
            "factor_count": 42,
            "topn_preview": [
                {
                    "trade_date": "2026-06-10",
                    "asset_id": "000001.SZ",
                    "rank": 1,
                    "score_total": 91.2,
                    "score_version": "manual_v1",
                    "score_components": {},
                }
            ],
        },
    )
    monkeypatch.setattr(
        market_monitor,
        "load_report_links",
        lambda trade_date: [
            {
                "report_type": "daily_topn_report",
                "title": "daily_topn_2026-06-10_manual_v1.md",
                "path": "/reports/topn.md",
                "format": "md",
                "trade_date": trade_date,
            }
        ],
    )
    monkeypatch.setattr(market_monitor, "load_market_emotion_row", lambda trade_date: None)
    monkeypatch.setattr(market_monitor, "load_emotion_stock_lists", lambda trade_date: {})

    payload = market_monitor.build_market_monitor_eod()

    assert payload["trade_date"] == "2026-06-10"
    assert payload["freshness"]["mode"] == "eod"
    assert payload["freshness"]["is_realtime"] is False
    assert payload["coverage"]["market_assets"] == 5300
    assert payload["strategy_signal_summary"]["topn_preview_count"] == 1
    assert payload["generated_reports"][0]["report_type"] == "daily_topn_report"


def test_build_market_monitor_eod_maps_market_emotion_row(monkeypatch):
    monkeypatch.setattr(
        market_monitor,
        "load_platform_summary",
        lambda score_version="manual_v1", top_n=5: {
            "latest_market_date": "2026-06-12",
            "latest_factor_date": "2026-06-12",
            "latest_score_date": "2026-06-12",
            "market_asset_count": 5300,
            "score_asset_count": 3100,
            "factor_count": 42,
            "topn_preview": [],
        },
    )
    monkeypatch.setattr(market_monitor, "load_report_links", lambda trade_date: [])
    monkeypatch.setattr(
        market_monitor,
        "load_market_emotion_row",
        lambda trade_date: {
            "trade_date": "2026-06-12",
            "emotion_score": 73.6,
            "emotion_state": "hot",
            "risk_state": "medium",
            "breadth_score": 68.2,
            "limit_score": 75.4,
            "relay_score": 71.1,
            "feedback_score": 66.8,
            "liquidity_score": 82.0,
            "traded_count": 5207,
            "up_count": 3610,
            "down_count": 1492,
            "strong_up_count": 269,
            "strong_down_count": 55,
            "limit_up_count": 90,
            "limit_down_count": 10,
            "broken_limit_up_count": 55,
            "broken_limit_up_rate": 0.3793,
            "first_board_count": 58,
            "second_board_count": 21,
            "third_board_plus_count": 11,
            "high_board_height": 6,
            "yesterday_limit_up_avg_return": 0.026,
            "yesterday_limit_up_red_rate": 0.7361,
            "yesterday_limit_up_limit_down_rate": 0.026,
            "yesterday_relay_avg_return": 0.018,
            "yesterday_relay_red_rate": 0.615,
            "yesterday_relay_continue_rate": 0.312,
            "yesterday_broken_avg_return": 0.007,
            "yesterday_broken_red_rate": 0.564,
            "yesterday_broken_limit_down_rate": 0.073,
            "total_amount": 1280000000000.0,
            "amount_ratio_5_20": 1.18,
            "style_signal_hint": "growth_favorable",
            "position_budget_hint": "reduced",
        },
    )
    monkeypatch.setattr(market_monitor, "load_emotion_stock_lists", lambda trade_date: {})

    payload = market_monitor.build_market_monitor_eod()

    assert payload["market_emotion"]["summary"] == {
        "score": 73.6,
        "state": "hot",
        "risk_state": "medium",
        "style_signal_hint": "growth_favorable",
        "position_budget_hint": "reduced",
        "status": "available",
    }
    assert payload["market_emotion"]["breadth"]["up_count"] == 3610
    assert payload["market_emotion"]["breadth"]["down_count"] == 1492
    assert payload["market_emotion"]["liquidity"]["amount_ratio_5_20"] == 1.18
    assert payload["market_emotion"]["limit_performance"]["limit_up_count"] == 90
    assert payload["market_emotion"]["profit_effect"]["limit_up_success_rate"] == 0.7361
    assert payload["market_emotion"]["profit_effect"]["limit_up_profit_rate"] == 0.026
    assert payload["market_emotion"]["drawdown_pressure"]["broken_limit_up_rate"] == 0.3793
    assert payload["market_emotion"]["weight_performance"]["status"] == "pending_source"
    assert payload["market_breadth"]["advancers"] == 3610
    assert payload["market_breadth"]["decliners"] == 1492
    assert payload["market_breadth"]["limit_up"] == 90
    assert payload["market_breadth"]["limit_down"] == 10
    assert payload["market_breadth"]["advancing_ratio"] == 3610 / 5207


def test_build_market_monitor_eod_includes_emotion_stock_lists(monkeypatch):
    monkeypatch.setattr(
        market_monitor,
        "load_platform_summary",
        lambda score_version="manual_v1", top_n=5: {
            "latest_market_date": "2026-06-12",
            "latest_factor_date": "2026-06-12",
            "latest_score_date": "2026-06-12",
            "market_asset_count": 5300,
            "score_asset_count": 3100,
            "factor_count": 42,
            "topn_preview": [],
        },
    )
    monkeypatch.setattr(market_monitor, "load_report_links", lambda trade_date: [])
    monkeypatch.setattr(market_monitor, "load_market_emotion_row", lambda trade_date: None)
    monkeypatch.setattr(
        market_monitor,
        "load_emotion_stock_lists",
        lambda trade_date: {
            "auction": [],
            "limit_up": [
                {
                    "tab": "limit_up",
                    "asset_id": "601958.SH",
                    "symbol": "601958",
                    "name": "金钼股份",
                    "amount": 3038000000.0,
                    "pct_chg": 10.02,
                    "board": "main",
                    "limit_up_streak": None,
                }
            ],
            "broken_limit_up": [
                {
                    "tab": "broken_limit_up",
                    "asset_id": "000001.SZ",
                    "symbol": "000001",
                    "name": "平安银行",
                    "amount": 2010000000.0,
                    "pct_chg": 4.3,
                    "board": "main",
                    "limit_up_streak": None,
                }
            ],
            "limit_down": [],
        },
    )

    payload = market_monitor.build_market_monitor_eod()

    stock_lists = payload["emotion_stock_lists"]
    assert stock_lists["limit_up"][0]["name"] == "金钼股份"
    assert stock_lists["limit_up"][0]["amount"] == 3038000000.0
    assert stock_lists["broken_limit_up"][0]["tab"] == "broken_limit_up"
    assert stock_lists["auction_status"] == "pending_source"


def test_build_market_monitor_eod_handles_zero_traded_count_for_legacy_breadth(monkeypatch):
    monkeypatch.setattr(
        market_monitor,
        "load_platform_summary",
        lambda score_version="manual_v1", top_n=5: {
            "latest_market_date": "2026-06-12",
            "latest_factor_date": "2026-06-12",
            "latest_score_date": "2026-06-12",
            "market_asset_count": 0,
            "score_asset_count": 0,
            "factor_count": 0,
            "topn_preview": [],
        },
    )
    monkeypatch.setattr(market_monitor, "load_report_links", lambda trade_date: [])
    monkeypatch.setattr(
        market_monitor,
        "load_market_emotion_row",
        lambda trade_date: {
            "emotion_score": 50,
            "emotion_state": "neutral",
            "risk_state": "medium",
            "traded_count": 0,
            "up_count": 0,
            "down_count": 0,
            "limit_up_count": 0,
            "limit_down_count": 0,
        },
    )
    monkeypatch.setattr(market_monitor, "load_emotion_stock_lists", lambda trade_date: {})

    payload = market_monitor.build_market_monitor_eod()

    assert payload["market_breadth"]["advancers"] == 0
    assert payload["market_breadth"]["decliners"] == 0
    assert payload["market_breadth"]["limit_up"] == 0
    assert payload["market_breadth"]["limit_down"] == 0
    assert payload["market_breadth"]["advancing_ratio"] is None


def test_build_market_emotion_payload_converts_decimal_values_for_json():
    payload = market_monitor.build_market_emotion_payload(
        {
            "emotion_score": Decimal("73.6"),
            "emotion_state": "hot",
            "risk_state": "medium",
            "breadth_score": Decimal("68.0"),
            "traded_count": Decimal("5207"),
            "up_count": Decimal("3610"),
            "down_count": Decimal("1492"),
            "limit_up_count": Decimal("90"),
            "limit_down_count": Decimal("10"),
            "broken_limit_up_rate": Decimal("0.3793"),
            "total_amount": Decimal("1280000000000.0"),
            "amount_ratio_5_20": Decimal("1.18"),
            "yesterday_limit_up_red_rate": Decimal("0.7361"),
            "yesterday_limit_up_avg_return": Decimal("0.026"),
        }
    )

    assert payload["summary"]["score"] == 73.6
    assert isinstance(payload["components"][0]["score"], int)
    assert payload["breadth"]["traded_count"] == 5207
    assert isinstance(payload["breadth"]["traded_count"], int)
    assert payload["liquidity"]["amount_ratio_5_20"] == 1.18
    assert payload["profit_effect"]["limit_up_success_rate"] == 0.7361
    json.dumps(payload)


def test_build_market_emotion_payload_converts_non_finite_decimal_values_for_strict_json():
    payload = market_monitor.build_market_emotion_payload(
        {
            "emotion_score": Decimal("NaN"),
            "emotion_state": "hot",
            "risk_state": "medium",
            "breadth_score": Decimal("Infinity"),
            "broken_limit_up_rate": Decimal("-Infinity"),
        }
    )

    assert payload["summary"]["score"] is None
    assert payload["components"][0]["score"] is None
    assert payload["limit_performance"]["broken_limit_up_rate"] is None
    assert payload["drawdown_pressure"]["broken_limit_up_rate"] is None
    json.dumps(payload, allow_nan=False)


class _SqlStateError(Exception):
    def __init__(self, sqlstate):
        super().__init__(sqlstate or "db error")
        self.sqlstate = sqlstate


@contextmanager
def _fake_connection():
    yield object()


@pytest.mark.parametrize("sqlstate", ["3F000", "42P01"])
def test_load_market_emotion_row_falls_back_for_missing_schema_or_table(
    monkeypatch,
    sqlstate,
):
    def fake_fetch_all(conn, sql, params):
        raise _SqlStateError(sqlstate)

    monkeypatch.setattr(market_monitor, "connect", lambda service: _fake_connection())
    monkeypatch.setattr(market_monitor, "fetch_all", fake_fetch_all)
    monkeypatch.setattr(
        market_monitor,
        "compute_market_emotion_row",
        lambda trade_date, service="research": {"trade_date": trade_date, "emotion_score": 61.5},
    )

    assert market_monitor.load_market_emotion_row("2026-06-12") == {
        "trade_date": "2026-06-12",
        "emotion_score": 61.5,
    }


def test_compute_market_emotion_row_builds_latest_selected_day(monkeypatch):
    market_monitor._compute_market_emotion_row_cached.cache_clear()
    monkeypatch.setattr(
        market_monitor,
        "load_market_emotion_source_frames",
        lambda start_date, end_date, service="research": ("bars", "status"),
    )
    monkeypatch.setattr(
        market_monitor,
        "build_market_emotion_state_from_frames",
        lambda bars, status: pd.DataFrame(
            [
                {"trade_date": "2026-06-10", "emotion_score": 55.0},
                {"trade_date": "2026-06-12", "emotion_score": 72.5},
            ]
        ),
    )

    assert market_monitor.compute_market_emotion_row("2026-06-12") == {
        "trade_date": "2026-06-12",
        "emotion_score": 72.5,
    }
    market_monitor._compute_market_emotion_row_cached.cache_clear()


def test_compute_market_emotion_row_caches_selected_day(monkeypatch):
    calls = 0
    market_monitor._compute_market_emotion_row_cached.cache_clear()

    def fake_load_source_frames(start_date, end_date, service="research"):
        nonlocal calls
        calls += 1
        return pd.DataFrame(), pd.DataFrame()

    monkeypatch.setattr(market_monitor, "load_market_emotion_source_frames", fake_load_source_frames)
    monkeypatch.setattr(
        market_monitor,
        "build_market_emotion_state_from_frames",
        lambda bars, status: pd.DataFrame(
            [
                {"trade_date": "2026-06-10", "emotion_score": 55.0},
            ]
        ),
    )

    assert market_monitor.compute_market_emotion_row("2026-06-10") == {
        "trade_date": "2026-06-10",
        "emotion_score": 55.0,
    }
    assert market_monitor.compute_market_emotion_row("2026-06-10") == {
        "trade_date": "2026-06-10",
        "emotion_score": 55.0,
    }
    assert calls == 1
    market_monitor._compute_market_emotion_row_cached.cache_clear()


@pytest.mark.parametrize("sqlstate", ["42703", None])
def test_load_market_emotion_row_reraises_undefined_column_and_generic_errors(
    monkeypatch,
    sqlstate,
):
    def fake_fetch_all(conn, sql, params):
        raise _SqlStateError(sqlstate)

    monkeypatch.setattr(market_monitor, "connect", lambda service: _fake_connection())
    monkeypatch.setattr(market_monitor, "fetch_all", fake_fetch_all)

    with pytest.raises(_SqlStateError):
        market_monitor.load_market_emotion_row("2026-06-12")


def test_load_emotion_stock_lists_maps_query_rows_and_limits_each_list(monkeypatch):
    captured = {}

    def fake_fetch_all(conn, sql, params):
        captured["sql"] = sql
        captured["params"] = params
        return [
            {
                "asset_id": "601958.SH",
                "symbol": "601958",
                "name": "金钼股份",
                "amount": Decimal("3038000000.0"),
                "pct_chg": Decimal("10.02"),
                "board": "main",
                "is_limit_up": True,
                "is_broken_limit_up": False,
                "is_limit_down": False,
            },
            {
                "asset_id": "000001.SZ",
                "symbol": "000001",
                "name": "平安银行",
                "amount": Decimal("2010000000.5"),
                "pct_chg": Decimal("4.30"),
                "board": "main",
                "is_limit_up": False,
                "is_broken_limit_up": True,
                "is_limit_down": False,
            },
            {
                "asset_id": "300001.SZ",
                "symbol": "300001",
                "name": "特锐德",
                "amount": Decimal("1500000000"),
                "pct_chg": Decimal("-20.0"),
                "board": "gem",
                "is_limit_up": False,
                "is_broken_limit_up": False,
                "is_limit_down": True,
            },
            {
                "asset_id": "600000.SH",
                "symbol": "600000",
                "name": "浦发银行",
                "amount": Decimal("1000000000"),
                "pct_chg": Decimal("10.0"),
                "board": "main",
                "is_limit_up": True,
                "is_broken_limit_up": False,
                "is_limit_down": False,
            },
        ]

    monkeypatch.setattr(market_monitor, "connect", lambda service: _fake_connection())
    monkeypatch.setattr(market_monitor, "fetch_all", fake_fetch_all)

    result = market_monitor.load_emotion_stock_lists("2026-06-12", limit=1)

    assert list(result.keys()) == ["auction", "limit_up", "broken_limit_up", "limit_down"]
    assert result["auction"] == []
    assert result["limit_up"] == [
        {
            "tab": "limit_up",
            "asset_id": "601958.SH",
            "symbol": "601958",
            "name": "金钼股份",
            "amount": 3038000000,
            "pct_chg": 10.02,
            "board": "main",
            "limit_up_streak": None,
        }
    ]
    assert result["broken_limit_up"][0] == {
        "tab": "broken_limit_up",
        "asset_id": "000001.SZ",
        "symbol": "000001",
        "name": "平安银行",
        "amount": 2010000000.5,
        "pct_chg": 4.3,
        "board": "main",
        "limit_up_streak": None,
    }
    assert result["limit_down"][0]["tab"] == "limit_down"
    assert result["limit_down"][0]["asset_id"] == "300001.SZ"
    assert len(result["limit_up"]) == 1
    assert captured["params"] == ["2026-06-12"]
    assert "FROM market_daily_bar b" in captured["sql"]
    assert "JOIN core.asset_status_daily s" in captured["sql"]
    assert "JOIN core.asset_master a" in captured["sql"]
    assert "ORDER BY b.amount DESC NULLS LAST" in captured["sql"]
    json.dumps(result)


def test_load_emotion_stock_lists_falls_back_when_asset_metadata_is_missing(monkeypatch):
    captured = {}

    def fake_fetch_all(conn, sql, params):
        captured["sql"] = sql
        captured["params"] = params
        return [
            {
                "asset_id": "688001.SH",
                "symbol": None,
                "name": None,
                "amount": Decimal("998000000"),
                "pct_chg": Decimal("20.0"),
                "board": None,
                "is_limit_up": True,
                "is_broken_limit_up": False,
                "is_limit_down": False,
            }
        ]

    monkeypatch.setattr(market_monitor, "connect", lambda service: _fake_connection())
    monkeypatch.setattr(market_monitor, "fetch_all", fake_fetch_all)

    result = market_monitor.load_emotion_stock_lists("2026-06-12")

    assert result["limit_up"][0]["asset_id"] == "688001.SH"
    assert result["limit_up"][0]["symbol"] == "688001.SH"
    assert result["limit_up"][0]["name"] == "688001.SH"
    assert result["limit_up"][0]["board"] == ""
    assert "LEFT JOIN core.asset_master a" in captured["sql"]
    assert "COALESCE(a.symbol, b.asset_id)" in captured["sql"]
    assert "COALESCE(a.name, b.asset_id)" in captured["sql"]
    assert captured["params"] == ["2026-06-12"]
    json.dumps(result)


def test_load_emotion_stock_lists_returns_empty_lists_without_trade_date():
    assert market_monitor.load_emotion_stock_lists("") == {
        "auction": [],
        "limit_up": [],
        "broken_limit_up": [],
        "limit_down": [],
    }


def test_build_market_monitor_eod_returns_warning_without_market_date(monkeypatch):
    monkeypatch.setattr(
        market_monitor,
        "load_platform_summary",
        lambda score_version="manual_v1", top_n=5: {
            "latest_market_date": None,
            "latest_factor_date": None,
            "latest_score_date": None,
            "market_asset_count": 0,
            "score_asset_count": 0,
            "factor_count": 0,
            "topn_preview": [],
        },
    )
    monkeypatch.setattr(market_monitor, "load_report_links", lambda trade_date: [])

    payload = market_monitor.build_market_monitor_eod()

    assert payload["trade_date"] == ""
    assert "latest complete market date is unavailable" in payload["warnings"]


def test_build_market_monitor_eod_warns_without_market_date_when_trade_date_explicit(
    monkeypatch,
):
    monkeypatch.setattr(
        market_monitor,
        "load_platform_summary",
        lambda score_version="manual_v1", top_n=5: {
            "latest_market_date": None,
            "latest_factor_date": None,
            "latest_score_date": None,
            "market_asset_count": 0,
            "score_asset_count": 0,
            "factor_count": 0,
            "topn_preview": [],
        },
    )
    monkeypatch.setattr(market_monitor, "load_report_links", lambda trade_date: [])
    monkeypatch.setattr(market_monitor, "load_market_emotion_row", lambda trade_date: None)
    monkeypatch.setattr(market_monitor, "load_emotion_stock_lists", lambda trade_date: {})

    payload = market_monitor.build_market_monitor_eod(trade_date="2026-06-10")

    assert payload["trade_date"] == "2026-06-10"
    assert "latest complete market date is unavailable" in payload["warnings"]


def test_build_market_monitor_eod_warns_when_score_or_factor_dates_differ(monkeypatch):
    monkeypatch.setattr(
        market_monitor,
        "load_platform_summary",
        lambda score_version="manual_v1", top_n=5: {
            "latest_market_date": "2026-06-10",
            "latest_factor_date": "2026-06-08",
            "latest_score_date": "2026-06-09",
            "market_asset_count": 5300,
            "score_asset_count": 3100,
            "factor_count": 42,
            "topn_preview": [],
        },
    )
    monkeypatch.setattr(market_monitor, "load_report_links", lambda trade_date: [])
    monkeypatch.setattr(market_monitor, "load_market_emotion_row", lambda trade_date: None)
    monkeypatch.setattr(market_monitor, "load_emotion_stock_lists", lambda trade_date: {})

    payload = market_monitor.build_market_monitor_eod()

    assert payload["freshness"]["latest_factor_date"] == "2026-06-08"
    assert payload["freshness"]["latest_score_date"] == "2026-06-09"
    assert (
        "latest score date 2026-06-09 differs from market monitor trade date 2026-06-10"
        in payload["warnings"]
    )
    assert (
        "latest factor date 2026-06-08 differs from market monitor trade date 2026-06-10"
        in payload["warnings"]
    )


def test_build_market_monitor_eod_uses_historical_mode_for_explicit_trade_date(monkeypatch):
    requested_top_scores: list[tuple[str, str, int]] = []
    monkeypatch.setattr(
        market_monitor,
        "load_platform_summary",
        lambda score_version="manual_v1", top_n=5: {
            "latest_market_date": "2026-06-11",
            "latest_factor_date": "2026-06-11",
            "latest_score_date": "2026-06-11",
            "market_asset_count": 5300,
            "score_asset_count": 3100,
            "factor_count": 42,
            "topn_preview": [
                {
                    "trade_date": "2026-06-11",
                    "asset_id": "LATEST.SZ",
                    "rank": 1,
                    "score_total": 99.0,
                    "score_version": "manual_v1",
                    "score_components": {},
                }
            ],
        },
    )
    monkeypatch.setattr(market_monitor, "load_report_links", lambda trade_date: [])
    monkeypatch.setattr(market_monitor, "load_market_emotion_row", lambda trade_date: None)
    monkeypatch.setattr(market_monitor, "load_emotion_stock_lists", lambda trade_date: {})

    def fake_load_top_scores(trade_date: str, score_version: str, top_n: int):
        requested_top_scores.append((trade_date, score_version, top_n))
        return [
            {
                "trade_date": trade_date,
                "asset_id": "HIST.SZ",
                "rank": 1,
                "score_total": 88.0,
                "score_version": score_version,
                "score_components": {},
            }
        ]

    monkeypatch.setattr(
        market_monitor,
        "load_top_scores_for_dashboard",
        fake_load_top_scores,
        raising=False,
    )

    payload = market_monitor.build_market_monitor_eod(trade_date="2026-06-10")

    assert payload["trade_date"] == "2026-06-10"
    assert payload["freshness"]["label"] == "Historical EOD"
    assert requested_top_scores == [("2026-06-10", "manual_v1", 5)]
    assert payload["strategy_signal_summary"]["topn_preview"][0]["asset_id"] == "HIST.SZ"
    assert not any("differs from market monitor trade date" in warning for warning in payload["warnings"])
