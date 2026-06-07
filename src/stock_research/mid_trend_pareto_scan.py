from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd


METRICS = [
    "future_20d_return",
    "future_30d_return",
    "future_40d_return",
    "future_60d_return",
    "future_60d_max_drawdown",
    "max_return_within_60d",
    "hit_double_within_60d",
]
THRESHOLD_GRID = {
    "volatility_20_score": [10, 15, 20, 25, 30, 35],
    "atr_pct_score": [10, 15, 20, 25, 30],
    "max_drawdown_20_score": [40, 50, 60, 70, 80],
    "trend_r2_20_score": [60, 70, 80],
    "ma60_slope_score": [70, 75, 80, 85],
}


def run_mid_trend_pareto_scan(
    *,
    funnel_detail_path: str | Path,
    output_dir: str | Path,
    top_n: int = 10,
) -> dict[str, Any]:
    funnel_detail = pd.read_csv(funnel_detail_path, low_memory=False)
    return build_mid_trend_pareto_scan_from_frames(
        funnel_detail=funnel_detail,
        top_n=top_n,
        output_dir=output_dir,
    )


def build_mid_trend_pareto_scan_from_frames(
    *,
    funnel_detail: pd.DataFrame,
    top_n: int = 10,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    detail = _normalize(funnel_detail)
    threshold_scan = _threshold_scan(detail, top_n=top_n)
    combo_scan = _combo_scan(detail, top_n=top_n)
    high_elasticity = _high_elasticity_decomposition(detail)
    recommendations = _pareto_recommendations(pd.concat([threshold_scan, combo_scan], ignore_index=True))
    report = _render_report(threshold_scan, combo_scan, high_elasticity, recommendations)

    result: dict[str, Any] = {
        "threshold_scan": threshold_scan,
        "combo_scan": combo_scan,
        "high_elasticity_decomposition": high_elasticity,
        "pareto_recommendations": recommendations,
        "report": report,
        "paths": {},
    }
    if output_dir is not None:
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        paths = {
            "threshold_scan": output / "mid_trend_drawdown_threshold_scan.csv",
            "combo_scan": output / "mid_trend_combo_rule_scan.csv",
            "high_elasticity_decomposition": output / "mid_trend_high_elasticity_decomposition.csv",
            "pareto_recommendations": output / "mid_trend_pareto_recommendations.csv",
            "report": output / "mid_trend_risk_return_pareto_scan_report.md",
        }
        threshold_scan.to_csv(paths["threshold_scan"], index=False)
        combo_scan.to_csv(paths["combo_scan"], index=False)
        high_elasticity.to_csv(paths["high_elasticity_decomposition"], index=False)
        recommendations.to_csv(paths["pareto_recommendations"], index=False)
        paths["report"].write_text(report, encoding="utf-8")
        result["paths"] = {key: str(value) for key, value in paths.items()}
    return result


def _normalize(frame: pd.DataFrame) -> pd.DataFrame:
    normalized = frame.copy()
    for column in [
        "trade_date",
        "asset_id",
        "mid_trend_layer",
        "mid_trend_funnel_score",
        "score_rank",
        "volatility_20_score",
        "atr_pct_score",
        "max_drawdown_20_score",
        "trend_r2_20_score",
        "ma60_slope_score",
        "ret_20_score",
        "ret_60_score",
    ]:
        if column not in normalized.columns:
            normalized[column] = np.nan
    normalized["trade_date"] = pd.to_datetime(normalized["trade_date"], errors="coerce")
    normalized["asset_id"] = normalized["asset_id"].astype(str)
    for column in [
        "mid_trend_funnel_score",
        "score_rank",
        "volatility_20_score",
        "atr_pct_score",
        "max_drawdown_20_score",
        "trend_r2_20_score",
        "ma60_slope_score",
        "ret_20_score",
        "ret_60_score",
        *METRICS,
    ]:
        if column not in normalized.columns:
            normalized[column] = np.nan
        normalized[column] = pd.to_numeric(normalized[column], errors="coerce")
    normalized["hit_double_within_60d"] = normalized["hit_double_within_60d"].fillna(0).astype(bool)
    return normalized.dropna(subset=["trade_date", "asset_id"]).copy()


def _threshold_scan(detail: pd.DataFrame, *, top_n: int) -> pd.DataFrame:
    rows = []
    for family, thresholds in THRESHOLD_GRID.items():
        for threshold in thresholds:
            selected = _select_top_n(detail[detail[family] >= threshold], top_n=top_n)
            rows.append(_metric_row(selected, rule_family=family, threshold=threshold))
    return pd.DataFrame(rows)


def _combo_scan(detail: pd.DataFrame, *, top_n: int) -> pd.DataFrame:
    rules: list[tuple[str, Callable[[pd.DataFrame], pd.DataFrame]]] = [
        (
            "vol15_trend70",
            lambda frame: frame[(frame["volatility_20_score"] >= 15) & (frame["trend_r2_20_score"] >= 70)],
        ),
        (
            "vol15_trend80",
            lambda frame: frame[(frame["volatility_20_score"] >= 15) & (frame["trend_r2_20_score"] >= 80)],
        ),
        (
            "vol15_trend70_no_bad_high_elasticity",
            lambda frame: _exclude_bad_high_elasticity(
                frame[(frame["volatility_20_score"] >= 15) & (frame["trend_r2_20_score"] >= 70)]
            ),
        ),
        (
            "vol20_trend70_no_bad_high_elasticity",
            lambda frame: _exclude_bad_high_elasticity(
                frame[(frame["volatility_20_score"] >= 20) & (frame["trend_r2_20_score"] >= 70)]
            ),
        ),
        (
            "vol15_trend70_ma60_80",
            lambda frame: frame[
                (frame["volatility_20_score"] >= 15)
                & (frame["trend_r2_20_score"] >= 70)
                & (frame["ma60_slope_score"] >= 80)
            ],
        ),
        (
            "vol20_or_good_high_elasticity",
            lambda frame: frame[(frame["volatility_20_score"] >= 20) | _good_high_elasticity_mask(frame)],
        ),
        (
            "trend80_or_good_high_elasticity",
            lambda frame: frame[(frame["trend_r2_20_score"] >= 80) | _good_high_elasticity_mask(frame)],
        ),
        (
            "good_high_elasticity_only",
            lambda frame: frame[_good_high_elasticity_mask(frame)],
        ),
    ]
    rows = []
    for rule_name, selector in rules:
        selected = _select_top_n(selector(detail), top_n=top_n)
        rows.append(_metric_row(selected, rule_family="combo_rule", threshold=np.nan, rule_name=rule_name))
    return pd.DataFrame(rows)


def _select_top_n(frame: pd.DataFrame, *, top_n: int) -> pd.DataFrame:
    if frame.empty or top_n <= 0:
        return frame.head(0).copy()
    ranked = frame.sort_values(["trade_date", "mid_trend_funnel_score", "score_rank"], ascending=[True, False, True])
    return ranked.groupby("trade_date", group_keys=False).head(top_n).reset_index(drop=True)


def _metric_row(
    frame: pd.DataFrame,
    *,
    rule_family: str,
    threshold: float,
    rule_name: str | None = None,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "rule_name": rule_name or f"{rule_family}>={threshold:g}",
        "rule_family": rule_family,
        "threshold": threshold,
        "sample_count": int(len(frame)),
        "unique_asset_count": int(frame["asset_id"].nunique()) if "asset_id" in frame.columns else 0,
        "avg_high_elasticity_count_per_day": _avg_layer_count(frame, "high_elasticity_watch"),
    }
    for horizon in [20, 30, 40, 60]:
        values = pd.to_numeric(frame.get(f"future_{horizon}d_return"), errors="coerce").dropna()
        row[f"avg_future_{horizon}d_return"] = float(values.mean()) if not values.empty else np.nan
        row[f"win_rate_{horizon}d"] = float((values > 0).mean()) if not values.empty else np.nan
    row["avg_future_60d_max_drawdown"] = _mean(frame.get("future_60d_max_drawdown"))
    row["avg_max_return_within_60d"] = _mean(frame.get("max_return_within_60d"))
    row["hit_double_within_60d_rate"] = _mean(frame.get("hit_double_within_60d"))
    row["return_drawdown_ratio_60d"] = _ratio(row["avg_future_60d_return"], row["avg_future_60d_max_drawdown"])
    row["meets_target"] = bool(
        row["avg_future_60d_return"] >= 0.115
        and row["avg_future_60d_max_drawdown"] >= -0.145
        and row["hit_double_within_60d_rate"] >= 0.06
    )
    return row


def _high_elasticity_decomposition(detail: pd.DataFrame) -> pd.DataFrame:
    high = detail[detail["mid_trend_layer"].eq("high_elasticity_watch")].copy()
    if high.empty:
        return pd.DataFrame(columns=["elasticity_bucket", "sample_count"])

    buckets: list[tuple[str, Callable[[pd.DataFrame], pd.DataFrame]]] = [
        (
            "good_high_elasticity",
            lambda frame: frame[
                (frame["volatility_20_score"] >= 20)
                & (frame["max_drawdown_20_score"] >= 55)
                & (frame["trend_r2_20_score"] >= 65)
            ],
        ),
        (
            "bad_high_elasticity",
            lambda frame: frame[
                (frame["volatility_20_score"] < 20)
                | (frame["max_drawdown_20_score"] < 55)
                | (frame["trend_r2_20_score"] < 65)
            ],
        ),
        (
            "high_elasticity_all",
            lambda frame: frame,
        ),
    ]
    rows = []
    for bucket, selector in buckets:
        selected = selector(high)
        row = _bucket_metric_row(selected, bucket)
        rows.append(row)
    return pd.DataFrame(rows)


def _good_high_elasticity_mask(frame: pd.DataFrame) -> pd.Series:
    return (
        frame["mid_trend_layer"].eq("high_elasticity_watch")
        & (frame["volatility_20_score"] >= 20)
        & (frame["max_drawdown_20_score"] >= 55)
        & (frame["trend_r2_20_score"] >= 65)
    )


def _exclude_bad_high_elasticity(frame: pd.DataFrame) -> pd.DataFrame:
    bad_high_elasticity = frame["mid_trend_layer"].eq("high_elasticity_watch") & ~_good_high_elasticity_mask(frame)
    return frame[~bad_high_elasticity].copy()


def _bucket_metric_row(frame: pd.DataFrame, bucket: str) -> dict[str, Any]:
    row: dict[str, Any] = {
        "elasticity_bucket": bucket,
        "sample_count": int(len(frame)),
        "unique_asset_count": int(frame["asset_id"].nunique()) if "asset_id" in frame.columns else 0,
    }
    for horizon in [20, 30, 40, 60]:
        row[f"avg_future_{horizon}d_return"] = _mean(frame.get(f"future_{horizon}d_return"))
    row["avg_future_60d_max_drawdown"] = _mean(frame.get("future_60d_max_drawdown"))
    row["avg_max_return_within_60d"] = _mean(frame.get("max_return_within_60d"))
    row["hit_double_within_60d_rate"] = _mean(frame.get("hit_double_within_60d"))
    row["return_drawdown_ratio_60d"] = _ratio(row["avg_future_60d_return"], row["avg_future_60d_max_drawdown"])
    return row


def _pareto_recommendations(threshold_scan: pd.DataFrame) -> pd.DataFrame:
    if threshold_scan.empty:
        return pd.DataFrame(columns=["rule_name", "pareto_score", "recommendation"])
    working = threshold_scan.copy()
    working["return_score"] = _percent_rank(working["avg_future_60d_return"])
    working["drawdown_score"] = _percent_rank(working["avg_future_60d_max_drawdown"])
    working["double_score"] = _percent_rank(working["hit_double_within_60d_rate"])
    working["sample_score"] = _percent_rank(working["sample_count"])
    working["pareto_score"] = (
        working["return_score"] * 0.35
        + working["drawdown_score"] * 0.35
        + working["double_score"] * 0.20
        + working["sample_score"] * 0.10
    )
    working["recommendation"] = np.where(working["meets_target"], "pareto_candidate", "diagnostic_only")
    cols = [
        "rule_name",
        "rule_family",
        "threshold",
        "sample_count",
        "avg_future_60d_return",
        "avg_future_60d_max_drawdown",
        "hit_double_within_60d_rate",
        "return_drawdown_ratio_60d",
        "pareto_score",
        "recommendation",
    ]
    return working.sort_values("pareto_score", ascending=False).loc[:, cols].reset_index(drop=True)


def _render_report(
    threshold_scan: pd.DataFrame,
    combo_scan: pd.DataFrame,
    high_elasticity: pd.DataFrame,
    recommendations: pd.DataFrame,
) -> str:
    lines = [
        "# Mid Trend Risk-Return Pareto Scan v1",
        "",
        "## 1. Scope",
        "扫描中线 Top10 的风险收益约束，只用于 shadow diagnostics，不生成交易建议。",
        "",
        "## 2. Threshold Scan",
        threshold_scan.to_markdown(index=False) if not threshold_scan.empty else "No threshold rows.",
        "",
        "## 3. Combo Rule Scan",
        combo_scan.to_markdown(index=False) if not combo_scan.empty else "No combo rows.",
        "",
        "## 4. High Elasticity Decomposition",
        high_elasticity.to_markdown(index=False) if not high_elasticity.empty else "No high elasticity rows.",
        "",
        "## 5. Pareto Recommendations",
        recommendations.head(15).to_markdown(index=False) if not recommendations.empty else "No recommendations.",
    ]
    return "\n".join(lines).rstrip() + "\n"


def _avg_layer_count(frame: pd.DataFrame, layer: str) -> float:
    if frame.empty:
        return 0.0
    counts = frame.groupby("trade_date")["mid_trend_layer"].apply(lambda values: int((values == layer).sum()))
    return float(counts.mean()) if not counts.empty else 0.0


def _mean(series: Any) -> float:
    if series is None:
        return np.nan
    values = pd.to_numeric(series, errors="coerce").dropna()
    return float(values.mean()) if not values.empty else np.nan


def _ratio(return_value: Any, drawdown_value: Any) -> float:
    ret = _zero_if_nan(return_value)
    dd = abs(_zero_if_nan(drawdown_value))
    return ret / dd if dd else np.nan


def _percent_rank(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    if numeric.dropna().empty:
        return pd.Series([0.0] * len(series), index=series.index)
    return numeric.rank(pct=True).fillna(0.0)


def _zero_if_nan(value: Any) -> float:
    return 0.0 if pd.isna(value) else float(value)
