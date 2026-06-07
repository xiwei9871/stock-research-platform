from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from stock_research.config import SETTINGS
from stock_research.mid_trend_rebalance_attribution import build_mid_trend_rebalance_attribution_from_frames
from stock_research.mid_trend_shadow_backtest import _load_prices
from stock_research.mid_trend_shadow_top10 import build_mid_trend_shadow_top10_from_frame
from stock_research.mid_trend_shadow_weekly_control import _simulate_variant
from stock_research.mid_trend_shadow_weekly_optimization import _prices_for_shadow


BASELINE_VARIANT = "top5_weekly_max_2_replacements"
CANDIDATE_VARIANT = "selective_trend_protection_score_gap_6"


def run_mid_trend_trend_protection_stability_review(
    *,
    funnel_detail_path: str | Path,
    start_date: str,
    end_date: str,
    output_dir: str | Path,
    protection_score_gap: float = 6.0,
    protection_mainline_gap: float = 0.05,
    protection_trend_r2_min: float = 75.0,
    protection_ret20_min: float = 65.0,
    protection_drawdown_min: float = 50.0,
    top_n: int = 5,
    max_weekly_replacements: int = 2,
    transaction_cost_bps: float = 20.0,
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
    return build_mid_trend_trend_protection_stability_review_from_frames(
        funnel_detail=funnel_detail,
        prices=prices,
        start_date=start_date,
        end_date=end_date,
        output_dir=output_dir,
        protection_score_gap=protection_score_gap,
        protection_mainline_gap=protection_mainline_gap,
        protection_trend_r2_min=protection_trend_r2_min,
        protection_ret20_min=protection_ret20_min,
        protection_drawdown_min=protection_drawdown_min,
        top_n=top_n,
        max_weekly_replacements=max_weekly_replacements,
        transaction_cost_bps=transaction_cost_bps,
        adjust_type=adjust_type,
    )


def build_mid_trend_trend_protection_stability_review_from_frames(
    *,
    funnel_detail: pd.DataFrame,
    prices: pd.DataFrame,
    start_date: str,
    end_date: str,
    output_dir: str | Path | None = None,
    protection_score_gap: float = 6.0,
    protection_mainline_gap: float = 0.05,
    protection_trend_r2_min: float = 75.0,
    protection_ret20_min: float = 65.0,
    protection_drawdown_min: float = 50.0,
    top_n: int = 5,
    max_weekly_replacements: int = 2,
    transaction_cost_bps: float = 20.0,
    adjust_type: str = "hfq",
) -> dict[str, Any]:
    primary_signals = build_mid_trend_shadow_top10_from_frame(funnel_detail, top_n=top_n)["top10"]
    buffer_signals = build_mid_trend_shadow_top10_from_frame(funnel_detail, top_n=max(top_n, 10))["top10"]
    scoped_prices = _prices_for_shadow(prices, pd.concat([primary_signals, buffer_signals], ignore_index=True))

    baseline = _simulate_variant(
        primary_signals,
        buffer_signals,
        scoped_prices,
        start_date=start_date,
        end_date=end_date,
        variant_name=BASELINE_VARIANT,
        top_n=top_n,
        buffer_rank=10,
        max_weekly_replacements=max_weekly_replacements,
        peak_drawdown_exit=0.12,
        transaction_cost_bps=transaction_cost_bps,
    )
    candidate = _simulate_variant(
        primary_signals,
        buffer_signals,
        scoped_prices,
        start_date=start_date,
        end_date=end_date,
        variant_name="top5_weekly_max2_selective_trend_holding_protection_v1",
        top_n=top_n,
        buffer_rank=10,
        max_weekly_replacements=max_weekly_replacements,
        peak_drawdown_exit=0.12,
        transaction_cost_bps=transaction_cost_bps,
        protection_score_gap=protection_score_gap,
        protection_mainline_gap=protection_mainline_gap,
        protection_trend_r2_min=protection_trend_r2_min,
        protection_ret20_min=protection_ret20_min,
        protection_drawdown_min=protection_drawdown_min,
    )
    candidate = _rename_result_variant(candidate, CANDIDATE_VARIANT)

    equity = pd.concat([baseline["equity_curve"], candidate["equity_curve"]], ignore_index=True)
    trades = pd.concat([baseline["trades"], candidate["trades"]], ignore_index=True)
    monthly = _period_summary(equity, trades, period_type="month")
    quarterly = _period_summary(equity, trades, period_type="quarter")

    baseline_attr = build_mid_trend_rebalance_attribution_from_frames(
        trades=trades,
        prices=scoped_prices,
        equity=equity,
        start_date=start_date,
        end_date=end_date,
        variant_name=BASELINE_VARIANT,
    )
    candidate_attr = build_mid_trend_rebalance_attribution_from_frames(
        trades=trades,
        prices=scoped_prices,
        equity=equity,
        start_date=start_date,
        end_date=end_date,
        variant_name=CANDIDATE_VARIANT,
    )
    attribution_summary = _combine_attribution_summary(baseline_attr["summary"], candidate_attr["summary"])
    attribution_detail = pd.concat(
        [
            _with_variant(baseline_attr["detail"], BASELINE_VARIANT),
            _with_variant(candidate_attr["detail"], CANDIDATE_VARIANT),
        ],
        ignore_index=True,
    )
    report = _render_report(monthly, quarterly, attribution_summary)
    result: dict[str, Any] = {
        "monthly": monthly,
        "quarterly": quarterly,
        "attribution_summary": attribution_summary,
        "attribution_detail": attribution_detail,
        "report": report,
        "paths": {},
    }
    if output_dir is not None:
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        paths = {
            "monthly": output / "mid_trend_trend_protection_monthly_stability.csv",
            "quarterly": output / "mid_trend_trend_protection_quarterly_stability.csv",
            "attribution_summary": output / "mid_trend_trend_protection_rebalance_attribution_summary.csv",
            "attribution_detail": output / "mid_trend_trend_protection_rebalance_attribution_detail.csv",
            "report": output / "mid_trend_trend_protection_stability_report.md",
        }
        monthly.to_csv(paths["monthly"], index=False)
        quarterly.to_csv(paths["quarterly"], index=False)
        attribution_summary.to_csv(paths["attribution_summary"], index=False)
        attribution_detail.to_csv(paths["attribution_detail"], index=False)
        paths["report"].write_text(report, encoding="utf-8")
        result["paths"] = {key: str(value) for key, value in paths.items()}
    return result


def _rename_result_variant(result: dict[str, Any], variant_name: str) -> dict[str, Any]:
    renamed = dict(result)
    for key in ["equity_curve", "positions", "trades"]:
        frame = renamed[key].copy()
        if not frame.empty and "variant_name" in frame.columns:
            frame["variant_name"] = variant_name
        renamed[key] = frame
    summary = dict(renamed["summary"])
    summary["variant_name"] = variant_name
    renamed["summary"] = summary
    return renamed


def _period_summary(equity: pd.DataFrame, trades: pd.DataFrame, *, period_type: str) -> pd.DataFrame:
    if equity.empty:
        return pd.DataFrame()
    frame = equity.copy()
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    frame["period"] = frame["date"].dt.to_period("M" if period_type == "month" else "Q").astype(str)
    trade_counts = _trade_counts_by_period(trades, period_type=period_type)
    rows = []
    for (variant_name, period), group in frame.groupby(["variant_name", "period"], sort=True):
        returns = pd.to_numeric(group["net_return"], errors="coerce").fillna(0.0)
        period_return = float((1.0 + returns).prod() - 1.0)
        equity_values = pd.to_numeric(group["equity"], errors="coerce")
        period_high = equity_values.cummax()
        period_drawdown = equity_values / period_high - 1.0
        turnover = pd.to_numeric(group["turnover"], errors="coerce")
        rows.append(
            {
                "period_type": period_type,
                "period": period,
                "variant_name": variant_name,
                "trading_days": int(len(group)),
                "period_return": period_return,
                "period_win_rate": float((returns > 0).mean()) if len(returns) else np.nan,
                "period_max_drawdown": float(period_drawdown.min()) if not period_drawdown.empty else np.nan,
                "avg_turnover": float(turnover.mean()) if not turnover.empty else np.nan,
                "trade_rows": int(trade_counts.get((variant_name, period), 0)),
            }
        )
    return pd.DataFrame(rows)


def _trade_counts_by_period(trades: pd.DataFrame, *, period_type: str) -> dict[tuple[str, str], int]:
    if trades.empty:
        return {}
    frame = trades.copy()
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="coerce")
    frame["period"] = frame["trade_date"].dt.to_period("M" if period_type == "month" else "Q").astype(str)
    grouped = frame.groupby(["variant_name", "period"]).size()
    return {(str(idx[0]), str(idx[1])): int(value) for idx, value in grouped.items()}


