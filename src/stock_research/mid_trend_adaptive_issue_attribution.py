from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from stock_research.mid_trend_bad_rebalance_state_attribution import (
    FEATURES,
    build_bad_rebalance_state_attribution_from_frames,
)


BASELINE_VARIANT = "top5_weekly_max_2_replacements"
CANDIDATE_VARIANT = "top5_adaptive_daily_check_max2_v1"


def run_mid_trend_adaptive_issue_attribution(
    *,
    monthly_path: str | Path,
    attribution_detail_path: str | Path,
    funnel_detail_path: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    monthly = pd.read_csv(monthly_path, low_memory=False)
    attribution_detail = pd.read_csv(attribution_detail_path, low_memory=False)
    funnel_detail = pd.read_csv(funnel_detail_path, low_memory=False)
    return build_mid_trend_adaptive_issue_attribution_from_frames(
        monthly=monthly,
        attribution_detail=attribution_detail,
        funnel_detail=funnel_detail,
        output_dir=output_dir,
    )


def build_mid_trend_adaptive_issue_attribution_from_frames(
    *,
    monthly: pd.DataFrame,
    attribution_detail: pd.DataFrame,
    funnel_detail: pd.DataFrame,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    period_gap = _period_gap(monthly)
    enriched = build_bad_rebalance_state_attribution_from_frames(
        attribution_detail=attribution_detail,
        funnel_detail=funnel_detail,
    )
    detail = enriched["detail"]
    sell_fly_detail = _sell_fly_detail(detail)
    feature_summary = _feature_summary(detail, sell_fly_detail)
    report = _render_report(period_gap, sell_fly_detail, feature_summary)
    result: dict[str, Any] = {
        "period_gap": period_gap,
        "sell_fly_detail": sell_fly_detail,
        "feature_summary": feature_summary,
        "report": report,
        "paths": {},
    }
    if output_dir is not None:
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        paths = {
            "period_gap": output / "mid_trend_adaptive_issue_period_gap.csv",
            "sell_fly_detail": output / "mid_trend_adaptive_issue_sell_fly_detail.csv",
            "feature_summary": output / "mid_trend_adaptive_issue_feature_summary.csv",
            "report": output / "mid_trend_adaptive_issue_attribution_report.md",
        }
        period_gap.to_csv(paths["period_gap"], index=False)
        sell_fly_detail.to_csv(paths["sell_fly_detail"], index=False)
        feature_summary.to_csv(paths["feature_summary"], index=False)
        paths["report"].write_text(report, encoding="utf-8")
        result["paths"] = {key: str(value) for key, value in paths.items()}
    return result


def _period_gap(monthly: pd.DataFrame) -> pd.DataFrame:
    if monthly.empty:
        return pd.DataFrame()
    frame = monthly.copy()
    frame = frame[frame["variant_name"].astype(str).isin({BASELINE_VARIANT, CANDIDATE_VARIANT})].copy()
    frame["period_return"] = pd.to_numeric(frame.get("period_return"), errors="coerce")
    frame["period_max_drawdown"] = pd.to_numeric(frame.get("period_max_drawdown"), errors="coerce")
    frame["trade_rows"] = pd.to_numeric(frame.get("trade_rows"), errors="coerce")
    pivot = frame.pivot_table(index="period", columns="variant_name", values=["period_return", "period_max_drawdown", "trade_rows"], aggfunc="first")
    rows = []
    for period in pivot.index.astype(str):
        row = {"period": period}
        for metric in ["period_return", "period_max_drawdown", "trade_rows"]:
            baseline = _pivot_value(pivot, metric, BASELINE_VARIANT, period)
            candidate = _pivot_value(pivot, metric, CANDIDATE_VARIANT, period)
            row[f"baseline_{metric}"] = baseline
            row[f"adaptive_{metric}"] = candidate
            row[f"{metric}_delta"] = candidate - baseline if pd.notna(candidate) and pd.notna(baseline) else np.nan
        row["return_delta"] = row["period_return_delta"]
        row["drawdown_improvement"] = row["period_max_drawdown_delta"]
        row["adaptive_worse_return"] = bool(pd.notna(row["return_delta"]) and row["return_delta"] < 0)
        row["adaptive_worse_drawdown"] = bool(pd.notna(row["drawdown_improvement"]) and row["drawdown_improvement"] < 0)
        rows.append(row)
    result = pd.DataFrame(rows)
    if result.empty:
        return result
    result["is_q1_2025"] = result["period"].astype(str).isin(["2025-01", "2025-02", "2025-03"])
    return result.sort_values(["is_q1_2025", "return_delta"], ascending=[False, True]).reset_index(drop=True)


def _pivot_value(pivot: pd.DataFrame, metric: str, variant: str, period: str) -> float:
    try:
        return float(pivot.loc[period, (metric, variant)])
    except (KeyError, TypeError, ValueError):
        return np.nan


def _sell_fly_detail(detail: pd.DataFrame) -> pd.DataFrame:
    if detail.empty:
        return detail
    frame = detail.copy()
    frame["variant_name"] = frame["variant_name"].astype(str)
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="coerce").dt.date.astype(str)
    mask = (
        frame["variant_name"].eq(CANDIDATE_VARIANT)
        & frame.get("bad_rebalance_reasons", "").astype(str).str.contains("sell_fly", na=False)
    )
    result = frame[mask].copy()
    if result.empty:
        return result
    result["is_q1_2025"] = result["trade_date"].between("2025-01-01", "2025-03-31")
    keep = [
        "variant_name",
        "trade_date",
        "sold_asset_id",
        "bought_asset_id",
        "replacement_alpha_10d",
        "replacement_alpha_20d",
        "sold_next_10d_return",
        "bought_next_10d_return",
        "bad_rebalance_reasons",
        "sold_still_strong",
        "bought_overheated",
        "bought_weak_mainline",
        "is_q1_2025",
    ]
    for side in ["sold", "bought"]:
        for feature in FEATURES:
            keep.append(f"{side}_{feature}")
        keep.extend([f"{side}_mid_trend_layer", f"{side}_industry_name", f"{side}_market_regime", f"{side}_mainline_status"])
    return result[[column for column in keep if column in result.columns]].sort_values(
        ["is_q1_2025", "replacement_alpha_10d"],
        ascending=[False, True],
    )


def _feature_summary(detail: pd.DataFrame, sell_fly_detail: pd.DataFrame) -> pd.DataFrame:
    rows = []
    groups = {
        "adaptive_all_bad": detail[
            detail.get("variant_name", pd.Series(dtype=str)).astype(str).eq(CANDIDATE_VARIANT)
            & detail.get("bad_rebalance_flag", pd.Series(dtype=bool)).astype(str).str.lower().eq("true")
        ] if not detail.empty else pd.DataFrame(),
        "adaptive_sell_fly": sell_fly_detail,
        "adaptive_q1_sell_fly": sell_fly_detail[sell_fly_detail.get("is_q1_2025", pd.Series(dtype=bool)).astype(bool)] if not sell_fly_detail.empty else pd.DataFrame(),
    }
    for name, group in groups.items():
        row = {"group": name, "sample_count": int(len(group))}
        if not group.empty:
            row["sold_still_strong_rate"] = _mean(group.get("sold_still_strong"))
            row["bought_overheated_rate"] = _mean(group.get("bought_overheated"))
            row["bought_weak_mainline_rate"] = _mean(group.get("bought_weak_mainline"))
            row["avg_replacement_alpha_10d"] = _mean(group.get("replacement_alpha_10d"))
            row["avg_sold_next_10d_return"] = _mean(group.get("sold_next_10d_return"))
            row["avg_bought_next_10d_return"] = _mean(group.get("bought_next_10d_return"))
            for side in ["sold", "bought"]:
                for feature in FEATURES:
                    row[f"avg_{side}_{feature}"] = _mean(group.get(f"{side}_{feature}"))
        rows.append(row)
    return pd.DataFrame(rows)


def _mean(series: Any) -> float:
    if series is None:
        return np.nan
    values = pd.Series(series)
    if values.dtype == object:
        values = values.map(lambda value: 1.0 if value is True else 0.0 if value is False else value)
    values = pd.to_numeric(values, errors="coerce").dropna()
    return float(values.mean()) if not values.empty else np.nan


def _render_report(period_gap: pd.DataFrame, sell_fly_detail: pd.DataFrame, feature_summary: pd.DataFrame) -> str:
    q1 = period_gap[period_gap.get("is_q1_2025", pd.Series(dtype=bool)).astype(bool)] if not period_gap.empty else period_gap
    worst = sell_fly_detail.head(30) if not sell_fly_detail.empty else sell_fly_detail
    lines = [
        "# Mid Trend Adaptive Issue Attribution",
        "",
        "## 1. Scope",
        "只做 adaptive_daily_check_max2_v1 的问题归因，不新增策略规则，不生成交易建议，不接实盘。",
        "",
        "## 2. Q1 Period Gap",
        q1.to_markdown(index=False) if not q1.empty else "No Q1 period gap rows.",
        "",
        "## 3. Sell-Fly State Summary",
        feature_summary.to_markdown(index=False) if not feature_summary.empty else "No feature summary rows.",
        "",
        "## 4. Worst Sell-Fly Rows",
        worst.to_markdown(index=False) if not worst.empty else "No sell-fly rows.",
    ]
    return "\n".join(lines).rstrip() + "\n"
