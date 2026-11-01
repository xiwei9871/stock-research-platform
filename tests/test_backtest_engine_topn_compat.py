import numpy as np
import pandas as pd
import pytest

from stock_research.backtest_constraints import BacktestExecutionConstraints
from stock_research.backtest_engine.topn_compat import compare_equity, run_topn_legacy_compat
from stock_research.vectorized_topn_backtest import VectorizedTopNConfig, run_vectorized_topn_backtest


def _fixture(seed: int, n_days: int = 60, n_assets: int = 12, flag_rate: float = 0.08):
    rng = np.random.default_rng(seed)
    days = pd.bdate_range("2024-01-02", periods=n_days).strftime("%Y-%m-%d").tolist()
    assets = [f"A{k:02d}" for k in range(n_assets)]
    price_rows, score_rows = [], []
    close = {a: 10.0 + k for k, a in enumerate(assets)}
    for day in days:
        for asset in assets:
            close[asset] *= 1.0 + rng.normal(0, 0.02)
            up = rng.random() < flag_rate
            down = (not up) and rng.random() < flag_rate
            price_rows.append({
                "trade_date": day, "asset_id": asset, "open": close[asset], "close": close[asset],
                "amount": 1e8, "trade_status": "1", "is_limit_up": up, "is_limit_down": down,
                "is_suspended": rng.random() < flag_rate / 2,
            })
        scores = rng.normal(size=n_assets)
        order = np.argsort(-scores)
        for rank, k in enumerate(order, start=1):
            score_rows.append({"trade_date": day, "asset_id": assets[k], "rank": rank,
                               "score_total": float(scores[k])})
    return pd.DataFrame(score_rows), pd.DataFrame(price_rows), days


CASES = [
    dict(top_n=3, rebalance_frequency="daily"),
    dict(top_n=5, rebalance_frequency="weekly"),
    dict(top_n=4, rebalance_frequency="daily", transaction_cost_bps=15.0),
    dict(top_n=4, rebalance_frequency="daily", max_position_weight=0.2,
         execution_constraints=BacktestExecutionConstraints(commission_bps=2.5, stamp_duty_bps=5.0,
                                                            slippage_bps=10.0)),
    dict(top_n=6, rebalance_frequency="weekly", max_positions=4,
         execution_constraints=BacktestExecutionConstraints(commission_bps=3.0,
                                                            block_missing_limit_state=True)),
]


@pytest.mark.parametrize("seed", [1, 7, 42])
@pytest.mark.parametrize("case", CASES, ids=lambda c: "-".join(f"{k}={v}" for k, v in c.items() if k != "execution_constraints"))
def test_t11_topn_legacy_compat_matches_old_engine_daily(seed, case):
    scores, prices, days = _fixture(seed)
    config = VectorizedTopNConfig(start_date=days[0], end_date=days[-1], **case)
    old = run_vectorized_topn_backtest(scores, prices, config).equity_curve
    new = run_topn_legacy_compat(scores, prices, config)["equity"]
    diff = compare_equity(old, new)
    assert (diff["_merge"] == "both").all(), "date sets differ"
    assert diff["equity_absdiff"].max() <= 1e-10
    assert diff["net_return_absdiff"].max() <= 1e-10
    assert diff["transaction_cost_absdiff"].max() <= 1e-10


def test_t11_topn_legacy_compat_trades_match_old_engine():
    scores, prices, days = _fixture(3, flag_rate=0.15)
    config = VectorizedTopNConfig(start_date=days[0], end_date=days[-1], top_n=4,
                                  transaction_cost_bps=10.0)
    old = run_vectorized_topn_backtest(scores, prices, config).trades
    new = run_topn_legacy_compat(scores, prices, config)["trades"]
    keys = ["signal_date", "execution_date", "asset_id", "side"]
    cols = keys + ["executed_weight", "transaction_cost", "skip_reason"]
    o = old[cols].sort_values(keys).reset_index(drop=True)
    n = new[cols].sort_values(keys).reset_index(drop=True)
    assert len(o) == len(n)
    pd.testing.assert_frame_equal(o[keys], n[keys])
    assert (o["executed_weight"] - n["executed_weight"]).abs().max() <= 1e-12
    assert (o["transaction_cost"] - n["transaction_cost"]).abs().max() <= 1e-12
    assert o["skip_reason"].fillna("").tolist() == n["skip_reason"].fillna("").tolist()
