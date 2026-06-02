from __future__ import annotations

from typing import Any

import pandas as pd

from stock_research.factor_eval.base import (
    merge_prepared_factor_returns,
    prepare_factor_frame,
    prepare_return_frame,
)
from stock_research.factor_eval.report import generate_factor_eval_report
from stock_research.factor_eval.turnover import calc_factor_turnover


def generate_multi_horizon_report(
    factors: pd.DataFrame,
    returns: pd.DataFrame,
    factor_name: str,
    horizons: list[int],
    factor_col: str = "factor_value",
    quantiles: int = 5,
    top_n: int = 20,
) -> dict[str, Any]:
    reports = {}
    prepared_factors = prepare_factor_frame(factors, factor_col=factor_col)
    prepared_returns = prepare_return_frame(
        returns,
        return_cols=[f"forward_return_{horizon}d" for horizon in horizons],
    )
    turnover_frame = calc_factor_turnover(
        prepared_factors,
        factor_col=factor_col,
        top_n=top_n,
    )
    for horizon in horizons:
        return_col = f"forward_return_{horizon}d"
        merged_frame = merge_prepared_factor_returns(
            prepared_factors,
            prepared_returns,
            factor_col=factor_col,
            return_col=return_col,
        )
        reports[horizon] = generate_factor_eval_report(
            factors,
            returns,
            factor_name=factor_name,
            factor_col=factor_col,
            return_col=return_col,
            quantiles=quantiles,
            top_n=top_n,
            turnover_frame=turnover_frame,
            merged_frame=merged_frame,
        )
    return {"factor_name": factor_name, "horizons": list(horizons), "reports": reports}
