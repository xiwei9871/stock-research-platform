import pandas as pd
import pytest

from stock_research.factor_eval.exposure import calc_group_exposure, calc_size_exposure


def test_calc_group_exposure_returns_factor_mean_by_industry():
    factors = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A", "factor_value": 1.0},
            {"trade_date": "2026-01-01", "asset_id": "B", "factor_value": 3.0},
            {"trade_date": "2026-01-01", "asset_id": "C", "factor_value": 5.0},
        ]
    )
    groups = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A", "industry_code": "I1"},
            {"trade_date": "2026-01-01", "asset_id": "B", "industry_code": "I1"},
            {"trade_date": "2026-01-01", "asset_id": "C", "industry_code": "I2"},
        ]
    )

    result = calc_group_exposure(factors, groups, group_col="industry_code")

    assert result.set_index("industry_code").loc["I1", "mean_factor"] == pytest.approx(2.0)
    assert result.set_index("industry_code").loc["I2", "count"] == 1


def test_calc_size_exposure_correlates_factor_with_log_market_cap_by_date():
    factors = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A", "factor_value": 1.0},
            {"trade_date": "2026-01-01", "asset_id": "B", "factor_value": 2.0},
            {"trade_date": "2026-01-01", "asset_id": "C", "factor_value": 3.0},
        ]
    )
    size = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A", "market_cap": 100.0},
            {"trade_date": "2026-01-01", "asset_id": "B", "market_cap": 200.0},
            {"trade_date": "2026-01-01", "asset_id": "C", "market_cap": 300.0},
        ]
    )

    result = calc_size_exposure(factors, size)

    assert result.iloc[0]["trade_date"] == "2026-01-01"
    assert result.iloc[0]["size_corr"] > 0.9
