from __future__ import annotations

import pandas as pd
import pytest

from stock_research.mid_trend_stock_protection_v1 import (
    StockProtectionConfig,
    apply_stock_protection_to_selection,
    compute_atr20,
)


def test_fixed_stop_excludes_asset_after_entry_drawdown() -> None:
    selection = pd.DataFrame(
        [
            {"trade_date": "2025-01-01", "asset_id": "A", "invested_weight": 1.0},
            {"trade_date": "2025-01-02", "asset_id": "A", "invested_weight": 1.0},
            {"trade_date": "2025-01-03", "asset_id": "A", "invested_weight": 1.0},
        ]
    )
    prices = pd.DataFrame(
        [
            {"trade_date": "2025-01-01", "asset_id": "A", "high": 10.5, "low": 9.5, "close": 10.0},
            {"trade_date": "2025-01-02", "asset_id": "A", "high": 9.4, "low": 8.8, "close": 8.9},
            {"trade_date": "2025-01-03", "asset_id": "A", "high": 9.2, "low": 8.7, "close": 9.0},
        ]
    )
    protected = apply_stock_protection_to_selection(
        selection,
        prices,
        pd.DataFrame(),
        StockProtectionConfig(variant_name="fixed_stop_10", fixed_stop_loss=0.10),
    )

    assert protected.loc[protected["trade_date"] == "2025-01-01", "asset_id"].tolist() == ["A"]
    day2 = protected[protected["trade_date"] == "2025-01-02"].iloc[0]
    assert pd.isna(day2["asset_id"])
    assert day2["protection_reason"] == "fixed_stop_loss"


def test_atr_score_confirmed_exit_requires_score_break() -> None:
    selection = pd.DataFrame(
        [
            {"trade_date": "2025-01-01", "asset_id": "A", "invested_weight": 1.0},
            {"trade_date": "2025-01-02", "asset_id": "A", "invested_weight": 1.0},
            {"trade_date": "2025-01-03", "asset_id": "A", "invested_weight": 1.0},
        ]
    )
    prices = pd.DataFrame(
        [
            {"trade_date": "2025-01-01", "asset_id": "A", "high": 10.5, "low": 9.5, "close": 10.0},
            {"trade_date": "2025-01-02", "asset_id": "A", "high": 10.2, "low": 9.7, "close": 10.0},
            {"trade_date": "2025-01-03", "asset_id": "A", "high": 10.0, "low": 8.9, "close": 9.0},
        ]
    )
    funnel = pd.DataFrame(
        [
            {"trade_date": "2025-01-01", "asset_id": "A", "score_rank": 5, "mid_trend_funnel_score": 90},
            {"trade_date": "2025-01-02", "asset_id": "A", "score_rank": 6, "mid_trend_funnel_score": 89},
            {"trade_date": "2025-01-03", "asset_id": "A", "score_rank": 35, "mid_trend_funnel_score": 80},
        ]
    )
    protected = apply_stock_protection_to_selection(
        selection,
        prices,
        funnel,
        StockProtectionConfig(
            variant_name="atr_score",
            atr_multiple=1.0,
            score_break_rank=30,
            score_decline_days=2,
        ),
    )

    day3 = protected[protected["trade_date"] == "2025-01-03"].iloc[0]
    assert pd.isna(day3["asset_id"])
    assert day3["protection_reason"] == "atr_score_confirmed"


def test_atr_break_without_score_break_keeps_asset() -> None:
    selection = pd.DataFrame(
        [
            {"trade_date": "2025-01-01", "asset_id": "A", "invested_weight": 1.0},
            {"trade_date": "2025-01-02", "asset_id": "A", "invested_weight": 1.0},
        ]
    )
    prices = pd.DataFrame(
        [
            {"trade_date": "2025-01-01", "asset_id": "A", "high": 10.5, "low": 9.5, "close": 10.0},
            {"trade_date": "2025-01-02", "asset_id": "A", "high": 10.0, "low": 8.9, "close": 9.0},
        ]
    )
    funnel = pd.DataFrame(
        [
            {"trade_date": "2025-01-01", "asset_id": "A", "score_rank": 5, "mid_trend_funnel_score": 90},
            {"trade_date": "2025-01-02", "asset_id": "A", "score_rank": 6, "mid_trend_funnel_score": 89},
        ]
    )
    protected = apply_stock_protection_to_selection(
        selection,
        prices,
        funnel,
        StockProtectionConfig(
            variant_name="atr_score",
            atr_multiple=1.0,
            score_break_rank=30,
            score_decline_days=2,
        ),
    )

    assert protected.loc[protected["trade_date"] == "2025-01-02", "asset_id"].tolist() == ["A"]


def test_compute_atr20_uses_true_range_by_asset() -> None:
    prices = pd.DataFrame(
        [
            {"trade_date": "2025-01-01", "asset_id": "A", "high": 11.0, "low": 10.0, "close": 10.5},
            {"trade_date": "2025-01-02", "asset_id": "A", "high": 12.0, "low": 10.8, "close": 11.8},
        ]
    )

    result = compute_atr20(prices, window=2)

    assert result.loc[result["trade_date"] == "2025-01-01", "atr20"].iloc[0] == pytest.approx(1.0)
    assert result.loc[result["trade_date"] == "2025-01-02", "atr20"].iloc[0] == pytest.approx(1.25)


