from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import pandas as pd


TEMPLATE_COLUMNS = [
    "time_series_momentum_template",
    "relative_strength_template",
    "dual_momentum_template",
    "minervini_like_template",
    "stage2_breakout_template",
    "pullback_reacceleration_template",
]
TREND_METRICS = [
    "future_10d_return",
    "future_20d_return",
    "future_30d_return",
    "future_40d_return",
    "future_60d_return",
    "future_20d_max_drawdown",
    "future_60d_max_drawdown",
    "max_return_within_60d",
    "hit_double_within_60d",
]


def run_trend_discovery_template_validation(
    *,
    detail_path: str | Path,
    output_dir: str | Path,
    strong_winner_path: str | Path | None = None,
) -> dict[str, Any]:
    detail = pd.read_csv(detail_path, low_memory=False)
    strong_winners = (
        pd.read_csv(strong_winner_path, low_memory=False)
        if strong_winner_path and Path(strong_winner_path).exists()
        else None
    )
    return build_trend_discovery_template_validation(
        detail=detail,
        strong_winners=strong_winners,
        output_dir=output_dir,
    )


def build_trend_discovery_template_validation(
    *,
    detail: pd.DataFrame,
    strong_winners: pd.DataFrame | None = None,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    warnings: list[str] = []
    enriched = _build_template_detail(detail, warnings)
    summary = _template_summary(enriched)
    strong_winner_capture = _strong_winner_capture(enriched, strong_winners)
    recommendations = _recommendations(summary, strong_winner_capture)
    report = _render_report(summary, strong_winner_capture, recommendations, warnings)

    result: dict[str, Any] = {
        "detail": enriched,
        "summary": summary,
        "strong_winner_capture": strong_winner_capture,
        "recommendations": recommendations,
        "report": report,
        "warnings": warnings,
        "paths": {},
    }
    if output_dir is not None:
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        paths = {
            "detail": output / "trend_discovery_template_detail.csv",
            "summary": output / "trend_discovery_template_effectiveness.csv",
            "strong_winner_capture": output / "trend_discovery_template_strong_winner_capture.csv",
            "recommendations": output / "trend_discovery_template_recommendations.csv",
            "report": output / "trend_discovery_template_validation_report.md",
        }
        enriched.to_csv(paths["detail"], index=False)
        summary.to_csv(paths["summary"], index=False)
        strong_winner_capture.to_csv(paths["strong_winner_capture"], index=False)
        recommendations.to_csv(paths["recommendations"], index=False)
        paths["report"].write_text(report, encoding="utf-8")
        result["paths"] = {key: str(value) for key, value in paths.items()}
    return result


def _build_template_detail(detail: pd.DataFrame, warnings: list[str]) -> pd.DataFrame:
    frame = detail.copy()
    for column in [
        "score_rank",
        "amount_vs_20d",
        "volatility_5d",
        "high_to_close_drawdown",
        "sector_strength_rank",
        *TREND_METRICS,
    ]:
        if column not in frame.columns:
            frame[column] = pd.NA
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    for column in [
        "watchlist_review_layer",
        "watch_group",
        "event_structure",
        "mainline_context",
        "sector_strength_bucket",
        "fundamental_quality_bucket",
    ]:
        if column not in frame.columns:
            frame[column] = ""
            warnings.append(f"missing_{column}")

    components = _score_component_frame(frame)
    frame = pd.concat([frame.reset_index(drop=True), components.reset_index(drop=True)], axis=1)
    trend_universe = frame["watchlist_review_layer"].eq("mid_term_trend_watch")
    mainline = frame["mainline_context"].eq("mainline")
    strong_sector = frame["sector_strength_bucket"].isin(["top_10", "top_30"]) | frame["sector_strength_rank"].le(30)
    clean_fundamental = frame["fundamental_quality_bucket"].isin(
        ["expectation_growth", "cyclical_or_turnaround", "clean_or_unknown"]
    )
    no_hard_fade = frame["high_to_close_drawdown"].fillna(0.0).le(0.08)
    moderate_volume = frame["amount_vs_20d"].between(1.0, 3.5, inclusive="both")
    low_to_mid_volatility = frame["volatility_5d"].fillna(0.0).le(0.06)
    relative_strength = frame["score_rank"].le(50) | frame["stock_excess_ret_20_score"].ge(75)
    absolute_momentum = (
        (frame["ret_20_score"].ge(65) | frame["ret_60_score"].ge(65))
        & frame["ma20_slope_score"].ge(60)
        & frame["ma60_slope_score"].ge(45)
    )
    stable_trend = frame["trend_r2_20_score"].ge(60)
    low_drawdown_score = frame["max_drawdown_20_score"].ge(55)

    frame["time_series_momentum_template"] = trend_universe & absolute_momentum & stable_trend
    frame["relative_strength_template"] = trend_universe & mainline & strong_sector & relative_strength
    frame["dual_momentum_template"] = (
        frame["time_series_momentum_template"] & frame["relative_strength_template"]
    )
    frame["minervini_like_template"] = (
        frame["dual_momentum_template"] & clean_fundamental & no_hard_fade & low_drawdown_score
    )
    frame["stage2_breakout_template"] = (
        trend_universe
        & mainline
        & strong_sector
        & moderate_volume
        & no_hard_fade
        & frame["ret_20_score"].ge(60)
        & frame["ret_60_score"].between(45, 85, inclusive="both")
    )
    frame["pullback_reacceleration_template"] = (
        trend_universe
        & mainline
        & strong_sector
        & frame["event_structure"].isin(["trend_continuation_candidate", "weak_to_strong_candidate"])
        & low_to_mid_volatility
        & no_hard_fade
        & frame["momentum_20_5_score"].ge(55)
    )
    frame["template_hit_count"] = frame[TEMPLATE_COLUMNS].sum(axis=1).astype(int)
    frame["matched_templates"] = frame[TEMPLATE_COLUMNS].apply(
        lambda row: ",".join([column for column, hit in row.items() if bool(hit)]),
        axis=1,
    )
    return frame


def _score_component_frame(frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, float | None]] = []
    for raw in frame.get("score_components", pd.Series([{}] * len(frame), index=frame.index)):
        parsed = _parse_components(raw)
        rows.append(
            {
                "ret_20_score": _float_or_none(parsed.get("ret_20_score")),
                "ret_60_score": _float_or_none(parsed.get("ret_60_score")),
                "ma20_slope_score": _float_or_none(parsed.get("ma20_slope_score")),
                "ma60_slope_score": _float_or_none(parsed.get("ma60_slope_score")),
                "trend_r2_20_score": _float_or_none(parsed.get("trend_r2_20_score")),
                "momentum_20_5_score": _float_or_none(parsed.get("momentum_20_5_score")),
                "sector_ret_20_score": _float_or_none(parsed.get("sector_ret_20_score")),
                "stock_excess_ret_20_score": _float_or_none(parsed.get("stock_excess_ret_20_score")),
                "max_drawdown_20_score": _float_or_none(parsed.get("max_drawdown_20_score")),
            }
        )
    component_frame = pd.DataFrame(rows)
    for column in component_frame.columns:
        component_frame[column] = pd.to_numeric(component_frame[column], errors="coerce").fillna(50.0)
    return component_frame


