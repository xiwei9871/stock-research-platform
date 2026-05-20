import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from stock_research.backtest import (
    BacktestSelection,
    LOW_LIQUIDITY_THRESHOLD,
    FEATURE_COLUMNS,
    REQUIRED_SCORE_FEATURES,
    load_backtest_bars,
    load_backtest_inputs,
    next_trade_date,
)
from stock_research.backtest_constraints import (
    BacktestExecutionConstraints,
    can_close_long,
    can_open_long,
    one_way_cost_rate,
)
from stock_research.portfolio_backtest import shares_for_budget
from stock_research.run_card import write_run_card
from stock_research.selection import score_asset
from stock_research.services.universe_service import (
    UniverseResult,
    filter_dataframe_by_universe,
    get_universe_allowed_ids,
)


RETENTION_TRADE_COLUMNS = [
    "strategy_id",
    "max_positions",
    "selection_date",
    "buy_date",
    "asset_id",
    "rank",
    "score",
    "shares",
    "buy_open",
    "buy_value",
    "sell_signal_date",
    "sell_date",
    "sell_open",
    "sell_value",
    "return_value",
    "status",
    "exit_reason",
    "skip_reason",
]

RETENTION_EQUITY_COLUMNS = [
    "strategy_id",
    "date",
    "cash",
    "market_value",
    "equity",
    "drawdown",
    "open_positions",
]

RETENTION_SUMMARY_COLUMNS = [
    "strategy_id",
    "max_positions",
    "initial_cash",
    "final_equity",
    "total_return",
    "max_drawdown",
    "closed_trades",
    "open_trades",
    "skipped_trades",
    "win_rate",
    "mean_trade_return",
    "average_holding_days",
    "max_holding_days",
    "turnover_count",
    "average_cash",
    "average_market_value",
    "average_capital_utilization",
    "insufficient_lot_cash_skips",
    "execution_skips",
]


@dataclass(frozen=True)
class RetentionConfig:
    start_date: object
    end_date: object
    initial_cash: float = 500000.0
    max_positions: int = 5
    lot_size: int = 100
    strategy_id: str | None = None
    entry_top_n: int = 20
    observe_top_n: int = 20
    exit_confirm_days: int = 1
    ma20_exit: bool = False
    use_adjusted_score: bool = False
    hard_entry_filters: bool = False
    market_entry_filter: bool = False
    board_entry_filter: bool = False
    stop_loss_pct: float | None = None
    execution_constraints: BacktestExecutionConstraints = field(
        default_factory=BacktestExecutionConstraints
    )


@dataclass(frozen=True)
class RetentionResult:
    config: RetentionConfig
    equity_curve: pd.DataFrame
    trades: pd.DataFrame


def simulate_retention_config(
    feature_frame: pd.DataFrame,
    bar_frame: pd.DataFrame,
    config: RetentionConfig,
    signal_cache: dict[str, dict[str, Any]] | None = None,
    universe_result: UniverseResult | None = None,
) -> RetentionResult:
    if config.max_positions <= 0:
        raise ValueError("max_positions must be positive")
    if config.lot_size <= 0:
        raise ValueError("lot_size must be positive")
    if config.entry_top_n <= 0:
        raise ValueError("entry_top_n must be positive")
    if config.observe_top_n < config.entry_top_n:
        raise ValueError("observe_top_n must be greater than or equal to entry_top_n")
    if config.exit_confirm_days <= 0:
        raise ValueError("exit_confirm_days must be positive")

    features = _normalize_dates(
        filter_dataframe_by_universe(
            feature_frame,
            universe_result,
            asset_id_col="asset_id",
        )
    )
    bars = _normalize_dates(
        filter_dataframe_by_universe(
            bar_frame,
            universe_result,
            asset_id_col="asset_id",
        )
    )
    filtered_signal_cache = _filter_retention_signal_cache_by_universe(
        signal_cache,
        universe_result,
    )
    trading_dates = _trading_dates(bars)
    start_date = _iso_date(config.start_date)
    end_date = _iso_date(config.end_date)
    simulation_dates = [date for date in trading_dates if start_date <= date]

    bars_by_date_asset = _bars_by_date_asset(bars)
    pending_buys: dict[str, list[dict[str, Any]]] = {}
    positions: list[dict[str, Any]] = []
    trade_rows: list[dict[str, Any]] = []
    equity_rows: list[dict[str, Any]] = []

    cash = float(config.initial_cash)
    peak_equity = float(config.initial_cash)

    for current_date in simulation_dates:
        if (
            current_date > end_date
            and not positions
            and current_date not in pending_buys
        ):
            break

        cash = _execute_pending_sells(current_date, cash, positions, bars_by_date_asset, config)

        for pending_buy in pending_buys.pop(current_date, []):
            cash, finalized = _execute_pending_buy(
                current_date=current_date,
                pending_buy=pending_buy,
                cash=cash,
                positions=positions,
                trade_rows=trade_rows,
                bars_by_date_asset=bars_by_date_asset,
                config=config,
            )
            if not finalized:
                next_buy_date = next_trade_date(trading_dates, current_date)
                if next_buy_date is None:
                    trade_rows.append(
                        _skip_trade(
                            pending_buy["selection"],
                            current_date,
                            config,
                            "missing_next_buy_date",
                        )
                    )
                    continue
                pending_buys.setdefault(next_buy_date, []).append(pending_buy)

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
            signal = (
                filtered_signal_cache.get(current_date, {})
                if filtered_signal_cache is not None
                else {}
            )
            selections = signal.get("selections")
            feature_values = signal.get("feature_values")
            market_allows_entry = bool(signal.get("market_allows_entry", True))
            entry_allowed_assets = signal.get("entry_allowed_assets")
            if selections is None:
                selections = select_retention_candidates(
                    features,
                    bars,
                    current_date,
                    config,
                    universe_result=universe_result,
                )
            if feature_values is None:
                feature_values = _feature_values_for_date(features, current_date)
            _schedule_retention_actions(
                current_date=current_date,
                end_date=end_date,
                selections=selections,
                feature_values=feature_values,
                market_allows_entry=market_allows_entry,
                entry_allowed_assets=entry_allowed_assets,
                trading_dates=trading_dates,
                positions=positions,
                pending_buys=pending_buys,
                config=config,
            )

    return RetentionResult(
        config=config,
        equity_curve=pd.DataFrame(equity_rows, columns=RETENTION_EQUITY_COLUMNS),
        trades=pd.DataFrame(trade_rows, columns=RETENTION_TRADE_COLUMNS),
    )


