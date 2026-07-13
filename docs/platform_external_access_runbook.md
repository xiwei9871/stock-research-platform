# Platform External Access Runbook

This runbook covers the platform shell only: React dashboard static hosting, FastAPI `/api/` reverse proxy, read-only views, write guardrails, and operations. It does not enable research external delivery, strategy publishing, trading, Agent, or RAG flows.

## Runtime Shape

- Build the frontend with `pnpm --dir dashboard build`; Nginx serves `dashboard/dist`.
- Run the API with `stock-research dashboard-api --host 127.0.0.1 --port 8765`.
- Nginx exposes `/api/` by proxying to FastAPI.
- Nginx serves all other frontend paths through SPA fallback: `try_files $uri /index.html`.
- PostgreSQL must not be exposed publicly; FastAPI is the only database client behind the proxy.

## Nginx

Use `deploy/nginx/stock_research_dashboard.conf.example` as the starting point.

Required properties:

- static root points at `dashboard/dist`
- `/api/` proxies to `127.0.0.1:8765`
- `Host`, `X-Forwarded-For`, and `X-Forwarded-Proto` are forwarded
- `client_max_body_size` is set explicitly
- static assets can use cache headers
- WebSocket support is not required by the current dashboard

Terminate HTTPS either in this Nginx server block or in an upstream load balancer. Preserve `X-Forwarded-Proto` so request logs and future auth integrations can distinguish HTTP from HTTPS.

## FastAPI Service

Use `deploy/systemd/stock-research-api.service.example` and `deploy/env/.env.dashboard.example`.

The service should bind to `127.0.0.1`, not a public interface. Keep `STOCK_RESEARCH_DASHBOARD_WRITE_TOKEN`, `PGSERVICEFILE`, and database credentials in server-side environment files only.

Do not bind FastAPI to `0.0.0.0` for normal deployment. If a temporary public bind is unavoidable during debugging, restrict it with cloud security groups and IP allowlists, and remove it after the test window. The database port must not be opened to the public internet.

Suggested operations:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now stock-research-api
sudo systemctl status stock-research-api
journalctl -u stock-research-api -f
```

## Auth And Guardrails

The dashboard now supports first-party auth with a Postgres-backed identity schema, cookie sessions, CSRF protection for authenticated writes, and `admin` / `user` roles. Enable it for staging or external access with:

```dotenv
STOCK_RESEARCH_DASHBOARD_AUTH_REQUIRED=true
STOCK_RESEARCH_DASHBOARD_COOKIE_SECURE=true
STOCK_RESEARCH_DASHBOARD_SESSION_TTL_SECONDS=43200
```

Bootstrap the identity schema and first admin from the server:

```bash
stock-research dashboard-auth-init
stock-research dashboard-admin-create --username admin --password '<local-secret>' --role admin
```

- Basic Auth can be removed only after first-party auth login, logout, session refresh, and admin user management have been verified on staging.
- Basic Auth or an upstream auth proxy may still be kept as an additional staging/internal access gate; it is not application role authorization.
- `X-Dashboard-Write-Token` remains required for existing guarded writes and is not replaced by dashboard login.
- Official research views remain read-only for regular users in this phase.
- Read-only dashboard pages should call GET APIs only.
- Platform `readiness` and publication guardrails remain separate from research queue publish checks.
- Request tracing uses `X-Request-ID`; the API echoes the header when provided.

## Smoke Checks

After deployment:

```bash
curl -i https://stock-research.example.com/
curl -i https://stock-research.example.com/api/platform/readiness
curl -i -H 'X-Request-ID: external-smoke-001' https://stock-research.example.com/api/platform/summary
```

Expected:

- `/` returns the React shell.
- frontend deep links return `index.html` through SPA fallback.
- `/api/platform/readiness` returns JSON.
- `X-Request-ID` is present in API responses.

## Logs

- Nginx access log: `/var/log/nginx/stock_research_dashboard.access.log`
- Nginx error log: `/var/log/nginx/stock_research_dashboard.error.log`
- API service logs: `journalctl -u stock-research-api`

## Current External Access Blockers

- First-party auth must be smoke-tested on the target host with HTTPS and `STOCK_RESEARCH_DASHBOARD_COOKIE_SECURE=true`.
- Keep external access limited to staging/internal users until account lifecycle, password rotation, and audit review are operationally accepted.
- Do not expose PostgreSQL, write tokens, or service credentials to the public internet or frontend bundle.
