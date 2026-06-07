from __future__ import annotations

from pathlib import Path
from typing import Any

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


def run_mid_trend_drawdown_control_validation(
    *,
    funnel_detail_path: str | Path,
    baseline_top10_path: str | Path,
    output_dir: str | Path,
    top_n: int = 10,
) -> dict[str, Any]:
    funnel_detail = pd.read_csv(funnel_detail_path, low_memory=False)
    baseline_top10 = pd.read_csv(baseline_top10_path, low_memory=False)
    return build_mid_trend_drawdown_control_validation_from_frames(
        funnel_detail=funnel_detail,
        baseline_top10=baseline_top10,
        top_n=top_n,
        output_dir=output_dir,
    )


def build_mid_trend_drawdown_control_validation_from_frames(
    *,
    funnel_detail: pd.DataFrame,
    baseline_top10: pd.DataFrame,
    top_n: int = 10,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    detail = _normalize(funnel_detail)
    baseline = _normalize(baseline_top10)
    variants = _build_variants(detail=detail, baseline=baseline, top_n=top_n)
    effectiveness = _effectiveness(variants)
    recommendations = _recommendations(effectiveness)
    report = _render_report(effectiveness, recommendations)

    result: dict[str, Any] = {
        "variant_detail": variants,
        "effectiveness": effectiveness,
        "recommendations": recommendations,
        "report": report,
        "paths": {},
    }
    if output_dir is not None:
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        paths = {
            "variant_detail": output / "mid_trend_drawdown_control_variant_detail.csv",
            "effectiveness": output / "mid_trend_drawdown_control_effectiveness.csv",
            "recommendations": output / "mid_trend_drawdown_control_recommendations.csv",
            "report": output / "mid_trend_drawdown_control_report.md",
        }
        variants.to_csv(paths["variant_detail"], index=False)
        effectiveness.to_csv(paths["effectiveness"], index=False)
        recommendations.to_csv(paths["recommendations"], index=False)
        paths["report"].write_text(report, encoding="utf-8")
        result["paths"] = {key: str(value) for key, value in paths.items()}
    return result


def _normalize(frame: pd.DataFrame) -> pd.DataFrame:
    normalized = frame.copy()
    for column in [
        "trade_date",
        "asset_id",
        "ts_code",
        "stock_name",
        "mid_trend_layer",
        "mid_trend_funnel_score",
        "score_rank",
        "ret_20_score",
        "ret_60_score",
        "ma20_slope_score",
        "ma60_slope_score",
        "trend_r2_20_score",
        "momentum_20_5_score",
        "stock_excess_ret_20_score",
        "sector_ret_20_score",
        "max_drawdown_20_score",
        "volatility_20_score",
        "atr_pct_score",
    ]:
        if column not in normalized.columns:
            normalized[column] = np.nan
    normalized["trade_date"] = pd.to_datetime(normalized["trade_date"], errors="coerce")
    normalized["asset_id"] = normalized["asset_id"].astype(str)
    for column in [
        "mid_trend_funnel_score",
        "score_rank",
        "ret_20_score",
        "ret_60_score",
        "ma20_slope_score",
        "ma60_slope_score",
        "trend_r2_20_score",
        "momentum_20_5_score",
        "stock_excess_ret_20_score",
        "sector_ret_20_score",
        "max_drawdown_20_score",
        "volatility_20_score",
        "atr_pct_score",
        *METRICS,
    ]:
        if column not in normalized.columns:
            normalized[column] = np.nan
        normalized[column] = pd.to_numeric(normalized[column], errors="coerce")
    normalized["hit_double_within_60d"] = normalized["hit_double_within_60d"].fillna(0).astype(bool)
    return normalized.dropna(subset=["trade_date", "asset_id"]).copy()


def _build_variants(*, detail: pd.DataFrame, baseline: pd.DataFrame, top_n: int) -> pd.DataFrame:
    variant_frames = [
        _tag_variant(_rank_top_n(baseline, top_n), "baseline_top10"),
        _tag_variant(_select_variant(detail, top_n, lambda frame: frame), "refit_top10_from_funnel"),
        _tag_variant(
            _select_variant(detail, top_n, lambda frame: frame[~frame["mid_trend_layer"].eq("high_elasticity_watch")]),
            "no_high_elasticity_top10",
        ),
        _tag_variant(_select_high_elasticity_quota(detail, top_n, quota=1), "high_elasticity_quota_1_top10"),
        _tag_variant(
            _select_variant(detail, top_n, lambda frame: frame[frame["max_drawdown_20_score"] >= 60]),
            "max_drawdown_floor_60_top10",
        ),
        _tag_variant(
            _select_variant(detail, top_n, lambda frame: frame[frame["volatility_20_score"] >= 20]),
            "volatility_floor_20_top10",
        ),
        _tag_variant(
            _select_variant(detail, top_n, lambda frame: frame[frame["atr_pct_score"] >= 20]),
            "atr_floor_20_top10",
        ),
        _tag_variant(_select_variant(detail, top_n, _vcp_like), "vcp_like_contraction_top10"),
        _tag_variant(
            _select_variant(detail, top_n, lambda frame: _vcp_like(frame)[lambda x: x["max_drawdown_20_score"] >= 60]),
            "vcp_like_drawdown_floor_top10",
        ),
    ]
    output = pd.concat(variant_frames, ignore_index=True) if variant_frames else detail.head(0).copy()
    if output.empty:
        output["variant_name"] = pd.Series(dtype=str)
    return output


def _select_variant(detail: pd.DataFrame, top_n: int, filter_func) -> pd.DataFrame:
    if detail.empty or top_n <= 0:
        return detail.head(0).copy()
    frames = []
    for _, group in detail.groupby("trade_date", sort=True):
        eligible = filter_func(group)
        selected = _rank_top_n(eligible, top_n)
        frames.append(selected)
    return pd.concat(frames, ignore_index=True) if frames else detail.head(0).copy()


def _rank_top_n(frame: pd.DataFrame, top_n: int) -> pd.DataFrame:
    if frame.empty or top_n <= 0:
        return frame.head(0).copy()
    ranked = frame.sort_values(["trade_date", "mid_trend_funnel_score", "score_rank"], ascending=[True, False, True]).copy()
    return ranked.groupby("trade_date", group_keys=False).head(top_n).reset_index(drop=True)


def _select_high_elasticity_quota(detail: pd.DataFrame, top_n: int, *, quota: int) -> pd.DataFrame:
    frames = []
    for _, group in detail.groupby("trade_date", sort=True):
        high = group[group["mid_trend_layer"].eq("high_elasticity_watch")].sort_values(
            ["mid_trend_funnel_score", "score_rank"], ascending=[False, True]
        )
        rest = group[~group["mid_trend_layer"].eq("high_elasticity_watch")].sort_values(
            ["mid_trend_funnel_score", "score_rank"], ascending=[False, True]
        )
        selected = pd.concat([high.head(quota), rest], ignore_index=False).sort_values(
            ["mid_trend_funnel_score", "score_rank"], ascending=[False, True]
        )
        frames.append(selected.head(top_n))
    return pd.concat(frames, ignore_index=True) if frames else detail.head(0).copy()


def _vcp_like(frame: pd.DataFrame) -> pd.DataFrame:
    return frame[
        (frame["ret_60_score"] >= 80)
        & (frame["ma20_slope_score"] >= 75)
        & (frame["ma60_slope_score"] >= 75)
        & (frame["trend_r2_20_score"] >= 65)
        & (frame["max_drawdown_20_score"] >= 50)
        & (frame["volatility_20_score"] >= 15)
        & (frame["atr_pct_score"] >= 15)
    ].copy()


def _tag_variant(frame: pd.DataFrame, variant_name: str) -> pd.DataFrame:
    tagged = frame.copy()
    tagged["variant_name"] = variant_name
    tagged["variant_rank"] = tagged.groupby("trade_date").cumcount() + 1 if not tagged.empty else []
    return tagged


def _effectiveness(variants: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for variant_name, group in variants.groupby("variant_name", sort=True):
        row = {
            "variant_name": variant_name,
            "sample_count": int(len(group)),
            "unique_asset_count": int(group["asset_id"].nunique()),
            "avg_high_elasticity_count_per_day": _avg_layer_count(group, "high_elasticity_watch"),
        }
        for horizon in [20, 30, 40, 60]:
            column = f"future_{horizon}d_return"
            values = pd.to_numeric(group[column], errors="coerce")
            row[f"avg_future_{horizon}d_return"] = float(values.mean()) if not values.dropna().empty else np.nan
            row[f"win_rate_{horizon}d"] = float((values.dropna() > 0).mean()) if not values.dropna().empty else np.nan
        row["avg_future_60d_max_drawdown"] = _mean(group["future_60d_max_drawdown"])
        row["avg_max_return_within_60d"] = _mean(group["max_return_within_60d"])
        row["hit_double_within_60d_rate"] = float(group["hit_double_within_60d"].mean()) if len(group) else np.nan
        row["return_drawdown_ratio_60d"] = _return_drawdown_ratio(
            row["avg_future_60d_return"], row["avg_future_60d_max_drawdown"]
        )
        rows.append(row)
    return pd.DataFrame(rows).sort_values(
        ["return_drawdown_ratio_60d", "avg_future_60d_return"], ascending=[False, False]
    )


def _recommendations(effectiveness: pd.DataFrame) -> pd.DataFrame:
    if effectiveness.empty:
        return pd.DataFrame(columns=["recommendation", "evidence_summary", "next_action"])
    baseline = _row(effectiveness, "baseline_top10")
    rows = []
    for candidate in effectiveness.to_dict("records"):
        if candidate["variant_name"] == "baseline_top10":
            continue
        return_delta = _num(candidate.get("avg_future_60d_return")) - _num(baseline.get("avg_future_60d_return"))
        drawdown_delta = _num(candidate.get("avg_future_60d_max_drawdown")) - _num(
            baseline.get("avg_future_60d_max_drawdown")
        )
        if drawdown_delta > 0 and return_delta > -0.02:
            recommendation = "promote_for_shadow_review"
        elif return_delta > 0 and drawdown_delta >= -0.02:
            recommendation = "watch_return_improver"
        else:
            recommendation = "keep_diagnostic_only"
        rows.append(
            {
                "variant_name": candidate["variant_name"],
                "recommendation": recommendation,
                "return_delta_vs_baseline": return_delta,
                "drawdown_delta_vs_baseline": drawdown_delta,
                "evidence_summary": (
                    f"60d={_num(candidate.get('avg_future_60d_return')):.2%}; "
                    f"dd60={_num(candidate.get('avg_future_60d_max_drawdown')):.2%}; "
                    f"ratio={_num(candidate.get('return_drawdown_ratio_60d')):.2f}"
                ),
                "next_action": "review as shadow rule; do not change production Top10 until rolling validation passes",
            }
        )
    return pd.DataFrame(rows)


def _render_report(effectiveness: pd.DataFrame, recommendations: pd.DataFrame) -> str:
    lines = [
        "# Mid Trend Drawdown Control Validation v1",
        "",
        "## 1. Scope",
        "验证中线 Top10 的回撤控制候选规则。只看 20/30/40/60d，不接短线、不生成交易建议。",
        "",
        "## 2. Variant Effectiveness",
        effectiveness.to_markdown(index=False) if not effectiveness.empty else "No variant rows.",
        "",
        "## 3. Recommendations",
        recommendations.to_markdown(index=False) if not recommendations.empty else "No recommendations.",
        "",
        "## 4. Interpretation",
        "- 回撤改善优先看 `avg_future_60d_max_drawdown` 是否更接近 0。",
        "- 收益保留优先看 60d return 和 return/drawdown ratio。",
        "- 这些规则只进入 shadow review，不直接改变 Top10。",
    ]
    return "\n".join(lines).rstrip() + "\n"


def _avg_layer_count(group: pd.DataFrame, layer: str) -> float:
    if group.empty:
        return 0.0
    counts = group.groupby("trade_date")["mid_trend_layer"].apply(lambda values: int((values == layer).sum()))
    return float(counts.mean()) if not counts.empty else 0.0


def _mean(series: pd.Series) -> float:
    values = pd.to_numeric(series, errors="coerce").dropna()
    return float(values.mean()) if not values.empty else np.nan


def _return_drawdown_ratio(return_value: Any, drawdown_value: Any) -> float:
    ret = _num(return_value)
    dd = abs(_num(drawdown_value))
    return ret / dd if dd else np.nan


def _row(frame: pd.DataFrame, variant_name: str) -> pd.Series:
    rows = frame[frame["variant_name"].eq(variant_name)]
    return rows.iloc[0] if not rows.empty else pd.Series(dtype=float)


def _num(value: Any) -> float:
    if pd.isna(value):
        return 0.0
    return float(value)
