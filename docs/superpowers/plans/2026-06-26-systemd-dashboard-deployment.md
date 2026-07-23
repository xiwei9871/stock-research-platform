# Systemd Dashboard Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the daily external dashboard publish path with a non-container deployment that syncs validated local code/artifacts to the external host and restarts a systemd-managed API.

**Architecture:** Keep the existing external repository at `/home/jqz/code/stock-research-platform-main` as the release root. Publish frontend files to `/var/www/stock-dashboard/current`, run the API from a Python virtualenv with `uvicorn` under systemd, and keep `outputs/` plus `reports/` as ordinary host directories so daily artifacts are immediately visible without container path mapping.

**Current cutover status:** Completed on 2026-06-26. External traffic on `https://stock.manqiaotechnology.com` is served by host nginx on port `1234`, static files are served from `/var/www/stock-dashboard/current`, API requests are proxied to `127.0.0.1:8765`, and `stock-research-dashboard-api.service` is active. The old `api` and `dashboard` Docker containers for this app are stopped; other Docker services are unchanged.

**Daily publish command:**

```bash
REMOTE_SUDO_PASSWORD='...' LATEST_STRATEGY_DAILY_EOD='strategy_daily_eod/YYYY-MM-DD' ./deploy/sync_dashboard_systemd.sh
```

Then verify:

```bash
BASE_URL='https://stock.manqiaotechnology.com' \
DASHBOARD_AUTH='mqkj:mqkj1234' \
TRADE_DATE='YYYY-MM-DD' \
START_DATE='2026-01-01' \
END_DATE='YYYY-MM-DD' \
./deploy/check_dashboard_release.sh
```

**Tech Stack:** Bash, rsync, systemd, nginx, Python venv, uvicorn, Vite dashboard build.

---

### Task 1: Add a non-container sync script

**Files:**
- Create: `deploy/sync_dashboard_systemd.sh`
- Keep: `deploy/sync_dashboard_fast.sh` for Docker fallback until cutover is proven.

- [ ] **Step 1: Create `deploy/sync_dashboard_systemd.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail

REMOTE_USER="${REMOTE_USER:-jqz}"
REMOTE_HOST="${REMOTE_HOST:-192.168.3.185}"
REMOTE_DIR="${REMOTE_DIR:-/home/${REMOTE_USER}/code/stock-research-platform-main}"
SSH_OPTS="${SSH_OPTS:--o PreferredAuthentications=password -o PubkeyAuthentication=no}"
STRATEGY_OUTPUT_ROOT="${STRATEGY_OUTPUT_ROOT:-/Users/xiwei/stock_research/outputs/research}"
REPORTS_ROOT="${REPORTS_ROOT:-/Users/xiwei/stock_research/reports}"
SERVICE_NAME="${SERVICE_NAME:-stock-research-dashboard-api.service}"

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

find_latest_strategy_daily_eod() {
  find "${STRATEGY_OUTPUT_ROOT}/strategy_daily_eod" -mindepth 1 -maxdepth 1 -type d -name '????-??-??' 2>/dev/null \
    | sed "s#^${STRATEGY_OUTPUT_ROOT}/##" \
    | sort \
    | tail -1
}

LATEST_STRATEGY_DAILY_EOD="${LATEST_STRATEGY_DAILY_EOD:-$(find_latest_strategy_daily_eod)}"
if [[ -z "$LATEST_STRATEGY_DAILY_EOD" ]]; then
  echo "No strategy_daily_eod artifact directory found under ${STRATEGY_OUTPUT_ROOT}" >&2
  exit 1
fi

strategy_output_dirs=(
  "$LATEST_STRATEGY_DAILY_EOD"
  "official_strategy_contract_rescan_20260101_20260617_fresh_all"
  "web_lhb_shortline_v1_runs"
  "mid_trend_shadow_top10_context_fixed_20260602"
  "mid_trend_refresh_20260602"
  "tech_bottleneck_discovery_v0_1_closeout_20260608"
  "web_tech_bottleneck_v1_runs/tech_bottleneck_v1_20260616_manual"
)

echo "Building dashboard frontend"
(cd "$repo_root/dashboard" && pnpm build)

echo "Syncing backend source"
rsync -az --delete -e "ssh ${SSH_OPTS}" "$repo_root/src/" "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_DIR}/src/"

echo "Syncing frontend source and static build"
rsync -az --delete -e "ssh ${SSH_OPTS}" "$repo_root/dashboard/src/" "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_DIR}/dashboard/src/"
rsync -az --delete -e "ssh ${SSH_OPTS}" "$repo_root/dashboard/dist/" "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_DIR}/dashboard/dist/"
rsync -az -e "ssh ${SSH_OPTS}" \
  "$repo_root/dashboard/index.html" \
  "$repo_root/dashboard/package.json" \
  "$repo_root/dashboard/pnpm-lock.yaml" \
  "$repo_root/dashboard/tsconfig.json" \
  "$repo_root/dashboard/vite.config.ts" \
  "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_DIR}/dashboard/"

rsync -az -e "ssh ${SSH_OPTS}" \
  "$repo_root/pyproject.toml" \
  "$repo_root/README.md" \
  "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_DIR}/"

echo "Syncing strategy review artifacts"
ssh ${SSH_OPTS} "${REMOTE_USER}@${REMOTE_HOST}" "mkdir -p '${REMOTE_DIR}/outputs/research'"
for output_dir in "${strategy_output_dirs[@]}"; do
  if [[ -d "${STRATEGY_OUTPUT_ROOT}/${output_dir}" ]]; then
    ssh ${SSH_OPTS} "${REMOTE_USER}@${REMOTE_HOST}" "mkdir -p '${REMOTE_DIR}/outputs/research/${output_dir}'"
    rsync -az -e "ssh ${SSH_OPTS}" \
      "${STRATEGY_OUTPUT_ROOT}/${output_dir}/" \
      "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_DIR}/outputs/research/${output_dir}/"
  else
    echo "Skipping missing strategy output directory: ${STRATEGY_OUTPUT_ROOT}/${output_dir}"
  fi
done

echo "Syncing report artifacts"
if [[ -d "${REPORTS_ROOT}" ]]; then
  ssh ${SSH_OPTS} "${REMOTE_USER}@${REMOTE_HOST}" "mkdir -p '${REMOTE_DIR}/reports'"
  rsync -az -e "ssh ${SSH_OPTS}" \
    "${REPORTS_ROOT}/" \
    "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_DIR}/reports/"
else
  echo "Skipping missing reports directory: ${REPORTS_ROOT}"
fi

echo "Restarting systemd API service"
ssh ${SSH_OPTS} "${REMOTE_USER}@${REMOTE_HOST}" "sudo systemctl restart '${SERVICE_NAME}'"

echo "Systemd dashboard sync complete"
```

