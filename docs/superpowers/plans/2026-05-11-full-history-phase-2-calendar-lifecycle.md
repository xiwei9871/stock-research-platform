# Full-History Phase 2 Calendar And Lifecycle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the trading calendar and asset lifecycle dimensions needed before full-history market data backfills.

**Architecture:** Add first-class dimension tables for open trading days and lifecycle events, then provide idempotent loaders that can derive a seed calendar from existing `market_daily_bar` and lifecycle events from `core.asset_master`. Later phases can replace or extend these rows with richer source-specific history without changing downstream consumers.

**Tech Stack:** Python, PostgreSQL, psycopg, pandas, pytest, existing `stock-research` CLI.

---

## Scope

In scope:

- `market.trading_calendar` schema;
- `core.asset_lifecycle_event` schema;
- idempotent upsert helpers;
- seed calendar generation from existing market bars;
- lifecycle event generation from `core.asset_master`;
- CLI commands and audit coverage for the new dimension tables.

Out of scope:

- fetching full historical daily bars;
- external exchange holiday source integration;
- index constituents;
- company actions;
- industry history.

## Files

- Modify: `src/stock_research/schema.py`
- Create: `src/stock_research/dimensions.py`
- Modify: `src/stock_research/cli.py`
- Modify: `src/stock_research/data_audit.py`
- Modify: `tests/test_schema.py`
- Create: `tests/test_dimensions.py`
- Modify: `tests/test_factor_cli.py`
- Modify: `tests/test_data_audit.py`
- Modify: `docs/daily-factor-pipeline-runbook.md`

## Task 1: Dimension Schema

- [ ] **Step 1: Write failing schema tests**

Add to `tests/test_schema.py`:

```python
def test_research_extension_includes_calendar_and_lifecycle_tables():
    sql = CREATE_RESEARCH_EXTENSION_SQL
    assert "CREATE TABLE IF NOT EXISTS market.trading_calendar" in sql
    assert "CREATE TABLE IF NOT EXISTS core.asset_lifecycle_event" in sql
    assert "idx_market_trading_calendar_open_date" in sql
    assert "idx_core_asset_lifecycle_event_asset_date" in sql
```

- [ ] **Step 2: Verify red**

Run:

```bash
.venv/bin/python -m pytest tests/test_schema.py::test_research_extension_includes_calendar_and_lifecycle_tables -q
```

Expected: FAIL because the tables do not exist.

- [ ] **Step 3: Implement schema**

Add `market.trading_calendar`:

```sql
CREATE TABLE IF NOT EXISTS market.trading_calendar (
    exchange text NOT NULL,
    trade_date date NOT NULL,
    is_open boolean NOT NULL,
    source text NOT NULL,
    source_version text NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (exchange, trade_date, source_version)
);
```

Add `core.asset_lifecycle_event`:

```sql
CREATE TABLE IF NOT EXISTS core.asset_lifecycle_event (
    asset_id text NOT NULL,
    event_date date NOT NULL,
    event_type text NOT NULL,
    event_value text,
    source text NOT NULL,
    source_version text NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (asset_id, event_date, event_type, source_version)
);
```

Add indexes:

```sql
CREATE INDEX IF NOT EXISTS idx_market_trading_calendar_open_date
    ON market.trading_calendar (exchange, is_open, trade_date);

CREATE INDEX IF NOT EXISTS idx_core_asset_lifecycle_event_asset_date
    ON core.asset_lifecycle_event (asset_id, event_date, event_type);
```

- [ ] **Step 4: Verify green**

Run:

```bash
.venv/bin/python -m pytest tests/test_schema.py::test_research_extension_includes_calendar_and_lifecycle_tables -q
```

Expected: PASS.

## Task 2: Dimension Helper Module

- [ ] **Step 1: Write failing tests**

Create `tests/test_dimensions.py` covering:

- `build_calendar_rows(["2024-01-02"], ["SH", "SZ"], source="derived:market_daily_bar", source_version="v1")`;
- `upsert_trading_calendar` SQL;
- `build_lifecycle_rows_from_assets` creates `listed` and `delisted` events only when source dates exist;
- `upsert_asset_lifecycle_events` SQL.

