import pandas as pd
import pytest

from stock_research.factors import value


def test_compute_value_factors_uses_point_in_time_finance_and_share_data():
    prices = pd.DataFrame(
        [{"trade_date": "2026-05-08", "asset_id": "A", "close": 10.0}]
    )
    finance = pd.DataFrame(
        [{"asset_id": "A", "np_parent_ttm": 100.0, "revenue_ttm": 1000.0, "equity_parent": 500.0}]
    )
    shares = pd.DataFrame(
        [{"asset_id": "A", "total_share": 100.0, "float_share": 80.0}]
    )

    result = value.compute_value_factors(prices, finance, shares)

    latest = result.iloc[0]
    assert latest["market_cap"] == pytest.approx(1000.0)
    assert latest["float_market_cap"] == pytest.approx(800.0)
    assert latest["pe_ttm"] == pytest.approx(10.0)
    assert latest["ps_ttm"] == pytest.approx(1.0)
    assert latest["pb"] == pytest.approx(2.0)
