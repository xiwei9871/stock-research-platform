from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from stock_research.mid_trend_bad_rebalance_state_attribution import (
    FEATURES,
    build_bad_rebalance_state_attribution_from_frames,
)


CANDIDATE_VARIANT = "top5_adaptive_daily_check_max2_v1"


def run_mid_trend_adaptive_bad_buy_attribution(
    *,
    attribution_detail_path: str | Path,
    funnel_detail_path: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    attribution_detail = pd.read_csv(attribution_detail_path, low_memory=False)
    funnel_detail = pd.read_csv(funnel_detail_path, low_memory=False)
    return build_mid_trend_adaptive_bad_buy_attribution_from_frames(
        attribution_detail=attribution_detail,
        funnel_detail=funnel_detail,
        output_dir=output_dir,
    )


def build_mid_trend_adaptive_bad_buy_attribution_from_frames(
    *,
    attribution_detail: pd.DataFrame,
    funnel_detail: pd.DataFrame,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    attribution_for_state = attribution_detail.copy()
    if "bad_rebalance_flag" in attribution_for_state.columns:
        attribution_for_state["bad_rebalance_flag"] = True
    enriched = build_bad_rebalance_state_attribution_from_frames(
        attribution_detail=attribution_for_state,
        funnel_detail=funnel_detail,
    )
    detail = _adaptive_detail(enriched["detail"])
    bad_buy_detail = _bad_buy_detail(detail)
    feature_contrast = _feature_contrast(detail, bad_buy_detail)
    report = _render_report(bad_buy_detail, feature_contrast)
    result: dict[str, Any] = {
        "bad_buy_detail": bad_buy_detail,
        "feature_contrast": feature_contrast,
        "report": report,
        "paths": {},
    }
    if output_dir is not None:
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        paths = {
            "bad_buy_detail": output / "mid_trend_adaptive_bad_buy_detail.csv",
            "feature_contrast": output / "mid_trend_adaptive_bad_buy_feature_contrast.csv",
            "report": output / "mid_trend_adaptive_bad_buy_attribution_report.md",
        }
        bad_buy_detail.to_csv(paths["bad_buy_detail"], index=False)
        feature_contrast.to_csv(paths["feature_contrast"], index=False)
        paths["report"].write_text(report, encoding="utf-8")
        result["paths"] = {key: str(value) for key, value in paths.items()}
    return result


def _adaptive_detail(detail: pd.DataFrame) -> pd.DataFrame:
    if detail.empty:
        return detail
    frame = detail.copy()
    frame["variant_name"] = frame["variant_name"].astype(str)
    frame = frame[frame["variant_name"].eq(CANDIDATE_VARIANT)].copy()
    if frame.empty:
        return frame
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="coerce").dt.date.astype(str)
    frame["bad_buy_label"] = frame.get("bad_rebalance_reasons", "").astype(str).str.contains("bad_buy", na=False)
    bought_return = pd.to_numeric(frame.get("bought_next_10d_return"), errors="coerce")
    frame["bad_buy_label"] = frame["bad_buy_label"] | bought_return.le(-0.05)
    frame["bought_high_volatility"] = pd.to_numeric(frame.get("bought_volatility_20_score"), errors="coerce").ge(85)
    frame["bought_poor_drawdown_quality"] = pd.to_numeric(frame.get("bought_max_drawdown_20_score"), errors="coerce").le(45)
    frame["bought_low_trend_quality"] = pd.to_numeric(frame.get("bought_trend_r2_20_score"), errors="coerce").lt(65)
    frame["bought_overheated_return"] = pd.to_numeric(frame.get("bought_ret_20_score"), errors="coerce").ge(90)
    for column in [
        "bad_buy_label",
        "bought_high_volatility",
        "bought_poor_drawdown_quality",
        "bought_low_trend_quality",
        "bought_overheated_return",
    ]:
        frame[column] = frame[column].astype(object)
    return frame


def _bad_buy_detail(detail: pd.DataFrame) -> pd.DataFrame:
    if detail.empty:
        return detail
    result = detail[detail["bad_buy_label"].astype(bool)].copy()
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
        "bought_overheated",
        "bought_weak_mainline",
        "bought_high_volatility",
        "bought_poor_drawdown_quality",
        "bought_low_trend_quality",
        "bought_overheated_return",
    ]
    for feature in FEATURES:
        keep.append(f"bought_{feature}")
    keep.extend(
        [
            "bought_mid_trend_layer",
            "bought_industry_name",
            "bought_market_regime",
            "bought_mainline_status",
            "bought_mainline_context",
        ]
    )
    keep = [column for column in keep if column in result.columns]
    return result[keep].sort_values(["bought_next_10d_return", "replacement_alpha_10d"], ascending=[True, True])


