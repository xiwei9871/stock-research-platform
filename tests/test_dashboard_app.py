from fastapi.testclient import TestClient

from stock_research import cli
from stock_research.dashboard import app as dashboard_app


def test_overview_route_returns_payload(monkeypatch):
    monkeypatch.setattr(
        dashboard_app,
        "build_dashboard_overview",
        lambda trade_date, score_version, watchlist_id, top_n: {
            "trade_date": trade_date,
            "score_version": score_version,
            "watchlist_id": watchlist_id,
            "top_scores": [],
            "watchlist_signals": [],
            "reports": [],
        },
    )
    client = TestClient(dashboard_app.create_app())

    response = client.get("/api/dashboard/overview?trade_date=2026-05-29")

    assert response.status_code == 200
    assert response.json()["trade_date"] == "2026-05-29"


def test_asset_detail_route_returns_404_for_missing_asset(monkeypatch):
    monkeypatch.setattr(dashboard_app, "load_asset_detail", lambda asset_id: None)
    client = TestClient(dashboard_app.create_app())

    response = client.get("/api/assets/000001.SZ")

    assert response.status_code == 404
    assert response.json()["detail"] == "asset not found"


def test_minute_bars_route_passes_source(monkeypatch):
    captured = {}

    def fake_load_minute_bars(asset_id, start_time, end_time, freq, adjust_type, source):
        captured["args"] = [asset_id, start_time, end_time, freq, adjust_type, source]
        return [{"time": "2026-05-29 09:35:00"}]

    monkeypatch.setattr(dashboard_app, "load_minute_bars", fake_load_minute_bars)
    client = TestClient(dashboard_app.create_app())

    response = client.get(
        "/api/assets/000001.SZ/minute-bars"
        "?start_time=2026-05-29T09:30:00"
        "&end_time=2026-05-29T15:00:00"
        "&freq=5min"
        "&adjust_type=qfq"
        "&source=tushare"
    )

    assert response.status_code == 200
    assert captured["args"] == [
        "000001.SZ",
        "2026-05-29T09:30:00",
        "2026-05-29T15:00:00",
        "5min",
        "qfq",
        "tushare",
    ]
    assert response.json()["items"] == [{"time": "2026-05-29 09:35:00"}]


def test_dashboard_api_cli_parser_accepts_host_and_port():
    args = cli.build_parser().parse_args(
        ["dashboard-api", "--host", "0.0.0.0", "--port", "9999"]
    )

    assert args.command == "dashboard-api"
    assert args.host == "0.0.0.0"
    assert args.port == 9999


def test_dashboard_api_cli_dispatches_to_runner(monkeypatch):
    captured = {}

    def fake_run_dashboard_api(host, port):
        captured["call"] = {"host": host, "port": port}

    monkeypatch.setattr(cli, "run_dashboard_api", fake_run_dashboard_api)

    cli.main_for_args(["dashboard-api", "--host", "0.0.0.0", "--port", "9999"])

    assert captured["call"] == {"host": "0.0.0.0", "port": 9999}
