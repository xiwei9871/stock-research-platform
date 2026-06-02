from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all
from stock_research.performance_metrics import calc_performance_metrics


EQUITY_COLUMNS = [
    "strategy_id",
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
    "strategy_id",
    "rebalance_date",
    "asset_id",
    "rank",
    "candidate_score",
    "weight",
]

TRADE_COLUMNS = [
    "strategy_id",
    "rebalance_date",
    "asset_id",
    "side",
    "previous_weight",
    "target_weight",
    "delta_weight",
    "turnover_contribution",
    "transaction_cost",
]

SUMMARY_COLUMNS = [
    "strategy_id",
    "start_date",
    "end_date",
    "top_n",
    "holding_days",
    "transaction_cost_bps",
    "cumulative_return",
    "annual_return",
    "annual_volatility",
    "max_drawdown",
    "sharpe_ratio",
    "sortino_ratio",
    "calmar_ratio",
    "win_rate",
    "annual_turnover",
    "average_holding_days",
    "final_equity",
    "periods",
    "rebalance_count",
    "avg_holdings_count",
]


@dataclass(frozen=True)
class TrendCandidateBacktestConfig:
    start_date: object
    end_date: object
    top_n: int = 20
    holding_days: int = 10
    transaction_cost_bps: float = 20.0
    strategy_id: str | None = None


@dataclass(frozen=True)
class TrendCandidateBacktestResult:
    config: TrendCandidateBacktestConfig
    equity_curve: pd.DataFrame
    positions: pd.DataFrame
    trades: pd.DataFrame = field(default_factory=lambda: pd.DataFrame(columns=TRADE_COLUMNS))
    summary: dict[str, Any] = field(default_factory=dict)


def run_fixed_holding_backtest(
    candidate_scores: pd.DataFrame,
    prices: pd.DataFrame,
    config: TrendCandidateBacktestConfig,
) -> TrendCandidateBacktestResult:
    if config.top_n <= 0:
        raise ValueError("top_n must be positive")
    if config.holding_days <= 0:
        raise ValueError("holding_days must be positive")

    scores = _normalize_scores(candidate_scores)
    price_frame = _normalize_prices(prices)
    trading_dates = _trading_dates(price_frame, config.start_date, config.end_date)
    returns = _close_to_close_returns(price_frame)
    rebalance_dates = set(_fixed_holding_rebalance_dates(trading_dates, config.holding_days))
    strategy_id = _strategy_id(config)
    cost_rate = float(config.transaction_cost_bps) / 10000.0

    equity = 1.0
    peak = 1.0
    current_weights: dict[str, float] = {}
    equity_rows: list[dict[str, Any]] = []
    position_rows: list[dict[str, Any]] = []
    trade_rows: list[dict[str, Any]] = []

    for index, trade_date in enumerate(trading_dates[:-1]):
        next_date = trading_dates[index + 1]
        turnover = 0.0
        if trade_date in rebalance_dates:
            target_weights, selected_rows = _target_weights_for_date(
                scores,
                trade_date,
                config.top_n,
                strategy_id,
            )
            if target_weights:
                turnover = _weight_turnover(current_weights, target_weights)
                trade_rows.extend(
                    _trade_rows_for_rebalance(
                        strategy_id,
                        trade_date,
                        current_weights,
                        target_weights,
                        cost_rate,
                    )
                )
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
                "strategy_id": strategy_id,
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
    summary = _summarize_result(config, strategy_id, equity_curve, positions)
    return TrendCandidateBacktestResult(
        config=config,
        equity_curve=equity_curve,
        positions=positions,
        trades=trades,
        summary=summary,
    )


