# Minimal Multi-User Watchlist And Review Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add admin-created users, cookie-based login, private watchlist, and private review journal flows into the existing dashboard while keeping all official review data read-only.

**Architecture:** Use Postgres-backed identity, session, watchlist, review, and audit tables behind new `stock_research.dashboard` service modules. Keep FastAPI route wiring inside the existing dashboard app, then refactor the React entrypoint into an auth-aware shell that preserves current official views and adds `我的观察池`, `我的复盘`, and `用户管理` as peer dashboard views.

**Tech Stack:** Python 3.11, FastAPI, psycopg/PostgreSQL, argon2-cffi, React 19, TypeScript, Vite, Vitest, Testing Library, Playwright

---

## File Map

- `pyproject.toml`
  Responsibility: add runtime auth dependency.
- `src/stock_research/config.py`
  Responsibility: expose cookie names, secure-cookie toggle, and session TTL settings.
- `src/stock_research/dashboard/user_schema.py`
  Responsibility: bootstrap `identity`, `watchlist`, `journal`, and `audit` schemas/tables/indexes for the new user layer.
- `src/stock_research/dashboard/user_models.py`
  Responsibility: serialize current-user, admin-user, watchlist, review-session, and review-item payloads consistently.
- `src/stock_research/dashboard/audit.py`
  Responsibility: insert audit log rows from auth, admin, watchlist, and review actions.
- `src/stock_research/dashboard/auth.py`
  Responsibility: password hashing/verification, login failure throttling, session creation/deletion, current-user lookup, and CSRF enforcement.
- `src/stock_research/dashboard/user_admin.py`
  Responsibility: create/list/enable/disable/reset users with audit hooks.
- `src/stock_research/dashboard/user_watchlist.py`
  Responsibility: load/create/update/soft-delete personal watchlist items.
- `src/stock_research/dashboard/user_reviews.py`
  Responsibility: load/create/update/soft-delete review sessions and review items, including `session_id + user_id` ownership checks.
- `src/stock_research/dashboard/app.py`
  Responsibility: mount `/api/auth/*`, `/api/admin/users*`, `/api/my/watchlist*`, `/api/my/reviews*`, and preserve the existing official read-only routes.
- `tests/test_dashboard_user_schema.py`
  Responsibility: prove schema SQL creates the required tables and partial unique index.
- `tests/test_dashboard_user_api.py`
  Responsibility: cover login/logout/me behavior, session cookies, CSRF, and login throttling.
- `tests/test_dashboard_user_admin.py`
  Responsibility: cover admin user CRUD-like actions and route protection.
- `tests/test_dashboard_user_watchlist.py`
  Responsibility: cover personal watchlist route behavior and soft delete semantics.
- `tests/test_dashboard_user_reviews.py`
  Responsibility: cover personal review session/item routes and the ownership-join rule.
- `dashboard/src/api/http.ts`
  Responsibility: centralize `fetch` with `credentials: 'include'`, JSON handling, and CSRF header injection.
- `dashboard/src/api/client.ts`
  Responsibility: add auth, admin, watchlist, and personal review API helpers beside the existing official-read-only helpers.
- `dashboard/src/api/types.ts`
  Responsibility: add frontend types for current user, admin users, watchlist items, review sessions, and review items.
- `dashboard/src/DashboardRoot.tsx`
  Responsibility: own login gating, grouped navigation, role-based view visibility, and switching between the existing official dashboard view and the new personal/admin views.
- `dashboard/src/views/LoginView.tsx`
  Responsibility: render the username/password form and surface login failures.
- `dashboard/src/views/MyWatchlistView.tsx`
  Responsibility: manage the user’s private watchlist list/add/edit/remove UI.
- `dashboard/src/views/MyReviewsView.tsx`
  Responsibility: manage review session list/detail editing and per-asset review items.
- `dashboard/src/views/UserManagementView.tsx`
  Responsibility: admin-only user list, create-user form, reset password, enable, and disable actions.
- `dashboard/src/App.tsx`
  Responsibility: remain the existing official dashboard workbench view.
- `dashboard/src/main.tsx`
  Responsibility: mount `DashboardRoot` instead of mounting the official dashboard view directly.
- `dashboard/src/styles.css`
  Responsibility: add shell, auth, and user-workspace styles without regressing the current official dashboard layout.
- `dashboard/tests/client.test.ts`
  Responsibility: cover auth/user API helpers, `credentials: 'include'`, and CSRF header injection.
- `dashboard/tests/app-shell.test.tsx`
  Responsibility: cover login gating, nav grouping, role-based admin visibility, and view switching.
- `dashboard/tests/my-watchlist-view.test.tsx`
  Responsibility: cover add/remove/edit flows for the private watchlist UI.
- `dashboard/tests/my-reviews-view.test.tsx`
  Responsibility: cover trade-date-prefilled session creation and item editing.
- `dashboard/tests/user-management-view.test.tsx`
  Responsibility: cover admin create/reset/enable/disable flows.
- `dashboard/tests/multi-user-smoke.spec.ts`
  Responsibility: cover one browser-level happy path across login, navigation, watchlist, and reviews.

## Implementation Notes

- Keep all official routes read-only. Do not retrofit official review tables to store personal notes.
- Use a server-side `identity.user_session` table plus two cookies:
  - `stock_research_session`: opaque session token, `HttpOnly`
  - `stock_research_csrf`: CSRF token for frontend echo via `X-CSRF-Token`
- Soft delete means `deleted_at` is set and normal list queries filter `deleted_at IS NULL`.
- Keep the weak linkage to official review data strictly at `trade_date` and `asset_id` in the UI layer. Do not add `official_run_id` columns.
- If the execution branch already contains the newer dashboard shell from the Lite integration work, extend that shell instead of recreating it. The view keys in this plan still apply.

### Task 1: Add User-Platform Schema Bootstrap And Runtime Settings

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/stock_research/config.py`
- Create: `src/stock_research/dashboard/user_schema.py`
- Test: `tests/test_dashboard_user_schema.py`

- [ ] **Step 1: Write the failing schema/bootstrap test**

```python
from stock_research.dashboard import user_schema


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


def test_apply_user_platform_schema_creates_tables_and_indexes(monkeypatch):
    conn = _Connection()
    monkeypatch.setattr(user_schema, "connect", lambda service: _Context(conn))

    user_schema.apply_user_platform_schema()

    sql = conn.cursor_obj.calls[0][0]
    assert "CREATE SCHEMA IF NOT EXISTS identity" in sql
    assert "CREATE TABLE IF NOT EXISTS identity.user_account" in sql
    assert "CREATE TABLE IF NOT EXISTS identity.user_session" in sql
    assert "CREATE TABLE IF NOT EXISTS watchlist.user_watchlist_item" in sql
    assert "CREATE UNIQUE INDEX IF NOT EXISTS uq_active_user_watchlist_item" in sql
    assert "CREATE TABLE IF NOT EXISTS journal.user_review_session" in sql
    assert "CREATE TABLE IF NOT EXISTS journal.user_review_item" in sql
    assert "CREATE TABLE IF NOT EXISTS audit.audit_log" in sql
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_dashboard_user_schema.py -q`

Expected: FAIL with `ImportError` / `ModuleNotFoundError` because `stock_research.dashboard.user_schema` does not exist yet.

- [ ] **Step 3: Write minimal implementation**

`pyproject.toml`

```toml
[project]
dependencies = [
  "akshare",
  "baostock",
  "pandas",
  "psycopg[binary]",
  "pypdf",
  "requests",
  "argon2-cffi",
]
```

`src/stock_research/config.py`

```python
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    research_service: str = "stock_research"
    hfq_service: str = "stock_hfq"
    qfq_service: str = "stock_qfq"
    default_market: str = "CN_A"
    default_currency: str = "CNY"
    selection_top_n: int = 20
    dashboard_session_cookie_name: str = os.getenv("STOCK_RESEARCH_SESSION_COOKIE", "stock_research_session")
    dashboard_csrf_cookie_name: str = os.getenv("STOCK_RESEARCH_CSRF_COOKIE", "stock_research_csrf")
    dashboard_session_ttl_hours: int = int(os.getenv("STOCK_RESEARCH_SESSION_TTL_HOURS", "168"))
    dashboard_secure_cookies: bool = os.getenv("STOCK_RESEARCH_SECURE_COOKIES", "0") == "1"
```

`src/stock_research/dashboard/user_schema.py`

```python
from stock_research.config import SETTINGS
from stock_research.db import connect


