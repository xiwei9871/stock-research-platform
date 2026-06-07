from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from stock_research.config import SETTINGS
from stock_research.mid_trend_shadow_backtest import _load_prices
from stock_research.mid_trend_shadow_top10 import build_mid_trend_shadow_top10_from_frame
from stock_research.mid_trend_shadow_weekly_control import _simulate_variant
from stock_research.mid_trend_shadow_weekly_optimization import _prices_for_shadow


DEFAULT_TOP_N_VALUES = [5, 8]
DEFAULT_MAX_WEEKLY_REPLACEMENT_VALUES = [1, 2, 3]
DEFAULT_TRANSACTION_COST_BPS_VALUES = [10.0, 20.0, 30.0]


def run_mid_trend_shadow_replacement_scan(
    *,
    funnel_detail_path: str | Path,
    start_date: str,
    end_date: str,
    output_dir: str | Path,
    top_n_values: list[int] | None = None,
    max_weekly_replacement_values: list[int] | None = None,
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
    return build_mid_trend_shadow_replacement_scan_from_frames(
        funnel_detail=funnel_detail,
        prices=prices,
        start_date=start_date,
        end_date=end_date,
        output_dir=output_dir,
        top_n_values=top_n_values,
        max_weekly_replacement_values=max_weekly_replacement_values,
        transaction_cost_bps_values=transaction_cost_bps_values,
        adjust_type=adjust_type,
    )


def build_mid_trend_shadow_replacement_scan_from_frames(
    *,
    funnel_detail: pd.DataFrame,
    prices: pd.DataFrame,
    start_date: str,
    end_date: str,
    output_dir: str | Path | None = None,
    top_n_values: list[int] | None = None,
    max_weekly_replacement_values: list[int] | None = None,
    transaction_cost_bps_values: list[float] | None = None,
    adjust_type: str = "hfq",
) -> dict[str, Any]:
    top_ns = _positive_int_values(top_n_values, DEFAULT_TOP_N_VALUES, "top_n_values")
    replacement_values = _positive_int_values(
        max_weekly_replacement_values,
        DEFAULT_MAX_WEEKLY_REPLACEMENT_VALUES,
        "max_weekly_replacement_values",
    )
    costs = _non_negative_float_values(
        transaction_cost_bps_values,
        DEFAULT_TRANSACTION_COST_BPS_VALUES,
        "transaction_cost_bps_values",
    )
    max_top_n = max(top_ns)
    primary_signals_by_top_n = {
        top_n: build_mid_trend_shadow_top10_from_frame(funnel_detail, top_n=top_n)["top10"]
        for top_n in top_ns
    }
    scoped_prices = _prices_for_shadow(
        prices,
        build_mid_trend_shadow_top10_from_frame(funnel_detail, top_n=max_top_n)["top10"],
    )

    rows: list[dict[str, Any]] = []
    report_notes: list[str] = []
    for top_n in top_ns:
        signals = primary_signals_by_top_n[top_n]
        for replacement_limit in replacement_values:
            for cost_bps in costs:
                variant_name = f"top{top_n}_weekly_max_replacements_{replacement_limit}"
                result = _simulate_variant(
                    signals,
                    signals,
                    scoped_prices,
                    start_date=start_date,
                    end_date=end_date,
                    variant_name=variant_name,
                    top_n=top_n,
                    buffer_rank=top_n,
                    max_weekly_replacements=replacement_limit,
                    peak_drawdown_exit=0.12,
                    transaction_cost_bps=cost_bps,
                )
                row = result["summary"]
                row["top_n"] = top_n
                row["max_weekly_replacements"] = replacement_limit
                row["transaction_cost_bps"] = float(cost_bps)
                row["adjust_type"] = adjust_type
                rows.append(row)

    summary = _rank_summary(pd.DataFrame(rows))
    report = _render_report(summary, report_notes)
    result: dict[str, Any] = {"summary": summary, "report": report, "paths": {}}
    if output_dir is not None:
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        paths = {
            "summary": output / "mid_trend_shadow_replacement_scan_summary.csv",
            "report": output / "mid_trend_shadow_replacement_scan_report.md",
        }
        summary.to_csv(paths["summary"], index=False)
        paths["report"].write_text(report, encoding="utf-8")
        result["paths"] = {key: str(value) for key, value in paths.items()}
    return result


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


def _positive_int_values(values: list[int] | None, default: list[int], name: str) -> list[int]:
    raw = values or default
    cleaned = sorted({int(value) for value in raw if int(value) > 0})
    if not cleaned:
        raise ValueError(f"{name} must include at least one positive integer")
    return cleaned


def _non_negative_float_values(values: list[float] | None, default: list[float], name: str) -> list[float]:
    raw = values or default
    cleaned = sorted({float(value) for value in raw if float(value) >= 0})
    if not cleaned:
        raise ValueError(f"{name} must include at least one non-negative number")
    return cleaned


def _render_report(summary: pd.DataFrame, notes: list[str]) -> str:
    best = summary.head(10) if not summary.empty else summary
    lines = [
        "# Mid Trend Shadow Replacement Scan",
        "",
        "## 1. Scope",
        "扫描周频 shadow TopN 的每周最大替换数量，不生成交易建议，不接实盘。",
        "",
        "## 2. Top Results",
        best.to_markdown(index=False) if not best.empty else "No scan rows.",
        "",
        "## 3. Notes",
        "\n".join(f"- {note}" for note in notes) if notes else "- no warnings",
    ]
    return "\n".join(lines).rstrip() + "\n"
