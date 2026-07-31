from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal

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


@pytest.mark.parametrize(
    ("amount", "source", "expected"),
    [
        (Decimal("691266.56"), "tushare", Decimal("691266560.00")),
        (691_266.56, "derived:tushare_raw_latest_factor", 691_266_560.0),
        (691_266.56, "TuShare", 691_266_560.0),
        (691_266_560.0, "baostock", 691_266_560.0),
        (691_266_560.0, "akshare", 691_266_560.0),
        (691_266_560.0, "eastmoney", 691_266_560.0),
        (691_266_560.0, None, 691_266_560.0),
    ],
)
def test_normalize_market_amount_is_source_aware(amount, source, expected):
    assert loaders.normalize_market_amount(amount, source) == expected


@pytest.mark.parametrize(
    "amount", [None, pd.NA, float("nan"), float("inf"), True, "691266.56"]
)
def test_normalize_market_amount_rejects_missing_or_invalid_amount(amount):
    with pytest.raises(ValueError, match="amount"):
        loaders.normalize_market_amount(amount, "tushare")


@pytest.mark.parametrize("source", [123, True, [], {}])
def test_normalize_market_amount_rejects_invalid_source(source):
    with pytest.raises(ValueError, match="source"):
        loaders.normalize_market_amount(691_266.56, source)


def _resolver_row(
    trade_date,
    *,
    expected,
    raw,
    hfq,
    paired,
    is_open=True,
):
    return {
        "trade_date": trade_date,
        "is_open": is_open,
        "expected_asset_count": expected,
        "raw_asset_count": raw,
        "hfq_asset_count": hfq,
        "paired_asset_count": paired,
    }


def test_resolver_uses_expanding_point_in_time_universe_denominator(monkeypatch):
    calls, services = _install_db(
        monkeypatch,
        [[
            _resolver_row(date(2026, 7, 30), expected=101, raw=99, hfq=99, paired=99),
            _resolver_row(date(2026, 7, 29), expected=100, raw=100, hfq=100, paired=100),
        ]],
    )

    assert loaders.resolve_latest_complete_consumer_trade_date(
        service="research-test"
    ) == "2026-07-29"
    assert services == ["research-test"]
    sql, params = calls[0]
    assert "FROM market.trading_calendar" in sql
    assert "JOIN core.asset_master" in sql
    assert "a.list_date <= d.trade_date" in sql
    assert "a.delist_date IS NULL OR a.delist_date >= d.trade_date" in sql
    assert "s.is_suspended IS DISTINCT FROM TRUE" in sql
    assert "COUNT(p.asset_id) AS expected_asset_count" in sql
    assert "p.has_raw AND p.has_hfq" in sql
    assert params == [20]


def test_resolver_accepts_smaller_expected_set_from_suspension(monkeypatch):
    _install_db(
        monkeypatch,
        [[
            _resolver_row(date(2026, 7, 30), expected=99, raw=99, hfq=99, paired=99),
            _resolver_row(date(2026, 7, 29), expected=100, raw=100, hfq=100, paired=100),
        ]],
    )
    assert loaders.resolve_latest_complete_consumer_trade_date(service="test") == "2026-07-30"


def test_resolver_expected_set_excludes_delisted_assets(monkeypatch):
    calls, _ = _install_db(
        monkeypatch,
        [[_resolver_row(date(2026, 7, 30), expected=98, raw=98, hfq=98, paired=98)]],
    )
    assert loaders.resolve_latest_complete_consumer_trade_date(service="test") == "2026-07-30"
    assert "a.delist_date IS NULL OR a.delist_date >= d.trade_date" in calls[0][0]


def test_resolver_rejects_disjoint_raw_and_hfq_asset_coverage(monkeypatch):
    _install_db(
        monkeypatch,
        [[
            _resolver_row(date(2026, 7, 30), expected=100, raw=99, hfq=99, paired=98),
            _resolver_row(date(2026, 7, 29), expected=100, raw=100, hfq=100, paired=100),
        ]],
    )
    assert loaders.resolve_latest_complete_consumer_trade_date(service="test") == "2026-07-29"


