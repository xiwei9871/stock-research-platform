from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from stock_research.config import SETTINGS
from stock_research.technical_method_validation import load_validation_bars


ALPHA191_PILOT_FACTORS = [
    "alpha191_ret_3_rank",
    "alpha191_ret_5_rank",
    "alpha191_ret_10_rank",
    "alpha191_ret_20_rank",
    "alpha191_amount_momentum_5_20",
    "alpha191_turnover_shock_5_20",
    "alpha191_volume_shock_5_20",
    "alpha191_amount_acceleration_5",
    "alpha191_price_volume_corr_10",
    "alpha191_price_amount_corr_10",
    "alpha191_volume_price_divergence_10",
    "alpha191_close_position",
    "alpha191_intraday_strength_6",
    "alpha191_high_to_close_fade",
    "alpha191_low_to_close_rebound",
    "alpha191_volatility_5",
    "alpha191_volatility_20",
    "alpha191_range_volatility_10",
    "alpha191_breakout_20",
    "alpha191_pullback_from_20_high",
    "alpha191_trend_quality_20",
    "alpha191_momentum_10",
    "alpha191_reversal_3",
]

ALPHA191_EXPANDED_FACTORS = ALPHA191_PILOT_FACTORS + [
    "alpha191_gap_open",
    "alpha191_abs_gap_open",
    "alpha191_intraday_return",
    "alpha191_upper_shadow",
    "alpha191_lower_shadow",
    "alpha191_body_pct",
    "alpha191_ret_1",
    "alpha191_momentum_5",
    "alpha191_momentum_20",
    "alpha191_reversal_1",
    "alpha191_reversal_5",
    "alpha191_amount_zscore_20",
    "alpha191_volume_zscore_20",
    "alpha191_turnover_zscore_20",
    "alpha191_amount_ts_rank_20",
    "alpha191_volume_ts_rank_20",
    "alpha191_close_ts_rank_10",
    "alpha191_close_ts_rank_20",
    "alpha191_high_ts_rank_20",
    "alpha191_low_ts_rank_20",
    "alpha191_ma5_bias",
    "alpha191_ma10_bias",
    "alpha191_ma20_bias",
    "alpha191_ma60_bias",
    "alpha191_ma5_slope",
    "alpha191_ma20_slope",
    "alpha191_volatility_ratio_5_20",
    "alpha191_drawdown_5",
    "alpha191_drawdown_10",
    "alpha191_drawdown_20",
    "alpha191_distance_to_high_60",
    "alpha191_distance_to_low_60",
    "alpha191_corr_ret_amount_10",
    "alpha191_corr_ret_volume_10",
    "alpha191_amount_price_divergence_20",
    "alpha191_up_days_5",
    "alpha191_up_days_10",
    "alpha191_down_days_5",
    "alpha191_limit_like_up",
    "alpha191_limit_like_down",
    "alpha191_consecutive_up_3",
    "alpha191_range_expansion_5_20",
    "alpha191_close_strength_with_amount",
    "alpha191_fade_with_amount",
    "alpha191_rebound_with_amount",
    "alpha191_vol_adjusted_momentum_10",
    "alpha191_vol_adjusted_reversal_3",
]

FACTOR_EFFECTIVENESS_COLUMNS = [
    "factor_name",
    "sample_count",
    "rank_ic_1d",
    "rank_ic_3d",
    "rank_ic_5d",
    "rank_ic_10d",
    "top_decile_avg_future_1d_return",
    "top_decile_avg_future_3d_return",
    "top_decile_avg_future_5d_return",
    "top_decile_avg_future_10d_return",
    "bottom_decile_avg_future_5d_return",
    "top_bottom_spread_5d",
    "top_decile_win_rate_5d",
    "top_decile_avg_future_5d_max_drawdown",
    "signal_type",
    "recommended_usage",
]

BUCKET_COLUMNS = [
    "factor_name",
    "bucket",
    "sample_count",
    "avg_future_1d_return",
    "avg_future_3d_return",
    "avg_future_5d_return",
    "avg_future_10d_return",
    "win_rate_5d",
    "avg_future_5d_max_drawdown",
]


