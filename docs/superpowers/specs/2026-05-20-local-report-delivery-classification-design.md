# Local Report Delivery Artifact Classification Design

## Scope

This spec covers a narrow enhancement to the existing local report delivery baseline in
`src/stock_research/report_delivery.py`.

It upgrades collected local artifacts from loose file bundles into more explicit report
objects that can later be consumed by OpenClaw, Feishu, or other adapters.

This spec does not:

- add any external delivery channel
- change current report generation workflows
- change `run_card` or evidence bundle generation
- add AI agent behavior
- add automatic trading behavior

## Goals

The classification enhancement should:

1. improve `report_type` detection
2. add conservative `severity` detection
3. extract a short `summary` from existing content
4. enrich `metadata` with stable, JSON-safe detection fields
5. add top-level `tags`
6. add top-level `recommended_channels`
7. add top-level `requires_attention`
8. add top-level `delivery_priority`
9. preserve backward compatibility for existing manifest consumers

## Non-Goals

This work does not attempt to infer investment conclusions, score alpha quality, or
convert report artifacts into trading instructions.

If classification is uncertain, it should fall back to conservative defaults rather than
guessing aggressively.

## Existing Baseline

The current local delivery adapter already supports:

- local file scanning
- grouped artifact collection
- dry-run and non-dry-run delivery
- `manifest.json`
- `delivery_log.jsonl`
- a `report-delivery-local` CLI entrypoint

The missing piece is stronger semantic classification for each collected artifact.

## Data Model Changes

`ReportArtifact` should keep all existing fields and add these top-level fields:

- `tags: list[str]`
- `recommended_channels: list[str]`
- `requires_attention: bool`
- `delivery_priority: int`

`metadata` remains the place for detection details and source characteristics.

This keeps downstream consumers from having to decode nested metadata for common routing
and priority decisions.

## Classification Pipeline

Artifact collection remains responsible for discovering and grouping files.

After grouping, each artifact should pass through a lightweight classification stage:

1. `detect_report_type(...)`
2. `detect_severity(...)`
3. `extract_summary(...)`
4. `build_artifact_metadata(...)`
5. `classify_artifact(...)`

The implementation should remain rule-based and lightweight:

- use file names and directory names first
- read only small JSON payloads or the first lines of Markdown when needed
- prefer existing `run_card` metadata when available
- do not read large files in full
- do not fail hard on corrupt JSON or empty Markdown

## Report Type Detection

Supported report types:

- `daily_market_report`
- `daily_topn_report`
- `watchlist_report`
- `watchlist_signal_report`
- `must_watch_report`
- `risk_alert_report`
- `factor_eval_report`
- `backtest_report`
- `run_card_bundle`
- `generic_report`

### Fixed Detection Priority

The final resolution priority is fixed as:

1. `run_card_bundle`
2. `risk_alert_report`
3. `must_watch_report`
4. `watchlist_signal_report`
5. `watchlist_report`
6. `factor_eval_report`
7. `daily_topn_report`
8. `daily_market_report`
9. `backtest_report`
10. `generic_report`

### Detection Rules

#### `run_card_bundle`

Match when the artifact contains a `run_card.json` file or an `evidence/manifest.json`
bundle.

This is the highest-priority bundle type.

#### `risk_alert_report`

Match only when file name, directory name, Markdown title, explicit report type, or
artifact severity clearly indicates a risk alert shape.

Plain JSON fields such as `risk_score` are not sufficient by themselves.

#### `must_watch_report`

Match when file name, directory name, or title contains:

- `must_watch`
- `must-watch`
- `must watch`

#### `watchlist_signal_report`

Match when file name, directory name, or title clearly indicates signal output, such as
`watchlist_signals`.

#### `watchlist_report`

Match when file name, directory name, or title clearly indicates a watchlist report but
does not match `must_watch_report` or `watchlist_signal_report`.

#### `factor_eval_report`

Match when file name, directory name, or title contains terms such as:

- `factor_eval`
- `factor_evaluation`
- `factor review`

#### `daily_topn_report`

Match when file name, directory name, or title clearly indicates top-N or selection
output.

#### `daily_market_report`

Prefer specific market report markers instead of broad `market` matching. The primary
markers are:

- `daily_market`
- `market_state`
- `market_regime`
- `market_summary`
- `market_report`

#### `backtest_report`

Match when file name, directory name, or title contains terms such as:

- `backtest`
- `retention`
- `strategy_lifecycle`

#### `generic_report`

Fallback when nothing else matches.

## Severity Rules

