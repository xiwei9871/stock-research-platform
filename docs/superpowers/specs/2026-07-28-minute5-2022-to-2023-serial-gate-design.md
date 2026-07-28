# 2022-to-2023 Minute5 Serial Gate Design

## Objective

Continue the 2022 full-market 5-minute backfill to verified completion, then and only then start the 2023 backfill with one worker. Fetch only raw minute bars from Baostock and derive qfq bars locally from the stored adjustment factors.

## Scope

- Covered: 2022 and 2023 full-year `5min` jobs for `raw` and `qfq` in `market.minute_bar_backfill_job`.
- Covered: strict transition gate, process sequencing, quota-aware raw fetches, local qfq derivation, fatal Baostock error handling, logging, and restart safety.
- Excluded: direct Baostock qfq requests, parallel workers, schema changes, historical years other than 2022 and 2023, and unrelated backfill pipelines.

## Current State

- 2022 is actively finishing the recovered raw jobs with `workers=1` and `derive_qfq_from_raw=True`.
- 2023 jobs already exist: 62,508 raw jobs and 62,508 qfq jobs, all initially pending.
- A previous run demonstrated that Baostock error `10001011` can affect many jobs if the runner continues after the account becomes blacklisted.

## Strict 2022 Completion Gate

The transition to 2023 is allowed only when all of the following are true for `2022-01-01..2022-12-31`, `freq=5min`:

1. Raw summary:
   - `total_jobs = 62508`
   - `success_jobs = 62508`
   - `pending_jobs = 0`
   - `running_jobs = 0`
   - `failed_jobs = 0`
   - `skipped_jobs = 0`
2. Qfq summary has the same exact counts.
3. `validate-minute-bars --start-date 2022-01-01 --end-date 2022-12-31 --freq 5min --adjust-types raw,qfq` reports `error_count = 0`.
4. No 2022 minute-backfill process remains active.

If any condition fails, the gate remains closed and 2023 must not start.

## 2023 Start Behavior

After the 2022 gate passes:

1. Verify Baostock login succeeds before claiming 2023 work.
2. Start 2023 with `workers=1`.
3. Claim only `raw` jobs for `2023-01-01..2023-12-31`.
4. Derive each corresponding qfq job locally using `market.adjustment_factor.qfq_factor` after the raw job succeeds.
5. Respect the Baostock daily request ledger and use bounded batches rather than one unbounded multi-day allocation.
6. Preserve restartability through the existing job table and quota ledger.

## Error Handling

- Treat `10001011` as a fatal run-level condition. Stop the active batch and do not claim more jobs.
- Do not convert a fatal account condition into hundreds of independent skipped jobs.
- Network receive errors and timeouts may be retried only within the existing bounded retry policy.
- If a batch exits with pending, failed, skipped, or stale running jobs, do not bypass the 2022 completion gate or claim 2023 work prematurely.
- Never fall back to direct qfq fetching.

## Observability

The supervisor log must record:

- 2022 raw/qfq summaries used by the gate.
- 2022 validation summary and error count.
- The exact timestamp at which the 2022 gate opens.
- Baostock login probe result before 2023 starts.
- 2023 batch start/end, attempted jobs, successes, failures, rows, and quota consumption.
- The reason for every stop or blocked transition.

## Acceptance Criteria

- 2023 cannot be observed running while any 2022 gate condition is false.
- 2022 raw and qfq both reach 62,508 successful jobs with no remaining non-success states.
- 2022 validation reports zero errors before 2023 starts.
- The first 2023 process uses one worker, requests raw only, and derives qfq locally.
- A `10001011` response stops the batch without continuing through the remaining claimed workload.
- Restarting the supervisor is idempotent and does not create duplicate concurrent backfill processes.
