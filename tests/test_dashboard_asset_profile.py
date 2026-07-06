from stock_research.dashboard import asset_profile
import pytest


class DummyConnection:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_build_asset_profile_includes_quote_and_company_snapshots(monkeypatch):
    monkeypatch.setattr(asset_profile, "connect", lambda service: DummyConnection())
    monkeypatch.setattr(asset_profile, "load_daily_bars", lambda *args, **kwargs: [])
    monkeypatch.setattr(asset_profile, "load_asset_detail", lambda *args, **kwargs: None)
    monkeypatch.setattr(asset_profile, "load_asset_score_for_dashboard", lambda *args, **kwargs: None)
    monkeypatch.setattr(asset_profile, "load_asset_watchlist_signals_for_dashboard", lambda *args, **kwargs: [])
    monkeypatch.setattr(asset_profile, "load_asset_decision_history", lambda *args, **kwargs: [])
    monkeypatch.setattr(asset_profile, "load_asset_outcome_history", lambda *args, **kwargs: [])

    def fake_fetch_all(conn, sql, params):
      normalized_sql = " ".join(sql.split())
      if "FROM core.asset_master" in normalized_sql:
          return [
              {
                  "asset_id": "CN:SZ:000001",
                  "ts_code": "000001.SZ",
                  "symbol": "000001",
                  "name": "平安银行",
                  "exchange": "SZ",
                  "board": "主板",
                  "list_date": "1991-04-03",
                  "is_active": True,
                  "is_beijing": False,
                  "is_star": False,
                  "is_chinext": False,
                  "region": "深圳",
                  "source": "test",
              }
          ]
      if "FROM staging.eastmoney_stock_spot_snapshot" in normalized_sql:
          return [
              {
                  "trade_date": "2026-06-29",
                  "volume_ratio": 1.24,
                  "turnover_rate": 0,
                  "total_market_cap": 198328483984.0,
                  "float_market_cap": 198325238674.0,
                  "pe_ttm": 3.41,
                  "pb": 0.43,
              }
          ]
      if "FROM finance.share_capital_event" in normalized_sql:
          return [
              {
                  "total_share": 19405918198,
                  "float_share": 19405600653,
                  "event_date": "2025-12-31",
              }
          ]
      if "FROM factor.factor_daily" in normalized_sql and "factor_name IN" in normalized_sql:
          return [{"factor_name": "pb", "factor_value": 0.44}]
      if "ORDER BY trade_date DESC LIMIT 20" in normalized_sql:
          return [
              {
                  "trade_date": "2026-06-08",
                  "open": 10.05,
                  "high": 10.18,
                  "low": 9.99,
                  "close": 10.16,
                  "preclose": 10.05,
                  "volume": 906889.82,
                  "amount": 915838.54912,
                  "turnover_rate": None,
                  "pct_chg": 1.0945,
              },
              {"trade_date": "2026-06-05", "close": 10.2, "volume": 1000000, "amount": 1000000000},
              {"trade_date": "2026-06-04", "close": 10.0, "volume": 900000, "amount": 900000000},
          ]
      if "min(trade_date)" in normalized_sql:
          return [{"min_date": "2026-06-01", "max_date": "2026-06-08", "row_count": 5}]
      if "max(trade_date)" in normalized_sql and "factor.factor_daily" in normalized_sql:
          return [{"latest_factor_date": None, "factor_count": 0}]
      return []

    monkeypatch.setattr(asset_profile, "fetch_all", fake_fetch_all)

    profile = asset_profile.build_asset_profile(
        "000001.SZ",
        "2026-06-08",
        "2026-06-01",
        "2026-06-08",
        service="test",
    )

    assert profile["quote_snapshot"]["trade_date"] == "2026-06-08"
    assert profile["quote_snapshot"]["close"] == 10.16
    assert profile["quote_snapshot"]["preclose"] == 10.05
    assert profile["quote_snapshot"]["amount"] == pytest.approx(915838549.12)
    assert profile["quote_snapshot"]["turnover_rate"] == pytest.approx(906889.82 * 100 / 19405600653 * 100)
    assert profile["quote_snapshot"]["pct_chg"] == 1.0945
    assert profile["quote_snapshot"]["amount_ratio_20d"] == pytest.approx(
        915838549.12 / ((915838549.12 + 1000000000 + 900000000) / 3)
    )
    assert profile["quote_snapshot"]["data_status"] == "available"
    assert profile["quote_snapshot"]["missing_fields"] == []

    assert profile["company_profile"]["name"] == "平安银行"
    assert profile["company_profile"]["board"] == "主板"
    assert profile["company_profile"]["list_date"] == "1991-04-03"
    assert profile["company_profile"]["region"] == "深圳"

    assert profile["valuation_snapshot"]["total_market_cap"] == pytest.approx(10.16 * 19405918198)
    assert profile["valuation_snapshot"]["float_market_cap"] == pytest.approx(10.16 * 19405600653)
    assert profile["valuation_snapshot"]["pe_ttm"] == 3.41
    assert profile["valuation_snapshot"]["pb"] == 0.43
    assert profile["valuation_snapshot"]["volume_ratio"] == 1.24
    assert profile["valuation_snapshot"]["data_status"] == "available"
    assert profile["valuation_snapshot"]["missing_fields"] == []
