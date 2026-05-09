import pandas as pd


def compute_value_factors(
    prices: pd.DataFrame,
    finance: pd.DataFrame,
    shares: pd.DataFrame,
) -> pd.DataFrame:
    frame = prices.merge(finance, on="asset_id", how="left").merge(shares, on="asset_id", how="left")
    frame["market_cap"] = pd.to_numeric(frame["close"], errors="coerce") * pd.to_numeric(
        frame["total_share"], errors="coerce"
    )
    frame["float_market_cap"] = pd.to_numeric(frame["close"], errors="coerce") * pd.to_numeric(
        frame["float_share"], errors="coerce"
    )
    frame["pe_ttm"] = frame["market_cap"] / pd.to_numeric(
        frame["np_parent_ttm"], errors="coerce"
    ).replace(0, pd.NA)
    frame["ps_ttm"] = frame["market_cap"] / pd.to_numeric(
        frame["revenue_ttm"], errors="coerce"
    ).replace(0, pd.NA)
    frame["pb"] = frame["market_cap"] / pd.to_numeric(
        frame["equity_parent"], errors="coerce"
    ).replace(0, pd.NA)
    return frame
