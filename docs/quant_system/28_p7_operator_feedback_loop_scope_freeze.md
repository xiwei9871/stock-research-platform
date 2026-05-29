# P7 Operator Feedback Loop Scope Freeze

Date: 2026-05-30

## Status

P7 scope is frozen around **Operator Decision Feedback Loop**.

P7 starts after:

- P6 dashboard workbench completion review:
  - `docs/quant_system/27_p6_completion_review.md`
- Dashboard workbench merge into `factor-scoring-daily-pipeline`:
  - `fe4dc8c Merge branch 'dashboard-workbench' into factor-scoring-daily-pipeline`
- Push of `factor-scoring-daily-pipeline` to origin:
  - local and remote head both at `fe4dc8c`

## Why This Scope

P3 made review outputs queryable. P4 made daily refresh repeatable. P5 made
operational status visible through notification artifacts. P6 gave operators a
read-only dashboard workbench for charts, TopN, watchlists, scores, and reports.

The next bottleneck is feedback capture. After an operator reviews the dashboard
and daily artifacts, the platform still needs a durable way to record:

- which assets were reviewed;
- what decision label was assigned;
- what evidence supported the decision;
- whether follow-up was required;
- how later outcomes should be compared with the original decision.

P7 therefore builds the first review-only feedback loop. It does not turn the
dashboard into a trading terminal, and it does not connect to a broker. It turns
human review into structured, auditable research data.

## Product Positioning

P7 is a **decision journal and review loop**, not an execution system.

The operator-facing workflow is:

1. Review P6 dashboard outputs.
2. Record review decisions for selected assets, watchlist items, reports, or
   portfolio states.
3. Persist those decisions as artifacts and compact read models.
4. Make the decisions visible to later reports, dashboard views, and runbooks.
5. Compare future outcomes against the original decision in later phases.

P7 output may support future trade advice, but it must not execute trades or
present an order workflow.

## Architecture

P7 keeps feedback capture separate from trading execution.

Artifact layer:

- Writes local JSON/CSV/Markdown decision-journal artifacts.
- Keeps evidence paths and source IDs explicit.
- Preserves manual-review semantics.

Read-model layer:

- Adds compact queryable records for review sessions and decision events.
- Stores only operator decision metadata, evidence references, and review status.
- Does not duplicate raw dashboard payloads or generated report bodies.

Dashboard integration:

- P6 dashboard may display decision history when the read model is available.
- Dashboard writes remain out of scope unless separately approved.
- A CLI-first artifact and import path comes before any UI editing surface.

Operational integration:

- P4/P5 runbooks can include a post-review recording step.
- Notification live-send remains out of scope.
- Scheduler execution remains unchanged.

## P7 In Scope

### P7-0 Scope Freeze And Baseline Review

Goal: freeze the P7 boundary before writing implementation code.

Deliver:

- This scope freeze document.
- Baseline review of current decision-adjacent modules:
  - `src/stock_research/trade_advice/advice.py`
  - `src/stock_research/simulation/virtual_portfolio.py`
  - `src/stock_research/p3/operator_export.py`
  - `src/stock_research/dashboard/`
- Confirmation that P7 starts from a clean mainline after P6 merge.

Acceptance:

- P7 explicitly stays review-only.
- P7 does not depend on Alpha191 work.
- P7 does not require a dashboard write surface.

### P7-1 Decision Journal Artifact Contract

Goal: define a stable artifact format for operator decisions.

Deliver:

- JSON schema shape for a decision journal run.
- CSV row shape for decision events.
- Markdown review summary.
- Validation for required fields:
  - `review_date`
  - `review_session_id`
  - `asset_id`
  - `decision_label`
  - `evidence_artifact_id`
  - `evidence_path`
  - `requires_follow_up`
  - `manual_review_required`
  - `auto_trade_enabled`

Candidate decision labels:

- `observe`
- `candidate`
- `caution`
- `remove`
- `no_action`

Boundary:

- Do not use buy/sell/order terms as primary labels.
- Do not store broker, account, cash, order, or execution fields.
- Do not store secrets, webhook URLs, or credentials.

Acceptance:

- Empty journals are valid and explicitly marked as `no_decisions_recorded`.
- Every non-empty decision row cites an evidence artifact or source path.
- `manual_review_required` is always true.
- `auto_trade_enabled` is always false.

### P7-2 Decision Journal CLI

Goal: let an operator create review artifacts without opening a database client.

Deliver:

- CLI command to build a decision journal from a CSV input file.
- CLI command options for:
  - review date
  - session ID
  - reviewer ID
  - source artifact root
  - output directory
- Validation errors for missing evidence, invalid labels, or execution-like
  fields.
