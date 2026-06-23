# External User Platform Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the merged multi-user dashboard externally deployable at the production root domain with the platform login view as the only product login layer, plus deterministic admin bootstrap and external-readiness verification.

**Architecture:** Start from `main` and keep the same-origin session-based dashboard architecture intact. Add a minimal admin bootstrap/recovery CLI, tighten root-path external auth coverage, and ship deployment/runbook artifacts that describe Nginx static serving plus `/api/*` reverse proxying to an internal FastAPI service.

**Tech Stack:** Python, FastAPI, PostgreSQL, Argon2, React, Vite, Vitest, Playwright, Nginx, systemd, Markdown runbooks.

---

## File Structure

- `src/stock_research/dashboard/user_admin.py`
  Responsibility: add operator-safe admin bootstrap and username-based recovery helpers close to existing account lifecycle logic.
- `src/stock_research/cli.py`
  Responsibility: expose operator commands for first-admin bootstrap and recovery.
- `tests/test_dashboard_admin_bootstrap.py`
  Responsibility: cover bootstrap/recovery helper behavior and CLI dispatch.
- `tests/test_dashboard_user_admin.py`
  Responsibility: add explicit non-admin denial coverage for admin routes if not already present in a route-level test.
- `dashboard/tests/app-shell.test.tsx`
  Responsibility: assert root-path login-first behavior in component tests.
- `dashboard/tests/external-root-auth.spec.ts`
  Responsibility: external-root browser smoke for unauthenticated entry, admin login, standard-user login, and logout.
- `dashboard/package.json`
  Responsibility: include the new external-root smoke in `test:e2e`.
- `deploy/nginx/stock.manqiaotechnology.com.conf.example`
  Responsibility: example same-origin production Nginx config with no Basic Auth at the production root.
- `deploy/systemd/stock-research-dashboard-api.service`
  Responsibility: example internal-only dashboard API service definition.
- `docs/external-user-platform-runbook.md`
  Responsibility: operator procedure for deploy, bootstrap, user management, recovery, logs, and rollback.
- `README.md`
  Responsibility: point operators to the external runbook and new bootstrap commands.

### Task 1: Add Admin Bootstrap And Recovery CLI

**Files:**
- Modify: `src/stock_research/dashboard/user_admin.py`
- Modify: `src/stock_research/cli.py`
- Modify: `README.md`
- Test: `tests/test_dashboard_admin_bootstrap.py`

- [ ] **Step 1: Write the failing bootstrap/recovery tests**

Create `tests/test_dashboard_admin_bootstrap.py`:

