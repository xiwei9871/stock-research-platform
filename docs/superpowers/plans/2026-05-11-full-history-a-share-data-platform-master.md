# Full-History A-Share Data Platform Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a full-history, point-in-time A-share research data platform from the earliest available A-share trading history through the current trading day.

**Architecture:** Implement the platform in phases: audit and orchestration first, raw and normalized data next, point-in-time reference data next, then labels, factors, approvals, scoring, and backtests. Every long-running ingest/backfill task must be resumable, observable, idempotent, and validated by coverage checks before downstream research uses it.

**Tech Stack:** Python, PostgreSQL, psycopg, pandas, pytest, existing `stock-research` CLI, existing `ingest`, `core`, `market`, `finance`, `factor`, `report`, `raw_baostock`, and `raw_akshare` schemas.

---

## Current Baseline

These are the observed gaps as of 2026-05-11:

- `market_daily_bar` starts at `2024-05-27`; full-history daily bars are not loaded.
- `label_snapshot` starts at `2024-05-27`; labels are short-window only.
- `factor.factor_daily` has partial data for only dozens of dates; no date has complete 31-candidate-factor coverage.
- `core.industry_membership` contains a current-style snapshot starting `2026-05-04`; historical point-in-time industry membership is missing.
- `market.industry_daily_bar` has only a few dates; historical sector bars are missing.
- `finance.indicator_quarter`, `finance.income_statement`, and `finance.share_capital_event` have partial history.
- `finance.balance_sheet` and `finance.cash_flow` are empty.
- `factor.factor_approval` has no approved factors.
- Long-running finance ingest has pending/running jobs; stale running-job recovery needs first-class tooling.
- Long-backfill testing edits are preserved separately and must not be mixed into full-history Phase 0 unless explicitly requested.

## Target Data Contract

The platform is usable only when these contracts hold:

- All normalized historical data is traceable to raw payload rows or an upstream source version.
- Every time-varying field is point-in-time: the row used for a trade date must have `effective_date <= trade_date` and, where applicable, `announcement_date <= trade_date`.
- Every batch is idempotent: re-running a completed task updates rows without duplicating rows.
- Every batch is resumable: interrupted tasks can restart from the last successful task.
- Every major dataset has coverage checks: date range, row count, asset count, missing trade dates, missing assets, and source/version.
- Research workflows must not run unless preflight confirms required upstream data coverage.

## Target Historical Range

- Full-history start is the earliest available A-share trading data from the selected source.
- The system must not hard-code `2024-01-01` as the historical start.
- For planning and task defaults, use `1990-12-01` as the broad lower bound, then let source discovery select the first real trading date per exchange and per asset.
- The end date is the latest completed market trading day available in upstream data.

## Phase 0: Stopgap Safety Before More Data Work

**Purpose:** Make sure partial historical backfills do not look complete.

**Tasks:**

- [x] Preserve the current long-backfill testing work outside the Phase 0 working tree.
- [ ] Add a strict factor coverage check that requires each candidate factor to appear on each factor date before preflight reports factor coverage as complete.
- [ ] Add a stale running-job recovery command for `ingest.batch_job`.
- [ ] Document that the current 2024-2026 data is a smoke-test slice, not a research-grade historical base.

**Acceptance:**

- `stock-research research-preflight` distinguishes "some factor rows exist" from "all required candidate factors are covered".
- Interrupted backfills can be resumed without manual SQL.
- Existing tests pass.

## Phase 1: Data Audit And Orchestration Infrastructure

**Purpose:** Build the control plane before loading decades of data.

**New or modified components:**

- `src/stock_research/data_audit.py`: dataset coverage checks.
- `src/stock_research/backfill_runs.py`: run/task persistence helpers.
- `src/stock_research/cli.py`: `data-audit`, `create-backfill-run`, `run-backfill-tasks`, `backfill-status`, `reset-stale-backfill-tasks`.
- `src/stock_research/schema.py`: `ingest.backfill_run`, `ingest.backfill_task`, optional dataset coverage summary table.
- `tests/test_data_audit.py`, `tests/test_backfill_runs.py`, `tests/test_cli.py`.

**Tasks:**

- [ ] Add schema for `ingest.backfill_run` with `run_id`, `dataset`, `start_date`, `end_date`, `status`, `source`, `source_version`, `created_at`, `started_at`, `finished_at`, `error_message`.
- [ ] Add schema for `ingest.backfill_task` with `task_id`, `run_id`, `dataset`, `partition_key`, `start_date`, `end_date`, `status`, `rows_read`, `rows_written`, `attempts`, `started_at`, `finished_at`, `error_message`.
- [ ] Add helper functions to create date-partitioned and asset-partitioned tasks.
- [ ] Add worker loop that claims pending tasks with row locking, writes task progress, and retries failed tasks up to a configured limit.
- [ ] Add stale-running reset based on `started_at` age.
- [ ] Add `data-audit` output in stable pipe-delimited lines, one line per dataset.
- [ ] Add tests for task claiming, stale reset, retry, idempotent task creation, and audit formatting.

**Acceptance:**

