import pandas as pd
import pytest

from stock_research.features import (
    compute_p0_features_for_asset,
    features_for_trade_date,
    load_bars_for_features,
)


def make_bars() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "trade_date": pd.date_range("2026-01-01", periods=70, freq="D"),
            "close": [float(i) for i in range(1, 71)],
            "amount": [1000.0 + i for i in range(70)],
            "turnover_rate": [1.0 for _ in range(70)],
            "is_st": [False for _ in range(70)],
            "trade_status": ["1" for _ in range(70)],
        }
    )


def test_compute_p0_features_for_asset_includes_latest_p0_features():
    bars = make_bars()

    features = compute_p0_features_for_asset("CN:SH:600000", bars)

    latest = features[features["trade_date"] == "2026-03-11"]
    names = set(latest["feature_name"])
    assert "ret_5d" in names
    assert "ret_20d" in names
    assert "ret_60d" in names
    assert "amount_20d_avg" in names
    assert "max_drawdown_20d" in names


def test_compute_p0_features_for_asset_computes_latest_ret_5d_value():
    features = compute_p0_features_for_asset("CN:SH:600000", make_bars())

    latest_ret_5d = features[
        (features["trade_date"] == "2026-03-11")
        & (features["feature_name"] == "ret_5d")
    ]["feature_value"].iloc[0]

    assert latest_ret_5d == pytest.approx(70.0 / 65.0 - 1.0)


def test_features_for_trade_date_returns_only_requested_date_rows():
    features = compute_p0_features_for_asset("CN:SH:600000", make_bars())

    filtered = features_for_trade_date(features, "2026-03-11")

    assert not filtered.empty
    assert set(filtered["trade_date"]) == {"2026-03-11"}


def test_compute_p0_features_for_asset_empty_input_returns_empty_dataframe():
    features = compute_p0_features_for_asset("CN:SH:600000", pd.DataFrame())

    assert features.empty


def test_load_bars_for_features_uses_latest_rows_per_asset(monkeypatch):
    captured = {}

    class FakeConnection:
        pass

    class FakeConnect:
        def __enter__(self):
            return FakeConnection()

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_connect(service):
        captured["service"] = service
        return FakeConnect()

    def fake_fetch_all(conn, sql, params):
        captured["sql"] = sql
        captured["params"] = params
        return [
            {
                "asset_id": "CN:SH:600000",
                "trade_date": "2026-03-11",
                "close": 70.0,
                "amount": 1069.0,
                "turnover_rate": 1.0,
                "is_st": False,
                "trade_status": "1",
            }
        ]

    monkeypatch.setattr("stock_research.features.connect", fake_connect)
    monkeypatch.setattr("stock_research.features.fetch_all", fake_fetch_all)

    bars = load_bars_for_features("2026-03-11", lookback_bars=120)

    assert "row_number() over (partition by asset_id order by trade_date desc)" in (
        " ".join(captured["sql"].split()).lower()
    )
    assert captured["params"] == ["2026-03-11", 120]
    assert list(bars) == ["CN:SH:600000"]
