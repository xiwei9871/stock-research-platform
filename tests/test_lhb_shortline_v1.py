from pathlib import Path

import pandas as pd
import pytest

import stock_research.lhb_shortline_v1 as lhb_shortline_v1
from stock_research import lhb_data
from stock_research.lhb_shortline_v1 import LHBShortlineV1Config
from stock_research.lhb_shortline_v1 import LHBShortlineV1Frames
from stock_research.lhb_shortline_v1 import apply_lhb_shortline_consecutive_weak_control
from stock_research.lhb_shortline_v1 import apply_lhb_shortline_v1_confirmations
from stock_research.lhb_shortline_v1 import build_lhb_shortline_market_regime_control
from stock_research.lhb_shortline_v1 import build_lhb_shortline_market_regime
from stock_research.lhb_shortline_v1 import build_lhb_shortline_v1_candidates
from stock_research.lhb_shortline_v1 import compare_with_legacy_lhb_benchmark
from stock_research.lhb_shortline_v1 import load_lhb_shortline_v1_frames_from_db
from stock_research.lhb_shortline_v1 import run_lhb_shortline_market_regime_account
from stock_research.lhb_shortline_v1 import run_lhb_shortline_v1_backtest_for_dashboard
from stock_research.lhb_shortline_v1 import run_lhb_shortline_v1_from_frames
from stock_research.lhb_shortline_v1 import write_lhb_shortline_v1_artifacts


def test_lhb_shortline_v1_config_normalizes_web_parameters():
    config = LHBShortlineV1Config(
        start_date="2026-01-01",
        end_date="2026-06-08",
        top_n=5,
        rebalance_frequency="daily",
        transaction_cost_bps=10,
        max_position_weight=0.2,
        adjust_type="hfq",
    )

    assert config.engine_version == "lhb_shortline_v1"
    assert config.top_n == 5
    assert config.candidate_pool_n == 10
    assert config.position_weight == 0.2
    assert config.round_trip_cost_return == 0.002
    assert config.risk_profile == "balanced"


def test_lhb_shortline_market_regime_uses_previous_trade_day_breadth():
    daily_bars = pd.DataFrame(
        [
            {"trade_date": "2026-01-13", "ts_code": "000001.SZ", "preclose": 10, "close": 9.5},
            {"trade_date": "2026-01-13", "ts_code": "000002.SZ", "preclose": 10, "close": 9.6},
            {"trade_date": "2026-01-13", "ts_code": "000003.SZ", "preclose": 10, "close": 10.2},
            {"trade_date": "2026-01-14", "ts_code": "000001.SZ", "preclose": 9.5, "close": 9.7},
            {"trade_date": "2026-01-14", "ts_code": "000002.SZ", "preclose": 9.6, "close": 9.8},
            {"trade_date": "2026-01-14", "ts_code": "000003.SZ", "preclose": 10.2, "close": 10.4},
        ]
    )

    regime = build_lhb_shortline_market_regime(daily_bars)

    jan14 = regime[regime["entry_trade_date"].eq("2026-01-14")].iloc[0]
    assert jan14["signal_trade_date"] == "2026-01-13"
    assert jan14["market_regime"] == "risk_off"
    assert jan14["max_total_exposure"] == 0.0


def test_lhb_shortline_market_regime_account_scales_and_skips_entries():
    lifecycle_trades = pd.DataFrame(
        [
            {
                "fill_status": "filled",
                "trade_date": "2026-01-13",
                "ts_code": "000001.SZ",
                "top_n": 5,
                "entry_trade_date": "2026-01-14",
                "exit_trade_date": "2026-01-15",
                "realized_return": 0.1,
            },
            {
                "fill_status": "filled",
                "trade_date": "2026-01-14",
                "ts_code": "000002.SZ",
                "top_n": 5,
                "entry_trade_date": "2026-01-15",
                "exit_trade_date": "2026-01-16",
                "realized_return": 0.1,
            },
        ]
    )
    regime = pd.DataFrame(
        [
            {"entry_trade_date": "2026-01-14", "market_regime": "risk_off", "position_scale": 0.0, "max_total_exposure": 0.0},
            {"entry_trade_date": "2026-01-15", "market_regime": "weak", "position_scale": 0.4, "max_total_exposure": 0.4},
        ]
    )

    result = run_lhb_shortline_market_regime_account(
        lifecycle_trades=lifecycle_trades,
        market_regime=regime,
        max_positions=5,
        base_position_pct=0.2,
    )

    trades = result["account_trades"]
    assert trades.loc[trades["ts_code"].eq("000001.SZ"), "account_trade_status"].iloc[0] == "market_regime_skipped"
    filled = trades[trades["account_trade_status"].eq("filled")].iloc[0]
    assert filled["ts_code"] == "000002.SZ"
    assert filled["position_notional"] == pytest.approx(0.08)
    assert filled["market_regime"] == "weak"
    assert result["summary"]["final_equity"] == pytest.approx(1.008)


def test_lhb_shortline_market_regime_summary_reports_latest_day_pnl():
    lifecycle_trades = pd.DataFrame(
        [
            {
                "fill_status": "filled",
                "trade_date": "2026-06-16",
                "ts_code": "000001.SZ",
                "top_n": 5,
                "entry_trade_date": "2026-06-17",
                "entry_price": 10.0,
                "exit_trade_date": "2026-06-18",
                "realized_return": -0.05,
            },
        ]
    )
    regime = pd.DataFrame(
        [
            {"entry_trade_date": "2026-06-17", "market_regime": "strong", "position_scale": 1.0, "max_total_exposure": 1.0},
            {"entry_trade_date": "2026-06-18", "market_regime": "strong", "position_scale": 1.0, "max_total_exposure": 1.0},
        ]
    )

    result = run_lhb_shortline_market_regime_account(
        lifecycle_trades=lifecycle_trades,
        market_regime=regime,
        max_positions=5,
        base_position_pct=0.2,
        end_date="2026-06-18",
    )

    summary = result["summary"]
    assert summary["actual_end_date"] == "2026-06-18"
    assert summary["latest_day_return"] == pytest.approx(0.99 / 1.0 - 1.0)
    assert summary["latest_day_drawdown"] == pytest.approx(-0.01)
    assert summary["open_position_count"] == 0


