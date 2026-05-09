# Ingest Batch Framework Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add resumable batch ingestion jobs for long-running historical data loads.

**Architecture:** Store batch jobs in PostgreSQL under an `ingest` schema. Generate deterministic Baostock finance jobs by year, quarter, offset, and limit. Run a bounded number of jobs per command and record state transitions.

**Tech Stack:** Python 3, PostgreSQL, psycopg, pytest.

---

## Tasks

### Task 1: Schema

- [ ] Add `ingest.batch_job` and `ingest.batch_event` SQL to `CREATE_RESEARCH_EXTENSION_SQL`.
- [ ] Add schema tests.

### Task 2: Job Model

- [ ] Create `stock_research.ingest_jobs`.
- [ ] Implement deterministic job id creation.
- [ ] Implement Baostock finance job generation.

### Task 3: Persistence

- [ ] Implement `create_baostock_finance_jobs`.
- [ ] Implement `fetch_runnable_jobs`, `mark_job_running`, `mark_job_success`, `mark_job_failed`, and `ingest_status`.

### Task 4: Runner

- [ ] Implement `run_ingest_jobs` for `baostock-finance`.
- [ ] Reuse existing `sync_finance_for_period(year, quarter, offset, limit)`.

### Task 5: CLI and Verification

- [ ] Add `create-ingest-jobs`, `run-ingest-jobs`, and `ingest-status`.
- [ ] Apply schema.
- [ ] Create 1990-2025 finance jobs with small batch size.
- [ ] Run a tiny number of jobs for validation.
- [ ] Run full tests.

