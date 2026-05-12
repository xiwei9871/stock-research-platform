# Full-History Phase 5 Index Bars And Constituents Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add historical index constituent infrastructure so benchmark universes can be queried point-in-time.

**Architecture:** Keep the existing `market.index_daily_bar` and `sync-index-bars` path for benchmark bars. Add `market.index_constituent` and a Baostock constituent snapshot loader for indexes Baostock explicitly supports: `SSE_50`, `CSI_300`, and `CSI_500`.

**Tech Stack:** Python, PostgreSQL, Baostock, pytest, existing `stock-research` CLI.

---

## Scope

In scope:

- `market.index_constituent` schema with `start_date`, `end_date`, optional `weight`, and `source_version`;
- Baostock constituent snapshot loader for `SSE_50`, `CSI_300`, and `CSI_500`;
- point-in-time index universe query helper;
- CLI command for date-specific constituent sync;
- audit coverage for both `market.index_daily_bar` and `market.index_constituent`;
- runbook commands for Phase 5.

Out of scope:

- claiming CSI1000 constituents when the current Baostock package does not expose a constituent endpoint;
- executing a 1990-current constituent backfill;
- changing every selection/backtest entry point to accept index universe filters.

## Files

- Modify: `src/stock_research/schema.py`
- Modify: `src/stock_research/loaders/baostock_ingestion.py`
- Create: `src/stock_research/services/index_universe_service.py`
- Modify: `src/stock_research/cli.py`
- Modify: `src/stock_research/data_audit.py`
- Modify: `tests/test_schema.py`
- Modify: `tests/test_baostock_ingestion.py`
- Create: `tests/test_index_universe_service.py`
- Modify: `tests/test_factor_cli.py`
- Modify: `tests/test_data_audit.py`
- Modify: `docs/daily-factor-pipeline-runbook.md`

## Task 1: Schema

- [ ] **Step 1: Write failing schema test**

Add:

```python
def test_research_extension_includes_index_constituent_table():
    sql = CREATE_RESEARCH_EXTENSION_SQL
    assert "CREATE TABLE IF NOT EXISTS market.index_constituent" in sql
    assert "source_version text NOT NULL" in sql
    assert "idx_market_index_constituent_lookup" in sql
```

- [ ] **Step 2: Verify red**

Run:

```bash
.venv/bin/python -m pytest tests/test_schema.py::test_research_extension_includes_index_constituent_table -q
```

Expected: FAIL because the table is not defined.

- [ ] **Step 3: Implement schema**

Add:

```sql
CREATE TABLE IF NOT EXISTS market.index_constituent (
    index_id text NOT NULL,
    asset_id text NOT NULL,
    start_date date NOT NULL,
    end_date date,
    weight numeric,
    source text NOT NULL,
    source_version text NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (index_id, asset_id, start_date, source_version)
);

CREATE INDEX IF NOT EXISTS idx_market_index_constituent_lookup
    ON market.index_constituent (index_id, start_date, end_date, asset_id);
```

- [ ] **Step 4: Verify green**

Run:

```bash
.venv/bin/python -m pytest tests/test_schema.py::test_research_extension_includes_index_constituent_table -q
```

Expected: PASS.

## Task 2: Baostock Constituent Loader

- [ ] **Step 1: Write failing loader tests**

Add tests for:

- `normalize_index_constituent_row("CSI_300", "2024-05-31", row, "baostock_snapshot_v1")`;
- `upsert_index_constituents`;
- `sync_index_constituents` using monkeypatched Baostock query functions.

- [ ] **Step 2: Verify red**

Run:

```bash
.venv/bin/python -m pytest tests/test_baostock_ingestion.py::test_normalize_index_constituent_row_maps_asset tests/test_baostock_ingestion.py::test_upsert_index_constituents tests/test_baostock_ingestion.py::test_sync_index_constituents_uses_selected_targets -q
```

Expected: FAIL because the functions are missing.

- [ ] **Step 3: Implement loader**

Add `INDEX_CONSTITUENT_TARGETS`, `normalize_index_constituent_row`, `upsert_index_constituents`, and `sync_index_constituents`.

- [ ] **Step 4: Verify green**

Run:

```bash
.venv/bin/python -m pytest tests/test_baostock_ingestion.py -q
```

Expected: PASS.

## Task 3: Point-In-Time Universe Query

- [ ] **Step 1: Write failing service test**

Create `tests/test_index_universe_service.py` asserting the query reads:

```sql
FROM market.index_constituent
WHERE index_id = %s
  AND start_date <= %s
  AND (end_date IS NULL OR %s <= end_date)
```

- [ ] **Step 2: Verify red**

Run:

```bash
.venv/bin/python -m pytest tests/test_index_universe_service.py -q
```

Expected: FAIL because service module is missing.

- [ ] **Step 3: Implement service**

Create `src/stock_research/services/index_universe_service.py` with `load_index_universe(conn, index_id, trade_date, source_version=None)`.

- [ ] **Step 4: Verify green**

Run:

```bash
.venv/bin/python -m pytest tests/test_index_universe_service.py -q
```

Expected: PASS.

## Task 4: CLI, Audit, And Runbook

- [ ] **Step 1: Write failing CLI and audit tests**

Add parser test for:

```bash
stock-research sync-index-constituents --trade-date 2024-05-31 --index-ids CSI_300,CSI_500 --source-version baostock_snapshot_v1
```

Add audit dataset assertions for:

- `market.index_daily_bar`;
- `market.index_constituent`.

- [ ] **Step 2: Verify red**

Run:

```bash
.venv/bin/python -m pytest tests/test_factor_cli.py tests/test_data_audit.py -q
```

Expected: FAIL because parser/audit entries are missing.

- [ ] **Step 3: Implement CLI and audit**

Add command handler printing:

```text
index_constituents_synced|COUNT
```

- [ ] **Step 4: Final verification**

Run:

```bash
.venv/bin/python -m pytest -q
.venv/bin/stock-research apply-research-schema
.venv/bin/stock-research sync-index-bars --start-date 2024-05-27 --end-date 2024-05-27
.venv/bin/stock-research sync-index-constituents --trade-date 2024-05-31 --index-ids CSI_300 --source-version phase5_smoke_v1
.venv/bin/stock-research data-audit --expected-start-date 1990-12-01
git status --short --branch
```

