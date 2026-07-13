# Minute5 Resumable Long-Run Ingest Design

**Date:** 2026-07-10

**Status:** Approved direction; awaiting written-spec review

## Goal

Make the daily BaoStock 5-minute bar ingest a recoverable long-running job instead of a fragile all-or-nothing cron command. The job must keep OpenClaw informed while it runs, fetch only the current trade date, reuse one BaoStock session, resume from persisted raw coverage after interruption, derive qfq locally, and leave truthful terminal job state for downstream readiness checks.

## Current Failure Pattern

The current pipeline combines several behaviors that make daily alerts unreliable:

1. `run_daily_close_pipeline_cron.sh` redirects the Python process stdout and stderr entirely into a detail log. OpenClaw therefore observes no command output until the Python process exits.
2. The OpenClaw command job has `noOutputTimeoutSeconds=1200`, so it sends `SIGTERM` after twenty minutes even though the detail log is receiving progress.
3. The daily stage requests a multi-day lookback for every expected symbol. This multiplies BaoStock response volume and database writes even though the daily job only needs the target trade date.
4. The logical single-worker path still wraps requests in per-call thread executors. A timed-out thread cannot be forcibly stopped and can continue using BaoStock's process-global socket while a retry relogs the same session.
5. The stage does not establish one explicit BaoStock login before the source loop. The first request may begin with `you don't login`, and transient network errors cause repeated logout/login cycles.
6. A killed process can leave `ops.daily_pipeline_job` source rows in `running`. Automatic retries start from the full universe and downstream jobs can treat the stale operational state as a blocker even after data repair succeeds.

Recent database evidence shows that raw and qfq coverage eventually reached 5,191 assets for 2026-07-06 through 2026-07-09, while the scheduled command still reported errors. The design therefore separates data quality from orchestration state and makes both truthful.

## Non-Goals

- Do not parallelize BaoStock SH/SZ requests.
- Do not use the daily path for historical minute backfill.
- Do not replace BaoStock as the authoritative current-day raw source.
- Do not add a second remote source to hide BaoStock failures.
- Do not refactor unrelated daily-bar, dashboard, factor, or strategy code.

## Architecture

### 1. Current-Day Raw Fetch Only

The daily minute5 stage always calls the source with:

```text
start_date = trade_date
end_date = trade_date
freq = 5min
adjust_type = raw
```

`MINUTE5_LOOKBACK_DAYS` no longer expands the daily request range. Historical repair and backfill commands retain their own explicit ranges.

The expected universe remains the active SH/SZ universe for the target trading day. Raw completeness requires a persisted row set with morning and afternoon coverage and at least the existing minimum bar-count threshold.

### 2. One Synchronous BaoStock Session

The stage owns one explicit session lifecycle:

```text
login once
  -> process SH symbols serially
  -> process SZ symbols serially
  -> logout in finally
```

The daily fetch adapter calls `query_baostock_minute_rows` synchronously. It does not wrap the query in an outer `ThreadPoolExecutor`. Socket timeout remains the request boundary. Retryable errors use the existing bounded relogin and backoff policy on the same serial control path.

The session lifecycle is injectable in tests so unit tests do not contact BaoStock.

### 3. Database-Backed Resume

Before source work begins, the stage inspects persisted raw quality for the target date.

- Symbols with complete raw coverage are skipped.
- Missing or abnormal symbols form the pending set.
- If no symbols are pending, source fetching is skipped.
- A restarted job recalculates the pending set from the database and never relies on in-memory state from the interrupted run.

Progress checkpoints continue refreshing `ops.daily_pipeline_quality` from persisted rows. Final quality is also calculated from the database, not solely from rows fetched during the current process.

The stage always evaluates qfq derivation after the raw phase. If raw is already complete but qfq is absent or incomplete, qfq derivation still runs from persisted raw rows and daily adjustment factors.

Quality remains explicit by adjustment type:

- `minute5_bar` records persisted raw completeness for compatibility with existing operations.
- `minute5_qfq_bar` records persisted qfq completeness using the same expected universe and session/bar-count checks.

The minute5 stage can report success only when both quality rows pass. A raw pass with a qfq warning or failure is a local-derivation failure, not a successful completed stage.

### 4. Observable Long-Run Wrapper

The shell wrapper starts the Python command as a child process and keeps the detailed combined output in the existing detail log. While the child is alive, the wrapper emits a compact heartbeat to stdout at a configurable interval, defaulting to 300 seconds.

Each heartbeat includes:

```text
daily_close_pipeline|heartbeat|stage=minute5|trade_date=...|elapsed=...|last_progress=...
```

`last_progress` is the most recent compact `progress|minute5_bar` or `minute5|progress` line found in the detail log. If no progress line exists yet, the heartbeat still reports that the process is alive.

The wrapper must:

- emit an immediate start line before waiting;
- clean up the heartbeat process on normal exit, error, `SIGINT`, or `SIGTERM`;
- preserve the Python child's real exit code;
- retain the existing compact final summary and detail-log path;
- avoid streaming the full detail log into OpenClaw.

This keeps output below the configured output cap while ensuring the no-output watchdog never mistakes normal work for a hang.

### 5. Interruption and Job-State Truthfulness

At stage startup, any source rows for the same trade date and stage that are still `running` from an older attempt are marked `failed` with an interruption/stale-attempt error before new rows are set to `running`.

The Python stage installs scoped `SIGTERM` and `SIGINT` handling for the minute5 command path. An interrupt causes the current attempt to:

1. stop accepting new symbols;
2. persist the latest database-derived raw quality checkpoint;
3. mark all source rows still owned by the attempt as `failed` with an `interrupted` summary;
4. log out of BaoStock in `finally`;
5. exit nonzero so OpenClaw records the interruption.

