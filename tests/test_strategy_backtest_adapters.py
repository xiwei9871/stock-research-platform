import pandas as pd
import pytest

from stock_research.dashboard.strategy_backtest_adapters import (
    STRATEGY_BACKTEST_REGISTRY,
    StrategyBacktestParams,
    build_lhb_shortline_scores_from_frames,
    build_manual_v1_scores_from_frame,
    normalize_strategy_scores,
)


def test_registry_contains_all_backtest_lab_strategies():
    assert set(STRATEGY_BACKTEST_REGISTRY) == {
        "manual_v1_topn_rotation",
        "lhb_shortline",
        "mid_trend",
        "tech_bottleneck",
        "position_control",
    }


def test_normalize_strategy_scores_ranks_high_scores_first():
    raw = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "B", "score_total": 80.0},
            {"trade_date": "2026-01-01", "asset_id": "A", "score_total": 90.0},
            {"trade_date": "2026-01-02", "asset_id": "A", "score_total": 70.0},
        ]
    )

    scores = normalize_strategy_scores(raw, strategy_id="unit_strategy")

    assert list(scores["trade_date"]) == ["2026-01-01", "2026-01-01", "2026-01-02"]
    assert list(scores["asset_id"]) == ["A", "B", "A"]
    assert list(scores["rank"]) == [1, 2, 1]
    assert list(scores["strategy_id"].unique()) == ["unit_strategy"]


def test_normalize_strategy_scores_rejects_empty_signal_set():
    with pytest.raises(ValueError, match="no unit_strategy strategy scores found"):
        normalize_strategy_scores(pd.DataFrame(), strategy_id="unit_strategy")


def test_normalize_strategy_scores_drops_missing_values_before_formatting_dates():
    raw = pd.DataFrame(
        [
            {
                "trade_date": pd.Timestamp("2026-01-01"),
                "asset_id": "A",
                "score_total": 90.0,
            },
            {"trade_date": None, "asset_id": "B", "score_total": 80.0},
            {"trade_date": "2026-01-01", "asset_id": None, "score_total": 70.0},
            {"trade_date": "2026-01-01", "asset_id": "C", "score_total": float("nan")},
        ]
    )

    scores = normalize_strategy_scores(raw, strategy_id="unit_strategy")

    assert len(scores) == 1
    assert scores.loc[0, "trade_date"] == "2026-01-01"
    assert scores.loc[0, "asset_id"] == "A"


def test_strategy_backtest_params_defaults():
    params = StrategyBacktestParams(start_date="2026-01-01", end_date="2026-06-08")

    assert params.score_version == "manual_v1"
    assert params.adjust_type == "hfq"


def test_manual_v1_builder_preserves_manual_score_order():
    manual = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A", "rank": 2, "score_total": 80.0},
            {"trade_date": "2026-01-01", "asset_id": "B", "rank": 1, "score_total": 90.0},
        ]
    )

    scores = build_manual_v1_scores_from_frame(manual)

    assert list(scores["asset_id"]) == ["B", "A"]
    assert list(scores["rank"]) == [1, 2]


def test_lhb_shortline_builder_ranks_positive_support_above_risky_rows():
    lhb = pd.DataFrame(
        [
            {
                "trade_date": "2026-01-01",
                "asset_id": "A",
                "on_lhb": True,
                "lhb_net_buy_ratio": 0.22,
                "lhb_net_buy_amount": 80_000_000,
                "institution_net_buy": 20_000_000,
                "repeat_on_list_count_3d": 2,
                "lhb_after_reversal": True,
                "lhb_one_day_pump_risk": 0.10,
            },
            {
                "trade_date": "2026-01-01",
                "asset_id": "B",
                "on_lhb": True,
                "lhb_net_buy_ratio": -0.05,
                "lhb_net_buy_amount": -5_000_000,
                "institution_net_buy": -2_000_000,
                "repeat_on_list_count_3d": 1,
                "lhb_after_reversal": False,
                "lhb_one_day_pump_risk": 0.90,
            },
        ]
    )
    technical = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A", "amount_vs_20d": 1.5, "high_to_close_drawdown": 0.03},
            {"trade_date": "2026-01-01", "asset_id": "B", "amount_vs_20d": 0.3, "high_to_close_drawdown": 0.16},
        ]
    )

    scores = build_lhb_shortline_scores_from_frames(lhb, technical)

    assert list(scores["asset_id"]) == ["A", "B"]
    assert scores.iloc[0]["score_total"] > scores.iloc[1]["score_total"]
    assert scores.iloc[1]["eligibility"] is False
    assert "pump_risk" in scores.iloc[1]["eligibility_reason"]
