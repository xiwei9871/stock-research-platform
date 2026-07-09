# Dashboard First-Party Auth Role Shell Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add first-party dashboard login, session identity, admin/user roles, and admin user management so the platform can move beyond temporary Nginx Basic Auth while keeping official research views read-only.

**Architecture:** Add a small Postgres-backed identity layer under `src/stock_research/dashboard/` with opaque cookie sessions, CSRF protection for authenticated writes, and admin-only user management APIs. Wrap the existing React `AppShell` in an auth-aware root that shows login before dashboard content and exposes a minimal admin user-management view only to `role=admin`; do not add personal watchlist/review features in this phase.

**Tech Stack:** Python 3.14/3.11-compatible stdlib crypto (`hashlib.pbkdf2_hmac`, `secrets`), FastAPI, psycopg/PostgreSQL, React, TypeScript, Vite, Vitest, Testing Library.

---

## Scope Boundary

Implement now:

- username/password login
- cookie session
- CSRF token cookie/header for authenticated writes
- `admin` and `user` roles
- admin user list/create/reset-password/enable/disable APIs
- auth-aware React root
- login view
- admin-only user management view
- deploy/runbook updates for first-party auth

Do not implement now:

- public registration
- SSO/OIDC
- personal watchlist
- personal review journal
- research queue / external delivery
- strategy, trading, signal, admission, scoring changes
- replacing `X-Dashboard-Write-Token`

## File Map

- `src/stock_research/dashboard/auth_schema.py`
  Responsibility: idempotently create `identity.user_account`, `identity.user_session`, and `identity.auth_audit_log`.
- `src/stock_research/dashboard/auth_models.py`
  Responsibility: small dataclasses/read-model helpers for current user and admin user responses.
- `src/stock_research/dashboard/auth_service.py`
  Responsibility: password hashing/verification, session creation, current-user lookup, logout, CSRF validation, and auth audit writes.
- `src/stock_research/dashboard/user_admin.py`
  Responsibility: admin-only create/list/reset/enable/disable user operations.
- `src/stock_research/dashboard/app.py`
  Responsibility: mount `/api/auth/*` and `/api/admin/users*`; optionally protect dashboard API routes when `STOCK_RESEARCH_DASHBOARD_AUTH_REQUIRED=true`.
- `src/stock_research/schema.py`
  Responsibility: call `apply_dashboard_auth_schema()` from the platform schema path.
- `src/stock_research/cli.py`
  Responsibility: add `dashboard-auth-init` and `dashboard-admin-create` operational commands.
- `src/stock_research/config.py`
  Responsibility: expose dashboard auth env settings.
- `dashboard/src/App.tsx`
  Responsibility: render the new auth-aware root instead of the bare shell.
- `dashboard/src/components/AppShell.tsx`
  Responsibility: remain the official dashboard shell; accept optional auth/user-management navigation hooks if needed.
- `dashboard/src/components/DashboardAuthRoot.tsx`
  Responsibility: fetch `/api/auth/me`, show login when unauthenticated, show official dashboard when authenticated, and show admin entry only for admins.
- `dashboard/src/components/LoginView.tsx`
  Responsibility: username/password form and login error state.
- `dashboard/src/components/UserManagementView.tsx`
  Responsibility: admin user list/create/reset/enable/disable controls.
- `dashboard/src/api/client.ts`
  Responsibility: add auth/admin API helpers with `credentials: 'include'` and CSRF header injection.
- `dashboard/src/api/types.ts`
  Responsibility: add `CurrentUser`, `AdminUser`, and auth/admin request/response types.
- `dashboard/src/styles.css`
  Responsibility: minimal auth shell/login/user-management styles consistent with the dashboard.
- `deploy/env/.env.dashboard.example`
  Responsibility: document auth-required, cookie-secure, session TTL, and bootstrap admin settings.
- `docs/platform_external_access_runbook.md`
  Responsibility: update external-access posture from Basic Auth-only staging to first-party auth-ready staging.

## Operational Model

- Session cookie: `stock_research_session`, `HttpOnly`, `SameSite=Lax`, `Secure` controlled by env.
- CSRF cookie: `stock_research_csrf`, readable by frontend, echoed as `X-CSRF-Token` for authenticated POST/PATCH/DELETE.
- Password hash format: `pbkdf2_sha256$<iterations>$<salt_b64>$<hash_b64>`.
- Default iterations: `260000`, configurable only by code constant for now.
- Auth enforcement env:
  - `STOCK_RESEARCH_DASHBOARD_AUTH_REQUIRED=false` by default for local/dev/test compatibility.
  - staging/external: set `STOCK_RESEARCH_DASHBOARD_AUTH_REQUIRED=true`.
- Existing `X-Dashboard-Write-Token` remains required for protected write/admin/replay operations where currently enforced. Login does not replace it.

## Task 0: Release Hygiene And Baseline

**Files:**
- Read: `outputs/research/platform_external_access_auth_proxy_smoke_v1/release_branch_plan.md`
- Read: `docs/superpowers/specs/2026-06-22-minimal-multi-user-watchlist-review-design.md`
- Read: this plan

- [ ] **Step 1: Confirm branch status**

Run:

```bash
rtk git status --short
rtk git rev-parse --abbrev-ref HEAD
rtk git rev-parse HEAD
```

Expected: working tree is dirty. Do not revert unrelated user changes.

- [ ] **Step 2: Decide execution branch**

Recommended:

```bash
git switch -c platform-auth-role-shell-v1 583853a598a58997fd26f3d2490a6a247f659e8b
```

If continuing in the current worktree, restrict edits to the files listed in this plan and do not touch paused business-line files.

