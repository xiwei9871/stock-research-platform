# Full-History Phase 1 Backfill Control Plane Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a generic, resumable, observable backfill run/task control plane for full-history data loading.

**Architecture:** Add `ingest.backfill_run` and `ingest.backfill_task` tables, then expose focused helpers in `stock_research.backfill_runs`. The CLI will create runs, create date-partition tasks, show run status, claim tasks for workers, mark tasks success/failure, and reset stale running tasks. This phase does not implement any dataset-specific historical loader.

**Tech Stack:** Python, PostgreSQL, psycopg, pytest, existing `stock-research` CLI and `stock_research.db` helpers.

---

## Scope

In scope:

- schema for run/task tracking;
- date partition task creation;
- pending/failed task claiming with row locking;
- success/failure transitions;
- stale running task reset;
- CLI status and recovery commands.

Out of scope:

- daily bar source ingestion;
- financial statement ingestion changes;
- industry/index/calendar loaders;
- running large mutation jobs.

## Files

- Modify: `src/stock_research/schema.py`
- Create: `src/stock_research/backfill_runs.py`
- Modify: `src/stock_research/cli.py`
- Create: `tests/test_backfill_runs.py`
- Modify: `tests/test_schema.py`
- Modify: `tests/test_factor_cli.py`
- Modify: `docs/daily-factor-pipeline-runbook.md`

## Task 1: Backfill Run And Task Schema

- [ ] **Step 1: Write failing schema tests**

Add to `tests/test_schema.py`:

```python
def test_research_extension_includes_backfill_run_task_tables():
    sql = CREATE_RESEARCH_EXTENSION_SQL
    assert "CREATE TABLE IF NOT EXISTS ingest.backfill_run" in sql
    assert "CREATE TABLE IF NOT EXISTS ingest.backfill_task" in sql
    assert "idx_ingest_backfill_task_status" in sql
    assert "idx_ingest_backfill_task_run_status" in sql
```

- [ ] **Step 2: Run test to verify red**

Run:

```bash
.venv/bin/python -m pytest tests/test_schema.py::test_research_extension_includes_backfill_run_task_tables -q
```

Expected: FAIL because the schema tables do not exist.

- [ ] **Step 3: Implement schema**

Add `ingest.backfill_run`:

```sql
CREATE TABLE IF NOT EXISTS ingest.backfill_run (
    run_id text PRIMARY KEY,
    dataset text NOT NULL,
    source text NOT NULL,
    source_version text NOT NULL,
    start_date date,
    end_date date,
    status text NOT NULL DEFAULT 'pending',
    params jsonb NOT NULL DEFAULT '{}'::jsonb,
    error_message text,
    created_at timestamptz NOT NULL DEFAULT now(),
    started_at timestamptz,
    finished_at timestamptz,
    updated_at timestamptz NOT NULL DEFAULT now()
);
```

Add `ingest.backfill_task`:

```sql
CREATE TABLE IF NOT EXISTS ingest.backfill_task (
    task_id text PRIMARY KEY,
    run_id text NOT NULL REFERENCES ingest.backfill_run(run_id),
    dataset text NOT NULL,
    partition_key text NOT NULL,
    start_date date,
    end_date date,
    status text NOT NULL DEFAULT 'pending',
    rows_read integer NOT NULL DEFAULT 0,
    rows_written integer NOT NULL DEFAULT 0,
    attempts integer NOT NULL DEFAULT 0,
    error_message text,
    params jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    started_at timestamptz,
    finished_at timestamptz,
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (run_id, partition_key)
);
```

Add indexes:

```sql
CREATE INDEX IF NOT EXISTS idx_ingest_backfill_task_status
    ON ingest.backfill_task (dataset, status, start_date);

CREATE INDEX IF NOT EXISTS idx_ingest_backfill_task_run_status
    ON ingest.backfill_task (run_id, status, start_date);
```

- [ ] **Step 4: Run test to verify green**

Run:

```bash
.venv/bin/python -m pytest tests/test_schema.py::test_research_extension_includes_backfill_run_task_tables -q
```

Expected: PASS.

## Task 2: Backfill Run Helpers

- [ ] **Step 1: Write failing tests**

Create `tests/test_backfill_runs.py` with fake connection helpers. Add tests for:

- `build_date_partitions("2024-01-01", "2024-03-31", months_per_partition=1)` returns three inclusive monthly partitions.
- `create_backfill_run` inserts one run and idempotently upserts tasks.
- `backfill_status` returns status counts for a run.

- [ ] **Step 2: Run tests to verify red**

Run:

```bash
.venv/bin/python -m pytest tests/test_backfill_runs.py -q
```

Expected: FAIL because `stock_research.backfill_runs` does not exist.

