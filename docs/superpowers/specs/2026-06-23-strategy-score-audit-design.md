# Strategy Score Audit Design

## Goal

Add a fixed, non-blocking audit workflow for the three official EOD strategies:

- `lhb_shortline`
- `mid_trend`
- `tech_bottleneck`

The workflow must let operators answer four questions for every selected stock on a given trade date:

1. Why was this stock selected?
2. What was the raw strategy score?
3. What score was published into the review queue?
4. Is the dashboard display score faithful to the strategy output?

This first phase does not block publication. It produces auditable artifacts, CLI output, and dashboard visibility so score and selection issues can be detected before they become operator confusion.

## Current Problem

The three official strategies do not expose a uniform score lineage.

- `Mid Trend` is relatively clean: the published score usually maps to `mid_trend_funnel_score`.
- `Tech Bottleneck` is relatively clean: the published score maps to `bottleneck_score * 100`.
- `LHB` is ambiguous: the current review queue can display `auction_enhanced_score`, which is partly an execution-state mapping rather than a pure raw candidate-strength score.

The concrete failure observed on `2026-06-22`:

- All five LHB names displayed `20.0`.
- That did not mean the five names had equal raw candidate quality.
- It meant all five names fell into `pending_intraday`, and the current published score used the mapped `auction_enhanced_score`.
- The raw structure score was not retained in the review-facing path, so operators could not tell whether the candidates were weak, tied, or simply missing intraday confirmation.

This is a trust problem, not only a display problem. We need a stable contract that records raw score, published score, display score, and the reason each differs.

## Scope

Phase 1 covers:

- official EOD publication for the three strategies
- audit artifact generation under `outputs/research/strategy_daily_eod/<trade_date>/`
- a CLI command to inspect the audit
- a lightweight dashboard API for audit summary and anomaly samples
- dashboard display of score source for review items

Phase 1 does not:

- block platform readiness
- redesign alpha models
- replace existing strategy contracts
- unify all strategy candidate engines behind a new internal framework

## Required Product Behavior

For every official strategy run on a trade date, the system must emit a unified audit detail table and a summary artifact.

Operators must be able to inspect, for each selected stock:

- selected rank
- selected flag
- raw candidate score
- raw candidate score source
- published score
- published score source
- display score
- display score source
- eligibility layer
- selection reason
- filter reason
- data date used
- anomaly flags

The review queue must continue to render even if audit anomalies exist, but the dashboard must surface that anomalies were found.

## Audit Data Model

Create a normalized audit artifact named:

- `strategy_score_audit_detail.csv`
- `strategy_score_audit_summary.json`
- `strategy_score_audit_report.md`

### Detail Rows

Each row represents one stock considered for official review output on one strategy and one trade date.

Required columns:

- `trade_date`
- `strategy_id`
- `strategy_name`
- `asset_id`
- `stock_name`
- `selected_flag`
- `selected_rank`
- `source_rank`
- `raw_candidate_score`
- `raw_candidate_score_source`
- `published_score`
- `published_score_source`
- `display_score`
- `display_score_source`
- `selection_reason`
- `eligibility_layer`
- `filter_reason`
- `data_date_used`
- `review_tier`
- `source_type`
- `strategy_run_id`
- `anomaly_flags`
- `notes`

### Summary Payload

Required summary fields:

- `trade_date`
- `generated_at`
- `strategies`
- `total_rows`
- `selected_rows`
- `anomaly_row_count`
- `anomaly_counts_by_type`
- `strategy_counts`

Each strategy summary must include:

- `strategy_id`
- `row_count`
- `selected_count`
- `anomaly_count`
- `published_score_sources`
- `display_score_sources`
- `raw_score_sources`
- `sample_anomalies`

## Score Semantics Contract

The audit must explicitly distinguish three score layers:

1. `raw_candidate_score`
2. `published_score`
3. `display_score`

Definitions:

- `raw_candidate_score`: the strategy-native strength score before review-queue publication transforms.
- `published_score`: the score written into `review_queue_strategy_manifest.csv` or an equivalent official review artifact.
- `display_score`: the score returned by the dashboard API and shown in the UI.

These values may be equal. If they differ, the reason must be recoverable from the audit fields and anomaly flags.

## Strategy-Specific Mapping Rules

### LHB

LHB must preserve both:

- raw structure score
- execution-state or confirmation score

For Phase 1:

- `raw_candidate_score` should prefer `final_score` when available.
- If `final_score` is unavailable, fall back to `score_total` from the raw LHB candidate ranking stage.
- `published_score` may remain `auction_enhanced_score` for compatibility in the first phase.
- `display_score` should mirror `published_score`.
- `eligibility_layer` should preserve `phase12a_rule_layer`.
- `selection_reason` should preserve values such as `candidate_reason`, confirmation context, or other LHB-specific reason fields when present.

If LHB publishes a mapped score but cannot provide a raw score, the row must receive `mapped_score_without_raw_score`.

### Mid Trend

Mid Trend should use:

- `raw_candidate_score = mid_trend_funnel_score`
- `published_score = mid_trend_funnel_score`
- `display_score = published_score`

If the review row was built from positions and the score had to be recovered via signal lookup, the audit should still record:

- `raw_candidate_score_source = mid_trend_funnel_score`
- `published_score_source = mid_trend_funnel_score`

### Tech Bottleneck

Tech Bottleneck should use:

- `raw_candidate_score = bottleneck_score`
- `published_score = bottleneck_score * 100`
- `display_score = published_score`

