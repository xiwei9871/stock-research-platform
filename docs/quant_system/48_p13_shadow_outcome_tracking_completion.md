# P13 Shadow Watchlist Outcome Tracking Completion Review

Date: 2026-06-01

## Status

P13 is complete for the first scoped pass.

Scope covered:

- `docs/quant_system/46_p13_shadow_outcome_tracking_scope_freeze.md`

## Delivered Capabilities

### P13-0 Scope Freeze

Delivered:

- `docs/quant_system/46_p13_shadow_outcome_tracking_scope_freeze.md`

Boundary:

- P13 consumes P12 review-only shadow candidates.
- P13 records later market outcomes as review evidence only.
- P13 does not convert outcomes into score, production watchlist, scheduler, or
  trading actions.

### P13-1 Shadow Outcome Contract

Delivered:

- `src/stock_research/operator_decision/shadow_outcomes.py`
- `tests/test_operator_shadow_outcomes.py`

Capabilities:

- Computes forward returns, max high returns, and max low drawdowns for shadow
  candidates across configured horizons.
- Preserves P12 shadow run, P11 replay run, P10 proposal run, and P9 analytics
  run references.
- Marks rows `complete` only when enough future bars exist.
- Rejects unsafe execution-like fields and unsafe safety flags.

### P13-2 Shadow Outcome Artifact CLI

Delivered:

- `stock-research p13-shadow-outcome-review`
- JSON, details CSV, and Markdown artifacts.
- CLI tests in `tests/test_factor_cli.py`.

Capabilities:

- Builds shadow outcome artifacts from P12 shadow JSON and daily bar CSV input.
- Produces review-only artifacts with no scoring, production watchlist,
  promotion, scheduler, broker, order, or execution mutation.

### P13-3 Shadow Outcome Read Model

Delivered:

- `src/stock_research/operator_decision/shadow_outcomes_read_model.py`
- Read-model schema:
  - `ops.operator_shadow_watchlist_outcome_run`
  - `ops.operator_shadow_watchlist_outcome_candidate`
- CLI command:
  - `p13-import-shadow-outcomes`
- Tests:
  - `tests/test_operator_shadow_outcomes_read_model.py`
  - `tests/test_schema.py`
  - `tests/test_factor_cli.py`

Capabilities:

- Imports one shadow outcome artifact or a directory of artifacts.
- Upserts shadow outcome runs and candidate outcome rows idempotently.
- Stores P13 review metadata only in `ops` tables.

### P13-4 Dashboard Read-Only Shadow Outcome Summary

Delivered:

- Backend:
  - `src/stock_research/dashboard/shadow_outcomes.py`
  - `GET /api/shadow-outcomes`
- Frontend:
  - `dashboard/src/components/ShadowOutcomesPanel.tsx`
  - dashboard inspector integration
- Tests:
  - `tests/test_dashboard_shadow_outcomes.py`
  - `tests/test_dashboard_app.py`
  - `dashboard/tests/client.test.ts`
  - `dashboard/tests/app-shell.test.tsx`
  - `dashboard/tests/app-smoke.spec.ts`

Capabilities:

- Shows shadow candidate outcome status, candidate date, asset, source P12/P11
  evidence, available future bars, and forward outcome metrics.
- Supports loading and empty states.
- Mobile smoke confirms no horizontal overflow.
- Adds no edit, promotion, score, production watchlist, trade, broker, order, or
  scheduler UI.

### P13-5 Runbook, Smoke, And Completion Review

Delivered:

- `src/stock_research/operator_decision/p13_smoke.py`
- `tests/test_p13_shadow_outcomes_smoke.py`
- `docs/quant_system/47_p13_shadow_outcome_tracking_runbook.md`
- This completion review.

TDD evidence:

```text
RED: .venv/bin/pytest tests/test_p13_shadow_outcomes_smoke.py -q
Result: failed during collection with ModuleNotFoundError: No module named 'stock_research.operator_decision.p13_smoke'

GREEN: .venv/bin/pytest tests/test_p13_shadow_outcomes_smoke.py tests/test_p12_shadow_watchlist_smoke.py -q
Result: 3 passed in 0.36s
```

Smoke result:

