from __future__ import annotations

import pandas as pd


KEY_COLUMNS = ["trade_date", "asset_id"]


def normalize_keys(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result["trade_date"] = result["trade_date"].astype(str).str[:10]
    result["asset_id"] = result["asset_id"].astype(str)
    return result


def merged_factor_returns(
    factors: pd.DataFrame,
    returns: pd.DataFrame,
    factor_col: str,
    return_col: str,
) -> pd.DataFrame:
    factor_frame = normalize_keys(factors)
    return_frame = normalize_keys(returns)
    merged = factor_frame[KEY_COLUMNS + [factor_col]].merge(
        return_frame[KEY_COLUMNS + [return_col]],
        on=KEY_COLUMNS,
        how="inner",
    )
    merged[factor_col] = pd.to_numeric(merged[factor_col], errors="coerce")
    merged[return_col] = pd.to_numeric(merged[return_col], errors="coerce")
    return merged.dropna(subset=[factor_col, return_col]).sort_values(KEY_COLUMNS).reset_index(drop=True)
