import pandas as pd
import pytest

import stock_research.market_emotion_state_v1 as market_emotion_state_v1
from stock_research.market_emotion_state_v1 import (
    build_market_emotion_state_from_frames,
    load_market_emotion_source_frames,
    run_market_emotion_state_v1_backfill,
    write_market_emotion_outputs,
)


def _sample_bars() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "trade_date": "2026-01-02",
                "asset_id": "A",
                "close": 11.0,
                "high": 11.0,
                "pct_chg": 10.0,
                "amount": 100.0,
            },
            {
                "trade_date": "2026-01-02",
                "asset_id": "B",
                "close": 9.0,
                "high": 11.0,
                "pct_chg": -2.0,
                "amount": 90.0,
            },
            {
                "trade_date": "2026-01-02",
                "asset_id": "C",
                "close": 10.5,
                "high": 10.5,
                "pct_chg": 5.0,
                "amount": 80.0,
            },
            {
                "trade_date": "2026-01-03",
                "asset_id": "A",
                "close": 12.1,
                "high": 12.1,
                "pct_chg": 10.0,
                "amount": 120.0,
            },
            {
                "trade_date": "2026-01-03",
                "asset_id": "B",
                "close": 10.0,
                "high": 10.0,
                "pct_chg": 1.0,
                "amount": 95.0,
            },
            {
                "trade_date": "2026-01-03",
                "asset_id": "C",
                "close": 9.4,
                "high": 11.5,
                "pct_chg": -10.0,
                "amount": 85.0,
            },
        ]
    )


def _sample_status() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "trade_date": "2026-01-02",
                "asset_id": "A",
                "is_trade": True,
                "is_st": False,
                "is_suspended": False,
                "is_limit_up": True,
                "is_limit_down": False,
                "limit_up_price": 11.0,
                "limit_down_price": 9.0,
            },
            {
                "trade_date": "2026-01-02",
                "asset_id": "B",
                "is_trade": True,
                "is_st": False,
                "is_suspended": False,
                "is_limit_up": False,
                "is_limit_down": False,
                "limit_up_price": 11.0,
                "limit_down_price": 9.0,
            },
            {
                "trade_date": "2026-01-02",
                "asset_id": "C",
                "is_trade": True,
                "is_st": False,
                "is_suspended": False,
                "is_limit_up": False,
                "is_limit_down": False,
                "limit_up_price": 11.0,
                "limit_down_price": 9.0,
            },
            {
                "trade_date": "2026-01-03",
                "asset_id": "A",
                "is_trade": True,
                "is_st": False,
                "is_suspended": False,
                "is_limit_up": True,
                "is_limit_down": False,
                "limit_up_price": 12.1,
                "limit_down_price": 9.9,
            },
            {
                "trade_date": "2026-01-03",
                "asset_id": "B",
                "is_trade": True,
                "is_st": False,
                "is_suspended": False,
                "is_limit_up": False,
                "is_limit_down": False,
                "limit_up_price": 11.0,
                "limit_down_price": 9.0,
            },
            {
                "trade_date": "2026-01-03",
                "asset_id": "C",
                "is_trade": True,
                "is_st": False,
                "is_suspended": False,
                "is_limit_up": False,
                "is_limit_down": True,
                "limit_up_price": 11.5,
                "limit_down_price": 9.4,
            },
        ]
    )


def test_market_emotion_calculates_relay_broken_board_and_feedback() -> None:
    result = build_market_emotion_state_from_frames(_sample_bars(), _sample_status())

    day1 = result[result["trade_date"].eq("2026-01-02")].iloc[0]
    assert day1["broken_limit_up_count"] == 1
    assert day1["broken_limit_up_rate"] == pytest.approx(0.5)

    day2 = result[result["trade_date"].eq("2026-01-03")].iloc[0]
    assert day2["limit_up_count"] == 1
    assert day2["limit_down_count"] == 1
    assert day2["second_board_count"] == 1
    assert day2["high_board_height"] == 2
    assert day2["yesterday_limit_up_avg_return"] == pytest.approx(0.10)
    assert day2["yesterday_limit_up_red_rate"] == pytest.approx(1.0)
    assert day2["yesterday_relay_avg_return"] == pytest.approx(0.0)
    assert day2["yesterday_broken_avg_return"] == pytest.approx(0.01)


