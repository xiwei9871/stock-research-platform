from __future__ import annotations

import pandas as pd

from stock_research.factor_eval.base import merged_factor_returns


def calc_ic(
    factors: pd.DataFrame,
    returns: pd.DataFrame,
    factor_col: str = "factor_value",
    return_col: str = "forward_return_5d",
) -> pd.DataFrame:
    merged = merged_factor_returns(factors, returns, factor_col, return_col)
    rows = []
    for trade_date, group in merged.groupby("trade_date", sort=True):
        rows.append(
            {
                "trade_date": trade_date,
                "ic": _correlation(group[factor_col], group[return_col], method="pearson"),
                "n": int(len(group)),
            }
        )
    return pd.DataFrame(rows, columns=["trade_date", "ic", "n"])


def calc_rank_ic(
    factors: pd.DataFrame,
    returns: pd.DataFrame,
    factor_col: str = "factor_value",
    return_col: str = "forward_return_5d",
) -> pd.DataFrame:
    merged = merged_factor_returns(factors, returns, factor_col, return_col)
    rows = []
    for trade_date, group in merged.groupby("trade_date", sort=True):
        factor_rank = group[factor_col].rank(method="average")
        return_rank = group[return_col].rank(method="average")
        rows.append(
            {
                "trade_date": trade_date,
                "rank_ic": _correlation(factor_rank, return_rank),
                "n": int(len(group)),
            }
        )
    return pd.DataFrame(rows, columns=["trade_date", "rank_ic", "n"])


def summarize_ic(ic_frame: pd.DataFrame, ic_col: str = "ic") -> dict[str, float | int | None]:
    clean = pd.to_numeric(ic_frame.get(ic_col, pd.Series(dtype="float64")), errors="coerce").dropna()
    if clean.empty:
        return {"mean_ic": None, "std_ic": None, "icir": None, "ic_count": 0}
    std = float(clean.std(ddof=1)) if len(clean) > 1 else 0.0
    mean = float(clean.mean())
    return {
        "mean_ic": mean,
        "std_ic": std,
        "icir": None if std == 0.0 else mean / std,
        "ic_count": int(len(clean)),
    }


def _correlation(left: pd.Series, right: pd.Series, method: str = "pearson") -> float | None:
    if len(left) < 2 or left.nunique(dropna=True) < 2 or right.nunique(dropna=True) < 2:
        return None
    value = left.corr(right, method=method)
    if pd.isna(value):
        return None
    return float(value)
