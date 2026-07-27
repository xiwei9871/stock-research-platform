# Repair Publication Final Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace stale-prone cron locking, make release gates parameter-identical, and retain durable failure summaries outside disposable staging.

**Architecture:** A Python wrapper owns a nonblocking `fcntl.flock`, passes the lock FD to the guarded cron child, forwards process-group signals, and returns the child's status. Dashboard release checks share one shell function and one provenance environment. Failed strategy runs atomically publish compact audit summaries under `.failures`, prune to ten runs, and remove large staging trees.

**Tech Stack:** Python 3, Bash, `fcntl`, `subprocess`, pytest.

---

### Task 1: Kernel-backed cron lock wrapper

**Files:**
- Create: `scripts/repair_publication_lock.py`
- Modify: `scripts/run_eod_auto_repair_cron.sh`
- Modify: `scripts/run_platform_ready_check_cron.sh`
- Delete: `scripts/repair_publication_lock.sh`
- Test: `tests/test_eod_auto_repair_scripts.py`

- [x] Add failing tests for two contenders, wrapper SIGKILL with inherited child lock, TERM forwarding, and exit-code passthrough.
- [x] Implement nonblocking `flock`, guarded self-reentry, inherited lock FD, process-group forwarding, and child wait.
- [x] Run the cron script test modules.

### Task 2: Identical desired-state and final release gates

**Files:**
- Modify: `deploy/sync_dashboard_release.sh`
- Test: `tests/test_dashboard_release_scripts.py`

- [x] Add a failing fixture assertion that records both gate environments and compares their provenance/base-image parameter sets.
- [x] Extract one `check_release_state` function used for both early and final checks, varying only timeout settings.
- [x] Run dashboard release script tests.

### Task 3: Durable failed-publication summaries

**Files:**
- Modify: `src/stock_research/strategy_daily_eod.py`
- Test: `tests/test_strategy_daily_eod.py`

- [x] Add failing tests that returned/DB summary paths exist after partial failure and only ten failure runs remain.
- [x] Atomically write compact summaries under `.failures/<date>/<run_id>`, prune old runs, and remove staging.
- [x] Run strategy tests, full Task 8 regression, Bash syntax checks, and `git diff --check`.
