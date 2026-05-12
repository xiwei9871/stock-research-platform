from stock_research.services import index_universe_service


class FakeConnection:
    def __init__(self):
        self.calls = []


def fake_fetch_all(conn, sql, params=None):
    conn.calls.append((sql, params))
    return [{"asset_id": "CN:SH:600000"}]


def test_load_index_universe_filters_point_in_time_membership(monkeypatch):
    conn = FakeConnection()
    monkeypatch.setattr(index_universe_service, "fetch_all", fake_fetch_all)

    rows = index_universe_service.load_index_universe(
        conn,
        "CSI_300",
        "2024-05-31",
        source_version="baostock_snapshot_v1",
    )

    assert rows == [{"asset_id": "CN:SH:600000"}]
    sql, params = conn.calls[0]
    assert "FROM market.index_constituent" in sql
    assert "index_id = %s" in sql
    assert "start_date <= %s" in sql
    assert "(end_date IS NULL OR %s <= end_date)" in sql
    assert "source_version = %s" in sql
    assert params == ["CSI_300", "2024-05-31", "2024-05-31", "baostock_snapshot_v1"]
