# Ingest Batch Framework Design

Date: 2026-05-09

## Goal

Support controlled ingestion of A-share research datasets from 1990 onward.
Large datasets must be split into small resumable batches instead of being
loaded by long one-off commands.

## Scope

Phase 1 covers Baostock finance jobs. The same framework will later support
index bars, industry snapshots, corporate actions, announcements, and AKShare
datasets.

## Schema

Create schema `ingest` with:

- `ingest.batch_job`: one resumable unit of work.
- `ingest.batch_event`: append-only event log for job state changes.

Each job records dataset, source, year, quarter, date range, offset, limit,
status, row counts, error message, and params.

## Job Identity

Baostock finance job ids are deterministic:

```text
baostock-finance:{year}Q{quarter}:offset{offset}:limit{limit}
```

Creating jobs is idempotent. Existing successful jobs are not overwritten.

## Status Rules

Allowed statuses:

```text
pending
running
success
failed
```

The runner selects `pending` and `failed` jobs, marks each as `running`, runs it,
then marks it `success` or `failed` with counts and error text.

## Batch Size

Finance jobs should default to 50 stocks per job. This is intentionally smaller
than the earlier 200-stock batch because full historical ingestion spans many
years and quarters.

## CLI

Add:

```bash
stock-research create-ingest-jobs --dataset baostock-finance --start-year 1990 --end-year 2025 --batch-size 50
stock-research run-ingest-jobs --dataset baostock-finance --limit-jobs 10
stock-research ingest-status --dataset baostock-finance
```

## Non-Goals

- Do not run all jobs automatically after creation.
- Do not ingest all historical data in a single command.
- Do not add external schedulers yet.
- Do not change existing daily bar ingestion.

