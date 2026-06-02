# P12 Shadow Watchlist Experiment Scope Freeze

Date: 2026-06-01

## Status

P12 scope is frozen around **Shadow Watchlist Experiment Read Model**.

## Why This Scope

P11 produced offline replay evidence for approved P10 proposals. The next useful
step is a review-only shadow watchlist candidate layer, not a production
watchlist write path.

P12 answers questions such as:

- Which passed P11 replay result produced a shadow candidate?
- Which P10 proposal and P9 analytics evidence support the candidate?
- Which asset, layer, and reason should be observed in shadow review?
- Which artifacts prove the candidate should remain review-only?

P12 does not make any candidate tradable or production-ready.

## In Scope

- Shadow watchlist candidate artifact contract.
- CLI to generate JSON/CSV/Markdown artifacts from P11 replay evidence.
- Read-model tables under `ops`.
- Import helper and CLI using idempotent upserts.
- Read-only dashboard API and panel.
- Synthetic smoke, runbook, and completion review.

## Out Of Scope

- Writing `watchlist.watchlist_daily_signal`.
- Writing `factor.stock_score_daily`.
- Writing `factor.factor_approval`.
- Changing ranking/scoring logic.
- Changing production watchlist generation logic.
- Scheduler automation.
- Broker, order, execution, account, cash, or position state.
- Treating `shadow_ready` or `shadow_observe` as production approval.
- Fixing unrelated watchlist, factor-pipeline, trend-discovery, or
  strong-winner dirty files currently outside P12 scope.

## Safety Fields

- `manual_review_required = true`
- `auto_trade_enabled = false`
- `production_watchlist_enabled = false`
- `production_write_enabled = false`

## Acceptance

- P12 artifacts preserve P11 replay, P10 proposal, and P9 analytics references.
- P12 read-model rows are stored separately from production watchlist tables.
- Dashboard surfaces are read-only and provide no promotion or trading controls.
- P12 commits do not include unrelated non-P12 workspace changes.
