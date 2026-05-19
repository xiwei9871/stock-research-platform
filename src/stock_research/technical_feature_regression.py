from __future__ import annotations

import argparse
import json

import numpy as np
import pandas as pd

from stock_research.technical_feature_benchmark import generate_synthetic_technical_feature_bars
from stock_research.technical_features import (
    TECHNICAL_FEATURE_COLUMNS,
    compute_daily_technical_features_legacy,
)
from stock_research.technical_features_fast import compute_daily_technical_features_fast

DEFAULT_FAST_REGRESSION_GATE = {
    "max_abs_diff": 1e-12,
    "mean_abs_diff": 1e-12,
    "nan_mismatch_count": 0,
}


def run_technical_feature_fast_regression(
    *,
    asset_count: int = 16,
    bar_count: int = 260,
) -> dict[str, object]:
    scenarios = build_regression_scenarios(asset_count=asset_count, bar_count=bar_count)
    aggregate = _empty_regression_summary(asset_count=asset_count, bar_count=bar_count)
    scenario_results: dict[str, dict[str, object]] = {}

    for scenario_name, grouped in scenarios.items():
        scenario_summary = _run_regression_for_grouped_frames(grouped)
        scenario_results[scenario_name] = scenario_summary
        aggregate["max_abs_diff"] = max(
            float(aggregate["max_abs_diff"]),
            float(scenario_summary["max_abs_diff"]),
        )
        aggregate["nan_mismatch_count"] = int(aggregate["nan_mismatch_count"]) + int(
            scenario_summary["nan_mismatch_count"]
        )
        aggregate["_diff_sum"] += float(scenario_summary["_diff_sum"])
        aggregate["_diff_count"] += int(scenario_summary["_diff_count"])
        _merge_per_column(aggregate["per_column"], scenario_summary["per_column"])

    diff_count = int(aggregate["_diff_count"])
    diff_sum = float(aggregate["_diff_sum"])
    aggregate["mean_abs_diff"] = 0.0 if diff_count == 0 else diff_sum / diff_count
    gate = evaluate_fast_regression_gate(
        max_abs_diff=float(aggregate["max_abs_diff"]),
        mean_abs_diff=float(aggregate["mean_abs_diff"]),
        nan_mismatch_count=int(aggregate["nan_mismatch_count"]),
    )
    return {
        "asset_count": asset_count,
        "bar_count": bar_count,
        "column_count": len(TECHNICAL_FEATURE_COLUMNS),
        "scenario_count": len(scenarios),
        "max_abs_diff": aggregate["max_abs_diff"],
        "mean_abs_diff": aggregate["mean_abs_diff"],
        "nan_mismatch_count": aggregate["nan_mismatch_count"],
        "gate": gate,
        "per_column": _strip_internal_fields(aggregate["per_column"]),
        "scenarios": {
            name: _strip_internal_fields(result)
            for name, result in scenario_results.items()
        },
    }


def build_regression_scenarios(
    *,
    asset_count: int,
    bar_count: int,
) -> dict[str, dict[str, pd.DataFrame]]:
    synthetic = generate_synthetic_technical_feature_bars(
        asset_count=asset_count,
        bar_count=bar_count,
    )
    synthetic = _inject_missing_values(synthetic)
    scenarios = {
        "synthetic_missing": _group_bars_by_asset(synthetic),
        "monotonic_rise": {
            "monotonic_rise": _build_manual_bars([float(index) for index in range(1, max(bar_count, 30) + 1)])
        },
        "monotonic_fall": {
            "monotonic_fall": _build_manual_bars([float(index) for index in range(max(bar_count, 30), 0, -1)])
        },
        "mixed_trend": {
            "mixed_trend": _build_manual_bars(
                [
                    10.0, 13.0, 12.0, 15.0, 14.0, 16.0, 15.0, 18.0, 17.0, 19.0,
                    18.0, 20.0, 17.0, 19.0, 16.0, 18.0, 19.0, 17.0, 21.0, 20.0,
                    22.0, 19.0, 23.0, 18.0, 24.0, 22.0, 25.0, 21.0, 26.0, 23.0,
                ]
            )
        },
        "interior_missing_recovery": {
            "interior_missing_recovery": _build_manual_bars(
                [
                    10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0, 18.0, 19.0,
                    np.nan, 20.0, 19.0, 21.0, 20.0, 22.0, 21.0, 23.0, 22.0, 24.0,
                    23.0, 25.0, 24.0, 26.0, 25.0, 27.0, 26.0, 28.0, 27.0, 29.0,
                ]
            )
        },
    }
    return scenarios


def evaluate_fast_regression_gate(
    *,
    max_abs_diff: float,
    mean_abs_diff: float,
    nan_mismatch_count: int,
) -> dict[str, object]:
    thresholds = dict(DEFAULT_FAST_REGRESSION_GATE)
    passed = (
        max_abs_diff <= float(thresholds["max_abs_diff"])
        and mean_abs_diff <= float(thresholds["mean_abs_diff"])
        and nan_mismatch_count <= int(thresholds["nan_mismatch_count"])
    )
    return {
        "passed": bool(passed),
        "thresholds": thresholds,
    }


