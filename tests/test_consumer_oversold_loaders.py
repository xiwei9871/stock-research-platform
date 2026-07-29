from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime

import pandas as pd
import pytest

from stock_research.consumer_oversold import loaders


@contextmanager
def _connection(service_calls: list[str]):
    service_calls.append("opened")
    yield object()


def _install_db(monkeypatch, responses):
    calls: list[tuple[str, list[object]]] = []
    services: list[str] = []
    iterator = iter(responses)

    @contextmanager
    def fake_connect(service):
        services.append(service)
        yield object()

    def fake_fetch_all(conn, sql, params=None):
        calls.append((" ".join(sql.split()), list(params or [])))
        return next(iterator)

    monkeypatch.setattr(loaders, "connect", fake_connect)
    monkeypatch.setattr(loaders, "fetch_all", fake_fetch_all)
    return calls, services


def test_universe_loads_four_stable_frames_and_point_in_time_sql(monkeypatch):
    calls, services = _install_db(
        monkeypatch,
        [
            [{"asset_id": "B", "stock_code": "000002", "name": "B", "list_date": date(2020, 1, 2)}],
            [{"asset_id": "B", "is_st": False, "is_delisting_risk": False, "is_suspended": True}],
            [{"asset_id": "B", "avg_turnover_amount": 42}],
            [
                {"asset_id": "B", "industry_system": "sw", "industry_name": "食品"},
                {"asset_id": "B", "industry_system": "citics", "industry_name": "消费"},
            ],
        ],
    )

    result = loaders.load_consumer_universe_frames("2026-07-29", service="research-test")

    assert services == ["research-test"]
    assert list(result) == ["assets", "statuses", "liquidity", "industries"]
    assert result["assets"].columns.tolist() == ["asset_id", "stock_code", "name", "list_date"]
    assert result["statuses"].columns.tolist() == ["asset_id", "is_st", "is_delisting_risk", "is_suspended"]
    assert result["liquidity"].columns.tolist() == ["asset_id", "avg_turnover_amount"]
    assert result["industries"].columns.tolist() == ["asset_id", "industry_system", "industry_name"]
    assert result["assets"].iloc[0]["list_date"] == "2020-01-02"
    assert not bool(result["statuses"].iloc[0]["is_delisting_risk"])
    assert "FROM core.asset_master" in calls[0][0]
    assert "core.asset_status_daily" in calls[1][0]
    assert "COALESCE" in calls[1][0] and "TRUE" in calls[1][0]
    assert "NOT a.is_active" not in calls[1][0]
    assert "a.delist_date IS NOT NULL AND a.delist_date <= %s" in calls[1][0]
    assert "LIMIT 20" in calls[2][0]
    assert "adjust_type = 'hfq'" in calls[2][0]
    assert "start_date <= %s" in calls[3][0]
    assert "%s < end_date" in calls[3][0]
    assert "PARTITION BY asset_id, industry_system" in calls[3][0]
    assert all("2026-07-29" in params for _, params in calls)


def test_universe_empty_database_results_have_stable_schema(monkeypatch):
    _install_db(monkeypatch, [[], [], [], []])
    result = loaders.load_consumer_universe_frames("2026-07-29", service="test")
    assert {key: frame.columns.tolist() for key, frame in result.items()} == {
        "assets": ["asset_id", "stock_code", "name", "list_date"],
        "statuses": ["asset_id", "is_st", "is_delisting_risk", "is_suspended"],
        "liquidity": ["asset_id", "avg_turnover_amount"],
        "industries": ["asset_id", "industry_system", "industry_name"],
    }


def test_market_requests_260_hfq_dates_and_sorts(monkeypatch):
    calls, _ = _install_db(
        monkeypatch,
        [[
            {"asset_id": "B", "trade_date": date(2026, 7, 29), "close": 2},
            {"asset_id": "A", "trade_date": date(2026, 7, 28), "close": 1},
        ]],
    )
    result = loaders.load_consumer_market_history("2026-07-29", service="test")
    assert result.to_dict("records") == [
        {"asset_id": "A", "trade_date": "2026-07-28", "close": 1},
        {"asset_id": "B", "trade_date": "2026-07-29", "close": 2},
    ]
    sql, params = calls[0]
    assert "SELECT DISTINCT trade_date" in sql
    assert "trade_date <= %s" in sql
    assert "LIMIT %s" in sql
    assert "adjust_type = 'hfq'" in sql
    assert params == ["2026-07-29", 260]


def test_asset_scoped_empty_lists_do_not_open_database(monkeypatch):
    def fail_connect(service):
        raise AssertionError("database must not be queried")

    monkeypatch.setattr(loaders, "connect", fail_connect)
    assert loaders.load_consumer_finance_history([], "2026-07-29", service="x").columns.tolist() == list(loaders.FINANCE_COLUMNS)
    assert loaders.load_consumer_valuation_history([], "2026-07-29", service="x").columns.tolist() == list(loaders.VALUATION_COLUMNS)
    assert loaders.load_consumer_earnings_forecasts([], "2026-07-29", service="x").columns.tolist() == list(loaders.EARNINGS_COLUMNS)