def run_trend_candidate_backtest_report(
    *,
    start_date: object,
    end_date: object,
    candidate_scores_path: str | Path,
    top_ns: tuple[int, ...] = (20, 50),
    holding_days: tuple[int, ...] = (5, 10, 20),
    transaction_cost_bps: float = 20.0,
    adjust_type: str = "hfq",
    reports_dir: str | Path = Path("/Users/xiwei/stock_research/reports"),
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    start = _iso_date(start_date)
    end = _iso_date(end_date)
    scores_path = Path(candidate_scores_path)
    if not scores_path.exists():
        raise FileNotFoundError(f"candidate_scores CSV not found: {scores_path}")

    candidate_scores = pd.read_csv(scores_path)
    prices = load_candidate_backtest_prices(
        start_date=start,
        end_date=end,
        adjust_type=adjust_type,
        service=service,
    )

    results: list[TrendCandidateBacktestResult] = []
    for top_n in top_ns:
        for days in holding_days:
            config = TrendCandidateBacktestConfig(
                start_date=start,
                end_date=end,
                top_n=int(top_n),
                holding_days=int(days),
                transaction_cost_bps=float(transaction_cost_bps),
            )
            results.append(run_fixed_holding_backtest(candidate_scores, prices, config))

    summary = pd.DataFrame([result.summary for result in results]).reindex(columns=SUMMARY_COLUMNS)
    equity_curve = _concat_result_frames(results, "equity_curve", EQUITY_COLUMNS)
    positions = _concat_result_frames(results, "positions", POSITION_COLUMNS)
    trades = _concat_result_frames(results, "trades", TRADE_COLUMNS)
    diagnostics = _diagnostics(candidate_scores=candidate_scores, prices=prices, summary=summary)
    output_dir = Path(reports_dir) / f"trend_candidate_backtest_{start.replace('-', '')}_{end.replace('-', '')}"
    paths = write_trend_candidate_backtest_outputs(
        output_dir=output_dir,
        start_date=start,
        end_date=end,
        summary=summary,
        equity_curve=equity_curve,
        positions=positions,
        trades=trades,
        diagnostics=diagnostics,
    )
    return {
        "paths": paths,
        "summary": summary,
        "equity_curve": equity_curve,
        "positions": positions,
        "trades": trades,
        "diagnostics": diagnostics,
    }


def write_trend_candidate_backtest_outputs(
    *,
    output_dir: str | Path,
    start_date: object,
    end_date: object,
    summary: pd.DataFrame,
    equity_curve: pd.DataFrame,
    positions: pd.DataFrame,
    trades: pd.DataFrame,
    diagnostics: list[str],
) -> dict[str, str]:
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)
    paths = {
        "summary": str(path / "summary.csv"),
        "equity_curve": str(path / "equity_curve.csv"),
        "positions": str(path / "positions.csv"),
        "trades": str(path / "trades.csv"),
        "markdown_report": str(path / "trend_candidate_backtest_report.md"),
    }
    summary.reindex(columns=SUMMARY_COLUMNS).to_csv(paths["summary"], index=False)
    equity_curve.reindex(columns=EQUITY_COLUMNS).to_csv(paths["equity_curve"], index=False)
    positions.reindex(columns=POSITION_COLUMNS).to_csv(paths["positions"], index=False)
    trades.reindex(columns=TRADE_COLUMNS).to_csv(paths["trades"], index=False)
    Path(paths["markdown_report"]).write_text(
        _markdown_report(
            start_date=str(start_date),
            end_date=str(end_date),
            summary=summary,
            diagnostics=diagnostics,
        ),
        encoding="utf-8",
    )
    return paths


