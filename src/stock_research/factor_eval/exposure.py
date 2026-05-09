from __future__ import annotations

import numpy as np
import pandas as pd

from stock_research.factor_eval.base import KEY_COLUMNS, normalize_keys


def calc_group_exposure(
    factors: pd.DataFrame,
    groups: pd.DataFrame,
    group_col: str,
    factor_col: str = "factor_value",
) -> pd.DataFrame:
    factor_frame = normalize_keys(factors)
    group_frame = normalize_keys(groups)
    joined = factor_frame[KEY_COLUMNS + [factor_col]].merge(
        group_frame[KEY_COLUMNS + [group_col]],
        on=KEY_COLUMNS,
        how="inner",
    )
    if joined.empty:
        return pd.DataFrame(columns=[group_col, "mean_factor", "count"])
    joined[factor_col] = pd.to_numeric(joined[factor_col], errors="coerce")
    result = (
        joined.dropna(subset=[factor_col, group_col])
        .groupby(group_col, as_index=False)[factor_col]
        .agg(mean_factor="mean", count="count")
        .sort_values(group_col)
        .reset_index(drop=True)
    )
    result["count"] = result["count"].astype(int)
    return result


def calc_size_exposure(
    factors: pd.DataFrame,
    size: pd.DataFrame,
    factor_col: str = "factor_value",
    size_col: str = "market_cap",
) -> pd.DataFrame:
    factor_frame = normalize_keys(factors)
    size_frame = normalize_keys(size)
    joined = factor_frame[KEY_COLUMNS + [factor_col]].merge(
        size_frame[KEY_COLUMNS + [size_col]],
        on=KEY_COLUMNS,
        how="inner",
    )
    if joined.empty:
        return pd.DataFrame(columns=["trade_date", "size_corr", "n"])
    joined[factor_col] = pd.to_numeric(joined[factor_col], errors="coerce")
    joined[size_col] = pd.to_numeric(joined[size_col], errors="coerce")
    joined = joined.dropna(subset=[factor_col, size_col])
    joined = joined[joined[size_col] > 0].copy()
    joined["log_size"] = np.log(joined[size_col])
    rows = []
    for trade_date, group in joined.groupby("trade_date", sort=True):
        if len(group) < 2 or group[factor_col].nunique() < 2 or group["log_size"].nunique() < 2:
            corr = None
        else:
            corr = float(group[factor_col].corr(group["log_size"]))
        rows.append({"trade_date": trade_date, "size_corr": corr, "n": int(len(group))})
    return pd.DataFrame(rows, columns=["trade_date", "size_corr", "n"])
