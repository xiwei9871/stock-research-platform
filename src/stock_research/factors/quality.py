import pandas as pd


def compute_quality_factors(indicators: pd.DataFrame) -> pd.DataFrame:
    result = indicators.copy()
    columns = ["roe", "roa", "gross_margin", "net_margin", "debt_ratio", "ocf_to_np"]
    for column in columns:
        result[column] = pd.to_numeric(result[column], errors="coerce")
    return result[["asset_id"] + columns]
