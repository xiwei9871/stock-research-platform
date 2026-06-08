from __future__ import annotations

import pandas as pd

from pathlib import Path

from stock_research.current_mid_trend_strategy_v1 import (
    build_current_mid_trend_strategy_v1_from_frames,
)


def test_current_mid_trend_strategy_v1_outputs_holdings_trades_and_summary(tmp_path: Path) -> None:
    regime = pd.DataFrame(
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
    funnel = pd.DataFrame(
        [
            _candidate("2025-01-01", "A", 1, 95),
            _candidate("2025-01-01", "B", 2, 94),
            _candidate("2025-01-02", "A", 1, 96),
            _candidate("2025-01-02", "C", 2, 93),
            _candidate("2025-01-03", "C", 1, 96),
            _candidate("2025-01-03", "D", 2, 92),
        ]
    )
    prices = pd.DataFrame(
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
    names = pd.DataFrame(
        [
            {"asset_id": "A", "stock_name": "Alpha"},
            {"asset_id": "B", "stock_name": "Beta"},
            {"asset_id": "C", "stock_name": "Gamma"},
            {"asset_id": "D", "stock_name": "Delta"},
        ]
    )

    result = build_current_mid_trend_strategy_v1_from_frames(
        regime=regime,
        funnel=funnel,
        prices=prices,
        asset_names=names,
        start_date="2025-01-01",
        end_date="2025-01-03",
        top_n=2,
        output_dir=tmp_path,
    )

    assert not result["summary"].empty
    assert not result["equity"].empty
    day1 = result["holdings"][result["holdings"]["trade_date"] == "2025-01-01"]
    assert day1["target_weight"].tolist() == [0.1, 0.1]
    day2_assets = set(result["holdings"][result["holdings"]["trade_date"] == "2025-01-02"]["asset_id"])
    assert day2_assets == {"A", "C"}
    trades = result["trades"]
    assert {"buy", "sell"}.issubset(set(trades["action"]))
    assert "current_mid_trend_strategy_v1_report.md" in str(result["paths"].get("report", ""))
    assert result["paths"]["report"].exists()


def test_current_mid_trend_strategy_v1_applies_c2_stock_protection() -> None:
    regime = pd.DataFrame(
        [
            {"trade_date": "2025-01-01", "confirmed_regime_state": "bull_trend", "target_exposure": 1.0, "rebalance_allowed": True},
            {"trade_date": "2025-01-02", "confirmed_regime_state": "bull_trend", "target_exposure": 1.0, "rebalance_allowed": True},
        ]
    )
    funnel = pd.DataFrame(
        [
            _candidate("2025-01-01", "A", 1, 90),
            _candidate("2025-01-01", "B", 2, 89),
            _candidate("2025-01-02", "A", 25, 91),
            _candidate("2025-01-02", "B", 2, 88),
        ]
    )
    prices = pd.DataFrame(
        [
            {"trade_date": "2025-01-01", "asset_id": "A", "high": 10.5, "low": 9.5, "close": 10.0, "atr20": 0.5},
            {"trade_date": "2025-01-01", "asset_id": "B", "high": 10.5, "low": 9.5, "close": 10.0, "atr20": 0.5},
            {"trade_date": "2025-01-02", "asset_id": "A", "high": 10.0, "low": 8.9, "close": 8.7, "atr20": 0.5},
            {"trade_date": "2025-01-02", "asset_id": "B", "high": 10.5, "low": 9.5, "close": 10.0, "atr20": 0.5},
        ]
    )

    result = build_current_mid_trend_strategy_v1_from_frames(
        regime=regime,
        funnel=funnel,
        prices=prices,
        start_date="2025-01-01",
        end_date="2025-01-02",
        top_n=2,
    )

    day2 = result["holdings"][result["holdings"]["trade_date"] == "2025-01-02"]
    assert int(day2["asset_id"].notna().sum()) == 1
    assert day2["protection_reason"].astype(str).str.contains("atr_score_confirmed").any()


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