def test_lhb_shortline_consecutive_weak_control_waits_for_confirmation():
    regime = pd.DataFrame(
        [
            {"entry_trade_date": "2026-01-14", "market_regime": "risk_off", "position_scale": 0.0, "max_total_exposure": 0.0},
            {"entry_trade_date": "2026-01-15", "market_regime": "strong", "position_scale": 1.0, "max_total_exposure": 1.0},
            {"entry_trade_date": "2026-01-16", "market_regime": "weak", "position_scale": 0.4, "max_total_exposure": 0.4},
            {"entry_trade_date": "2026-01-19", "market_regime": "risk_off", "position_scale": 0.0, "max_total_exposure": 0.0},
        ]
    )

    adjusted = apply_lhb_shortline_consecutive_weak_control(
        regime,
        min_weak_streak_days=2,
        risk_off_scale=0.6,
        weak_scale=0.8,
    )

    first_risk_off = adjusted[adjusted["entry_trade_date"].eq("2026-01-14")].iloc[0]
    confirmed_risk_off = adjusted[adjusted["entry_trade_date"].eq("2026-01-19")].iloc[0]
    assert first_risk_off["raw_market_regime"] == "risk_off"
    assert first_risk_off["weak_streak_days"] == 1
    assert first_risk_off["position_scale"] == 1.0
    assert confirmed_risk_off["raw_market_regime"] == "risk_off"
    assert confirmed_risk_off["weak_streak_days"] == 2
    assert confirmed_risk_off["position_scale"] == 0.6
    assert confirmed_risk_off["max_total_exposure"] == 0.6


def test_lhb_shortline_consecutive_weak_control_can_lightly_cut_first_risk_off_day():
    regime = pd.DataFrame(
        [
            {"entry_trade_date": "2026-01-14", "market_regime": "risk_off", "position_scale": 0.0, "max_total_exposure": 0.0},
            {"entry_trade_date": "2026-01-15", "market_regime": "weak", "position_scale": 0.4, "max_total_exposure": 0.4},
        ]
    )

    adjusted = apply_lhb_shortline_consecutive_weak_control(
        regime,
        min_weak_streak_days=2,
        risk_off_scale=0.5,
        weak_scale=0.7,
        unconfirmed_risk_off_scale=0.7,
        unconfirmed_weak_scale=1.0,
    )

    first_risk_off = adjusted[adjusted["entry_trade_date"].eq("2026-01-14")].iloc[0]
    confirmed_weak = adjusted[adjusted["entry_trade_date"].eq("2026-01-15")].iloc[0]
    assert first_risk_off["weak_streak_days"] == 1
    assert first_risk_off["position_scale"] == 0.7
    assert first_risk_off["max_total_exposure"] == 0.7
    assert confirmed_weak["weak_streak_days"] == 2
    assert confirmed_weak["position_scale"] == 0.7


def test_lhb_shortline_market_regime_control_supports_three_user_profiles():
    daily_bars = pd.DataFrame(
        [
            {"trade_date": "2026-01-13", "ts_code": "000001.SZ", "preclose": 10, "close": 9.5},
            {"trade_date": "2026-01-13", "ts_code": "000002.SZ", "preclose": 10, "close": 9.6},
            {"trade_date": "2026-01-13", "ts_code": "000003.SZ", "preclose": 10, "close": 10.2},
            {"trade_date": "2026-01-14", "ts_code": "000001.SZ", "preclose": 9.5, "close": 9.7},
            {"trade_date": "2026-01-14", "ts_code": "000002.SZ", "preclose": 9.6, "close": 9.8},
            {"trade_date": "2026-01-14", "ts_code": "000003.SZ", "preclose": 10.2, "close": 10.4},
        ]
    )

    return_max = build_lhb_shortline_market_regime_control(daily_bars, risk_profile="return_max")
    balanced = build_lhb_shortline_market_regime_control(daily_bars, risk_profile="balanced")
    drawdown = build_lhb_shortline_market_regime_control(daily_bars, risk_profile="drawdown_control")

    assert return_max.empty
    assert balanced.loc[balanced["entry_trade_date"].eq("2026-01-14"), "position_scale"].iloc[0] == pytest.approx(0.8)
    assert drawdown.loc[drawdown["entry_trade_date"].eq("2026-01-14"), "position_scale"].iloc[0] == pytest.approx(0.65)


def test_build_lhb_shortline_v1_candidates_scores_and_filters_lhb_events():
    lhb = pd.DataFrame(
        [
            {
                "trade_date": "2026-01-05",
                "ts_code": "000001.SZ",
                "on_lhb": True,
                "lhb_net_buy_ratio": 0.35,
                "lhb_net_buy_amount": 120_000_000,
                "institution_net_buy": 20_000_000,
                "repeat_on_list_count_3d": 2,
                "lhb_after_reversal": True,
                "lhb_one_day_pump_risk": 0.20,
            },
            {
                "trade_date": "2026-01-05",
                "ts_code": "000002.SZ",
                "on_lhb": True,
                "lhb_net_buy_ratio": 0.10,
                "lhb_net_buy_amount": 10_000_000,
                "institution_net_buy": 0,
                "repeat_on_list_count_3d": 0,
                "lhb_after_reversal": False,
                "lhb_one_day_pump_risk": 0.90,
            },
        ]
    )
    technical = pd.DataFrame(
        [
            {
                "trade_date": "2026-01-05",
                "ts_code": "000001.SZ",
                "amount_vs_20d": 1.8,
                "high_to_close_drawdown": -0.01,
            },
            {
                "trade_date": "2026-01-05",
                "ts_code": "000002.SZ",
                "amount_vs_20d": 0.6,
                "high_to_close_drawdown": -0.08,
            },
        ]
    )

    result = build_lhb_shortline_v1_candidates(lhb, technical, candidate_pool_n=10)

    assert list(result["ts_code"]) == ["000001.SZ"]
    assert result.iloc[0]["rank"] == 1
    assert result.iloc[0]["score_total"] > 70
    assert result.iloc[0]["candidate_reason"] == "lhb_capital_plus_structure"


def test_apply_lhb_shortline_v1_confirmations_rewards_strong_open_and_intraday():
    candidates = pd.DataFrame(
        [
            {
                "trade_date": "2026-01-05",
                "ts_code": "000001.SZ",
                "score_total": 80.0,
                "rank": 1,
            },
            {
                "trade_date": "2026-01-05",
                "ts_code": "000002.SZ",
                "score_total": 82.0,
                "rank": 2,
            },
        ]
    )
    auction = pd.DataFrame(
        [
            {
                "trade_date": "2026-01-06",
                "ts_code": "000001.SZ",
                "auction_phase": "open_call",
                "open": 11.0,
                "close": 11.0,
                "prev_close": 10.0,
                "amount": 30_000_000,
            },
            {
                "trade_date": "2026-01-06",
                "ts_code": "000002.SZ",
                "auction_phase": "open_call",
                "open": 9.8,
                "close": 9.8,
                "prev_close": 10.0,
                "amount": 1_000_000,
            },
        ]
    )
    intraday = pd.DataFrame(
        [
            {
                "trade_date": "2026-01-06",
                "ts_code": "000001.SZ",
                "morning_return": 0.02,
                "close_to_vwap": 0.01,
                "intraday_return": 0.03,
            },
            {
                "trade_date": "2026-01-06",
                "ts_code": "000002.SZ",
                "morning_return": -0.03,
                "close_to_vwap": -0.02,
                "intraday_return": -0.04,
            },
        ]
    )

    result = apply_lhb_shortline_v1_confirmations(candidates, auction, intraday)

    assert list(result.sort_values("final_score", ascending=False)["ts_code"]) == [
        "000001.SZ",
        "000002.SZ",
    ]
    assert (
        result.loc[result["ts_code"].eq("000001.SZ"), "confirmation_action"].iloc[0]
        == "confirm_follow"
    )
    assert (
        result.loc[result["ts_code"].eq("000002.SZ"), "confirmation_action"].iloc[0]
        == "reject_follow"
    )


