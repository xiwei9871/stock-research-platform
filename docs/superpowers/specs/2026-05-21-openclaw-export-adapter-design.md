# OpenClaw Export Adapter Design

## Scope

This spec covers the first phase of an OpenClaw delivery path for report delivery.

The phase is explicitly an export adapter, not a live sender.

It reads the existing Local Delivery `manifest.json`, filters and transforms artifacts
that are suitable for OpenClaw, and writes a structured local export package for later
consumption.

## Goals

The adapter should:

1. read Local Delivery `manifest.json`
2. select exportable artifacts
3. convert them into structured OpenClaw items
4. write local export files
5. record export status locally
6. support dry-run by default
7. avoid any dependency on a running OpenClaw environment

## Non-Goals

This phase does not:

- call OpenClaw
- connect to OpenClaw Gateway
- send any external request
- perform AI reasoning
- generate investment conclusions
- trigger trading or execution
- replace Local Delivery as the source of truth

## Architecture

The adapter should be implemented as a separate module:

- `src/stock_research/report_delivery_openclaw.py`

This keeps Local Delivery focused on artifact collection and local packaging, while
OpenClaw export becomes a downstream transformation layer.

The local delivery module remains the source of the normalized artifact contract.

## Data Flow

1. Local Delivery writes `manifest.json`
2. OpenClaw Export Adapter loads that manifest
3. It selects artifacts based on routing and severity rules
4. It builds one structured export item per selected artifact
5. It writes:
   - `openclaw_manifest.json`
   - `openclaw_items.jsonl`
   - `openclaw_delivery_log.jsonl`

This is a reference-style export:

- `source_paths`
- `evidence_paths`
- `run_card_path`

all point to existing Local Delivery outputs. The adapter does not copy files into a new
artifact bundle.

## Core Types

### `OpenClawExportItem`

Each selected artifact becomes one export item with these fields:

- `item_id`
- `artifact_id`
- `report_type`
- `title`
- `summary`
- `severity`
- `requires_attention`
- `delivery_priority`
- `tags`
- `source_paths`
- `evidence_paths`
- `run_card_path`
- `recommended_action`
- `openclaw_route`
- `payload`

### `OpenClawExportResult`

The overall export result should include:

- `export_id`
- `channel`
- `status`
- `trade_date`
- `item_count`
- `output_dir`
- `openclaw_manifest_path`
- `openclaw_items_path`
- `openclaw_delivery_log_path`
- `warnings`
- `errors`
- `generated_at`

### `OpenClawExportAdapter`

The adapter should provide:

- `load_local_manifest(...)`
- `select_openclaw_artifacts(...)`
- `build_openclaw_item(...)`
- `export(...)`
- `write_openclaw_log(...)`

## Manifest Input

The input source is the Local Delivery `manifest.json`.

The adapter should treat Local Delivery as authoritative for:

- `artifact_id`
- `report_type`
- `severity`
- `summary`
- `tags`
- `recommended_channels`
- `requires_attention`
- `delivery_priority`
- `metadata`

This adapter must not re-run business classification logic.

If the input manifest is missing, unreadable, or structurally invalid:

- return a clear error
- do not crash with an opaque traceback

## Artifact Selection Rules

Default export behavior:

- only export artifacts whose `recommended_channels` contains `openclaw`

Optional flags:

- `--include-all`: export all artifacts, regardless of channels
- `--min-severity`: only include artifacts with severity at or above the chosen level

Default severity threshold:

- `info`

Selection constraints:

- do not auto-promote severity
- do not drop `run_card_bundle` simply because `requires_attention` is false
- skip artifacts whose referenced source paths do not exist, while recording a warning
- if no artifact matches, still write an empty export package and warning instead of
  crashing

## Recommended Action Rules

The adapter should map artifact types to routing-friendly actions:

- `run_card_bundle` -> `review_evidence`
- `daily_topn_report` -> `review_topn_candidates`
- `watchlist_report` -> `review_watchlist`
- `must_watch_report` -> `review_must_watch`
- `risk_alert_report` -> `review_risk_alert`
- `factor_eval_report` -> `review_factor_eval`
- `backtest_report` -> `review_backtest`
- `generic_report` -> `review_report`

These are static mappings, not model-generated judgments.

## OpenClaw Route Rules

The adapter should map artifacts to export routes using these rules:

1. if `requires_attention == true`, route to `research_alert`
2. else if `report_type == run_card_bundle`, route to `evidence_review`
3. else if `report_type` is one of:
   - `daily_topn_report`
   - `watchlist_report`
   - `must_watch_report`
   route to `daily_research`
