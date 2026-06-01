# P17 Shadow Decision Follow-up Queue Scope Freeze

Date: 2026-06-02

## Status

P17 scope is frozen around **Shadow Decision Follow-up Queue**.

## Why This Scope

P16 records conservative operator workflow decisions for P15 shadow analytics
review groups. The next useful step is to turn those decisions into an auditable
review-only follow-up queue so operators can see which groups need continued
observation, more data, a separately scoped research follow-up, or lower review
priority.

P17 does not promote shadow groups into production. It records follow-up work
items derived from P16 decision groups.

## In Scope

- Review-only follow-up queue generation from P16 decision artifacts.
- Deterministic mapping from P16 decision statuses to P17 follow-up statuses,
  priority buckets, and required inputs.
- JSON/CSV/Markdown P17 follow-up artifacts.
- Independent read-model tables under `ops`.
- Import helper and CLI using idempotent upserts.
- Read-only dashboard API and panel.
- Synthetic smoke, runbook, and completion review.

## Out Of Scope

- Production promotion recommendations.
- Automatic watchlist writes.
- Writing `watchlist.watchlist_daily_signal`.
- Writing `factor.stock_score_daily`.
- Writing `factor.factor_approval`.
- Changing scoring or ranking logic.
- Changing production watchlist generation logic.
- Scheduler automation.
- Broker, order, execution, account, cash, or position state.
- Treating any P16 or P17 status as production approval.
- Candidate-level order sizing, allocation, or execution planning.
- Closing or mutating P16 decision rows.

## Allowed Follow-up Statuses

- `observe_shadow_group`
- `collect_more_evidence`
- `open_research_ticket`
- `deprioritized`

These statuses are operator workflow notes only. `open_research_ticket` means a
separately scoped research task should be opened before any production
consideration; it is not a production approval.

## Safety Fields

- `manual_review_required = true`
- `auto_trade_enabled = false`
- `production_watchlist_enabled = false`
- `production_write_enabled = false`

## Boundary

P17 may write local artifacts and independent
`ops.operator_shadow_follow_up_*` read-model rows. P17 must not write production
watchlist, scoring, approval, scheduler, broker, order, account, execution,
cash, or position state.