def test_run_lhb_shortline_v1_from_frames_applies_topn_weight_cost_and_exit():
    config = LHBShortlineV1Config(
        start_date="2026-01-05",
        end_date="2026-01-10",
        top_n=1,
        transaction_cost_bps=10,
        max_position_weight=0.2,
    )
    candidates = pd.DataFrame(
        [
            {
                "trade_date": "2026-01-05",
                "ts_code": "000001.SZ",
                "final_score": 100.0,
                "confirmation_action": "confirm_follow",
            },
            {
                "trade_date": "2026-01-05",
                "ts_code": "000002.SZ",
                "final_score": 90.0,
                "confirmation_action": "confirm_follow",
            },
        ]
    )
    daily = pd.DataFrame(
        [
            {"trade_date": "2026-01-06", "ts_code": "000001.SZ", "open": 10.0, "close": 10.5},
            {"trade_date": "2026-01-07", "ts_code": "000001.SZ", "open": 10.6, "close": 11.0},
            {"trade_date": "2026-01-08", "ts_code": "000001.SZ", "open": 11.0, "close": 11.0},
        ]
    )

    result = run_lhb_shortline_v1_from_frames(
        config=config,
        scored_candidates=candidates,
        daily_bars=daily,
    )

    assert result.summary["filled_trade_count"] == 1
    assert result.trades.iloc[0]["ts_code"] == "000001.SZ"
    assert result.trades.iloc[0]["position_weight"] == 0.2
    assert result.trades.iloc[0]["realized_return"] == pytest.approx(0.098)
    assert "sharpe_ratio" in result.summary
    assert result.summary["final_equity"] == pytest.approx(1.0196)


def test_run_lhb_shortline_v1_from_frames_treats_end_date_as_hard_asof_cutoff():
    config = LHBShortlineV1Config(
        start_date="2026-01-05",
        end_date="2026-01-06",
        top_n=1,
        transaction_cost_bps=10,
        max_position_weight=0.2,
    )
    candidates = pd.DataFrame(
        [
            {
                "trade_date": "2026-01-05",
                "ts_code": "000001.SZ",
                "final_score": 100.0,
                "confirmation_action": "confirm_follow",
            },
        ]
    )
    daily = pd.DataFrame(
        [
            {"trade_date": "2026-01-06", "ts_code": "000001.SZ", "open": 10.0, "close": 10.5},
            {"trade_date": "2026-01-07", "ts_code": "000001.SZ", "open": 10.6, "close": 11.0},
            {"trade_date": "2026-01-08", "ts_code": "000001.SZ", "open": 11.0, "close": 11.0},
        ]
    )

    result = run_lhb_shortline_v1_from_frames(
        config=config,
        scored_candidates=candidates,
        daily_bars=daily,
    )

    assert result.trades.empty
    assert result.equity_curve.empty
    assert result.summary["filled_trade_count"] == 0


def test_run_lhb_shortline_v1_from_frames_canonicalizes_daily_asset_ids_and_skips_missing():
    config = LHBShortlineV1Config(
        start_date="2026-01-05",
        end_date="2026-01-10",
        top_n=2,
        transaction_cost_bps=0,
        max_position_weight=0.2,
    )
    candidates = pd.DataFrame(
        [
            {
                "trade_date": "2026-01-05",
                "ts_code": "000001.SZ",
                "final_score": 100.0,
                "confirmation_action": "confirm_follow",
            },
            {
                "trade_date": "2026-01-05",
                "ts_code": "000002.SZ",
                "final_score": 90.0,
                "confirmation_action": "confirm_follow",
            },
        ]
    )
    daily = pd.DataFrame(
        [
            {"trade_date": "2026-01-06", "ts_code": "CN:SZ:000001", "open": 10.0, "close": 10.5},
            {"trade_date": "2026-01-07", "ts_code": "CN:SZ:000001", "open": 10.6, "close": 11.0},
        ]
    )

    result = run_lhb_shortline_v1_from_frames(
        config=config,
        scored_candidates=candidates,
        daily_bars=daily,
    )

    assert result.summary["filled_trade_count"] == 1
    assert result.trades.iloc[0]["ts_code"] == "000001.SZ"


def test_lhb_shortline_v1_auction_score_uses_signal_close_call_and_entry_open_call():
    lifecycle = pd.DataFrame(
        [
            {
                "trade_date": "2026-01-05",
                "ts_code": "600370.SH",
                "phase12a_rule_layer": "follow_pool_core",
                "entry_trade_date": "2026-01-06",
            }
        ]
    )
    auction = pd.DataFrame(
        [
            {
                "trade_date": "2026-01-05",
                "ts_code": "600370.SH",
                "auction_phase": "open_call",
                "open": 2.25,
                "close": 2.25,
                "amount": 723_375.04,
            },
            {
                "trade_date": "2026-01-05",
                "ts_code": "600370.SH",
                "auction_phase": "close_call",
                "open": 2.49,
                "close": 2.49,
                "amount": 6_604_227.20,
            },
            {
                "trade_date": "2026-01-06",
                "ts_code": "600370.SH",
                "auction_phase": "open_call",
                "open": 2.55,
                "close": 2.55,
                "amount": 13_595_284.48,
            },
        ]
    )

    scored = lhb_shortline_v1._attach_lhb_shortline_v1_auction_score(lifecycle, auction)

    assert scored.iloc[0]["entry_open_vs_signal_close"] == pytest.approx(2.55 / 2.49 - 1)
    assert scored.iloc[0]["auction_enhanced_score"] == 110.0


def test_lhb_shortline_v1_auction_score_falls_back_to_daily_open_when_auction_missing():
    lifecycle = pd.DataFrame(
        [
            {
                "trade_date": "2026-06-25",
                "ts_code": "600667.SH",
                "phase12a_rule_layer": "follow_pool_core",
                "entry_trade_date": "2026-06-26",
            }
        ]
    )
    daily = pd.DataFrame(
        [
            {"trade_date": "2026-06-25", "ts_code": "600667.SH", "open": 9.8, "close": 10.0},
            {"trade_date": "2026-06-26", "ts_code": "600667.SH", "open": 10.5, "close": 10.8},
        ]
    )

    scored = lhb_shortline_v1._attach_lhb_shortline_v1_auction_score(
        lifecycle,
        pd.DataFrame(),
        daily_bars=daily,
    )

    assert scored.iloc[0]["signal_close_close"] == pytest.approx(10.0)
    assert scored.iloc[0]["entry_open_open"] == pytest.approx(10.5)
    assert scored.iloc[0]["entry_open_vs_signal_close"] == pytest.approx(0.05)
    assert scored.iloc[0]["auction_enhanced_score"] == 125.0


