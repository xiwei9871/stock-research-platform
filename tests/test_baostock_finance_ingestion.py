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


def test_sync_finance_for_period_retries_not_logged_in(monkeypatch):
    class DummyContext:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, tb):
            return False

    class Result:
        fields = ["code", "pubDate", "statDate", "MBRevenue", "netProfit", "epsTTM"]

        def __init__(self, error_code, error_msg="", rows=None):
            self.error_code = error_code
            self.error_msg = error_msg
            self.rows = rows or []
            self.index = -1

        def next(self):
            self.index += 1
            return self.index < len(self.rows)

        def get_row_data(self):
            return self.rows[self.index]

    class Login:
        error_code = "0"
        error_msg = ""

    login_calls = []
    logout_calls = []
    monkeypatch.setattr(baostock_finance_ingestion, "connect", lambda service: DummyContext())
    monkeypatch.setattr(
        baostock_finance_ingestion,
        "_baostock_codes",
        lambda conn, limit, offset, year=None, quarter=None: ["sh.600000"],
    )
    monkeypatch.setattr(
        baostock_finance_ingestion.bs,
        "login",
        lambda: login_calls.append(True) or Login(),
    )
    monkeypatch.setattr(
        baostock_finance_ingestion.bs,
        "logout",
        lambda: logout_calls.append(True),
    )

    monkeypatch.setattr(
        baostock_finance_ingestion.bs,
        "query_profit_data",
        lambda **kwargs: (
            Result("10001001", "用户未登录")
            if len(login_calls) == 1
            else Result("0", rows=[["sh.600000", "2026-03-31", "2025-12-31", "1", "2", "3"]])
        ),
    )
    for name in [
        "query_balance_data",
        "query_cash_flow_data",
        "query_growth_data",
        "query_operation_data",
        "query_dupont_data",
    ]:
        monkeypatch.setattr(
            baostock_finance_ingestion.bs,
            name,
            lambda **kwargs: Result(
                "0",
                rows=[["sh.600000", "2026-03-31", "2025-12-31", "1", "2", "3"]],
            ),
        )

    monkeypatch.setattr(
        baostock_finance_ingestion,
        "upsert_finance_rows",
        lambda conn, indicators, incomes, share_capital_events: {
            "indicator_quarter": len(indicators),
            "income_statement": len(incomes),
            "share_capital_event": len(share_capital_events),
        },
    )

    result = baostock_finance_ingestion.sync_finance_for_period(2025, 4, limit=50, offset=0)

    assert result == {
        "indicator_quarter": 1,
        "income_statement": 1,
        "share_capital_event": 1,
        "queried_assets": 1,
    }
    assert len(login_calls) == 2
    assert len(logout_calls) == 2


def test_login_or_raise_retries_transient_network_error(monkeypatch):
    class Login:
        def __init__(self, error_code, error_msg=""):
            self.error_code = error_code
            self.error_msg = error_msg

    logins = [
        Login("10002007", "网络接收错误。"),
        Login("10002007", "网络接收错误。"),
        Login("0"),
    ]
    sleeps = []
    monkeypatch.setattr(
        baostock_finance_ingestion.bs,
        "login",
        lambda: logins.pop(0),
    )
    monkeypatch.setattr(baostock_finance_ingestion.time, "sleep", sleeps.append)

    baostock_finance_ingestion._login_or_raise()

    assert sleeps == [
        baostock_finance_ingestion.BAOSTOCK_LOGIN_RETRY_SECONDS,
        baostock_finance_ingestion.BAOSTOCK_LOGIN_RETRY_SECONDS,
    ]