- `stock-research data-audit` reports the current gaps without mutating data.
- `stock-research backfill-status --run-id ...` reports pending/running/success/failed counts.
- A killed task can be reset and rerun.

## Phase 2: Trading Calendar And Asset Lifecycle

**Purpose:** Establish the primary date and asset dimensions used by every later module.

**Datasets:**

- `market.trading_calendar`
- `core.asset_master`
- `core.asset_lifecycle_event`

**Tasks:**

- [ ] Add `market.trading_calendar` with `exchange`, `trade_date`, `is_open`, `source`, `source_version`.
- [ ] Backfill Shanghai and Shenzhen trading calendars from the earliest available source date through the latest completed trading day.
- [ ] Add asset lifecycle events: listed, delisted, suspended listing, resumed listing, name change, board change where source provides it.
- [ ] Reconcile `asset_master` and `core.asset_master`; remove the one-row mismatch or explain it with lifecycle data.
- [ ] Add audit checks for missing calendar dates, duplicate assets, list date after first bar, and delist date before last bar.

**Acceptance:**

- The platform can answer "what was the tradable universe on date X?" without reading current-only metadata.
- Calendar coverage starts before the first normalized market bar.

## Phase 3: Full-History Daily Bars And Raw Archive

**Purpose:** Load all available daily OHLCV data for every A-share security.

**Datasets:**

- Raw source payload tables under `raw_baostock`, `raw_akshare`, or another chosen raw schema.
- Normalized `market_daily_bar`.

**Tasks:**

- [ ] Define source priority for daily bars and document it in the runbook.
- [ ] Add raw daily-bar payload persistence before normalization.
- [ ] Implement full-history daily-bar backfill by asset and date partition.
- [ ] Preserve `adjust_type` and source version explicitly.
- [ ] Add reconciliation checks: raw rows vs normalized rows, missing bars for listed assets, duplicate bars, impossible OHLC values, non-positive volume/amount anomalies.
- [ ] Add incremental daily update using the same normalization path as historical backfill.

**Acceptance:**

- `market_daily_bar` covers the earliest available A-share history through the latest completed trading day.
- Re-running the same backfill does not duplicate rows.
- Audit reports missing bars by exchange/date and by asset.

## Phase 4: Corporate Actions, Adjustment Factors, ST, Suspension, Limits

**Purpose:** Make prices and tradability point-in-time and research-safe.

**Datasets:**

- `market.adjustment_factor`
- `market.corporate_action`
- `core.asset_status_daily`

**Tasks:**

- [ ] Add or verify schema for adjustment factors and corporate actions.
- [ ] Backfill dividend, split, rights issue, and adjustment factor history.
- [ ] Recompute or verify front-adjusted, back-adjusted, and raw price versions.
- [ ] Backfill ST status, suspension status, limit-up/limit-down flags, and tradability flags.
- [ ] Add audit checks comparing adjusted prices against raw price and adjustment factor continuity.

**Acceptance:**

- Backtests can filter suspended, ST, and limit-up/limit-down assets point-in-time.
- Adjusted prices are reproducible from raw prices plus adjustment factors.

## Phase 5: Index Bars And Historical Index Constituents

**Purpose:** Support benchmark returns, index universes, and relative strength research.

**Datasets:**

- `market.index_daily_bar`
- `market.index_constituent`

**Tasks:**

- [ ] Backfill index daily bars from source inception through current date.
- [ ] Add historical index constituents with `start_date`, `end_date`, and weight where source provides it.
- [ ] Add audit checks for constituent gaps and benchmark bar gaps.
- [ ] Update selection/backtest code to use historical constituents when a universe is index-based.

**Acceptance:**

- The system can build CSI300/CSI500/CSI1000-style universes for historical dates without current-member leakage.

## Phase 6: Historical Industry Membership And Sector Bars

**Purpose:** Remove current-industry leakage and enable historical sector factors.

**Datasets:**

- `core.industry_membership`
- `market.industry_daily_bar`

**Tasks:**

- [ ] Select supported industry systems, starting with the one the current code uses (`csrc`) and adding others only when source coverage is clear.
- [ ] Backfill historical industry membership with effective windows.
- [ ] Rebuild `market.industry_daily_bar` from historical membership and `market_daily_bar`.
- [ ] Add checks for assets with no industry on active trading dates.
- [ ] Update sector factor preflight to block when historical industry membership is missing.

**Acceptance:**

- Sector factors for 1990-current use only industry membership effective on the trade date.
- `market.industry_daily_bar` covers every date where both market bars and industry membership exist.

## Phase 7: Full Financial Statements And Point-In-Time Fundamentals

**Purpose:** Complete fundamental data so value/quality factors can be trusted.

**Datasets:**

- `finance.income_statement`
- `finance.balance_sheet`
- `finance.cash_flow`
- `finance.indicator_quarter`
- `finance.share_capital_event`

**Tasks:**

- [ ] Extend finance ingestion to persist balance sheet rows into `finance.balance_sheet`.
- [ ] Extend finance ingestion to persist cash flow rows into `finance.cash_flow`.
- [ ] Verify each financial row has both `report_period` and `announcement_date`.
- [ ] Add point-in-time loaders for latest known financials as of a trade date.
- [ ] Add TTM calculations with strict announcement-date filtering.
- [ ] Add audit checks for missing financial statements by asset/period and inconsistent announcement dates.

