import pandas as pd

from stock_research import factor_config, factor_pipeline


def test_manual_v1_config_contains_directions_weights_and_groups():
    config = factor_config.manual_v1_config()

    assert config["score_version"] == "manual_v1"
    assert config["calc_version"] == "v1"
    assert config["source_data_version"] == "market_daily_bar:hfq"
    assert config["factor_groups"]["ret_20"] == "momentum"
    assert config["factor_directions"]["ret_20"] == "higher"
    assert config["factor_directions"]["volatility_20"] == "lower"
    assert config["weights"]["ret_20_score"] > 0
    assert config["weights"]["volatility_20_score"] > 0


def test_load_market_bars_for_factor_date_queries_lookback_window(monkeypatch):
    calls = []

    def fake_fetch_all(conn, sql, params=None):
        calls.append((sql, params))
        return [
            {
                "trade_date": "2026-05-08",
                "asset_id": "CN:SH:600001",
                "open": 10.0,
                "high": 11.0,
                "low": 9.5,
                "close": 10.5,
                "preclose": 10.0,
                "volume": 1000.0,
                "amount": 1000000.0,
                "turnover_rate": 1.0,
                "trade_status": "1",
                "is_st": False,
            }
        ]

    monkeypatch.setattr(factor_pipeline, "connect", lambda service: _context(object()))
    monkeypatch.setattr(factor_pipeline, "fetch_all", fake_fetch_all)

    bars = factor_pipeline.load_market_bars_for_factor_date(
        "2026-05-08",
        lookback_bars=130,
    )

    assert len(bars) == 1
    assert bars.iloc[0]["asset_id"] == "CN:SH:600001"
    assert "row_number() over" in calls[0][0]
    assert calls[0][1] == ["2026-05-08", "hfq", 130]


def test_compute_technical_factor_rows_returns_long_factor_daily_rows():
    dates = pd.date_range("2026-01-01", periods=70, freq="D")
    bars = pd.DataFrame(
        {
            "trade_date": list(dates) * 2,
            "asset_id": ["A"] * 70 + ["B"] * 70,
            "open": list(range(1, 71)) + list(range(2, 72)),
            "high": list(range(2, 72)) + list(range(3, 73)),
            "low": list(range(1, 71)) + list(range(2, 72)),
            "close": list(range(1, 71)) + list(range(2, 72)),
            "preclose": [None] + list(range(1, 70)) + [None] + list(range(2, 71)),
            "volume": [1000.0 + index for index in range(70)] * 2,
            "amount": [1000000.0 + index * 1000 for index in range(70)] * 2,
            "turnover_rate": [1.0 + index / 100 for index in range(70)] * 2,
            "trade_status": ["1"] * 140,
            "is_st": [False] * 140,
        }
    )

    rows = factor_pipeline.compute_technical_factor_rows(
        bars,
        trade_date="2026-03-11",
        factor_groups={"ret_20": "momentum", "volatility_20": "risk"},
        calc_version="v1",
        source_data_version="market_daily_bar:hfq",
    )

    assert len(rows) == 4
    assert set(zip(rows["asset_id"], rows["factor_name"], strict=True)) == {
        ("A", "ret_20"),
        ("A", "volatility_20"),
        ("B", "ret_20"),
        ("B", "volatility_20"),
    }
    assert set(rows["trade_date"]) == {"2026-03-11"}
    assert set(rows["factor_group"]) == {"momentum", "risk"}
    assert set(rows["calc_version"]) == {"v1"}
    assert set(rows["source"]) == {"custom"}
    assert set(rows["source_data_version"]) == {"market_daily_bar:hfq"}
    assert not rows["factor_value"].isna().any()


def test_compute_technical_factor_rows_strict_mode_raises_for_missing_factor():
    dates = pd.date_range("2026-01-01", periods=70, freq="D")
    bars = pd.DataFrame(
        {
            "trade_date": dates,
            "asset_id": ["A"] * 70,
            "open": range(1, 71),
            "high": range(2, 72),
            "low": range(1, 71),
            "close": range(1, 71),
            "preclose": [None] + list(range(1, 70)),
            "volume": [1000.0 + index for index in range(70)],
            "amount": [1000000.0 + index * 1000 for index in range(70)],
            "turnover_rate": [1.0 + index / 100 for index in range(70)],
            "trade_status": ["1"] * 70,
            "is_st": [False] * 70,
        }
    )

    try:
        factor_pipeline.compute_technical_factor_rows(
            bars,
            trade_date="2026-03-11",
            factor_groups={"sector_ret_20": "sector"},
            calc_version="v1",
            source_data_version="market_daily_bar:hfq",
        )
    except ValueError as exc:
        assert "sector_ret_20" in str(exc)
    else:
        raise AssertionError("Expected missing configured technical factor to raise")


def test_build_and_store_factor_daily_loads_computes_and_upserts(monkeypatch):
    calls = []
    dates = pd.date_range("2026-01-01", periods=70, freq="D")
    bars = pd.DataFrame(
        {
            "trade_date": dates,
            "asset_id": ["A"] * 70,
            "open": range(1, 71),
            "high": range(2, 72),
            "low": range(1, 71),
            "close": range(1, 71),
            "preclose": [None] + list(range(1, 70)),
            "volume": [1000.0 + index for index in range(70)],
            "amount": [1000000.0 + index * 1000 for index in range(70)],
            "turnover_rate": [1.0 + index / 100 for index in range(70)],
            "trade_status": ["1"] * 70,
            "is_st": [False] * 70,
        }
    )

    monkeypatch.setattr(
        factor_pipeline,
        "load_market_bars_for_factor_date",
        lambda *args, **kwargs: bars,
    )
    monkeypatch.setattr(
        factor_pipeline,
        "upsert_factor_daily",
        lambda rows: calls.append(rows) or len(rows),
        raising=False,
    )

    count = factor_pipeline.build_and_store_factor_daily(
        "2026-03-11",
        lookback_bars=130,
    )

    assert count > 0
    assert calls[0]["trade_date"].nunique() == 1


class _context:
    def __init__(self, value):
        self.value = value

    def __enter__(self):
        return self.value

    def __exit__(self, exc_type, exc, tb):
        return False
