from fastapi import Request
from fastapi.testclient import TestClient

from stock_research.config import SETTINGS
from stock_research.dashboard import app as dashboard_app


class _FakeUser:
    def __init__(self, user_id=7, username="analyst", display_name="Analyst", role="admin"):
        self.id = user_id
        self.username = username
        self.display_name = display_name
        self.role = role

    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "display_name": self.display_name,
            "role": self.role,
        }


def test_login_me_logout_flow_sets_session_and_csrf_cookies(monkeypatch):
    events = {"audit": [], "revoked": [], "request_cookies": []}
    user = _FakeUser()

    def fake_require_current_user(request: Request):
        events["request_cookies"].append(dict(request.cookies))
        session_cookie = request.cookies.get(SETTINGS.dashboard_session_cookie_name)
        if not session_cookie:
            raise AssertionError("missing session cookie on authenticated route")
        return user

    def fake_require_csrf(request: Request):
        assert request.headers["X-CSRF-Token"] == request.cookies[SETTINGS.dashboard_csrf_cookie_name]

    monkeypatch.setattr(dashboard_app, "apply_user_platform_schema", lambda: None, raising=False)
    monkeypatch.setattr(dashboard_app, "count_recent_login_failures", lambda **kwargs: 0, raising=False)
    monkeypatch.setattr(
        dashboard_app,
        "authenticate_dashboard_user",
        lambda username, password, **kwargs: user,
        raising=False,
    )
    monkeypatch.setattr(
        dashboard_app,
        "create_user_session",
        lambda current_user, **kwargs: {
            "session_token": "session-token",
            "csrf_token": "csrf-token",
        },
        raising=False,
    )
    monkeypatch.setattr(
        dashboard_app,
        "require_current_user",
        fake_require_current_user,
        raising=False,
    )
    monkeypatch.setattr(
        dashboard_app,
        "require_csrf",
        fake_require_csrf,
        raising=False,
    )
    monkeypatch.setattr(
        dashboard_app,
        "revoke_user_session",
        lambda request, **kwargs: events["revoked"].append(request.cookies.get(
            SETTINGS.dashboard_session_cookie_name
        )),
        raising=False,
    )
    monkeypatch.setattr(
        dashboard_app,
        "record_audit_log",
        lambda **kwargs: events["audit"].append(kwargs),
        raising=False,
    )

    with TestClient(dashboard_app.create_app()) as client:
        login_response = client.post(
            "/api/auth/login",
            json={"username": "analyst", "password": "secret"},
        )

        assert login_response.status_code == 200
        assert login_response.cookies.get(SETTINGS.dashboard_session_cookie_name) == "session-token"
        assert login_response.cookies.get(SETTINGS.dashboard_csrf_cookie_name) == "csrf-token"

        me_response = client.get("/api/auth/me")

        assert me_response.status_code == 200
        assert me_response.json() == user.to_dict()
        assert events["request_cookies"][-1][SETTINGS.dashboard_session_cookie_name] == "session-token"

        logout_response = client.post(
            "/api/auth/logout",
            headers={"X-CSRF-Token": "csrf-token"},
        )

        assert logout_response.status_code == 200
        assert events["revoked"] == ["session-token"]
        assert events["audit"][-1]["action"] == "logout"
        assert client.cookies.get(SETTINGS.dashboard_session_cookie_name) is None
        assert client.cookies.get(SETTINGS.dashboard_csrf_cookie_name) is None


def test_login_returns_429_when_recent_failures_exceed_limit(monkeypatch):
    calls = {"authenticate": 0}

    monkeypatch.setattr(dashboard_app, "apply_user_platform_schema", lambda: None, raising=False)
    monkeypatch.setattr(dashboard_app, "count_recent_login_failures", lambda **kwargs: 5, raising=False)

    def fake_authenticate(*args, **kwargs):
        calls["authenticate"] += 1
        return None

    monkeypatch.setattr(dashboard_app, "authenticate_dashboard_user", fake_authenticate, raising=False)

    with TestClient(dashboard_app.create_app()) as client:
        response = client.post(
            "/api/auth/login",
            json={"username": "analyst", "password": "wrong"},
        )

    assert response.status_code == 429
    assert response.json()["detail"] == "too many login attempts"
    assert calls["authenticate"] == 0
