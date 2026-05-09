# Stock Research Database Expansion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the first phase of a point-in-time stock research database extension without breaking the existing daily bar pipeline.

**Architecture:** Extend `schema.py` with additive PostgreSQL schemas and tables. Add small query services for point-in-time finance, historical industry membership, and daily asset status. Add loader helpers that persist raw source payloads before normalized rows; complete endpoint crawlers are out of scope.

**Tech Stack:** Python 3, PostgreSQL, psycopg, pytest.

---

## File Structure

- Modify `src/stock_research/schema.py`: add `CREATE_RESEARCH_EXTENSION_SQL` and apply it from `apply_schema`.
- Create `src/stock_research/services/__init__.py`: service package marker.
- Create `src/stock_research/services/point_in_time_finance.py`: finance PIT query functions.
- Create `src/stock_research/services/industry_membership_service.py`: historical industry membership query function.
- Create `src/stock_research/services/asset_status_service.py`: daily status and tradability helpers.
- Create `src/stock_research/loaders/__init__.py`: loader package marker.
- Create `src/stock_research/loaders/raw_payloads.py`: raw payload hashing and persistence helpers.
- Create `src/stock_research/loaders/akshare_finance_loader.py`: AKShare loader boundary.
- Create `src/stock_research/loaders/baostock_finance_loader.py`: Baostock loader boundary.
- Modify `src/stock_research/cli.py`: add `apply-research-schema` command.
- Create tests under `tests/` for schema, PIT services, status service, industry service, and raw payload helpers.

## Task 1: Add Research Schema SQL

**Files:**
- Modify: `src/stock_research/schema.py`
- Modify: `tests/test_schema.py`

- [ ] **Step 1: Write failing schema tests**

Add tests asserting the new schemas, tables, indexes, and additive `apply_schema` behavior exist.

- [ ] **Step 2: Run schema tests and verify failure**

Run: `/Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_schema.py -v`

Expected: fails because `CREATE_RESEARCH_EXTENSION_SQL` is missing.

- [ ] **Step 3: Implement additive schema SQL**

Add `CREATE_RESEARCH_EXTENSION_SQL`, append it in `apply_schema`, and keep existing `CREATE_TABLES_SQL` unchanged for compatibility.

- [ ] **Step 4: Run schema tests and verify pass**

Run: `/Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_schema.py -v`

Expected: all schema tests pass.

## Task 2: Add Point-in-Time Finance Service

**Files:**
- Create: `src/stock_research/services/__init__.py`
- Create: `src/stock_research/services/point_in_time_finance.py`
- Create: `tests/test_point_in_time_finance.py`

- [ ] **Step 1: Write failing tests**

Test that SQL filters by `announcement_date <= trade_date`, orders by newest `announcement_date` then newest `report_period`, and returns `None` when no row exists.

- [ ] **Step 2: Run tests and verify failure**

Run: `/Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_point_in_time_finance.py -v`

Expected: import failure because the service does not exist.

- [ ] **Step 3: Implement minimal service**

Implement `get_latest_indicator`, `get_latest_income_statement`, `get_latest_balance_sheet`, and `get_latest_cash_flow`.

- [ ] **Step 4: Run tests and verify pass**

Run: `/Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_point_in_time_finance.py -v`

Expected: all tests pass.

## Task 3: Add Historical Industry and Status Services

**Files:**
- Create: `src/stock_research/services/industry_membership_service.py`
- Create: `src/stock_research/services/asset_status_service.py`
- Create: `tests/test_industry_membership_service.py`
- Create: `tests/test_asset_status_service.py`

- [ ] **Step 1: Write failing tests**

Test historical membership windows and daily tradability filters.

- [ ] **Step 2: Run tests and verify failure**

Run: `/Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_industry_membership_service.py tests/test_asset_status_service.py -v`

Expected: import failures because services do not exist.

- [ ] **Step 3: Implement minimal services**

Implement `get_membership`, `get_status`, and `is_tradable`.

- [ ] **Step 4: Run tests and verify pass**

Run: `/Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_industry_membership_service.py tests/test_asset_status_service.py -v`

Expected: all tests pass.

## Task 4: Add Raw Payload Loader Boundary

**Files:**
- Create: `src/stock_research/loaders/__init__.py`
- Create: `src/stock_research/loaders/raw_payloads.py`
- Create: `src/stock_research/loaders/akshare_finance_loader.py`
- Create: `src/stock_research/loaders/baostock_finance_loader.py`
- Create: `tests/test_raw_payloads.py`

- [ ] **Step 1: Write failing tests**

Test stable payload hashing, raw payload insert SQL, AKShare target table, and Baostock target table.

- [ ] **Step 2: Run tests and verify failure**

Run: `/Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_raw_payloads.py -v`

Expected: import failure because loader helpers do not exist.

- [ ] **Step 3: Implement minimal loader helpers**

Implement `payload_hash`, `store_raw_payload`, `store_akshare_finance_payload`, and `store_baostock_finance_payload`.

- [ ] **Step 4: Run tests and verify pass**

Run: `/Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_raw_payloads.py -v`

Expected: all tests pass.

## Task 5: Add CLI Entry and Full Verification

**Files:**
- Modify: `src/stock_research/cli.py`
- Modify: `tests/test_schema.py`

- [ ] **Step 1: Write failing CLI parser test**

Test that `apply-research-schema` is accepted by the parser.

- [ ] **Step 2: Run test and verify failure**

Run: `/Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_schema.py -v`

Expected: failure because parser does not yet include `apply-research-schema`.

- [ ] **Step 3: Implement CLI command**

Add parser command and call `apply_schema()` for it.

- [ ] **Step 4: Run focused tests**

Run all focused tests added in this plan.

- [ ] **Step 5: Run full test suite**

Run: `/Users/xiwei/stock_research/.venv/bin/python -m pytest -q`

Expected: all tests pass.