def _run_regression_for_grouped_frames(grouped: dict[str, pd.DataFrame]) -> dict[str, object]:
    summary = _empty_regression_summary(asset_count=len(grouped), bar_count=max(len(frame) for frame in grouped.values()))
    for asset_bars in grouped.values():
        legacy = compute_daily_technical_features_legacy(asset_bars)
        fast = compute_daily_technical_features_fast(asset_bars)
        for column in TECHNICAL_FEATURE_COLUMNS:
            legacy_values = pd.to_numeric(legacy[column], errors="coerce").to_numpy(dtype="float64")
            fast_values = pd.to_numeric(fast[column], errors="coerce").to_numpy(dtype="float64")
            nan_mismatch = np.isnan(legacy_values) ^ np.isnan(fast_values)
            valid = ~np.isnan(legacy_values) & ~np.isnan(fast_values)
            diffs = np.abs(legacy_values[valid] - fast_values[valid])
            column_max = float(diffs.max()) if diffs.size else 0.0
            column_mean = float(diffs.mean()) if diffs.size else 0.0
            column_nan_mismatch = int(nan_mismatch.sum())
            summary["per_column"][column]["max_abs_diff"] = max(
                float(summary["per_column"][column]["max_abs_diff"]),
                column_max,
            )
            summary["per_column"][column]["_diff_sum"] += float(diffs.sum()) if diffs.size else 0.0
            summary["per_column"][column]["_diff_count"] += int(diffs.size)
            summary["per_column"][column]["mean_abs_diff"] = max(
                float(summary["per_column"][column]["mean_abs_diff"]),
                column_mean,
            )
            summary["per_column"][column]["nan_mismatch_count"] = int(
                summary["per_column"][column]["nan_mismatch_count"]
            ) + column_nan_mismatch
            summary["max_abs_diff"] = max(float(summary["max_abs_diff"]), column_max)
            summary["nan_mismatch_count"] = int(summary["nan_mismatch_count"]) + column_nan_mismatch
            if diffs.size:
                summary["_diff_sum"] += float(diffs.sum())
                summary["_diff_count"] += int(diffs.size)

    diff_count = int(summary["_diff_count"])
    diff_sum = float(summary["_diff_sum"])
    summary["mean_abs_diff"] = 0.0 if diff_count == 0 else diff_sum / diff_count
    return summary


def _inject_missing_values(bars: pd.DataFrame) -> pd.DataFrame:
    mutated = bars.copy()
    for _, group in mutated.groupby("asset_id", sort=False):
        if len(group) > 12:
            mutated.loc[group.index[10], "close"] = np.nan
            mutated.loc[group.index[11], "high"] = np.nan
            mutated.loc[group.index[11], "low"] = np.nan
    return mutated


def _group_bars_by_asset(bars: pd.DataFrame) -> dict[str, pd.DataFrame]:
    return {
        str(asset_id): group.drop(columns=["asset_id"]).reset_index(drop=True).copy()
        for asset_id, group in bars.groupby("asset_id", sort=False)
    }


def _build_manual_bars(closes: list[float]) -> pd.DataFrame:
    period_count = len(closes)
    close_values = np.array(closes, dtype="float64")
    preclose = np.concatenate(([np.nan], close_values[:-1]))
    open_values = np.where(np.isnan(close_values), np.nan, close_values - 1.0)
    high_values = np.where(np.isnan(close_values), np.nan, close_values + 1.0)
    low_values = np.where(np.isnan(close_values), np.nan, close_values - 2.0)
    return pd.DataFrame(
        {
            "trade_date": pd.date_range("2026-01-01", periods=period_count, freq="D"),
            "open": open_values,
            "high": high_values,
            "low": low_values,
            "close": close_values,
            "preclose": preclose,
            "volume": [1000.0 + index * 10.0 for index in range(period_count)],
            "amount": [10000.0 + index * 200.0 for index in range(period_count)],
            "turnover_rate": [1.0 + index * 0.02 for index in range(period_count)],
        }
    )


def _empty_regression_summary(*, asset_count: int, bar_count: int) -> dict[str, object]:
    return {
        "asset_count": asset_count,
        "bar_count": bar_count,
        "column_count": len(TECHNICAL_FEATURE_COLUMNS),
        "max_abs_diff": 0.0,
        "mean_abs_diff": 0.0,
        "nan_mismatch_count": 0,
        "_diff_sum": 0.0,
        "_diff_count": 0,
        "per_column": {
            column: {
                "max_abs_diff": 0.0,
                "mean_abs_diff": 0.0,
                "nan_mismatch_count": 0,
                "_diff_sum": 0.0,
                "_diff_count": 0,
            }
            for column in TECHNICAL_FEATURE_COLUMNS
        },
    }


def _merge_per_column(
    target: dict[str, dict[str, float | int]],
    source: dict[str, dict[str, float | int]],
) -> None:
    for column in TECHNICAL_FEATURE_COLUMNS:
        target[column]["max_abs_diff"] = max(
            float(target[column]["max_abs_diff"]),
            float(source[column]["max_abs_diff"]),
        )
        target[column]["nan_mismatch_count"] = int(target[column]["nan_mismatch_count"]) + int(
            source[column]["nan_mismatch_count"]
        )
        target[column]["_diff_sum"] += float(source[column]["_diff_sum"])
        target[column]["_diff_count"] += int(source[column]["_diff_count"])
        diff_count = int(target[column]["_diff_count"])
        diff_sum = float(target[column]["_diff_sum"])
        target[column]["mean_abs_diff"] = 0.0 if diff_count == 0 else diff_sum / diff_count


def _strip_internal_fields(payload: dict[str, object]) -> dict[str, object]:
    cleaned: dict[str, object] = {}
    for key, value in payload.items():
        if key.startswith("_"):
            continue
        if isinstance(value, dict):
            cleaned[key] = _strip_internal_fields(value)
        else:
            cleaned[key] = value
    return cleaned


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m stock_research.technical_feature_regression")
    parser.add_argument("--asset-count", type=int, default=16)
    parser.add_argument("--bar-count", type=int, default=260)
    args = parser.parse_args(argv)
    print(
        json.dumps(
            run_technical_feature_fast_regression(
                asset_count=args.asset_count,
                bar_count=args.bar_count,
            ),
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
