from datetime import date, timedelta

import pandas as pd
import pytest

from stock_research.rolling_oversold.market_regime import compute_market_regime_features


def test_market_regime_labels_panic_rebound_watch_after_breadth_shock_and_rebound():
    anchor = date(2026, 7, 3)
    dates = [anchor - timedelta(days=2), anchor - timedelta(days=1), anchor]
    source = {
        "index_bars": pd.DataFrame(
            {
                "index_id": ["benchmark"] * 3,
                "trade_date": dates,
                "close": [100.0, 85.0, 90.0],
                "amount": [100.0, 130.0, 150.0],
            }
        ),
        "stock_bars": pd.DataFrame(
            [
                {
                    "asset_id": asset_id,
                    "trade_date": trade_date,
                    "close": close,
                    "amount": 10.0,
                    "pct_chg": pct_chg,
                }
                for asset_id in ("A", "B", "C")
                for trade_date, close, pct_chg in zip(
                    dates, [100.0, 70.0, 80.0], [0.0, -30.0, 14.29]
                )
            ]
        ),
    }

    result = compute_market_regime_features(source, anchor_date=anchor)

    assert result["market_regime"] == "panic_rebound_watch"
    assert result["breadth_below_ma20"] > 0.5
    assert result["data_cutoff_date"] == anchor


def test_market_regime_rejects_future_only_source():
    source = {
        "index_bars": pd.DataFrame(
            {
                "index_id": ["benchmark"],
                "trade_date": [date(2026, 7, 4)],
                "close": [100.0],
                "amount": [10.0],
            }
        ),
        "stock_bars": pd.DataFrame(),
    }

    with pytest.raises(ValueError, match="on or before anchor_date"):
        compute_market_regime_features(source, anchor_date=date(2026, 7, 3))


def test_market_dispersion_uses_all_assets_in_recent_sessions():
    anchor = date(2026, 7, 3)
    dates = [anchor - timedelta(days=2), anchor - timedelta(days=1), anchor]
    source = {
        "index_bars": pd.DataFrame(
            {
                "index_id": ["benchmark"] * 3,
                "trade_date": dates,
                "close": [100.0, 100.0, 100.0],
            }
        ),
        "stock_bars": pd.DataFrame(
            [
                {
                    "asset_id": asset_id,
                    "trade_date": trade_date,
                    "close": 100.0,
                    "pct_chg": pct_chg,
                }
                for asset_id, changes in (("A", [0.0, 0.0, 0.0]), ("B", [-10.0, 10.0, -10.0]))
                for trade_date, pct_chg in zip(dates, changes)
            ]
        ),
    }

    result = compute_market_regime_features(source, anchor_date=anchor)

    assert result["dispersion_20d"] > 0.0


def test_market_regime_ignores_future_rows_when_a_cutoff_exists():
    anchor = date(2026, 7, 3)
    source = {
        "index_bars": pd.DataFrame(
            {
                "index_id": ["benchmark", "benchmark", "benchmark"],
                "trade_date": [anchor - timedelta(days=1), anchor, anchor + timedelta(days=1)],
                "close": [100.0, 80.0, 200.0],
            }
        ),
        "stock_bars": pd.DataFrame(
            {
                "asset_id": ["A", "A", "A"],
                "trade_date": [anchor - timedelta(days=1), anchor, anchor + timedelta(days=1)],
                "close": [100.0, 80.0, 200.0],
                "pct_chg": [0.0, -20.0, 150.0],
            }
        ),
    }

    result = compute_market_regime_features(source, anchor_date=anchor)

    assert result["data_cutoff_date"] == anchor
    assert result["breadth_below_ma20"] == 1.0
    assert result["index_return_1d"] == pytest.approx(-0.20)


def test_market_duplicate_rows_are_permutation_invariant():
    anchor = date(2026, 7, 3)
    index_bars = pd.DataFrame(
        {
            "index_id": ["benchmark", "benchmark", "benchmark", "benchmark"],
            "trade_date": [anchor - timedelta(days=1), anchor, anchor, anchor],
            "close": [100.0, 80.0, 90.0, 80.0],
            "amount": [100.0, 200.0, 150.0, 200.0],
        }
    )
    stock_bars = pd.DataFrame(
        {
            "asset_id": ["A", "A", "A", "A"],
            "trade_date": [anchor - timedelta(days=1), anchor, anchor, anchor],
            "close": [100.0, 80.0, 90.0, 80.0],
            "amount": [10.0, 20.0, 30.0, 20.0],
            "pct_chg": [0.0, -20.0, -10.0, -20.0],
        }
    )

    first = compute_market_regime_features(
        {"index_bars": index_bars, "stock_bars": stock_bars}, anchor_date=anchor
    )
    second = compute_market_regime_features(
        {
            "index_bars": index_bars.sample(frac=1.0, random_state=11).reset_index(drop=True),
            "stock_bars": stock_bars.sample(frac=1.0, random_state=19).reset_index(drop=True),
        },
        anchor_date=anchor,
    )

    pd.testing.assert_frame_equal(
        pd.DataFrame([first]).sort_index(axis=1), pd.DataFrame([second]).sort_index(axis=1)
    )