```text
p13_smoke|p12_shadow|/tmp/stock_research_p13_smoke/p12/operator_shadow_watchlist_2026-06-30.json
p13_smoke|p13_shadow_outcome|/tmp/stock_research_p13_smoke/p13/operator_shadow_outcomes_2026-08-29.json
p13_smoke|details_csv|/tmp/stock_research_p13_smoke/p13/operator_shadow_outcomes_2026-08-29_details.csv
p13_smoke|markdown|/tmp/stock_research_p13_smoke/p13/operator_shadow_outcomes_2026-08-29.md
p13_smoke|outcome_count|1
p13_smoke|read_model_candidates|1
p13_smoke|outcome_statuses|complete
p13_smoke|source_p12_runs|p12-smoke-shadow-watchlist-2026-06-30
p13_smoke|source_p11_runs|p11-smoke-replay-2026-06-30
p13_smoke|source_p10_runs|p10-smoke-proposals-2026-06-30
p13_smoke|source_p9_runs|p9-smoke-analytics-2026-05-30-2026-06-30
p13_smoke|manual_review_required|True
p13_smoke|auto_trade_enabled|False
p13_smoke|production_watchlist_enabled|False
p13_smoke|production_write_enabled|False
```

## Acceptance Criteria Review

| Criterion | Status | Evidence |
| --- | --- | --- |
| P13 smoke starts from P12 smoke artifact | Pass | `p13_smoke|p12_shadow|...` |
| P13 smoke writes JSON, CSV, and Markdown artifacts | Pass | Smoke output artifact paths |
| Smoke read model contains one candidate outcome | Pass | `read_model_candidates|1` |
| Outcome is complete | Pass | `outcome_statuses|complete` |
| Source P12, P11, P10, and P9 references are preserved | Pass | Smoke source run output |
| Artifacts are review-only | Pass | Smoke safety fields |
| No production watchlist/scoring/scheduler/trading mutation added | Pass | Safety review below |

## Verification Evidence

P13-focused Python verification:

```bash
.venv/bin/pytest tests/test_operator_shadow_outcomes.py tests/test_operator_shadow_outcomes_read_model.py tests/test_p13_shadow_outcomes_smoke.py tests/test_schema.py tests/test_factor_cli.py tests/test_dashboard_shadow_outcomes.py tests/test_dashboard_app.py -k 'shadow_outcome or p13_shadow_outcome or p13_import_shadow_outcomes or dashboard' -q
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
Python: 42 passed, 195 deselected, 3 warnings
Vitest: 21 passed
Vite build: passed
Playwright: 2 passed
```

The Python warnings are existing `py_mini_racer` deprecation warnings and an
existing FastAPI/Starlette `httpx` compatibility warning. The Playwright run
emits existing `NO_COLOR` / `FORCE_COLOR` environment warnings.

## Final Review Fixes

Final code review identified two blocking issues, both fixed before P13
completion:

- The dashboard shadow outcome loader now returns an empty read-only summary
  when the P13 `ops` schema/table has not been initialized yet, instead of
  surfacing a 500 from `/api/shadow-outcomes`.
- The P13 read-model loader now preserves only current-run-scoped
  `shadow_outcome_id` values. Legacy or mismatched artifact IDs are normalized
  to the current run, preventing cross-run primary-key collisions and misleading
  lineage.

Regression evidence:

```text
.venv/bin/pytest tests/test_dashboard_shadow_outcomes.py tests/test_dashboard_app.py -k 'shadow_outcomes and table_missing' -q
Result: 2 passed, 14 deselected, 3 warnings

.venv/bin/pytest tests/test_operator_shadow_outcomes_read_model.py -k 'mismatched_run_scoped or preserves_safe_run_scoped or normalizes_legacy' -q
Result: 3 passed, 11 deselected
```

## Safety Review

- No broker adapter was added.
- No order placement was added.
- No order ticket UI was added.
- No account, cash, order, execution, position, or broker ledger table was
  added.
- No scheduler automation was added.
- No production promotion path was added.
- No factor score mutation was added.
- No production watchlist signal write path was added.
- No `factor.factor_approval` write path was added.
- P13 artifacts force `manual_review_required = true`.
- P13 artifacts force `auto_trade_enabled = false`.
- P13 artifacts force `production_watchlist_enabled = false`.
- P13 artifacts force `production_write_enabled = false`.
- Dashboard shadow outcome summaries are read-only.
- `complete` means enough future market bars exist for the configured horizons,
  not production approval.

## Known Non-P13 Workspace Files

The worktree contains an unrelated untracked support file:

- `src/stock_research/strong_winner_topn_attribution.py`

It was not modified, staged, or included in the P13 Task 5 commit.