@pytest.mark.parametrize(
    ("expected", "covered", "selected"),
    [(100, 99, "2026-07-30"), (101, 99, "2026-07-29")],
)
def test_resolver_uses_exact_integer_ninety_nine_percent_boundary(
    monkeypatch, expected, covered, selected
):
    _install_db(
        monkeypatch,
        [[
            _resolver_row(
                date(2026, 7, 30),
                expected=expected,
                raw=covered,
                hfq=covered,
                paired=covered,
            ),
            _resolver_row(date(2026, 7, 29), expected=100, raw=100, hfq=100, paired=100),
        ]],
    )
    assert loaders.resolve_latest_complete_consumer_trade_date(service="test") == selected


def test_resolver_excludes_future_open_dates_using_shanghai_database_time(monkeypatch):
    calls, _ = _install_db(
        monkeypatch,
        [[_resolver_row(date(2026, 7, 30), expected=100, raw=100, hfq=100, paired=100)]],
    )
    assert loaders.resolve_latest_complete_consumer_trade_date(service="test") == "2026-07-30"
    assert "trade_date <= (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Shanghai')::date" in calls[0][0]
    assert "CURRENT_DATE" not in calls[0][0]


@pytest.mark.parametrize(
    "rows",
    [
        [],
        [_resolver_row(date(2026, 7, 30), expected=100, raw=100, hfq=100, paired=100, is_open=False)],
        [_resolver_row("not-a-date", expected=100, raw=100, hfq=100, paired=100)],
        [_resolver_row(date(2026, 7, 30), expected=0, raw=0, hfq=0, paired=0)],
        [_resolver_row(date(2026, 7, 30), expected=100, raw=100, hfq=100, paired=101)],
        [_resolver_row(date(2026, 7, 30), expected=True, raw=1, hfq=1, paired=1)],
        [
            {
                key: value
                for key, value in _resolver_row(
                    date(2026, 7, 30), expected=100, raw=100, hfq=100, paired=100
                ).items()
                if key != "paired_asset_count"
            }
        ],
        [
            _resolver_row(date(2026, 7, 30), expected=100, raw=100, hfq=100, paired=100),
            _resolver_row(date(2026, 7, 30), expected=100, raw=100, hfq=100, paired=100),
        ],
    ],
)
def test_resolver_rejects_closed_empty_invalid_or_incomplete_rows(monkeypatch, rows):
    _install_db(monkeypatch, [rows])
    with pytest.raises(ValueError, match="complete consumer trade date|invalid"):
        loaders.resolve_latest_complete_consumer_trade_date(service="test")


