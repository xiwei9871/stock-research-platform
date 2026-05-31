# P10 Experiment Promotion Governance Completion Review

Date: 2026-05-31

## Status

P10 is complete for the first scoped pass.

Scope covered:

- `docs/quant_system/37_p10_experiment_promotion_governance_scope_freeze.md`

## Delivered Capabilities

### P10-0 Scope Freeze

Delivered:

- `docs/quant_system/37_p10_experiment_promotion_governance_scope_freeze.md`

Boundary:

- P10 starts from P9 analytics contracts.
- P10 remains governance-only.
- P10 does not reuse `factor.factor_approval` as a scoring or watchlist shortcut.

### P10-1 Experiment Proposal Contract

Delivered:

- `src/stock_research/operator_decision/experiment_proposals.py`
- `tests/test_operator_experiment_proposals.py`

Capabilities:

- Validates proposal identity, hypothesis, P9 evidence, validation method,
  risk notes, reviewer, and status.
- Supports statuses: `draft`, `needs_more_data`, `approved_for_experiment`,
  `rejected`, and `deferred`.
- Rejects missing P9 evidence, invalid statuses, execution-like fields, and
  `auto_trade_enabled = true`.
- Keeps `manual_review_required = true`, `auto_trade_enabled = false`, and
  `promotion_enabled = false`.

### P10-2 Proposal Artifact CLI

Delivered:

- `stock-research p10-experiment-proposals`
- JSON, proposal CSV, and Markdown artifacts.
- CLI tests in `tests/test_factor_cli.py`.

Capabilities:

- Builds proposal artifacts from reviewer-authored CSV rows.
- Preserves P9 analytics run IDs, group IDs, diagnostic refs, and artifact paths.
- Produces review-only artifacts with no scoring, watchlist, trade, broker, or
  scheduler mutation.

### P10-3 Proposal Read Model

Delivered:

- `src/stock_research/operator_decision/experiment_proposals_read_model.py`
- Read-model schema:
  - `ops.operator_experiment_proposal_run`
  - `ops.operator_experiment_proposal`
- CLI command:
  - `p10-import-experiment-proposals`
- Tests:
  - `tests/test_operator_experiment_proposals_read_model.py`
  - `tests/test_schema.py`
  - `tests/test_factor_cli.py`

Capabilities:

- Imports one proposal artifact or a directory of artifacts.
- Upserts proposal runs and proposal rows idempotently.
- Preserves P9 evidence references and proposal artifact paths.
- Stores governance decisions only.

### P10-4 Dashboard Read-Only Proposal Summary

Delivered:

- Backend:
  - `src/stock_research/dashboard/experiment_proposals.py`
  - `GET /api/experiment-proposals`
- Frontend:
  - `dashboard/src/components/ExperimentProposalsPanel.tsx`
  - dashboard inspector integration
- Tests:
  - `tests/test_dashboard_experiment_proposals.py`
  - `tests/test_dashboard_app.py`
  - `dashboard/tests/client.test.ts`
  - `dashboard/tests/app-shell.test.tsx`
  - `dashboard/tests/app-smoke.spec.ts`

Capabilities:

- Shows proposal title, status, hypothesis, reviewer, review date, and source P9
  analytics run.
- Supports empty proposal state.
- Mobile smoke confirms no horizontal overflow.
- Adds no edit, approve, reject, promotion, score, watchlist, trade, broker, or
  order UI.

### P10-5 Runbook, Smoke, And Completion Review

Delivered:

- `src/stock_research/operator_decision/p10_smoke.py`
- `tests/test_p10_experiment_proposals_smoke.py`
- `docs/quant_system/38_p10_experiment_promotion_governance_runbook.md`
- This completion review.

Smoke result:

```text
p10_smoke|p9_analytics|/tmp/stock_research_p10_smoke/p9/operator_decision_outcome_analytics_2026-05-30_2026-06-30.json
p10_smoke|p10_proposals|/tmp/stock_research_p10_smoke/p10/operator_experiment_proposals_2026-06-30.json
p10_smoke|proposals_csv|/tmp/stock_research_p10_smoke/p10/operator_experiment_proposals_2026-06-30_proposals.csv
p10_smoke|markdown|/tmp/stock_research_p10_smoke/p10/operator_experiment_proposals_2026-06-30.md
p10_smoke|proposal_count|2
p10_smoke|read_model_proposals|2
p10_smoke|source_p9_runs|p9-smoke-analytics-2026-05-30-2026-06-30
p10_smoke|manual_review_required|True
p10_smoke|auto_trade_enabled|False
p10_smoke|promotion_enabled|False
```

## Acceptance Criteria Review

| Criterion | Status | Evidence |
| --- | --- | --- |
| Proposal artifacts preserve P9 source evidence | Pass | Proposal contract/read-model tests; P10 smoke |
| Artifacts are review-only | Pass | Contract tests; smoke safety fields |
| CLI creates repeatable artifacts | Pass | CLI tests; runbook command |
| Read model imports proposals idempotently | Pass | Import SQL uses `ON CONFLICT`; importer tests |
| Dashboard shows read-only proposal summary | Pass | Backend/frontend/dashboard smoke tests |
| No scoring/watchlist/trading mutation added | Pass | Safety review below |

## Verification Evidence

P10-focused Python verification:

```bash
.venv/bin/pytest tests/test_operator_experiment_proposals.py tests/test_operator_experiment_proposals_read_model.py tests/test_p10_experiment_proposals_smoke.py tests/test_schema.py tests/test_factor_cli.py tests/test_dashboard_experiment_proposals.py tests/test_dashboard_app.py -k 'experiment_proposal or p10_experiment_proposals or p10_import_experiment_proposals or operator_experiment_proposal or dashboard' -q
```

Dashboard frontend verification:

```bash
cd dashboard
pnpm test
pnpm build
pnpm test:e2e
```

Results:

```text
Python: 29 passed, 176 deselected, 2 warnings
Vitest: 17 passed
Vite build: passed
Playwright: 2 passed
```

The Python warnings are existing `py_mini_racer` deprecation warnings. The
Playwright run emits existing `NO_COLOR` / `FORCE_COLOR` environment warnings.

## Safety Review

- No broker adapter was added.
- No order placement was added.
- No order ticket UI was added.
- No account, cash, order, execution, position, or broker ledger table was
  added.
- No scheduler promotion automation was added.
- No factor score mutation was added.
- No watchlist signal write path was added.
- No `factor.factor_approval` write path was added.
- P10 artifacts force `manual_review_required = true`.
- P10 artifacts force `auto_trade_enabled = false`.
- P10 artifacts force `promotion_enabled = false`.
- Dashboard proposal summaries are read-only.
- `approved_for_experiment` means ready for a later experiment scope, not ready
  for production scoring or watchlist changes.

## Known Non-P10 Workspace Files

The workspace still contains unrelated non-P10 dirty files. They are not part of
this completion review and were not staged for P10 commits:

- `src/stock_research/cli.py`
- `src/stock_research/factor_pipeline.py`
- `src/stock_research/watchlist/effectiveness.py`
- `tests/test_factor_pipeline.py`
- `tests/test_watchlist_cli.py`
- `tests/test_watchlist_effectiveness.py`
- untracked watchlist, trend, and strong-winner files

## Completion Definition

P10 is complete when a reviewer can:

1. Draft explicit experiment proposals from P9 analytics evidence.
2. Export proposal artifacts with review-only safety fields.
3. Import proposal artifacts into a compact read model.
4. Inspect proposal summaries in the dashboard.
5. Run a repeatable smoke proving artifact and read-model behavior.
6. Confirm that P10 adds no scoring mutation, watchlist mutation, or trading
   execution path.

All six conditions are satisfied for the first scoped pass after the final
verification run recorded above.
