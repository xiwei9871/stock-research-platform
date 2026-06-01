# P16 Shadow Review Decision Packet Scope Freeze

Date: 2026-06-02

## Status

P16 scope is frozen around **Shadow Review Decision Packet**.

## Why This Scope

P15 records manual operational review of P14 shadow outcome analytics groups.
The next useful step is to preserve the operator's next-step decision for each
reviewed group as an auditable packet.

P16 does not promote shadow groups into production. It translates P15 review
status into conservative decision work items:

- keep observing a shadow group
- request more data or data-quality follow-up
- open a separately scoped research follow-up
- deprioritize a weak shadow group

## In Scope

- Review-only decision packet generation from P15 review artifacts.
- Deterministic mapping from P15 review statuses to P16 decision statuses.
- JSON/CSV/Markdown P16 decision artifacts.
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
- Treating any P15 or P16 status as production approval.
- Candidate-level order sizing, allocation, or execution planning.

## Allowed Decision Statuses

- `continue_shadow_observation`
- `request_more_data`
- `open_research_follow_up`
- `deprioritize_shadow_group`

These statuses are operator workflow notes only. `open_research_follow_up` means
the group deserves a separately scoped research task; it does not approve
production watchlist, scoring, scheduler, or trading changes.

## Safety Fields

- `manual_review_required = true`
- `auto_trade_enabled = false`
- `production_watchlist_enabled = false`
- `production_write_enabled = false`

## Boundary

P16 may write local artifacts and independent `ops.operator_shadow_review_*`
read-model rows. P16 must not write production watchlist, scoring, approval,
scheduler, broker, order, account, execution, cash, or position state.
