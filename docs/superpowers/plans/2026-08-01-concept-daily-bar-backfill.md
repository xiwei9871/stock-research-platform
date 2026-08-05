# Concept Daily Bar Historical Backfill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Backfill the canonical THS concept-board daily OHLCV series in `market.concept_daily_bar` from 2024-01-01 through the latest available market date.

**Architecture:** Use AkShare's `stock_board_concept_index_ths` as the historical concept-index source, map returned board names to existing `core.concept_board` THS codes, normalize the vendor columns into the local schema, and upsert board-by-board so interrupted runs are safe to resume. Preserve existing breadth fields when the direct historical source does not provide them, while marking direct rows with an explicit source value.

**Tech Stack:** Python 3.11+, pandas, AkShare, psycopg/PostgreSQL, pytest, existing `stock_research.db` helpers.

---

### Task 1: Lock the source and target contract

**Files:**
- Read: `src/stock_research/core_data.py:721-825`
- Read: `src/stock_research/schema.py:588-620`
- Create: `docs/superpowers/plans/2026-08-01-concept-daily-bar-backfill.md`

- [x] Confirm `concept_system='ths'` is the platform's canonical concept source, `market.concept_daily_bar` is the target, and the latest market date is derived from `public.market_daily_bar`.
- [x] Confirm AkShare returns `日期`, `开盘价`, `最高价`, `最低价`, `收盘价`, `成交量`, and `成交额`, while local `preclose` can be derived from the prior returned close.
- [x] Confirm the direct vendor series has no breadth counts, so `stock_count`, `up_count`, and `down_count` must remain nullable and existing non-null values must not be overwritten by nulls.

### Task 2: Write failing tests for normalization and upsert payloads

**Files:**
- Create: `tests/test_concept_daily_backfill.py`
- Create: `src/stock_research/concept_daily_backfill.py`

- [ ] Add a test that imports `normalize_concept_history` and expects Chinese AkShare columns to become typed local rows with sorted dates and a previous-close `preclose`.
- [ ] Add a test that invalid rows with missing dates or close prices are dropped while numeric vendor values become Python numeric values or `None`.
- [ ] Add a test that `build_upsert_rows` emits the target concept code/name/source and leaves breadth fields null for direct index rows.
- [ ] Run `rtk .venv/bin/pytest tests/test_concept_daily_backfill.py -q`; it must fail because the new module/functions do not exist yet.

### Task 3: Implement the minimal backfill module

**Files:**
- Modify: `src/stock_research/concept_daily_backfill.py`
- Create: `scripts/backfill_concept_daily_bars.py`

- [ ] Implement `normalize_concept_history(frame, concept_system, concept_code, concept_name, source)` with explicit column mapping, date filtering, numeric coercion, sorting, and derived `preclose`.
- [ ] Implement `load_active_concept_boards(conn, concept_system)` and `load_latest_market_date(conn)` using read-only SQL.
- [ ] Implement `upsert_concept_daily_rows(conn, rows)` with `ON CONFLICT (concept_system, concept_code, trade_date) DO UPDATE`; update OHLCV/source fields and preserve existing breadth counts when the incoming direct row has null counts.
- [ ] Implement `fetch_concept_history` using `ak.stock_board_concept_index_ths` and allow an injected fetcher for tests.
- [ ] Implement board-by-board processing with bounded worker concurrency, retry handling, per-board commits, and a failure summary so rerunning the script is idempotent.
- [ ] Add CLI arguments for `--service`, `--start-date`, `--end-date`, `--concept-system`, `--workers`, `--limit`, and `--dry-run`.

### Task 4: Verify the implementation before full mutation

**Files:**
- Modify: `tests/test_concept_daily_backfill.py`

- [ ] Run the focused test and confirm it passes.
- [ ] Run a dry-run for the single board `机器人概念` through the script's board filter/limit path and verify it reports 2024-01-01 through the latest market date without writing rows.
- [ ] Run a single-board write for `机器人概念`, then query its min/max dates, row count, and source; confirm the upsert is repeatable and existing breadth counts are not erased.

### Task 5: Execute the full THS historical backfill

**Files:**
- Runtime target: `market.concept_daily_bar`
- Runtime report: `outputs/research/concept_daily_backfill/`

- [ ] Run the script for all active THS concept boards from 2024-01-01 through the latest `public.market_daily_bar` date using bounded workers.
- [ ] Record successful board count, inserted/upserted row count, failed board names, and exception summaries in a JSON/CSV report.
- [ ] If the external source rate-limits or fails, rerun only failed boards with lower concurrency; do not delete existing rows.

### Task 6: Validate coverage and strategy-useful outputs

**Files:**
- Runtime target: `market.concept_daily_bar`

- [ ] Verify per-board min/max dates, distinct date counts, duplicate-key absence, and source distribution.
- [ ] Verify the canonical THS concept table covers 2024-01-01 onward for all successfully fetched boards and quantify any failures.
- [ ] Recompute the robot-concept historical-high to recent-one-month-low drawdown using the completed series and report the result separately from the individual-stock drawdown screen.
