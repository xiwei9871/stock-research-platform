# BaoStock 2020 Minute5 Weekend Backfill Design

**Date:** 2026-07-11

**Status:** Approved direction; awaiting written-spec review

## Goal

Use the non-trading-day BaoStock request allowance to complete the remaining 2020 raw 5-minute backfill and derive qfq bars locally without consuming duplicate remote requests.

## Current State

- Scope: 2020-01-01 through 2020-12-31.
- Trading days: 243, from 2020-01-02 through 2020-12-31.
- Expected BaoStock asset-month requests: 44,842 for one adjustment type.
- Raw status: 62,508 planned jobs, 33,840 successful, 28,667 pending, zero failed, zero running.
- QFQ status: 33,840 successful and 28,668 pending.
- Raw progress is complete through 2020-05-29; 2020-06-01 is the current partial trade date.
- Active BaoStock assets used for quota planning: 5,209.
- Non-trading-day theoretical safe request budget: 45,454 requests after the 1.1 safety multiplier.
- The existing dedicated runner conservatively reserves 5,209 requests for one current-day raw pass, leaving an effective backfill budget of 40,245; this still exceeds the 28,667 requested jobs.
- No active minute-backfill process or launchd watchdog was found before planning.

## Execution Strategy

Run the existing dedicated entry point:

```text
scripts/run_baostock_2020_minute5_raw_derive_backfill_today.py
```

with an explicit request target of 28,667. The quota allocator may grant no more than the current safe daily budget and records the reservation in `logs/baostock_minute_request_quota.json`.

The backfill runner will use:

```text
start_date: 2020-01-01
end_date: 2020-12-31
freq: 5min
remote adjust types: raw only
batching: month
workers: 1
sleep: 0.75 seconds per request
retry_failed: true
derive_qfq_from_raw: true
progress interval: 50 jobs
heartbeat interval: 300 seconds
```

Raw jobs are claimed from PostgreSQL before execution. Each successful raw job is persisted and marked successful before its corresponding qfq bars are derived locally. The qfq derivation does not call BaoStock.

## Quota Contract

- The safe daily ceiling remains 45,454 rather than the nominal 50,000.
- The existing runner conservatively applies a 5,209-request current-day reservation even on this weekend run; no code change is introduced solely to reclaim that unused headroom.
- The requested allocation is 28,667, matching the observed remaining raw jobs.
- The ledger finalizer converts only attempted requests into consumed requests and releases unused reservations on normal or exceptional exit.
- If the observed pending count changes between planning and claiming, the runner processes only the jobs actually claimed; unused quota is released.

## Runtime and Observability

The expected runtime is approximately 6–10 hours. The process runs in one synchronous BaoStock worker to avoid shared-session corruption.

Operational output includes:

- budget and allocation records before remote work;
- raw/qfq status before execution;
- progress every 50 attempted jobs;
- a liveness heartbeat every 300 seconds;
- final quota consumption;
- raw/qfq status after execution.

The run output is retained in a timestamped log under `logs/`. The process PID and log path must be recorded when launching so the run can be monitored without relying on the initiating terminal session.

## Interruption and Resume

- Completed jobs remain successful in PostgreSQL and are not reclaimed.
- On interruption, the quota finalizer records attempted requests and releases unused reservation.
- A stale `running` job is reset by the existing backfill runner before the next attempt.
- Restarting the same entry point claims only pending or retryable jobs.
- No destructive cleanup or row deletion is part of this run.

## Validation

Before launch:

1. Re-read raw/qfq summaries and confirm no competing process.
2. Confirm today's ledger has enough unconsumed quota.
3. Run focused quota and minute-backfill tests.

During execution:

1. Confirm the first successful jobs increase both raw and qfq success counts.
2. Confirm failures do not indicate BaoStock quota or blacklist errors.
3. Confirm consumed requests track attempted raw jobs only.

After execution:

1. Raw and qfq pending jobs should be zero or have an exact failure list.
2. No jobs may remain `running`.
3. Raw and qfq database coverage must span all 243 trading days.
4. Covered asset-days must have the expected 5-minute session boundaries and bar counts.
5. The quota ledger must have zero active reservation for the run day.

## Stop Conditions

Stop or interrupt the run if any of these occur:

- BaoStock reports blacklist or daily-limit errors;
- repeated authentication/session failures accumulate;
- database writes fail or jobs stop making progress for more than two heartbeat intervals;
- consumed requests approach the safe daily ceiling unexpectedly;
- another production BaoStock minute process starts and competes for the shared source.

## Acceptance Criteria

- No more than the safe daily BaoStock budget is consumed.
- Only raw bars use remote requests; qfq is derived locally.
- Work is serial, checkpointed, and resumable.
- Progress and quota usage remain observable for the full run.
- The final raw/qfq status and database coverage are explicitly audited.
