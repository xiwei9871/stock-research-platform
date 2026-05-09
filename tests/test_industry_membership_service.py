from stock_research.services import industry_membership_service


class FakeConnection:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []


def fake_fetch_all(conn, sql, params=None):
    conn.calls.append((sql, params))
    return conn.rows


def test_get_membership_uses_historical_window(monkeypatch):
    conn = FakeConnection(
        [
            {
                "asset_id": "CN:SH:600000",
                "industry_system": "sw",
                "industry_name": "银行",
                "start_date": "2020-01-01",
                "end_date": None,
            }
        ]
    )
    monkeypatch.setattr(industry_membership_service, "fetch_all", fake_fetch_all)

    row = industry_membership_service.get_membership(
        conn,
        "CN:SH:600000",
        "2026-05-08",
        "sw",
    )

    assert row["industry_name"] == "银行"
    sql, params = conn.calls[0]
    assert "FROM core.industry_membership" in sql
    assert "start_date <= %s" in sql
    assert "(end_date IS NULL OR %s < end_date)" in sql
    assert "ORDER BY level DESC, start_date DESC" in sql
    assert params == ["CN:SH:600000", "sw", "2026-05-08", "2026-05-08"]


def test_get_membership_returns_none_without_match(monkeypatch):
    conn = FakeConnection([])
    monkeypatch.setattr(industry_membership_service, "fetch_all", fake_fetch_all)

    row = industry_membership_service.get_membership(
        conn,
        "CN:SH:600000",
        "2026-05-08",
        "sw",
    )

    assert row is None
