# Concept Sector Source Ingestion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a real concept-sector data path for Market Monitor so the concept heatmap, fund-flow proxy, and sector detail read from local database artifacts instead of returning a placeholder empty payload.

**Architecture:** Reuse the existing industry-sector model. Add local `core.concept_board`, `core.concept_membership`, and `market.concept_daily_bar` tables, then build concept daily bars from point-in-time concept membership plus `market_daily_bar`. Dashboard services keep the existing `/market-monitor/sectors/*?type=concept` API contract and switch from hardcoded empty responses to the new concept tables.

**Tech Stack:** PostgreSQL, psycopg, Python service modules, pytest, React dashboard API consumers.

---

### Task 1: Add Concept Sector Schema

**Files:**
- Modify: `src/stock_research/schema.py`
- Test: `tests/test_schema.py`

- [ ] **Step 1: Write the failing schema test**

Add assertions that the schema creates concept board, membership, daily bar tables, and indexes:

```python
def test_research_extension_contains_concept_sector_tables():
    sql = CREATE_RESEARCH_EXTENSION_SQL
    assert "CREATE TABLE IF NOT EXISTS core.concept_board" in sql
    assert "CREATE TABLE IF NOT EXISTS core.concept_membership" in sql
    assert "CREATE TABLE IF NOT EXISTS market.concept_daily_bar" in sql
    assert "idx_core_concept_membership_asset_date" in sql
    assert "idx_market_concept_daily_bar_system_date_desc" in sql
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run: `rtk .venv/bin/python -m pytest tests/test_schema.py::test_research_extension_contains_concept_sector_tables -q`

Expected: FAIL because the concept table names are not present in `CREATE_RESEARCH_EXTENSION_SQL`.

- [ ] **Step 3: Add concept tables and indexes**

Add these tables to `CREATE_RESEARCH_EXTENSION_SQL` near the industry tables:

```sql
CREATE TABLE IF NOT EXISTS core.concept_board (
    concept_system text NOT NULL,
    concept_code text NOT NULL,
    concept_name text NOT NULL,
    source text NOT NULL,
    is_active boolean NOT NULL DEFAULT true,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (concept_system, concept_code)
);

CREATE TABLE IF NOT EXISTS core.concept_membership (
    asset_id text NOT NULL,
    concept_system text NOT NULL,
    concept_code text NOT NULL,
    concept_name text NOT NULL,
    start_date date NOT NULL,
    end_date date,
    source text NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (asset_id, concept_system, concept_code, start_date)
);

CREATE TABLE IF NOT EXISTS market.concept_daily_bar (
    concept_system text NOT NULL,
    concept_code text NOT NULL,
    concept_name text NOT NULL,
    trade_date date NOT NULL,
    open numeric,
    high numeric,
    low numeric,
    close numeric,
    preclose numeric,
    volume numeric,
    amount numeric,
    stock_count integer,
    up_count integer,
    down_count integer,
    source text NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (concept_system, concept_code, trade_date)
);
```

Add indexes:

```sql
CREATE INDEX IF NOT EXISTS idx_core_concept_membership_asset_date
    ON core.concept_membership (asset_id, concept_system, start_date, end_date);

CREATE INDEX IF NOT EXISTS idx_core_concept_membership_concept_date
    ON core.concept_membership (concept_system, concept_code, start_date, end_date);

CREATE INDEX IF NOT EXISTS idx_market_concept_daily_bar_date
    ON market.concept_daily_bar (trade_date, concept_system, concept_code);

CREATE INDEX IF NOT EXISTS idx_market_concept_daily_bar_system_date_desc
    ON market.concept_daily_bar (concept_system, trade_date DESC);
```

- [ ] **Step 4: Run schema tests**

Run: `rtk .venv/bin/python -m pytest tests/test_schema.py -q`

Expected: PASS.

### Task 2: Build Concept Daily Bars From Local Membership

**Files:**
- Modify: `src/stock_research/core_data.py`
- Test: `tests/test_core_data.py`

- [ ] **Step 1: Write the failing build test**

Add a test mirroring the industry daily bar test:

```python
def test_build_concept_daily_bars_uses_point_in_time_memberships(monkeypatch):
    calls = {}

    class FakeConn:
        pass

    def fake_execute(conn, sql, params=None):
        calls["sql"] = sql
        calls["params"] = params

    monkeypatch.setattr(core_data, "execute", fake_execute)

    core_data.build_concept_daily_bars(
        FakeConn(),
        start_date="2026-06-26",
        end_date="2026-06-26",
        concept_system="ths",
        adjust_type="qfq",
    )

    assert "INSERT INTO market.concept_daily_bar" in calls["sql"]
    assert "core.concept_membership" in calls["sql"]
    assert "m.start_date <= b.trade_date" in calls["sql"]
    assert "(m.end_date IS NULL OR b.trade_date < m.end_date)" in calls["sql"]
    assert calls["params"] == ["ths", "qfq", "2026-06-26", "2026-06-26"]
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run: `rtk .venv/bin/python -m pytest tests/test_core_data.py::test_build_concept_daily_bars_uses_point_in_time_memberships -q`

