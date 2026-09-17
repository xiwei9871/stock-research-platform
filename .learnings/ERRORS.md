# Errors

## 2026-07-30 — Transient DNS failure during external dashboard inspection

- A read-only `curl` request to `stock.manqiaotechnology.com` temporarily failed with `Could not resolve host` after an earlier request had succeeded.
- Retry the same targeted request before treating the site as unavailable; the retry succeeded and confirmed the deployed asset contained the admin user-management routes.

## 2026-07-30 — Manual dashboard release omitted the canonical remote env filename

- A manual `sync_dashboard_release.sh` run reached remote restart and exited because it defaulted to `.env.dashboard`, while the production host uses `.env` as configured by the launch agent.
- Manual releases must pass `DASHBOARD_REMOTE_ENV_FILE=.env` or run with the same environment as `com.stockresearch.dashboard-daily-sync`.

## 2026-07-30 — Dashboard release root lagged the latest successful strategy snapshot

- The external release gate kept `strategy_artifact_date` empty because the database's latest successful strategy status was `2026-07-29`, while the clean release root contained artifacts only through `2026-07-28`.
- Before publishing, compare the database's latest successful strategy date with the release-root artifact directories, copy the matching trusted snapshot when needed, and run `deploy/validate_strategy_release.py` before synchronization.
