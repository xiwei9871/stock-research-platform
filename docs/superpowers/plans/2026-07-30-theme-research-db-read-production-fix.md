# Theme Research Production DB Read Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore production Theme Research reads from PostgreSQL while allowing optional priority-policy support to be unavailable without failing core data.

**Architecture:** Refactor `load_db_context()` to build its canonical theme and mapping packages from the normalized database package, then derive optional priority fields through the existing scoped support helper. Change the production read-source environment to `db`, publish through the canonical release gate, and verify the external list and detail routes.

**Tech Stack:** Python 3.12, FastAPI, PostgreSQL, Pytest, React 19, Vitest, Vite, Docker Compose, canonical dashboard release scripts.

---

### Task 1: Specify DB Reads Without Full Artifact Context

**Files:**
- Modify: `tests/test_dashboard_theme_research_db.py`

- [ ] **Step 1: Add a failing regression test**

Create a test that normalizes the existing artifact fixture into a database package, stubs `load_database_package()` to return it, makes `priority.load_theme_research_priority_package()` fail if called, and makes `_load_workflow_priority_support()` raise `FileNotFoundError`. Call `load_db_context()` and assert that DB themes, nodes, sources, claims, and mappings remain populated while `priority_status` is `unavailable` and all priority collections are empty.

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```bash
rtk /Users/xiwei/stock_research/.venv/bin/pytest -q tests/test_dashboard_theme_research_db.py -k db_context_survives_missing_optional_priority_support
```

Expected: FAIL because the current DB loader still calls the complete artifact package loader.

### Task 2: Make Optional Priority Support Non-Blocking

**Files:**
- Modify: `src/stock_research/dashboard/theme_research_db.py`
- Test: `tests/test_dashboard_theme_research_db.py`

- [ ] **Step 1: Build DB packages before priority support**

In `load_db_context()`, load and normalize the database package, build `theme_package` and `mapping_package`, then call `_build_scoped_priority_context(theme_package["nodes"], mapping_package["company_mappings"])`.

- [ ] **Step 2: Return the scoped priority fields**

Return `policy`, `priority_status`, `node_priorities`, `company_priorities`, `evidence_gap_priorities`, and `review_queue` from the scoped priority context together with the DB theme and mapping packages. Do not call `load_theme_research_priority_package()` from `load_db_context()`.

- [ ] **Step 3: Run the focused DB tests and verify GREEN**

Run:

```bash
rtk /Users/xiwei/stock_research/.venv/bin/pytest -q tests/test_dashboard_theme_research_db.py
```

Expected: all tests PASS, including artifact/DB parity when optional support exists.

- [ ] **Step 4: Commit the code fix**

Commit the test and implementation with message `fix: make theme research DB reads artifact-independent`.

### Task 3: Package Static Priority Support

**Files:**
- Modify: `.dockerignore`
- Modify: `deploy/dashboard-api.Dockerfile`
- Modify: `deploy/sync_dashboard_release.sh`
- Modify: `tests/test_dashboard_release_scripts.py`

- [ ] Add a failing release-contract test requiring priority-policy and tech-bottleneck crosswalk directories in the Docker build context, remote synchronization, and API image.
- [ ] Run the focused test and verify RED.
- [ ] Allow only those two artifact subdirectories through `.dockerignore`.
- [ ] Synchronize both directories into the canonical remote release root.
- [ ] Copy both directories into `/app/artifacts/theme_decomposition` in the API image.
- [ ] Run the focused release-contract test and release-script test file and verify GREEN.
- [ ] Commit with message `fix: package theme research priority support`.

### Task 4: Verify the Release Candidate

**Files:**
- Verify all modified files.

- [ ] Run `rtk git diff --check`.
- [ ] Run the focused Theme Research backend tests.
- [ ] Run the complete dashboard frontend Vitest suite.
- [ ] Run the production dashboard build.
- [ ] Review the final diff against the approved design and commit state.

### Task 5: Switch Production to DB and Publish

**Files and state:**
- Update remote `/home/jqz/code/stock-research-platform-main/.env`.
- Use: `deploy/sync_dashboard_release.sh`.

- [ ] Confirm the remote environment contains exactly `THEME_RESEARCH_READ_SOURCE=artifact`.
- [ ] Create a timestamped backup of the remote environment file and replace that exact line with `THEME_RESEARCH_READ_SOURCE=db`.
- [ ] Fast-forward the clean canonical release root to the fix commit.
- [ ] Publish with expected trade date `2026-07-29` and production environment file `.env`.
- [ ] Confirm the external release gate reports the new commit.

### Task 6: Verify Theme Research Externally

**Files:**
- No additional changes.

- [ ] Confirm `/api/research/theme-decomposition/themes` returns HTTP 200 through an authenticated production session.
- [ ] Confirm the external Theme Research list renders 2 themes.
- [ ] Confirm node and company counts are populated from DB data plus static priority support.
- [ ] Open one theme detail and confirm its overview and node priorities render.
- [ ] Confirm production API logs contain no new `PRIORITY_POLICY_DIRECTORY_NOT_FOUND` or HTTP 500 for the Theme Research endpoint after verification started.
- [ ] Keep the verified Theme Research page open for the user.
