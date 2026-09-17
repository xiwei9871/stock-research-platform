# P2 Residual Data Completeness Backfill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:verification-before-completion before reporting completion. Execute each operational step with a read-only scope check and a post-write verification.

**Goal:** Close the remaining P2 data-layer completeness gaps identified by the 2026-08-05 full scan, using 2026-08-03 as the historical cutoff and leaving the current-day/08-04-specific issues out of scope.

**Scope assumption:** P0/P1 data repairs are already complete. The original quant-system P2 artifact/runbook flow is also complete; this plan covers only residual data coverage and backfill work.

**Architecture:** First identify whether each candidate is a true gap or an intentional snapshot/warm-up boundary. Then run the repository's existing backfill/sync commands only for confirmed gaps, recording permission or source limitations as blockers rather than fabricating data.

**Tech Stack:** PostgreSQL (`service=stock_research`), repository CLI commands under `stock_research`, existing factor/technical-feature/index-constituent loaders, and SQL verification queries.

---

## Task 1: Establish the P2 residual-gap baseline

- [x] Inspect schemas, source/calc versions, and date coverage for `factor.factor_daily`, `factor.stock_technical_features_daily`, and `market.index_constituent`.
- [x] Compare each candidate against its intended trading-date universe through 2026-08-03.
- [x] Record intentional warm-up/snapshot boundaries separately from actionable gaps: factor dates before 1991-06-24 are lookback warm-up; factor dates 2016-07-01 through 2022-12-30 were an actionable contiguous gap; monthly index snapshots are the intended cadence.

## Task 2: Repair confirmed index-constituent coverage gaps

- [x] Verify the available sync command, source permissions, and requested date range.
- [x] Run the existing monthly sync for confirmed missing snapshots through 2026-08-03 (`2026-06-30` and `2026-07-31`, 850 rows each).
- [x] Verify date coverage, row counts, duplicate keys, and constituent uniqueness: both snapshots contain 3 indexes / 850 rows and duplicate key count is 0; latest snapshot through the cutoff is 2026-07-31.

## Task 3: Repair confirmed factor-daily gaps

- [x] Determine the factor universe and expected date range from the implementation and current metadata. The actionable gap is 1,583 trading dates from 2016-07-01 through 2022-12-30; earlier dates are the 130-bar warm-up boundary.
- [x] Run the smallest safe existing backfill command for confirmed gaps. A one-day benchmark on 2016-07-01 wrote 107,457 rows; the remaining 1,582 dates are now running in a precise date window with four workers.
- [x] Verify date coverage and calculation-version scope: 1,583/1,583 trading dates are present through 2022-12-30, the CLI reported 236,719,543 rows for the 1,582-date run, and the table primary key protects factor-date duplicates.

## Task 4: Repair residual pre-2025 HFQ technical-feature gaps

- [x] Run the bounded gap check for dates before 2025-01-02 and size the missing workload: 8,312 trading dates have gaps (currently zero HFQ feature rows on those dates).
- [ ] Backfill only confirmed gaps with the existing daily technical-feature command and a bounded lookback.
- [ ] Verify coverage and duplicate keys across the repaired range, including expected warm-up nulls.

## Task 4b: Repair recent turnover-derived feature inputs

- [x] Derive the previously missing turnover rates from historical float-share events for the affected 2026-06-18, 2026-06-24, and 2026-07-01 source dates.
- [x] Add CNInfo share-change records for 14 new-listing assets, fill all three market-bar adjustment types, and rebuild the five affected feature dates (2026-07-16, 07-17, 07-20, 07-21, 07-22). Each date now has all eight P0 feature names.

## Task 4c: Finance residual-source review

- [x] Retry the residual reports through the existing Eastmoney, Sina, and Tushare paths; the targeted 2020+ residual is 22 balance-sheet and 7 cash-flow keys.
- [ ] Populate those keys only when a source returns the exact report period; the current providers omit them, so this remains blocked pending a new authoritative source.

## Task 5: Final P2 verification and handoff

- [ ] Re-run the relevant gap checks and the database audit through 2026-08-03.
- [ ] Confirm no new duplicate keys or out-of-scope writes were introduced.
- [ ] Update this plan with completed items and explicitly list any source-permission or intentional-boundary blockers.