def _combine_attribution_summary(baseline: pd.DataFrame, candidate: pd.DataFrame) -> pd.DataFrame:
    return pd.concat(
        [
            _with_variant(baseline, BASELINE_VARIANT),
            _with_variant(candidate, CANDIDATE_VARIANT),
        ],
        ignore_index=True,
    )


def _with_variant(frame: pd.DataFrame, variant_name: str) -> pd.DataFrame:
    result = frame.copy()
    result.insert(0, "variant_name", variant_name)
    return result


def _render_report(monthly: pd.DataFrame, quarterly: pd.DataFrame, attribution_summary: pd.DataFrame) -> str:
    lines = [
        "# Mid Trend Selective Protection Stability Review",
        "",
        "## 1. Scope",
        "按月、按季度检查 score_gap=6 的选择性趋势持仓保护；只做历史诊断，不生成交易建议，不接实盘。",
        "",
        "## 2. Monthly Stability",
        monthly.to_markdown(index=False) if not monthly.empty else "No monthly rows.",
        "",
        "## 3. Quarterly Stability",
        quarterly.to_markdown(index=False) if not quarterly.empty else "No quarterly rows.",
        "",
        "## 4. Rebalance Attribution",
        attribution_summary.to_markdown(index=False) if not attribution_summary.empty else "No attribution rows.",
    ]
    return "\n".join(lines).rstrip() + "\n"
