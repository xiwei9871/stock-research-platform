# P16 Shadow Review Decision Packet Design

Date: 2026-06-02

## Purpose

P16 turns P15 shadow analytics operational reviews into an auditable decision
packet. The packet records what the operator should do next with each reviewed
shadow group: continue observation, request more data, open a research follow-up,
or deprioritize the group.

P16 remains review-only. It does not promote groups into production, write
production watchlists, mutate factor scores, create scheduler automation, or
create trading instructions.

## Current Context

P12 created review-only shadow watchlist candidates from approved experiment
replay evidence. P13 measured candidate outcomes. P14 summarized outcomes by
`shadow_layer` and `shadow_status`. P15 recorded operational review status,
evidence summaries, risk notes, and next research questions for those P14
groups.

P15 deliberately stopped before a formal decision packet. P16 closes that loop
by recording the operator's next-step decision for each P15 review group while
preserving all upstream lineage.

The main worktree contains unrelated dirty trend, mid-trend, strong-winner,
watchlist, and factor-pipeline files. P16 work must stay isolated from those
changes unless the user explicitly asks to reconcile them.

## Scope

P16 implements a review-only decision packet layer for P15 shadow analytics
review groups.

In scope:

- P16 scope freeze document.
- A P16 artifact contract that consumes P15 review groups.
- Group-level decision statuses and decision reasons.
- JSON, CSV, and Markdown decision artifacts.
- Independent `ops` read-model tables and import helper.
- Read-only dashboard API and panel.
- Synthetic smoke, runbook, and completion review.

Out of scope:

- Production promotion recommendations.
- Automatic generation of production watchlist rows.
- Writing `watchlist.watchlist_daily_signal`.
- Writing `factor.stock_score_daily`.
- Writing `factor.factor_approval`.
- Changing scoring, ranking, or production watchlist generation logic.
- Scheduler automation.
- Broker, order, execution, account, cash, or position state.
- Treating any P15 review status or P16 decision status as production approval.

## Decision Contract

Each P16 run should preserve:

- `run_id`
- `decision_date`
- `source_p15_review_run_ids`
- `status`
- `operator_id`
- `manual_review_required`
- `auto_trade_enabled`
- `production_watchlist_enabled`
- `production_write_enabled`
- artifact paths

Each group decision row should preserve:

- `decision_group_id`
- `run_id`
- `source_p15_review_group_id`
- `source_p15_review_run_id`
- `source_p14_analytics_group_id`
- `source_p14_analytics_run_id`
- `group_key`
- `shadow_layer`
- `shadow_status`
- `sample_count`
- `complete_count`
- `insufficient_data_count`
- `review_status`
- `review_bucket`
- `decision_status`
- `decision_bucket`
- `decision_reason`
- `required_next_action`
- `evidence_summary`
- `risk_notes`
- `next_research_question`
- `manual_review_required`
- `auto_trade_enabled`
- `production_watchlist_enabled`
- `production_write_enabled`

Allowed `decision_status` values:

- `continue_shadow_observation`
- `request_more_data`
- `open_research_follow_up`
- `deprioritize_shadow_group`

Decision statuses are workflow notes only. `open_research_follow_up` means
"create a separately scoped research task"; it does not approve production
changes.

## Decision Rules

The first P16 pass should use deterministic, conservative mapping rules:

- P15 `needs_more_data` becomes `request_more_data`.
- P15 `investigate_data_quality` becomes `request_more_data`.
- P15 `research_follow_up_candidate` becomes `open_research_follow_up`.
- P15 `deprioritize_review` becomes `deprioritize_shadow_group`.
- P15 `continue_observing` becomes `continue_shadow_observation`.

P16 must reject artifacts with unsafe execution-like fields or unsafe safety
flags. All P16 outputs must force:

- `manual_review_required = true`
- `auto_trade_enabled = false`
- `production_watchlist_enabled = false`
- `production_write_enabled = false`

## Data Flow

1. Load P15 review artifacts or read-model rows.
2. Validate review-only safety fields.
3. Preserve P15 and upstream P14 lineage.
4. Apply deterministic decision mapping rules.
5. Write JSON, group CSV, and Markdown decision artifacts.
6. Import artifacts into independent `ops` read-model tables.
7. Dashboard displays decisions as read-only workflow evidence.

No step writes to production watchlist, scoring, approval, scheduler, or trading
tables.

## Proposed Tables

- `ops.operator_shadow_review_decision_run`
- `ops.operator_shadow_review_decision_group`

The group table should key rows by a run-scoped `decision_group_id`, derived
from `run_id|source_p15_review_group_id|decision_status`, and upsert on that
key.

## CLI Design

Artifact creation:

```bash
stock-research p16-shadow-review-decisions \
  --p15-review-json outputs/p15/operator_shadow_analytics_review_2026-06-30_2026-08-29.json \
  --run-id p16-shadow-review-decisions-2026-08-29 \
  --decision-date 2026-08-29 \
  --operator-id operator \
  --output-dir outputs/p16
```

Read-model import:

```bash
stock-research p16-import-shadow-review-decisions \
  --path outputs/p16/operator_shadow_review_decisions_2026-08-29.json \
  --service stock_research
```

## Dashboard Design

Add a read-only dashboard panel for P16 shadow review decisions.

The panel should show:

- shadow layer and status
- P15 review status and bucket
- P16 decision status and bucket
- sample and completion counts
- decision reason
- required next action
- evidence summary
- risk notes
- next research question

The panel must not include promotion, production watchlist write, score
mutation, trade, broker, order, or scheduler controls.

## Testing Strategy

Python tests:

- P16 contract maps every allowed P15 review status to the expected P16 decision
  status.
- Safety field validation rejects production or execution-like fields.
- Artifact writer emits JSON, CSV, and Markdown paths.
- Read-model importer performs idempotent upserts.
- Schema tests assert P16 tables and indexes.
- CLI parser and dispatch tests cover artifact and import commands.
- Synthetic smoke starts from P15 smoke and writes P16 artifacts/read-model rows.

Dashboard tests:

- Backend query is read-only and returns `[]` if P16 tables are missing.
- API route returns read-only decision items.
- Client fetches P16 decision items.
- App renders loading, empty, and populated states.
- Browser smoke verifies desktop render and mobile no-overflow.
- Tests assert no promotion, trade, write-watchlist, score mutation, or
  scheduler controls exist.

## Execution Plan Sketch

P16-0 Scope Freeze:

- Commit P16 scope freeze and design.

P16-1 Decision Contract:

- Build P16 decision artifact contract and mapping tests.

P16-2 Artifact CLI:

- Add artifact-generation CLI and focused tests.

P16-3 Read Model:

- Add independent `ops` tables and import CLI.

P16-4 Dashboard:

- Add read-only backend query, API route, client, and panel.

P16-5 Smoke, Runbook, Completion:

- Add synthetic P15-to-P16 smoke, runbook, and completion review.

## Acceptance Criteria

- P16 consumes P15 review artifacts without mutating P15 data.
- P16 preserves P15 and P14 lineage through source IDs.
- P16 emits review-only decision artifacts and read-model rows.
- P16 decision statuses are workflow notes, not production approval.
- P16 dashboard is read-only and usable when P16 tables are missing.
- P16 adds no production watchlist, factor score, approval, scheduler, broker,
  order, account, cash, execution, or position writes.
