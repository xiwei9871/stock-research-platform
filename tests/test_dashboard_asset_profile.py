from stock_research.dashboard import asset_profile
from stock_research.dashboard import asset_profile_fundamentals
from stock_research.services import finance_ttm, point_in_time_finance
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


def test_build_asset_profile_includes_fundamentals_contract(monkeypatch):
    monkeypatch.setattr(asset_profile, "connect", lambda service: DummyConnection())
    monkeypatch.setattr(asset_profile, "load_daily_bars", lambda *args, **kwargs: [])
    monkeypatch.setattr(asset_profile, "load_asset_detail", lambda *args, **kwargs: None)
    monkeypatch.setattr(asset_profile, "load_asset_score_for_dashboard", lambda *args, **kwargs: None)
    monkeypatch.setattr(asset_profile, "load_asset_watchlist_signals_for_dashboard", lambda *args, **kwargs: [])
    monkeypatch.setattr(asset_profile, "load_asset_decision_history", lambda *args, **kwargs: [])
    monkeypatch.setattr(asset_profile, "load_asset_outcome_history", lambda *args, **kwargs: [])
    monkeypatch.setattr(finance_ttm, "load_income_ttm_rows", lambda *args, **kwargs: pytest.fail("legacy finance_ttm loader should not be used"))
    monkeypatch.setattr(point_in_time_finance, "get_latest_indicator", lambda *args, **kwargs: pytest.fail("legacy PIT indicator helper should not be used"))
    monkeypatch.setattr(point_in_time_finance, "get_latest_cash_flow", lambda *args, **kwargs: pytest.fail("legacy PIT cash-flow helper should not be used"))
    monkeypatch.setattr(point_in_time_finance, "get_latest_income_statement", lambda *args, **kwargs: pytest.fail("legacy PIT income helper should not be used"))

    def fake_fetch_all(conn, sql, params=None):
        normalized_sql = " ".join(sql.split())
        if "FROM core.asset_master" in normalized_sql:
            if "WHERE asset_id = %s LIMIT 1" in normalized_sql:
                return [
                    {
                        "name": "平安银行",
                        "board": "主板",
                        "region": "深圳",
                    }
                ]
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
                    "turnover_rate": 1.5,
                    "total_market_cap": 198328483984.0,
                    "float_market_cap": 198325238674.0,
                    "pe_ttm": 3.41,
                    "pb": 0.43,
                }
            ]
        if "FROM finance.share_capital_event" in normalized_sql:
            return [
                {
                    "asset_id": "CN:SZ:000001",
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
                    "turnover_rate": 1.5,
                    "pct_chg": 1.0945,
                }
            ]
        if "FROM core.industry_membership" in normalized_sql:
            assert params == ["CN:SZ:000001", "2026-06-08", "2026-06-08"]
            return [
                {
                    "industry_name": "银行",
                }
            ]
        if "FROM core.concept_membership" in normalized_sql:
            assert params == ["CN:SZ:000001", "2026-06-08", "2026-06-08"]
            return [
                {"concept_name": "中字头"},
                {"concept_name": "高股息"},
            ]
        if "FROM finance.main_business_composition" in normalized_sql and "report_period = %s" in normalized_sql:
            assert params == ["CN:SZ:000001", "2025-12-31"]
            return [
                {
                    "report_period": "2025-12-31",
                    "classify_type": "按产品",
                    "item_name": "公司银行业务",
                    "revenue": 120000000000.0,
                    "revenue_ratio": 0.52,
                    "gross_margin": 0.42,
                },
                {
                    "report_period": "2025-12-31",
                    "classify_type": "按产品",
                    "item_name": "零售银行业务",
                    "revenue": 80000000000.0,
                    "revenue_ratio": 0.35,
                    "gross_margin": 0.40,
                },
                {
                    "report_period": "2025-12-31",
                    "classify_type": "地区",
                    "item_name": "华南地区",
                    "revenue": 60000000000.0,
                    "revenue_ratio": 0.26,
                    "gross_margin": 0.40,
                },
            ]
        if "SELECT report_period::text AS report_period, announcement_date::text AS announcement_date, revenue, np_parent" in normalized_sql:
            assert params == ["CN:SZ:000001", "2026-06-08"]
            return [
                {
                    "report_period": "2026-03-31",
                    "announcement_date": "2026-08-01",
                    "revenue": 70000000000.0,
                    "np_parent": 12000000000.0,
                },
                {
                    "report_period": "2025-12-31",
                    "announcement_date": "2026-03-20",
                    "revenue": 220000000000.0,
                    "np_parent": 45000000000.0,
                }
            ]
        if "FROM finance.cash_flow" in normalized_sql and "ORDER BY announcement_date DESC, report_period DESC LIMIT 1" in normalized_sql:
            assert params == ["CN:SZ:000001", "2026-06-08"]
            return [
                {
                    "report_period": "2025-12-31",
                    "announcement_date": "2026-03-25",
                    "net_operate_cash_flow": 51000000000.0,
                }
            ]
        if "FROM finance.indicator_quarter" in normalized_sql and "ORDER BY announcement_date DESC, report_period DESC LIMIT 1" in normalized_sql:
            assert params == ["CN:SZ:000001", "2026-06-08"]
            return [
                {
                    "report_period": "2025-09-30",
                    "announcement_date": "2025-10-31",
                    "roe": 0.1234,
                    "gross_margin": 0.418,
                    "debt_ratio": 0.912,
                    "ocf_to_np": 1.13,
                }
            ]
        if "SELECT report_period::text AS report_period, announcement_date::text AS announcement_date FROM finance.income_statement" in normalized_sql:
            assert params == ["CN:SZ:000001", "2026-06-08"]
            return [
                {"report_period": "2026-03-31", "announcement_date": "2026-08-01"},
                {"report_period": "2025-12-31", "announcement_date": "2026-03-20"},
            ]
        if "SELECT report_period::text AS report_period, announcement_date::text AS announcement_date FROM finance.cash_flow" in normalized_sql:
            assert params == ["CN:SZ:000001", "2026-06-08"]
            return [
                {"report_period": "2025-12-31", "announcement_date": "2026-03-25"},
            ]
        if "SELECT report_period::text AS report_period, announcement_date::text AS announcement_date FROM finance.indicator_quarter" in normalized_sql:
            assert params == ["CN:SZ:000001", "2026-06-08"]
            return [
                {"report_period": "2025-09-30", "announcement_date": "2025-10-31"},
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
        "2026-06-30",
        service="test",
    )

    assert profile["company_overview"] == {
        "industry": "银行",
        "concept_tags": ["中字头", "高股息"],
        "business_summary": "主营产品包括公司银行业务、零售银行业务。",
        "profile_summary": "平安银行位于深圳，属于银行行业，上市板为主板。",
        "primary_products": ["公司银行业务", "零售银行业务"],
        "data_status": "available",
        "missing_fields": [],
    }
    assert profile["business_composition"] == {
        "report_period": "2025-12-31",
        "data_status": "available",
        "missing_fields": [],
        "groups": [
            {
                "classify_type": "按产品",
                "items": [
                    {
                        "item_name": "公司银行业务",
                        "revenue": 120000000000.0,
                        "revenue_ratio": 0.52,
                        "gross_margin": 0.42,
                    },
                    {
                        "item_name": "零售银行业务",
                        "revenue": 80000000000.0,
                        "revenue_ratio": 0.35,
                        "gross_margin": 0.40,
                    },
                ],
            },
            {
                "classify_type": "地区",
                "items": [
                    {
                        "item_name": "华南地区",
                        "revenue": 60000000000.0,
                        "revenue_ratio": 0.26,
                        "gross_margin": 0.40,
                    }
                ],
            },
        ],
    }
    assert profile["financial_snapshot"] == {
        "report_period": "2025-09-30",
        "announcement_date": "2025-10-31",
        "revenue_ttm": 220000000000.0,
        "np_parent_ttm": 45000000000.0,
        "operating_cash_flow": 51000000000.0,
        "roe": 0.1234,
        "gross_margin": 0.418,
        "debt_ratio": 0.912,
        "ocf_to_np": 1.13,
        "data_status": "available",
        "missing_fields": [],
    }