4. else if `report_type` is one of:
   - `factor_eval_report`
   - `backtest_report`
   route to `research_validation`
5. else route to `research_inbox`

## Payload Shape

`payload` should be a structured export view of the original artifact.

It should include at least:

- `title`
- `summary`
- `severity`
- `report_type`
- `tags`
- `source_paths`
- `evidence_paths`
- `metadata`
- `warnings`

The adapter should not synthesize conclusions or advice.

## Output Directory

Recommended output path:

- `outputs/report_delivery/openclaw/YYYY-MM-DD/`

Example:

```text
outputs/report_delivery/openclaw/2026-05-20/
  openclaw_manifest.json
  openclaw_items.jsonl
  openclaw_delivery_log.jsonl
```

## Output Files

### `openclaw_manifest.json`

Must include:

- `generated_at`
- `trade_date`
- `channel`
- `dry_run`
- `source_manifest_path`
- `item_count`
- `items`
- `warnings`
- `errors`

### `openclaw_items.jsonl`

One JSON object per exported item, containing at least:

- `item_id`
- `artifact_id`
- `report_type`
- `title`
- `summary`
- `severity`
- `requires_attention`
- `delivery_priority`
- `tags`
- `source_paths`
- `evidence_paths`
- `run_card_path`
- `recommended_action`
- `openclaw_route`
- `payload`

### `openclaw_delivery_log.jsonl`

Each line must contain at least:

- `export_id`
- `generated_at`
- `channel`
- `status`
- `trade_date`
- `item_count`
- `openclaw_manifest_path`
- `openclaw_items_path`
- `error_message`

## Dry-Run Semantics

Dry-run is the default.

In dry-run mode:

- the adapter still writes `openclaw_manifest.json`
- the adapter still writes `openclaw_items.jsonl`
- the adapter still writes `openclaw_delivery_log.jsonl`
- the delivery log status should be `dry_run`
- no external service is contacted

This makes dry-run fully auditable and replayable.

## CLI

Add a new CLI command:

```bash
stock-research report-delivery-openclaw-export \
  --trade-date 2026-05-20 \
  --manifest outputs/report_delivery/2026-05-20/manifest.json \
  --output-dir outputs/report_delivery/openclaw/2026-05-20 \
  --dry-run
```

Optional flags:

- `--include-all`
- `--min-severity info`
- `--no-dry-run`

Behavior:

- default `dry_run=True`
- return clear errors for missing manifest path
- allow empty export result with warnings
- never attempt to call OpenClaw

## Error Handling

The adapter should handle these cases explicitly:

- missing input manifest
- invalid manifest JSON
- invalid artifact rows inside manifest
- missing source paths
- no matching artifacts

Error handling should be stable and local:

- record warnings for recoverable cases
- record errors for export-level failures
- avoid uncaught tracebacks in ordinary bad-input scenarios

## Testing

Add tests in:

- `tests/test_report_delivery_openclaw.py`

At minimum cover:

1. loading Local Delivery manifest
2. exporting only artifacts with `recommended_channels` containing `openclaw`
3. `--include-all` exporting all artifacts
4. `--min-severity` filtering artifacts
5. `run_card_bundle` action -> `review_evidence`
6. `daily_topn_report` action -> `review_topn_candidates`
7. `risk_alert_report` action -> `review_risk_alert`
8. `requires_attention=true` route -> `research_alert`
9. `run_card_bundle` route -> `evidence_review`
10. `daily_topn_report` route -> `daily_research`
11. writing `openclaw_manifest.json`
12. writing `openclaw_items.jsonl`
13. writing `openclaw_delivery_log.jsonl` with stable dry-run behavior
14. clear error for missing input manifest
15. empty match set without crash
16. no external service access

If the CLI is tested in `tests/test_factor_cli.py`, add focused command coverage there as
well.

## Documentation Update

Append a short `OpenClaw Export Adapter` section to:

- `docs/quant_system/12_p1_report_delivery_adapter_plan.md`

It should explain:

1. first phase is export-only
2. input is Local Delivery `manifest.json`
3. outputs are `openclaw_manifest.json`, `openclaw_items.jsonl`, and
   `openclaw_delivery_log.jsonl`
4. `recommended_action` rules
5. `openclaw_route` rules
6. CLI example
7. dry-run semantics
8. later live sender remains separate

## Scope Discipline

This phase should not:

- add Feishu integration
- add OpenClaw live sending
- add AI reasoning
- add portfolio or trading behavior
- refactor Local Delivery architecture beyond what export integration requires