Ordinary exceptions follow the same terminal-state path. Successful or partial completion updates both source rows with finished timestamps and measured counts.

### 6. Downstream Readiness Contract

For minute5, persisted dataset quality is the authoritative completeness signal:

- `minute5_bar=pass` and `minute5_qfq_bar=pass` together supersede stale or historical source-attempt failures for readiness.
- `warning` or `fail` remains a blocker unless an existing documented tolerance explicitly permits degraded readiness.
- A source row that is currently `running` remains operationally visible, but it must not override a later quality `pass` produced by repair.

This contract applies to finalize, platform-ready, strategy EOD, and auto-repair checks without changing unrelated datasets.

### 7. OpenClaw Job Configuration

Keep the command-job model and the existing 17:00 schedule. Update the job to:

- retain a no-output watchdog because the wrapper now emits heartbeats;
- set `noOutputTimeoutSeconds` comfortably above the heartbeat interval;
- increase `timeoutSeconds` from four hours to six hours;
- keep compact output and the existing Feishu delivery target;
- allow a timed-out or interrupted retry to resume from persisted coverage.

Recommended values:

```text
heartbeat interval: 300 seconds
no-output timeout: 1200 seconds
total timeout: 21600 seconds
```

The six-hour limit is a safety boundary, not an expectation that each run should take six hours.

## Data Flow

```text
OpenClaw 17:00 command
  -> cron wrapper emits start
  -> wrapper launches minute5 child and heartbeat loop
  -> stage marks stale running attempts interrupted
  -> stage loads expected universe
  -> stage inspects persisted raw coverage
  -> stage logs into BaoStock once
  -> serially fetches only missing/abnormal symbols for trade_date
  -> each successful symbol is upserted immediately
  -> periodic persisted-quality checkpoints
  -> BaoStock logout
  -> derive qfq from persisted raw
  -> final persisted raw and qfq quality rows
  -> terminal source job states
  -> wrapper emits compact final summary
  -> downstream gates consume quality-first result
```

## Failure Handling

### BaoStock login failure

Use bounded login retries. If login cannot be established, mark source jobs failed, persist current database quality, and exit nonzero. A later retry resumes without refetching already complete symbols.

### Query timeout or transient socket failure

Apply synchronous bounded retry and relogin. Record a symbol-level failure after the retry budget is exhausted, continue to the next symbol, and let final coverage decide `partial_success` versus `failed`.

### Database upsert failure

Stop the stage because fetched data is not safely checkpointed. Mark owned source jobs failed and exit nonzero.

### qfq derivation failure

Raw quality remains recorded, `minute5_qfq_bar` records warning or failure, and the overall minute5 stage cannot report success. Persist a precise derivation error so auto-repair can rerun local derivation without refetching complete raw bars.

### Process interruption or gateway restart

Persist the latest raw quality and terminal interruption state when the process receives a catchable signal. If the process is killed uncatchably, the next startup's stale-running cleanup repairs operational state before resuming from persisted raw rows.

## Testing Strategy

### Python unit tests

Add focused tests proving:

1. daily source calls use only `trade_date` as start and end;
2. one login and one logout wrap the serial source loops;
3. the daily fetch adapter has no outer thread-executor timeout layer;
4. persisted complete symbols are skipped and only missing/abnormal symbols are fetched;
5. a restarted attempt resumes from database coverage;
6. final quality is database-derived and includes rows from previous attempts;
7. qfq derivation runs when raw is already complete;
8. ordinary exceptions and simulated interrupts close source jobs truthfully;
9. paired raw/qfq quality passes supersede stale minute5 source failures in downstream readiness.

### Shell-wrapper tests

Use a stub child command and a short test heartbeat interval to prove:

1. a start line and heartbeat reach stdout before child completion;
2. detailed child output remains in the log;
3. child exit status is preserved;
4. heartbeat cleanup occurs on success, failure, and termination;
5. the final summary includes the detail-log path.

### Integration and operational verification

1. Run focused pytest suites for minute data, daily pipeline, wrapper, finalize, platform readiness, and EOD repair.
2. Run a smoke command with injected/stub source behavior.
3. Run a controlled real target-date attempt and confirm heartbeats appear in OpenClaw before twenty minutes.
4. Interrupt a controlled run, restart it, and prove the second attempt requests only the remaining symbols.
5. Confirm raw and qfq asset counts, first/last bar times, quality state, and terminal job rows in PostgreSQL.
6. Confirm `openclaw cron get` reports the six-hour total timeout and the expected no-output timeout.

## Acceptance Criteria

The work is complete only when all of the following are proven:

- The daily path requests only the target trade date.
- BaoStock runs through one explicit serial session without leaked timeout threads.
- The wrapper emits heartbeats often enough to avoid the 1,200-second no-output timeout.
- Interrupted or retried runs resume from persisted missing/abnormal raw symbols.
- A completed raw dataset can derive or rederive qfq without remote refetch.
- No completed, failed, or interrupted attempt leaves source rows permanently `running`.
- Final raw and qfq minute5 quality is derived from persisted data and stored separately.
- Downstream readiness accepts paired raw/qfq quality passes despite superseded attempt failures.
- The OpenClaw job uses a six-hour total timeout and preserves compact Feishu delivery.
- Focused automated tests pass.
- A controlled runtime verification demonstrates heartbeat visibility and resume behavior.

## Rollback

Code changes are isolated to the minute5 source path, wrapper, readiness interpretation, tests, and the single OpenClaw job. If runtime behavior regresses:

1. restore the previous OpenClaw job timeout values;
2. revert the minute5-specific code commit;
3. retain already persisted raw/qfq rows;
4. run the existing targeted repair path for the affected trade date.

No destructive database migration is required.
