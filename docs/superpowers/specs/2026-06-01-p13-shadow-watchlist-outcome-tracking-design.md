# P13 Shadow Watchlist Outcome Tracking Design

Date: 2026-06-01

## Purpose

P13 measures what happened after P12 shadow watchlist candidates entered the
review-only shadow pool. It turns each P12 candidate into a per-candidate
outcome record with forward returns, upside capture, drawdown, and data
completeness.

P13 does not aggregate shadow performance into recommendations. P14 should cover
shadow outcome analytics. P13 also does not create production watchlist signals,
factor scores, factor approvals, scheduler automation, trades, orders, broker
state, account state, or position state.

## Current Context

P12 records shadow watchlist candidates from passed P11 offline replay evidence.
Each P12 candidate preserves source references back to:

- P11 replay result and replay run
- P10 experiment proposal run
- P9 analytics run
- P12 shadow artifact path

P12 completion explicitly keeps `shadow_ready` and `shadow_observe` as review
states only. P13 starts from those P12 rows and asks whether later market bars
support continued observation.

The current workspace also contains unrelated watchlist, factor-pipeline,
trend-discovery, strong-winner, and mid-trend dirty files. P13 must stay
isolated from those changes unless the user explicitly asks to reconcile them.

## Scope

P13 implements a shadow candidate outcome measurement layer.

In scope:

- P13 scope freeze document.
- Per-shadow-candidate outcome metric contract.
- CLI to generate JSON/CSV/Markdown outcome artifacts from P12 candidates and
  daily bars.
- Read-model schema and importer for shadow outcome runs/results.
- Dashboard read-only shadow outcome view.
- Synthetic smoke, runbook, and completion review.

Out of scope:

- Aggregating shadow outcome performance across layers, statuses, proposals, or
  replay sources.
- Promotion recommendations.
- Writing `watchlist.watchlist_daily_signal`.
- Writing `factor.stock_score_daily`.
- Writing `factor.factor_approval`.
- Changing production watchlist generation logic.
- Changing ranking/scoring logic.
- Scheduler automation.
- Broker, order, execution, account, cash, or position state.
- Treating any P13 outcome as production approval.

## Recommended Architecture

Use an independent `ops` read model and artifact family:

- Artifact module: `stock_research.operator_decision.shadow_outcomes`
- Read model module: `stock_research.operator_decision.shadow_outcomes_read_model`
- Smoke module: `stock_research.operator_decision.p13_smoke`
- Dashboard backend module: `stock_research.dashboard.shadow_outcomes`
- Dashboard component: `ShadowOutcomesPanel`

Candidate tables:

- `ops.operator_shadow_watchlist_outcome_run`
- `ops.operator_shadow_watchlist_outcome_candidate`

This mirrors P8 decision outcome review, but the measured entity is a P12 shadow
candidate rather than a P7 operator decision event.

## Data Flow

1. Load P12 shadow candidates from a JSON artifact or read-model rows.
2. Load market daily bars for candidate assets.
3. For each candidate, find the candidate date close and future daily bars.
4. Compute per-horizon outcomes.
5. Write JSON, candidate outcome CSV, and Markdown artifacts.
6. Import outcome artifacts into compact `ops` read-model tables.
7. Dashboard shows read-only outcome rows by asset/date range/status.

No step writes to production watchlist, scoring, approval, scheduler, or trading
tables.

## Outcome Contract

Each outcome row should preserve:

- `shadow_outcome_id`
- `run_id`
- `shadow_candidate_id`
- `source_p12_shadow_run_id`
- `replay_result_id`
- `source_p11_replay_run_id`
- `source_p10_proposal_run_id`
- `source_p9_analytics_run_id`
- `candidate_date`
- `asset_id`
- optional `stock_code`
- optional `stock_name`
- `shadow_layer`
- `shadow_status`
- `base_trade_date`
- `base_close`
- `available_future_bars`
- `outcome_status`
- `forward_returns`
- `max_high_returns`
- `max_low_drawdowns`
- `source_shadow_artifact_path`
- `outcome_artifact_path`
- safety fields

Outcome horizons:

- `1d`
- `3d`
- `5d`
- `10d`
- `20d`
- `60d`

Metrics:

- forward close-to-close return by horizon
- max high return within horizon
- max low drawdown within horizon
- available future daily bars
- outcome status:
  - `complete`
  - `insufficient_data`

Safety fields:

- `manual_review_required = true`
- `auto_trade_enabled = false`
- `production_watchlist_enabled = false`
- `production_write_enabled = false`

The contract rejects:

- missing P12/P11/P10/P9 source references
- missing asset identity
- missing candidate date
- missing base daily bar
- unsafe execution-like fields
- `auto_trade_enabled = true`
- `production_watchlist_enabled = true`
- `production_write_enabled = true`

If future bars are incomplete, P13 records `insufficient_data` and leaves metrics
for unavailable horizons as `null`; it does not silently use zero returns.

## CLI Design

Artifact creation:

```bash
stock-research p13-shadow-outcome-review \
  --shadow-json outputs/p12/2026-06-30/operator_shadow_watchlist_2026-06-30.json \
  --bars-csv inputs/p13/market_daily_bars_2026-06-30.csv \
  --run-id p13-shadow-outcomes-2026-06-30 \
  --review-date 2026-06-30 \
  --output-dir outputs/p13/2026-06-30
```

Read-model import:

```bash
stock-research p13-import-shadow-outcomes \
  --path outputs/p13/2026-06-30/operator_shadow_outcomes_2026-06-30.json
```

Both commands print stable machine-readable summary lines following P8 through
P12 patterns.

## Dashboard Design

Add a read-only dashboard view for shadow candidate outcomes.

The panel should show:

- candidate asset
- shadow status and layer
- candidate date
- outcome status
- available future bars
- selected horizon returns
- selected horizon drawdowns
- source P12/P11/P10/P9 references

The panel must support loading, empty, and error states through existing app
patterns. It must not include editing, promotion controls, watchlist write
controls, score controls, trade controls, broker controls, order UI, or
scheduler controls.

## Testing Strategy

Use TDD for implementation.

Python tests:

- contract computes complete horizon metrics
- contract records insufficient data explicitly
- contract rejects unsafe or production-enabled rows
- CLI creates review-only artifacts
- read model imports one artifact and directories idempotently
- schema contains P13 read-model tables
- dashboard backend returns read-only rows
- smoke creates artifacts and parses read-model rows

Dashboard tests:

- API client fetches shadow outcomes
- app shell renders the panel
- empty/loading states render
- Playwright smoke verifies desktop and mobile without horizontal overflow
- tests assert no promotion/trade/watchlist write controls are present

## Phase Breakdown

P13-0 Scope Freeze:

- Write scope freeze and baseline review.
- Preserve non-P13 dirty changes.

P13-1 Shadow Candidate Outcome Contract:

- Implement per-candidate outcome metric builder.
- Validate source references and safety fields.
- Handle insufficient data explicitly.

P13-2 Shadow Outcome Artifact CLI:

- Add `p13-shadow-outcome-review`.
- Generate JSON/CSV/Markdown artifacts.

P13-3 Shadow Outcome Read Model:

- Add schema tables.
- Add importer and `p13-import-shadow-outcomes`.

P13-4 Dashboard Read-Only Shadow Outcome View:

- Add backend endpoint and frontend panel.
- Add browser smoke coverage.

P13-5 Runbook, Smoke, Completion Review:

- Add synthetic smoke from P12 candidates and synthetic bars.
- Write runbook and completion review.
- Record verification evidence.

## Acceptance Criteria

- P13 artifacts preserve P12, P11, P10, and P9 source references.
- P13 artifacts force review-only safety fields.
- P13 computes complete per-candidate outcomes when enough future bars exist.
- P13 records insufficient data explicitly when future bars are missing.
- P13 read-model imports are idempotent.
- Dashboard can show shadow outcomes for a selected date range or asset.
- Dashboard remains usable when no shadow outcomes exist.
- P13 adds no production watchlist write path.
- P13 adds no factor score or factor approval write path.
- P13 adds no scheduler automation or trading execution path.
