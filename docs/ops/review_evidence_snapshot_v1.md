# Review Evidence Snapshot v1

## Scope

Batch C persists the evidence context behind daily review decisions. It adds durable snapshots for Review Queue items and Evidence Digest payloads, plus read-only APIs to query those snapshots by `run_id`, `trade_date`, `asset_id`, or `digest_key`.

## Out Of Scope

This batch does not add strategies, factors, data sources, trading actions, broker integration, or UI redesign. It does not change candidate semantics, strategy output logic, HomeCockpit, Strategy Command Center, or Backtest Lab. Dashboard decision APIs remain read-oriented in this batch.

## Current Chain

Review Queue items are now serializable API objects with Batch B lineage fields such as `run_id`, `latest_trade_date`, `digest_key`, `source_type`, `source_name`, `topn_rank`, `evidence_status`, and evidence gap counts.

Evidence Digest responses are serializable API objects with `digest_key`, `overall_status`, `sections`, `missing_evidence`, `partial_evidence`, and `lineage`, while retaining legacy `facts`, `risk_flags`, and `next_actions`.

Operator decisions currently read from `ops.operator_decision_event`. Rows include `event_id`, `review_date`, `asset_id`, `decision_label`, `evidence_artifact_id`, `evidence_path`, and `source_context`, but no explicit snapshot FK. Outcomes read from `ops.operator_decision_outcome_event` and include an outcome `run_id` plus `decision_event_id`.

No existing table stores Review Queue or Evidence Digest snapshots, so Batch C adds two narrow `ops` tables.

## Data Model

### `ops.review_item_snapshot`

Stores one Review Queue item as seen for a run.

Fields:

- `snapshot_id`
- `run_id`
- `trade_date`
- `latest_trade_date`
- `asset_id`
- `stock_code`
- `stock_name`
- `digest_key`
- `source_type`
- `source_name`
- `source_rank`
- `topn_rank`
- `score_version`
- `score`
- `evidence_status`
- `missing_evidence_count`
- `partial_evidence_count`
- `warnings_count`
- `review_item_payload`
- `payload_hash`
- `schema_version`
- `created_at`
- `updated_at`

Unique key: `(run_id, digest_key)`.

### `ops.evidence_digest_snapshot`

Stores one Evidence Digest payload as seen for a run.

Fields:

- `snapshot_id`
- `run_id`
- `trade_date`
- `latest_trade_date`
- `asset_id`
- `stock_code`
- `stock_name`
- `digest_key`
- `overall_status`
- `missing_evidence`
- `partial_evidence`
- `sections_status`
- `digest_payload`
- `payload_hash`
- `schema_version`
- `created_at`
- `updated_at`

Unique key: `(run_id, digest_key)`.

## Payload Hash

`payload_hash` is `sha256(canonical_json(payload))`, where canonical JSON uses `sort_keys=True`, compact separators, and UTF-8. Hashes are stable for equal semantic payloads.

## Schema Version

Snapshot schema version starts at `v1`. Changing payload shape or business-key semantics should create a new version rather than mutating historical interpretation.

## Snapshot Write Timing

Batch C implements a service that can write snapshots from current Review Queue and Evidence Digest API payloads. It does not force a large EOD pipeline refactor.

Low-risk write paths:

- `snapshot_review_queue_payload(queue_payload)`: persist each queue item and embedded digest.
- `snapshot_review_item(item)`: persist a single Review Queue item.
- `snapshot_evidence_digest(digest)`: persist a single digest.

Future EOD orchestration can call the service after Review Queue generation and record `snapshot_count` in `run_summary.json`.

## Operator Decision Linkage

Current decision rows are not altered in-place in Batch C. The dashboard decision read model exposes best-effort linkage by parsing `source_context` if it contains JSON with:

- `review_item_snapshot_id`
- `evidence_digest_snapshot_id`
- `run_id`
- `digest_key`
- `evidence_as_of`
- `review_item_as_of`

If context is plain text or missing, the response includes empty linkage fields and `snapshot_linkage_status = "missing"`. This avoids breaking current decision ingestion and leaves a clear migration path to explicit nullable columns later.

## APIs

New read-only APIs:

```http
GET /api/review-queue/snapshots?run_id=...&trade_date=...&asset_id=...&digest_key=...
GET /api/evidence-digest/snapshots?run_id=...&trade_date=...&asset_id=...&digest_key=...
GET /api/evidence-digest/snapshots/{snapshot_id}
```

Responses use:

```json
{
  "items": [],
  "warnings": [],
  "as_of": "2026-06-15T00:00:00+00:00",
  "source": "ops.review_item_snapshot"
}
```

## Test Plan

- schema DDL declares both snapshot tables and unique indexes;
- insert functions create stable `snapshot_id`, `payload_hash`, and JSON payloads;
- equal payloads produce equal hashes regardless of key order;
- duplicate `(run_id, digest_key)` upserts update the same logical row;
- Review Queue item and Evidence Digest payloads can be persisted;
- missing/partial evidence is preserved in payload and indexed fields;
- list APIs filter by `run_id`, `trade_date`, `asset_id`, and `digest_key`;
- snapshot detail API returns a single digest snapshot;
- decision read model exposes snapshot linkage when `source_context` contains JSON;
- missing linkage does not fail decision history;
- Batch A readiness and Batch B review/digest tests remain green.

## Smoke Test

```bash
/Users/xiwei/stock_research/.venv/bin/pytest \
  tests/test_review_evidence_snapshots.py \
  tests/test_dashboard_review_queue.py \
  tests/test_dashboard_evidence_digest.py \
  tests/test_dashboard_decisions.py \
  tests/test_dashboard_app.py \
  tests/test_dashboard_readiness.py -q

cd dashboard && pnpm exec vitest run --exclude "**/*.spec.ts" tests/client.test.ts

cd dashboard && pnpm build
```

## Batch D/E Reserve

Batch D can connect operator decision creation forms to snapshot IDs. Batch E can add compact UI views for snapshot history and evidence diffs.
