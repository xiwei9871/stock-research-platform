# Full-History Phase 0 Safety And Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent smoke-test or partially backfilled data from being treated as research-grade full-history coverage.

**Architecture:** Keep Phase 0 read-safe and narrowly scoped: strengthen existing preflight semantics, add stale ingest job recovery for the current `ingest.batch_job` table, and add a read-only data audit CLI. Do not start full-history mutation jobs in this phase.

**Tech Stack:** Python, PostgreSQL, psycopg, pandas, pytest, existing `stock-research` CLI.

---

## Task 0: Preserve Long-Backfill Test Work

**Files:**
- Existing stash: `stash@{0}` named `wip long backfill test changes before full-history phase 0`

- [x] **Step 1: Save unrelated long-backfill testing edits**

Run:

```bash
git stash push -m "wip long backfill test changes before full-history phase 0"
```

Expected:

```text
Saved working directory and index state ...
```

- [x] **Step 2: Confirm clean working tree before Phase 0**

Run:

```bash
git status --short --branch
```

Expected: no modified source files.

## Task 1: Strict Factor Completeness Preflight

**Files:**
- Modify: `src/stock_research/research_preflight.py`
- Modify: `src/stock_research/cli.py`
- Modify: `tests/test_research_preflight.py`
- Modify: `tests/test_factor_cli.py`

- [ ] **Step 1: Write failing tests**

Add tests that build fake SQL results where factor rows exist on several dates but no date has all requested factor names. Expected result:

```python
coverage = check_factor_label_coverage(
    factor_names=["ret_5", "ret_20"],
    start_date="2024-01-01",
    end_date="2024-01-31",
    horizons=[5, 10],
    min_label_dates=2,
)
assert coverage["status"] == "blocked"
assert "insufficient_complete_factor_dates" in coverage["reasons"]
assert coverage["factor_date_count"] == 3
assert coverage["factor_complete_date_count"] == 0
```

Add a CLI test expecting the coverage line to include complete factor dates:

```text
research_preflight|coverage|blocked|factor_dates|3|complete_factor_dates|0
```

- [ ] **Step 2: Verify red**

Run:

```bash
.venv/bin/python -m pytest tests/test_research_preflight.py tests/test_factor_cli.py::test_research_preflight_cli_prints_machine_readable_lines -q
```

Expected: FAIL because `factor_complete_date_count` is not implemented and the CLI output lacks `complete_factor_dates`.

- [ ] **Step 3: Implement minimal code**

Change `check_factor_label_coverage` to compute:

- `factor_date_count`: distinct dates with any requested factor.
- `factor_complete_date_count`: distinct dates where `count(distinct factor_name) = len(factor_names)`.
- `missing_factor_names`: requested factor names with zero rows in the range.

Block when `factor_complete_date_count < min_label_dates`.

- [ ] **Step 4: Verify green**

Run:

```bash
.venv/bin/python -m pytest tests/test_research_preflight.py tests/test_factor_cli.py -q
```

Expected: PASS.

## Task 2: Stale Ingest Job Recovery

**Files:**
- Modify: `src/stock_research/ingest_jobs.py`
- Modify: `src/stock_research/cli.py`
- Modify: `tests/test_ingest_jobs.py`
- Modify: `tests/test_factor_cli.py` or existing CLI test file that covers ingest commands

- [ ] **Step 1: Write failing tests**

Add tests for `reset_stale_ingest_jobs`:

```python
count = reset_stale_ingest_jobs(
    conn,
    dataset="baostock-finance",
    older_than_minutes=60,
)
assert count == 2
```

Expected SQL semantics:

```sql
UPDATE ingest.batch_job
SET status = 'pending',
    error_message = 'reset stale running job',
    finished_at = now(),
    updated_at = now()
WHERE dataset = %s
  AND status = 'running'
  AND started_at < now() - (%s::text || ' minutes')::interval
```

Add CLI test expecting:

```text
ingest_stale_reset|baostock-finance|2
```

