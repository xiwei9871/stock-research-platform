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


DEFAULT_SCORE_GAPS = [6.0, 8.0, 10.0, 12.0]
DEFAULT_MAINLINE_GAPS = [0.05, 0.10, 0.15]
DEFAULT_TREND_R2_MINS = [75.0, 80.0]
DEFAULT_RET20_MINS = [65.0, 70.0]
DEFAULT_DRAWDOWN_MINS = [50.0, 55.0]


def run_mid_trend_trend_protection_scan(
    *,
    funnel_detail_path: str | Path,
    start_date: str,
    end_date: str,
    output_dir: str | Path,
    score_gap_values: list[float] | None = None,
    mainline_gap_values: list[float] | None = None,
    trend_r2_min_values: list[float] | None = None,
    ret20_min_values: list[float] | None = None,
    drawdown_min_values: list[float] | None = None,
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
    return build_mid_trend_trend_protection_scan_from_frames(
        funnel_detail=funnel_detail,
        prices=prices,
        start_date=start_date,
        end_date=end_date,
        output_dir=output_dir,
        score_gap_values=score_gap_values,
        mainline_gap_values=mainline_gap_values,
        trend_r2_min_values=trend_r2_min_values,
        ret20_min_values=ret20_min_values,
        drawdown_min_values=drawdown_min_values,
        top_n=top_n,
        max_weekly_replacements=max_weekly_replacements,
        transaction_cost_bps=transaction_cost_bps,
        adjust_type=adjust_type,
    )


def build_mid_trend_trend_protection_scan_from_frames(
    *,
    funnel_detail: pd.DataFrame,
    prices: pd.DataFrame,
    start_date: str,
    end_date: str,
    output_dir: str | Path | None = None,
    score_gap_values: list[float] | None = None,
    mainline_gap_values: list[float] | None = None,
    trend_r2_min_values: list[float] | None = None,
    ret20_min_values: list[float] | None = None,
    drawdown_min_values: list[float] | None = None,
    top_n: int = 5,
    max_weekly_replacements: int = 2,
    transaction_cost_bps: float = 20.0,
    adjust_type: str = "hfq",
) -> dict[str, Any]:
    score_gaps = _float_values(score_gap_values, DEFAULT_SCORE_GAPS, "score_gap_values")
    mainline_gaps = _float_values(mainline_gap_values, DEFAULT_MAINLINE_GAPS, "mainline_gap_values")
    trend_r2_mins = _float_values(trend_r2_min_values, DEFAULT_TREND_R2_MINS, "trend_r2_min_values")
    ret20_mins = _float_values(ret20_min_values, DEFAULT_RET20_MINS, "ret20_min_values")
    drawdown_mins = _float_values(drawdown_min_values, DEFAULT_DRAWDOWN_MINS, "drawdown_min_values")

    primary_signals = build_mid_trend_shadow_top10_from_frame(funnel_detail, top_n=top_n)["top10"]
    buffer_signals = build_mid_trend_shadow_top10_from_frame(funnel_detail, top_n=max(top_n, 10))["top10"]
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
        buffer_rank=10,
        max_weekly_replacements=max_weekly_replacements,
        peak_drawdown_exit=0.12,
        transaction_cost_bps=transaction_cost_bps,
    )["summary"]
    baseline.update(
        {
            "protection_score_gap": np.nan,
            "protection_mainline_gap": np.nan,
            "protection_trend_r2_min": np.nan,
            "protection_ret20_min": np.nan,
            "protection_drawdown_min": np.nan,
            "adjust_type": adjust_type,
        }
    )
    rows.append(baseline)

    for score_gap, mainline_gap, trend_min, ret_min, drawdown_min in product(
        score_gaps,
        mainline_gaps,
        trend_r2_mins,
        ret20_mins,
        drawdown_mins,
    ):
        result = _simulate_variant(
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
            protection_score_gap=score_gap,
            protection_mainline_gap=mainline_gap,
            protection_trend_r2_min=trend_min,
            protection_ret20_min=ret_min,
            protection_drawdown_min=drawdown_min,
        )
        row = result["summary"]
        row.update(
            {
                "variant_name": (
                    "selective_trend_protection"
                    f"_score_gap_{score_gap:g}"
                    f"_mainline_gap_{mainline_gap:g}"
                    f"_trend_{trend_min:g}"
                    f"_ret_{ret_min:g}"
                    f"_drawdown_{drawdown_min:g}"
                ),
                "protection_score_gap": score_gap,
                "protection_mainline_gap": mainline_gap,
                "protection_trend_r2_min": trend_min,
                "protection_ret20_min": ret_min,
                "protection_drawdown_min": drawdown_min,
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
            "summary": output / "mid_trend_trend_protection_scan_summary.csv",
            "report": output / "mid_trend_trend_protection_scan_report.md",
        }
        summary.to_csv(paths["summary"], index=False)
        paths["report"].write_text(report, encoding="utf-8")
        result["paths"] = {key: str(value) for key, value in paths.items()}
    return result


def _float_values(values: list[float] | None, default: list[float], name: str) -> list[float]:
    raw = values or default
    cleaned = sorted({float(value) for value in raw})
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
        "# Mid Trend Selective Trend Protection Scan",
        "",
        "## 1. Scope",
        "扫描周频 Top5 max2 的趋势持仓保护参数；只做历史诊断，不生成交易建议，不接实盘。",
        "",
        "## 2. Top Results",
        best.to_markdown(index=False) if not best.empty else "No scan rows.",
        "",
        "## 3. Guardrail",
        "优先寻找收益、Sharpe、回撤和换手之间的稳定区域，不按单一最优参数定策略。",
    ]
    return "\n".join(lines).rstrip() + "\n"