def test_lhb_shortline_v1_minute_rows_prefer_qfq_and_fallback_to_raw():
    rows = [
        {
            "trade_date": "2026-06-18",
            "ts_code": "CN:SH:600667",
            "trade_time": "2026-06-18 09:35:00",
            "open": 10.0,
            "high": 10.2,
            "low": 9.9,
            "close": 10.1,
            "volume": 100,
            "amount": 1_000,
            "adjust_type": "raw",
        },
        {
            "trade_date": "2026-06-18",
            "ts_code": "CN:SH:600667",
            "trade_time": "2026-06-18 09:35:00",
            "open": 11.0,
            "high": 11.2,
            "low": 10.9,
            "close": 11.1,
            "volume": 100,
            "amount": 1_100,
            "adjust_type": "qfq",
        },
        {
            "trade_date": "2026-06-25",
            "ts_code": "CN:SH:600667",
            "trade_time": "2026-06-25 09:35:00",
            "open": 12.0,
            "high": 12.2,
            "low": 11.9,
            "close": 12.1,
            "volume": 100,
            "amount": 1_200,
            "adjust_type": "raw",
        },
    ]

    minute = lhb_shortline_v1._prefer_lhb_shortline_minute_rows(rows)

    assert minute["ts_code"].tolist() == ["600667.SH", "600667.SH"]
    assert minute["trade_date"].tolist() == ["2026-06-18", "2026-06-25"]
    assert minute["open"].tolist() == [11.0, 12.0]


def test_lhb_shortline_v1_uses_fixed_top10_candidate_pool_for_phase18c():
    assert lhb_shortline_v1._lhb_shortline_v1_top_values(5) == [10]
    assert lhb_shortline_v1._lhb_shortline_v1_top_values(20) == [20]


def test_lhb_shortline_v1_lifecycle_minute_window_matches_legacy_trade_date_scope():
    selected = pd.DataFrame(
        [
            {"trade_date": "2026-01-06", "ts_code": "300986.SZ"},
        ]
    )
    minute_bars = pd.DataFrame(
        [
            {
                "trade_date": "2026-01-07",
                "ts_code": "300986.SZ",
                "trade_time": "2026-01-07 09:35:00",
                "open": 17.44,
                "high": 17.44,
                "low": 17.44,
                "close": 17.44,
            },
            {
                "trade_date": "2026-01-12",
                "ts_code": "300986.SZ",
                "trade_time": "2026-01-12 15:00:00",
                "open": 33.38,
                "high": 33.38,
                "low": 33.38,
                "close": 33.38,
            },
            {
                "trade_date": "2026-01-08",
                "ts_code": "000001.SZ",
                "trade_time": "2026-01-08 09:35:00",
                "open": 1.0,
                "high": 1.0,
                "low": 1.0,
                "close": 1.0,
            },
            {
                "trade_date": "2026-01-09",
                "ts_code": "000001.SZ",
                "trade_time": "2026-01-09 09:35:00",
                "open": 1.0,
                "high": 1.0,
                "low": 1.0,
                "close": 1.0,
            },
            {
                "trade_date": "2026-01-13",
                "ts_code": "000001.SZ",
                "trade_time": "2026-01-13 09:35:00",
                "open": 1.0,
                "high": 1.0,
                "low": 1.0,
                "close": 1.0,
            },
            {
                "trade_date": "2026-01-14",
                "ts_code": "000001.SZ",
                "trade_time": "2026-01-14 09:35:00",
                "open": 1.0,
                "high": 1.0,
                "low": 1.0,
                "close": 1.0,
            },
            {
                "trade_date": "2026-01-16",
                "ts_code": "300986.SZ",
                "trade_time": "2026-01-16 10:25:00",
                "open": 28.22,
                "high": 28.22,
                "low": 28.22,
                "close": 28.22,
            },
        ]
    )

    result = lhb_shortline_v1._filter_lhb_shortline_v1_lifecycle_minute_window(
        selected=selected,
        minute_bars=minute_bars,
        holding_trade_days=5,
    )

    assert result["trade_date"].tolist() == ["2026-01-07", "2026-01-12"]


def test_lhb_shortline_v1_legacy_entry_allows_one_price_limit_execution_bar():
    frame = pd.DataFrame(
        [
            {"open": 24.92, "high": 24.92, "low": 24.92, "close": 24.92},
        ]
    )

    execution_idx, blocked_count = lhb_data._find_lhb_next_tradable_entry_execution_idx(
        frame=frame,
        start_idx=0,
        reference_price=24.92,
    )

    assert execution_idx == 0
    assert blocked_count == 0


def test_lhb_shortline_v1_lifecycle_applies_default_market_regime_profile(monkeypatch, tmp_path: Path):
    frames = LHBShortlineV1Frames(
        lhb_features=pd.DataFrame(),
        technical_features=pd.DataFrame(),
        auction_open=pd.DataFrame(),
        intraday_confirmation=pd.DataFrame(),
        daily_bars=pd.DataFrame(
            [
                {"trade_date": "2026-01-13", "ts_code": "000001.SZ", "preclose": 10.0, "open": 10.0, "close": 9.5},
                {"trade_date": "2026-01-13", "ts_code": "000002.SZ", "preclose": 10.0, "open": 10.0, "close": 9.6},
                {"trade_date": "2026-01-13", "ts_code": "000003.SZ", "preclose": 10.0, "open": 10.0, "close": 10.2},
                {"trade_date": "2026-01-14", "ts_code": "000001.SZ", "preclose": 9.5, "open": 9.5, "close": 9.7},
                {"trade_date": "2026-01-15", "ts_code": "000001.SZ", "preclose": 9.7, "open": 9.7, "close": 9.8},
            ]
        ),
        minute_bars=pd.DataFrame(),
        coverage={},
    )
    selected = pd.DataFrame([{"trade_date": "2026-01-13", "ts_code": "000001.SZ", "top_n": 5}])
    phase18c_trade = pd.DataFrame(
        [
            {
                "account_trade_status": "filled",
                "strategy": "auction_enhanced_rerank",
                "trade_date": "2026-01-13",
                "ts_code": "000001.SZ",
                "top_n": 5,
                "entry_trade_date": "2026-01-14",
                "exit_trade_date": "2026-01-15",
                "realized_return": 0.10,
            }
        ]
    )

    monkeypatch.setattr(lhb_data, "build_lhb_full_market_pool_backtest_v1", lambda **kwargs: {"selected_trades": selected, "paths": {}})
    monkeypatch.setattr(lhb_data, "build_lhb_shortline_intraday_confirmation_v1", lambda **kwargs: {"detail": pd.DataFrame(), "paths": {}})
    monkeypatch.setattr(lhb_data, "build_lhb_phase12a_multi_context_decision_v1", lambda **kwargs: {"decision": pd.DataFrame(), "paths": {}})
    monkeypatch.setattr(lhb_data, "build_lhb_phase12a_rule_decision_v1", lambda **kwargs: {"rule_decision": pd.DataFrame(), "paths": {}})
    monkeypatch.setattr(lhb_data, "build_lhb_phase12a_real_entry_backtest_v1", lambda **kwargs: {"trades": pd.DataFrame(), "paths": {}})
    monkeypatch.setattr(lhb_data, "build_lhb_phase14c_lifecycle_portfolio_v1", lambda **kwargs: {"lifecycle_trades": phase18c_trade, "paths": {}})
    monkeypatch.setattr(
        lhb_data,
        "build_lhb_phase18c_auction_enhanced_cash_account_backtest_v1",
        lambda **kwargs: {
            "account_trades": phase18c_trade,
            "account_curve": pd.DataFrame(
                [{"trade_date": "2026-01-15", "equity": 1.02, "strategy": "auction_enhanced_rerank", "top_n": 5}]
            ),
            "summary": pd.DataFrame(
                [
                    {
                        "strategy": "auction_enhanced_rerank",
                        "top_n": 5,
                        "final_equity": 1.02,
                        "total_return": 0.02,
                        "max_drawdown": 0.0,
                        "filled_trade_count": 1,
                    }
                ]
            ),
            "selected_trades": phase18c_trade,
            "paths": {},
        },
    )

    result, _, _ = lhb_shortline_v1.run_lhb_shortline_v1_lifecycle_from_frames(
        config=LHBShortlineV1Config(
            start_date="2026-01-13",
            end_date="2026-01-15",
            top_n=5,
            max_position_weight=0.2,
        ),
        frames=frames,
        output_dir=tmp_path,
    )

    assert result.summary["market_regime_profile"] == "first_risk80_gradient_2d90_3d80_4d70"
    assert result.summary["final_equity"] == pytest.approx(1.016)
    assert result.trades.iloc[0]["position_notional"] == pytest.approx(0.16)
    assert result.trades.iloc[0]["market_regime"] == "risk_off"


