"""T12: TB / MT adapters reproduce the old simulators in LEGACY_COMPAT."""

import numpy as np
import pandas as pd
import pytest

from stock_research.backtest_constraints import BacktestExecutionConstraints
from stock_research.backtest_engine.adapters import (
    mid_trend_target_weights,
    positions_to_target_weights,
)
from stock_research.backtest_engine.legacy_compat import LegacyCompatConfig, execute_legacy_compat
from stock_research.market_style_switch_v1 import _simulate_equal_weight_daily
from stock_research.serenity_tight3b_c2_experiment import ProtectionConfig, _simulate_one_config


def _market(seed, n_days=80, n_assets=10):
    rng = np.random.default_rng(seed)
    days = pd.bdate_range("2025-01-02", periods=n_days).strftime("%Y-%m-%d").tolist()
    assets = [f"S{k:02d}" for k in range(n_assets)]
    close = {a: 20.0 + k for k, a in enumerate(assets)}
    prices, ranks = [], []
    for day in days:
        for a in assets:
            close[a] *= 1.0 + rng.normal(0.0005, 0.025)
            prices.append({"trade_date": day, "asset_id": a, "close": close[a],
                           "high": close[a] * 1.01, "low": close[a] * 0.99})
        order = np.argsort(-rng.normal(size=n_assets))
        for r, k in enumerate(order, start=1):
            ranks.append({"trade_date": day, "asset_id": assets[k], "bottleneck_rank": r,
                          "bottleneck_score": float(n_assets - r)})
    exposure = pd.DataFrame({"trade_date": days,
                             "target_exposure": rng.choice([1.0, 0.6, 0.3], size=n_days)})
    return days, pd.DataFrame(prices), pd.DataFrame(ranks), exposure


@pytest.mark.parametrize("seed", [2, 11])
@pytest.mark.parametrize("frequency", ["weekly", "monthly"])
def test_t12_tech_bottleneck_adapter_reproduces_serenity_engine(seed, frequency):
    days, prices, ranks, exposure = _market(seed)
    bps = 20.0
    old = _simulate_one_config(
        ranks=ranks, prices=prices, market_exposure=exposure, start_date=days[0],
        end_date=days[-1], universe_name="fixture", frequency=frequency, top_n=5,
        protection=ProtectionConfig(name="rank_exit_top10_1d", rank_exit=8),
        transaction_cost_bps=bps,
    )
    signal_dates = days[:-1]
    targets = positions_to_target_weights(old["positions"], signal_dates, strategy_id="tech_bottleneck")
    compat = LegacyCompatConfig(fill_lag=0, apply_constraints=False,
                                constraints=BacktestExecutionConstraints(commission_bps=bps))
    new = execute_legacy_compat(targets, prices, days, signal_dates, compat)["equity"]
    o = old["equity"][["trade_date", "equity", "transaction_cost"]].rename(columns={"trade_date": "date"})
    merged = o.merge(new[["date", "equity", "transaction_cost"]], on="date", suffixes=("_old", "_new"))
    assert len(merged) == len(o) == len(new)
    assert (merged.equity_old - merged.equity_new).abs().max() <= 1e-10
    assert (merged.transaction_cost_old - merged.transaction_cost_new).abs().max() <= 1e-12


def _mt_selection(days, prices, seed, budget=(1.0, 0.6, 0.2)):
    rng = np.random.default_rng(seed)
    assets = sorted(prices["asset_id"].unique())
    rows = []
    for day in days:
        w = float(rng.choice(budget))
        picks = rng.choice(assets, size=int(rng.integers(0, 4)), replace=False)
        if len(picks) == 0:
            rows.append({"trade_date": day, "asset_id": None, "invested_weight": w})
        for a in picks:
            rows.append({"trade_date": day, "asset_id": a, "invested_weight": w})
    return pd.DataFrame(rows)


@pytest.mark.parametrize("seed", [4, 9])
def test_t12_mid_trend_adapter_reproduces_equal_weight_daily(seed):
    days, prices, _, _ = _market(seed)
    selected = _mt_selection(days, prices, seed)
    old = _simulate_equal_weight_daily(prices, selected, strategy_family="mt")
    targets = mid_trend_target_weights(selected)
    signal_dates = days[:-1]
    compat = LegacyCompatConfig(fill_lag=0, apply_constraints=False)
    new = execute_legacy_compat(targets, prices, days, signal_dates, compat)["equity"]
    # Documented convention difference: MT dates the close(t)->close(t+1)
    # return on t; the engine dates it on t+1.
    shift = dict(zip(days[1:], days[:-1]))
    new = new.assign(date=new["date"].map(shift))
    merged = old[["trade_date", "equity"]].merge(
        new[["date", "equity"]].rename(columns={"date": "trade_date"}), on="trade_date",
        suffixes=("_old", "_new"))
    assert len(merged) == len(old)
    assert (merged.equity_old - merged.equity_new).abs().max() <= 1e-10


def test_t12_mid_trend_known_difference_missing_price_bar():
    """Recorded divergence, not hidden: when an asset has no bar on day d,
    MT's groupby-shift(-1) bridges the gap (books the d-1 -> d+1 move on
    d-1) and drops the asset on d; the engine books zero return for the
    missing bar. Equity therefore diverges from d-1 onwards."""
    days, prices, _, _ = _market(5, n_days=6, n_assets=3)
    prices = prices[~((prices.asset_id == "S01") & (prices.trade_date == days[3]))]
    selected = pd.DataFrame([{"trade_date": d, "asset_id": a, "invested_weight": 1.0}
                             for d in days for a in ("S00", "S01")])
    old = _simulate_equal_weight_daily(prices, selected, strategy_family="mt").set_index("trade_date")
    compat = LegacyCompatConfig(fill_lag=0, apply_constraints=False)
    new = execute_legacy_compat(mid_trend_target_weights(selected), prices, days, days[:-1],
                                compat)["equity"].set_index("date")
    assert old.loc[days[3], "priced_holdings"] == 1
    assert abs(old.loc[days[1], "equity"] - new.loc[days[2], "equity"]) <= 1e-10
    assert abs(old.loc[days[2], "equity"] - new.loc[days[3], "equity"]) > 1e-6


def test_adapters_tag_frozen_signal_replay_and_schedule_keeps_empty_days():
    from stock_research.backtest_engine.adapters import FROZEN_SIGNAL_REPLAY, signal_schedule

    days, prices, _, _ = _market(3, n_days=8, n_assets=3)
    selected = pd.DataFrame([{"trade_date": days[0], "asset_id": "S00", "invested_weight": 1.0},
                             {"trade_date": days[1], "asset_id": None, "invested_weight": 0.0}])
    targets = mid_trend_target_weights(selected)
    assert (targets["signal_provenance"] == FROZEN_SIGNAL_REPLAY).all()
    assert days[1] not in set(targets["signal_date"])        # cash day has no rows ...
    sched = signal_schedule(selected["trade_date"])
    assert days[1] in set(sched["signal_date"])              # ... but stays a decision
    assert sched["signal_ts"].str.endswith("+08:00").all()
