# DB-Backed Combo Replay Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Backtest Lab read validated combo backtest replay data from database read-model tables instead of CSV artifacts.

**Architecture:** Add `backtest.strategy_backtest_*` read-model tables for run metadata, equity, positions, and trades. Add a materializer/importer that can bootstrap those tables from existing validated research artifacts, then update Backtest Lab adapters to query the database first and only use artifacts as a controlled bootstrap path.

**Tech Stack:** Python, pandas, PostgreSQL SQL in `schema.py`, existing `stock_research.db` helpers, pytest, FastAPI dashboard API.

---

### Task 1: Schema And Read Model

**Files:**
- Modify: `src/stock_research/schema.py`
- Create: `src/stock_research/strategy_backtest_read_model.py`
- Modify: `tests/test_schema.py`
- Create: `tests/test_strategy_backtest_read_model.py`

- [ ] Add schema tests for `backtest.strategy_backtest_run`, `backtest.strategy_backtest_equity`, `backtest.strategy_backtest_position`, and `backtest.strategy_backtest_trade`.
- [ ] Add read-model tests for payload-to-row normalization, idempotent upsert SQL, and DB payload loading.
- [ ] Implement DDL and read-model importer/loader.

### Task 2: Backtest Lab DB-First Replay

**Files:**
- Modify: `src/stock_research/dashboard/strategy_backtest_adapters.py`
- Modify: `tests/test_strategy_backtest_adapters.py`
- Modify: `tests/test_dashboard_backtests.py`

- [ ] Add tests that a combo adapter returns DB payload without reading CSV artifacts when the DB has a matching run.
- [ ] Update artifact replay adapters to load DB replay first, then bootstrap from artifact and import if DB is missing.
- [ ] Preserve existing API shape for the dashboard.

### Task 3: Materialize And Verify

**Files:**
- Runtime: PostgreSQL service `stock_research`
- Runtime: dashboard API on `127.0.0.1:8765`

- [ ] Apply schema with `stock-research apply-research-schema`.
- [ ] Run each default combo once through the materializer/API so the DB tables are populated.
- [ ] Verify direct DB-backed API calls return the three combo schemes.
- [ ] Run backend focused tests, dashboard tests, build, and Playwright e2e.
