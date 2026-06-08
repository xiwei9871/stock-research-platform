from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all


DEFAULT_TOP_N_VALUES = [5, 8, 10]
DEFAULT_REBALANCE_FREQUENCIES = ["monthly", "biweekly", "weekly"]
DEFAULT_PROTECTION_CONFIGS = [
    {"name": "atr_rank_2p5_rank20_1d", "atr_mult": 2.5, "rank_break": 20, "confirm_days": 1},
    {"name": "atr_rank_3p0_rank30_1d", "atr_mult": 3.0, "rank_break": 30, "confirm_days": 1},
    {"name": "rank_exit_top10_1d", "rank_exit": 10, "confirm_days": 1},
    {"name": "rank_exit_top15_2d", "rank_exit": 15, "confirm_days": 2},
    {"name": "ma60_rank20_1d", "ma_window": 60, "rank_break": 20, "confirm_days": 1},
]

SUMMARY_COLUMNS = [
    "universe",
    "frequency",
    "top_n",
    "protection_name",
    "atr_mult",
    "rank_break",
    "rank_exit",
    "ma_window",
    "confirm_days",
    "start_date",
    "end_date",
    "days",
    "total_return",
    "annualized_return",
    "annualized_volatility",
    "sharpe",
    "max_drawdown",
    "calmar",
    "avg_actual_exposure",
    "avg_holdings",
    "turnover_avg",
    "transaction_cost_sum",
    "c2_trigger_count",
]


@dataclass(frozen=True)
class ProtectionConfig:
    name: str
    atr_mult: float | None = None
    rank_break: int | None = None
    rank_exit: int | None = None
    ma_window: int | None = None
    confirm_days: int = 1


