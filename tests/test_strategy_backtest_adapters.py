import pandas as pd
import pytest

from stock_research.dashboard.strategy_backtest_adapters import (
    STRATEGY_BACKTEST_REGISTRY,
    StrategyBacktestParams,
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


def test_strategy_backtest_params_defaults():
    params = StrategyBacktestParams(start_date="2026-01-01", end_date="2026-06-08")

    assert params.score_version == "manual_v1"
    assert params.adjust_type == "hfq"