- [ ] **Step 2: Make the script executable**

Run: `chmod +x deploy/sync_dashboard_systemd.sh`

- [ ] **Step 3: Verify it builds locally without running remote operations**

Run: `bash -n deploy/sync_dashboard_systemd.sh`

Expected: exit code `0`.

---

### Task 2: Add a systemd API unit for the external host

**Files:**
- Modify: `deploy/systemd/stock-research-dashboard-api.service`

- [ ] **Step 1: Update the service to run from the external release root**

```ini
[Unit]
Description=Stock Research Dashboard API
After=network.target

[Service]
Type=simple
WorkingDirectory=/home/jqz/code/stock-research-platform-main
Environment=PYTHONPATH=/home/jqz/code/stock-research-platform-main/src
Environment=STOCK_RESEARCH_OUTPUT_ROOT=/home/jqz/code/stock-research-platform-main/outputs
Environment=STOCK_RESEARCH_REPORTS_ROOT=/home/jqz/code/stock-research-platform-main/reports
EnvironmentFile=/home/jqz/code/stock-research-platform-main/.env
ExecStart=/home/jqz/code/stock-research-platform-main/.venv/bin/python -m uvicorn stock_research.dashboard.app:app --host 127.0.0.1 --port 8765 --http h11
Restart=always
RestartSec=5
User=jqz
Group=jqz

[Install]
WantedBy=multi-user.target
```

- [ ] **Step 2: Install the unit on the external host**

Run:

```bash
sudo cp deploy/systemd/stock-research-dashboard-api.service /etc/systemd/system/stock-research-dashboard-api.service
sudo systemctl daemon-reload
sudo systemctl enable stock-research-dashboard-api.service
sudo systemctl restart stock-research-dashboard-api.service
```

- [ ] **Step 3: Verify the service**

Run:

```bash
systemctl status stock-research-dashboard-api.service --no-pager
curl -fsS http://127.0.0.1:8765/api/platform/display-date
```

Expected: service is `active (running)` and curl returns JSON with `display_trade_date`.

---

### Task 3: Point nginx to the systemd API and static dist

**Files:**
- Modify: external nginx config for `stock.manqiaotechnology.com`

- [ ] **Step 1: Update the server block**

Use the active nginx config that owns public port `1234` for `stock.manqiaotechnology.com`. Set:

```nginx
root /var/www/stock-dashboard/current;

location /api/ {
    proxy_pass http://127.0.0.1:8765;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_read_timeout 180s;
    proxy_send_timeout 180s;
}

location /assets/ {
    try_files $uri =404;
    expires 30d;
    add_header Cache-Control "public, immutable";
}

location / {
    try_files $uri $uri/ /index.html;
}
```

- [ ] **Step 2: Validate and reload nginx**

Run:

```bash
sudo nginx -t
sudo systemctl reload nginx
```

Expected: `syntax is ok`, `test is successful`.

- [ ] **Step 3: Verify the external URL**

Run:

```bash
curl -fsS -u 'mqkj:mqkj1234' https://stock.manqiaotechnology.com/api/platform/display-date
```

Expected: JSON shows the same display date as the internal validated dashboard.

---

### Task 4: Disable the old dashboard containers after systemd passes

**Files:**
- External host only.

- [ ] **Step 1: Stop only this app's old containers**

Run from `/home/jqz/code/stock-research-platform-main`:

```bash
docker compose stop api dashboard
```

- [ ] **Step 2: Confirm nginx still serves the site**

Run:

```bash
curl -fsS -u 'mqkj:mqkj1234' https://stock.manqiaotechnology.com/api/platform/display-date
curl -fsS -u 'mqkj:mqkj1234' https://stock.manqiaotechnology.com/api/review-queue?trade_date=2026-06-26\&limit=20
```

Expected: both return `200`.

---

### Task 5: Final release verification

**Files:**
- Existing: `deploy/check_dashboard_release.sh`

- [ ] **Step 1: Run the existing release check against external**

Run:

```bash
BASE_URL='https://stock.manqiaotechnology.com' \
DASHBOARD_AUTH='mqkj:mqkj1234' \
TRADE_DATE='2026-06-26' \
START_DATE='2026-01-01' \
END_DATE='2026-06-26' \
./deploy/check_dashboard_release.sh
```

Expected: `Dashboard release check passed.`

- [ ] **Step 2: Verify daily publish command**

Run the new command for a known good artifact date:

```bash
LATEST_STRATEGY_DAILY_EOD='strategy_daily_eod/2026-06-26' ./deploy/sync_dashboard_systemd.sh
```

Expected: frontend builds, files sync, systemd API restarts, and release check passes afterward.
