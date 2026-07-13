# Platform External Access Auth Proxy Smoke Runbook

This runbook covers staging/internal access only. It uses Nginx Basic Auth and optional IP allowlist as an upstream access gate so selected reviewers can smoke test the dashboard while first-party dashboard auth is enabled and verified.

Basic Auth is not application role authorization. Application login, admin/user roles, user management, and cookie sessions are handled by first-party auth inside the dashboard API.

## Scope

In scope:

- Nginx serves `dashboard/dist`.
- Nginx protects `/` and `/api/` with Basic Auth and optional IP allowlist.
- Nginx proxies `/api/` to FastAPI on `127.0.0.1:8765`.
- SPA fallback returns `index.html` for frontend paths.
- FastAPI first-party auth, guardrails, `X-Request-ID`, readiness, and write-token behavior are smoke tested.

Out of scope:

- public multi-user authorization
- research delivery
- strategy publishing
- trading

## Nginx Staging Config

Start from:

```text
deploy/nginx/stock_research_dashboard.staging_basic_auth.conf.example
```

Required properties:

- `auth_basic` protects the server block.
- `auth_basic_user_file` points to an htpasswd file outside the repo.
- Optional `allow` / `deny all` restrict access to reviewer or VPN egress IPs.
- `root` points to `/opt/stock_research/dashboard/dist`.
- `/api/` proxies to `http://127.0.0.1:8765`.
- `Host`, `X-Real-IP`, `X-Forwarded-For`, and `X-Forwarded-Proto` are forwarded.
- `client_max_body_size` is explicit.
- PostgreSQL and database port access remain private.
- `X-Dashboard-Write-Token` stays server-side and never enters the frontend bundle.
- Current dashboard does not need WebSocket support.

Example htpasswd creation:

```bash
sudo htpasswd -c /etc/nginx/.htpasswd-stock-research-dashboard reviewer
sudo nginx -t
sudo systemctl reload nginx
```

## FastAPI And Runtime

Use:

```bash
stock-research dashboard-api --host 127.0.0.1 --port 8765
```

Enable first-party auth in the server-side env:

```dotenv
STOCK_RESEARCH_DASHBOARD_AUTH_REQUIRED=true
STOCK_RESEARCH_DASHBOARD_COOKIE_SECURE=true
STOCK_RESEARCH_DASHBOARD_SESSION_TTL_SECONDS=43200
```

Initialize auth before reviewer access:

```bash
stock-research dashboard-auth-init
stock-research dashboard-admin-create --username admin --password '<local-secret>' --role admin
```

With systemd, use:

```text
deploy/systemd/stock-research-api.service.example
deploy/env/.env.dashboard.example
```

Do not bind FastAPI to `0.0.0.0` for normal staging. If public bind is temporarily required for debugging, restrict it with security groups and IP allowlists.

## Manual Smoke Checklist

1. Open `/` with Basic Auth credentials. It should show the first-party login view before dashboard content.
2. Refresh a frontend path such as `/research/data-to-brief/docling-90`; it should not return 404 because SPA fallback is active.
3. Open `/api/auth/me` without a first-party session; it should return controlled 401/403.
4. Log in with the bootstrap admin account. `/api/auth/me` should return that user through the session cookie.
5. Open admin user management. `/api/admin/users` should return 200 for the admin session.
6. Log in as a regular user if one exists; the `用户管理` navigation should not be visible.
7. Open `/api/platform/summary`; it should return 200 JSON after Basic Auth and first-party auth where required.
8. Confirm API responses include `X-Request-ID`.
9. Call a write endpoint without `X-Dashboard-Write-Token`; it should be rejected even after first-party login.
10. Call a write endpoint with a wrong token; it should also be rejected.
11. Open `/api/platform/readiness`; readiness/publication guardrail data should be returned normally.
12. Confirm JS/CSS static resources load without 404.
13. Browser console should not show production requests to `localhost` or `127.0.0.1`.
14. Confirm Nginx access log and error log record the request path and status.
15. Restart `stock-research-api` through systemd; `/api/platform/summary` should recover.
16. Confirm the Nginx root points at the current dashboard build artifact.

## Scripted Smoke

Run:

```bash
python scripts/smoke_platform_external_access.py \
  --base-url https://stock-research-staging.example.com \
  --basic-auth-user reviewer \
  --basic-auth-password 'replace-locally' \
  --check-first-party-auth \
  --auth-username admin \
  --auth-password 'replace-locally' \
  --check-admin-users \
  --check-write-guard
```

To confirm Basic Auth challenge without credentials:

```bash
python scripts/smoke_platform_external_access.py \
  --base-url https://stock-research-staging.example.com \
  --expect-auth
```

The script prints a JSON summary and exits non-zero on clear failures.

## Boundaries

This smoke setup is for staging/internal access. It does not make the dashboard a formal public multi-user platform. Formal public access still requires staging acceptance of first-party auth operations, account lifecycle, password rotation, and audit review.
