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
PREFERRED_MID_TREND_INDUSTRIES = {
    "计算机、通信和其他电子设备制造业",
    "电气机械和器材制造业",
    "有色金属冶炼和压延加工业",
    "专用设备制造业",
    "通用设备制造业",
    "医药制造业",
}
WEAK_STABILITY_INDUSTRIES = {
    "汽车制造业",
    "互联网和相关服务",
    "软件和信息技术服务业",
    "化学原料和化学制品制造业",
}


def run_mid_trend_shadow_stability_review(
    *,
    funnel_detail_path: str | Path,
    baseline_top10_path: str | Path,
    output_dir: str | Path,
    top_n: int = 10,
) -> dict[str, Any]:
    funnel_detail = pd.read_csv(funnel_detail_path, low_memory=False)
    baseline_top10 = pd.read_csv(baseline_top10_path, low_memory=False)
    return build_mid_trend_shadow_stability_review_from_frames(
        funnel_detail=funnel_detail,
        baseline_top10=baseline_top10,
        top_n=top_n,
        output_dir=output_dir,
    )


def build_mid_trend_shadow_stability_review_from_frames(
    *,
    funnel_detail: pd.DataFrame,
    baseline_top10: pd.DataFrame,
    top_n: int = 10,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    detail = _normalize(funnel_detail)
    baseline = _normalize(baseline_top10)
    variants = _build_variants(detail, baseline, top_n=top_n)
    by_period = _group_summary(variants, "period")
    by_regime = _group_summary(variants, "market_regime")
    by_industry = _group_summary(variants, "industry_name")
    by_layer = _group_summary(variants, "mid_trend_layer")
    decision = _decision_summary(by_period, by_regime)
    report = _render_report(by_period, by_regime, by_industry, by_layer, decision)

    result: dict[str, Any] = {
        "variant_detail": variants,
        "by_period": by_period,
        "by_regime": by_regime,
        "by_industry": by_industry,
        "by_layer": by_layer,
        "decision": decision,
        "report": report,
        "paths": {},
    }
    if output_dir is not None:
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        paths = {
            "variant_detail": output / "mid_trend_shadow_stability_variant_detail.csv",
            "by_period": output / "mid_trend_shadow_stability_by_period.csv",
            "by_regime": output / "mid_trend_shadow_stability_by_regime.csv",
            "by_industry": output / "mid_trend_shadow_stability_by_industry.csv",
            "by_layer": output / "mid_trend_shadow_stability_by_layer.csv",
            "decision": output / "mid_trend_shadow_stability_decision.csv",
            "report": output / "mid_trend_shadow_stability_report.md",
        }
        variants.to_csv(paths["variant_detail"], index=False)
        by_period.to_csv(paths["by_period"], index=False)
        by_regime.to_csv(paths["by_regime"], index=False)
        by_industry.to_csv(paths["by_industry"], index=False)
        by_layer.to_csv(paths["by_layer"], index=False)
        decision.to_csv(paths["decision"], index=False)
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
        "trend_r2_20_score",
        "market_regime",
        "industry_name",
        "mainline_status",
        "mainline_context",
        "industry_mainline_score_v1",
        "ret_20_score",
        "max_drawdown_20_score",
    ]:
        if column not in normalized.columns:
            normalized[column] = ""
    normalized["trade_date"] = pd.to_datetime(normalized["trade_date"], errors="coerce")
    normalized["asset_id"] = normalized["asset_id"].astype(str)
    normalized["market_regime"] = normalized["market_regime"].fillna("unknown").replace("", "unknown")
    normalized["industry_name"] = normalized["industry_name"].fillna("unknown").replace("", "unknown")
    normalized["mainline_status"] = normalized["mainline_status"].fillna("unknown").replace("", "unknown")
    normalized["mainline_context"] = normalized["mainline_context"].fillna("unknown").replace("", "unknown")
    for column in [
        "mid_trend_funnel_score",
        "score_rank",
        "volatility_20_score",
        "trend_r2_20_score",
        "industry_mainline_score_v1",
        "ret_20_score",
        "max_drawdown_20_score",
        *METRICS,
    ]:
        if column not in normalized.columns:
            normalized[column] = np.nan
        normalized[column] = pd.to_numeric(normalized[column], errors="coerce")
    normalized["hit_double_within_60d"] = normalized["hit_double_within_60d"].fillna(0).astype(bool)
    normalized["period"] = normalized["trade_date"].map(_period_label)
    return normalized.dropna(subset=["trade_date", "asset_id"]).copy()


