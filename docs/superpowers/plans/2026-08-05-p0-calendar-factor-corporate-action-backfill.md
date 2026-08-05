# P0 Calendar, Factor, and Corporate-Action Backfill Implementation Plan

> **For agentic workers:** Execute the three database-only tasks in order and verify each checkpoint before continuing.

**Goal:** Fill the historical P0 gaps identified in the 2026-08-04 scan for the trading calendar, adjustment factors, and derived corporate actions through 2026-08-03.

**Architecture:** Use the existing Tushare calendar synchronizer for the missing calendar range. Build adjustment factors from the already synchronized raw/qfq/hfq daily bars with the existing idempotent builder, then derive corporate-action events from the completed factor series. No 2026-08-04 rows are included and no raw/qfq/hfq daily bars are modified.

**Tech Stack:** PostgreSQL service `stock_research`, existing `stock-research` CLI, Tushare calendar adapter, `src/stock_research/corporate_actions.py`.

---

### Task 1: Fill the trading calendar

**Files:**
- Modify: database table `market.trading_calendar`
- Verify: read-only SQL coverage checks

- [ ] Sync Tushare calendar for `2026-05-12` through `2026-08-03` for SH and SZ using source version `tushare_trade_cal_v1`.
- [ ] Verify all daily-bar trade dates in that range have calendar rows for both exchanges.
- [ ] Verify no dates after `2026-08-03` are included in this run.

### Task 2: Fill adjustment factors

**Files:**
- Modify: database table `market.adjustment_factor`
- Reuse: `src/stock_research/corporate_actions.py::build_adjustment_factors`
- Verify: factor row count, date range, asset coverage, and null-factor count

- [ ] Run `build-adjustment-factors --start-date 2026-05-12 --end-date 2026-08-03 --source-version derived_market_daily_bar_v1`.
- [ ] Verify the canonical source version reaches `2026-08-03` and has no null `qfq_factor` or `hfq_factor` rows in the filled range.

### Task 3: Fill derived corporate actions

**Files:**
- Modify: database table `market.corporate_action`
- Reuse: `src/stock_research/corporate_actions.py::build_corporate_actions_from_factors`
- Verify: event date range, source version, and factor-change consistency

- [ ] Run `build-corporate-actions --start-date 2026-05-12 --end-date 2026-08-03 --source-version derived_adjustment_factor_v1 --factor-source-version derived_market_daily_bar_v1`.
- [ ] Verify events are derived only from the canonical factor source and reach the requested end date when factor changes exist.
- [ ] Verify raw daily rows and adjusted daily rows are unchanged by comparing counts and date ranges before/after.

### Final verification

- [ ] Confirm the 28 previously missing calendar dates are present for SH and SZ.
- [ ] Confirm adjustment factors cover the P0 window through `2026-08-03`.
- [ ] Confirm corporate-action derivation completed without errors and has no orphan factor references.
- [ ] Record command output and final counts in the user-facing status report.
