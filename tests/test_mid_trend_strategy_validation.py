from __future__ import annotations

from importlib import import_module

import pandas as pd

from stock_research.current_mid_trend_strategy_v1 import (
    build_current_mid_trend_strategy_v1_from_frames,
)
from stock_research.mid_trend_shadow_backtest import (
    build_mid_trend_shadow_backtest_from_frames,
)
from stock_research.mid_trend_strategy_validation import (
    build_mid_trend_validation_scorecard,
    discover_mid_trend_strategy_candidates,
    filter_complete_mid_trend_candidates,
    rank_mid_trend_validation_scorecard,
)


def test_discover_mid_trend_strategy_candidates_returns_known_complete_entries() -> None:
    candidates = discover_mid_trend_strategy_candidates()

    ids = {item["strategy_id"] for item in candidates}
    assert "current_mid_trend_strategy_v1" in ids
    assert "mid_trend_shadow_backtest" in ids


def test_known_mid_trend_candidates_expose_importable_runner_names() -> None:
    candidates = {
        item["strategy_id"]: item
        for item in discover_mid_trend_strategy_candidates()
    }

    expected_runners = {
        "current_mid_trend_strategy_v1": (
            "stock_research.current_mid_trend_strategy_v1",
            "run_current_mid_trend_strategy_v1_backtest",
        ),
        "mid_trend_shadow_backtest": (
            "stock_research.mid_trend_shadow_backtest",
            "run_mid_trend_shadow_backtest",
        ),
    }

    for strategy_id, (module_name, runner_name) in expected_runners.items():
        candidate = candidates[strategy_id]
        module = import_module(module_name)

        assert candidate["runner_name"] == runner_name
        assert hasattr(module, runner_name)
        assert callable(getattr(module, runner_name))


def test_known_mid_trend_candidates_result_keys_match_actual_payloads() -> None:
    candidates = {
        item["strategy_id"]: item
        for item in discover_mid_trend_strategy_candidates()
    }

    current_result = build_current_mid_trend_strategy_v1_from_frames(
        regime=_current_regime_frame(),
        funnel=_current_funnel_frame(),
        prices=_current_prices_frame(),
        asset_names=_current_asset_names_frame(),
        start_date="2025-01-01",
        end_date="2025-01-03",
        top_n=2,
    )
    shadow_result = build_mid_trend_shadow_backtest_from_frames(
        shadow_top10=_shadow_top10_frame(),
        prices=_shadow_prices_frame(),
        start_date="2025-01-01",
        end_date="2025-01-03",
        top_n=2,
        transaction_cost_bps=10.0,
    )

    assert candidates["current_mid_trend_strategy_v1"]["result_keys"] <= current_result.keys()
    assert candidates["mid_trend_shadow_backtest"]["result_keys"] <= shadow_result.keys()


def test_filter_complete_mid_trend_candidates_keeps_only_complete_portfolio_versions() -> None:
    candidates = [
        {
            "strategy_id": "current_mid_trend_strategy_v1",
            "group": "portfolio",
            "result_keys": {"holdings", "trades", "equity", "summary"},
        },
        {
            "strategy_id": "mid_trend_incomplete_portfolio",
            "group": "portfolio",
            "result_keys": {"holdings", "trades", "equity"},
        },
        {
            "strategy_id": "mid_trend_portfolio_review",
            "group": "review",
            "result_keys": {"review_rows", "portfolio_summary"},
        },
    ]

    filtered = filter_complete_mid_trend_candidates(candidates)

    assert [item["strategy_id"] for item in filtered] == ["current_mid_trend_strategy_v1"]


def test_build_mid_trend_validation_scorecard_extracts_five_metrics() -> None:
    scorecard = build_mid_trend_validation_scorecard(
        [
            {
                "strategy_id": "a",
                "summary_frame": pd.DataFrame(
                    [
                        {"metric": "total_return", "value": 0.50},
                        {"metric": "max_drawdown", "value": -0.10},
                        {"metric": "average_turnover", "value": 0.15},
                    ]
                ),
                "equity_frame": pd.DataFrame(
                    [
                        {"date": "2025-01-31", "equity": 1.02},
                        {"date": "2025-02-28", "equity": 1.05},
                    ]
                ),
            }
        ]
    )

    row = scorecard.iloc[0]
    assert row["strategy_id"] == "a"
    assert row["total_return"] == 0.50
    assert row["max_drawdown"] == -0.10
    assert row["return_drawdown_ratio"] == 5.0
    assert row["monthly_win_rate"] == 1.0
    assert row["turnover_penalized_stability"] > 0


def test_rank_mid_trend_validation_scorecard_prefers_better_drawdown_efficiency_and_stability() -> None:
    ranked = rank_mid_trend_validation_scorecard(
        pd.DataFrame(
            [
                {
                    "strategy_id": "stable",
                    "total_return": 0.40,
                    "max_drawdown": -0.08,
                    "return_drawdown_ratio": 5.0,
                    "monthly_win_rate": 0.75,
                    "turnover_penalized_stability": 0.70,
                },
                {
                    "strategy_id": "wild",
                    "total_return": 0.45,
                    "max_drawdown": -0.25,
                    "return_drawdown_ratio": 1.8,
                    "monthly_win_rate": 0.50,
                    "turnover_penalized_stability": 0.20,
                },
            ]
        )
    )

    assert ranked.iloc[0]["strategy_id"] == "stable"


