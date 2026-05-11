# Real Data Flow Smoke - 2026-05-10

Purpose: verify the historical factor research loop can run on real PostgreSQL data. This was not an algorithm or strategy validation run.

## Window

- Selected range: `2026-01-28` to `2026-01-30`
- Reason: `label_snapshot` had all required forward-return horizons through `2026-01-30` for `60d`.

## Results

- Factor backfill:
  - Command: `stock-research backfill-factor-daily --start-date 2026-01-28 --end-date 2026-01-30 --lookback-bars 130 --industry-system csrc`
  - Output: `factor_daily_backfill|dates|3`
  - Output: `factor_daily_backfill|rows|433839`
- Coverage preflight:
  - Status: `ok`
  - Factor dates: `3`
  - Label horizons: `5, 10, 20, 60`, each with `3` dates.
- Batch gate:
  - Factors: `alpha101_delta_close_1_rank`, `gtja191_amount_momentum_5_10`, `qlib_ret_5`
  - Result: all rejected with `insufficient_ic_count`, expected for a 3-day smoke window.
- Approved-only scoring:
  - Result: `0` rows for each date, expected because no factor was approved.
- TopN workflow smoke:
  - Used isolated score version: `flow_smoke_v1`
  - Score rows: `10359` across `2026-01-28` and `2026-01-29`
  - Report path: `reports/flow_smoke/flow_smoke_topn_20260128_20260130_2026-01-28_2026-01-30_tearsheet.md`

## Issues Found

- Empty approved factor set caused scoring to raise `KeyError: 'factor_name'`.
  - Fixed in `factor_store.score_and_store_factor_daily` by returning `0` for empty factor input.
  - Added regression test in `tests/test_factor_store.py`.
- Runbook referenced nonexistent factor `qlib_alpha158_ret_5`.
  - Correct factor name is `qlib_ret_5`.
  - Updated runbook and execution plan.

## Next Flow Checks

- Add a first-class CLI command for `research_preflight` so operators do not need `python -c`.
- Add progress output to `backfill-factor-daily`; 3 days took several minutes with no intermediate output.
- Run a longer historical backfill range only after choosing a bounded window that can satisfy `min_ic_count`.

## Interpretation

The `2026-01-28` to `2026-01-30` run was a pipeline smoke test only. It proved that factor backfill, label coverage checks, batch gate persistence, approved-only scoring, and TopN workflow wiring can execute on real PostgreSQL data.

It was not a factor-validity test. A 3-day window is too small for IC, RankIC, quantile return, turnover, or TopN performance conclusions. The historical approved-factor research flow now starts at `2024-01-01` and ends at the latest date covered by all required forward-return horizons.