- [ ] **Step 2: Verify red**

Run:

```bash
.venv/bin/python -m pytest tests/test_ingest_jobs.py tests/test_factor_cli.py::test_reset_stale_ingest_jobs_cli_prints_count -q
```

Expected: FAIL because the function and CLI command do not exist.

- [ ] **Step 3: Implement minimal code**

Add `reset_stale_ingest_jobs` and `reset_stale_ingest_jobs_for_service`.
Add CLI command:

```bash
stock-research reset-stale-ingest-jobs --dataset baostock-finance --older-than-minutes 60
```

- [ ] **Step 4: Verify green**

Run:

```bash
.venv/bin/python -m pytest tests/test_ingest_jobs.py tests/test_factor_cli.py -q
```

Expected: PASS.

## Task 3: Read-Only Data Audit CLI

**Files:**
- Create: `src/stock_research/data_audit.py`
- Modify: `src/stock_research/cli.py`
- Create: `tests/test_data_audit.py`
- Modify: `tests/test_factor_cli.py`

- [ ] **Step 1: Write failing tests**

Add a unit test for audit line formatting:

```python
line = format_audit_line(
    {"dataset": "market_daily_bar", "rows": 10, "date_count": 2, "min_date": "2024-01-01", "max_date": "2024-01-02", "status": "short_history"}
)
assert line == "data_audit|market_daily_bar|short_history|rows|10|dates|2|min|2024-01-01|max|2024-01-02"
```

Add a CLI test that monkeypatches `run_data_audit` and expects stable output.

- [ ] **Step 2: Verify red**

Run:

```bash
.venv/bin/python -m pytest tests/test_data_audit.py tests/test_factor_cli.py::test_data_audit_cli_prints_lines -q
```

Expected: FAIL because `stock_research.data_audit` and `data-audit` do not exist.

- [ ] **Step 3: Implement minimal code**

Implement read-only audit checks for:

- `market_daily_bar`
- `label_snapshot`
- `factor.factor_daily`
- `core.industry_membership`
- `market.industry_daily_bar`
- `finance.income_statement`
- `finance.balance_sheet`
- `finance.cash_flow`
- `factor.factor_approval`
- `ingest.batch_job`

Use `1990-12-01` as the default expected start lower bound.

- [ ] **Step 4: Verify green**

Run:

```bash
.venv/bin/python -m pytest tests/test_data_audit.py tests/test_factor_cli.py -q
```

Expected: PASS.

## Task 4: Documentation And Final Verification

**Files:**
- Modify: `docs/daily-factor-pipeline-runbook.md`
- Modify: `docs/superpowers/plans/2026-05-11-full-history-a-share-data-platform-master.md`

- [ ] **Step 1: Document Phase 0 commands**

Add runbook commands:

```bash
stock-research data-audit --expected-start-date 1990-12-01
stock-research reset-stale-ingest-jobs --dataset baostock-finance --older-than-minutes 60
stock-research research-preflight --start-date 1990-12-01 --horizons 5,10,20,60 --min-label-dates 20
```

- [ ] **Step 2: Run full verification**

Run:

```bash
.venv/bin/python -m pytest -q
.venv/bin/stock-research data-audit --expected-start-date 1990-12-01
git status --short --branch
```

Expected: tests pass, audit command exits 0, working tree contains only intentional Phase 0 files before commit.

- [ ] **Step 3: Commit**

Run:

```bash
git add src/stock_research/research_preflight.py src/stock_research/ingest_jobs.py src/stock_research/data_audit.py src/stock_research/cli.py tests/test_research_preflight.py tests/test_ingest_jobs.py tests/test_data_audit.py tests/test_factor_cli.py docs/daily-factor-pipeline-runbook.md docs/superpowers/plans/2026-05-11-full-history-a-share-data-platform-master.md docs/superpowers/plans/2026-05-11-full-history-phase-0-safety-and-audit.md
git commit -m "Add full-history phase 0 safety checks"
```

Expected: one focused Phase 0 commit.
