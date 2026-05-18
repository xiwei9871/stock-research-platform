from __future__ import annotations

import pandas as pd
from pandas.api.types import is_numeric_dtype


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
    factor_frame = prepare_factor_frame(factors, factor_col=factor_col)
    return_frame = prepare_return_frame(returns, return_cols=[return_col])
    return merge_prepared_factor_returns(
        factor_frame,
        return_frame,
        factor_col=factor_col,
        return_col=return_col,
    )


def prepare_factor_frame(
    factors: pd.DataFrame,
    factor_col: str = "factor_value",
) -> pd.DataFrame:
    factor_frame = normalize_keys(factors)
    factor_frame[factor_col] = pd.to_numeric(factor_frame[factor_col], errors="coerce")
    return factor_frame


def prepare_return_frame(
    returns: pd.DataFrame,
    return_cols: list[str] | None = None,
) -> pd.DataFrame:
    return_frame = normalize_keys(returns)
    target_return_cols = (
        [column for column in return_frame.columns if column not in KEY_COLUMNS]
        if return_cols is None
        else list(return_cols)
    )
    for column in target_return_cols:
        if column in return_frame.columns:
            if not is_numeric_dtype(return_frame[column]):
                return_frame[column] = pd.to_numeric(
                    return_frame[column],
                    errors="coerce",
                )
    return return_frame


def merge_prepared_factor_returns(
    factor_frame: pd.DataFrame,
    return_frame: pd.DataFrame,
    factor_col: str,
    return_col: str,
) -> pd.DataFrame:
    merged = factor_frame[KEY_COLUMNS + [factor_col]].merge(
        return_frame[KEY_COLUMNS + [return_col]],
        on=KEY_COLUMNS,
        how="inner",
    )
    return (
        merged.dropna(subset=[factor_col, return_col])
        .sort_values(KEY_COLUMNS)
        .reset_index(drop=True)
    )
