# P17 Shadow Decision Follow-up Queue Completion Review

Date: 2026-06-02

## Status

P17 is complete for the first scoped pass.

Scope covered:

- `docs/quant_system/58_p17_shadow_decision_follow_up_queue_scope_freeze.md`

## Delivered Capabilities

### P17-0 Scope Freeze

Delivered:

- `docs/quant_system/58_p17_shadow_decision_follow_up_queue_scope_freeze.md`
- `docs/superpowers/specs/2026-06-02-p17-shadow-decision-follow-up-queue-design.md`
- `docs/superpowers/plans/2026-06-02-p17-shadow-decision-follow-up-queue.md`

Boundary:

- P17 consumes P16 review-only shadow review decision artifacts.
- P17 records review-only follow-up queue items by P16 decision group.
- P17 does not recommend production promotion, write production watchlists,
  mutate factor scores, schedule jobs, or create trading actions.

### P17-1 Shadow Follow-up Queue Contract

Delivered:

- `src/stock_research/operator_decision/shadow_follow_up_queue.py`
- `tests/test_operator_shadow_follow_up_queue.py`

Capabilities:

- Maps P16 decision statuses to P17 follow-up statuses.
- Writes JSON, items CSV, and Markdown artifacts.
- Preserves P16, P15, and P14 lineage.
- Rejects unsafe execution-like fields and unsafe safety flags.

### P17-2 Shadow Follow-up Queue CLI

Delivered:

- `stock-research p17-shadow-follow-up-queue`
- CLI tests in `tests/test_factor_cli.py`

Capabilities:

- Builds P17 artifacts from P16 decision JSON.
- Emits artifact paths and item counts.
- Preserves the review-only safety boundary.

### P17-3 Shadow Follow-up Queue Read Model

Delivered:

- `src/stock_research/operator_decision/shadow_follow_up_queue_read_model.py`
- Read-model schema:
  - `ops.operator_shadow_follow_up_run`
  - `ops.operator_shadow_follow_up_item`
- CLI command:
  - `p17-import-shadow-follow-up-queue`
- Tests:
  - `tests/test_operator_shadow_follow_up_queue_read_model.py`
  - `tests/test_schema.py`
  - `tests/test_factor_cli.py`

Capabilities:

- Imports one follow-up artifact or a directory of artifacts.
- Upserts follow-up runs and item rows idempotently.
- Preserves source P16 decision, P15 review, and P14 analytics lineage.

### P17-4 Dashboard Read-Only Shadow Follow-up Queue

Delivered:

- Backend:
  - `src/stock_research/dashboard/shadow_follow_up_queue.py`
  - `GET /api/shadow-follow-up-queue`
- Frontend dashboard integration.
- Tests:
  - `tests/test_dashboard_shadow_follow_up_queue.py`
  - `tests/test_dashboard_app.py`
  - dashboard client, build, and e2e coverage.

Capabilities:

- Shows read-only grouped P17 follow-up rows.
- Handles loading, empty, and missing-table states.
- Adds no edit, promotion, score, production watchlist, trade, broker, order, or
  scheduler UI.

### P17-5 Smoke, Runbook, And Completion Review

Delivered:

- `src/stock_research/operator_decision/p17_smoke.py`
- `tests/test_p17_shadow_follow_up_queue_smoke.py`
- `docs/quant_system/59_p17_shadow_decision_follow_up_queue_runbook.md`
- This completion review.

TDD evidence:

```text
RED: /Users/xiwei/stock_research/.venv/bin/pytest tests/test_p17_shadow_follow_up_queue_smoke.py -q
Result: failed during collection with ModuleNotFoundError: No module named 'stock_research.operator_decision.p17_smoke'

GREEN: /Users/xiwei/stock_research/.venv/bin/pytest tests/test_p17_shadow_follow_up_queue_smoke.py tests/test_p16_shadow_review_decisions_smoke.py -q
Result: 2 passed in 0.37s
```

Smoke result:

```text
p17_smoke|p16_shadow_review_decisions|/tmp/stock_research_p17_smoke/p16/operator_shadow_review_decisions_2026-08-29.json
p17_smoke|p17_shadow_follow_up_queue|/tmp/stock_research_p17_smoke/p17/operator_shadow_follow_up_queue_2026-08-29.json
p17_smoke|items_csv|/tmp/stock_research_p17_smoke/p17/operator_shadow_follow_up_queue_2026-08-29_items.csv
p17_smoke|markdown|/tmp/stock_research_p17_smoke/p17/operator_shadow_follow_up_queue_2026-08-29.md
p17_smoke|source_decision_group_count|1
p17_smoke|follow_up_item_count|1
p17_smoke|read_model_items|1
p17_smoke|follow_up_statuses|collect_more_evidence
p17_smoke|priority_buckets|high
p17_smoke|source_p16_decision_runs|p16-smoke-shadow-review-decisions-2026-08-29
p17_smoke|manual_review_required|True
p17_smoke|auto_trade_enabled|False
p17_smoke|production_watchlist_enabled|False
p17_smoke|production_write_enabled|False
```

## Acceptance Criteria Review

| Criterion | Status | Evidence |
| --- | --- | --- |
| P17 smoke starts from P16 smoke artifact | Pass | `p17_smoke|p16_shadow_review_decisions|...` |
| P17 smoke writes JSON, items CSV, and Markdown artifacts | Pass | Smoke output artifact paths |
| Smoke read model contains one item row | Pass | `read_model_items|1` |
| Source and follow-up item counts are one | Pass | `source_decision_group_count|1`, `follow_up_item_count|1` |
| P16 `request_more_data` maps to P17 `collect_more_evidence` | Pass | `follow_up_statuses|collect_more_evidence` |
| Priority bucket is high | Pass | `priority_buckets|high` |
| Artifacts are review-only | Pass | Smoke safety fields |
| No production watchlist/scoring/scheduler/trading mutation added | Pass | Safety review below |

## Verification Evidence

Final verification commands:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_operator_shadow_follow_up_queue.py tests/test_operator_shadow_follow_up_queue_read_model.py tests/test_p17_shadow_follow_up_queue_smoke.py tests/test_schema.py tests/test_factor_cli.py tests/test_dashboard_shadow_follow_up_queue.py tests/test_dashboard_app.py -k 'shadow_follow_up_queue or p17_shadow_follow_up_queue or p17_import_shadow_follow_up_queue or dashboard' -q
cd dashboard && pnpm test
cd dashboard && pnpm build
cd dashboard && pnpm test:e2e
git diff --check
```

Results:

```text
Python: 35 passed, 214 deselected, 2 warnings
Vitest: 31 passed
Vite build: passed
Playwright: 2 passed
git diff --check: passed
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
- No production watchlist signal write path was added.
- No `factor.factor_approval` write path was added.
- P17 remains review-only by P16 decision group.
- `manual_review_required` remains `true`.
- `auto_trade_enabled`, `production_watchlist_enabled`, and
  `production_write_enabled` remain `false`.