- [ ] **Step 2: Verify red**

Run:

```bash
.venv/bin/python -m pytest tests/test_dimensions.py -q
```

Expected: FAIL because `stock_research.dimensions` does not exist.

- [ ] **Step 3: Implement module**

Create `src/stock_research/dimensions.py` with:

- `build_calendar_rows(trade_dates, exchanges, source, source_version)`;
- `load_distinct_market_trade_dates(start_date, end_date, adjust_type="hfq", service=...)`;
- `upsert_trading_calendar(conn, rows)`;
- `seed_trading_calendar_from_bars(start_date, end_date, exchanges, source_version, adjust_type="hfq", service=...)`;
- `load_asset_master_lifecycle_inputs(service=...)`;
- `build_lifecycle_rows_from_assets(assets, source_version)`;
- `upsert_asset_lifecycle_events(conn, rows)`;
- `sync_asset_lifecycle_from_master(source_version="core_asset_master_v1", service=...)`.

- [ ] **Step 4: Verify green**

Run:

```bash
.venv/bin/python -m pytest tests/test_dimensions.py -q
```

Expected: PASS.

## Task 3: CLI Commands

- [ ] **Step 1: Write failing CLI tests**

Add tests for:

```bash
stock-research seed-trading-calendar --start-date 2024-01-01 --end-date 2024-01-31 --exchanges SH,SZ --source-version derived_v1
stock-research sync-asset-lifecycle --source-version core_asset_master_v1
```

Expected output:

```text
trading_calendar_seeded|rows|44
asset_lifecycle_synced|rows|100
```

- [ ] **Step 2: Verify red**

Run:

```bash
.venv/bin/python -m pytest tests/test_factor_cli.py::test_calendar_lifecycle_cli_prints_counts -q
```

Expected: FAIL because CLI commands do not exist.

- [ ] **Step 3: Implement CLI**

Import dimension helpers into `src/stock_research/cli.py`.
Add `parse_str_list` or reuse a local parser for `--exchanges`.
Add command handlers for the two commands.

- [ ] **Step 4: Verify green**

Run:

```bash
.venv/bin/python -m pytest tests/test_factor_cli.py tests/test_dimensions.py -q
```

Expected: PASS.

## Task 4: Audit And Docs

- [ ] **Step 1: Add audit datasets**

Update `src/stock_research/data_audit.py` to include:

- `market.trading_calendar` using `trade_date`;
- `core.asset_lifecycle_event` using `event_date`.

Update `tests/test_data_audit.py` to assert the dataset names exist in `AUDIT_DATASETS`.

- [ ] **Step 2: Update runbook**

Add Phase 2 seed commands:

```bash
stock-research seed-trading-calendar --start-date 1990-12-01 --end-date YYYY-MM-DD --exchanges SH,SZ --source-version derived_market_daily_bar_v1
stock-research sync-asset-lifecycle --source-version core_asset_master_v1
stock-research data-audit --expected-start-date 1990-12-01
```

- [ ] **Step 3: Final verification**

Run:

```bash
.venv/bin/python -m pytest -q
.venv/bin/stock-research apply-research-schema
.venv/bin/stock-research seed-trading-calendar --start-date 2024-05-27 --end-date 2024-05-31 --exchanges SH,SZ --source-version phase2_smoke_v1
.venv/bin/stock-research sync-asset-lifecycle --source-version phase2_smoke_v1
.venv/bin/stock-research data-audit --expected-start-date 1990-12-01
git status --short --branch
```

- [ ] **Step 4: Commit**

Run:

```bash
git add src/stock_research/schema.py src/stock_research/dimensions.py src/stock_research/cli.py src/stock_research/data_audit.py tests/test_schema.py tests/test_dimensions.py tests/test_factor_cli.py tests/test_data_audit.py docs/daily-factor-pipeline-runbook.md docs/superpowers/plans/2026-05-11-full-history-phase-2-calendar-lifecycle.md
git commit -m "Add trading calendar and lifecycle dimensions"
```
