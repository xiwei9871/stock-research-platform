# Full-History Phase 6 Industry History Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build safe historical industry membership and sector-bar infrastructure without accidentally launching a slow full-history job.

**Architecture:** Reuse the existing Baostock `query_stock_industry(date=...)` loader and `market.industry_daily_bar` builder. Add a single-day benchmark command and a guarded range runner with progress and `--max-dates`, then add a preflight coverage check for sector factor inputs.

**Tech Stack:** Python, PostgreSQL, Baostock, pytest, existing `stock-research` CLI.

---

## Single-Day Baseline

Measured before implementation on `2024-05-31`:

- `sync-industry-memberships --trade-date 2024-05-31`: 5326 rows, 21.69 seconds.
- `build-industry-bars --start-date 2024-05-31 --end-date 2024-05-31 --industry-system csrc --adjust-type hfq`: 0.35 seconds.

Implication: the Baostock industry endpoint is the bottleneck. Full-history execution must use a guarded, resumable, progress-reporting loop and should not be launched blindly.

## Scope

In scope:

- single-day benchmark helper and CLI;
- guarded date-range industry history command with progress and `--max-dates`;
- coverage check comparing tradable market bars to point-in-time industry membership;
- `research-preflight --require-industry-membership` option;
- runbook commands that require a single-day benchmark before range execution.

Out of scope:

- executing 1990-current industry backfill;
- adding non-CSRC industry systems;
- changing the sector factor definitions.

## Files

- Create: `src/stock_research/industry_history.py`
- Modify: `src/stock_research/cli.py`
- Modify: `src/stock_research/research_preflight.py`
- Modify: `tests/test_factor_cli.py`
- Create: `tests/test_industry_history.py`
- Modify: `tests/test_research_preflight.py`
- Modify: `docs/daily-factor-pipeline-runbook.md`

## Task 1: Industry History Benchmark And Guarded Runner

- [ ] **Step 1: Write failing tests**

Create `tests/test_industry_history.py` covering:

- `benchmark_industry_day` calls membership sync and industry bar build, records elapsed seconds, and returns rows.
- `build_industry_history_dates` filters by `max_dates`.
- `run_industry_history_range` emits progress events and calls one-day work per date.

- [ ] **Step 2: Verify red**

Run:

```bash
.venv/bin/python -m pytest tests/test_industry_history.py -q
```

Expected: FAIL because the module is missing.

- [ ] **Step 3: Implement module**

Create `src/stock_research/industry_history.py` with:

- `benchmark_industry_day(trade_date, industry_system="csrc", adjust_type="hfq", sync_func=..., build_func=..., timer=time.perf_counter)`;
- `build_industry_history_dates(start_date, end_date, max_dates=None)`;
- `run_industry_history_range(start_date, end_date, max_dates, industry_system, adjust_type, progress=None)`.

- [ ] **Step 4: Verify green**

Run:

```bash
.venv/bin/python -m pytest tests/test_industry_history.py -q
```

Expected: PASS.

## Task 2: CLI

- [ ] **Step 1: Write failing CLI tests**

Add parser tests for:

```bash
stock-research benchmark-industry-day --trade-date 2024-05-31 --industry-system csrc --adjust-type hfq
stock-research backfill-industry-history --start-date 2024-05-27 --end-date 2024-05-31 --max-dates 2 --industry-system csrc --adjust-type hfq
```

- [ ] **Step 2: Verify red**

Run:

```bash
.venv/bin/python -m pytest tests/test_factor_cli.py::test_cli_accepts_phase6_industry_history_commands -q
```

Expected: FAIL because parser commands are missing.

- [ ] **Step 3: Implement CLI**

Add command handlers printing stable lines:

```text
industry_day_benchmark|sync_memberships|DATE|rows|N|seconds|S
industry_day_benchmark|build_bars|DATE|seconds|S
industry_history_progress|DATE|INDEX|TOTAL|membership_rows|N|seconds|S
industry_history_done|dates|N|membership_rows|TOTAL|seconds|S
```

- [ ] **Step 4: Verify green**

Run:

```bash
.venv/bin/python -m pytest tests/test_factor_cli.py -q
```

Expected: PASS.

## Task 3: Preflight Coverage Check

- [ ] **Step 1: Write failing tests**

Add `check_industry_membership_coverage` tests in `tests/test_research_preflight.py` asserting it reads `market_daily_bar` and `core.industry_membership`, returns status `ok` or `blocked`, and exposes missing row counts.

- [ ] **Step 2: Verify red**

Run:

```bash
.venv/bin/python -m pytest tests/test_research_preflight.py::test_check_industry_membership_coverage_blocks_missing_memberships -q
```

Expected: FAIL because the helper is missing.

- [ ] **Step 3: Implement helper and CLI option**

Add `--require-industry-membership` to `research-preflight`. When enabled, print:

```text
research_preflight|industry_membership|STATUS|market_rows|N|covered_rows|N|missing_rows|N
```

- [ ] **Step 4: Verify green**

Run:

```bash
.venv/bin/python -m pytest tests/test_research_preflight.py tests/test_factor_cli.py -q
```

Expected: PASS.

## Task 4: Final Verification

- [ ] **Step 1: Update runbook**

Add Phase 6 commands:

```bash
stock-research benchmark-industry-day --trade-date YYYY-MM-DD --industry-system csrc --adjust-type hfq
stock-research backfill-industry-history --start-date YYYY-MM-DD --end-date YYYY-MM-DD --max-dates N --industry-system csrc --adjust-type hfq
stock-research research-preflight --start-date YYYY-MM-DD --end-date YYYY-MM-DD --require-industry-membership
```

- [ ] **Step 2: Final verification**

Run:

```bash
.venv/bin/python -m pytest -q
.venv/bin/stock-research benchmark-industry-day --trade-date 2024-05-31 --industry-system csrc --adjust-type hfq
.venv/bin/stock-research research-preflight --start-date 2024-05-31 --end-date 2024-05-31 --require-industry-membership --min-label-dates 1
git status --short --branch
```

