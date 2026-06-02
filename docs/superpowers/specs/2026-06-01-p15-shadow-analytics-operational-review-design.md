# P15 Shadow Analytics Operational Review Design

Date: 2026-06-01

## Purpose

P15 turns P14 shadow outcome analytics into an operator-facing review packet.
The goal is to help the operator decide which shadow layers and statuses deserve
continued observation, data-quality investigation, or a separately scoped
research follow-up.

P15 remains review-only. It does not promote groups into production, rank
individual candidates, write production watchlists, mutate factor scores, create
scheduler automation, or create trading instructions.

## Current Context

P12 created review-only shadow watchlist candidates from approved experiment
replay evidence. P13 measured candidate outcomes. P14 summarized those outcomes
by `shadow_layer` and `shadow_status` and exposed the summary through artifacts,
read-model tables, and the dashboard.

P14 deliberately stopped before operational interpretation. The next useful
loop is not production promotion. It is a manual review layer that records what
the P14 evidence suggests, what remains uncertain, and what research question
should be considered next.

The main worktree also contains unrelated dirty trend, mid-trend, strong-winner,
watchlist, and factor-pipeline files. P15 must remain isolated from those
changes unless the user explicitly asks to reconcile them.

## Scope

P15 implements a review-only operational interpretation layer for P14 group
analytics.

In scope:

- P15 scope freeze document.
- A P15 artifact contract that consumes P14 analytics groups.
- Group-level review classifications for operational triage.
- JSON, CSV, and Markdown review artifacts.
- Independent `ops` read-model tables and import helper.
- Read-only dashboard API and panel.
- Synthetic smoke, runbook, and completion review.

Out of scope:

- Candidate-level ranking diagnostics.
- Production promotion recommendations.
- Automatic generation of production watchlist rows.
- Writing `watchlist.watchlist_daily_signal`.
- Writing `factor.stock_score_daily`.
- Writing `factor.factor_approval`.
- Changing scoring, ranking, or production watchlist generation logic.
- Scheduler automation.
- Broker, order, execution, account, cash, or position state.
- Treating any P15 review status as production approval.

## Review Contract

Each P15 run should preserve:

- `run_id`
- `review_start_date`
- `review_end_date`
- `source_p14_analytics_run_ids`
- `status`
- `reviewer_id`
- `manual_review_required`
- `auto_trade_enabled`
- `production_watchlist_enabled`
- `production_write_enabled`
- artifact paths

Each group review row should preserve:

- `review_group_id`
- `run_id`
- `source_p14_analytics_group_id`
- `source_p14_analytics_run_id`
- `group_key`
- `shadow_layer`
- `shadow_status`
- `sample_count`
- `complete_count`
- `insufficient_data_count`
- `horizon_metrics`
- `review_status`
- `review_bucket`
- `evidence_summary`
- `risk_notes`
- `next_research_question`
- `manual_review_required`
- `auto_trade_enabled`
- `production_watchlist_enabled`
- `production_write_enabled`

Allowed `review_status` values:

- `continue_observing`
- `needs_more_data`
- `investigate_data_quality`
- `deprioritize_review`
- `research_follow_up_candidate`

These statuses are operational notes only. `research_follow_up_candidate` means
"consider a future research question"; it does not approve production changes.

## Triage Rules

The first P15 pass should use deterministic, conservative triage rules:

- Low sample groups become `needs_more_data`.
- Groups with high insufficient-data share become `investigate_data_quality`.
- Groups with materially negative forward mean or severe drawdown become
  `deprioritize_review`.
- Groups with adequate samples, positive forward mean, and controlled drawdown
  become `research_follow_up_candidate`.
- Otherwise groups remain `continue_observing`.

Thresholds must be explicit parameters in the artifact builder and recorded in
run metadata. Defaults should be conservative and easy to override.

## Data Flow

1. Load P14 analytics artifacts or read-model rows.
2. Validate review-only safety fields.
3. Preserve P14 group lineage and horizon metrics.
4. Apply deterministic review triage rules.
5. Write JSON, group CSV, and Markdown review artifacts.
6. Import artifacts into independent `ops` read-model tables.
7. Dashboard displays review statuses and notes as read-only evidence.

No step writes to production watchlist, scoring, approval, scheduler, or trading
tables.

## Proposed Tables

- `ops.operator_shadow_analytics_review_run`
- `ops.operator_shadow_analytics_review_group`

The group table should key rows by a run-scoped `review_group_id`, derived from
`run_id|source_p14_analytics_group_id|review_status`, and upsert on that key.

## CLI Design

Artifact creation:

```bash
stock-research p15-shadow-analytics-review \
  --p14-analytics-json outputs/p14/2026-08-29/operator_shadow_outcome_analytics_2026-06-30_2026-08-29.json \
  --run-id p15-shadow-analytics-review-2026-06-30-2026-08-29 \
  --review-start-date 2026-06-30 \
  --review-end-date 2026-08-29 \
  --reviewer-id operator \
  --output-dir outputs/p15/2026-08-29
```

Read-model import:

```bash
stock-research p15-import-shadow-analytics-review \
  --path outputs/p15/2026-08-29/operator_shadow_analytics_review_2026-06-30_2026-08-29.json
```

## Dashboard Design

Add a read-only dashboard panel for P15 operational review.

The panel should show:

- shadow layer and status
- P14 sample and completion counts
- selected horizon metrics
- P15 review status
- review bucket
- evidence summary
- risk notes
- next research question

The panel must not include promotion, production watchlist write, score mutation,
trade, broker, order, or scheduler controls.

## Testing Strategy

Python tests:

- P15 contract groups and triage rules.
- Safety field validation.
- Artifact writer paths and Markdown content.
- Read-model importer idempotent upserts.
- Schema table/index assertions.
- CLI parser and dispatch.
- Synthetic smoke from P14 artifacts through P15 read-model rows.

Dashboard tests:

- Backend query is read-only and returns `[]` if P15 tables are missing.
- API route returns read-only items.
- Client fetches P15 review items.
- App renders loading, empty, populated, and invalid-metric states.
- Browser smoke verifies desktop render and mobile no-overflow.
- Tests assert no promotion, trade, write-watchlist, score mutation, or
  scheduler controls exist.

## Execution Plan Sketch

P15-0 Scope Freeze:

- Commit P15 scope freeze.

P15-1 Operational Review Contract:

- Build P15 review artifact contract and triage tests.

P15-2 Artifact CLI:

- Add artifact-generation CLI and focused tests.

P15-3 Read Model:

- Add independent `ops` tables and import CLI.

P15-4 Dashboard:

- Add read-only backend query, API route, client, and panel.

P15-5 Smoke, Runbook, Completion:

- Add synthetic P14-to-P15 smoke, runbook, and completion review.

## Acceptance Criteria

- P15 consumes P14 analytics without mutating P14 data.
- P15 preserves P14 lineage back to P13/P12/P11/P10/P9 through source IDs.
- P15 emits review-only artifacts and read-model rows.
- P15 review statuses are operational notes, not production approval.
- P15 dashboard is read-only and usable when P15 tables are missing.
- P15 adds no production watchlist, factor score, approval, scheduler, broker,
  order, account, cash, execution, or position writes.