def test_market_emotion_score_is_clipped_and_risk_can_be_high_when_score_is_hot() -> None:
    daily = pd.DataFrame(
        [
            {
                "trade_date": "2026-01-05",
                "traded_count": 100,
                "up_count": 80,
                "down_count": 20,
                "strong_up_count": 50,
                "strong_down_count": 5,
                "limit_up_count": 40,
                "limit_down_count": 1,
                "broken_limit_up_count": 30,
                "broken_limit_up_rate": 0.75,
                "first_board_count": 30,
                "second_board_count": 8,
                "third_board_plus_count": 2,
                "high_board_height": 4,
                "yesterday_limit_up_avg_return": 0.02,
                "yesterday_limit_up_red_rate": 0.70,
                "yesterday_limit_up_limit_down_rate": 0.0,
                "yesterday_relay_avg_return": 0.01,
                "yesterday_relay_red_rate": 0.60,
                "yesterday_relay_continue_rate": 0.20,
                "yesterday_broken_avg_return": -0.02,
                "yesterday_broken_red_rate": 0.40,
                "yesterday_broken_limit_down_rate": 0.05,
                "total_amount": 100000.0,
                "amount_ratio_5_20": 1.2,
            }
        ]
    )

    scored = market_emotion_state_v1._score_daily(daily)

    assert 0.0 <= scored.iloc[0]["emotion_score"] <= 100.0
    assert scored.iloc[0]["emotion_state"] in {"hot", "euphoria"}
    assert scored.iloc[0]["risk_state"] == "high"


def test_write_market_emotion_outputs_csv_report_and_mid_trend_breakdown(tmp_path) -> None:
    result = build_market_emotion_state_from_frames(_sample_bars(), _sample_status())
    equity = pd.DataFrame(
        [
            {"date": "2026-01-02", "variant_name": "base", "net_return": 0.01, "drawdown": 0.0},
            {"date": "2026-01-03", "variant_name": "base", "net_return": -0.02, "drawdown": -0.02},
        ]
    )

    paths = write_market_emotion_outputs(result, output_dir=tmp_path, mid_trend_equity=equity)

    assert paths["daily_path"].exists()
    assert paths["report_path"].exists()
    assert paths["distribution_path"].exists()
    assert paths["year_path"].exists()
    assert paths["mid_trend_state_breakdown_path"].exists()
    assert "market_emotion_state_daily.csv" in str(paths["daily_path"])
    assert "Market Emotion State V1" in paths["report_path"].read_text(encoding="utf-8")


def test_load_market_emotion_source_frames_queries_daily_bars_and_status(monkeypatch) -> None:
    calls = []

    class _Context:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_connect(service):
        calls.append(("service", service))
        return _Context()

    def fake_fetch_all(_conn, sql, params):
        calls.append(("query", sql, list(params)))
        return []

    monkeypatch.setattr(market_emotion_state_v1, "connect", fake_connect)
    monkeypatch.setattr(market_emotion_state_v1, "fetch_all", fake_fetch_all)

    bars, status = load_market_emotion_source_frames("2026-01-01", "2026-01-05")

    assert bars.empty
    assert status.empty
    assert any("FROM market_daily_bar" in call[1] for call in calls if call[0] == "query")
    assert any("FROM core.asset_status_daily" in call[1] for call in calls if call[0] == "query")


def test_run_market_emotion_backfill_writes_outputs(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        market_emotion_state_v1,
        "load_market_emotion_source_frames",
        lambda *_args, **_kwargs: (_sample_bars(), _sample_status()),
    )

    result = run_market_emotion_state_v1_backfill(
        start_date="2026-01-02",
        end_date="2026-01-03",
        output_dir=tmp_path,
    )

    assert len(result["daily"]) == 2
    assert result["paths"]["daily_path"].exists()
