# P14 Shadow Outcome Analytics Design

Date: 2026-06-01

## Purpose

P14 summarizes P13 shadow watchlist outcomes by `shadow_layer` and
`shadow_status`. It turns per-candidate shadow outcome rows into review-only
group analytics so the operator can see which shadow layers and statuses have
better later market behavior.

P14 does not rank individual candidates, recommend promotion, write production
watchlist signals, mutate factor scores, approve factors, schedule jobs, or
create trading instructions.

## Current Context

P12 produced review-only shadow watchlist candidates from P11 replay evidence.
P13 measured later per-candidate outcomes and stored them in:

- `ops.operator_shadow_watchlist_outcome_run`
- `ops.operator_shadow_watchlist_outcome_candidate`

Each P13 candidate outcome preserves source references back to P12, P11, P10,
and P9. P13 completion explicitly states that outcome status means data
completeness, not production approval.

P14 starts from P13 outcome rows and asks a narrower question: by shadow layer
and shadow status, what aggregate outcome pattern appears?

The current workspace also contains unrelated dirty and untracked trend,
mid-trend, strong-winner, watchlist, and factor-pipeline files. P14 must stay
isolated from those changes unless the user explicitly asks to reconcile them.

## Scope

P14 implements a read-only shadow outcome analytics layer.

In scope:

- P14 scope freeze document.
- Analytics contract grouped by `shadow_layer` and `shadow_status`.
- CLI to generate JSON/CSV/Markdown analytics artifacts from P13 outcome JSON
  or CSV input.
- Independent `ops` read-model schema and importer.
- Read-only dashboard API and panel.
- Synthetic smoke, runbook, and completion review.

Out of scope:

- Candidate-level ranking diagnostics.
- Promotion recommendations.
- Aggregation by proposal, replay run, P9 analytics run, sector, industry, or
  asset.
- Writing `watchlist.watchlist_daily_signal`.
- Writing `factor.stock_score_daily`.
- Writing `factor.factor_approval`.
- Changing production watchlist generation logic.
- Changing ranking or scoring logic.
- Scheduler automation.
- Broker, order, execution, account, cash, or position state.
- Treating any P14 analytics result as production approval.

## Recommended Architecture

Use a new artifact family and independent `ops` read model:

- Artifact module:
  `stock_research.operator_decision.shadow_outcome_analytics`
- Read model module:
  `stock_research.operator_decision.shadow_outcome_analytics_read_model`
- Smoke module:
  `stock_research.operator_decision.p14_smoke`
- Dashboard backend module:
  `stock_research.dashboard.shadow_outcome_analytics`
- Dashboard component:
  `ShadowOutcomeAnalyticsPanel`

Candidate tables:

- `ops.operator_shadow_watchlist_outcome_analytics_run`
- `ops.operator_shadow_watchlist_outcome_analytics_group`

This mirrors P9 decision outcome analytics, but the measured input is the P13
shadow watchlist outcome candidate rather than a P8 operator decision outcome.

## Data Flow

1. Load P13 shadow outcome rows from a JSON artifact or details CSV.
2. Validate review-only safety fields and required source lineage.
3. Keep rows within the requested review date range.
4. Group rows by:
   - `shadow_layer`
   - `shadow_status`
5. Compute group-level sample and horizon metrics.
6. Write JSON, group CSV, and Markdown analytics artifacts.
7. Import analytics artifacts into compact `ops` read-model tables.
8. Dashboard shows read-only group analytics by date range.

No step writes to production watchlist, scoring, approval, scheduler, or trading
tables.

## Analytics Contract

Each analytics run should preserve:

- `run_id`
- `review_start_date`
- `review_end_date`
- `status`
- `group_by`
- `group_count`
- `manual_review_required`
- `auto_trade_enabled`
- `production_watchlist_enabled`
- `production_write_enabled`
- artifact paths

Each group row should preserve:

- `analytics_group_id`
- `run_id`
- `review_start_date`
- `review_end_date`
- `group_key`
- `shadow_layer`
- `shadow_status`
- `sample_count`
- `complete_count`
- `insufficient_data_count`
- `source_p12_shadow_run_count`
- `source_p11_replay_run_count`
- `source_p10_proposal_run_count`
- `source_p9_analytics_run_count`
- `horizon_metrics`
- `manual_review_required`
- `auto_trade_enabled`
- `production_watchlist_enabled`
- `production_write_enabled`

Horizon metrics for each available horizon should include:

- `forward_return_mean`
- `forward_return_median`
- `forward_win_rate`
- `max_high_return_mean`
- `max_low_drawdown_mean`
- `max_low_drawdown_worst`

