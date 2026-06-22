from fastapi import Request
from fastapi.testclient import TestClient

from stock_research.dashboard import app as dashboard_app


class _FakeAdminUser:
    def __init__(self, user_id: int = 1, username: str = "admin"):
        self.id = user_id
        self.username = username
        self.display_name = "Admin User"
        self.role = "admin"
        self.is_active = True

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "username": self.username,
            "display_name": self.display_name,
            "role": self.role,
            "is_active": self.is_active,
        }


def test_admin_list_users_route_returns_items(monkeypatch):
    events: dict[str, object] = {"admin_checks": [], "items": []}

    def fake_require_admin_user(request: Request):
        events["admin_checks"].append(request.url.path)
        return _FakeAdminUser()

    def fake_list_user_accounts(**kwargs):
        events["items"].append(kwargs)
        return [
            {
                "id": 2,
                "username": "analyst",
                "email": "analyst@example.com",
                "display_name": "Analyst",
                "role": "user",
                "is_active": True,
                "disabled_at": None,
            }
        ]

    monkeypatch.setattr(dashboard_app, "apply_user_platform_schema", lambda: None, raising=False)
    monkeypatch.setattr(dashboard_app, "require_admin_user", fake_require_admin_user, raising=False)
    monkeypatch.setattr(dashboard_app, "list_user_accounts", fake_list_user_accounts, raising=False)

    with TestClient(dashboard_app.create_app()) as client:
        response = client.get("/api/admin/users")

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {
                "id": 2,
                "username": "analyst",
                "email": "analyst@example.com",
                "display_name": "Analyst",
                "role": "user",
                "is_active": True,
                "disabled_at": None,
            }
        ]
    }
    assert events["admin_checks"] == ["/api/admin/users"]
    assert events["items"] == [{}]


def test_admin_create_user_route_returns_created_user(monkeypatch):
    events: dict[str, object] = {
        "admin_checks": [],
        "csrf_checks": [],
        "create_calls": [],
        "audit": [],
    }

    def fake_require_admin_user(request: Request):
        events["admin_checks"].append(request.url.path)
        return _FakeAdminUser(user_id=9, username="root-admin")

    def fake_require_csrf(request: Request):
        events["csrf_checks"].append(request.url.path)

    def fake_create_user_account(**kwargs):
        events["create_calls"].append(kwargs)
        return {
            "id": 12,
            "username": kwargs["username"],
            "email": kwargs["email"],
            "display_name": kwargs["display_name"],
            "role": kwargs["role"],
            "is_active": True,
            "disabled_at": None,
        }

    monkeypatch.setattr(dashboard_app, "apply_user_platform_schema", lambda: None, raising=False)
    monkeypatch.setattr(dashboard_app, "require_admin_user", fake_require_admin_user, raising=False)
    monkeypatch.setattr(dashboard_app, "require_csrf", fake_require_csrf, raising=False)
    monkeypatch.setattr(dashboard_app, "create_user_account", fake_create_user_account, raising=False)
    monkeypatch.setattr(
        dashboard_app,
        "record_audit_log",
        lambda **kwargs: events["audit"].append(kwargs),
        raising=False,
    )

    with TestClient(dashboard_app.create_app()) as client:
        response = client.post(
            "/api/admin/users",
            json={
                "username": "analyst",
                "email": "analyst@example.com",
                "display_name": "Analyst",
                "password": "secret123",
                "role": "user",
            },
        )

    assert response.status_code == 200
    assert response.json() == {
        "id": 12,
        "username": "analyst",
        "email": "analyst@example.com",
        "display_name": "Analyst",
        "role": "user",
        "is_active": True,
        "disabled_at": None,
    }
    assert events["admin_checks"] == ["/api/admin/users"]
    assert events["csrf_checks"] == ["/api/admin/users"]
    assert events["create_calls"] == [
        {
            "username": "analyst",
            "email": "analyst@example.com",
            "display_name": "Analyst",
            "password": "secret123",
            "role": "user",
        }
    ]
    assert events["audit"] == [
        {
            "actor_user_id": 9,
            "action": "admin_create_user",
            "target_type": "user_account",
            "target_id": "12",
            "metadata": {"username": "analyst"},
            "ip_address": "testclient",
            "user_agent": "testclient",
        }
    ]


