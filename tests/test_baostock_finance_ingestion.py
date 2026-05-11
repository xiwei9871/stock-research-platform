from stock_research.loaders import baostock_finance_ingestion


class FakeConnection:
    def __init__(self):
        self.many_calls = []


def fake_execute_many(conn, sql, rows):
    conn.many_calls.append((sql, list(rows)))


def test_merge_finance_rows_by_code_pubdate_and_statdate():
    merged = baostock_finance_ingestion.merge_finance_rows(
        [
            {"code": "sh.600000", "pubDate": "2026-03-31", "statDate": "2025-12-31", "roeAvg": "0.1"},
        ],
        [
            {"code": "sh.600000", "pubDate": "2026-03-31", "statDate": "2025-12-31", "YOYNI": "0.2"},
        ],
    )

    assert merged == [
        {
            "code": "sh.600000",
            "pubDate": "2026-03-31",
            "statDate": "2025-12-31",
            "roeAvg": "0.1",
            "YOYNI": "0.2",
        }
    ]


def test_normalize_indicator_row_maps_available_baostock_fields():
    row = {
        "code": "sh.600000",
        "pubDate": "2026-03-31",
        "statDate": "2025-12-31",
        "roeAvg": "0.064403",
        "gpMargin": "0.31",
        "npMargin": "0.289744",
        "liabilityToAsset": "0.55",
        "YOYNI": "0.099705",
        "YOYPNI": "0.105177",
        "CFOToNP": "7.456324",
        "AssetTurnRatio": "0.017803",
        "currentRatio": "1.2",
        "quickRatio": "1.1",
    }

    normalized = baostock_finance_ingestion.normalize_indicator_row(row)

    assert normalized["asset_id"] == "CN:SH:600000"
    assert normalized["report_period"] == "2025-12-31"
    assert normalized["announcement_date"] == "2026-03-31"
    assert normalized["roe"] == 0.064403
    assert normalized["gross_margin"] == 0.31
    assert normalized["np_yoy"] == 0.099705
    assert normalized["calc_version"] == "baostock_v1"


def test_normalize_income_row_uses_profit_fields():
    row = {
        "code": "sh.600000",
        "pubDate": "2026-03-31",
        "statDate": "2025-12-31",
        "MBRevenue": "173964000000.000000",
        "netProfit": "50405000000.000000",
        "epsTTM": "1.501749",
    }

    normalized = baostock_finance_ingestion.normalize_income_row(row)

    assert normalized["asset_id"] == "CN:SH:600000"
    assert normalized["report_type"] == "FY"
    assert normalized["revenue"] == 173964000000.0
    assert normalized["net_profit"] == 50405000000.0
    assert normalized["eps_basic"] == 1.501749


def test_normalize_share_capital_row_uses_profit_share_fields():
    row = {
        "code": "sh.600000",
        "pubDate": "2026-03-31",
        "statDate": "2025-12-31",
        "totalShare": "33305838300.00",
        "liqaShare": "33305838300.00",
    }

    normalized = baostock_finance_ingestion.normalize_share_capital_row(row)

    assert normalized["asset_id"] == "CN:SH:600000"
    assert normalized["event_date"] == "2025-12-31"
    assert normalized["announcement_date"] == "2026-03-31"
    assert normalized["total_share"] == 33305838300.0
    assert normalized["float_share"] == 33305838300.0


def test_upsert_finance_rows(monkeypatch):
    conn = FakeConnection()
    monkeypatch.setattr(baostock_finance_ingestion, "execute_many", fake_execute_many)

    count = baostock_finance_ingestion.upsert_finance_rows(
        conn,
        indicators=[
            {
                "asset_id": "CN:SH:600000",
                "report_period": "2025-12-31",
                "announcement_date": "2026-03-31",
                "roe": 0.1,
                "roa": None,
                "gross_margin": None,
                "net_margin": None,
                "debt_ratio": None,
                "revenue_yoy": None,
                "np_yoy": None,
                "deduct_np_yoy": None,
                "ocf_to_np": None,
                "asset_turnover": None,
                "current_ratio": None,
                "quick_ratio": None,
                "source": "baostock",
                "calc_version": "baostock_v1",
            }
        ],
        incomes=[],
        share_capital_events=[],
    )

    assert count == {"indicator_quarter": 1, "income_statement": 0, "share_capital_event": 0}
    sql, rows = conn.many_calls[0]
    assert "INSERT INTO finance.indicator_quarter" in sql
    assert rows[0][0] == "CN:SH:600000"


def test_quarter_end_date_maps_standard_quarters():
    assert baostock_finance_ingestion.quarter_end_date(1993, 1) == "1993-03-31"
    assert baostock_finance_ingestion.quarter_end_date(1993, 4) == "1993-12-31"


def test_slice_baostock_codes_supports_offset_and_limit(monkeypatch):
    class FakeConn:
        pass

    monkeypatch.setattr(
        baostock_finance_ingestion,
        "fetch_all",
        lambda conn, sql, params=None: [
            {"baostock_code": "sh.600000"},
            {"baostock_code": "sh.600004"},
            {"baostock_code": "sh.600006"},
        ],
    )

    codes = baostock_finance_ingestion._baostock_codes(
        FakeConn(),
        limit=1,
        offset=1,
    )

    assert codes == ["sh.600004"]


def test_baostock_codes_can_filter_by_historical_universe(monkeypatch):
    class FakeConn:
        pass

    captured = {}

    def fake_fetch_all(conn, sql, params=None):
        captured['sql'] = sql
        captured['params'] = params
        return [
            {"baostock_code": "sh.600000"},
            {"baostock_code": "sz.000001"},
        ]

    monkeypatch.setattr(
        baostock_finance_ingestion,
        "fetch_all",
        fake_fetch_all,
    )

    codes = baostock_finance_ingestion._baostock_codes(
        FakeConn(),
        year=1993,
        quarter=4,
    )

    assert codes == ["sh.600000", "sz.000001"]
    assert captured['params'] == ['1993-12-31', '1993-12-31']
    assert 'list_date IS NULL OR list_date <= %s' in captured['sql']
    assert 'delist_date IS NULL OR delist_date >= %s' in captured['sql']


def test_sync_finance_for_period_short_circuits_when_no_codes(monkeypatch):
    monkeypatch.setattr(baostock_finance_ingestion, "connect", lambda service: (_ for _ in ()).throw(AssertionError("connect should not be called again")))
    monkeypatch.setattr(
        baostock_finance_ingestion,
        "_baostock_codes",
        lambda conn, limit, offset, year=None, quarter=None: [],
    )

    class DummyContext:
        def __enter__(self):
            return object()
        def __exit__(self, exc_type, exc, tb):
            return False

    calls = []
    monkeypatch.setattr(baostock_finance_ingestion, "connect", lambda service: DummyContext())
    monkeypatch.setattr(baostock_finance_ingestion.bs, "login", lambda: calls.append("login") or None)

    result = baostock_finance_ingestion.sync_finance_for_period(1993, 4, limit=50, offset=2050)

    assert result == {
        "indicator_quarter": 0,
        "income_statement": 0,
        "share_capital_event": 0,
        "queried_assets": 0,
    }
    assert calls == []