CREATE_USER_PLATFORM_SCHEMA_SQL = """
CREATE SCHEMA IF NOT EXISTS identity;
CREATE SCHEMA IF NOT EXISTS journal;
CREATE SCHEMA IF NOT EXISTS audit;

CREATE TABLE IF NOT EXISTS identity.user_account (
    id bigserial PRIMARY KEY,
    username text NOT NULL UNIQUE,
    email text UNIQUE,
    password_hash text NOT NULL,
    display_name text NOT NULL,
    role text NOT NULL CHECK (role IN ('admin', 'user')),
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    last_login_at timestamptz,
    password_updated_at timestamptz,
    disabled_at timestamptz
);

CREATE TABLE IF NOT EXISTS identity.user_session (
    id bigserial PRIMARY KEY,
    user_id bigint NOT NULL REFERENCES identity.user_account(id),
    session_token_hash text NOT NULL UNIQUE,
    csrf_token_hash text NOT NULL,
    ip_address text,
    user_agent text,
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    revoked_at timestamptz
);

CREATE TABLE IF NOT EXISTS watchlist.user_watchlist_item (
    id bigserial PRIMARY KEY,
    user_id bigint NOT NULL REFERENCES identity.user_account(id),
    asset_id text NOT NULL,
    trade_date_added date NOT NULL,
    source text NOT NULL,
    notes text NOT NULL DEFAULT '',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    deleted_at timestamptz
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_active_user_watchlist_item
    ON watchlist.user_watchlist_item (user_id, asset_id)
    WHERE deleted_at IS NULL;

CREATE TABLE IF NOT EXISTS journal.user_review_session (
    id bigserial PRIMARY KEY,
    user_id bigint NOT NULL REFERENCES identity.user_account(id),
    trade_date date NOT NULL,
    title text NOT NULL,
    summary text NOT NULL DEFAULT '',
    market_view text NOT NULL DEFAULT '',
    position_view text NOT NULL DEFAULT '',
    next_action text NOT NULL DEFAULT '',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    deleted_at timestamptz
);

CREATE TABLE IF NOT EXISTS journal.user_review_item (
    id bigserial PRIMARY KEY,
    session_id bigint NOT NULL REFERENCES journal.user_review_session(id),
    user_id bigint NOT NULL REFERENCES identity.user_account(id),
    asset_id text NOT NULL,
    decision text NOT NULL,
    conviction text NOT NULL,
    tags jsonb NOT NULL DEFAULT '[]'::jsonb,
    notes text NOT NULL DEFAULT '',
    follow_up_required boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    deleted_at timestamptz
);

CREATE TABLE IF NOT EXISTS audit.audit_log (
    id bigserial PRIMARY KEY,
    actor_user_id bigint REFERENCES identity.user_account(id),
    action text NOT NULL,
    target_type text NOT NULL,
    target_id text NOT NULL,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    ip_address text,
    user_agent text,
    created_at timestamptz NOT NULL DEFAULT now()
);
"""


def apply_user_platform_schema(service: str = SETTINGS.research_service) -> None:
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute(CREATE_USER_PLATFORM_SCHEMA_SQL)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_dashboard_user_schema.py -q`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml \
  src/stock_research/config.py \
  src/stock_research/dashboard/user_schema.py \
  tests/test_dashboard_user_schema.py
git commit -m "feat: add multi-user schema bootstrap"
```

### Task 2: Implement Auth, Session, CSRF, And Login Throttling

**Files:**
- Create: `src/stock_research/dashboard/user_models.py`
- Create: `src/stock_research/dashboard/audit.py`
- Create: `src/stock_research/dashboard/auth.py`
- Modify: `src/stock_research/dashboard/app.py`
- Test: `tests/test_dashboard_user_api.py`

- [ ] **Step 1: Write the failing auth route tests**

```python
from fastapi.testclient import TestClient

from stock_research.dashboard import app as dashboard_app
from stock_research.dashboard.user_models import CurrentUser


def test_login_me_logout_flow_sets_session_and_csrf_cookies(monkeypatch):
    monkeypatch.setattr(dashboard_app, "count_recent_login_failures", lambda identifier, ip_address: 0)
    monkeypatch.setattr(
        dashboard_app,
        "authenticate_dashboard_user",
        lambda identifier, password: CurrentUser(
            id=7,
            username="xiwei",
            display_name="Xiwei",
            role="admin",
            is_active=True,
        ),
    )
    monkeypatch.setattr(dashboard_app, "create_user_session", lambda user_id, ip_address, user_agent: ("session-1", "csrf-1"))
    monkeypatch.setattr(dashboard_app, "record_audit_log", lambda **kwargs: None)
    monkeypatch.setattr(dashboard_app, "apply_user_platform_schema", lambda: None)

    client = TestClient(dashboard_app.create_app())

    response = client.post("/api/auth/login", json={"identifier": "xiwei", "password": "secret"})

    assert response.status_code == 200
    assert response.json()["username"] == "xiwei"
    assert response.cookies["stock_research_session"] == "session-1"
    assert response.cookies["stock_research_csrf"] == "csrf-1"


def test_login_returns_429_when_recent_failures_exceed_limit(monkeypatch):
    monkeypatch.setattr(dashboard_app, "count_recent_login_failures", lambda identifier, ip_address: 5)
    monkeypatch.setattr(dashboard_app, "apply_user_platform_schema", lambda: None)
    client = TestClient(dashboard_app.create_app())

    response = client.post("/api/auth/login", json={"identifier": "xiwei", "password": "bad"})

    assert response.status_code == 429
    assert response.json()["detail"] == "too many login attempts"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_dashboard_user_api.py -q`

Expected: FAIL because `CurrentUser`, auth helpers, and `/api/auth/login` do not exist yet.

- [ ] **Step 3: Write minimal implementation**

`src/stock_research/dashboard/user_models.py`

```python
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class CurrentUser:
    id: int
    username: str
    display_name: str
    role: str
    is_active: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
```

`src/stock_research/dashboard/audit.py`

```python
import json
from typing import Any

from stock_research.config import SETTINGS
from stock_research.db import connect


def record_audit_log(
    *,
    action: str,
    target_type: str,
    target_id: str,
    actor_user_id: int | None,
    metadata: dict[str, Any] | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    service: str = SETTINGS.research_service,
) -> None:
    sql = """
    INSERT INTO audit.audit_log (
        actor_user_id, action, target_type, target_id, metadata, ip_address, user_agent
    )
    VALUES (%(actor_user_id)s, %(action)s, %(target_type)s, %(target_id)s,
            %(metadata)s::jsonb, %(ip_address)s, %(user_agent)s)
    """
    params = {
        "actor_user_id": actor_user_id,
        "action": action,
        "target_type": target_type,
        "target_id": target_id,
        "metadata": json.dumps(metadata or {}, ensure_ascii=False, sort_keys=True),
        "ip_address": ip_address,
        "user_agent": user_agent,
    }
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
```

`src/stock_research/dashboard/auth.py`

```python
import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from argon2 import PasswordHasher
from fastapi import Depends, HTTPException, Request, Response

from stock_research.config import SETTINGS
from stock_research.dashboard.user_models import CurrentUser
from stock_research.db import connect, fetch_all

PASSWORD_HASHER = PasswordHasher()


def hash_password(password: str) -> str:
    return PASSWORD_HASHER.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return PASSWORD_HASHER.verify(password_hash, password)
    except Exception:
        return False


def count_recent_login_failures(identifier: str, ip_address: str | None, service: str = SETTINGS.research_service) -> int:
    sql = """
    SELECT count(*) AS count
    FROM audit.audit_log
    WHERE action = 'login_failed'
      AND created_at >= now() - interval '15 minutes'
      AND (
        metadata ->> 'identifier' = %(identifier)s
        OR ip_address = %(ip_address)s
      )
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, {"identifier": identifier, "ip_address": ip_address})
    return int(rows[0]["count"]) if rows else 0


def authenticate_dashboard_user(identifier: str, password: str, service: str = SETTINGS.research_service) -> CurrentUser:
    sql = """
    SELECT id, username, display_name, role, is_active, password_hash
    FROM identity.user_account
    WHERE username = %(identifier)s OR email = %(identifier)s
    LIMIT 1
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, {"identifier": identifier})
    if not rows or not verify_password(password, str(rows[0]["password_hash"])) or not bool(rows[0]["is_active"]):
        raise HTTPException(status_code=401, detail="invalid credentials")
    row = rows[0]
    return CurrentUser(
        id=int(row["id"]),
        username=str(row["username"]),
        display_name=str(row["display_name"]),
        role=str(row["role"]),
        is_active=bool(row["is_active"]),
    )


def create_user_session(user_id: int, ip_address: str | None, user_agent: str | None, service: str = SETTINGS.research_service) -> tuple[str, str]:
    session_token = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(24)
    sql = """
    INSERT INTO identity.user_session (
        user_id, session_token_hash, csrf_token_hash, ip_address, user_agent, expires_at
    )
    VALUES (%(user_id)s, %(session_hash)s, %(csrf_hash)s, %(ip_address)s, %(user_agent)s, %(expires_at)s)
    """
    params = {
        "user_id": user_id,
        "session_hash": hashlib.sha256(session_token.encode("utf-8")).hexdigest(),
        "csrf_hash": hashlib.sha256(csrf_token.encode("utf-8")).hexdigest(),
        "ip_address": ip_address,
        "user_agent": user_agent,
        "expires_at": datetime.now(UTC) + timedelta(hours=SETTINGS.dashboard_session_ttl_hours),
    }
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
    return session_token, csrf_token


def revoke_user_session(session_token: str | None, service: str = SETTINGS.research_service) -> None:
    if not session_token:
        return
    sql = """
    UPDATE identity.user_session
    SET revoked_at = now()
    WHERE session_token_hash = %s
      AND revoked_at IS NULL
    """
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, [hashlib.sha256(session_token.encode("utf-8")).hexdigest()])


def load_current_user_from_request(request: Request, service: str = SETTINGS.research_service) -> CurrentUser:
    session_token = request.cookies.get(SETTINGS.dashboard_session_cookie_name)
    if not session_token:
        raise HTTPException(status_code=401, detail="not authenticated")
    sql = """
    SELECT user_account.id, user_account.username, user_account.display_name, user_account.role, user_account.is_active
    FROM identity.user_session AS user_session
    JOIN identity.user_account AS user_account
      ON user_account.id = user_session.user_id
    WHERE user_session.session_token_hash = %s
      AND user_session.revoked_at IS NULL
      AND user_session.expires_at > now()
      AND user_account.is_active = true
    LIMIT 1
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, [hashlib.sha256(session_token.encode("utf-8")).hexdigest()])
    if not rows:
        raise HTTPException(status_code=401, detail="not authenticated")
    row = rows[0]
    return CurrentUser(
        id=int(row["id"]),
        username=str(row["username"]),
        display_name=str(row["display_name"]),
        role=str(row["role"]),
        is_active=bool(row["is_active"]),
    )


def attach_auth_cookies(response: Response, session_token: str, csrf_token: str) -> None:
    response.set_cookie(
        SETTINGS.dashboard_session_cookie_name,
        session_token,
        httponly=True,
        samesite="lax",
        secure=SETTINGS.dashboard_secure_cookies,
    )
    response.set_cookie(
        SETTINGS.dashboard_csrf_cookie_name,
        csrf_token,
        httponly=False,
        samesite="lax",
        secure=SETTINGS.dashboard_secure_cookies,
    )


def clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(SETTINGS.dashboard_session_cookie_name)
    response.delete_cookie(SETTINGS.dashboard_csrf_cookie_name)


def require_current_user(request: Request) -> CurrentUser:
    return load_current_user_from_request(request)


def require_admin_user(current_user: CurrentUser = Depends(require_current_user)) -> CurrentUser:
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="admin access required")
    return current_user


def require_csrf(request: Request) -> None:
    csrf_cookie = request.cookies.get(SETTINGS.dashboard_csrf_cookie_name)
    csrf_header = request.headers.get("X-CSRF-Token")
    if not csrf_cookie or csrf_cookie != csrf_header:
        raise HTTPException(status_code=403, detail="invalid csrf token")
```