```python
import pytest

from stock_research import cli
from stock_research.dashboard import user_admin


class _Cursor:
    def __init__(self, *, rows=None):
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
    def __init__(self, *, rows=None):
        self.cursor_obj = _Cursor(rows=rows)

    def cursor(self):
        return self.cursor_obj


class _Context:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self.conn

    def __exit__(self, exc_type, exc, tb):
        return False


def test_bootstrap_admin_account_creates_first_admin_and_audit(monkeypatch):
    conn = _Connection(
        rows=[
            {"active_admin_count": 0},
            {
                "id": 1,
                "username": "admin",
                "email": None,
                "display_name": "Platform Admin",
                "role": "admin",
                "is_active": True,
                "created_at": "2026-06-23T00:00:00Z",
                "updated_at": "2026-06-23T00:00:00Z",
                "last_login_at": None,
                "password_updated_at": "2026-06-23T00:00:00Z",
                "disabled_at": None,
            },
        ]
    )
    monkeypatch.setattr(user_admin, "connect", lambda service: _Context(conn))
    monkeypatch.setattr(user_admin, "hash_password", lambda password: f"hashed::{password}")

    account = user_admin.bootstrap_admin_account(
        username="admin",
        password="secret123",
        display_name="Platform Admin",
        email=None,
    )

    assert account["username"] == "admin"
    count_sql, _ = conn.cursor_obj.calls[0]
    insert_sql, insert_params = conn.cursor_obj.calls[1]
    audit_sql, audit_params = conn.cursor_obj.calls[2]
    assert "active_admin_count" in count_sql
    assert insert_params["password_hash"] == "hashed::secret123"
    assert "INSERT INTO audit.audit_log" in audit_sql
    assert audit_params["action"] == "admin_bootstrap_user"
    assert audit_params["actor_user_id"] is None


def test_bootstrap_admin_account_rejects_if_active_admin_exists(monkeypatch):
    conn = _Connection(rows=[{"active_admin_count": 1}])
    monkeypatch.setattr(user_admin, "connect", lambda service: _Context(conn))

    with pytest.raises(ValueError, match="active admin already exists"):
        user_admin.bootstrap_admin_account(
            username="admin",
            password="secret123",
            display_name="Platform Admin",
            email=None,
        )


def test_enable_user_account_by_username_reenables_disabled_user(monkeypatch):
    conn = _Connection(rows=[{"id": 9}])
    monkeypatch.setattr(user_admin, "connect", lambda service: _Context(conn))

    assert user_admin.enable_user_account_by_username(username="admin") is True
    update_sql, update_params = conn.cursor_obj.calls[0]
    assert "UPDATE identity.user_account" in update_sql
    assert update_params == {"username": "admin"}


def test_dashboard_bootstrap_admin_cli_dispatches(monkeypatch, capsys):
    monkeypatch.setattr(
        cli,
        "bootstrap_admin_account",
        lambda **kwargs: {"username": kwargs["username"]},
        raising=False,
    )

    cli.main_for_args(
        [
            "dashboard-bootstrap-admin",
            "--username",
            "admin",
            "--password",
            "secret123",
            "--display-name",
            "Platform Admin",
        ]
    )

    assert "dashboard_admin_bootstrapped|admin" in capsys.readouterr().out
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run:

```bash
source /tmp/stock-research-task9-venv/bin/activate
cd /Users/xiwei/stock_research/.worktrees/external-user-platform-integration.7ZWQKk
pytest tests/test_dashboard_admin_bootstrap.py -q
```

Expected: FAIL because `bootstrap_admin_account`, `enable_user_account_by_username`, and the new CLI commands do not exist yet.

- [ ] **Step 3: Implement the bootstrap/recovery helpers and CLI wiring**

Modify `src/stock_research/dashboard/user_admin.py` to add:

```python
def bootstrap_admin_account(
    *,
    username: str,
    password: str,
    display_name: str,
    email: str | None,
    service: str = SETTINGS.research_service,
) -> dict[str, object]:
    count_sql = """
    SELECT COUNT(*) AS active_admin_count
    FROM identity.user_account
    WHERE role = 'admin'
      AND is_active IS TRUE
      AND disabled_at IS NULL
    """
    insert_sql = f"""
    INSERT INTO identity.user_account (
        username,
        email,
        password_hash,
        display_name,
        role,
        password_updated_at
    )
    VALUES (
        %(username)s,
        %(email)s,
        %(password_hash)s,
        %(display_name)s,
        'admin',
        now()
    )
    RETURNING {USER_ACCOUNT_COLUMNS}
    """
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute(count_sql)
            row = cur.fetchone()
            active_admin_count = int(row["active_admin_count"]) if row else 0
            if active_admin_count > 0:
                raise ValueError("active admin already exists")
            cur.execute(
                insert_sql,
                {
                    "username": username,
                    "email": email,
                    "password_hash": hash_password(password),
                    "display_name": display_name,
                },
            )
            created = cur.fetchone()
            if created is None:
                raise RuntimeError("failed to bootstrap admin account")
            account = _serialize_user_account(created)
            _insert_audit_log(
                cur,
                actor_user_id=None,
                action="admin_bootstrap_user",
                target_type="user_account",
                target_id=str(account["id"]),
                metadata={"username": str(account["username"])},
            )
    return account


def enable_user_account_by_username(
    *,
    username: str,
    service: str = SETTINGS.research_service,
) -> bool:
    sql = """
    UPDATE identity.user_account
    SET is_active = TRUE,
        disabled_at = NULL,
        updated_at = now()
    WHERE username = %(username)s
    RETURNING id
    """
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, {"username": username})
            row = cur.fetchone()
    return row is not None
```

Modify `src/stock_research/cli.py` parser and dispatch:

```python
dashboard_bootstrap_admin = subparsers.add_parser("dashboard-bootstrap-admin")
dashboard_bootstrap_admin.add_argument("--username", required=True)
dashboard_bootstrap_admin.add_argument("--password", required=True)
dashboard_bootstrap_admin.add_argument("--display-name")
dashboard_bootstrap_admin.add_argument("--email")

dashboard_enable_user = subparsers.add_parser("dashboard-enable-user")
dashboard_enable_user.add_argument("--username", required=True)
```

```python
elif args.command == "dashboard-bootstrap-admin":
    account = bootstrap_admin_account(
        username=args.username,
        password=args.password,
        display_name=args.display_name or args.username,
        email=args.email,
    )
    print(f"dashboard_admin_bootstrapped|{account['username']}")
