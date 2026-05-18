from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all
from stock_research.technical_features import compute_daily_technical_features, _atr, _wilder_average


ROOT = Path(__file__).resolve().parents[2]

FEATURE_BUCKET_COLUMNS = [
    "feature_name",
    "bucket",
    "sample_count",
    "avg_future_1d_return",
    "avg_future_3d_return",
    "avg_future_5d_return",
    "avg_future_10d_return",
    "avg_future_20d_return",
    "median_future_3d_return",
    "median_future_5d_return",
    "median_future_10d_return",
    "win_rate_1d",
    "win_rate_3d",
    "win_rate_5d",
    "win_rate_10d",
    "avg_future_3d_max_drawdown",
    "avg_future_5d_max_drawdown",
    "avg_future_10d_max_drawdown",
    "feature_null_rate",
    "signal_type",
]

COMBO_COLUMNS = [
    "combo_name",
    "combo_definition",
    "sample_count",
    "avg_future_1d_return",
    "avg_future_3d_return",
    "avg_future_5d_return",
    "avg_future_10d_return",
    "median_future_5d_return",
    "win_rate_1d",
    "win_rate_3d",
    "win_rate_5d",
    "win_rate_10d",
    "avg_future_5d_max_drawdown",
    "avg_future_10d_max_drawdown",
    "signal_type",
    "interpretation",
]

REGIME_COLUMNS = [
    "market_regime",
    "indicator_type",
    "feature_name",
    "combo_name",
    "bucket",
    "signal_flag",
    "sample_count",
    "avg_future_3d_return",
    "avg_future_5d_return",
    "avg_future_10d_return",
    "win_rate_3d",
    "win_rate_5d",
    "win_rate_10d",
    "avg_future_5d_max_drawdown",
    "avg_future_10d_max_drawdown",
]

CASE_EVENT_COLUMNS = [
    "verified_case_type",
    "success_or_failure",
    "event_type",
    "relative_day",
    "feature_name",
    "avg_feature_value",
    "median_feature_value",
    "sample_count",
]

LHB_CROSS_COLUMNS = [
    "combo_name",
    "sample_count",
    "avg_future_3d_return",
    "avg_future_5d_return",
    "avg_future_10d_return",
    "win_rate_5d",
    "avg_future_5d_max_drawdown",
    "avg_future_10d_max_drawdown",
    "interpretation",
]

CORRELATION_COLUMNS = [
    "feature_a",
    "feature_b",
    "correlation",
    "redundancy_group",
    "recommended_keep",
    "reason",
]

RECOMMENDATION_COLUMNS = [
    "feature_or_method",
    "category",
    "signal_type",
    "recommended_usage",
    "evidence_summary",
    "sample_count",
    "confidence_level",
    "next_action",
]

CORE_FEATURES = [
    "close_vs_ma5",
    "close_vs_ma10",
    "close_vs_ma20",
    "close_vs_ma60",
    "ma5_slope",
    "ma10_slope",
    "ma20_slope",
    "ma60_slope",
    "ma_bullish_alignment",
    "macd_dif",
    "macd_dea",
    "macd_hist",
    "macd_above_zero",
    "macd_hist_rising",
    "macd_cross_up",
    "macd_cross_down",
    "rsi6",
    "rsi12",
    "rsi24",
    "rsi_overbought",
    "rsi_oversold",
    "boll_position_20",
    "boll_width_20",
    "boll_break_upper",
    "boll_break_lower",
    "boll_squeeze",
    "kdj_k",
    "kdj_d",
    "kdj_j",
    "kdj_overbought",
    "kdj_oversold",
    "kdj_cross_up",
    "amount_vs_5d",
    "amount_vs_20d",
    "volume_vs_5d",
    "volume_vs_20d",
    "turnover_vs_20d",
    "atr_pct14",
    "volatility_5d",
    "volatility_20d",
    "max_drawdown_5d",
    "max_drawdown_10d",
    "max_drawdown_20d",
    "high_to_close_drawdown",
    "close_position_in_day",
    "amplitude",
    "adx14",
    "plus_di14",
    "minus_di14",
    "cci14",
    "obv",
    "mfi14",
]

BASE_TECH_COLUMNS = [
    "ma5",
    "ma10",
    "ma20",
    "ma60",
    "ma120",
    "ema12",
    "ema26",
    "macd_dif",
    "macd_dea",
    "macd_hist",
    "rsi6",
    "rsi12",
    "rsi24",
    "boll_upper_20",
    "boll_mid_20",
    "boll_lower_20",
    "atr14",
    "cci14",
    "kdj_k",
    "kdj_d",
    "kdj_j",
    "adx14",
    "obv",
    "ret_1d",
    "ret_20d",
    "close_position_in_day",
]


@dataclass(frozen=True)
class ValidationInputPaths:
    case_view: Path | None
    case_snapshot: Path | None
    lhb_case_detail: Path | None
    market_regime: Path | None
    industry_focus: Path | None
    industry_mainline: Path | None


