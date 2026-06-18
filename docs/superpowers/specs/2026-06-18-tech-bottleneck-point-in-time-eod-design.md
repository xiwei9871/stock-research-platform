# Tech Bottleneck Point-In-Time EOD Design

## Goal

Upgrade Tech Bottleneck from a fixed candidate CSV workflow to a formal EOD strategy chain that is as trustworthy as LHB and Mid Trend.

The strategy must not use a latest-only candidate universe for historical backtests. It must use point-in-time candidate snapshots: for each `trade_date`, the strategy can only see data that would have been available on or before that date.

## Current Problem

The current Tech Bottleneck V1 path reads a fixed candidate file:

`outputs/research/serenity_bottleneck_baseline_st_only_financial_state_20250101_20260605/strict_153_st_only_financial_state_candidates.csv`

That file has candidates up to 2026-06-05. Later Strategy Lab and EOD runs can still update prices and portfolio trades, but they cannot discover new candidates after 2026-06-05. This makes current Tech results semi-live rather than fully formal:

- DB prices are current.
- Portfolio simulation is current.
- Candidate discovery is stale.
- Market exposure is extended from the last file row when needed.

This is not acceptable for a formal active strategy.

## Required Product Behavior

Tech Bottleneck readiness must mean the whole chain is current:

1. Candidate snapshot is available for the platform display date.
2. Candidate snapshot is point-in-time, not latest-only.
3. Bottleneck score and rank are computed for that trade date.
4. The official strategy contract has run against those snapshots.
5. Review Queue and Home only read manifest-backed formal outputs.

If the candidate snapshot latest date is older than the platform display date, Tech Bottleneck is not ready:

- Home must not count Tech in `策略就绪`.
- Review Queue must not show stale Tech candidates as formal review items.
- Strategy Lab may still expose research/backtest output, but it must label the candidate source as stale/non-formal.

## Candidate Snapshot Model

Create a formal daily candidate snapshot dataset, conceptually named:

`tech_bottleneck_daily_candidates`

Each row represents one stock's Tech Bottleneck candidate state for one trading day.

Required columns:

- `trade_date`
- `asset_id`
- `stock_name`
- `first_hit_date`
- `hit_count_as_of_date`
- `primary_chain_id`
- `primary_chain_name`
- `matched_bottleneck_dimensions`
- `financial_as_of_date`
- `technical_as_of_date`
- `data_as_of_date`
- `filter_decision`
- `filter_reason`
- `bottleneck_score`
- `bottleneck_rank`
- `is_top5`
- `engine_version`
- `run_id`

Important invariant:

For every row:

- `first_hit_date <= trade_date`
- `financial_as_of_date <= trade_date`
- `technical_as_of_date <= trade_date`
- `data_as_of_date <= trade_date`

The table is a point-in-time history. It is not a list of candidates known today.

## Daily Update Semantics

Daily EOD should incrementally update the latest available trading day.

Example:

If the latest available trading day is 2026-06-17, the daily job writes candidate rows where:

`trade_date = 2026-06-17`

Those rows represent what Tech Bottleneck could know as of the 2026-06-17 close.

The daily job should be idempotent. Re-running it for the same date replaces or upserts that date's snapshot and reruns the strategy outputs for that date.

## Full Rebuild Semantics

The system must also support a full rebuild mode:

`2025-01-01 -> latest available trading day`

Full rebuild is used for:

- First migration from the fixed CSV path.
- Data backfills.
- Strategy definition or filter bug fixes.
- Periodic audit.

Full rebuild must produce the same schema as daily update, just for all trading dates in the requested range.

Strategy Lab historical backtests should read this point-in-time dataset by date range. They must not use a latest-only candidate list.

## Candidate Definition

For the first implementation, keep the existing `strict_153_st_only_financial_state` candidate definition and filtering logic.

Do not optimize the candidate definition unless an implementation audit finds an obvious bug. The current business change is data freshness and point-in-time correctness, not alpha redesign.

The implementation should separate:

- candidate generation
- score/rank calculation
- portfolio simulation
- manifest publication

This makes later alpha changes reviewable without changing EOD plumbing.

## Official Strategy Contract

The formal Tech Bottleneck contract remains:

- universe: `strict_153_st_only_financial_state`
- top_n: `5`
- frequency: `biweekly`
- protection: `rank_exit_top10_1d`
- transaction_cost_bps: `20`
- adjust_type: `hfq`

The strategy simulation uses:

1. point-in-time daily candidates
2. DB daily prices
3. current formal market exposure series
4. official contract parameters

Outputs:

- equity rows
- position rows
- trade rows
- review rows
- manifest module `strategy_tech_bottleneck`

## Data Flow

Daily EOD flow:

1. Load DB base data through the latest available trading day.
2. Build or upsert `tech_bottleneck_daily_candidates` for that date.
3. Compute `bottleneck_score` and `bottleneck_rank` for that date.
4. Run Tech Bottleneck official strategy contract.
5. Write formal strategy artifacts under `outputs/research/strategy_daily_eod/<trade_date>/`.
6. Write manifest metadata including:
   - candidate snapshot latest date
   - candidate row count
   - strategy summary
   - contract identity
   - artifact paths
7. Frontend reads only manifest-backed formal artifacts for Home and Review Queue.

Historical Strategy Lab flow:

1. User selects a date range.
2. Backtest loader reads `tech_bottleneck_daily_candidates` for that date range.
3. Loader reads DB prices for the same range.
4. Simulation uses only rows whose `trade_date` is inside the selected window.
5. Result labels the source as point-in-time formal candidate snapshots.

## Freshness And Trust Rules

Tech is formal-ready only when:

- latest candidate snapshot date equals the display trade date
- latest strategy manifest date equals the display trade date
- strategy summary passes the official contract validator
- position/trade/equity artifacts are present

Tech is not formal-ready when:

- candidate snapshot latest date is older than display date
- strategy run used fixed CSV candidates
- contract metadata is missing or mismatched
- manifest artifacts are missing

## Migration Plan

Initial migration should:

1. Build the point-in-time candidate snapshot from 2025-01-01 to the latest available trading day.
2. Compare the 2026-06-05 snapshot against the old fixed candidate file.
3. Document major differences.
4. Switch Tech V1 official runs to the new snapshot source.
5. Mark the old fixed CSV path as research-only.

The old CSV can remain available for audit and research comparison, but it must not be counted as formal EOD readiness.

## Testing Requirements

Tests must cover:

- Snapshot rows reject future-dated inputs.
- Daily update writes only the selected trade date.
- Full rebuild writes all requested trading dates.
- Historical backtest does not read future snapshots.
- Tech readiness fails when candidate snapshot is stale.
- Review Queue ignores stale Tech outputs.
- Official contract metadata is present in manifest.
- Strategy Lab labels point-in-time candidate source correctly.

## Open Implementation Detail

The storage target can be a DB table or a parquet/csv artifact in the first implementation. The required behavior is more important than the storage engine:

- append/upsert by `trade_date`
- fast range reads
- manifest-visible freshness
- no latest-only universe for historical backtests

If DB schema changes are straightforward, prefer a DB table. If migration speed matters, start with parquet/csv snapshots and add DB storage later.
