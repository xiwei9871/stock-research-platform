import pytest
from fastapi import Request
from fastapi.testclient import TestClient

from stock_research.dashboard import app as dashboard_app
from stock_research.dashboard import user_admin


class _FakeAdminUser:
    def __init__(self, user_id: int = 1, username: str = "admin"):
        self.id = user_id
        self.username = username
        self.display_name = "Admin User"
        self.role = "admin"
        self.is_active = True


class _Cursor:
    def __init__(self, *, rows=None, all_rows=None):
        self.rows = list(rows or [])
        self.all_rows = list(all_rows or [])
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        self.calls.append((sql, params))

    def fetchone(self):
        if not self.rows:
            return None
        return self.rows.pop(0)

    def fetchall(self):
        return list(self.all_rows)


class _Connection:
    def __init__(self, *, rows=None, all_rows=None):
        self.cursor_obj = _Cursor(rows=rows, all_rows=all_rows)

    def cursor(self):
        return self.cursor_obj


class _Context:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self.conn

    def __exit__(self, exc_type, exc, tb):
        return False


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
            "actor_user_id": 9,
            "ip_address": "testclient",
            "user_agent": "testclient",
        }
    ]


def test_admin_create_user_route_rejects_invalid_role_before_service(monkeypatch):
    events = {"create_calls": 0}

    def fake_require_admin_user(request: Request):
        return _FakeAdminUser(user_id=9, username="root-admin")

    def fake_require_csrf(request: Request):
        return None

    def fake_create_user_account(**kwargs):
        events["create_calls"] += 1
        return kwargs

    monkeypatch.setattr(dashboard_app, "apply_user_platform_schema", lambda: None, raising=False)
    monkeypatch.setattr(dashboard_app, "require_admin_user", fake_require_admin_user, raising=False)
    monkeypatch.setattr(dashboard_app, "require_csrf", fake_require_csrf, raising=False)
    monkeypatch.setattr(dashboard_app, "create_user_account", fake_create_user_account, raising=False)

    with TestClient(dashboard_app.create_app()) as client:
        response = client.post(
            "/api/admin/users",
            json={
                "username": "analyst",
                "email": "analyst@example.com",
                "display_name": "Analyst",
                "password": "secret123",
                "role": "superuser",
            },
        )

    assert response.status_code == 422
    assert events["create_calls"] == 0


def test_admin_disable_route_passes_target_user_id(monkeypatch):
    events: dict[str, object] = {
        "admin_checks": [],
        "csrf_checks": [],
        "disable_calls": [],
    }

    def fake_require_admin_user(request: Request):
        events["admin_checks"].append(request.url.path)
        return _FakeAdminUser(user_id=7, username="ops-admin")

    def fake_require_csrf(request: Request):
        events["csrf_checks"].append(request.url.path)

    def fake_disable_user_account(**kwargs):
        events["disable_calls"].append(kwargs)
        return True

    monkeypatch.setattr(dashboard_app, "apply_user_platform_schema", lambda: None, raising=False)
    monkeypatch.setattr(dashboard_app, "require_admin_user", fake_require_admin_user, raising=False)
    monkeypatch.setattr(dashboard_app, "require_csrf", fake_require_csrf, raising=False)
    monkeypatch.setattr(dashboard_app, "disable_user_account", fake_disable_user_account, raising=False)

    with TestClient(dashboard_app.create_app()) as client:
        response = client.post("/api/admin/users/42/disable")

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert events["admin_checks"] == ["/api/admin/users/42/disable"]
    assert events["csrf_checks"] == ["/api/admin/users/42/disable"]
    assert events["disable_calls"] == [
        {
            "user_id": 42,
            "actor_user_id": 7,
            "ip_address": "testclient",
            "user_agent": "testclient",
        }
    ]


def test_admin_reset_password_route_passes_actor_context(monkeypatch):
    events: dict[str, object] = {
        "admin_checks": [],
        "csrf_checks": [],
        "reset_calls": [],
    }

    def fake_require_admin_user(request: Request):
        events["admin_checks"].append(request.url.path)
        return _FakeAdminUser(user_id=5, username="security-admin")

    def fake_require_csrf(request: Request):
        events["csrf_checks"].append(request.url.path)

    def fake_reset_user_password(**kwargs):
        events["reset_calls"].append(kwargs)
        return True

    monkeypatch.setattr(dashboard_app, "apply_user_platform_schema", lambda: None, raising=False)
    monkeypatch.setattr(dashboard_app, "require_admin_user", fake_require_admin_user, raising=False)
    monkeypatch.setattr(dashboard_app, "require_csrf", fake_require_csrf, raising=False)
    monkeypatch.setattr(dashboard_app, "reset_user_password", fake_reset_user_password, raising=False)

    with TestClient(dashboard_app.create_app()) as client:
        response = client.post(
            "/api/admin/users/21/reset-password",
            json={"password": "new-secret"},
        )

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert events["admin_checks"] == ["/api/admin/users/21/reset-password"]
    assert events["csrf_checks"] == ["/api/admin/users/21/reset-password"]
    assert events["reset_calls"] == [
        {
            "user_id": 21,
            "password": "new-secret",
            "actor_user_id": 5,
            "ip_address": "testclient",
            "user_agent": "testclient",
        }
    ]


