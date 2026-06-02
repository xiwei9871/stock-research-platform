# P13 Shadow Watchlist Outcome Tracking Scope Freeze

Date: 2026-06-01

## Status

P13 scope is frozen around **Shadow Watchlist Outcome Tracking**.

## Why This Scope

P12 produced review-only shadow watchlist candidates. The next useful step is to
measure each candidate's later market outcome, not to promote candidates or
write production watchlist state.

## In Scope

- Per-shadow-candidate outcome metric contract.
- CLI to generate JSON/CSV/Markdown outcome artifacts from P12 candidates and
  daily bars.
- Read-model tables under `ops`.
- Import helper and CLI using idempotent upserts.
- Read-only dashboard API and panel.
- Synthetic smoke, runbook, and completion review.

## Out Of Scope

- Aggregating outcomes across layers, statuses, proposals, or replay sources.
- Promotion recommendations.
- Writing `watchlist.watchlist_daily_signal`.
- Writing `factor.stock_score_daily`.
- Writing `factor.factor_approval`.
- Changing ranking/scoring logic.
- Changing production watchlist generation logic.
- Scheduler automation.
- Broker, order, execution, account, cash, or position state.
- Treating P13 outcome status as production approval.

## Safety Fields

- `manual_review_required = true`
- `auto_trade_enabled = false`
- `production_watchlist_enabled = false`
- `production_write_enabled = false`