- Tests for valid journals, empty journals, invalid labels, and unsafe fields.

Boundary:

- CLI writes local artifacts only.
- CLI does not mutate watchlist, factor, simulation, dashboard, notification, or
  trading state.

Acceptance:

- The command writes JSON, CSV, and Markdown outputs.
- Output filenames include `review_date` and `review_session_id`.
- Invalid input exits non-zero with actionable validation messages.

### P7-3 Decision Journal Read Model

Goal: make decision journals queryable across days and sessions.

Deliver:

- Schema for review sessions.
- Schema for decision events.
- Import helper for one artifact or a directory of artifacts.
- CLI command to import journal artifacts.
- Tests for schema DDL, idempotent upserts, source path preservation, and
  repeated imports.

Candidate tables:

- `ops.operator_review_session`
- `ops.operator_decision_event`

Boundary:

- Store compact metadata only.
- Keep generated artifacts as the audit source.
- Do not create order, execution, account, cash, or live position tables.

Acceptance:

- Imported rows preserve evidence references and source artifact paths.
- Re-importing the same artifact is idempotent.
- Unsafe execution fields are rejected before import.

### P7-4 Dashboard Read-Only Decision History

Goal: expose decision history to the dashboard without making the dashboard an
editing or execution surface.

Deliver:

- Read-only API endpoint for recent decision events by asset and date range.
- Optional dashboard panel or asset-detail section showing decision history.
- Frontend empty/loading/error states.
- Unit and browser smoke coverage for read-only rendering.

Boundary:

- No dashboard form for writing decisions in P7.
- No order ticket, broker widget, or action button that implies execution.
- No live-send or scheduler mutation from the dashboard.

Acceptance:

- Dashboard can show decision history for an asset.
- Dashboard remains usable when no decision history exists.
- Browser smoke confirms no horizontal overflow on the supported mobile viewport.

### P7-5 Runbook, Smoke, And Completion Review

Goal: make the feedback loop operationally repeatable.

Deliver:

- Daily runbook update with a post-dashboard review step.
- Smoke fixture for one review session and multiple decision labels.
- Operational smoke command sequence.
- P7 completion review document.

Acceptance:

- Full Python regression passes.
- Dashboard unit/build/e2e checks pass if dashboard files change.
- P7 smoke writes artifacts and imports them into read models.
- Completion review records commands, results, residual risks, and out-of-scope
  items.

## Out Of Scope For P7

- Broker integration.
- Automatic order placement.
- Order ticket UI.
- Real order, execution, account, cash, or broker ledger tables.
- Live notification send enablement.
- Scheduler installation or scheduler behavior changes.
- TradingView external service integration.
- TradingView private Charting Library.
- Alpha191 implementation, validation, or promotion.
- Replacing P1/P2/P3/P4/P5/P6 artifact contracts.
- Dashboard write/edit forms unless a later scope explicitly approves them.

## Execution Order

1. P7-0: commit this scope freeze and confirm clean baseline.
2. P7-1: implement decision journal artifact contract and validation.
3. P7-2: add CLI artifact writer with tests.
4. P7-3: add read model schema and artifact import path.
5. P7-4: add read-only dashboard decision history only if P7-1 through P7-3
   are stable.
6. P7-5: run smoke, update runbook, and write completion review.

## Review Gates

Before P7-2:

- Artifact format must be stable enough for runbook use.
- Unsafe execution-like fields must be rejected.

Before P7-3:

- JSON and CSV artifacts must round-trip in tests.
- Decision labels must be normalized.

Before P7-4:

- Read model import must be idempotent.
- API shape must be read-only and dashboard-friendly.

Before P7 completion:

- P7 smoke must prove the operator can record and re-query at least one review
  session.
- Completion review must explicitly state that no trading execution path was
  introduced.

## Verification Plan

Expected verification commands as P7 work progresses:

```bash
.venv/bin/pytest tests/test_operator_decision_journal.py -q
.venv/bin/pytest tests/test_operator_decision_read_model.py -q
.venv/bin/pytest tests/test_factor_cli.py -k operator_decision -q
.venv/bin/pytest -q
```

If P7-4 changes dashboard files:

```bash
cd dashboard
pnpm test
pnpm build
pnpm test:e2e
```

## Completion Definition

P7 is complete when an operator can:

1. Review P6 dashboard and existing artifacts.
2. Record structured decisions through a CLI artifact workflow.
3. Import those decisions into durable read models.
4. Query or view decision history without editing platform state.
5. Run a documented smoke test proving the loop works end to end.

P7 remains incomplete if the only output is a document or if decisions cannot be
reused by later reports, dashboard reads, or operational review.