def _feature_contrast(detail: pd.DataFrame, bad_buy_detail: pd.DataFrame) -> pd.DataFrame:
    if detail.empty:
        return pd.DataFrame()
    groups = {
        "adaptive_bad_buy": detail[detail["bad_buy_label"].astype(bool)].copy(),
        "adaptive_other_buys": detail[~detail["bad_buy_label"].astype(bool)].copy(),
    }
    rows = []
    for group_name, group in groups.items():
        row: dict[str, Any] = {"group": group_name, "sample_count": int(len(group))}
        if not group.empty:
            row["avg_bought_next_10d_return"] = _mean(group.get("bought_next_10d_return"))
            row["avg_replacement_alpha_10d"] = _mean(group.get("replacement_alpha_10d"))
            row["bought_weak_mainline_rate"] = _mean(group.get("bought_weak_mainline"))
            row["bought_overheated_rate"] = _mean(group.get("bought_overheated"))
            row["bought_high_volatility_rate"] = _mean(group.get("bought_high_volatility"))
            row["bought_poor_drawdown_quality_rate"] = _mean(group.get("bought_poor_drawdown_quality"))
            row["bought_low_trend_quality_rate"] = _mean(group.get("bought_low_trend_quality"))
            row["bought_overheated_return_rate"] = _mean(group.get("bought_overheated_return"))
            for feature in FEATURES:
                row[f"avg_bought_{feature}"] = _mean(group.get(f"bought_{feature}"))
        rows.append(row)
    result = pd.DataFrame(rows)
    if not result.empty and not bad_buy_detail.empty:
        result["bad_buy_sample_share"] = len(bad_buy_detail) / max(1, len(detail))
    return result


def _mean(series: Any) -> float:
    if series is None:
        return np.nan
    values = pd.Series(series)
    if values.dtype == object:
        values = values.map(lambda value: 1.0 if value is True else 0.0 if value is False else value)
    values = pd.to_numeric(values, errors="coerce").dropna()
    return float(values.mean()) if not values.empty else np.nan


def _render_report(bad_buy_detail: pd.DataFrame, feature_contrast: pd.DataFrame) -> str:
    worst = bad_buy_detail.head(30) if not bad_buy_detail.empty else bad_buy_detail
    columns = [
        "trade_date",
        "bought_asset_id",
        "bought_next_10d_return",
        "replacement_alpha_10d",
        "bad_rebalance_reasons",
        "bought_weak_mainline",
        "bought_high_volatility",
        "bought_poor_drawdown_quality",
        "bought_low_trend_quality",
        "bought_ret_20_score",
        "bought_volatility_20_score",
        "bought_max_drawdown_20_score",
        "bought_industry_mainline_score_v1",
    ]
    columns = [column for column in columns if column in worst.columns]
    lines = [
        "# Mid Trend Adaptive Bad-Buy Attribution",
        "",
        "## 1. Scope",
        "只分析 top5_adaptive_daily_check_max2_v1 的坏买入样本，不新增交易规则，不生成交易建议。",
        "",
        "## 2. Feature Contrast",
        feature_contrast.to_markdown(index=False) if not feature_contrast.empty else "No feature contrast rows.",
        "",
        "## 3. Worst Bad Buys",
        worst[columns].to_markdown(index=False) if not worst.empty else "No bad-buy rows.",
    ]
    return "\n".join(lines).rstrip() + "\n"
