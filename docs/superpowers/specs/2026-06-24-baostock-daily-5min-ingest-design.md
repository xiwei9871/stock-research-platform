# Baostock Daily 5min Ingest Design

## 1. Objective

Build a dedicated daily ingest path for Baostock 5-minute bars that starts at `16:30`, only processes the current trading day, and favors stability over throughput.

The system should:

1. run as a single instance;
2. use one Baostock session per run;
3. fetch only today's `5min` data;
4. keep retry pressure low;
5. finish by about `20:00` when conditions are normal, but continue slowly if a few symbols still need cleanup.

This is a daily ingest path, not a historical backfill path.

## 2. Scope

### In scope

- current trading day only;
- `5min` bars only;
- one process, one worker, one session;
- serialized symbol-by-symbol fetch;
- low-frequency retry and cooldown;
- simple run status reporting;
- cron-friendly execution.

### Out of scope

- historical replay;
- month-level job planning;
- parallel workers;
- intraday polling during market hours;
- strategy logic;
- new market schemas.

## 3. Current State

The repository already has Baostock ingestion code in:

- `src/stock_research/minute_data.py`
- `src/stock_research/minute_backfill.py`
- `scripts/run_minute_backfill_monthly.py`

But those paths are optimized for backfill-style work:

- `minute_backfill.py` can fan out to `ProcessPoolExecutor` when `workers > 1`;
- `minute_data.py` already has Baostock login, retry, and upsert helpers;
- existing cron scripts are not tailored to “today only, slow and stable”.

The new design should reuse helpers, but not reuse the backfill control flow.

## 4. Architecture

Add a dedicated daily runner, for example:

- `src/stock_research/minute_daily_ingest.py`
- `scripts/run_baostock_minute_daily.sh`

The runner should expose a single entrypoint such as:

```python
run_baostock_minute_daily(
    trade_date: str | None = None,
    freq: str = "5min",
    sleep_seconds: float = 1.0,
    retry_limit: int = 2,
    cooldown_seconds: int = 600,
)
```

Key properties:

- no `workers` argument;
- no process pool;
- no batch planning table;
- no historical scan;
- no implicit parallelism.

The daily path must not call the month-level job planner, `claim_backfill_jobs`, or stale-job reset logic from the historical backfill controller.

## 5. Execution Flow

### 5.1 Start gate

At startup the runner must:

1. acquire a global lock;
2. resolve the trading day;
3. skip non-trading days cleanly;
4. load the active Baostock symbol universe;
5. open exactly one Baostock session.

The lock prevents overlap with:

- cron overlap;
- manual reruns;
- other Baostock jobs.

Recommended lock implementation:

- lock file: `/tmp/stock_research_baostock_minute_daily.lock`;
- non-blocking acquisition;
- if the lock is already held, exit cleanly and log `skipped_locked`.

### 5.2 Main pass

The main pass should:

1. iterate symbols in a fixed order;
2. query only the selected trade date;
3. write rows immediately after each symbol;
4. sleep between symbols;
5. record `success`, `empty`, or `failed`.

### 5.3 Retry pass

Failed symbols should be retried only in a small retry queue.

Rules:

- retry the current session first;
- only relogin after repeated retryable failures;
- after a burst of failures, enter cooldown before retrying again;
- never restart the full universe just because a few symbols failed.

## 6. Anti-ban Policy

The daily runner must be conservative by default.

Required behavior:

- one login per run unless failure forces relogin;
- serialized requests only;
- `workers=1` equivalent behavior only;
- backoff on retryable Baostock errors;
- cooldown after repeated failures;
- no aggressive relogin loop.

Suggested thresholds:

- per-symbol sleep: about `1.0s`;
- retry attempts before relogin: `2`;
- relogin after consecutive retryable failures: `3`;
- cooldown after repeated failure burst: `10-15 min`.

If the service remains unhealthy, the runner should slow down rather than amplify load.

## 7. Status And Success Criteria

The runner should emit a small status record for each run, including:

- run status: `success`, `partial`, `failed`, `skipped_non_trading_day`, or `skipped_locked`;
- trade date;
- symbol count;
- success count;
- empty count;
- failed count;
- retry count;
- relogin count;
- total rows written;
- last error summary.

Recommended artifacts:

- `outputs/research/baostock_minute_daily/<trade_date>/summary.json`
- `outputs/research/baostock_minute_daily/<trade_date>/failed_symbols.txt`
- append-only local log for the full run transcript

`success` means:

- all target symbols were processed for the current trading day;
- failed count is exactly zero;
- the run completed without overlap.

`partial` means:

- the main pass completed;
- one or more symbols still failed after the retry queue finished;
- the remaining failures were explicitly recorded for later cleanup.

The operational target is to start at `16:30` and usually finish by `20:00`, but the process may continue past that if it is still clearing a small retry queue.

## 8. Testing

The implementation should add tests for:

- single-instance lock behavior;
- current-trade-date-only query window;
- no relogin on the first retryable failure;
- relogin only after the configured repeated-failure threshold;
- cooldown activation after repeated failure bursts;
- retry queue containing only failed symbols from the main pass;
- final run status selection: `success`, `partial`, and skip cases.

## 9. Rollout

Implement in this order:

1. add the dedicated daily runner;
2. wire it to existing Baostock query and upsert helpers;
3. add the global lock;
4. add cron entry at `16:30`;
5. add basic run logging and summary output;
6. validate on one trading day before replacing any manual workflow.

## 10. Non-Goals

This design does not try to:

- make Baostock faster;
- parallelize symbol fetches;
- eliminate all retries;
- repair historical data gaps;
- introduce new research tables.