`src/stock_research/dashboard/app.py`

```python
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from pydantic import BaseModel

from stock_research.config import SETTINGS
from stock_research.dashboard.audit import record_audit_log
from stock_research.dashboard.auth import (
    attach_auth_cookies,
    authenticate_dashboard_user,
    clear_auth_cookies,
    count_recent_login_failures,
    create_user_session,
    load_current_user_from_request,
    require_admin_user,
    require_csrf,
    require_current_user,
    revoke_user_session,
)
from stock_research.dashboard.user_models import CurrentUser
from stock_research.dashboard.user_schema import apply_user_platform_schema


class LoginPayload(BaseModel):
    identifier: str
    password: str


def create_app() -> FastAPI:
    app = FastAPI(title="Stock Research Dashboard API")

    @app.on_event("startup")
    def _apply_user_schema() -> None:
        apply_user_platform_schema()

    @app.post("/api/auth/login")
    def auth_login(payload: LoginPayload, request: Request, response: Response):
        ip_address = request.client.host if request.client else None
        if count_recent_login_failures(payload.identifier, ip_address) >= 5:
            raise HTTPException(status_code=429, detail="too many login attempts")
        user = authenticate_dashboard_user(payload.identifier, payload.password)
        session_token, csrf_token = create_user_session(user.id, ip_address, request.headers.get("user-agent"))
        attach_auth_cookies(response, session_token, csrf_token)
        record_audit_log(
            action="login_success",
            target_type="user_account",
            target_id=str(user.id),
            actor_user_id=user.id,
            metadata={"identifier": payload.identifier},
            ip_address=ip_address,
            user_agent=request.headers.get("user-agent"),
        )
        return user.to_dict()

    @app.get("/api/auth/me")
    def auth_me(current_user: CurrentUser = Depends(require_current_user)):
        return current_user.to_dict()

    @app.post("/api/auth/logout")
    def auth_logout(
        request: Request,
        response: Response,
        current_user: CurrentUser = Depends(require_current_user),
        _: None = Depends(require_csrf),
    ):
        revoke_user_session(request.cookies.get(SETTINGS.dashboard_session_cookie_name))
        clear_auth_cookies(response)
        record_audit_log(
            action="logout",
            target_type="user_account",
            target_id=str(current_user.id),
            actor_user_id=current_user.id,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
        return {"ok": True}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_dashboard_user_api.py -q`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/dashboard/user_models.py \
  src/stock_research/dashboard/audit.py \
  src/stock_research/dashboard/auth.py \
  src/stock_research/dashboard/app.py \
  tests/test_dashboard_user_api.py
git commit -m "feat: add dashboard auth and session flow"
```

### Task 3: Add Admin User Management Routes

**Files:**
- Create: `src/stock_research/dashboard/user_admin.py`
- Modify: `src/stock_research/dashboard/app.py`
- Test: `tests/test_dashboard_user_admin.py`

- [ ] **Step 1: Write the failing admin tests**

```python
from fastapi.testclient import TestClient

from stock_research.dashboard import app as dashboard_app
from stock_research.dashboard.user_models import CurrentUser


def test_admin_create_user_route_returns_created_user(monkeypatch):
    app = dashboard_app.create_app()
    app.dependency_overrides[dashboard_app.require_admin_user] = lambda: CurrentUser(
        id=1, username="admin", display_name="Admin", role="admin", is_active=True
    )
    app.dependency_overrides[dashboard_app.require_csrf] = lambda request: None
    monkeypatch.setattr(dashboard_app, "apply_user_platform_schema", lambda: None)
    monkeypatch.setattr(
        dashboard_app,
        "create_user_account",
        lambda username, email, display_name, password, role, actor_user_id: {
            "id": 8,
            "username": username,
            "email": email,
            "display_name": display_name,
            "role": role,
            "is_active": True,
        },
    )
    client = TestClient(app)

    response = client.post(
        "/api/admin/users",
        json={
            "username": "new-user",
            "email": "new-user@example.com",
            "display_name": "New User",
            "password": "secret123",
            "role": "user",
        },
    )

    assert response.status_code == 200
    assert response.json()["username"] == "new-user"
    assert response.json()["role"] == "user"


def test_admin_disable_route_passes_target_user_id(monkeypatch):
    app = dashboard_app.create_app()
    app.dependency_overrides[dashboard_app.require_admin_user] = lambda: CurrentUser(
        id=1, username="admin", display_name="Admin", role="admin", is_active=True
    )
    app.dependency_overrides[dashboard_app.require_csrf] = lambda request: None
    monkeypatch.setattr(dashboard_app, "apply_user_platform_schema", lambda: None)
    captured = {}

    def fake_disable(user_id, actor_user_id):
        captured["args"] = [user_id, actor_user_id]

    monkeypatch.setattr(dashboard_app, "disable_user_account", fake_disable)
    client = TestClient(app)

    response = client.post("/api/admin/users/8/disable")

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert captured["args"] == [8, 1]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_dashboard_user_admin.py -q`

Expected: FAIL because the admin routes and user-management service functions do not exist yet.

- [ ] **Step 3: Write minimal implementation**

`src/stock_research/dashboard/user_admin.py`

```python
from stock_research.config import SETTINGS
from stock_research.dashboard.audit import record_audit_log
from stock_research.dashboard.auth import hash_password
from stock_research.db import connect, fetch_all


def list_user_accounts(service: str = SETTINGS.research_service) -> list[dict[str, object]]:
    sql = """
    SELECT id, username, email, display_name, role, is_active, created_at, last_login_at, disabled_at
    FROM identity.user_account
    ORDER BY created_at DESC, id DESC
    """
    with connect(service) as conn:
        return fetch_all(conn, sql)


def create_user_account(username: str, email: str | None, display_name: str, password: str, role: str, actor_user_id: int) -> dict[str, object]:
    sql = """
    INSERT INTO identity.user_account (
        username, email, password_hash, display_name, role, password_updated_at
    )
    VALUES (%(username)s, %(email)s, %(password_hash)s, %(display_name)s, %(role)s, now())
    RETURNING id, username, email, display_name, role, is_active
    """
    params = {
        "username": username,
        "email": email,
        "password_hash": hash_password(password),
        "display_name": display_name,
        "role": role,
    }
    with connect(SETTINGS.research_service) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
    record_audit_log(
        action="admin_create_user",
        target_type="user_account",
        target_id=str(row["id"]),
        actor_user_id=actor_user_id,
        metadata={"username": username, "role": role},
    )
    return dict(row)


def reset_user_password(user_id: int, new_password: str, actor_user_id: int) -> None:
    sql = """
    UPDATE identity.user_account
    SET password_hash = %(password_hash)s,
        password_updated_at = now(),
        updated_at = now()
    WHERE id = %(user_id)s
    """
    with connect(SETTINGS.research_service) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, {"user_id": user_id, "password_hash": hash_password(new_password)})
    record_audit_log(
        action="admin_reset_password",
        target_type="user_account",
        target_id=str(user_id),
        actor_user_id=actor_user_id,
    )


def set_user_active_state(user_id: int, is_active: bool, actor_user_id: int) -> None:
    sql = """
    UPDATE identity.user_account
    SET is_active = %(is_active)s,
        disabled_at = CASE WHEN %(is_active)s THEN NULL ELSE now() END,
        updated_at = now()
    WHERE id = %(user_id)s
    """
    with connect(SETTINGS.research_service) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, {"user_id": user_id, "is_active": is_active})
    record_audit_log(
        action="admin_enable_user" if is_active else "admin_disable_user",
        target_type="user_account",
        target_id=str(user_id),
        actor_user_id=actor_user_id,
    )


def disable_user_account(user_id: int, actor_user_id: int) -> None:
    set_user_active_state(user_id, False, actor_user_id)


def enable_user_account(user_id: int, actor_user_id: int) -> None:
    set_user_active_state(user_id, True, actor_user_id)
```

`src/stock_research/dashboard/app.py`

```python
from fastapi import Depends
from pydantic import BaseModel

