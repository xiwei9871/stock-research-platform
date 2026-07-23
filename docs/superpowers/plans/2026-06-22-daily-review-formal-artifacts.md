# Daily Review Formal Artifacts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate formal Daily Review artifact files and register them in `report.report_run` so the dashboard can read a real daily review package instead of fallback-only data.

**Architecture:** Add a focused daily review artifact module that builds the dashboard payload, writes `json/md/manifest/operator_plan_template`, and records report paths with `report_type='daily_review_lite'`. Update the dashboard loader to prefer a registered JSON artifact and auto-generate one locally when no run exists yet.

**Tech Stack:** Python, FastAPI, pytest, existing `report_run_store`, local filesystem artifact writing under `reports/`.

---

### Task 1: Artifact Writer and Run Registration

**Files:**
- Create: `src/stock_research/dashboard/daily_review_artifacts.py`
- Test: `tests/test_dashboard_daily_review_artifacts.py`

- [x] Write failing tests for writing `json/md/manifest/operator_plan_template`.
- [x] Write failing tests for `record_report_run(..., report_type='daily_review_lite')`.
- [x] Implement the minimal artifact writer and registration helper.
- [x] Run the targeted pytest file and keep it green.

### Task 2: Dashboard Loader Integration

**Files:**
- Modify: `src/stock_research/dashboard/daily_review_lite.py`
- Test: `tests/test_dashboard_daily_review_artifacts.py`

- [x] Write a failing test that `build_daily_review_lite()` prefers a registered JSON artifact.
- [x] Write a failing test that missing runs trigger one local generation attempt.
- [x] Implement the loader integration.
- [x] Re-run the targeted pytest file and keep it green.

### Task 3: Local Verification

**Files:** none

- [x] Generate a real local Daily Review artifact for the latest trade date.
- [x] Verify `report.report_run` contains a `daily_review_lite` row.
- [x] Verify `http://127.0.0.1:5174` no longer shows `no registered daily review run selected` for that date.
