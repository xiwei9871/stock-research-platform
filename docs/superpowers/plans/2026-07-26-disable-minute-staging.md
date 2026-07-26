# Disable Minute Staging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reclaim the 92 GB minute staging table and make future Baostock minute staging writes disabled by default while preserving market K-line writes.

**Architecture:** Add one environment-controlled predicate in `minute_data.py`. `upsert_stock_minute_bars()` always writes normalized market rows and writes staging rows only when explicitly enabled. Truncate the existing staging relation after confirming the market relation remains queryable.

**Tech Stack:** Python, pytest, PostgreSQL, psycopg

---

### Task 1: Lock the desired ingestion behavior with tests

**Files:**
- Modify: `tests/test_minute_data.py`

- [ ] Add a test asserting the default environment produces exactly one `execute_many` call targeting `market.stock_minute_bar`.
- [ ] Add a test setting `BAOSTOCK_MINUTE_STAGING_ENABLED=true` and asserting staging and market inserts both occur.
- [ ] Run `.venv/bin/pytest tests/test_minute_data.py -q` and confirm the default-disabled test fails before implementation.

### Task 2: Disable staging writes by default

**Files:**
- Modify: `src/stock_research/minute_data.py`

- [ ] Add `minute_staging_enabled()` that returns true only for `1`, `true`, `yes`, or `on`.
- [ ] Build staging payloads and execute the staging insert only when that predicate is true.
- [ ] Keep the market insert unconditional and preserve the existing return value.
- [ ] Run `.venv/bin/pytest tests/test_minute_data.py -q` and confirm all tests pass.

### Task 3: Reclaim database space

**Files:**
- No source files.

- [ ] Record the staging relation size and row count.
- [ ] Execute `TRUNCATE TABLE staging.baostock_stock_minute_bar`.
- [ ] Verify the row count is zero and relation storage is minimal.
- [ ] Query a 2022 raw 5-minute bar from `market.stock_minute_bar` to prove K-line data remains accessible.

### Task 4: Final verification

**Files:**
- Verify: `src/stock_research/minute_data.py`
- Verify: `tests/test_minute_data.py`

- [ ] Run the focused minute-data tests.
- [ ] Run minute-backfill tests that exercise `upsert_stock_minute_bars` integration.
- [ ] Inspect `git diff` to confirm no unrelated user files changed.
- [ ] Report reclaimed database space and the environment variable for re-enabling archival.