## Task 1: Auth Schema And Settings

**Files:**
- Create: `src/stock_research/dashboard/auth_schema.py`
- Modify: `src/stock_research/config.py`
- Modify: `src/stock_research/schema.py`
- Test: `tests/test_dashboard_auth_schema.py`

- [ ] **Step 1: Write failing schema/settings tests**

Create `tests/test_dashboard_auth_schema.py`:

```python
from stock_research.dashboard import auth_schema
from stock_research.config import Settings


class _Cursor:
    def __init__(self):
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        self.calls.append((sql, params))


class _Connection:
    def __init__(self):
        self.cursor_obj = _Cursor()

    def cursor(self):
        return self.cursor_obj


class _Context:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self.conn

    def __exit__(self, exc_type, exc, tb):
        return False


def test_apply_dashboard_auth_schema_creates_identity_tables(monkeypatch):
    conn = _Connection()
    monkeypatch.setattr(auth_schema, "connect", lambda service: _Context(conn))

    auth_schema.apply_dashboard_auth_schema()

    sql = conn.cursor_obj.calls[0][0]
    assert "CREATE SCHEMA IF NOT EXISTS identity" in sql
    assert "CREATE TABLE IF NOT EXISTS identity.user_account" in sql
    assert "CREATE UNIQUE INDEX IF NOT EXISTS uq_identity_user_account_username" in sql
    assert "CREATE TABLE IF NOT EXISTS identity.user_session" in sql
    assert "CREATE TABLE IF NOT EXISTS identity.auth_audit_log" in sql
    assert "role IN ('admin', 'user')" in sql


def test_dashboard_auth_settings_defaults_are_local_dev_safe(monkeypatch):
    monkeypatch.delenv("STOCK_RESEARCH_DASHBOARD_AUTH_REQUIRED", raising=False)
    settings = Settings()

    assert settings.dashboard_auth_required is False
    assert settings.dashboard_session_cookie == "stock_research_session"
    assert settings.dashboard_csrf_cookie == "stock_research_csrf"
    assert settings.dashboard_session_ttl_seconds == 60 * 60 * 12
```

- [ ] **Step 2: Run tests and confirm failure**

Run:

```bash
rtk .venv/bin/pytest tests/test_dashboard_auth_schema.py -q
```

Expected: fails because `auth_schema` and settings fields do not exist.

- [ ] **Step 3: Implement schema/settings**

Create `src/stock_research/dashboard/auth_schema.py`:

```python
from stock_research.config import SETTINGS
from stock_research.db import connect


DASHBOARD_AUTH_SCHEMA_SQL = """
CREATE SCHEMA IF NOT EXISTS identity;

CREATE TABLE IF NOT EXISTS identity.user_account (
    user_id text PRIMARY KEY,
    username text NOT NULL,
    display_name text NOT NULL DEFAULT '',
    role text NOT NULL CHECK (role IN ('admin', 'user')),
    password_hash text NOT NULL,
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    last_login_at timestamptz,
    password_updated_at timestamptz NOT NULL DEFAULT now(),
    disabled_at timestamptz,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_identity_user_account_username
    ON identity.user_account (lower(username));

CREATE TABLE IF NOT EXISTS identity.user_session (
    session_id text PRIMARY KEY,
    user_id text NOT NULL REFERENCES identity.user_account(user_id),
    session_token_hash text NOT NULL,
    csrf_token_hash text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    revoked_at timestamptz,
    user_agent text NOT NULL DEFAULT '',
    ip_address text NOT NULL DEFAULT '',
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_identity_user_session_user_id
    ON identity.user_session (user_id, created_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS uq_identity_user_session_token_hash
    ON identity.user_session (session_token_hash);

CREATE TABLE IF NOT EXISTS identity.auth_audit_log (
    audit_id text PRIMARY KEY,
    action text NOT NULL,
    actor_user_id text NOT NULL DEFAULT '',
    target_user_id text NOT NULL DEFAULT '',
    username text NOT NULL DEFAULT '',
    ip_address text NOT NULL DEFAULT '',
    user_agent text NOT NULL DEFAULT '',
    status text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb
);
"""


def apply_dashboard_auth_schema(service: str = SETTINGS.research_service) -> None:
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute(DASHBOARD_AUTH_SCHEMA_SQL)
```

Modify `src/stock_research/config.py`:

```python
def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return default


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    return int(raw)
```

Add fields to `Settings`:

```python
dashboard_auth_required: bool = field(default_factory=lambda: _env_bool("STOCK_RESEARCH_DASHBOARD_AUTH_REQUIRED", False))
dashboard_cookie_secure: bool = field(default_factory=lambda: _env_bool("STOCK_RESEARCH_DASHBOARD_COOKIE_SECURE", False))
dashboard_session_cookie: str = "stock_research_session"
dashboard_csrf_cookie: str = "stock_research_csrf"
dashboard_session_ttl_seconds: int = field(default_factory=lambda: _env_int("STOCK_RESEARCH_DASHBOARD_SESSION_TTL_SECONDS", 60 * 60 * 12))
```

Modify `src/stock_research/schema.py` to import and call:

```python
from stock_research.dashboard.auth_schema import DASHBOARD_AUTH_SCHEMA_SQL
```

and include `DASHBOARD_AUTH_SCHEMA_SQL` in the existing schema apply path. If the file uses separate apply functions, add:

```python
def apply_dashboard_auth_schema(service: str = SETTINGS.research_service) -> None:
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute(DASHBOARD_AUTH_SCHEMA_SQL)
```

- [ ] **Step 4: Run tests**

