# P9 Decision Outcome Analytics Scope Freeze

Date: 2026-05-31

## Status

P9 scope is frozen around **Decision Outcome Analytics / Decision Quality
Review**.

P9 starts after:

- P8 decision outcome review completion:
  - `docs/quant_system/33_p8_decision_outcome_review_completion.md`
- Local P8 completion commit:
  - `deedbde docs: complete p8 outcome review`

## Why This Scope

P8 made decision outcomes measurable and queryable. The next useful loop is not
promotion, scoring changes, or trading. The next useful loop is understanding
which decision labels, evidence sources, and review contexts are producing
useful outcomes.

P9 answers review questions such as:

- Did `candidate` decisions show better forward returns than `observe` or
  `caution` decisions?
- Did `caution` decisions avoid downside or simply miss upside?
- Which `source_context` groups produce more complete and useful outcomes?
- Which review sessions have too many insufficient-data records?
- Which evidence paths are missing or weakly represented?
- What should a human reviewer inspect weekly before proposing experiments?

P9 remains research/review-only. It does not modify factor scores, watchlist
signals, trade advice, scheduler state, or any trading execution path.

## Product Positioning

P9 is an **analytics layer** over P8 outcome read models.

The reviewer-facing workflow is:

1. Generate and import P8 outcome rows.
2. Aggregate outcomes by decision label, source context, review session, and
   asset.
3. Produce outcome analytics reports and compact read models.
4. Surface summary analytics in the dashboard as read-only views.
5. Use the analytics to write human review notes and future experiment
   proposals.

P9 does not decide that a label or evidence source should be promoted. Promotion
governance is deferred to P10.

## Architecture

P9 builds on P8 read models and dashboard infrastructure.

Inputs:

- `ops.operator_decision_outcome_run`
- `ops.operator_decision_outcome_event`
- local P8 outcome artifacts for smoke fixtures
- existing dashboard API/frontend

Outputs:

- local JSON/CSV/Markdown analytics artifacts
- compact analytics read-model rows
- read-only dashboard summary endpoints and panels
- P9 runbook, smoke, and completion review

Core rule:

- outcome analytics are diagnostic only;
- no output is a score update, watchlist signal, trade advice, order, position,
  execution, account state, or broker action.

## P9 In Scope

### P9-0 Scope Freeze And Baseline Review

Goal: freeze the P9 boundary before implementation.

Deliver:

- This scope freeze document.
- Baseline review of P8 outcome artifact, read-model, and dashboard contracts.
- Confirmation that current non-P9 dirty files are excluded from P9 work.

Acceptance:

- P9 starts from P8 contracts, not from unrelated watchlist, factor-pipeline, or
  strong-winner dirty files.
- P9 is explicitly review-only.

### P9-1 Outcome Analytics Metric Contract

Goal: define aggregate decision outcome analytics.

Deliver:

- Function contract for aggregating P8 outcome rows.
- Group levels:
  - `decision_label`
  - `source_context`
  - `review_session_id`
  - `asset_id`
- Metrics:
  - sample count
  - complete count
  - insufficient-data count
  - follow-up required rate when available
  - mean forward return by horizon
  - median forward return by horizon
  - win rate by horizon
  - mean max high return by horizon
  - mean max low drawdown by horizon
  - worst drawdown by horizon

Boundary:

- Do not infer real holdings or trades.
- Do not compute portfolio PnL.
- Do not use outcome analytics as a scoring input.
- Do not write factor scores, watchlist signals, trade advice, or scheduler
  state.

Acceptance:

- Empty outcome sets produce explicit empty analytics, not errors.
- Insufficient-data rows are counted and excluded from return statistics.
- Metrics preserve grouping labels and run date range metadata.

### P9-2 Outcome Analytics Artifact CLI

Goal: generate repeatable analytics artifacts from P8 outcome rows.

Deliver:

- CLI command to build an analytics review for a date range or review session.
- JSON/CSV/Markdown outputs.
- Tests for:
  - normal grouped metrics
  - empty outcome set
  - insufficient-data handling
  - review-only safety fields

Candidate command:

```bash
stock-research p9-outcome-analytics \
  --start-date 2026-05-01 \
  --end-date 2026-06-30 \
  --output-dir outputs/p9/2026-06-30
```

Acceptance:

- Outputs include grouped summaries and top/bottom diagnostic rows.
- Artifacts keep `manual_review_required = true`.
- Artifacts keep `auto_trade_enabled = false`.

### P9-3 Outcome Analytics Read Model

Goal: make outcome analytics queryable across date ranges and sessions.

Deliver:

- Schema for analytics runs.
- Schema for grouped analytics rows.
- Import helper for one artifact or a directory.
- CLI command to import analytics artifacts.
- Tests for idempotent upserts and source artifact path preservation.

