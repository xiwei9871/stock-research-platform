from __future__ import annotations

from typing import Any

import pandas as pd

from stock_research.factor_eval.report import generate_factor_eval_report


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
    for horizon in horizons:
        return_col = f"forward_return_{horizon}d"
        reports[horizon] = generate_factor_eval_report(
            factors,
            returns,
            factor_name=factor_name,
            factor_col=factor_col,
            return_col=return_col,
            quantiles=quantiles,
            top_n=top_n,
        )
    return {"factor_name": factor_name, "horizons": list(horizons), "reports": reports}
