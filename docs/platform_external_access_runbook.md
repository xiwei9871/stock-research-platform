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

## Canonical Release Entry Point

`deploy/sync_dashboard_release.sh` 是外部仪表盘发布的唯一入口 (the only supported external dashboard release entry point). Do not publish directly from validation branches or `.worktrees` directories. The script fails closed unless the selected release root is clean (including untracked files), the selected Python imports `stock_research` from that root, and the exact dated strategy artifact directory exists.

Required operational inputs are normally stored in the server-only file selected by `DASHBOARD_SYNC_ENV` (default `/Users/xiwei/.stock_research_dashboard_sync.env`):

```dotenv
STOCK_RESEARCH_RELEASE_ROOT=/Users/xiwei/stock_research_release_YYYYMMDD
# Optional manual override; omit for LaunchAgent dynamic resolution.
# EXPECTED_TRADE_DATE=YYYY-MM-DD
LOCAL_READINESS_URL=http://127.0.0.1:8765/api/platform/readiness
STOCK_RESEARCH_PYTHON=/absolute/path/to/python
REMOTE_USER=deployment-user
REMOTE_HOST=deployment-host
REMOTE_DIR=/absolute/remote/release/path
SSH_OPTS=-o BatchMode=yes
STOCK_RESEARCH_SSH_CONFIG=/Users/xiwei/.ssh/stock-research-dashboard.conf
STRATEGY_OUTPUT_ROOT=/absolute/local/outputs/research
DASHBOARD_REMOTE_ENV_FILE=.env.dashboard
DASHBOARD_PGSERVICE_FILE=.pg_service.conf
STOCK_RESEARCH_COMPOSE_PROJECT=stock_research_dashboard
DASHBOARD_API_BIND_PORT=8765
DASHBOARD_FRONTEND_BIND_PORT=5174
BASE_URL=https://stock.manqiaotechnology.com
DASHBOARD_AUTH=user:password
REMOTE_CONTAINER_RELEASE_ROOT=/app
```

`EXPECTED_TRADE_DATE` is an optional explicit override. When it is absent (the normal LaunchAgent path), the script accepts `latest_market_date` from `LOCAL_READINESS_URL` only when that process proves it is running the selected Git release and exact source/package roots. Otherwise the already import-validated `STOCK_RESEARCH_PYTHON` runs the selected release's `stock_research.dashboard.platform.load_platform_summary()` directly with `PYTHONPATH=$STOCK_RESEARCH_RELEASE_ROOT/src`, using the same inherited database/service configuration. The script then validates that exact date's publish summary, manifest, and three review CSVs. It never infers the market date from whichever strategy artifact directory happens to be newest and never starts or trusts an old API process. Without an explicit Python override, the script prefers `$STOCK_RESEARCH_RELEASE_ROOT/.venv/bin/python` and falls back to `/Users/xiwei/stock_research/.venv/bin/python`, while still requiring `stock_research.__file__` to belong to the selected release.

`REMOTE_USER`, `REMOTE_HOST`, and `REMOTE_DIR` retain the existing defaults (`jqz`, `192.168.3.185`, and `/home/$REMOTE_USER/code/stock-research-platform-main`) but should be set explicitly outside that host. SSH defaults to `BatchMode=yes`; use a dedicated host entry through `STOCK_RESEARCH_SSH_CONFIG`. Legacy `SSH_OPTS` remains an explicit compatibility override, accepts only simple option tokens, and should not be used to restore password-only automation. The script verifies SSH and `docker compose` before the first `rsync`. `DASHBOARD_AUTH` is passed only to the release check and must not be committed or embedded in the frontend.

The release sync uses only the complete version-controlled `deploy/dashboard-release.compose.yml`; it never merges an unknown remote Compose file. Every Compose command uses the explicit `STOCK_RESEARCH_COMPOSE_PROJECT` name (default `stock_research_dashboard`). The canonical stack builds both images, binds the API to host `127.0.0.1:8765`, binds the frontend to host `127.0.0.1:5174`, and connects them on the dedicated `stock-research-dashboard-release` network. The frontend Nginx container proxies `/api/` to `api:8765`. Server-only application variables come from `DASHBOARD_REMOTE_ENV_FILE`; PostgreSQL service configuration comes from `DASHBOARD_PGSERVICE_FILE`. Both files must already exist on the remote and are never synchronized from the repository.

