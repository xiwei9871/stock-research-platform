# Daily Review Lite Workspace Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an independent Daily Review workspace to the local dashboard so daily operator review is not hidden inside the single-stock workspace.

**Architecture:** Add a backend read-only projection for a Daily Review Lite payload, then render it in a dedicated frontend workspace between Review Queue and Market Monitor. The first version uses registered report artifacts when present and otherwise returns a partial fallback assembled from existing platform, market, review queue, and generated report APIs.

**Tech Stack:** FastAPI backend, React/Vite dashboard, Vitest frontend tests, pytest backend route tests.

---

### Task 1: Backend Daily Review Lite Contract

**Files:**
- Create: `src/stock_research/dashboard/daily_review_lite.py`
- Modify: `src/stock_research/dashboard/app.py`
- Test: `tests/test_dashboard_app.py`

- [x] Write a failing route test for `/api/daily-review-lite`.
- [x] Implement a read-only payload with `status`, `trade_date`, `sections`, `artifacts`, `run`, and `warnings`.
- [x] Verify pytest route test passes.

### Task 2: Frontend Workspace

**Files:**
- Modify: `dashboard/src/api/types.ts`
- Modify: `dashboard/src/api/client.ts`
- Create: `dashboard/src/components/DailyReviewLiteWorkspace.tsx`
- Modify: `dashboard/src/components/AppShell.tsx`
- Modify: `dashboard/src/styles.css`
- Test: `dashboard/tests/daily-review-lite-workspace.test.tsx`
- Test: `dashboard/tests/app-shell.test.tsx`

- [x] Write failing tests for independent navigation and fixed Daily Review sections.
- [x] Implement API client/types and workspace UI.
- [x] Add AppShell nav item after Review Queue.
- [x] Verify Vitest and build pass.

### Task 3: Browser Verification

**Files:** none

- [x] Open `http://127.0.0.1:5174`.
- [x] Click `每日复盘`.
- [x] Verify the page renders the Daily Review Lite sections and date picker.
