# BaoStock Minute5 Raw-Only Slow Run Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the daily 5-minute bar pipeline fetch only BaoStock raw bars, derive qfq from raw immediately, and schedule downstream EOD jobs after the slow run can complete.

**Architecture:** The daily minute5 stage remains the source of truth for current-day raw minute bars. It fetches SH/SZ via BaoStock single-worker source loops, upserts raw rows, derives qfq from raw and daily factors, then evaluates raw completeness. EOD auto repair repairs raw gaps directly from `ops.daily_pipeline_quality.missing_symbols`, derives qfq again, and must not report success when no rows were attempted and the quality check remains failed.

**Tech Stack:** Python, pytest, PostgreSQL access helpers, OpenClaw cron CLI, shell wrappers.

---

### Task 1: Raw-Only Daily Minute5 Behavior

**Files:**
- Modify: `tests/test_daily_close_pipeline.py`
- Modify: `src/stock_research/daily_close_pipeline.py`

- [ ] Add a test proving `run_minute5_stage` fetches raw rows once per symbol and invokes qfq derivation after raw upsert.
- [ ] Run the test and verify it fails if qfq is treated as an external fetch target or derivation is skipped.
- [ ] Keep `run_minute5_stage` source fetchers BaoStock-only and raw-only; qfq comes only from `derive_qfq_minute5_from_daily_factor`.
- [ ] Run the focused daily close tests.

### Task 2: Direct Raw Gap Repair

**Files:**
- Modify: `tests/test_eod_auto_repair_actions.py`
- Modify: `src/stock_research/eod_auto_repair_actions.py`
- Modify: `src/stock_research/eod_auto_repair.py`

- [ ] Add a test proving minute5 repair can repair explicit missing raw symbols directly and derives qfq after upsert.
- [ ] Add a test proving `attempted=0` does not return a misleading success when no direct repair is available.
- [ ] Implement direct raw repair action using today's `missing_symbols`, BaoStock raw fetch, raw upsert, qfq derivation, and quality refresh.
- [ ] Wire EOD auto repair to the direct repair path.
- [ ] Run focused EOD repair tests.

### Task 3: Cron Timing

**Files:**
- Update OpenClaw cron jobs via CLI.
- No code file should be changed unless deploy manifests also contain those schedules.

- [ ] Move `stock-daily-close-minute5-split` to 17:00 unchanged in name for compatibility.
- [ ] Move `stock-daily-close-finalize`, `stock-platform-ready-build`, `stock-strategy-daily-eod`, and `stock-eod-auto-repair` later so a 2-3 hour BaoStock slow run can finish before checks.
- [ ] Confirm `minute-backfill-watchdog` remains disabled.
- [ ] Print the resulting cron summary.

### Task 4: Verification

**Files:**
- Read-only outputs/logs only.

- [ ] Run the focused pytest targets.
- [ ] Run wrapper smoke checks where available.
- [ ] Run a read-only platform check after any manual repair run only if needed.