**Acceptance:**

- Fundamental factor code can use income, balance sheet, cash flow, indicators, and share capital without future leakage.
- `finance.balance_sheet` and `finance.cash_flow` are no longer empty for covered financial periods.

## Phase 8: Features, Labels, And Candidate Factors Over Full History

**Purpose:** Build the model-ready research layer after base data is complete.

**Datasets:**

- `feature_snapshot`
- `label_snapshot`
- `factor.factor_daily`

**Tasks:**

- [ ] Parameterize feature and label historical starts from actual market coverage, not hard-coded 2024.
- [ ] Generate labels for 5, 10, 20, and 60 trading-day horizons over full history.
- [ ] Backfill all candidate factors over all eligible trading dates with resumable tasks.
- [ ] Make factor completeness checks require every configured candidate factor unless a factor is explicitly marked unavailable for that historical period.
- [ ] Add per-factor availability metadata for factors that legitimately start later due to required lookback or source availability.

**Acceptance:**

- `label_snapshot` covers all dates with enough future bars.
- `factor.factor_daily` has explicit completeness status by date and factor.
- Factor evaluation can use thousands of dates instead of smoke-test windows.

## Phase 9: Factor Evaluation, Approval, Scoring, And Backtests

**Purpose:** Promote only tested factors into scoring and validate strategy behavior over long history.

**Datasets:**

- `factor.factor_eval_run`
- `factor.factor_approval`
- `factor.stock_score_daily`
- `backtest_run`, `backtest_trade`, `backtest_summary`, `backtest_equity_curve`

**Tasks:**

- [ ] Evaluate candidate factors across rolling periods and multiple market regimes.
- [ ] Store approval decisions with thresholds, sample size, and reason.
- [ ] Score only approved factors for production score versions.
- [ ] Backfill approved-only scores over full available history.
- [ ] Run TopN and portfolio backtests over full history with transaction costs and tradability constraints.
- [ ] Add walk-forward validation to avoid selecting factors on the same window used for reporting.

**Acceptance:**

- `factor.factor_approval` contains approved/rejected decisions backed by full-history evaluation.
- Production scores are generated only from approved factors.
- Backtest reports include long-history, subperiod, and regime-split results.

## Phase 10: Daily Incremental Operations

**Purpose:** Keep the full-history platform current after the initial build.

**Tasks:**

- [ ] Define one daily DAG order: raw bars, normalized bars, asset status, index data, industry bars, labels, factors, approvals as needed, scores, reports.
- [ ] Add run recording for every daily job.
- [ ] Add data freshness checks.
- [ ] Add alerting for failed ingest/backfill tasks and stale data.
- [ ] Add runbook commands for recovery after source outage or interrupted jobs.

**Acceptance:**

- The platform can update one new market day without rerunning full history.
- A failed step blocks downstream steps and reports an actionable reason.

## Phase 11: Performance, Storage, And Maintenance

**Purpose:** Make decades of data practical to query and maintain.

**Tasks:**

- [ ] Add indexes for date/asset/factor lookup patterns observed in full-history workloads.
- [ ] Evaluate partitioning for the largest tables: `market_daily_bar`, `label_snapshot`, `factor.factor_daily`, and raw payload tables.
- [ ] Add `VACUUM ANALYZE` guidance after large backfills.
- [ ] Add export snapshots for reproducible research runs.
- [ ] Add backup and restore checks before destructive schema migrations.

**Acceptance:**

- Common preflight, factor evaluation, and backtest queries complete within operationally acceptable time.
- Full-history backfills do not require manual database cleanup after normal retries.

## Execution Order

Execute modules in this order:

1. Phase 0: Safety and strict completeness.
2. Phase 1: Audit and orchestration.
3. Phase 2: Calendar and asset lifecycle.
4. Phase 3: Full-history daily bars.
5. Phase 4: Corporate actions and tradability.
6. Phase 5: Index bars and constituents.
7. Phase 6: Historical industry and sector bars.
8. Phase 7: Full financial statements.
9. Phase 8: Features, labels, and candidate factors.
10. Phase 9: Factor approval, scoring, and backtests.
11. Phase 10: Daily incremental operations.
12. Phase 11: Performance and maintenance.

## Module Planning Rule

Before implementing each phase, write a focused implementation plan under `docs/superpowers/plans/` for that phase only. Each focused plan must include:

- Exact files to create or modify.
- Failing tests first.
- Small commits per task.
- Data audit queries before and after mutation.
- Rollback or resume procedure for interrupted long-running jobs.
- Acceptance commands and expected output.

## Immediate Next Plan

The first executable module should be:

`docs/superpowers/plans/2026-05-11-full-history-phase-0-safety-and-audit.md`

It should cover:

- strict factor completeness;
- stale ingest/backfill task recovery;
- `data-audit` read-only CLI;
- documentation that existing 2024-2026 data is only a smoke-test slice.

Do not start full-history mutation jobs until Phase 0 and Phase 1 are implemented and verified.
