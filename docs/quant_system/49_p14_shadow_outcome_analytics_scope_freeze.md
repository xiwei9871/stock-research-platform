# P14 Shadow Outcome Analytics Scope Freeze

Date: 2026-06-01

## Status

P14 scope is frozen around **Shadow Outcome Analytics**.

## Why This Scope

P13 made each P12 shadow watchlist candidate measurable. The next useful step is
to summarize those outcomes by shadow layer and shadow status, not to rank
individual candidates or promote production watchlist logic.

## In Scope

- Group analytics by `shadow_layer` and `shadow_status`.
- JSON/CSV/Markdown analytics artifacts.
- Read-model tables under `ops`.
- Import helper and CLI using idempotent upserts.
- Read-only dashboard API and panel.
- Synthetic smoke, runbook, and completion review.

## Out Of Scope

- Candidate-level ranking diagnostics.
- Promotion recommendations.
- Aggregation by proposal, replay run, P9 analytics run, sector, industry, or asset.
- Writing `watchlist.watchlist_daily_signal`.
- Writing `factor.stock_score_daily`.
- Writing `factor.factor_approval`.
- Changing ranking/scoring logic.
- Changing production watchlist generation logic.
- Scheduler automation.
- Broker, order, execution, account, cash, or position state.
- Treating P14 analytics as production approval.

## Safety Fields

- `manual_review_required = true`
- `auto_trade_enabled = false`
- `production_watchlist_enabled = false`
- `production_write_enabled = false`