- [ ] **Step 3: Implement helpers**

Create `src/stock_research/backfill_runs.py` with:

- `build_date_partitions(start_date, end_date, months_per_partition=1) -> list[dict]`;
- `create_backfill_run(conn, run_id, dataset, source, source_version, start_date, end_date, partitions, params=None) -> dict`;
- `backfill_status(conn, run_id) -> dict`.

Use `execute` / `execute_many` / `fetch_all` from `stock_research.db`.

- [ ] **Step 4: Run tests to verify green**

Run:

```bash
.venv/bin/python -m pytest tests/test_backfill_runs.py -q
```

Expected: PASS.

## Task 3: Task Claim And State Transitions

- [ ] **Step 1: Write failing tests**

Add tests for:

- `claim_backfill_tasks(conn, run_id="run-1", limit=2)` selects pending/failed tasks and sets them to running with `attempts = attempts + 1`.
- `mark_backfill_task_success(conn, task_id="task-1", rows_read=10, rows_written=9)` marks success.
- `mark_backfill_task_failed(conn, task_id="task-1", error_message="boom")` marks failed.
- `reset_stale_backfill_tasks(conn, older_than_minutes=60, dataset="daily-bars")` resets old running tasks to pending.

- [ ] **Step 2: Run tests to verify red**

Run:

```bash
.venv/bin/python -m pytest tests/test_backfill_runs.py -q
```

Expected: FAIL because these functions do not exist.

- [ ] **Step 3: Implement transitions**

Implement the functions in `src/stock_research/backfill_runs.py`. Claiming tasks must use:

```sql
FOR UPDATE SKIP LOCKED
```

to support multiple workers later.

- [ ] **Step 4: Run tests to verify green**

Run:

```bash
.venv/bin/python -m pytest tests/test_backfill_runs.py -q
```

Expected: PASS.

## Task 4: CLI Commands

- [ ] **Step 1: Write failing CLI tests**

Add to `tests/test_factor_cli.py`:

- parser accepts `create-backfill-run`;
- parser accepts `backfill-status`;
- parser accepts `claim-backfill-tasks`;
- parser accepts `mark-backfill-task-success`;
- parser accepts `mark-backfill-task-failed`;
- parser accepts `reset-stale-backfill-tasks`;
- each command prints stable pipe-delimited output when monkeypatched.

Expected output examples:

```text
backfill_run_created|run-1|daily-bars|tasks|3
backfill_status|run-1|pending|3
backfill_task_claimed|task-1|2024-01|2024-01-01|2024-01-31
backfill_task_success|task-1|10|9
backfill_task_failed|task-1|boom
backfill_task_stale_reset|daily-bars|2
```

- [ ] **Step 2: Run tests to verify red**

Run:

```bash
.venv/bin/python -m pytest tests/test_factor_cli.py -q
```

Expected: FAIL because CLI commands do not exist.

- [ ] **Step 3: Implement CLI**

Import the helper functions from `stock_research.backfill_runs`.
Add parser commands:

```bash
stock-research create-backfill-run --run-id RUN --dataset DATASET --source SOURCE --source-version VERSION --start-date YYYY-MM-DD --end-date YYYY-MM-DD --months-per-partition 1
stock-research backfill-status --run-id RUN
stock-research claim-backfill-tasks --run-id RUN --limit 10
stock-research mark-backfill-task-success --task-id TASK --rows-read 10 --rows-written 9
stock-research mark-backfill-task-failed --task-id TASK --error-message boom
stock-research reset-stale-backfill-tasks --dataset DATASET --older-than-minutes 60
```

- [ ] **Step 4: Run tests to verify green**

Run:

```bash
.venv/bin/python -m pytest tests/test_factor_cli.py tests/test_backfill_runs.py -q
```

Expected: PASS.

## Task 5: Docs And Verification

- [ ] **Step 1: Update runbook**

Add Phase 1 control plane commands to `docs/daily-factor-pipeline-runbook.md` under the full-history section.

- [ ] **Step 2: Run full verification**

Run:

```bash
.venv/bin/python -m pytest -q
.venv/bin/stock-research data-audit --expected-start-date 1990-12-01
git status --short --branch
```

Expected:

- tests pass;
- audit exits 0;
- only intended files are modified.

- [ ] **Step 3: Commit**

Run:

```bash
git add src/stock_research/schema.py src/stock_research/backfill_runs.py src/stock_research/cli.py tests/test_schema.py tests/test_backfill_runs.py tests/test_factor_cli.py docs/daily-factor-pipeline-runbook.md docs/superpowers/plans/2026-05-11-full-history-phase-1-backfill-control-plane.md
git commit -m "Add full-history backfill control plane"
```
