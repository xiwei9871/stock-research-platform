import pandas as pd

from stock_research.factors.base import numeric_series, prepare_daily_bars, safe_divide


def compute_sector_factors(
    stock_bars: pd.DataFrame,
    sector_bars: pd.DataFrame,
    ret_window: int = 20,
) -> pd.DataFrame:
    stocks = prepare_daily_bars(stock_bars)
    sectors = prepare_daily_bars(sector_bars)
    keys = ["trade_date", "industry_code"]

    stocks["trade_date"] = stocks["trade_date"].astype(str).str[:10]
    sectors["trade_date"] = sectors["trade_date"].astype(str).str[:10]

    stocks[f"stock_ret_{ret_window}"] = stocks.groupby("asset_id", group_keys=False)["close"].transform(
        lambda values: pd.to_numeric(values, errors="coerce") / pd.to_numeric(values, errors="coerce").shift(ret_window)
        - 1.0
    )
    sectors[f"sector_ret_{ret_window}"] = sectors.groupby("industry_code", group_keys=False)["close"].transform(
        lambda values: pd.to_numeric(values, errors="coerce")
        / pd.to_numeric(values, errors="coerce").shift(ret_window)
        - 1.0
    )

    stock_close = numeric_series(stocks, "close")
    stock_preclose = numeric_series(stocks, "preclose")
    stocks["_is_up"] = stock_close > stock_preclose
    up_ratio = (
        stocks.groupby(keys, as_index=False)["_is_up"]
        .mean()
        .rename(columns={"_is_up": "sector_up_ratio"})
    )

    merged = stocks.merge(
        sectors[keys + [f"sector_ret_{ret_window}", "amount"]].rename(columns={"amount": "sector_amount"}),
        on=keys,
        how="left",
    )
    merged = merged.merge(up_ratio, on=keys, how="left")
    merged[f"stock_excess_ret_{ret_window}"] = (
        merged[f"stock_ret_{ret_window}"] - merged[f"sector_ret_{ret_window}"]
    )
    merged[f"stock_rank_in_sector_{ret_window}"] = merged.groupby(keys)[f"stock_ret_{ret_window}"].rank(
        ascending=False,
        method="min",
    )
    merged[f"sector_amount_ratio_{ret_window}"] = safe_divide(
        merged["sector_amount"],
        merged.groupby("industry_code")["sector_amount"].transform(lambda values: values.rolling(ret_window).mean()),
    )
    return merged.drop(columns=["_is_up"])
