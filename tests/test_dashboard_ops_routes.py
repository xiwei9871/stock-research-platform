from datetime import date

from fastapi.testclient import TestClient

from stock_research.dashboard import app as dashboard_app


def test_ops_snapshot_route_passes_none_when_date_query_missing(monkeypatch):
    captured = {}

    def fake_build_internal_ops_snapshot(trade_date=None):
        captured["trade_date"] = trade_date
        return {"run_window": {"trade_date": "2026-06-29"}}

    monkeypatch.setattr(dashboard_app, "build_internal_ops_snapshot", fake_build_internal_ops_snapshot)

    client = TestClient(dashboard_app.create_app())
    response = client.get("/api/ops/snapshot")

    assert response.status_code == 200
    assert captured["trade_date"] is None


def test_ops_snapshot_route_parses_explicit_date_query(monkeypatch):
    captured = {}

    def fake_build_internal_ops_snapshot(trade_date=None):
        captured["trade_date"] = trade_date
        return {"run_window": {"trade_date": "2026-06-29"}}

    monkeypatch.setattr(dashboard_app, "build_internal_ops_snapshot", fake_build_internal_ops_snapshot)
    monkeypatch.setattr(dashboard_app, "_resolve_dashboard_trade_date", lambda value: date(2026, 6, 29))

    client = TestClient(dashboard_app.create_app())
    response = client.get("/api/ops/snapshot?date=2026-06-29")

    assert response.status_code == 200
    assert captured["trade_date"] == date(2026, 6, 29)