elif args.command == "dashboard-enable-user":
    if not enable_user_account_by_username(username=args.username):
        raise SystemExit(f"user not found: {args.username}")
    print(f"dashboard_user_enabled|{args.username}")
```

Update `README.md` command examples:

````md
Bootstrap the first dashboard admin:

```bash
stock-research dashboard-bootstrap-admin \
  --username admin \
  --password 'initial-password' \
  --display-name 'Platform Admin'
```

Re-enable a disabled dashboard user:

```bash
stock-research dashboard-enable-user --username admin
```
````

- [ ] **Step 4: Run the focused tests to verify they pass**

Run:

```bash
source /tmp/stock-research-task9-venv/bin/activate
cd /Users/xiwei/stock_research/.worktrees/external-user-platform-integration.7ZWQKk
pytest tests/test_dashboard_admin_bootstrap.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit the bootstrap/recovery task**

```bash
cd /Users/xiwei/stock_research/.worktrees/external-user-platform-integration.7ZWQKk
git add src/stock_research/dashboard/user_admin.py src/stock_research/cli.py README.md tests/test_dashboard_admin_bootstrap.py
git commit -m "feat: add dashboard admin bootstrap cli"
```

### Task 2: Add External Root Auth And Role Verification Coverage

**Files:**
- Modify: `tests/test_dashboard_user_admin.py`
- Modify: `dashboard/tests/app-shell.test.tsx`
- Create: `dashboard/tests/external-root-auth.spec.ts`
- Modify: `dashboard/package.json`

- [ ] **Step 1: Write the failing backend and browser verification tests**

Append to `tests/test_dashboard_user_admin.py`:

```python
def test_admin_list_users_route_returns_403_for_non_admin(monkeypatch):
    def fake_require_admin_user(request: Request):
        raise dashboard_app.HTTPException(status_code=403, detail="admin required")

    monkeypatch.setattr(dashboard_app, "apply_user_platform_schema", lambda: None, raising=False)
    monkeypatch.setattr(dashboard_app, "require_admin_user", fake_require_admin_user, raising=False)

    with TestClient(dashboard_app.create_app()) as client:
        response = client.get("/api/admin/users")

    assert response.status_code == 403
    assert response.json() == {"detail": "admin required"}
```

Create `dashboard/tests/external-root-auth.spec.ts`:

```ts
import { expect, test } from '@playwright/test';

test('root path shows login for unauthenticated visitors and admin sees management', async ({ page }) => {
  await page.route('/api/auth/me', async (route) => {
    await route.fulfill({
      status: 401,
      contentType: 'application/json',
      body: JSON.stringify({ detail: 'authentication required' })
    });
  });

  await page.route('/api/auth/login', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        id: 1,
        username: 'admin',
        display_name: 'Admin User',
        role: 'admin',
        is_active: true
      }),
      headers: {
        'set-cookie':
          'stock_research_session=session-1; Path=/; SameSite=Lax, stock_research_csrf=csrf-1; Path=/; SameSite=Lax'
      }
    });
  });

  await page.goto('/');
  await expect(page.getByRole('heading', { name: '登录' })).toBeVisible();

  await page.getByLabel('用户名或邮箱').fill('admin');
  await page.getByLabel('密码').fill('secret123');
  await page.getByRole('button', { name: '登录' }).click();

  await expect(page.getByRole('button', { name: '用户管理' })).toBeVisible();
  await page.getByRole('button', { name: '退出登录' }).click();
  await expect(page.getByRole('heading', { name: '登录' })).toBeVisible();
});

test('standard users cannot see management and can reach private views', async ({ page }) => {
  await page.route('/api/auth/me', async (route) => {
    await route.fulfill({
      status: 401,
      contentType: 'application/json',
      body: JSON.stringify({ detail: 'authentication required' })
    });
  });

  await page.route('/api/auth/login', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        id: 7,
        username: 'analyst',
        display_name: 'Analyst',
        role: 'user',
        is_active: true
      }),
      headers: {
        'set-cookie':
          'stock_research_session=session-2; Path=/; SameSite=Lax, stock_research_csrf=csrf-2; Path=/; SameSite=Lax'
      }
    });
  });

  await page.route('/api/my/watchlist', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ items: [] }) });
  });

  await page.route('/api/my/reviews', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ items: [] }) });
  });

  await page.goto('/');
  await page.getByLabel('用户名或邮箱').fill('analyst');
  await page.getByLabel('密码').fill('secret123');
  await page.getByRole('button', { name: '登录' }).click();

  await expect(page.getByRole('button', { name: '用户管理' })).toHaveCount(0);
  await page.getByRole('button', { name: '我的观察池' }).click();
  await expect(page.getByText('暂无观察资产。')).toBeVisible();
  await page.getByRole('button', { name: '我的复盘' }).click();
  await expect(page.getByText('暂无复盘记录。')).toBeVisible();
});
```