def test_finance_queries_all_sources_with_cutoff_and_computes_pit_ttm(monkeypatch):
    income = [
        {"asset_id": "A", "report_period": "2023-03-31", "announcement_date": "2023-04-20", "revenue": 20, "np_parent": 2, "source": "s"},
        {"asset_id": "A", "report_period": "2023-12-31", "announcement_date": "2024-03-20", "revenue": 100, "np_parent": 10, "source": "s"},
        {"asset_id": "A", "report_period": "2024-03-31", "announcement_date": "2024-04-20", "revenue": 30, "np_parent": 3, "source": "s"},
        {"asset_id": "A", "report_period": "2024-03-31", "announcement_date": "2024-06-01", "revenue": 35, "np_parent": 4, "source": "revision"},
        {"asset_id": "A", "report_period": "2024-12-31", "announcement_date": "2025-03-20", "revenue": 150, "np_parent": 15, "source": "s"},
    ]
    indicators = [
        {"asset_id": "A", "report_period": "2024-03-31", "announcement_date": "2024-04-25", "revenue_yoy": .1, "np_yoy": .2, "gross_margin": .3, "net_margin": .1, "roe": .08, "ocf_to_np": 1.2, "debt_ratio": .4, "source": "s", "calc_version": "v1"},
    ]
    balances = [
        {"asset_id": "A", "report_period": "2024-03-31", "announcement_date": "2024-04-22", "total_equity": 50, "source": "s"},
    ]
    cash = [
        {"asset_id": "A", "report_period": "2023-03-31", "announcement_date": "2023-04-20", "net_operate_cash_flow": 1, "source": "s"},
        {"asset_id": "A", "report_period": "2023-12-31", "announcement_date": "2024-03-20", "net_operate_cash_flow": 8, "source": "s"},
        {"asset_id": "A", "report_period": "2024-03-31", "announcement_date": "2024-04-23", "net_operate_cash_flow": 2, "source": "s"},
    ]
    calls, _ = _install_db(monkeypatch, [income, indicators, balances, cash])

    result = loaders.load_consumer_finance_history([" A "], "2025-04-01", service="test")
    march = result.loc[result["report_period"].eq("2024-03-31")].iloc[0]
    assert march["announcement_date"] == "2024-06-01"
    assert march["revenue_ttm"] == pytest.approx(115)
    assert march["np_parent_ttm"] == pytest.approx(12)
    assert march["operating_cash_flow"] == pytest.approx(9)
    assert march["equity_parent"] == 50
    assert march["revenue_growth"] == .1
    annual = result.loc[result["report_period"].eq("2024-12-31")].iloc[0]
    assert annual["revenue_ttm"] == 150
    assert annual["np_parent_ttm"] == 15
    for sql, params in calls:
        assert "announcement_date <= %s" in sql
        assert "asset_id = ANY(%s)" in sql
        assert params == [["A"], "2025-04-01"]


def test_finance_does_not_use_revision_announced_after_period_asof(monkeypatch):
    income = [
        {"asset_id": "A", "report_period": "2023-03-31", "announcement_date": "2023-04-20", "revenue": 20, "np_parent": 2, "source": "s"},
        {"asset_id": "A", "report_period": "2023-12-31", "announcement_date": "2024-03-20", "revenue": 100, "np_parent": 10, "source": "s"},
        {"asset_id": "A", "report_period": "2024-03-31", "announcement_date": "2024-04-20", "revenue": 30, "np_parent": 3, "source": "s"},
        {"asset_id": "A", "report_period": "2024-03-31", "announcement_date": "2024-06-01", "revenue": 300, "np_parent": 30, "source": "late"},
    ]
    _install_db(monkeypatch, [income, [], [], []])
    result = loaders.load_consumer_finance_history(["A"], "2024-05-01", service="test")
    early = result.loc[result["announcement_date"].eq("2024-04-20")].iloc[0]
    assert early["revenue_ttm"] == 110


def test_finance_does_not_label_prior_period_ttm_as_a_later_report_period(monkeypatch):
    income = [{
        "asset_id": "A", "report_period": "2023-12-31", "announcement_date": "2024-03-20",
        "revenue": 100, "np_parent": 10, "source": "s",
    }]
    indicators = [{
        "asset_id": "A", "report_period": "2024-06-30", "announcement_date": "2024-08-20",
        "revenue_yoy": .1, "source": "s", "calc_version": "v1",
    }]
    _install_db(monkeypatch, [income, indicators, [], []])
    result = loaders.load_consumer_finance_history(["A"], "2024-09-01", service="test")
    june = result.loc[result["report_period"].eq("2024-06-30")].iloc[0]
    assert pd.isna(june["revenue_ttm"])
    assert pd.isna(june["np_parent_ttm"])