def test_lhb_shortline_v1_lifecycle_treats_end_date_as_hard_asof_cutoff(
    monkeypatch,
    tmp_path: Path,
):
    frames = LHBShortlineV1Frames(
        lhb_features=pd.DataFrame(),
        technical_features=pd.DataFrame(),
        auction_open=pd.DataFrame(),
        intraday_confirmation=pd.DataFrame(),
        daily_bars=pd.DataFrame(
            [
                {"trade_date": "2026-01-13", "ts_code": "000001.SZ", "preclose": 10.0, "open": 10.0, "close": 10.2},
                {"trade_date": "2026-01-14", "ts_code": "000001.SZ", "preclose": 10.2, "open": 10.2, "close": 10.3},
                {"trade_date": "2026-01-15", "ts_code": "000001.SZ", "preclose": 10.3, "open": 10.3, "close": 10.6},
                {"trade_date": "2026-01-16", "ts_code": "000001.SZ", "preclose": 10.6, "open": 10.6, "close": 10.8},
            ]
        ),
        minute_bars=pd.DataFrame(),
        coverage={},
    )
    selected = pd.DataFrame([{"trade_date": "2026-01-14", "ts_code": "000001.SZ", "top_n": 5}])
    future_trade = pd.DataFrame(
        [
            {
                "account_trade_status": "filled",
                "fill_status": "filled",
                "strategy": "auction_enhanced_rerank",
                "trade_date": "2026-01-14",
                "ts_code": "000001.SZ",
                "top_n": 5,
                "entry_trade_date": "2026-01-15",
                "exit_trade_date": "2026-01-16",
                "realized_return": 0.10,
            }
        ]
    )

    monkeypatch.setattr(lhb_data, "build_lhb_full_market_pool_backtest_v1", lambda **kwargs: {"selected_trades": selected, "paths": {}})
    monkeypatch.setattr(lhb_data, "build_lhb_shortline_intraday_confirmation_v1", lambda **kwargs: {"detail": pd.DataFrame(), "paths": {}})
    monkeypatch.setattr(lhb_data, "build_lhb_phase12a_multi_context_decision_v1", lambda **kwargs: {"decision": pd.DataFrame(), "paths": {}})
    monkeypatch.setattr(lhb_data, "build_lhb_phase12a_rule_decision_v1", lambda **kwargs: {"rule_decision": pd.DataFrame(), "paths": {}})
    monkeypatch.setattr(lhb_data, "build_lhb_phase12a_real_entry_backtest_v1", lambda **kwargs: {"trades": pd.DataFrame(), "paths": {}})
    monkeypatch.setattr(lhb_data, "build_lhb_phase14c_lifecycle_portfolio_v1", lambda **kwargs: {"lifecycle_trades": future_trade, "paths": {}})
    monkeypatch.setattr(
        lhb_data,
        "build_lhb_phase18c_auction_enhanced_cash_account_backtest_v1",
        lambda **kwargs: {
            "account_trades": future_trade,
            "account_curve": pd.DataFrame(
                [{"trade_date": "2026-01-16", "equity": 1.02, "strategy": "auction_enhanced_rerank", "top_n": 5}]
            ),
            "summary": pd.DataFrame(
                [
                    {
                        "strategy": "auction_enhanced_rerank",
                        "top_n": 5,
                        "final_equity": 1.02,
                        "total_return": 0.02,
                        "max_drawdown": 0.0,
                        "filled_trade_count": 1,
                    }
                ]
            ),
            "selected_trades": future_trade,
            "paths": {},
        },
    )

    result, scored, _ = lhb_shortline_v1.run_lhb_shortline_v1_lifecycle_from_frames(
        config=LHBShortlineV1Config(
            start_date="2026-01-13",
            end_date="2026-01-14",
            top_n=5,
            max_position_weight=0.2,
        ),
        frames=frames,
        output_dir=tmp_path,
    )

    assert result.trades.empty
    assert result.equity_curve.empty
    assert result.summary["filled_trade_count"] == 0
    assert scored.empty


