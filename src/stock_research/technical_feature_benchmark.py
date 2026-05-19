from __future__ import annotations

import argparse
import json
import time

import numpy as np
import pandas as pd

from stock_research import technical_feature_store
from stock_research.technical_features import (
    TECHNICAL_FEATURE_COLUMNS,
    compute_daily_technical_features,
    compute_daily_technical_features_legacy,
)
from stock_research.technical_features_fast import compute_daily_technical_features_fast


def generate_synthetic_technical_feature_bars(
    *,
    asset_count: int = 16,
    bar_count: int = 260,
    start_date: str = "2020-01-01",
) -> pd.DataFrame:
    if asset_count < 1:
        raise ValueError("asset_count must be >= 1")
    if bar_count < 2:
        raise ValueError("bar_count must be >= 2")

    trade_dates = pd.bdate_range(start=start_date, periods=bar_count)
    base_steps = np.linspace(0.0, 1.0, bar_count)
    frames: list[pd.DataFrame] = []
    for asset_index in range(asset_count):
        asset_id = f"asset_{asset_index + 1:04d}"
        trend = 10.0 + asset_index * 0.35 + base_steps * (1.5 + asset_index * 0.01)
        seasonal = np.sin(np.linspace(0.0, 6.0, bar_count) + asset_index * 0.2) * 0.3
        close = trend + seasonal
        preclose = np.concatenate(([close[0]], close[:-1]))
        high = close + 0.25 + (asset_index % 5) * 0.01
        low = close - 0.22 - (asset_index % 3) * 0.01
        open_price = (close + preclose) / 2.0
        volume = 1_000_000.0 + asset_index * 2500.0 + np.arange(bar_count) * 500.0
        amount = close * volume
        turnover_rate = 0.01 + (asset_index % 7) * 0.001 + base_steps * 0.002
        frames.append(
            pd.DataFrame(
                {
                    "trade_date": trade_dates.astype(str),
                    "asset_id": asset_id,
                    "open": open_price,
                    "high": high,
                    "low": low,
                    "close": close,
                    "preclose": preclose,
                    "volume": volume,
                    "amount": amount,
                    "turnover_rate": turnover_rate,
                }
            )
        )
    return pd.concat(frames, ignore_index=True)


def run_technical_feature_compute_benchmark(
    *,
    asset_count: int = 16,
    bar_count: int = 260,
    repeat: int = 1,
    engine: str = "legacy",
) -> dict[str, int | float | str]:
    if repeat < 1:
        raise ValueError("repeat must be >= 1")
    if engine not in {"legacy", "fast"}:
        raise ValueError("engine must be one of: legacy, fast")

    bars = generate_synthetic_technical_feature_bars(
        asset_count=asset_count,
        bar_count=bar_count,
    )
    grouped = {
        str(asset_id): group.drop(columns=["asset_id"]).reset_index(drop=True).copy()
        for asset_id, group in bars.groupby("asset_id", sort=False)
    }

    compute = (
        compute_daily_technical_features_legacy
        if engine == "legacy"
        else compute_daily_technical_features_fast
    )
    rows_written = 0
    started_at = time.perf_counter()
    for _ in range(repeat):
        for asset_bars in grouped.values():
            features = compute(asset_bars)
            if features.empty:
                continue
            rows_written += 1
    total_seconds = time.perf_counter() - started_at
    total_assets_processed = asset_count * repeat
    per_asset_seconds = total_seconds / total_assets_processed if total_assets_processed > 0 else 0.0
    rows_per_second = rows_written / total_seconds if total_seconds > 0 else 0.0
    return {
        "asset_count": asset_count,
        "bar_count": bar_count,
        "repeat": repeat,
        "engine": engine,
        "indicator_columns": len(TECHNICAL_FEATURE_COLUMNS),
        "rows_written": rows_written,
        "output_mode": "latest_per_asset",
        "total_seconds": total_seconds,
        "per_asset_seconds": per_asset_seconds,
        "rows_per_second": rows_per_second,
    }


