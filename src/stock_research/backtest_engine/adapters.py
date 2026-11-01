"""Strategy -> target-weight adapters.

Adapters keep each strategy's own scoring/selection untouched and only
express its decision as target weights for the execution engine.

Provenance labels (must be carried into every report):
  FROZEN_SIGNAL_REPLAY  decisions were taken from an old simulator's
                        output; they do NOT react to the new engine's
                        actual holdings (blocked fills, drift). Measures the
                        effect of execution rules only.
  FULL_STRATEGY_REPLAY  decisions regenerated from the new engine's actual
                        holdings and point-in-time inputs. Not implemented
                        in V0.1 for TB/MT (their exit logic lives inside
                        their simulators).
TopN selection does not depend on holdings, so its targets are equivalent
under both labels; it is still tagged FROZEN_SIGNAL_REPLAY when produced
from scores computed outside the engine.
"""

from __future__ import annotations

import pandas as pd

from stock_research import vectorized_topn_backtest as topn

FROZEN_SIGNAL_REPLAY = "FROZEN_SIGNAL_REPLAY"
FULL_STRATEGY_REPLAY = "FULL_STRATEGY_REPLAY"
EX_POST_UNIVERSE = "EX_POST_UNIVERSE"


def signal_schedule(dates, *, signal_time: str = "15:00:00", tz_offset: str = "+08:00",
                    inputs_asof_time: str | None = None) -> pd.DataFrame:
    """Explicit decision schedule. Every listed date is a decision; a date
    without target rows means ALL_CASH_TARGET."""
    days = sorted({pd.Timestamp(d).date().isoformat() for d in dates})
    frame = pd.DataFrame({"signal_date": days,
                          "signal_ts": [f"{d}T{signal_time}{tz_offset}" for d in days]})
    if inputs_asof_time is not None:
        frame["inputs_asof_ts"] = [f"{d}T{inputs_asof_time}{tz_offset}" for d in days]
    return frame


def topn_target_weights(
    scores: pd.DataFrame,
    prices: pd.DataFrame,
    config: topn.VectorizedTopNConfig,
    *,
    strategy_id: str = "topn",
) -> tuple[pd.DataFrame, list[str], list[str]]:
    """Reproduce vectorized_topn_backtest selection as target weights.

    Returns (target_weights in rank order, signal_dates, trading_dates).
    Uses the old module's own helpers so the selection is identical.
    """
    norm_scores = topn._normalize_scores(scores)
    norm_prices = topn._normalize_prices(prices)
    trading_dates = topn._trading_dates(norm_prices, config.start_date, config.end_date)
    signal_dates = topn._rebalance_dates(norm_scores, trading_dates, config.rebalance_frequency)
    rows = []
    for day in signal_dates:
        weights, _ = topn._target_weights_for_date(norm_scores, day, config)
        for asset_id, weight in weights.items():
            rows.append({"signal_date": day, "asset_id": asset_id, "target_weight": weight,
                         "strategy_id": strategy_id, "signal_provenance": FROZEN_SIGNAL_REPLAY})
    frame = pd.DataFrame(rows, columns=["signal_date", "asset_id", "target_weight", "strategy_id",
                                        "signal_provenance"])
    return frame, signal_dates, trading_dates


def positions_to_target_weights(
    positions: pd.DataFrame,
    signal_dates: list[str],
    *,
    date_col: str = "trade_date",
    weight_col: str = "weight",
    strategy_id: str,
) -> pd.DataFrame:
    """Turn an old engine's per-day post-decision weights into targets.

    Used for engines (TB serenity, MT) whose selection/protection logic is
    interleaved with their simulator: the weights they decided on each date
    are the strategy's target for that date. Dates in signal_dates with no
    rows mean "target = all cash".
    """
    if positions.empty:
        return pd.DataFrame(columns=["signal_date", "asset_id", "target_weight", "strategy_id"])
    frame = positions[[date_col, "asset_id", weight_col]].copy()
    frame.columns = ["signal_date", "asset_id", "target_weight"]
    frame["signal_date"] = pd.to_datetime(frame["signal_date"]).dt.strftime("%Y-%m-%d")
    frame = frame[frame["signal_date"].isin(set(signal_dates)) & (frame["target_weight"] > 0)]
    frame["strategy_id"] = strategy_id
    frame["signal_provenance"] = FROZEN_SIGNAL_REPLAY
    return frame.reset_index(drop=True)


def mid_trend_target_weights(selected: pd.DataFrame, *, strategy_id: str = "mid_trend") -> pd.DataFrame:
    """MT selection rows (trade_date, asset_id, invested_weight) -> targets.

    The old MT simulator holds invested_weight split equally across the
    day's selected assets (rebalanced daily).
    """
    frame = selected.copy()
    frame["signal_date"] = pd.to_datetime(frame["trade_date"], format="mixed").dt.strftime("%Y-%m-%d")
    frame["invested_weight"] = pd.to_numeric(frame["invested_weight"], errors="coerce").fillna(0.0)
    frame = frame[frame["asset_id"].notna() & (frame["asset_id"].astype(str) != "")]
    frame = frame.drop_duplicates(["signal_date", "asset_id"])
    counts = frame.groupby("signal_date")["asset_id"].transform("count")
    frame["target_weight"] = frame["invested_weight"] / counts
    frame = frame[frame["target_weight"] > 0]
    frame["strategy_id"] = strategy_id
    frame["signal_provenance"] = FROZEN_SIGNAL_REPLAY
    return frame[["signal_date", "asset_id", "target_weight", "strategy_id",
                  "signal_provenance"]].reset_index(drop=True)
