# Platform Internal Auth Smoke Runbook

This runbook is for internal network only. It verifies first-party dashboard auth on an intranet host before any public or staging external exposure.

## Scope

In scope:

- First-party login and session cookies.
- Admin user management visibility and `/api/admin/users`.
- Regular user cannot see `用户管理`.
- API request id echo.
- SPA fallback and `/api/` reverse proxy separation.
- `X-Dashboard-Write-Token` still protects guarded writes after login.

Out of scope:

- Public internet access.
- Basic Auth or external identity provider validation.
- HTTPS-only cookie validation.
- Trading, strategy publishing, research delivery, Agent, or RAG.

## Runtime Env

For internal HTTP smoke, keep auth required but do not mark cookies Secure:

```dotenv
STOCK_RESEARCH_DASHBOARD_AUTH_REQUIRED=true
STOCK_RESEARCH_DASHBOARD_COOKIE_SECURE=false
STOCK_RESEARCH_DASHBOARD_SESSION_TTL_SECONDS=43200
```

`STOCK_RESEARCH_DASHBOARD_COOKIE_SECURE=true` should be used later for HTTPS staging/public access.

Bootstrap auth on the server:

```bash
stock-research dashboard-auth-init
stock-research dashboard-admin-create --username admin --password '<internal-secret>' --role admin
stock-research dashboard-admin-create --username analyst --password '<internal-secret>' --role user
```

Basic Auth is not required for this internal smoke. Keep the network restricted to trusted office/VPN subnets.

## Scripted Smoke

Run against the internal dashboard URL:

```bash
python scripts/smoke_platform_external_access.py \
  --base-url http://stock-research-internal.local \
  --internal \
  --check-first-party-auth \
  --auth-username admin \
  --auth-password '<internal-secret>' \
  --check-admin-users \
  --check-regular-user-admin-denied \
  --regular-auth-username analyst \
  --regular-auth-password '<internal-secret>' \
  --check-write-guard
```

Expected result:

- `access_mode=internal`
- `/` returns the React app.
- `/api/platform/summary` returns 200 and echoes `X-Request-ID`.
- `/api/__external_smoke_missing` is not served by SPA fallback.
- `/api/auth/me` rejects missing session.
- `/api/auth/login` returns a session cookie.
- `/api/auth/me` accepts the session cookie.
- `/api/admin/users` returns 200 for the admin account.
- A regular user login succeeds, but `/api/admin/users` is rejected.
- A guarded write without `X-Dashboard-Write-Token` is rejected.

## Manual Browser Smoke

1. Open the internal URL.
2. Confirm the first screen is the login view.
3. Log in as admin.
4. Confirm dashboard shell loads.
5. Confirm `用户管理` is visible to admin.
6. Create or verify a regular user.
7. Log out or use a fresh browser session.
8. Log in as the regular user.
9. Confirm `用户管理` is not visible.
10. Open read-only dashboard views and confirm they load without write actions.
11. Confirm browser network requests use relative `/api/...`, not `localhost`.
12. Confirm readiness and platform summary APIs work.
13. Confirm guarded writes still require `X-Dashboard-Write-Token`.

## Internal Release Blockers

- Do not call this public-ready.
- Do not expose PostgreSQL.
- Do not put the write token in the frontend bundle.
- Do not disable `STOCK_RESEARCH_DASHBOARD_AUTH_REQUIRED` for shared internal access.
- Do not use this runbook as proof that HTTPS Secure cookies work; that belongs to external/staging smoke.
