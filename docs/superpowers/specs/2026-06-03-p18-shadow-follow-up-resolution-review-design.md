# P18 Shadow Follow-up Resolution Review Design

Date: 2026-06-03

## Purpose

P18 converts P17 shadow follow-up queue items into a review-only resolution
review. It lets operators inspect whether each follow-up item has enough
evidence, should open a separate research ticket, should keep observing, can be
closed as deprioritized, or remains stale and unresolved.

## Inputs

P18 consumes a P17 follow-up queue artifact with:

- run metadata from `operator_shadow_follow_up_queue_*.json`
- item rows containing P16/P15/P14 lineage
- P17 follow-up status, priority bucket, required input, evidence, risk, and
  next research question
- safety fields proving the artifact is review-only

## Outputs

P18 writes:

- JSON artifact: `operator_shadow_follow_up_resolution_<resolution_date>.json`
- item CSV: `operator_shadow_follow_up_resolution_<resolution_date>_items.csv`
- Markdown summary: `operator_shadow_follow_up_resolution_<resolution_date>.md`
- read-model rows under `ops.operator_shadow_follow_up_resolution_run`
- read-model rows under `ops.operator_shadow_follow_up_resolution_item`
- read-only dashboard data for resolution review inspection

## Status Mapping

P18 maps P17 follow-up rows conservatively:

| P17 follow-up status | Priority bucket | P18 resolution status | Resolution bucket |
| --- | --- | --- | --- |
| `collect_more_evidence` | `high` | `stale_unresolved` | `needs_operator_review` |
| `open_research_ticket` | `high` | `research_ticket_opened` | `research_follow_up` |
| `observe_shadow_group` | `normal` | `continue_observing` | `observe` |
| `deprioritized` | `low` | `deprioritized_closed` | `closed_low_priority` |

The default for unknown combinations is rejected, not guessed.

## Architecture

The implementation follows P17 patterns:

- `shadow_follow_up_resolution.py` builds and writes P18 artifacts.
- `shadow_follow_up_resolution_read_model.py` loads/imports P18 artifacts into
  ops read-model tables.
- `cli.py` exposes build and import commands.
- `schema.py` owns the new `ops` DDL and indexes.
- dashboard backend and frontend read the resolution read model only.
- `p18_smoke.py` builds a synthetic P15 -> P16 -> P17 -> P18 flow for
  operational smoke evidence.

## Safety Design

P18 rejects unsafe execution-like fields anywhere in consumed artifacts. It also
requires review-only safety flags and writes these flags back to each run and
item:

- `manual_review_required = true`
- `auto_trade_enabled = false`
- `production_watchlist_enabled = false`
- `production_write_enabled = false`

P18 never writes production watchlist, factor score, factor approval, scheduler,
broker, order, account, execution, cash, or position state.

## Dashboard Design

The dashboard adds a read-only resolution review panel. It shows latest P18 item
rows with status, bucket, recommended action, source P17/P16/P15/P14 lineage,
evidence, risk notes, and next research question. Missing tables return an empty
state. No edit, promote, trade, order, score, scheduler, or write controls are
added.

## Testing

Tests cover:

- artifact contract and safety rejection
- CLI parser and dispatch
- read-model row loading and idempotent upsert SQL
- schema DDL presence
- dashboard API missing-table and populated states
- dashboard frontend loading/empty/populated states
- synthetic smoke from P17 artifact to P18 artifact/read-model rows

## Non-Goals

P18 does not mutate P17 follow-up items, assign owners, connect to task trackers,
schedule jobs, or trigger production actions. Those require separate scope
freezes after the review-only resolution loop is proven useful.