def _parse_components(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        parsed = ast.literal_eval(value)
    except (ValueError, SyntaxError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _template_summary(frame: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for template in TEMPLATE_COLUMNS:
        subset = frame[frame[template]]
        rows.append(_metric_row(subset, template_name=template, template_definition=_template_definition(template)))
    return pd.DataFrame(rows).sort_values(["sample_count", "future_60d_return_mean"], ascending=[False, False])


def _metric_row(frame: pd.DataFrame, *, template_name: str, template_definition: str) -> dict[str, Any]:
    row: dict[str, Any] = {
        "template_name": template_name,
        "template_definition": template_definition,
        "sample_count": len(frame),
    }
    for metric in TREND_METRICS:
        column = _metric_name(metric)
        row[column] = pd.to_numeric(frame.get(metric, pd.Series(dtype=float)), errors="coerce").mean()
    return row


def _strong_winner_capture(frame: pd.DataFrame, strong_winners: pd.DataFrame | None) -> pd.DataFrame:
    if strong_winners is None or strong_winners.empty or "asset_id" not in strong_winners.columns:
        return pd.DataFrame(
            [
                {
                    "template_name": template,
                    "captured_strong_winner_count": 0,
                    "total_strong_winner_count": 0,
                    "capture_rate": 0.0,
                }
                for template in TEMPLATE_COLUMNS
            ]
        )
    winner_assets = set(str(value) for value in strong_winners["asset_id"].dropna().unique())
    total = len(winner_assets)
    rows = []
    for template in TEMPLATE_COLUMNS:
        hit_assets = set(str(value) for value in frame.loc[frame[template], "asset_id"].dropna().unique())
        captured = len(winner_assets & hit_assets)
        rows.append(
            {
                "template_name": template,
                "captured_strong_winner_count": captured,
                "total_strong_winner_count": total,
                "capture_rate": captured / total if total else 0.0,
            }
        )
    return pd.DataFrame(rows).sort_values(["capture_rate", "captured_strong_winner_count"], ascending=False)


def _recommendations(summary: pd.DataFrame, capture: pd.DataFrame) -> pd.DataFrame:
    merged = summary.merge(capture, on="template_name", how="left")
    rows = []
    for _, row in merged.iterrows():
        sample_count = int(row.get("sample_count") or 0)
        future_60d = _float_or_none(row.get("future_60d_return_mean")) or 0.0
        drawdown_60d = _float_or_none(row.get("future_60d_max_drawdown_mean")) or 0.0
        hit_double = _float_or_none(row.get("hit_double_within_60d_rate")) or 0.0
        if sample_count >= 30 and future_60d > 0.08 and drawdown_60d > -0.16:
            action = "promote_for_v2_candidate"
            confidence = "medium"
        elif sample_count >= 30 and (future_60d > 0.05 or hit_double > 0.05):
            action = "keep_for_further_validation"
            confidence = "low_medium"
        elif sample_count < 30:
            action = "needs_more_samples"
            confidence = "low"
        else:
            action = "deprioritize"
            confidence = "low"
        rows.append(
            {
                "template_name": row["template_name"],
                "recommended_action": action,
                "confidence_level": confidence,
                "evidence_summary": (
                    f"sample={sample_count}, 60d={future_60d:.2%}, "
                    f"dd60={drawdown_60d:.2%}, hit_double={hit_double:.2%}"
                ),
            }
        )
    return pd.DataFrame(rows)


def _render_report(
    summary: pd.DataFrame,
    capture: pd.DataFrame,
    recommendations: pd.DataFrame,
    warnings: list[str],
) -> str:
    lines = [
        "# Trend Discovery Template Validation v1",
        "",
        "## 1. Scope",
        "验证成熟趋势模板的代理规则是否能解释 10/20/30/40/60d 趋势表现；不接入 watchlist 生成、不改 stock_score。",
        "",
        "## 2. Warnings",
        *([f"- {warning}" for warning in warnings] or ["- none"]),
        "",
        "## 3. Template Effectiveness",
        summary.to_markdown(index=False),
        "",
        "## 4. Strong Winner Capture",
        capture.to_markdown(index=False),
        "",
        "## 5. Recommendations",
        recommendations.to_markdown(index=False),
        "",
        "## 6. Interpretation",
        "这些模板使用当前 detail 和 score_components 中已有字段做代理验证。后续只有表现较好的模板才值得进一步改造成正式趋势观察规则。",
    ]
    return "\n".join(lines) + "\n"


def _template_definition(template: str) -> str:
    definitions = {
        "time_series_momentum_template": "absolute momentum + MA slope proxy + trend stability",
        "relative_strength_template": "mainline sector + top sector rank + cross-sectional strength",
        "dual_momentum_template": "time-series momentum AND relative strength",
        "minervini_like_template": "dual momentum + acceptable drawdown + non-hard-risk fundamental proxy",
        "stage2_breakout_template": "mainline + sector strength + moderate volume + emerging momentum",
        "pullback_reacceleration_template": "trend candidate + moderate volatility + no hard fade + reacceleration proxy",
    }
    return definitions.get(template, template)


def _metric_name(column: str) -> str:
    if column == "hit_double_within_60d":
        return "hit_double_within_60d_rate"
    return f"{column}_mean"


def _float_or_none(value: Any) -> float | None:
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
