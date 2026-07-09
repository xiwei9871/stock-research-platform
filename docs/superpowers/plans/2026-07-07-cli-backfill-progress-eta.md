# CLI Backfill Progress ETA Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add reusable progress bars and ETA output for daily bar and 5-minute bar data backfills.

**Architecture:** Add a small zero-dependency `cli_progress` module. Wire it into `run-baostock-minute-backfill` through the existing progress callback and into `run_daily_stage` through a new optional progress callback.

**Tech Stack:** Python stdlib, pytest, existing `stock_research.cli` and `daily_close_pipeline`.

---

### Task 1: Shared Progress Renderer

**Files:**
- Create: `src/stock_research/cli_progress.py`
- Test: `tests/test_cli_progress.py`
- Modify: `src/stock_research/cli.py`

- [ ] Write tests for progress bar, duration formatting, ETA estimation, and non-TTY output.
- [ ] Verify tests fail before implementation.
- [ ] Implement the renderer and keep `stock_research.cli.format_progress_bar` compatible by delegating to the new module.
- [ ] Run `pytest tests/test_cli_progress.py tests/test_schema.py::test_format_progress_bar -q`.

### Task 2: Minute Backfill CLI Integration

**Files:**
- Modify: `src/stock_research/cli.py`
- Test: existing CLI tests near minute backfill parser/command coverage.

- [ ] Write a failing test proving `run-baostock-minute-backfill` passes a progress callback and final stdout summaries remain unchanged.
- [ ] Wire `ProgressRenderer("minute5_backfill")` into `run_baostock_minute_backfill`.
- [ ] Run the focused CLI test.

### Task 3: Daily Stage Progress Events

**Files:**
- Modify: `src/stock_research/daily_close_pipeline.py`
- Test: `tests/test_daily_close_pipeline.py`

- [ ] Write a failing test proving `run_daily_stage` emits progress events when supplied a callback.
- [ ] Add optional `progress` callback to `run_daily_stage`.
- [ ] Emit events for start, Tushare raw completion, adjusted fallback completion, upsert, and completed.
- [ ] Run daily close pipeline focused tests.

### Task 4: Verification

**Files:**
- No new files.

- [ ] Run `pytest tests/test_cli_progress.py tests/test_schema.py::test_format_progress_bar tests/test_daily_close_pipeline.py tests/test_minute_backfill.py -q`.
- [ ] Run a CLI smoke with mocked tests only, not live BaoStock.