def select_retention_candidates(
    feature_frame: pd.DataFrame,
    bar_frame: pd.DataFrame,
    selection_date: object,
    config: RetentionConfig,
    universe_result: UniverseResult | None = None,
) -> list[BacktestSelection]:
    normalized_date = _iso_date(selection_date)
    if feature_frame.empty or bar_frame.empty:
        return []

    filtered_features = filter_dataframe_by_universe(
        feature_frame,
        universe_result,
        asset_id_col="asset_id",
    )
    filtered_bars = filter_dataframe_by_universe(
        bar_frame,
        universe_result,
        asset_id_col="asset_id",
    )

    matrix = _feature_values_for_date(filtered_features, normalized_date)
    if not matrix:
        return []

    bars = filtered_bars.copy()
    bars["trade_date"] = bars["trade_date"].map(_iso_date)
    bars = bars[bars["trade_date"] == normalized_date]
    if bars.empty:
        return []
    bars_by_asset = bars.drop_duplicates("asset_id").set_index("asset_id")

    scored: list[dict[str, Any]] = []
    for asset_id, features in matrix.items():
        if asset_id not in bars_by_asset.index:
            continue
        status = bars_by_asset.loc[asset_id]
        if bool(status["is_st"]) is True or str(status["trade_status"]) != "1":
            continue
        if any(_is_missing(features.get(name)) for name in REQUIRED_SCORE_FEATURES):
            continue
        amount_20d_avg = features.get("amount_20d_avg")
        if _is_missing(amount_20d_avg) or float(amount_20d_avg) < 30000000.0:
            continue
        if config.hard_entry_filters and not _passes_hard_entry_filters(features):
            continue

        scored.append(
            {
                "asset_id": str(asset_id),
                "score": _retention_score(features, config.use_adjusted_score),
                "ret_20d": features.get("ret_20d"),
                "amount_20d_avg": amount_20d_avg,
            }
        )

    scored.sort(key=lambda row: (-float(row["score"]), row["asset_id"]))
    return [
        BacktestSelection(
            selection_date=normalized_date,
            asset_id=row["asset_id"],
            rank=rank,
            score=float(row["score"]),
            ret_20d=_float_or_none(row["ret_20d"]),
            amount_20d_avg=_float_or_none(row["amount_20d_avg"]),
        )
        for rank, row in enumerate(scored[: config.observe_top_n], start=1)
    ]


def summarize_retention_result(result: RetentionResult) -> dict[str, object]:
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
        else pd.Series("", index=trades.index, dtype=object)
    )
    closed_mask = statuses == "closed"
    closed_trades = int(closed_mask.sum())
    open_trades = int((statuses == "open").sum())
    skipped_trades = int((statuses == "skipped").sum())

    closed_returns = pd.Series(dtype=float)
    if not trades.empty and "return_value" in trades.columns and "status" in trades.columns:
        closed_returns = pd.to_numeric(
            trades.loc[closed_mask, "return_value"],
            errors="coerce",
        ).dropna()
    win_rate = float((closed_returns > 0).mean()) if not closed_returns.empty else None
    mean_trade_return = float(closed_returns.mean()) if not closed_returns.empty else None

    holding_days = _closed_holding_days(trades, closed_mask)
    average_holding_days = (
        float(holding_days.mean()) if not holding_days.empty else None
    )
    max_holding_days = int(holding_days.max()) if not holding_days.empty else None

    skip_reasons = (
        trades.loc[statuses == "skipped", "skip_reason"].astype(str)
        if "skip_reason" in trades.columns and not trades.empty
        else pd.Series(dtype=object)
    )
    insufficient_lot_cash_skips = int((skip_reasons == "insufficient_lot_cash").sum())
    execution_skips = int(skipped_trades - insufficient_lot_cash_skips)

    return {
        "strategy_id": config.strategy_id,
        "max_positions": config.max_positions,
        "initial_cash": float(config.initial_cash),
        "final_equity": final_equity,
        "total_return": total_return,
        "max_drawdown": max_drawdown,
        "closed_trades": closed_trades,
        "open_trades": open_trades,
        "skipped_trades": skipped_trades,
        "win_rate": win_rate,
        "mean_trade_return": mean_trade_return,
        "average_holding_days": average_holding_days,
        "max_holding_days": max_holding_days,
        "turnover_count": closed_trades,
        "average_cash": average_cash,
        "average_market_value": average_market_value,
        "average_capital_utilization": average_capital_utilization,
        "insufficient_lot_cash_skips": insufficient_lot_cash_skips,
        "execution_skips": execution_skips,
    }