def _build_variants(detail: pd.DataFrame, baseline: pd.DataFrame, *, top_n: int) -> pd.DataFrame:
    baseline_variant = _tag(_top_n_by_day(baseline, top_n), "baseline_top10")
    base_shadow = detail[(detail["volatility_20_score"] >= 15) & (detail["trend_r2_20_score"] >= 80)]
    positive_mainline = _positive_mainline_mask(base_shadow)
    variants = [
        baseline_variant,
        _tag(_top_n_by_day(base_shadow, top_n), "vol15_trend80_shadow"),
        _tag(
            _top_n_by_day(
                base_shadow[
                    base_shadow["market_regime"].astype(str).eq("mainline")
                    & positive_mainline
                ],
                top_n,
            ),
            "context_v2_mainline_quality_shadow",
        ),
        _tag(
            _top_n_by_day(
                base_shadow[
                    base_shadow["market_regime"].astype(str).eq("rotation")
                    & base_shadow["mid_trend_layer"].astype(str).eq("stable_trend_watch")
                ],
                top_n,
            ),
            "context_v2_rotation_stable_shadow",
        ),
        _tag(
            _top_n_by_day(
                base_shadow[
                    base_shadow["market_regime"].astype(str).isin({"mainline", "rotation", "broad_market"})
                    & positive_mainline
                ],
                top_n,
            ),
            "context_v2_combined_shadow",
        ),
        _tag(
            _structured_top_n_by_day(
                base_shadow[
                    base_shadow["market_regime"].astype(str).isin({"mainline", "rotation", "broad_market"})
                    & positive_mainline
                ],
                top_n,
            ),
            "context_v2_structured_top10_shadow",
        ),
    ]
    return pd.concat(variants, ignore_index=True)


def _positive_mainline_mask(frame: pd.DataFrame) -> pd.Series:
    status = frame["mainline_status"].astype(str)
    context = frame["mainline_context"].astype(str)
    score = pd.to_numeric(frame["industry_mainline_score_v1"], errors="coerce")
    positive_tags = {
        "sustained_mainline",
        "broad_strength",
        "mainline",
        "strong_mainline",
        "healthy_mainline",
    }
    return score.ge(0.45).fillna(False) | status.isin(positive_tags) | context.eq("mainline")


def _structured_top_n_by_day(frame: pd.DataFrame, top_n: int) -> pd.DataFrame:
    if frame.empty or top_n <= 0:
        return frame.head(0).copy()
    picked_frames = []
    for _, group in frame.groupby("trade_date", sort=True):
        picked_frames.append(_structured_top_n_for_day(group, top_n))
    return pd.concat(picked_frames, ignore_index=True) if picked_frames else frame.head(0).copy()