def test_universe_loads_four_stable_frames_and_point_in_time_sql(monkeypatch):
    calls, services = _install_db(
        monkeypatch,
        [
            [{"asset_id": "B", "stock_code": "000002", "name": "B", "list_date": date(2020, 1, 2)}],
            [{"asset_id": "B", "is_st": False, "is_delisting_risk": False, "is_suspended": True}],
            [{"asset_id": "B", "avg_turnover_amount": 691_266.56}],
            [
                {"asset_id": "B", "industry_system": "citics", "industry_name": "消费"},
                {"asset_id": "B", "industry_system": "sw", "industry_name": "食品"},
                {"asset_id": "B", "industry_system": "csrc", "industry_name": "制造"},
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
    assert result["liquidity"].iloc[0]["avg_turnover_amount"] == 691_266.56
    assert result["industries"].to_dict("records") == [
        {"asset_id": "B", "industry_system": "sw", "industry_name": "食品"}
    ]
    assert "FROM core.asset_master" in calls[0][0]
    assert "core.asset_status_daily" in calls[1][0]
    assert "COALESCE" in calls[1][0] and "TRUE" in calls[1][0]
    assert "NOT a.is_active" not in calls[1][0]
    assert "a.delist_date IS NOT NULL AND a.delist_date <= %s" in calls[1][0]
    assert "LIMIT 20" in calls[2][0]
    assert "adjust_type = 'hfq'" in calls[2][0]
    assert (
        "AVG(CASE WHEN lower(COALESCE(b.source, '')) LIKE '%%tushare%%' "
        "THEN b.amount * 1000 ELSE b.amount END) AS avg_turnover_amount"
        in calls[2][0]
    )
    assert "LIKE '%tushare%'" not in calls[2][0]
    assert "start_date <= %s" in calls[3][0]
    assert "%s < end_date" in calls[3][0]
    assert "PARTITION BY asset_id" in calls[3][0]
    assert "PARTITION BY asset_id, industry_system" not in calls[3][0]
    assert "CASE lower(industry_system) WHEN 'sw' THEN 0 WHEN 'citics' THEN 1 WHEN 'csrc' THEN 2 ELSE 9 END" in calls[3][0]
    assert "level DESC, start_date DESC, industry_code" in calls[3][0]
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


def test_market_requests_520_hfq_dates_normalizes_amount_and_sorts(monkeypatch):
    calls, _ = _install_db(
        monkeypatch,
        [[
            {
                "asset_id": "B", "trade_date": date(2026, 7, 29),
                "close": 2, "raw_close": 20, "amount": 2_000,
                "turnover_rate": 0.2, "pct_chg": 2.0, "is_st": False,
                "trade_status": "normal",
            },
            {
                "asset_id": "A", "trade_date": date(2026, 7, 28),
                "close": 1, "raw_close": 10, "amount": None,
                "turnover_rate": 0.1, "pct_chg": -1.0, "is_st": True,
                "trade_status": "suspended",
            },
        ]],
    )
    result = loaders.load_consumer_market_history("2026-07-29", service="test")
    assert result.drop(columns="amount").to_dict("records") == [
        {
            "asset_id": "A", "trade_date": "2026-07-28", "close": 1,
            "raw_close": 10, "turnover_rate": 0.1,
            "pct_chg": -1.0, "is_st": True, "trade_status": "suspended",
        },
        {
            "asset_id": "B", "trade_date": "2026-07-29", "close": 2,
            "raw_close": 20, "turnover_rate": 0.2,
            "pct_chg": 2.0, "is_st": False, "trade_status": "normal",
        },
    ]
    assert pd.isna(result.loc[0, "amount"])
    assert result.loc[1, "amount"] == 2_000
    sql, params = calls[0]
    assert "SELECT DISTINCT trade_date" in sql
    assert "trade_date <= %s" in sql
    assert "LIMIT %s" in sql
    assert "adjust_type = 'hfq'" in sql
    assert "LEFT JOIN market_daily_bar raw" in sql
    assert "raw.adjust_type = 'raw'" in sql
    assert (
        "CASE WHEN lower(COALESCE(b.source, '')) LIKE '%%tushare%%' "
        "THEN b.amount * 1000 ELSE b.amount END AS amount"
        in sql
    )
    assert "COALESCE(b.amount, 0)" not in sql
    assert "b.turnover_rate" in sql
    assert "b.pct_chg" in sql
    assert "b.is_st" in sql
    assert "b.trade_status" in sql
    assert "stock_code" not in sql
    assert params == ["2026-07-29", 520]


def test_market_can_scope_assets_and_empty_scope_skips_database(monkeypatch):
    calls, _ = _install_db(
        monkeypatch,
        [[{
            "asset_id": "A", "trade_date": date(2026, 7, 29),
            "close": 10, "raw_close": 5, "amount": 1_000,
            "turnover_rate": 0.1, "pct_chg": 1.0, "is_st": False,
            "trade_status": "normal",
        }]],
    )

    result = loaders.load_consumer_market_history(
        "2026-07-29", service="test", asset_ids=[" A "]
    )

    assert result["asset_id"].tolist() == ["A"]
    sql, params = calls[0]
    assert "b.asset_id = ANY(%s)" in sql
    assert params == ["2026-07-29", 520, ["A"]]

    def fail_connect(service):
        raise AssertionError("empty asset scope must not query the database")

    monkeypatch.setattr(loaders, "connect", fail_connect)
    empty = loaders.load_consumer_market_history(
        "2026-07-29", service="test", asset_ids=[]
    )
    assert empty.columns.tolist() == list(loaders.MARKET_COLUMNS)


def test_market_empty_database_result_has_expanded_stable_schema(monkeypatch):
    _install_db(monkeypatch, [[]])

    result = loaders.load_consumer_market_history(
        "2026-07-29", service="test", asset_ids=["A"]
    )

    assert result.columns.tolist() == [
        "asset_id", "trade_date", "close", "raw_close", "amount",
        "turnover_rate", "pct_chg", "is_st", "trade_status",
    ]
    assert result.empty


def test_market_loader_carries_private_turnover_inputs_without_expanding_public_schema(
    monkeypatch,
):
    calls, _ = _install_db(
        monkeypatch,
        [[{
            "asset_id": "A",
            "trade_date": date(2026, 7, 29),
            "close": 10,
            "raw_close": 5,
            "amount": 1_000,
            "turnover_rate": None,
            "pct_chg": 1.0,
            "is_st": False,
            "trade_status": "normal",
            "turnover_volume": 250_000,
            "turnover_source": "derived:tushare",
        }]],
    )

    result = loaders.load_consumer_market_history(
        "2026-07-29", service="test", asset_ids=["A"]
    )

    assert result.columns.tolist() == list(loaders.MARKET_COLUMNS)
    assert result.attrs[loaders.TURNOVER_DERIVATION_INPUTS_ATTR] == [
        {
            "asset_id": "A",
            "trade_date": "2026-07-29",
            "volume": 250_000,
            "source": "derived:tushare",
        }
    ]
    sql, _ = calls[0]
    assert "b.volume AS turnover_volume" in sql
    assert "b.source AS turnover_source" in sql


@pytest.mark.parametrize(
    ("source", "volume", "float_share", "expected", "marker"),
    [
        ("baostock", 2_000_000, 100_000_000, 2.0, "baostock"),
        (
            "derived:tushare_raw_latest_factor",
            20_000,
            100_000_000,
            2.0,
            "derived:tushare_raw_latest_factor",
        ),
    ],
)
def test_derive_missing_turnover_is_source_aware_and_auditable(
    source, volume, float_share, expected, marker
):
    bars = pd.DataFrame(
        [{
            "asset_id": "A",
            "trade_date": "2026-07-27",
            "close": 10.0,
            "raw_close": 10.0,
            "amount": 1_000_000.0,
            "turnover_rate": None,
            "pct_chg": 0.0,
            "is_st": False,
            "trade_status": "normal",
        }],
        columns=loaders.MARKET_COLUMNS,
    )
    bars.attrs[loaders.TURNOVER_DERIVATION_INPUTS_ATTR] = [
        {
            "asset_id": "A",
            "trade_date": "2026-07-27",
            "volume": volume,
            "source": source,
        }
    ]
    shares = pd.DataFrame(
        [{
            "asset_id": "A",
            "total_share": 120_000_000,
            "float_share": float_share,
            "free_float_share": 80_000_000,
        }],
        columns=loaders.SHARE_CAPACITY_COLUMNS,
    )
    bars_original = bars.copy(deep=True)
    shares_original = shares.copy(deep=True)

    result = loaders.derive_consumer_market_turnover_history(
        bars,
        shares,
        trade_date="2026-07-27",
    )

    assert result.loc[0, "turnover_rate"] == pytest.approx(expected)
    assert result.columns.tolist() == list(loaders.MARKET_COLUMNS)
    assert result.attrs[loaders.TURNOVER_DERIVATION_COVERAGE_ATTR] == {
        "method": "pit_source_aware_v1",
        "share_capacity_cutoff": "2026-07-27",
        "missing_turnover_rows": 1,
        "derived_rows": 1,
        "unresolved_rows": 0,
        "derived_rows_by_source": {marker: 1},
    }
    pd.testing.assert_frame_equal(bars, bars_original)
    pd.testing.assert_frame_equal(shares, shares_original)


def test_derive_missing_turnover_uses_share_capacity_as_of_each_bar_date():
    bars = pd.DataFrame(
        [
            {
                "asset_id": "A",
                "trade_date": "2026-07-15",
                "close": 10.0,
                "raw_close": 10.0,
                "amount": 1_000_000.0,
                "turnover_rate": None,
                "pct_chg": 0.0,
                "is_st": False,
                "trade_status": "normal",
            },
            {
                "asset_id": "A",
                "trade_date": "2026-07-25",
                "close": 10.0,
                "raw_close": 10.0,
                "amount": 1_000_000.0,
                "turnover_rate": None,
                "pct_chg": 0.0,
                "is_st": False,
                "trade_status": "normal",
            },
        ],
        columns=loaders.MARKET_COLUMNS,
    )
    bars.attrs[loaders.TURNOVER_DERIVATION_INPUTS_ATTR] = [
        {
            "asset_id": "A",
            "trade_date": date,
            "volume": 10_000,
            "source": "derived:tushare",
        }
        for date in ("2026-07-15", "2026-07-25")
    ]
    shares = pd.DataFrame(
        [
            {
                "asset_id": "A",
                "total_share": 220_000_000,
                "float_share": 220_000_000,
                "free_float_share": 220_000_000,
            }
        ],
        columns=loaders.SHARE_CAPACITY_COLUMNS,
    )
    shares.attrs[loaders.SHARE_CAPACITY_HISTORY_ATTR] = [
        {
            "asset_id": "A",
            "event_date": "2026-07-01",
            "announcement_date": "2026-07-01",
            "total_share": 100_000_000,
            "float_share": 100_000_000,
            "free_float_share": 100_000_000,
        },
        {
            "asset_id": "A",
            "event_date": "2026-07-20",
            "announcement_date": "2026-07-20",
            "total_share": 220_000_000,
            "float_share": 220_000_000,
            "free_float_share": 220_000_000,
        },
    ]

    result = loaders.derive_consumer_market_turnover_history(
        bars,
        shares,
        trade_date="2026-07-27",
    )

    assert result["turnover_rate"].tolist() == pytest.approx([1.0, 100_000_000 / 220_000_000])


@pytest.mark.parametrize(
    ("float_share", "volume", "source"),
    [
        (None, 2_000_000, "baostock"),
        (0, 2_000_000, "baostock"),
        (100_000_000, None, "baostock"),
        (100_000_000, 0, "baostock"),
        (100_000_000, 2_000_000, "unknown"),
    ],
)
def test_derive_missing_turnover_leaves_unverifiable_rows_missing(
    float_share, volume, source
):
    bars = pd.DataFrame(
        [{
            "asset_id": "A",
            "trade_date": "2026-07-27",
            "close": 10.0,
            "raw_close": 10.0,
            "amount": 1_000_000.0,
            "turnover_rate": None,
            "pct_chg": 0.0,
            "is_st": False,
            "trade_status": "normal",
        }],
        columns=loaders.MARKET_COLUMNS,
    )
    bars.attrs[loaders.TURNOVER_DERIVATION_INPUTS_ATTR] = [
        {
            "asset_id": "A",
            "trade_date": "2026-07-27",
            "volume": volume,
            "source": source,
        }
    ]
    shares = pd.DataFrame(
        [{
            "asset_id": "A",
            "total_share": 120_000_000,
            "float_share": float_share,
            "free_float_share": 80_000_000,
        }],
        columns=loaders.SHARE_CAPACITY_COLUMNS,
    )

    result = loaders.derive_consumer_market_turnover_history(
        bars,
        shares,
        trade_date="2026-07-27",
    )

    assert pd.isna(result.loc[0, "turnover_rate"])
    assert result.attrs[loaders.TURNOVER_DERIVATION_COVERAGE_ATTR]["derived_rows"] == 0
    assert result.attrs[loaders.TURNOVER_DERIVATION_COVERAGE_ATTR]["unresolved_rows"] == 1


def test_asset_scoped_empty_lists_do_not_open_database(monkeypatch):
    def fail_connect(service):
        raise AssertionError("database must not be queried")

    monkeypatch.setattr(loaders, "connect", fail_connect)
    assert loaders.load_consumer_market_history("2026-07-29", service="x", asset_ids=[]).columns.tolist() == list(loaders.MARKET_COLUMNS)
    assert loaders.load_consumer_share_capacity([], "2026-07-29", service="x").columns.tolist() == list(loaders.SHARE_CAPACITY_COLUMNS)
    assert loaders.load_consumer_finance_history([], "2026-07-29", service="x").columns.tolist() == list(loaders.FINANCE_COLUMNS)
    assert loaders.load_consumer_valuation_history([], "2026-07-29", service="x").columns.tolist() == list(loaders.VALUATION_COLUMNS)
    assert loaders.load_consumer_earnings_forecasts([], "2026-07-29", service="x").columns.tolist() == list(loaders.EARNINGS_COLUMNS)


def test_share_capacity_loads_latest_visible_event_with_stable_fallback_columns(monkeypatch):
    calls, services = _install_db(
        monkeypatch,
        [[
            {
                "asset_id": "B", "total_share": Decimal("200"),
                "float_share": Decimal("180"),
            },
            {
                "asset_id": "A", "total_share": Decimal("100"),
                "float_share": Decimal("80"),
                "free_float_share": Decimal("60"),
            },
        ]],
    )

    result = loaders.load_consumer_share_capacity(
        [" B ", "A"], "2026-07-29", service="research-test"
    )

    assert services == ["research-test"]
    assert result.columns.tolist() == [
        "asset_id", "total_share", "float_share", "free_float_share"
    ]
    assert result["asset_id"].tolist() == ["A", "B"]
    assert result.loc[0, "total_share"] == Decimal("100")
    assert result.loc[0, "free_float_share"] == Decimal("60")
    assert pd.isna(result.loc[1, "free_float_share"])
    sql, params = calls[0]
    assert "SELECT DISTINCT ON (asset_id)" in sql
    assert "finance.share_capital_event" in sql
    assert "event_date <= %s" in sql
    assert "announcement_date IS NULL OR announcement_date <= %s" in sql
    assert (
        "ORDER BY asset_id, event_date DESC, announcement_date DESC NULLS LAST, source ASC"
        in sql
    )
    assert params == [["B", "A"], "2026-07-29", "2026-07-29"]


def test_share_capacity_empty_database_result_has_stable_schema(monkeypatch):
    _install_db(monkeypatch, [[]])

    result = loaders.load_consumer_share_capacity(
        ["A"], "2026-07-29", service="test"
    )

    assert result.columns.tolist() == list(loaders.SHARE_CAPACITY_COLUMNS)
    assert result.empty


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
    shares = [
        {
            "asset_id": "A",
            "event_date": "2025-03-31",
            "announcement_date": "2025-03-31",
            "total_share": 123.0,
        }
    ]
    calls, _ = _install_db(monkeypatch, [income, indicators, balances, cash, shares])

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
    assert result["total_share"].eq(123.0).all()
    for sql, params in calls[:4]:
        assert "announcement_date <= %s" in sql
        assert "asset_id = ANY(%s)" in sql
        assert params == [["A"], "2025-04-01"]
    share_sql, share_params = calls[4]
    assert "finance.share_capital_event" in share_sql
    assert "event_date <= %s" in share_sql
    assert "announcement_date IS NULL OR announcement_date <= %s" in share_sql
    assert share_params == [["A"], "2025-04-01", "2025-04-01"]


def test_finance_preserves_non_null_fields_and_derives_balance_debt_ratio(monkeypatch):
    income = [
        {"asset_id": "A", "report_period": "2023-03-31", "announcement_date": "2023-04-20", "revenue": 20, "np_parent": 2, "source": "s"},
        {"asset_id": "A", "report_period": "2023-12-31", "announcement_date": "2024-03-20", "revenue": 100, "np_parent": 10, "source": "s"},
        {"asset_id": "A", "report_period": "2024-03-31", "announcement_date": "2024-04-20", "revenue": 30, "np_parent": 3, "source": "s"},
        {"asset_id": "A", "report_period": "2024-12-31", "announcement_date": "2025-03-20", "revenue": 140, "np_parent": 14, "source": "s"},
        {"asset_id": "A", "report_period": "2025-03-31", "announcement_date": "2025-04-20", "revenue": 40, "np_parent": 4, "source": "s"},
    ]
    indicators = [
        {"asset_id": "A", "report_period": "2025-03-31", "announcement_date": "2025-04-21", "gross_margin": .35, "debt_ratio": .9, "source": "old", "calc_version": "v1"},
        {"asset_id": "A", "report_period": "2025-03-31", "announcement_date": "2025-04-22", "gross_margin": None, "debt_ratio": None, "source": "new", "calc_version": "v2"},
    ]
    balances = [
        {"asset_id": "A", "report_period": "2025-03-31", "announcement_date": "2025-04-23", "total_equity": 100, "total_assets": 200, "total_liabilities": 80, "source": "old"},
        {"asset_id": "A", "report_period": "2025-03-31", "announcement_date": "2025-04-24", "total_equity": None, "total_assets": None, "total_liabilities": None, "source": "new"},
        {"asset_id": "A", "report_period": "2025-03-31", "announcement_date": "2025-08-01", "total_equity": 999, "total_assets": 999, "total_liabilities": 998, "source": "future"},
    ]
    cash = [
        {"asset_id": "A", "report_period": "2023-03-31", "announcement_date": "2023-04-20", "net_operate_cash_flow": 1, "source": "s"},
        {"asset_id": "A", "report_period": "2023-12-31", "announcement_date": "2024-03-20", "net_operate_cash_flow": 8, "source": "s"},
        {"asset_id": "A", "report_period": "2024-03-31", "announcement_date": "2024-04-20", "net_operate_cash_flow": 2, "source": "s"},
        {"asset_id": "A", "report_period": "2024-12-31", "announcement_date": "2025-03-20", "net_operate_cash_flow": 12, "source": "s"},
        {"asset_id": "A", "report_period": "2025-03-31", "announcement_date": "2025-04-20", "net_operate_cash_flow": 3, "source": "s"},
    ]
    calls, _ = _install_db(monkeypatch, [income, indicators, balances, cash, []])

    result = loaders.load_consumer_finance_history(["A"], "2025-06-30", service="test")
    latest = result.loc[result["report_period"].eq("2025-03-31")].iloc[0]

    assert latest["equity_parent"] == 100
    assert latest["gross_margin"] == .35
    assert latest["debt_ratio"] == .4
    assert "total_assets, total_liabilities" in calls[2][0]


def test_finance_does_not_use_revision_announced_after_period_asof(monkeypatch):
    income = [
        {"asset_id": "A", "report_period": "2023-03-31", "announcement_date": "2023-04-20", "revenue": 20, "np_parent": 2, "source": "s"},
        {"asset_id": "A", "report_period": "2023-12-31", "announcement_date": "2024-03-20", "revenue": 100, "np_parent": 10, "source": "s"},
        {"asset_id": "A", "report_period": "2024-03-31", "announcement_date": "2024-04-20", "revenue": 30, "np_parent": 3, "source": "s"},
        {"asset_id": "A", "report_period": "2024-03-31", "announcement_date": "2024-06-01", "revenue": 300, "np_parent": 30, "source": "late"},
    ]
    _install_db(monkeypatch, [income, [], [], [], []])
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
    _install_db(monkeypatch, [income, indicators, [], [], []])
    result = loaders.load_consumer_finance_history(["A"], "2024-09-01", service="test")
    june = result.loc[result["report_period"].eq("2024-06-30")].iloc[0]
    assert pd.isna(june["revenue_ttm"])
    assert pd.isna(june["np_parent_ttm"])


def test_finance_ttm_scans_only_asset_local_rows(monkeypatch):
    income = [
        {"asset_id": asset_id, "report_period": "2024-12-31", "announcement_date": "2025-03-20", "revenue": value, "np_parent": value / 10, "source": "s"}
        for asset_id, value in (("A", 100), ("B", 200))
    ]
    cash = [
        {"asset_id": asset_id, "report_period": "2024-12-31", "announcement_date": "2025-03-21", "net_operate_cash_flow": value, "source": "s"}
        for asset_id, value in (("A", 10), ("B", 20))
    ]
    _install_db(monkeypatch, [income, [], [], cash, []])
    scanned_assets: list[set[str]] = []
    original = loaders._ttm_at_period

    def probe(rows, **kwargs):
        scanned_assets.append({str(row["asset_id"]) for row in rows})
        return original(rows, **kwargs)

    monkeypatch.setattr(loaders, "_ttm_at_period", probe)
    loaders.load_consumer_finance_history(["A", "B"], "2025-04-01", service="test")

    assert scanned_assets
    assert all(len(asset_set) <= 1 for asset_set in scanned_assets)


def test_finance_retains_latest_share_capital_without_finance_periods(monkeypatch):
    shares = [
        {"asset_id": "A", "event_date": "2025-01-01", "announcement_date": None, "total_share": 90},
        {"asset_id": "A", "event_date": "2025-06-01", "announcement_date": "2025-06-10", "total_share": 120},
    ]
    _install_db(monkeypatch, [[], [], [], [], shares])

    result = loaders.load_consumer_finance_history(["A"], "2026-07-29", service="test")

    assert result[["asset_id", "total_share"]].to_dict("records") == [
        {"asset_id": "A", "total_share": 120}
    ]
    assert pd.isna(result.loc[0, "report_period"])


def test_share_capital_same_dates_use_source_ascending_tie_break(monkeypatch):
    rows = [
        {
            "asset_id": "A",
            "event_date": "2025-06-01",
            "announcement_date": "2025-06-10",
            "total_share": 200,
            "source": "z_source",
        },
        {
            "asset_id": "A",
            "event_date": "2025-06-01",
            "announcement_date": "2025-06-10",
            "total_share": 100,
            "source": "a_source",
        },
    ]
    selected = []
    last_calls = None
    for ordered in (rows, list(reversed(rows))):
        calls, _ = _install_db(monkeypatch, [[], [], [], [], ordered])
        result = loaders.load_consumer_finance_history(["A"], "2026-07-29", service="test")
        selected.append(result.loc[0, "total_share"])
        last_calls = calls

    assert selected == [100, 100]
    sql, _ = last_calls[4]
    assert "SELECT DISTINCT ON (asset_id)" in sql
    assert "announcement_date DESC NULLS LAST" in sql
    assert "source ASC" in sql


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
    assert "f.computed_at < ((%s::date + interval '1 day') AT TIME ZONE 'Asia/Shanghai')" in sql
    assert params == [["A"], "2026-07-29", "2026-07-29", "2026-07-29"]


def test_valuation_uses_absolute_asia_shanghai_day_end_for_version_visibility(monkeypatch):
    rows = [
        {
            "asset_id": "A", "trade_date": "2026-07-28", "factor_name": "pe_ttm",
            "factor_value": 99, "computed_at": "2026-07-29T16:00:00Z",
            "calc_version": "future_utc", "industry_system": "sw", "industry_name": "食品",
        },
        {
            "asset_id": "A", "trade_date": "2026-07-28", "factor_name": "pe_ttm",
            "factor_value": 98, "computed_at": "2026-07-30T00:00:00+08:00",
            "calc_version": "future_shanghai", "industry_system": "sw", "industry_name": "食品",
        },
        {
            "asset_id": "A", "trade_date": "2026-07-28", "factor_name": "pe_ttm",
            "factor_value": 12, "computed_at": "2026-07-29T15:59:59Z",
            "calc_version": "visible", "industry_system": "sw", "industry_name": "食品",
        },
    ]
    _install_db(monkeypatch, [rows])
    result = loaders.load_consumer_valuation_history(["A"], "2026-07-29", service="test")
    assert result.iloc[0]["pe_ttm"] == 12


@pytest.mark.parametrize("missing_column", ["computed_at", "calc_version"])
def test_valuation_rejects_nonempty_database_rows_missing_version_metadata(monkeypatch, missing_column):
    row = {
        "asset_id": "A", "trade_date": "2026-07-28", "factor_name": "pe_ttm", "factor_value": 12,
        "computed_at": "2026-07-29T09:00:00+08:00", "calc_version": "v1",
        "industry_system": None, "industry_name": None,
    }
    row.pop(missing_column)
    _install_db(monkeypatch, [[row]])
    with pytest.raises(ValueError, match=missing_column):
        loaders.load_consumer_valuation_history(["A"], "2026-07-29", service="test")


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
    scoped_loaders = (
        lambda: loaders.load_consumer_market_history(
            "2026-07-29", service="test", asset_ids=asset_ids
        ),
        lambda: loaders.load_consumer_share_capacity(
            asset_ids, "2026-07-29", service="test"
        ),
        lambda: loaders.load_consumer_finance_history(
            asset_ids, "2026-07-29", service="test"
        ),
    )
    for load in scoped_loaders:
        with pytest.raises(ValueError, match="asset_ids"):
            load()
