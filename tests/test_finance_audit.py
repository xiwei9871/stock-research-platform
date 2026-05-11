from stock_research import finance_audit


class FakeConnection:
    def __init__(self, rows_by_call):
        self.rows_by_call = list(rows_by_call)
        self.calls = []


class _ConnectionContext:
    def __init__(self, value):
        self.value = value

    def __enter__(self):
        return self.value

    def __exit__(self, exc_type, exc, tb):
        return False


def fake_fetch_all(conn, sql, params=None):
    conn.calls.append((sql, params))
    return conn.rows_by_call.pop(0)


def test_summarize_finance_coverage_flags_missing_statement_rows(monkeypatch):
    conn = FakeConnection(
        [
            [{"rows": 2}],
            [{"rows": 0}],
            [{"rows": 1}],
            [{"rows": 3}],
        ]
    )
    monkeypatch.setattr(finance_audit, "connect", lambda service: _ConnectionContext(conn))
    monkeypatch.setattr(finance_audit, "fetch_all", fake_fetch_all)

    rows = finance_audit.summarize_finance_coverage()

    assert rows == [
        {"check": "missing_balance_sheet", "status": "blocked", "rows": 2},
        {"check": "missing_cash_flow", "status": "ok", "rows": 0},
        {"check": "missing_announcement_date", "status": "blocked", "rows": 1},
        {"check": "announcement_before_report_period", "status": "warning", "rows": 3},
    ]
    queries = [sql for sql, _params in conn.calls]
    assert any("LEFT JOIN finance.balance_sheet" in sql for sql in queries)
    assert any("LEFT JOIN finance.cash_flow" in sql for sql in queries)
    assert any("announcement_date IS NULL" in sql for sql in queries)
    assert any("announcement_date < report_period" in sql for sql in queries)


def test_format_finance_audit_line_is_stable():
    line = finance_audit.format_finance_audit_line(
        {"check": "missing_balance_sheet", "status": "blocked", "rows": 2}
    )

    assert line == "finance_audit|missing_balance_sheet|blocked|rows|2"
