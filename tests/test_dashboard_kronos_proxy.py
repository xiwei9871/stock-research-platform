from __future__ import annotations

import json

from fastapi.testclient import TestClient

from stock_research.dashboard import app as dashboard_app
from stock_research.dashboard import kronos_proxy


class FakeResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload
        self.content = json.dumps(payload).encode("utf-8")

    def json(self):
        return self._payload


def test_kronos_proxy_normalizes_external_asset_id_and_unwraps_response(monkeypatch):
    calls = []

    def fake_request(method, url, *, headers, params=None, json=None, timeout=None):
        calls.append(
            {
                "method": method,
                "url": url,
                "headers": headers,
                "params": params,
                "json": json,
                "timeout": timeout,
            }
        )
        return FakeResponse(
            202,
            {
                "success": True,
                "data": {"run_id": "run-1", "code": "600418", "status": "queued"},
            },
        )

    monkeypatch.setenv("KRONOS_PROXY_BASE_URL", "http://192.168.3.187:8080/api/internal")
    monkeypatch.setenv("KRONOS_PROXY_TOKEN", "proxy-secret")
    monkeypatch.setattr(kronos_proxy.requests, "request", fake_request)

    payload = kronos_proxy.create_prediction("CN:SH:600418", force=True)

    assert payload["run_id"] == "run-1"
    assert calls[0]["method"] == "POST"
    assert calls[0]["url"].endswith("/internal/stocks/600418/kronos/predictions")
    assert calls[0]["params"] == {"force": "true"}
    assert calls[0]["headers"]["X-Kronos-Proxy-Token"] == "proxy-secret"


def test_kronos_proxy_routes_are_readable_from_dashboard_api(monkeypatch):
    monkeypatch.setenv("STOCK_RESEARCH_DASHBOARD_AUTH_REQUIRED", "false")
    monkeypatch.setenv("KRONOS_PROXY_BASE_URL", "http://192.168.3.187:8080/api/internal")
    monkeypatch.setenv("KRONOS_PROXY_TOKEN", "proxy-secret")

    def fake_request(method, url, *, headers, params=None, json=None, timeout=None):
        assert headers["X-Kronos-Proxy-Token"] == "proxy-secret"
        if method == "GET" and url.endswith("/kronos/predictions/latest"):
            return FakeResponse(
                200,
                {"success": True, "data": {"run_id": "run-2", "code": "600418", "status": "succeeded"}},
            )
        return FakeResponse(404, {"detail": "not found"})

    monkeypatch.setattr(kronos_proxy.requests, "request", fake_request)

    with TestClient(dashboard_app.create_app()) as client:
        response = client.get("/api/assets/600418.SH/kronos/predictions/latest")

    assert response.status_code == 200
    assert response.json()["run_id"] == "run-2"


def test_kronos_proxy_reports_missing_configuration(monkeypatch):
    monkeypatch.delenv("KRONOS_PROXY_BASE_URL", raising=False)
    monkeypatch.delenv("KRONOS_PROXY_TOKEN", raising=False)

    try:
        kronos_proxy.create_prediction("600418")
    except kronos_proxy.KronosProxyError as exc:
        assert exc.status_code == 503
    else:
        raise AssertionError("expected a configuration error")