def _current_regime_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "trade_date": "2025-01-01",
                "confirmed_regime_state": "weak_repair",
                "target_exposure": 0.2,
                "rebalance_allowed": True,
                "emotion_score": 45,
                "emotion_state": "neutral",
                "risk_state": "medium",
            },
            {
                "trade_date": "2025-01-02",
                "confirmed_regime_state": "bull_trend",
                "target_exposure": 1.0,
                "rebalance_allowed": True,
                "emotion_score": 70,
                "emotion_state": "hot",
                "risk_state": "low",
            },
            {
                "trade_date": "2025-01-03",
                "confirmed_regime_state": "bull_trend",
                "target_exposure": 1.0,
                "rebalance_allowed": True,
                "emotion_score": 72,
                "emotion_state": "hot",
                "risk_state": "low",
            },
        ]
    )


def _current_funnel_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            _candidate("2025-01-01", "A", 1, 95),
            _candidate("2025-01-01", "B", 2, 94),
            _candidate("2025-01-02", "A", 1, 96),
            _candidate("2025-01-02", "C", 2, 93),
            _candidate("2025-01-03", "C", 1, 96),
            _candidate("2025-01-03", "D", 2, 92),
        ]
    )


def _current_prices_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"trade_date": "2025-01-01", "asset_id": "A", "high": 10.5, "low": 9.5, "close": 10.0},
            {"trade_date": "2025-01-01", "asset_id": "B", "high": 20.5, "low": 19.5, "close": 20.0},
            {"trade_date": "2025-01-01", "asset_id": "C", "high": 30.5, "low": 29.5, "close": 30.0},
            {"trade_date": "2025-01-01", "asset_id": "D", "high": 40.5, "low": 39.5, "close": 40.0},
            {"trade_date": "2025-01-02", "asset_id": "A", "high": 11.5, "low": 10.5, "close": 11.0},
            {"trade_date": "2025-01-02", "asset_id": "B", "high": 19.5, "low": 18.5, "close": 19.0},
            {"trade_date": "2025-01-02", "asset_id": "C", "high": 33.5, "low": 32.5, "close": 33.0},
            {"trade_date": "2025-01-02", "asset_id": "D", "high": 39.5, "low": 38.5, "close": 39.0},
            {"trade_date": "2025-01-03", "asset_id": "A", "high": 12.5, "low": 11.5, "close": 12.0},
            {"trade_date": "2025-01-03", "asset_id": "B", "high": 18.5, "low": 17.5, "close": 18.0},
            {"trade_date": "2025-01-03", "asset_id": "C", "high": 34.5, "low": 33.5, "close": 34.0},
            {"trade_date": "2025-01-03", "asset_id": "D", "high": 42.5, "low": 41.5, "close": 42.0},
        ]
    )


def _current_asset_names_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"asset_id": "A", "stock_name": "Alpha"},
            {"asset_id": "B", "stock_name": "Beta"},
            {"asset_id": "C", "stock_name": "Gamma"},
            {"asset_id": "D", "stock_name": "Delta"},
        ]
    )


def _shadow_top10_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"trade_date": "2025-01-01", "asset_id": "A", "shadow_top10_rank": 1, "mid_trend_funnel_score": 90},
            {"trade_date": "2025-01-01", "asset_id": "B", "shadow_top10_rank": 2, "mid_trend_funnel_score": 80},
            {"trade_date": "2025-01-02", "asset_id": "B", "shadow_top10_rank": 1, "mid_trend_funnel_score": 90},
            {"trade_date": "2025-01-02", "asset_id": "C", "shadow_top10_rank": 2, "mid_trend_funnel_score": 80},
        ]
    )


def _shadow_prices_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"trade_date": "2025-01-01", "asset_id": "A", "close": 10.0},
            {"trade_date": "2025-01-01", "asset_id": "B", "close": 20.0},
            {"trade_date": "2025-01-01", "asset_id": "C", "close": 30.0},
            {"trade_date": "2025-01-02", "asset_id": "A", "close": 11.0},
            {"trade_date": "2025-01-02", "asset_id": "B", "close": 18.0},
            {"trade_date": "2025-01-02", "asset_id": "C", "close": 30.0},
            {"trade_date": "2025-01-03", "asset_id": "A", "close": 11.0},
            {"trade_date": "2025-01-03", "asset_id": "B", "close": 19.8},
            {"trade_date": "2025-01-03", "asset_id": "C", "close": 33.0},
        ]
    )


def _candidate(trade_date: str, asset_id: str, score_rank: int, score: float) -> dict[str, object]:
    return {
        "trade_date": trade_date,
        "asset_id": asset_id,
        "score_rank": score_rank,
        "score_total": score,
        "rank": score_rank,
        "mid_trend_funnel_score": score,
        "mid_trend_layer": "stable_trend_watch",
        "industry_name": "Tech",
        "mainline_status": "sustained_mainline",
        "industry_mainline_score_v1": 0.6,
        "ret_20_score": 80,
        "ret_60_score": 80,
        "trend_r2_20_score": 80,
        "max_drawdown_20_score": 80,
        "volatility_20_score": 80,
    }