Update `dashboard/package.json`:

```json
{
  "scripts": {
    "test:e2e": "CI=1 PLAYWRIGHT_PORT=4074 playwright test tests/app-smoke.spec.ts tests/multi-user-smoke.spec.ts tests/external-root-auth.spec.ts"
  }
}
```

- [ ] **Step 2: Run the focused tests to verify they fail**

Run:

```bash
source /tmp/stock-research-task9-venv/bin/activate
cd /Users/xiwei/stock_research/.worktrees/external-user-platform-integration.7ZWQKk
pytest tests/test_dashboard_user_admin.py -q
cd dashboard
pnpm exec playwright test tests/external-root-auth.spec.ts
```

Expected: FAIL because the new route-level denial test and new browser spec do not exist yet.

- [ ] **Step 3: Add root-path and role-aware assertions**

Append to `dashboard/tests/app-shell.test.tsx` a root-path assertion using the existing `DashboardRoot` mocks:

```tsx
it('uses the root path as the external unauthenticated entry', async () => {
  apiMocks.fetchCurrentUser.mockRejectedValue(new Error('GET /api/auth/me failed with 401: Unauthorized'));
  window.history.replaceState({}, '', '/');

  render(<DashboardRoot />);

  expect(await screen.findByRole('heading', { name: '登录' })).toBeVisible();
  expect(window.location.pathname).toBe('/');
});
```

If the new Playwright spec exposes brittle login mocks, keep the implementation minimal by only adjusting test fixtures and route handlers. Do not rewrite `DashboardRoot` if the current behavior already satisfies the external-root contract.

- [ ] **Step 4: Run the focused tests to verify they pass**

Run:

```bash
source /tmp/stock-research-task9-venv/bin/activate
cd /Users/xiwei/stock_research/.worktrees/external-user-platform-integration.7ZWQKk
pytest tests/test_dashboard_user_admin.py -q
cd dashboard
pnpm exec vitest run tests/app-shell.test.tsx
pnpm exec playwright test tests/external-root-auth.spec.ts
```

Expected: PASS.

- [ ] **Step 5: Commit the external-root verification task**

```bash
cd /Users/xiwei/stock_research/.worktrees/external-user-platform-integration.7ZWQKk
git add tests/test_dashboard_user_admin.py dashboard/tests/app-shell.test.tsx dashboard/tests/external-root-auth.spec.ts dashboard/package.json
git commit -m "test: add external root auth coverage"
```

### Task 3: Add Same-Origin Deploy Artifacts

**Files:**
- Create: `deploy/nginx/stock.manqiaotechnology.com.conf.example`
- Create: `deploy/systemd/stock-research-dashboard-api.service`

- [ ] **Step 1: Write the deploy artifact files**

Create `deploy/nginx/stock.manqiaotechnology.com.conf.example`:

```nginx
server {
    listen 80;
    server_name stock.manqiaotechnology.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name stock.manqiaotechnology.com;

    ssl_certificate /etc/letsencrypt/live/stock.manqiaotechnology.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/stock.manqiaotechnology.com/privkey.pem;

    root /opt/stock-research/dashboard/dist;
    index index.html;

    location /api/ {
        proxy_pass http://127.0.0.1:8000/api/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
    }

    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

Create `deploy/systemd/stock-research-dashboard-api.service`:

```ini
[Unit]
Description=Stock Research Dashboard API
After=network.target

[Service]
Type=simple
User=stock
Group=stock
WorkingDirectory=/opt/stock-research
Environment=STOCK_RESEARCH_SECURE_COOKIES=1
ExecStart=/opt/stock-research/.venv/bin/stock-research dashboard-api --host 127.0.0.1 --port 8000
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

- [ ] **Step 2: Verify the deploy artifacts are present and contain the required production shape**

Run:

```bash
cd /Users/xiwei/stock_research/.worktrees/external-user-platform-integration.7ZWQKk
rg -n "auth_basic|proxy_pass http://127.0.0.1:8000/api/|try_files|STOCK_RESEARCH_SECURE_COOKIES=1|--host 127.0.0.1 --port 8000" \
  deploy/nginx/stock.manqiaotechnology.com.conf.example \
  deploy/systemd/stock-research-dashboard-api.service
```

