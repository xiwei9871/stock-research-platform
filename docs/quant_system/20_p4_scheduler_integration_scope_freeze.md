# P4 Scheduler Integration Scope Freeze

Date: 2026-05-29

## Status

P4 scope is frozen around **Scheduler Integration + Operational Repeatability**.

P4 starts after:

- P3 completion review:
  - `docs/quant_system/19_p3_completion_review.md`
- P3 read-model scope:
  - `docs/quant_system/18_p3_scope_freeze.md`
- P2 daily runbook and operational smoke:
  - `docs/quant_system/17_p2_daily_runbook_and_smoke_report.md`

## Why This Scope

P3 made review artifacts queryable:

1. P2 aggregate review artifacts can be imported into `ops` read models.
2. Virtual portfolio review artifacts can be imported into `simulation` read models.
3. Operator-ready JSON/CSV exports can be generated from durable read models.

The next bottleneck is repeatability. Operators should not need to remember the
exact manual sequence after every daily run. P4 therefore connects the existing
commands into one scheduler-safe orchestration path before building any dashboard.

## P4 In Scope

### P4-1 Daily P3 Orchestration Command

Goal: provide one command that imports P3 read models and writes operator exports
for a trade-date window.

Deliver:

- CLI command for daily P3 orchestration.
- Parameters for trade date, artifact roots, output directory, and service.
- Calls existing P3 importers and operator export instead of duplicating parser
  logic.
- Emits machine-readable summary lines for runbooks and smoke checks.
- Tests for command parsing, happy path summary, missing artifact behavior, and
  failure propagation.

Boundary:

- No scheduler daemon in this task.
- No new database tables unless existing `ops.daily_job_run` cannot capture the
  run evidence.
- Do not mutate generated P2 artifacts.

Implementation status: implemented and ready for review.

Delivered:

- `stock_research.p4.scheduler.run_daily_orchestration`
- `stock_research.p4.scheduler.format_daily_orchestration_lines`
- CLI command:
  - `p4-daily-orchestration`
- Module tests:
  - `tests/test_p4_scheduler.py`
- CLI tests:
  - `tests/test_factor_cli.py -k p4_daily_orchestration`

### P4-2 Read Model Freshness Smoke

Goal: verify that the scheduled/imported read models are fresh enough for operator
use.

Deliver:

- Smoke check for latest `ops.p2_review_run` by trade date.
- Smoke check for latest `simulation.virtual_portfolio_state_daily` by portfolio.
- Smoke check for P3 operator export row counts and file existence.
- CLI output that distinguishes pass, warning, and blocked states.
- Tests for stale data, missing rows, missing export files, and successful smoke.

Boundary:

- This is a read-only verification command.
- Do not infer market data freshness from read-model freshness.
- Do not page or notify directly; return structured output that a later notifier
  can consume.

Implementation status: implemented and ready for review.

Delivered:

- `stock_research.p4.scheduler.check_read_model_freshness`
- `stock_research.p4.scheduler.format_read_model_freshness_lines`
- CLI command:
  - `p4-read-model-smoke`
- Freshness checks:
  - latest `ops.p2_review_run`
  - latest `simulation.virtual_portfolio_state_daily`
  - operator export file existence
  - operator export row counts
- Module tests:
  - `tests/test_p4_scheduler.py`
- CLI tests:
  - `tests/test_factor_cli.py -k p4_read_model_smoke`

### P4-3 Daily Run Recording

Goal: make scheduled P3 operations auditable in the existing operational record.

Deliver:

- Record P3 orchestration step status into the existing daily job run mechanism
  where available.
- Preserve command input parameters, output paths, row counts, and failure reason.
- Tests proving successful and failed runs are recorded with useful metadata.

Boundary:

- Prefer existing `ops.daily_job_run` support.
- Do not create broad scheduler-specific schemas.
- Do not store credentials, webhook URLs, or machine-local secrets.

### P4-4 Scheduler Wrapper And Runbook

Goal: document and package a scheduler-safe command sequence for local operation.

Deliver:

- A daily scheduler wrapper or documented command sequence.
- Launchd/cron guidance if it fits existing project conventions.
- Dry-run mode or no-op verification where possible.
- Runbook covering:
  - prerequisites
  - expected command order
  - success output
  - warning output
  - failure triage
  - rollback/manual rerun steps

Boundary:

- Do not auto-install a scheduler entry without explicit operator approval.
- Do not add cloud scheduler, queue, worker, or service deployment.
- Do not send notifications in P4 unless reusing an existing dry-run-safe
  notification path for smoke output only.

## Out Of Scope For P4

- Web dashboard UI.
- Broker adapters.
- Live trading.
- Automatic order placement.
- Real order, execution, account, or cash ledger tables.
- Replacing P2/P3 artifact contracts.
- Rewriting the daily factor, watchlist, agent, report, or simulation pipelines.
- Cloud deployment, queue infrastructure, or multi-worker scheduling.

## Execution Order

1. P4-0: confirm workspace state and preserve P3 verification evidence.
2. P4-1: add daily P3 orchestration command.
3. P4-2: add read-model freshness and export smoke checks.
4. P4-3: add daily run recording for P3 orchestration.
5. P4-4: write scheduler wrapper/runbook.
6. P4 review: decide whether P5 should be dashboard UI or notification hardening.

## Acceptance Criteria

P4 is ready for review when:

- One command can run the P3 import/export path for a trade-date window.
- The command is idempotent when run repeatedly for the same artifacts.
- Freshness smoke can detect missing, stale, and successful read-model states.
- Operator export files are verified after orchestration.
- Daily run evidence is recorded or explicitly reported as unavailable.
- Scheduler instructions are documented without auto-installing anything.
- No trading automation or broker integration is introduced.
- `.venv/bin/pytest -q` passes.

## Safety Rules

- Scheduler integration must remain review-only.
- Every trading-adjacent output must keep manual review semantics.
- Every generated operator output must preserve source artifact paths where
  applicable.
- No credential, token, webhook URL, broker account, order payload, or local secret
  may be persisted.
- Scheduler installation must remain a manual operator step unless separately
  approved.
- Dashboard work remains out of scope until scheduler freshness is repeatable.

## First Implementation Target

Start with P4-1 and P4-2 together:

- add one orchestration command that wires existing P3 import/export functions
- add smoke checks that prove the read models and exports are current
- keep the implementation read-only except for existing import/upsert paths and
  optional daily run evidence

This is the narrowest useful slice because it turns the P3 manual workflow into a
repeatable operational unit while leaving scheduler installation and UI decisions
for later tasks.
