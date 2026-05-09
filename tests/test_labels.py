import pandas as pd

from stock_research.labels import compute_labels_for_asset


def test_compute_labels_for_asset_future_return():
    bars = pd.DataFrame(
        {
            "trade_date": pd.date_range("2026-01-01", periods=70, freq="D"),
            "close": [float(i) for i in range(1, 71)],
        }
    )

    labels = compute_labels_for_asset("CN:SH:600000", bars)

    sample = labels[
        (labels["trade_date"] == "2026-01-01")
        & (labels["horizon"] == 5)
        & (labels["label_name"] == "future_return")
    ]
    assert round(float(sample.iloc[0]["label_value"]), 6) == 5.0


def test_compute_labels_for_asset_skips_dates_without_future_data():
    bars = pd.DataFrame(
        {
            "trade_date": pd.date_range("2026-01-01", periods=70, freq="D"),
            "close": [float(i) for i in range(1, 71)],
        }
    )

    labels = compute_labels_for_asset("CN:SH:600000", bars)

    last_5_dates = {date.date().isoformat() for date in bars["trade_date"].tail(5)}
    horizon_5_dates = set(labels.loc[labels["horizon"] == 5, "trade_date"])
    assert horizon_5_dates.isdisjoint(last_5_dates)


def test_compute_labels_for_asset_includes_supported_horizons_when_available():
    bars = pd.DataFrame(
        {
            "trade_date": pd.date_range("2026-01-01", periods=70, freq="D"),
            "close": [float(i) for i in range(1, 71)],
        }
    )

    labels = compute_labels_for_asset("CN:SH:600000", bars)

    assert set(labels["horizon"]) == {5, 20, 60}


def test_compute_labels_for_asset_empty_input_returns_empty_frame():
    labels = compute_labels_for_asset(
        "CN:SH:600000",
        pd.DataFrame(columns=["trade_date", "close"]),
    )

    assert labels.empty
