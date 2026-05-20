from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from stock_research.backtest_constraints import (
    BacktestExecutionConstraints,
    can_close_long,
    can_open_long,
    one_way_cost_rate,
)
from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all
from stock_research.run_card import write_run_card
from stock_research.services.universe_service import (
    UniverseResult,
    filter_dataframe_by_universe,
)


EQUITY_COLUMNS = [
    "date",
    "gross_return",
    "turnover",
    "transaction_cost",
    "net_return",
    "equity",
    "drawdown",
    "holdings_count",
]

POSITION_COLUMNS = [
    "rebalance_date",
    "asset_id",
    "rank",
    "score_total",
    "weight",
]

TRADE_COLUMNS = [
    "rebalance_date",
    "signal_date",
    "execution_date",
    "asset_id",
    "side",
    "previous_weight",
    "target_weight",
    "executed_weight",
    "delta_weight",
    "turnover_contribution",
    "transaction_cost",
    "skip_reason",
]


@dataclass(frozen=True)
class VectorizedTopNConfig:
    start_date: object
    end_date: object
    top_n: int = 20
    rebalance_frequency: str = "daily"
    transaction_cost_bps: float = 0.0
    max_positions: int | None = None
    execution_constraints: BacktestExecutionConstraints = field(
        default_factory=BacktestExecutionConstraints
    )


@dataclass(frozen=True)
class VectorizedTopNResult:
    config: VectorizedTopNConfig
    equity_curve: pd.DataFrame
    positions: pd.DataFrame
    trades: pd.DataFrame = field(default_factory=lambda: pd.DataFrame(columns=TRADE_COLUMNS))
    summary: dict[str, Any] = field(default_factory=dict)


