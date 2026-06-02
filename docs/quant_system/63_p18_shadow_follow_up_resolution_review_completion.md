# P18 Shadow Follow-up Resolution Review Completion

## Status

P18 is complete for the first scoped pass.

It builds a review-only resolution review from P17 shadow follow-up queue
artifacts, imports independent P18 ops read-model rows, and exposes those rows
through the dashboard. P18 does not mutate P17 queue rows and does not create
production actions.

## Delivered

### P18-0 Scope Freeze

Artifacts:

- `docs/quant_system/61_p18_shadow_follow_up_resolution_review_scope_freeze.md`
- `docs/superpowers/specs/2026-06-03-p18-shadow-follow-up-resolution-review-design.md`
- `docs/superpowers/plans/2026-06-03-p18-shadow-follow-up-resolution-review.md`

### P18-1 Artifact Contract

Artifacts:

- `src/stock_research/operator_decision/shadow_follow_up_resolution.py`
- `tests/test_operator_shadow_follow_up_resolution.py`

Result:

- Builds JSON, items CSV, and Markdown resolution artifacts from P17 artifacts.
- Maps P17 follow-up statuses to P18 resolution statuses.
- Rejects unsafe execution fields and unsafe production flags.

### P18-2 Build CLI

Artifacts:

- `stock-research p18-shadow-follow-up-resolution`
- `tests/test_factor_cli.py`

Result:

- CLI builds P18 artifacts from a P17 follow-up JSON artifact.
- CLI prints status, item count, JSON path, CSV path, and Markdown path.

### P18-3 Read Model And Import CLI

Artifacts:

- `src/stock_research/operator_decision/shadow_follow_up_resolution_read_model.py`
- `tests/test_operator_shadow_follow_up_resolution_read_model.py`
- `src/stock_research/schema.py`
- `stock-research p18-import-shadow-follow-up-resolution`

Result:

- Adds `ops.operator_shadow_follow_up_resolution_run`.
- Adds `ops.operator_shadow_follow_up_resolution_item`.
- Upserts run and item rows by stable P18 keys.
- Preserves P17/P16/P15/P14 lineage.
- Forces review-only safety flags in read-model output.

### P18-4 Dashboard

Artifacts:

- `src/stock_research/dashboard/shadow_follow_up_resolution.py`
- `src/stock_research/dashboard/app.py`
- `dashboard/src/components/ShadowFollowUpResolutionPanel.tsx`
- `dashboard/src/api/client.ts`
- `dashboard/src/api/types.ts`
- `dashboard/src/App.tsx`
- `tests/test_dashboard_shadow_follow_up_resolution.py`
- `dashboard/tests/client.test.ts`
- `dashboard/tests/app-shell.test.tsx`
- `dashboard/tests/app-smoke.spec.ts`

Result:

- Adds read-only `/api/shadow-follow-up-resolution`.
- Adds dashboard panel after the P17 follow-up queue panel.
- Browser smoke verifies desktop and mobile rendering without horizontal overflow.
- No promote, trade, write, scheduler, broker, order, account, cash, or position control was added.

### P18-5 Smoke And Runbook

Artifacts:

- `src/stock_research/operator_decision/p18_smoke.py`
- `tests/test_p18_shadow_follow_up_resolution_smoke.py`
- `docs/quant_system/62_p18_shadow_follow_up_resolution_review_runbook.md`
- This completion review.

Smoke output from 2026-06-03:

```text
p18_smoke|p17_shadow_follow_up_queue_json_path|/tmp/stock_research_p18_smoke/p17/operator_shadow_follow_up_queue_2026-08-29.json
p18_smoke|p18_shadow_follow_up_resolution_json_path|/tmp/stock_research_p18_smoke/p18/operator_shadow_follow_up_resolution_2026-08-29.json
p18_smoke|p18_shadow_follow_up_resolution_items_csv_path|/tmp/stock_research_p18_smoke/p18/operator_shadow_follow_up_resolution_2026-08-29_items.csv
p18_smoke|p18_shadow_follow_up_resolution_markdown_path|/tmp/stock_research_p18_smoke/p18/operator_shadow_follow_up_resolution_2026-08-29.md
p18_smoke|source_follow_up_item_count|1
p18_smoke|resolution_item_count|1
p18_smoke|read_model_item_count|1
p18_smoke|follow_up_statuses|['collect_more_evidence']
p18_smoke|resolution_statuses|['stale_unresolved']
p18_smoke|resolution_buckets|['needs_operator_review']
p18_smoke|source_p17_follow_up_run_ids|['p17-smoke-shadow-follow-up-queue-2026-08-29']
p18_smoke|manual_review_required|True
p18_smoke|auto_trade_enabled|False
p18_smoke|production_watchlist_enabled|False
p18_smoke|production_write_enabled|False
```

## Verification

Focused artifact/read-model/CLI/schema:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_operator_shadow_follow_up_resolution.py tests/test_operator_shadow_follow_up_resolution_read_model.py tests/test_schema.py tests/test_factor_cli.py -k 'shadow_follow_up_resolution or p18_shadow_follow_up_resolution or p18_import_shadow_follow_up_resolution' -q && git diff --check
```

Result:

```text
15 passed, 219 deselected, 2 warnings
```

P18 dashboard backend:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_dashboard_shadow_follow_up_resolution.py tests/test_dashboard_app.py -k 'shadow_follow_up_resolution' -q
```

Result:

```text
3 passed, 17 deselected, 2 warnings
```

P18 frontend client/app shell:

```bash
pnpm test -- --run tests/client.test.ts tests/app-shell.test.tsx
```

Result:

```text
Test Files  3 passed (3)
Tests  33 passed (33)
```

P18 frontend build:

```bash
pnpm build
```

Result:

```text
54 modules transformed.
built in 622ms
```

P18 browser smoke:

```bash
pnpm exec playwright test tests/app-smoke.spec.ts
```

Result:

```text
2 passed (1.7s)
```

P18 synthetic smoke:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_p18_shadow_follow_up_resolution_smoke.py tests/test_p17_shadow_follow_up_queue_smoke.py -q
```

Result:

```text
2 passed
```

## Completion Gates

| Gate | Status | Evidence |
| --- | --- | --- |
| P18 consumes P17 follow-up queue artifact | Pass | P18 smoke starts from P17 smoke JSON |
| P18 writes JSON, CSV, and Markdown artifacts | Pass | Smoke artifact paths |
| P18 read model preserves lineage | Pass | P18 read-model tests and smoke |
| P18 dashboard is read-only | Pass | Dashboard tests and browser smoke |
| P18 does not mutate P17 rows | Pass | Separate P18 artifact/read-model tables only |
| P18 has no production write path | Pass | Safety tests and no production controls |

## Residual Risk

- P18 status labels are deterministic defaults. Any actual resolution decision
  that changes research priority still requires operator review.
- Dashboard data depends on P18 read-model import freshness.
- Production promotion remains explicitly out of scope.

## Merge Readiness

P18 is ready for local merge review back to `factor-scoring-daily-pipeline`
after final focused verification on this branch. Main worktree non-P18 dirty
changes should remain protected during merge, following the P16/P17 merge
pattern.
