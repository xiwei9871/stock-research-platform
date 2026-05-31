# P10 Experiment Promotion Governance Scope Freeze

Date: 2026-05-31

## Status

P10 scope is frozen around **Experiment Promotion / Feedback Governance**.

P10 starts after:

- P9 decision outcome analytics completion:
  - `docs/quant_system/36_p9_decision_outcome_analytics_completion.md`
- Local P9 completion commit:
  - `f54bc59 docs: complete p9 outcome analytics`

## Why This Scope

P9 made decision outcome analytics repeatable and visible. The next useful loop
is not automatic scoring mutation or watchlist mutation. The next useful loop is
capturing which analytics findings deserve a controlled experiment, why, what
evidence supports them, and whether a human reviewer approves, rejects, or
defers them.

P10 answers governance questions such as:

- Which P9 finding is being proposed as an experiment?
- What hypothesis is being tested?
- Which artifacts support the proposal?
- What validation gates must pass before any downstream implementation?
- Who reviewed the proposal and what decision was made?
- Why was a proposal rejected, deferred, or approved for a later implementation
  phase?

P10 remains governance-only. It creates experiment proposals and review records,
not factor scores, watchlist signals, trades, or scheduler mutations.

## Product Positioning

P10 is an **experiment governance layer** between P9 analytics and any future
implementation work.

The reviewer-facing workflow is:

1. Review P9 outcome analytics.
2. Draft explicit experiment proposals from selected findings.
3. Attach source artifacts and validation expectations.
4. Record human decisions: `approved_for_experiment`, `rejected`, `deferred`,
   or `needs_more_data`.
5. Export/import compact governance read models.
6. Use approved proposals only as inputs to later scoped implementation phases.

P10 does not implement the experiment itself. It does not change scoring,
watchlist logic, trading behavior, or dashboard action surfaces.

## Architecture

P10 builds on P9 analytics artifacts/read models and existing dashboard
infrastructure.

Inputs:

- P9 analytics artifacts.
- `ops.operator_decision_outcome_analytics_run`
- `ops.operator_decision_outcome_analytics_group`
- optional reviewer-authored proposal CSV/JSON inputs.

Outputs:

- local JSON/CSV/Markdown experiment proposal artifacts.
- compact proposal and review-decision read-model rows.
- read-only dashboard summary of proposal status.
- P10 runbook, smoke, and completion review.

Core rule:

- P10 records governance intent only;
- no output is a score update, watchlist signal, trade advice, order, position,
  execution, account state, broker action, or scheduler mutation.

## P10 In Scope

### P10-0 Scope Freeze And Baseline Review

Goal: freeze the P10 boundary before implementation.

Deliver:

- This scope freeze document.
- Baseline review of P9 analytics artifacts, read models, dashboard contracts,
  and existing factor approval mechanisms.
- Confirmation that current non-P10 dirty files are excluded from P10 work.

Acceptance:

- P10 starts from P9 contracts.
- P10 is explicitly governance-only.
- P10 does not reuse existing `factor.factor_approval` as a shortcut for
  watchlist/scoring changes.

### P10-1 Experiment Proposal Contract

Goal: define a structured proposal artifact.

Deliver:

- Proposal schema for:
  - proposal id
  - proposal title
  - hypothesis
  - source P9 analytics run id
  - source analytics group ids or diagnostic rows
  - expected validation method
  - risk notes
  - reviewer id
  - status
  - review-only safety fields
- Tests for valid proposals, missing evidence, invalid statuses, and unsafe
  execution fields.

Candidate statuses:

- `draft`
- `needs_more_data`
- `approved_for_experiment`
- `rejected`
- `deferred`

Boundary:

- Do not create factor score changes.
- Do not create watchlist signal changes.
- Do not treat `approved_for_experiment` as approval for production scoring.

Acceptance:

- Proposal artifacts preserve P9 source artifact references.
- Proposal artifacts keep `manual_review_required = true`.
- Proposal artifacts keep `auto_trade_enabled = false`.

### P10-2 Proposal Artifact CLI

Goal: make proposal creation repeatable from reviewer input.

Deliver:

- CLI command to build proposal artifacts from a CSV/JSON proposal input.
- JSON/CSV/Markdown outputs.
- Tests for normal proposals, missing source evidence, invalid statuses, and
  review-only safety fields.

Candidate command:

```bash
stock-research p10-experiment-proposals \
  --input-csv inputs/p10/proposals_2026-06-30.csv \
  --output-dir outputs/p10/2026-06-30
```

Acceptance:

- Outputs preserve proposal text and source P9 artifacts.
- Outputs are review-only and do not modify scoring/watchlist state.

### P10-3 Proposal Read Model

Goal: make proposal and review decisions queryable.

Deliver:

- Schema for proposal runs.
- Schema for proposal rows.
- Import helper for one artifact or a directory.
- CLI command to import proposal artifacts.
- Tests for idempotent upserts and source artifact preservation.

Candidate tables:

- `ops.operator_experiment_proposal_run`
- `ops.operator_experiment_proposal`

Boundary:

- Store proposal metadata and review decisions only.
- Do not write factor approval rows.
- Do not write watchlist, score, position, order, account, cash, execution, or
  broker tables.

Acceptance:

- Re-importing the same artifact is idempotent.
- Every proposal points back to source P9 analytics evidence.

### P10-4 Dashboard Read-Only Proposal Summary

Goal: show proposal status in the dashboard without edit or promotion controls.

Deliver:

- Read-only API endpoint for proposal summaries by date range/status.
- Dashboard panel for proposal counts and recent proposal decisions.
- Empty/loading/error states.
- Browser smoke coverage if dashboard files change.

Boundary:

- No approve/reject buttons in this P10 dashboard pass.
- No promotion buttons.
- No score/watchlist/trade action buttons.
- No broker or order UI.

Acceptance:

- Dashboard can show proposals for a selected date range.
- Dashboard remains usable when no proposals exist.
- Mobile smoke has no horizontal overflow.

### P10-5 Runbook, Smoke, And Completion Review

Goal: make proposal governance repeatable.

Deliver:

- P10 runbook.
- P10 smoke fixture using synthetic P9 analytics evidence and proposal input.
- P10 completion review.

Acceptance:

- P10 smoke proves proposal artifacts can be created and imported.
- Verification commands and results are recorded.
- Completion review explicitly states that P10 added no scoring mutation,
  watchlist mutation, or trading execution path.

## Out Of Scope For P10

- Broker integration.
- Automatic order placement.
- Real order, execution, account, cash, position, or broker ledger tables.
- Turning proposals into trades.
- Writing factor scores.
- Writing watchlist signals.
- Writing `factor.factor_approval`.
- Changing ranking/scoring logic.
- Changing watchlist generation logic.
- Scheduler automation for proposal promotion.
- Training models from P8/P9/P10 outcomes.
- Using future outcome metrics as historical scoring inputs.
- Fixing unrelated watchlist, factor-pipeline, trend-discovery, or
  strong-winner dirty files currently in the workspace.

## Deferred Beyond P10

Future phases may implement approved experiments, but only under a new scope
freeze. Candidate future scopes:

- P11: experiment execution sandbox / offline replay.
- P12: shadow watchlist experiment read model.
- P13: controlled scoring candidate evaluation.

None of those are part of P10.

## Execution Order

1. P10-0: commit this scope freeze.
2. P10-1: implement proposal contract with focused tests.
3. P10-2: add proposal artifact CLI.
4. P10-3: add proposal read model schema and importer.
5. P10-4: add dashboard read-only proposal summary only after P10-1 through
   P10-3 are stable.
6. P10-5: run smoke, write runbook, and write completion review.

## Review Gates

Before P10-2:

- Proposal fields and statuses must be explicit.
- Unsafe execution fields must be rejected.

Before P10-3:

- Proposal artifacts must be stable enough to import.
- Source P9 evidence references must be preserved.

Before P10-4:

- Proposal read-model import must be idempotent.
- API must remain read-only.

Before P10 completion:

- P10 smoke must prove at least one approved-for-experiment proposal and one
  rejected/deferred proposal can be generated and imported.
- Completion review must record verification evidence and remaining non-P10
  dirty files.
- Completion review must explicitly state that no scoring mutation, watchlist
  mutation, or trading execution path was added.

## Verification Plan

Expected Python verification as P10 progresses:

```bash
.venv/bin/pytest tests/test_operator_experiment_proposals.py tests/test_operator_experiment_proposal_read_model.py tests/test_schema.py tests/test_factor_cli.py -k 'p10 or experiment_proposal' -q
```

If P10-4 changes dashboard files:

```bash
.venv/bin/pytest tests/test_dashboard_app.py tests/test_dashboard_experiment_proposals.py -q
cd dashboard
pnpm test
pnpm build
pnpm test:e2e
```

## Completion Definition

P10 is complete when a reviewer can:

1. Convert P9 findings into explicit experiment proposal artifacts.
2. Preserve P9 source evidence and validation expectations.
3. Import proposals into a compact read model.
4. Inspect proposal status in the dashboard.
5. Run a repeatable smoke proving the proposal artifact and read-model path.
6. Confirm that P10 remains governance-only and introduces no scoring mutation,
   watchlist mutation, or trading execution path.

P10 remains incomplete if proposals only exist as ad hoc notes, or if any P10
output directly changes scoring, watchlist generation, scheduler behavior, or
trading surfaces.