def run_validate_technical_methods(
    *,
    start_date: str,
    end_date: str,
    adjust_type: str = "qfq",
    sample_size: int | None = None,
    asset_id: str | None = None,
    ts_code: str | None = None,
    feature_source: str = "technical_table",
    output_dir: str | Path,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    warnings: list[str] = []
    bars = load_validation_bars(
        start_date=start_date,
        end_date=end_date,
        adjust_type=adjust_type,
        sample_size=sample_size,
        asset_id=asset_id,
        ts_code=ts_code,
        service=service,
    )
    paths = _resolve_optional_inputs(output_dir)
    case_view = _load_optional_csv(paths.case_view, warnings, "case_view")
    case_snapshot = _load_optional_csv(paths.case_snapshot, warnings, "case_snapshot")
    lhb_detail = _load_optional_csv(paths.lhb_case_detail, warnings, "lhb_case_detail")
    market_regime = _load_optional_csv(paths.market_regime, warnings, "market_regime")
    tech_table = pd.DataFrame()
    source_used = feature_source
    if feature_source == "technical_table":
        tech_table = load_validation_technical_table(
            start_date=start_date,
            end_date=end_date,
            adjust_type=adjust_type,
            sample_size=sample_size,
            asset_id=asset_id,
            ts_code=ts_code,
            service=service,
        )
        if tech_table.empty:
            warnings.append("technical_table had no matching rows in requested window; fell back to computed_on_fly")
            source_used = "computed_on_fly"
    result = build_technical_method_validation_from_frames(
        bars=bars,
        output_dir=output_dir,
        case_view=case_view,
        case_snapshot=case_snapshot,
        lhb_case_detail=lhb_detail,
        regime_frame=market_regime,
        technical_features=tech_table if source_used == "technical_table" else None,
        feature_source=source_used,
        warnings=warnings,
        start_date=start_date,
        end_date=end_date,
        adjust_type=adjust_type,
    )
    return result


def build_technical_method_validation_from_frames(
    *,
    bars: pd.DataFrame,
    output_dir: str | Path,
    case_view: pd.DataFrame | None = None,
    case_snapshot: pd.DataFrame | None = None,
    lhb_case_detail: pd.DataFrame | None = None,
    regime_frame: pd.DataFrame | None = None,
    technical_features: pd.DataFrame | None = None,
    feature_source: str = "computed_on_fly",
    warnings: list[str] | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    adjust_type: str = "qfq",
) -> dict[str, Any]:
    warnings = list(warnings or [])
    dataset = compute_validation_features(bars, technical_features=technical_features)
    if dataset.empty:
        warnings.append("validation dataset is empty")

    regime_frame = _ensure_market_regime(dataset, regime_frame, warnings)
    dataset = dataset.merge(regime_frame[["trade_date", "market_regime"]], on="trade_date", how="left")
    dataset["market_regime"] = dataset["market_regime"].fillna("unknown")

    feature_bucket, feature_summary = build_feature_bucket_effectiveness(dataset)
    combo_effectiveness = build_combo_effectiveness(dataset)
    correlation = build_feature_correlation(dataset)
    redundancy = build_redundancy_report(correlation, feature_summary)
    feature_bucket = _apply_redundant_signal_override(feature_bucket, redundancy)
    feature_summary = _apply_redundant_signal_override_summary(feature_summary, redundancy)
    regime_effectiveness = build_regime_effectiveness(dataset, feature_bucket, combo_effectiveness)
    case_effectiveness = build_case_event_effectiveness(dataset, case_view, case_snapshot)
    lhb_cross = build_lhb_cross_effectiveness(dataset, lhb_case_detail, warnings)
    recommendation = build_recommendation(feature_summary, combo_effectiveness, redundancy)
    report = build_validation_report(
        dataset=dataset,
        feature_source=feature_source,
        adjust_type=adjust_type,
        start_date=start_date or _date_or_empty(dataset["trade_date"].min() if not dataset.empty else ""),
        end_date=end_date or _date_or_empty(dataset["trade_date"].max() if not dataset.empty else ""),
        feature_bucket=feature_bucket,
        combo_effectiveness=combo_effectiveness,
        regime_effectiveness=regime_effectiveness,
        case_effectiveness=case_effectiveness,
        lhb_cross=lhb_cross,
        redundancy=redundancy,
        recommendation=recommendation,
        warnings=warnings,
    )

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = {
        "feature_bucket_effectiveness": str(out / "technical_method_feature_bucket_effectiveness.csv"),
        "combo_effectiveness": str(out / "technical_method_combo_effectiveness.csv"),
        "regime_effectiveness": str(out / "technical_method_regime_effectiveness.csv"),
        "case_event_effectiveness": str(out / "technical_method_case_event_effectiveness.csv"),
        "lhb_cross_effectiveness": str(out / "technical_method_lhb_cross_effectiveness.csv"),
        "feature_correlation": str(out / "technical_method_feature_correlation.csv"),
        "redundancy_report": str(out / "technical_method_redundancy_report.csv"),
        "recommendation": str(out / "technical_method_recommendation.csv"),
        "report": str(out / "technical_method_validation_report.md"),
    }
    feature_bucket.to_csv(paths["feature_bucket_effectiveness"], index=False)
    combo_effectiveness.to_csv(paths["combo_effectiveness"], index=False)
    regime_effectiveness.to_csv(paths["regime_effectiveness"], index=False)
    case_effectiveness.to_csv(paths["case_event_effectiveness"], index=False)
    lhb_cross.to_csv(paths["lhb_cross_effectiveness"], index=False)
    correlation.to_csv(paths["feature_correlation"], index=False)
    redundancy.to_csv(paths["redundancy_report"], index=False)
    recommendation.to_csv(paths["recommendation"], index=False)
    Path(paths["report"]).write_text(report, encoding="utf-8")
    return {
        "dataset": dataset,
        "feature_bucket_effectiveness": feature_bucket,
        "combo_effectiveness": combo_effectiveness,
        "regime_effectiveness": regime_effectiveness,
        "case_event_effectiveness": case_effectiveness,
        "lhb_cross_effectiveness": lhb_cross,
        "feature_correlation": correlation,
        "redundancy_report": redundancy,
        "recommendation": recommendation,
        "warnings": warnings,
        "paths": paths,
    }


def load_validation_bars(
    *,
    start_date: str,
    end_date: str,
    adjust_type: str = "qfq",
    sample_size: int | None = None,
    asset_id: str | None = None,
    ts_code: str | None = None,
    service: str = SETTINGS.research_service,
) -> pd.DataFrame:
    params: list[Any] = [adjust_type, start_date, end_date]
    filters = ["bars.adjust_type = %s", "bars.trade_date BETWEEN %s AND %s", "bars.trade_status = '1'"]
    selected_cte = ""
    if asset_id:
        filters.append("bars.asset_id = %s")
        params.append(str(asset_id))
    elif ts_code:
        filters.append("bars.asset_id = %s")
        params.append(_ts_code_to_asset_id(ts_code))
    elif sample_size:
        selected_cte = """
        WITH selected_assets AS (
            SELECT DISTINCT asset_id
            FROM market_daily_bar
            WHERE adjust_type = %s
              AND trade_date BETWEEN %s AND %s
            ORDER BY asset_id
            LIMIT %s
        )
        """
        params = [adjust_type, start_date, end_date, int(sample_size), adjust_type, start_date, end_date]
        filters = ["bars.adjust_type = %s", "bars.trade_date BETWEEN %s AND %s", "bars.trade_status = '1'", "bars.asset_id IN (SELECT asset_id FROM selected_assets)"]
    sql = f"""
    {selected_cte}
    SELECT
        bars.asset_id,
        bars.trade_date,
        bars.open,
        bars.high,
        bars.low,
        bars.close,
        bars.preclose,
        bars.volume,
        bars.amount,
        bars.turnover_rate,
        bars.pct_chg,
        bars.is_st,
        bars.trade_status
    FROM market_daily_bar bars
    WHERE {' AND '.join(filters)}
    ORDER BY bars.asset_id, bars.trade_date
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, params)
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    frame["ts_code"] = frame["asset_id"].map(_asset_id_to_ts_code)
    return frame


def load_validation_technical_table(
    *,
    start_date: str,
    end_date: str,
    adjust_type: str = "qfq",
    sample_size: int | None = None,
    asset_id: str | None = None,
    ts_code: str | None = None,
    service: str = SETTINGS.research_service,
) -> pd.DataFrame:
    params: list[Any] = [start_date, end_date, adjust_type]
    filters = ["trade_date BETWEEN %s AND %s", "adjust_type = %s"]
    if asset_id:
        filters.append("asset_id = %s")
        params.append(str(asset_id))
    elif ts_code:
        filters.append("asset_id = %s")
        params.append(_ts_code_to_asset_id(ts_code))
    elif sample_size:
        filters.append("asset_id IN (SELECT DISTINCT asset_id FROM factor.stock_technical_features_daily WHERE trade_date BETWEEN %s AND %s AND adjust_type = %s ORDER BY asset_id LIMIT %s)")
        params.extend([start_date, end_date, adjust_type, int(sample_size)])
    sql = f"""
    SELECT *
    FROM factor.stock_technical_features_daily
    WHERE {' AND '.join(filters)}
    ORDER BY asset_id, trade_date
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, params)
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    frame["ts_code"] = frame["asset_id"].map(_asset_id_to_ts_code)
    return frame


def compute_validation_features(bars: pd.DataFrame, technical_features: pd.DataFrame | None = None) -> pd.DataFrame:
    if bars.empty:
        return pd.DataFrame()
    base = bars.copy()
    base = base.sort_values(["asset_id", "trade_date"]).reset_index(drop=True)
    results: list[pd.DataFrame] = []
    tech_lookup = None
    if technical_features is not None and not technical_features.empty:
        tech_lookup = technical_features.copy()
        tech_lookup = tech_lookup.sort_values(["asset_id", "trade_date"]).reset_index(drop=True)
    for asset_id, group in base.groupby("asset_id", sort=False):
        ordered = group.sort_values("trade_date").reset_index(drop=True).copy()
        if tech_lookup is not None:
            asset_tech = tech_lookup[tech_lookup["asset_id"] == asset_id].copy()
            tech_frame = asset_tech.drop(columns=[col for col in ["ts_code", "adjust_type", "source", "source_data_version", "calc_version"] if col in asset_tech.columns], errors="ignore")
        else:
            tech_frame = compute_daily_technical_features(
                ordered[
                    [
                        "trade_date",
                        "open",
                        "high",
                        "low",
                        "close",
                        "preclose",
                        "volume",
                        "amount",
                        "turnover_rate",
                    ]
                ]
            )
        merged = ordered.merge(tech_frame, on="trade_date", how="left")
        merged = _derive_extended_features(merged)
        merged = _append_future_metrics(merged)
        results.append(merged)
    dataset = pd.concat(results, ignore_index=True)
    feature_cols = [col for col in CORE_FEATURES if col in dataset.columns]
    metric_cols = [col for col in dataset.columns if col.startswith("future_")]
    keep_cols = [
        "asset_id",
        "ts_code",
        "trade_date",
        "open",
        "high",
        "low",
        "close",
        "preclose",
        "volume",
        "amount",
        "turnover_rate",
        "pct_chg",
    ] + feature_cols + metric_cols
    return dataset.reindex(columns=keep_cols)