def test_valuation_enforces_pit_deduplicates_versions_and_pivots(monkeypatch):
    rows = [
        {"asset_id": "A", "trade_date": date(2026, 7, 28), "factor_name": "pe_ttm", "factor_value": 12, "computed_at": datetime(2026, 7, 29, 9), "calc_version": "v2", "industry_system": "sw", "industry_name": "食品"},
        {"asset_id": "A", "trade_date": date(2026, 7, 28), "factor_name": "pe_ttm", "factor_value": 99, "computed_at": datetime(2026, 7, 28, 9), "calc_version": "v9", "industry_system": "sw", "industry_name": "食品"},
        {"asset_id": "A", "trade_date": date(2026, 7, 28), "factor_name": "ps_ttm", "factor_value": 2, "computed_at": datetime(2026, 7, 29, 9), "calc_version": "v1", "industry_system": "sw", "industry_name": "食品"},
    ]
    calls, _ = _install_db(monkeypatch, [rows])
    result = loaders.load_consumer_valuation_history(["A"], "2026-07-29", service="test")
    assert result.to_dict("records") == [{
        "asset_id": "A", "valuation_date": "2026-07-28", "pe_ttm": 12,
        "ps_ttm": 2, "ev_ebitda": None, "industry_system": "sw", "industry_name": "食品",
    }]
    sql, params = calls[0]
    assert "factor_name IN ('pe_ttm', 'ps_ttm', 'ev_ebitda')" in sql
    assert "trade_date <= %s" in sql
    assert "INTERVAL '5 years'" in sql
    assert "core.industry_membership" in sql
    assert "computed_at::date <= %s" in sql
    assert params == [["A"], "2026-07-29", "2026-07-29", "2026-07-29"]


def test_valuation_ignores_factor_revision_computed_after_cutoff(monkeypatch):
    rows = [
        {
            "asset_id": "A", "trade_date": "2026-07-28", "factor_name": "pe_ttm",
            "factor_value": 99, "computed_at": "2026-07-30T00:30:00+08:00",
            "calc_version": "future", "industry_system": "sw", "industry_name": "食品",
        },
        {
            "asset_id": "A", "trade_date": "2026-07-28", "factor_name": "pe_ttm",
            "factor_value": 12, "computed_at": "2026-07-29T09:00:00+08:00",
            "calc_version": "visible", "industry_system": "sw", "industry_name": "食品",
        },
    ]
    _install_db(monkeypatch, [rows])
    result = loaders.load_consumer_valuation_history(["A"], "2026-07-29", service="test")
    assert result.iloc[0]["pe_ttm"] == 12


def test_valuation_keeps_factor_rows_when_industry_and_version_metadata_are_missing(monkeypatch):
    _install_db(monkeypatch, [[{
        "asset_id": "A", "trade_date": "2026-07-28", "factor_name": "pe_ttm", "factor_value": 12,
    }]])
    result = loaders.load_consumer_valuation_history(["A"], "2026-07-29", service="test")
    assert len(result) == 1
    assert result.iloc[0]["pe_ttm"] == 12
    assert pd.isna(result.iloc[0]["industry_system"])


def test_earnings_unifies_forecast_and_express(monkeypatch):
    forecasts = [{
        "asset_id": "A", "announcement_date": date(2026, 1, 2), "report_period": date(2025, 12, 31),
        "forecast_type": "预增", "forecast_np_min": 1, "forecast_np_max": 2,
        "forecast_np_change_min": 10, "forecast_np_change_max": 20, "summary": "up",
        "source": "eastmoney", "source_endpoint": "f",
    }]
    express = [{
        "asset_id": "A", "announcement_date": date(2026, 2, 2), "report_period": date(2025, 12, 31),
        "revenue": 100, "revenue_yoy": 5, "np_parent": 10, "np_parent_yoy": 8,
        "source": "eastmoney", "source_endpoint": "e",
    }]
    calls, _ = _install_db(monkeypatch, [forecasts, express])
    result = loaders.load_consumer_earnings_forecasts([" A "], "2026-07-29", service="test")
    assert result["event_type"].tolist() == ["forecast", "express"]
    assert result["announcement_date"].tolist() == ["2026-01-02", "2026-02-02"]
    assert result.iloc[1]["np_yoy"] == 8
    assert pd.isna(result.iloc[0]["revenue"])
    assert all("announcement_date <= %s" in sql for sql, _ in calls)
    assert all(params == [["A"], "2026-07-29"] for _, params in calls)


@pytest.mark.parametrize("value", ["2026-02-30", "2026-7-29", " 2026-07-29", "not-a-date"])
def test_all_loaders_reject_non_real_or_non_strict_dates(value):
    with pytest.raises(ValueError, match="trade_date"):
        loaders.load_consumer_market_history(value, service="test")


@pytest.mark.parametrize("asset_ids", [[""], ["   "], ["A", " A "], [1], [None]])
def test_asset_scoped_loaders_reject_invalid_or_duplicate_asset_ids(asset_ids):
    with pytest.raises(ValueError, match="asset_ids"):
        loaders.load_consumer_finance_history(asset_ids, "2026-07-29", service="test")