def test_build_asset_profile_overview_status_tracks_all_required_fields(monkeypatch):
    monkeypatch.setattr(asset_profile, "connect", lambda service: DummyConnection())
    monkeypatch.setattr(asset_profile, "load_daily_bars", lambda *args, **kwargs: [])
    monkeypatch.setattr(asset_profile, "load_asset_detail", lambda *args, **kwargs: None)
    monkeypatch.setattr(asset_profile, "load_asset_score_for_dashboard", lambda *args, **kwargs: None)
    monkeypatch.setattr(asset_profile, "load_asset_watchlist_signals_for_dashboard", lambda *args, **kwargs: [])
    monkeypatch.setattr(asset_profile, "load_asset_decision_history", lambda *args, **kwargs: [])
    monkeypatch.setattr(asset_profile, "load_asset_outcome_history", lambda *args, **kwargs: [])

    def fake_fetch_all(conn, sql, params=None):
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
                    "turnover_rate": 1.5,
                    "pct_chg": 1.0945,
                }
            ]
        if "FROM staging.eastmoney_stock_spot_snapshot" in normalized_sql:
            return []
        if "FROM finance.share_capital_event" in normalized_sql:
            return []
        if "FROM finance.main_business_composition" in normalized_sql:
            return []
        if "FROM core.industry_membership" in normalized_sql:
            return []
        if "FROM core.concept_membership" in normalized_sql:
            return []
        if "FROM factor.factor_daily" in normalized_sql and "factor_name IN" in normalized_sql:
            return []
        if "FROM finance.income_statement" in normalized_sql and "announcement_date <=" in normalized_sql:
            return []
        if "FROM finance.cash_flow" in normalized_sql and "announcement_date <=" in normalized_sql:
            return []
        if "FROM finance.indicator_quarter" in normalized_sql and "announcement_date <=" in normalized_sql:
            return []
        if "min(trade_date)" in normalized_sql:
            return [{"min_date": "2026-06-01", "max_date": "2026-06-08", "row_count": 1}]
        if "max(trade_date)" in normalized_sql and "factor.factor_daily" in normalized_sql:
            return [{"latest_factor_date": None, "factor_count": 0}]
        return []

    monkeypatch.setattr(asset_profile, "fetch_all", fake_fetch_all)

    profile = asset_profile.build_asset_profile(
        "000001.SZ",
        "2026-06-08",
        "2026-06-01",
        "2026-06-30",
        service="test",
    )

    assert profile["company_overview"]["profile_summary"] == "平安银行位于深圳，上市板为主板。"
    assert profile["company_overview"]["data_status"] == "partial"
    assert profile["company_overview"]["missing_fields"] == [
        "industry",
        "concept_tags",
        "business_summary",
        "primary_products",
    ]