Run:

```bash
rtk .venv/bin/pytest tests/test_dashboard_auth_schema.py tests/test_schema.py -q
```

Expected: pass.

## Task 2: Password, Session, CSRF, And Audit Service

**Files:**
- Create: `src/stock_research/dashboard/auth_models.py`
- Create: `src/stock_research/dashboard/auth_service.py`
- Test: `tests/test_dashboard_auth_service.py`

- [ ] **Step 1: Write failing auth service tests**

Create `tests/test_dashboard_auth_service.py`:

```python
import re

import pytest

from stock_research.dashboard import auth_service
from stock_research.dashboard.auth_models import CurrentUser


def test_password_hash_round_trip_and_wrong_password_rejected():
    password_hash = auth_service.hash_password("secret-password")

    assert password_hash.startswith("pbkdf2_sha256$")
    assert auth_service.verify_password("secret-password", password_hash) is True
    assert auth_service.verify_password("wrong-password", password_hash) is False


def test_generated_tokens_are_urlsafe_and_not_equal():
    first = auth_service.generate_token()
    second = auth_service.generate_token()

    assert first != second
    assert re.fullmatch(r"[A-Za-z0-9_-]+", first)


def test_current_user_read_model_uses_whitelisted_fields_only():
    user = CurrentUser(user_id="user:1", username="xiwei", display_name="Xiwei", role="admin", is_active=True)

    assert auth_service.current_user_read_model(user) == {
        "user_id": "user:1",
        "username": "xiwei",
        "display_name": "Xiwei",
        "role": "admin",
        "is_active": True,
    }


def test_csrf_validation_rejects_missing_or_mismatched_token():
    with pytest.raises(PermissionError, match="csrf_token_required"):
        auth_service.validate_csrf(csrf_cookie="", csrf_header="")

    with pytest.raises(PermissionError, match="csrf_token_mismatch"):
        auth_service.validate_csrf(csrf_cookie="abc", csrf_header="def")

    assert auth_service.validate_csrf(csrf_cookie="abc", csrf_header="abc") is None
```

- [ ] **Step 2: Run test and confirm failure**

Run:

```bash
rtk .venv/bin/pytest tests/test_dashboard_auth_service.py -q
```

Expected: fails because modules/functions do not exist.

- [ ] **Step 3: Implement auth models/service**

Create `src/stock_research/dashboard/auth_models.py`:

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class CurrentUser:
    user_id: str
    username: str
    display_name: str
    role: str
    is_active: bool
```

Create `src/stock_research/dashboard/auth_service.py`:

```python
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from stock_research.config import SETTINGS
from stock_research.dashboard.auth_models import CurrentUser
from stock_research.db import connect, fetch_all

PASSWORD_ITERATIONS = 260_000


def generate_token() -> str:
    return secrets.token_urlsafe(32)


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _unb64(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS)
    return f"pbkdf2_sha256${PASSWORD_ITERATIONS}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        algorithm, iterations_raw, salt_raw, digest_raw = password_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        iterations = int(iterations_raw)
        expected = _unb64(digest_raw)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), _unb64(salt_raw), iterations)
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def validate_csrf(*, csrf_cookie: str, csrf_header: str) -> None:
    if not csrf_cookie or not csrf_header:
        raise PermissionError("csrf_token_required")
    if not hmac.compare_digest(csrf_cookie, csrf_header):
        raise PermissionError("csrf_token_mismatch")


def current_user_read_model(user: CurrentUser) -> dict:
    return {
        "user_id": user.user_id,
        "username": user.username,
        "display_name": user.display_name,
        "role": user.role,
        "is_active": user.is_active,
    }
```

Add DB-backed functions after the tested helpers:

```python
def authenticate_user(username: str, password: str, service: str = SETTINGS.research_service) -> CurrentUser:
    rows = fetch_all(
        """
        SELECT user_id, username, display_name, role, is_active, password_hash
        FROM identity.user_account
        WHERE lower(username) = lower(%s)
        LIMIT 1
        """,
        (username,),
        service=service,
    )
    if not rows:
        raise PermissionError("invalid_credentials")
    row = dict(rows[0])
    if not row["is_active"]:
        raise PermissionError("user_disabled")
    if not verify_password(password, str(row["password_hash"])):
        raise PermissionError("invalid_credentials")
    return CurrentUser(
        user_id=str(row["user_id"]),
        username=str(row["username"]),
        display_name=str(row["display_name"] or ""),
        role=str(row["role"]),
        is_active=bool(row["is_active"]),
    )


def create_session(user: CurrentUser, *, user_agent: str = "", ip_address: str = "", service: str = SETTINGS.research_service) -> dict:
    session_token = generate_token()
    csrf_token = generate_token()
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=SETTINGS.dashboard_session_ttl_seconds)
    session_id = f"dashboard_session:{uuid4()}"
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO identity.user_session (
                    session_id, user_id, session_token_hash, csrf_token_hash,
                    expires_at, user_agent, ip_address
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (session_id, user.user_id, token_hash(session_token), token_hash(csrf_token), expires_at, user_agent, ip_address),
            )
            cur.execute("UPDATE identity.user_account SET last_login_at = now() WHERE user_id = %s", (user.user_id,))
    return {"session_id": session_id, "session_token": session_token, "csrf_token": csrf_token, "expires_at": expires_at}
```

- [ ] **Step 4: Run tests**

Run:

```bash
rtk .venv/bin/pytest tests/test_dashboard_auth_service.py -q
```

Expected: pass.

## Task 3: Auth API Routes

**Files:**
- Modify: `src/stock_research/dashboard/app.py`
- Test: `tests/test_dashboard_auth_api.py`

- [ ] **Step 1: Write failing route tests**

Create `tests/test_dashboard_auth_api.py`:

```python
from fastapi.testclient import TestClient

