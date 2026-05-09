import pandas as pd

from stock_research.factors import alpha101


def _bars() -> pd.DataFrame:
    dates = pd.date_range("2026-01-01", periods=12, freq="D")
    return pd.DataFrame(
        {
            "trade_date": list(dates) * 2,
            "asset_id": ["A"] * 12 + ["B"] * 12,
            "open": list(range(10, 22)) + list(range(20, 32)),
            "high": list(range(11, 23)) + list(range(21, 33)),
            "low": list(range(9, 21)) + list(range(19, 31)),
            "close": list(range(10, 22)) + list(range(21, 33)),
            "preclose": [None] + list(range(10, 21)) + [None] + list(range(21, 32)),
            "volume": [1000.0 + index * 10 for index in range(12)] * 2,
            "amount": [100000.0 + index * 1000 for index in range(12)] * 2,
        }
    )


def test_compute_alpha101_factors_returns_representative_columns():
    result = alpha101.compute_alpha101_factors(_bars())

    assert {
        "alpha101_delta_close_1_rank",
        "alpha101_corr_open_volume_10",
        "alpha101_decay_delta_close_5",
    }.issubset(result.columns)
    assert set(result["asset_id"]) == {"A", "B"}
    assert not result.groupby("asset_id").tail(1)["alpha101_delta_close_1_rank"].isna().any()


def test_alpha101_factors_do_not_use_future_rows():
    bars = _bars()
    baseline = alpha101.compute_alpha101_factors(bars).copy()
    mutated = bars.copy()
    mutated.loc[mutated["trade_date"] == pd.Timestamp("2026-01-12"), "close"] = 9999.0

    changed = alpha101.compute_alpha101_factors(mutated)
    mask = baseline["trade_date"] < pd.Timestamp("2026-01-12")

    assert baseline.loc[mask, "alpha101_delta_close_1_rank"].equals(
        changed.loc[mask, "alpha101_delta_close_1_rank"]
    )
