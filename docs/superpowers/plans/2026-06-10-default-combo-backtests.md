# Default Combo Backtests Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Backtest Lab run the three validated default combo schemes for LHB Shortline, Mid Trend, and Tech Bottleneck.

**Architecture:** Keep the existing vectorized TopN path for manual and position-control baselines. Add a read-only artifact replay path for validated combo strategies so API results align with CLI research evidence while preserving the same BacktestRunResult shape for the dashboard and comparison table.

**Tech Stack:** Python dashboard API, pandas CSV replay artifacts, React Backtest Lab UI, pytest, Vitest, Playwright.

---

### Task 1: Backend Combo Replay Adapters

**Files:**
- Modify: `src/stock_research/dashboard/strategy_backtest_adapters.py`
- Modify: `src/stock_research/dashboard/backtests.py`
- Test: `tests/test_strategy_backtest_adapters.py`
- Test: `tests/test_dashboard_backtests.py`

- [ ] Add failing tests that require `lhb_shortline`, `mid_trend`, and `tech_bottleneck` to expose validated combo replay metadata and return read-only replay payloads.
- [ ] Implement combo replay helpers that load configured summary/equity/position/trade artifacts, filter the selected variant/profile, normalize columns to the dashboard contract, and add `combo_scheme` / `evidence_source` summary fields.
- [ ] Update `run_backtest` to call `run_replay` when an adapter supports it; otherwise keep the vectorized TopN path.
- [ ] Run backend tests for adapters and backtests.

### Task 2: Catalog And UI Copy

**Files:**
- Modify: `src/stock_research/dashboard/strategy_catalog.py`
- Modify: `dashboard/src/components/BacktestLabWorkspace.tsx`
- Test: `tests/test_dashboard_strategy_catalog.py`
- Test: `dashboard/tests/backtest-lab-workspace.test.tsx`

- [ ] Add failing tests that assert the three default strategies describe their combo layers and evidence artifacts.
- [ ] Update catalog names/descriptions/defaults so Backtest Lab presents LHB/Mid/Tech as combo schemes, not simple factor branches.
- [ ] Ensure Backtest Lab summary/details render `combo_scheme` and evidence fields returned by the API.
- [ ] Run catalog and Backtest Lab component tests.

### Task 3: Full Verification

**Files:**
- Test: `tests/test_dashboard_backtests.py`
- Test: `tests/test_strategy_backtest_adapters.py`
- Test: `dashboard/tests/backtest-lab-workspace.test.tsx`
- Test: `dashboard/tests/platform-full-flow.spec.ts`

- [ ] Run focused backend tests.
- [ ] Run focused frontend tests.
- [ ] Run dashboard build and Playwright full flow if focused tests pass.
- [ ] Report the exact URL and any remaining caveats about replay artifacts versus live database recomputation.
