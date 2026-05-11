import pandas as pd

from stock_research.factor_backfill import build_trade_date_range, load_trade_dates_for_backfill
from stock_research.factor_store import score_stored_factor_daily


def score_approved_factors_range(
    start_date: str,
    end_date: str,
    score_version: str = "manual_v1",
    calc_version: str = "v1",
    trading_days_only: bool = True,
    adjust_type: str = "hfq",
) -> pd.DataFrame:
    trade_dates = (
        load_trade_dates_for_backfill(
            start_date=start_date,
            end_date=end_date,
            adjust_type=adjust_type,
        )
        if trading_days_only
        else build_trade_date_range(start_date, end_date)
    )
    rows = []
    for trade_date in trade_dates:
        count = score_stored_factor_daily(
            trade_date=trade_date,
            score_version=score_version,
            calc_version=calc_version,
            approved_only=True,
        )
        rows.append({"trade_date": trade_date, "score_rows": count})
    return pd.DataFrame(rows)
