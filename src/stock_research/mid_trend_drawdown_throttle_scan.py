from __future__ import annotations

from itertools import product
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from stock_research.config import SETTINGS
from stock_research.mid_trend_shadow_backtest import _load_prices
from stock_research.mid_trend_shadow_top10 import build_mid_trend_shadow_top10_from_frame
from stock_research.mid_trend_shadow_weekly_control import _simulate_variant
from stock_research.mid_trend_shadow_weekly_optimization import _prices_for_shadow


DEFAULT_THRESHOLDS = [0.08, 0.10, 0.12]
DEFAULT_INVESTED_WEIGHTS = [0.8, 0.9, 1.0]
DEFAULT_MAX_REPLACEMENTS = [1, 2]


def run_mid_trend_drawdown_throttle_scan(
    *,
    funnel_detail_path: str | Path,
    start_date: str,
    end_date: str,
    output_dir: str | Path,
    threshold_values: list[float] | None = None,
    invested_weight_values: list[float] | None = None,
    max_replacement_values: list[int] | None = None,
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
    return build_mid_trend_drawdown_throttle_scan_from_frames(
        funnel_detail=funnel_detail,
        prices=prices,
        start_date=start_date,
        end_date=end_date,
        output_dir=output_dir,
        threshold_values=threshold_values,
        invested_weight_values=invested_weight_values,
        max_replacement_values=max_replacement_values,
        top_n=top_n,
        buffer_rank=buffer_rank,
        max_weekly_replacements=max_weekly_replacements,
        transaction_cost_bps=transaction_cost_bps,
        adjust_type=adjust_type,
    )


def build_mid_trend_drawdown_throttle_scan_from_frames(
    *,
    funnel_detail: pd.DataFrame,
    prices: pd.DataFrame,
    start_date: str,
    end_date: str,
    output_dir: str | Path | None = None,
    threshold_values: list[float] | None = None,
    invested_weight_values: list[float] | None = None,
    max_replacement_values: list[int] | None = None,
    top_n: int = 5,
    buffer_rank: int = 10,
    max_weekly_replacements: int = 2,
    transaction_cost_bps: float = 20.0,
    adjust_type: str = "hfq",
) -> dict[str, Any]:
    thresholds = _negative_thresholds(threshold_values)
    invested_weights = _float_values(invested_weight_values, DEFAULT_INVESTED_WEIGHTS, "invested_weight_values")
    replacement_limits = _int_values(max_replacement_values, DEFAULT_MAX_REPLACEMENTS, "max_replacement_values")

    primary_signals = build_mid_trend_shadow_top10_from_frame(funnel_detail, top_n=top_n)["top10"]
    buffer_signals = build_mid_trend_shadow_top10_from_frame(funnel_detail, top_n=max(top_n, buffer_rank))["top10"]
    scoped_prices = _prices_for_shadow(prices, pd.concat([primary_signals, buffer_signals], ignore_index=True))

    rows: list[dict[str, Any]] = []
    baseline = _simulate_variant(
        primary_signals,
        buffer_signals,
        scoped_prices,
        start_date=start_date,
        end_date=end_date,
        variant_name="top5_weekly_max_2_replacements",
        top_n=top_n,
        buffer_rank=buffer_rank,
        max_weekly_replacements=max_weekly_replacements,
        peak_drawdown_exit=0.12,
        transaction_cost_bps=transaction_cost_bps,
    )["summary"]
    baseline.update(
        {
            "drawdown_throttle_threshold": np.nan,
            "drawdown_throttle_invested_weight": np.nan,
            "drawdown_throttle_max_replacements": np.nan,
            "adjust_type": adjust_type,
        }
    )
    rows.append(baseline)

    for threshold, invested_weight, replacement_limit in product(thresholds, invested_weights, replacement_limits):
        result = _simulate_variant(
            primary_signals,
            buffer_signals,
            scoped_prices,
            start_date=start_date,
            end_date=end_date,
            variant_name="top5_weekly_max2_drawdown_throttle_v1",
            top_n=top_n,
            buffer_rank=buffer_rank,
            max_weekly_replacements=max_weekly_replacements,
            peak_drawdown_exit=0.12,
            transaction_cost_bps=transaction_cost_bps,
            drawdown_throttle_threshold=threshold,
            drawdown_throttle_invested_weight=invested_weight,
            drawdown_throttle_max_replacements=replacement_limit,
        )
        row = result["summary"]
        row.update(
            {
                "variant_name": (
                    "drawdown_throttle"
                    f"_threshold_{abs(threshold):g}"
                    f"_weight_{invested_weight:g}"
                    f"_maxrep_{replacement_limit:g}"
                ),
                "drawdown_throttle_threshold": threshold,
                "drawdown_throttle_invested_weight": invested_weight,
                "drawdown_throttle_max_replacements": replacement_limit,
                "adjust_type": adjust_type,
            }
        )
        rows.append(row)

    summary = _rank_summary(pd.DataFrame(rows))
    report = _render_report(summary)
    result: dict[str, Any] = {"summary": summary, "report": report, "paths": {}}
    if output_dir is not None:
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        paths = {
            "summary": output / "mid_trend_drawdown_throttle_scan_summary.csv",
            "report": output / "mid_trend_drawdown_throttle_scan_report.md",
        }
        summary.to_csv(paths["summary"], index=False)
        paths["report"].write_text(report, encoding="utf-8")
        result["paths"] = {key: str(value) for key, value in paths.items()}
    return result


def _negative_thresholds(values: list[float] | None) -> list[float]:
    raw = _float_values(values, DEFAULT_THRESHOLDS, "threshold_values")
    return sorted({-abs(value) for value in raw})


def _float_values(values: list[float] | None, default: list[float], name: str) -> list[float]:
    raw = values or default
    cleaned = sorted({float(value) for value in raw})
    if not cleaned:
        raise ValueError(f"{name} must include at least one value")
    return cleaned


def _int_values(values: list[int] | None, default: list[int], name: str) -> list[int]:
    raw = values or default
    cleaned = sorted({int(value) for value in raw})
    if not cleaned:
        raise ValueError(f"{name} must include at least one value")
    return cleaned


def _rank_summary(summary: pd.DataFrame) -> pd.DataFrame:
    if summary.empty:
        return pd.DataFrame()
    ranked = summary.copy()
    for column in [
        "total_return",
        "annualized_return",
        "max_drawdown",
        "sharpe_ratio",
        "calmar_ratio",
        "average_turnover",
        "total_transaction_cost",
        "drawdown_throttle_trigger_count",
        "average_invested_weight",
    ]:
        ranked[column] = pd.to_numeric(ranked.get(column), errors="coerce")
    ranked = ranked.sort_values(
        ["sharpe_ratio", "calmar_ratio", "total_return", "max_drawdown", "average_turnover"],
        ascending=[False, False, False, False, True],
        na_position="last",
    ).reset_index(drop=True)
    ranked.insert(0, "scan_rank", range(1, len(ranked) + 1))
    return ranked


def _render_report(summary: pd.DataFrame) -> str:
    best = summary.head(15) if not summary.empty else summary
    lines = [
        "# Mid Trend Drawdown Throttle Scan",
        "",
        "## 1. Scope",
        "扫描周频 Top5 max2 的组合回撤期降仓/降换手参数；只做历史诊断，不生成交易建议，不接实盘。",
        "",
        "## 2. Top Results",
        best.to_markdown(index=False) if not best.empty else "No scan rows.",
        "",
        "## 3. Guardrail",
        "重点看收益、Sharpe、最大回撤、触发次数、平均仓位和换手成本；不按单一最优参数直接定策略。",
    ]
    return "\n".join(lines).rstrip() + "\n"
