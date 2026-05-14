# Minute Backfill Controller v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make 3-year full-market 5-minute raw/qfq imports resumable, observable, retryable, and safe to run in bounded batches.

**Architecture:** Convert `market.stock_minute_bar` to monthly `trade_date` RANGE partitions while preserving existing sample rows. Add `market.minute_bar_backfill_job` as the controller state table, and keep planning, execution, status, validation, and report generation in `minute_backfill.py` behind CLI commands.

**Tech Stack:** PostgreSQL partitioned tables, psycopg, Baostock, Python stdlib CSV/report output, pytest.

---

### Task 1: Partition and Job Schema

- [ ] Add schema tests for monthly partition DDL, partition-compatible primary key, idempotent schema application, and job table indexes.
- [ ] Update `schema.py` with safe ordinary-table migration and monthly partition creation.
- [ ] Verify existing sample rows remain after schema apply.

### Task 2: Controller Core

- [ ] Add tests for monthly job planning, success skip, failed retry, status summary, and validation errors.
- [ ] Create `minute_backfill.py` with planner, runner, status, validation, CSV output, and report writer.
- [ ] Reuse existing `minute_data.py` query/upsert functions.

### Task 3: CLI

- [ ] Add parser tests for `plan-baostock-minute-backfill`, `run-baostock-minute-backfill`, `baostock-minute-backfill-status`, and `validate-minute-bars`.
- [ ] Wire commands in `cli.py`.

### Task 4: Small Trial

- [ ] Plan 10 assets over 5 trading days, raw/qfq, 5min.
- [ ] Run only the bounded planned jobs.
- [ ] Record elapsed time, rows, failure rate, DB/index size delta, duplicate check, and validation output.
- [ ] Write `outputs/research/minute_backfill_controller_report.md`.
