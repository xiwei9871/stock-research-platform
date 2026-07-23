# Prod Publish Wrapper Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a one-command production publish wrapper that accepts a trade date, runs the systemd sync, and verifies the public release.

**Architecture:** Keep `deploy/sync_dashboard_systemd.sh` as the single source of publish logic. Add a thin wrapper script that derives environment variables from one date argument and then delegates to the sync and release-check scripts.

**Tech Stack:** Bash, pytest deployment asset tests.

---

### Task 1: Add a failing deployment test for the new wrapper

**Files:**
- Modify: `tests/test_dashboard_deployment_assets.py`

- [ ] **Step 1: Add a test that describes the wrapper contract**

Check for:
- executable bit on `deploy/publish_prod.sh`;
- `set -euo pipefail`;
- one required trade-date argument;
- `LATEST_STRATEGY_DAILY_EOD="strategy_daily_eod/...`;
- calls to `deploy/sync_dashboard_systemd.sh` and `deploy/check_dashboard_release.sh`.

- [ ] **Step 2: Run the targeted test and confirm it fails**

Run: `PYTHONPATH=src pytest tests/test_dashboard_deployment_assets.py -k publish_prod -q`

Expected: FAIL because `deploy/publish_prod.sh` does not exist yet.

### Task 2: Implement the thin wrapper

**Files:**
- Create: `deploy/publish_prod.sh`

- [ ] **Step 1: Create the minimal wrapper**

Behavior:
- resolve `repo_root`;
- source `DASHBOARD_DAILY_SYNC_ENV` when present;
- require exactly one `YYYY-MM-DD` trade-date argument;
- require `DASHBOARD_AUTH` unless `SKIP_RELEASE_CHECK=1`;
- call `deploy/sync_dashboard_systemd.sh` with `LATEST_STRATEGY_DAILY_EOD`;
- run `deploy/check_dashboard_release.sh` with `TRADE_DATE`, `START_DATE`, `END_DATE`.

- [ ] **Step 2: Make the script executable**

Run: `chmod +x deploy/publish_prod.sh`

### Task 3: Document and verify

**Files:**
- Modify: `docs/deployment-dashboard.md`
- Modify: `tests/test_dashboard_deployment_assets.py`

- [ ] **Step 1: Document the new operator command**

Add a short section showing:
`./deploy/publish_prod.sh 2026-06-27`

- [ ] **Step 2: Run targeted verification**

Run:
- `PYTHONPATH=src pytest tests/test_dashboard_deployment_assets.py -q`
- `bash -n deploy/publish_prod.sh`

Expected: PASS.
