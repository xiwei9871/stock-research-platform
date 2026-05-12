# Full-History Phase 6 Industry History Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce industry-history backfill cost by caching Baostock industry snapshots and supporting sparse sampling before any full-history expansion.

**Architecture:** Store raw Baostock industry snapshot payloads keyed by snapshot date, then reuse cached snapshots on reruns. Extend the guarded industry range runner with `daily`, `monthly`, and `quarterly` sampling so broad history can be probed with far fewer remote calls before fine-grained refinement.

**Tech Stack:** Python, PostgreSQL, Baostock, pytest, existing `stock-research` CLI.

---

## Baseline

Observed Phase 6 single-day benchmarks:

- `sync_industry_memberships(2024-05-31)`: 13-21 seconds.
- `build_industry_daily_bars(2024-05-31)`: about 0.1-0.35 seconds.

The remote Baostock industry endpoint is the bottleneck. SQL aggregation is not the bottleneck.

## Scope

In scope:

- `raw_baostock.industry_snapshot_payload` schema;
- cached snapshot read/write helpers;
- `sync_industry_memberships(..., use_cache=True)`;
- `backfill-industry-history --frequency daily|monthly|quarterly`;
- `benchmark-industry-day --no-cache`;
- audit coverage for raw industry snapshots;
- small batch comparison: uncached fetch vs cached rerun, and daily vs sparse date count.

Out of scope:

- executing 1990-current industry backfill;
- automatic binary search for exact industry change dates;
- adding non-CSRC industry systems.

## Files

- Modify: `src/stock_research/schema.py`
- Modify: `src/stock_research/loaders/baostock_ingestion.py`
- Modify: `src/stock_research/industry_history.py`
- Modify: `src/stock_research/cli.py`
- Modify: `src/stock_research/data_audit.py`
- Modify: `tests/test_schema.py`
- Modify: `tests/test_baostock_ingestion.py`
- Modify: `tests/test_industry_history.py`
- Modify: `tests/test_factor_cli.py`
- Modify: `tests/test_data_audit.py`
- Modify: `docs/daily-factor-pipeline-runbook.md`

## Task 1: Raw Snapshot Cache Schema

- [ ] **Step 1: Write failing schema and audit tests**

Assert `CREATE_RESEARCH_EXTENSION_SQL` contains `raw_baostock.industry_snapshot_payload` and `idx_raw_baostock_industry_snapshot_date`.
Assert `data_audit.AUDIT_DATASETS` includes `raw_baostock.industry_snapshot_payload`.

- [ ] **Step 2: Implement schema**

Add:

```sql
CREATE TABLE IF NOT EXISTS raw_baostock.industry_snapshot_payload (
    snapshot_date date NOT NULL,
    source_endpoint text NOT NULL,
    request_params jsonb NOT NULL,
    payload jsonb NOT NULL,
    payload_hash text NOT NULL,
    row_count integer NOT NULL,
    fetched_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (snapshot_date, source_endpoint)
);
```

## Task 2: Cache-Aware Industry Sync

- [ ] **Step 1: Write failing loader tests**

Cover:

- `store_industry_snapshot_payload` inserts canonical JSON and hash;
- `load_cached_industry_snapshot_payload` returns cached rows;
- `sync_industry_memberships(..., use_cache=True)` skips Baostock login when cache exists.

- [ ] **Step 2: Implement loader cache**

Use `stock_research.loaders.raw_payloads.canonical_json` and `payload_hash`.
Keep `sync_industry_memberships` default cache-aware, and support `use_cache=False`.

## Task 3: Sparse Sampling

- [ ] **Step 1: Write failing industry history tests**

Cover:

- `build_industry_history_dates(..., frequency="monthly")`;
- `build_industry_history_dates(..., frequency="quarterly")`;
- `run_industry_history_range(..., frequency="monthly")`;
- parser accepts `--frequency monthly` and `--no-cache`.

- [ ] **Step 2: Implement sampling**

Add `frequency` to date generation and range runner. Add CLI choices.

## Task 4: Verification And Comparison

- [ ] **Step 1: Run tests**

```bash
.venv/bin/python -m pytest -q
```

- [ ] **Step 2: Small batch comparison**

Run:

```bash
.venv/bin/stock-research benchmark-industry-day --trade-date 2024-06-28 --industry-system csrc --adjust-type hfq --no-cache
.venv/bin/stock-research benchmark-industry-day --trade-date 2024-06-28 --industry-system csrc --adjust-type hfq
.venv/bin/stock-research backfill-industry-history --start-date 2024-06-01 --end-date 2024-06-30 --max-dates 31 --frequency monthly --industry-system csrc --adjust-type hfq
```

Compare:

- uncached remote fetch seconds;
- cached rerun seconds;
- monthly sampled date count vs daily date count.