from stock_research.dashboard.auth import require_admin_user, require_csrf
from stock_research.dashboard.user_admin import (
    create_user_account,
    disable_user_account,
    enable_user_account,
    list_user_accounts,
    reset_user_password,
)
from stock_research.dashboard.user_models import CurrentUser


class AdminCreateUserPayload(BaseModel):
    username: str
    email: str | None = None
    display_name: str
    password: str
    role: str = "user"


class ResetPasswordPayload(BaseModel):
    password: str


@app.get("/api/admin/users")
def admin_list_users(current_user: CurrentUser = Depends(require_admin_user)):
    return {"items": list_user_accounts()}


@app.post("/api/admin/users")
def admin_create_user(
    payload: AdminCreateUserPayload,
    current_user: CurrentUser = Depends(require_admin_user),
    _: None = Depends(require_csrf),
):
    return create_user_account(
        username=payload.username,
        email=payload.email,
        display_name=payload.display_name,
        password=payload.password,
        role=payload.role,
        actor_user_id=current_user.id,
    )


@app.post("/api/admin/users/{user_id}/reset-password")
def admin_reset_password(
    user_id: int,
    payload: ResetPasswordPayload,
    current_user: CurrentUser = Depends(require_admin_user),
    _: None = Depends(require_csrf),
):
    reset_user_password(user_id, payload.password, current_user.id)
    return {"ok": True}


@app.post("/api/admin/users/{user_id}/disable")
def admin_disable_user(
    user_id: int,
    current_user: CurrentUser = Depends(require_admin_user),
    _: None = Depends(require_csrf),
):
    disable_user_account(user_id, current_user.id)
    return {"ok": True}


@app.post("/api/admin/users/{user_id}/enable")
def admin_enable_user(
    user_id: int,
    current_user: CurrentUser = Depends(require_admin_user),
    _: None = Depends(require_csrf),
):
    enable_user_account(user_id, current_user.id)
    return {"ok": True}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_dashboard_user_admin.py -q`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/dashboard/user_admin.py \
  src/stock_research/dashboard/app.py \
  tests/test_dashboard_user_admin.py
git commit -m "feat: add admin user management routes"
```

### Task 4: Add Personal Watchlist Backend With Soft Delete

**Files:**
- Create: `src/stock_research/dashboard/user_watchlist.py`
- Modify: `src/stock_research/dashboard/user_models.py`
- Modify: `src/stock_research/dashboard/app.py`
- Test: `tests/test_dashboard_user_watchlist.py`

- [ ] **Step 1: Write the failing watchlist tests**

```python
from fastapi.testclient import TestClient

from stock_research.dashboard import app as dashboard_app
from stock_research.dashboard.user_models import CurrentUser


def test_delete_my_watchlist_item_soft_deletes(monkeypatch):
    app = dashboard_app.create_app()
    app.dependency_overrides[dashboard_app.require_current_user] = lambda: CurrentUser(
        id=7, username="xiwei", display_name="Xiwei", role="user", is_active=True
    )
    app.dependency_overrides[dashboard_app.require_csrf] = lambda request: None
    monkeypatch.setattr(dashboard_app, "apply_user_platform_schema", lambda: None)

    captured = {}

    def fake_soft_delete(user_id, asset_id):
        captured["args"] = [user_id, asset_id]

    monkeypatch.setattr(dashboard_app, "soft_delete_user_watchlist_item", fake_soft_delete)
    client = TestClient(app)

    response = client.delete("/api/my/watchlist/items/000001.SZ")

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert captured["args"] == [7, "000001.SZ"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_dashboard_user_watchlist.py -q`

Expected: FAIL because `/api/my/watchlist/items/{asset_id}` and `soft_delete_user_watchlist_item` do not exist yet.

- [ ] **Step 3: Write minimal implementation**

`src/stock_research/dashboard/user_models.py`

```python
@dataclass(frozen=True)
class UserWatchlistItem:
    id: int
    user_id: int
    asset_id: str
    trade_date_added: str
    source: str
    notes: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
```

`src/stock_research/dashboard/user_watchlist.py`

```python
from datetime import date

from stock_research.config import SETTINGS
from stock_research.dashboard.audit import record_audit_log
from stock_research.db import connect, fetch_all


def list_user_watchlist_items(user_id: int, service: str = SETTINGS.research_service) -> list[dict[str, object]]:
    sql = """
    SELECT id, user_id, asset_id, trade_date_added, source, notes
    FROM watchlist.user_watchlist_item
    WHERE user_id = %s
      AND deleted_at IS NULL
    ORDER BY trade_date_added DESC, id DESC
    """
    with connect(service) as conn:
        return fetch_all(conn, sql, [user_id])


def create_user_watchlist_item(user_id: int, asset_id: str, source: str, notes: str, service: str = SETTINGS.research_service) -> dict[str, object]:
    sql = """
    INSERT INTO watchlist.user_watchlist_item (
        user_id, asset_id, trade_date_added, source, notes
    )
    VALUES (%(user_id)s, %(asset_id)s, %(trade_date_added)s, %(source)s, %(notes)s)
    RETURNING id, user_id, asset_id, trade_date_added, source, notes
    """
    params = {
        "user_id": user_id,
        "asset_id": asset_id,
        "trade_date_added": date.today().isoformat(),
        "source": source,
        "notes": notes,
    }
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
    record_audit_log(
        action="watchlist_add_item",
        target_type="user_watchlist_item",
        target_id=f"{user_id}:{asset_id}",
        actor_user_id=user_id,
        metadata={"asset_id": asset_id, "source": source},
    )
    return dict(row)


def update_user_watchlist_item(user_id: int, asset_id: str, source: str, notes: str, service: str = SETTINGS.research_service) -> dict[str, object]:
    sql = """
    UPDATE watchlist.user_watchlist_item
    SET source = %(source)s,
        notes = %(notes)s,
        updated_at = now()
    WHERE user_id = %(user_id)s
      AND asset_id = %(asset_id)s
      AND deleted_at IS NULL
    RETURNING id, user_id, asset_id, trade_date_added, source, notes
    """
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, {"user_id": user_id, "asset_id": asset_id, "source": source, "notes": notes})
            row = cur.fetchone()
    record_audit_log(
        action="watchlist_update_item",
        target_type="user_watchlist_item",
        target_id=f"{user_id}:{asset_id}",
        actor_user_id=user_id,
        metadata={"asset_id": asset_id},
    )
    return dict(row)


def soft_delete_user_watchlist_item(user_id: int, asset_id: str, service: str = SETTINGS.research_service) -> None:
    sql = """
    UPDATE watchlist.user_watchlist_item
    SET deleted_at = now(), updated_at = now()
    WHERE user_id = %s
      AND asset_id = %s
      AND deleted_at IS NULL
    """
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, [user_id, asset_id])
    record_audit_log(
        action="watchlist_remove_item",
        target_type="user_watchlist_item",
        target_id=f"{user_id}:{asset_id}",
        actor_user_id=user_id,
        metadata={"asset_id": asset_id},
    )
```

`src/stock_research/dashboard/app.py`

```python
from pydantic import BaseModel

from fastapi import Depends

from stock_research.dashboard.auth import require_csrf, require_current_user
from stock_research.dashboard.user_watchlist import (
    create_user_watchlist_item,
    list_user_watchlist_items,
    soft_delete_user_watchlist_item,
    update_user_watchlist_item,
)


class WatchlistItemPayload(BaseModel):
    asset_id: str
    source: str = "manual"
    notes: str = ""


class WatchlistItemUpdatePayload(BaseModel):
    source: str = "manual"
    notes: str = ""


@app.get("/api/my/watchlist")
def my_watchlist(current_user: CurrentUser = Depends(require_current_user)):
    return {"items": list_user_watchlist_items(current_user.id)}


@app.post("/api/my/watchlist/items")
def my_watchlist_create(
    payload: WatchlistItemPayload,
    current_user: CurrentUser = Depends(require_current_user),
    _: None = Depends(require_csrf),
):
    return create_user_watchlist_item(current_user.id, payload.asset_id, payload.source, payload.notes)


@app.patch("/api/my/watchlist/items/{asset_id}")
def my_watchlist_patch(
    asset_id: str,
    payload: WatchlistItemUpdatePayload,
    current_user: CurrentUser = Depends(require_current_user),
    _: None = Depends(require_csrf),
):
    return update_user_watchlist_item(current_user.id, asset_id, payload.source, payload.notes)


@app.delete("/api/my/watchlist/items/{asset_id}")
def my_watchlist_delete(
    asset_id: str,
    current_user: CurrentUser = Depends(require_current_user),
    _: None = Depends(require_csrf),
):
    soft_delete_user_watchlist_item(current_user.id, asset_id)
    return {"ok": True}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_dashboard_user_watchlist.py -q`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/dashboard/user_watchlist.py \
  src/stock_research/dashboard/user_models.py \
  src/stock_research/dashboard/app.py \
  tests/test_dashboard_user_watchlist.py
git commit -m "feat: add personal watchlist routes"
```

### Task 5: Add Personal Review Session And Item Backend

**Files:**
- Create: `src/stock_research/dashboard/user_reviews.py`
- Modify: `src/stock_research/dashboard/user_models.py`
- Modify: `src/stock_research/dashboard/app.py`
- Test: `tests/test_dashboard_user_reviews.py`

- [ ] **Step 1: Write the failing review tests**

```python
from fastapi.testclient import TestClient

from stock_research.dashboard import app as dashboard_app
from stock_research.dashboard.user_models import CurrentUser


