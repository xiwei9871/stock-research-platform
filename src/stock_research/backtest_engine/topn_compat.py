"""TopN through the unified engine: LEGACY_COMPAT regression + realistic run."""

from __future__ import annotations

import pandas as pd

from stock_research import vectorized_topn_backtest as topn
from stock_research.backtest_engine.adapters import topn_target_weights
from stock_research.backtest_engine.legacy_compat import LegacyCompatConfig, execute_legacy_compat


def run_topn_legacy_compat(
    scores: pd.DataFrame,
    prices: pd.DataFrame,
    config: topn.VectorizedTopNConfig,
) -> dict[str, pd.DataFrame]:
    targets, signal_dates, trading_dates = topn_target_weights(scores, prices, config)
    compat = LegacyCompatConfig(
        fill_lag=1,
        apply_constraints=True,
        constraints=topn._effective_execution_constraints(config),
    )
    result = execute_legacy_compat(
        targets, topn._normalize_prices(prices), trading_dates, signal_dates, compat
    )
    result["targets"] = targets
    return result


def compare_equity(old: pd.DataFrame, new: pd.DataFrame) -> pd.DataFrame:
    """Day-by-day diff of two equity curves on (date, equity, net_return, cost)."""
    cols = ["date", "equity", "net_return", "transaction_cost", "turnover"]
    merged = old[cols].merge(new[cols], on="date", how="outer", suffixes=("_old", "_new"),
                             indicator=True)
    for col in cols[1:]:
        merged[f"{col}_absdiff"] = (merged[f"{col}_old"] - merged[f"{col}_new"]).abs()
    return merged.sort_values("date").reset_index(drop=True)