def run_technical_feature_compare_benchmark(
    *,
    asset_count: int = 16,
    bar_count: int = 260,
    repeat: int = 1,
) -> dict[str, int | float]:
    legacy = run_technical_feature_compute_benchmark(
        asset_count=asset_count,
        bar_count=bar_count,
        repeat=repeat,
        engine="legacy",
    )
    fast = run_technical_feature_compute_benchmark(
        asset_count=asset_count,
        bar_count=bar_count,
        repeat=repeat,
        engine="fast",
    )
    legacy_total = float(legacy["total_seconds"])
    fast_total = float(fast["total_seconds"])
    speedup_ratio = legacy_total / fast_total if fast_total > 0 else 0.0
    return {
        "asset_count": asset_count,
        "bar_count": bar_count,
        "repeat": repeat,
        "legacy_total_seconds": legacy_total,
        "fast_total_seconds": fast_total,
        "legacy_rows_per_second": float(legacy["rows_per_second"]),
        "fast_rows_per_second": float(fast["rows_per_second"]),
        "speedup_ratio": speedup_ratio,
    }


def run_technical_feature_store_compare_benchmark(
    *,
    asset_count: int = 16,
    bar_count: int = 260,
) -> dict[str, int | float]:
    bars = generate_synthetic_technical_feature_bars(
        asset_count=asset_count,
        bar_count=bar_count,
    )
    normalized_trade_date = str(pd.to_datetime(bars["trade_date"]).max())[:10]
    source_data_version = "synthetic:benchmark"

    legacy_started_at = time.perf_counter()
    legacy_groups = {
        str(asset_id): group.drop(columns=["asset_id"]).reset_index(drop=True).copy()
        for asset_id, group in bars.groupby("asset_id", sort=False)
    }
    legacy_rows = technical_feature_store._build_technical_feature_rows_for_assets(
        legacy_groups.items(),
        normalized_trade_date=normalized_trade_date,
        adjust_type="qfq",
        source_data_version=source_data_version,
    )
    legacy_total_seconds = time.perf_counter() - legacy_started_at

    batch_started_at = time.perf_counter()
    batch_rows = technical_feature_store._build_technical_feature_rows_for_assets(
        ((str(asset_id), group) for asset_id, group in bars.groupby("asset_id", sort=False)),
        normalized_trade_date=normalized_trade_date,
        adjust_type="qfq",
        source_data_version=source_data_version,
    )
    batch_total_seconds = time.perf_counter() - batch_started_at

    latest_only_started_at = time.perf_counter()
    latest_only_rows = technical_feature_store._build_technical_feature_rows_latest_only(
        ((str(asset_id), group) for asset_id, group in bars.groupby("asset_id", sort=False)),
        normalized_trade_date=normalized_trade_date,
        adjust_type="qfq",
        source_data_version=source_data_version,
    )
    latest_only_total_seconds = time.perf_counter() - latest_only_started_at

    speedup_ratio = legacy_total_seconds / batch_total_seconds if batch_total_seconds > 0 else 0.0
    latest_only_speedup_ratio = (
        legacy_total_seconds / latest_only_total_seconds if latest_only_total_seconds > 0 else 0.0
    )
    return {
        "asset_count": asset_count,
        "bar_count": bar_count,
        "legacy_total_seconds": legacy_total_seconds,
        "batch_frame_total_seconds": batch_total_seconds,
        "latest_only_total_seconds": latest_only_total_seconds,
        "legacy_rows_written": len(legacy_rows),
        "batch_frame_rows_written": len(batch_rows),
        "latest_only_rows_written": len(latest_only_rows),
        "speedup_ratio": speedup_ratio,
        "latest_only_speedup_ratio": latest_only_speedup_ratio,
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m stock_research.technical_feature_benchmark")
    parser.add_argument("--asset-count", type=int, default=16)
    parser.add_argument("--bar-count", type=int, default=260)
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--engine", choices=["legacy", "fast", "compare", "store_compare"], default="legacy")
    args = parser.parse_args(argv)
    if args.engine == "compare":
        payload = run_technical_feature_compare_benchmark(
            asset_count=args.asset_count,
            bar_count=args.bar_count,
            repeat=args.repeat,
        )
    elif args.engine == "store_compare":
        payload = run_technical_feature_store_compare_benchmark(
            asset_count=args.asset_count,
            bar_count=args.bar_count,
        )
    else:
        payload = run_technical_feature_compute_benchmark(
            asset_count=args.asset_count,
            bar_count=args.bar_count,
            repeat=args.repeat,
            engine=args.engine,
        )
    print(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
