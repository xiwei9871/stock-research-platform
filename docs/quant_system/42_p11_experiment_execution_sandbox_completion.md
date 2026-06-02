# P11 Experiment Execution Sandbox Completion Review

Date: 2026-05-31

## Status

P11 is complete for the first scoped pass.

Scope covered:

- `docs/quant_system/40_p11_experiment_execution_sandbox_scope_freeze.md`

## Delivered Capabilities

### P11-0 Scope Freeze

Delivered:

- `docs/quant_system/40_p11_experiment_execution_sandbox_scope_freeze.md`

Boundary:

- P11 consumes approved P10 proposals.
- P11 remains offline/review-only.
- P11 does not convert replay results into score, watchlist, scheduler, or
  trading actions.

### P11-1 Offline Replay Contract

Delivered:

- `src/stock_research/operator_decision/experiment_replay.py`
- `tests/test_operator_experiment_replay.py`

Capabilities:

- Validates replay identity, proposal ID, source P10 run, source P9 analytics
  run, replay date range, input artifact paths, validation method, status, and
  metric summaries.
- Supports statuses: `replay_ready`, `passed_offline_replay`,
  `failed_offline_replay`, `needs_more_data`, and `blocked`.
- Rejects unapproved proposals, missing replay input evidence, invalid statuses,
  execution-like fields, `auto_trade_enabled = true`, and
  `production_write_enabled = true`.
- Keeps `manual_review_required = true`, `auto_trade_enabled = false`, and
  `production_write_enabled = false`.

### P11-2 Replay Artifact CLI

Delivered:

- `stock-research p11-experiment-replay`
- JSON, result CSV, and Markdown artifacts.
- CLI tests in `tests/test_factor_cli.py`.

Capabilities:

- Builds replay artifacts from P10 proposal JSON and replay metric CSV input.
- Preserves proposal ID, source P10 proposal run ID, source P9 analytics run ID,
  replay input artifact paths, and metric summaries.
- Produces review-only artifacts with no scoring, watchlist, promotion,
  scheduler, broker, order, or execution mutation.

### P11-3 Replay Read Model

Delivered:

- `src/stock_research/operator_decision/experiment_replay_read_model.py`
- Read-model schema:
  - `ops.operator_experiment_replay_run`
  - `ops.operator_experiment_replay_result`
- CLI command:
  - `p11-import-experiment-replay`
- Tests:
  - `tests/test_operator_experiment_replay_read_model.py`
  - `tests/test_schema.py`
  - `tests/test_factor_cli.py`

Capabilities:

- Imports one replay artifact or a directory of artifacts.
- Upserts replay runs and replay result rows idempotently.
- Preserves source P10 proposal evidence, source P9 analytics evidence, replay
  input paths, metric summaries, and replay artifact paths.
- Stores replay review metadata only.

### P11-4 Dashboard Read-Only Replay Summary

Delivered:

- Backend:
  - `src/stock_research/dashboard/experiment_replay.py`
  - `GET /api/experiment-replay`
- Frontend:
  - `dashboard/src/components/ExperimentReplayPanel.tsx`
  - dashboard inspector integration
- Tests:
  - `tests/test_dashboard_experiment_replay.py`
  - `tests/test_dashboard_app.py`
  - `dashboard/tests/client.test.ts`
  - `dashboard/tests/app-shell.test.tsx`
  - `dashboard/tests/app-smoke.spec.ts`

Capabilities:

- Shows replay proposal ID, status, pass/fail/sample counts, source P10 proposal
  run, and source P9 analytics run.
- Supports loading and empty replay states.
- Mobile smoke confirms no horizontal overflow.
- Adds no edit, pass/fail, promotion, score, watchlist, trade, broker, order, or
  scheduler UI.

### P11-5 Runbook, Smoke, And Completion Review

Delivered:

- `src/stock_research/operator_decision/p11_smoke.py`
- `tests/test_p11_experiment_replay_smoke.py`
- `docs/quant_system/41_p11_experiment_execution_sandbox_runbook.md`
- This completion review.

Smoke result:

```text
p11_smoke|p10_proposals|/tmp/stock_research_p11_smoke/p10/operator_experiment_proposals_2026-06-30.json
p11_smoke|replay_input_metrics|/tmp/stock_research_p11_smoke/p11/replay_metrics_2026-06-30.csv
p11_smoke|p11_replay|/tmp/stock_research_p11_smoke/p11/operator_experiment_replay_2026-01-01_2026-06-30.json
p11_smoke|results_csv|/tmp/stock_research_p11_smoke/p11/operator_experiment_replay_2026-01-01_2026-06-30_results.csv
p11_smoke|markdown|/tmp/stock_research_p11_smoke/p11/operator_experiment_replay_2026-01-01_2026-06-30.md
p11_smoke|result_count|1
p11_smoke|read_model_results|1
p11_smoke|source_p10_runs|p10-smoke-proposals-2026-06-30
p11_smoke|source_p9_runs|p9-smoke-analytics-2026-05-30-2026-06-30
p11_smoke|manual_review_required|True
p11_smoke|auto_trade_enabled|False
p11_smoke|production_write_enabled|False
```

## Acceptance Criteria Review

| Criterion | Status | Evidence |
| --- | --- | --- |
| Replay artifacts preserve P10 and P9 references | Pass | Contract/read-model tests; P11 smoke |
| Artifacts are review-only | Pass | Contract tests; smoke safety fields |
| CLI creates repeatable replay artifacts | Pass | CLI tests; runbook command |
| Read model imports replay rows idempotently | Pass | Import SQL uses `ON CONFLICT`; importer tests |
| Dashboard shows read-only replay summary | Pass | Backend/frontend/dashboard smoke tests |
| No scoring/watchlist/trading mutation added | Pass | Safety review below |

## Verification Evidence

P11-focused Python verification:

```bash
.venv/bin/pytest tests/test_operator_experiment_replay.py tests/test_operator_experiment_replay_read_model.py tests/test_p11_experiment_replay_smoke.py tests/test_schema.py tests/test_factor_cli.py tests/test_dashboard_experiment_replay.py tests/test_dashboard_app.py -k 'experiment_replay or p11_experiment_replay or p11_import_experiment_replay or dashboard' -q
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
Python: 32 passed, 183 deselected, 2 warnings
Vitest: 18 passed
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
- No scheduler automation was added.
- No production promotion path was added.
- No factor score mutation was added.
- No watchlist signal write path was added.
- No `factor.factor_approval` write path was added.
- P11 artifacts force `manual_review_required = true`.
- P11 artifacts force `auto_trade_enabled = false`.
- P11 artifacts force `production_write_enabled = false`.
- Dashboard replay summaries are read-only.
- `passed_offline_replay` means replay evidence is ready for later review, not
  production approval.

## Known Non-P11 Workspace Files

The workspace still contains unrelated watchlist, factor-pipeline,
trend-discovery, and strong-winner dirty files. They were not included in P11
commits.
