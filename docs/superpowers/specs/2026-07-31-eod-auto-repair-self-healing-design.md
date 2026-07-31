# EOD Auto Repair Self-Healing Design

## Context

The 2026-07-30 EOD repair run exposed three independent failure modes:

1. The scheduled `scripts/run_platform_ready_check_cron.sh` invoked
   `stock_research.eod_auto_repair` with `--mode repair`, so the existing
   multi-cycle loop was not used by the production entrypoint.
2. The strategy publisher rejected a valid safety-filtered LHB review set with
   four distinct rows because a later contract required exactly five rows for
   every strategy. The LHB review tests already define four rows as an
   intentional result of safety filtering.
3. The legacy strategy EOD writer did not populate the existing database column
   `ops.strategy_daily_eod_status.midtrend_artifacts_status`, which is `NOT
   NULL` on the running database.

The system also had no durable unresolved-trade-date queue. Once a newer market
date became current, a failed older date was no longer selected by the
scheduled repair wrapper.

## Goal

Make unattended EOD repair able to recover publishable dates across repeated
runs, while preserving safety filters, making degraded output explicit, and
keeping schema and code contracts aligned.

## Non-goals

- Do not refill an unsafe LHB candidate merely to reach five rows.
- Do not redesign the underlying strategy engines or data pipelines.
- Do not make optional reports or evidence artifacts hard blockers.
- Do not add a new database queue table; the repair queue is a small atomic JSON
  state file under the existing output root.
- Do not change the behavior of a manual single-date invocation unless the
  caller explicitly enables pending-date processing.

## Approaches considered

### A. Only switch the cron wrapper to loop mode

This fixes the dead loop path but leaves the LHB contract failure, schema drift,
and old failed dates unresolved. It is insufficient.

### B. Store unresolved dates in PostgreSQL

This provides strong concurrency and queryability, but adds a migration and a
new operational dependency to a repair path that already has filesystem
reports. It is unnecessary for the small number of dates involved.

### C. Shared publication contract plus an atomic filesystem queue (recommended)

Keep the existing loop, make its scheduled entrypoint use it, define a
strategy-specific review contract, and persist unresolved dates in
`outputs/research/eod_auto_repair/pending_dates.json`. The queue is bootstrapped
from recent failed run summaries, updated after every batch item, and retried in
oldest-first order before the current date. This directly addresses the
observed failure chain with limited surface area.

## Design

### 1. Strategy review contract

The publisher will validate counts per strategy rather than applying one exact
count to all strategies:

| Strategy | Valid rows | Degraded condition | Blocking conditions |
|---|---:|---|---|
| `lhb_shortline` | 1–5 distinct rows, with row count equal to unique count | 1–4 rows: publish and emit a warning | zero rows, duplicate assets, or more than five rows |
| `mid_trend` | exactly 5 distinct rows | none | any other count or duplicate assets |
| `tech_bottleneck` | exactly 5 distinct rows | none | any other count or duplicate assets |

For LHB rows 1–4, `publish_strategy_eod` writes the review manifest, score
audit, and summary with `publishable=true`, a `degraded_strategies` list, and
an explicit warning. The auto-repair review-queue check returns
`RepairStatus.DEGRADED` without `blocker=true`, so the overall run can exit
successfully with a visible degraded status. Empty or malformed strategy groups
remain blockers.

### 2. Durable pending-date queue

Add a focused queue module responsible for selection and atomic persistence:

- Queue path: `$OUTPUT_ROOT/research/eod_auto_repair/pending_dates.json`.
- A queue record contains `trade_date`, `attempts`, `last_status`,
  `remaining_blockers`, `last_error`, and `updated_at`.
- On the first queued run, scan exact `YYYY-MM-DD` repair directories for the
  previous seven calendar days and import summaries with a failed status or
  remaining blockers. Non-date exploratory directories are ignored.
- Each scheduled invocation selects up to three oldest pending dates, then
  appends the current market date if it is not already selected.
- A date is removed after `success` or `degraded` with no remaining blockers.
  A failed date remains queued with updated diagnostics.
- State is written through a sibling temporary file followed by `replace`, so a
  process interruption cannot leave a partially written JSON document.

The CLI gains an opt-in `--include-pending-dates` mode and a
`--pending-date-limit` argument. It runs each selected date independently,
continues to the next date after a failed date, writes a batch summary, and
returns failure only if at least one selected date still has a blocker. A
normal single-date invocation continues to run exactly one date.

### 3. Scheduled entrypoints

The platform-ready wrapper, which is the actual scheduled OpenClaw command,
will pass:

```text
--mode loop
--max-cycles "$PLATFORM_READY_REPAIR_MAX_CYCLES"
--include-pending-dates
--pending-date-limit "$PLATFORM_READY_PENDING_DATE_LIMIT"
```

The direct EOD repair wrapper will use the same flags so the two entrypoints do
not diverge. Existing heartbeat, timeout, logging, and exit-code behavior is
preserved.

### 4. Strategy status schema compatibility

Update `strategy_daily_eod_store` so schema setup is safe for both new and
existing databases:

- Define `midtrend_artifacts_status` with default `unknown`.
- Add it with `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` for an existing table.
- Include it in status payload construction, upsert columns, and load queries.
- The legacy strategy EOD success and dependency-failure paths both write the
  artifact status explicitly (`success`, `failed`, or `skipped`).
- Keep existing status values accepted by the live database while making the
  create-table definition match the current operational status vocabulary.

### 5. Observability and failure semantics

Reports will distinguish:

- hard blockers that keep a date queued;
- degraded-but-publishable strategy output;
- queue dates selected in the current batch;
- per-date attempt counts and the latest failure message.

The loop remains bounded per date by `max_cycles`; the durable queue provides
cross-day retry rather than an unbounded inner loop. A deterministic blocker is
therefore retried on later runs with a clear accumulated record instead of
silently disappearing when the market date advances.

## Testing strategy

Add regression coverage before production changes for:

1. LHB four-row publication succeeds with a degraded warning; zero, duplicate,
   and over-limit rows still fail.
2. Review-queue checks classify LHB 1–4 as degraded and malformed groups as
   blockers.
3. The platform-ready wrapper passes loop and pending-date flags; the direct
   wrapper remains aligned.
4. Queue bootstrap, oldest-first selection, deduplication, removal after a
   blocker-free degraded result, and atomic persistence.
5. The legacy strategy status payload contains
   `midtrend_artifacts_status`, and the schema SQL contains the compatibility
   migration.
6. A batch continues after one failed date, records that date as pending, and
   returns a failed aggregate status when any blocker remains.

The final verification will run the focused unit/script suites and a read-only
replay of the 2026-07-30 report inputs. A live repair is only run after the
focused tests establish the contract changes.

## Acceptance criteria

- The scheduled wrapper invokes loop mode.
- A four-row safe LHB result no longer aborts the whole strategy publication.
- The 7/30 schema error is no longer produced by the legacy status writer.
- Failed dates remain visible in `pending_dates.json` and are retried on later
  scheduled runs.
- A publishable degraded date exits with code 0; a date with hard blockers stays
  queued and exits with code 2.
- Existing user modifications outside this scope remain untouched.
