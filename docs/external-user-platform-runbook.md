# External User Platform Runbook

This runbook covers the externally deployed dashboard user platform at the production root domain. The production shape is same-origin:

- `https://stock.manqiaotechnology.com/` serves the built dashboard frontend.
- `https://stock.manqiaotechnology.com/api/*` reverse proxies to the internal FastAPI service on `127.0.0.1:8000`.
- There is no production Basic Auth layer at the root. The dashboard login view is the only product login surface.

## First Deployment

1. Prepare the host checkout and Python environment:

```bash
cd /opt/stock-research
git fetch --all
git checkout main
# or: git checkout <release-tag>
# or: git checkout <release-commit>
/opt/stock-research/.venv/bin/pip install -e .
```

Use a durable release ref on the host. Do not deploy from an ephemeral feature branch name.

2. Build the frontend bundle that Nginx serves from the root:

```bash
cd /opt/stock-research/dashboard
pnpm install --frozen-lockfile
pnpm build
```

3. Install the example systemd and Nginx configs, then review any environment-specific paths before enabling them:

```bash
sudo cp /opt/stock-research/deploy/systemd/stock-research-dashboard-api.service /etc/systemd/system/
sudo cp /opt/stock-research/deploy/nginx/stock.manqiaotechnology.com.conf.example /etc/nginx/conf.d/stock.manqiaotechnology.com.conf
sudo systemctl daemon-reload
sudo systemctl enable --now stock-research-dashboard-api
sudo nginx -t
sudo systemctl reload nginx
```

4. Verify the deployed shape:

```bash
curl -I https://stock.manqiaotechnology.com/
curl -I https://stock.manqiaotechnology.com/api/auth/me
sudo systemctl status stock-research-dashboard-api --no-pager
```

Expected results:

- `/` returns the frontend shell from `/opt/stock-research/dashboard/dist`.
- `/api/auth/me` returns `401 Unauthorized` before login.
- The API service is running on `127.0.0.1:8000`.

Notes:

- `deploy/systemd/stock-research-dashboard-api.service` sets `STOCK_RESEARCH_SECURE_COOKIES=1`; keep that enabled in production HTTPS.
- The API applies the `identity`, `watchlist`, `journal`, and `audit` schema objects on startup. No separate migration step is required for this user platform scope.

## Create The First Admin

Run the bootstrap CLI once, on the production host, after the API package is installed:

```bash
cd /opt/stock-research
/opt/stock-research/.venv/bin/stock-research dashboard-bootstrap-admin \
  --username admin \
  --display-name 'Platform Admin' \
  --email admin@example.com
```

The command prompts for the password twice. For controlled automation, you can pass `--password`, but interactive entry is safer for the first production admin.

Success output:

```text
dashboard_admin_bootstrapped|admin
```

Important behavior:

- The bootstrap command only works when there is no active admin account yet.
- The command writes an audit row with action `bootstrap_admin_account`.

## Admin Login

1. Open `https://stock.manqiaotechnology.com/`.
2. Confirm the root path shows the dashboard login view, not a Basic Auth prompt.
3. Sign in with either the admin username or admin email plus the password set during bootstrap.
4. After login, confirm the `用户管理` button is visible in the shell.

If login fails:

- Invalid credentials return `401` with `invalid username or password`.
- Repeated failures are rate limited after 5 failed attempts within 15 minutes for the identifier or source IP.
- Disabled accounts cannot authenticate because login only accepts accounts where `disabled_at IS NULL`.

## Create A Standard User

Use the admin UI:

1. Log in as an admin.
2. Open `用户管理`.
3. Fill `用户名`, `显示名称`, optional `邮箱`, `初始密码`, and set `角色` to `user`.
4. Click `创建用户`.

Expected result:

- The new user appears in the user list with status `user · 已启用`.
- The create action writes an audit row with action `admin_create_user`.

If the username or email already exists, the API returns `409 user already exists`.

## Reset Password

Use the admin UI:

1. Log in as an admin.
2. Open `用户管理`.
3. Find the target user row.
4. Click `重置密码`.
5. Enter the replacement password in the prompt.

Expected result:

- The API returns success with no page reload requirement.
- Existing sessions for that user are revoked.
- The action writes an audit row with action `admin_reset_password`.

