import pandas as pd
import pytest

from stock_research import intraday_features


def test_build_stock_intraday_features_daily_from_5min_bars():
    bars = pd.DataFrame(
        [
            {
                "trade_date": "2026-06-05",
                "asset_id": "CN:SH:600001",
                "ts_code": "600001.SH",
                "trade_time": "2026-06-05 09:35:00",
                "open": 10.0,
                "high": 10.2,
                "low": 9.9,
                "close": 10.1,
                "volume": 100,
                "amount": 1010.0,
            },
            {
                "trade_date": "2026-06-05",
                "asset_id": "CN:SH:600001",
                "ts_code": "600001.SH",
                "trade_time": "2026-06-05 10:00:00",
                "open": 10.1,
                "high": 10.4,
                "low": 10.0,
                "close": 10.3,
                "volume": 120,
                "amount": 1236.0,
            },
            {
                "trade_date": "2026-06-05",
                "asset_id": "CN:SH:600001",
                "ts_code": "600001.SH",
                "trade_time": "2026-06-05 14:35:00",
                "open": 10.3,
                "high": 10.5,
                "low": 10.2,
                "close": 10.4,
                "volume": 150,
                "amount": 1560.0,
            },
            {
                "trade_date": "2026-06-05",
                "asset_id": "CN:SH:600001",
                "ts_code": "600001.SH",
                "trade_time": "2026-06-05 15:00:00",
                "open": 10.4,
                "high": 10.6,
                "low": 10.3,
                "close": 10.5,
                "volume": 200,
                "amount": 2100.0,
            },
        ]
    )

    result = intraday_features.build_stock_intraday_features_daily(
        bars,
        trade_date="2026-06-05",
        freq="5min",
        adjust_type="raw",
    )

    values = result.set_index("feature_name")["feature_value"].to_dict()
    assert values["intraday_return"] == pytest.approx(0.05)
    assert values["last_30m_return"] == pytest.approx(10.5 / 10.3 - 1.0)
    assert values["close_position_in_day"] == pytest.approx((10.5 - 9.9) / (10.6 - 9.9))
    assert values["amount_tail_1h_ratio"] == pytest.approx((1560.0 + 2100.0) / (
        1010.0 + 1236.0 + 1560.0 + 2100.0
    ))
    assert set(result["calc_version"]) == {"intraday_v1"}
    assert set(result["source_data_version"]) == {"stock_minute_bar:5min:raw"}


def test_build_industry_intraday_features_daily_aggregates_stock_features():
    stock_features = pd.DataFrame(
        [
            _stock_feature("A", "intraday_return", 0.03),
            _stock_feature("B", "intraday_return", -0.01),
            _stock_feature("A", "last_30m_return", 0.02),
            _stock_feature("B", "last_30m_return", 0.01),
            _stock_feature("A", "intraday_volatility_5min", 0.04),
            _stock_feature("B", "intraday_volatility_5min", 0.02),
        ]
    )
    memberships = pd.DataFrame(
        [
            {
                "asset_id": "A",
                "industry_code": "I1",
                "industry_name": "Industry 1",
            },
            {
                "asset_id": "B",
                "industry_code": "I1",
                "industry_name": "Industry 1",
            },
        ]
    )

    result = intraday_features.build_industry_intraday_features_daily(
        stock_features,
        memberships,
        trade_date="2026-06-05",
        industry_system="csrc",
        freq="5min",
        adjust_type="raw",
    )

    values = result.set_index("feature_name")["feature_value"].to_dict()
    assert values["industry_intraday_return_median"] == pytest.approx(0.01)
    assert values["industry_up_ratio"] == pytest.approx(0.5)
    assert values["industry_tail_strength_median"] == pytest.approx(0.015)
    assert values["industry_intraday_volatility_median"] == pytest.approx(0.03)


def test_run_intraday_feature_gap_check_reports_missing_dates(monkeypatch):
    class _Context:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_fetch_all(conn, sql, params):
        if "FROM market.stock_minute_bar" in sql:
            return [
                {"trade_date": "2026-06-04", "asset_id": "A"},
                {"trade_date": "2026-06-05", "asset_id": "A"},
            ]
        if "FROM factor.stock_intraday_features_daily" in sql:
            return [{"trade_date": "2026-06-05", "asset_id": "A"}]
        if "FROM factor.industry_intraday_features_daily" in sql:
            return []
        raise AssertionError(sql)

    monkeypatch.setattr(intraday_features, "connect", lambda service: _Context())
    monkeypatch.setattr(intraday_features, "fetch_all", fake_fetch_all)

    result = intraday_features.run_intraday_feature_gap_check(
        start_date="2026-06-04",
        end_date="2026-06-05",
        freq="5min",
        adjust_type="raw",
    )

    rows = {row["trade_date"]: row for row in result["dates"]}
    assert rows["2026-06-04"]["stock_missing"] == 1
    assert rows["2026-06-05"]["stock_missing"] == 0
    assert result["summary"]["dates_with_stock_gaps"] == 1


def _stock_feature(asset_id: str, feature_name: str, value: float) -> dict:
    return {
        "trade_date": "2026-06-05",
        "asset_id": asset_id,
        "freq": "5min",
        "adjust_type": "raw",
        "feature_name": feature_name,
        "feature_value": value,
        "calc_version": "intraday_v1",
        "source": "intraday_features",
        "source_data_version": "stock_minute_bar:5min:raw",
    }
