# P8 Decision Outcome Review Completion Review

Date: 2026-05-31

## Status

P8 is complete for the first scoped pass.

Scope covered: **Decision Outcome Review**.

P8 stayed inside:

- `docs/quant_system/31_p8_decision_outcome_review_scope_freeze.md`

## Delivered Capabilities

### P8-0 Scope Freeze

Delivered:

- `docs/quant_system/31_p8_decision_outcome_review_scope_freeze.md`

Decision:

- P8 reviews outcomes after P7 operator decisions.
- P8 stays review-only.
- P8 does not add broker, order, execution, account, cash, or live trading
  paths.

### P8-1 Outcome Metric Contract

Delivered:

- `src/stock_research/operator_decision/outcome.py`
- `tests/test_operator_decision_outcome.py`

Capabilities:

- Computes forward returns for 1D, 3D, 5D, 10D, 20D, and 60D horizons.
- Computes max high return and max low drawdown per horizon.
- Marks insufficient future data without zero filling.
- Preserves P7 evidence and source artifact references.
- Rejects execution-enabled decision events.

### P8-2 Outcome Review Artifact CLI

Delivered:

- `stock-research p8-decision-outcome-review`
- JSON, details CSV, summary CSV, and Markdown artifacts.
- CLI tests in `tests/test_factor_cli.py`.

Capabilities:

- Generates outcome artifacts from DB rows or local CSV inputs.
- Keeps `manual_review_required = true`.
- Keeps `auto_trade_enabled = false`.
- Outputs per-event details and grouped summaries.

### P8-3 Outcome Read Model

Delivered:

- `src/stock_research/operator_decision/outcome_read_model.py`
- Read-model schema:
  - `ops.operator_decision_outcome_run`
  - `ops.operator_decision_outcome_event`
- CLI command:
  - `p8-import-decision-outcome-review`
- Tests:
  - `tests/test_operator_decision_outcome_read_model.py`
  - `tests/test_schema.py`
  - `tests/test_factor_cli.py`

Capabilities:

- Loads outcome artifacts into compact read-model rows.
- Supports one file or directory import.
- Upserts runs and events idempotently.
- Preserves P7 decision event IDs and source artifact paths.
- Stores compact metrics in JSONB maps.

### P8-4 Dashboard Read-Only Outcome View

Delivered:

- Backend:
  - `src/stock_research/dashboard/outcomes.py`
  - `GET /api/assets/{asset_id}/outcomes`
- Frontend:
  - `dashboard/src/components/OutcomeHistoryPanel.tsx`
  - dashboard inspector integration
- Tests:
  - `tests/test_dashboard_outcomes.py`
  - `tests/test_dashboard_app.py`
  - `dashboard/tests/client.test.ts`
  - `dashboard/tests/app-shell.test.tsx`
  - `dashboard/tests/app-smoke.spec.ts`

Capabilities:

- Shows outcome history for the selected asset.
- Supports date range, optional review session, and limit filters.
- Handles empty outcome history.
- Keeps dashboard free of edit forms, trade recommendation buttons, broker
  widgets, and order UI.
- Mobile smoke confirms no horizontal overflow.

### P8-5 Runbook, Smoke, And Completion Review

Delivered:

- `src/stock_research/operator_decision/p8_smoke.py`
- `tests/test_p8_decision_outcome_smoke.py`
- `docs/quant_system/32_p8_decision_outcome_review_runbook.md`
- `docs/quant_system/33_p8_decision_outcome_review_completion.md`

Smoke result:

```text
p8_smoke|p7_journal|/tmp/stock_research_p8_smoke/p7/operator_decision_journal_2026-05-30_p8-smoke.json
p8_smoke|p8_outcome|/tmp/stock_research_p8_smoke/p8/operator_decision_outcome_review_2026-05-30_2026-06-30.json
p8_smoke|journal_decisions|2
p8_smoke|outcomes|2
p8_smoke|read_model_events|2
p8_smoke|labels|candidate,caution
p8_smoke|manual_review_required|True
p8_smoke|auto_trade_enabled|False
```

## Acceptance Criteria Review

| Criterion | Status | Evidence |
| --- | --- | --- |
| Decision events can produce outcome artifacts | Pass | P8 smoke; `tests/test_p8_decision_outcome_smoke.py` |
| Outcome artifacts can produce read-model rows | Pass | P8 smoke; outcome read-model tests |
| Re-importing same artifact is idempotent | Pass | SQL uses `ON CONFLICT`; importer tests |
| Every outcome event points back to decision/source artifacts | Pass | read-model tests; P8 smoke |
| Dashboard can show outcome history for an asset | Pass | dashboard API/frontend tests |
| Dashboard remains usable when no outcome rows exist | Pass | frontend empty-state tests |
| Mobile dashboard has no horizontal overflow | Pass | Playwright mobile smoke |
| No trading execution path was introduced | Pass | Safety review below |

## Verification Evidence

P8-focused Python verification:

```bash
.venv/bin/pytest tests/test_operator_decision_journal.py tests/test_operator_decision_read_model.py tests/test_operator_decision_outcome.py tests/test_operator_decision_outcome_read_model.py tests/test_p8_decision_outcome_smoke.py tests/test_dashboard_app.py tests/test_dashboard_outcomes.py tests/test_dashboard_decisions.py tests/test_schema.py tests/test_factor_cli.py -k 'operator_decision or p7_decision_journal or p8_decision_outcome or dashboard_api' -q
```

Result:

```text
29 passed, 175 deselected, 2 warnings
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
Vitest: 15 passed
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
- No live notification send was enabled.
- No scheduler behavior was changed.
- Outcome artifacts force `manual_review_required = true`.
- Outcome artifacts force `auto_trade_enabled = false`.
- Outcome imports preserve source artifacts and compact metrics only.
- Dashboard outcome history is read-only.
- P8 outcomes are not used as scoring inputs or trading instructions.

## Known Non-P8 Workspace Files

The workspace contains unrelated non-P8 dirty files. They are not part of this
completion review and should be handled separately:

- `src/stock_research/cli.py`
- `src/stock_research/factor_pipeline.py`
- `src/stock_research/watchlist/effectiveness.py`
- `tests/test_factor_pipeline.py`
- `tests/test_watchlist_cli.py`
- `tests/test_watchlist_effectiveness.py`
- untracked watchlist and strong-winner files

## Completion Definition

P8 is complete when a reviewer can:

1. Generate outcome review artifacts from P7 decisions and market bars.
2. Import outcome artifacts into a compact read model.
3. Inspect outcome history in the dashboard.
4. Run a repeatable smoke proving the artifact and read-model path.
5. Confirm that P8 remains review-only and introduces no trading execution path.

All five conditions are satisfied for the first scoped pass.