def load_vectorized_topn_inputs(
    start_date: str,
    end_date: str,
    score_version: str = "manual_v1",
    adjust_type: str = "hfq",
    universe_result: UniverseResult | None = None,
    service: str = SETTINGS.research_service,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    score_sql = """
    SELECT trade_date, asset_id, rank, score_total
    FROM factor.stock_score_daily
    WHERE score_version = %s
      AND trade_date BETWEEN %s AND %s
    ORDER BY trade_date, rank, asset_id
    """
    price_sql = """
    SELECT trade_date, asset_id, open, close, amount, trade_status, is_limit_up, is_limit_down, is_suspended
    FROM market_daily_bar
    WHERE adjust_type = %s
      AND trade_date BETWEEN %s AND %s
    ORDER BY trade_date, asset_id
    """
    with connect(service) as conn:
        score_rows = fetch_all(conn, score_sql, [score_version, start_date, end_date])
        price_rows = fetch_all(conn, price_sql, [adjust_type, start_date, end_date])
    scores = filter_dataframe_by_universe(
        pd.DataFrame(score_rows),
        universe_result,
        asset_id_col="asset_id",
    )
    prices = filter_dataframe_by_universe(
        pd.DataFrame(price_rows),
        universe_result,
        asset_id_col="asset_id",
    )
    return scores, prices


def run_vectorized_topn_backtest(
    scores: pd.DataFrame,
    prices: pd.DataFrame,
    config: VectorizedTopNConfig,
    universe_result: UniverseResult | None = None,
) -> VectorizedTopNResult:
    if config.top_n <= 0:
        raise ValueError("top_n must be positive")
    if config.max_positions is not None and config.max_positions <= 0:
        raise ValueError("max_positions must be positive")
    if config.rebalance_frequency not in {"daily", "weekly"}:
        raise ValueError("rebalance_frequency must be daily or weekly")

    normalized_scores = filter_dataframe_by_universe(
        _normalize_scores(scores),
        universe_result,
        asset_id_col="asset_id",
    )
    normalized_prices = filter_dataframe_by_universe(
        _normalize_prices(prices),
        universe_result,
        asset_id_col="asset_id",
    )
    trading_dates = _trading_dates(normalized_prices, config.start_date, config.end_date)
    returns = _close_to_close_returns(normalized_prices)
    rebalance_dates = set(
        _rebalance_dates(normalized_scores, trading_dates, config.rebalance_frequency)
    )
    execution_constraints = _effective_execution_constraints(config)
    prices_by_date = _price_bars_by_date(normalized_prices)

    equity = 1.0
    peak = 1.0
    current_weights: dict[str, float] = {}
    cash_weight = 1.0
    pending_sell_targets: dict[str, dict[str, Any]] = {}
    equity_rows: list[dict[str, Any]] = []
    position_rows: list[dict[str, Any]] = []
    trade_rows: list[dict[str, Any]] = []
    for index, execution_date in enumerate(trading_dates[1:], start=1):
        signal_date = trading_dates[index - 1]
        turnover = 0.0
        trade_rows_for_date: list[dict[str, Any]] = []
        execution_bars = prices_by_date.get(execution_date, {})
        current_weights, cash_weight, pending_sell_targets, retry_rows = _retry_pending_sell_orders(
            current_weights=current_weights,
            cash_weight=cash_weight,
            pending_sell_targets=pending_sell_targets,
            execution_date=execution_date,
            execution_bars=execution_bars,
            constraints=execution_constraints,
        )
        trade_rows_for_date.extend(retry_rows)
        turnover = float(
            sum(
                abs(float(row["executed_weight"]) - float(row["previous_weight"]))
                for row in retry_rows
            )
        )
        if signal_date in rebalance_dates:
            target_weights, selected_rows = _target_weights_for_date(
                normalized_scores,
                signal_date,
                config,
            )
            current_weights, cash_weight, pending_sell_targets, signal_rows = _execute_signal_rebalance(
                signal_date=signal_date,
                execution_date=execution_date,
                current_weights=current_weights,
                cash_weight=cash_weight,
                target_weights=target_weights,
                execution_bars=execution_bars,
                constraints=execution_constraints,
                pending_sell_targets=pending_sell_targets,
            )
            trade_rows_for_date.extend(signal_rows)
            position_rows.extend(selected_rows)
            turnover = float(
                sum(
                    abs(float(row["executed_weight"]) - float(row["previous_weight"]))
                    for row in trade_rows_for_date
                )
            )

        trade_rows.extend(trade_rows_for_date)
        next_index = index + 1
        if next_index >= len(trading_dates):
            continue
        next_date = trading_dates[next_index]
        gross_return = _portfolio_return(current_weights, returns, next_date)
        transaction_cost = float(sum(float(row["transaction_cost"]) for row in trade_rows_for_date))
        net_return = gross_return - transaction_cost
        equity *= 1.0 + net_return
        peak = max(peak, equity)
        drawdown = equity / peak - 1.0 if peak else 0.0
        equity_rows.append(
            {
                "date": next_date,
                "gross_return": gross_return,
                "turnover": turnover,
                "transaction_cost": transaction_cost,
                "net_return": net_return,
                "equity": equity,
                "drawdown": drawdown,
                "holdings_count": len(current_weights),
            }
        )

    equity_curve = pd.DataFrame(equity_rows, columns=EQUITY_COLUMNS)
    positions = pd.DataFrame(position_rows, columns=POSITION_COLUMNS)
    trades = pd.DataFrame(trade_rows, columns=TRADE_COLUMNS)
    return VectorizedTopNResult(
        config=config,
        equity_curve=equity_curve,
        positions=positions,
        trades=trades,
        summary=_summarize(equity_curve),
    )


def write_vectorized_topn_run_card(
    result: VectorizedTopNResult,
    output_dir: str | Path,
) -> dict[str, str]:
    config = result.config
    actual_dates = (
        result.equity_curve["date"].astype(str).tolist()
        if not result.equity_curve.empty and "date" in result.equity_curve.columns
        else []
    )
    return write_run_card(
        output_dir=output_dir,
        run_type="vectorized_topn_backtest",
        run_id=(
            f"vectorized:{_iso_date(config.start_date)}:{_iso_date(config.end_date)}:"
            f"top{config.top_n}:{config.rebalance_frequency}"
        ),
        title="Vectorized TopN Backtest",
        config={
            "start_date": _iso_date(config.start_date),
            "end_date": _iso_date(config.end_date),
            "top_n": config.top_n,
            "rebalance_frequency": config.rebalance_frequency,
            "transaction_cost_bps": config.transaction_cost_bps,
            "max_positions": config.max_positions,
        },
        metrics=result.summary,
        artifact_paths={
            "equity_rows": len(result.equity_curve),
            "position_rows": len(result.positions),
            "trade_rows": len(result.trades),
        },
        warnings=["equity_curve_empty"] if result.equity_curve.empty else [],
        data_coverage={
            "input_start_date": _iso_date(config.start_date),
            "input_end_date": _iso_date(config.end_date),
            "actual_dates": actual_dates,
            "row_count": len(result.positions),
            "asset_count": int(result.positions["asset_id"].nunique()) if not result.positions.empty else 0,
        },
    )


def _normalize_scores(scores: pd.DataFrame) -> pd.DataFrame:
    if scores.empty:
        return pd.DataFrame(columns=["trade_date", "asset_id", "rank", "score_total"])
    frame = scores.copy()
    frame["trade_date"] = frame["trade_date"].map(_iso_date)
    frame["rank"] = pd.to_numeric(frame["rank"], errors="coerce")
    frame["score_total"] = pd.to_numeric(frame["score_total"], errors="coerce")
    return frame


def _normalize_prices(prices: pd.DataFrame) -> pd.DataFrame:
    if prices.empty:
        return pd.DataFrame(
            columns=[
                "trade_date",
                "asset_id",
                "open",
                "close",
                "amount",
                "trade_status",
                "is_limit_up",
                "is_limit_down",
                "is_suspended",
            ]
        )
    frame = prices.copy()
    frame["trade_date"] = frame["trade_date"].map(_iso_date)
    if "close" not in frame.columns and "open" in frame.columns:
        frame["close"] = frame["open"]
    if "open" not in frame.columns:
        frame["open"] = frame.get("close")
    for col in ["open", "close", "amount"]:
        if col not in frame.columns:
            frame[col] = pd.NA
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    if "trade_status" not in frame.columns:
        frame["trade_status"] = "1"
    for col in ["is_limit_up", "is_limit_down", "is_suspended"]:
        if col not in frame.columns:
            frame[col] = False
    frame = frame.dropna(subset=["close"])
    return frame


def _iso_date(value: object) -> str:
    return pd.Timestamp(value).date().isoformat()


def _trading_dates(
    prices: pd.DataFrame,
    start_date: object,
    end_date: object,
) -> list[str]:
    if prices.empty:
        return []
    start = _iso_date(start_date)
    end = _iso_date(end_date)
    return sorted(
        {
            trade_date
            for trade_date in prices["trade_date"].astype(str)
            if start <= trade_date <= end
        }
    )


def _close_to_close_returns(prices: pd.DataFrame) -> pd.DataFrame:
    if prices.empty:
        return pd.DataFrame()
    close = prices.pivot_table(
        index="trade_date",
        columns="asset_id",
        values="close",
        aggfunc="last",
    ).sort_index()
    return close.pct_change(fill_method=None)


def _rebalance_dates(
    scores: pd.DataFrame,
    trading_dates: list[str],
    frequency: str,
) -> list[str]:
    score_dates = set(scores["trade_date"].astype(str)) if not scores.empty else set()
    available = [trade_date for trade_date in trading_dates[:-1] if trade_date in score_dates]
    if frequency == "daily":
        return available

    weekly_dates: list[str] = []
    seen_weeks: set[tuple[int, int]] = set()
    for trade_date in available:
        iso = pd.Timestamp(trade_date).isocalendar()
        key = (int(iso.year), int(iso.week))
        if key not in seen_weeks:
            weekly_dates.append(trade_date)
            seen_weeks.add(key)
    return weekly_dates


def _effective_execution_constraints(config: VectorizedTopNConfig) -> BacktestExecutionConstraints:
    constraints = config.execution_constraints
    if (
        float(config.transaction_cost_bps) != 0.0
        and constraints.commission_bps == 0.0
        and constraints.stamp_duty_bps == 0.0
        and constraints.slippage_bps == 0.0
    ):
        return BacktestExecutionConstraints(
            commission_bps=float(config.transaction_cost_bps),
            stamp_duty_bps=constraints.stamp_duty_bps,
            slippage_bps=constraints.slippage_bps,
            min_amount=constraints.min_amount,
            block_suspended=constraints.block_suspended,
            block_limit_up_buy=constraints.block_limit_up_buy,
            block_limit_down_sell=constraints.block_limit_down_sell,
        )
    return constraints


def _price_bars_by_date(prices: pd.DataFrame) -> dict[str, dict[str, dict[str, Any]]]:
    if prices.empty:
        return {}
    grouped: dict[str, dict[str, dict[str, Any]]] = {}
    for trade_date, frame in prices.groupby("trade_date", sort=True):
        grouped[str(trade_date)] = {
            str(row["asset_id"]): row.to_dict()
            for _, row in frame.iterrows()
        }
    return grouped


def _target_weights_for_date(
    scores: pd.DataFrame,
    trade_date: str,
    config: VectorizedTopNConfig,
) -> tuple[dict[str, float], list[dict[str, Any]]]:
    limit = config.top_n
    if config.max_positions is not None:
        limit = min(limit, config.max_positions)

    selected = (
        scores[scores["trade_date"] == trade_date]
        .dropna(subset=["rank"])
        .sort_values(["rank", "score_total", "asset_id"], ascending=[True, False, True])
        .head(limit)
    )
    if selected.empty:
        return {}, []

    weight = 1.0 / len(selected)
    weights = {str(row["asset_id"]): weight for row in selected.to_dict("records")}
    rows = [
        {
            "rebalance_date": trade_date,
            "asset_id": str(row["asset_id"]),
            "rank": int(row["rank"]),
            "score_total": float(row["score_total"]),
            "weight": weight,
        }
        for row in selected.to_dict("records")
    ]
    return weights, rows


def _weight_turnover(
    previous_weights: dict[str, float],
    target_weights: dict[str, float],
) -> float:
    assets = set(previous_weights) | set(target_weights)
    return float(
        sum(abs(target_weights.get(asset, 0.0) - previous_weights.get(asset, 0.0)) for asset in assets)
    )


def _execute_signal_rebalance(
    *,
    signal_date: str,
    execution_date: str,
    current_weights: dict[str, float],
    cash_weight: float,
    target_weights: dict[str, float],
    execution_bars: dict[str, dict[str, Any]],
    constraints: BacktestExecutionConstraints,
    pending_sell_targets: dict[str, dict[str, Any]],
) -> tuple[dict[str, float], float, dict[str, dict[str, Any]], list[dict[str, Any]]]:
    updated_weights = dict(current_weights)
    cash = float(cash_weight)
    pending_sell_targets = dict(pending_sell_targets)
    rows = []
    cost_rate_buy = one_way_cost_rate("buy", constraints)
    cost_rate_sell = one_way_cost_rate("sell", constraints)

    sell_assets = sorted(
        asset_id
        for asset_id in set(updated_weights) | set(target_weights)
        if float(updated_weights.get(asset_id, 0.0)) > float(target_weights.get(asset_id, 0.0))
    )
    buy_assets = [
        asset_id
        for asset_id in target_weights.keys()
        if float(target_weights.get(asset_id, 0.0)) > float(updated_weights.get(asset_id, 0.0))
    ]

    for asset_id in sell_assets:
        previous_weight = float(updated_weights.get(asset_id, 0.0))
        target_weight = float(target_weights.get(asset_id, 0.0))
        bar = execution_bars.get(asset_id, {})
        allowed, reason = can_close_long(bar, constraints)
        if not allowed:
            rows.append(
                {
                    "rebalance_date": signal_date,
                    "signal_date": signal_date,
                    "execution_date": execution_date,
                    "asset_id": asset_id,
                    "side": "sell",
                    "previous_weight": previous_weight,
                    "target_weight": target_weight,
                    "executed_weight": previous_weight,
                    "delta_weight": 0.0,
                    "turnover_contribution": 0.0,
                    "transaction_cost": 0.0,
                    "skip_reason": reason,
                }
            )
            pending_sell_targets[asset_id] = {
                "signal_date": signal_date,
                "target_weight": target_weight,
            }
            continue
        pending_sell_targets.pop(asset_id, None)
        executed_weight = target_weight
        delta_weight = executed_weight - previous_weight
        turnover_contribution = abs(delta_weight)
        cash += previous_weight - executed_weight
        if executed_weight > 0:
            updated_weights[asset_id] = executed_weight
        else:
            updated_weights.pop(asset_id, None)
        rows.append(
            {
                "rebalance_date": signal_date,
                "signal_date": signal_date,
                "execution_date": execution_date,
                "asset_id": asset_id,
                "side": "sell",
                "previous_weight": previous_weight,
                "target_weight": target_weight,
                "executed_weight": executed_weight,
                "delta_weight": delta_weight,
                "turnover_contribution": turnover_contribution,
                "transaction_cost": turnover_contribution * cost_rate_sell,
                "skip_reason": None,
            }
        )

    for asset_id in buy_assets:
        current_weight = float(updated_weights.get(asset_id, 0.0))
        target_weight = float(target_weights.get(asset_id, 0.0))
        if target_weight <= current_weight:
            continue
        bar = execution_bars.get(asset_id, {})
        allowed, reason = can_open_long(bar, constraints)
        if not allowed:
            rows.append(
                {
                    "rebalance_date": signal_date,
                    "signal_date": signal_date,
                    "execution_date": execution_date,
                    "asset_id": asset_id,
                    "side": "buy",
                    "previous_weight": current_weight,
                    "target_weight": target_weight,
                    "executed_weight": current_weight,
                    "delta_weight": 0.0,
                    "turnover_contribution": 0.0,
                    "transaction_cost": 0.0,
                    "skip_reason": reason,
                }
            )
            continue
        desired_delta = target_weight - current_weight
        executed_delta = min(desired_delta, cash)
        executed_weight = current_weight + executed_delta
        cash -= executed_delta
        if executed_weight > 0:
            updated_weights[asset_id] = executed_weight
        else:
            updated_weights.pop(asset_id, None)
        rows.append(
            {
                "rebalance_date": signal_date,
                "signal_date": signal_date,
                "execution_date": execution_date,
                "asset_id": asset_id,
                "side": "buy",
                "previous_weight": current_weight,
                "target_weight": target_weight,
                "executed_weight": executed_weight,
                "delta_weight": executed_delta,
                "turnover_contribution": abs(executed_delta),
                "transaction_cost": abs(executed_delta) * cost_rate_buy,
                "skip_reason": None if executed_delta == desired_delta else "insufficient_cash",
            }
        )

    return updated_weights, cash, pending_sell_targets, rows


def _retry_pending_sell_orders(
    *,
    current_weights: dict[str, float],
    cash_weight: float,
    pending_sell_targets: dict[str, dict[str, Any]],
    execution_date: str,
    execution_bars: dict[str, dict[str, Any]],
    constraints: BacktestExecutionConstraints,
) -> tuple[dict[str, float], float, dict[str, dict[str, Any]], list[dict[str, Any]]]:
    if not pending_sell_targets:
        return current_weights, cash_weight, pending_sell_targets, []

    updated_weights = dict(current_weights)
    cash = float(cash_weight)
    remaining: dict[str, dict[str, Any]] = {}
    rows: list[dict[str, Any]] = []
    cost_rate_sell = one_way_cost_rate("sell", constraints)

    for asset_id, order in sorted(
        pending_sell_targets.items(),
        key=lambda item: (str(item[1]["signal_date"]), str(item[0])),
    ):
        previous_weight = float(updated_weights.get(asset_id, 0.0))
        target_weight = float(order["target_weight"])
        if previous_weight <= target_weight:
            continue
        bar = execution_bars.get(asset_id, {})
        allowed, reason = can_close_long(bar, constraints)
        if not allowed:
            rows.append(
                {
                    "rebalance_date": order["signal_date"],
                    "signal_date": order["signal_date"],
                    "execution_date": execution_date,
                    "asset_id": asset_id,
                    "side": "sell",
                    "previous_weight": previous_weight,
                    "target_weight": target_weight,
                    "executed_weight": previous_weight,
                    "delta_weight": 0.0,
                    "turnover_contribution": 0.0,
                    "transaction_cost": 0.0,
                    "skip_reason": reason,
                }
            )
            remaining[asset_id] = order
            continue

        executed_weight = target_weight
        delta_weight = executed_weight - previous_weight
        turnover_contribution = abs(delta_weight)
        cash += previous_weight - executed_weight
        if executed_weight > 0:
            updated_weights[asset_id] = executed_weight
        else:
            updated_weights.pop(asset_id, None)
        rows.append(
            {
                "rebalance_date": order["signal_date"],
                "signal_date": order["signal_date"],
                "execution_date": execution_date,
                "asset_id": asset_id,
                "side": "sell",
                "previous_weight": previous_weight,
                "target_weight": target_weight,
                "executed_weight": executed_weight,
                "delta_weight": delta_weight,
                "turnover_contribution": turnover_contribution,
                "transaction_cost": turnover_contribution * cost_rate_sell,
                "skip_reason": None,
            }
        )

    return updated_weights, cash, remaining, rows


def _portfolio_return(
    weights: dict[str, float],
    returns: pd.DataFrame,
    next_date: str,
) -> float:
    if not weights or returns.empty or next_date not in returns.index:
        return 0.0
    row = returns.loc[next_date]
    total = 0.0
    for asset_id, weight in weights.items():
        asset_return = row.get(asset_id)
        if asset_return is None or pd.isna(asset_return):
            continue
        total += float(weight) * float(asset_return)
    return float(total)


def _summarize(equity_curve: pd.DataFrame) -> dict[str, Any]:
    if equity_curve.empty:
        return {
            "total_return": 0.0,
            "max_drawdown": 0.0,
            "average_turnover": 0.0,
            "periods": 0,
        }
    return {
        "total_return": float(equity_curve.iloc[-1]["equity"]) - 1.0,
        "max_drawdown": float(equity_curve["drawdown"].min()),
        "average_turnover": float(equity_curve["turnover"].mean()),
        "periods": int(len(equity_curve)),
    }
