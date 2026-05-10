from dataclasses import dataclass
from typing import Any

import pandas as pd


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


@dataclass(frozen=True)
class VectorizedTopNConfig:
    start_date: object
    end_date: object
    top_n: int = 20
    rebalance_frequency: str = "daily"
    transaction_cost_bps: float = 0.0
    max_positions: int | None = None


@dataclass(frozen=True)
class VectorizedTopNResult:
    config: VectorizedTopNConfig
    equity_curve: pd.DataFrame
    positions: pd.DataFrame
    summary: dict[str, Any]


def run_vectorized_topn_backtest(
    scores: pd.DataFrame,
    prices: pd.DataFrame,
    config: VectorizedTopNConfig,
) -> VectorizedTopNResult:
    if config.top_n <= 0:
        raise ValueError("top_n must be positive")
    if config.max_positions is not None and config.max_positions <= 0:
        raise ValueError("max_positions must be positive")
    if config.rebalance_frequency not in {"daily", "weekly"}:
        raise ValueError("rebalance_frequency must be daily or weekly")

    normalized_scores = _normalize_scores(scores)
    normalized_prices = _normalize_prices(prices)
    trading_dates = _trading_dates(normalized_prices, config.start_date, config.end_date)
    returns = _close_to_close_returns(normalized_prices)
    rebalance_dates = set(
        _rebalance_dates(normalized_scores, trading_dates, config.rebalance_frequency)
    )

    equity = 1.0
    peak = 1.0
    previous_weights: dict[str, float] = {}
    current_weights: dict[str, float] = {}
    equity_rows: list[dict[str, Any]] = []
    position_rows: list[dict[str, Any]] = []
    cost_rate = float(config.transaction_cost_bps) / 10000.0

    for index, trade_date in enumerate(trading_dates[:-1]):
        next_date = trading_dates[index + 1]
        turnover = 0.0
        if trade_date in rebalance_dates:
            target_weights, selected_rows = _target_weights_for_date(
                normalized_scores,
                trade_date,
                config,
            )
            turnover = _weight_turnover(previous_weights, target_weights)
            previous_weights = target_weights
            current_weights = target_weights
            position_rows.extend(selected_rows)

        gross_return = _portfolio_return(current_weights, returns, next_date)
        transaction_cost = turnover * cost_rate
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
    return VectorizedTopNResult(
        config=config,
        equity_curve=equity_curve,
        positions=positions,
        summary=_summarize(equity_curve),
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
        return pd.DataFrame(columns=["trade_date", "asset_id", "close"])
    frame = prices.copy()
    frame["trade_date"] = frame["trade_date"].map(_iso_date)
    frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
    return frame.dropna(subset=["close"])


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
