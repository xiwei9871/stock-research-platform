import hashlib

import pytest
from fastapi import HTTPException
from fastapi import Request
from fastapi.testclient import TestClient
from psycopg import OperationalError

from stock_research.config import SETTINGS
from stock_research.dashboard import app as dashboard_app
from stock_research.dashboard import auth as dashboard_auth
from stock_research.dashboard.user_models import CurrentUser


class _Cursor:
    def __init__(self, rows=None):
        self.rows = list(rows or [])
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


class _Connection:
    def __init__(self, rows=None):
        self.cursor_obj = _Cursor(rows)

    def cursor(self):
        return self.cursor_obj


class _Context:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self.conn

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeUser:
    def __init__(self, user_id=7, username="analyst", display_name="Analyst", role="admin", is_active=True):
        self.id = user_id
        self.username = username
        self.display_name = display_name
        self.role = role
        self.is_active = is_active

    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "display_name": self.display_name,
            "role": self.role,
            "is_active": self.is_active,
        }


def _build_request(
    *,
    method: str = "GET",
    path: str = "/",
    cookies: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
) -> Request:
    scope_headers = []
    if cookies:
        cookie_header = "; ".join(f"{key}={value}" for key, value in cookies.items())
        scope_headers.append((b"cookie", cookie_header.encode("utf-8")))
    for key, value in (headers or {}).items():
        scope_headers.append((key.lower().encode("utf-8"), value.encode("utf-8")))
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": method,
        "path": path,
        "raw_path": path.encode("utf-8"),
        "query_string": b"",
        "headers": scope_headers,
        "client": ("203.0.113.8", 50000),
        "server": ("testserver", 80),
        "scheme": "http",
    }
    return Request(scope)


def test_current_user_to_dict_includes_is_active():
    assert CurrentUser.__annotations__.get("is_active") is bool

    current_user = CurrentUser(
        id=3,
        username="analyst",
        display_name="Analyst",
        role="admin",
        is_active=True,
    )

    assert current_user.to_dict() == {
        "id": 3,
        "username": "analyst",
        "display_name": "Analyst",
        "role": "admin",
        "is_active": True,
    }


def test_hash_password_and_verify_password_round_trip_uses_argon2():
    password_hash = dashboard_auth.hash_password("secret")

    assert password_hash != "secret"
    assert password_hash.startswith("$argon2")
    assert dashboard_auth.verify_password("secret", password_hash) is True
    assert dashboard_auth.verify_password("wrong", password_hash) is False


def test_count_recent_login_failures_counts_identifier_or_ip(monkeypatch):
    conn = _Connection(rows=[{"failure_count": 4}])
    monkeypatch.setattr(dashboard_auth, "connect", lambda service: _Context(conn))

    failure_count = dashboard_auth.count_recent_login_failures(
        identifier="analyst@example.com",
        ip_address="203.0.113.8",
    )

    assert failure_count == 4
    sql, params = conn.cursor_obj.calls[0]
    assert "metadata->>'identifier' = %(identifier)s" in sql
    assert "OR ip_address = %(ip_address)s" in sql
    assert params["identifier"] == "analyst@example.com"
    assert params["ip_address"] == "203.0.113.8"


def test_authenticate_dashboard_user_supports_username_or_email_lookup(monkeypatch):
    password_hash = dashboard_auth.hash_password("secret")
    conn = _Connection(
        rows=[
            {
                "id": 9,
                "username": "analyst",
                "display_name": "Analyst",
                "role": "admin",
                "is_active": True,
                "password_hash": password_hash,
            }
        ]
    )
    monkeypatch.setattr(dashboard_auth, "connect", lambda service: _Context(conn))

    current_user = dashboard_auth.authenticate_dashboard_user(
        identifier="analyst@example.com",
        password="secret",
    )

    assert current_user.to_dict() == {
        "id": 9,
        "username": "analyst",
        "display_name": "Analyst",
        "role": "admin",
        "is_active": True,
    }
    select_sql, select_params = conn.cursor_obj.calls[0]
    assert "WHERE (username = %(identifier)s OR email = %(identifier)s)" in select_sql
    assert select_params == {"identifier": "analyst@example.com"}
    update_sql, update_params = conn.cursor_obj.calls[1]
    assert "SET last_login_at = now(), updated_at = now()" in update_sql
    assert update_params == {"user_id": 9}