Candidate tables:

- `ops.operator_decision_outcome_analytics_run`
- `ops.operator_decision_outcome_analytics_group`

Boundary:

- Store compact aggregate metrics only.
- Keep generated artifacts as the audit source.
- Do not create experiment, promotion, score, watchlist, position, order,
  account, cash, or execution tables.

Acceptance:

- Re-importing the same artifact is idempotent.
- Every analytics group points back to an analytics artifact and date range.

### P9-4 Dashboard Read-Only Analytics Summary

Goal: show outcome analytics summaries in the dashboard without write or
execution surfaces.

Deliver:

- Read-only API endpoint for grouped outcome analytics by date range/session.
- Dashboard summary panel for decision-label and source-context analytics.
- Empty/loading/error states.
- Browser smoke coverage if dashboard files change.

Boundary:

- No editing of analytics rows in the dashboard.
- No experiment promotion buttons.
- No trade recommendation buttons.
- No broker or order UI.

Acceptance:

- Dashboard can show grouped analytics for a selected date range.
- Dashboard remains usable when no analytics rows exist.
- Mobile smoke has no horizontal overflow.

### P9-5 Runbook, Smoke, And Completion Review

Goal: make outcome analytics repeatable.

Deliver:

- P9 daily/weekly runbook.
- P9 smoke fixture using P8 synthetic outcome rows.
- P9 completion review.

Acceptance:

- P9 smoke proves P8 outcome rows can produce analytics artifacts and read-model
  rows.
- Verification commands and results are recorded.
- Completion review explicitly states that no scoring mutation or trading
  execution path was added.

## Out Of Scope For P9

- Broker integration.
- Automatic order placement.
- Real order, execution, account, cash, position, or broker ledger tables.
- Turning decision labels into trading instructions.
- Writing factor scores, watchlist signals, trade advice, or scheduler state.
- Promoting evidence sources or labels into scoring logic.
- Training models from P8/P9 outcomes.
- Using future outcome metrics as inputs for historical scoring.
- Fixing unrelated watchlist, factor-pipeline, or strong-winner dirty files
  currently in the workspace.

## Deferred To P10

P10 should cover **Experiment Promotion / Feedback Governance** after P9
analytics are stable.

Candidate P10 scope:

- Convert P9 findings into explicit experiment proposals.
- Track hypotheses, validation artifacts, promotion decisions, and rejection
  reasons.
- Add promotion gates before anything can affect watchlist or scoring logic.
- Keep promotion governance separate from outcome analytics.

## Execution Order

1. P9-0: commit this scope freeze.
2. P9-1: implement outcome analytics metric contract with focused tests.
3. P9-2: add outcome analytics artifact CLI.
4. P9-3: add analytics read model schema and importer.
5. P9-4: add dashboard read-only analytics summary only after P9-1 through
   P9-3 are stable.
6. P9-5: run smoke, write runbook, and write completion review.

## Review Gates

Before P9-2:

- Analytics metric definitions must be explicit.
- Insufficient-data semantics must be tested.

Before P9-3:

- Analytics artifacts must be stable enough to import.
- Source P8 artifact references must be preserved.

Before P9-4:

- Analytics read model import must be idempotent.
- API must remain read-only.

Before P9 completion:

- P9 smoke must prove at least one decision-label group and one source-context
  group can be generated.
- Completion review must record verification evidence and remaining non-P9 dirty
  files.
- Completion review must explicitly state that no scoring mutation or trading
  execution path was added.

## Verification Plan

Expected Python verification as P9 progresses:

```bash
.venv/bin/pytest tests/test_operator_decision_outcome.py tests/test_operator_decision_outcome_read_model.py tests/test_p8_decision_outcome_smoke.py tests/test_schema.py tests/test_factor_cli.py -k 'operator_decision_outcome or p8_decision_outcome or p9_outcome_analytics' -q
```

If P9-4 changes dashboard files:

```bash
.venv/bin/pytest tests/test_dashboard_app.py tests/test_dashboard_outcomes.py -q
cd dashboard
pnpm test
pnpm build
pnpm test:e2e
```

## Completion Definition

P9 is complete when a reviewer can:

1. Generate grouped outcome analytics from P8 outcome rows.
2. Export analytics artifacts with grouped summaries and diagnostics.
3. Import analytics artifacts into a compact read model.
4. Inspect analytics summaries in the dashboard.
5. Run a repeatable smoke proving the artifact and read-model path.
6. Confirm that P9 remains review-only and introduces no scoring mutation or
   trading execution path.

P9 remains incomplete if analytics only exist as ad hoc notebooks/CSVs or if the
dashboard summary encourages promotion/trading actions without a P10 governance
scope.