Expected: FAIL because `build_concept_daily_bars` does not exist.

- [ ] **Step 3: Implement concept daily bar builders**

Add `build_concept_daily_bars_for_service()` and `build_concept_daily_bars()` next to the industry builders. Use `core.concept_membership`, `market_daily_bar`, and `adjust_type` filters. Compute concept OHLC as member averages, volume/amount as sums, `stock_count`, `up_count`, and `down_count` from member bars.

- [ ] **Step 4: Run core data tests**

Run: `rtk .venv/bin/python -m pytest tests/test_core_data.py -q`

Expected: PASS.

### Task 3: Teach Dashboard Services To Read Concept Rows

**Files:**
- Modify: `src/stock_research/dashboard/sector_heatmap_service.py`
- Modify: `src/stock_research/dashboard/sector_fund_flow_service.py`
- Modify: `src/stock_research/dashboard/sector_detail_service.py`
- Test: `tests/test_dashboard_market_monitor_sector_services.py`

- [ ] **Step 1: Write failing service tests**

Add tests that concept heatmap, fund-flow, and detail no longer return the concept source unavailable warning when concept rows exist. The service tests should monkeypatch loader functions with concept-shaped rows and assert `data_status == "completed"`, `sector_type == "concept"`, and `source` includes `market.concept_daily_bar` or the mocked source.

- [ ] **Step 2: Run focused service tests to verify failure**

Run: `rtk .venv/bin/python -m pytest tests/test_dashboard_market_monitor_sector_services.py -q`

Expected: FAIL on concept tests because current services return empty payloads for `sector_type="concept"`.

- [ ] **Step 3: Implement concept loaders**

Change the service loaders so:

```python
if sector_type == "concept":
    query market.concept_daily_bar and core.concept_membership
else:
    keep the existing industry path unchanged
```

For fund-flow, keep the warning text explicit:

```python
"fund flow values are derived directional proxies from amount, price, and breadth"
```

- [ ] **Step 4: Run service tests**

Run: `rtk .venv/bin/python -m pytest tests/test_dashboard_market_monitor_sector_services.py -q`

Expected: PASS.

### Task 4: Add Daily Close Stage Hook And Readiness Check

**Files:**
- Modify: `src/stock_research/daily_close_pipeline.py`
- Test: `tests/test_daily_close_pipeline.py`

- [ ] **Step 1: Write failing pipeline test**

Extend the market monitor stage test so it expects `build_concept_daily_bars_for_service(trade_date, trade_date, "ths", "qfq", service)` to be called after industry bars.

- [ ] **Step 2: Run focused pipeline test to verify failure**

Run: `rtk .venv/bin/python -m pytest tests/test_daily_close_pipeline.py -q`

Expected: FAIL because the market monitor stage does not build concept bars.

- [ ] **Step 3: Wire concept daily bar build into market monitor stage**

Import `build_concept_daily_bars_for_service` and call it with `concept_system="ths"` and `adjust_type="qfq"`. Do not fail the whole market monitor stage when there are no concept memberships yet; record concept rows in `sources` as optional.

- [ ] **Step 4: Run pipeline tests**

Run: `rtk .venv/bin/python -m pytest tests/test_daily_close_pipeline.py -q`

Expected: PASS.

### Task 5: Verify API And Frontend Behavior

**Files:**
- No production file changes unless verification exposes a real bug.

- [ ] **Step 1: Run backend focused tests**

Run:

```bash
rtk .venv/bin/python -m pytest tests/test_schema.py tests/test_core_data.py tests/test_dashboard_market_monitor_sector_services.py tests/test_daily_close_pipeline.py -q
```

Expected: PASS.

- [ ] **Step 2: Run frontend focused tests**

Run:

```bash
cd dashboard
rtk pnpm exec vitest run tests/market-monitor-workspace.test.tsx
rtk pnpm build
```

Expected: PASS. Build may keep the existing chunk-size warning.

- [ ] **Step 3: Browser verify localhost**

Open `http://127.0.0.1:5174/`, enter Market Monitor, switch to concept mode. Expected before concept membership ingestion: the page may still show no concept tiles, but API source should be ready to serve real concept data once `core.concept_membership` exists. Expected after concept membership ingestion and daily build: concept mode shows concept tiles with no `concept sector source is unavailable` warning.

---

## Self-Review

- Spec coverage: The plan covers local schema, daily concept aggregation, dashboard heatmap/fund-flow/detail services, daily close hook, and verification.
- Placeholder scan: No `TBD` or open-ended implementation steps remain; optional live vendor ingestion is intentionally excluded from MVP.
- Type consistency: `concept_system`, `concept_code`, `concept_name`, and `sector_type="concept"` are used consistently across schema, builders, and service payloads.