def load_candidate_backtest_prices(
    *,
    start_date: str,
    end_date: str,
    adjust_type: str = "hfq",
    service: str = SETTINGS.research_service,
) -> pd.DataFrame:
    sql = """
        SELECT trade_date, asset_id, close
        FROM market_daily_bar
        WHERE adjust_type = %s
          AND trade_date BETWEEN %s AND %s
        ORDER BY trade_date, asset_id
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, [adjust_type, start_date, end_date])
    return pd.DataFrame(rows)


def _normalize_scores(candidate_scores: pd.DataFrame) -> pd.DataFrame:
    if candidate_scores.empty:
        return pd.DataFrame(columns=["trade_date", "asset_id", "candidate_score"])
    frame = candidate_scores.copy()
    frame["trade_date"] = frame["trade_date"].map(_iso_date)
    frame["asset_id"] = frame["asset_id"].astype(str)
    frame["candidate_score"] = pd.to_numeric(frame["candidate_score"], errors="coerce")
    return frame.dropna(subset=["candidate_score"])


def _normalize_prices(prices: pd.DataFrame) -> pd.DataFrame:
    if prices.empty:
        return pd.DataFrame(columns=["trade_date", "asset_id", "close"])
    frame = prices.copy()
    frame["trade_date"] = frame["trade_date"].map(_iso_date)
    frame["asset_id"] = frame["asset_id"].astype(str)
    frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
    return frame.dropna(subset=["close"])


def _trading_dates(prices: pd.DataFrame, start_date: object, end_date: object) -> list[str]:
    if prices.empty:
        return []
    start = _iso_date(start_date)
    end = _iso_date(end_date)
    return sorted(
        {
            str(trade_date)
            for trade_date in prices["trade_date"]
            if start <= str(trade_date) <= end
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


def _fixed_holding_rebalance_dates(trading_dates: list[str], holding_days: int) -> list[str]:
    if len(trading_dates) < 2:
        return []
    return trading_dates[:-1:int(holding_days)]


def _target_weights_for_date(
    scores: pd.DataFrame,
    trade_date: str,
    top_n: int,
    strategy_id: str,
) -> tuple[dict[str, float], list[dict[str, Any]]]:
    selected = (
        scores[scores["trade_date"] == trade_date]
        .sort_values(["candidate_score", "asset_id"], ascending=[False, True])
        .head(int(top_n))
        .reset_index(drop=True)
    )
    if selected.empty:
        return {}, []
    weight = 1.0 / len(selected)
    weights = {str(row.asset_id): weight for row in selected.itertuples(index=False)}
    position_rows = [
        {
            "strategy_id": strategy_id,
            "rebalance_date": trade_date,
            "asset_id": str(row.asset_id),
            "rank": int(rank),
            "candidate_score": float(row.candidate_score),
            "weight": weight,
        }
        for rank, row in enumerate(selected.itertuples(index=False), start=1)
    ]
    return weights, position_rows


def _weight_turnover(previous: dict[str, float], target: dict[str, float]) -> float:
    assets = set(previous) | set(target)
    return float(sum(abs(target.get(asset, 0.0) - previous.get(asset, 0.0)) for asset in assets))


def _trade_rows_for_rebalance(
    strategy_id: str,
    rebalance_date: str,
    previous: dict[str, float],
    target: dict[str, float],
    cost_rate: float,
) -> list[dict[str, Any]]:
    rows = []
    for asset_id in sorted(set(previous) | set(target)):
        previous_weight = float(previous.get(asset_id, 0.0))
        target_weight = float(target.get(asset_id, 0.0))
        delta = target_weight - previous_weight
        if delta == 0:
            continue
        turnover_contribution = abs(delta)
        rows.append(
            {
                "strategy_id": strategy_id,
                "rebalance_date": rebalance_date,
                "asset_id": asset_id,
                "side": "buy" if delta > 0 else "sell",
                "previous_weight": previous_weight,
                "target_weight": target_weight,
                "delta_weight": delta,
                "turnover_contribution": turnover_contribution,
                "transaction_cost": turnover_contribution * cost_rate,
            }
        )
    return rows


def _portfolio_return(weights: dict[str, float], returns: pd.DataFrame, next_date: str) -> float:
    if not weights or returns.empty or next_date not in returns.index:
        return 0.0
    row = returns.loc[next_date]
    total = 0.0
    for asset_id, weight in weights.items():
        if asset_id not in row.index or pd.isna(row[asset_id]):
            continue
        total += float(weight) * float(row[asset_id])
    return float(total)


def _summarize_result(
    config: TrendCandidateBacktestConfig,
    strategy_id: str,
    equity_curve: pd.DataFrame,
    positions: pd.DataFrame,
) -> dict[str, Any]:
    metrics = calc_performance_metrics(equity_curve, positions)
    final_equity = (
        float(equity_curve["equity"].iloc[-1])
        if not equity_curve.empty
        else 1.0
    )
    return {
        "strategy_id": strategy_id,
        "start_date": _iso_date(config.start_date),
        "end_date": _iso_date(config.end_date),
        "top_n": int(config.top_n),
        "holding_days": int(config.holding_days),
        "transaction_cost_bps": float(config.transaction_cost_bps),
        **metrics,
        "annual_turnover": metrics.get("annual_turnover"),
        "average_holding_days": float(config.holding_days),
        "final_equity": final_equity,
        "rebalance_count": int(positions["rebalance_date"].nunique()) if not positions.empty else 0,
        "avg_holdings_count": (
            float(equity_curve["holdings_count"].mean())
            if not equity_curve.empty
            else 0.0
        ),
    }


def _strategy_id(config: TrendCandidateBacktestConfig) -> str:
    if config.strategy_id:
        return config.strategy_id
    return f"top{int(config.top_n)}_hold{int(config.holding_days)}_cost{float(config.transaction_cost_bps):g}bps"


def _concat_result_frames(
    results: list[TrendCandidateBacktestResult],
    attribute: str,
    columns: list[str],
) -> pd.DataFrame:
    frames = [getattr(result, attribute) for result in results if not getattr(result, attribute).empty]
    if not frames:
        return pd.DataFrame(columns=columns)
    return pd.concat(frames, ignore_index=True).reindex(columns=columns)


def _diagnostics(
    *,
    candidate_scores: pd.DataFrame,
    prices: pd.DataFrame,
    summary: pd.DataFrame,
) -> list[str]:
    diagnostics = []
    if candidate_scores.empty:
        diagnostics.append("No candidate scores were provided.")
    if prices.empty:
        diagnostics.append("No price rows were loaded for the backtest period.")
    if summary.empty:
        diagnostics.append("No backtest summaries were produced.")
    diagnostics.append(
        "Paper backtest uses same-day candidate scores, close-to-close returns, fixed holding-day rebalances, "
        "and transaction-cost bps on weight turnover; it does not model limit-up/down execution or slippage."
    )
    return diagnostics


def _markdown_report(
    *,
    start_date: str,
    end_date: str,
    summary: pd.DataFrame,
    diagnostics: list[str],
) -> str:
    lines = [
        "# Trend Candidate Paper Backtest",
        "",
        f"- Period: {start_date} to {end_date}",
        "- Scope: fixed holding-day paper portfolio validation for trend candidate scores.",
        "- Execution: close-to-close returns with transaction costs on weight turnover.",
        "",
        "## Summary",
        "",
        _markdown_table(summary),
        "",
        "## Data Issues",
        "",
    ]
    if diagnostics:
        lines.extend(f"- {item}" for item in diagnostics)
    else:
        lines.append("- No data issues detected by backtest diagnostics.")
    lines.extend(
        [
            "",
            "## Next Stage",
            "",
            "- Compare 20/40/60 horizon candidate scores before choosing a portfolio rule.",
            "- Add limit-up/down and liquidity execution constraints before treating results as tradable.",
            "",
        ]
    )
    return "\n".join(lines)


def _markdown_table(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "_No rows._"
    return frame.to_markdown(index=False)


def _iso_date(value: object) -> str:
    return pd.Timestamp(value).date().isoformat()