from stock_research.dashboard import app as dashboard_app
from stock_research.dashboard.auth_models import CurrentUser


def test_auth_me_returns_401_when_not_logged_in(monkeypatch):
    client = TestClient(dashboard_app.create_app())

    response = client.get("/api/auth/me")

    assert response.status_code == 401
    assert response.json()["detail"] == "not_authenticated"


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


def test_logout_clears_session_cookie(monkeypatch):
    monkeypatch.setattr(dashboard_app, "revoke_session", lambda session_token: None)
    client = TestClient(dashboard_app.create_app())

    response = client.post("/api/auth/logout", cookies={"stock_research_session": "session-token"})

    assert response.status_code == 200
    assert response.json() == {"status": "logged_out"}
    assert "stock_research_session=" in response.headers["set-cookie"]
```

- [ ] **Step 2: Run tests and confirm failure**

Run:

```bash
rtk .venv/bin/pytest tests/test_dashboard_auth_api.py -q
```

Expected: fails because auth routes are missing.

- [ ] **Step 3: Implement minimal auth routes**

Modify imports in `src/stock_research/dashboard/app.py`:

```python
from pydantic import BaseModel
from fastapi.responses import JSONResponse
from stock_research.config import SETTINGS
from stock_research.dashboard.auth_service import (
    authenticate_user,
    create_session,
    current_user_read_model,
    load_current_user_from_session,
    revoke_session,
)
```

Add payload models near helper functions:

```python
class LoginPayload(BaseModel):
    username: str
    password: str
```

Add cookie helper:

```python
def _set_auth_cookies(response: JSONResponse, session_token: str, csrf_token: str) -> None:
    response.set_cookie(
        SETTINGS.dashboard_session_cookie,
        session_token,
        httponly=True,
        secure=SETTINGS.dashboard_cookie_secure,
        samesite="lax",
        max_age=SETTINGS.dashboard_session_ttl_seconds,
        path="/",
    )
    response.set_cookie(
        SETTINGS.dashboard_csrf_cookie,
        csrf_token,
        httponly=False,
        secure=SETTINGS.dashboard_cookie_secure,
        samesite="lax",
        max_age=SETTINGS.dashboard_session_ttl_seconds,
        path="/",
    )
```

Add routes inside `create_app()` before other API routes:

```python
    @app.get("/api/auth/me")
    def auth_me(request: Request):
        session_token = request.cookies.get(SETTINGS.dashboard_session_cookie, "")
        user = load_current_user_from_session(session_token)
        if user is None:
            raise HTTPException(status_code=401, detail="not_authenticated")
        return {"user": current_user_read_model(user)}

    @app.post("/api/auth/login")
    def auth_login(payload: LoginPayload, request: Request):
        try:
            user = authenticate_user(payload.username, payload.password)
        except PermissionError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        session = create_session(
            user,
            user_agent=str(request.headers.get("user-agent") or ""),
            ip_address=str(request.client.host if request.client else ""),
        )
        response = JSONResponse({"user": current_user_read_model(user)})
        _set_auth_cookies(response, str(session["session_token"]), str(session["csrf_token"]))
        return response

    @app.post("/api/auth/logout")
    def auth_logout(request: Request):
        session_token = request.cookies.get(SETTINGS.dashboard_session_cookie, "")
        if session_token:
            revoke_session(session_token)
        response = JSONResponse({"status": "logged_out"})
        response.delete_cookie(SETTINGS.dashboard_session_cookie, path="/")
        response.delete_cookie(SETTINGS.dashboard_csrf_cookie, path="/")
        return response
```

- [ ] **Step 4: Run tests**

Run:

```bash
rtk .venv/bin/pytest tests/test_dashboard_auth_api.py tests/test_dashboard_app.py -q
```

Expected: pass.

## Task 4: Admin User Management API

**Files:**
- Create: `src/stock_research/dashboard/user_admin.py`
- Modify: `src/stock_research/dashboard/app.py`
- Test: `tests/test_dashboard_user_admin.py`

- [ ] **Step 1: Write failing admin API tests**

Create `tests/test_dashboard_user_admin.py`:

```python
from fastapi.testclient import TestClient

from stock_research.dashboard import app as dashboard_app
from stock_research.dashboard.auth_models import CurrentUser


def test_admin_users_requires_admin(monkeypatch):
    monkeypatch.setattr(
        dashboard_app,
        "load_current_user_from_session",
        lambda token: CurrentUser("user:2", "regular", "Regular", "user", True),
    )
    client = TestClient(dashboard_app.create_app())

    response = client.get("/api/admin/users", cookies={"stock_research_session": "session"})

    assert response.status_code == 403
    assert response.json()["detail"] == "admin_required"


