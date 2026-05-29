# P8 Decision Outcome Review Scope Freeze

Date: 2026-05-30

## Status

P8 scope is frozen around **Decision Outcome Review**.

P8 starts after:

- P7 operator feedback loop completion review:
  - `docs/quant_system/30_p7_completion_review.md`
- P7 remote sync:
  - `origin/factor-scoring-daily-pipeline` at `7cb1b43`

## Why This Scope

P7 records what the operator decided and which evidence supported the decision.
The next useful loop is measuring what happened afterward.

P8 answers review questions such as:

- Did `candidate` decisions outperform `observe` decisions?
- Did `caution` decisions avoid drawdown?
- Did `remove` decisions correctly identify weak follow-through?
- Were follow-up items resolved or left stale?
- Which evidence sources were most useful after outcomes are known?

P8 remains research/review-only. It does not convert decisions into orders,
positions, account state, or broker instructions.

## Product Positioning

P8 is an **outcome measurement layer** for operator decisions.

The operator-facing workflow is:

1. Record decisions through P7.
2. Wait for enough market data to observe later returns and drawdowns.
3. Compute outcome metrics by decision label, asset, evidence source, and review
   session.
4. Store and export review-only outcome summaries.
5. Surface outcome history in reports or dashboard read-only views.

P8 does not judge whether an operator "should have traded." It measures whether
the recorded review labels were useful research signals.

## Architecture

P8 builds on P7 read models and existing market bars.

Inputs:

- `ops.operator_review_session`
- `ops.operator_decision_event`
- `market_daily_bar`
- optional P7 decision journal artifacts for smoke tests

Outputs:

- local JSON/CSV/Markdown outcome review artifacts
- compact read models for decision outcome runs and per-event metrics
- optional dashboard-ready read-only exports

Core rule:

- outcome metrics are diagnostic only;
- no output is an order, execution, position, cash movement, or broker action.

## P8 In Scope

### P8-0 Scope Freeze And Baseline Review

Goal: freeze the P8 boundary before implementation.

Deliver:

- This scope freeze document.
- Baseline review of P7 decision journal and read-model contracts.
- Confirmation that current non-P8 dirty files are excluded from P8 work.

Acceptance:

- P8 starts from P7 contracts, not from unrelated watchlist or strong-winner
  dirty files.
- P8 is explicitly review-only.

### P8-1 Outcome Metric Contract

Goal: define the per-decision outcome metrics.

Deliver:

- Function contract for joining decision events to future market bars.
- Outcome horizons:
  - `1d`
  - `3d`
  - `5d`
  - `10d`
  - `20d`
  - `60d`
- Metrics:
  - forward close-to-close return by horizon
  - max high return within horizon
  - max low drawdown within horizon
  - outcome status for insufficient future bars
  - follow-up required/resolved flags

Boundary:

- Do not infer real holdings.
- Do not use future outcomes as a scoring input.
- Do not write factor scores, watchlist signals, or trade advice.

Acceptance:

- Missing future bars produce explicit `insufficient_data`, not silent zeros.
- Metrics preserve the original P7 evidence references.

### P8-2 Outcome Review Artifact CLI

Goal: generate outcome review artifacts from P7 decisions and market bars.

Deliver:

- CLI command to build an outcome review for a date range or review session.
- JSON/CSV/Markdown outputs.
- Tests for:
  - normal metrics
  - insufficient future bars
  - empty decision set
  - review-only safety fields

Candidate command:

```bash
stock-research p8-decision-outcome-review \
  --start-date 2026-05-01 \
  --end-date 2026-05-30 \
  --output-dir outputs/p8/2026-05-30
```

Acceptance:

- Outputs include per-event details and grouped summaries.
- Artifacts keep `manual_review_required = true`.
- Artifacts keep `auto_trade_enabled = false`.

### P8-3 Outcome Read Model

Goal: make decision outcomes queryable across sessions and dates.

