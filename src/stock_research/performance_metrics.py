from typing import Any

import pandas as pd


def calc_performance_metrics(
    equity_curve: pd.DataFrame,
    positions: pd.DataFrame | None = None,
    annualization: int = 252,
) -> dict[str, Any]:
    if equity_curve.empty:
        return {
            "cumulative_return": 0.0,
            "annual_return": None,
            "annual_volatility": None,
            "max_drawdown": 0.0,
            "sharpe_ratio": None,
            "sortino_ratio": None,
            "calmar_ratio": None,
            "win_rate": None,
            "average_holding_days": None,
            "annual_turnover": None,
            "periods": 0,
        }

    returns = pd.to_numeric(equity_curve.get("net_return"), errors="coerce").dropna()
    equity = pd.to_numeric(equity_curve.get("equity"), errors="coerce").dropna()
    drawdown = pd.to_numeric(equity_curve.get("drawdown"), errors="coerce").dropna()
    turnover = pd.to_numeric(equity_curve.get("turnover"), errors="coerce").dropna()
    periods = int(len(returns))

    cumulative_return = float(equity.iloc[-1] - 1.0) if not equity.empty else 0.0
    annual_return = _annual_return(cumulative_return, periods, annualization)
    annual_volatility = _annual_volatility(returns, annualization)
    max_drawdown = float(drawdown.min()) if not drawdown.empty else 0.0
    sharpe = _sharpe_ratio(returns, annualization)
    sortino = _sortino_ratio(returns, annualization)
    calmar = (
        annual_return / abs(max_drawdown)
        if annual_return is not None and max_drawdown < 0
        else None
    )
    win_rate = float((returns > 0).mean()) if not returns.empty else None
    annual_turnover = float(turnover.mean() * annualization) if not turnover.empty else None

    return {
        "cumulative_return": cumulative_return,
        "annual_return": annual_return,
        "annual_volatility": annual_volatility,
        "max_drawdown": max_drawdown,
        "sharpe_ratio": sharpe,
        "sortino_ratio": sortino,
        "calmar_ratio": calmar,
        "win_rate": win_rate,
        "average_holding_days": _average_holding_days(positions),
        "annual_turnover": annual_turnover,
        "periods": periods,
    }


def _annual_return(
    cumulative_return: float,
    periods: int,
    annualization: int,
) -> float | None:
    if periods <= 0:
        return None
    return float((1.0 + cumulative_return) ** (annualization / periods) - 1.0)


def _annual_volatility(returns: pd.Series, annualization: int) -> float | None:
    if len(returns) < 2:
        return None
    volatility = returns.std(ddof=1)
    if pd.isna(volatility):
        return None
    return float(volatility * (annualization**0.5))


def _sharpe_ratio(returns: pd.Series, annualization: int) -> float | None:
    if len(returns) < 2:
        return None
    volatility = returns.std(ddof=1)
    if pd.isna(volatility) or volatility == 0:
        return None
    return float(returns.mean() / volatility * (annualization**0.5))


def _sortino_ratio(returns: pd.Series, annualization: int) -> float | None:
    downside = returns[returns < 0]
    if downside.empty:
        return None
    downside_deviation = downside.std(ddof=0)
    if pd.isna(downside_deviation) or downside_deviation == 0:
        return None
    return float(returns.mean() / downside_deviation * (annualization**0.5))


def _average_holding_days(positions: pd.DataFrame | None) -> float | None:
    if positions is None or positions.empty or "rebalance_date" not in positions.columns:
        return None
    dates = (
        positions["rebalance_date"]
        .dropna()
        .map(lambda value: pd.Timestamp(value).normalize())
        .drop_duplicates()
        .sort_values()
    )
    if len(dates) < 2:
        return None
    deltas = dates.diff().dropna().dt.days
    if deltas.empty:
        return None
    return float(deltas.mean())