def test_patch_review_item_passes_session_id_item_id_and_user_id(monkeypatch):
    app = dashboard_app.create_app()
    app.dependency_overrides[dashboard_app.require_current_user] = lambda: CurrentUser(
        id=9, username="xiwei", display_name="Xiwei", role="user", is_active=True
    )
    app.dependency_overrides[dashboard_app.require_csrf] = lambda request: None
    monkeypatch.setattr(dashboard_app, "apply_user_platform_schema", lambda: None)
    captured = {}

    def fake_update_item(session_id, item_id, user_id, payload):
        captured["args"] = [session_id, item_id, user_id, payload]
        return {"id": item_id, "session_id": session_id, "user_id": user_id}

    monkeypatch.setattr(dashboard_app, "update_user_review_item", fake_update_item)
    client = TestClient(app)

    response = client.patch(
        "/api/my/reviews/12/items/34",
        json={"decision": "hold", "conviction": "medium", "tags": ["retest"], "notes": "", "follow_up_required": True},
    )

    assert response.status_code == 200
    assert captured["args"][0:3] == [12, 34, 9]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_dashboard_user_reviews.py -q`

Expected: FAIL because `/api/my/reviews/{session_id}/items/{item_id}` and `update_user_review_item` do not exist yet.

- [ ] **Step 3: Write minimal implementation**

`src/stock_research/dashboard/user_models.py`

```python
@dataclass(frozen=True)
class UserReviewSession:
    id: int
    user_id: int
    trade_date: str
    title: str
    summary: str
    market_view: str
    position_view: str
    next_action: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class UserReviewItem:
    id: int
    session_id: int
    user_id: int
    asset_id: str
    decision: str
    conviction: str
    tags: list[str]
    notes: str
    follow_up_required: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
```

`src/stock_research/dashboard/user_reviews.py`

```python
import json

from stock_research.config import SETTINGS
from stock_research.dashboard.audit import record_audit_log
from stock_research.db import connect, fetch_all


def list_user_review_sessions(user_id: int, service: str = SETTINGS.research_service) -> list[dict[str, object]]:
    sql = """
    SELECT id, user_id, trade_date, title, summary, market_view, position_view, next_action
    FROM journal.user_review_session
    WHERE user_id = %s
      AND deleted_at IS NULL
    ORDER BY trade_date DESC, id DESC
    """
    with connect(service) as conn:
        return fetch_all(conn, sql, [user_id])


def create_user_review_session(user_id: int, payload: dict[str, object], service: str = SETTINGS.research_service) -> dict[str, object]:
    sql = """
    INSERT INTO journal.user_review_session (
        user_id, trade_date, title, summary, market_view, position_view, next_action
    )
    VALUES (%(user_id)s, %(trade_date)s, %(title)s, %(summary)s, %(market_view)s, %(position_view)s, %(next_action)s)
    RETURNING id, user_id, trade_date, title, summary, market_view, position_view, next_action
    """
    params = {
        "user_id": user_id,
        "trade_date": payload["trade_date"],
        "title": payload["title"],
        "summary": payload.get("summary", ""),
        "market_view": payload.get("market_view", ""),
        "position_view": payload.get("position_view", ""),
        "next_action": payload.get("next_action", ""),
    }
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
    record_audit_log(
        action="review_create_session",
        target_type="user_review_session",
        target_id=str(row["id"]),
        actor_user_id=user_id,
        metadata={"trade_date": payload["trade_date"]},
    )
    return dict(row)


def update_user_review_item(
    session_id: int,
    item_id: int,
    user_id: int,
    payload: dict[str, object],
    service: str = SETTINGS.research_service,
) -> dict[str, object]:
    sql = """
    UPDATE journal.user_review_item AS item
    SET decision = %(decision)s,
        conviction = %(conviction)s,
        tags = %(tags)s::jsonb,
        notes = %(notes)s,
        follow_up_required = %(follow_up_required)s,
        updated_at = now()
    FROM journal.user_review_session AS session
    WHERE item.id = %(item_id)s
      AND item.session_id = %(session_id)s
      AND item.user_id = %(user_id)s
      AND item.deleted_at IS NULL
      AND session.id = item.session_id
      AND session.user_id = %(user_id)s
      AND session.deleted_at IS NULL
    RETURNING item.id, item.session_id, item.user_id, item.asset_id, item.decision,
              item.conviction, item.tags, item.notes, item.follow_up_required
    """
    params = {
        "session_id": session_id,
        "item_id": item_id,
        "user_id": user_id,
        "decision": payload["decision"],
        "conviction": payload["conviction"],
        "tags": json.dumps(payload.get("tags", []), ensure_ascii=False, sort_keys=True),
        "notes": payload.get("notes", ""),
        "follow_up_required": payload.get("follow_up_required", False),
    }
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
    record_audit_log(
        action="review_update_item",
        target_type="user_review_item",
        target_id=str(item_id),
        actor_user_id=user_id,
        metadata={"session_id": session_id},
    )
    return dict(row)


def soft_delete_user_review_session(session_id: int, user_id: int, service: str = SETTINGS.research_service) -> None:
    sql = """
    UPDATE journal.user_review_session
    SET deleted_at = now(), updated_at = now()
    WHERE id = %s
      AND user_id = %s
      AND deleted_at IS NULL
    """
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, [session_id, user_id])
    record_audit_log(
        action="review_delete_session",
        target_type="user_review_session",
        target_id=str(session_id),
        actor_user_id=user_id,
    )


def soft_delete_user_review_item(session_id: int, item_id: int, user_id: int, service: str = SETTINGS.research_service) -> None:
    sql = """
    UPDATE journal.user_review_item AS item
    SET deleted_at = now(), updated_at = now()
    FROM journal.user_review_session AS session
    WHERE item.id = %(item_id)s
      AND item.session_id = %(session_id)s
      AND item.user_id = %(user_id)s
      AND item.deleted_at IS NULL
      AND session.id = item.session_id
      AND session.user_id = %(user_id)s
      AND session.deleted_at IS NULL
    """
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, {"session_id": session_id, "item_id": item_id, "user_id": user_id})
    record_audit_log(
        action="review_delete_item",
        target_type="user_review_item",
        target_id=str(item_id),
        actor_user_id=user_id,
        metadata={"session_id": session_id},
    )
```

`src/stock_research/dashboard/app.py`

```python
from pydantic import BaseModel

from stock_research.dashboard.user_reviews import (
    create_user_review_session,
    list_user_review_sessions,
    soft_delete_user_review_item,
    soft_delete_user_review_session,
    update_user_review_item,
)


class ReviewItemPayload(BaseModel):
    decision: str
    conviction: str
    tags: list[str] = []
    notes: str = ""
    follow_up_required: bool = False


class ReviewSessionPayload(BaseModel):
    trade_date: str
    title: str
    summary: str = ""
    market_view: str = ""
    position_view: str = ""
    next_action: str = ""


@app.get("/api/my/reviews")
def my_reviews(current_user: CurrentUser = Depends(require_current_user)):
    return {"items": list_user_review_sessions(current_user.id)}


@app.post("/api/my/reviews")
def my_reviews_create(
    payload: ReviewSessionPayload,
    current_user: CurrentUser = Depends(require_current_user),
    _: None = Depends(require_csrf),
):
    return create_user_review_session(current_user.id, payload.model_dump())


@app.patch("/api/my/reviews/{session_id}/items/{item_id}")
def my_review_item_patch(
    session_id: int,
    item_id: int,
    payload: ReviewItemPayload,
    current_user: CurrentUser = Depends(require_current_user),
    _: None = Depends(require_csrf),
):
    return update_user_review_item(session_id, item_id, current_user.id, payload.model_dump())


@app.delete("/api/my/reviews/{session_id}")
def my_review_delete(
    session_id: int,
    current_user: CurrentUser = Depends(require_current_user),
    _: None = Depends(require_csrf),
):
    soft_delete_user_review_session(session_id, current_user.id)
    return {"ok": True}


@app.delete("/api/my/reviews/{session_id}/items/{item_id}")
def my_review_item_delete(
    session_id: int,
    item_id: int,
    current_user: CurrentUser = Depends(require_current_user),
    _: None = Depends(require_csrf),
):
    soft_delete_user_review_item(session_id, item_id, current_user.id)
    return {"ok": True}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_dashboard_user_reviews.py -q`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/dashboard/user_reviews.py \
  src/stock_research/dashboard/user_models.py \
  src/stock_research/dashboard/app.py \
  tests/test_dashboard_user_reviews.py
git commit -m "feat: add personal review routes"
```

### Task 6: Add Frontend Auth/User HTTP Helpers And API Types

**Files:**
- Create: `dashboard/src/api/http.ts`
- Modify: `dashboard/src/api/client.ts`
- Modify: `dashboard/src/api/types.ts`
- Test: `dashboard/tests/client.test.ts`

- [ ] **Step 1: Write the failing frontend client tests**

```tsx
import { describe, expect, it, vi } from 'vitest';
import { fetchCurrentUser, login, createMyReviewItem } from '../src/api/client';

describe('user API client', () => {
  it('sends credentials on auth requests', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ id: 1, username: 'xiwei' }) });
    vi.stubGlobal('fetch', fetchMock);

    await fetchCurrentUser();

    expect(fetchMock).toHaveBeenCalledWith('/api/auth/me', expect.objectContaining({ credentials: 'include' }));
  });

  it('adds csrf header to mutating personal review requests', async () => {
    Object.defineProperty(document, 'cookie', {
      value: 'stock_research_csrf=csrf-1',
      configurable: true,
    });
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ id: 34 }) });
    vi.stubGlobal('fetch', fetchMock);

    await createMyReviewItem(12, {
      asset_id: '000001.SZ',
      decision: 'watch',
      conviction: 'medium',
      tags: [],
      notes: '',
      follow_up_required: false,
    });

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/my/reviews/12/items',
      expect.objectContaining({
        credentials: 'include',
        headers: expect.objectContaining({
          'Content-Type': 'application/json',
          'X-CSRF-Token': 'csrf-1',
        }),
      }),
    );
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd dashboard && pnpm exec vitest run tests/client.test.ts -t "sends credentials on auth requests" -t "adds csrf header to mutating personal review requests"`

