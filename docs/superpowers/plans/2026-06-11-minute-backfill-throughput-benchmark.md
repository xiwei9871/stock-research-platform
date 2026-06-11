# Minute Backfill Throughput Benchmark Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a safe benchmark command that compares BaoStock minute backfill throughput across worker counts without changing production defaults.

**Architecture:** Keep the existing `run_baostock_minute_backfill` execution path unchanged. Add a small wrapper in `minute_backfill.py` that runs the existing function for several worker counts, measures elapsed time, computes throughput metrics, and returns structured rows for CLI output.

**Tech Stack:** Python, pytest, existing argparse CLI, existing BaoStock minute backfill job table.

---

### Task 1: Add Benchmark Function

**Files:**
- Modify: `src/stock_research/minute_backfill.py`
- Test: `tests/test_minute_backfill.py`

- [ ] **Step 1: Write failing test**

Add a test that monkeypatches `run_baostock_minute_backfill` and a monotonic timer. The expected behavior is one benchmark row per worker count with elapsed seconds, jobs per second, rows per second, and failed rate.

- [ ] **Step 2: Run failing test**

Run:

```bash
.venv/bin/pytest tests/test_minute_backfill.py::test_benchmark_minute_backfill_workers_reports_throughput -q
```

Expected: fail because `benchmark_baostock_minute_backfill_workers` is not defined.

- [ ] **Step 3: Implement minimal function**

Add `benchmark_baostock_minute_backfill_workers(...)` to `minute_backfill.py`. It should accept the same scope arguments as `run_baostock_minute_backfill`, plus `worker_counts`. It should call the existing runner once per worker count and compute:

- `elapsed_seconds`
- `attempted`
- `success`
- `failed`
- `rows`
- `jobs_per_second`
- `rows_per_second`
- `failed_rate`

- [ ] **Step 4: Run passing test**

Run:

```bash
.venv/bin/pytest tests/test_minute_backfill.py::test_benchmark_minute_backfill_workers_reports_throughput -q
```

Expected: pass.

### Task 2: Add CLI Command

**Files:**
- Modify: `src/stock_research/cli.py`
- Test: `tests/test_schema.py`

- [ ] **Step 1: Write failing CLI parser test**

Add a parser test for:

```bash
benchmark-baostock-minute-backfill --workers-list 4,8,12 --max-jobs 300 --freq 5min --adjust-types raw
```

Expected parsed values:

- command: `benchmark-baostock-minute-backfill`
- worker_counts: `[4, 8, 12]`
- max_jobs: `300`
- freq: `5min`
- adjust_types: `["raw"]`

- [ ] **Step 2: Run failing parser test**

Run:

```bash
.venv/bin/pytest tests/test_schema.py::test_cli_accepts_baostock_ingestion_commands -q
```

Expected: fail because the command does not exist.

- [ ] **Step 3: Implement parser and dispatch**

Add the command near the existing minute backfill commands. Print one line per row:

```text
minute_backfill_benchmark|workers|4|attempted|300|success|298|failed|2|rows|14304|elapsed_seconds|120.0|jobs_per_second|2.5|rows_per_second|119.2|failed_rate|0.0067
```

- [ ] **Step 4: Run parser and dispatch tests**

Run:

```bash
.venv/bin/pytest tests/test_schema.py::test_cli_accepts_baostock_ingestion_commands tests/test_minute_backfill.py::test_benchmark_minute_backfill_workers_reports_throughput -q
```

Expected: pass.

### Task 3: Verification

**Files:**
- Modify: none unless tests reveal issues.

- [ ] **Step 1: Run focused tests**

```bash
.venv/bin/pytest tests/test_minute_backfill.py tests/test_schema.py::test_cli_accepts_baostock_ingestion_commands -q
```

- [ ] **Step 2: Run hygiene checks**

```bash
git diff --check
rg -n "(TOKEN|token|secret|api_key).*[A-Za-z0-9_-]{20,}" src tests docs scripts || true
```

- [ ] **Step 3: Commit and push**

```bash
git add src/stock_research/minute_backfill.py src/stock_research/cli.py tests/test_minute_backfill.py tests/test_schema.py docs/superpowers/plans/2026-06-11-minute-backfill-throughput-benchmark.md
git commit -m "feat: add minute backfill throughput benchmark"
git push origin lhb-shortline-strategy-dev-20260609
```
