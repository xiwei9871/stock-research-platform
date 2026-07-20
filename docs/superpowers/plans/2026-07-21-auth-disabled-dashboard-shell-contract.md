# Auth-Disabled Dashboard Shell Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the explicitly auth-disabled local profile return a stable synthetic current user so the Dashboard shell and read-only Playwright profile agree on one authentication contract.

**Architecture:** Keep session-backed behavior unchanged whenever `STOCK_RESEARCH_DASHBOARD_AUTH_REQUIRED=true`. When authentication is explicitly disabled, `/api/auth/me` returns a deterministic in-memory admin read model without querying the session store or setting cookies; other write guards remain independent and unchanged.

**Tech Stack:** FastAPI, Python dataclasses, pytest, Playwright.

---

## File Structure

- `src/stock_research/dashboard/auth_service.py`: owns the deterministic auth-disabled current-user factory.
- `src/stock_research/dashboard/app.py`: applies the auth-mode branch at `/api/auth/me`.
- `tests/test_dashboard_auth_required.py`: proves disabled/enabled behavior and prevents session-store access in disabled mode.
- `dashboard/tests/e2e/real/critical-journeys.spec.ts`: remains the end-to-end acceptance contract.

### Task 1: Freeze The Backend Contract With Failing Tests

**Files:**
- Modify: `tests/test_dashboard_auth_required.py`

- [ ] **Step 1: Add the auth-disabled `/api/auth/me` test**

```python
def test_auth_me_returns_local_admin_when_auth_is_disabled(monkeypatch):
    monkeypatch.setenv("STOCK_RESEARCH_DASHBOARD_AUTH_REQUIRED", "false")
    monkeypatch.setattr(
        dashboard_app,
        "load_current_user_from_session",
        lambda _token: (_ for _ in ()).throw(AssertionError("session lookup must not run")),
    )
    client = TestClient(dashboard_app.create_app())

    response = client.get("/api/auth/me")

    assert response.status_code == 200
    assert response.json() == {
        "user": {
            "user_id": "dashboard-auth-disabled",
            "username": "local",
            "display_name": "Local Operator",
            "role": "admin",
            "is_active": True,
        }
    }
    assert "set-cookie" not in response.headers
```

- [ ] **Step 2: Strengthen the auth-required regression**

Keep `test_dashboard_api_allows_auth_routes_when_auth_required` and assert `/api/auth/me` remains `401/not_authenticated` without a valid session.

- [ ] **Step 3: Run the focused test and verify RED**

Run:

```bash
rtk /Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_dashboard_auth_required.py -q
```

Expected: the new disabled-mode test fails because `/api/auth/me` currently returns 401.

### Task 2: Implement The Synthetic Disabled-Mode Identity

**Files:**
- Modify: `src/stock_research/dashboard/auth_service.py`
- Modify: `src/stock_research/dashboard/app.py`

- [ ] **Step 1: Add a typed factory in `auth_service.py`**

```python
def auth_disabled_current_user() -> CurrentUser:
    return CurrentUser(
        user_id="dashboard-auth-disabled",
        username="local",
        display_name="Local Operator",
        role="admin",
        is_active=True,
    )
```

- [ ] **Step 2: Branch only the `/api/auth/me` endpoint**

Import the factory in `app.py` and make the endpoint start with:

```python
if not _dashboard_auth_required():
    return {"user": current_user_read_model(auth_disabled_current_user())}
```

Leave login, logout, session creation, middleware, CSRF enforcement, and the dashboard write guard unchanged.

- [ ] **Step 3: Run backend regressions**

Run:

```bash
rtk /Users/xiwei/stock_research/.venv/bin/python -m pytest \
  tests/test_dashboard_auth_required.py \
  tests/test_dashboard_app.py \
  tests/test_dashboard_auth_api.py \
  tests/test_dashboard_user_admin.py -q
```

Expected: PASS.

- [ ] **Step 4: Commit the backend contract**

```bash
git add src/stock_research/dashboard/auth_service.py src/stock_research/dashboard/app.py tests/test_dashboard_auth_required.py
git commit -m "fix: align auth-disabled dashboard identity"
```

### Task 3: Verify The Browser Shell And Security Boundary

**Files:**
- No product-file changes expected.

- [ ] **Step 1: Run the focused Real prerequisite**

```bash
cd dashboard
PLAYWRIGHT_PROFILE=real \
PLAYWRIGHT_DASHBOARD_PORT=5374 \
PLAYWRIGHT_API_PORT=8966 \
pnpm exec playwright test tests/e2e/real/critical-journeys.spec.ts \
  --grep "auth-disabled Real profile" \
  --project=chromium-desktop
```

Expected: PASS with `/api/auth/me=200` and `/api/platform/summary=200`.

- [ ] **Step 2: Run the P0 auth suite**

```bash
cd dashboard
PLAYWRIGHT_PROFILE=mock pnpm exec playwright test tests/e2e/p0/auth.spec.ts
```

Expected: PASS; auth-required login/logout/expiry behavior is unchanged.

- [ ] **Step 3: Run full affected verification**

```bash
rtk /Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_dashboard_auth_required.py tests/test_dashboard_app.py -q
cd dashboard && rtk pnpm test -- --run && rtk pnpm build
```

Expected: all commands exit 0.

- [ ] **Step 4: Re-run the frozen Real profile with a new audit ID**

Do not overwrite `pv-initial-20260720-372f4a5`. The new run must prove the auth root is closed before any baseline is promoted.
