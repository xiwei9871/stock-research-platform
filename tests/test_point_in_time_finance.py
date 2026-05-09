from stock_research.services import point_in_time_finance


class FakeConnection:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []


def fake_fetch_all(conn, sql, params=None):
    conn.calls.append((sql, params))
    return conn.rows


def test_get_latest_indicator_uses_announcement_date_cutoff(monkeypatch):
    conn = FakeConnection(
        [
            {
                "asset_id": "CN:SH:600000",
                "report_period": "2025-12-31",
                "announcement_date": "2026-03-20",
                "roe": 0.12,
            }
        ]
    )
    monkeypatch.setattr(point_in_time_finance, "fetch_all", fake_fetch_all)

    row = point_in_time_finance.get_latest_indicator(
        conn,
        "CN:SH:600000",
        "2026-04-01",
    )

    assert row["report_period"] == "2025-12-31"
    sql, params = conn.calls[0]
    assert "FROM finance.indicator_quarter" in sql
    assert "announcement_date <= %s" in sql
    assert "ORDER BY announcement_date DESC, report_period DESC" in sql
    assert "LIMIT 1" in sql
    assert params == ["CN:SH:600000", "2026-04-01"]


def test_get_latest_indicator_returns_none_without_available_row(monkeypatch):
    conn = FakeConnection([])
    monkeypatch.setattr(point_in_time_finance, "fetch_all", fake_fetch_all)

    row = point_in_time_finance.get_latest_indicator(
        conn,
        "CN:SH:600000",
        "2026-01-10",
    )

    assert row is None


def test_statement_helpers_query_standardized_finance_tables(monkeypatch):
    conn = FakeConnection([{"asset_id": "CN:SH:600000"}])
    monkeypatch.setattr(point_in_time_finance, "fetch_all", fake_fetch_all)

    point_in_time_finance.get_latest_income_statement(
        conn,
        "CN:SH:600000",
        "2026-04-01",
    )
    point_in_time_finance.get_latest_balance_sheet(
        conn,
        "CN:SH:600000",
        "2026-04-01",
    )
    point_in_time_finance.get_latest_cash_flow(
        conn,
        "CN:SH:600000",
        "2026-04-01",
    )

    queried_tables = [call[0] for call in conn.calls]
    assert any("FROM finance.income_statement" in sql for sql in queried_tables)
    assert any("FROM finance.balance_sheet" in sql for sql in queried_tables)
    assert any("FROM finance.cash_flow" in sql for sql in queried_tables)
