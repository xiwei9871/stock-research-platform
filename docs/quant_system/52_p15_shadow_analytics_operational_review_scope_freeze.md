# P15 Shadow Analytics Operational Review Scope Freeze

Date: 2026-06-01

## Status

P15 scope is frozen around **Shadow Analytics Operational Review**.

## Why This Scope

P14 made shadow outcome patterns visible by `shadow_layer` and `shadow_status`.
The next useful step is to record a manual operational interpretation of those
group analytics, not to promote groups into production or change scoring.

P15 creates a review packet that answers:

- Which P14 groups need more data?
- Which groups have data-quality concerns?
- Which groups should remain under observation?
- Which groups deserve a future separately scoped research question?
- Which groups should be deprioritized for review because evidence or risk is
  weak?

## In Scope

- Review-only operational triage of P14 group analytics.
- Group-level review statuses and evidence notes.
- JSON/CSV/Markdown P15 review artifacts.
- Independent read-model tables under `ops`.
- Import helper and CLI using idempotent upserts.
- Read-only dashboard API and panel.
- Synthetic smoke, runbook, and completion review.

## Out Of Scope

- Candidate-level ranking diagnostics.
- Production promotion recommendations.
- Automatic watchlist writes.
- Writing `watchlist.watchlist_daily_signal`.
- Writing `factor.stock_score_daily`.
- Writing `factor.factor_approval`.
- Changing scoring or ranking logic.
- Changing production watchlist generation logic.
- Scheduler automation.
- Broker, order, execution, account, cash, or position state.
- Treating any P15 review status as production approval.

## Allowed Review Statuses

- `continue_observing`
- `needs_more_data`
- `investigate_data_quality`
- `deprioritize_review`
- `research_follow_up_candidate`

These statuses are manual review notes only. They do not authorize production
watchlist, scoring, approval, scheduler, or trading changes.

## Safety Fields

- `manual_review_required = true`
- `auto_trade_enabled = false`
- `production_watchlist_enabled = false`
- `production_write_enabled = false`

## Boundary

P15 may write local artifacts and independent `ops.operator_shadow_analytics_*`
read-model rows. P15 must not write production watchlist, scoring, approval,
scheduler, broker, order, account, execution, cash, or position state.