def build_feature_bucket_effectiveness(dataset: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    if dataset.empty:
        return pd.DataFrame(columns=FEATURE_BUCKET_COLUMNS), pd.DataFrame(columns=["feature_name", "signal_type", "sample_count", "feature_null_rate"])
    rows: list[dict[str, Any]] = []
    summary_rows: list[dict[str, Any]] = []
    for feature in [name for name in CORE_FEATURES if name in dataset.columns]:
        series = pd.to_numeric(dataset[feature], errors="coerce")
        valid = dataset.loc[series.notna()].copy()
        null_rate = 1.0 - (len(valid) / len(dataset) if len(dataset) else 0.0)
        if valid.empty:
            continue
        valid[feature] = pd.to_numeric(valid[feature], errors="coerce")
        valid["bucket"] = _assign_buckets(valid[feature])
        bucket_rows = []
        for bucket, group in valid.groupby("bucket", dropna=False):
            bucket_rows.append(
                {
                    "feature_name": feature,
                    "bucket": bucket,
                    "sample_count": int(len(group)),
                    "avg_future_1d_return": pd.to_numeric(group["future_1d_return"], errors="coerce").mean(),
                    "avg_future_3d_return": pd.to_numeric(group["future_3d_return"], errors="coerce").mean(),
                    "avg_future_5d_return": pd.to_numeric(group["future_5d_return"], errors="coerce").mean(),
                    "avg_future_10d_return": pd.to_numeric(group["future_10d_return"], errors="coerce").mean(),
                    "avg_future_20d_return": pd.to_numeric(group["future_20d_return"], errors="coerce").mean(),
                    "median_future_3d_return": pd.to_numeric(group["future_3d_return"], errors="coerce").median(),
                    "median_future_5d_return": pd.to_numeric(group["future_5d_return"], errors="coerce").median(),
                    "median_future_10d_return": pd.to_numeric(group["future_10d_return"], errors="coerce").median(),
                    "win_rate_1d": _win_rate(group["future_1d_return"]),
                    "win_rate_3d": _win_rate(group["future_3d_return"]),
                    "win_rate_5d": _win_rate(group["future_5d_return"]),
                    "win_rate_10d": _win_rate(group["future_10d_return"]),
                    "avg_future_3d_max_drawdown": pd.to_numeric(group["future_3d_max_drawdown"], errors="coerce").mean(),
                    "avg_future_5d_max_drawdown": pd.to_numeric(group["future_5d_max_drawdown"], errors="coerce").mean(),
                    "avg_future_10d_max_drawdown": pd.to_numeric(group["future_10d_max_drawdown"], errors="coerce").mean(),
                    "feature_null_rate": null_rate,
                }
            )
        bucket_frame = pd.DataFrame(bucket_rows).sort_values("bucket").reset_index(drop=True)
        signal_type = _classify_feature_signal(bucket_frame)
        bucket_frame["signal_type"] = signal_type
        rows.extend(bucket_frame.to_dict("records"))
        summary_rows.append(
            {
                "feature_name": feature,
                "signal_type": signal_type,
                "sample_count": int(len(valid)),
                "feature_null_rate": null_rate,
            }
        )
    return (
        pd.DataFrame(rows).reindex(columns=FEATURE_BUCKET_COLUMNS),
        pd.DataFrame(summary_rows),
    )


def build_combo_effectiveness(dataset: pd.DataFrame) -> pd.DataFrame:
    if dataset.empty:
        return pd.DataFrame(columns=COMBO_COLUMNS)
    baseline = _baseline_stats(dataset)
    rows: list[dict[str, Any]] = []
    for combo_name, combo_definition, mask in _combo_definitions(dataset):
        group = dataset.loc[mask].copy()
        signal_type = _classify_group_signal(group, baseline) if not group.empty else "weak_signal"
        rows.append(
            {
                "combo_name": combo_name,
                "combo_definition": combo_definition,
                "sample_count": int(len(group)),
                "avg_future_1d_return": pd.to_numeric(group["future_1d_return"], errors="coerce").mean() if not group.empty else None,
                "avg_future_3d_return": pd.to_numeric(group["future_3d_return"], errors="coerce").mean() if not group.empty else None,
                "avg_future_5d_return": pd.to_numeric(group["future_5d_return"], errors="coerce").mean() if not group.empty else None,
                "avg_future_10d_return": pd.to_numeric(group["future_10d_return"], errors="coerce").mean() if not group.empty else None,
                "median_future_5d_return": pd.to_numeric(group["future_5d_return"], errors="coerce").median() if not group.empty else None,
                "win_rate_1d": _win_rate(group["future_1d_return"]) if not group.empty else None,
                "win_rate_3d": _win_rate(group["future_3d_return"]) if not group.empty else None,
                "win_rate_5d": _win_rate(group["future_5d_return"]) if not group.empty else None,
                "win_rate_10d": _win_rate(group["future_10d_return"]) if not group.empty else None,
                "avg_future_5d_max_drawdown": pd.to_numeric(group["future_5d_max_drawdown"], errors="coerce").mean() if not group.empty else None,
                "avg_future_10d_max_drawdown": pd.to_numeric(group["future_10d_max_drawdown"], errors="coerce").mean() if not group.empty else None,
                "signal_type": signal_type,
                "interpretation": _combo_interpretation(combo_name, signal_type) if not group.empty else f"{combo_name} had no samples in this run.",
            }
        )
    return pd.DataFrame(rows).reindex(columns=COMBO_COLUMNS).sort_values(["signal_type", "avg_future_10d_return"], ascending=[True, False]).reset_index(drop=True)


def build_regime_effectiveness(
    dataset: pd.DataFrame,
    feature_bucket: pd.DataFrame,
    combo_effectiveness: pd.DataFrame,
) -> pd.DataFrame:
    if dataset.empty or "market_regime" not in dataset.columns:
        return pd.DataFrame(columns=REGIME_COLUMNS)
    rows: list[dict[str, Any]] = []
    for feature in [name for name in CORE_FEATURES if name in dataset.columns]:
        frame = dataset[["market_regime", feature, "future_3d_return", "future_5d_return", "future_10d_return", "future_5d_max_drawdown", "future_10d_max_drawdown"]].copy()
        frame = frame[pd.to_numeric(frame[feature], errors="coerce").notna()].copy()
        if frame.empty:
            continue
        frame["bucket"] = _assign_buckets(pd.to_numeric(frame[feature], errors="coerce"))
        for (regime, bucket), group in frame.groupby(["market_regime", "bucket"], dropna=False):
            rows.append(
                {
                    "market_regime": regime,
                    "indicator_type": "feature",
                    "feature_name": feature,
                    "combo_name": "",
                    "bucket": bucket,
                    "signal_flag": "",
                    "sample_count": int(len(group)),
                    "avg_future_3d_return": pd.to_numeric(group["future_3d_return"], errors="coerce").mean(),
                    "avg_future_5d_return": pd.to_numeric(group["future_5d_return"], errors="coerce").mean(),
                    "avg_future_10d_return": pd.to_numeric(group["future_10d_return"], errors="coerce").mean(),
                    "win_rate_3d": _win_rate(group["future_3d_return"]),
                    "win_rate_5d": _win_rate(group["future_5d_return"]),
                    "win_rate_10d": _win_rate(group["future_10d_return"]),
                    "avg_future_5d_max_drawdown": pd.to_numeric(group["future_5d_max_drawdown"], errors="coerce").mean(),
                    "avg_future_10d_max_drawdown": pd.to_numeric(group["future_10d_max_drawdown"], errors="coerce").mean(),
                }
            )
    for combo_name, _, mask in _combo_definitions(dataset):
        group = dataset.loc[mask].copy()
        if group.empty:
            continue
        for regime, regime_group in group.groupby("market_regime", dropna=False):
            rows.append(
                {
                    "market_regime": regime,
                    "indicator_type": "combo",
                    "feature_name": "",
                    "combo_name": combo_name,
                    "bucket": "",
                    "signal_flag": 1,
                    "sample_count": int(len(regime_group)),
                    "avg_future_3d_return": pd.to_numeric(regime_group["future_3d_return"], errors="coerce").mean(),
                    "avg_future_5d_return": pd.to_numeric(regime_group["future_5d_return"], errors="coerce").mean(),
                    "avg_future_10d_return": pd.to_numeric(regime_group["future_10d_return"], errors="coerce").mean(),
                    "win_rate_3d": _win_rate(regime_group["future_3d_return"]),
                    "win_rate_5d": _win_rate(regime_group["future_5d_return"]),
                    "win_rate_10d": _win_rate(regime_group["future_10d_return"]),
                    "avg_future_5d_max_drawdown": pd.to_numeric(regime_group["future_5d_max_drawdown"], errors="coerce").mean(),
                    "avg_future_10d_max_drawdown": pd.to_numeric(regime_group["future_10d_max_drawdown"], errors="coerce").mean(),
                }
            )
    return pd.DataFrame(rows).reindex(columns=REGIME_COLUMNS)


def build_case_event_effectiveness(
    dataset: pd.DataFrame,
    case_view: pd.DataFrame | None,
    case_snapshot: pd.DataFrame | None,
) -> pd.DataFrame:
    if dataset.empty or case_view is None or case_view.empty:
        return pd.DataFrame(columns=CASE_EVENT_COLUMNS)
    events = case_view.copy()
    if case_snapshot is not None and not case_snapshot.empty and "case_id" in events.columns:
        zero = case_snapshot.copy()
        if "relative_day" in zero.columns:
            zero = zero[pd.to_numeric(zero["relative_day"], errors="coerce").fillna(999).eq(0)]
        events = events.merge(
            zero[["case_id", "event_type", "event_date"]].drop_duplicates(subset=["case_id"]),
            on="case_id",
            how="left",
            suffixes=("", "_snapshot"),
        )
        events["event_type"] = events["event_type"].fillna(events.get("event_type_snapshot"))
        events["event_date"] = events["event_date"].fillna(events.get("event_date_snapshot"))
    rows: list[dict[str, Any]] = []
    by_ts = {ts: group.reset_index(drop=True) for ts, group in dataset.groupby("ts_code", sort=False)}
    for event in events.fillna("").to_dict("records"):
        ts_code = str(event.get("ts_code") or "")
        event_date = str(event.get("event_date") or "")
        if ts_code not in by_ts or not event_date:
            continue
        ordered = by_ts[ts_code]
        idx_matches = ordered.index[ordered["trade_date"] == event_date].tolist()
        if not idx_matches:
            continue
        idx = idx_matches[0]
        start = max(0, idx - 5)
        end = min(len(ordered), idx + 6)
        window = ordered.iloc[start:end].copy()
        window["relative_day"] = range(start - idx, end - idx)
        for _, row in window.iterrows():
            for feature in [name for name in CORE_FEATURES if name in window.columns]:
                value = pd.to_numeric(pd.Series([row.get(feature)]), errors="coerce").iloc[0]
                if pd.isna(value):
                    continue
                rows.append(
                    {
                        "verified_case_type": event.get("verified_case_type") or event.get("verified_case_type_v2_1") or event.get("case_type") or "",
                        "success_or_failure": event.get("success_or_failure") or "",
                        "event_type": event.get("event_type") or "",
                        "relative_day": int(row["relative_day"]),
                        "feature_name": feature,
                        "feature_value": float(value),
                    }
                )
    if not rows:
        return pd.DataFrame(columns=CASE_EVENT_COLUMNS)
    frame = pd.DataFrame(rows)
    grouped = frame.groupby(["verified_case_type", "success_or_failure", "event_type", "relative_day", "feature_name"], dropna=False)
    result = grouped["feature_value"].agg(avg_feature_value="mean", median_feature_value="median", sample_count="size").reset_index()
    return result.reindex(columns=CASE_EVENT_COLUMNS)


def build_lhb_cross_effectiveness(
    dataset: pd.DataFrame,
    lhb_case_detail: pd.DataFrame | None,
    warnings: list[str],
) -> pd.DataFrame:
    if lhb_case_detail is None or lhb_case_detail.empty:
        warnings.append("LHB detail file was not available; skipped technical/LHB cross diagnostics")
        return pd.DataFrame(columns=LHB_CROSS_COLUMNS)
    merged = lhb_case_detail.copy()
    merged["ts_code"] = merged.get("ts_code", pd.Series(dtype="object")).fillna("").astype(str).str.upper()
    merged["event_date"] = pd.to_datetime(merged.get("event_date", pd.Series(dtype="object")), errors="coerce").dt.strftime("%Y-%m-%d")
    base = dataset.copy()
    base["ts_code"] = base.get("ts_code", pd.Series(dtype="object")).fillna("").astype(str).str.upper()
    base["trade_date"] = pd.to_datetime(base.get("trade_date", pd.Series(dtype="object")), errors="coerce").dt.strftime("%Y-%m-%d")
    merged = merged.merge(
        base,
        left_on=["ts_code", "event_date"],
        right_on=["ts_code", "trade_date"],
        how="left",
        suffixes=("", "_feature"),
    )
    combos = {
        "lhb_high_risk_plus_rsi_overheat": (pd.to_numeric(merged.get("lhb_risk_score"), errors="coerce") >= 0.66) & (pd.to_numeric(merged.get("rsi6"), errors="coerce") >= 80),
        "lhb_high_risk_plus_extreme_volume": (pd.to_numeric(merged.get("lhb_risk_score"), errors="coerce") >= 0.66) & (pd.to_numeric(merged.get("amount_vs_20d"), errors="coerce") >= 5),
        "lhb_high_risk_plus_high_intraday_fade": (pd.to_numeric(merged.get("lhb_risk_score"), errors="coerce") >= 0.66) & (pd.to_numeric(merged.get("high_to_close_drawdown"), errors="coerce") >= 0.06),
        "lhb_negative_net_buy_plus_low_close_position": merged.get("lhb_negative_net_buy", pd.Series(dtype=bool)).fillna(False).astype(bool) & (pd.to_numeric(merged.get("close_position_in_day"), errors="coerce") <= 0.30),
        "lhb_positive_net_buy_plus_not_overheated": (pd.to_numeric(merged.get("lhb_net_buy_amount_event"), errors="coerce") > 0) & (pd.to_numeric(merged.get("rsi6"), errors="coerce") < 80) & (pd.to_numeric(merged.get("amount_vs_20d"), errors="coerce").between(1.0, 3.0)),
        "lhb_after_event_attention_plus_technical_weakening": merged.get("lhb_after_event_attention", pd.Series(dtype=bool)).fillna(False).astype(bool) & ((pd.to_numeric(merged.get("macd_hist_rising"), errors="coerce") == 0) | (pd.to_numeric(merged.get("close_vs_ma5"), errors="coerce") < 0) | (pd.to_numeric(merged.get("high_to_close_drawdown"), errors="coerce") >= 0.05)),
    }
    rows: list[dict[str, Any]] = []
    for combo_name, mask in combos.items():
        group = merged.loc[mask].copy()
        rows.append(
            {
                "combo_name": combo_name,
                "sample_count": int(len(group)),
                "avg_future_3d_return": pd.to_numeric(group["future_3d_return"], errors="coerce").mean() if not group.empty else None,
                "avg_future_5d_return": pd.to_numeric(group["future_5d_return"], errors="coerce").mean() if not group.empty else None,
                "avg_future_10d_return": pd.to_numeric(group["future_10d_return"], errors="coerce").mean() if not group.empty else None,
                "win_rate_5d": _win_rate(group["future_5d_return"]) if not group.empty else None,
                "avg_future_5d_max_drawdown": pd.to_numeric(group["future_5d_max_drawdown"], errors="coerce").mean() if not group.empty else None,
                "avg_future_10d_max_drawdown": pd.to_numeric(group["future_10d_max_drawdown"], errors="coerce").mean() if not group.empty else None,
                "interpretation": _lhb_combo_interpretation(combo_name) if not group.empty else f"{combo_name} had no matching LHB/technical overlap in this run.",
            }
        )
    return pd.DataFrame(rows).reindex(columns=LHB_CROSS_COLUMNS)


def build_feature_correlation(dataset: pd.DataFrame) -> pd.DataFrame:
    feature_cols = [name for name in CORE_FEATURES if name in dataset.columns]
    if dataset.empty or not feature_cols:
        return pd.DataFrame(columns=CORRELATION_COLUMNS)
    numeric = dataset[feature_cols].apply(pd.to_numeric, errors="coerce")
    if len(numeric) > 100000:
        numeric = numeric.sample(100000, random_state=42)
    corr = numeric.corr()
    rows: list[dict[str, Any]] = []
    for idx, feature_a in enumerate(feature_cols):
        for feature_b in feature_cols[idx + 1 :]:
            value = corr.loc[feature_a, feature_b]
            if pd.isna(value):
                continue
            rows.append(
                {
                    "feature_a": feature_a,
                    "feature_b": feature_b,
                    "correlation": float(value),
                    "redundancy_group": "",
                    "recommended_keep": "",
                    "reason": "",
                }
            )
    return pd.DataFrame(rows).reindex(columns=CORRELATION_COLUMNS)


def build_redundancy_report(correlation: pd.DataFrame, feature_summary: pd.DataFrame) -> pd.DataFrame:
    if correlation.empty:
        return pd.DataFrame(columns=CORRELATION_COLUMNS)
    strong = correlation[correlation["correlation"].abs() >= 0.85].copy()
    if strong.empty:
        return pd.DataFrame(columns=CORRELATION_COLUMNS)
    graph: dict[str, set[str]] = {}
    for row in strong.itertuples(index=False):
        graph.setdefault(row.feature_a, set()).add(row.feature_b)
        graph.setdefault(row.feature_b, set()).add(row.feature_a)
    groups: list[set[str]] = []
    visited: set[str] = set()
    for node in graph:
        if node in visited:
            continue
        stack = [node]
        component: set[str] = set()
        while stack:
            current = stack.pop()
            if current in visited:
                continue
            visited.add(current)
            component.add(current)
            stack.extend(graph.get(current, set()) - visited)
        groups.append(component)
    signal_map = feature_summary.set_index("feature_name")["signal_type"].to_dict() if not feature_summary.empty else {}
    score_map = feature_summary.set_index("feature_name")["sample_count"].to_dict() if not feature_summary.empty else {}
    rank = {"useful_signal": 4, "risk_signal": 3, "inverted_signal": 2, "weak_signal": 1, "redundant_signal": 0}
    keep_map: dict[str, tuple[str, str]] = {}
    for idx, component in enumerate(groups, start=1):
        ordered = sorted(
            component,
            key=lambda name: (
                -rank.get(signal_map.get(name, "weak_signal"), 1),
                -int(score_map.get(name, 0) or 0),
                name,
            ),
        )
        keep = ordered[0]
        for name in component:
            keep_map[name] = (f"group_{idx:02d}", keep)
    rows = []
    for row in strong.itertuples(index=False):
        group_id, keep = keep_map.get(row.feature_a, ("", row.feature_a))
        rows.append(
            {
                "feature_a": row.feature_a,
                "feature_b": row.feature_b,
                "correlation": row.correlation,
                "redundancy_group": group_id,
                "recommended_keep": keep,
                "reason": f"abs(corr)>={0.85}; keep representative feature {keep}",
            }
        )
    return pd.DataFrame(rows).reindex(columns=CORRELATION_COLUMNS)


def build_recommendation(
    feature_summary: pd.DataFrame,
    combo_effectiveness: pd.DataFrame,
    redundancy: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    redundant_features = set()
    keep_map = {}
    if not redundancy.empty:
        redundant_features = set(redundancy["feature_a"]).union(set(redundancy["feature_b"]))
        keep_map = {row.feature_a: row.recommended_keep for row in redundancy.itertuples(index=False)}
        keep_map.update({row.feature_b: row.recommended_keep for row in redundancy.itertuples(index=False)})
    for row in feature_summary.itertuples(index=False):
        signal_type = row.signal_type
        if row.feature_name in redundant_features and keep_map.get(row.feature_name) != row.feature_name:
            signal_type = "redundant_signal"
        rows.append(
            {
                "feature_or_method": row.feature_name,
                "category": "technical_feature",
                "signal_type": signal_type,
                "recommended_usage": _recommended_usage(row.feature_name, signal_type),
                "evidence_summary": f"sample={int(row.sample_count)} null_rate={row.feature_null_rate:.2%}",
                "sample_count": int(row.sample_count),
                "confidence_level": _confidence_level(int(row.sample_count)),
                "next_action": _next_action(signal_type),
            }
        )
    for row in combo_effectiveness.itertuples(index=False):
        rows.append(
            {
                "feature_or_method": row.combo_name,
                "category": "technical_combo",
                "signal_type": row.signal_type,
                "recommended_usage": _recommended_usage(row.combo_name, row.signal_type),
                "evidence_summary": row.interpretation,
                "sample_count": int(row.sample_count),
                "confidence_level": _confidence_level(int(row.sample_count)),
                "next_action": _next_action(row.signal_type),
            }
        )
    return pd.DataFrame(rows).reindex(columns=RECOMMENDATION_COLUMNS)


def build_validation_report(
    *,
    dataset: pd.DataFrame,
    feature_source: str,
    adjust_type: str,
    start_date: str,
    end_date: str,
    feature_bucket: pd.DataFrame,
    combo_effectiveness: pd.DataFrame,
    regime_effectiveness: pd.DataFrame,
    case_effectiveness: pd.DataFrame,
    lhb_cross: pd.DataFrame,
    redundancy: pd.DataFrame,
    recommendation: pd.DataFrame,
    warnings: list[str],
) -> str:
    signal_counts = recommendation["signal_type"].value_counts().to_dict() if not recommendation.empty else {}
    useful = recommendation[recommendation["signal_type"] == "useful_signal"].head(12)
    risk = recommendation[recommendation["signal_type"] == "risk_signal"].head(12)
    inverted = recommendation[recommendation["signal_type"] == "inverted_signal"].head(12)
    weak = recommendation[recommendation["signal_type"].isin(["weak_signal", "redundant_signal"])].head(12)
    return "\n".join(
        [
            "# Technical Method Validation v1 Report",
            "",
            "## 1. Research Goal",
            "This run validates whether common technical indicators and technical methods have statistical value. It does not connect to live trading, does not generate trade signals, and does not enter strategy scoring.",
            "",
            "## 2. Data Scope",
            f"start_date={start_date}, end_date={end_date}, adjust_type={adjust_type}, feature_source={feature_source}, sample_rows={len(dataset)}.",
            "",
            "## 3. Single Feature Buckets",
            f"signal_counts={signal_counts}",
            _table_preview(feature_bucket, rows=20),
            "",
            "## 4. Technical Combos",
            _table_preview(combo_effectiveness, rows=20),
            "",
            "## 5. Regime Split",
            _table_preview(regime_effectiveness, rows=20),
            "",
            "## 6. Case Event Validation",
            _table_preview(case_effectiveness, rows=20),
            "",
            "## 7. LHB Cross",
            _table_preview(lhb_cross, rows=12),
            "",
            "## 8. Redundancy",
            _table_preview(redundancy, rows=20),
            "",
            "## 9. Conclusion",
            "Keep useful_signal and risk_signal candidates for future watchlist diagnostics; keep weak or redundant signals out of any scoring layer for now.",
            "",
            "## 10. Recommendation",
            _table_preview(recommendation, rows=20),
            "",
            "### Useful",
            _table_preview(useful, rows=12),
            "",
            "### Risk",
            _table_preview(risk, rows=12),
            "",
            "### Inverted",
            _table_preview(inverted, rows=12),
            "",
            "### Weak",
            _table_preview(weak, rows=12),
            "",
            "### Warnings",
            *(warnings or ["none"]),
        ]
    )


def _derive_extended_features(frame: pd.DataFrame) -> pd.DataFrame:
    close = pd.to_numeric(frame["close"], errors="coerce")
    high = pd.to_numeric(frame["high"], errors="coerce")
    low = pd.to_numeric(frame["low"], errors="coerce")
    preclose = pd.to_numeric(frame["preclose"], errors="coerce").replace(0.0, np.nan)
    amount = pd.to_numeric(frame["amount"], errors="coerce")
    volume = pd.to_numeric(frame["volume"], errors="coerce")
    turnover = pd.to_numeric(frame["turnover_rate"], errors="coerce")

    for window in (5, 10, 20, 60):
        ma = pd.to_numeric(frame.get(f"ma{window}"), errors="coerce")
        frame[f"close_vs_ma{window}"] = close / ma - 1.0
        frame[f"ma{window}_slope"] = ma.pct_change()
    frame["ma_bullish_alignment"] = ((pd.to_numeric(frame["ma5"], errors="coerce") > pd.to_numeric(frame["ma10"], errors="coerce")) & (pd.to_numeric(frame["ma10"], errors="coerce") > pd.to_numeric(frame["ma20"], errors="coerce"))).astype(float)

    dif = pd.to_numeric(frame["macd_dif"], errors="coerce")
    dea = pd.to_numeric(frame["macd_dea"], errors="coerce")
    hist = pd.to_numeric(frame["macd_hist"], errors="coerce")
    frame["macd_above_zero"] = ((dif > 0) & (dea > 0)).astype(float)
    frame["macd_hist_rising"] = (hist > hist.shift(1)).astype(float)
    frame["macd_cross_up"] = ((dif > dea) & (dif.shift(1) <= dea.shift(1))).astype(float)
    frame["macd_cross_down"] = ((dif < dea) & (dif.shift(1) >= dea.shift(1))).astype(float)

    frame["rsi_overbought"] = ((pd.to_numeric(frame["rsi6"], errors="coerce") >= 80) | (pd.to_numeric(frame["rsi12"], errors="coerce") >= 80)).astype(float)
    frame["rsi_oversold"] = ((pd.to_numeric(frame["rsi6"], errors="coerce") <= 20) | (pd.to_numeric(frame["rsi12"], errors="coerce") <= 20)).astype(float)

    upper = pd.to_numeric(frame["boll_upper_20"], errors="coerce")
    mid = pd.to_numeric(frame["boll_mid_20"], errors="coerce")
    lower = pd.to_numeric(frame["boll_lower_20"], errors="coerce")
    width = (upper - lower) / mid.replace(0.0, np.nan)
    frame["boll_position_20"] = (close - lower) / (upper - lower).replace(0.0, np.nan)
    frame["boll_width_20"] = width
    frame["boll_break_upper"] = (close > upper).astype(float)
    frame["boll_break_lower"] = (close < lower).astype(float)
    frame["boll_squeeze"] = (width <= width.rolling(20, min_periods=5).median() * 0.8).astype(float)

    k = pd.to_numeric(frame["kdj_k"], errors="coerce")
    d = pd.to_numeric(frame["kdj_d"], errors="coerce")
    j = pd.to_numeric(frame["kdj_j"], errors="coerce")
    frame["kdj_overbought"] = ((k >= 80) | (j >= 100)).astype(float)
    frame["kdj_oversold"] = ((k <= 20) | (j <= 0)).astype(float)
    frame["kdj_cross_up"] = ((k > d) & (k.shift(1) <= d.shift(1))).astype(float)

    frame["amount_vs_5d"] = amount / amount.rolling(5).mean()
    frame["amount_vs_20d"] = amount / amount.rolling(20).mean()
    frame["volume_vs_5d"] = volume / volume.rolling(5).mean()
    frame["volume_vs_20d"] = volume / volume.rolling(20).mean()
    frame["turnover_vs_20d"] = turnover / turnover.rolling(20).mean()

    atr = pd.to_numeric(frame["atr14"], errors="coerce")
    frame["atr_pct14"] = atr / close.replace(0.0, np.nan)
    ret_1d = close / close.shift(1) - 1.0
    frame["volatility_5d"] = ret_1d.rolling(5).std()
    frame["volatility_20d"] = ret_1d.rolling(20).std()
    frame["max_drawdown_5d"] = close.rolling(5).apply(_window_drawdown, raw=True)
    frame["max_drawdown_10d"] = close.rolling(10).apply(_window_drawdown, raw=True)
    frame["max_drawdown_20d"] = close.rolling(20).apply(_window_drawdown, raw=True)
    frame["high_to_close_drawdown"] = (high - close) / high.replace(0.0, np.nan)
    if "close_position_in_day" not in frame.columns:
        frame["close_position_in_day"] = (close - low) / (high - low).replace(0.0, np.nan)
    frame["amplitude"] = (high - low) / preclose

    plus_di, minus_di = _plus_minus_di(high, low, close, 14)
    frame["plus_di14"] = plus_di
    frame["minus_di14"] = minus_di
    frame["mfi14"] = _mfi(high, low, close, volume, 14)
    return frame


def _append_future_metrics(frame: pd.DataFrame) -> pd.DataFrame:
    close = pd.to_numeric(frame["close"], errors="coerce")
    for horizon in (1, 3, 5, 10, 20):
        frame[f"future_{horizon}d_return"] = close.shift(-horizon) / close - 1.0
    for horizon in (3, 5, 10):
        frame[f"future_{horizon}d_max_drawdown"] = _forward_drawdown(close, horizon)
    return frame


def _plus_minus_di(high: pd.Series, low: pd.Series, close: pd.Series, window: int) -> tuple[pd.Series, pd.Series]:
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = pd.Series(np.where((up_move > down_move) & (up_move > 0.0), up_move, 0.0), index=high.index, dtype="float64")
    minus_dm = pd.Series(np.where((down_move > up_move) & (down_move > 0.0), down_move, 0.0), index=high.index, dtype="float64")
    atr = _atr(high, low, close.shift(1), window)
    plus_smoothed = _wilder_average(plus_dm, window)
    minus_smoothed = _wilder_average(minus_dm, window)
    plus_di = 100.0 * plus_smoothed / atr.replace(0.0, np.nan)
    minus_di = 100.0 * minus_smoothed / atr.replace(0.0, np.nan)
    return plus_di, minus_di


def _mfi(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series, window: int) -> pd.Series:
    typical = (high + low + close) / 3.0
    money_flow = typical * volume.fillna(0.0)
    direction = typical.diff()
    positive = pd.Series(np.where(direction > 0, money_flow, 0.0), index=typical.index)
    negative = pd.Series(np.where(direction < 0, money_flow, 0.0), index=typical.index)
    pos_sum = positive.rolling(window).sum()
    neg_sum = negative.rolling(window).sum().replace(0.0, np.nan)
    ratio = pos_sum / neg_sum
    return 100.0 - 100.0 / (1.0 + ratio)


def _window_drawdown(values: np.ndarray) -> float:
    arr = np.asarray(values, dtype=float)
    if len(arr) == 0 or np.isnan(arr).any():
        return np.nan
    running_max = np.maximum.accumulate(arr)
    drawdowns = arr / running_max - 1.0
    return float(drawdowns.min())


def _forward_drawdown(close: pd.Series, horizon: int) -> pd.Series:
    values = close.to_numpy(dtype=float)
    result = np.full(len(values), np.nan)
    for idx in range(len(values)):
        if idx + horizon >= len(values):
            continue
        window = values[idx + 1 : idx + horizon + 1]
        if len(window) == 0 or np.isnan(window).all() or np.isnan(values[idx]) or values[idx] == 0:
            continue
        drawdowns = window / values[idx] - 1.0
        result[idx] = np.nanmin(drawdowns)
    return pd.Series(result, index=close.index, dtype="float64")


def _combo_definitions(dataset: pd.DataFrame) -> list[tuple[str, str, pd.Series]]:
    close_vs_ma20 = pd.to_numeric(dataset.get("close_vs_ma20"), errors="coerce")
    ma20_slope = pd.to_numeric(dataset.get("ma20_slope"), errors="coerce")
    close_vs_ma5 = pd.to_numeric(dataset.get("close_vs_ma5"), errors="coerce")
    close_vs_ma10 = pd.to_numeric(dataset.get("close_vs_ma10"), errors="coerce")
    boll_pos = pd.to_numeric(dataset.get("boll_position_20"), errors="coerce")
    amount_vs_20d = pd.to_numeric(dataset.get("amount_vs_20d"), errors="coerce")
    rsi6 = pd.to_numeric(dataset.get("rsi6"), errors="coerce")
    rsi12 = pd.to_numeric(dataset.get("rsi12"), errors="coerce")
    high_to_close = pd.to_numeric(dataset.get("high_to_close_drawdown"), errors="coerce")
    close_pos = pd.to_numeric(dataset.get("close_position_in_day"), errors="coerce")
    ret_20d = pd.to_numeric(dataset.get("ret_20d"), errors="coerce")

    return [
        ("ma_bullish_stack", "close > ma5 > ma10 > ma20", pd.to_numeric(dataset.get("ma_bullish_alignment"), errors="coerce") > 0),
        ("close_above_ma20_and_ma20_up", "close > ma20 and ma20_slope > 0", (close_vs_ma20 > 0) & (ma20_slope > 0)),
        ("reclaim_ma20_after_pullback", "close reclaims ma20 after prior pullback", (close_vs_ma20 > 0) & (close_vs_ma20.shift(1) <= 0)),
        ("macd_cross_up", "macd_cross_up", pd.to_numeric(dataset.get("macd_cross_up"), errors="coerce") > 0),
        ("macd_above_zero", "macd_above_zero", pd.to_numeric(dataset.get("macd_above_zero"), errors="coerce") > 0),
        ("macd_hist_rising", "macd_hist_rising", pd.to_numeric(dataset.get("macd_hist_rising"), errors="coerce") > 0),
        ("macd_cross_up_above_zero", "macd_cross_up + macd_above_zero", (pd.to_numeric(dataset.get("macd_cross_up"), errors="coerce") > 0) & (pd.to_numeric(dataset.get("macd_above_zero"), errors="coerce") > 0)),
        ("rsi6_above_80", "rsi6 > 80", rsi6 > 80),
        ("rsi6_above_90", "rsi6 > 90", rsi6 > 90),
        ("rsi12_above_80", "rsi12 > 80", rsi12 > 80),
        ("rsi6_extreme_with_extreme_amount", "rsi6 > 90 and amount_vs_20d > 5", (rsi6 > 90) & (amount_vs_20d > 5)),
        ("rsi_falling_from_high", "rsi6 falls from high", (rsi6.shift(1) > 80) & (rsi6 < rsi6.shift(1))),
        ("close_breaks_boll_upper", "close > boll_upper", pd.to_numeric(dataset.get("boll_break_upper"), errors="coerce") > 0),
        ("boll_squeeze_breakout_up", "boll_squeeze then upward breakout", (pd.to_numeric(dataset.get("boll_squeeze"), errors="coerce") > 0) & (pd.to_numeric(dataset.get("boll_break_upper"), errors="coerce") > 0)),
        ("boll_break_upper_moderate_amount", "close > boll_upper and amount_vs_20d between 1.2 and 3", (pd.to_numeric(dataset.get("boll_break_upper"), errors="coerce") > 0) & amount_vs_20d.between(1.2, 3.0)),
        ("boll_break_upper_extreme_rsi", "close > boll_upper and rsi6 > 80", (pd.to_numeric(dataset.get("boll_break_upper"), errors="coerce") > 0) & (rsi6 > 80)),
        ("amount_vs_20d_above_2", "amount_vs_20d > 2", amount_vs_20d > 2),
        ("amount_vs_20d_above_5", "amount_vs_20d > 5", amount_vs_20d > 5),
        ("amount_vs_20d_moderate", "amount_vs_20d between 1.2 and 3", amount_vs_20d.between(1.2, 3.0)),
        ("extreme_amount_weak_close", "extreme amount and low close position", (amount_vs_20d > 5) & (close_pos < 0.3)),
        ("high_intraday_fade", "high_to_close_drawdown large", high_to_close > 0.06),
        ("low_close_position", "close_position_in_day low", close_pos < 0.3),
        ("high_fade_with_high_amount", "high_to_close_drawdown large and amount_vs_20d high", (high_to_close > 0.06) & (amount_vs_20d > 2)),
        ("high_trailing_drawdown_5d", "max_drawdown_5d high", pd.to_numeric(dataset.get("max_drawdown_5d"), errors="coerce") < -0.08),
        ("high_atr_pct14", "atr_pct14 high", pd.to_numeric(dataset.get("atr_pct14"), errors="coerce") > pd.to_numeric(dataset.get("atr_pct14"), errors="coerce").quantile(0.8)),
        ("second_wave_supportive_setup", "prior trend, reclaim ma5/ma10, boll repaired, moderate amount, not overheated, no large fade", (ret_20d > 0.15) & (close_vs_ma5 > 0) & (close_vs_ma10 > 0) & boll_pos.between(0.45, 0.9) & amount_vs_20d.between(1.2, 3.0) & (rsi6 < 80) & (high_to_close < 0.05)),
    ]


def _assign_buckets(series: pd.Series) -> pd.Series:
    clean = pd.to_numeric(series, errors="coerce")
    if clean.dropna().nunique() <= 2:
        return clean.fillna(-1).astype(int)
    ranks = clean.rank(method="first")
    return pd.qcut(ranks, q=min(10, clean.notna().sum()), labels=False, duplicates="drop") + 1


def _classify_feature_signal(bucket_frame: pd.DataFrame) -> str:
    frame = bucket_frame.sort_values("bucket")
    if frame.empty or len(frame) < 2:
        return "weak_signal"
    top = frame.iloc[-1]
    bottom = frame.iloc[0]
    spread = _f(top["avg_future_10d_return"]) - _f(bottom["avg_future_10d_return"])
    win_spread = _f(top["win_rate_10d"]) - _f(bottom["win_rate_10d"])
    dd_diff = _f(top["avg_future_10d_max_drawdown"]) - _f(bottom["avg_future_10d_max_drawdown"])
    if (dd_diff < -0.03 or win_spread < -0.08) and spread <= 0.01:
        return "risk_signal"
    if spread >= 0.01 and dd_diff >= -0.03:
        return "useful_signal"
    if spread <= -0.01 and dd_diff <= 0.02:
        return "inverted_signal"
    return "weak_signal"


def _classify_group_signal(group: pd.DataFrame, baseline: dict[str, float]) -> str:
    future_10d = pd.to_numeric(group["future_10d_return"], errors="coerce").mean()
    drawdown = pd.to_numeric(group["future_10d_max_drawdown"], errors="coerce").mean()
    win_rate = _win_rate(group["future_10d_return"])
    if drawdown < baseline["drawdown_10d"] - 0.03 and future_10d <= baseline["future_10d"] + 0.005:
        return "risk_signal"
    if future_10d > baseline["future_10d"] + 0.01 and drawdown >= baseline["drawdown_10d"] - 0.02 and win_rate >= baseline["win_rate_10d"]:
        return "useful_signal"
    if future_10d < baseline["future_10d"] - 0.01 and drawdown <= baseline["drawdown_10d"] + 0.02:
        return "inverted_signal"
    return "weak_signal"


def _baseline_stats(dataset: pd.DataFrame) -> dict[str, float]:
    return {
        "future_10d": float(pd.to_numeric(dataset["future_10d_return"], errors="coerce").mean()),
        "drawdown_10d": float(pd.to_numeric(dataset["future_10d_max_drawdown"], errors="coerce").mean()),
        "win_rate_10d": float(_win_rate(dataset["future_10d_return"]) or 0.0),
    }


def _apply_redundant_signal_override(feature_bucket: pd.DataFrame, redundancy: pd.DataFrame) -> pd.DataFrame:
    if feature_bucket.empty or redundancy.empty:
        return feature_bucket
    keep_map = {}
    for row in redundancy.itertuples(index=False):
        keep_map[row.feature_a] = row.recommended_keep
        keep_map[row.feature_b] = row.recommended_keep
    frame = feature_bucket.copy()
    mask = frame["feature_name"].map(lambda name: keep_map.get(name, name) != name)
    frame.loc[mask, "signal_type"] = "redundant_signal"
    return frame


def _apply_redundant_signal_override_summary(summary: pd.DataFrame, redundancy: pd.DataFrame) -> pd.DataFrame:
    if summary.empty or redundancy.empty:
        return summary
    keep_map = {}
    for row in redundancy.itertuples(index=False):
        keep_map[row.feature_a] = row.recommended_keep
        keep_map[row.feature_b] = row.recommended_keep
    frame = summary.copy()
    mask = frame["feature_name"].map(lambda name: keep_map.get(name, name) != name)
    frame.loc[mask, "signal_type"] = "redundant_signal"
    return frame


def _combo_interpretation(combo_name: str, signal_type: str) -> str:
    return f"{combo_name} behaves as {signal_type} in this sample."


def _lhb_combo_interpretation(combo_name: str) -> str:
    return f"{combo_name} cross-checks LHB behavior against technical state."


def _recommended_usage(name: str, signal_type: str) -> str:
    lower = name.lower()
    if signal_type == "redundant_signal":
        return "discard"
    if signal_type == "risk_signal":
        return "risk_filter"
    if signal_type == "useful_signal":
        if any(token in lower for token in ["regime", "mainline"]):
            return "regime_filter"
        if any(token in lower for token in ["drawdown", "atr", "volatility", "overbought", "fade"]):
            return "risk_filter"
        return "entry_confirmation"
    if signal_type == "inverted_signal":
        return "case_diagnostic"
    return "discard"


def _next_action(signal_type: str) -> str:
    mapping = {
        "useful_signal": "keep_for_watchlist_validation",
        "risk_signal": "keep_for_risk_filter_validation",
        "inverted_signal": "keep_for_case_diagnostic_only",
        "weak_signal": "deprioritize",
        "redundant_signal": "drop_duplicate",
    }
    return mapping.get(signal_type, "deprioritize")


def _confidence_level(sample_count: int) -> str:
    if sample_count >= 5000:
        return "high"
    if sample_count >= 1000:
        return "medium"
    return "low"


def _ensure_market_regime(dataset: pd.DataFrame, regime_frame: pd.DataFrame | None, warnings: list[str]) -> pd.DataFrame:
    if regime_frame is not None and not regime_frame.empty:
        frame = regime_frame.copy()
        date_col = "trade_date" if "trade_date" in frame.columns else "rebalance_date" if "rebalance_date" in frame.columns else None
        if date_col and "market_regime" in frame.columns:
            frame["trade_date"] = pd.to_datetime(frame[date_col], errors="coerce").dt.strftime("%Y-%m-%d")
            frame["market_regime"] = frame["market_regime"].fillna("unknown").astype(str)
            return frame[["trade_date", "market_regime"]].drop_duplicates(subset=["trade_date"])
    warnings.append("market_regime_diagnostics.csv was not available; used fallback regime classification")
    summary = dataset.groupby("trade_date").agg(
        breadth=("pct_chg", lambda s: pd.to_numeric(s, errors="coerce").gt(0).mean()),
        strong_share=("pct_chg", lambda s: pd.to_numeric(s, errors="coerce").gt(0.02).mean()),
        weak_share=("pct_chg", lambda s: pd.to_numeric(s, errors="coerce").lt(-0.02).mean()),
        total_amount=("amount", lambda s: pd.to_numeric(s, errors="coerce").sum()),
    ).reset_index()
    summary["amount_vs_20d"] = summary["total_amount"] / summary["total_amount"].rolling(20).mean()
    regimes = []
    for row in summary.itertuples(index=False):
        regime = "unknown"
        if row.breadth >= 0.60 and row.strong_share >= 0.18 and _f(row.amount_vs_20d) >= 1.02:
            regime = "mainline"
        elif row.breadth >= 0.48 and row.strong_share >= 0.10:
            regime = "rotation"
        elif row.breadth <= 0.35 and row.weak_share >= 0.15:
            regime = "retreat"
        elif row.breadth >= 0.55:
            regime = "broad_market"
        elif row.breadth < 0.45:
            regime = "weak"
        regimes.append({"trade_date": row.trade_date, "market_regime": regime})
    return pd.DataFrame(regimes)


def _resolve_optional_inputs(output_dir: str | Path) -> ValidationInputPaths:
    out = Path(output_dir)
    case_view = out / "dragon_case_curated_library_failure_v2_1.csv"
    if not case_view.exists():
        case_view = out / "dragon_case_curated_library_2024_2026.csv"
    lhb_detail = out / "lhb_risk_feature_case_detail_v2_1.csv"
    if not lhb_detail.exists():
        lhb_detail = out / "lhb_risk_feature_case_detail.csv"
    market_regime = out / "market_regime_diagnostics.csv"
    return ValidationInputPaths(
        case_view=case_view if case_view.exists() else None,
        case_snapshot=(out / "dragon_case_factor_snapshot_2024_2026.csv") if (out / "dragon_case_factor_snapshot_2024_2026.csv").exists() else None,
        lhb_case_detail=lhb_detail if lhb_detail.exists() else None,
        market_regime=market_regime if market_regime.exists() else None,
        industry_focus=(out / "industry_focus_score_v2_diagnostics.csv") if (out / "industry_focus_score_v2_diagnostics.csv").exists() else None,
        industry_mainline=(out / "industry_mainline_regime_diagnostics.csv") if (out / "industry_mainline_regime_diagnostics.csv").exists() else None,
    )


def _load_optional_csv(path: Path | None, warnings: list[str], label: str) -> pd.DataFrame:
    if path is None or not path.exists():
        warnings.append(f"{label} input was not available")
        return pd.DataFrame()
    return pd.read_csv(path, low_memory=False)


def _asset_id_to_ts_code(asset_id: str) -> str:
    text = str(asset_id or "")
    parts = text.split(":")
    if len(parts) == 3:
        return f"{parts[2]}.{parts[1]}"
    return text


def _ts_code_to_asset_id(ts_code: str) -> str:
    text = str(ts_code or "").upper()
    if "." not in text:
        return text
    code, exchange = text.split(".", 1)
    return f"CN:{exchange}:{code}"


def _date_or_empty(value: Any) -> str:
    if value is None or value == "":
        return ""
    return pd.to_datetime(value, errors="coerce").strftime("%Y-%m-%d")


def _table_preview(frame: pd.DataFrame, rows: int = 12) -> str:
    if frame is None or frame.empty:
        return "no available sample."
    return frame.head(rows).to_markdown(index=False)


def _win_rate(series: pd.Series) -> float | None:
    values = pd.to_numeric(series, errors="coerce")
    if not values.notna().any():
        return None
    return float((values > 0).mean())


def _f(value: Any) -> float:
    if value is None or pd.isna(value):
        return 0.0
    return float(value)
