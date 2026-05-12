# Full-History Phase 4 Actions And Tradability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add point-in-time adjustment factor and corporate action foundations while reusing existing daily tradability status.

**Architecture:** Keep `core.asset_status_daily` as the canonical ST, suspension, and limit flag table. Add `market.adjustment_factor` and `market.corporate_action`, then derive adjustment factors from already-loaded `market_daily_bar` price variants and derive adjustment events from factor changes.

**Tech Stack:** Python, PostgreSQL, pytest, existing `stock-research` CLI.

---

## Scope

In scope:

- `market.adjustment_factor` schema;
- `market.corporate_action` schema;
- idempotent builder for adjustment factors from `raw`, `qfq`, and `hfq` daily bars;
- idempotent builder for derived corporate action events when the factor changes;
- CLI commands for small date-range builds;
- audit coverage for the new tables;
- runbook commands for Phase 4.

Out of scope:

- fetching dividend, split, rights issue detail from an external provider;
- rewriting normalized daily bar storage;
- executing 1990-current mutation jobs;
- changing backtest execution logic.

## Files

- Modify: `src/stock_research/schema.py`
- Create: `src/stock_research/corporate_actions.py`
- Modify: `src/stock_research/cli.py`
- Modify: `src/stock_research/data_audit.py`
- Modify: `tests/test_schema.py`
- Create: `tests/test_corporate_actions.py`
- Modify: `tests/test_factor_cli.py`
- Modify: `tests/test_data_audit.py`
- Modify: `docs/daily-factor-pipeline-runbook.md`

## Task 1: Schema

- [ ] **Step 1: Write failing schema test**

Add:

```python
def test_research_extension_includes_phase4_action_tables():
    sql = CREATE_RESEARCH_EXTENSION_SQL
    assert "CREATE TABLE IF NOT EXISTS market.adjustment_factor" in sql
    assert "CREATE TABLE IF NOT EXISTS market.corporate_action" in sql
    assert "idx_market_adjustment_factor_date" in sql
    assert "idx_market_corporate_action_asset_date" in sql
```

- [ ] **Step 2: Verify red**

Run:

```bash
.venv/bin/python -m pytest tests/test_schema.py::test_research_extension_includes_phase4_action_tables -q
```

Expected: FAIL because the tables do not exist.

- [ ] **Step 3: Implement schema**

Add:

```sql
CREATE TABLE IF NOT EXISTS market.adjustment_factor (
    asset_id text NOT NULL,
    trade_date date NOT NULL,
    raw_close numeric,
    qfq_close numeric,
    hfq_close numeric,
    qfq_factor numeric,
    hfq_factor numeric,
    source text NOT NULL,
    source_version text NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (asset_id, trade_date, source_version)
);

CREATE TABLE IF NOT EXISTS market.corporate_action (
    asset_id text NOT NULL,
    event_date date NOT NULL,
    action_type text NOT NULL,
    factor_before numeric,
    factor_after numeric,
    source text NOT NULL,
    source_version text NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (asset_id, event_date, action_type, source_version)
);
```

- [ ] **Step 4: Verify green**

Run:

```bash
.venv/bin/python -m pytest tests/test_schema.py::test_research_extension_includes_phase4_action_tables -q
```

Expected: PASS.

## Task 2: Builders

- [ ] **Step 1: Write failing builder tests**

Create `tests/test_corporate_actions.py` verifying:

- `build_adjustment_factors` inserts from raw/qfq/hfq `market_daily_bar`;
- factors use `qfq.close / raw.close` and `hfq.close / raw.close`;
- `build_corporate_actions_from_factors` uses `lag(...)` and records factor-change events;
- service wrappers open a connection.

- [ ] **Step 2: Verify red**

Run:

```bash
.venv/bin/python -m pytest tests/test_corporate_actions.py -q
```

Expected: FAIL because module is missing.

- [ ] **Step 3: Implement module**

Create `src/stock_research/corporate_actions.py` with:

- `build_adjustment_factors(conn, start_date=None, end_date=None, source_version="derived_market_daily_bar_v1") -> None`;
- `build_adjustment_factors_for_service(...) -> None`;
- `build_corporate_actions_from_factors(conn, start_date=None, end_date=None, source_version="derived_adjustment_factor_v1") -> None`;
- `build_corporate_actions_from_factors_for_service(...) -> None`.

- [ ] **Step 4: Verify green**

Run:

```bash
.venv/bin/python -m pytest tests/test_corporate_actions.py -q
```

Expected: PASS.

## Task 3: CLI And Audit

- [ ] **Step 1: Write failing tests**

Add CLI parser tests for:

```bash
stock-research build-adjustment-factors --start-date 2024-01-01 --end-date 2024-01-31 --source-version derived_v1
stock-research build-corporate-actions --start-date 2024-01-01 --end-date 2024-01-31 --source-version derived_v1
```

Add audit dataset assertions for:

- `market.adjustment_factor`;
- `market.corporate_action`.

- [ ] **Step 2: Verify red**

Run:

```bash
.venv/bin/python -m pytest tests/test_factor_cli.py tests/test_data_audit.py -q
```

Expected: FAIL because parser and audit datasets are missing.

- [ ] **Step 3: Implement CLI and audit**

Import the two service wrappers. Add commands and print:

```text
adjustment_factors_built
corporate_actions_built
```

Add audit datasets using `trade_date` and `event_date`.

- [ ] **Step 4: Verify green**

Run:

```bash
.venv/bin/python -m pytest tests/test_factor_cli.py tests/test_data_audit.py -q
```

Expected: PASS.

## Task 4: Runbook And Final Verification

- [ ] **Step 1: Update runbook**

Add:

```bash
stock-research build-asset-status --start-date 1990-12-19 --end-date YYYY-MM-DD --adjust-type hfq
stock-research build-adjustment-factors --start-date 1990-12-19 --end-date YYYY-MM-DD --source-version derived_market_daily_bar_v1
stock-research build-corporate-actions --start-date 1990-12-19 --end-date YYYY-MM-DD --source-version derived_adjustment_factor_v1
stock-research data-audit --expected-start-date 1990-12-01
```

- [ ] **Step 2: Final verification**

Run:

```bash
.venv/bin/python -m pytest -q
.venv/bin/stock-research apply-research-schema
.venv/bin/stock-research build-asset-status --start-date 2024-05-27 --end-date 2024-05-27 --adjust-type hfq
.venv/bin/stock-research build-adjustment-factors --start-date 2024-05-27 --end-date 2024-05-27 --source-version phase4_smoke_v1
.venv/bin/stock-research build-corporate-actions --start-date 2024-05-27 --end-date 2024-05-27 --source-version phase4_smoke_v1
.venv/bin/stock-research data-audit --expected-start-date 1990-12-01
git status --short --branch
```

