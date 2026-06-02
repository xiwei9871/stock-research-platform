# P12 Shadow Watchlist Experiment Design

Date: 2026-06-01

## Purpose

P12 turns reviewed P11 offline replay evidence into a shadow watchlist candidate
review layer. It is a review-only bridge between offline experiment replay and
any later controlled watchlist or scoring implementation scope.

P12 does not create production watchlist signals, factor scores, factor
approvals, scheduler automation, trades, orders, broker state, account state, or
position state.

## Current Context

P10 records experiment proposals from P9 outcome analytics. P11 records offline
replay results for approved P10 proposals and keeps replay output review-only.

P11 completion explicitly deferred P12 as:

- shadow watchlist experiment read model

P12 starts from P11 replay artifacts/read models, especially replay rows with
`replay_status = passed_offline_replay`, but that status is only evidence for
review. It is not production approval.

The current workspace also contains unrelated watchlist, factor-pipeline,
trend-discovery, and strong-winner dirty files. P12 must stay isolated from
those changes unless the user explicitly asks to reconcile them.

## Scope

P12 implements a shadow watchlist candidate review model.

In scope:

- P12 scope freeze document.
- Shadow watchlist candidate artifact contract.
- CLI to create shadow candidate artifacts from P11 replay evidence.
- JSON/CSV/Markdown outputs.
- Read-model schema and importer for shadow candidate runs/results.
- Dashboard read-only shadow candidate summary.
- Synthetic smoke, runbook, and completion review.

Out of scope:

- Writing `watchlist.watchlist_daily_signal`.
- Writing `factor.stock_score_daily`.
- Writing `factor.factor_approval`.
- Changing watchlist generation logic.
- Changing ranking/scoring logic.
- Scheduler automation.
- Broker, order, execution, account, cash, or position state.
- Treating shadow candidate status as production approval.

## Recommended Architecture

Use an independent `ops` read model and artifact family:

- Artifact module: `stock_research.operator_decision.shadow_watchlist`
- Read model module: `stock_research.operator_decision.shadow_watchlist_read_model`
- Smoke module: `stock_research.operator_decision.p12_smoke`
- Dashboard backend module: `stock_research.dashboard.shadow_watchlist`
- Dashboard component: `ShadowWatchlistPanel`

Candidate tables:

- `ops.operator_shadow_watchlist_run`
- `ops.operator_shadow_watchlist_candidate`

This keeps P12 queryable while avoiding any ambiguity with the production
watchlist schema.

## Data Flow

1. Operator reviews P11 replay rows.
2. P12 candidate input references replay evidence:
   - `replay_result_id`
   - `source_p11_replay_run_id`
   - `source_p10_proposal_run_id`
   - `source_p9_analytics_run_id`
   - replay artifact paths
3. P12 contract validates that each candidate is review-only and evidence-backed.
4. CLI writes JSON, candidate CSV, and Markdown artifacts.
5. Read-model importer upserts the run and candidate rows into `ops`.
6. Dashboard shows read-only candidates by date range/status.

No step writes to production watchlist, scoring, approval, scheduler, or trading
tables.

## Candidate Contract

Each candidate row should preserve:

- `shadow_candidate_id`
- `replay_result_id`
- `source_p11_replay_run_id`
- `source_p10_proposal_run_id`
- `source_p9_analytics_run_id`
- `candidate_date`
- `asset_id`
- optional `stock_code`
- optional `stock_name`
- `shadow_layer`
- `candidate_reason`
- `evidence_artifact_paths`
- `metric_summary`
- `reviewer_id`
- `status`
- `review_notes`
- safety fields

Allowed statuses:

- `shadow_ready`
- `shadow_observe`
- `shadow_rejected`
- `needs_more_data`
- `blocked`

Safety fields:

- `manual_review_required = true`
- `auto_trade_enabled = false`
- `production_watchlist_enabled = false`
- `production_write_enabled = false`

The contract rejects:

- missing replay/P10/P9 evidence
- missing asset identity
- empty evidence artifacts
- invalid statuses
- execution-like fields
- `auto_trade_enabled = true`
- `production_watchlist_enabled = true`
- `production_write_enabled = true`

## CLI Design

Artifact creation:

```bash
stock-research p12-shadow-watchlist \
  --replay-json outputs/p11/2026-06-30/operator_experiment_replay_2026-01-01_2026-06-30.json \
  --candidates-csv inputs/p12/shadow_candidates_2026-06-30.csv \
  --review-date 2026-06-30 \
  --run-id p12-shadow-watchlist-2026-06-30 \
  --output-dir outputs/p12/2026-06-30
```

Read-model import:

```bash
stock-research p12-import-shadow-watchlist \
  --path outputs/p12/2026-06-30/operator_shadow_watchlist_2026-06-30.json
```

Both commands print stable machine-readable summary lines, following P10/P11
patterns.

## Dashboard Design

Add a read-only dashboard panel for shadow candidates.

The panel should show:

- candidate asset
- shadow status
- shadow layer
- candidate date
- source replay result
- source P10/P9 run references

The panel must support loading, empty, and error states through existing app
patterns. It must not include pass/fail editing, promotion controls, watchlist
write controls, score controls, trade controls, broker controls, order UI, or
scheduler controls.

## Testing Strategy

Use TDD for implementation.

Python tests:

- contract builds valid shadow candidates
- rejects unsafe or production-enabled rows
- CLI creates review-only artifacts
- read model imports one artifact and directories idempotently
- schema contains P12 read-model tables
- dashboard backend returns read-only rows
- smoke creates artifacts and parses read-model rows

Dashboard tests:

- API client fetches shadow candidates
- app shell renders the panel
- empty/loading states render
- Playwright smoke verifies desktop and mobile without horizontal overflow
- tests assert no promotion/trade/watchlist write controls are present

## Phase Breakdown

P12-0 Scope Freeze:

- Write scope freeze and baseline review.
- Preserve non-P12 dirty changes.

P12-1 Shadow Watchlist Candidate Contract:

- Implement candidate artifact builder and writer.
- Validate evidence and safety fields.

P12-2 Shadow Artifact CLI:

- Add `p12-shadow-watchlist`.
- Generate JSON/CSV/Markdown artifacts.

P12-3 Shadow Read Model:

- Add schema tables.
- Add importer and `p12-import-shadow-watchlist`.

P12-4 Dashboard Read-Only Shadow Summary:

- Add backend endpoint and frontend panel.
- Add browser smoke coverage.

P12-5 Runbook, Smoke, Completion Review:

- Add synthetic smoke.
- Write runbook and completion review.
- Record verification evidence.

## Acceptance Criteria

- P12 artifacts preserve P11 replay, P10 proposal, and P9 analytics references.
- P12 artifacts force review-only safety fields.
- P12 read-model imports are idempotent.
- Dashboard can show shadow candidates for a selected date range.
- Dashboard remains usable when no shadow candidates exist.
- P12 adds no production watchlist write path.
- P12 adds no factor score or factor approval write path.
- P12 adds no scheduler automation or trading execution path.