Expected: matches for the same-origin `/api/*` proxy, `try_files`, internal-only API bind, and secure-cookie environment.

- [ ] **Step 3: Commit the deploy artifact task**

```bash
cd /Users/xiwei/stock_research/.worktrees/external-user-platform-integration.7ZWQKk
git add deploy/nginx/stock.manqiaotechnology.com.conf.example deploy/systemd/stock-research-dashboard-api.service
git commit -m "ops: add external dashboard deploy examples"
```

### Task 4: Add External Operator Runbook And Run Full Regression

**Files:**
- Create: `docs/external-user-platform-runbook.md`
- Modify: `README.md`

- [ ] **Step 1: Write the operator runbook**

Create `docs/external-user-platform-runbook.md`:

````md
# External User Platform Runbook

## 1. First Deployment

1. Build the dashboard frontend:
   - `cd dashboard && pnpm install --frozen-lockfile && pnpm build`
2. Install the frontend assets under `/opt/stock-research/dashboard/dist`
3. Install the Nginx config from `deploy/nginx/stock.manqiaotechnology.com.conf.example`
4. Install the systemd unit from `deploy/systemd/stock-research-dashboard-api.service`
5. Confirm the production root is not protected by Nginx Basic Auth

## 2. Create The First Admin

```bash
stock-research dashboard-bootstrap-admin \
  --username admin \
  --password 'initial-password' \
  --display-name 'Platform Admin'
```

Expected: `dashboard_admin_bootstrapped|admin`

## 3. Admin Login

- Open `https://stock.manqiaotechnology.com/`
- Confirm the login page is rendered by the dashboard app
- Log in with the bootstrap credentials

## 4. Create A Standard User

- Sign in as admin
- Open `管理`
- Create the user from `用户管理`

## 5. Reset Password

- Sign in as admin
- Open `管理`
- Use `重置密码`

## 6. Disable Or Enable A User

- Sign in as admin
- Open `管理`
- Use `禁用` or `启用`

## 7. Recover A Disabled Account

```bash
stock-research dashboard-enable-user --username admin
```

## 8. Inspect Audit Logs

- Query `audit.audit_log`
- Filter for:
  - `login_success`
  - `login_failed`
  - `admin_create_user`
  - `admin_reset_password`
  - `admin_disable_user`
  - `admin_enable_user`

## 9. Inspect Service Logs

```bash
journalctl -u stock-research-dashboard-api.service -n 200 --no-pager
```

## 10. Roll Back

1. Restore the previous `dashboard/dist`
2. Restore the previous Nginx config if needed
3. Restart Nginx and the dashboard API service
````

Update `README.md` by appending the new external runbook entry:

```md
| External user platform | `docs/external-user-platform-runbook.md` |
```

- [ ] **Step 2: Run the full external-readiness regression suite**

Run:

```bash
source /tmp/stock-research-task9-venv/bin/activate
cd /Users/xiwei/stock_research/.worktrees/external-user-platform-integration.7ZWQKk
pytest tests/test_dashboard_admin_bootstrap.py tests/test_dashboard_user_schema.py tests/test_dashboard_user_api.py tests/test_dashboard_user_admin.py tests/test_dashboard_user_watchlist.py tests/test_dashboard_user_reviews.py -q
cd dashboard
pnpm test
pnpm test:e2e
pnpm build
```

Expected:

- Python: PASS
- Vitest: PASS
- Playwright: PASS
- Build: PASS

- [ ] **Step 3: Commit the runbook and verification task**

```bash
cd /Users/xiwei/stock_research/.worktrees/external-user-platform-integration.7ZWQKk
git add docs/external-user-platform-runbook.md README.md
git commit -m "docs: add external user platform runbook"
```

## Spec Coverage Check

- Basic Auth cutover: Task 3 deploy artifacts + Task 4 runbook
- same-origin Nginx shape: Task 3
- FastAPI internal-only bind: Task 3
- secure cookie deployment requirement: Task 3 systemd env + existing config usage
- initial admin bootstrap: Task 1
- recovery path: Task 1 CLI + Task 4 runbook
- root-path login-first verification: Task 2 + Task 4 full regression
- admin/user role visibility and private views: Task 2

## Self-Review Notes

- No placeholder deployment shape remains; the plan names concrete files for Nginx, systemd, runbook, CLI, backend tests, Vitest, and Playwright.
- Scope stays within the approved v1 boundary: no self-registration, no mail reset flow, no strategy platform work, no landing page.
- The plan assumes `main` already contains `DashboardRoot` and the multi-user implementation; Task 2 validates that baseline explicitly rather than rebuilding it.
