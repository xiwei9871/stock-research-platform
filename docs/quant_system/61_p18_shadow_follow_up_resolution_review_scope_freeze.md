# P18 Shadow Follow-up Resolution Review Scope Freeze

Date: 2026-06-03

## Status

P18 scope is frozen around **Shadow Follow-up Resolution Review**.

## Why This Scope

P17 records review-only follow-up queue items derived from P16 shadow review
decisions. The next useful step is to record a review-only resolution assessment
for each follow-up item: whether evidence was collected, a research ticket should
be opened, observation should continue, the item should be closed as
deprioritized, or the item remains stale and unresolved.

P18 does not mutate P17 queue rows. It creates independent resolution artifacts
and read-model rows.

## In Scope

- Review-only resolution artifact generation from P17 follow-up queue artifacts.
- Deterministic mapping from P17 follow-up statuses and priority buckets to P18
  resolution statuses.
- JSON/CSV/Markdown P18 resolution artifacts.
- Independent read-model tables under `ops`.
- Import helper and CLI using idempotent upserts.
- Read-only dashboard API and panel.
- Synthetic smoke, runbook, and completion review.

## Out Of Scope

- Mutating or closing P17 follow-up queue rows.
- Assigning owners or connecting to task trackers.
- Production promotion recommendations.
- Automatic watchlist writes.
- Writing `watchlist.watchlist_daily_signal`.
- Writing `factor.stock_score_daily`.
- Writing `factor.factor_approval`.
- Changing scoring or ranking logic.
- Changing production watchlist generation logic.
- Scheduler automation.
- Broker, order, execution, account, cash, or position state.
- Treating any P17 or P18 status as production approval.
- Candidate-level order sizing, allocation, or execution planning.

## Allowed Resolution Statuses

- `evidence_collected`
- `research_ticket_opened`
- `continue_observing`
- `deprioritized_closed`
- `stale_unresolved`

These statuses are operator workflow notes only. `research_ticket_opened` means a
separately scoped research task should exist before any production consideration;
it is not a production approval.

## Safety Fields

- `manual_review_required = true`
- `auto_trade_enabled = false`
- `production_watchlist_enabled = false`
- `production_write_enabled = false`

## Boundary

P18 may write local artifacts and independent
`ops.operator_shadow_follow_up_resolution_*` read-model rows. P18 must not write
production watchlist, scoring, approval, scheduler, broker, order, account,
execution, cash, or position state.