Expected: FAIL because `fetchCurrentUser`, `createMyReviewItem`, and the shared HTTP wrapper do not exist yet.

- [ ] **Step 3: Write minimal implementation**

`dashboard/src/api/http.ts`

```ts
function readCookie(name: string): string | null {
  const match = document.cookie
    .split(';')
    .map((part) => part.trim())
    .find((part) => part.startsWith(`${name}=`));
  return match ? decodeURIComponent(match.slice(name.length + 1)) : null;
}

async function requestJson<T>(url: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers ?? {});
  const method = (init.method ?? 'GET').toUpperCase();
  if (method !== 'GET') {
    const csrfToken = readCookie('stock_research_csrf');
    if (csrfToken) headers.set('X-CSRF-Token', csrfToken);
    if (!headers.has('Content-Type') && init.body) {
      headers.set('Content-Type', 'application/json');
    }
  }
  const response = await fetch(url, {
    ...init,
    headers,
    credentials: 'include',
  });
  if (!response.ok) {
    throw new Error(`request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export function getJson<T>(url: string): Promise<T> {
  return requestJson<T>(url);
}

export function postJson<T>(url: string, body?: unknown): Promise<T> {
  return requestJson<T>(url, {
    method: 'POST',
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

export function patchJson<T>(url: string, body: unknown): Promise<T> {
  return requestJson<T>(url, {
    method: 'PATCH',
    body: JSON.stringify(body),
  });
}

export function deleteJson<T>(url: string): Promise<T> {
  return requestJson<T>(url, { method: 'DELETE' });
}
```

`dashboard/src/api/types.ts`

```ts
export type CurrentUser = {
  id: number;
  username: string;
  display_name: string;
  role: 'admin' | 'user';
  is_active: boolean;
};

export type UserWatchlistItem = {
  id: number;
  user_id: number;
  asset_id: string;
  trade_date_added: string;
  source: string;
  notes: string;
};

export type AdminUser = {
  id: number;
  username: string;
  email: string | null;
  display_name: string;
  role: 'admin' | 'user';
  is_active: boolean;
};

export type UserReviewSession = {
  id: number;
  user_id: number;
  trade_date: string;
  title: string;
  summary: string;
  market_view: string;
  position_view: string;
  next_action: string;
};

export type UserReviewItem = {
  id: number;
  session_id: number;
  user_id: number;
  asset_id: string;
  decision: string;
  conviction: string;
  tags: string[];
  notes: string;
  follow_up_required: boolean;
};
```

`dashboard/src/api/client.ts`

```ts
import { deleteJson, getJson, patchJson, postJson } from './http';
import type { CurrentUser, UserReviewItem } from './types';

export function fetchCurrentUser(): Promise<CurrentUser> {
  return getJson('/api/auth/me');
}

export function login(identifier: string, password: string): Promise<CurrentUser> {
  return postJson('/api/auth/login', { identifier, password });
}

export function logout(): Promise<{ ok: boolean }> {
  return postJson('/api/auth/logout');
}

export function createMyReviewItem(
  sessionId: number,
  payload: {
    asset_id: string;
    decision: string;
    conviction: string;
    tags: string[];
    notes: string;
    follow_up_required: boolean;
  },
): Promise<UserReviewItem> {
  return postJson(`/api/my/reviews/${sessionId}/items`, payload);
}

export function updateMyReviewItem(sessionId: number, itemId: number, payload: Omit<UserReviewItem, 'id' | 'session_id' | 'user_id'>) {
  return patchJson(`/api/my/reviews/${sessionId}/items/${itemId}`, payload);
}

export function removeMyWatchlistItem(assetId: string) {
  return deleteJson(`/api/my/watchlist/items/${encodeURIComponent(assetId)}`);
}

export function fetchMyWatchlist(): Promise<UserWatchlistItem[]> {
  return getJson<{ items: UserWatchlistItem[] }>('/api/my/watchlist').then((payload) => payload.items);
}

export function createMyWatchlistItem(payload: { asset_id: string; source: string; notes: string }) {
  return postJson('/api/my/watchlist/items', payload);
}

export function updateMyWatchlistItem(assetId: string, payload: { source: string; notes: string }) {
  return patchJson(`/api/my/watchlist/items/${encodeURIComponent(assetId)}`, payload);
}

export function fetchMyReviewSessions(): Promise<UserReviewSession[]> {
  return getJson<{ items: UserReviewSession[] }>('/api/my/reviews').then((payload) => payload.items);
}

export function fetchMyReviewSession(sessionId: number) {
  return getJson(`/api/my/reviews/${sessionId}`);
}

export function createMyReviewSession(payload: { trade_date: string; title: string }) {
  return postJson('/api/my/reviews', payload);
}

export function updateMyReviewSession(sessionId: number, payload: Partial<UserReviewSession>) {
  return patchJson(`/api/my/reviews/${sessionId}`, payload);
}

export function removeMyReviewItem(sessionId: number, itemId: number) {
  return deleteJson(`/api/my/reviews/${sessionId}/items/${itemId}`);
}

export function fetchUsers(): Promise<AdminUser[]> {
  return getJson<{ items: AdminUser[] }>('/api/admin/users').then((payload) => payload.items);
}

export function createUser(payload: {
  username: string;
  display_name: string;
  password: string;
  role: 'admin' | 'user';
}) {
  return postJson('/api/admin/users', payload);
}

export function resetUserPassword(userId: number, password: string) {
  return postJson(`/api/admin/users/${userId}/reset-password`, { password });
}

export function disableUser(userId: number) {
  return postJson(`/api/admin/users/${userId}/disable`);
}

export function enableUser(userId: number) {
  return postJson(`/api/admin/users/${userId}/enable`);
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd dashboard && pnpm exec vitest run tests/client.test.ts`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add dashboard/src/api/http.ts \
  dashboard/src/api/client.ts \
  dashboard/src/api/types.ts \
  dashboard/tests/client.test.ts
git commit -m "feat: add frontend auth and user api helpers"
```

### Task 7: Add An Auth-Aware Dashboard Root Without Rewriting The Official View

**Files:**
- Create: `dashboard/src/DashboardRoot.tsx`
- Create: `dashboard/src/views/LoginView.tsx`
- Modify: `dashboard/src/main.tsx`
- Test: `dashboard/tests/app-shell.test.tsx`

- [ ] **Step 1: Write the failing shell tests**

```tsx
import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { DashboardRoot } from '../src/DashboardRoot';

const apiMocks = vi.hoisted(() => ({
  fetchCurrentUser: vi.fn(),
  login: vi.fn(),
}));

vi.mock('../src/api/client', async () => {
  const actual = await vi.importActual<typeof import('../src/api/client')>('../src/api/client');
  return { ...actual, ...apiMocks };
});

vi.mock('../src/App', () => ({
  App: () => <div>Official dashboard content</div>,
}));

afterEach(() => {
  cleanup();
  window.history.replaceState({}, '', '/');
});

describe('DashboardRoot', () => {
  it('renders login when there is no active session', async () => {
    apiMocks.fetchCurrentUser.mockRejectedValueOnce(new Error('request failed: 401'));

    render(<DashboardRoot />);

    expect(await screen.findByRole('heading', { name: '登录' })).toBeInTheDocument();
  });

  it('shows grouped navigation for an admin and updates the URL when switching views', async () => {
    apiMocks.fetchCurrentUser.mockResolvedValueOnce({
      id: 1,
      username: 'admin',
      display_name: 'Admin',
      role: 'admin',
      is_active: true,
    });

    render(<DashboardRoot />);

    expect(await screen.findByText('Official dashboard content')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '我的观察池' }));

    await waitFor(() => {
      expect(new URL(window.location.href).searchParams.get('view')).toBe('my-watchlist');
    });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd dashboard && pnpm exec vitest run tests/app-shell.test.tsx`

Expected: FAIL because `DashboardRoot` and the login-aware shell do not exist yet.

- [ ] **Step 3: Write minimal implementation**

`dashboard/src/views/LoginView.tsx`

```tsx
import { FormEvent, useState } from 'react';

type LoginViewProps = {
  onSubmit: (identifier: string, password: string) => Promise<void>;
  error: string | null;
};

export function LoginView({ onSubmit, error }: LoginViewProps) {
  const [identifier, setIdentifier] = useState('');
  const [password, setPassword] = useState('');

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await onSubmit(identifier, password);
  }

  return (
    <section className="login-card">
      <h1>登录</h1>
      <form onSubmit={handleSubmit}>
        <label>
          用户名或邮箱
          <input value={identifier} onChange={(event) => setIdentifier(event.target.value)} />
        </label>
        <label>
          密码
          <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} />
        </label>
        {error ? <p role="alert">{error}</p> : null}
        <button type="submit">登录</button>
      </form>
    </section>
  );
}
```

`dashboard/src/DashboardRoot.tsx`

```tsx
import { useEffect, useState } from 'react';
import { App as OfficialDashboardView } from './App';
import { fetchCurrentUser, login } from './api/client';
import type { CurrentUser } from './api/types';
import { LoginView } from './views/LoginView';

export type DashboardViewKey = 'official' | 'my-watchlist' | 'my-reviews' | 'user-management';

const NAV = [
  { key: 'official-group', label: '官方', items: [{ key: 'official', label: '研究工作台' }] },
  { key: 'my-group', label: '我的', items: [{ key: 'my-watchlist', label: '我的观察池' }, { key: 'my-reviews', label: '我的复盘' }] },
  { key: 'admin-group', label: '管理', items: [{ key: 'user-management', label: '用户管理' }] },
] as const;

export function DashboardRoot() {
  const [currentUser, setCurrentUser] = useState<CurrentUser | null>(null);
  const [authChecked, setAuthChecked] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchCurrentUser()
      .then((user) => setCurrentUser(user))
      .catch(() => setCurrentUser(null))
      .finally(() => setAuthChecked(true));
  }, []);

  async function handleLogin(identifier: string, password: string) {
    try {
      const user = await login(identifier, password);
      setCurrentUser(user);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  if (!authChecked) {
    return <div>Loading…</div>;
  }

  if (!currentUser) {
    return <LoginView onSubmit={handleLogin} error={error} />;
  }

  return (
    <main className="dashboard-shell">
      <aside className="dashboard-shell-nav">
        {NAV.filter((group) => currentUser.role === 'admin' || group.key !== 'admin-group').map((group) => (
          <section key={group.key}>
            <h2>{group.label}</h2>
            {group.items.map((item) => (
              <button
                key={item.key}
                type="button"
                onClick={() => {
                  const url = new URL(window.location.href);
                  url.searchParams.set('view', item.key);
                  window.history.replaceState({}, '', `${url.pathname}?${url.searchParams.toString()}`);
                }}
              >
                {item.label}
              </button>
            ))}
          </section>
        ))}
      </aside>
      <section className="dashboard-shell-content">
        <OfficialDashboardView />
      </section>
    </main>
  );
}
```

`dashboard/src/main.tsx`

```tsx
import React from 'react';
import ReactDOM from 'react-dom/client';
import { DashboardRoot } from './DashboardRoot';
import './styles.css';

ReactDOM.createRoot(document.getElementById('root') as HTMLElement).render(
  <React.StrictMode>
    <DashboardRoot />
  </React.StrictMode>
);
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd dashboard && pnpm exec vitest run tests/app-shell.test.tsx`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add dashboard/src/DashboardRoot.tsx \
  dashboard/src/views/LoginView.tsx \
  dashboard/src/main.tsx \
  dashboard/tests/app-shell.test.tsx
git commit -m "feat: add auth-aware dashboard root"
```

### Task 8: Add My Watchlist, My Reviews, And User Management Views

**Files:**
- Create: `dashboard/src/views/MyWatchlistView.tsx`
- Create: `dashboard/src/views/MyReviewsView.tsx`
- Create: `dashboard/src/views/UserManagementView.tsx`
- Modify: `dashboard/src/DashboardRoot.tsx`
- Modify: `dashboard/src/styles.css`
- Test: `dashboard/tests/my-watchlist-view.test.tsx`
- Test: `dashboard/tests/my-reviews-view.test.tsx`
- Test: `dashboard/tests/user-management-view.test.tsx`

- [ ] **Step 1: Write the failing user-view tests**

```tsx
import '@testing-library/jest-dom/vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { MyWatchlistView } from '../src/views/MyWatchlistView';

describe('MyWatchlistView', () => {
  it('adds a new item and refreshes the list', async () => {
    const createItem = vi.fn().mockResolvedValue({ id: 2, asset_id: '000001.SZ' });
    const loadItems = vi
      .fn()
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([{ id: 2, user_id: 7, asset_id: '000001.SZ', trade_date_added: '2026-06-22', source: 'manual', notes: '' }]);

    render(<MyWatchlistView loadItems={loadItems} createItem={createItem} removeItem={vi.fn()} updateItem={vi.fn()} />);

    fireEvent.change(screen.getByLabelText('Asset ID'), { target: { value: '000001.SZ' } });
    fireEvent.click(screen.getByRole('button', { name: '添加' }));

    await waitFor(() => {
      expect(createItem).toHaveBeenCalledWith({ asset_id: '000001.SZ', source: 'manual', notes: '' });
    });
  });
});
```

```tsx
import '@testing-library/jest-dom/vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { MyReviewsView } from '../src/views/MyReviewsView';

describe('MyReviewsView', () => {
  it('creates a new review session prefilling the selected trade date', async () => {
    const createSession = vi.fn().mockResolvedValue({ id: 12, trade_date: '2026-06-22', title: '盘后复盘' });
    render(
      <MyReviewsView
        tradeDate="2026-06-22"
        loadSessions={vi.fn().mockResolvedValue([])}
        loadSessionDetail={vi.fn()}
        createSession={createSession}
        updateSession={vi.fn()}
        createItem={vi.fn()}
        updateItem={vi.fn()}
        deleteItem={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: '新建我的复盘' }));

    await waitFor(() => {
      expect(createSession).toHaveBeenCalledWith(expect.objectContaining({ trade_date: '2026-06-22' }));
    });
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd dashboard
pnpm exec vitest run tests/my-watchlist-view.test.tsx
pnpm exec vitest run tests/my-reviews-view.test.tsx
pnpm exec vitest run tests/user-management-view.test.tsx
```

Expected: FAIL because the new user workspace components do not exist yet.

- [ ] **Step 3: Write minimal implementation**

`dashboard/src/views/MyWatchlistView.tsx`

```tsx
import { FormEvent, useEffect, useState } from 'react';
import type { UserWatchlistItem } from '../api/types';

type Props = {
  loadItems: () => Promise<UserWatchlistItem[]>;
  createItem: (payload: { asset_id: string; source: string; notes: string }) => Promise<unknown>;
  updateItem: (assetId: string, payload: { notes: string; source: string }) => Promise<unknown>;
  removeItem: (assetId: string) => Promise<unknown>;
};

export function MyWatchlistView({ loadItems, createItem, updateItem, removeItem }: Props) {
  const [items, setItems] = useState<UserWatchlistItem[]>([]);
  const [assetId, setAssetId] = useState('');

  async function refresh() {
    setItems(await loadItems());
  }

  useEffect(() => {
    void refresh();
  }, []);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    await createItem({ asset_id: assetId, source: 'manual', notes: '' });
    setAssetId('');
    await refresh();
  }

  return (
    <section>
      <h1>我的观察池</h1>
      <form onSubmit={handleSubmit}>
        <label>
          Asset ID
          <input value={assetId} onChange={(event) => setAssetId(event.target.value)} />
        </label>
        <button type="submit">添加</button>
      </form>
      <ul>
        {items.map((item) => (
          <li key={item.id}>
            <span>{item.asset_id}</span>
            <button type="button" onClick={() => void removeItem(item.asset_id).then(refresh)}>
              删除
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
```

`dashboard/src/views/MyReviewsView.tsx`

```tsx
type UserReviewSessionSummary = {
  id: number;
  trade_date: string;
  title: string;
};

type Props = {
  tradeDate: string;
  loadSessions: () => Promise<UserReviewSessionSummary[]>;
  loadSessionDetail: (sessionId: number) => Promise<unknown>;
  createSession: (payload: { trade_date: string; title: string }) => Promise<unknown>;
  updateSession: (sessionId: number, payload: unknown) => Promise<unknown>;
  createItem: (sessionId: number, payload: unknown) => Promise<unknown>;
  updateItem: (sessionId: number, itemId: number, payload: unknown) => Promise<unknown>;
  deleteItem: (sessionId: number, itemId: number) => Promise<unknown>;
};

export function MyReviewsView({ tradeDate, loadSessions, createSession }: Props) {
  return (
    <section>
      <h1>我的复盘</h1>
      <button type="button" onClick={() => void createSession({ trade_date: tradeDate, title: '盘后复盘' })}>
        新建我的复盘
      </button>
    </section>
  );
}
```

`dashboard/src/views/UserManagementView.tsx`

```tsx
import { FormEvent, useEffect, useState } from 'react';

type AdminUser = {
  id: number;
  username: string;
  display_name: string;
  role: 'admin' | 'user';
  is_active: boolean;
};

type Props = {
  loadUsers: () => Promise<AdminUser[]>;
  createUser: (payload: { username: string; display_name: string; password: string; role: 'admin' | 'user' }) => Promise<unknown>;
  resetPassword: (userId: number, password: string) => Promise<unknown>;
  enableUser: (userId: number) => Promise<unknown>;
  disableUser: (userId: number) => Promise<unknown>;
};

export function UserManagementView({ loadUsers, createUser, resetPassword, enableUser, disableUser }: Props) {
  const [users, setUsers] = useState<AdminUser[]>([]);

  useEffect(() => {
    loadUsers().then(setUsers);
  }, [loadUsers]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    await createUser({
      username: String(form.get('username')),
      display_name: String(form.get('display_name')),
      password: String(form.get('password')),
      role: 'user',
    });
    setUsers(await loadUsers());
  }

  return (
    <section>
      <h1>用户管理</h1>
      <form onSubmit={handleSubmit}>
        <input name="username" aria-label="Username" />
        <input name="display_name" aria-label="Display Name" />
        <input name="password" aria-label="Password" type="password" />
        <button type="submit">创建用户</button>
      </form>
      <ul>
        {users.map((user) => (
          <li key={user.id}>
            <span>{user.username}</span>
            <button type="button" onClick={() => void resetPassword(user.id, 'TempPass123!')}>
              重置密码
            </button>
            {user.is_active ? (
              <button type="button" onClick={() => void disableUser(user.id).then(async () => setUsers(await loadUsers()))}>
                停用
              </button>
            ) : (
              <button type="button" onClick={() => void enableUser(user.id).then(async () => setUsers(await loadUsers()))}>
                启用
              </button>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
```

`dashboard/src/DashboardRoot.tsx`

```tsx
import { App as OfficialDashboardView } from './App';
import {
  createMyReviewItem,
  createMyReviewSession,
  createMyWatchlistItem,
  createUser,
  fetchMyReviewSession,
  fetchMyReviewSessions,
  fetchMyWatchlist,
  fetchUsers,
  enableUser,
  removeMyReviewItem,
  removeMyWatchlistItem,
  resetUserPassword,
  disableUser,
  updateMyReviewItem,
  updateMyReviewSession,
  updateMyWatchlistItem,
} from './api/client';
import type { CurrentUser } from './api/types';
import { MyReviewsView } from './views/MyReviewsView';
import { MyWatchlistView } from './views/MyWatchlistView';
import { UserManagementView } from './views/UserManagementView';

function readViewFromUrl(): DashboardViewKey {
  const view = new URL(window.location.href).searchParams.get('view');
  if (view === 'my-watchlist' || view === 'my-reviews' || view === 'user-management') {
    return view;
  }
  return 'official';
}

export function renderDashboardContent(currentUser: CurrentUser) {
  const currentView = readViewFromUrl();
  return (
    <section className="dashboard-shell-content">
      {currentView === 'official' ? <OfficialDashboardView /> : null}
      {currentView === 'my-watchlist' ? (
        <MyWatchlistView
          loadItems={fetchMyWatchlist}
          createItem={createMyWatchlistItem}
          updateItem={updateMyWatchlistItem}
          removeItem={removeMyWatchlistItem}
        />
      ) : null}
      {currentView === 'my-reviews' ? (
        <MyReviewsView
          tradeDate="2026-06-22"
          loadSessions={fetchMyReviewSessions}
          loadSessionDetail={fetchMyReviewSession}
          createSession={createMyReviewSession}
          updateSession={updateMyReviewSession}
          createItem={createMyReviewItem}
          updateItem={updateMyReviewItem}
          deleteItem={removeMyReviewItem}
        />
      ) : null}
  {currentView === 'user-management' && currentUser.role === 'admin' ? (
    <UserManagementView
      loadUsers={fetchUsers}
      createUser={createUser}
      resetPassword={resetUserPassword}
      enableUser={enableUser}
      disableUser={disableUser}
    />
  ) : null}
    </section>
  );
}
```

`dashboard/src/styles.css`

```css
.dashboard-shell {
  display: grid;
  grid-template-columns: 240px 1fr;
  min-height: 100vh;
}

.dashboard-shell-nav {
  padding: 24px;
  border-right: 1px solid #d7d0c2;
  background: linear-gradient(180deg, #f8f3e8 0%, #efe5d3 100%);
}

.dashboard-shell-content {
  padding: 24px 32px;
}

.login-card {
  width: min(420px, calc(100vw - 32px));
  margin: 96px auto;
  padding: 24px;
  border: 1px solid #d7d0c2;
  background: #fffaf0;
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
cd dashboard
pnpm exec vitest run tests/my-watchlist-view.test.tsx
pnpm exec vitest run tests/my-reviews-view.test.tsx
pnpm exec vitest run tests/user-management-view.test.tsx
pnpm exec vitest run tests/app-shell.test.tsx
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add dashboard/src/views/MyWatchlistView.tsx \
  dashboard/src/views/MyReviewsView.tsx \
  dashboard/src/views/UserManagementView.tsx \
  dashboard/src/DashboardRoot.tsx \
  dashboard/src/styles.css \
  dashboard/tests/my-watchlist-view.test.tsx \
  dashboard/tests/my-reviews-view.test.tsx \
  dashboard/tests/user-management-view.test.tsx
git commit -m "feat: add personal watchlist review and admin views"
```

### Task 9: Add Browser Smoke And Final Regression Verification

**Files:**
- Create: `dashboard/tests/multi-user-smoke.spec.ts`
- Modify: `dashboard/package.json`

- [ ] **Step 1: Write the failing browser smoke**

```ts
import { expect, test } from '@playwright/test';

test('login and navigate through my watchlist and my reviews', async ({ page }) => {
  await page.route('/api/auth/me', async (route) => {
    await route.fulfill({ status: 401, json: { detail: 'not authenticated' } });
  });
  await page.route('/api/auth/login', async (route) => {
    await route.fulfill({
      json: { id: 1, username: 'admin', display_name: 'Admin', role: 'admin', is_active: true },
      headers: {
        'set-cookie':
          'stock_research_session=session-1; Path=/; HttpOnly; SameSite=Lax\nstock_research_csrf=csrf-1; Path=/; SameSite=Lax',
      },
    });
  });
  await page.route('/api/my/watchlist', async (route) => {
    await route.fulfill({ json: { items: [] } });
  });
  await page.route('/api/my/reviews', async (route) => {
    await route.fulfill({ json: { items: [] } });
  });

  await page.goto('/');
  await page.getByLabel('用户名或邮箱').fill('admin');
  await page.getByLabel('密码').fill('secret');
  await page.getByRole('button', { name: '登录' }).click();
  await page.getByRole('button', { name: '我的观察池' }).click();
  await expect(page.getByRole('heading', { name: '我的观察池' })).toBeVisible();
  await page.getByRole('button', { name: '我的复盘' }).click();
  await expect(page.getByRole('heading', { name: '我的复盘' })).toBeVisible();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd dashboard && pnpm exec playwright test tests/multi-user-smoke.spec.ts`

Expected: FAIL because the login form, navigation, or user views are not all wired together yet.

- [ ] **Step 3: Write minimal implementation**

`dashboard/package.json`

```json
{
  "scripts": {
    "test:e2e": "playwright test tests/app-smoke.spec.ts tests/multi-user-smoke.spec.ts"
  }
}
```

`dashboard/tests/multi-user-smoke.spec.ts`

```ts
import { expect, test } from '@playwright/test';

test('login and navigate through my watchlist and my reviews', async ({ page }) => {
  await page.route('/api/auth/me', async (route) => {
    await route.fulfill({ status: 401, json: { detail: 'not authenticated' } });
  });
  await page.route('/api/auth/login', async (route) => {
    await route.fulfill({
      json: { id: 1, username: 'admin', display_name: 'Admin', role: 'admin', is_active: true },
      headers: {
        'set-cookie':
          'stock_research_session=session-1; Path=/; HttpOnly; SameSite=Lax\nstock_research_csrf=csrf-1; Path=/; SameSite=Lax',
      },
    });
  });
  await page.route('/api/my/watchlist', async (route) => {
    await route.fulfill({ json: { items: [] } });
  });
  await page.route('/api/my/reviews', async (route) => {
    await route.fulfill({ json: { items: [] } });
  });

  await page.goto('/');
  await page.getByLabel('用户名或邮箱').fill('admin');
  await page.getByLabel('密码').fill('secret');
  await page.getByRole('button', { name: '登录' }).click();
  await page.getByRole('button', { name: '我的观察池' }).click();
  await expect(page.getByRole('heading', { name: '我的观察池' })).toBeVisible();
  await page.getByRole('button', { name: '我的复盘' }).click();
  await expect(page.getByRole('heading', { name: '我的复盘' })).toBeVisible();
});
```

- [ ] **Step 4: Run the full verification suite**

Run:

```bash
pytest tests/test_dashboard_user_schema.py \
  tests/test_dashboard_user_api.py \
  tests/test_dashboard_user_admin.py \
  tests/test_dashboard_user_watchlist.py \
  tests/test_dashboard_user_reviews.py -q

cd dashboard && pnpm exec vitest run \
  tests/client.test.ts \
  tests/app-shell.test.tsx \
  tests/my-watchlist-view.test.tsx \
  tests/my-reviews-view.test.tsx \
  tests/user-management-view.test.tsx

cd dashboard && pnpm exec playwright test tests/app-smoke.spec.ts tests/multi-user-smoke.spec.ts
```

Expected:
- `pytest`: PASS
- `vitest`: PASS
- `playwright`: PASS

- [ ] **Step 5: Commit**

```bash
git add dashboard/package.json \
  dashboard/tests/multi-user-smoke.spec.ts
git commit -m "test: add multi-user dashboard smoke coverage"
```

## Coverage Check

- `users` additions: Task 1 schema, Task 3 admin routes.
- `audit_logs`: Task 1 schema, Task 2 shared writer, Tasks 3-5 action hooks.
- `trade_date` naming: Task 1 review session schema, Task 8 review creation UI.
- watchlist soft delete: Task 1 partial unique index, Task 4 delete route.
- review item ownership join: Task 5 `UPDATE ... FROM journal.user_review_session`.
- password hash, cookie flags, CSRF, rate limit: Task 1 settings, Task 2 auth flow.
- dashboard product shape: Task 7 shell and Task 8 user/admin views.

## Self-Review Notes

- No placeholder endpoints remain; every API path used in tasks matches the approved spec.
- The only intentional implementation detail added beyond the spec is `identity.user_session`, required to support cookie sessions and CSRF cleanly.
- If the execution branch already contains a richer official dashboard shell, keep that shell and port only the new auth/user views instead of re-splitting official content.