def run_serenity_tight3b_c2_experiment(
    *,
    candidates_path: str | Path,
    market_exposure_path: str | Path,
    start_date: str,
    end_date: str,
    output_dir: str | Path,
    universe_name: str = "strict_153",
    top_n_values: list[int] | None = None,
    rebalance_frequencies: list[str] | None = None,
    transaction_cost_bps: float = 20.0,
    adjust_type: str = "hfq",
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    candidates = pd.read_csv(candidates_path, low_memory=False)
    market_exposure = pd.read_csv(market_exposure_path, low_memory=False)
    prices = _load_prices(
        start_date=start_date,
        end_date=end_date,
        adjust_type=adjust_type,
        service=service,
    )
    return build_serenity_tight3b_c2_experiment_from_frames(
        candidates=candidates,
        prices=prices,
        market_exposure=market_exposure,
        start_date=start_date,
        end_date=end_date,
        output_dir=output_dir,
        universe_name=universe_name,
        top_n_values=top_n_values,
        rebalance_frequencies=rebalance_frequencies,
        transaction_cost_bps=transaction_cost_bps,
        adjust_type=adjust_type,
    )


def build_serenity_tight3b_c2_experiment_from_frames(
    *,
    candidates: pd.DataFrame,
    prices: pd.DataFrame,
    market_exposure: pd.DataFrame,
    start_date: str,
    end_date: str,
    output_dir: str | Path | None = None,
    universe_name: str = "strict_153",
    top_n_values: list[int] | None = None,
    rebalance_frequencies: list[str] | None = None,
    protection_configs: list[dict[str, Any]] | None = None,
    transaction_cost_bps: float = 20.0,
    adjust_type: str = "hfq",
) -> dict[str, Any]:
    top_ns = _clean_top_n_values(top_n_values)
    frequencies = _clean_frequencies(rebalance_frequencies)
    protections = _clean_protection_configs(protection_configs)
    normalized_prices = _normalize_prices(prices, start_date=start_date, end_date=end_date)
    normalized_candidates = _normalize_candidates(candidates)
    normalized_exposure = _normalize_market_exposure(market_exposure)
    ranks = _build_daily_bottleneck_ranks(
        candidates=normalized_candidates,
        prices=normalized_prices,
        start_date=start_date,
        end_date=end_date,
    )

    all_summary: list[pd.DataFrame] = []
    all_equity: list[pd.DataFrame] = []
    all_positions: list[pd.DataFrame] = []
    all_trades: list[pd.DataFrame] = []
    runs: dict[tuple[str, int, str], dict[str, pd.DataFrame]] = {}

    for frequency in frequencies:
        for top_n in top_ns:
            for protection in protections:
                run = _simulate_one_config(
                    ranks=ranks,
                    prices=normalized_prices,
                    market_exposure=normalized_exposure,
                    start_date=start_date,
                    end_date=end_date,
                    universe_name=universe_name,
                    frequency=frequency,
                    top_n=top_n,
                    protection=protection,
                    transaction_cost_bps=transaction_cost_bps,
                )
                all_summary.append(run["summary"])
                all_equity.append(run["equity"])
                all_positions.append(run["positions"])
                all_trades.append(run["trades"])
                runs[(frequency, top_n, protection.name)] = run

    summary = _rank_summary(_concat(all_summary, SUMMARY_COLUMNS))
    equity = _concat(all_equity)
    positions = _concat(all_positions)
    trades = _concat(all_trades)
    report = _render_report(summary)
    best = _best_run(summary, runs)
    universe = _render_universe_definitions(normalized_candidates)

    result: dict[str, Any] = {
        "summary": summary,
        "equity": equity,
        "positions": positions,
        "trades": trades,
        "best_equity": best.get("equity", pd.DataFrame()),
        "best_positions": best.get("positions", pd.DataFrame()),
        "best_trades": best.get("trades", pd.DataFrame()),
        "universe_definitions": universe,
        "report": report,
        "paths": {},
    }
    if output_dir is not None:
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        paths = {
            "summary": output / "serenity_tight3b_c2_matrix_summary.csv",
            "equity": output / "serenity_tight3b_c2_equity.csv",
            "positions": output / "serenity_tight3b_c2_positions.csv",
            "trades": output / "serenity_tight3b_c2_trades.csv",
            "best_equity": output / "serenity_tight3b_c2_best_equity.csv",
            "best_positions": output / "serenity_tight3b_c2_best_positions.csv",
            "best_trades": output / "serenity_tight3b_c2_best_trades.csv",
            "universe_definitions": output / "serenity_universe_definitions.csv",
            "report": output / "summary.md",
        }
        summary.to_csv(paths["summary"], index=False)
        equity.to_csv(paths["equity"], index=False)
        positions.to_csv(paths["positions"], index=False)
        trades.to_csv(paths["trades"], index=False)
        result["best_equity"].to_csv(paths["best_equity"], index=False)
        result["best_positions"].to_csv(paths["best_positions"], index=False)
        result["best_trades"].to_csv(paths["best_trades"], index=False)
        universe.to_csv(paths["universe_definitions"], index=False)
        paths["report"].write_text(report, encoding="utf-8")
        result["paths"] = {key: str(value) for key, value in paths.items()}
    return result


def _simulate_one_config(
    *,
    ranks: pd.DataFrame,
    prices: pd.DataFrame,
    market_exposure: pd.DataFrame,
    start_date: str,
    end_date: str,
    universe_name: str,
    frequency: str,
    top_n: int,
    protection: ProtectionConfig,
    transaction_cost_bps: float,
) -> dict[str, pd.DataFrame]:
    trading_dates = _trading_dates(prices, start_date, end_date)
    if len(trading_dates) < 2:
        empty_summary = _summary_frame(
            universe_name=universe_name,
            frequency=frequency,
            top_n=top_n,
            protection=protection,
            start_date=start_date,
            end_date=end_date,
            equity=pd.DataFrame(),
            positions=pd.DataFrame(),
            trades=pd.DataFrame(),
        )
        return {"summary": empty_summary, "equity": pd.DataFrame(), "positions": pd.DataFrame(), "trades": pd.DataFrame()}

    closes = prices.pivot(index="trade_date", columns="asset_id", values="close").sort_index()
    highs = prices.pivot(index="trade_date", columns="asset_id", values="high").sort_index()
    lows = prices.pivot(index="trade_date", columns="asset_id", values="low").sort_index()
    atr = _average_true_range(highs, lows, closes)
    ma = closes.rolling(60, min_periods=3).mean()
    returns = closes.pct_change().fillna(0.0)
    rank_by_date = {date: day.set_index("asset_id") for date, day in ranks.groupby("trade_date")}
    exposure_by_date = market_exposure.set_index("trade_date")["target_exposure"].to_dict()
    rebalance_dates = set(_rebalance_dates(trading_dates[:-1], frequency))

    equity = 1.0
    peak_equity = 1.0
    weights: dict[str, float] = {}
    entry_high: dict[str, float] = {}
    violation_counts: dict[str, int] = {}
    equity_rows: list[dict[str, Any]] = []
    position_rows: list[dict[str, Any]] = []
    trade_rows: list[dict[str, Any]] = []

    for i, trade_date in enumerate(trading_dates[:-1]):
        next_date = trading_dates[i + 1]
        day_ranks = rank_by_date.get(trade_date, pd.DataFrame())
        target = dict(weights)
        triggered: list[tuple[str, str]] = []

        if trade_date in rebalance_dates:
            selected = _selected_for_day(day_ranks, top_n)
            exposure = float(exposure_by_date.get(trade_date, 1.0))
            selected_assets = selected["asset_id"].astype(str).tolist() if not selected.empty else []
            weight = exposure / len(selected_assets) if selected_assets else 0.0
            target = {asset_id: weight for asset_id in selected_assets}
            for asset_id in selected_assets:
                entry_high[asset_id] = max(
                    float(closes.at[trade_date, asset_id]) if asset_id in closes.columns else 0.0,
                    float(entry_high.get(asset_id, 0.0)),
                )

        for asset_id in list(target):
            if asset_id in closes.columns:
                entry_high[asset_id] = max(
                    float(entry_high.get(asset_id, 0.0)),
                    float(closes.at[trade_date, asset_id]),
                )
            should_exit, reason = _protection_triggered(
                asset_id=asset_id,
                trade_date=trade_date,
                day_ranks=day_ranks,
                closes=closes,
                atr=atr,
                ma=ma,
                entry_high=entry_high,
                protection=protection,
            )
            if should_exit:
                violation_counts[asset_id] = int(violation_counts.get(asset_id, 0)) + 1
            else:
                violation_counts[asset_id] = 0
            if violation_counts[asset_id] >= protection.confirm_days:
                target.pop(asset_id, None)
                triggered.append((asset_id, reason))
                violation_counts[asset_id] = 0

        turnover = float(sum(abs(target.get(asset_id, 0.0) - weights.get(asset_id, 0.0)) for asset_id in set(target) | set(weights)))
        transaction_cost = turnover * transaction_cost_bps / 10000.0
        for asset_id in sorted(set(target) | set(weights)):
            previous_weight = float(weights.get(asset_id, 0.0))
            target_weight = float(target.get(asset_id, 0.0))
            if abs(previous_weight - target_weight) > 1e-12:
                trade_rows.append(
                    _trade_row(
                        trade_date=trade_date,
                        asset_id=asset_id,
                        side="buy" if target_weight > previous_weight else "sell",
                        reason=_trade_reason(asset_id, triggered, trade_date in rebalance_dates),
                        previous_weight=previous_weight,
                        target_weight=target_weight,
                        turnover=abs(target_weight - previous_weight),
                        transaction_cost=abs(target_weight - previous_weight) * transaction_cost_bps / 10000.0,
                        universe_name=universe_name,
                        frequency=frequency,
                        top_n=top_n,
                        protection=protection,
                    )
                )

        weights = target
        daily_gross_return = float(
            sum(float(weight) * float(returns.at[next_date, asset_id]) for asset_id, weight in weights.items() if asset_id in returns.columns)
        )
        net_return = daily_gross_return - transaction_cost
        equity *= 1.0 + net_return
        peak_equity = max(peak_equity, equity)
        equity_rows.append(
            {
                "trade_date": next_date,
                "universe": universe_name,
                "frequency": frequency,
                "top_n": top_n,
                **_protection_fields(protection),
                "gross_return": daily_gross_return,
                "turnover": turnover,
                "transaction_cost": transaction_cost,
                "net_return": net_return,
                "equity": equity,
                "drawdown": equity / peak_equity - 1.0 if peak_equity else 0.0,
                "actual_exposure": sum(weights.values()),
                "holdings_count": len(weights),
            }
        )
        for asset_id, weight in sorted(weights.items()):
            rank_value = _rank_for_asset(day_ranks, asset_id)
            score_value = _score_for_asset(day_ranks, asset_id)
            position_rows.append(
                {
                    "trade_date": trade_date,
                    "universe": universe_name,
                    "frequency": frequency,
                    "top_n": top_n,
                    **_protection_fields(protection),
                    "asset_id": asset_id,
                    "weight": weight,
                    "bottleneck_rank": rank_value,
                    "bottleneck_score": score_value,
                }
            )

    equity_frame = pd.DataFrame(equity_rows)
    positions = pd.DataFrame(position_rows)
    trades = pd.DataFrame(trade_rows)
    summary = _summary_frame(
        universe_name=universe_name,
        frequency=frequency,
        top_n=top_n,
        protection=protection,
        start_date=start_date,
        end_date=end_date,
        equity=equity_frame,
        positions=positions,
        trades=trades,
    )
    return {"summary": summary, "equity": equity_frame, "positions": positions, "trades": trades}


def _normalize_candidates(candidates: pd.DataFrame) -> pd.DataFrame:
    if candidates.empty:
        return pd.DataFrame(columns=["asset_id", "stock_name", "first_hit_date", "hit_count"])
    frame = candidates.copy()
    frame["asset_id"] = frame["asset_id"].astype(str)
    frame["first_hit_date"] = pd.to_datetime(frame["first_hit_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    frame["hit_count"] = pd.to_numeric(frame.get("hit_count", 1), errors="coerce").fillna(1)
    for column in ["stock_name", "primary_chain_id", "primary_chain_name"]:
        if column not in frame.columns:
            frame[column] = ""
    return frame.dropna(subset=["asset_id", "first_hit_date"])


def _normalize_prices(prices: pd.DataFrame, *, start_date: str, end_date: str) -> pd.DataFrame:
    if prices.empty:
        return pd.DataFrame(columns=["trade_date", "asset_id", "open", "high", "low", "close"])
    frame = prices.copy()
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    frame["asset_id"] = frame["asset_id"].astype(str)
    for column in ["open", "close"]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    if "high" not in frame.columns:
        frame["high"] = frame[["open", "close"]].max(axis=1)
    if "low" not in frame.columns:
        frame["low"] = frame[["open", "close"]].min(axis=1)
    frame["high"] = pd.to_numeric(frame["high"], errors="coerce")
    frame["low"] = pd.to_numeric(frame["low"], errors="coerce")
    frame = frame[(frame["trade_date"] >= start_date) & (frame["trade_date"] <= end_date)]
    return frame.dropna(subset=["trade_date", "asset_id", "close"]).sort_values(["trade_date", "asset_id"])


def _normalize_market_exposure(market_exposure: pd.DataFrame) -> pd.DataFrame:
    frame = market_exposure.copy()
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    frame["target_exposure"] = pd.to_numeric(frame["target_exposure"], errors="coerce").fillna(1.0)
    return frame[["trade_date", "target_exposure"]].dropna(subset=["trade_date"])


def _build_daily_bottleneck_ranks(
    *,
    candidates: pd.DataFrame,
    prices: pd.DataFrame,
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    trading_dates = _trading_dates(prices, start_date, end_date)
    closes = prices.pivot(index="trade_date", columns="asset_id", values="close").sort_index()
    high_120 = closes.rolling(120, min_periods=3).max()
    rows: list[dict[str, Any]] = []
    max_evidence = float(np.log1p(pd.to_numeric(candidates["hit_count"], errors="coerce").fillna(1)).max()) if not candidates.empty else 1.0
    max_evidence = max(max_evidence, 1.0)
    for trade_date in trading_dates:
        eligible = candidates[candidates["first_hit_date"] <= trade_date]
        for row in eligible.itertuples(index=False):
            asset_id = str(row.asset_id)
            evidence_norm = float(np.log1p(float(row.hit_count)) / max_evidence)
            age_days = max((pd.Timestamp(trade_date) - pd.Timestamp(row.first_hit_date)).days, 0)
            freshness = max(0.0, 1.0 - age_days / 240.0)
            low_position = 0.5
            if asset_id in closes.columns and trade_date in closes.index:
                close = closes.at[trade_date, asset_id]
                rolling_high = high_120.at[trade_date, asset_id] if asset_id in high_120.columns else np.nan
                if pd.notna(close) and pd.notna(rolling_high) and rolling_high > 0:
                    low_position = float(max(0.0, min(1.0, 1.0 - close / rolling_high)))
            score = 0.45 * evidence_norm + 0.25 * freshness + 0.30 * low_position
            rows.append(
                {
                    "trade_date": trade_date,
                    "asset_id": asset_id,
                    "stock_name": getattr(row, "stock_name", ""),
                    "primary_chain_id": getattr(row, "primary_chain_id", ""),
                    "primary_chain_name": getattr(row, "primary_chain_name", ""),
                    "first_hit_date": row.first_hit_date,
                    "hit_count": float(row.hit_count),
                    "bottleneck_score": score,
                }
            )
    frame = pd.DataFrame(rows)
    if frame.empty:
        return pd.DataFrame(columns=["trade_date", "asset_id", "bottleneck_rank", "bottleneck_score"])
    frame = frame.sort_values(["trade_date", "bottleneck_score", "hit_count", "asset_id"], ascending=[True, False, False, True])
    frame["bottleneck_rank"] = frame.groupby("trade_date").cumcount() + 1
    return frame


def _selected_for_day(day_ranks: pd.DataFrame, top_n: int) -> pd.DataFrame:
    if day_ranks.empty:
        return pd.DataFrame(columns=["asset_id", "bottleneck_rank", "bottleneck_score"])
    selected = day_ranks.reset_index()
    selected = selected[pd.to_numeric(selected["bottleneck_rank"], errors="coerce") <= top_n]
    return selected.sort_values("bottleneck_rank")


def _protection_triggered(
    *,
    asset_id: str,
    trade_date: str,
    day_ranks: pd.DataFrame,
    closes: pd.DataFrame,
    atr: pd.DataFrame,
    ma: pd.DataFrame,
    entry_high: dict[str, float],
    protection: ProtectionConfig,
) -> tuple[bool, str]:
    rank = _rank_for_asset(day_ranks, asset_id)
    close = float(closes.at[trade_date, asset_id]) if asset_id in closes.columns and trade_date in closes.index else np.nan
    if protection.rank_exit is not None and pd.notna(rank) and rank > protection.rank_exit:
        return True, f"C2_rank_exit_{protection.rank_exit}"
    if protection.atr_mult is not None and protection.rank_break is not None:
        current_atr = float(atr.at[trade_date, asset_id]) if asset_id in atr.columns and trade_date in atr.index else np.nan
        stop = float(entry_high.get(asset_id, close)) - float(protection.atr_mult) * current_atr
        if pd.notna(close) and pd.notna(stop) and pd.notna(rank) and close < stop and rank > protection.rank_break:
            return True, f"C2_ATR{protection.atr_mult}_rank{protection.rank_break}"
    if protection.ma_window is not None and protection.rank_break is not None:
        moving_average = float(ma.at[trade_date, asset_id]) if asset_id in ma.columns and trade_date in ma.index else np.nan
        if pd.notna(close) and pd.notna(moving_average) and pd.notna(rank) and close < moving_average and rank > protection.rank_break:
            return True, f"C2_MA{protection.ma_window}_rank{protection.rank_break}"
    return False, ""


def _average_true_range(highs: pd.DataFrame, lows: pd.DataFrame, closes: pd.DataFrame, window: int = 14) -> pd.DataFrame:
    previous_close = closes.shift(1)
    true_range = pd.concat(
        [
            highs.sub(lows).stack(),
            highs.sub(previous_close).abs().stack(),
            lows.sub(previous_close).abs().stack(),
        ],
        axis=1,
    ).max(axis=1).unstack()
    return true_range.rolling(window, min_periods=3).mean()


def _trading_dates(prices: pd.DataFrame, start_date: str, end_date: str) -> list[str]:
    if prices.empty:
        return []
    dates = sorted(prices["trade_date"].dropna().astype(str).unique())
    return [date for date in dates if start_date <= date <= end_date]


def _rebalance_dates(trading_dates: list[str], frequency: str) -> list[str]:
    if frequency == "weekly":
        period = pd.to_datetime(pd.Series(trading_dates)).dt.to_period("W-FRI")
    elif frequency == "biweekly":
        weekly = pd.to_datetime(pd.Series(trading_dates)).dt.isocalendar().week.astype(int)
        period = pd.to_datetime(pd.Series(trading_dates)).dt.year.astype(str) + "-" + ((weekly - 1) // 2).astype(str)
    elif frequency == "monthly":
        period = pd.to_datetime(pd.Series(trading_dates)).dt.to_period("M")
    else:
        raise ValueError("rebalance frequency must be weekly, biweekly, or monthly")
    frame = pd.DataFrame({"trade_date": trading_dates, "period": period.astype(str)})
    return frame.groupby("period")["trade_date"].first().tolist()


def _summary_frame(
    *,
    universe_name: str,
    frequency: str,
    top_n: int,
    protection: ProtectionConfig,
    start_date: str,
    end_date: str,
    equity: pd.DataFrame,
    positions: pd.DataFrame,
    trades: pd.DataFrame,
) -> pd.DataFrame:
    if equity.empty:
        metrics = {
            "days": 0,
            "total_return": 0.0,
            "annualized_return": 0.0,
            "annualized_volatility": np.nan,
            "sharpe": np.nan,
            "max_drawdown": 0.0,
            "calmar": np.nan,
            "avg_actual_exposure": 0.0,
            "avg_holdings": 0.0,
            "turnover_avg": 0.0,
            "transaction_cost_sum": 0.0,
            "c2_trigger_count": 0,
        }
    else:
        returns = pd.to_numeric(equity["net_return"], errors="coerce").fillna(0.0)
        days = len(equity)
        total_return = float(equity.iloc[-1]["equity"]) - 1.0
        annualized_return = (1.0 + total_return) ** (252.0 / days) - 1.0 if days and total_return > -1.0 else np.nan
        volatility = float(returns.std(ddof=1) * np.sqrt(252.0)) if len(returns) > 1 else np.nan
        sharpe = float(returns.mean() / returns.std(ddof=1) * np.sqrt(252.0)) if len(returns) > 1 and returns.std(ddof=1) else np.nan
        max_drawdown = float(pd.to_numeric(equity["drawdown"], errors="coerce").min())
        metrics = {
            "days": days,
            "total_return": total_return,
            "annualized_return": annualized_return,
            "annualized_volatility": volatility,
            "sharpe": sharpe,
            "max_drawdown": max_drawdown,
            "calmar": annualized_return / abs(max_drawdown) if max_drawdown < 0 else np.nan,
            "avg_actual_exposure": float(pd.to_numeric(equity["actual_exposure"], errors="coerce").mean()),
            "avg_holdings": float(pd.to_numeric(equity["holdings_count"], errors="coerce").mean()),
            "turnover_avg": float(pd.to_numeric(equity["turnover"], errors="coerce").mean()),
            "transaction_cost_sum": float(pd.to_numeric(equity["transaction_cost"], errors="coerce").sum()),
            "c2_trigger_count": int(trades["reason"].astype(str).str.startswith("C2_").sum()) if not trades.empty else 0,
        }
    row = {
        "universe": universe_name,
        "frequency": frequency,
        "top_n": top_n,
        **_protection_fields(protection),
        "start_date": start_date,
        "end_date": end_date,
        **metrics,
    }
    return pd.DataFrame([row], columns=SUMMARY_COLUMNS)


def _rank_summary(summary: pd.DataFrame) -> pd.DataFrame:
    if summary.empty:
        return pd.DataFrame(columns=SUMMARY_COLUMNS)
    ranked = summary.copy()
    ranked = ranked.sort_values(
        ["calmar", "sharpe", "total_return", "max_drawdown", "turnover_avg"],
        ascending=[False, False, False, False, True],
        na_position="last",
    ).reset_index(drop=True)
    return ranked[SUMMARY_COLUMNS]


def _best_run(summary: pd.DataFrame, runs: dict[tuple[str, int, str], dict[str, pd.DataFrame]]) -> dict[str, pd.DataFrame]:
    if summary.empty:
        return {}
    row = summary.iloc[0]
    return runs.get((str(row["frequency"]), int(row["top_n"]), str(row["protection_name"])), {})


def _protection_fields(protection: ProtectionConfig) -> dict[str, Any]:
    return {
        "protection_name": protection.name,
        "atr_mult": protection.atr_mult,
        "rank_break": protection.rank_break,
        "rank_exit": protection.rank_exit,
        "ma_window": protection.ma_window,
        "confirm_days": protection.confirm_days,
    }


def _trade_row(
    *,
    trade_date: str,
    asset_id: str,
    side: str,
    reason: str,
    previous_weight: float,
    target_weight: float,
    turnover: float,
    transaction_cost: float,
    universe_name: str,
    frequency: str,
    top_n: int,
    protection: ProtectionConfig,
) -> dict[str, Any]:
    return {
        "trade_date": trade_date,
        "universe": universe_name,
        "frequency": frequency,
        "top_n": top_n,
        **_protection_fields(protection),
        "asset_id": asset_id,
        "side": side,
        "reason": reason,
        "previous_weight": previous_weight,
        "target_weight": target_weight,
        "turnover_contribution": turnover,
        "transaction_cost": transaction_cost,
    }


def _trade_reason(asset_id: str, triggered: list[tuple[str, str]], is_rebalance: bool) -> str:
    for trigger_asset_id, reason in triggered:
        if trigger_asset_id == asset_id:
            return reason
    return "rebalance" if is_rebalance else "weight_adjust"


def _rank_for_asset(day_ranks: pd.DataFrame, asset_id: str) -> float:
    if day_ranks.empty or asset_id not in day_ranks.index:
        return np.nan
    return float(day_ranks.at[asset_id, "bottleneck_rank"])


def _score_for_asset(day_ranks: pd.DataFrame, asset_id: str) -> float:
    if day_ranks.empty or asset_id not in day_ranks.index:
        return np.nan
    return float(day_ranks.at[asset_id, "bottleneck_score"])


def _render_universe_definitions(candidates: pd.DataFrame) -> pd.DataFrame:
    columns = ["asset_id", "stock_name", "first_hit_date", "hit_count", "primary_chain_id", "primary_chain_name"]
    if candidates.empty:
        return pd.DataFrame(columns=columns)
    return candidates[[column for column in columns if column in candidates.columns]].drop_duplicates("asset_id")


def _concat(frames: list[pd.DataFrame], columns: list[str] | None = None) -> pd.DataFrame:
    non_empty = [frame for frame in frames if frame is not None and not frame.empty]
    if not non_empty:
        return pd.DataFrame(columns=columns or [])
    return pd.concat(non_empty, ignore_index=True)


def _clean_top_n_values(values: list[int] | None) -> list[int]:
    raw = values or DEFAULT_TOP_N_VALUES
    cleaned = sorted({int(value) for value in raw if int(value) > 0})
    if not cleaned:
        raise ValueError("top_n_values must include at least one positive integer")
    return cleaned


def _clean_frequencies(values: list[str] | None) -> list[str]:
    raw = values or DEFAULT_REBALANCE_FREQUENCIES
    allowed = {"weekly", "biweekly", "monthly"}
    cleaned = [str(value).strip() for value in raw if str(value).strip()]
    invalid = sorted(set(cleaned) - allowed)
    if invalid:
        raise ValueError(f"unsupported rebalance frequencies: {', '.join(invalid)}")
    return list(dict.fromkeys(cleaned))


def _clean_protection_configs(values: list[dict[str, Any]] | None) -> list[ProtectionConfig]:
    raw = values or DEFAULT_PROTECTION_CONFIGS
    configs = []
    for item in raw:
        configs.append(
            ProtectionConfig(
                name=str(item.get("name") or _default_protection_name(item)),
                atr_mult=_optional_float(item.get("atr_mult")),
                rank_break=_optional_int(item.get("rank_break")),
                rank_exit=_optional_int(item.get("rank_exit")),
                ma_window=_optional_int(item.get("ma_window")),
                confirm_days=max(1, int(item.get("confirm_days", 1))),
            )
        )
    return configs


def _default_protection_name(item: dict[str, Any]) -> str:
    if item.get("rank_exit") is not None:
        return f"rank_exit_{item['rank_exit']}_{item.get('confirm_days', 1)}d"
    if item.get("ma_window") is not None:
        return f"ma{item['ma_window']}_rank{item.get('rank_break', 'na')}_{item.get('confirm_days', 1)}d"
    return f"atr{item.get('atr_mult', 'na')}_rank{item.get('rank_break', 'na')}_{item.get('confirm_days', 1)}d"


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _render_report(summary: pd.DataFrame) -> str:
    lines = [
        "# Serenity Bottleneck + tight3b_bt100 + C2 Experiment",
        "",
        "## Scope",
        "- selection: tech bottleneck discovery only",
        "- market exposure: tight3b_bt100 target_exposure",
        "- protection: C2 rank/ATR/MA exits over bottleneck ranks",
        "",
        "## Top Results",
        summary.head(20).to_markdown(index=False) if not summary.empty else "No results.",
        "",
        "## Files",
        "- serenity_tight3b_c2_matrix_summary.csv",
        "- serenity_tight3b_c2_equity.csv",
        "- serenity_tight3b_c2_positions.csv",
        "- serenity_tight3b_c2_trades.csv",
        "- serenity_tight3b_c2_best_equity.csv",
        "- serenity_tight3b_c2_best_positions.csv",
        "- serenity_tight3b_c2_best_trades.csv",
        "- serenity_universe_definitions.csv",
    ]
    return "\n".join(lines).rstrip() + "\n"


def _load_prices(
    *,
    start_date: str,
    end_date: str,
    adjust_type: str,
    service: str,
) -> pd.DataFrame:
    sql = """
        SELECT
            trade_date,
            asset_id,
            open,
            high,
            low,
            close,
            amount,
            trade_status,
            false AS is_limit_up,
            false AS is_limit_down,
            false AS is_suspended
        FROM market_daily_bar
        WHERE adjust_type = %s
          AND trade_date BETWEEN %s AND %s
        ORDER BY trade_date, asset_id
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, [adjust_type, start_date, end_date])
    return pd.DataFrame(rows)