def test_admin_disable_route_passes_target_user_id(monkeypatch):
    events: dict[str, object] = {
        "admin_checks": [],
        "csrf_checks": [],
        "disable_calls": [],
        "audit": [],
    }

    def fake_require_admin_user(request: Request):
        events["admin_checks"].append(request.url.path)
        return _FakeAdminUser(user_id=7, username="ops-admin")

    def fake_require_csrf(request: Request):
        events["csrf_checks"].append(request.url.path)

    def fake_disable_user_account(user_id: int, **kwargs):
        events["disable_calls"].append({"user_id": user_id, **kwargs})
        return True

    monkeypatch.setattr(dashboard_app, "apply_user_platform_schema", lambda: None, raising=False)
    monkeypatch.setattr(dashboard_app, "require_admin_user", fake_require_admin_user, raising=False)
    monkeypatch.setattr(dashboard_app, "require_csrf", fake_require_csrf, raising=False)
    monkeypatch.setattr(dashboard_app, "disable_user_account", fake_disable_user_account, raising=False)
    monkeypatch.setattr(
        dashboard_app,
        "record_audit_log",
        lambda **kwargs: events["audit"].append(kwargs),
        raising=False,
    )

    with TestClient(dashboard_app.create_app()) as client:
        response = client.post("/api/admin/users/42/disable")

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert events["admin_checks"] == ["/api/admin/users/42/disable"]
    assert events["csrf_checks"] == ["/api/admin/users/42/disable"]
    assert events["disable_calls"] == [{"user_id": 42}]
    assert events["audit"] == [
        {
            "actor_user_id": 7,
            "action": "admin_disable_user",
            "target_type": "user_account",
            "target_id": "42",
            "metadata": {},
            "ip_address": "testclient",
            "user_agent": "testclient",
        }
    ]


def test_admin_reset_password_route_records_audit(monkeypatch):
    events: dict[str, object] = {
        "admin_checks": [],
        "csrf_checks": [],
        "reset_calls": [],
        "audit": [],
    }

    def fake_require_admin_user(request: Request):
        events["admin_checks"].append(request.url.path)
        return _FakeAdminUser(user_id=5, username="security-admin")

    def fake_require_csrf(request: Request):
        events["csrf_checks"].append(request.url.path)

    def fake_reset_user_password(user_id: int, password: str, **kwargs):
        events["reset_calls"].append({"user_id": user_id, "password": password, **kwargs})
        return True

    monkeypatch.setattr(dashboard_app, "apply_user_platform_schema", lambda: None, raising=False)
    monkeypatch.setattr(dashboard_app, "require_admin_user", fake_require_admin_user, raising=False)
    monkeypatch.setattr(dashboard_app, "require_csrf", fake_require_csrf, raising=False)
    monkeypatch.setattr(dashboard_app, "reset_user_password", fake_reset_user_password, raising=False)
    monkeypatch.setattr(
        dashboard_app,
        "record_audit_log",
        lambda **kwargs: events["audit"].append(kwargs),
        raising=False,
    )

    with TestClient(dashboard_app.create_app()) as client:
        response = client.post(
            "/api/admin/users/21/reset-password",
            json={"password": "new-secret"},
        )

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert events["admin_checks"] == ["/api/admin/users/21/reset-password"]
    assert events["csrf_checks"] == ["/api/admin/users/21/reset-password"]
    assert events["reset_calls"] == [{"user_id": 21, "password": "new-secret"}]
    assert events["audit"] == [
        {
            "actor_user_id": 5,
            "action": "admin_reset_password",
            "target_type": "user_account",
            "target_id": "21",
            "metadata": {},
            "ip_address": "testclient",
            "user_agent": "testclient",
        }
    ]


def test_admin_enable_route_records_audit(monkeypatch):
    events: dict[str, object] = {
        "admin_checks": [],
        "csrf_checks": [],
        "enable_calls": [],
        "audit": [],
    }

    def fake_require_admin_user(request: Request):
        events["admin_checks"].append(request.url.path)
        return _FakeAdminUser(user_id=3, username="ops-admin")

    def fake_require_csrf(request: Request):
        events["csrf_checks"].append(request.url.path)

    def fake_enable_user_account(user_id: int, **kwargs):
        events["enable_calls"].append({"user_id": user_id, **kwargs})
        return True

    monkeypatch.setattr(dashboard_app, "apply_user_platform_schema", lambda: None, raising=False)
    monkeypatch.setattr(dashboard_app, "require_admin_user", fake_require_admin_user, raising=False)
    monkeypatch.setattr(dashboard_app, "require_csrf", fake_require_csrf, raising=False)
    monkeypatch.setattr(dashboard_app, "enable_user_account", fake_enable_user_account, raising=False)
    monkeypatch.setattr(
        dashboard_app,
        "record_audit_log",
        lambda **kwargs: events["audit"].append(kwargs),
        raising=False,
    )

    with TestClient(dashboard_app.create_app()) as client:
        response = client.post("/api/admin/users/42/enable")

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert events["admin_checks"] == ["/api/admin/users/42/enable"]
    assert events["csrf_checks"] == ["/api/admin/users/42/enable"]
    assert events["enable_calls"] == [{"user_id": 42}]
    assert events["audit"] == [
        {
            "actor_user_id": 3,
            "action": "admin_enable_user",
            "target_type": "user_account",
            "target_id": "42",
            "metadata": {},
            "ip_address": "testclient",
            "user_agent": "testclient",
        }
    ]
