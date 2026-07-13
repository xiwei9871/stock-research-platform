# 2026-06-24 Strategy Daily EOD Readiness Design

## Background

The stock research platform currently reaches a data-level ready state based on daily bars, minute bars, dependency jobs, scores, watchlists, and reports. However, the platform also depends on three daily strategy end-of-day outputs:

- `lhb_shortline`
- `mid_trend`
- `tech_bottleneck`

These strategy EOD artifacts have been generated on some prior dates under `outputs/research/strategy_daily_eod/<trade_date>/`, but they are not currently managed as a first-class daily pipeline task, are not clearly scheduled in OpenClaw, and are not enforced by the platform readiness contract.

This creates an operational gap:

- the platform can report `READY` or `DEGRADED_READY` while one or more strategy EOD outputs for the current trade date are missing;
- operators cannot reliably tell whether the strategy layer has actually been published for the day;
- troubleshooting mixes data pipeline state and strategy publish state.

The goal of this design is to make the three strategy EOD outputs a formal daily task with an explicit success contract and to require that contract for platform readiness.

## Goal

Add a dedicated daily `strategy_daily_eod` task that:

- runs every trading day at a fixed time;
- checks upstream dependencies before doing any publish work;
- generates the three required strategy EOD outputs for the current trade date;
- records explicit per-strategy status in a database-backed status table; and
- becomes a hard requirement for platform `READY`.

The strategy logic itself is out of scope. This task only guarantees daily EOD generation for already-defined strategy outputs.

## Non-Goals

- changing the selection logic, ranking logic, or portfolio logic of `lhb_shortline`, `mid_trend`, or `tech_bottleneck`;
- redesigning the existing strategy file schemas beyond adding a stable publish summary contract;
- relaxing current data readiness standards;
- reverse-engineering and preserving any undocumented historical one-off workflow if a clearer formal task can replace it.

## User Requirements Confirmed

- The three strategy definitions are externally owned; daily EOD generation must not depend on changing strategy internals.
- The daily strategy EOD task must be a first-class daily operation.
- Strategy EOD should be fixed-time triggered, not only dependency-triggered.
- Before strategy EOD generation starts, it must check whether upstream dependencies are satisfied.
- If any one of the three strategy EOD outputs does not complete successfully for the current trade date, the platform should be treated as `NOT_READY`.

## Strategy EOD Scope

The task covers exactly three strategy families:

- `lhb_shortline`
- `mid_trend`
- `tech_bottleneck`

For each trade date, strategy EOD generation is considered complete only when all three strategy families have generated their required outputs and the publish summary marks them as successful.

## Proposed Architecture

Introduce a dedicated daily publish task:

- task id: `strategy_daily_eod`
- scheduler surface: OpenClaw cron
- runtime surface: a single dedicated wrapper script, for example `scripts/run_strategy_daily_eod_cron.sh`
- storage surface:
  - output files under `outputs/research/strategy_daily_eod/<trade_date>/`
  - task status in a new database table `ops.strategy_daily_eod_status`

This task is separate from `platform_ready_build`. It should not be treated as a side effect of broader platform build steps.

### Why a Separate Task

Separating strategy EOD from `platform_ready_build` gives clean failure boundaries:

- upstream data tasks can succeed while strategy publish fails;
- strategy publish can be re-run independently;
- readiness checks can distinguish data-layer failures from strategy-layer failures;
- operators can inspect one explicit status row instead of inferring state from missing files.

## Scheduling Design

Add a dedicated OpenClaw cron job:

- name: `stock-strategy-daily-eod`
- timezone: `Asia/Shanghai`
- trigger time: `19:40`

### Rationale

The current daily flow already places:

- daily bar completion after market close;
- minute bar processing in the evening window;
- finalize and readiness-related tasks between roughly `18:30` and `19:55`.

Scheduling strategy EOD at `19:40` provides:

- enough time for normal `daily`, `minute5`, and `deps` completion;
- enough separation from data ingestion to reduce overlap risk;
- enough time before `19:55` final readiness checking for the strategy task to complete or fail explicitly.

The trigger is still fixed-time, per requirement. Dependency checks happen inside the task rather than controlling whether the task is scheduled.

## Dependency Gate

When the task starts, it must check the current trade date and validate three prerequisites:

- `daily_bar` stage status is in `success` or `partial_success`
- `minute5_bar` stage status is in `success` or `partial_success`
- `deps` stage status is `success`

### Dependency Outcomes

If all prerequisites pass:

- the task proceeds to strategy EOD generation.

If any prerequisite fails:

- the task exits with failure;
- it writes `ops.strategy_daily_eod_status.status = failed`;
- it records which dependency failed;
- it does not publish formal strategy EOD outputs for that trade date.

This preserves the fixed-time schedule while ensuring the publish result is explicit and machine-readable.

## Strategy Execution Contract

Within one successful `strategy_daily_eod` run, the task executes the three strategy publish steps in a fixed order:

1. `lhb_shortline`
2. `mid_trend`
3. `tech_bottleneck`

Each strategy step produces strategy-specific outputs and a per-strategy status result.

The overall task is:

- `success` only if all three per-strategy statuses are `success`;
- `failed` if any one strategy fails.

There is no `partial_success` at the strategy EOD task level because the platform contract requires all three.

## File Output Contract

For each trade date, the task writes to:

- `outputs/research/strategy_daily_eod/<trade_date>/`

### Required Strategy Review Files

These files must exist and be non-empty:

- `strategy_lhb_shortline_review.csv`
- `strategy_mid_trend_review.csv`
- `strategy_tech_bottleneck_review.csv`

### Required Extended Artifacts

These files are expected for operator use and downstream platform consumers:

- strategy-specific `positions.csv`
- strategy-specific `trades.csv`
- strategy-specific `equity.csv`
- `review_queue_strategy_manifest.csv`
- `strategy_score_audit_detail.csv`
- `strategy_score_audit_summary.json`
- `strategy_eod_publish_summary.json`

The exact file list may continue to grow, but the three review files plus the summary file are the hard readiness contract.

## Publish Summary Contract

The file:

- `strategy_eod_publish_summary.json`

must exist for every successful run and must include at minimum:

- `trade_date`
- `run_id`
- `output_dir`
- `dependency_check`
- `strategy_status`
  - `lhb_shortline`
  - `mid_trend`
  - `tech_bottleneck`
- `review_rows`
- `status`
- `error_summary`

This file becomes the canonical file-system summary of strategy EOD success for the day.

## Database Status Contract

Add a new table:

- `ops.strategy_daily_eod_status`

Suggested columns:

- `trade_date date primary key`
- `status text not null`
- `dependency_check_status text not null`
- `lhb_shortline_status text not null`
- `mid_trend_status text not null`
- `tech_bottleneck_status text not null`
- `review_rows integer not null default 0`
- `output_dir text`
- `summary_path text`
- `error_summary text`
- `updated_at timestamptz not null default now()`

Allowed `status` values should be intentionally narrow:

- `success`
- `failed`
- `running`
- `skipped`

The task writes this table on every run attempt, including dependency-gate failures.

## Platform Readiness Integration

The `platform_ready` contract must be extended to include strategy EOD as a hard check.

### New Platform Checks

Add a readiness check that validates:

- `ops.strategy_daily_eod_status` exists for the current trade date;
- `status == success`;
- `lhb_shortline_status == success`;
- `mid_trend_status == success`;
- `tech_bottleneck_status == success`;
- `summary_path` exists;
- the three required review CSV files exist and are non-empty.

### Readiness Rule

If any one of the above conditions fails:

- platform readiness is `NOT_READY`

This is stricter than the current external-data gap tolerance rules because the user requirement is explicit: if any one of the three strategy EOD outputs is missing, the platform should not be considered ready.

## Relationship To Existing Ready States

The current platform state machine includes:

- `READY`
- `DEGRADED_READY`
- `NOT_READY`

Under this design:

- external data gaps may still allow `DEGRADED_READY` if they stay within accepted thresholds;
- but strategy EOD failure overrides that and forces `NOT_READY`.

Examples:

- daily/minute5 partial but within accepted tolerance, and all three strategy EOD tasks succeed:
  - final state can still be `DEGRADED_READY`
- daily/minute5 acceptable, but `mid_trend` EOD missing:
  - final state is `NOT_READY`

## Mid-Trend Interpretation Clarification

Recent observations that `mid_trend` appeared to show `CN:SH:601211` (`国泰海通`) across multiple days do not imply the strategy was producing only one name.

Observed behavior indicates:

- `mid_trend` EOD artifacts previously stored a five-name basket;
- the top-ranked name remained `601211` across the observed dates;
- the source basket itself was weekly and could legitimately persist across days;
- today’s real issue was missing current-date EOD publication, not the presence of a single-name strategy output.

This design therefore focuses on daily publication correctness, not on changing `mid_trend` strategy content.

## Failure Handling

### Dependency Failure

- mark task as `failed`
- record unmet dependencies in `error_summary`
- do not publish official strategy files for the day

### Single Strategy Failure

- mark failing strategy status as `failed`
- mark overall task as `failed`
- preserve any already-generated intermediate outputs for debugging
- do not treat the day as platform-ready

### Missing Summary Or Missing Review Files

- treat as task failure even if some intermediate strategy files exist
- readiness contract depends on formal publish outputs, not ad hoc partial files

## Operator Visibility

Operators should be able to answer four questions without reading raw logs:

- did `strategy_daily_eod` run today?
- which dependency, if any, blocked it?
- which of the three strategy outputs failed?
- where are today’s outputs?

The combination of:

- `ops.strategy_daily_eod_status`
- `strategy_eod_publish_summary.json`

must make these answers obvious.

## Testing Requirements

At minimum, tests should cover:

- dependency gate failure when `daily` is missing;
- dependency gate failure when `minute5` is missing;
- dependency gate failure when `deps` is missing;
- successful run with all three strategy outputs present;
- failure when one strategy output generation fails;
- failure when summary file is missing;
- platform readiness returning `NOT_READY` when strategy EOD status is not `success`;
- platform readiness passing strategy checks only when all three review files exist and are non-empty.

## Rollout Plan

Recommended rollout sequence:

1. add `ops.strategy_daily_eod_status` schema;
2. add a dedicated runner and cron wrapper;
3. register the OpenClaw `19:40` cron job;
4. generate `strategy_daily_eod` outputs using the dedicated task;
5. extend `platform_ready` with hard strategy EOD checks;
6. update dashboard and snapshot consumers to display strategy EOD state explicitly.

## Recommended Approach

Use a dedicated first-class `strategy_daily_eod` daily task with:

- fixed-time scheduling;
- internal dependency gating;
- explicit per-strategy status tracking;
- a stable file-system publish contract; and
- a hard readiness dependency in `platform_ready`.

This is the most defensible operational model because it treats strategy EOD publication as a required platform subsystem instead of an incidental side effect.