Deliver:

- Schema for outcome review runs.
- Schema for per-decision outcome metrics.
- Import helper for one artifact or a directory.
- CLI command to import outcome artifacts.
- Tests for idempotent upserts and source artifact path preservation.

Candidate tables:

- `ops.operator_decision_outcome_run`
- `ops.operator_decision_outcome_event`

Boundary:

- Store compact metrics only.
- Keep generated artifacts as the audit source.
- Do not create position, order, account, cash, or execution tables.

Acceptance:

- Re-importing the same artifact is idempotent.
- Every outcome event points back to a P7 decision event or source artifact.

### P8-4 Dashboard Read-Only Outcome View

Goal: show decision outcomes in the dashboard without adding write or execution
surfaces.

Deliver:

- Read-only API endpoint for decision outcomes by asset/date/session.
- Optional dashboard panel for outcome summaries.
- Empty/loading/error states.
- Browser smoke coverage if dashboard files change.

Boundary:

- No editing of outcome rows in the dashboard.
- No trade recommendation buttons.
- No broker or order UI.

Acceptance:

- Dashboard can show outcome history for an asset.
- Dashboard remains usable when no outcome rows exist.
- Mobile smoke has no horizontal overflow.

### P8-5 Runbook, Smoke, And Completion Review

Goal: make outcome review repeatable.

Deliver:

- P8 daily/weekly runbook.
- P8 smoke fixture using P7 decision events and synthetic market bars.
- P8 completion review.

Acceptance:

- P8 smoke proves decision events can produce outcome artifacts and read-model
  rows.
- Verification commands and results are recorded.
- Completion review explicitly states that no trading execution path was added.

## Out Of Scope For P8

- Broker integration.
- Automatic order placement.
- Real order, execution, account, cash, position, or broker ledger tables.
- Turning decision labels into trading instructions.
- Writing factor scores, watchlist signals, trade advice, or scheduler state.
- Training models from P8 outcomes.
- Using future outcome metrics as inputs for historical scoring.
- Fixing unrelated watchlist/strong-winner dirty files currently in the
  workspace.

## Execution Order

1. P8-0: commit this scope freeze.
2. P8-1: implement outcome metric contract with focused tests.
3. P8-2: add outcome review artifact CLI.
4. P8-3: add outcome read model schema and importer.
5. P8-4: add dashboard read-only outcome view only after P8-1 through P8-3 are
   stable.
6. P8-5: run smoke, write runbook, and write completion review.

## Review Gates

Before P8-2:

- Outcome metric definitions must be explicit.
- Insufficient data semantics must be tested.

Before P8-3:

- Outcome artifacts must be stable enough to import.
- Source P7 evidence references must be preserved.

Before P8-4:

- Outcome read model import must be idempotent.
- API must remain read-only.

Before P8 completion:

- P8 smoke must prove at least one `candidate` and one `caution` decision can be
  evaluated.
- Completion review must record verification evidence and remaining non-P8 dirty
  files.

## Verification Plan

Expected Python verification as P8 progresses:

```bash
.venv/bin/pytest tests/test_operator_decision_outcome.py -q
.venv/bin/pytest tests/test_operator_decision_outcome_read_model.py -q
.venv/bin/pytest tests/test_factor_cli.py -k p8_decision_outcome -q
.venv/bin/pytest tests/test_schema.py -q
```

If P8-4 changes dashboard files:

```bash
cd dashboard
pnpm test
pnpm build
pnpm test:e2e
```

## Completion Definition

P8 is complete when an operator can:

1. Compute review-only outcomes for P7 decision events.
2. Export outcome details and summaries as artifacts.
3. Import outcome artifacts into durable read models.
4. Query or view decision outcomes without editing platform state.
5. Run documented smoke and verification commands.

P8 remains incomplete if outcomes only exist as ad hoc CSV calculations or if the
results cannot be tied back to P7 decision events and evidence.
