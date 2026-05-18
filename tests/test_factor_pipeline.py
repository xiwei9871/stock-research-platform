import pandas as pd
import pytest

from stock_research import factor_config, factor_pipeline


def test_manual_v1_config_contains_directions_weights_and_groups():
    config = factor_config.manual_v1_config()

    assert config["score_version"] == "manual_v1"
    assert config["calc_version"] == "v1"
    assert config["source_data_version"] == "market_daily_bar:hfq"
    assert config["factor_groups"]["ret_20"] == "momentum"
    assert config["factor_groups"]["amount_vs_20d"] == "volume_price"
    assert config["factor_groups"]["volatility_5d"] == "risk"
    assert config["factor_groups"]["high_to_close_drawdown"] == "risk"
    assert config["factor_directions"]["ret_20"] == "higher"
    assert config["factor_directions"]["volatility_20"] == "lower"
    assert config["factor_directions"]["amount_vs_20d"] == "lower"
    assert config["factor_directions"]["volatility_5d"] == "lower"
    assert config["factor_directions"]["high_to_close_drawdown"] == "lower"
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
    assert "row_number() over" not in calls[0][0]
    assert "lookback_dates" in calls[0][0]
    assert "LIMIT %s" in calls[0][0]
    assert calls[0][1] == ["hfq", "2026-05-08", 130, "hfq"]


def test_enrich_bars_with_industry_uses_point_in_time_membership(monkeypatch):
    calls = []

    def fake_fetch_all(conn, sql, params=None):
        calls.append((sql, params))
        return [{"asset_id": "A", "industry_code": "T", "industry_name": "Tech"}]

    monkeypatch.setattr(factor_pipeline, "connect", lambda service: _context(object()))
    monkeypatch.setattr(factor_pipeline, "fetch_all", fake_fetch_all)

    bars = pd.DataFrame({"trade_date": ["2026-05-08"], "asset_id": ["A"], "close": [10.0]})
    result = factor_pipeline.enrich_bars_with_industry(
        bars,
        trade_date="2026-05-08",
        industry_system="csrc",
    )

    assert result.iloc[0]["industry_code"] == "T"
    assert "core.industry_membership" in calls[0][0]
    assert "DISTINCT ON (asset_id)" in calls[0][0]
    assert "ORDER BY asset_id, start_date DESC" in calls[0][0]
    assert calls[0][1] == ["csrc", "2026-05-08", "2026-05-08"]


def test_load_industry_bars_for_factor_date_queries_window(monkeypatch):
    calls = []

    def fake_fetch_all(conn, sql, params=None):
        calls.append((sql, params))
        return [{"trade_date": "2026-05-08", "industry_code": "T", "close": 100.0}]

    monkeypatch.setattr(factor_pipeline, "connect", lambda service: _context(object()))
    monkeypatch.setattr(factor_pipeline, "fetch_all", fake_fetch_all)

    result = factor_pipeline.load_industry_bars_for_factor_date(
        "2026-05-08",
        lookback_bars=130,
        industry_system="csrc",
    )

    assert len(result) == 1
    assert "market.industry_daily_bar" in calls[0][0]
    assert "row_number() over" not in calls[0][0]
    assert "lookback_dates" in calls[0][0]
    assert "LIMIT %s" in calls[0][0]
    assert calls[0][1] == ["csrc", "2026-05-08", 130, "csrc"]


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