def run_validate_alpha191_pilot(
    *,
    start_date: str,
    end_date: str,
    adjust_type: str = "qfq",
    sample_size: int | None = None,
    asset_id: str | None = None,
    ts_code: str | None = None,
    strong_start_date: str = "2025-01-01",
    strong_end_date: str = "2025-05-01",
    output_dir: str | Path,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    bars = load_validation_bars(
        start_date=start_date,
        end_date=end_date,
        adjust_type=adjust_type,
        sample_size=sample_size,
        asset_id=asset_id,
        ts_code=ts_code,
        service=service,
    )
    return build_alpha191_pilot_validation_from_frames(
        bars,
        start_date=start_date,
        end_date=end_date,
        adjust_type=adjust_type,
        strong_start_date=strong_start_date,
        strong_end_date=strong_end_date,
        output_dir=output_dir,
    )


def run_validate_alpha191_expanded(
    *,
    start_date: str,
    end_date: str,
    adjust_type: str = "qfq",
    sample_size: int | None = None,
    asset_id: str | None = None,
    ts_code: str | None = None,
    strong_start_date: str = "2025-01-01",
    strong_end_date: str = "2025-05-01",
    output_dir: str | Path,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    bars = load_validation_bars(
        start_date=start_date,
        end_date=end_date,
        adjust_type=adjust_type,
        sample_size=sample_size,
        asset_id=asset_id,
        ts_code=ts_code,
        service=service,
    )
    return build_alpha191_expanded_validation_from_frames(
        bars,
        start_date=start_date,
        end_date=end_date,
        adjust_type=adjust_type,
        strong_start_date=strong_start_date,
        strong_end_date=strong_end_date,
        output_dir=output_dir,
    )


def build_alpha191_pilot_validation_from_frames(
    bars: pd.DataFrame,
    *,
    start_date: str,
    end_date: str,
    adjust_type: str = "qfq",
    strong_start_date: str = "2025-01-01",
    strong_end_date: str = "2025-05-01",
    output_dir: str | Path,
) -> dict[str, Any]:
    dataset = compute_alpha191_expanded_dataset(bars)
    factors = [factor for factor in ALPHA191_PILOT_FACTORS if factor in dataset.columns]
    factor_effectiveness = build_alpha191_factor_effectiveness(dataset, factors=factors)
    strong_winner = build_strong_winner_explanation(
        dataset,
        strong_start_date=strong_start_date,
        strong_end_date=strong_end_date,
        factors=factors,
    )
    trend_overlay = build_trend_continuation_overlay(dataset)
    high_volatility_risk_split = build_high_volatility_risk_split(dataset)
    recommendation = build_alpha191_pilot_recommendation(factor_effectiveness, strong_winner)
    report = build_alpha191_pilot_report(
        dataset=dataset,
        start_date=start_date,
        end_date=end_date,
        adjust_type=adjust_type,
        factor_effectiveness=factor_effectiveness,
        strong_winner=strong_winner,
        trend_overlay=trend_overlay,
        high_volatility_risk_split=high_volatility_risk_split,
        recommendation=recommendation,
    )
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    paths = {
        "factor_effectiveness": output / "alpha191_pilot_factor_effectiveness.csv",
        "strong_winner_explanation": output / "alpha191_pilot_strong_winner_explanation.csv",
        "trend_overlay": output / "alpha191_pilot_trend_continuation_overlay.csv",
        "high_volatility_risk_split": output / "alpha191_pilot_high_volatility_risk_split.csv",
        "recommendation": output / "alpha191_pilot_recommendation.csv",
        "report": output / "alpha191_pilot_validation_report.md",
    }
    factor_effectiveness.to_csv(paths["factor_effectiveness"], index=False)
    strong_winner.to_csv(paths["strong_winner_explanation"], index=False)
    trend_overlay.to_csv(paths["trend_overlay"], index=False)
    high_volatility_risk_split.to_csv(paths["high_volatility_risk_split"], index=False)
    recommendation.to_csv(paths["recommendation"], index=False)
    Path(paths["report"]).write_text(report, encoding="utf-8")
    return {
        "dataset": dataset,
        "factor_effectiveness": factor_effectiveness,
        "strong_winner_explanation": strong_winner,
        "trend_overlay": trend_overlay,
        "high_volatility_risk_split": high_volatility_risk_split,
        "recommendation": recommendation,
        "paths": paths,
    }


def build_alpha191_expanded_validation_from_frames(
    bars: pd.DataFrame,
    *,
    start_date: str,
    end_date: str,
    adjust_type: str = "qfq",
    strong_start_date: str = "2025-01-01",
    strong_end_date: str = "2025-05-01",
    output_dir: str | Path,
) -> dict[str, Any]:
    dataset = compute_alpha191_expanded_dataset(bars)
    factors = [factor for factor in ALPHA191_EXPANDED_FACTORS if factor in dataset.columns]
    factor_effectiveness = build_alpha191_factor_effectiveness(dataset, factors=factors)
    factor_bucket = build_alpha191_factor_bucket_effectiveness(dataset, factors=factors)
    strong_winner = build_strong_winner_explanation(
        dataset,
        strong_start_date=strong_start_date,
        strong_end_date=strong_end_date,
        factors=factors,
    )
    drawdown_risk = build_drawdown_risk_effectiveness(dataset, factors=factors)
    redundancy = build_alpha191_redundancy_report(dataset, factors=factors)
    candidate_factors = build_alpha191_candidate_factors(
        factor_effectiveness=factor_effectiveness,
        strong_winner=strong_winner,
        redundancy=redundancy,
    )
    trend_overlay = build_trend_continuation_overlay(dataset)
    high_volatility_risk_split = build_high_volatility_risk_split(dataset)
    report = build_alpha191_expanded_report(
        dataset=dataset,
        start_date=start_date,
        end_date=end_date,
        adjust_type=adjust_type,
        factor_effectiveness=factor_effectiveness,
        factor_bucket=factor_bucket,
        strong_winner=strong_winner,
        drawdown_risk=drawdown_risk,
        redundancy=redundancy,
        candidate_factors=candidate_factors,
        trend_overlay=trend_overlay,
        high_volatility_risk_split=high_volatility_risk_split,
    )
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    paths = {
        "factor_effectiveness": output / "alpha191_expanded_factor_effectiveness_v2.csv",
        "factor_bucket_effectiveness": output / "alpha191_expanded_factor_bucket_effectiveness_v2.csv",
        "strong_winner_explanation": output / "alpha191_expanded_strong_winner_explanation_v2.csv",
        "drawdown_risk_effectiveness": output / "alpha191_expanded_drawdown_risk_effectiveness_v2.csv",
        "redundancy_report": output / "alpha191_expanded_redundancy_report_v2.csv",
        "candidate_factors": output / "alpha191_expanded_candidate_factors_v2.csv",
        "trend_overlay": output / "alpha191_expanded_trend_continuation_overlay_v2.csv",
        "high_volatility_risk_split": output / "alpha191_expanded_high_volatility_risk_split_v2.csv",
        "report": output / "alpha191_expanded_validation_report_v2.md",
    }
    factor_effectiveness.to_csv(paths["factor_effectiveness"], index=False)
    factor_bucket.to_csv(paths["factor_bucket_effectiveness"], index=False)
    strong_winner.to_csv(paths["strong_winner_explanation"], index=False)
    drawdown_risk.to_csv(paths["drawdown_risk_effectiveness"], index=False)
    redundancy.to_csv(paths["redundancy_report"], index=False)
    candidate_factors.to_csv(paths["candidate_factors"], index=False)
    trend_overlay.to_csv(paths["trend_overlay"], index=False)
    high_volatility_risk_split.to_csv(paths["high_volatility_risk_split"], index=False)
    Path(paths["report"]).write_text(report, encoding="utf-8")
    return {
        "dataset": dataset,
        "factor_effectiveness": factor_effectiveness,
        "factor_bucket_effectiveness": factor_bucket,
        "strong_winner_explanation": strong_winner,
        "drawdown_risk_effectiveness": drawdown_risk,
        "redundancy_report": redundancy,
        "candidate_factors": candidate_factors,
        "trend_overlay": trend_overlay,
        "high_volatility_risk_split": high_volatility_risk_split,
        "paths": paths,
    }


def compute_alpha191_expanded_dataset(bars: pd.DataFrame) -> pd.DataFrame:
    if bars.empty:
        return pd.DataFrame()
    pieces = []
    for _, group in bars.sort_values(["asset_id", "trade_date"]).groupby("asset_id", sort=False):
        ordered = group.sort_values("trade_date").reset_index(drop=True).copy()
        factors = compute_alpha191_expanded_factors(ordered)
        future = _append_future_metrics(factors)
        pieces.append(future)
    return pd.concat(pieces, ignore_index=True) if pieces else pd.DataFrame()


def compute_alpha191_expanded_factors(bars: pd.DataFrame) -> pd.DataFrame:
    frame = bars.sort_values(["asset_id", "trade_date"] if "asset_id" in bars.columns else ["trade_date"]).copy()
    open_ = _num(frame.get("open"))
    high = _num(frame.get("high"))
    low = _num(frame.get("low"))
    close = _num(frame.get("close"))
    preclose = _num(frame.get("preclose")).replace(0.0, np.nan)
    volume = _num(frame.get("volume"))
    amount = _num(frame.get("amount"))
    turnover = _num(frame.get("turnover_rate"))
    true_range = pd.concat(
        [(high - low).abs(), (high - close.shift(1)).abs(), (low - close.shift(1)).abs()],
        axis=1,
    ).max(axis=1)
    ret_1 = close / preclose - 1.0
    ret_3 = close / close.shift(3) - 1.0
    ret_5 = close / close.shift(5) - 1.0
    ret_10 = close / close.shift(10) - 1.0
    ret_20 = close / close.shift(20) - 1.0
    close_position = _safe_divide(close - low, high - low)
    high_to_close_fade = _safe_divide(high - close, close.shift(1))
    low_to_close_rebound = _safe_divide(close - low, close.shift(1))
    range_pct = _safe_divide(high - low, close.shift(1))
    amount_5 = amount.rolling(5, min_periods=3).mean()
    amount_10 = amount.rolling(10, min_periods=5).mean()
    amount_20 = amount.rolling(20, min_periods=10).mean()
    volume_5 = volume.rolling(5, min_periods=3).mean()
    volume_10 = volume.rolling(10, min_periods=5).mean()
    volume_20 = volume.rolling(20, min_periods=10).mean()
    turnover_5 = turnover.rolling(5, min_periods=3).mean()
    turnover_20 = turnover.rolling(20, min_periods=10).mean()
    ma5 = close.rolling(5, min_periods=3).mean()
    ma10 = close.rolling(10, min_periods=5).mean()
    ma20 = close.rolling(20, min_periods=10).mean()
    ma60 = close.rolling(60, min_periods=20).mean()
    volatility_5 = ret_1.rolling(5, min_periods=3).std()
    volatility_20 = ret_1.rolling(20, min_periods=10).std()

    frame["alpha191_ret_3_rank"] = _ts_rank(ret_3, 20)
    frame["alpha191_ret_5_rank"] = _ts_rank(ret_5, 20)
    frame["alpha191_ret_10_rank"] = _ts_rank(ret_10, 20)
    frame["alpha191_ret_20_rank"] = _ts_rank(ret_20, 20)
    frame["alpha191_amount_momentum_5_20"] = _safe_divide(amount_5, amount_20)
    frame["alpha191_turnover_shock_5_20"] = _safe_divide(turnover_5, turnover_20)
    frame["alpha191_volume_shock_5_20"] = _safe_divide(volume_5, volume_20)
    frame["alpha191_amount_acceleration_5"] = _safe_divide(amount_5, amount_5.shift(5))
    frame["alpha191_price_volume_corr_10"] = ret_1.rolling(10, min_periods=5).corr(volume)
    frame["alpha191_price_amount_corr_10"] = ret_1.rolling(10, min_periods=5).corr(amount)
    frame["alpha191_volume_price_divergence_10"] = _zscore(volume, 10) - _zscore(close, 10)
    frame["alpha191_close_position"] = close_position
    frame["alpha191_intraday_strength_6"] = close_position.rolling(6, min_periods=3).mean()
    frame["alpha191_high_to_close_fade"] = high_to_close_fade
    frame["alpha191_low_to_close_rebound"] = low_to_close_rebound
    frame["alpha191_volatility_5"] = volatility_5
    frame["alpha191_volatility_20"] = volatility_20
    frame["alpha191_range_volatility_10"] = range_pct.rolling(10, min_periods=5).mean()
    frame["alpha191_breakout_20"] = close / close.rolling(20, min_periods=10).max() - 1.0
    frame["alpha191_pullback_from_20_high"] = frame["alpha191_breakout_20"]
    frame["alpha191_trend_quality_20"] = ret_20 / volatility_20.replace(0.0, np.nan)
    frame["alpha191_momentum_10"] = ret_10
    frame["alpha191_reversal_3"] = -ret_3

    frame["alpha191_gap_open"] = open_ / preclose - 1.0
    frame["alpha191_abs_gap_open"] = frame["alpha191_gap_open"].abs()
    frame["alpha191_intraday_return"] = close / open_.replace(0.0, np.nan) - 1.0
    frame["alpha191_upper_shadow"] = _safe_divide(high - np.maximum(open_, close), preclose)
    frame["alpha191_lower_shadow"] = _safe_divide(np.minimum(open_, close) - low, preclose)
    frame["alpha191_body_pct"] = _safe_divide((close - open_).abs(), preclose)
    frame["alpha191_ret_1"] = ret_1
    frame["alpha191_momentum_5"] = ret_5
    frame["alpha191_momentum_20"] = ret_20
    frame["alpha191_reversal_1"] = -ret_1
    frame["alpha191_reversal_5"] = -ret_5
    frame["alpha191_amount_zscore_20"] = _zscore(amount, 20)
    frame["alpha191_volume_zscore_20"] = _zscore(volume, 20)
    frame["alpha191_turnover_zscore_20"] = _zscore(turnover, 20)
    frame["alpha191_amount_ts_rank_20"] = _ts_rank(amount, 20)
    frame["alpha191_volume_ts_rank_20"] = _ts_rank(volume, 20)
    frame["alpha191_close_ts_rank_10"] = _ts_rank(close, 10)
    frame["alpha191_close_ts_rank_20"] = _ts_rank(close, 20)
    frame["alpha191_high_ts_rank_20"] = _ts_rank(high, 20)
    frame["alpha191_low_ts_rank_20"] = _ts_rank(low, 20)
    frame["alpha191_ma5_bias"] = close / ma5 - 1.0
    frame["alpha191_ma10_bias"] = close / ma10 - 1.0
    frame["alpha191_ma20_bias"] = close / ma20 - 1.0
    frame["alpha191_ma60_bias"] = close / ma60 - 1.0
    frame["alpha191_ma5_slope"] = ma5.pct_change()
    frame["alpha191_ma20_slope"] = ma20.pct_change()
    frame["alpha191_volatility_ratio_5_20"] = _safe_divide(volatility_5, volatility_20)
    frame["alpha191_drawdown_5"] = close / close.rolling(5, min_periods=3).max() - 1.0
    frame["alpha191_drawdown_10"] = close / close.rolling(10, min_periods=5).max() - 1.0
    frame["alpha191_drawdown_20"] = frame["alpha191_breakout_20"]
    frame["alpha191_distance_to_high_60"] = close / close.rolling(60, min_periods=20).max() - 1.0
    frame["alpha191_distance_to_low_60"] = close / close.rolling(60, min_periods=20).min() - 1.0
    frame["alpha191_corr_ret_amount_10"] = ret_1.rolling(10, min_periods=5).corr(amount.pct_change())
    frame["alpha191_corr_ret_volume_10"] = ret_1.rolling(10, min_periods=5).corr(volume.pct_change())
    frame["alpha191_amount_price_divergence_20"] = _zscore(amount, 20) - _zscore(close, 20)
    frame["alpha191_up_days_5"] = (ret_1 > 0).astype(float).rolling(5, min_periods=3).sum()
    frame["alpha191_up_days_10"] = (ret_1 > 0).astype(float).rolling(10, min_periods=5).sum()
    frame["alpha191_down_days_5"] = (ret_1 < 0).astype(float).rolling(5, min_periods=3).sum()
    frame["alpha191_limit_like_up"] = (ret_1 >= 0.095).astype(float)
    frame["alpha191_limit_like_down"] = (ret_1 <= -0.095).astype(float)
    frame["alpha191_consecutive_up_3"] = ((ret_1 > 0) & (ret_1.shift(1) > 0) & (ret_1.shift(2) > 0)).astype(float)
    frame["alpha191_range_expansion_5_20"] = _safe_divide(true_range.rolling(5, min_periods=3).mean(), true_range.rolling(20, min_periods=10).mean())
    frame["alpha191_close_strength_with_amount"] = close_position * frame["alpha191_amount_momentum_5_20"]
    frame["alpha191_fade_with_amount"] = high_to_close_fade * frame["alpha191_amount_momentum_5_20"]
    frame["alpha191_rebound_with_amount"] = low_to_close_rebound * frame["alpha191_amount_momentum_5_20"]
    frame["alpha191_vol_adjusted_momentum_10"] = ret_10 / volatility_20.replace(0.0, np.nan)
    frame["alpha191_vol_adjusted_reversal_3"] = -ret_3 / volatility_5.replace(0.0, np.nan)
    return frame


def build_alpha191_factor_effectiveness(
    dataset: pd.DataFrame,
    *,
    factors: list[str] | None = None,
) -> pd.DataFrame:
    factors = factors or ALPHA191_PILOT_FACTORS
    rows = []
    for factor in [item for item in factors if item in dataset.columns]:
        cols = [
            "trade_date",
            factor,
            "future_1d_return",
            "future_3d_return",
            "future_5d_return",
            "future_10d_return",
            "future_5d_max_drawdown",
        ]
        frame = dataset[cols].copy()
        frame[factor] = pd.to_numeric(frame[factor], errors="coerce")
        frame = frame.loc[frame[factor].notna()]
        if frame.empty:
            continue
        frame["bucket"] = _assign_buckets(frame[factor])
        top = frame[frame["bucket"] == 10]
        bottom = frame[frame["bucket"] == 1]
        spread = _mean(top["future_5d_return"]) - _mean(bottom["future_5d_return"])
        drawdown = _mean(top["future_5d_max_drawdown"])
        signal_type, usage = _classify_factor(_mean_rank_ic(frame, factor, "future_5d_return"), spread, drawdown)
        rows.append(
            {
                "factor_name": factor,
                "sample_count": int(frame[factor].notna().sum()),
                "rank_ic_1d": _mean_rank_ic(frame, factor, "future_1d_return"),
                "rank_ic_3d": _mean_rank_ic(frame, factor, "future_3d_return"),
                "rank_ic_5d": _mean_rank_ic(frame, factor, "future_5d_return"),
                "rank_ic_10d": _mean_rank_ic(frame, factor, "future_10d_return"),
                "top_decile_avg_future_1d_return": _mean(top["future_1d_return"]),
                "top_decile_avg_future_3d_return": _mean(top["future_3d_return"]),
                "top_decile_avg_future_5d_return": _mean(top["future_5d_return"]),
                "top_decile_avg_future_10d_return": _mean(top["future_10d_return"]),
                "bottom_decile_avg_future_5d_return": _mean(bottom["future_5d_return"]),
                "top_bottom_spread_5d": spread,
                "top_decile_win_rate_5d": _win_rate(top["future_5d_return"]),
                "top_decile_avg_future_5d_max_drawdown": drawdown,
                "signal_type": signal_type,
                "recommended_usage": usage,
            }
        )
    return pd.DataFrame(rows, columns=FACTOR_EFFECTIVENESS_COLUMNS).sort_values(
        ["signal_type", "rank_ic_5d"], na_position="last"
    ).reset_index(drop=True)


def build_alpha191_factor_bucket_effectiveness(
    dataset: pd.DataFrame,
    *,
    factors: list[str] | None = None,
) -> pd.DataFrame:
    factors = factors or ALPHA191_EXPANDED_FACTORS
    rows = []
    for factor in [item for item in factors if item in dataset.columns]:
        frame = dataset[[factor, "future_1d_return", "future_3d_return", "future_5d_return", "future_10d_return", "future_5d_max_drawdown"]].copy()
        frame[factor] = pd.to_numeric(frame[factor], errors="coerce")
        frame = frame.loc[frame[factor].notna()]
        if frame.empty:
            continue
        frame["bucket"] = _assign_buckets(frame[factor])
        for bucket, group in frame.groupby("bucket", dropna=False):
            rows.append(_bucket_row(factor, bucket, group))
    return pd.DataFrame(rows, columns=BUCKET_COLUMNS)


def build_drawdown_risk_effectiveness(
    dataset: pd.DataFrame,
    *,
    factors: list[str] | None = None,
) -> pd.DataFrame:
    return build_alpha191_factor_bucket_effectiveness(dataset, factors=factors)


def build_strong_winner_explanation(
    dataset: pd.DataFrame,
    *,
    strong_start_date: str,
    strong_end_date: str,
    factors: list[str] | None = None,
) -> pd.DataFrame:
    factors = factors or ALPHA191_PILOT_FACTORS
    if dataset.empty:
        return pd.DataFrame(columns=[
            "factor_name",
            "window_start",
            "window_end",
            "sample_count",
            "strong_winner_count",
            "strong_winner_capture_rate_top_decile",
            "top_decile_strong_winner_rate",
            "baseline_strong_winner_rate",
            "lift_vs_baseline",
        ])
    frame = dataset.loc[(dataset["trade_date"] >= strong_start_date) & (dataset["trade_date"] <= strong_end_date)].copy()
    frame["strong_winner_5d"] = pd.to_numeric(frame["future_5d_return"], errors="coerce") >= 0.10
    baseline = float(frame["strong_winner_5d"].mean()) if len(frame) else np.nan
    total_winners = int(frame["strong_winner_5d"].sum())
    rows = []
    for factor in [item for item in factors if item in frame.columns]:
        valid = frame.loc[pd.to_numeric(frame[factor], errors="coerce").notna()].copy()
        if valid.empty:
            continue
        valid["bucket"] = _assign_buckets(valid[factor])
        top = valid[valid["bucket"] == 10]
        top_winners = int(top["strong_winner_5d"].sum())
        top_rate = float(top["strong_winner_5d"].mean()) if len(top) else np.nan
        rows.append(
            {
                "factor_name": factor,
                "window_start": strong_start_date,
                "window_end": strong_end_date,
                "sample_count": int(len(valid)),
                "strong_winner_count": total_winners,
                "strong_winner_capture_rate_top_decile": top_winners / total_winners if total_winners else np.nan,
                "top_decile_strong_winner_rate": top_rate,
                "baseline_strong_winner_rate": baseline,
                "lift_vs_baseline": top_rate / baseline if baseline and not np.isnan(baseline) else np.nan,
            }
        )
    return pd.DataFrame(rows).sort_values("lift_vs_baseline", ascending=False, na_position="last").reset_index(drop=True)


def build_trend_continuation_overlay(dataset: pd.DataFrame) -> pd.DataFrame:
    required = {"alpha191_reversal_5", "alpha191_volatility_5", "alpha191_fade_with_amount"}
    if dataset.empty or not required.issubset(dataset.columns):
        return pd.DataFrame(columns=["trend_alpha_bucket", *BUCKET_COLUMNS[2:]])
    frame = dataset.copy()
    trend_filter = (
        (pd.to_numeric(frame["alpha191_volatility_5"], errors="coerce") > pd.to_numeric(frame["alpha191_volatility_5"], errors="coerce").quantile(0.80))
        & (pd.to_numeric(frame["alpha191_fade_with_amount"], errors="coerce") < pd.to_numeric(frame["alpha191_fade_with_amount"], errors="coerce").quantile(0.70))
    )
    frame = frame.loc[trend_filter].copy()
    if frame.empty:
        return pd.DataFrame(columns=["trend_alpha_bucket", "sample_count", "avg_future_1d_return", "avg_future_3d_return", "avg_future_5d_return", "win_rate_5d", "avg_future_5d_max_drawdown"])
    frame["trend_alpha_bucket"] = pd.qcut(pd.to_numeric(frame["alpha191_reversal_5"], errors="coerce"), q=3, labels=["low", "mid", "high"], duplicates="drop")
    rows = []
    for bucket, group in frame.groupby("trend_alpha_bucket", observed=False):
        rows.append(
            {
                "trend_alpha_bucket": bucket,
                "sample_count": int(len(group)),
                "avg_future_1d_return": _mean(group["future_1d_return"]),
                "avg_future_3d_return": _mean(group["future_3d_return"]),
                "avg_future_5d_return": _mean(group["future_5d_return"]),
                "win_rate_5d": _win_rate(group["future_5d_return"]),
                "avg_future_5d_max_drawdown": _mean(group["future_5d_max_drawdown"]),
            }
        )
    return pd.DataFrame(rows)


def build_high_volatility_risk_split(dataset: pd.DataFrame) -> pd.DataFrame:
    if dataset.empty:
        return pd.DataFrame()
    frame = dataset.copy()
    vol = pd.to_numeric(frame.get("alpha191_volatility_5"), errors="coerce")
    fade = pd.to_numeric(frame.get("alpha191_fade_with_amount"), errors="coerce")
    reversal = pd.to_numeric(frame.get("alpha191_reversal_5"), errors="coerce")
    high_vol = vol >= vol.quantile(0.90)
    hard_risk = high_vol & (fade >= fade.quantile(0.80))
    clean_strength = high_vol & (fade < fade.quantile(0.60)) & (reversal < reversal.quantile(0.60))
    frame["volatility_risk_group"] = "not_high_vol"
    frame.loc[high_vol, "volatility_risk_group"] = "high_vol_mixed"
    frame.loc[hard_risk, "volatility_risk_group"] = "high_vol_hard_risk"
    frame.loc[clean_strength, "volatility_risk_group"] = "high_vol_clean_strength"
    rows = []
    for group_name, group in frame.groupby("volatility_risk_group"):
        rows.append(
            {
                "volatility_risk_group": group_name,
                "sample_count": int(len(group)),
                "avg_future_1d_return": _mean(group["future_1d_return"]),
                "avg_future_3d_return": _mean(group["future_3d_return"]),
                "avg_future_5d_return": _mean(group["future_5d_return"]),
                "win_rate_5d": _win_rate(group["future_5d_return"]),
                "avg_future_5d_max_drawdown": _mean(group["future_5d_max_drawdown"]),
                "strong_winner_rate_5d": float((pd.to_numeric(group["future_5d_return"], errors="coerce") >= 0.10).mean()) if len(group) else np.nan,
            }
        )
    return pd.DataFrame(rows)


def build_alpha191_redundancy_report(
    dataset: pd.DataFrame,
    *,
    factors: list[str] | None = None,
    threshold: float = 0.85,
) -> pd.DataFrame:
    factors = [factor for factor in (factors or ALPHA191_EXPANDED_FACTORS) if factor in dataset.columns]
    if not factors:
        return pd.DataFrame(columns=["factor_name", "redundancy_group", "recommended_keep", "max_abs_correlation", "reason"])
    sample = dataset[factors].sample(min(len(dataset), 100_000), random_state=17) if len(dataset) > 100_000 else dataset[factors]
    corr = sample.apply(pd.to_numeric, errors="coerce").corr().abs()
    groups: dict[str, str] = {}
    rows = []
    group_id = 1
    for factor in factors:
        if factor in groups:
            continue
        peers = [peer for peer in factors if peer != factor and corr.loc[factor, peer] >= threshold]
        if not peers:
            rows.append(
                {
                    "factor_name": factor,
                    "redundancy_group": "",
                    "recommended_keep": factor,
                    "max_abs_correlation": float(corr.loc[factor].drop(index=factor).max()) if len(factors) > 1 else np.nan,
                    "reason": "not highly correlated with peer factors",
                }
            )
            continue
        group_name = f"group_{group_id:02d}"
        group_id += 1
        members = [factor, *peers]
        keep = _choose_redundancy_representative(members)
        for member in members:
            groups[member] = group_name
            rows.append(
                {
                    "factor_name": member,
                    "redundancy_group": group_name,
                    "recommended_keep": keep,
                    "max_abs_correlation": float(corr.loc[member, [item for item in members if item != member]].max()),
                    "reason": "highly correlated with peer factors; keep representative",
                }
            )
    return pd.DataFrame(rows).drop_duplicates("factor_name").reset_index(drop=True)


def build_alpha191_candidate_factors(
    *,
    factor_effectiveness: pd.DataFrame,
    strong_winner: pd.DataFrame,
    redundancy: pd.DataFrame,
) -> pd.DataFrame:
    if factor_effectiveness.empty:
        return pd.DataFrame()
    frame = factor_effectiveness.merge(
        strong_winner[["factor_name", "lift_vs_baseline"]].rename(columns={"lift_vs_baseline": "strong_winner_lift"}),
        on="factor_name",
        how="left",
    ).merge(
        redundancy[["factor_name", "redundancy_group", "recommended_keep"]],
        on="factor_name",
        how="left",
    )
    decisions = []
    reasons = []
    for _, row in frame.iterrows():
        keep = not row.get("redundancy_group") or row["factor_name"] == row.get("recommended_keep")
        if row["signal_type"] == "useful_signal" and keep:
            decisions.append("promote_candidate")
            reasons.append("positive RankIC and top-bottom spread")
        elif row["signal_type"] == "risk_signal" and keep:
            decisions.append("risk_candidate")
            reasons.append("risk signal with drawdown evidence")
        elif row["signal_type"] == "inverted_signal" and keep:
            decisions.append("inverse_or_filter_candidate")
            reasons.append("factor direction is inverted in validation window")
        elif (row.get("strong_winner_lift") or 0) >= 1.50 and row.get("top_decile_avg_future_5d_max_drawdown", -1) > -0.08 and keep:
            decisions.append("watchlist_diagnostic_candidate")
            reasons.append("captures 2025Q1 strong winners without excessive top-decile drawdown")
        else:
            decisions.append("reject")
            reasons.append("weak or redundant evidence")
    frame["formal_candidate_decision"] = decisions
    frame["candidate_reason"] = reasons
    ordered = frame.sort_values(
        ["formal_candidate_decision", "strong_winner_lift", "rank_ic_5d"],
        ascending=[True, False, False],
        na_position="last",
    )
    return ordered[
        [
            "factor_name",
            "signal_type",
            "recommended_usage",
            "sample_count",
            "rank_ic_5d",
            "top_bottom_spread_5d",
            "top_decile_avg_future_5d_return",
            "top_decile_avg_future_5d_max_drawdown",
            "strong_winner_lift",
            "redundancy_group",
            "recommended_keep",
            "formal_candidate_decision",
            "candidate_reason",
        ]
    ].reset_index(drop=True)


def build_alpha191_pilot_recommendation(
    factor_effectiveness: pd.DataFrame,
    strong_winner: pd.DataFrame,
) -> pd.DataFrame:
    if factor_effectiveness.empty:
        return pd.DataFrame()
    frame = factor_effectiveness.merge(
        strong_winner[["factor_name", "lift_vs_baseline"]],
        on="factor_name",
        how="left",
    )
    frame["category"] = "alpha191_pilot_factor"
    frame["evidence_summary"] = frame.apply(
        lambda row: f"rank_ic_5d={row['rank_ic_5d']:.4f} spread_5d={row['top_bottom_spread_5d']:.4f} strong_lift={row.get('lift_vs_baseline', np.nan):.4f}",
        axis=1,
    )
    frame["next_action"] = np.where(frame["lift_vs_baseline"].fillna(0) >= 1.1, "keep_for_alpha191_pilot_v2", "deprioritize")
    return frame.rename(columns={"factor_name": "feature_or_method"})[
        [
            "feature_or_method",
            "category",
            "signal_type",
            "recommended_usage",
            "evidence_summary",
            "sample_count",
            "next_action",
        ]
    ]


def build_alpha191_pilot_report(**kwargs: Any) -> str:
    return _build_report(title="Alpha191 Pilot Validation", expanded=False, **kwargs)


def build_alpha191_expanded_report(**kwargs: Any) -> str:
    return _build_report(title="Alpha191 Expanded Validation v2", expanded=True, **kwargs)


def _build_report(
    *,
    title: str,
    dataset: pd.DataFrame,
    start_date: str,
    end_date: str,
    adjust_type: str,
    factor_effectiveness: pd.DataFrame,
    strong_winner: pd.DataFrame,
    trend_overlay: pd.DataFrame,
    high_volatility_risk_split: pd.DataFrame,
    expanded: bool,
    factor_bucket: pd.DataFrame | None = None,
    drawdown_risk: pd.DataFrame | None = None,
    redundancy: pd.DataFrame | None = None,
    candidate_factors: pd.DataFrame | None = None,
    recommendation: pd.DataFrame | None = None,
) -> str:
    candidate_counts = candidate_factors["formal_candidate_decision"].value_counts().to_dict() if candidate_factors is not None and not candidate_factors.empty else {}
    return "\n".join(
        [
            f"# {title}",
            "",
            "## 1. Research Goal",
            "This validation is diagnostic only: no live trading, no factor_daily writes, and no strategy scoring integration.",
            "",
            "## 2. Data Scope",
            f"start_date={start_date}, end_date={end_date}, adjust_type={adjust_type}, sample_rows={len(dataset)}, factor_count={len([col for col in dataset.columns if col.startswith('alpha191_')])}.",
            "",
            "## 3. RankIC and Decile Effectiveness",
            _table_preview(factor_effectiveness, 30),
            "",
            "## 4. Strong Winner Explanation (2025Q1 default window)",
            _table_preview(strong_winner, 30),
            "",
            "## 5. Bucket / Drawdown Diagnostics",
            _table_preview(factor_bucket if factor_bucket is not None else drawdown_risk, 30),
            "",
            "## 6. Redundancy",
            _table_preview(redundancy, 30),
            "",
            "## 7. Formal Candidate Factors",
            f"decision_counts={candidate_counts}",
            _table_preview(candidate_factors if candidate_factors is not None else recommendation, 30),
            "",
            "## 8. Trend Continuation Overlay",
            _table_preview(trend_overlay, 20),
            "",
            "## 9. High Volatility Strength vs True Risk",
            _table_preview(high_volatility_risk_split, 20),
            "",
            "## 10. Current Interpretation",
            "Use promoted candidates for the next watchlist diagnostics experiment only after manual review. Do not add the expanded set wholesale to scoring.",
        ]
    )


def _append_future_metrics(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    close = _num(result["close"])
    for horizon in (1, 3, 5, 10, 20):
        result[f"future_{horizon}d_return"] = close.shift(-horizon) / close - 1.0
    for horizon in (3, 5, 10):
        future_low = pd.concat([close.shift(-step) for step in range(1, horizon + 1)], axis=1).min(axis=1)
        result[f"future_{horizon}d_max_drawdown"] = future_low / close - 1.0
    return result


def _assign_buckets(series: pd.Series) -> pd.Series:
    ranked = pd.to_numeric(series, errors="coerce").rank(method="first")
    try:
        return pd.qcut(ranked, q=10, labels=False, duplicates="drop") + 1
    except ValueError:
        return pd.Series([1] * len(series), index=series.index)


def _bucket_row(factor: str, bucket: Any, group: pd.DataFrame) -> dict[str, Any]:
    return {
        "factor_name": factor,
        "bucket": bucket,
        "sample_count": int(len(group)),
        "avg_future_1d_return": _mean(group["future_1d_return"]),
        "avg_future_3d_return": _mean(group["future_3d_return"]),
        "avg_future_5d_return": _mean(group["future_5d_return"]),
        "avg_future_10d_return": _mean(group["future_10d_return"]),
        "win_rate_5d": _win_rate(group["future_5d_return"]),
        "avg_future_5d_max_drawdown": _mean(group["future_5d_max_drawdown"]),
    }


def _mean_rank_ic(frame: pd.DataFrame, factor: str, target: str) -> float:
    values = []
    for _, group in frame[["trade_date", factor, target]].dropna().groupby("trade_date", sort=False):
        if len(group) < 5:
            continue
        corr = group[factor].rank().corr(group[target].rank())
        if pd.notna(corr):
            values.append(corr)
    return float(np.mean(values)) if values else np.nan


def _classify_factor(rank_ic_5d: float, spread_5d: float, drawdown_5d: float) -> tuple[str, str]:
    if pd.isna(rank_ic_5d) or pd.isna(spread_5d):
        return "weak_signal", "discard"
    if rank_ic_5d >= 0.02 and spread_5d >= 0.004 and (pd.isna(drawdown_5d) or drawdown_5d > -0.065):
        return "useful_signal", "entry_confirmation"
    if rank_ic_5d <= -0.02 and spread_5d <= -0.004:
        return "inverted_signal", "case_diagnostic"
    if drawdown_5d <= -0.075 and spread_5d <= 0.0:
        return "risk_signal", "risk_filter"
    return "weak_signal", "discard"


def _choose_redundancy_representative(members: list[str]) -> str:
    priority = [
        "alpha191_reversal_5",
        "alpha191_fade_with_amount",
        "alpha191_rebound_with_amount",
        "alpha191_amount_price_divergence_20",
        "alpha191_price_amount_corr_10",
        "alpha191_amount_zscore_20",
        "alpha191_high_ts_rank_20",
        "alpha191_intraday_return",
        "alpha191_down_days_5",
    ]
    for item in priority:
        if item in members:
            return item
    return sorted(members)[0]


def _num(series: Any) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _safe_divide(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    return numerator / denominator.replace(0.0, np.nan)


def _zscore(series: pd.Series, window: int) -> pd.Series:
    mean = series.rolling(window, min_periods=max(3, window // 2)).mean()
    std = series.rolling(window, min_periods=max(3, window // 2)).std()
    return (series - mean) / std.replace(0.0, np.nan)


def _ts_rank(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window, min_periods=max(3, window // 2)).rank(pct=True)


def _mean(series: pd.Series) -> float:
    return float(pd.to_numeric(series, errors="coerce").mean())


def _win_rate(series: pd.Series) -> float:
    numeric = pd.to_numeric(series, errors="coerce").dropna()
    return float((numeric > 0).mean()) if len(numeric) else np.nan


def _table_preview(frame: pd.DataFrame | None, rows: int = 20) -> str:
    if frame is None or frame.empty:
        return "no data"
    return frame.head(rows).to_markdown(index=False)
