# Technical Feature Performance Plan

## Current State

- `technical-features` is the current longest-running backfill in the project.
- As of `2026-05-19 19:28 +0800`, the backfill had reached `2007-10-18`.
- Completed coverage was `4119` trading days and `2,650,558` rows.
- Target coverage is `2026-05-14`, which leaves about `4508` distinct trading days remaining.
- The current job is not hung. It runs with `3` workers and each worker is usually CPU-bound.
- Recent watchdog batches process `30` trading days at a time and take roughly `37` to `42` minutes of compute time.
- Wall-clock throughput is lower than compute throughput because runs are launched on a `30` minute external interval.

## Confirmed Bottlenecks

- Database write time is not the primary bottleneck.
- Historical measurements showed:
  - loading lookback bars is about `6` to `8` seconds per day
  - upsert time is negligible relative to compute
  - the dominant time is inside single-day technical feature calculation
- Confirmed hotspots remain:
  - `_wilder_average()` in [technical_features.py](/Users/xiwei/stock_research/src/stock_research/technical_features.py:48)
  - `_rsi()` in [technical_features.py](/Users/xiwei/stock_research/src/stock_research/technical_features.py:83)
  - `_adx()` in [technical_features.py](/Users/xiwei/stock_research/src/stock_research/technical_features.py:159)
  - per-asset `DataFrame` splitting in [technical_feature_store.py](/Users/xiwei/stock_research/src/stock_research/technical_feature_store.py:72)
- `max_drawdown_20d` was already optimized and reduced the measured single-day compute loop from roughly `39.0s` to `20.9s`.

## Stage 1: Low-Risk Changes

This stage intentionally avoids formula changes and schema changes.

- Audit the watchdog launch chain and make the scheduling source explicit.
- Stop silently dropping `run_timeout_seconds` in the technical-feature adapter.
- Thread timeout through the batch execution path so the watchdog can stop scheduling additional work when a batch exceeds its budget.
- Add explicit `sleep_between_runs_seconds` configuration for the watchdog command.
- Emit stable batch metrics in watchdog output:
  - `batch_start_date`
  - `batch_end_date`
  - `batch_size_days`
  - `worker_count`
  - `compute_seconds`
  - `sleep_between_runs_seconds`
  - `rows_written`
  - `days_per_hour`
  - `rows_per_hour`
  - `timed_out`
- Add an offline synthetic benchmark tool for `compute_daily_technical_features()` and the store-style per-asset loop.

## 30-Minute Gap Source

- The observed `30` minute gap is not caused by a hidden Python sleep in `technical_feature_watchdog.py`.
- The current source is the external launchd schedule in [com.stockresearch.technical-feature-backfill-watchdog.plist](/Users/xiwei/stock_research/deploy/launchd/com.stockresearch.technical-feature-backfill-watchdog.plist:31), which uses `StartInterval = 1800`.
- The host wrapper script is [run_technical_feature_backfill_watchdog_host.sh](/Users/xiwei/stock_research/scripts/run_technical_feature_backfill_watchdog_host.sh:1).
- Stage 1 keeps that production cadence unchanged by default and only makes any in-process sleep explicit and configurable.

## Scheduling Tuning

- The next low-risk step is to reduce [launchd](/Users/xiwei/stock_research/deploy/launchd/com.stockresearch.technical-feature-backfill-watchdog.plist:33) `StartInterval` to `300` seconds.
- Setting it to `0` is not recommended because it would allow the job to relaunch immediately and amplify startup churn.
- A host-level lock is required because the batch itself can still run longer than the launch interval.
- The host script should acquire a lock before spawning the CLI and exit early with a clear skip message if another instance is already running.
- Safe rollout:
  - wait for the current batch to finish
  - reload the launchd job with the updated plist and host script
  - confirm the log prints `start_interval_seconds=300`
  - confirm `whether_lock_acquired=true` on the active batch
  - confirm a second trigger logs `skipped because another technical-feature watchdog is running` instead of starting a second batch
- Expected wall-clock gain:
  - batch compute time stays the same
  - the idle gap between batches should shrink from about `30` minutes to about `0` to `5` minutes depending on scheduling overhead
- Watch:
  - `compute_seconds`
  - real inter-batch interval
  - `days/hour`
  - `rows/hour`
  - `skipped because another technical-feature watchdog is running`

## Why Not Just Add More Workers

- The current workers are already CPU-bound.
- The dominant cost is still single-day per-asset technical indicator computation.
- Increasing workers before reducing single-day cost risks higher memory pressure and weaker marginal gains.
- The scheduler interval also limits wall-clock throughput, so worker count alone does not address the full gap.

## Stage 2: Algorithm-Level Optimization Candidates

These changes should only happen after benchmark-driven validation and numerical regression checks.

- Rework `_wilder_average()` to reduce Python-loop overhead.
- Rework `_rsi()` using a numerically equivalent but faster smoothing path.
- Rework `_adx()` so it reuses faster Wilder smoothing and avoids unnecessary intermediate pandas objects.
- Evaluate optional backends:
  - TA-Lib backend where operationally acceptable
  - pandas `ewm`-based equivalent formulations
  - numba-accelerated array kernels

## Fast-Path Regression Status

- A separate fast-path implementation and regression tool now exist for `_wilder_average`, `_rsi`, and `_adx`.
- The fast path is now the default path for `compute_daily_technical_features()`.
- A rollback switch remains available through `STOCK_RESEARCH_TECHNICAL_FEATURE_ENGINE=legacy`.
- Current synthetic regression output shows zero mismatches versus legacy on the tested data.
- Current synthetic benchmark output shows the fast path is materially faster than legacy on the same input shape.
- The next decision gate is to re-run the same comparison on a broader and more adversarial sample before switching any default implementation.
- The default switch is only acceptable when the regression gate remains green across:
  - monotonic rise/fall
  - NaN interior recovery
  - mixed-trend sequences
  - long lookback windows
- Current gate:
  - `max_abs_diff <= 1e-12`
  - `mean_abs_diff <= 1e-12`
  - `nan_mismatch_count == 0`
- If any future regression run fails the gate, switch back immediately with:
  - `STOCK_RESEARCH_TECHNICAL_FEATURE_ENGINE=legacy`

## Stage 3: Batch/Array-Level Optimization Candidates

- Reduce or remove the current per-asset `DataFrame` split.
- Compute over larger array batches instead of thousands of small pandas objects.
- Avoid materializing full per-asset histories when only the target date output is needed.
- Separate bar loading, feature calculation, and final-date extraction more explicitly.

## Safety and Restart Guidance

- Do not kill the currently running production watchdog mid-batch just to pick up these changes.
- First validate the code changes with focused tests and, if needed, one manual dry run against fake or non-production inputs.
- To roll out safely:
  - update the host script and launchd plist on disk
  - wait for the current run boundary or intentionally stop the launchd job between batches
  - restart `com.stockresearch.technical-feature-backfill-watchdog`
  - verify the host log shows the new metrics lines and the explicit sleep parameter

## Acceptance Metrics

- Wall-clock throughput in `days/hour`
- Compute time per batch in `compute_seconds`
- `rows/hour`
- CPU utilization across workers
- Batch error rate and timeout rate
- Numerical consistency versus pre-change technical feature outputs
