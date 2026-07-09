from fastapi.testclient import TestClient

from stock_research.dashboard import app as dashboard_app
from stock_research.dashboard.auth_models import CurrentUser


def test_auth_me_returns_401_when_not_logged_in():
    client = TestClient(dashboard_app.create_app())

    response = client.get("/api/auth/me")

    assert response.status_code == 401
    assert response.json()["detail"] == "not_authenticated"


def test_auth_me_returns_current_user(monkeypatch):
    monkeypatch.setattr(
        dashboard_app,
        "load_current_user_from_session",
        lambda token: CurrentUser("user:1", "admin", "Admin", "admin", True),
    )
    client = TestClient(dashboard_app.create_app())

    response = client.get("/api/auth/me", cookies={"stock_research_session": "session-token"})

    assert response.status_code == 200
    assert response.json()["user"] == {
        "user_id": "user:1",
        "username": "admin",
        "display_name": "Admin",
        "role": "admin",
        "is_active": True,
    }


def test_login_sets_session_and_csrf_cookies(monkeypatch):
    user = CurrentUser(user_id="user:1", username="admin", display_name="Admin", role="admin", is_active=True)
    monkeypatch.setattr(dashboard_app, "authenticate_user", lambda username, password: user)
    monkeypatch.setattr(
        dashboard_app,
        "create_session",
        lambda user, user_agent="", ip_address="": {
            "session_token": "session-token",
            "csrf_token": "csrf-token",
            "expires_at": "2026-07-08T12:00:00+00:00",
        },
    )
    client = TestClient(dashboard_app.create_app())

    response = client.post("/api/auth/login", json={"username": "admin", "password": "secret"})

    assert response.status_code == 200
    assert response.json()["user"]["role"] == "admin"
    assert "stock_research_session=session-token" in response.headers["set-cookie"]
    assert "stock_research_csrf=csrf-token" in response.headers["set-cookie"]


def test_login_rejects_invalid_credentials(monkeypatch):
    def reject(username, password):
        raise PermissionError("invalid_credentials")

    monkeypatch.setattr(dashboard_app, "authenticate_user", reject)
    client = TestClient(dashboard_app.create_app())

    response = client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})

    assert response.status_code == 401
    assert response.json()["detail"] == "invalid_credentials"


def test_logout_clears_session_cookie(monkeypatch):
    called = []
    monkeypatch.setattr(dashboard_app, "revoke_session", lambda session_token: called.append(session_token))
    client = TestClient(dashboard_app.create_app())

    response = client.post("/api/auth/logout", cookies={"stock_research_session": "session-token"})

    assert response.status_code == 200
    assert response.json() == {"status": "logged_out"}
    assert called == ["session-token"]
    assert "stock_research_session=" in response.headers["set-cookie"]
