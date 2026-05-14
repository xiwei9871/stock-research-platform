# Stock Minute Bar Ingestion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add unified PostgreSQL minute-bar storage and a Baostock import command for full-market 5-minute A-share data.

**Architecture:** Store research-ready minute bars in one wide table, `market.stock_minute_bar`, keyed by asset, timestamp, frequency, adjustment, and source. Keep Baostock raw payloads in `staging.baostock_stock_minute_bar`; import code normalizes Baostock rows into both staging and market tables without touching strategy backtests.

**Tech Stack:** PostgreSQL, psycopg, Baostock, Python package `stock_research`, pytest.

---

### Task 1: Schema

**Files:**
- Modify: `src/stock_research/schema.py`
- Modify: `tests/test_schema.py`

- [ ] Add failing schema assertions for `market.stock_minute_bar`, `staging.baostock_stock_minute_bar`, supported `freq` and `adjust_type` values, requested unique key, and requested indexes.
- [ ] Add the schema DDL and indexes.
- [ ] Run: `/Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_schema.py -q`

### Task 2: Minute Data Loader

**Files:**
- Create: `src/stock_research/minute_data.py`
- Create: `tests/test_minute_data.py`

- [ ] Add failing tests for Baostock time parsing, normalized market rows, staging payload rows, upsert SQL, and query parameters for raw/qfq 5-minute bars.
- [ ] Implement the smallest loader module that passes those tests.
- [ ] Run: `/Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_minute_data.py -q`

### Task 3: CLI

**Files:**
- Modify: `src/stock_research/cli.py`
- Modify: `tests/test_schema.py`

- [ ] Add failing parser assertions for `sync-baostock-minute-bars`.
- [ ] Wire the command to the loader and print a per-adjust-type row summary.
- [ ] Run: `/Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_schema.py tests/test_minute_data.py -q`

### Task 4: Verification

**Files:**
- Apply schema against `stock_research`.
- Run a one-stock, one-day import sample with `--limit-assets 1`.

- [ ] Run targeted tests.
- [ ] Run schema apply.
- [ ] Run a small Baostock sample import for `2024-01-02`.
- [ ] Verify rows exist in `market.stock_minute_bar` and `staging.baostock_stock_minute_bar`.
