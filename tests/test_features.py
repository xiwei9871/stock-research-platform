import pandas as pd
import pytest

from stock_research.features import (
    compute_p0_features_for_asset,
    compute_and_store_p0_features_range,
    derive_feature_backfill_window,
    features_for_trade_date,
    load_bars_for_features,
)
from stock_research import features as features_module


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


def test_compute_and_store_p0_features_batches_assets_into_one_upsert(monkeypatch):
    pending = {
        "CN:SH:600000": make_bars(),
        "CN:SZ:000001": make_bars(),
    }
    upserts = []
    monkeypatch.setattr(features_module, "load_bars_for_features", lambda *args, **kwargs: pending)
    monkeypatch.setattr(
        features_module,
        "replace_feature_snapshot",
        lambda trade_date, frame: upserts.append((trade_date, frame)) or len(frame),
    )

    count = features_module.compute_and_store_p0_features("2026-03-11")

    assert len(upserts) == 1
    assert upserts[0][0] == "2026-03-11"
    assert len(upserts[0][1]) == 16
    assert set(upserts[0][1]["asset_id"]) == set(pending)
    assert count == 16


def test_load_complete_feature_dates_requires_per_feature_asset_coverage(monkeypatch):
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
        return []

    monkeypatch.setattr(features_module, "connect", fake_connect)
    monkeypatch.setattr(features_module, "fetch_all", fake_fetch_all)

    assert features_module.load_complete_feature_dates("2026-03-01", "2026-03-11") == set()

    normalized_sql = " ".join(captured["sql"].split()).lower()
    assert "market_daily_bar" in normalized_sql
    assert "min(asset_count)" in normalized_sql
    assert "expected_assets" in normalized_sql
    assert "feature_name = any" in normalized_sql
    assert "join market_daily_bar" in normalized_sql
    assert captured["params"][-3] == features_module.FEATURE_NAMES
    assert captured["params"][-1] == pytest.approx(0.99)


def test_compute_and_store_p0_features_replaces_stale_rows_for_trade_date(monkeypatch):
    pending = {"CN:SH:600000": make_bars()}
    replacements = []
    monkeypatch.setattr(features_module, "load_bars_for_features", lambda *args, **kwargs: pending)
    monkeypatch.setattr(
        features_module,
        "replace_feature_snapshot",
        lambda trade_date, frame: replacements.append((trade_date, frame)) or len(frame),
    )

    count = features_module.compute_and_store_p0_features("2026-03-11")

    assert len(replacements) == 1
    assert replacements[0][0] == "2026-03-11"
    assert count == len(replacements[0][1])


def test_feature_snapshot_coverage_rejects_partial_replacement():
    snapshot = pd.DataFrame(
        [
            {"asset_id": "CN:SH:600000", "feature_name": feature_name}
            for feature_name in features_module.FEATURE_NAMES
        ]
    )

    with pytest.raises(RuntimeError, match="refusing to replace incomplete"):
        features_module._validate_feature_snapshot_coverage(
            snapshot,
            trade_date="2026-03-11",
            expected_asset_count=100,
        )


def test_load_bars_for_features_limits_source_scan_to_lookback_dates(monkeypatch):
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

    normalized_sql = " ".join(captured["sql"].split()).lower()
    assert "with lookback_dates as" in normalized_sql
    assert "join lookback_dates" in normalized_sql
    assert "row_number() over (partition by asset_id order by trade_date desc)" not in normalized_sql
    assert captured["params"] == ["2026-03-11", 120]
    assert list(bars) == ["CN:SH:600000"]


def test_derive_feature_backfill_window_uses_market_bounds(monkeypatch):
    calls = []
    monkeypatch.setattr(
        features_module,
        "load_market_date_bounds",
        lambda adjust_type="hfq": {
            "start_date": "1990-12-19",
            "end_date": "2026-05-08",
            "date_count": 8200,
        },
    )
    monkeypatch.setattr(
        features_module,
        "derive_feature_window",
        lambda **kwargs: calls.append(kwargs)
        or {
            "start_date": "1991-06-20",
            "end_date": "2026-05-08",
            "date_count": 8071,
        },
    )

    window = derive_feature_backfill_window(lookback_bars=130)

    assert window == {
        "start_date": "1991-06-20",
        "end_date": "2026-05-08",
        "date_count": 8071,
    }
    assert calls[0]["lookback_bars"] == 130


def test_compute_and_store_p0_features_range_skips_complete_dates(monkeypatch):
    calls = []
    monkeypatch.setattr(
        features_module,
        "load_trade_dates",
        lambda start_date, end_date, adjust_type="hfq": ["2026-05-01", "2026-05-04"],
    )
    monkeypatch.setattr(
        features_module,
        "load_complete_feature_dates",
        lambda start_date, end_date: {"2026-05-01"},
    )
    monkeypatch.setattr(
        features_module,
        "compute_and_store_p0_features",
        lambda trade_date, lookback_bars=120: calls.append((trade_date, lookback_bars)) or 8,
    )

    result = compute_and_store_p0_features_range(
        start_date="2026-05-01",
        end_date="2026-05-04",
        lookback_bars=130,
        skip_complete=True,
    )

    assert list(result["trade_date"]) == ["2026-05-04"]
    assert list(result["feature_rows"]) == [8]
    assert calls == [("2026-05-04", 130)]


def test_compute_and_store_p0_features_range_runs_with_workers(monkeypatch):
    calls = []
    executor_kwargs = []

    class ImmediateExecutor:
        def __init__(self, **kwargs):
            executor_kwargs.append(kwargs)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def submit(self, fn, *args, **kwargs):
            from concurrent.futures import Future

            future = Future()
            future.set_result(fn(*args, **kwargs))
            return future

    monkeypatch.setattr(features_module, "ProcessPoolExecutor", ImmediateExecutor)
    monkeypatch.setattr(
        features_module,
        "load_trade_dates",
        lambda start_date, end_date, adjust_type="hfq": ["2026-05-01", "2026-05-04"],
    )
    monkeypatch.setattr(
        features_module,
        "compute_and_store_p0_features",
        lambda trade_date, lookback_bars=120: calls.append((trade_date, lookback_bars)) or 8,
    )

    result = compute_and_store_p0_features_range(
        start_date="2026-05-01",
        end_date="2026-05-04",
        lookback_bars=130,
        workers=2,
    )

    assert sorted(result["trade_date"]) == ["2026-05-01", "2026-05-04"]
    assert calls == [("2026-05-01", 130), ("2026-05-04", 130)]
    assert executor_kwargs == [{"max_workers": 2, "max_tasks_per_child": 1}]