The audit must explicitly record the scale change:

- `raw_candidate_score_source = bottleneck_score`
- `published_score_source = bottleneck_score_x100`

If the scaled value does not match the published value within a small tolerance, the row must receive `published_score_mismatch`.

## Anomaly Rules

The audit must assign zero or more anomaly flags per row.

Phase 1 anomaly types:

- `missing_candidate_source`
- `missing_published_score_source`
- `missing_display_score_source`
- `missing_raw_candidate_score`
- `mapped_score_without_raw_score`
- `published_display_score_mismatch`
- `published_score_mismatch`
- `stale_source`
- `rank_only_placeholder_score`
- `unknown_selection_reason`

### Rule Definitions

`missing_candidate_source`
- Selected row has no recoverable candidate lineage.

`missing_published_score_source`
- Published score exists but score source is blank.

`missing_display_score_source`
- Dashboard display score exists but display source is blank in audit construction.

`missing_raw_candidate_score`
- Selected row has no raw candidate score.

`mapped_score_without_raw_score`
- Published or display score is based on a mapped layer score, but the raw candidate score is not available.

`published_display_score_mismatch`
- Dashboard display score differs from published score without a declared transform rule.

`published_score_mismatch`
- Strategy-specific published score mapping rule failed.

`stale_source`
- Candidate or score source date is older than the platform trade date.

`rank_only_placeholder_score`
- Score was synthesized from rank or another non-score placeholder.

`unknown_selection_reason`
- Selected row lacks any interpretable reason or eligibility context.

## Data Flow

### EOD Publish Flow

1. Strategy engine runs as it does today.
2. Official review rows are built.
3. Audit builder gathers source records from:
   - `signals`
   - `candidates`
   - `positions`
   - strategy-specific review artifacts when needed
4. Audit builder normalizes score lineage for each selected row.
5. Audit builder computes anomaly flags.
6. EOD output writes:
   - `review_queue_strategy_manifest.csv`
   - `strategy_score_audit_detail.csv`
   - `strategy_score_audit_summary.json`
   - `strategy_score_audit_report.md`
7. Dashboard and CLI read audit artifacts from the same dated output directory.

### Dashboard Flow

1. Review queue payload continues to read formal published review items.
2. Review items surface `score_source` directly when available.
3. New audit API reads the latest summary for the selected trade date.
4. Readiness and overview pages can show audit anomaly counts without blocking readiness.

## CLI

Add a command:

`stock-research strategy-score-audit --trade-date YYYY-MM-DD`

Expected behavior:

- load the dated summary and detail artifacts
- print one summary line per strategy
- print aggregate anomaly counts
- optionally print sample anomaly rows

Phase 1 CLI options:

- `--trade-date`
- `--strategy-id`
- `--anomalies-only`
- `--limit`

## Dashboard API

Add a lightweight endpoint:

- `/api/strategy-score-audit?trade_date=YYYY-MM-DD`

Response fields:

- `trade_date`
- `generated_at`
- `overall_status`
- `total_rows`
- `anomaly_row_count`
- `anomaly_counts_by_type`
- `strategies`
- `sample_rows`

`overall_status` values:

- `ok`
- `warning`
- `missing`

Phase 1 sets:

- `ok` when no anomalies exist
- `warning` when artifacts exist and anomalies exist
- `missing` when no audit artifacts exist for the trade date

## Dashboard UI

Phase 1 UI changes:

- review queue item facts should show `score_source` when available
- platform overview should show `策略打分审计` with:
  - status
  - anomaly row count
  - per-strategy anomaly counts
- a simple audit panel should show sample anomalies

This is intentionally lightweight. Phase 1 is for operational trust, not a new deep analytics screen.

## Implementation Boundaries

Add one new module for audit construction, for example:

- `src/stock_research/strategy_score_audit.py`

Responsibilities:

- normalize audit rows across strategies
- compute anomaly flags
- write detail, summary, and markdown report

Existing modules should keep their current responsibilities:

- `strategy_eod_publish.py`
  - orchestrates official EOD output
  - calls audit generation after review rows are finalized
- `dashboard/review_queue.py`
  - exposes published review rows
  - should not recompute score lineage logic beyond display needs
- dashboard API layer
  - reads audit artifacts and returns summary payload

## Testing Requirements

Tests must cover:

- audit row generation for each strategy
- LHB rows preserve both raw score and published score when both exist
- LHB rows flag `mapped_score_without_raw_score` when only mapped score exists
- Mid Trend rows report `mid_trend_funnel_score` lineage correctly
- Tech rows report `bottleneck_score` and scaled published score correctly
- summary counts aggregate anomalies correctly
- CLI reads and prints audit output
- dashboard API returns `missing`, `ok`, and `warning` states correctly
- review queue continues to show published rows even if audit warnings exist

## Rollout

Phase 1 rollout steps:

1. Add audit builder and tests.
2. Integrate audit generation into `strategy_eod_publish`.
3. Add CLI command.
4. Add audit API endpoint.
5. Add lightweight dashboard summary display.
6. Re-run `2026-06-22` and verify LHB anomaly is surfaced.

## Success Criteria

The feature is successful when operators can inspect any official selected stock and answer:

- what raw strategy score existed
- what published score was used
- what dashboard score was shown
- why the stock was selected
- whether any score-lineage anomaly exists

The system should make `2026-06-22` LHB immediately diagnosable from the audit output without requiring code inspection or manual artifact digging.
