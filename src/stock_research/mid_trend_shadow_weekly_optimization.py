from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from stock_research.config import SETTINGS
from stock_research.mid_trend_shadow_backtest import (
    _load_prices,
    build_mid_trend_shadow_backtest_from_frames,
)
from stock_research.mid_trend_shadow_top10 import build_mid_trend_shadow_top10_from_frame


DEFAULT_TOP_N_VALUES = [5, 8, 10, 12, 15]
DEFAULT_TRANSACTION_COST_BPS_VALUES = [10.0, 20.0, 30.0]
SUMMARY_COLUMNS = [
    "optimization_rank",
    "top_n",
    "transaction_cost_bps",
    "rebalance_frequency",
    "start_date",
    "end_date",
    "actual_start_date",
    "actual_end_date",
    "periods",
    "final_equity",
    "total_return",
    "annualized_return",
    "annualized_volatility",
    "sharpe_ratio",
    "max_drawdown",
    "calmar_ratio",
    "daily_win_rate",
    "average_turnover",
    "total_transaction_cost",
    "position_rows",
    "trade_rows",
    "diagnostic_note",
]


def run_mid_trend_shadow_weekly_optimization(
    *,
    funnel_detail_path: str | Path,
    start_date: str,
    end_date: str,
    output_dir: str | Path,
    top_n_values: list[int] | None = None,
    transaction_cost_bps_values: list[float] | None = None,
    adjust_type: str = "hfq",
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    funnel_detail = pd.read_csv(funnel_detail_path, low_memory=False)
    prices = _load_prices(
        start_date=start_date,
        end_date=end_date,
        adjust_type=adjust_type,
        service=service,
    )
    return build_mid_trend_shadow_weekly_optimization_from_frames(
        funnel_detail=funnel_detail,
        prices=prices,
        start_date=start_date,
        end_date=end_date,
        output_dir=output_dir,
        top_n_values=top_n_values,
        transaction_cost_bps_values=transaction_cost_bps_values,
        adjust_type=adjust_type,
    )


def build_mid_trend_shadow_weekly_optimization_from_frames(
    *,
    funnel_detail: pd.DataFrame,
    prices: pd.DataFrame,
    start_date: str,
    end_date: str,
    output_dir: str | Path | None = None,
    top_n_values: list[int] | None = None,
    transaction_cost_bps_values: list[float] | None = None,
    adjust_type: str = "hfq",
) -> dict[str, Any]:
    top_ns = _clean_top_n_values(top_n_values)
    costs = _clean_cost_values(transaction_cost_bps_values)
    if funnel_detail.empty or prices.empty:
        summary = pd.DataFrame(columns=SUMMARY_COLUMNS)
        best = _empty_backtest()
        report = _render_report(summary)
        return _result_with_optional_outputs(summary, best, report, output_dir)

    rows: list[dict[str, Any]] = []
    backtests: dict[tuple[int, float], dict[str, Any]] = {}

    for top_n in top_ns:
        shadow = build_mid_trend_shadow_top10_from_frame(funnel_detail, top_n=top_n)["top10"]
        scoped_prices = _prices_for_shadow(prices, shadow)
        for cost_bps in costs:
            backtest = build_mid_trend_shadow_backtest_from_frames(
                shadow_top10=shadow,
                prices=scoped_prices,
                start_date=start_date,
                end_date=end_date,
                top_n=top_n,
                rebalance_frequency="weekly",
                transaction_cost_bps=cost_bps,
                adjust_type=adjust_type,
            )
            row = _wide_summary_row(backtest["summary"])
            row["top_n"] = top_n
            row["transaction_cost_bps"] = float(cost_bps)
            row["rebalance_frequency"] = "weekly"
            row["diagnostic_note"] = "weekly shadow diagnostic only; no trading signal"
            rows.append(row)
            backtests[(top_n, float(cost_bps))] = backtest

    summary = _rank_summary(pd.DataFrame(rows))
    best_key = _best_key(summary)
    best = backtests.get(best_key, _empty_backtest())
    report = _render_report(summary)
    return _result_with_optional_outputs(summary, best, report, output_dir)


def _result_with_optional_outputs(
    summary: pd.DataFrame,
    best: dict[str, pd.DataFrame],
    report: str,
    output_dir: str | Path | None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "summary": summary,
        "best_equity_curve": best["equity_curve"],
        "best_positions": best["positions"],
        "best_trades": best["trades"],
        "report": report,
        "paths": {},
    }
    if output_dir is not None:
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        paths = {
            "summary": output / "mid_trend_shadow_weekly_optimization_summary.csv",
            "best_equity_curve": output / "mid_trend_shadow_weekly_optimization_best_equity.csv",
            "best_positions": output / "mid_trend_shadow_weekly_optimization_best_positions.csv",
            "best_trades": output / "mid_trend_shadow_weekly_optimization_best_trades.csv",
            "report": output / "mid_trend_shadow_weekly_optimization_report.md",
        }
        summary.to_csv(paths["summary"], index=False)
        best["equity_curve"].to_csv(paths["best_equity_curve"], index=False)
        best["positions"].to_csv(paths["best_positions"], index=False)
        best["trades"].to_csv(paths["best_trades"], index=False)
        paths["report"].write_text(report, encoding="utf-8")
        result["paths"] = {key: str(value) for key, value in paths.items()}
    return result


def _clean_top_n_values(values: list[int] | None) -> list[int]:
    raw = values or DEFAULT_TOP_N_VALUES
    cleaned = sorted({int(value) for value in raw if int(value) > 0})
    if not cleaned:
        raise ValueError("top_n_values must include at least one positive integer")
    return cleaned


def _prices_for_shadow(prices: pd.DataFrame, shadow: pd.DataFrame) -> pd.DataFrame:
    if prices.empty or shadow.empty or "asset_id" not in prices.columns or "asset_id" not in shadow.columns:
        return prices.head(0).copy()
    asset_ids = set(shadow["asset_id"].dropna().astype(str))
    return prices[prices["asset_id"].astype(str).isin(asset_ids)].copy()


def _clean_cost_values(values: list[float] | None) -> list[float]:
    raw = values or DEFAULT_TRANSACTION_COST_BPS_VALUES
    cleaned = sorted({float(value) for value in raw if float(value) >= 0.0})
    if not cleaned:
        raise ValueError("transaction_cost_bps_values must include at least one non-negative number")
    return cleaned


def _wide_summary_row(summary: pd.DataFrame) -> dict[str, Any]:
    if summary.empty:
        return {}
    row = summary.set_index("metric")["value"].to_dict()
    return {key: row.get(key, np.nan) for key in SUMMARY_COLUMNS if key not in {"optimization_rank", "diagnostic_note"}}


def _rank_summary(summary: pd.DataFrame) -> pd.DataFrame:
    if summary.empty:
        return pd.DataFrame(columns=SUMMARY_COLUMNS)
    ranked = summary.copy()
    for column in [
        "total_return",
        "annualized_return",
        "annualized_volatility",
        "sharpe_ratio",
        "max_drawdown",
        "calmar_ratio",
        "daily_win_rate",
        "average_turnover",
        "total_transaction_cost",
    ]:
        if column not in ranked.columns:
            ranked[column] = np.nan
        ranked[column] = pd.to_numeric(ranked[column], errors="coerce")
    ranked = ranked.sort_values(
        ["sharpe_ratio", "calmar_ratio", "total_return", "max_drawdown", "average_turnover"],
        ascending=[False, False, False, False, True],
        na_position="last",
    ).reset_index(drop=True)
    ranked.insert(0, "optimization_rank", range(1, len(ranked) + 1))
    return _ensure_columns(ranked, SUMMARY_COLUMNS)


def _best_key(summary: pd.DataFrame) -> tuple[int, float] | None:
    if summary.empty:
        return None
    first = summary.iloc[0]
    return int(first["top_n"]), float(first["transaction_cost_bps"])


def _empty_backtest() -> dict[str, pd.DataFrame]:
    return {
        "equity_curve": pd.DataFrame(),
        "positions": pd.DataFrame(),
        "trades": pd.DataFrame(),
    }


def _ensure_columns(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    result = frame.copy()
    for column in columns:
        if column not in result.columns:
            result[column] = np.nan
    return result[columns]


def _render_report(summary: pd.DataFrame) -> str:
    lines = [
        "# Mid Trend Shadow Weekly Optimization",
        "",
        "## 1. Scope",
        "周频 shadow TopN 历史组合诊断，用于降低日频换手和交易成本影响；不生成交易建议，不接实盘。",
        "",
        "## 2. Optimization Grid",
        summary.to_markdown(index=False) if not summary.empty else "No optimization rows.",
        "",
        "## 3. Decision Guardrail",
        "优先看 Sharpe / Calmar / 回撤 / 换手的综合平衡；本报告只用于 shadow 观察池规则复盘。",
    ]
    return "\n".join(lines).rstrip() + "\n"
