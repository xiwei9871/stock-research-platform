import pandas as pd
import pytest

from stock_research.factors import base


def test_cross_sectional_rank_ranks_within_trade_date():
    frame = pd.DataFrame(
        {
            "trade_date": ["2026-01-01", "2026-01-01", "2026-01-02"],
            "asset_id": ["A", "B", "A"],
            "value": [10.0, 20.0, 5.0],
        }
    )

    result = base.cross_sectional_rank(frame, "value")

    assert result.tolist() == [0.5, 1.0, 1.0]


def test_ts_rank_uses_current_and_prior_values_only():
    values = pd.Series([3.0, 1.0, 2.0, 5.0])

    result = base.ts_rank(values, window=3)

    assert pd.isna(result.iloc[0])
    assert result.iloc[2] == pytest.approx(2 / 3)
    assert result.iloc[3] == pytest.approx(1.0)


def test_decay_linear_weights_recent_values_more():
    values = pd.Series([1.0, 2.0, 3.0])

    result = base.decay_linear(values, window=3)

    assert result.iloc[-1] == pytest.approx((1.0 * 1 + 2.0 * 2 + 3.0 * 3) / 6)


def test_delta_delay_signed_power_and_rolling_relationships():
    left = pd.Series([1.0, 2.0, 4.0, 7.0])
    right = pd.Series([2.0, 4.0, 8.0, 14.0])

    assert base.delta(left, period=1).tolist()[1:] == [1.0, 2.0, 3.0]
    assert base.delay(left, period=2).tolist()[2:] == [1.0, 2.0]
    assert base.signed_power(pd.Series([-2.0, 3.0]), 2).tolist() == [-4.0, 9.0]
    assert base.rolling_corr(left, right, window=3).iloc[-1] == pytest.approx(1.0)
    assert base.rolling_cov(left, right, window=3).iloc[-1] > 0