def test_rank_break_can_require_consecutive_days() -> None:
    selection = pd.DataFrame(
        [
            {"trade_date": "2025-01-01", "asset_id": "A", "invested_weight": 1.0},
            {"trade_date": "2025-01-02", "asset_id": "A", "invested_weight": 1.0},
            {"trade_date": "2025-01-03", "asset_id": "A", "invested_weight": 1.0},
        ]
    )
    prices = pd.DataFrame(
        [
            {"trade_date": "2025-01-01", "asset_id": "A", "high": 10.5, "low": 9.5, "close": 10.0, "atr20": 0.5},
            {"trade_date": "2025-01-02", "asset_id": "A", "high": 10.0, "low": 8.9, "close": 9.0, "atr20": 0.5},
            {"trade_date": "2025-01-03", "asset_id": "A", "high": 9.8, "low": 8.8, "close": 8.9, "atr20": 0.5},
        ]
    )
    funnel = pd.DataFrame(
        [
            {"trade_date": "2025-01-01", "asset_id": "A", "score_rank": 10, "mid_trend_funnel_score": 90},
            {"trade_date": "2025-01-02", "asset_id": "A", "score_rank": 25, "mid_trend_funnel_score": 89},
            {"trade_date": "2025-01-03", "asset_id": "A", "score_rank": 26, "mid_trend_funnel_score": 88},
        ]
    )

    protected = apply_stock_protection_to_selection(
        selection,
        prices,
        funnel,
        StockProtectionConfig(
            variant_name="atr_rank_two_day",
            atr_multiple=1.0,
            score_break_rank=20,
            rank_break_days=2,
            score_decline_days=10,
        ),
    )

    assert protected.loc[protected["trade_date"] == "2025-01-02", "asset_id"].tolist() == ["A"]
    day3 = protected[protected["trade_date"] == "2025-01-03"].iloc[0]
    assert pd.isna(day3["asset_id"])
    assert day3["protection_reason"] == "atr_score_confirmed"


def test_single_day_rank_break_confirms_without_score_decline() -> None:
    selection = pd.DataFrame(
        [
            {"trade_date": "2025-01-01", "asset_id": "A", "invested_weight": 1.0},
            {"trade_date": "2025-01-02", "asset_id": "A", "invested_weight": 1.0},
        ]
    )
    prices = pd.DataFrame(
        [
            {"trade_date": "2025-01-01", "asset_id": "A", "high": 10.5, "low": 9.5, "close": 10.0, "atr20": 0.5},
            {"trade_date": "2025-01-02", "asset_id": "A", "high": 10.0, "low": 8.9, "close": 9.0, "atr20": 0.5},
        ]
    )
    funnel = pd.DataFrame(
        [
            {"trade_date": "2025-01-01", "asset_id": "A", "score_rank": 5, "mid_trend_funnel_score": 80},
            {"trade_date": "2025-01-02", "asset_id": "A", "score_rank": 25, "mid_trend_funnel_score": 81},
        ]
    )

    protected = apply_stock_protection_to_selection(
        selection,
        prices,
        funnel,
        StockProtectionConfig(
            variant_name="atr_rank_single_day",
            atr_multiple=1.0,
            score_break_rank=20,
            rank_break_days=1,
            score_decline_days=2,
        ),
    )

    day2 = protected[protected["trade_date"] == "2025-01-02"].iloc[0]
    assert pd.isna(day2["asset_id"])
    assert day2["protection_reason"] == "atr_score_confirmed"


def test_regime_specific_atr_multiple_controls_exit_sensitivity() -> None:
    selection = pd.DataFrame(
        [
            {
                "trade_date": "2025-01-01",
                "asset_id": "A",
                "invested_weight": 1.0,
                "confirmed_regime_state": "bull_trend",
            },
            {
                "trade_date": "2025-01-02",
                "asset_id": "A",
                "invested_weight": 1.0,
                "confirmed_regime_state": "bull_trend",
            },
            {
                "trade_date": "2025-01-01",
                "asset_id": "B",
                "invested_weight": 1.0,
                "confirmed_regime_state": "weak_repair",
            },
            {
                "trade_date": "2025-01-02",
                "asset_id": "B",
                "invested_weight": 1.0,
                "confirmed_regime_state": "weak_repair",
            },
        ]
    )
    prices = pd.DataFrame(
        [
            {"trade_date": "2025-01-01", "asset_id": "A", "high": 10.5, "low": 9.5, "close": 10.0, "atr20": 0.5},
            {"trade_date": "2025-01-02", "asset_id": "A", "high": 10.0, "low": 8.9, "close": 9.0, "atr20": 0.5},
            {"trade_date": "2025-01-01", "asset_id": "B", "high": 10.5, "low": 9.5, "close": 10.0, "atr20": 0.5},
            {"trade_date": "2025-01-02", "asset_id": "B", "high": 10.0, "low": 8.9, "close": 9.0, "atr20": 0.5},
        ]
    )
    funnel = pd.DataFrame(
        [
            {"trade_date": "2025-01-01", "asset_id": "A", "score_rank": 10, "mid_trend_funnel_score": 90},
            {"trade_date": "2025-01-02", "asset_id": "A", "score_rank": 25, "mid_trend_funnel_score": 89},
            {"trade_date": "2025-01-01", "asset_id": "B", "score_rank": 10, "mid_trend_funnel_score": 90},
            {"trade_date": "2025-01-02", "asset_id": "B", "score_rank": 25, "mid_trend_funnel_score": 89},
        ]
    )

    protected = apply_stock_protection_to_selection(
        selection,
        prices,
        funnel,
        StockProtectionConfig(
            variant_name="regime_atr",
            atr_multiple=2.5,
            atr_multiple_by_regime={"weak_repair": 1.0, "bull_trend": 3.0},
            score_break_rank=20,
        ),
    )

    day2 = protected[protected["trade_date"] == "2025-01-02"].sort_values("asset_id", na_position="last")
    assert "A" in day2["asset_id"].dropna().tolist()
    blocked = day2[day2["asset_id"].isna()].iloc[0]
    assert blocked["protection_reason"] == "atr_score_confirmed"
