from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


METRICS = [
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
CANDIDATE_COLUMNS = [
    "v2_final_baseline",
    "v2_1_quality_no_highvol_extremeamount",
    "v2_2_growth_trend_core",
    "v2_2_cyclical_trend_core",
    "v2_2_trend_continuation_boost",
    "v2_2_high_elasticity_shadow",
    "existing_trend_continuation_candidate",
]


def run_trend_discovery_v2_2_replay(
    *,
    v2_detail_path: str | Path,
    output_dir: str | Path,
    strong_winner_path: str | Path | None = None,
) -> dict[str, Any]:
    v2_detail = pd.read_csv(v2_detail_path, low_memory=False)
    strong_winners = (
        pd.read_csv(strong_winner_path, low_memory=False)
        if strong_winner_path and Path(strong_winner_path).exists()
        else None
    )
    return build_trend_discovery_v2_2_replay(
        v2_detail=v2_detail,
        strong_winners=strong_winners,
        output_dir=output_dir,
    )


def build_trend_discovery_v2_2_replay(
    *,
    v2_detail: pd.DataFrame,
    strong_winners: pd.DataFrame | None = None,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    warnings: list[str] = []
    detail = _build_detail(v2_detail, warnings)
    layer_effectiveness = _layer_effectiveness(detail)
    vs_existing = _vs_existing(detail)
    strong_winner_capture = _strong_winner_capture(detail, strong_winners)
    recommendations = _recommendations(layer_effectiveness)
    report = _render_report(
        layer_effectiveness=layer_effectiveness,
        vs_existing=vs_existing,
        strong_winner_capture=strong_winner_capture,
        recommendations=recommendations,
        warnings=warnings,
    )

    result: dict[str, Any] = {
        "detail": detail,
        "layer_effectiveness": layer_effectiveness,
        "vs_existing": vs_existing,
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
            "detail": output / "trend_discovery_v2_2_replay_detail.csv",
            "layer_effectiveness": output / "trend_discovery_v2_2_layer_effectiveness.csv",
            "vs_existing": output / "trend_discovery_v2_2_vs_existing.csv",
            "strong_winner_capture": output / "trend_discovery_v2_2_strong_winner_capture.csv",
            "recommendations": output / "trend_discovery_v2_2_recommendations.csv",
            "report": output / "trend_discovery_v2_2_replay_report.md",
        }
        detail.to_csv(paths["detail"], index=False)
        layer_effectiveness.to_csv(paths["layer_effectiveness"], index=False)
        vs_existing.to_csv(paths["vs_existing"], index=False)
        strong_winner_capture.to_csv(paths["strong_winner_capture"], index=False)
        recommendations.to_csv(paths["recommendations"], index=False)
        paths["report"].write_text(report, encoding="utf-8")
        result["paths"] = {key: str(value) for key, value in paths.items()}
    return result


def _build_detail(frame: pd.DataFrame, warnings: list[str]) -> pd.DataFrame:
    detail = frame.copy()
    for column in METRICS:
        if column not in detail.columns:
            detail[column] = pd.NA
            warnings.append(f"missing_{column}")
        detail[column] = pd.to_numeric(detail[column], errors="coerce")
    for column in [
        "asset_id",
        "ts_code",
        "stock_name",
        "sector_strength_bucket",
        "fundamental_quality_bucket",
        "event_structure",
        "amount_vs_20d_bucket",
        "volatility_5d_bucket",
    ]:
        if column not in detail.columns:
            detail[column] = ""
            warnings.append(f"missing_{column}")
    if "trend_discovery_v2_final_candidate" not in detail.columns:
        detail["trend_discovery_v2_final_candidate"] = False
        warnings.append("missing_trend_discovery_v2_final_candidate")
    detail["trend_discovery_v2_final_candidate"] = detail["trend_discovery_v2_final_candidate"].map(_bool)
    detail["hit_double_within_60d"] = detail["hit_double_within_60d"].map(_bool).astype(float)

    final = detail["trend_discovery_v2_final_candidate"]
    quality = detail["fundamental_quality_bucket"].isin(["expectation_growth", "cyclical_or_turnaround"])
    no_high_vol = ~detail["volatility_5d_bucket"].isin(["high_volatility", "extreme_volatility"])
    no_extreme_amount = ~detail["amount_vs_20d_bucket"].eq("extreme_volume")
    detail["v2_final_baseline"] = final
    detail["v2_1_quality_no_highvol_extremeamount"] = final & quality & no_high_vol & no_extreme_amount
    detail["v2_2_growth_trend_core"] = (
        final
        & detail["fundamental_quality_bucket"].eq("expectation_growth")
        & detail["volatility_5d_bucket"].eq("low_volatility")
        & no_extreme_amount
    )
    detail["v2_2_cyclical_trend_core"] = (
        final
        & detail["fundamental_quality_bucket"].eq("cyclical_or_turnaround")
        & detail["volatility_5d_bucket"].isin(["low_volatility", "mid_volatility"])
        & no_extreme_amount
        & detail["sector_strength_bucket"].isin(["top_10", "top_30"])
    )
    detail["v2_2_trend_continuation_boost"] = (
        detail["v2_1_quality_no_highvol_extremeamount"]
        & detail["event_structure"].eq("trend_continuation_candidate")
    )
    detail["v2_2_high_elasticity_shadow"] = (
        final
        & (
            detail["volatility_5d_bucket"].isin(["high_volatility", "extreme_volatility"])
            | detail["amount_vs_20d_bucket"].eq("extreme_volume")
        )
    )
    detail["existing_trend_continuation_candidate"] = detail["event_structure"].eq("trend_continuation_candidate")
    return detail


def _layer_effectiveness(detail: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(
        [_metric_row(detail[detail[column]], key_name="candidate_set", key_value=column) for column in CANDIDATE_COLUMNS]
    )


def _vs_existing(detail: pd.DataFrame) -> pd.DataFrame:
    rows = []
    existing = detail["existing_trend_continuation_candidate"]
    for column in [
        "v2_1_quality_no_highvol_extremeamount",
        "v2_2_growth_trend_core",
        "v2_2_cyclical_trend_core",
        "v2_2_trend_continuation_boost",
    ]:
        rows.append(_metric_row(detail[existing & detail[column]], key_name="comparison_set", key_value=f"{column}_and_existing"))
        rows.append(_metric_row(detail[detail[column] & ~existing], key_name="comparison_set", key_value=f"{column}_only"))
    rows.append(_metric_row(detail[existing], key_name="comparison_set", key_value="existing_trend_continuation_candidate"))
    return pd.DataFrame(rows)


def _strong_winner_capture(detail: pd.DataFrame, strong_winners: pd.DataFrame | None) -> pd.DataFrame:
    if strong_winners is None or strong_winners.empty or "asset_id" not in strong_winners.columns:
        winner_assets: set[str] = set()
    else:
        winner_assets = set(str(value) for value in strong_winners["asset_id"].dropna().unique())
    rows = []
    for column in CANDIDATE_COLUMNS:
        hit_assets = set(str(value) for value in detail.loc[detail[column], "asset_id"].dropna().unique())
        captured = len(winner_assets & hit_assets)
        rows.append(
            {
                "candidate_set": column,
                "captured_strong_winner_count": captured,
                "total_strong_winner_count": len(winner_assets),
                "capture_rate": captured / len(winner_assets) if winner_assets else 0.0,
            }
        )
    return pd.DataFrame(rows)


def _recommendations(layer_effectiveness: pd.DataFrame) -> pd.DataFrame:
    baseline = _row_by_name(layer_effectiveness, "v2_1_quality_no_highvol_extremeamount")
    growth = _row_by_name(layer_effectiveness, "v2_2_growth_trend_core")
    cyclical = _row_by_name(layer_effectiveness, "v2_2_cyclical_trend_core")
    boost = _row_by_name(layer_effectiveness, "v2_2_trend_continuation_boost")
    rows = [
        {
            "recommendation": "replay_growth_and_cyclical_core_separately",
            "rule_hint": "split v2.1 into growth low-volatility core and cyclical mainline core",
            "evidence_summary": (
                f"baseline_60d={_metric(baseline, 'future_60d_return_mean'):.2%}; "
                f"growth_60d={_metric(growth, 'future_60d_return_mean'):.2%}; "
                f"cyclical_60d={_metric(cyclical, 'future_60d_return_mean'):.2%}"
            ),
            "next_action": "keep as watchlist diagnostics shadow until rolling review confirms stability",
        },
        {
            "recommendation": "promote_trend_continuation_boost_for_review",
            "rule_hint": "v2.1 quality/no-high-vol/no-extreme-volume AND event_structure=trend_continuation_candidate",
            "evidence_summary": (
                f"boost_sample={int(_metric(boost, 'sample_count'))}; "
                f"boost_60d={_metric(boost, 'future_60d_return_mean'):.2%}; "
                f"boost_dd60={_metric(boost, 'future_60d_max_drawdown_mean'):.2%}"
            ),
            "next_action": "review top10 names by day before changing production watchlist rules",
        },
        {
            "recommendation": "keep_high_elasticity_as_shadow",
            "rule_hint": "v2_final AND (high/extreme volatility OR extreme volume)",
            "evidence_summary": "high elasticity names are not low-risk trend core; evaluate separately on shorter windows",
            "next_action": "do not mix into mid-term core watchlist",
        },
    ]
    return pd.DataFrame(rows)


def _render_report(
    *,
    layer_effectiveness: pd.DataFrame,
    vs_existing: pd.DataFrame,
    strong_winner_capture: pd.DataFrame,
    recommendations: pd.DataFrame,
    warnings: list[str],
) -> str:
    lines = [
        "# Trend Discovery v2.2 Replay Report",
        "",
        "## 1. Scope",
        "回放 v2.2 趋势候选分层：growth core、cyclical core、trend continuation boost、high elasticity shadow；不接入 stock_score，不生成交易建议。",
        "",
        "## 2. Warnings",
        *([f"- {warning}" for warning in warnings] or ["- none"]),
        "",
        "## 3. Candidate Layer Effectiveness",
        layer_effectiveness.to_markdown(index=False),
        "",
        "## 4. v2.2 vs Existing Trend Continuation",
        vs_existing.to_markdown(index=False),
        "",
        "## 5. Strong Winner Capture",
        strong_winner_capture.to_markdown(index=False),
        "",
        "## 6. Recommendations",
        recommendations.to_markdown(index=False),
    ]
    return "\n".join(lines) + "\n"


def _metric_row(frame: pd.DataFrame, *, key_name: str, key_value: str) -> dict[str, Any]:
    row: dict[str, Any] = {key_name: key_value, "sample_count": len(frame)}
    for metric in METRICS:
        row[_metric_name(metric)] = pd.to_numeric(frame.get(metric, pd.Series(dtype=float)), errors="coerce").mean()
    return row


def _row_by_name(layer_effectiveness: pd.DataFrame, name: str) -> pd.Series:
    rows = layer_effectiveness[layer_effectiveness["candidate_set"].eq(name)]
    if rows.empty:
        return pd.Series(dtype=float)
    return rows.iloc[0]


def _metric(row: pd.Series, column: str) -> float:
    try:
        if pd.isna(row.get(column)):
            return 0.0
        return float(row.get(column))
    except (TypeError, ValueError):
        return 0.0


def _metric_name(column: str) -> str:
    if column == "hit_double_within_60d":
        return "hit_double_within_60d_rate"
    return f"{column}_mean"


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    try:
        if pd.isna(value):
            return False
    except Exception:
        pass
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"", "0", "false", "f", "no", "n", "off", "none", "null", "nan"}:
            return False
        if normalized in {"1", "true", "t", "yes", "y", "on"}:
            return True
    return bool(value)
