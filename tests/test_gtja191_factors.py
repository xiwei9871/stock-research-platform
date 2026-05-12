import pandas as pd

from stock_research.factors import gtja191


def test_compute_gtja191_factors_returns_short_horizon_volume_price_columns():
    dates = pd.date_range("2026-01-01", periods=15, freq="D")
    bars = pd.DataFrame(
        {
            "trade_date": dates,
            "asset_id": ["A"] * 15,
            "open": range(10, 25),
            "high": range(11, 26),
            "low": range(9, 24),
            "close": range(10, 25),
            "preclose": [None] + list(range(10, 24)),
            "volume": [1000.0 + index * 20 for index in range(15)],
            "amount": [100000.0 + index * 2000 for index in range(15)],
        }
    )

    result = gtja191.compute_gtja191_factors(bars)

    assert {
        "gtja191_vp_corr_10",
        "gtja191_amount_momentum_5_10",
        "gtja191_intraday_strength_6",
    }.issubset(result.columns)
    assert result.iloc[-1]["gtja191_amount_momentum_5_10"] > 1.0