def test_lhb_shortline_v1_extends_account_curve_to_available_end_date(
    monkeypatch,
    tmp_path: Path,
):
    frames = LHBShortlineV1Frames(
        lhb_features=pd.DataFrame(),
        technical_features=pd.DataFrame(),
        auction_open=pd.DataFrame(),
        intraday_confirmation=pd.DataFrame(),
        daily_bars=pd.DataFrame(
            [
                {"trade_date": "2026-06-16", "ts_code": "000001.SZ", "preclose": 10.0, "open": 10.0, "close": 10.2},
                {"trade_date": "2026-06-17", "ts_code": "000001.SZ", "preclose": 10.2, "open": 10.2, "close": 10.3},
                {"trade_date": "2026-06-18", "ts_code": "000001.SZ", "preclose": 10.3, "open": 10.3, "close": 10.4},
            ]
        ),
        minute_bars=pd.DataFrame(),
        coverage={},
    )
    selected = pd.DataFrame([{"trade_date": "2026-06-16", "ts_code": "000001.SZ", "top_n": 5}])
    lifecycle_trade = pd.DataFrame(
        [
            {
                "account_trade_status": "filled",
                "fill_status": "filled",
                "strategy": "auction_enhanced_rerank",
                "trade_date": "2026-06-16",
                "ts_code": "000001.SZ",
                "top_n": 5,
                "entry_trade_date": "2026-06-16",
                "exit_trade_date": "2026-06-17",
                "realized_return": 0.10,
            }
        ]
    )

    monkeypatch.setattr(lhb_data, "build_lhb_full_market_pool_backtest_v1", lambda **kwargs: {"selected_trades": selected, "paths": {}})
    monkeypatch.setattr(lhb_data, "build_lhb_shortline_intraday_confirmation_v1", lambda **kwargs: {"detail": pd.DataFrame(), "paths": {}})
    monkeypatch.setattr(lhb_data, "build_lhb_phase12a_multi_context_decision_v1", lambda **kwargs: {"decision": pd.DataFrame(), "paths": {}})
    monkeypatch.setattr(lhb_data, "build_lhb_phase12a_rule_decision_v1", lambda **kwargs: {"rule_decision": pd.DataFrame(), "paths": {}})
    monkeypatch.setattr(lhb_data, "build_lhb_phase12a_real_entry_backtest_v1", lambda **kwargs: {"trades": pd.DataFrame(), "paths": {}})
    monkeypatch.setattr(lhb_data, "build_lhb_phase14c_lifecycle_portfolio_v1", lambda **kwargs: {"lifecycle_trades": lifecycle_trade, "paths": {}})
    monkeypatch.setattr(
        lhb_data,
        "build_lhb_phase18c_auction_enhanced_cash_account_backtest_v1",
        lambda **kwargs: {
            "account_trades": lifecycle_trade,
            "account_curve": pd.DataFrame(
                [
                    {"trade_date": "2026-06-16", "equity": 1.0, "drawdown": 0.0, "strategy": "auction_enhanced_rerank", "top_n": 5},
                    {"trade_date": "2026-06-17", "equity": 1.02, "drawdown": 0.0, "strategy": "auction_enhanced_rerank", "top_n": 5},
                ]
            ),
            "summary": pd.DataFrame(
                [
                    {
                        "strategy": "auction_enhanced_rerank",
                        "top_n": 5,
                        "final_equity": 1.02,
                        "total_return": 0.02,
                        "max_drawdown": 0.0,
                        "filled_trade_count": 1,
                    }
                ]
            ),
            "selected_trades": lifecycle_trade,
            "paths": {},
        },
    )

    result, _, _ = lhb_shortline_v1.run_lhb_shortline_v1_lifecycle_from_frames(
        config=LHBShortlineV1Config(
            start_date="2026-06-16",
            end_date="2026-06-18",
            top_n=5,
            max_position_weight=0.2,
        ),
        frames=frames,
        output_dir=tmp_path,
    )

    assert result.summary["actual_end_date"] == "2026-06-18"
    assert result.equity_curve["trade_date"].tolist()[-2:] == ["2026-06-17", "2026-06-18"]
    assert result.equity_curve.iloc[-1]["equity"] == pytest.approx(result.equity_curve.iloc[-2]["equity"])
    assert result.equity_curve.iloc[-1]["daily_realized_pnl"] == pytest.approx(0.0)


def test_lhb_shortline_v1_marks_open_positions_to_market_at_end_date(
    monkeypatch,
    tmp_path: Path,
):
    frames = LHBShortlineV1Frames(
        lhb_features=pd.DataFrame(),
        technical_features=pd.DataFrame(),
        auction_open=pd.DataFrame(),
        intraday_confirmation=pd.DataFrame(),
        daily_bars=pd.DataFrame(
            [
                {"trade_date": "2026-06-16", "ts_code": "000001.SZ", "preclose": 10.0, "open": 10.0, "close": 10.0},
                {"trade_date": "2026-06-17", "ts_code": "000001.SZ", "preclose": 10.0, "open": 10.0, "close": 10.0},
                {"trade_date": "2026-06-18", "ts_code": "000001.SZ", "preclose": 10.0, "open": 10.0, "close": 11.0},
            ]
        ),
        minute_bars=pd.DataFrame(),
        coverage={},
    )
    selected = pd.DataFrame([{"trade_date": "2026-06-16", "ts_code": "000001.SZ", "top_n": 5}])
    open_trade = pd.DataFrame(
        [
            {
                "account_trade_status": "filled",
                "fill_status": "filled",
                "strategy": "auction_enhanced_rerank",
                "trade_date": "2026-06-16",
                "ts_code": "000001.SZ",
                "top_n": 5,
                "entry_trade_date": "2026-06-17",
                "entry_time": "10:35:00",
                "entry_price": 10.0,
                "exit_trade_date": pd.NA,
                "realized_return": pd.NA,
            }
        ]
    )

    monkeypatch.setattr(lhb_data, "build_lhb_full_market_pool_backtest_v1", lambda **kwargs: {"selected_trades": selected, "paths": {}})
    monkeypatch.setattr(lhb_data, "build_lhb_shortline_intraday_confirmation_v1", lambda **kwargs: {"detail": pd.DataFrame(), "paths": {}})
    monkeypatch.setattr(lhb_data, "build_lhb_phase12a_multi_context_decision_v1", lambda **kwargs: {"decision": pd.DataFrame(), "paths": {}})
    monkeypatch.setattr(lhb_data, "build_lhb_phase12a_rule_decision_v1", lambda **kwargs: {"rule_decision": pd.DataFrame(), "paths": {}})
    monkeypatch.setattr(lhb_data, "build_lhb_phase12a_real_entry_backtest_v1", lambda **kwargs: {"trades": pd.DataFrame(), "paths": {}})
    monkeypatch.setattr(lhb_data, "build_lhb_phase14c_lifecycle_portfolio_v1", lambda **kwargs: {"lifecycle_trades": open_trade, "paths": {}})
    monkeypatch.setattr(
        lhb_data,
        "build_lhb_phase18c_auction_enhanced_cash_account_backtest_v1",
        lambda **kwargs: {
            "account_trades": open_trade,
            "account_curve": pd.DataFrame(),
            "summary": pd.DataFrame(
                [
                    {
                        "strategy": "auction_enhanced_rerank",
                        "top_n": 5,
                        "final_equity": 1.0,
                        "total_return": 0.0,
                        "max_drawdown": 0.0,
                        "filled_trade_count": 1,
                    }
                ]
            ),
            "selected_trades": open_trade,
            "paths": {},
        },
    )

    result, _, _ = lhb_shortline_v1.run_lhb_shortline_v1_lifecycle_from_frames(
        config=LHBShortlineV1Config(
            start_date="2026-06-16",
            end_date="2026-06-18",
            top_n=5,
            max_position_weight=0.2,
        ),
        frames=frames,
        output_dir=tmp_path,
    )

    latest = result.equity_curve.iloc[-1]
    position_notional = result.trades.iloc[0]["position_notional"]
    assert latest["trade_date"] == "2026-06-18"
    assert latest["open_position_count"] == 1
    assert latest["equity"] == pytest.approx(1.0 + position_notional * 0.10)
    assert result.summary["final_equity"] == pytest.approx(1.0 + position_notional * 0.10)
    assert result.trades.iloc[0]["pnl"] == pytest.approx(position_notional * 0.10)


