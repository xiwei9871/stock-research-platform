# P7 Completion Review

Date: 2026-05-30

## Status

P7 is complete for the first scoped pass.

Scope covered: **Operator Decision Feedback Loop**.

P7 stayed inside the scope from:

- `docs/quant_system/28_p7_operator_feedback_loop_scope_freeze.md`

## Delivered Capabilities

### P7-0 Scope Freeze

Delivered:

- `docs/quant_system/28_p7_operator_feedback_loop_scope_freeze.md`

Decision:

- P7 records review decisions and evidence.
- P7 stays review-only.
- P7 does not add broker, order, execution, account, cash, or live trading
  paths.

### P7-1 Decision Journal Artifact Contract

Delivered:

- `src/stock_research/operator_decision/journal.py`
- `tests/test_operator_decision_journal.py`

Capabilities:

- Builds decision journal payloads.
- Writes JSON, CSV, and Markdown artifacts.
- Supports empty review sessions as `no_decisions_recorded`.
- Enforces allowed labels:
  - `observe`
  - `candidate`
  - `caution`
  - `remove`
  - `no_action`
- Requires evidence references for non-empty decisions.
- Rejects execution-like fields.

### P7-2 Decision Journal CLI

Delivered:

- CLI command:
  - `p7-decision-journal`
- CLI tests in:
  - `tests/test_factor_cli.py`

Capabilities:

- Reads operator decision CSV input.
- Writes decision journal JSON/CSV/Markdown.
- Prints stable artifact paths.
- Returns non-zero for invalid labels or unsafe fields.

### P7-3 Decision Journal Read Model

Delivered:

- `src/stock_research/operator_decision/read_model.py`
- Read-model schema:
  - `ops.operator_review_session`
  - `ops.operator_decision_event`
- CLI command:
  - `p7-import-decision-journal`
- Tests:
  - `tests/test_operator_decision_read_model.py`
  - `tests/test_schema.py`
  - `tests/test_factor_cli.py`

Capabilities:

- Loads decision journal artifacts into compact read-model rows.
- Supports one file or directory import.
- Upserts sessions and events.
- Preserves evidence paths and source artifact paths.
- Rejects unsafe execution fields before import.

### P7-4 Dashboard Read-Only Decision History

Delivered:

- Backend:
  - `src/stock_research/dashboard/decisions.py`
  - `GET /api/assets/{asset_id}/decisions`
- Frontend:
  - `dashboard/src/components/DecisionHistoryPanel.tsx`
  - dashboard inspector integration
- Tests:
  - `tests/test_dashboard_decisions.py`
  - `tests/test_dashboard_app.py`
  - `dashboard/tests/client.test.ts`
  - `dashboard/tests/app-shell.test.tsx`
  - `dashboard/tests/app-smoke.spec.ts`

Capabilities:

- Shows read-only decision history for the selected asset.
- Handles empty decision history.
- Keeps dashboard free of write forms, order tickets, broker widgets, or
  execution actions.

### P7-5 Runbook And Smoke

Delivered:

- `docs/quant_system/29_p7_operator_feedback_loop_runbook.md`
- `docs/quant_system/30_p7_completion_review.md`

Smoke result:

```text
p7_decision_journal|status|review_recorded
p7_decision_journal|json|/tmp/stock_research_p7_smoke/output/operator_decision_journal_2026-05-30_p7-smoke.json
p7_decision_journal|csv|/tmp/stock_research_p7_smoke/output/operator_decision_journal_2026-05-30_p7-smoke.csv
p7_decision_journal|markdown|/tmp/stock_research_p7_smoke/output/operator_decision_journal_2026-05-30_p7-smoke.md
```

Read-model loader smoke:

```text
p7_smoke_read_model|session|p7-smoke|decisions|2
p7_smoke_read_model|events|2
p7_smoke_read_model|labels|candidate,caution
```

## Acceptance Criteria Review

| Criterion | Status | Evidence |
| --- | --- | --- |
| Operator can write structured decision artifacts | Pass | `p7-decision-journal`; P7 smoke |
| Empty review session is valid | Pass | `tests/test_operator_decision_journal.py` |
| Invalid decision labels are rejected | Pass | `tests/test_operator_decision_journal.py`; CLI tests |
| Execution-like fields are rejected | Pass | journal/read-model tests |
| Decision journals can be imported into read models | Pass | `p7-import-decision-journal`; read-model tests |
| Import is idempotent by upsert | Pass | SQL uses `ON CONFLICT`; importer tests |
| Dashboard shows decision history read-only | Pass | dashboard backend/frontend/smoke tests |
| No trading execution path was introduced | Pass | Safety review below |

## Verification Evidence

P7-focused Python verification:

```bash
.venv/bin/pytest tests/test_operator_decision_journal.py tests/test_operator_decision_read_model.py tests/test_dashboard_decisions.py tests/test_dashboard_app.py tests/test_factor_cli.py tests/test_schema.py -q
```

Result:

```text
186 passed, 2 warnings
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
Vitest: 14 passed
Vite build: passed
Playwright: 2 passed
```

Current full-regression note:

- Unfiltered full-regression is not used as the P7-5 completion gate while
  unrelated non-P7 dirty files are present in the workspace.
- The P7-focused Python suite above covers P7 artifact contracts, P7 read models,
  dashboard decision history, CLI wiring, and schema wiring.

The warnings are existing `py_mini_racer` deprecation warnings.

## Safety Review

- No broker adapter was added.
- No order placement was added.
- No order ticket UI was added.
- No account, cash, order, execution, or broker ledger table was added.
- No live notification send was enabled.
- No scheduler behavior was changed.
- Dashboard decision history is read-only.
- Decision journal artifacts force `manual_review_required = true`.
- Decision journal artifacts force `auto_trade_enabled = false`.
- Import rejects execution-like fields.

## Known Non-P7 Workspace Files

The workspace contains unrelated non-P7 dirty files. They are not part of this
completion review and should be handled separately:

- `src/stock_research/cli.py`
- `src/stock_research/watchlist/effectiveness.py`
- `tests/test_watchlist_cli.py`
- `tests/test_watchlist_effectiveness.py`
- `src/stock_research/strong_winner_topn_attribution.py`
- `tests/test_risk_watch_split.py`
- `tests/test_strong_winner_topn_attribution.py`

## Completion Definition

P7 is complete when an operator can:

1. Record structured decisions through CLI artifacts.
2. Validate those decisions against review-only safety rules.
3. Import decision journals into durable read models.
4. View decision history in the dashboard without editing platform state.
5. Run documented smoke and verification commands.

All five conditions are met for the first scoped pass.

## Recommended Next Phase

Recommended P8 direction: **Decision Outcome Review**.

Reasoning:

- P7 records what the operator decided and why.
- The next useful loop is measuring what happened afterward:
  - did `candidate` decisions outperform `observe`;
  - did `caution` avoid drawdown;
  - did follow-up items get resolved;
  - which evidence sources were most useful.

P8 should remain research/review-only unless a new scope explicitly approves a
trading-adjacent expansion.