def test_compute_technical_factor_rows_matches_reference_latest_values():
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
    factor_groups = {
        "ret_20": "momentum",
        "ret_60": "momentum",
        "momentum_20_5": "momentum",
        "close_above_ma20": "trend",
        "ma20_slope": "trend",
        "trend_r2_20": "trend",
        "amount_ratio_5_20": "volume_price",
        "amount_vs_20d": "volume_price",
        "price_volume_corr_10": "volume_price",
        "volatility_20": "risk",
        "volatility_5d": "risk",
        "max_drawdown_20": "risk",
        "atr_pct": "risk",
        "high_to_close_drawdown": "risk",
        "distance_ma60": "risk",
    }

    rows = factor_pipeline.compute_technical_factor_rows(
        bars,
        trade_date="2026-03-11",
        factor_groups=factor_groups,
        calc_version="v1",
        source_data_version="market_daily_bar:hfq",
    )

    values = rows.set_index("factor_name")["factor_value"].to_dict()
    assert values["ret_20"] == pytest.approx(70 / 50 - 1.0)
    assert values["ret_60"] == pytest.approx(70 / 10 - 1.0)
    assert values["momentum_20_5"] == pytest.approx((70 / 50 - 1.0) - (70 / 65 - 1.0))
    assert values["close_above_ma20"] == 1.0
    assert values["ma20_slope"] == pytest.approx(5.0)
    assert values["trend_r2_20"] == pytest.approx(1.0)
    assert values["amount_ratio_5_20"] > 1.0
    expected_amount_vs_20d = (1000000.0 + 69 * 1000) / pd.Series(
        [1000000.0 + index * 1000 for index in range(50, 70)],
        dtype="float64",
    ).mean()
    assert values["amount_vs_20d"] == pytest.approx(expected_amount_vs_20d)
    assert values["price_volume_corr_10"] == pytest.approx(1.0)
    assert values["volatility_20"] >= 0.0
    assert values["volatility_5d"] >= 0.0
    assert values["max_drawdown_20"] == pytest.approx(0.0)
    assert values["atr_pct"] > 0.0
    assert values["high_to_close_drawdown"] == pytest.approx((71.0 - 70.0) / 71.0)
    assert values["distance_ma60"] > 0.0


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
        "enrich_bars_with_industry",
        lambda bars, **kwargs: bars.assign(industry_code="T", industry_name="Tech"),
    )
    monkeypatch.setattr(
        factor_pipeline,
        "load_industry_bars_for_factor_date",
        lambda *args, **kwargs: pd.DataFrame(),
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


def test_compute_sector_factor_rows_returns_sector_factor_daily_rows():
    dates = pd.date_range("2026-01-01", periods=25, freq="D")
    stock_bars = pd.DataFrame(
        {
            "trade_date": list(dates) * 2,
            "asset_id": ["A"] * 25 + ["B"] * 25,
            "industry_code": ["T"] * 50,
            "close": list(range(10, 35)) + list(range(20, 45)),
            "preclose": [9] + list(range(10, 34)) + [19] + list(range(20, 44)),
            "amount": [100.0] * 50,
        }
    )
    industry_bars = pd.DataFrame(
        {
            "trade_date": dates,
            "industry_code": ["T"] * 25,
            "industry_name": ["Tech"] * 25,
            "close": range(100, 125),
            "preclose": [99] + list(range(100, 124)),
            "amount": [1000.0] * 25,
        }
    )

    result = factor_pipeline.compute_sector_factor_rows(
        stock_bars,
        industry_bars,
        trade_date="2026-01-25",
        factor_groups={"sector_ret_20": "sector", "stock_excess_ret_20": "sector"},
        calc_version="v1",
        source_data_version="market_daily_bar:hfq",
    )

    assert set(result["factor_name"]) == {"sector_ret_20", "stock_excess_ret_20"}
    assert set(result["asset_id"]) == {"A", "B"}


def test_compute_external_factor_rows_preserves_source_labels(monkeypatch):
    bars = pd.DataFrame(
        {
            "trade_date": ["2026-05-08"],
            "asset_id": ["A"],
            "open": [10.0],
            "high": [11.0],
            "low": [9.0],
            "close": [10.5],
            "preclose": [10.0],
            "volume": [1000.0],
            "amount": [100000.0],
        }
    )

    monkeypatch.setattr(
        factor_pipeline.alpha101,
        "compute_alpha101_factors",
        lambda frame: pd.DataFrame(
            {"trade_date": ["2026-05-08"], "asset_id": ["A"], "alpha101_delta_close_1_rank": [0.8]}
        ),
    )
    monkeypatch.setattr(
        factor_pipeline.gtja191,
        "compute_gtja191_factors",
        lambda frame: pd.DataFrame(
            {"trade_date": ["2026-05-08"], "asset_id": ["A"], "gtja191_vp_corr_10": [0.5]}
        ),
    )
    monkeypatch.setattr(
        factor_pipeline.qlib_alpha,
        "compute_qlib_alpha_factors",
        lambda frame: pd.DataFrame(
            {"trade_date": ["2026-05-08"], "asset_id": ["A"], "qlib_klen": [0.05]}
        ),
    )

    rows = factor_pipeline.compute_external_factor_rows(
        bars,
        trade_date="2026-05-08",
        factor_groups={
            "alpha101_delta_close_1_rank": "alpha101",
            "gtja191_vp_corr_10": "gtja191",
            "qlib_klen": "qlib",
        },
        calc_version="v1",
        source_data_version="market_daily_bar:hfq",
    )

    assert set(rows["source"]) == {"alpha101", "gtja191", "qlib"}
    assert set(rows["factor_name"]) == {
        "alpha101_delta_close_1_rank",
        "gtja191_vp_corr_10",
        "qlib_klen",
    }


class _context:
    def __init__(self, value):
        self.value = value

    def __enter__(self):
        return self.value

    def __exit__(self, exc_type, exc, tb):
        return False