## Disable Or Enable User

Use the admin UI:

1. Log in as an admin.
2. Open `用户管理`.
3. In the target user row, click `禁用` or `启用`.

Expected result:

- Disabled users show `已禁用`.
- Enabled users show `已启用`.
- Disable writes `admin_disable_user`; enable writes `admin_enable_user`.

Safety rules enforced by the API:

- An admin cannot disable their own account from the UI.
- The last active admin cannot be disabled.
- Disabling a user revokes existing sessions.

## Recover A Disabled Account

If the target user cannot log in because the account was disabled, re-enable it from the host with the recovery CLI:

```bash
cd /opt/stock-research
/opt/stock-research/.venv/bin/stock-research dashboard-enable-user --username analyst
```

Success output:

```text
dashboard_user_enabled|analyst
```

Behavior:

- This path is intended for operator recovery when the user cannot self-recover through the login screen.
- The command writes the same `admin_enable_user` audit action with a null actor when no admin user is attached.

If the account is enabled but the password is lost or incorrect, reset it from the host:

```bash
cd /opt/stock-research
/opt/stock-research/.venv/bin/stock-research dashboard-reset-password --username admin
```

The command prompts for the new password twice. For controlled automation, `--password` is also available.

Success output:

```text
dashboard_password_reset|admin
```

This recovery path revokes active sessions for that username and writes `admin_reset_password` to `audit.audit_log`.

## Inspect Audit Logs

The platform writes authentication and user-management events to `audit.audit_log`.

Useful queries:

```bash
psql \"service=stock_research\" -c "
SELECT created_at, actor_user_id, action, target_type, target_id, metadata
FROM audit.audit_log
WHERE action IN (
  'bootstrap_admin_account',
  'login_failed',
  'login_success',
  'logout',
  'admin_create_user',
  'admin_reset_password',
  'admin_disable_user',
  'admin_enable_user'
)
ORDER BY created_at DESC
LIMIT 50;
"
```

Inspect one user by username:

```bash
psql \"service=stock_research\" -c "
SELECT al.created_at, al.action, al.target_id, al.metadata
FROM audit.audit_log al
LEFT JOIN identity.user_account ua
  ON ua.id::text = al.target_id
WHERE (
    al.metadata->>'username' = 'analyst'
    OR al.metadata->>'identifier' = 'analyst'
    OR al.metadata->>'identifier' = 'analyst@example.com'
    OR ua.username = 'analyst'
    OR ua.email = 'analyst@example.com'
)
ORDER BY al.created_at DESC;
"
```

## Inspect Service Logs

API service logs:

```bash
sudo journalctl -u stock-research-dashboard-api -n 200 --no-pager
sudo journalctl -u stock-research-dashboard-api -f
```

Service state and restart history:

```bash
sudo systemctl status stock-research-dashboard-api --no-pager
```

Nginx validation and logs:

```bash
sudo nginx -t
sudo tail -n 200 /var/log/nginx/access.log
sudo tail -n 200 /var/log/nginx/error.log
```

If root-path login is failing, check both the API journal and the Nginx error log before changing config.

## Roll Back

Roll back the frontend bundle and API code together to the last known-good commit. Do not leave the root frontend on one version and the API on another.

1. Move the checkout to the previous release commit:

```bash
cd /opt/stock-research
git fetch --all
git checkout <previous-good-commit>
/opt/stock-research/.venv/bin/pip install -e .
```

2. Rebuild the frontend for that commit:

```bash
cd /opt/stock-research/dashboard
pnpm install --frozen-lockfile
pnpm build
```

3. If this release changed deploy config files, restore the previous known-good copies in `/etc/systemd/system/` and `/etc/nginx/conf.d/`.

4. Restart the API and reload Nginx:

```bash
sudo systemctl daemon-reload
sudo systemctl restart stock-research-dashboard-api
sudo nginx -t
sudo systemctl reload nginx
```

5. Re-verify:

```bash
curl -I https://stock.manqiaotechnology.com/
curl -I https://stock.manqiaotechnology.com/api/auth/me
sudo systemctl status stock-research-dashboard-api --no-pager
```

If the incident was caused by an accidental account disable rather than a bad deploy, prefer the recovery CLI instead of a code rollback.
