from stock_research.services import asset_status_service


class FakeConnection:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []


def fake_fetch_all(conn, sql, params=None):
    conn.calls.append((sql, params))
    return conn.rows


def test_get_status_queries_daily_status(monkeypatch):
    conn = FakeConnection(
        [
            {
                "asset_id": "CN:SH:600000",
                "trade_date": "2026-05-08",
                "is_trade": True,
                "is_st": False,
                "is_suspended": False,
                "is_limit_up": False,
                "is_limit_down": False,
            }
        ]
    )
    monkeypatch.setattr(asset_status_service, "fetch_all", fake_fetch_all)

    row = asset_status_service.get_status(conn, "CN:SH:600000", "2026-05-08")

    assert row["is_trade"] is True
    sql, params = conn.calls[0]
    assert "FROM core.asset_status_daily" in sql
    assert "asset_id = %s" in sql
    assert "trade_date = %s" in sql
    assert params == ["CN:SH:600000", "2026-05-08"]


def test_is_tradable_rejects_st_suspended_and_limit_up(monkeypatch):
    monkeypatch.setattr(
        asset_status_service,
        "get_status",
        lambda conn, asset_id, trade_date: {
            "is_trade": True,
            "is_st": False,
            "is_suspended": False,
            "is_limit_up": False,
            "is_limit_down": False,
        },
    )
    assert asset_status_service.is_tradable(object(), "CN:SH:600000", "2026-05-08")

    for blocked_field in ["is_trade", "is_st", "is_suspended", "is_limit_up"]:
        def fake_status(conn, asset_id, trade_date, field=blocked_field):
            status = {
                "is_trade": True,
                "is_st": False,
                "is_suspended": False,
                "is_limit_up": False,
                "is_limit_down": False,
            }
            status[field] = False if field == "is_trade" else True
            return status

        monkeypatch.setattr(asset_status_service, "get_status", fake_status)
        assert not asset_status_service.is_tradable(
            object(),
            "CN:SH:600000",
            "2026-05-08",
        )


def test_is_tradable_rejects_missing_status(monkeypatch):
    monkeypatch.setattr(
        asset_status_service,
        "get_status",
        lambda conn, asset_id, trade_date: None,
    )

    assert not asset_status_service.is_tradable(
        object(),
        "CN:SH:600000",
        "2026-05-08",
    )
