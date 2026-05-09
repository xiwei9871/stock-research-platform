from __future__ import annotations

import pandas as pd


def normalize_trade_keys(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    if "trade_date" in result.columns:
        result["trade_date"] = result["trade_date"].astype(str).str[:10]
    if "asset_id" in result.columns:
        result["asset_id"] = result["asset_id"].astype(str)
    return result


def numeric_column(frame: pd.DataFrame, column: str) -> pd.Series:
    return pd.to_numeric(frame[column], errors="coerce")