def test_lhb_shortline_v1_truncates_future_exit_to_open_mark_to_market(
    monkeypatch,
    tmp_path: Path,
):
    frames = LHBShortlineV1Frames(
        lhb_features=pd.DataFrame(),
        technical_features=pd.DataFrame(),
        auction_open=pd.DataFrame(),
        intraday_confirmation=pd.DataFrame(),
        daily_bars=pd.DataFrame(
            [
                {"trade_date": "2026-06-17", "ts_code": "000001.SZ", "preclose": 10.0, "open": 10.0, "close": 10.0},
                {"trade_date": "2026-06-18", "ts_code": "000001.SZ", "preclose": 10.0, "open": 10.0, "close": 11.0},
                {"trade_date": "2026-06-19", "ts_code": "000001.SZ", "preclose": 11.0, "open": 11.0, "close": 12.0},
            ]
        ),
        minute_bars=pd.DataFrame(),
        coverage={},
    )
    selected = pd.DataFrame([{"trade_date": "2026-06-16", "ts_code": "000001.SZ", "top_n": 5}])
    future_exit_trade = pd.DataFrame(
        [
            {
                "account_trade_status": "filled",
                "fill_status": "filled",
                "strategy": "auction_enhanced_rerank",
                "trade_date": "2026-06-16",
                "ts_code": "000001.SZ",
                "top_n": 5,
                "entry_trade_date": "2026-06-17",
                "entry_time": "10:35:00",
                "entry_price": 10.0,
                "exit_trade_date": "2026-06-19",
                "realized_return": 0.20,
            }
        ]
    )

    monkeypatch.setattr(lhb_data, "build_lhb_full_market_pool_backtest_v1", lambda **kwargs: {"selected_trades": selected, "paths": {}})
    monkeypatch.setattr(lhb_data, "build_lhb_shortline_intraday_confirmation_v1", lambda **kwargs: {"detail": pd.DataFrame(), "paths": {}})
    monkeypatch.setattr(lhb_data, "build_lhb_phase12a_multi_context_decision_v1", lambda **kwargs: {"decision": pd.DataFrame(), "paths": {}})
    monkeypatch.setattr(lhb_data, "build_lhb_phase12a_rule_decision_v1", lambda **kwargs: {"rule_decision": pd.DataFrame(), "paths": {}})
    monkeypatch.setattr(lhb_data, "build_lhb_phase12a_real_entry_backtest_v1", lambda **kwargs: {"trades": pd.DataFrame(), "paths": {}})
    monkeypatch.setattr(lhb_data, "build_lhb_phase14c_lifecycle_portfolio_v1", lambda **kwargs: {"lifecycle_trades": future_exit_trade, "paths": {}})
    monkeypatch.setattr(
        lhb_data,
        "build_lhb_phase18c_auction_enhanced_cash_account_backtest_v1",
        lambda **kwargs: {
            "account_trades": future_exit_trade,
            "account_curve": pd.DataFrame(),
            "summary": pd.DataFrame(
                [
                    {
                        "strategy": "auction_enhanced_rerank",
                        "top_n": 5,
                        "final_equity": 1.0,
                        "total_return": 0.0,
                        "max_drawdown": 0.0,
                        "filled_trade_count": 1,
                    }
                ]
            ),
            "selected_trades": future_exit_trade,
            "paths": {},
        },
    )

    result, _, _ = lhb_shortline_v1.run_lhb_shortline_v1_lifecycle_from_frames(
        config=LHBShortlineV1Config(
            start_date="2026-06-16",
            end_date="2026-06-18",
            top_n=5,
            max_position_weight=0.2,
        ),
        frames=frames,
        output_dir=tmp_path,
    )

    latest = result.equity_curve.iloc[-1]
    position_notional = result.trades.iloc[0]["position_notional"]
    assert latest["trade_date"] == "2026-06-18"
    assert latest["open_position_count"] == 1
    assert pd.isna(result.trades.iloc[0]["exit_trade_date"]) or result.trades.iloc[0]["exit_trade_date"] == ""
    assert latest["equity"] == pytest.approx(1.0 + position_notional * 0.10)


def test_phase15_cash_account_preserves_lifecycle_trade_timing_and_position():
    lifecycle_trades = pd.DataFrame(
        [
            {
                "fill_status": "filled",
                "trade_date": "2026-01-05",
                "ts_code": "300986.SZ",
                "top_n": 5,
                "phase12a_rule_layer": "follow",
                "entry_trade_date": "2026-01-06",
                "entry_time": "10:30:00",
                "entry_price": 18.05,
                "exit_status": "signal_exit",
                "exit_signal": "take_profit",
                "exit_reason": "target_reached",
                "exit_trade_date": "2026-01-08",
                "exit_time": "14:55:00",
                "exit_price": 20.62,
                "realized_return": 0.1191,
            }
        ]
    )

    account_trades, _account_curve = lhb_data._build_lhb_phase15_cash_account_frames(
        lifecycle_trades=lifecycle_trades,
        max_positions=5,
        position_pct=0.2,
    )

    row = account_trades.iloc[0]
    assert row["entry_time"] == "10:30:00"
    assert row["exit_time"] == "14:55:00"
    assert row["exit_reason"] == "target_reached"
    assert row["position_notional"] == pytest.approx(0.2)


def test_write_lhb_shortline_v1_artifacts_writes_reproducible_run_files(tmp_path: Path):
    config = LHBShortlineV1Config(start_date="2026-01-01", end_date="2026-06-08", top_n=5)
    summary = {"engine_version": "lhb_shortline_v1", "final_equity": 1.2}
    candidates = pd.DataFrame([{"trade_date": "2026-01-05", "ts_code": "000001.SZ"}])
    trades = pd.DataFrame(
        [{"trade_date": "2026-01-05", "ts_code": "000001.SZ", "realized_return": 0.1}]
    )
    curve = pd.DataFrame([{"trade_date": "2026-01-06", "equity": 1.02}])

    paths = write_lhb_shortline_v1_artifacts(
        output_dir=tmp_path,
        config=config,
        summary=summary,
        candidates=candidates,
        trades=trades,
        equity_curve=curve,
    )

    assert Path(paths["summary"]).exists()
    assert Path(paths["candidates"]).exists()
    assert Path(paths["trades"]).exists()
    assert Path(paths["equity_curve"]).exists()