The first P14 pass should use the horizons already present in P13 artifacts,
typically:

- `1d`
- `3d`
- `5d`
- `10d`
- `20d`
- `60d`

Safety fields:

- `manual_review_required = true`
- `auto_trade_enabled = false`
- `production_watchlist_enabled = false`
- `production_write_enabled = false`

The contract rejects:

- missing `shadow_layer`
- missing `shadow_status`
- missing P12/P11/P10/P9 source references
- malformed metric maps
- unsafe execution-like fields
- `auto_trade_enabled = true`
- `production_watchlist_enabled = true`
- `production_write_enabled = true`

Rows with `outcome_status = insufficient_data` contribute to sample and
insufficient counts, but unavailable horizon metrics are ignored rather than
zero-filled.

## CLI Design

Artifact creation:

```bash
stock-research p14-shadow-outcome-analytics \
  --shadow-outcomes-json outputs/p13/2026-08-29/operator_shadow_outcomes_2026-08-29.json \
  --run-id p14-shadow-outcome-analytics-2026-06-30-2026-08-29 \
  --review-start-date 2026-06-30 \
  --review-end-date 2026-08-29 \
  --output-dir outputs/p14/2026-08-29
```

Read-model import:

```bash
stock-research p14-import-shadow-outcome-analytics \
  --path outputs/p14/2026-08-29/operator_shadow_outcome_analytics_2026-06-30_2026-08-29.json
```

Both commands should print stable machine-readable summary lines following the
P9 through P13 command patterns.

## Dashboard Design

Add a read-only dashboard panel for P14 shadow outcome analytics.

The panel should show:

- `shadow_layer`
- `shadow_status`
- sample count
- complete count
- insufficient data count
- source run coverage counts
- selected horizon forward return mean
- selected horizon forward win rate
- selected horizon worst drawdown

The panel must support loading, empty, and missing-table states through existing
dashboard patterns. It must not include editing, promotion controls, watchlist
write controls, score controls, trade controls, broker controls, order UI, or
scheduler controls.

## Testing Strategy

Use TDD for implementation.

Python tests:

- contract groups by `shadow_layer` and `shadow_status`
- contract computes counts and horizon metrics
- contract ignores unavailable horizon metrics instead of zero-filling
- contract rejects unsafe or production-enabled rows
- CLI creates review-only artifacts
- read model imports one artifact and directories idempotently
- schema contains P14 read-model tables and indexes
- dashboard backend returns read-only analytics rows
- dashboard backend returns an empty list when P14 tables are missing
- smoke creates P13 input artifacts, P14 analytics artifacts, and read-model
  rows

Dashboard tests:

- API client fetches shadow outcome analytics
- app shell renders the panel
- empty/loading states render
- Playwright smoke verifies desktop and mobile without horizontal overflow
- tests assert no promotion, trade, watchlist write, or score mutation controls
  are present

## Phase Breakdown

P14-0 Scope Freeze:

- Write scope freeze and baseline review.
- Preserve non-P14 dirty changes.

P14-1 Shadow Outcome Analytics Contract:

- Implement group analytics builder.
- Validate source references, metric maps, and safety fields.
- Handle insufficient data without zero-filling unavailable metrics.

P14-2 Shadow Outcome Analytics Artifact CLI:

- Add `p14-shadow-outcome-analytics`.
- Generate JSON/CSV/Markdown artifacts.

P14-3 Shadow Outcome Analytics Read Model:

- Add schema tables.
- Add importer and `p14-import-shadow-outcome-analytics`.
- Keep analytics group IDs run-scoped and idempotent.

P14-4 Dashboard Read-Only Analytics View:

- Add backend endpoint and frontend panel.
- Handle missing P14 tables as an empty read-only state.
- Add browser smoke coverage.

P14-5 Runbook, Smoke, Completion Review:

- Add synthetic smoke that starts from P13 smoke outputs.
- Write runbook and completion review.
- Record verification evidence.

## Acceptance Criteria

- P14 artifacts preserve P13 source lineage back to P12, P11, P10, and P9.
- P14 artifacts force review-only safety fields.
- P14 groups only by `shadow_layer` and `shadow_status`.
- P14 computes group counts and horizon metrics without zero-filling missing
  horizon data.
- P14 read-model imports are idempotent.
- Dashboard can show shadow outcome analytics for a selected date range.
- Dashboard remains usable when no P14 analytics exist or P14 tables are
  missing.
- P14 adds no candidate ranking, promotion recommendation, production watchlist
  write path, factor score mutation, factor approval mutation, scheduler
  automation, or trading execution path.
