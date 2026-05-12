import pandas as pd

from stock_research import labels as labels_module
from stock_research.labels import (
    compute_and_store_labels,
    compute_labels_for_asset,
    derive_label_backfill_window,
)


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

    assert set(labels["horizon"]) == {5, 10, 20, 60}


def test_compute_labels_for_asset_includes_10_day_horizon():
    bars = pd.DataFrame(
        {
            "trade_date": pd.date_range("2026-01-01", periods=70, freq="D"),
            "close": [float(i) for i in range(1, 71)],
        }
    )

    labels = compute_labels_for_asset("CN:SH:600000", bars)

    sample = labels[
        (labels["trade_date"] == "2026-01-01")
        & (labels["horizon"] == 10)
        & (labels["label_name"] == "future_return")
    ]
    assert round(float(sample.iloc[0]["label_value"]), 6) == 10.0


def test_compute_labels_for_asset_empty_input_returns_empty_frame():
    labels = compute_labels_for_asset(
        "CN:SH:600000",
        pd.DataFrame(columns=["trade_date", "close"]),
    )

    assert labels.empty


def test_compute_and_store_labels_uses_sql_window_upsert(monkeypatch):
    calls = []

    class Cursor:
        rowcount = 7

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, sql, params):
            calls.append((sql, params))

    class Conn:
        def cursor(self):
            return Cursor()

    monkeypatch.setattr(labels_module, "connect", lambda service: _context(Conn()))

    count = compute_and_store_labels("2026-05-08")

    assert count == 28
    assert len(calls) == 4
    assert "LEAD(close, 10)" in calls[1][0]
    assert calls[0][1]["end_date"] == "2026-05-08"
    assert calls[0][1]["label_name"] == "future_return"


def test_compute_and_store_labels_accepts_start_date_and_horizons(monkeypatch):
    calls = []

    class Cursor:
        rowcount = 11

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, sql, params):
            calls.append((sql, params))

    class Conn:
        def cursor(self):
            return Cursor()

    monkeypatch.setattr(labels_module, "connect", lambda service: _context(Conn()))

    count = compute_and_store_labels(
        "2026-05-08",
        start_date="1990-12-19",
        horizons=[20, 60],
    )

    assert count == 22
    assert len(calls) == 2
    assert "trade_date >= %(start_date)s" in calls[0][0]
    assert calls[0][1]["start_date"] == "1990-12-19"
    assert calls[0][1]["horizon"] == 20
    assert calls[1][1]["horizon"] == 60


def test_derive_label_backfill_window_uses_market_bounds(monkeypatch):
    calls = []
    monkeypatch.setattr(
        labels_module,
        "load_market_date_bounds",
        lambda adjust_type="hfq": {
            "start_date": "1990-12-19",
            "end_date": "2026-05-08",
            "date_count": 8200,
        },
    )
    monkeypatch.setattr(
        labels_module,
        "derive_label_window",
        lambda **kwargs: calls.append(kwargs)
        or {
            "start_date": "1990-12-19",
            "end_date": "2026-02-01",
            "date_count": 8140,
        },
    )

    window = derive_label_backfill_window(horizons=[5, 20, 60])

    assert window == {
        "start_date": "1990-12-19",
        "end_date": "2026-02-01",
        "date_count": 8140,
    }
    assert calls == [
        {
            "start_date": "1990-12-19",
            "end_date": "2026-05-08",
            "horizons": [5, 20, 60],
            "adjust_type": "hfq",
        }
    ]


class _context:
    def __init__(self, value):
        self.value = value

    def __enter__(self):
        return self.value

    def __exit__(self, exc_type, exc, tb):
        return False