def test_compare_with_legacy_lhb_benchmark_reports_deltas():
    current = {
        "total_return": 0.50,
        "final_equity": 1.50,
        "max_drawdown": -0.20,
        "filled_trade_count": 20,
    }
    legacy = {
        "total_return": 0.40,
        "final_equity": 1.40,
        "max_drawdown": -0.25,
        "filled_trade_count": 18,
    }

    result = compare_with_legacy_lhb_benchmark(current, legacy)

    assert result["benchmark_name"] == "legacy_best_lhb_research"
    assert result["total_return_delta"] == 0.10
    assert result["max_drawdown_delta"] == 0.05
    assert result["trade_count_delta"] == 2


def test_run_lhb_shortline_v1_backtest_for_dashboard_uses_db_loader_and_returns_payload(
    monkeypatch,
    tmp_path: Path,
):
    frames = LHBShortlineV1Frames(
        lhb_features=pd.DataFrame(
            [
                {
                    "trade_date": "2026-01-05",
                    "ts_code": "000001.SZ",
                    "on_lhb": True,
                    "lhb_net_buy_ratio": 0.35,
                    "lhb_net_buy_amount": 120_000_000,
                    "institution_net_buy": 20_000_000,
                    "repeat_on_list_count_3d": 2,
                    "lhb_after_reversal": True,
                    "lhb_one_day_pump_risk": 0.20,
                }
            ]
        ),
        technical_features=pd.DataFrame(
            [
                {
                    "trade_date": "2026-01-05",
                    "ts_code": "000001.SZ",
                    "amount_vs_20d": 1.8,
                    "high_to_close_drawdown": -0.01,
                }
            ]
        ),
        auction_open=pd.DataFrame(
            [
                {
                    "trade_date": "2026-01-06",
                    "ts_code": "000001.SZ",
                    "auction_phase": "open_call",
                    "open": 10.0,
                    "prev_close": 9.8,
                    "amount": 30_000_000,
                }
            ]
        ),
        intraday_confirmation=pd.DataFrame(
            [
                {
                    "trade_date": "2026-01-06",
                    "ts_code": "000001.SZ",
                    "morning_return": 0.02,
                    "close_to_vwap": 0.01,
                    "intraday_return": 0.03,
                }
            ]
        ),
        daily_bars=pd.DataFrame(
            [
                {"trade_date": "2026-01-06", "ts_code": "000001.SZ", "open": 10.0, "close": 10.5},
                {"trade_date": "2026-01-07", "ts_code": "000001.SZ", "open": 10.6, "close": 11.0},
                {"trade_date": "2026-01-08", "ts_code": "000001.SZ", "open": 11.0, "close": 11.0},
            ]
        ),
        minute_bars=pd.DataFrame(),
        coverage={"source": "db_base_tables"},
    )
    calls = {}

    def fake_load(config, *, service=None):
        calls["config"] = config
        calls["service"] = service
        return frames

    monkeypatch.setattr(lhb_shortline_v1, "load_lhb_shortline_v1_frames_from_db", fake_load)

    def fake_lifecycle(config, frames, output_dir):
        calls["lifecycle_config"] = config
        calls["output_dir"] = output_dir
        return (
            lhb_shortline_v1.LHBShortlineV1Result(
                summary={
                    "engine_version": "lhb_shortline_v1",
                    "final_equity": 1.0196,
                    "total_return": 0.0196,
                    "max_drawdown": 0.0,
                    "filled_trade_count": 1,
                    "win_rate": 1.0,
                },
                equity_curve=pd.DataFrame([{"trade_date": "2026-01-08", "equity": 1.0196}]),
                positions=pd.DataFrame(
                    [{"trade_date": "2026-01-05", "ts_code": "000001.SZ", "position_notional": 0.2}]
                ),
                trades=pd.DataFrame(
                    [{"trade_date": "2026-01-05", "ts_code": "000001.SZ", "realized_return": 0.098}]
                ),
            ),
            pd.DataFrame([{"trade_date": "2026-01-05", "ts_code": "000001.SZ"}]),
            {"pipeline_summary": str(tmp_path / "pipeline.csv")},
        )

    monkeypatch.setattr(lhb_shortline_v1, "run_lhb_shortline_v1_lifecycle_from_frames", fake_lifecycle)

    result = run_lhb_shortline_v1_backtest_for_dashboard(
        {
            "start_date": "2026-01-05",
            "end_date": "2026-01-10",
            "top_n": 1,
            "transaction_cost_bps": 10,
            "max_position_weight": 0.2,
            "db_service": "research_test",
            "output_dir": str(tmp_path),
        }
    )

    assert calls["service"] == "research_test"
    assert calls["lifecycle_config"].max_positions is None
    assert result["source_kind"] == "lhb_shortline_v1"
    assert result["config"]["engine_version"] == "lhb_shortline_v1"
    assert result["summary"]["filled_trade_count"] == 1
    assert result["summary"]["data_coverage"] == {"source": "db_base_tables"}
    assert "legacy_benchmark" in result["summary"]
    assert result["data_coverage"] == {"source": "db_base_tables"}
    assert result["artifacts"]["summary"].endswith("lhb_shortline_v1_summary.json")
    assert result["artifacts"]["pipeline_summary"].endswith("pipeline.csv")
    assert result["trades"][0]["ts_code"] == "000001.SZ"


def test_load_lhb_shortline_v1_frames_from_db_queries_base_tables(monkeypatch):
    import stock_research.db as db

    captured = {"service": None, "sql": []}

    class FakeConnection:
        pass

    class FakeConnect:
        def __init__(self, service):
            captured["service"] = service

        def __enter__(self):
            return FakeConnection()

        def __exit__(self, exc_type, exc, traceback):
            return False

    def fake_fetch_all(conn, sql, params=None):
        del conn, params
        captured["sql"].append(sql)
        if "factor.lhb_event_features_daily" in sql:
            return [
                {
                    "trade_date": "2026-01-02",
                    "ts_code": "000001.SZ",
                    "lhb_net_buy_amount": 1_000_000,
                    "lhb_net_buy_ratio": 0.1,
                    "institution_net_buy": 0,
                    "lhb_one_day_pump_risk": 0.1,
                }
            ]
        return []

    monkeypatch.setattr(db, "connect", FakeConnect)
    monkeypatch.setattr(db, "fetch_all", fake_fetch_all)

    config = LHBShortlineV1Config(start_date="2026-01-01", end_date="2026-01-10", top_n=5)

    frames = load_lhb_shortline_v1_frames_from_db(config, service="research_test")

    sql = "\n".join(captured["sql"]).lower()
    assert captured["service"] == "research_test"
    assert frames.coverage["source"] == "db_base_tables"
    assert "factor.lhb_event_features_daily" in sql
    assert "factor.stock_technical_features_daily" in sql
    assert "market_daily_bar" in sql
    assert "market.stock_auction_bar" in sql
    assert "market.stock_minute_bar" in sql
    assert "m.adjust_type in ('qfq', 'raw')" in sql
    assert "factor.stock_intraday_features_daily" in sql
    assert "morning_return" in sql
    assert "first_60m_return" not in sql
    assert "phase14c" not in sql
    assert "phase18b" not in sql
    assert "read_csv" not in sql
