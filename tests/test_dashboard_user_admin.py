from fastapi.testclient import TestClient

from stock_research.dashboard import app as dashboard_app
from stock_research.dashboard.auth_models import CurrentUser


def _admin() -> CurrentUser:
    return CurrentUser("user:1", "admin", "Admin", "admin", True)


def _regular() -> CurrentUser:
    return CurrentUser("user:2", "regular", "Regular", "user", True)


def test_admin_users_requires_login(monkeypatch):
    monkeypatch.setattr(dashboard_app, "load_current_user_from_session", lambda token: None)
    client = TestClient(dashboard_app.create_app())

    response = client.get("/api/admin/users")

    assert response.status_code == 401
    assert response.json()["detail"] == "not_authenticated"


def test_admin_users_requires_admin(monkeypatch):
    monkeypatch.setattr(dashboard_app, "load_current_user_from_session", lambda token: _regular())
    client = TestClient(dashboard_app.create_app())

    response = client.get("/api/admin/users", cookies={"stock_research_session": "session"})

    assert response.status_code == 403
    assert response.json()["detail"] == "admin_required"


def test_admin_can_list_users(monkeypatch):
    monkeypatch.setattr(dashboard_app, "load_current_user_from_session", lambda token: _admin())
    monkeypatch.setattr(
        dashboard_app,
        "list_admin_users",
        lambda: [{"user_id": "user:1", "username": "admin", "display_name": "Admin", "role": "admin", "is_active": True}],
    )
    client = TestClient(dashboard_app.create_app())

    response = client.get("/api/admin/users", cookies={"stock_research_session": "session"})

    assert response.status_code == 200
    assert response.json()["items"][0]["username"] == "admin"


def test_admin_create_user_requires_csrf(monkeypatch):
    monkeypatch.setattr(dashboard_app, "load_current_user_from_session", lambda token: _admin())
    client = TestClient(dashboard_app.create_app())

    response = client.post(
        "/api/admin/users",
        cookies={"stock_research_session": "session", "stock_research_csrf": "csrf"},
        json={"username": "new", "password": "secret", "role": "user"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "csrf_token_required"


def test_admin_can_create_user_with_csrf(monkeypatch):
    monkeypatch.setattr(dashboard_app, "load_current_user_from_session", lambda token: _admin())
    monkeypatch.setattr(
        dashboard_app,
        "create_dashboard_user",
        lambda username, password, role="user", display_name="": {
            "user_id": "user:3",
            "username": username,
            "display_name": display_name,
            "role": role,
            "is_active": True,
        },
    )
    client = TestClient(dashboard_app.create_app())

    response = client.post(
        "/api/admin/users",
        headers={"X-CSRF-Token": "csrf"},
        cookies={"stock_research_session": "session", "stock_research_csrf": "csrf"},
        json={"username": "new", "password": "secret", "role": "user", "display_name": "New User"},
    )

    assert response.status_code == 200
    assert response.json()["user"]["username"] == "new"


def test_admin_can_disable_enable_and_reset_password(monkeypatch):
    monkeypatch.setattr(dashboard_app, "load_current_user_from_session", lambda token: _admin())
    calls = []
    monkeypatch.setattr(dashboard_app, "set_dashboard_user_active", lambda user_id, is_active: calls.append((user_id, is_active)))
    monkeypatch.setattr(dashboard_app, "reset_dashboard_user_password", lambda user_id, password: calls.append((user_id, password)))
    client = TestClient(dashboard_app.create_app())
    cookies = {"stock_research_session": "session", "stock_research_csrf": "csrf"}
    headers = {"X-CSRF-Token": "csrf"}

    disable = client.post("/api/admin/users/user:3/disable", headers=headers, cookies=cookies)
    enable = client.post("/api/admin/users/user:3/enable", headers=headers, cookies=cookies)
    reset = client.post(
        "/api/admin/users/user:3/reset-password",
        headers=headers,
        cookies=cookies,
        json={"password": "new-secret"},
    )

    assert disable.status_code == 200
    assert enable.status_code == 200
    assert reset.status_code == 200
    assert calls == [("user:3", False), ("user:3", True), ("user:3", "new-secret")]
