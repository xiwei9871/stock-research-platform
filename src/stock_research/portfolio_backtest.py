from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from stock_research.backtest import (
    BacktestBar,
    BacktestSelection,
    apply_buy_filter,
    load_backtest_inputs,
    next_trade_date,
    select_top_for_date,
    sell_bar_for_holding,
)
from stock_research.run_card import write_run_card
from stock_research.services.universe_service import (
    UniverseResult,
    filter_dataframe_by_universe,
)


TRADE_COLUMNS = [
    "strategy_id",
    "top_k",
    "holding_days",
    "selection_date",
    "buy_date",
    "asset_id",
    "rank",
    "score",
    "shares",
    "buy_open",
    "buy_value",
    "sell_date",
    "sell_open",
    "sell_value",
    "return_value",
    "status",
    "skip_reason",
]

EQUITY_COLUMNS = [
    "strategy_id",
    "date",
    "cash",
    "market_value",
    "equity",
    "drawdown",
    "open_positions",
]

SUMMARY_COLUMNS = [
    "strategy_id",
    "top_k",
    "holding_days",
    "initial_cash",
    "final_equity",
    "total_return",
    "max_drawdown",
    "closed_trades",
    "open_trades",
    "skipped_trades",
    "win_rate",
    "mean_trade_return",
    "average_cash",
    "average_market_value",
    "average_capital_utilization",
    "insufficient_lot_cash_skips",
    "execution_skips",
]


@dataclass(frozen=True)
class PortfolioConfig:
    start_date: object
    end_date: object
    initial_cash: float = 500000.0
    top_k: int = 5
    holding_days: int = 5
    lot_size: int = 100
    strategy_id: str | None = None


@dataclass(frozen=True)
class PortfolioResult:
    config: PortfolioConfig
    equity_curve: pd.DataFrame
    trades: pd.DataFrame


