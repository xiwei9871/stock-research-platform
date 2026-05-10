import pandas as pd

from stock_research.factor_pipeline import build_and_store_factor_daily


def build_trade_date_range(start_date: str, end_date: str) -> list[str]:
    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date)
    if end < start:
        raise ValueError("end_date must be >= start_date")
    return [value.date().isoformat() for value in pd.date_range(start, end, freq="D")]


def backfill_factor_daily_range(
    start_date: str,
    end_date: str,
    lookback_bars: int = 130,
    industry_system: str = "csrc",
) -> pd.DataFrame:
    rows = []
    for trade_date in build_trade_date_range(start_date, end_date):
        count = build_and_store_factor_daily(
            trade_date=trade_date,
            lookback_bars=lookback_bars,
            industry_system=industry_system,
        )
        rows.append({"trade_date": trade_date, "factor_rows": count})
    return pd.DataFrame(rows)
