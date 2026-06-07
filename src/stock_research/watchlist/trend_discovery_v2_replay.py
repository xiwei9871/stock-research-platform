from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


LAYER_COLUMNS = [
    "trend_discovery_v2_recall",
    "trend_discovery_v2_core",
    "trend_discovery_v2_high_purity",
    "trend_discovery_v2_final_candidate",
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


def run_trend_discovery_v2_replay(
    *,
    template_detail_path: str | Path,
    output_dir: str | Path,
    strong_winner_path: str | Path | None = None,
) -> dict[str, Any]:
    template_detail = pd.read_csv(template_detail_path, low_memory=False)
    strong_winners = (
        pd.read_csv(strong_winner_path, low_memory=False)
        if strong_winner_path and Path(strong_winner_path).exists()
        else None
    )
    return build_trend_discovery_v2_replay(
        template_detail=template_detail,
        strong_winners=strong_winners,
        output_dir=output_dir,
    )


def build_trend_discovery_v2_replay(
    *,
    template_detail: pd.DataFrame,
    strong_winners: pd.DataFrame | None = None,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    warnings: list[str] = []
    detail = _build_replay_detail(template_detail, warnings)
    layer_effectiveness = _layer_effectiveness(detail)
    vs_existing = _vs_existing_candidate(detail)
    strong_winner_capture = _strong_winner_capture(detail, strong_winners)
    recommendations = _recommendations(layer_effectiveness, vs_existing, strong_winner_capture)
    report = _render_report(layer_effectiveness, vs_existing, strong_winner_capture, recommendations, warnings)

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
            "detail": output / "trend_discovery_v2_replay_detail.csv",
            "layer_effectiveness": output / "trend_discovery_v2_layer_effectiveness.csv",
            "vs_existing": output / "trend_discovery_v2_vs_existing_candidate.csv",
            "strong_winner_capture": output / "trend_discovery_v2_strong_winner_capture.csv",
            "recommendations": output / "trend_discovery_v2_recommendations.csv",
            "report": output / "trend_discovery_v2_replay_report.md",
        }
        detail.to_csv(paths["detail"], index=False)
        layer_effectiveness.to_csv(paths["layer_effectiveness"], index=False)
        vs_existing.to_csv(paths["vs_existing"], index=False)
        strong_winner_capture.to_csv(paths["strong_winner_capture"], index=False)
        recommendations.to_csv(paths["recommendations"], index=False)
        paths["report"].write_text(report, encoding="utf-8")
        result["paths"] = {key: str(value) for key, value in paths.items()}
    return result


def _build_replay_detail(template_detail: pd.DataFrame, warnings: list[str]) -> pd.DataFrame:
    frame = template_detail.copy()
    for column in [
        "time_series_momentum_template",
        "relative_strength_template",
        "dual_momentum_template",
        "minervini_like_template",
    ]:
        if column not in frame.columns:
            frame[column] = False
            warnings.append(f"missing_{column}")
        frame[column] = frame[column].map(_bool)
    for column in ["mainline_context", "fundamental_quality_bucket", "event_structure"]:
        if column not in frame.columns:
            frame[column] = ""
            warnings.append(f"missing_{column}")
    for column in TREND_METRICS:
        if column not in frame.columns:
            frame[column] = pd.NA
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame["hit_double_within_60d"] = frame["hit_double_within_60d"].map(_bool).astype(float)

    good_fundamental = frame["fundamental_quality_bucket"].isin(
        ["expectation_growth", "cyclical_or_turnaround", "clean_or_unknown"]
    )
    mainline = frame["mainline_context"].eq("mainline")
    frame["trend_discovery_v2_recall"] = (
        frame["time_series_momentum_template"] | frame["relative_strength_template"]
    )
    frame["trend_discovery_v2_core"] = frame["dual_momentum_template"]
    frame["trend_discovery_v2_high_purity"] = frame["minervini_like_template"]
    frame["trend_discovery_v2_final_candidate"] = (
        frame["dual_momentum_template"] & mainline & (frame["minervini_like_template"] | good_fundamental)
    )
    frame["existing_trend_continuation_candidate"] = frame["event_structure"].eq("trend_continuation_candidate")
    frame["v2_layer_count"] = frame[LAYER_COLUMNS].sum(axis=1).astype(int)
    return frame


def _layer_effectiveness(detail: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for column, label in [
        ("trend_discovery_v2_recall", "v2_recall"),
        ("trend_discovery_v2_core", "v2_core"),
        ("trend_discovery_v2_high_purity", "v2_high_purity"),
        ("trend_discovery_v2_final_candidate", "v2_final_candidate"),
    ]:
        rows.append(_metric_row(detail[detail[column]], key_name="v2_layer", key_value=label))
    return pd.DataFrame(rows)


def _vs_existing_candidate(detail: pd.DataFrame) -> pd.DataFrame:
    rows = [
        _metric_row(
            detail[detail["existing_trend_continuation_candidate"]],
            key_name="candidate_set",
            key_value="existing_trend_continuation",
        ),
        _metric_row(
            detail[detail["trend_discovery_v2_final_candidate"]],
            key_name="candidate_set",
            key_value="v2_final_candidate",
        ),
    ]
    existing_assets = set(detail.loc[detail["existing_trend_continuation_candidate"], "asset_id"].dropna().astype(str))
    v2_assets = set(detail.loc[detail["trend_discovery_v2_final_candidate"], "asset_id"].dropna().astype(str))
    rows.append(
        {
            "candidate_set": "intersection",
            "sample_count": len(existing_assets & v2_assets),
            **_empty_metrics(),
        }
    )
    rows.append(
        {
            "candidate_set": "v2_only",
            "sample_count": len(v2_assets - existing_assets),
            **_empty_metrics(),
        }
    )
    rows.append(
        {
            "candidate_set": "existing_only",
            "sample_count": len(existing_assets - v2_assets),
            **_empty_metrics(),
        }
    )
    return pd.DataFrame(rows)


def _strong_winner_capture(detail: pd.DataFrame, strong_winners: pd.DataFrame | None) -> pd.DataFrame:
    if strong_winners is None or strong_winners.empty or "asset_id" not in strong_winners.columns:
        total_assets: set[str] = set()
    else:
        total_assets = set(str(value) for value in strong_winners["asset_id"].dropna().unique())
    rows = []
    for column, label in [
        ("trend_discovery_v2_recall", "v2_recall"),
        ("trend_discovery_v2_core", "v2_core"),
        ("trend_discovery_v2_high_purity", "v2_high_purity"),
        ("trend_discovery_v2_final_candidate", "v2_final_candidate"),
        ("existing_trend_continuation_candidate", "existing_trend_continuation"),
    ]:
        hit_assets = set(str(value) for value in detail.loc[detail[column], "asset_id"].dropna().unique())
        captured = len(total_assets & hit_assets)
        rows.append(
            {
                "candidate_set": label,
                "captured_strong_winner_count": captured,
                "total_strong_winner_count": len(total_assets),
                "capture_rate": captured / len(total_assets) if total_assets else 0.0,
            }
        )
    return pd.DataFrame(rows)


def _recommendations(
    layer_effectiveness: pd.DataFrame,
    vs_existing: pd.DataFrame,
    strong_winner_capture: pd.DataFrame,
) -> pd.DataFrame:
    final = layer_effectiveness[layer_effectiveness["v2_layer"].eq("v2_final_candidate")]
    existing = vs_existing[vs_existing["candidate_set"].eq("existing_trend_continuation")]
    final_60 = _float_or_zero(final["future_60d_return_mean"].iloc[0]) if not final.empty else 0.0
    existing_60 = _float_or_zero(existing["future_60d_return_mean"].iloc[0]) if not existing.empty else 0.0
    final_dd = _float_or_zero(final["future_60d_max_drawdown_mean"].iloc[0]) if not final.empty else 0.0
    action = "keep_research_only"
    if final_60 > existing_60 and final_dd > -0.16:
        action = "promote_to_watchlist_diagnostics_shadow"
    return pd.DataFrame(
        [
            {
                "recommendation": action,
                "reason": (
                    f"v2_final_60d={final_60:.2%}, existing_60d={existing_60:.2%}, "
                    f"v2_final_dd60={final_dd:.2%}"
                ),
            }
        ]
    )


def _metric_row(frame: pd.DataFrame, *, key_name: str, key_value: str) -> dict[str, Any]:
    row: dict[str, Any] = {key_name: key_value, "sample_count": len(frame)}
    for metric in TREND_METRICS:
        row[_metric_name(metric)] = pd.to_numeric(frame.get(metric, pd.Series(dtype=float)), errors="coerce").mean()
    return row


def _empty_metrics() -> dict[str, Any]:
    return {_metric_name(metric): pd.NA for metric in TREND_METRICS}


def _render_report(
    layer_effectiveness: pd.DataFrame,
    vs_existing: pd.DataFrame,
    strong_winner_capture: pd.DataFrame,
    recommendations: pd.DataFrame,
    warnings: list[str],
) -> str:
    lines = [
        "# Trend Discovery v2 Replay Report",
        "",
        "## 1. Scope",
        "回放 v2 趋势漏斗：recall -> core -> high purity -> final candidate；不接入 stock_score，不生成交易建议。",
        "",
        "## 2. Warnings",
        *([f"- {warning}" for warning in warnings] or ["- none"]),
        "",
        "## 3. Layer Effectiveness",
        layer_effectiveness.to_markdown(index=False),
        "",
        "## 4. v2 vs Existing Trend Continuation",
        vs_existing.to_markdown(index=False),
        "",
        "## 5. Strong Winner Capture",
        strong_winner_capture.to_markdown(index=False),
        "",
        "## 6. Recommendations",
        recommendations.to_markdown(index=False),
    ]
    return "\n".join(lines) + "\n"


def _metric_name(column: str) -> str:
    if column == "hit_double_within_60d":
        return "hit_double_within_60d_rate"
    return f"{column}_mean"


def _float_or_zero(value: Any) -> float:
    try:
        if pd.isna(value):
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


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