def shares_for_budget(budget: float, price: float, lot_size: int = 100) -> int:
    if lot_size <= 0:
        raise ValueError("lot_size must be positive")
    if budget <= 0 or price <= 0 or pd.isna(price):
        return 0
    whole_lots = int(float(budget) // (float(price) * lot_size))
    return whole_lots * lot_size


def simulate_portfolio_config(
    feature_frame: pd.DataFrame,
    bar_frame: pd.DataFrame,
    config: PortfolioConfig,
    universe_result: UniverseResult | None = None,
) -> PortfolioResult:
    if config.holding_days <= 0:
        raise ValueError("holding_days must be positive")
    if config.top_k <= 0:
        raise ValueError("top_k must be positive")

    features = _normalize_dates(feature_frame)
    bars = _normalize_dates(bar_frame)
    features = filter_dataframe_by_universe(
        features,
        universe_result,
        asset_id_col="asset_id",
        code_col="stock_code",
    )
    bars = filter_dataframe_by_universe(
        bars,
        universe_result,
        asset_id_col="asset_id",
        code_col="stock_code",
    )
    trading_dates = _trading_dates(bars)
    start_date = _iso_date(config.start_date)
    end_date = _iso_date(config.end_date)
    simulation_dates = [date for date in trading_dates if start_date <= date]

    bars_by_asset = _bars_by_asset(bars)
    bars_by_date_asset = _bars_by_date_asset(bars)
    pending_buys: dict[str, list[dict[str, Any]]] = {}
    positions: list[dict[str, Any]] = []
    trade_rows: list[dict[str, Any]] = []
    equity_rows: list[dict[str, Any]] = []

    cash = float(config.initial_cash)
    peak_equity = float(config.initial_cash)

    for current_date in simulation_dates:
        if current_date > end_date and not positions and current_date not in pending_buys:
            break

        cash = _close_due_positions(current_date, cash, positions)

        for batch in pending_buys.pop(current_date, []):
            cash = _execute_buy_batch(
                current_date=current_date,
                batch=batch,
                cash=cash,
                positions=positions,
                trade_rows=trade_rows,
                bars_by_asset=bars_by_asset,
                bars_by_date_asset=bars_by_date_asset,
                config=config,
            )

        market_value = _market_value(positions, bars_by_date_asset, current_date)
        equity = cash + market_value
        peak_equity = max(peak_equity, equity)
        drawdown = equity / peak_equity - 1.0 if peak_equity else 0.0
        equity_rows.append(
            {
                "strategy_id": config.strategy_id,
                "date": current_date,
                "cash": cash,
                "market_value": market_value,
                "equity": equity,
                "drawdown": drawdown,
                "open_positions": len(positions),
            }
        )

        if current_date <= end_date:
            _schedule_next_buy_batch(
                current_date=current_date,
                end_date=end_date,
                features=features,
                bars=bars,
                trading_dates=trading_dates,
                bars_by_date_asset=bars_by_date_asset,
                pending_buys=pending_buys,
                trade_rows=trade_rows,
                config=config,
            )

    return PortfolioResult(
        config=config,
        equity_curve=pd.DataFrame(equity_rows, columns=EQUITY_COLUMNS),
        trades=pd.DataFrame(trade_rows, columns=TRADE_COLUMNS),
    )


def summarize_portfolio_result(result: PortfolioResult) -> dict[str, object]:
    config = result.config
    equity_curve = result.equity_curve.copy()
    trades = result.trades.copy()

    final_equity = _last_numeric_value(equity_curve, "equity", config.initial_cash)
    total_return = (
        final_equity / float(config.initial_cash) - 1.0
        if config.initial_cash and final_equity is not None
        else None
    )
    max_drawdown = _min_numeric_value(equity_curve, "drawdown")
    average_cash = _mean_numeric_value(equity_curve, "cash")
    average_market_value = _mean_numeric_value(equity_curve, "market_value")
    average_capital_utilization = (
        average_market_value / float(config.initial_cash)
        if config.initial_cash and average_market_value is not None
        else None
    )

    statuses = (
        trades["status"].astype(str)
        if "status" in trades.columns
        else pd.Series(dtype=object)
    )
    closed_trades = int((statuses == "closed").sum())
    open_trades = int((statuses == "open").sum())
    skipped_trades = int((statuses == "skipped").sum())

    closed_returns = pd.Series(dtype=float)
    if not trades.empty and "return_value" in trades.columns and "status" in trades.columns:
        closed_returns = pd.to_numeric(
            trades.loc[statuses == "closed", "return_value"],
            errors="coerce",
        ).dropna()
    win_rate = float((closed_returns > 0).mean()) if not closed_returns.empty else None
    mean_trade_return = float(closed_returns.mean()) if not closed_returns.empty else None

    skip_reasons = (
        trades.loc[statuses == "skipped", "skip_reason"].astype(str)
        if "skip_reason" in trades.columns and not trades.empty
        else pd.Series(dtype=object)
    )
    insufficient_lot_cash_skips = int((skip_reasons == "insufficient_lot_cash").sum())
    execution_skips = int(skipped_trades - insufficient_lot_cash_skips)

    return {
        "strategy_id": config.strategy_id,
        "top_k": config.top_k,
        "holding_days": config.holding_days,
        "initial_cash": float(config.initial_cash),
        "final_equity": final_equity,
        "total_return": total_return,
        "max_drawdown": max_drawdown,
        "closed_trades": closed_trades,
        "open_trades": open_trades,
        "skipped_trades": skipped_trades,
        "win_rate": win_rate,
        "mean_trade_return": mean_trade_return,
        "average_cash": average_cash,
        "average_market_value": average_market_value,
        "average_capital_utilization": average_capital_utilization,
        "insufficient_lot_cash_skips": insufficient_lot_cash_skips,
        "execution_skips": execution_skips,
    }


def write_portfolio_report(
    results: list[PortfolioResult],
    summary: pd.DataFrame,
    start_date: object,
    end_date: object,
    initial_cash: float,
    top_ks: tuple[int, ...] = (5, 10),
    holding_days: tuple[int, ...] = (5, 10, 15, 20, 30),
    reports_dir: str | Path = Path("/Users/xiwei/stock_research/reports"),
) -> dict[str, str]:
    reports_path = Path(reports_dir)
    reports_path.mkdir(parents=True, exist_ok=True)

    start = _iso_date(start_date)
    end = _iso_date(end_date)
    stem = _portfolio_report_stem(start, end, initial_cash, top_ks, holding_days)
    report_path = reports_path / f"{stem}.md"
    equity_curve_path = reports_path / f"{stem}_equity.csv"
    trades_path = reports_path / f"{stem}_trades.csv"
    summary_path = reports_path / f"{stem}_summary.csv"

    equity_curve = _combined_equity_curve(results)
    trades = _combined_trades(results)
    equity_curve.to_csv(equity_curve_path, index=False)
    trades.to_csv(trades_path, index=False)
    summary.to_csv(summary_path, index=False)

    lines = [
        "# 账户级模拟交易回测报告",
        "",
        "仅作为研究验证，不构成交易指令。",
        "",
        "## 总览",
        "",
        f"- 回测区间：{start} 至 {end}",
        f"- 初始资金：{_format_decimal(initial_cash, digits=0)}",
        f"- TopK：{', '.join(str(value) for value in top_ks)}",
        f"- 持有周期：{', '.join(str(value) for value in holding_days)}",
        "",
        "| strategy_id | top_k | holding_days | final_equity | total_return | 最大回撤 | closed | open | skipped | win_rate | 资金利用率 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]

    for _, row in summary.iterrows():
        lines.append(
            "| "
            f"{_markdown_cell(row.get('strategy_id'))} | "
            f"{_format_int(row.get('top_k'))} | "
            f"{_format_int(row.get('holding_days'))} | "
            f"{_format_decimal(row.get('final_equity'), digits=2)} | "
            f"{_format_percent(row.get('total_return'))} | "
            f"{_format_percent(row.get('max_drawdown'))} | "
            f"{_format_int(row.get('closed_trades'))} | "
            f"{_format_int(row.get('open_trades'))} | "
            f"{_format_int(row.get('skipped_trades'))} | "
            f"{_format_percent(row.get('win_rate'))} | "
            f"{_format_percent(row.get('average_capital_utilization'))} |"
        )

    lines.extend(
        [
            "",
            "## 资金曲线",
            "",
            f"- 资金曲线 CSV：{equity_curve_path}",
            f"- 交易明细 CSV：{trades_path}",
            f"- 汇总指标 CSV：{summary_path}",
            "",
            "## 最大回撤",
            "",
        ]
    )
    if summary.empty:
        lines.append("- 无汇总样本。")
    else:
        for _, row in summary.iterrows():
            lines.append(
                f"- top_k={_format_int(row.get('top_k'))}, "
                f"holding_days={_format_int(row.get('holding_days'))}："
                f"{_format_percent(row.get('max_drawdown'))}"
            )

    lines.extend(["", "## 资金利用率", ""])
    if summary.empty:
        lines.append("- 无资金利用率样本。")
    else:
        for _, row in summary.iterrows():
            lines.append(
                f"- top_k={_format_int(row.get('top_k'))}, "
                f"holding_days={_format_int(row.get('holding_days'))}："
                f"{_format_percent(row.get('average_capital_utilization'))}"
            )

    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {
        "report_path": str(report_path),
        "equity_curve_path": str(equity_curve_path),
        "trades_path": str(trades_path),
        "summary_path": str(summary_path),
    }


def run_portfolio_backtest(
    start_date: object,
    end_date: object,
    initial_cash: float = 500000.0,
    top_ks: tuple[int, ...] = (5, 10),
    holding_days: tuple[int, ...] = (5, 10, 15, 20, 30),
    reports_dir: str | Path = Path("/Users/xiwei/stock_research/reports"),
    universe_result: UniverseResult | None = None,
) -> dict[str, object]:
    horizons = tuple(int(value) for value in holding_days)
    top_values = tuple(int(value) for value in top_ks)
    future_buffer_days = max(max(horizons) * 3, 30) if horizons else 30
    features, bars = load_backtest_inputs(
        start_date,
        end_date,
        future_buffer_days=future_buffer_days,
    )

    results: list[PortfolioResult] = []
    for top_k in top_values:
        for horizon in horizons:
            config = PortfolioConfig(
                start_date=start_date,
                end_date=end_date,
                initial_cash=float(initial_cash),
                top_k=top_k,
                holding_days=horizon,
                strategy_id=_portfolio_strategy_id(
                    start_date,
                    end_date,
                    top_k,
                    horizon,
                    initial_cash,
                ),
            )
            if universe_result is None:
                results.append(simulate_portfolio_config(features, bars, config))
            else:
                results.append(
                    simulate_portfolio_config(
                        features,
                        bars,
                        config,
                        universe_result=universe_result,
                    )
                )

    summary = pd.DataFrame(
        [summarize_portfolio_result(result) for result in results],
        columns=SUMMARY_COLUMNS,
    )
    report_paths = write_portfolio_report(
        results,
        summary,
        start_date=start_date,
        end_date=end_date,
        initial_cash=float(initial_cash),
        top_ks=top_values,
        holding_days=horizons,
        reports_dir=reports_dir,
    )
    run_card = write_portfolio_run_card(
        results=results,
        summary=summary,
        start_date=start_date,
        end_date=end_date,
        initial_cash=float(initial_cash),
        top_ks=top_values,
        holding_days=horizons,
        reports_dir=reports_dir,
        report_paths=report_paths,
    )
    return {
        "results": results,
        "equity_curve": _combined_equity_curve(results),
        "trades": _combined_trades(results),
        "summary": summary,
        "report_path": report_paths["report_path"],
        "report_paths": report_paths,
        "run_card": run_card,
    }


def write_portfolio_run_card(
    *,
    results: list[PortfolioResult],
    summary: pd.DataFrame,
    start_date: object,
    end_date: object,
    initial_cash: float,
    top_ks: tuple[int, ...],
    holding_days: tuple[int, ...],
    reports_dir: str | Path,
    report_paths: dict[str, str],
) -> dict[str, str]:
    equity_curve = _combined_equity_curve(results)
    trades = _combined_trades(results)
    actual_dates = (
        sorted(equity_curve["date"].astype(str).unique().tolist())
        if not equity_curve.empty and "date" in equity_curve.columns
        else []
    )
    asset_count = int(trades["asset_id"].nunique()) if not trades.empty and "asset_id" in trades.columns else 0
    warnings: list[str] = []
    if summary.empty:
        warnings.append("summary_empty")
    if trades.empty:
        warnings.append("trades_empty")
    if equity_curve.empty:
        warnings.append("equity_curve_empty")
    return write_run_card(
        output_dir=Path(reports_dir) / "run_card",
        run_type="portfolio_backtest",
        run_id=(
            f"portfolio:{_iso_date(start_date)}:{_iso_date(end_date)}:"
            f"top{'-'.join(str(value) for value in top_ks)}:"
            f"h{'-'.join(str(value) for value in holding_days)}"
        ),
        title="Portfolio Backtest",
        config={
            "start_date": _iso_date(start_date),
            "end_date": _iso_date(end_date),
            "initial_cash": float(initial_cash),
            "top_ks": list(top_ks),
            "holding_days": list(holding_days),
        },
        metrics={
            "workflow_type": "portfolio_backtest",
            "strategy_count": len(results),
            "summary_rows": int(len(summary)),
            "final_equity_mean": _mean_numeric_value(summary, "final_equity"),
            "max_drawdown_min": _min_numeric_value(summary, "max_drawdown"),
            "total_return_mean": _mean_numeric_value(summary, "total_return"),
            "annualized_return": None,
            "sharpe": None,
            "trade_count": int(len(trades)),
            "rebalance_count": int(len(equity_curve)),
            "position_count": asset_count,
            "start_date": _iso_date(start_date),
            "end_date": _iso_date(end_date),
        },
        artifact_paths=report_paths,
        warnings=warnings,
        data_coverage={
            "input_start_date": _iso_date(start_date),
            "input_end_date": _iso_date(end_date),
            "actual_dates": actual_dates,
            "row_count": int(len(trades)),
            "asset_count": asset_count,
        },
    )


def _normalize_dates(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty or "trade_date" not in frame.columns:
        return frame.copy()
    normalized = frame.copy()
    normalized["trade_date"] = normalized["trade_date"].map(_iso_date)
    return normalized


def _iso_date(value: object) -> str:
    return pd.Timestamp(value).date().isoformat()


def _trading_dates(bar_frame: pd.DataFrame) -> list[str]:
    if bar_frame.empty:
        return []
    return sorted({_iso_date(value) for value in bar_frame["trade_date"]})


def _bars_by_asset(bar_frame: pd.DataFrame) -> dict[str, list[BacktestBar]]:
    grouped: dict[str, list[BacktestBar]] = {}
    if bar_frame.empty:
        return grouped
    for row in bar_frame.sort_values(["asset_id", "trade_date"]).to_dict("records"):
        bar = _bar_from_record(row)
        grouped.setdefault(bar.asset_id, []).append(bar)
    return grouped


def _bars_by_date_asset(bar_frame: pd.DataFrame) -> dict[tuple[str, str], BacktestBar]:
    indexed: dict[tuple[str, str], BacktestBar] = {}
    if bar_frame.empty:
        return indexed
    for row in bar_frame.to_dict("records"):
        bar = _bar_from_record(row)
        indexed[(bar.trade_date, bar.asset_id)] = bar
    return indexed


def _bar_from_record(row: dict[str, Any]) -> BacktestBar:
    return BacktestBar(
        asset_id=str(row["asset_id"]),
        trade_date=_iso_date(row["trade_date"]),
        open=_float_or_none(row.get("open")),
        preclose=_float_or_none(row.get("preclose")),
        amount=_float_or_none(row.get("amount")),
        trade_status=str(row.get("trade_status")),
        is_st=bool(row.get("is_st")),
    )


def _float_or_none(value: object) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)


def _last_numeric_value(
    frame: pd.DataFrame,
    column: str,
    default: float | None = None,
) -> float | None:
    if frame.empty or column not in frame.columns:
        return default
    values = pd.to_numeric(frame[column], errors="coerce").dropna()
    if values.empty:
        return default
    return float(values.iloc[-1])


def _min_numeric_value(frame: pd.DataFrame, column: str) -> float | None:
    if frame.empty or column not in frame.columns:
        return None
    values = pd.to_numeric(frame[column], errors="coerce").dropna()
    if values.empty:
        return None
    return float(values.min())


def _mean_numeric_value(frame: pd.DataFrame, column: str) -> float | None:
    if frame.empty or column not in frame.columns:
        return None
    values = pd.to_numeric(frame[column], errors="coerce").dropna()
    if values.empty:
        return None
    return float(values.mean())


def _cash_part(value: float) -> str:
    numeric = float(value)
    return str(int(numeric)) if numeric.is_integer() else f"{numeric:g}"


def _portfolio_strategy_id(
    start_date: object,
    end_date: object,
    top_k: int,
    holding_days: int,
    initial_cash: float,
) -> str:
    return (
        f"portfolio:{_iso_date(start_date)}:{_iso_date(end_date)}:"
        f"top{top_k}:h{holding_days}:cash{_cash_part(initial_cash)}"
    )


def _portfolio_report_stem(
    start_date: str,
    end_date: str,
    initial_cash: float,
    top_ks: tuple[int, ...],
    holding_days: tuple[int, ...],
) -> str:
    top_part = "-".join(str(value) for value in top_ks)
    holding_part = "-".join(str(value) for value in holding_days)
    return (
        f"portfolio_{start_date}_{end_date}_cash{_cash_part(initial_cash)}"
        f"_top{top_part}_h{holding_part}"
    )


def _combined_equity_curve(results: list[PortfolioResult]) -> pd.DataFrame:
    frames = []
    for result in results:
        frame = result.equity_curve.copy()
        frame["top_k"] = result.config.top_k
        frame["holding_days"] = result.config.holding_days
        frames.append(frame)
    if not frames:
        return pd.DataFrame(columns=EQUITY_COLUMNS + ["top_k", "holding_days"])
    return pd.concat(frames, ignore_index=True)


def _combined_trades(results: list[PortfolioResult]) -> pd.DataFrame:
    frames = [result.trades.copy() for result in results]
    if not frames:
        return pd.DataFrame(columns=TRADE_COLUMNS)
    return pd.concat(frames, ignore_index=True)


def _format_decimal(value: object, digits: int = 4) -> str:
    if value is None or pd.isna(value):
        return "N/A"
    return f"{float(value):.{digits}f}"


def _format_int(value: object) -> str:
    if value is None or pd.isna(value):
        return "N/A"
    return str(int(value))


def _format_percent(value: object) -> str:
    if value is None or pd.isna(value):
        return "N/A"
    return f"{float(value) * 100:.2f}%"


def _markdown_cell(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).replace("|", "\\|")


def _base_trade_row(
    selection: BacktestSelection,
    buy_date: str | None,
    config: PortfolioConfig,
) -> dict[str, Any]:
    return {
        "strategy_id": config.strategy_id,
        "top_k": config.top_k,
        "holding_days": config.holding_days,
        "selection_date": selection.selection_date,
        "buy_date": buy_date,
        "asset_id": selection.asset_id,
        "rank": selection.rank,
        "score": selection.score,
        "shares": 0,
        "buy_open": None,
        "buy_value": None,
        "sell_date": None,
        "sell_open": None,
        "sell_value": None,
        "return_value": None,
        "status": "skipped",
        "skip_reason": None,
    }


def _skip_trade(
    selection: BacktestSelection,
    buy_date: str | None,
    config: PortfolioConfig,
    skip_reason: str,
) -> dict[str, Any]:
    row = _base_trade_row(selection, buy_date, config)
    row["skip_reason"] = skip_reason
    return row


def _schedule_next_buy_batch(
    current_date: str,
    end_date: str,
    features: pd.DataFrame,
    bars: pd.DataFrame,
    trading_dates: list[str],
    bars_by_date_asset: dict[tuple[str, str], BacktestBar],
    pending_buys: dict[str, list[dict[str, Any]]],
    trade_rows: list[dict[str, Any]],
    config: PortfolioConfig,
) -> None:
    selections = select_top_for_date(features, bars, current_date, top_n=config.top_k)
    if not selections:
        return

    buy_date = next_trade_date(trading_dates, current_date)
    if buy_date is None:
        for selection in selections:
            trade_rows.append(
                _skip_trade(selection, None, config, "missing_next_buy_date")
            )
        return
    if buy_date > end_date:
        return

    eligible: list[tuple[BacktestSelection, BacktestBar]] = []
    for selection in selections:
        buy_bar = bars_by_date_asset.get((buy_date, selection.asset_id))
        decision = apply_buy_filter(selection, buy_bar)
        if decision.can_buy and buy_bar is not None:
            eligible.append((selection, buy_bar))
        else:
            trade_rows.append(
                _skip_trade(
                    selection,
                    buy_date,
                    config,
                    decision.skip_reason or "missing_next_buy_date",
                )
            )

    if not eligible:
        return

    pending_buys.setdefault(buy_date, []).append(
        {
            "selection_date": current_date,
            "eligible": eligible,
        }
    )


def _execute_buy_batch(
    current_date: str,
    batch: dict[str, Any],
    cash: float,
    positions: list[dict[str, Any]],
    trade_rows: list[dict[str, Any]],
    bars_by_asset: dict[str, list[BacktestBar]],
    bars_by_date_asset: dict[tuple[str, str], BacktestBar],
    config: PortfolioConfig,
) -> float:
    equity = cash + _market_value(positions, bars_by_date_asset, current_date)
    batch_budget = min(float(cash), float(equity) / config.holding_days)
    single_stock_budget = batch_budget / len(batch["eligible"])

    for selection, buy_bar in batch["eligible"]:
        if buy_bar.open is None:
            trade_rows.append(
                _skip_trade(selection, current_date, config, "missing_price")
            )
            continue

        affordable_budget = min(float(single_stock_budget), cash)
        shares = shares_for_budget(affordable_budget, buy_bar.open, config.lot_size)
        if shares == 0:
            trade_rows.append(
                _skip_trade(
                    selection,
                    current_date,
                    config,
                    "insufficient_lot_cash",
                )
            )
            continue

        buy_value = shares * float(buy_bar.open)
        cash -= buy_value
        sell_bar = sell_bar_for_holding(
            bars_by_asset.get(selection.asset_id, []),
            current_date,
            config.holding_days,
        )
        trade = _base_trade_row(selection, current_date, config)
        trade.update(
            {
                "shares": shares,
                "buy_open": float(buy_bar.open),
                "buy_value": buy_value,
                "status": "open",
            }
        )
        if sell_bar is not None:
            trade.update(
                {
                    "sell_date": sell_bar.trade_date,
                    "sell_open": sell_bar.open,
                    "sell_value": shares * float(sell_bar.open),
                    "return_value": round(
                        float(sell_bar.open) / float(buy_bar.open) - 1.0,
                        10,
                    ),
                }
            )

        trade_rows.append(trade)
        positions.append(
            {
                "asset_id": selection.asset_id,
                "shares": shares,
                "trade": trade,
                "sell_date": sell_bar.trade_date if sell_bar is not None else None,
                "last_price": float(buy_bar.open),
            }
        )

    return cash


def _close_due_positions(
    current_date: str,
    cash: float,
    positions: list[dict[str, Any]],
) -> float:
    remaining: list[dict[str, Any]] = []
    for position in positions:
        if position["sell_date"] == current_date:
            trade = position["trade"]
            cash += float(trade["sell_value"])
            trade["status"] = "closed"
        else:
            remaining.append(position)
    positions[:] = remaining
    return cash


def _market_value(
    positions: list[dict[str, Any]],
    bars_by_date_asset: dict[tuple[str, str], BacktestBar],
    current_date: str,
) -> float:
    value = 0.0
    for position in positions:
        bar = bars_by_date_asset.get((current_date, position["asset_id"]))
        if bar is not None and bar.open is not None:
            mark_price = float(bar.open)
            position["last_price"] = mark_price
        else:
            mark_price = position.get("last_price", position["trade"]["buy_open"])
        value += int(position["shares"]) * float(mark_price)
    return value
