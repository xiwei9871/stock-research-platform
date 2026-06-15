# EOD Snapshot Integration v1

## Scope

Batch D wires the Batch C snapshot service into the local EOD workflow. The goal is to make Review Queue and Evidence Digest snapshots a fixed post-run artifact, visible in `run_summary.json`, `run_manifest.json`, `ops.data_run_manifest`, and readiness.

## Out Of Scope

- No automatic trading, broker integration, or execution signal terminology.
- No new strategy, factor, or data source.
- No HomeCockpit, Strategy Command Center, Backtest Lab, or large frontend work.
- No rewrite of `daily_data_pipeline.py`; this is a post-step integration.

## Current State

- `daily_data_pipeline.py` runs command-based steps, writes `run_summary.json` and `run_manifest.json` after each step, and derives module status through `STEP_MODULES` plus synthetic modules.
- `review_evidence_snapshots.py` can build and upsert `ops.review_item_snapshot` and `ops.evidence_digest_snapshot`.
- `readiness.py` consumes `ops.data_run_manifest` when present and already treats Tier 2 failures as `PARTIAL`.
- `cli.py` uses one large argparse parser and dispatch block.

## EOD Snapshot Step

The new step is `review_evidence_snapshots`.

It runs after factor/score/review queue generation and before report delivery. It:

1. Builds the current Review Queue for `trade_date`, `score_version`, and `limit`.
2. Persists each Review Queue item snapshot.
3. Persists each embedded Evidence Digest snapshot.
4. Writes an optional `review_evidence_snapshots_summary.json` artifact.
5. Returns counts and warnings for the EOD summary/manifest.

The step uses upsert semantics from Batch C, so rerunning the same `run_id + digest_key` is idempotent.

## Tier

`review_evidence_snapshots` is Tier 2.

Reason: snapshots are important for reproducible review, but a snapshot write failure should not block the core EOD candidate generation path when Tier 1 data, score, TopN, and Review Queue are available.

## Status Rules

- `success`: at least one review item snapshot was written and there were no item-level errors.
- `partial`: at least one snapshot was written, but one or more items/digests failed or produced warnings.
- `skipped`: Review Queue had no items.
- `failed`: the whole snapshot step failed before producing a usable result.

Per-item digest failures become warnings and do not stop the whole step.

## CLI

Independent rerun command:

```bash
python -m stock_research.cli snapshot-review-evidence \
  --run-id eod-YYYY-MM-DD-local \
  --trade-date YYYY-MM-DD \
  --output-dir outputs/research/stock_daily_data_pipeline/YYYY-MM-DD \
  --limit 100
```

The command does not fetch new data. It reads existing dashboard read models and writes snapshots.

## run_summary.json

New top-level fields:

```json
{
  "review_item_snapshot_count": 20,
  "evidence_digest_snapshot_count": 20,
  "snapshot_status": "success",
  "snapshot_warning_count": 0,
  "snapshot_warnings": [],
  "snapshot_errors": [],
  "snapshot_module_status": "success",
  "snapshot_summary_path": "outputs/.../review_evidence_snapshots_summary.json"
}
```

`modules` also includes:

```json
{
  "module": "review_evidence_snapshots",
  "source": "review_queue/evidence_digest",
  "tier": "tier2",
  "status": "success",
  "row_count": 40,
  "asset_count": 20,
  "warning_count": 0
}
```

## run_manifest.json

`run_manifest.json` gets the same module entry as `run_summary.json.modules`. Its `artifact_path` points at `review_evidence_snapshots_summary.json` when available.

## data_run_manifest

The snapshot step writes one `ops.data_run_manifest` row:

- `module = review_evidence_snapshots`
- `source = review_queue/evidence_digest`
- `tier = tier2`
- `status = success | partial | skipped | failed`
- `row_count = review_item_snapshot_count + evidence_digest_snapshot_count`
- `asset_count = review_item_snapshot_count`
- `warnings`, `error_message`, `artifact_path`, and `latest_trade_date`

## Readiness Impact

Readiness v2 already derives status from manifest tiers. This batch adds explicit check labels and warning text for `review_evidence_snapshots`:

- `success`: readiness can remain `OK`.
- `partial` / `failed` / `unavailable`: readiness becomes `PARTIAL` when Tier 1 is OK.
- `skipped`: no blocking effect, but the module remains visible.

## Testing Plan

- Unit tests for snapshot EOD service success, partial, skipped, and idempotent upsert behavior.
- Pipeline tests for `run_summary.json` and `run_manifest.json` snapshot fields.
- Manifest test verifying Tier 2 snapshot rows.
- Readiness tests verifying snapshot failure produces `PARTIAL`, not `BLOCKED`.
- CLI parser and smoke tests for `snapshot-review-evidence`.

## Smoke Test

```bash
/Users/xiwei/stock_research/.venv/bin/pytest \
  tests/test_review_evidence_snapshots.py \
  tests/test_daily_data_pipeline.py \
  tests/test_dashboard_readiness.py -q

/Users/xiwei/stock_research/.venv/bin/python -m stock_research.cli snapshot-review-evidence \
  --run-id eod-YYYY-MM-DD-local \
  --trade-date YYYY-MM-DD \
  --output-dir outputs/research/stock_daily_data_pipeline/YYYY-MM-DD \
  --limit 30
```

## Batch E Reserved

- Add a dashboard data-quality view for snapshot coverage history.
- Link operator decisions to generated snapshot IDs during decision write, not only read-model parsing.
- Add retention/archival policy for old snapshot payloads.
