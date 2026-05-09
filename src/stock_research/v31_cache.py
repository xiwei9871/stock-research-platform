import json
from pathlib import Path
from typing import Any

import pandas as pd

from stock_research.backtest import load_backtest_inputs
from stock_research.retention_backtest import (
    _board_key,
    _entry_allowed_assets_from_daily,
    _feature_values_by_date,
    _limit_stats,
    _market_amount_ok_by_date,
    _normalize_dates,
    _is_up_bar,
    _numeric_series,
    _passes_hard_entry_filters,
    _retention_config_for_variant,
    _retention_score,
    _up_ratio,
)


CACHE_FILES = {
    "asset_features": "asset_features",
    "market_regime": "market_regime",
    "board_regime": "board_regime",
    "retention_candidates": "retention_candidates_v3_1",
}


def build_v31_cache(
    start_date: object,
    end_date: object,
    cache_dir: str | Path = Path("/Users/xiwei/stock_research/cache/v3_1"),
    output_format: str = "auto",
) -> dict[str, Any]:
    features, bars = load_backtest_inputs(start_date, end_date, future_buffer_days=30)
    return build_v31_cache_from_frames(
        features,
        bars,
        start_date=start_date,
        end_date=end_date,
        cache_dir=cache_dir,
        prefer_parquet=output_format != "csv",
    )


def build_v31_cache_from_frames(
    feature_frame: pd.DataFrame,
    bar_frame: pd.DataFrame,
    start_date: object,
    end_date: object,
    cache_dir: str | Path,
    prefer_parquet: bool = True,
) -> dict[str, Any]:
    cache_path = Path(cache_dir)
    cache_path.mkdir(parents=True, exist_ok=True)

    features = _normalize_dates(feature_frame)
    bars = _normalize_dates(bar_frame)
    start = _iso_date(start_date)
    end = _iso_date(end_date)
    features = features[(features["trade_date"] >= start) & (features["trade_date"] <= end)]
    bars = bars[(bars["trade_date"] >= start) & (bars["trade_date"] <= end)]

    asset_features = _asset_features_frame(features)
    market_regime = _market_regime_frame(bars)
    board_regime = _board_regime_frame(features, bars)
    candidates = _retention_candidates_frame(features, bars)

    paths = {
        "asset_features": _write_frame(
            asset_features,
            cache_path / CACHE_FILES["asset_features"],
            prefer_parquet,
        ),
        "market_regime": _write_frame(
            market_regime,
            cache_path / CACHE_FILES["market_regime"],
            prefer_parquet,
        ),
        "board_regime": _write_frame(
            board_regime,
            cache_path / CACHE_FILES["board_regime"],
            prefer_parquet,
        ),
        "retention_candidates": _write_frame(
            candidates,
            cache_path / CACHE_FILES["retention_candidates"],
            prefer_parquet,
        ),
    }
    manifest = {
        "start_date": start,
        "end_date": end,
        "paths": paths,
        "counts": {
            "asset_features": int(len(asset_features)),
            "market_regime": int(len(market_regime)),
            "board_regime": int(len(board_regime)),
            "retention_candidates": int(len(candidates)),
        },
    }
    manifest_path = cache_path / "manifest.json"
    paths["manifest"] = str(manifest_path)
    manifest["paths"] = paths
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def _asset_features_frame(features: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "trade_date",
        "asset_id",
        "ret_5d",
        "ret_20d",
        "ret_60d",
        "amount_20d_avg",
        "turnover_20d_avg",
        "volatility_20d",
        "ma20_deviation",
        "max_drawdown_20d",
    ]
    if features.empty:
        return pd.DataFrame(columns=columns)
    matrix = (
        features.pivot_table(
            index=["trade_date", "asset_id"],
            columns="feature_name",
            values="feature_value",
            aggfunc="first",
        )
        .reset_index()
        .rename_axis(None, axis=1)
    )
    return matrix.reindex(columns=columns).sort_values(["trade_date", "asset_id"])


def _market_regime_frame(bars: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "trade_date",
        "total_amount",
        "amount_ratio_20d",
        "up_ratio",
        "limit_up_count",
        "limit_down_count",
        "limit_up_down_ratio",
        "market_allows_entry",
    ]
    if bars.empty:
        return pd.DataFrame(columns=columns)
    daily_amount = (
        bars.groupby("trade_date", as_index=False)["amount"]
        .sum()
        .sort_values("trade_date")
        .reset_index(drop=True)
    )
    amount_ok = _market_amount_ok_by_date(daily_amount)
    rolling_amount = pd.to_numeric(daily_amount["amount"], errors="coerce").rolling(20, min_periods=5).mean()
    amount_ratio = {
        str(row["trade_date"]): (
            None
            if pd.isna(rolling_amount.iloc[index]) or float(rolling_amount.iloc[index]) == 0.0
            else float(row["amount"]) / float(rolling_amount.iloc[index])
        )
        for index, row in daily_amount.iterrows()
    }
    rows = []
    for trade_date, group in bars.groupby("trade_date", sort=True):
        tradable = group[group["trade_status"].astype(str) == "1"].copy()
        limit_stats = _limit_stats(tradable)
        up_ratio = _up_ratio(tradable)
        market_allows_entry = (
            up_ratio >= 0.45
            and limit_stats["limit_down_count"] <= 80
            and limit_stats["limit_up_down_ratio"] >= 1.2
            and amount_ok.get(str(trade_date), True)
        )
        rows.append(
            {
                "trade_date": str(trade_date),
                "total_amount": float(pd.to_numeric(group["amount"], errors="coerce").sum()),
                "amount_ratio_20d": amount_ratio.get(str(trade_date)),
                "up_ratio": up_ratio,
                "limit_up_count": limit_stats["limit_up_count"],
                "limit_down_count": limit_stats["limit_down_count"],
                "limit_up_down_ratio": limit_stats["limit_up_down_ratio"],
                "market_allows_entry": market_allows_entry,
            }
        )
    return pd.DataFrame(rows, columns=columns)


