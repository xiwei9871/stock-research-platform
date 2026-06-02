# P17 Shadow Decision Follow-up Queue Design

Date: 2026-06-02

## Purpose

P17 converts P16 shadow review decisions into a review-only follow-up queue. It
gives operators an auditable backlog of next work items without creating any
production promotion, watchlist, scoring, scheduler, or trading path.

## Inputs

P17 consumes a P16 shadow review decision artifact with:

- run metadata from `operator_shadow_review_decisions_*.json`
- group rows containing P15/P14 lineage
- P16 decision status, bucket, reason, required next action, evidence, risk, and
  next research question
- safety fields proving the artifact is review-only

## Outputs

P17 writes:

- JSON artifact: `operator_shadow_follow_up_queue_<follow_up_date>.json`
- item CSV: `operator_shadow_follow_up_queue_<follow_up_date>_items.csv`
- Markdown summary: `operator_shadow_follow_up_queue_<follow_up_date>.md`
- read-model rows under `ops.operator_shadow_follow_up_run`
- read-model rows under `ops.operator_shadow_follow_up_item`
- read-only dashboard data for follow-up queue inspection

## Status Mapping

P17 maps P16 decision statuses conservatively:

| P16 decision status | P17 follow-up status | Priority bucket | Required input |
| --- | --- | --- | --- |
| `continue_shadow_observation` | `observe_shadow_group` | `normal` | More shadow outcome observations |
| `request_more_data` | `collect_more_evidence` | `high` | Additional outcome or data-quality evidence |
| `open_research_follow_up` | `open_research_ticket` | `high` | Separately scoped research plan |
| `deprioritize_shadow_group` | `deprioritized` | `low` | New evidence before renewed review |

## Architecture

The implementation follows P16 patterns:

- `shadow_follow_up_queue.py` builds and writes P17 artifacts.
- `shadow_follow_up_queue_read_model.py` loads/imports P17 artifacts into ops
  read-model tables.
- `cli.py` exposes build and import commands.
- `schema.py` owns the new `ops` DDL and indexes.
- dashboard backend and frontend read the follow-up read model only.
- `p17_smoke.py` builds a synthetic P15 -> P16 -> P17 flow for operational
  smoke evidence.

## Safety Design

P17 rejects unsafe execution-like fields anywhere in consumed artifacts. It also
requires review-only safety flags and writes these flags back to each run and
item:

- `manual_review_required = true`
- `auto_trade_enabled = false`
- `production_watchlist_enabled = false`
- `production_write_enabled = false`

P17 never writes production watchlist, factor score, factor approval, scheduler,
broker, order, account, execution, cash, or position state.

## Dashboard Design

The dashboard adds a read-only follow-up queue panel. It shows latest P17 item
rows with status, priority, required input, source P16/P15/P14 lineage, evidence,
risk notes, and next research question. Missing tables return an empty state.
No edit, promote, trade, order, score, scheduler, or write controls are added.

## Testing

Tests cover:

- artifact contract and safety rejection
- CLI parser and dispatch
- read-model row loading and idempotent upsert SQL
- schema DDL presence
- dashboard API missing-table and populated states
- dashboard frontend loading/empty/populated states
- synthetic smoke from P16 artifact to P17 artifact/read-model rows

## Non-Goals

P17 does not close follow-up items, assign owners, connect to task trackers,
schedule jobs, or trigger production actions. Those require separate scope
freezes after the review-only queue is proven useful.
