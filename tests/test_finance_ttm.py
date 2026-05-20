from stock_research.services import finance_ttm


class FakeConnection:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.calls = []


def fake_fetch_all(conn, sql, params=None):
    conn.calls.append((sql, params))
    return conn.rows


def test_calc_ttm_uses_only_announced_rows():
    rows = [
        {"report_period": "2024-12-31", "announcement_date": "2025-03-30", "np_parent": 100.0},
        {"report_period": "2025-03-31", "announcement_date": "2025-04-30", "np_parent": 30.0},
        {"report_period": "2025-06-30", "announcement_date": "2025-08-30", "np_parent": 80.0},
        {"report_period": "2024-03-31", "announcement_date": "2024-04-30", "np_parent": 30.0},
    ]

    value = finance_ttm.calc_ttm_from_cumulative_rows(
        rows,
        value_column="np_parent",
        trade_date="2025-07-31",
    )

    assert value == 100.0


def test_calc_ttm_returns_full_year_value_for_latest_annual_report():
    rows = [
        {"report_period": "2024-12-31", "announcement_date": "2025-03-30", "np_parent": 100.0},
        {"report_period": "2025-03-31", "announcement_date": "2025-04-30", "np_parent": 30.0},
    ]

    value = finance_ttm.calc_ttm_from_cumulative_rows(
        rows,
        value_column="np_parent",
        trade_date="2025-04-01",
    )

    assert value == 100.0


def test_calc_ttm_returns_none_when_components_are_missing():
    rows = [
        {"report_period": "2025-03-31", "announcement_date": "2025-04-30", "np_parent": 30.0},
    ]

    value = finance_ttm.calc_ttm_from_cumulative_rows(
        rows,
        value_column="np_parent",
        trade_date="2025-07-31",
    )

    assert value is None


def test_load_income_ttm_queries_point_in_time_income_rows(monkeypatch):
    conn = FakeConnection(
        [
            {
                "asset_id": "CN:SH:600000",
                "report_period": "2025-03-31",
                "announcement_date": "2025-04-30",
                "np_parent": 30.0,
            },
            {
                "asset_id": "CN:SH:600000",
                "report_period": "2024-12-31",
                "announcement_date": "2025-03-30",
                "np_parent": 100.0,
            },
            {
                "asset_id": "CN:SH:600000",
                "report_period": "2024-03-31",
                "announcement_date": "2024-04-30",
                "np_parent": 20.0,
            },
        ]
    )
    monkeypatch.setattr(finance_ttm, "fetch_all", fake_fetch_all)

    value = finance_ttm.load_income_ttm(
        conn,
        "CN:SH:600000",
        "2025-07-31",
        value_column="np_parent",
    )

    sql, params = conn.calls[0]
    assert value == 110.0
    assert "FROM finance.income_statement" in sql
    assert "asset_id = ANY(%s)" in sql
    assert "announcement_date <= %s" in sql
    assert "ORDER BY asset_id, report_period DESC, announcement_date DESC" in sql
    assert params == [["CN:SH:600000"], "2025-07-31"]


def test_load_income_ttm_rows_derives_non_year_end_ttm_in_batch(monkeypatch):
    conn = FakeConnection(
        [
            {
                "asset_id": "CN:SH:600000",
                "report_period": "2025-09-30",
                "announcement_date": "2025-10-30",
                "np_parent": 180.0,
                "revenue": 900.0,
            },
            {
                "asset_id": "CN:SH:600000",
                "report_period": "2024-12-31",
                "announcement_date": "2025-03-30",
                "np_parent": 200.0,
                "revenue": 1000.0,
            },
            {
                "asset_id": "CN:SH:600000",
                "report_period": "2024-09-30",
                "announcement_date": "2024-10-30",
                "np_parent": 120.0,
                "revenue": 650.0,
            },
            {
                "asset_id": "CN:SZ:000001",
                "report_period": "2025-09-30",
                "announcement_date": "2025-10-28",
                "np_parent": 50.0,
                "revenue": 400.0,
            },
            {
                "asset_id": "CN:SZ:000001",
                "report_period": "2024-12-31",
                "announcement_date": "2025-03-20",
                "np_parent": 80.0,
                "revenue": 700.0,
            },
        ]
    )
    monkeypatch.setattr(finance_ttm, "fetch_all", fake_fetch_all)

    values = finance_ttm.load_income_ttm_rows(
        conn,
        ["CN:SH:600000", "CN:SZ:000001"],
        "2025-10-31",
        value_columns=["np_parent", "revenue"],
    )

    assert values == {
        "CN:SH:600000": {
            "np_parent_ttm": 260.0,
            "revenue_ttm": 1250.0,
        },
        "CN:SZ:000001": {
            "np_parent_ttm": None,
            "revenue_ttm": None,
        },
    }
    sql, params = conn.calls[0]
    assert "FROM finance.income_statement" in sql
    assert "asset_id = ANY(%s)" in sql
    assert "announcement_date <= %s" in sql
    assert "ORDER BY asset_id, report_period DESC, announcement_date DESC" in sql
    assert params == [["CN:SH:600000", "CN:SZ:000001"], "2025-10-31"]


def test_load_income_ttm_rows_prefers_latest_announcement_for_same_report_period(monkeypatch):
    conn = FakeConnection(
        [
            {
                "asset_id": "CN:SH:600000",
                "report_period": "2025-09-30",
                "announcement_date": "2025-11-05",
                "np_parent": 190.0,
            },
            {
                "asset_id": "CN:SH:600000",
                "report_period": "2025-09-30",
                "announcement_date": "2025-10-30",
                "np_parent": 180.0,
            },
            {
                "asset_id": "CN:SH:600000",
                "report_period": "2024-12-31",
                "announcement_date": "2025-03-30",
                "np_parent": 200.0,
            },
            {
                "asset_id": "CN:SH:600000",
                "report_period": "2024-09-30",
                "announcement_date": "2024-10-30",
                "np_parent": 120.0,
            },
        ]
    )
    monkeypatch.setattr(finance_ttm, "fetch_all", fake_fetch_all)

    values = finance_ttm.load_income_ttm_rows(
        conn,
        ["CN:SH:600000"],
        "2025-11-06",
        value_columns=["np_parent"],
    )

    assert values == {
        "CN:SH:600000": {
            "np_parent_ttm": 270.0,
        }
    }
