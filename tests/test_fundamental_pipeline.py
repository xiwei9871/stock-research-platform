from stock_research import fundamental_pipeline


def test_load_point_in_time_indicators_filters_by_announcement_date(monkeypatch):
    calls = []

    def fake_fetch_all(conn, sql, params=None):
        calls.append((sql, params))
        return [{"asset_id": "A", "roe": 0.15, "announcement_date": "2026-03-20"}]

    monkeypatch.setattr(fundamental_pipeline, "connect", lambda service: _context(object()))
    monkeypatch.setattr(fundamental_pipeline, "fetch_all", fake_fetch_all)

    frame = fundamental_pipeline.load_point_in_time_indicators("2026-05-08")

    assert frame.iloc[0]["asset_id"] == "A"
    assert "announcement_date <= %s" in calls[0][0]
    assert calls[0][1] == ["2026-05-08"]


class _context:
    def __init__(self, value):
        self.value = value

    def __enter__(self):
        return self.value

    def __exit__(self, exc_type, exc, tb):
        return False