Before synchronization, the remote preflight lists Compose projects/containers and checks host listeners with `ss` (falling back to `lsof` or `netstat`). It enumerates all running and stopped containers labeled with the selected project and permits only the `api` and `dashboard` services. Port 8765 may be occupied only by that project's `api` service, and port 5174 only by its `dashboard` service. Same-project orphan services (including stopped or portless workers), other projects, non-Compose containers, and non-Docker listeners all fail with a migration message; the script never stops them. One-time migration is operator-owned: inspect the reported container/project, intentionally run its own `docker compose --project-name <legacy-project> down` from the legacy deployment, verify the ports are free, then rerun the canonical release. If the legacy service must remain, select approved `DASHBOARD_API_BIND_PORT` / `DASHBOARD_FRONTEND_BIND_PORT` overrides and update the outer reverse proxy before release. Canonical `compose up` uses `--remove-orphans` only after the ownership preflight and image build succeed.

Frontend dependencies are installed from `dashboard/pnpm-lock.yaml` with `--frozen-lockfile`. `deploy/dashboard-api-requirements.lock` is generated from `deploy/dashboard-api-requirements.in` with pip-tools and contains the complete transitive graph plus hashes; the image installs it with `--require-hashes`, then installs the local package with `--no-deps`. Base images are fixed to the official manifest-list references `python:3.12.11-slim-bookworm@sha256:519591d6871b7bc437060736b9f7456b8731f1499a57e22e6c285135ae657bf7` and `nginx:1.27.5-alpine@sha256:65645c7bb6a0661892a8b03b89d0743208a18dd2f3f17a54ef4b76fb8e2f2a10`. `dashboard/dist/release.json` records those exact references; the release gate checks the public metadata plus the container source/package roots.

Regenerate the API lock only through `pip-compile --generate-hashes --allow-unsafe --output-file deploy/dashboard-api-requirements.lock deploy/dashboard-api-requirements.in`, review the complete diff, and verify it with `pip install --dry-run --require-hashes -r deploy/dashboard-api-requirements.lock` before release.

Run the release only after the official strategy publisher has completed successfully:

```bash
STOCK_RESEARCH_RELEASE_ROOT=/Users/xiwei/stock_research_release_YYYYMMDD \
EXPECTED_TRADE_DATE=YYYY-MM-DD \
deploy/sync_dashboard_release.sh
```

Before any remote mutation, the script validates the publish summary, manifest, and all three official review CSVs for the selected platform date. A date returned by `LOCAL_READINESS_URL` is accepted only when that process reports the current Git release ID and the exact selected source/package roots; otherwise the current release's direct platform loader is authoritative. The command then builds one `release_id`, syncs backend source, the canonical `dashboard/dist`, and only `outputs/research/strategy_daily_eod/$EXPECTED_TRADE_DATE`, rebuilds and recreates the API and dashboard services, then waits at most 120 seconds for the readiness and Review Queue contracts.

### 回滚

Keep the previous clean release root and commit available. To roll back, set `STOCK_RESEARCH_RELEASE_ROOT` to that root, set `EXPECTED_TRADE_DATE` to the artifact date that belongs to it, and run the same `deploy/sync_dashboard_release.sh` entry point. The same provenance and Review Queue gates apply; do not bypass `deploy/check_dashboard_release.sh` or manually copy only frontend/backend files.

## Logs

- Nginx access log: `/var/log/nginx/stock_research_dashboard.access.log`
- Nginx error log: `/var/log/nginx/stock_research_dashboard.error.log`
- API service logs: `journalctl -u stock-research-api`

## Current External Access Blockers

- First-party auth must be smoke-tested on the target host with HTTPS and `STOCK_RESEARCH_DASHBOARD_COOKIE_SECURE=true`.
- Keep external access limited to staging/internal users until account lifecycle, password rotation, and audit review are operationally accepted.
- Do not expose PostgreSQL, write tokens, or service credentials to the public internet or frontend bundle.
