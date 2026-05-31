# P11 Experiment Execution Sandbox Scope Freeze

Date: 2026-05-31

## Status

P11 scope is frozen around **Experiment Execution Sandbox / Offline Replay**.

P11 starts after:

- P10 experiment promotion governance completion:
  - `docs/quant_system/39_p10_experiment_promotion_governance_completion.md`
- Local P10 completion commit:
  - `e8a5de1 docs: complete p10 experiment governance`

## Why This Scope

P10 can record which P9 analytics findings deserve a controlled experiment. The
next useful step is not to mutate production scoring or watchlist logic. The next
useful step is to run approved proposals through a repeatable offline sandbox and
produce replay evidence that can be reviewed before any future implementation
scope.

P11 answers execution-sandbox questions such as:

- Which `approved_for_experiment` proposal was replayed?
- What candidate universe and date window were used?
- What historical bars or outcome rows were used as input?
- What metrics were produced?
- Did the replay pass, fail, or require more data?
- Which artifacts prove the replay result?

P11 remains offline and review-only. It creates experiment replay artifacts and
read-model rows, not factor scores, watchlist signals, trades, or scheduler
mutations.

## Product Positioning

P11 is an **offline experiment sandbox** between P10 governance approval and any
future shadow/production implementation work.

The reviewer-facing workflow is:

1. Review P10 proposals.
2. Select proposals with `status = approved_for_experiment`.
3. Run offline replay using explicit historical inputs.
4. Record replay metrics and validation status.
5. Export/import compact replay read models.
6. Use passing replay evidence only as input to later scoped phases.

P11 does not implement the experiment in production. It does not change scoring,
watchlist logic, trading behavior, dashboard action surfaces, or scheduler
automation.

## Architecture

P11 builds on P10 proposal artifacts/read models and existing P8/P9 outcome
data.

Inputs:

- P10 proposal artifacts.
- `ops.operator_experiment_proposal_run`
- `ops.operator_experiment_proposal`
- P9 analytics artifacts/read models.
- optional local replay input CSVs for candidate rows, labels, bars, or outcome
  rows.

Outputs:

- local JSON/CSV/Markdown experiment replay artifacts.
- compact replay run and replay result read-model rows.
- read-only dashboard summary of replay status.
- P11 runbook, smoke, and completion review.

Core rule:

- P11 runs offline replay only;
- no output is a score update, watchlist signal, trade advice, order, position,
  execution, account state, broker action, or scheduler mutation.

## P11 In Scope

### P11-0 Scope Freeze And Baseline Review

Goal: freeze the P11 boundary before implementation.

Deliver:

- This scope freeze document.
- Baseline review of P10 proposal artifacts/read models and P9 outcome
  analytics contracts.
- Confirmation that current non-P11 dirty files are excluded from P11 work.

Acceptance:

- P11 starts from P10 `approved_for_experiment` proposals.
- P11 is explicitly offline and review-only.
- P11 does not write `factor.factor_approval`, factor scores, watchlist signals,
  or scheduler state.

### P11-1 Offline Replay Contract

Goal: define a structured replay artifact for one or more approved proposals.

Deliver:

- Replay schema for:
  - replay run id
  - proposal id
  - source P10 proposal run id
  - source P9 analytics run id
  - replay start/end dates
  - replay input artifact paths
  - validation method
  - replay status
  - sample counts and metric summary
  - failure/defer reasons
  - review-only safety fields
- Tests for valid replay rows, unapproved proposals, missing source evidence,
  invalid statuses, and unsafe execution fields.

Candidate replay statuses:

- `replay_ready`
- `passed_offline_replay`
- `failed_offline_replay`
- `needs_more_data`
- `blocked`

Boundary:

- Do not create factor score changes.
- Do not create watchlist signal changes.
- Do not treat `passed_offline_replay` as production approval.

Acceptance:

- Replay artifacts preserve P10 proposal and P9 analytics references.
- Replay artifacts keep `manual_review_required = true`.
- Replay artifacts keep `auto_trade_enabled = false`.
- Replay artifacts keep `production_write_enabled = false`.

### P11-2 Replay Artifact CLI

Goal: make offline replay artifact creation repeatable.

Deliver:

- CLI command to build replay artifacts from approved proposal input and replay
  metrics input.
- JSON/CSV/Markdown outputs.
- Tests for normal replay, unapproved proposal rejection, missing evidence,
  invalid statuses, and review-only safety fields.

Candidate command:

```bash
stock-research p11-experiment-replay \
  --proposals-json outputs/p10/2026-06-30/operator_experiment_proposals_2026-06-30.json \
  --metrics-csv inputs/p11/replay_metrics_2026-06-30.csv \
  --output-dir outputs/p11/2026-06-30
```

Acceptance:

- Outputs preserve proposal text, P10 artifacts, and source P9 artifacts.
- Outputs are review-only and do not modify scoring/watchlist state.

### P11-3 Replay Read Model

Goal: make replay results queryable.

Deliver:

- Schema for replay runs.
- Schema for replay result rows.
- Import helper for one artifact or a directory.
- CLI command to import replay artifacts.
- Tests for idempotent upserts and source artifact preservation.

Candidate tables:

- `ops.operator_experiment_replay_run`
- `ops.operator_experiment_replay_result`

Boundary:

- Store replay metadata and metrics only.
- Do not write factor approval rows.
- Do not write watchlist, score, position, order, account, cash, execution, or
  broker tables.

Acceptance:

- Re-importing the same artifact is idempotent.
- Every replay result points back to source P10 proposal evidence and P9
  analytics evidence.

### P11-4 Dashboard Read-Only Replay Summary

Goal: show replay status in the dashboard without edit or promotion controls.

Deliver:

- Read-only API endpoint for replay summaries by date range/status.
- Dashboard panel for replay counts and recent replay decisions.
- Empty/loading/error states.
- Browser smoke coverage if dashboard files change.

Boundary:

- No pass/fail editing buttons.
- No promotion buttons.
- No score/watchlist/trade action buttons.
- No broker or order UI.

Acceptance:

- Dashboard can show replay summaries for a selected date range.
- Dashboard remains usable when no replay rows exist.
- Mobile smoke has no horizontal overflow.

### P11-5 Runbook, Smoke, And Completion Review

Goal: make offline replay governance repeatable.

Deliver:

- P11 runbook.
- P11 smoke fixture using synthetic P10 proposals and replay metrics.
- P11 completion review.

Acceptance:

- P11 smoke proves replay artifacts can be created and imported.
- Verification commands and results are recorded.
- Completion review explicitly states that P11 added no scoring mutation,
  watchlist mutation, production promotion, scheduler automation, or trading
  execution path.

## Out Of Scope For P11

- Broker integration.
- Automatic order placement.
- Real order, execution, account, cash, position, or broker ledger tables.
- Turning experiments into trades.
- Writing factor scores.
- Writing watchlist signals.
- Writing `factor.factor_approval`.
- Changing ranking/scoring logic.
- Changing watchlist generation logic.
- Scheduler automation for replay or promotion.
- Shadow watchlist generation.
- Controlled scoring candidate evaluation.
- Training models from P8/P9/P10/P11 outcomes.
- Using replay metrics as historical scoring inputs.
- Fixing unrelated watchlist, factor-pipeline, trend-discovery, or
  strong-winner dirty files currently in the workspace.

## Deferred Beyond P11

Future phases may consume passing replay evidence, but only under new scope
freezes. Candidate future scopes:

- P12: shadow watchlist experiment read model.
- P13: controlled scoring candidate evaluation.
- P14: promotion review package and rollback planning.

None of those are part of P11.