def write_retention_report(
    results: list[RetentionResult],
    summary: pd.DataFrame,
    start_date: object,
    end_date: object,
    initial_cash: float,
    top_ks: tuple[int, ...] = (5, 10),
    variant: str = "v1",
    reports_dir: str | Path = Path("/Users/xiwei/stock_research/reports"),
) -> dict[str, str]:
    reports_path = Path(reports_dir)
    reports_path.mkdir(parents=True, exist_ok=True)

    start = _iso_date(start_date)
    end = _iso_date(end_date)
    top_values = tuple(int(value) for value in top_ks)
    stem = _retention_report_stem(start, end, initial_cash, top_values, variant)
    report_path = reports_path / f"{stem}.md"
    equity_curve_path = reports_path / f"{stem}_equity.csv"
    trades_path = reports_path / f"{stem}_trades.csv"
    summary_path = reports_path / f"{stem}_summary.csv"

    equity_curve = _combined_equity_curve(results)
    trades = _combined_trades(results)
    summary = summary.reindex(columns=RETENTION_SUMMARY_COLUMNS)
    equity_curve.to_csv(equity_curve_path, index=False)
    trades.to_csv(trades_path, index=False)
    summary.to_csv(summary_path, index=False)

    lines = [
        "# Top20 留存策略账户回测报告",
        "",
        "仅作为研究验证，不构成交易指令。",
        "",
        "## 总览",
        "",
        f"- 回测区间：{start} 至 {end}",
        f"- 初始资金：{_format_decimal(initial_cash, digits=0)}",
        f"- 策略版本：{variant}",
        f"- 最大持仓数：{', '.join(str(value) for value in top_values)}",
        f"- 退出规则：{_exit_rule_description(variant)}",
        "",
        "| strategy_id | max_positions | final_equity | total_return | 最大回撤 | closed | open | skipped | win_rate | 平均持有天数 | 换手次数 | 资金利用率 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]

    for _, row in summary.iterrows():
        lines.append(
            "| "
            f"{_markdown_cell(row.get('strategy_id'))} | "
            f"{_format_int(row.get('max_positions'))} | "
            f"{_format_decimal(row.get('final_equity'), digits=2)} | "
            f"{_format_percent(row.get('total_return'))} | "
            f"{_format_percent(row.get('max_drawdown'))} | "
            f"{_format_int(row.get('closed_trades'))} | "
            f"{_format_int(row.get('open_trades'))} | "
            f"{_format_int(row.get('skipped_trades'))} | "
            f"{_format_percent(row.get('win_rate'))} | "
            f"{_format_decimal(row.get('average_holding_days'), digits=2)} | "
            f"{_format_int(row.get('turnover_count'))} | "
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
                f"- max_positions={_format_int(row.get('max_positions'))}："
                f"{_format_percent(row.get('max_drawdown'))}"
            )

    lines.extend(["", "## 持有与换手", ""])
    if summary.empty:
        lines.append("- 无持有样本。")
    else:
        for _, row in summary.iterrows():
            lines.append(
                f"- max_positions={_format_int(row.get('max_positions'))}："
                f"平均持有 {_format_decimal(row.get('average_holding_days'), digits=2)} 天，"
                f"换手 {_format_int(row.get('turnover_count'))} 次。"
            )

    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {
        "report_path": str(report_path),
        "equity_curve_path": str(equity_curve_path),
        "trades_path": str(trades_path),
        "summary_path": str(summary_path),
    }


def run_retention_backtest(
    start_date: object,
    end_date: object,
    initial_cash: float = 500000.0,
    top_ks: tuple[int, ...] = (5, 10),
    reports_dir: str | Path = Path("/Users/xiwei/stock_research/reports"),
    variant: str = "v1",
    cache_dir: str | Path | None = Path("/Users/xiwei/stock_research/cache/v3_1"),
    universe_result: UniverseResult | None = None,
    execution_constraints: BacktestExecutionConstraints | None = None,
) -> dict[str, object]:
    normalized_variant = _normalize_variant(variant)
    top_values = tuple(int(value) for value in top_ks)
    signal_config = _retention_config_for_variant(
        variant=normalized_variant,
        start_date=start_date,
        end_date=end_date,
        initial_cash=float(initial_cash),
        max_positions=top_values[0] if top_values else 1,
        strategy_id=None,
        execution_constraints=execution_constraints,
    )
    if normalized_variant == "v3.1" and cache_dir is not None:
        features = pd.DataFrame(columns=FEATURE_COLUMNS)
        bars = load_backtest_bars(
            start_date,
            end_date,
            future_buffer_days=30,
        )
        signal_cache = _load_v31_signal_cache(
            cache_dir=cache_dir,
            start_date=start_date,
            end_date=end_date,
            config=signal_config,
            universe_result=universe_result,
        )
    else:
        features, bars = load_backtest_inputs(
            start_date,
            end_date,
            future_buffer_days=30,
        )
        signal_cache = _build_retention_signal_cache(
            features,
            bars,
            signal_config,
            universe_result=universe_result,
        )

    results: list[RetentionResult] = []
    for top_k in top_values:
        config = _retention_config_for_variant(
            variant=normalized_variant,
            start_date=start_date,
            end_date=end_date,
            initial_cash=float(initial_cash),
            max_positions=top_k,
            strategy_id=_retention_strategy_id(
                start_date,
                end_date,
                top_k,
                initial_cash,
                normalized_variant,
            ),
            execution_constraints=execution_constraints,
        )
        simulate_kwargs = {
            "signal_cache": signal_cache,
        }
        if universe_result is not None:
            simulate_kwargs["universe_result"] = universe_result
        results.append(
            simulate_retention_config(
                features,
                bars,
                config,
                **simulate_kwargs,
            )
        )

    summary = pd.DataFrame(
        [summarize_retention_result(result) for result in results],
        columns=RETENTION_SUMMARY_COLUMNS,
    )
    report_paths = write_retention_report(
        results,
        summary,
        start_date=start_date,
        end_date=end_date,
        initial_cash=float(initial_cash),
        top_ks=top_values,
        variant=normalized_variant,
        reports_dir=reports_dir,
    )
    run_card = write_retention_run_card(
        results=results,
        summary=summary,
        start_date=start_date,
        end_date=end_date,
        initial_cash=float(initial_cash),
        top_ks=top_values,
        variant=normalized_variant,
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


def write_retention_run_card(
    *,
    results: list[RetentionResult],
    summary: pd.DataFrame,
    start_date: object,
    end_date: object,
    initial_cash: float,
    top_ks: tuple[int, ...],
    variant: str,
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
        run_type="retention_backtest",
        run_id=(
            f"retention:{_iso_date(start_date)}:{_iso_date(end_date)}:"
            f"top{'-'.join(str(value) for value in top_ks)}:{variant}"
        ),
        title="Retention Backtest",
        config={
            **(asdict(results[0].config) if results else {}),
            "start_date": _iso_date(start_date),
            "end_date": _iso_date(end_date),
            "initial_cash": float(initial_cash),
            "top_ks": list(top_ks),
            "variant": variant,
        },
        metrics={
            "workflow_type": "retention_backtest",
            "strategy_count": len(results),
            "summary_rows": int(len(summary)),
            "final_equity_mean": _mean_numeric_value(summary, "final_equity"),
            "max_drawdown_min": _min_numeric_value(summary, "max_drawdown"),
            "total_return_mean": _mean_numeric_value(summary, "total_return"),
            "trade_count": int(len(trades)),
            "position_count": asset_count,
            "win_rate_mean": _mean_numeric_value(summary, "win_rate"),
            "start_date": _iso_date(start_date),
            "end_date": _iso_date(end_date),
            "candidate_count": None,
            "retained_count": int(len(results)),
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


def _normalize_variant(variant: str) -> str:
    normalized = str(variant).strip().lower()
    if normalized not in {"v1", "v2", "v3.1", "v31"}:
        raise ValueError("variant must be one of: v1, v2, v3.1")
    if normalized == "v31":
        return "v3.1"
    return normalized


def _build_retention_signal_cache(
    feature_frame: pd.DataFrame,
    bar_frame: pd.DataFrame,
    config: RetentionConfig,
    universe_result: UniverseResult | None = None,
) -> dict[str, dict[str, Any]]:
    if "trade_date" not in feature_frame.columns or "trade_date" not in bar_frame.columns:
        return {}
    features = _normalize_dates(
        filter_dataframe_by_universe(
            feature_frame,
            universe_result,
            asset_id_col="asset_id",
        )
    )
    bars = _normalize_dates(
        filter_dataframe_by_universe(
            bar_frame,
            universe_result,
            asset_id_col="asset_id",
        )
    )
    start_date = _iso_date(config.start_date)
    end_date = _iso_date(config.end_date)
    cache: dict[str, dict[str, Any]] = {}
    daily_bars = _daily_bar_frames(bars)
    feature_values_by_date = _feature_values_by_date(features)
    market_entry_by_date = _market_entry_by_date(bars, daily_bars, config)
    board_assets_by_date = _entry_allowed_assets_by_date(
        feature_values_by_date,
        daily_bars,
        config,
    )
    for trade_date in sorted(daily_bars):
        if trade_date < start_date or trade_date > end_date:
            continue
        cache[trade_date] = {
            "selections": select_retention_candidates(
                features,
                bars,
                trade_date,
                config,
                universe_result=universe_result,
            ),
            "feature_values": feature_values_by_date.get(trade_date, {}),
            "market_allows_entry": market_entry_by_date.get(trade_date, True),
            "entry_allowed_assets": board_assets_by_date.get(trade_date),
        }
    return cache


def _load_v31_signal_cache(
    cache_dir: str | Path,
    start_date: object,
    end_date: object,
    config: RetentionConfig,
    universe_result: UniverseResult | None = None,
) -> dict[str, dict[str, Any]]:
    cache_path = Path(cache_dir)
    manifest_path = cache_path / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"v3.1 cache manifest not found: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    start = _iso_date(start_date)
    end = _iso_date(end_date)
    if str(manifest["start_date"]) > start or str(manifest["end_date"]) < end:
        raise ValueError(
            "v3.1 cache does not cover requested backtest range: "
            f"{start} to {end}"
        )

    paths = manifest["paths"]
    asset_features = _read_cache_frame(paths["asset_features"])
    market_regime = _read_cache_frame(paths["market_regime"])
    board_regime = _read_cache_frame(paths["board_regime"])
    candidates = _read_cache_frame(paths["retention_candidates"])

    asset_features = _slice_cache_dates(asset_features, start, end)
    market_regime = _slice_cache_dates(market_regime, start, end)
    board_regime = _slice_cache_dates(board_regime, start, end)
    candidates = _slice_cache_dates(candidates, start, end)

    feature_values = _feature_values_from_asset_feature_cache(asset_features)
    market_entry = {
        str(row["trade_date"]): _bool_value(row.get("market_allows_entry"))
        for row in market_regime.to_dict("records")
    }
    board_assets = _entry_allowed_assets_from_board_cache(asset_features, board_regime)
    selections = _selections_from_candidate_cache(candidates, feature_values, config)

    dates = sorted(set(feature_values) | set(selections) | set(market_entry) | set(board_assets))
    result = {
        trade_date: {
            "selections": selections.get(trade_date, []),
            "feature_values": feature_values.get(trade_date, {}),
            "market_allows_entry": market_entry.get(trade_date, True),
            "entry_allowed_assets": board_assets.get(trade_date),
        }
        for trade_date in dates
    }
    return _filter_retention_signal_cache_by_universe(result, universe_result)


def _filter_retention_signal_cache_by_universe(
    signal_cache: dict[str, dict[str, Any]] | None,
    universe_result: UniverseResult | None,
) -> dict[str, dict[str, Any]] | None:
    if signal_cache is None or universe_result is None:
        return signal_cache
    allowed = get_universe_allowed_ids(universe_result)
    if allowed is None:
        return signal_cache
    filtered: dict[str, dict[str, Any]] = {}
    for trade_date, payload in signal_cache.items():
        selections = [
            selection
            for selection in payload.get("selections", [])
            if str(selection.asset_id) in allowed
        ]
        feature_values = {
            str(asset_id): values
            for asset_id, values in payload.get("feature_values", {}).items()
            if str(asset_id) in allowed
        }
        entry_allowed_assets = payload.get("entry_allowed_assets")
        if entry_allowed_assets is not None:
            entry_allowed_assets = {
                str(asset_id) for asset_id in entry_allowed_assets if str(asset_id) in allowed
            }
        filtered[trade_date] = {
            "selections": selections,
            "feature_values": feature_values,
            "market_allows_entry": payload.get("market_allows_entry", True),
            "entry_allowed_assets": entry_allowed_assets,
        }
    return filtered


def _read_cache_frame(path: str) -> pd.DataFrame:
    cache_file = Path(path)
    if cache_file.suffix == ".parquet":
        return pd.read_parquet(cache_file)
    return pd.read_csv(cache_file)


def _slice_cache_dates(frame: pd.DataFrame, start_date: str, end_date: str) -> pd.DataFrame:
    if frame.empty or "trade_date" not in frame.columns:
        return frame.copy()
    result = frame.copy()
    result["trade_date"] = result["trade_date"].map(_iso_date)
    return result[
        (result["trade_date"] >= start_date)
        & (result["trade_date"] <= end_date)
    ].reset_index(drop=True)


def _feature_values_from_asset_feature_cache(
    asset_features: pd.DataFrame,
) -> dict[str, dict[str, dict[str, float]]]:
    result: dict[str, dict[str, dict[str, float]]] = {}
    for row in asset_features.to_dict("records"):
        trade_date = str(row["trade_date"])
        asset_id = str(row["asset_id"])
        result.setdefault(trade_date, {})[asset_id] = {
            str(name): float(value)
            for name, value in row.items()
            if name not in {"trade_date", "asset_id"} and not _is_missing(value)
        }
    return result


def _entry_allowed_assets_from_board_cache(
    asset_features: pd.DataFrame,
    board_regime: pd.DataFrame,
) -> dict[str, set[str] | None]:
    if asset_features.empty:
        return {}
    allowed_boards_by_date: dict[str, set[str]] = {}
    for row in board_regime.to_dict("records"):
        if _bool_value(row.get("board_allows_entry")):
            allowed_boards_by_date.setdefault(str(row["trade_date"]), set()).add(
                str(row["board"])
            )

    result: dict[str, set[str] | None] = {}
    for row in asset_features[["trade_date", "asset_id"]].drop_duplicates().to_dict("records"):
        trade_date = str(row["trade_date"])
        allowed_boards = allowed_boards_by_date.get(trade_date, set())
        result.setdefault(trade_date, set())
        if _board_key(str(row["asset_id"])) in allowed_boards:
            result[trade_date].add(str(row["asset_id"]))  # type: ignore[union-attr]
    return result


def _selections_from_candidate_cache(
    candidates: pd.DataFrame,
    feature_values: dict[str, dict[str, dict[str, float]]],
    config: RetentionConfig,
) -> dict[str, list[BacktestSelection]]:
    result: dict[str, list[BacktestSelection]] = {}
    if candidates.empty:
        return result
    frame = candidates.copy()
    frame["rank"] = pd.to_numeric(frame["rank"], errors="coerce")
    frame["score"] = pd.to_numeric(frame["score"], errors="coerce")
    frame = frame[frame["rank"].notna() & frame["score"].notna()]
    if config.hard_entry_filters and "hard_filter_pass" in frame.columns:
        frame = frame[frame["hard_filter_pass"].map(_bool_value)]
    frame = frame.sort_values(["trade_date", "rank", "asset_id"])
    for trade_date, group in frame.groupby("trade_date", sort=True):
        selections = []
        for row in group.to_dict("records"):
            if int(row["rank"]) > config.observe_top_n:
                continue
            asset_id = str(row["asset_id"])
            values = feature_values.get(str(trade_date), {}).get(asset_id, {})
            selections.append(
                BacktestSelection(
                    selection_date=str(trade_date),
                    asset_id=asset_id,
                    rank=int(row["rank"]),
                    score=float(row["score"]),
                    ret_20d=_float_or_none(values.get("ret_20d")),
                    amount_20d_avg=_float_or_none(values.get("amount_20d_avg")),
                )
            )
        result[str(trade_date)] = selections
    return result


def _bool_value(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if _is_missing(value):
        return False
    return str(value).strip().lower() in {"1", "true", "t", "yes", "y"}


def _market_allows_entry(
    bar_frame: pd.DataFrame,
    trade_date: str,
    config: RetentionConfig,
) -> bool:
    if not config.market_entry_filter:
        return True
    current = _bars_for_date(bar_frame, trade_date)
    if current.empty:
        return False
    tradable = current[current["trade_status"].astype(str) == "1"].copy()
    if tradable.empty:
        return False
    up_ratio = _up_ratio(tradable)
    limit_stats = _limit_stats(tradable)
    amount_ok = _market_amount_ok(bar_frame, trade_date)
    return (
        up_ratio >= 0.45
        and limit_stats["limit_down_count"] <= 80
        and limit_stats["limit_up_down_ratio"] >= 1.2
        and amount_ok
    )


def _daily_bar_frames(bar_frame: pd.DataFrame) -> dict[str, pd.DataFrame]:
    if bar_frame.empty or "trade_date" not in bar_frame.columns:
        return {}
    return {
        str(trade_date): group.reset_index(drop=True).copy()
        for trade_date, group in bar_frame.groupby("trade_date", sort=True)
    }


def _feature_values_by_date(
    feature_frame: pd.DataFrame,
) -> dict[str, dict[str, dict[str, float]]]:
    if feature_frame.empty or "trade_date" not in feature_frame.columns:
        return {}
    by_date: dict[str, dict[str, dict[str, float]]] = {}
    for trade_date, group in feature_frame.groupby("trade_date", sort=True):
        by_date[str(trade_date)] = _feature_values_from_frame(group)
    return by_date


def _feature_values_from_frame(feature_frame: pd.DataFrame) -> dict[str, dict[str, float]]:
    if feature_frame.empty:
        return {}
    matrix = feature_frame.pivot_table(
        index="asset_id",
        columns="feature_name",
        values="feature_value",
        aggfunc="first",
    )
    values: dict[str, dict[str, float]] = {}
    for asset_id, row in matrix.iterrows():
        values[str(asset_id)] = {
            str(name): float(value)
            for name, value in row.to_dict().items()
            if not _is_missing(value)
        }
    return values


def _market_entry_by_date(
    bar_frame: pd.DataFrame,
    daily_bars: dict[str, pd.DataFrame],
    config: RetentionConfig,
) -> dict[str, bool]:
    if not config.market_entry_filter:
        return {trade_date: True for trade_date in daily_bars}
    daily_amount = (
        bar_frame.groupby("trade_date", as_index=False)["amount"]
        .sum()
        .sort_values("trade_date")
        .reset_index(drop=True)
    )
    amount_ok_by_date = _market_amount_ok_by_date(daily_amount)
    result: dict[str, bool] = {}
    for trade_date, current in daily_bars.items():
        tradable = current[current["trade_status"].astype(str) == "1"].copy()
        if tradable.empty:
            result[trade_date] = False
            continue
        up_ratio = _up_ratio(tradable)
        limit_stats = _limit_stats(tradable)
        result[trade_date] = (
            up_ratio >= 0.45
            and limit_stats["limit_down_count"] <= 80
            and limit_stats["limit_up_down_ratio"] >= 1.2
            and amount_ok_by_date.get(trade_date, True)
        )
    return result


def _market_amount_ok_by_date(daily_amount: pd.DataFrame) -> dict[str, bool]:
    if daily_amount.empty:
        return {}
    frame = daily_amount.copy()
    frame["amount"] = pd.to_numeric(frame["amount"], errors="coerce")
    rolling_mean = frame["amount"].rolling(20, min_periods=5).mean()
    result: dict[str, bool] = {}
    for index, row in frame.iterrows():
        trade_date = str(row["trade_date"])
        mean_value = rolling_mean.iloc[index]
        if pd.isna(mean_value):
            result[trade_date] = True
        else:
            result[trade_date] = _float_or_zero(row["amount"]) >= float(mean_value) * 0.75
    return result


def _entry_allowed_assets_by_date(
    feature_values_by_date: dict[str, dict[str, dict[str, float]]],
    daily_bars: dict[str, pd.DataFrame],
    config: RetentionConfig,
) -> dict[str, set[str] | None]:
    if not config.board_entry_filter:
        return {trade_date: None for trade_date in daily_bars}
    result: dict[str, set[str] | None] = {}
    for trade_date, current in daily_bars.items():
        result[trade_date] = _entry_allowed_assets_from_daily(
            feature_values_by_date.get(trade_date, {}),
            current,
        )
    return result


def _entry_allowed_assets_from_daily(
    features: dict[str, dict[str, float]],
    current: pd.DataFrame,
) -> set[str]:
    if current.empty:
        return set()

    rows = []
    for row in current.to_dict("records"):
        asset_id = str(row["asset_id"])
        asset_features = features.get(asset_id, {})
        rows.append(
            {
                "asset_id": asset_id,
                "board": _board_key(asset_id),
                "is_up": _is_up_bar(row),
                "amount": _float_or_none(row.get("amount")),
                "ret_5d": asset_features.get("ret_5d"),
                "ret_20d": asset_features.get("ret_20d"),
            }
        )
    frame = pd.DataFrame(rows)
    if frame.empty:
        return set()

    allowed_boards: set[str] = set()
    for board, group in frame.groupby("board", sort=False):
        ret_5d = pd.to_numeric(group["ret_5d"], errors="coerce").dropna()
        ret_20d = pd.to_numeric(group["ret_20d"], errors="coerce").dropna()
        up_flags = group["is_up"].dropna()
        if ret_20d.empty or up_flags.empty:
            continue
        if (
            float(ret_20d.median()) > 0.0
            and float(ret_5d.median()) > -0.03
            and float(up_flags.mean()) >= 0.45
        ):
            allowed_boards.add(str(board))

    return {
        str(row["asset_id"])
        for row in frame.to_dict("records")
        if row["board"] in allowed_boards
    }


def _entry_allowed_assets_for_date(
    feature_frame: pd.DataFrame,
    bar_frame: pd.DataFrame,
    trade_date: str,
    config: RetentionConfig,
) -> set[str] | None:
    if not config.board_entry_filter:
        return None
    current = _bars_for_date(bar_frame, trade_date)
    if current.empty:
        return set()

    features = _feature_values_for_date(feature_frame, trade_date)
    rows = []
    for row in current.to_dict("records"):
        asset_id = str(row["asset_id"])
        asset_features = features.get(asset_id, {})
        rows.append(
            {
                "asset_id": asset_id,
                "board": _board_key(asset_id),
                "is_up": _is_up_bar(row),
                "amount": _float_or_none(row.get("amount")),
                "ret_5d": asset_features.get("ret_5d"),
                "ret_20d": asset_features.get("ret_20d"),
            }
        )
    frame = pd.DataFrame(rows)
    if frame.empty:
        return set()

    allowed_boards: set[str] = set()
    for board, group in frame.groupby("board", sort=False):
        ret_5d = pd.to_numeric(group["ret_5d"], errors="coerce").dropna()
        ret_20d = pd.to_numeric(group["ret_20d"], errors="coerce").dropna()
        up_flags = group["is_up"].dropna()
        if ret_20d.empty or up_flags.empty:
            continue
        if (
            float(ret_20d.median()) > 0.0
            and float(ret_5d.median()) > -0.03
            and float(up_flags.mean()) >= 0.45
        ):
            allowed_boards.add(str(board))

    return {
        str(row["asset_id"])
        for row in frame.to_dict("records")
        if row["board"] in allowed_boards
    }


def _retention_config_for_variant(
    variant: str,
    start_date: object,
    end_date: object,
    initial_cash: float,
    max_positions: int,
    strategy_id: str | None,
    execution_constraints: BacktestExecutionConstraints | None = None,
) -> RetentionConfig:
    base_kwargs = {
        "start_date": start_date,
        "end_date": end_date,
        "initial_cash": initial_cash,
        "max_positions": max_positions,
        "strategy_id": strategy_id,
        "execution_constraints": execution_constraints or BacktestExecutionConstraints(),
    }
    if variant == "v2":
        return RetentionConfig(
            **base_kwargs,
            entry_top_n=20,
            observe_top_n=30,
            exit_confirm_days=2,
            ma20_exit=True,
            use_adjusted_score=True,
        )
    if variant == "v3.1":
        return RetentionConfig(
            **base_kwargs,
            entry_top_n=20,
            observe_top_n=30,
            exit_confirm_days=2,
            ma20_exit=True,
            use_adjusted_score=True,
            hard_entry_filters=True,
            market_entry_filter=True,
            board_entry_filter=True,
            stop_loss_pct=0.10,
        )
    return RetentionConfig(**base_kwargs)


def _exit_rule_description(variant: str) -> str:
    if variant == "v3.1":
        return "V2 留存；叠加 10% 硬止损、过热硬过滤、市场情绪过滤和板块趋势过滤。"
    if variant == "v2":
        return "Top20 内继续持有；Top20 外 Top30 内连续 2 天观察；跌出 Top30 或 MA20 破坏退出。"
    return "跌出 Top20 退出。"


def _schedule_retention_actions(
    current_date: str,
    end_date: str,
    selections: list[BacktestSelection],
    feature_values: dict[str, dict[str, float]],
    market_allows_entry: bool,
    entry_allowed_assets: set[str] | None,
    trading_dates: list[str],
    positions: list[dict[str, Any]],
    pending_buys: dict[str, list[dict[str, Any]]],
    config: RetentionConfig,
) -> None:
    selections_by_asset = {selection.asset_id: selection for selection in selections}
    exiting_assets = {
        position["asset_id"]
        for position in positions
        if position.get("sell_date") is not None
    }
    sell_date = next_trade_date(trading_dates, current_date)

    for position in positions:
        if position.get("sell_date") is not None:
            continue
        exit_reason = _retention_exit_reason(
            position,
            selections_by_asset.get(position["asset_id"]),
            feature_values.get(position["asset_id"], {}),
            config,
        )
        if exit_reason is None:
            continue
        if sell_date is None:
            continue
        trade = position["trade"]
        trade["sell_signal_date"] = current_date
        trade["sell_date"] = sell_date
        trade["exit_reason"] = exit_reason
        position["sell_date"] = sell_date
        position["sell_signal_date"] = current_date
        position["exit_reason"] = exit_reason
        exiting_assets.add(position["asset_id"])

    buy_date = next_trade_date(trading_dates, current_date)
    if buy_date is None:
        return
    if config.market_entry_filter and not market_allows_entry:
        return

    held_assets = {position["asset_id"] for position in positions}
    pending_buy_assets = {
        pending["selection"].asset_id
        for pending_list in pending_buys.values()
        for pending in pending_list
    }
    unavailable_assets = held_assets | pending_buy_assets | exiting_assets
    retained_position_count = sum(
        1 for position in positions if position["asset_id"] not in exiting_assets
    )
    open_or_pending = retained_position_count + len(pending_buy_assets)
    slots = max(config.max_positions - open_or_pending, 0)
    if slots == 0 or buy_date > end_date:
        return

    for selection in selections:
        if slots == 0:
            break
        if selection.rank > config.entry_top_n:
            break
        if (
            config.board_entry_filter
            and entry_allowed_assets is not None
            and selection.asset_id not in entry_allowed_assets
        ):
            continue
        if selection.asset_id in unavailable_assets:
            continue
        pending_buys.setdefault(buy_date, []).append(
            {
                "selection": selection,
            }
        )
        pending_buy_assets.add(selection.asset_id)
        unavailable_assets.add(selection.asset_id)
        slots -= 1


def _execute_pending_buy(
    current_date: str,
    pending_buy: dict[str, Any],
    cash: float,
    positions: list[dict[str, Any]],
    trade_rows: list[dict[str, Any]],
    bars_by_date_asset: dict[tuple[str, str], dict[str, Any]],
    config: RetentionConfig,
) -> tuple[float, bool]:
    selection = pending_buy["selection"]
    if len(positions) >= config.max_positions:
        return cash, False

    if _is_missing(selection.amount_20d_avg) or float(selection.amount_20d_avg) < LOW_LIQUIDITY_THRESHOLD:
        trade_rows.append(
            _skip_trade(
                selection,
                current_date,
                config,
                "low_liquidity",
            )
        )
        return cash, True

    buy_bar = bars_by_date_asset.get((current_date, selection.asset_id))
    if buy_bar is None:
        trade_rows.append(
            _skip_trade(
                selection,
                current_date,
                config,
                "suspended",
            )
        )
        return cash, True

    if _bool_value(buy_bar.get("is_st")):
        trade_rows.append(_skip_trade(selection, current_date, config, "st"))
        return cash, True

    buy_amount = _float_or_none(buy_bar.get("amount"))
    if buy_amount is None or buy_amount < LOW_LIQUIDITY_THRESHOLD:
        trade_rows.append(_skip_trade(selection, current_date, config, "low_liquidity"))
        return cash, True

    allowed, reason = can_open_long(buy_bar, config.execution_constraints)
    if not allowed:
        trade_rows.append(
            _skip_trade(
                selection,
                current_date,
                config,
                reason or "suspended",
            )
        )
        return cash, True

    if buy_bar.get("open") is None or buy_bar.get("preclose") is None:
        trade_rows.append(_skip_trade(selection, current_date, config, "missing_price"))
        return cash, True

    if float(buy_bar["open"]) >= float(buy_bar["preclose"]) * 1.095:
        trade_rows.append(_skip_trade(selection, current_date, config, "limit_up_open"))
        return cash, True

    equity = cash + _market_value(positions, bars_by_date_asset, current_date)
    target_budget = equity / config.max_positions
    buy_cost_rate = one_way_cost_rate("buy", config.execution_constraints)
    affordable_budget = min(target_budget, cash / (1.0 + buy_cost_rate))
    shares = shares_for_budget(affordable_budget, float(buy_bar["open"]), config.lot_size)
    if shares == 0:
        trade_rows.append(
            _skip_trade(selection, current_date, config, "insufficient_lot_cash")
        )
        return cash, True

    buy_open = float(buy_bar["open"])
    buy_value = shares * buy_open
    cash -= buy_value * (1.0 + buy_cost_rate)
    trade = _base_trade_row(selection, current_date, config)
    trade.update(
        {
            "shares": shares,
            "buy_open": buy_open,
            "buy_value": buy_value,
            "status": "open",
            "skip_reason": None,
        }
    )
    trade_rows.append(trade)
    positions.append(
        {
            "asset_id": selection.asset_id,
            "shares": shares,
            "trade": trade,
            "sell_signal_date": None,
            "sell_date": None,
            "last_price": buy_open,
            "out_of_entry_count": 0,
            "exit_reason": None,
            "buy_cost_rate": buy_cost_rate,
        }
    )
    return cash, True


def _execute_pending_sells(
    current_date: str,
    cash: float,
    positions: list[dict[str, Any]],
    bars_by_date_asset: dict[tuple[str, str], dict[str, Any]],
    config: RetentionConfig,
) -> float:
    remaining: list[dict[str, Any]] = []
    for position in positions:
        sell_date = position.get("sell_date")
        if sell_date is None or current_date < sell_date:
            remaining.append(position)
            continue

        bar = bars_by_date_asset.get((current_date, position["asset_id"]))
        if bar is None:
            remaining.append(position)
            continue

        allowed, _reason = can_close_long(bar, config.execution_constraints)
        if not allowed:
            remaining.append(position)
            continue

        if not _is_tradable_open(bar):
            remaining.append(position)
            continue

        sell_open = float(bar["open"])
        sell_cost_rate = one_way_cost_rate(
            "sell",
            config.execution_constraints,
        )
        position["last_price"] = sell_open
        sell_value = int(position["shares"]) * sell_open
        cash += sell_value * (1.0 - sell_cost_rate)
        trade = position["trade"]
        trade.update(
            {
                "sell_date": current_date,
                "sell_open": sell_open,
                "sell_value": sell_value,
                "return_value": round(
                    (sell_value * (1.0 - sell_cost_rate))
                    / (
                        float(trade["buy_value"])
                        * (1.0 + float(position.get("buy_cost_rate", 0.0)))
                    )
                    - 1.0,
                    10,
                ),
                "status": "closed",
                "exit_reason": position.get("exit_reason") or "exit_top20",
            }
        )
    positions[:] = remaining
    return cash


def _market_value(
    positions: list[dict[str, Any]],
    bars_by_date_asset: dict[tuple[str, str], dict[str, Any]],
    current_date: str,
) -> float:
    value = 0.0
    for position in positions:
        bar = bars_by_date_asset.get((current_date, position["asset_id"]))
        if bar is not None and bar.get("open") is not None:
            position["last_price"] = float(bar["open"])
        value += int(position["shares"]) * float(position["last_price"])
    return value


def _base_trade_row(
    selection: BacktestSelection,
    buy_date: str | None,
    config: RetentionConfig,
) -> dict[str, Any]:
    return {
        "strategy_id": config.strategy_id,
        "max_positions": config.max_positions,
        "selection_date": selection.selection_date,
        "buy_date": buy_date,
        "asset_id": selection.asset_id,
        "rank": selection.rank,
        "score": selection.score,
        "shares": 0,
        "buy_open": None,
        "buy_value": None,
        "sell_signal_date": None,
        "sell_date": None,
        "sell_open": None,
        "sell_value": None,
        "return_value": None,
        "status": "skipped",
        "exit_reason": None,
        "skip_reason": None,
    }


def _skip_trade(
    selection: BacktestSelection,
    buy_date: str | None,
    config: RetentionConfig,
    skip_reason: str,
) -> dict[str, Any]:
    trade = _base_trade_row(selection, buy_date, config)
    trade["skip_reason"] = skip_reason
    return trade


def _normalize_dates(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty or "trade_date" not in frame.columns:
        return frame.copy()
    normalized = frame.copy()
    normalized["trade_date"] = normalized["trade_date"].map(_iso_date)
    return normalized


def _feature_values_for_date(
    feature_frame: pd.DataFrame,
    selection_date: object,
) -> dict[str, dict[str, float]]:
    normalized_date = _iso_date(selection_date)
    if feature_frame.empty or "trade_date" not in feature_frame.columns:
        return {}
    features = feature_frame.copy()
    features["trade_date"] = features["trade_date"].map(_iso_date)
    features = features[features["trade_date"] == normalized_date]
    if features.empty:
        return {}
    return _feature_values_from_frame(features)


def _retention_score(features: dict[str, float], use_adjusted_score: bool) -> float:
    base_score = score_asset(features)
    if not use_adjusted_score:
        return base_score

    overheat_penalty = max(features.get("ret_5d", 0.0) - 0.18, 0.0) * 140.0
    ma_extension_penalty = max(features.get("ma20_deviation", 0.0) - 0.20, 0.0) * 80.0
    volatility_penalty = max(features.get("volatility_20d", 0.0) - 0.06, 0.0) * 160.0
    drawdown_penalty = max(abs(min(features.get("max_drawdown_20d", 0.0), 0.0)) - 0.12, 0.0) * 60.0
    adjusted = (
        base_score
        - overheat_penalty
        - ma_extension_penalty
        - volatility_penalty
        - drawdown_penalty
    )
    return round(adjusted, 4)


def _passes_hard_entry_filters(features: dict[str, float]) -> bool:
    if features.get("ret_5d", 0.0) > 0.20:
        return False
    if features.get("ma20_deviation", 0.0) > 0.20:
        return False
    if features.get("volatility_20d", 0.0) > 0.08:
        return False
    if features.get("max_drawdown_20d", 0.0) < -0.15:
        return False
    return True


def _retention_exit_reason(
    position: dict[str, Any],
    selection: BacktestSelection | None,
    features: dict[str, float],
    config: RetentionConfig,
) -> str | None:
    if _position_stop_loss_triggered(position, config):
        return "exit_stop_loss"

    ma20_deviation = features.get("ma20_deviation")
    if config.ma20_exit and ma20_deviation is not None and ma20_deviation < 0:
        return "exit_ma20"

    if selection is None or selection.rank > config.observe_top_n:
        position["out_of_entry_count"] = config.exit_confirm_days
        if config.observe_top_n == config.entry_top_n:
            return "exit_top20"
        return "exit_observe_pool"

    if selection.rank <= config.entry_top_n:
        position["out_of_entry_count"] = 0
        return None

    out_count = int(position.get("out_of_entry_count") or 0) + 1
    position["out_of_entry_count"] = out_count
    if out_count >= config.exit_confirm_days:
        return "exit_confirmed_out_top20"
    return None


def _position_stop_loss_triggered(
    position: dict[str, Any],
    config: RetentionConfig,
) -> bool:
    if config.stop_loss_pct is None:
        return False
    trade = position.get("trade", {})
    buy_open = trade.get("buy_open")
    last_price = position.get("last_price")
    if _is_missing(buy_open) or _is_missing(last_price):
        return False
    return float(last_price) / float(buy_open) - 1.0 <= -float(config.stop_loss_pct)


def _bars_for_date(bar_frame: pd.DataFrame, trade_date: str) -> pd.DataFrame:
    if bar_frame.empty or "trade_date" not in bar_frame.columns:
        return pd.DataFrame()
    frame = bar_frame.copy()
    frame["trade_date"] = frame["trade_date"].map(_iso_date)
    return frame[frame["trade_date"] == _iso_date(trade_date)].reset_index(drop=True)


def _up_ratio(bar_frame: pd.DataFrame) -> float:
    if bar_frame.empty:
        return 0.0
    close = _numeric_series(bar_frame, "close")
    preclose = _numeric_series(bar_frame, "preclose")
    valid = close.notna() & preclose.notna() & (preclose > 0)
    if not valid.any():
        pct_chg = _numeric_series(bar_frame, "pct_chg").dropna()
        return float((pct_chg > 0).mean()) if not pct_chg.empty else 0.0
    return float((close[valid] > preclose[valid]).mean())


def _is_up_bar(row: dict[str, Any]) -> bool | None:
    pct_chg = _float_or_none(row.get("pct_chg"))
    if pct_chg is not None:
        return pct_chg > 0
    close = _float_or_none(row.get("close"))
    preclose = _float_or_none(row.get("preclose"))
    if close is None or preclose is None or preclose <= 0:
        return None
    return close > preclose


def _limit_stats(bar_frame: pd.DataFrame) -> dict[str, float]:
    pct_chg = _numeric_series(bar_frame, "pct_chg").dropna()
    if pct_chg.empty:
        return {
            "limit_up_count": 0.0,
            "limit_down_count": 0.0,
            "limit_up_down_ratio": 999.0,
        }
    limit_up_count = float((pct_chg >= 9.8).sum())
    limit_down_count = float((pct_chg <= -9.8).sum())
    return {
        "limit_up_count": limit_up_count,
        "limit_down_count": limit_down_count,
        "limit_up_down_ratio": (limit_up_count + 1.0) / (limit_down_count + 1.0),
    }


def _market_amount_ok(bar_frame: pd.DataFrame, trade_date: str) -> bool:
    if bar_frame.empty or "trade_date" not in bar_frame.columns:
        return True
    frame = bar_frame.copy()
    frame["trade_date"] = frame["trade_date"].map(_iso_date)
    daily = (
        frame[frame["trade_date"] <= _iso_date(trade_date)]
        .groupby("trade_date", as_index=False)["amount"]
        .sum()
        .sort_values("trade_date")
    )
    if daily.empty:
        return True
    current_amount = _float_or_zero(daily.iloc[-1]["amount"])
    history = pd.to_numeric(daily["amount"], errors="coerce").dropna().tail(20)
    if len(history) < 5:
        return True
    return current_amount >= float(history.mean()) * 0.75


def _numeric_series(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(dtype=float)
    return pd.to_numeric(frame[column], errors="coerce")


def _float_or_zero(value: object) -> float:
    if _is_missing(value):
        return 0.0
    return float(value)


def _board_key(asset_id: str) -> str:
    parts = asset_id.split(":")
    exchange = parts[1] if len(parts) > 1 else ""
    symbol = parts[2] if len(parts) > 2 else asset_id
    if exchange == "SH" and symbol.startswith("688"):
        return "STAR"
    if exchange == "SZ" and symbol.startswith(("300", "301", "302")):
        return "CHINEXT"
    if exchange == "BJ":
        return "BEIJING"
    return f"{exchange}_MAIN"


def _iso_date(value: object) -> str:
    return pd.Timestamp(value).date().isoformat()


def _is_missing(value: object) -> bool:
    return value is None or pd.isna(value)


def _float_or_none(value: object) -> float | None:
    if _is_missing(value):
        return None
    return float(value)


def _trading_dates(bar_frame: pd.DataFrame) -> list[str]:
    if bar_frame.empty:
        return []
    return sorted({_iso_date(value) for value in bar_frame["trade_date"]})


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


def _closed_holding_days(trades: pd.DataFrame, closed_mask: pd.Series) -> pd.Series:
    if trades.empty or "buy_date" not in trades.columns or "sell_date" not in trades.columns:
        return pd.Series(dtype=float)
    if len(closed_mask) != len(trades):
        return pd.Series(dtype=float)
    buy_dates = pd.to_datetime(trades.loc[closed_mask, "buy_date"], errors="coerce")
    sell_dates = pd.to_datetime(trades.loc[closed_mask, "sell_date"], errors="coerce")
    days = (sell_dates - buy_dates).dt.days.dropna()
    return days.astype(float)


def _cash_part(value: float) -> str:
    numeric = float(value)
    return str(int(numeric)) if numeric.is_integer() else f"{numeric:g}"


def _retention_strategy_id(
    start_date: object,
    end_date: object,
    max_positions: int,
    initial_cash: float,
    variant: str = "v1",
) -> str:
    prefix = "retention" if variant == "v1" else f"retention_{variant}"
    return (
        f"{prefix}:{_iso_date(start_date)}:{_iso_date(end_date)}:"
        f"top{max_positions}:cash{_cash_part(initial_cash)}"
    )


def _retention_report_stem(
    start_date: str,
    end_date: str,
    initial_cash: float,
    top_ks: tuple[int, ...],
    variant: str = "v1",
) -> str:
    top_part = "-".join(str(value) for value in top_ks)
    prefix = "retention" if variant == "v1" else f"retention_{variant}"
    return (
        f"{prefix}_{start_date}_{end_date}_cash{_cash_part(initial_cash)}"
        f"_top{top_part}"
    )


def _combined_equity_curve(results: list[RetentionResult]) -> pd.DataFrame:
    frames = []
    for result in results:
        frame = result.equity_curve.reindex(columns=RETENTION_EQUITY_COLUMNS)
        frame["max_positions"] = result.config.max_positions
        frames.append(frame)
    if not frames:
        return pd.DataFrame(columns=RETENTION_EQUITY_COLUMNS + ["max_positions"])
    return pd.concat(frames, ignore_index=True).reindex(
        columns=RETENTION_EQUITY_COLUMNS + ["max_positions"],
    )


def _combined_trades(results: list[RetentionResult]) -> pd.DataFrame:
    frames = [
        result.trades.reindex(columns=RETENTION_TRADE_COLUMNS)
        for result in results
    ]
    if not frames:
        return pd.DataFrame(columns=RETENTION_TRADE_COLUMNS)
    return pd.concat(frames, ignore_index=True).reindex(
        columns=RETENTION_TRADE_COLUMNS,
    )


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


def _bars_by_date_asset(bar_frame: pd.DataFrame) -> dict[tuple[str, str], dict[str, Any]]:
    indexed: dict[tuple[str, str], dict[str, Any]] = {}
    if bar_frame.empty:
        return indexed
    for row in bar_frame.to_dict("records"):
        trade_date = _iso_date(row["trade_date"])
        asset_id = str(row["asset_id"])
        indexed[(trade_date, asset_id)] = {
            "asset_id": asset_id,
            "trade_date": trade_date,
            "open": _float_or_none(row.get("open")),
            "preclose": _float_or_none(row.get("preclose")),
            "amount": _float_or_none(row.get("amount")),
            "trade_status": str(row.get("trade_status")),
            "is_st": _bool_value(row.get("is_st")),
            "is_suspended": _bool_value(row.get("is_suspended")),
            "is_limit_up": _bool_value(row.get("is_limit_up")),
            "is_limit_down": _bool_value(row.get("is_limit_down")),
        }
    return indexed


def _float_or_none(value: object) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)


def _is_tradable_open(bar: dict[str, Any] | None) -> bool:
    return (
        bar is not None
        and str(bar.get("trade_status")) == "1"
        and bar.get("open") is not None
        and not pd.isna(bar.get("open"))
    )