def test_load_current_user_from_request_returns_user_and_caches_session(monkeypatch):
    session_token = "session-token"
    csrf_token = "csrf-token"
    csrf_hash = hashlib.sha256(csrf_token.encode("utf-8")).hexdigest()
    conn = _Connection(
        rows=[
            {
                "user_id": 11,
                "username": "analyst",
                "display_name": "Analyst",
                "role": "admin",
                "is_active": True,
                "session_id": 21,
                "csrf_token_hash": csrf_hash,
            }
        ]
    )
    monkeypatch.setattr(dashboard_auth, "connect", lambda service: _Context(conn))
    request = _build_request(
        cookies={
            SETTINGS.dashboard_session_cookie_name: session_token,
            SETTINGS.dashboard_csrf_cookie_name: csrf_token,
        }
    )

    current_user = dashboard_auth.load_current_user_from_request(request)

    assert current_user.to_dict() == {
        "id": 11,
        "username": "analyst",
        "display_name": "Analyst",
        "role": "admin",
        "is_active": True,
    }
    assert request.state.auth_session == {
        "session_id": 21,
        "csrf_token_hash": csrf_hash,
    }
    sql, params = conn.cursor_obj.calls[0]
    assert "FROM identity.user_session us" in sql
    assert params["session_token_hash"] == hashlib.sha256(session_token.encode("utf-8")).hexdigest()

    cached_user = dashboard_auth.load_current_user_from_request(request)

    assert cached_user == current_user
    assert len(conn.cursor_obj.calls) == 1


def test_require_csrf_accepts_matching_cookie_header_and_stored_hash(monkeypatch):
    session_token = "session-token"
    csrf_token = "csrf-token"
    csrf_hash = hashlib.sha256(csrf_token.encode("utf-8")).hexdigest()
    conn = _Connection(
        rows=[
            {
                "user_id": 11,
                "username": "analyst",
                "display_name": "Analyst",
                "role": "admin",
                "is_active": True,
                "session_id": 21,
                "csrf_token_hash": csrf_hash,
            }
        ]
    )
    monkeypatch.setattr(dashboard_auth, "connect", lambda service: _Context(conn))
    request = _build_request(
        method="POST",
        path="/api/auth/logout",
        cookies={
            SETTINGS.dashboard_session_cookie_name: session_token,
            SETTINGS.dashboard_csrf_cookie_name: csrf_token,
        },
        headers={"X-CSRF-Token": csrf_token},
    )

    dashboard_auth.require_csrf(request)

    assert request.state.auth_session["csrf_token_hash"] == csrf_hash
    assert request.state.current_user.username == "analyst"


def test_require_csrf_rejects_when_stored_hash_does_not_match_header(monkeypatch):
    session_token = "session-token"
    csrf_token = "csrf-token"
    conn = _Connection(
        rows=[
            {
                "user_id": 11,
                "username": "analyst",
                "display_name": "Analyst",
                "role": "admin",
                "is_active": True,
                "session_id": 21,
                "csrf_token_hash": hashlib.sha256(b"other-token").hexdigest(),
            }
        ]
    )
    monkeypatch.setattr(dashboard_auth, "connect", lambda service: _Context(conn))
    request = _build_request(
        method="POST",
        path="/api/auth/logout",
        cookies={
            SETTINGS.dashboard_session_cookie_name: session_token,
            SETTINGS.dashboard_csrf_cookie_name: csrf_token,
        },
        headers={"X-CSRF-Token": csrf_token},
    )

    with pytest.raises(HTTPException) as exc_info:
        dashboard_auth.require_csrf(request)

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "csrf token required"


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
        lambda identifier, password, **kwargs: user,
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
            json={"identifier": "analyst@example.com", "password": "secret"},
        )

        assert login_response.status_code == 200
        assert login_response.cookies.get(SETTINGS.dashboard_session_cookie_name) == "session-token"
        assert login_response.cookies.get(SETTINGS.dashboard_csrf_cookie_name) == "csrf-token"
        assert events["audit"][0]["action"] == "login_success"
        assert events["audit"][0]["metadata"] == {"identifier": "analyst"}

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
        assert events["audit"][-1]["metadata"] == {"identifier": "analyst"}
        assert client.cookies.get(SETTINGS.dashboard_session_cookie_name) is None
        assert client.cookies.get(SETTINGS.dashboard_csrf_cookie_name) is None


def test_login_returns_429_when_recent_failures_exceed_limit(monkeypatch):
    calls = {"authenticate": 0}

    monkeypatch.setattr(dashboard_app, "apply_user_platform_schema", lambda: None, raising=False)
    monkeypatch.setattr(dashboard_app, "LOGIN_FAILURE_LIMIT", 3, raising=False)
    monkeypatch.setattr(dashboard_app, "count_recent_login_failures", lambda **kwargs: 3, raising=False)

    def fake_authenticate(*args, **kwargs):
        calls["authenticate"] += 1
        return None

    monkeypatch.setattr(dashboard_app, "authenticate_dashboard_user", fake_authenticate, raising=False)

    with TestClient(dashboard_app.create_app()) as client:
        response = client.post(
            "/api/auth/login",
            json={"identifier": "analyst", "password": "wrong"},
        )

    assert response.status_code == 429
    assert response.json()["detail"] == "too many login attempts"
    assert calls["authenticate"] == 0


def test_app_startup_propagates_user_schema_bootstrap_errors(monkeypatch):
    monkeypatch.setattr(
        dashboard_app,
        "apply_user_platform_schema",
        lambda: (_ for _ in ()).throw(OperationalError("db unavailable")),
        raising=False,
    )

    with pytest.raises(OperationalError, match="db unavailable"):
        with TestClient(dashboard_app.create_app()):
            pass
