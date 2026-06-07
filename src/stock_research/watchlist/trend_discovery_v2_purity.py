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
SLICE_COLUMNS = [
    "score_rank_bucket",
    "sector_strength_bucket",
    "fundamental_quality_bucket",
    "event_structure",
    "amount_vs_20d_bucket",
    "high_to_close_drawdown_bucket",
    "volatility_5d_bucket",
    "template_hit_bucket",
]


def run_trend_discovery_v2_purity_audit(
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
    return build_trend_discovery_v2_purity_audit(
        v2_detail=v2_detail,
        strong_winners=strong_winners,
        output_dir=output_dir,
    )


def build_trend_discovery_v2_purity_audit(
    *,
    v2_detail: pd.DataFrame,
    strong_winners: pd.DataFrame | None = None,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    warnings: list[str] = []
    detail = _enrich_detail(v2_detail, warnings)
    final = detail[detail["trend_discovery_v2_final_candidate"]].copy()
    purity_slice = _purity_slice(final)
    bad_slice_audit = _bad_slice_audit(purity_slice)
    high_elasticity_slice = _high_elasticity_slice(detail)
    v2_1_candidate_effectiveness = _v2_1_candidate_effectiveness(detail)
    missed_winner_audit = _missed_winner_audit(detail, strong_winners)
    recommendations = _recommendations(purity_slice, bad_slice_audit, high_elasticity_slice, v2_1_candidate_effectiveness)
    report = _render_report(
        purity_slice=purity_slice,
        bad_slice_audit=bad_slice_audit,
        high_elasticity_slice=high_elasticity_slice,
        v2_1_candidate_effectiveness=v2_1_candidate_effectiveness,
        missed_winner_audit=missed_winner_audit,
        recommendations=recommendations,
        warnings=warnings,
    )

    result: dict[str, Any] = {
        "detail": detail,
        "purity_slice": purity_slice,
        "bad_slice_audit": bad_slice_audit,
        "high_elasticity_slice": high_elasticity_slice,
        "v2_1_candidate_effectiveness": v2_1_candidate_effectiveness,
        "missed_winner_audit": missed_winner_audit,
        "recommendations": recommendations,
        "report": report,
        "warnings": warnings,
        "paths": {},
    }
    if output_dir is not None:
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        paths = {
            "detail": output / "trend_discovery_v2_purity_detail.csv",
            "purity_slice": output / "trend_discovery_v2_purity_slice.csv",
            "bad_slice_audit": output / "trend_discovery_v2_bad_slice_audit.csv",
            "high_elasticity_slice": output / "trend_discovery_v2_high_elasticity_slice.csv",
            "v2_1_candidate_effectiveness": output / "trend_discovery_v2_1_candidate_effectiveness.csv",
            "missed_winner_audit": output / "trend_discovery_v2_missed_winner_audit.csv",
            "recommendations": output / "trend_discovery_v2_purity_recommendations.csv",
            "report": output / "trend_discovery_v2_purity_audit_report.md",
        }
        detail.to_csv(paths["detail"], index=False)
        purity_slice.to_csv(paths["purity_slice"], index=False)
        bad_slice_audit.to_csv(paths["bad_slice_audit"], index=False)
        high_elasticity_slice.to_csv(paths["high_elasticity_slice"], index=False)
        v2_1_candidate_effectiveness.to_csv(paths["v2_1_candidate_effectiveness"], index=False)
        missed_winner_audit.to_csv(paths["missed_winner_audit"], index=False)
        recommendations.to_csv(paths["recommendations"], index=False)
        paths["report"].write_text(report, encoding="utf-8")
        result["paths"] = {key: str(value) for key, value in paths.items()}
    return result


def _enrich_detail(frame: pd.DataFrame, warnings: list[str]) -> pd.DataFrame:
    detail = frame.copy()
    for column in [
        "score_rank",
        "amount_vs_20d",
        "high_to_close_drawdown",
        "volatility_5d",
        "template_hit_count",
        *METRICS,
    ]:
        if column not in detail.columns:
            detail[column] = pd.NA
            warnings.append(f"missing_{column}")
        detail[column] = pd.to_numeric(detail[column], errors="coerce")
    for column in [
        "sector_strength_bucket",
        "fundamental_quality_bucket",
        "event_structure",
        "asset_id",
        "ts_code",
        "stock_name",
    ]:
        if column not in detail.columns:
            detail[column] = ""
            warnings.append(f"missing_{column}")
    for column in [
        "trend_discovery_v2_recall",
        "trend_discovery_v2_core",
        "trend_discovery_v2_high_purity",
        "trend_discovery_v2_final_candidate",
    ]:
        if column not in detail.columns:
            detail[column] = False
            warnings.append(f"missing_{column}")
        detail[column] = detail[column].map(_bool)
    detail["score_rank_bucket"] = detail["score_rank"].map(_score_rank_bucket)
    detail["amount_vs_20d_bucket"] = detail["amount_vs_20d"].map(_amount_bucket)
    detail["high_to_close_drawdown_bucket"] = detail["high_to_close_drawdown"].map(_drawdown_bucket)
    detail["volatility_5d_bucket"] = detail["volatility_5d"].map(_volatility_bucket)
    detail["template_hit_bucket"] = detail["template_hit_count"].map(_template_hit_bucket)
    detail["hit_double_within_60d"] = detail["hit_double_within_60d"].map(_bool).astype(float)
    return detail


def _purity_slice(final: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for column in SLICE_COLUMNS:
        if column not in final.columns:
            continue
        grouped = final.groupby(column, dropna=False)
        metric = grouped[METRICS].mean(numeric_only=True).reset_index()
        counts = grouped.size().reset_index(name="sample_count")
        summary = counts.merge(metric, on=column, how="left")
        summary.insert(0, "slice_value", summary[column].astype(str))
        summary.insert(0, "slice_dimension", column)
        summary = summary.drop(columns=[column])
        rows.append(summary.rename(columns={metric_name: _metric_name(metric_name) for metric_name in METRICS}))
    if not rows:
        return pd.DataFrame(columns=["slice_dimension", "slice_value", "sample_count"])
    return pd.concat(rows, ignore_index=True).sort_values(["slice_dimension", "sample_count"], ascending=[True, False])


def _bad_slice_audit(purity_slice: pd.DataFrame) -> pd.DataFrame:
    if purity_slice.empty:
        return purity_slice.copy()
    working = purity_slice.copy()
    sample_ok = pd.to_numeric(working["sample_count"], errors="coerce").fillna(0) >= 1
    ret60 = pd.to_numeric(working.get("future_60d_return_mean"), errors="coerce")
    dd60 = pd.to_numeric(working.get("future_60d_max_drawdown_mean"), errors="coerce")
    bad = working[sample_ok & ((ret60 < 0.03) | (dd60 < -0.18))].copy()
    if bad.empty:
        bad = working.sort_values(["future_60d_return_mean", "future_60d_max_drawdown_mean"]).head(10).copy()
    bad["audit_reason"] = bad.apply(_bad_slice_reason, axis=1)
    return bad.reset_index(drop=True)


def _high_elasticity_slice(detail: pd.DataFrame) -> pd.DataFrame:
    high_elasticity = detail[
        detail["trend_discovery_v2_core"]
        & (
            detail["amount_vs_20d_bucket"].eq("extreme_volume")
            | detail["volatility_5d_bucket"].isin(["high_volatility", "extreme_volatility"])
        )
    ].copy()
    if high_elasticity.empty:
        return pd.DataFrame(columns=["elasticity_bucket", "sample_count", *_metric_output_columns()])
    high_elasticity["elasticity_bucket"] = high_elasticity.apply(
        lambda row: "extreme_volume" if row["amount_vs_20d_bucket"] == "extreme_volume" else "high_volatility",
        axis=1,
    )
    grouped = high_elasticity.groupby("elasticity_bucket", dropna=False)
    metric = grouped[METRICS].mean(numeric_only=True).reset_index()
    counts = grouped.size().reset_index(name="sample_count")
    return counts.merge(metric, on="elasticity_bucket").rename(
        columns={metric_name: _metric_name(metric_name) for metric_name in METRICS}
    )


def _v2_1_candidate_effectiveness(detail: pd.DataFrame) -> pd.DataFrame:
    final = detail[detail["trend_discovery_v2_final_candidate"]].copy()
    quality_fundamental = final["fundamental_quality_bucket"].isin(["expectation_growth", "cyclical_or_turnaround"])
    no_high_volatility = ~final["volatility_5d_bucket"].isin(["high_volatility", "extreme_volatility"])
    no_extreme_volume = ~final["amount_vs_20d_bucket"].eq("extreme_volume")
    low_intraday_fade = final["high_to_close_drawdown_bucket"].isin(["low_intraday_fade", "mid_intraday_fade"])
    template_4plus = final["template_hit_bucket"].isin(["hit_4", "hit_5plus"])
    sets = {
        "v2_final_baseline": final.index == final.index,
        "v2_1_no_highvol_extremeamount": no_high_volatility & no_extreme_volume,
        "v2_1_quality_fundamental": quality_fundamental,
        "v2_1_quality_no_highvol_extremeamount": quality_fundamental & no_high_volatility & no_extreme_volume,
        "v2_1_quality_lowfade_no_highvol": quality_fundamental
        & no_high_volatility
        & no_extreme_volume
        & low_intraday_fade,
        "v2_1_template4_quality_no_highvol": template_4plus
        & quality_fundamental
        & no_high_volatility
        & no_extreme_volume,
    }
    rows = []
    for name, mask in sets.items():
        rows.append(_metric_row(final[mask], key_name="candidate_set", key_value=name))
    return pd.DataFrame(rows)


def _missed_winner_audit(detail: pd.DataFrame, strong_winners: pd.DataFrame | None) -> pd.DataFrame:
    if strong_winners is None or strong_winners.empty or "asset_id" not in strong_winners.columns:
        return pd.DataFrame(columns=["asset_id", "winner_id", "in_v2_recall", "in_v2_final_candidate", "miss_reason"])
    flags = (
        detail.groupby("asset_id", dropna=False)[
            [
                "trend_discovery_v2_recall",
                "trend_discovery_v2_core",
                "trend_discovery_v2_high_purity",
                "trend_discovery_v2_final_candidate",
            ]
        ]
        .max()
        .reset_index()
    )
    winners = strong_winners.copy()
    winners["asset_id"] = winners["asset_id"].astype(str)
    flags["asset_id"] = flags["asset_id"].astype(str)
    merged = winners.merge(flags, on="asset_id", how="left")
    for column in [
        "trend_discovery_v2_recall",
        "trend_discovery_v2_core",
        "trend_discovery_v2_high_purity",
        "trend_discovery_v2_final_candidate",
    ]:
        merged[column] = merged[column].map(_bool)
    merged["in_v2_recall"] = merged["trend_discovery_v2_recall"]
    merged["in_v2_final_candidate"] = merged["trend_discovery_v2_final_candidate"]
    merged["miss_reason"] = merged.apply(_winner_miss_reason, axis=1)
    return merged


def _recommendations(
    purity_slice: pd.DataFrame,
    bad_slice_audit: pd.DataFrame,
    high_elasticity_slice: pd.DataFrame,
    v2_1_candidate_effectiveness: pd.DataFrame,
) -> pd.DataFrame:
    rows = [
        {
            "recommendation": "tighten_v2_final_candidate",
            "rule_hint": "prefer score_rank top50, sector top10/top30, template_hit_count >=4, avoid extreme intraday fade",
            "evidence_summary": _top_bad_evidence(bad_slice_audit),
        }
    ]
    if not high_elasticity_slice.empty:
        rows.append(
            {
                "recommendation": "split_high_elasticity_trend_shadow",
                "rule_hint": "keep high volume/high volatility dual momentum names separate from mid-term low-risk trend pool",
                "evidence_summary": high_elasticity_slice.head(5).to_json(orient="records", force_ascii=False),
            }
        )
    if not purity_slice.empty:
        best = purity_slice.sort_values(["future_60d_return_mean", "future_60d_max_drawdown_mean"], ascending=False).head(3)
        rows.append(
            {
                "recommendation": "promote_best_slices_for_shadow_replay",
                "rule_hint": "use best slices as candidate filters before changing watchlist generation",
                "evidence_summary": best[["slice_dimension", "slice_value", "sample_count", "future_60d_return_mean"]].to_json(
                    orient="records", force_ascii=False
                ),
            }
        )
    if not v2_1_candidate_effectiveness.empty:
        best = v2_1_candidate_effectiveness.sort_values(
            ["future_60d_return_mean", "future_60d_max_drawdown_mean"], ascending=False
        ).head(3)
        rows.append(
            {
                "recommendation": "replay_v2_1_quality_no_highvol_extremeamount",
                "rule_hint": "candidate = v2_final AND quality fundamental AND no high volatility AND no extreme volume",
                "evidence_summary": best[
                    ["candidate_set", "sample_count", "future_60d_return_mean", "future_60d_max_drawdown_mean"]
                ].to_json(orient="records", force_ascii=False),
            }
        )
    return pd.DataFrame(rows)


def _render_report(
    *,
    purity_slice: pd.DataFrame,
    bad_slice_audit: pd.DataFrame,
    high_elasticity_slice: pd.DataFrame,
    v2_1_candidate_effectiveness: pd.DataFrame,
    missed_winner_audit: pd.DataFrame,
    recommendations: pd.DataFrame,
    warnings: list[str],
) -> str:
    lines = [
        "# Trend Discovery v2 Purity Audit",
        "",
        "## 1. Scope",
        "审计 v2_final_candidate 内部切片，目标是在保留召回的基础上提高收益、降低回撤；本报告不改 stock_score，不生成交易建议。",
        "",
        "## 2. Warnings",
        *([f"- {warning}" for warning in warnings] or ["- none"]),
        "",
        "## 3. Purity Slice",
        purity_slice.head(30).to_markdown(index=False),
        "",
        "## 4. Bad Slice Audit",
        bad_slice_audit.head(30).to_markdown(index=False),
        "",
        "## 5. High Elasticity Slice",
        high_elasticity_slice.head(20).to_markdown(index=False),
        "",
        "## 6. v2.1 Candidate Effectiveness",
        v2_1_candidate_effectiveness.to_markdown(index=False),
        "",
        "## 7. Missed Winner Audit",
        missed_winner_audit.head(20).to_markdown(index=False),
        "",
        "## 8. Recommendations",
        recommendations.to_markdown(index=False),
    ]
    return "\n".join(lines) + "\n"


def _score_rank_bucket(value: Any) -> str:
    number = _float_or_none(value)
    if number is None:
        return "unknown_score_rank"
    if number <= 10:
        return "top10"
    if number <= 30:
        return "top30"
    if number <= 50:
        return "top50"
    return "rank_gt50"


def _amount_bucket(value: Any) -> str:
    number = _float_or_none(value)
    if number is None:
        return "unknown_amount"
    if number < 1.0:
        return "no_volume_expansion"
    if number <= 3.5:
        return "moderate_volume"
    return "extreme_volume"


def _drawdown_bucket(value: Any) -> str:
    number = _float_or_none(value)
    if number is None:
        return "unknown_intraday_fade"
    if number <= 0.04:
        return "low_intraday_fade"
    if number <= 0.08:
        return "mid_intraday_fade"
    return "high_intraday_fade"


def _volatility_bucket(value: Any) -> str:
    number = _float_or_none(value)
    if number is None:
        return "unknown_volatility"
    if number <= 0.03:
        return "low_volatility"
    if number <= 0.06:
        return "mid_volatility"
    if number <= 0.10:
        return "high_volatility"
    return "extreme_volatility"


def _template_hit_bucket(value: Any) -> str:
    number = _float_or_none(value)
    if number is None:
        return "unknown_template_hit"
    if number >= 5:
        return "hit_5plus"
    if number >= 4:
        return "hit_4"
    if number >= 2:
        return "hit_2_3"
    return "hit_0_1"


def _bad_slice_reason(row: pd.Series) -> str:
    reasons = []
    if _float_or_none(row.get("future_60d_return_mean")) is not None and float(row["future_60d_return_mean"]) < 0.03:
        reasons.append("low_60d_return")
    if _float_or_none(row.get("future_60d_max_drawdown_mean")) is not None and float(row["future_60d_max_drawdown_mean"]) < -0.18:
        reasons.append("deep_60d_drawdown")
    return ",".join(reasons) or "relative_underperforming_slice"


def _winner_miss_reason(row: pd.Series) -> str:
    if row["trend_discovery_v2_final_candidate"]:
        return "captured_by_v2_final"
    if row["trend_discovery_v2_high_purity"]:
        return "lost_after_final_filter"
    if row["trend_discovery_v2_core"]:
        return "lost_after_high_purity_filter"
    if row["trend_discovery_v2_recall"]:
        return "lost_after_core_filter"
    return "not_in_v2_recall_or_not_in_diagnostics"


def _metric_row(frame: pd.DataFrame, *, key_name: str, key_value: str) -> dict[str, Any]:
    row: dict[str, Any] = {key_name: key_value, "sample_count": len(frame)}
    for metric in METRICS:
        row[_metric_name(metric)] = pd.to_numeric(frame.get(metric, pd.Series(dtype=float)), errors="coerce").mean()
    return row


def _top_bad_evidence(bad_slice_audit: pd.DataFrame) -> str:
    if bad_slice_audit.empty:
        return "no_bad_slice_identified"
    cols = ["slice_dimension", "slice_value", "sample_count", "future_60d_return_mean", "future_60d_max_drawdown_mean"]
    available = [column for column in cols if column in bad_slice_audit.columns]
    return bad_slice_audit[available].head(5).to_json(orient="records", force_ascii=False)


def _metric_name(column: str) -> str:
    if column == "hit_double_within_60d":
        return "hit_double_within_60d_rate"
    return f"{column}_mean"


def _metric_output_columns() -> list[str]:
    return [_metric_name(metric) for metric in METRICS]


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
