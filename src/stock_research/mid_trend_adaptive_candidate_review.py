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
from stock_research.mid_trend_trend_protection_stability import _period_summary


BASELINE_VARIANT = "top5_weekly_max_2_replacements"
CANDIDATE_VARIANT = "top5_adaptive_daily_check_max2_v1"
WEAK_PERIODS = [
    ("2025Q1", "2025-01-01", "2025-03-31"),
    ("2025Q4", "2025-10-01", "2025-12-31"),
]


def run_mid_trend_adaptive_candidate_review(
    *,
    funnel_detail_path: str | Path,
    start_date: str,
    end_date: str,
    output_dir: str | Path,
    cost_bps_values: list[float] | None = None,
    top_n: int = 5,
    buffer_rank: int = 10,
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
    return build_mid_trend_adaptive_candidate_review_from_frames(
        funnel_detail=funnel_detail,
        prices=prices,
        start_date=start_date,
        end_date=end_date,
        output_dir=output_dir,
        cost_bps_values=cost_bps_values,
        top_n=top_n,
        buffer_rank=buffer_rank,
        max_weekly_replacements=max_weekly_replacements,
        transaction_cost_bps=transaction_cost_bps,
        adjust_type=adjust_type,
    )


def build_mid_trend_adaptive_candidate_review_from_frames(
    *,
    funnel_detail: pd.DataFrame,
    prices: pd.DataFrame,
    start_date: str,
    end_date: str,
    output_dir: str | Path | None = None,
    cost_bps_values: list[float] | None = None,
    top_n: int = 5,
    buffer_rank: int = 10,
    max_weekly_replacements: int = 2,
    transaction_cost_bps: float = 20.0,
    adjust_type: str = "hfq",
) -> dict[str, Any]:
    primary_signals = build_mid_trend_shadow_top10_from_frame(funnel_detail, top_n=top_n)["top10"]
    buffer_signals = build_mid_trend_shadow_top10_from_frame(funnel_detail, top_n=max(top_n, buffer_rank))["top10"]
    scoped_prices = _prices_for_shadow(prices, pd.concat([primary_signals, buffer_signals], ignore_index=True))

    baseline = _simulate_candidate(
        primary_signals,
        buffer_signals,
        scoped_prices,
        start_date=start_date,
        end_date=end_date,
        variant_name=BASELINE_VARIANT,
        top_n=top_n,
        buffer_rank=buffer_rank,
        max_weekly_replacements=max_weekly_replacements,
        transaction_cost_bps=transaction_cost_bps,
    )
    candidate = _simulate_candidate(
        primary_signals,
        buffer_signals,
        scoped_prices,
        start_date=start_date,
        end_date=end_date,
        variant_name=CANDIDATE_VARIANT,
        top_n=top_n,
        buffer_rank=buffer_rank,
        max_weekly_replacements=max_weekly_replacements,
        transaction_cost_bps=transaction_cost_bps,
    )
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
    attribution_summary = pd.concat(
        [
            _with_variant(baseline_attr["summary"], BASELINE_VARIANT),
            _with_variant(candidate_attr["summary"], CANDIDATE_VARIANT),
        ],
        ignore_index=True,
    )
    attribution_detail = pd.concat(
        [
            _with_variant(baseline_attr["detail"], BASELINE_VARIANT),
            _with_variant(candidate_attr["detail"], CANDIDATE_VARIANT),
        ],
        ignore_index=True,
    )

    cost_scan = _cost_scan(
        primary_signals,
        buffer_signals,
        scoped_prices,
        start_date=start_date,
        end_date=end_date,
        cost_bps_values=cost_bps_values or [10.0, 20.0, 30.0, 50.0],
        top_n=top_n,
        buffer_rank=buffer_rank,
        max_weekly_replacements=max_weekly_replacements,
        adjust_type=adjust_type,
    )
    weak_periods = _weak_period_summary(equity)
    report = _render_report(monthly, quarterly, attribution_summary, cost_scan, weak_periods)

    result: dict[str, Any] = {
        "monthly": monthly,
        "quarterly": quarterly,
        "attribution_summary": attribution_summary,
        "attribution_detail": attribution_detail,
        "cost_scan": cost_scan,
        "weak_periods": weak_periods,
        "report": report,
        "paths": {},
    }
    if output_dir is not None:
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        paths = {
            "monthly": output / "mid_trend_adaptive_candidate_monthly_stability.csv",
            "quarterly": output / "mid_trend_adaptive_candidate_quarterly_stability.csv",
            "attribution_summary": output / "mid_trend_adaptive_candidate_rebalance_attribution_summary.csv",
            "attribution_detail": output / "mid_trend_adaptive_candidate_rebalance_attribution_detail.csv",
            "cost_scan": output / "mid_trend_adaptive_candidate_cost_scan.csv",
            "weak_periods": output / "mid_trend_adaptive_candidate_weak_periods.csv",
            "report": output / "mid_trend_adaptive_candidate_review_report.md",
        }
        monthly.to_csv(paths["monthly"], index=False)
        quarterly.to_csv(paths["quarterly"], index=False)
        attribution_summary.to_csv(paths["attribution_summary"], index=False)
        attribution_detail.to_csv(paths["attribution_detail"], index=False)
        cost_scan.to_csv(paths["cost_scan"], index=False)
        weak_periods.to_csv(paths["weak_periods"], index=False)
        paths["report"].write_text(report, encoding="utf-8")
        result["paths"] = {key: str(value) for key, value in paths.items()}
    return result


def _simulate_candidate(
    primary_signals: pd.DataFrame,
    buffer_signals: pd.DataFrame,
    prices: pd.DataFrame,
    *,
    start_date: str,
    end_date: str,
    variant_name: str,
    top_n: int,
    buffer_rank: int,
    max_weekly_replacements: int,
    transaction_cost_bps: float,
) -> dict[str, Any]:
    return _simulate_variant(
        primary_signals,
        buffer_signals,
        prices,
        start_date=start_date,
        end_date=end_date,
        variant_name=variant_name,
        top_n=top_n,
        buffer_rank=buffer_rank,
        max_weekly_replacements=max_weekly_replacements,
        peak_drawdown_exit=0.12,
        transaction_cost_bps=transaction_cost_bps,
    )


def _cost_scan(
    primary_signals: pd.DataFrame,
    buffer_signals: pd.DataFrame,
    prices: pd.DataFrame,
    *,
    start_date: str,
    end_date: str,
    cost_bps_values: list[float],
    top_n: int,
    buffer_rank: int,
    max_weekly_replacements: int,
    adjust_type: str,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for cost in sorted({float(value) for value in cost_bps_values}):
        for variant in [BASELINE_VARIANT, CANDIDATE_VARIANT]:
            result = _simulate_candidate(
                primary_signals,
                buffer_signals,
                prices,
                start_date=start_date,
                end_date=end_date,
                variant_name=variant,
                top_n=top_n,
                buffer_rank=buffer_rank,
                max_weekly_replacements=max_weekly_replacements,
                transaction_cost_bps=cost,
            )
            row = dict(result["summary"])
            row["transaction_cost_bps"] = cost
            row["adjust_type"] = adjust_type
            rows.append(row)
    return pd.DataFrame(rows)


def _weak_period_summary(equity: pd.DataFrame) -> pd.DataFrame:
    frame = equity.copy()
    if frame.empty:
        return pd.DataFrame()
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    rows = []
    for period, start, end in WEAK_PERIODS:
        scoped = frame[frame["date"].between(pd.Timestamp(start), pd.Timestamp(end))]
        for variant, group in scoped.groupby("variant_name", sort=True):
            returns = pd.to_numeric(group["net_return"], errors="coerce").fillna(0.0)
            equity_values = pd.to_numeric(group["equity"], errors="coerce")
            high = equity_values.cummax()
            drawdown = equity_values / high - 1.0
            rows.append(
                {
                    "period": period,
                    "variant_name": variant,
                    "trading_days": int(len(group)),
                    "period_return": float((1.0 + returns).prod() - 1.0),
                    "period_win_rate": float((returns > 0).mean()) if len(returns) else np.nan,
                    "period_max_drawdown": float(drawdown.min()) if not drawdown.empty else np.nan,
                }
            )
    return pd.DataFrame(rows)


def _with_variant(frame: pd.DataFrame, variant_name: str) -> pd.DataFrame:
    result = frame.copy()
    result.insert(0, "variant_name", variant_name)
    return result


def _render_report(
    monthly: pd.DataFrame,
    quarterly: pd.DataFrame,
    attribution_summary: pd.DataFrame,
    cost_scan: pd.DataFrame,
    weak_periods: pd.DataFrame,
) -> str:
    lines = [
        "# Mid Trend Adaptive Candidate Review",
        "",
        "## 1. Scope",
        "验证 adaptive_daily_check_max2_v1 作为 max2 weekly 主候选；只做历史诊断，不生成交易建议，不接实盘。",
        "",
        "## 2. Monthly Stability",
        monthly.to_markdown(index=False) if not monthly.empty else "No monthly rows.",
        "",
        "## 3. Quarterly Stability",
        quarterly.to_markdown(index=False) if not quarterly.empty else "No quarterly rows.",
        "",
        "## 4. Rebalance Attribution",
        attribution_summary.to_markdown(index=False) if not attribution_summary.empty else "No attribution rows.",
        "",
        "## 5. Cost Scan",
        cost_scan.to_markdown(index=False) if not cost_scan.empty else "No cost scan rows.",
        "",
        "## 6. Weak Periods",
        weak_periods.to_markdown(index=False) if not weak_periods.empty else "No weak period rows.",
    ]
    return "\n".join(lines).rstrip() + "\n"
