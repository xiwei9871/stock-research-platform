import pandas as pd

from stock_research.factors import qlib_alpha


def test_compute_qlib_alpha_factors_returns_price_shape_columns():
    dates = pd.date_range("2026-01-01", periods=8, freq="D")
    bars = pd.DataFrame(
        {
            "trade_date": dates,
            "asset_id": ["A"] * 8,
            "open": [10, 11, 12, 13, 14, 15, 16, 17],
            "high": [11, 12, 13, 14, 15, 16, 17, 18],
            "low": [9, 10, 11, 12, 13, 14, 15, 16],
            "close": [10.5, 11.5, 12.5, 13.5, 14.5, 15.5, 16.5, 17.5],
            "preclose": [None, 10.5, 11.5, 12.5, 13.5, 14.5, 15.5, 16.5],
            "volume": [1000.0] * 8,
            "amount": [100000.0] * 8,
        }
    )

    result = qlib_alpha.compute_qlib_alpha_factors(bars)

    assert {
        "qlib_klen",
        "qlib_kupper",
        "qlib_klower",
        "qlib_ret_5",
    }.issubset(result.columns)
    assert result.iloc[-1]["qlib_klen"] > 0
