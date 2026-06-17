# Dashboard Deployment Runbook

This runbook deploys the Stock Research dashboard frontend and API from the same `origin/dashboard` commit. The reference version for the current dashboard work is `2d2f223`.

## Current Diagnosis

The public site at `https://stock.manqiaotechnology.com/` was serving the old dashboard shell (`TOPN`, `WATCHLIST`, `ASSET REVIEW`). The old API could still answer `/api/dashboard/overview`, so the database was not completely disconnected. The missing endpoints `/api/platform/summary` and `/api/backtests/strategies` showed that the API process behind `/api` was also an older app version.

The fix is to deploy frontend and backend atomically from the same dashboard branch commit.

## Server Layout

Use these paths unless the server already has a stronger convention:

```bash
/opt/stock_research                  # git checkout of origin/dashboard
/opt/stock_research/.venv            # Python virtual environment
/opt/stock_research/.pg_service.conf # database service definitions for the API user
/var/www/stock-dashboard/releases    # versioned frontend builds
/var/www/stock-dashboard/current     # symlink used by nginx
```

The API service must be able to read `.pg_service.conf`. It must define all three services used by the dashboard:

```ini
[stock_research]

[stock_hfq]

[stock_qfq]
```

Do not rely on root's home directory for this file if systemd runs the service as `www-data`.

## Backend Deploy

```bash
cd /opt/stock_research
git fetch origin
git checkout dashboard
git pull --ff-only origin dashboard

python3 -m venv .venv
.venv/bin/python -m pip install -U pip
.venv/bin/python -m pip install -e ".[dashboard]"
```

Install the service template from `deploy/systemd/stock-research-dashboard-api.service`, adjusting `WorkingDirectory`, `ExecStart`, `User`, `Group`, and `PGSERVICEFILE` if the server paths differ.

```bash
sudo cp deploy/systemd/stock-research-dashboard-api.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable stock-research-dashboard-api
sudo systemctl restart stock-research-dashboard-api
sudo systemctl status stock-research-dashboard-api --no-pager
```

Database smoke checks must run as the same user that runs the service:

```bash
sudo -u www-data PGSERVICEFILE=/opt/stock_research/.pg_service.conf psql service=stock_research -c 'select 1'
sudo -u www-data PGSERVICEFILE=/opt/stock_research/.pg_service.conf psql service=stock_hfq -c 'select 1'
sudo -u www-data PGSERVICEFILE=/opt/stock_research/.pg_service.conf psql service=stock_qfq -c 'select 1'
```

## Frontend Deploy

```bash
cd /opt/stock_research/dashboard
pnpm install --frozen-lockfile
pnpm build

release="/var/www/stock-dashboard/releases/$(git -C .. rev-parse --short HEAD)"
sudo mkdir -p "$release"
sudo rsync -a --delete dist/ "$release/"
sudo ln -sfn "$release" /var/www/stock-dashboard/current
```

The deployed dashboard must show the new workspace, including `Research Cockpit`, `Data Explorer`, `Factor Lab`, and `Backtest Lab`. It should not show the old standalone `TOPN`, `WATCHLIST`, `ASSET REVIEW` homepage.

## Fast Docker Deploy On 192.168.3.185

The current 192.168.3.185 deployment keeps Docker Compose as the process
manager, but the containers mount the mutable app files from the host:

- `./src` is mounted into the API container at `/app/src`.
- `PYTHONPATH=/app/src` makes restarted API workers load the mounted source.
- `./dashboard/dist` is mounted into the dashboard nginx container at
  `/usr/share/nginx/html`.
- `./outputs/research` is mounted read/write into the API container at
  `/Users/xiwei/stock_research/outputs/research` so the strategy review queue
  sees the same lightweight strategy artifacts as the local dashboard and fresh
  backtests can write run artifacts.

For ordinary frontend and backend source changes, run:

```bash
./deploy/sync_dashboard_fast.sh
```

The script builds `dashboard/dist`, rsyncs `src/`, `dashboard/src/`, frontend
build inputs, `dashboard/dist/`, the current `strategy_daily_eod` review
directory, and the small strategy review artifact directories under
`outputs/research` to 192.168.3.185, then restarts the API and dashboard
containers. No image rebuild is needed for normal source changes.

Use a rebuild only when dependencies, Dockerfiles, or system packages change:

```bash
REBUILD=1 ./deploy/sync_dashboard_fast.sh
```

## Daily Local-To-185 Sync

Use `deploy/sync_dashboard_daily.sh` to keep the public Docker deployment in
sync with the local `v0.1-local-eod-web` worktree after the local dashboard has
been committed.

The daily wrapper:

- refuses to run when tracked files are dirty or untracked files exist outside
  `tmp/`;
- runs `deploy/sync_dashboard_fast.sh`;
- runs `deploy/check_dashboard_release.sh` against
  `https://stock.manqiaotechnology.com`;
- writes logs to `logs/dashboard_daily_sync.log`;
- uses a local lock directory to avoid overlapping runs.

Create a local-only environment file for credentials and host overrides:

```bash
cat > /Users/xiwei/.stock_research_dashboard_sync.env <<'EOF'
DASHBOARD_AUTH='user:password'
REMOTE_USER='jqz'
REMOTE_HOST='192.168.3.185'
SSH_OPTS='-o PreferredAuthentications=password -o PubkeyAuthentication=no'
EOF
chmod 600 /Users/xiwei/.stock_research_dashboard_sync.env
```

The env file must not be committed. For unattended launchd runs, configure SSH
so the sync script can connect to `192.168.3.185` without interactive input.
If password-only SSH remains required, run the daily wrapper manually.

Install the local launchd schedule:

```bash
cp deploy/launchd/com.stockresearch.dashboard-daily-sync.plist ~/Library/LaunchAgents/
launchctl unload ~/Library/LaunchAgents/com.stockresearch.dashboard-daily-sync.plist 2>/dev/null || true
launchctl load ~/Library/LaunchAgents/com.stockresearch.dashboard-daily-sync.plist
```

The default schedule is every day at 18:30 local time.

## Nginx Deploy

Install `deploy/nginx/stock-dashboard.conf` into the server's nginx site configuration. Keep Basic Auth if the site is private.

Key requirements:

- `/api/` proxies to `http://127.0.0.1:8765` without stripping `/api`.
- `/assets/` serves static frontend assets.
- `/` uses SPA fallback to `index.html`.
- `proxy_read_timeout` is at least `180s` because fresh comparisons can take close to a minute or more.

```bash
sudo nginx -t
sudo systemctl reload nginx
```

## Release Verification

Run the bundled check from any machine that can reach the public site:

```bash
cd /opt/stock_research
DASHBOARD_AUTH='mqkj:mqkj1234' ./deploy/check_dashboard_release.sh
```

The script verifies:

- The frontend is the new dashboard shell.
- `/api/platform/summary` returns successfully.
- `/api/backtests/strategies` exposes only the three combo strategies.
- `/api/assets/000001.SZ/profile` can read the asset profile path.
- `/api/backtests/run-fresh` is wired to real fresh execution.

Manual browser checks:

- Homepage has the new dashboard navigation.
- Strategy Catalog does not show `manual_v1_topn` or `position_control` as runnable strategies.
- Backtest Lab exposes `Run Fresh Backtest` and fresh comparison controls.
- `Load Cached Replay` is not available.

## Troubleshooting

If the frontend is still the old page, check the nginx `root` and the `current` symlink:

```bash
readlink -f /var/www/stock-dashboard/current
ls -la /var/www/stock-dashboard/current/assets
```

If `/api/platform/summary` returns 404, nginx is proxying to an old API process or the new service did not start:

```bash
sudo systemctl status stock-research-dashboard-api --no-pager
sudo journalctl -u stock-research-dashboard-api -n 100 --no-pager
```

If API endpoints return 500 and mention PostgreSQL service lookup or connection errors, verify `PGSERVICEFILE` and file permissions for `stock_research`, `stock_hfq`, and `stock_qfq`.

If fresh backtests timeout through the browser but work locally on the server, raise nginx `proxy_read_timeout` and confirm the API process remains healthy during execution.

## 回滚

Keep each frontend build in a versioned release directory. To roll back the frontend:

```bash
sudo ln -sfn /var/www/stock-dashboard/releases/<previous_commit> /var/www/stock-dashboard/current
sudo systemctl reload nginx
```

To roll back the backend:

```bash
cd /opt/stock_research
git checkout <previous_commit>
sudo systemctl restart stock-research-dashboard-api
```

After rollback, rerun the release verification command for the version you expect to serve.