def _board_regime_frame(features: pd.DataFrame, bars: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "trade_date",
        "board",
        "ret_5d_median",
        "ret_20d_median",
        "up_ratio",
        "amount",
        "board_allows_entry",
    ]
    if bars.empty:
        return pd.DataFrame(columns=columns)
    feature_values = _feature_values_by_date(features)
    rows = []
    for trade_date, group in bars.groupby("trade_date", sort=True):
        allowed_assets = _entry_allowed_assets_from_daily(
            feature_values.get(str(trade_date), {}),
            group,
        )
        asset_rows = []
        for row in group.to_dict("records"):
            asset_id = str(row["asset_id"])
            values = feature_values.get(str(trade_date), {}).get(asset_id, {})
            asset_rows.append(
                {
                    "asset_id": asset_id,
                    "board": _board_key(asset_id),
                    "ret_5d": values.get("ret_5d"),
                    "ret_20d": values.get("ret_20d"),
                    "is_up": _is_up_bar(row),
                    "amount": row.get("amount"),
                    "board_allows_entry": asset_id in allowed_assets,
                }
            )
        frame = pd.DataFrame(asset_rows)
        for board, board_frame in frame.groupby("board", sort=False):
            up_flags = board_frame["is_up"].dropna()
            rows.append(
                {
                    "trade_date": str(trade_date),
                    "board": str(board),
                    "ret_5d_median": _median_or_none(board_frame["ret_5d"]),
                    "ret_20d_median": _median_or_none(board_frame["ret_20d"]),
                    "up_ratio": float(up_flags.mean()) if not up_flags.empty else None,
                    "amount": float(pd.to_numeric(board_frame["amount"], errors="coerce").sum()),
                    "board_allows_entry": bool(board_frame["board_allows_entry"].any()),
                }
            )
    return pd.DataFrame(rows, columns=columns)


def _retention_candidates_frame(features: pd.DataFrame, bars: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "trade_date",
        "asset_id",
        "rank",
        "score",
        "hard_filter_pass",
        "board_filter_pass",
        "market_filter_pass",
    ]
    if features.empty or bars.empty:
        return pd.DataFrame(columns=columns)
    config = _retention_config_for_variant("v3.1", features["trade_date"].min(), features["trade_date"].max(), 1000000.0, 10, "cache")
    feature_values = _feature_values_by_date(features)
    market = _market_regime_frame(bars).set_index("trade_date")
    rows = []
    for trade_date, values_by_asset in feature_values.items():
        day_bars = bars[bars["trade_date"] == trade_date]
        allowed_assets = _entry_allowed_assets_from_daily(values_by_asset, day_bars)
        market_allows = bool(market.loc[trade_date, "market_allows_entry"]) if trade_date in market.index else True
        scored = []
        tradable_assets = set(day_bars.loc[day_bars["trade_status"].astype(str) == "1", "asset_id"].astype(str))
        for asset_id, asset_features in values_by_asset.items():
            if asset_id not in tradable_assets:
                continue
            if any(asset_features.get(name) is None for name in ("ret_20d", "ret_60d", "amount_20d_avg", "volatility_20d", "max_drawdown_20d")):
                continue
            if float(asset_features.get("amount_20d_avg", 0.0)) < 30000000.0:
                continue
            if not _passes_hard_entry_filters(asset_features):
                continue
            scored.append((asset_id, _retention_score(asset_features, True), asset_features))
        scored.sort(key=lambda item: (-float(item[1]), item[0]))
        for rank, (asset_id, score, asset_features) in enumerate(scored[:30], start=1):
            rows.append(
                {
                    "trade_date": trade_date,
                    "asset_id": asset_id,
                    "rank": rank,
                    "score": score,
                    "hard_filter_pass": _passes_hard_entry_filters(asset_features),
                    "board_filter_pass": asset_id in allowed_assets,
                    "market_filter_pass": market_allows,
                }
            )
    return pd.DataFrame(rows, columns=columns)


def _median_or_none(values: pd.Series) -> float | None:
    numeric = pd.to_numeric(values, errors="coerce").dropna()
    if numeric.empty:
        return None
    return float(numeric.median())


def _write_frame(frame: pd.DataFrame, path_without_suffix: Path, prefer_parquet: bool) -> str:
    if prefer_parquet:
        try:
            path = path_without_suffix.with_suffix(".parquet")
            frame.to_parquet(path, index=False)
            return str(path)
        except (ImportError, ModuleNotFoundError, ValueError):
            pass
    path = path_without_suffix.with_suffix(".csv")
    frame.to_csv(path, index=False)
    return str(path)


def _iso_date(value: object) -> str:
    return pd.Timestamp(value).date().isoformat()
