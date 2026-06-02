# P12 Shadow Watchlist Experiment Completion Review

Date: 2026-06-01

## Status

P12 is complete for the first scoped pass.

Scope covered:

- `docs/quant_system/43_p12_shadow_watchlist_scope_freeze.md`

## Delivered Capabilities

### P12-0 Scope Freeze

Delivered:

- `docs/quant_system/43_p12_shadow_watchlist_scope_freeze.md`

Boundary:

- P12 consumes passed P11 offline replay evidence.
- P12 remains shadow/review-only.
- P12 does not convert candidates into score, production watchlist, scheduler,
  or trading actions.

### P12-1 Shadow Watchlist Contract

Delivered:

- `src/stock_research/operator_decision/shadow_watchlist.py`
- `tests/test_operator_shadow_watchlist.py`

Capabilities:

- Validates candidate identity, P11 replay result ID, source P11 replay run,
  source P10 proposal run, source P9 analytics run, candidate date, asset,
  shadow layer, evidence paths, metric summaries, reviewer, status, and notes.
- Supports statuses: `shadow_ready`, `shadow_observe`, `shadow_rejected`,
  `needs_more_data`, and `blocked`.
- Rejects missing replay evidence, non-passed replay rows, invalid statuses,
  execution-like fields, `auto_trade_enabled = true`,
  `production_watchlist_enabled = true`, and `production_write_enabled = true`.
- Keeps `manual_review_required = true`, `auto_trade_enabled = false`,
  `production_watchlist_enabled = false`, and
  `production_write_enabled = false`.

### P12-2 Shadow Artifact CLI

Delivered:

- `stock-research p12-shadow-watchlist`
- JSON, candidate CSV, and Markdown artifacts.
- CLI tests in `tests/test_factor_cli.py`.

Capabilities:

- Builds shadow watchlist artifacts from P11 replay JSON and candidate CSV
  input.
- Preserves P11 replay, P10 proposal, and P9 analytics evidence references.
- Produces review-only artifacts with no scoring, production watchlist,
  promotion, scheduler, broker, order, or execution mutation.

### P12-3 Shadow Read Model

Delivered:

- `src/stock_research/operator_decision/shadow_watchlist_read_model.py`
- Read-model schema:
  - `ops.operator_shadow_watchlist_run`
  - `ops.operator_shadow_watchlist_candidate`
- CLI command:
  - `p12-import-shadow-watchlist`
- Tests:
  - `tests/test_operator_shadow_watchlist_read_model.py`
  - `tests/test_schema.py`
  - `tests/test_factor_cli.py`

Capabilities:

- Imports one shadow artifact or a directory of artifacts.
- Upserts shadow watchlist runs and candidate rows idempotently.
- Preserves source P11 replay, P10 proposal, P9 analytics, evidence artifact
  paths, metric summaries, and shadow artifact paths.
- Stores review metadata only in `ops` tables.

### P12-4 Dashboard Read-Only Shadow Summary

Delivered:

- Backend:
  - `src/stock_research/dashboard/shadow_watchlist.py`
  - `GET /api/shadow-watchlist`
- Frontend:
  - `dashboard/src/components/ShadowWatchlistPanel.tsx`
  - dashboard inspector integration
- Tests:
  - `tests/test_dashboard_shadow_watchlist.py`
  - `tests/test_dashboard_app.py`
  - `dashboard/tests/client.test.ts`
  - `dashboard/tests/app-shell.test.tsx`
  - `dashboard/tests/app-smoke.spec.ts`

Capabilities:

- Shows candidate name or asset, status, candidate date, shadow layer, asset,
  candidate reason, source P11 replay run, and source P10 proposal run.
- Supports loading and empty states.
- Mobile smoke confirms no horizontal overflow.
- Adds no edit, promotion, score, production watchlist, trade, broker, order, or
  scheduler UI.

### P12-5 Runbook, Smoke, And Completion Review

Delivered:

- `src/stock_research/operator_decision/p12_smoke.py`
- `tests/test_p12_shadow_watchlist_smoke.py`
- `docs/quant_system/44_p12_shadow_watchlist_runbook.md`
- This completion review.

Smoke result:

```text
p12_smoke|p11_replay|/tmp/stock_research_p12_smoke/p11/operator_experiment_replay_2026-01-01_2026-06-30.json
p12_smoke|p12_shadow|/tmp/stock_research_p12_smoke/p12/operator_shadow_watchlist_2026-06-30.json
p12_smoke|candidates_csv|/tmp/stock_research_p12_smoke/p12/operator_shadow_watchlist_2026-06-30_candidates.csv
p12_smoke|markdown|/tmp/stock_research_p12_smoke/p12/operator_shadow_watchlist_2026-06-30.md
p12_smoke|candidate_count|1
p12_smoke|read_model_candidates|1
p12_smoke|source_p11_runs|p11-smoke-replay-2026-06-30
p12_smoke|source_p10_runs|p10-smoke-proposals-2026-06-30
p12_smoke|source_p9_runs|p9-smoke-analytics-2026-05-30-2026-06-30
p12_smoke|manual_review_required|True
p12_smoke|auto_trade_enabled|False
p12_smoke|production_watchlist_enabled|False
p12_smoke|production_write_enabled|False
```

## Acceptance Criteria Review

| Criterion | Status | Evidence |
| --- | --- | --- |
| Shadow artifacts preserve P11, P10, and P9 references | Pass | Contract/read-model tests; P12 smoke |
| Artifacts are review-only | Pass | Contract tests; smoke safety fields |
| CLI creates repeatable shadow artifacts | Pass | CLI tests; runbook command |
| Read model imports shadow rows idempotently | Pass | Import SQL uses `ON CONFLICT`; importer tests |
| Dashboard shows read-only shadow summary | Pass | Backend/frontend/dashboard smoke tests |
| No production watchlist/scoring/scheduler/trading mutation added | Pass | Safety review below |

## Verification Evidence

P12-focused Python verification:

```bash
.venv/bin/pytest tests/test_operator_shadow_watchlist.py tests/test_operator_shadow_watchlist_read_model.py tests/test_p12_shadow_watchlist_smoke.py tests/test_schema.py tests/test_factor_cli.py tests/test_dashboard_shadow_watchlist.py tests/test_dashboard_app.py -k 'shadow_watchlist or p12_shadow_watchlist or p12_import_shadow_watchlist or dashboard' -q
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
Python: 24 passed, 191 deselected, 3 warnings
Vitest: 19 passed
Vite build: passed
Playwright: 2 passed
```

The Python warnings are existing `py_mini_racer` deprecation warnings and an
existing FastAPI/Starlette `httpx` compatibility warning. The Playwright run
emits existing `NO_COLOR` / `FORCE_COLOR` environment warnings.

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
- P12 artifacts force `manual_review_required = true`.
- P12 artifacts force `auto_trade_enabled = false`.
- P12 artifacts force `production_watchlist_enabled = false`.
- P12 artifacts force `production_write_enabled = false`.
- Dashboard shadow watchlist summaries are read-only.
- `shadow_ready` and `shadow_observe` mean shadow review evidence only, not
  production approval.

## Known Non-P12 Workspace Files

The main workspace still contains unrelated watchlist, factor-pipeline,
trend-discovery, strong-winner, and Alpha191-adjacent dirty files. They were
not included in P12 commits.
