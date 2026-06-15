# Operator Decision Write API v1

## Scope

Batch F adds an explicit dashboard write API for local operator decisions:

- `POST /api/operator-decisions`
- a small write service under `operator_decision`
- snapshot linkage reuse from Batch E
- source context JSON merge compatibility
- frontend API client/types only
- focused tests and smoke commands

The API records human research decisions against candidates, evidence digests, manual notes, or follow-up work. It does not create orders, broker instructions, execution signals, or strategy outputs.

## Out Of Scope

- automatic trading
- broker or account integration
- new strategies, factors, or data sources
- HomeCockpit, Strategy Command Center, Backtest Lab, or large UI changes
- new permission system
- schema redesign
- renaming candidates into buy, sell, or trade signals

## Current Decision Chain

The existing write path is journal import:

1. `operator_decision/read_model.py::import_decision_journal`
2. `load_decision_journal_read_model_rows`
3. `_upsert_session`
4. `_event_row`
5. `_upsert_event`

The target table is `ops.operator_decision_event`. Its `source_context` column is text and already stores JSON when snapshot linkage is present. The dashboard read path is `dashboard/decisions.py::load_asset_decision_history`, which parses `source_context` and exposes:

- `run_id`
- `digest_key`
- `review_item_snapshot_id`
- `evidence_digest_snapshot_id`
- payload hashes
- evidence/review as-of timestamps
- `snapshot_linkage_status`
- `snapshot_linkage_warnings`

Batch E added `operator_decision/snapshot_linkage.py`, which resolves snapshot linkage from explicit snapshot IDs, `run_id + digest_key`, or `run_id + asset_id`.

## POST API

Endpoint:

```http
POST /api/operator-decisions
```

Request:

```json
{
  "asset_id": "000001.SZ",
  "stock_code": "000001.SZ",
  "stock_name": "Ping An Bank",
  "decision_date": "2026-06-12",
  "operator_action": "watch",
  "decision_status": "open",
  "operator_note": "Observe after pullback confirmation",
  "run_id": "eod-2026-06-12-local",
  "digest_key": "2026-06-12:manual_v1:000001.SZ",
  "source_type": "score_topn",
  "source_name": "manual_v1_topn",
  "follow_up_date": "2026-06-17",
  "tags": ["topn", "manual_review"],
  "source_context": {
    "entry": "review_queue",
    "note_source": "dashboard"
  }
}
```

Response:

```json
{
  "event_id": "operator_decision:operator-decision-api-2026-06-12:0:abc123",
  "asset_id": "000001.SZ",
  "stock_code": "000001.SZ",
  "stock_name": "Ping An Bank",
  "decision_date": "2026-06-12",
  "operator_action": "watch",
  "decision_status": "open",
  "decision_label": "observe",
  "run_id": "eod-2026-06-12-local",
  "digest_key": "2026-06-12:manual_v1:000001.SZ",
  "review_item_snapshot_id": "review_item_snapshot:abc",
  "evidence_digest_snapshot_id": "evidence_digest_snapshot:def",
  "snapshot_linkage_status": "linked",
  "snapshot_linkage_warnings": [],
  "warnings": []
}
```

## Write Service

The service will live at:

```text
src/stock_research/operator_decision/write_service.py
```

Responsibilities:

- validate required request fields
- normalize `asset_id` and `stock_code`
- map conservative `operator_action` values to existing `decision_label`
- merge request `source_context` with Batch E snapshot linkage
- preserve legacy/plain source context text as `source_context_label`
- upsert `ops.operator_review_session`
- upsert `ops.operator_decision_event`
- return a response matching dashboard read-model linkage fields

The service should reuse existing `_upsert_session`, `_upsert_event`, and `_event_id` from `read_model.py` so journal import and direct API writes keep the same storage shape.

## Operator Actions

Allowed v1 actions are research workflow actions only:

- `watch`
- `skip`
- `follow_up`
- `add_to_shadow`
- `remove_from_shadow`
- `note`
- `pause`
- `close`

They map to the existing journal `decision_label` set:

| operator_action | decision_label |
| --- | --- |
| watch | observe |
| skip | no_action |
| follow_up | observe |
| add_to_shadow | candidate |
| remove_from_shadow | remove |
| note | observe |
| pause | caution |
| close | remove |

## Source Context Merge

The final persisted `source_context` remains JSON text:

```json
{
  "entry": "review_queue",
  "note_source": "dashboard",
  "run_id": "eod-2026-06-12-local",
  "digest_key": "2026-06-12:manual_v1:000001.SZ",
  "review_item_snapshot_id": "review_item_snapshot:abc",
  "evidence_digest_snapshot_id": "evidence_digest_snapshot:def",
  "review_item_payload_hash": "review-hash",
  "evidence_digest_payload_hash": "digest-hash",
  "snapshot_linkage_status": "linked",
  "snapshot_linkage_warnings": [],
  "source_type": "score_topn",
  "source_name": "manual_v1_topn",
  "operator_action": "watch",
  "decision_status": "open"
}
```

Request fields are preserved unless a resolver linkage field supplies the canonical value. Plain text source context is retained under `source_context_label`.

## Missing Snapshot Behavior

Snapshot lookup is non-blocking. If snapshots do not exist, the decision is still written:

```json
{
  "snapshot_linkage_status": "missing",
  "snapshot_linkage_warnings": [
    "No review_item_snapshot found for run_id + digest_key",
    "No evidence_digest_snapshot found for run_id + digest_key"
  ],
  "warnings": [
    "No review_item_snapshot found for run_id + digest_key",
    "No evidence_digest_snapshot found for run_id + digest_key"
  ]
}
```

Only invalid requests or database write failures should fail the API.

## Validation

Minimal validation:

- `asset_id` or `stock_code` is required
- `operator_action` is required and must be allowed
- `decision_date` defaults to local current date if missing and must be ISO date when supplied
- `follow_up_date` must be ISO date when supplied
- `source_context` must be object, string, or null
- `manual_review_required` is always true
- `auto_trade_enabled` is always false

## Import Compatibility

`import_decision_journal` remains supported and continues to resolve snapshot linkage. The direct write API shares the low-level session/event upsert functions and source-context merge semantics; it does not replace journal import.

## Tests

Focused tests:

- direct write succeeds
- explicit snapshot IDs are linked
- `run_id + digest_key` resolves snapshots
- missing snapshots stay non-blocking
- source context merge preserves old fields
- invalid action returns validation error
- missing asset returns validation error
- dashboard POST route returns the write response
- dashboard POST route maps validation errors to 4xx
- frontend client posts to `/api/operator-decisions`

## Smoke Test

```bash
curl -s -X POST http://localhost:8000/api/operator-decisions \
  -H 'Content-Type: application/json' \
  -d '{
    "asset_id":"000001.SZ",
    "stock_code":"000001.SZ",
    "decision_date":"2026-06-12",
    "operator_action":"watch",
    "operator_note":"manual review note",
    "run_id":"eod-2026-06-12-local",
    "digest_key":"2026-06-12:manual_v1:000001.SZ",
    "source_context":{"entry":"review_queue"}
  }' | jq .
```

Read-back smoke:

```bash
curl -s 'http://localhost:8000/api/assets/000001.SZ/decisions?start_date=2026-06-12&end_date=2026-06-12&limit=5' | jq .
```

## Batch G Reserve

- UI button from Review Queue / Evidence Digest to create decision
- operator decision edit/close workflow
- decision/outcome reconciliation cockpit
- richer audit trail around changed decisions