def test_admin_enable_route_passes_actor_context(monkeypatch):
    events: dict[str, object] = {
        "admin_checks": [],
        "csrf_checks": [],
        "enable_calls": [],
    }

    def fake_require_admin_user(request: Request):
        events["admin_checks"].append(request.url.path)
        return _FakeAdminUser(user_id=3, username="ops-admin")

    def fake_require_csrf(request: Request):
        events["csrf_checks"].append(request.url.path)

    def fake_enable_user_account(**kwargs):
        events["enable_calls"].append(kwargs)
        return True

    monkeypatch.setattr(dashboard_app, "apply_user_platform_schema", lambda: None, raising=False)
    monkeypatch.setattr(dashboard_app, "require_admin_user", fake_require_admin_user, raising=False)
    monkeypatch.setattr(dashboard_app, "require_csrf", fake_require_csrf, raising=False)
    monkeypatch.setattr(dashboard_app, "enable_user_account", fake_enable_user_account, raising=False)

    with TestClient(dashboard_app.create_app()) as client:
        response = client.post("/api/admin/users/42/enable")

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert events["admin_checks"] == ["/api/admin/users/42/enable"]
    assert events["csrf_checks"] == ["/api/admin/users/42/enable"]
    assert events["enable_calls"] == [
        {
            "user_id": 42,
            "actor_user_id": 3,
            "ip_address": "testclient",
            "user_agent": "testclient",
        }
    ]


def test_reset_user_password_revokes_existing_sessions_and_records_audit(monkeypatch):
    conn = _Connection(rows=[{"id": 21}])
    audit_events = []

    monkeypatch.setattr(user_admin, "connect", lambda service: _Context(conn))
    monkeypatch.setattr(user_admin, "hash_password", lambda password: f"hashed::{password}")
    monkeypatch.setattr(
        user_admin,
        "record_audit_log",
        lambda **kwargs: audit_events.append(kwargs),
        raising=False,
    )

    result = user_admin.reset_user_password(
        user_id=21,
        password="new-secret",
        actor_user_id=5,
        ip_address="203.0.113.8",
        user_agent="pytest-agent",
    )

    assert result is True
    update_sql, update_params = conn.cursor_obj.calls[0]
    revoke_sql, revoke_params = conn.cursor_obj.calls[1]
    assert "UPDATE identity.user_account" in update_sql
    assert update_params == {"user_id": 21, "password_hash": "hashed::new-secret"}
    assert "UPDATE identity.user_session" in revoke_sql
    assert revoke_params == {"user_id": 21}
    assert audit_events == [
        {
            "actor_user_id": 5,
            "action": "admin_reset_password",
            "target_type": "user_account",
            "target_id": "21",
            "metadata": {},
            "ip_address": "203.0.113.8",
            "user_agent": "pytest-agent",
            "service": "stock_research",
        }
    ]


def test_disable_user_account_revokes_existing_sessions_and_records_audit(monkeypatch):
    conn = _Connection(rows=[{"id": 42}])
    audit_events = []

    monkeypatch.setattr(user_admin, "connect", lambda service: _Context(conn))
    monkeypatch.setattr(
        user_admin,
        "record_audit_log",
        lambda **kwargs: audit_events.append(kwargs),
        raising=False,
    )

    result = user_admin.disable_user_account(
        user_id=42,
        actor_user_id=7,
        ip_address="203.0.113.9",
        user_agent="pytest-agent",
    )

    assert result is True
    update_sql, update_params = conn.cursor_obj.calls[0]
    revoke_sql, revoke_params = conn.cursor_obj.calls[1]
    assert "UPDATE identity.user_account" in update_sql
    assert update_params == {"user_id": 42, "is_active": False}
    assert "UPDATE identity.user_session" in revoke_sql
    assert revoke_params == {"user_id": 42}
    assert audit_events == [
        {
            "actor_user_id": 7,
            "action": "admin_disable_user",
            "target_type": "user_account",
            "target_id": "42",
            "metadata": {},
            "ip_address": "203.0.113.9",
            "user_agent": "pytest-agent",
            "service": "stock_research",
        }
    ]


def test_enable_user_account_does_not_revoke_sessions(monkeypatch):
    conn = _Connection(rows=[{"id": 42}])
    audit_events = []

    monkeypatch.setattr(user_admin, "connect", lambda service: _Context(conn))
    monkeypatch.setattr(
        user_admin,
        "record_audit_log",
        lambda **kwargs: audit_events.append(kwargs),
        raising=False,
    )

    result = user_admin.enable_user_account(
        user_id=42,
        actor_user_id=3,
        ip_address="203.0.113.10",
        user_agent="pytest-agent",
    )

    assert result is True
    assert len(conn.cursor_obj.calls) == 1
    update_sql, update_params = conn.cursor_obj.calls[0]
    assert "UPDATE identity.user_account" in update_sql
    assert update_params == {"user_id": 42, "is_active": True}
    assert audit_events == [
        {
            "actor_user_id": 3,
            "action": "admin_enable_user",
            "target_type": "user_account",
            "target_id": "42",
            "metadata": {},
            "ip_address": "203.0.113.10",
            "user_agent": "pytest-agent",
            "service": "stock_research",
        }
    ]
