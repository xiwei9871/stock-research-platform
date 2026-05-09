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


class _context:
    def __init__(self, value):
        self.value = value

    def __enter__(self):
        return self.value

    def __exit__(self, exc_type, exc, tb):
        return False