def test_admin_can_list_users(monkeypatch):
    monkeypatch.setattr(
        dashboard_app,
        "load_current_user_from_session",
        lambda token: CurrentUser("user:1", "admin", "Admin", "admin", True),
    )
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
    monkeypatch.setattr(
        dashboard_app,
        "load_current_user_from_session",
        lambda token: CurrentUser("user:1", "admin", "Admin", "admin", True),
    )
    client = TestClient(dashboard_app.create_app())

    response = client.post(
        "/api/admin/users",
        cookies={"stock_research_session": "session", "stock_research_csrf": "csrf"},
        json={"username": "new", "password": "secret", "role": "user"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "csrf_token_required"
```

- [ ] **Step 2: Run tests and confirm failure**

Run:

```bash
rtk .venv/bin/pytest tests/test_dashboard_user_admin.py -q
```

Expected: fails because user admin module/routes are missing.

- [ ] **Step 3: Implement admin service and routes**

Create `src/stock_research/dashboard/user_admin.py` with:

```python
from __future__ import annotations

from uuid import uuid4

from stock_research.config import SETTINGS
from stock_research.dashboard.auth_service import hash_password
from stock_research.db import connect, fetch_all

ALLOWED_ROLES = {"admin", "user"}


def admin_user_read_model(row: dict) -> dict:
    return {
        "user_id": str(row["user_id"]),
        "username": str(row["username"]),
        "display_name": str(row.get("display_name") or ""),
        "role": str(row["role"]),
        "is_active": bool(row["is_active"]),
        "created_at": str(row.get("created_at") or ""),
        "last_login_at": str(row.get("last_login_at") or ""),
    }


def list_admin_users(service: str = SETTINGS.research_service) -> list[dict]:
    rows = fetch_all(
        """
        SELECT user_id, username, display_name, role, is_active, created_at, last_login_at
        FROM identity.user_account
        ORDER BY lower(username)
        """,
        service=service,
    )
    return [admin_user_read_model(dict(row)) for row in rows]


def create_dashboard_user(username: str, password: str, *, role: str = "user", display_name: str = "", service: str = SETTINGS.research_service) -> dict:
    if role not in ALLOWED_ROLES:
        raise ValueError("invalid_role")
    user_id = f"dashboard_user:{uuid4()}"
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO identity.user_account (user_id, username, display_name, role, password_hash)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING user_id, username, display_name, role, is_active, created_at, last_login_at
                """,
                (user_id, username, display_name, role, hash_password(password)),
            )
            row = cur.fetchone()
    return admin_user_read_model(dict(row))
```

Add admin route dependencies in `app.py`:

```python
def _current_user_or_401(request: Request):
    session_token = request.cookies.get(SETTINGS.dashboard_session_cookie, "")
    user = load_current_user_from_session(session_token)
    if user is None:
        raise HTTPException(status_code=401, detail="not_authenticated")
    return user


def _admin_user_or_403(request: Request):
    user = _current_user_or_401(request)
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="admin_required")
    return user


def _require_csrf(request: Request) -> None:
    try:
        validate_csrf(
            csrf_cookie=request.cookies.get(SETTINGS.dashboard_csrf_cookie, ""),
            csrf_header=str(request.headers.get("x-csrf-token") or request.headers.get("X-CSRF-Token") or ""),
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
```

Add routes:

```python
    @app.get("/api/admin/users")
    def admin_users(request: Request):
        _admin_user_or_403(request)
        return {"items": list_admin_users()}

    @app.post("/api/admin/users")
    def admin_create_user(payload: AdminCreateUserPayload, request: Request):
        _admin_user_or_403(request)
        _require_csrf(request)
        return {"user": create_dashboard_user(payload.username, payload.password, role=payload.role, display_name=payload.display_name)}
```

Also add reset/disable/enable routes in the same style:

- `POST /api/admin/users/{user_id}/reset-password`
- `POST /api/admin/users/{user_id}/disable`
- `POST /api/admin/users/{user_id}/enable`

- [ ] **Step 4: Run tests**

Run:

```bash
rtk .venv/bin/pytest tests/test_dashboard_user_admin.py tests/test_dashboard_auth_api.py -q
```

Expected: pass.

## Task 5: Optional API Auth Enforcement Middleware

**Files:**
- Modify: `src/stock_research/dashboard/app.py`
- Test: `tests/test_dashboard_auth_required.py`

- [ ] **Step 1: Write failing auth-required tests**

Create `tests/test_dashboard_auth_required.py`:

```python
from fastapi.testclient import TestClient

from stock_research.dashboard import app as dashboard_app
from stock_research.dashboard.auth_models import CurrentUser


def test_dashboard_api_allows_reads_when_auth_not_required(monkeypatch):
    monkeypatch.setenv("STOCK_RESEARCH_DASHBOARD_AUTH_REQUIRED", "false")
    monkeypatch.setattr(dashboard_app, "load_platform_summary", lambda **kwargs: {"latest_market_date": "2026-07-08"})
    client = TestClient(dashboard_app.create_app())

    response = client.get("/api/platform/summary")

    assert response.status_code == 200


def test_dashboard_api_rejects_reads_when_auth_required_and_missing_session(monkeypatch):
    monkeypatch.setenv("STOCK_RESEARCH_DASHBOARD_AUTH_REQUIRED", "true")
    client = TestClient(dashboard_app.create_app())

    response = client.get("/api/platform/summary")

    assert response.status_code == 401
    assert response.json()["detail"] == "not_authenticated"


def test_dashboard_api_allows_auth_routes_when_auth_required(monkeypatch):
    monkeypatch.setenv("STOCK_RESEARCH_DASHBOARD_AUTH_REQUIRED", "true")
    client = TestClient(dashboard_app.create_app())

    response = client.get("/api/auth/me")

    assert response.status_code == 401
    assert response.json()["detail"] == "not_authenticated"
```

- [ ] **Step 2: Implement middleware**

Add middleware after request-id middleware:

```python
AUTH_EXEMPT_PATHS = {"/api/auth/login", "/api/auth/logout", "/api/auth/me"}


@app.middleware("http")
async def dashboard_auth_required_middleware(request: Request, call_next):
    if SETTINGS.dashboard_auth_required and request.url.path.startswith("/api/") and request.url.path not in AUTH_EXEMPT_PATHS:
        session_token = request.cookies.get(SETTINGS.dashboard_session_cookie, "")
        if load_current_user_from_session(session_token) is None:
            raise HTTPException(status_code=401, detail="not_authenticated")
    return await call_next(request)
```

If raising `HTTPException` from middleware does not serialize as expected, return `JSONResponse({"detail": "not_authenticated"}, status_code=401)` directly.

- [ ] **Step 3: Run tests**

Run:

```bash
rtk .venv/bin/pytest tests/test_dashboard_auth_required.py tests/test_dashboard_app.py -q
```

Expected: pass.

## Task 6: Frontend Auth Client And Login Root

**Files:**
- Modify: `dashboard/src/api/types.ts`
- Modify: `dashboard/src/api/client.ts`
- Create: `dashboard/src/components/DashboardAuthRoot.tsx`
- Create: `dashboard/src/components/LoginView.tsx`
- Modify: `dashboard/src/App.tsx`
- Test: `dashboard/tests/auth-root.test.tsx`
- Test: `dashboard/tests/client.test.ts`

- [ ] **Step 1: Write failing frontend tests**

Create `dashboard/tests/auth-root.test.tsx`:

```tsx
import '@testing-library/jest-dom/vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { DashboardAuthRoot } from '../src/components/DashboardAuthRoot';

const apiMocks = vi.hoisted(() => ({
  fetchCurrentUser: vi.fn(),
  loginDashboardUser: vi.fn(),
  logoutDashboardUser: vi.fn()
}));

vi.mock('../src/api/client', () => apiMocks);
vi.mock('../src/components/AppShell', () => ({ AppShell: () => <div>Official Dashboard</div> }));

describe('DashboardAuthRoot', () => {
  it('shows login when current user is not authenticated', async () => {
    apiMocks.fetchCurrentUser.mockRejectedValueOnce(new Error('not_authenticated'));

    render(<DashboardAuthRoot />);

    expect(await screen.findByRole('heading', { name: '登录' })).toBeVisible();
  });

  it('renders official dashboard after login succeeds', async () => {
    apiMocks.fetchCurrentUser.mockRejectedValueOnce(new Error('not_authenticated'));
    apiMocks.loginDashboardUser.mockResolvedValueOnce({
      user: { user_id: 'user:1', username: 'admin', display_name: 'Admin', role: 'admin', is_active: true }
    });

    render(<DashboardAuthRoot />);
    fireEvent.change(await screen.findByLabelText('用户名'), { target: { value: 'admin' } });
    fireEvent.change(screen.getByLabelText('密码'), { target: { value: 'secret' } });
    fireEvent.click(screen.getByRole('button', { name: '登录' }));

    expect(await screen.findByText('Official Dashboard')).toBeVisible();
  });
});
```

- [ ] **Step 2: Implement frontend auth client**

Add types:

```ts
export type CurrentUser = {
  user_id: string;
  username: string;
  display_name: string;
  role: 'admin' | 'user';
  is_active: boolean;
};

export type AuthMeResponse = { user: CurrentUser };
export type LoginRequest = { username: string; password: string };
export type LoginResponse = { user: CurrentUser };
```

Add helpers in `client.ts`:

```ts
function csrfTokenFromCookie() {
  return document.cookie
    .split(';')
    .map((part) => part.trim())
    .find((part) => part.startsWith('stock_research_csrf='))
    ?.split('=')
    .slice(1)
    .join('=') ?? '';
}

export async function fetchCurrentUser(): Promise<AuthMeResponse> {
  return getJson('/api/auth/me', { credentials: 'include' });
}

export async function loginDashboardUser(request: LoginRequest): Promise<LoginResponse> {
  return postJson('/api/auth/login', request, { credentials: 'include' });
}

export async function logoutDashboardUser(): Promise<{ status: string }> {
  return postJson('/api/auth/logout', {}, { credentials: 'include', csrfToken: csrfTokenFromCookie() });
}
```

If current `getJson`/`postJson` do not support options, extend them in place with default-compatible optional args.

- [ ] **Step 3: Implement `LoginView` and `DashboardAuthRoot`**

`LoginView.tsx`:

```tsx
type LoginViewProps = {
  error: string;
  onSubmit: (username: string, password: string) => void;
};

export function LoginView({ error, onSubmit }: LoginViewProps) {
  return (
    <main className="login-shell">
      <section className="login-panel">
        <h1>登录</h1>
        <form
          onSubmit={(event) => {
            event.preventDefault();
            const form = new FormData(event.currentTarget);
            onSubmit(String(form.get('username') ?? ''), String(form.get('password') ?? ''));
          }}
        >
          <label>
            用户名
            <input name="username" autoComplete="username" />
          </label>
          <label>
            密码
            <input name="password" type="password" autoComplete="current-password" />
          </label>
          {error ? <p role="alert">{error}</p> : null}
          <button type="submit">登录</button>
        </form>
      </section>
    </main>
  );
}
```

`DashboardAuthRoot.tsx`:

```tsx
import { useEffect, useState } from 'react';
import { fetchCurrentUser, loginDashboardUser } from '../api/client';
import type { CurrentUser } from '../api/types';
import { AppShell } from './AppShell';
import { LoginView } from './LoginView';

export function DashboardAuthRoot() {
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    fetchCurrentUser()
      .then((payload) => setUser(payload.user))
      .catch(() => setUser(null))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <main className="login-shell">加载中</main>;
  if (!user) {
    return (
      <LoginView
        error={error}
        onSubmit={(username, password) => {
          setError('');
          loginDashboardUser({ username, password })
            .then((payload) => setUser(payload.user))
            .catch((err) => setError(`登录失败：${err instanceof Error ? err.message : 'unknown'}`));
        }}
      />
    );
  }

  return <AppShell currentUser={user} />;
}
```

Modify `App.tsx`:

```tsx
import { DashboardAuthRoot } from './components/DashboardAuthRoot';

export function App() {
  return <DashboardAuthRoot />;
}
```

- [ ] **Step 4: Run frontend tests**

Run:

```bash
rtk pnpm --dir dashboard test -- dashboard/tests/auth-root.test.tsx dashboard/tests/client.test.ts
```

Expected: pass.

## Task 7: Admin User Management UI

**Files:**
- Create: `dashboard/src/components/UserManagementView.tsx`
- Modify: `dashboard/src/components/AppShell.tsx`
- Modify: `dashboard/src/api/client.ts`
- Modify: `dashboard/src/api/types.ts`
- Test: `dashboard/tests/user-management-view.test.tsx`

- [ ] **Step 1: Write failing admin view tests**

Create `dashboard/tests/user-management-view.test.tsx`:

```tsx
import '@testing-library/jest-dom/vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { UserManagementView } from '../src/components/UserManagementView';

const apiMocks = vi.hoisted(() => ({
  fetchAdminUsers: vi.fn(),
  createAdminUser: vi.fn()
}));

vi.mock('../src/api/client', () => apiMocks);

describe('UserManagementView', () => {
  it('lists users and creates a user', async () => {
    apiMocks.fetchAdminUsers.mockResolvedValueOnce({
      items: [{ user_id: 'user:1', username: 'admin', display_name: 'Admin', role: 'admin', is_active: true }]
    });
    apiMocks.createAdminUser.mockResolvedValueOnce({
      user: { user_id: 'user:2', username: 'analyst', display_name: 'Analyst', role: 'user', is_active: true }
    });

    render(<UserManagementView />);

    expect(await screen.findByText('admin')).toBeVisible();
    fireEvent.change(screen.getByLabelText('新用户名'), { target: { value: 'analyst' } });
    fireEvent.change(screen.getByLabelText('初始密码'), { target: { value: 'secret123' } });
    fireEvent.click(screen.getByRole('button', { name: '创建用户' }));

    expect(apiMocks.createAdminUser).toHaveBeenCalledWith({
      username: 'analyst',
      password: 'secret123',
      role: 'user',
      display_name: ''
    });
  });
});
```

- [ ] **Step 2: Implement admin client helpers and view**

Add types:

```ts
export type AdminUser = CurrentUser & {
  created_at?: string;
  last_login_at?: string;
};

export type AdminUsersResponse = { items: AdminUser[] };
export type CreateAdminUserRequest = { username: string; password: string; role: 'admin' | 'user'; display_name: string };
export type CreateAdminUserResponse = { user: AdminUser };
```

Add client helpers:

```ts
export async function fetchAdminUsers(): Promise<AdminUsersResponse> {
  return getJson('/api/admin/users', { credentials: 'include' });
}

export async function createAdminUser(request: CreateAdminUserRequest): Promise<CreateAdminUserResponse> {
  return postJson('/api/admin/users', request, { credentials: 'include', csrfToken: csrfTokenFromCookie() });
}
```

Create `UserManagementView.tsx` with a minimal list and create form. Keep reset/enable/disable buttons in the same component after API helpers exist.

- [ ] **Step 3: Add admin-only navigation**

Modify `AppShell` props:

```tsx
type AppShellProps = {
  currentUser?: CurrentUser;
};

export function AppShell({ currentUser }: AppShellProps) {
  const isAdmin = currentUser?.role === 'admin';
  ...
}
```

Only render `用户管理` nav item when `isAdmin` is true.

- [ ] **Step 4: Run frontend tests**

Run:

```bash
rtk pnpm --dir dashboard test -- dashboard/tests/user-management-view.test.tsx dashboard/tests/app-shell.test.tsx
```

Expected: pass after updating existing AppShell mocks/types.

## Task 8: CLI Bootstrap Commands

**Files:**
- Modify: `src/stock_research/cli.py`
- Test: `tests/test_dashboard_auth_cli.py`

- [ ] **Step 1: Write failing CLI tests**

Create `tests/test_dashboard_auth_cli.py`:

```python
from stock_research import cli


def test_dashboard_auth_init_command_applies_schema(monkeypatch, capsys):
    called = []
    monkeypatch.setattr(cli, "apply_dashboard_auth_schema", lambda: called.append(True))

    cli.main(["dashboard-auth-init"])

    assert called == [True]
    assert "dashboard_auth_schema_applied" in capsys.readouterr().out


def test_dashboard_admin_create_uses_service(monkeypatch, capsys):
    captured = {}
    monkeypatch.setattr(
        cli,
        "create_dashboard_user",
        lambda username, password, role, display_name: captured.update(
            {"username": username, "password": password, "role": role, "display_name": display_name}
        )
        or {"user_id": "user:1", "username": username},
    )

    cli.main(["dashboard-admin-create", "--username", "admin", "--password", "secret", "--role", "admin"])

    assert captured["username"] == "admin"
    assert captured["role"] == "admin"
    assert "dashboard_admin_user_created" in capsys.readouterr().out
```

- [ ] **Step 2: Add CLI commands**

Add imports:

```python
from stock_research.dashboard.auth_schema import apply_dashboard_auth_schema
from stock_research.dashboard.user_admin import create_dashboard_user
```

Add parsers:

```python
subparsers.add_parser("dashboard-auth-init")
dashboard_admin_create = subparsers.add_parser("dashboard-admin-create")
dashboard_admin_create.add_argument("--username", required=True)
dashboard_admin_create.add_argument("--password", required=True)
dashboard_admin_create.add_argument("--role", choices=["admin", "user"], default="admin")
dashboard_admin_create.add_argument("--display-name", default="")
```

Add handlers:

```python
elif args.command == "dashboard-auth-init":
    apply_dashboard_auth_schema()
    print("dashboard_auth_schema_applied")
elif args.command == "dashboard-admin-create":
    user = create_dashboard_user(args.username, args.password, role=args.role, display_name=args.display_name)
    print(f"dashboard_admin_user_created|{user['user_id']}|{user['username']}")
```

- [ ] **Step 3: Run tests**

Run:

```bash
rtk .venv/bin/pytest tests/test_dashboard_auth_cli.py -q
```

Expected: pass.

## Task 9: Deploy Docs And Env

**Files:**
- Modify: `deploy/env/.env.dashboard.example`
- Modify: `docs/platform_external_access_runbook.md`
- Modify: `docs/platform_external_access_auth_proxy_smoke_runbook.md`
- Test: `tests/test_platform_external_access_deploy_docs.py`

- [ ] **Step 1: Extend deploy docs test**

Add assertions:

```python
def test_external_access_docs_include_first_party_auth_settings():
    env = _read("deploy/env/.env.dashboard.example")
    runbook = _read("docs/platform_external_access_runbook.md")

    assert "STOCK_RESEARCH_DASHBOARD_AUTH_REQUIRED=true" in env
    assert "STOCK_RESEARCH_DASHBOARD_COOKIE_SECURE=true" in env
    assert "STOCK_RESEARCH_DASHBOARD_SESSION_TTL_SECONDS" in env
    assert "dashboard-auth-init" in runbook
    assert "dashboard-admin-create" in runbook
    assert "first-party auth" in runbook
```

- [ ] **Step 2: Update env/runbooks**

Add to env example:

```dotenv
STOCK_RESEARCH_DASHBOARD_AUTH_REQUIRED=true
STOCK_RESEARCH_DASHBOARD_COOKIE_SECURE=true
STOCK_RESEARCH_DASHBOARD_SESSION_TTL_SECONDS=43200
```

Add runbook setup:

```bash
stock-research dashboard-auth-init
stock-research dashboard-admin-create --username admin --password '<local-secret>' --role admin
```

Clarify:

- Basic Auth can be removed only after first-party auth is verified.
- `X-Dashboard-Write-Token` remains required for guarded writes.
- Official research views are still read-only for regular users.

- [ ] **Step 3: Run docs tests**

Run:

```bash
rtk .venv/bin/pytest tests/test_platform_external_access_deploy_docs.py -q
```

Expected: pass.

## Task 10: Verification And Release Gate

**Files:**
- No new files unless fixing defects found by tests.

- [ ] **Step 1: Backend verification**

Run:

```bash
rtk .venv/bin/pytest \
  tests/test_dashboard_auth_schema.py \
  tests/test_dashboard_auth_service.py \
  tests/test_dashboard_auth_api.py \
  tests/test_dashboard_user_admin.py \
  tests/test_dashboard_auth_required.py \
  tests/test_dashboard_auth_cli.py \
  tests/test_dashboard_api_guardrails.py \
  tests/test_dashboard_observability.py \
  tests/test_dashboard_readiness.py \
  tests/test_platform_external_access_deploy_docs.py \
  -q
```

Expected: all pass.

- [ ] **Step 2: Frontend verification**

Run:

```bash
rtk pnpm --dir dashboard test -- \
  dashboard/tests/auth-root.test.tsx \
  dashboard/tests/user-management-view.test.tsx \
  dashboard/tests/client.test.ts \
  dashboard/tests/app-shell.test.tsx
```

Expected: auth/admin tests pass. If unrelated paused-business tests fail in full test suite, record them separately and do not fix them in this auth branch.

- [ ] **Step 3: Build**

Run:

```bash
rtk pnpm --dir dashboard build
```

Expected: build exits 0. Existing Vite chunk warning may remain non-blocking.

- [ ] **Step 4: Manual staging smoke**

With staging env:

```dotenv
STOCK_RESEARCH_DASHBOARD_AUTH_REQUIRED=true
STOCK_RESEARCH_DASHBOARD_COOKIE_SECURE=true
STOCK_RESEARCH_DASHBOARD_WRITE_GUARD=true
```

Run:

```bash
stock-research dashboard-auth-init
stock-research dashboard-admin-create --username admin --password '<local-secret>' --role admin
python scripts/smoke_platform_external_access.py --base-url https://stock-research-staging.example.com --expect-auth
```

Then log in from browser and verify:

- unauthenticated `/` shows login
- admin logs in
- admin sees `用户管理`
- regular user does not see `用户管理`
- `/api/platform/summary` requires session when auth-required is true
- guarded write endpoint still requires `X-Dashboard-Write-Token`

## Self-Review

Coverage:

- First-party login: Task 2, Task 3, Task 6.
- Admin/user role: Task 1, Task 4, Task 7.
- Admin user management: Task 4, Task 7, Task 8.
- CSRF: Task 2, Task 4.
- Existing write token retained: Task 9, Task 10 verification.
- No personal watchlist/review: scope boundary excludes it.
- No business-line work: file map excludes research delivery, v7, strategy, signal/admission/scoring.

Open decision before implementation:

- Whether staging should keep Nginx Basic Auth in front of first-party auth for an initial burn-in window. Recommended: yes, keep it until first-party auth passes browser smoke and log review.
