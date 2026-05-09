from __future__ import annotations

from typing import Any

import pandas as pd

from stock_research.factor_eval import ic, quantile_return, turnover


def generate_factor_eval_report(
    factors: pd.DataFrame,
    returns: pd.DataFrame,
    factor_name: str,
    factor_col: str = "factor_value",
    return_col: str = "forward_return_5d",
    quantiles: int = 5,
    top_n: int = 20,
) -> dict[str, Any]:
    ic_frame = ic.calc_ic(factors, returns, factor_col=factor_col, return_col=return_col)
    rank_ic_frame = ic.calc_rank_ic(factors, returns, factor_col=factor_col, return_col=return_col)
    quantile_frame = quantile_return.calc_quantile_return(
        factors,
        returns,
        factor_col=factor_col,
        return_col=return_col,
        quantiles=quantiles,
    )
    turnover_frame = turnover.calc_factor_turnover(factors, factor_col=factor_col, top_n=top_n)
    spread_frame = quantile_return.calc_top_bottom_spread(quantile_frame)

    return {
        "factor_name": factor_name,
        "factor_col": factor_col,
        "return_col": return_col,
        "ic": ic_frame,
        "rank_ic": rank_ic_frame,
        "ic_summary": ic.summarize_ic(ic_frame, ic_col="ic"),
        "rank_ic_summary": ic.summarize_ic(rank_ic_frame, ic_col="rank_ic"),
        "quantile_return": quantile_frame,
        "top_bottom_spread": spread_frame,
        "turnover": turnover_frame,
    }
