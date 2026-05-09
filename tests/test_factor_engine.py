from decimal import Decimal

import pandas as pd
import pytest

from stock_research.factors import (
    momentum,
    risk,
    sector,
    trend,
    volume_price,
)


def price_frame() -> pd.DataFrame:
    close = [float(value) for value in range(1, 71)]
    return pd.DataFrame(
        {
            "trade_date": pd.date_range("2026-01-01", periods=70, freq="D"),
            "close": close,
            "high": [value + 1.0 for value in close],
            "low": [max(value - 1.0, 0.5) for value in close],
            "open": close,
            "preclose": [None] + close[:-1],
            "volume": [1000.0 + value for value in range(70)],
            "amount": [1000000.0 + value * 1000.0 for value in range(70)],
            "turnover_rate": [1.0 + value / 100.0 for value in range(70)],
        }
    )


def test_momentum_factors_compute_returns_and_skip_recent_window():
    bars = price_frame()

    factors = momentum.compute_momentum_factors(bars)

    latest = factors.iloc[-1]
    assert latest["ret_5"] == pytest.approx(70 / 65 - 1.0)
    assert latest["ret_20"] == pytest.approx(70 / 50 - 1.0)
    assert latest["ret_60"] == pytest.approx(70 / 10 - 1.0)
    assert latest["momentum_20_5"] == pytest.approx((70 / 50 - 1.0) - (70 / 65 - 1.0))


def test_trend_factors_compute_ma_alignment_and_new_highs():
    bars = price_frame()

    factors = trend.compute_trend_factors(bars)

    latest = factors.iloc[-1]
    assert bool(latest["close_above_ma20"]) is True
    assert bool(latest["close_above_ma60"]) is True
    assert bool(latest["ma_alignment"]) is True
    assert bool(latest["new_high_20"]) is True
    assert latest["ma20_slope"] > 0
    assert latest["trend_r2_20"] == pytest.approx(1.0)


def test_volume_price_factors_compute_ratios_and_corr():
    bars = price_frame()

    factors = volume_price.compute_volume_price_factors(bars)

    latest = factors.iloc[-1]
    assert latest["amount_ratio_5_20"] > 1.0
    assert latest["volume_ratio_5_20"] > 1.0
    assert latest["turnover_ratio_5_20"] > 1.0
    assert latest["price_volume_corr_10"] == pytest.approx(1.0)
    assert bool(latest["amount_breakout"]) is True


def test_risk_factors_compute_drawdown_atr_and_distance():
    bars = price_frame()

    factors = risk.compute_risk_factors(bars)

    latest = factors.iloc[-1]
    assert latest["volatility_20"] >= 0
    assert latest["max_drawdown_20"] == pytest.approx(0.0)
    assert latest["atr_14"] > 0
    assert latest["atr_pct"] > 0
    assert latest["distance_ma20"] > 0
    assert latest["distance_ma60"] > 0


def test_sector_factors_join_sector_strength_and_rank_stock():
    stock = pd.DataFrame(
        {
            "trade_date": ["2026-01-01", "2026-01-02", "2026-01-03"],
            "asset_id": ["A", "A", "A"],
            "industry_code": ["T", "T", "T"],
            "close": [10.0, 12.0, 15.0],
            "preclose": [9.0, 10.0, 12.0],
            "amount": [100.0, 140.0, 220.0],
        }
    )
    sector_bars = pd.DataFrame(
        {
            "trade_date": ["2026-01-01", "2026-01-02", "2026-01-03"],
            "industry_code": ["T", "T", "T"],
            "close": [100.0, 110.0, 121.0],
            "preclose": [99.0, 100.0, 110.0],
            "amount": [1000.0, 1200.0, 1800.0],
        }
    )

    factors = sector.compute_sector_factors(stock, sector_bars, ret_window=2)

    latest = factors.iloc[-1]
    assert latest["sector_ret_2"] == pytest.approx(121 / 100 - 1.0)
    assert latest["stock_excess_ret_2"] == pytest.approx((15 / 10 - 1.0) - (121 / 100 - 1.0))
    assert latest["sector_up_ratio"] == pytest.approx(1.0)


def test_sector_factors_accept_decimal_amounts_from_postgres():
    stock = pd.DataFrame(
        {
            "trade_date": ["2026-01-01", "2026-01-02", "2026-01-03"],
            "asset_id": ["A", "A", "A"],
            "industry_code": ["T", "T", "T"],
            "close": [Decimal("10"), Decimal("12"), Decimal("15")],
            "preclose": [Decimal("9"), Decimal("10"), Decimal("12")],
            "amount": [Decimal("100"), Decimal("140"), Decimal("220")],
        }
    )
    sector_bars = pd.DataFrame(
        {
            "trade_date": ["2026-01-01", "2026-01-02", "2026-01-03"],
            "industry_code": ["T", "T", "T"],
            "close": [Decimal("100"), Decimal("110"), Decimal("121")],
            "preclose": [Decimal("99"), Decimal("100"), Decimal("110")],
            "amount": [Decimal("1000"), Decimal("1200"), Decimal("1800")],
        }
    )

    factors = sector.compute_sector_factors(stock, sector_bars, ret_window=2)

    assert factors.iloc[-1]["sector_amount_ratio_2"] == pytest.approx(1800 / 1500)