Supported severities:

- `info`
- `low`
- `medium`
- `high`
- `critical`

Severity should remain conservative.

Rules:

- ordinary daily reports default to `info`
- ordinary TopN reports default to `info` or `low`
- ordinary watchlist observations default to `low`
- watchlist reports with explicit risk, breakdown, or overheating markers may rise to
  `medium`
- `risk_alert_report` should be at least `high`
- major anomalies, empty critical output, or explicit data quality failures may rise to
  `critical`
- if the signal is ambiguous, severity must fall back to `info`

The classifier must not overstate urgency.

## Summary Extraction

Summary should be short, factual, and derived only from existing content.

Priority:

1. use JSON `summary` when present
2. use `run_card` title, metrics, or warning summaries when available
3. use the first Markdown H1 title
4. fall back to a cleaned file or bundle name

The classifier must not generate investment advice or inferred market conclusions.

## Metadata Schema

`ReportArtifact.metadata` should remain JSON-serializable and include these stable keys:

- `source_path`
- `source_kind`
- `detected_by`
- `file_count`
- `has_markdown`
- `has_json`
- `has_csv`
- `has_run_card`
- `has_evidence_bundle`
- `run_id`
- `config_hash`
- `workflow_type`
- `date_range`
- `asset_count`
- `warning_count`

If a value is not available, store `null` rather than inventing it.

## Tags

`tags` should be a top-level list of stable routing tags.

Base mapping:

- `run_card_bundle` -> `run_card`, `evidence`
- `daily_topn_report` -> `daily`, `topn`
- `daily_market_report` -> `daily`
- `watchlist_report` -> `watchlist`
- `watchlist_signal_report` -> `watchlist`
- `must_watch_report` -> `watchlist`, `urgent`
- `risk_alert_report` -> `risk`, `urgent`
- `factor_eval_report` -> `factor`
- `backtest_report` -> `backtest`

Add `review_required` when `requires_attention` is true.

## Recommended Channels

`recommended_channels` should be a top-level routing hint.

Rules:

- all artifacts include `local`
- `generic_report` uses only `local`
- `run_card_bundle` adds `openclaw`
- `daily_topn_report` adds `openclaw`
- `watchlist_report` adds `openclaw`
- `high` or `critical` severity adds `feishu`

This field is advisory only. It does not trigger real delivery.

## Attention and Priority

`requires_attention` should be true when:

- severity is `high` or `critical`
- report type is `risk_alert_report`
- warning count is greater than zero

Otherwise it should default to false.

`delivery_priority` maps directly from severity:

- `critical` -> `100`
- `high` -> `80`
- `medium` -> `50`
- `low` -> `20`
- `info` -> `10`

## Error Handling

The classifier must be tolerant of partial or damaged artifacts.

Rules:

- corrupt JSON should add a warning and continue
- empty Markdown should not crash classification
- missing optional files should not fail delivery
- manifest generation should still succeed even if some artifact metadata is partial

## Manifest Compatibility

`manifest.json` keeps its current outer structure.

Each artifact entry retains all old fields and gains:

- `tags`
- `recommended_channels`
- `requires_attention`
- `delivery_priority`

Existing consumers that only read prior fields should continue to work.

## CLI Impact

The existing `report-delivery-local` command should automatically use the enhanced
classification.

CLI behavior remains backward compatible. Additional summary lines may be added, such as:

- `report_delivery|high_severity|N`
- `report_delivery|requires_attention|N`
- `report_delivery|report_types|...`

These additions must not break existing output parsing.

## Testing

Add or extend tests to cover:

1. daily report classification into `daily_market_report` or `daily_topn_report`
2. watchlist report classification
3. run-card bundle classification into `run_card_bundle`
4. risk report classification into `risk_alert_report`
5. generic fallback classification
6. default severity fallback to `info`
7. risk severity at least `high`
8. `requires_attention` for high or critical artifacts
9. `run_card_bundle` recommended channels including `openclaw`
10. `high` severity recommended channels including `feishu`
11. summary extraction from Markdown H1
12. summary extraction from JSON `summary`
13. metadata flags for Markdown, JSON, CSV, and run-card presence
14. manifest entries containing the new classification fields
15. corrupt JSON producing warnings without crashing

Update CLI tests only if output lines change.

## Rollout

This enhancement should ship as a local-only semantic upgrade on top of the current
Local Delivery Adapter baseline.

It prepares future OpenClaw and Feishu adapters by making artifact objects richer and
more stable, without coupling the current phase to any external service.
