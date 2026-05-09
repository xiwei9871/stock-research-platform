import pandas as pd


def compute_growth_factors(indicators: pd.DataFrame) -> pd.DataFrame:
    result = indicators.copy()
    result["revenue_yoy"] = pd.to_numeric(result["revenue_yoy"], errors="coerce")
    result["np_parent_yoy"] = pd.to_numeric(result["np_yoy"], errors="coerce")
    result["deduct_np_yoy"] = pd.to_numeric(result["deduct_np_yoy"], errors="coerce")
    return result[["asset_id", "revenue_yoy", "np_parent_yoy", "deduct_np_yoy"]]
