from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


CANDIDATE_COLUMNS = [
    "v2_final_baseline",
    "v2_1_quality_no_highvol_extremeamount",
    "v2_2_growth_trend_core",
    "v2_2_cyclical_trend_core",
    "v2_2_trend_continuation_boost",
    "v2_2_high_elasticity_shadow",
    "existing_trend_continuation_candidate",
]
RETURN_METRICS = [
    "future_1d_return",
    "future_3d_return",
    "future_5d_return",
    "future_10d_return",
    "future_20d_return",
    "future_30d_return",
    "future_40d_return",
    "future_60d_return",
]
DRAWDOWN_METRICS = [
    "future_10d_max_drawdown",
    "future_20d_max_drawdown",
    "future_30d_max_drawdown",
    "future_40d_max_drawdown",
    "future_60d_max_drawdown",
]
EXTRA_METRICS = ["max_return_within_60d", "hit_double_within_60d"]
METRICS = RETURN_METRICS + DRAWDOWN_METRICS + EXTRA_METRICS


def run_trend_discovery_v2_2_stability_review(
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
    return build_trend_discovery_v2_2_stability_review(
        detail=detail,
        strong_winners=strong_winners,
        output_dir=output_dir,
    )


def build_trend_discovery_v2_2_stability_review(
    *,
    detail: pd.DataFrame,
    strong_winners: pd.DataFrame | None = None,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    warnings: list[str] = []
    frame = _prepare_detail(detail, warnings)
    by_period = _slice_summary(frame, "period", "period")
    by_regime = pd.concat(
        [
            _slice_summary(frame, "market_regime", "regime_value"),
            _slice_summary(frame, "mainline_context", "regime_value"),
        ],
        ignore_index=True,
    )
    by_industry = _slice_summary(frame, "industry_name", "industry_name")
    high_elasticity_short_horizon = _high_elasticity_short_horizon(frame)
    strong_winner_capture = _strong_winner_capture(frame, strong_winners)
    decision = _decision_table(frame, by_period, high_elasticity_short_horizon, strong_winner_capture)
    report = _render_report(
        by_period=by_period,
        by_regime=by_regime,
        by_industry=by_industry,
        high_elasticity_short_horizon=high_elasticity_short_horizon,
        strong_winner_capture=strong_winner_capture,
        decision=decision,
        warnings=warnings,
    )

    result: dict[str, Any] = {
        "detail": frame,
        "by_period": by_period,
        "by_regime": by_regime,
        "by_industry": by_industry,
        "high_elasticity_short_horizon": high_elasticity_short_horizon,
        "strong_winner_capture": strong_winner_capture,
        "decision": decision,
        "report": report,
        "warnings": warnings,
        "paths": {},
    }
    if output_dir is not None:
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        paths = {
            "by_period": output / "trend_discovery_v2_2_stability_by_period.csv",
            "by_regime": output / "trend_discovery_v2_2_stability_by_regime.csv",
            "by_industry": output / "trend_discovery_v2_2_stability_by_industry.csv",
            "high_elasticity_short_horizon": output
            / "trend_discovery_v2_2_high_elasticity_short_horizon.csv",
            "strong_winner_capture": output / "trend_discovery_v2_2_stability_strong_winner_capture.csv",
            "decision": output / "trend_discovery_v2_2_stability_decision.csv",
            "report": output / "trend_discovery_v2_2_stability_review_report.md",
        }
        by_period.to_csv(paths["by_period"], index=False)
        by_regime.to_csv(paths["by_regime"], index=False)
        by_industry.to_csv(paths["by_industry"], index=False)
        high_elasticity_short_horizon.to_csv(paths["high_elasticity_short_horizon"], index=False)
        strong_winner_capture.to_csv(paths["strong_winner_capture"], index=False)
        decision.to_csv(paths["decision"], index=False)
        paths["report"].write_text(report, encoding="utf-8")
        result["paths"] = {key: str(value) for key, value in paths.items()}
    return result


def _prepare_detail(frame: pd.DataFrame, warnings: list[str]) -> pd.DataFrame:
    detail = frame.copy()
    if "trade_date" not in detail.columns:
        detail["trade_date"] = pd.NaT
        warnings.append("missing_trade_date")
    detail["trade_date"] = pd.to_datetime(detail["trade_date"], errors="coerce")
    detail["period"] = detail["trade_date"].map(_period_label)
    for column in ["asset_id", "market_regime", "mainline_context", "industry_name"]:
        if column not in detail.columns:
            detail[column] = "unknown"
            warnings.append(f"missing_{column}")
        detail[column] = detail[column].fillna("unknown").astype(str).replace({"": "unknown"})
    for column in CANDIDATE_COLUMNS:
        if column not in detail.columns:
            detail[column] = False
            warnings.append(f"missing_{column}")
        detail[column] = detail[column].map(_bool)
    for column in METRICS:
        if column not in detail.columns:
            detail[column] = pd.NA
            warnings.append(f"missing_{column}")
        detail[column] = pd.to_numeric(detail[column], errors="coerce")
    detail["hit_double_within_60d"] = detail["hit_double_within_60d"].map(_bool).astype(float)
    return detail


def _slice_summary(frame: pd.DataFrame, group_column: str, output_column: str) -> pd.DataFrame:
    rows = []
    for candidate in CANDIDATE_COLUMNS:
        selected = frame[frame[candidate]].copy()
        if selected.empty:
            continue
        grouped = selected.groupby(group_column, dropna=False)
        for group_value, group in grouped:
            row = _metric_row(group)
            row["candidate_set"] = candidate
            row[output_column] = str(group_value)
            row["active_slice_count"] = selected[group_column].nunique(dropna=False)
            rows.append(row)
    columns = ["candidate_set", output_column, "sample_count", "active_slice_count", *_metric_columns()]
    if not rows:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame(rows)[columns].sort_values(["candidate_set", output_column]).reset_index(drop=True)


def _high_elasticity_short_horizon(frame: pd.DataFrame) -> pd.DataFrame:
    selected = frame[frame["v2_2_high_elasticity_shadow"]].copy()
    row = _metric_row(selected)
    short_return = _float(row.get("future_5d_return_mean"))
    long_return = _float(row.get("future_60d_return_mean"))
    long_drawdown = _float(row.get("future_60d_max_drawdown_mean"))
    row.update(
        {
            "candidate_set": "v2_2_high_elasticity_shadow",
            "short_horizon_edge": short_return > 0 and (long_return < short_return or long_drawdown < -0.16),
            "recommended_usage": "short_horizon_only"
            if short_return > 0 and long_drawdown < -0.16
            else "keep_shadow",
        }
    )
    columns = ["candidate_set", "recommended_usage", "short_horizon_edge", "sample_count", *_metric_columns()]
    return pd.DataFrame([row])[columns]


def _strong_winner_capture(frame: pd.DataFrame, strong_winners: pd.DataFrame | None) -> pd.DataFrame:
    if strong_winners is None or strong_winners.empty or "asset_id" not in strong_winners.columns:
        winner_assets: set[str] = set()
    else:
        winner_assets = set(str(value) for value in strong_winners["asset_id"].dropna().unique())
    rows = []
    for candidate in CANDIDATE_COLUMNS:
        selected_assets = set(str(value) for value in frame.loc[frame[candidate], "asset_id"].dropna().unique())
        captured = len(winner_assets & selected_assets)
        rows.append(
            {
                "candidate_set": candidate,
                "captured_strong_winner_count": captured,
                "total_strong_winner_count": len(winner_assets),
                "capture_rate": captured / len(winner_assets) if winner_assets else 0.0,
            }
        )
    return pd.DataFrame(rows)


def _decision_table(
    frame: pd.DataFrame,
    by_period: pd.DataFrame,
    high_elasticity_short_horizon: pd.DataFrame,
    strong_winner_capture: pd.DataFrame,
) -> pd.DataFrame:
    rows = []
    baseline = _metric_row(frame[frame["v2_1_quality_no_highvol_extremeamount"]])
    baseline_return = _float(baseline.get("future_60d_return_mean"))
    baseline_drawdown = _float(baseline.get("future_60d_max_drawdown_mean"))
    for candidate in CANDIDATE_COLUMNS:
        selected = frame[frame[candidate]]
        metrics = _metric_row(selected)
        candidate_periods = by_period[by_period["candidate_set"].eq(candidate)]
        active_periods = int(candidate_periods["period"].nunique()) if not candidate_periods.empty else 0
        good_periods = int((pd.to_numeric(candidate_periods.get("future_60d_return_mean"), errors="coerce") > 0).sum())
        capture = strong_winner_capture[strong_winner_capture["candidate_set"].eq(candidate)]
        capture_rate = _float(capture["capture_rate"].iloc[0]) if not capture.empty else 0.0
        decision, reason = _candidate_decision(
            candidate=candidate,
            metrics=metrics,
            baseline_return=baseline_return,
            baseline_drawdown=baseline_drawdown,
            active_periods=active_periods,
            good_periods=good_periods,
            high_elasticity_short_horizon=high_elasticity_short_horizon,
        )
        rows.append(
            {
                "candidate_set": candidate,
                "decision": decision,
                "reason": reason,
                "sample_count": metrics["sample_count"],
                "active_period_count": active_periods,
                "positive_period_count": good_periods,
                "capture_rate": capture_rate,
                "future_20d_return_mean": metrics.get("future_20d_return_mean"),
                "future_60d_return_mean": metrics.get("future_60d_return_mean"),
                "future_60d_max_drawdown_mean": metrics.get("future_60d_max_drawdown_mean"),
                "hit_double_within_60d_rate": metrics.get("hit_double_within_60d_rate"),
            }
        )
    return pd.DataFrame(rows)


def _candidate_decision(
    *,
    candidate: str,
    metrics: dict[str, Any],
    baseline_return: float,
    baseline_drawdown: float,
    active_periods: int,
    good_periods: int,
    high_elasticity_short_horizon: pd.DataFrame,
) -> tuple[str, str]:
    sample_count = int(metrics.get("sample_count", 0))
    ret60 = _float(metrics.get("future_60d_return_mean"))
    dd60 = _float(metrics.get("future_60d_max_drawdown_mean"))
    if candidate == "v2_2_high_elasticity_shadow":
        usage = high_elasticity_short_horizon["recommended_usage"].iloc[0]
        return str(usage), "high_elasticity_should_not_mix_into_mid_term_core"
    if sample_count < 100:
        if ret60 > baseline_return and dd60 >= baseline_drawdown - 0.02:
            return "keep_shadow", "sample_count_too_small_for_promotion"
        return "discard_or_rework", "sample_count_too_small_and_no_clear_edge"
    if ret60 > baseline_return and dd60 >= baseline_drawdown - 0.02 and good_periods >= max(1, active_periods // 2):
        return "promote_candidate", "beats_v2_1_with_acceptable_drawdown_across_periods"
    if ret60 > 0 and sample_count >= 50:
        return "keep_shadow", "positive_but_not_stable_enough_to_promote"
    return "discard_or_rework", "weak_return_or_unacceptable_drawdown"


def _metric_row(frame: pd.DataFrame) -> dict[str, Any]:
    row: dict[str, Any] = {"sample_count": len(frame)}
    for metric in METRICS:
        series = pd.to_numeric(frame.get(metric, pd.Series(dtype=float)), errors="coerce")
        out_name = _metric_name(metric)
        row[out_name] = series.mean()
        if metric in RETURN_METRICS:
            row[f"{metric}_win_rate"] = (series > 0).mean()
    return row


def _metric_columns() -> list[str]:
    columns = []
    for metric in METRICS:
        columns.append(_metric_name(metric))
        if metric in RETURN_METRICS:
            columns.append(f"{metric}_win_rate")
    return columns


def _render_report(
    *,
    by_period: pd.DataFrame,
    by_regime: pd.DataFrame,
    by_industry: pd.DataFrame,
    high_elasticity_short_horizon: pd.DataFrame,
    strong_winner_capture: pd.DataFrame,
    decision: pd.DataFrame,
    warnings: list[str],
) -> str:
    lines = [
        "# Trend Discovery v2.2 Stability Review",
        "",
        "## 1. Scope",
        "验证 v2.2 各候选层在时间、市场环境、行业和强票捕捉上的稳定性；不接 stock_score，不生成交易建议。",
        "",
        "## 2. Warnings",
        *([f"- {warning}" for warning in warnings] or ["- none"]),
        "",
        "## 3. Decision",
        decision.to_markdown(index=False),
        "",
        "## 4. Period Stability",
        by_period.head(80).to_markdown(index=False),
        "",
        "## 5. Regime Stability",
        by_regime.head(80).to_markdown(index=False),
        "",
        "## 6. Industry Stability",
        by_industry.head(80).to_markdown(index=False),
        "",
        "## 7. High Elasticity Short Horizon",
        high_elasticity_short_horizon.to_markdown(index=False),
        "",
        "## 8. Strong Winner Capture",
        strong_winner_capture.to_markdown(index=False),
    ]
    return "\n".join(lines) + "\n"


def _period_label(value: Any) -> str:
    if pd.isna(value):
        return "unknown"
    date = pd.Timestamp(value)
    if date.year == 2024:
        return "2024H1" if date.month <= 6 else "2024H2"
    if date.year == 2025:
        return f"2025Q{((date.month - 1) // 3) + 1}"
    if date.year == 2026:
        return "2026YTD"
    return str(date.year)


def _metric_name(column: str) -> str:
    if column == "hit_double_within_60d":
        return "hit_double_within_60d_rate"
    return f"{column}_mean"


def _float(value: Any) -> float:
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