def _structured_top_n_for_day(group: pd.DataFrame, top_n: int) -> pd.DataFrame:
    ordered = group.sort_values(["mid_trend_funnel_score", "score_rank"], ascending=[False, True]).copy()
    weak_cap = max(1, top_n // 10)
    core_quota = max(1, round(top_n * 0.5))
    high_odds_quota = max(1, round(top_n * 0.1))
    selected: list[pd.Series] = []
    selected_indexes: set[Any] = set()
    weak_count = 0

    def try_add(candidates: pd.DataFrame, slot: str, quota: int | None = None) -> None:
        nonlocal weak_count
        added = 0
        for idx, row in candidates.iterrows():
            if idx in selected_indexes:
                continue
            industry = str(row.get("industry_name") or "")
            is_weak = industry in WEAK_STABILITY_INDUSTRIES
            if is_weak and weak_count >= weak_cap:
                continue
            item = row.copy()
            item["structure_slot"] = slot
            selected.append(item)
            selected_indexes.add(idx)
            weak_count += int(is_weak)
            added += 1
            if len(selected) >= top_n or (quota is not None and added >= quota):
                break

    core = ordered[
        ordered["industry_name"].astype(str).isin(PREFERRED_MID_TREND_INDUSTRIES)
        & ordered["mid_trend_layer"].astype(str).isin({"stable_trend_watch", "mainline_momentum_watch"})
    ]
    try_add(core, "preferred_mainline_core", core_quota)

    high_odds = ordered[
        ordered["mid_trend_layer"].astype(str).eq("high_elasticity_watch")
        & pd.to_numeric(ordered["ret_20_score"], errors="coerce").ge(85)
        & pd.to_numeric(ordered["max_drawdown_20_score"], errors="coerce").ge(45)
    ]
    try_add(high_odds, "controlled_high_odds", high_odds_quota)

    stable = ordered[ordered["mid_trend_layer"].astype(str).isin({"stable_trend_watch", "pullback_reacceleration_watch"})]
    try_add(stable, "stable_fill", None)
    if len(selected) < top_n:
        try_add(ordered, "rank_fill", None)

    if not selected:
        return ordered.head(0).copy()
    result = pd.DataFrame(selected).head(top_n).reset_index(drop=True)
    return result


def _top_n_by_day(frame: pd.DataFrame, top_n: int) -> pd.DataFrame:
    if frame.empty or top_n <= 0:
        return frame.head(0).copy()
    ranked = frame.sort_values(["trade_date", "mid_trend_funnel_score", "score_rank"], ascending=[True, False, True])
    return ranked.groupby("trade_date", group_keys=False).head(top_n).reset_index(drop=True)


def _tag(frame: pd.DataFrame, variant_name: str) -> pd.DataFrame:
    tagged = frame.copy()
    tagged["variant_name"] = variant_name
    tagged["variant_rank"] = tagged.groupby("trade_date").cumcount() + 1 if not tagged.empty else []
    return tagged


def _group_summary(frame: pd.DataFrame, group_col: str) -> pd.DataFrame:
    rows = []
    group_cols = ["variant_name", group_col]
    for keys, group in frame.groupby(group_cols, sort=True):
        variant_name, group_value = keys
        row = {
            "variant_name": variant_name,
            group_col: group_value,
            "sample_count": int(len(group)),
            "unique_asset_count": int(group["asset_id"].nunique()),
            "trade_date_count": int(group["trade_date"].nunique()),
        }
        for horizon in [20, 30, 40, 60]:
            values = pd.to_numeric(group[f"future_{horizon}d_return"], errors="coerce").dropna()
            row[f"avg_future_{horizon}d_return"] = float(values.mean()) if not values.empty else np.nan
            row[f"win_rate_{horizon}d"] = float((values > 0).mean()) if not values.empty else np.nan
        row["avg_future_60d_max_drawdown"] = _mean(group["future_60d_max_drawdown"])
        row["avg_max_return_within_60d"] = _mean(group["max_return_within_60d"])
        row["hit_double_within_60d_rate"] = _mean(group["hit_double_within_60d"])
        row["return_drawdown_ratio_60d"] = _ratio(row["avg_future_60d_return"], row["avg_future_60d_max_drawdown"])
        rows.append(row)
    return pd.DataFrame(rows)


def _decision_summary(by_period: pd.DataFrame, by_regime: pd.DataFrame) -> pd.DataFrame:
    rows = []
    baseline_period = by_period[by_period["variant_name"].eq("baseline_top10")]
    for variant_name, group in by_period.groupby("variant_name", sort=True):
        if variant_name == "baseline_top10":
            continue
        merged = group.merge(
            baseline_period,
            on="period",
            suffixes=("_shadow", "_baseline"),
            how="inner",
        )
        period_count = len(merged)
        improved_drawdown = int(
            (merged["avg_future_60d_max_drawdown_shadow"] > merged["avg_future_60d_max_drawdown_baseline"]).sum()
        )
        preserved_return = int(
            (
                merged["avg_future_60d_return_shadow"]
                >= merged["avg_future_60d_return_baseline"] - 0.02
            ).sum()
        )
        regime = by_regime[by_regime["variant_name"].eq(variant_name)]
        avg_return = _mean(regime["avg_future_60d_return"]) if not regime.empty else np.nan
        avg_drawdown = _mean(regime["avg_future_60d_max_drawdown"]) if not regime.empty else np.nan
        review_status = (
            "promote_to_shadow_watch"
            if period_count and improved_drawdown / period_count >= 0.5 and preserved_return / period_count >= 0.5
            else "keep_diagnostic_only"
        )
        rows.append(
            {
                "variant_name": variant_name,
                "period_count": period_count,
                "drawdown_improved_period_count": improved_drawdown,
                "return_preserved_period_count": preserved_return,
                "avg_regime_60d_return": avg_return,
                "avg_regime_60d_max_drawdown": avg_drawdown,
                "review_status": review_status,
                "decision_note": "shadow rule only; no production Top10 change",
            }
        )
    return pd.DataFrame(rows)


def _render_report(
    by_period: pd.DataFrame,
    by_regime: pd.DataFrame,
    by_industry: pd.DataFrame,
    by_layer: pd.DataFrame,
    decision: pd.DataFrame,
) -> str:
    lines = [
        "# Mid Trend Shadow Rule Stability Review v1",
        "",
        "## 1. Scope",
        "`volatility_20_score >= 15 AND trend_r2_20_score >= 80` 的中线稳定性验证；不改变生产 Top10。",
        "",
        "## 2. By Period",
        by_period.to_markdown(index=False) if not by_period.empty else "No period rows.",
        "",
        "## 3. By Regime",
        by_regime.to_markdown(index=False) if not by_regime.empty else "No regime rows.",
        "",
        "## 4. By Industry",
        by_industry.head(30).to_markdown(index=False) if not by_industry.empty else "No industry rows.",
        "",
        "## 5. By Layer",
        by_layer.to_markdown(index=False) if not by_layer.empty else "No layer rows.",
        "",
        "## 6. Decision",
        decision.to_markdown(index=False) if not decision.empty else "No decision rows.",
    ]
    return "\n".join(lines).rstrip() + "\n"


def _period_label(value: pd.Timestamp) -> str:
    if pd.isna(value):
        return "unknown"
    return f"{int(value.year)}Q{int(value.quarter)}"


def _mean(series: Any) -> float:
    values = pd.to_numeric(series, errors="coerce").dropna()
    return float(values.mean()) if not values.empty else np.nan


def _ratio(return_value: Any, drawdown_value: Any) -> float:
    if pd.isna(return_value) or pd.isna(drawdown_value) or float(drawdown_value) == 0:
        return np.nan
    return float(return_value) / abs(float(drawdown_value))
