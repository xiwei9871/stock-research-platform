from dataclasses import dataclass, field, replace
from typing import Any, Callable

import pandas as pd

from stock_research.vectorized_topn_backtest import (
    VectorizedTopNConfig,
    VectorizedTopNResult,
    load_vectorized_topn_inputs,
    run_vectorized_topn_backtest,
)


@dataclass(frozen=True)
class TopNStrategyConfig:
    start_date: object
    end_date: object
    score_version: str = "manual_v1"
    adjust_type: str = "hfq"
    top_n: int = 20
    rebalance_frequency: str = "daily"
    transaction_cost_bps: float = 0.0
    max_positions: int | None = None
    strategy_id: str | None = None


@dataclass(frozen=True)
class StrategyLifecycleContext:
    config: TopNStrategyConfig
    scores: pd.DataFrame = field(default_factory=pd.DataFrame)
    prices: pd.DataFrame = field(default_factory=pd.DataFrame)
    signals: pd.DataFrame = field(default_factory=pd.DataFrame)
    backtest_result: VectorizedTopNResult | None = None
    report: dict[str, Any] = field(default_factory=dict)
    lifecycle_steps: list[str] = field(default_factory=list)


Loader = Callable[[object, object, str, str], tuple[pd.DataFrame, pd.DataFrame]]
BacktestRunner = Callable[[pd.DataFrame, pd.DataFrame, VectorizedTopNConfig], VectorizedTopNResult]


def prepare_data(
    config: TopNStrategyConfig,
    loader: Loader = load_vectorized_topn_inputs,
) -> StrategyLifecycleContext:
    scores, prices = loader(
        config.start_date,
        config.end_date,
        config.score_version,
        config.adjust_type,
    )
    return StrategyLifecycleContext(
        config=config,
        scores=scores,
        prices=prices,
        lifecycle_steps=["prepare_data"],
    )


def before_market(context: StrategyLifecycleContext) -> StrategyLifecycleContext:
    return _append_step(context, "before_market")


def generate_signals(context: StrategyLifecycleContext) -> StrategyLifecycleContext:
    signals = _candidate_signals(context.scores, context.config)
    return replace(
        context,
        signals=signals,
        lifecycle_steps=[*context.lifecycle_steps, "generate_signals"],
    )


def rebalance(
    context: StrategyLifecycleContext,
    backtest_runner: BacktestRunner = run_vectorized_topn_backtest,
) -> StrategyLifecycleContext:
    vectorized_config = VectorizedTopNConfig(
        start_date=context.config.start_date,
        end_date=context.config.end_date,
        top_n=context.config.top_n,
        rebalance_frequency=context.config.rebalance_frequency,
        transaction_cost_bps=context.config.transaction_cost_bps,
        max_positions=context.config.max_positions,
    )
    result = backtest_runner(context.signals, context.prices, vectorized_config)
    return replace(
        context,
        backtest_result=result,
        lifecycle_steps=[*context.lifecycle_steps, "rebalance"],
    )


def after_market(context: StrategyLifecycleContext) -> StrategyLifecycleContext:
    return _append_step(context, "after_market")


def generate_report(context: StrategyLifecycleContext) -> StrategyLifecycleContext:
    result = context.backtest_result
    report = {
        "strategy_id": _strategy_id(context.config),
        "start_date": _iso_date(context.config.start_date),
        "end_date": _iso_date(context.config.end_date),
        "score_version": context.config.score_version,
        "top_n": context.config.top_n,
        "rebalance_frequency": context.config.rebalance_frequency,
        "score_rows": int(len(context.scores)),
        "signal_rows": int(len(context.signals)),
        "price_rows": int(len(context.prices)),
        "summary": result.summary if result is not None else {},
        "latest_equity": _latest_equity(result),
    }
    return replace(
        context,
        report=report,
        lifecycle_steps=[*context.lifecycle_steps, "generate_report"],
    )


def run_topn_strategy_lifecycle(
    config: TopNStrategyConfig,
    loader: Loader = load_vectorized_topn_inputs,
    backtest_runner: BacktestRunner = run_vectorized_topn_backtest,
) -> StrategyLifecycleContext:
    context = prepare_data(config, loader=loader)
    context = before_market(context)
    context = generate_signals(context)
    context = rebalance(context, backtest_runner=backtest_runner)
    context = after_market(context)
    return generate_report(context)


def _append_step(
    context: StrategyLifecycleContext,
    step: str,
) -> StrategyLifecycleContext:
    return replace(context, lifecycle_steps=[*context.lifecycle_steps, step])


def _candidate_signals(scores: pd.DataFrame, config: TopNStrategyConfig) -> pd.DataFrame:
    if scores.empty:
        return pd.DataFrame(columns=["trade_date", "asset_id", "rank", "score_total"])

    frame = scores.copy()
    frame["trade_date"] = frame["trade_date"].map(_iso_date)
    start = _iso_date(config.start_date)
    end = _iso_date(config.end_date)
    frame = frame[(frame["trade_date"] >= start) & (frame["trade_date"] <= end)]
    frame["rank"] = pd.to_numeric(frame["rank"], errors="coerce")
    frame["score_total"] = pd.to_numeric(frame["score_total"], errors="coerce")
    frame = frame.dropna(subset=["rank"]).sort_values(
        ["trade_date", "rank", "score_total", "asset_id"],
        ascending=[True, True, False, True],
    )

    limit = config.top_n
    if config.max_positions is not None:
        limit = min(limit, config.max_positions)
    return frame.groupby("trade_date", group_keys=False).head(limit).reset_index(drop=True)


def _strategy_id(config: TopNStrategyConfig) -> str:
    if config.strategy_id:
        return config.strategy_id
    return (
        f"topn_lifecycle:{_iso_date(config.start_date)}:{_iso_date(config.end_date)}:"
        f"{config.score_version}:top{config.top_n}:{config.rebalance_frequency}"
    )


def _iso_date(value: object) -> str:
    return pd.Timestamp(value).date().isoformat()


def _latest_equity(result: VectorizedTopNResult | None) -> float | None:
    if result is None or result.equity_curve.empty:
        return None
    return float(result.equity_curve.iloc[-1]["equity"])
