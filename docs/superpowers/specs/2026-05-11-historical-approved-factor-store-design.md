# Historical Approved Factor Store Design

## Purpose

Replace the short 3-day smoke-test flow with a durable historical research flow. Candidate factors should be computed first over a meaningful historical window and persisted to `factor.factor_daily`. Evaluation then decides which factors are effective. Only approved factors should be used for scoring, TopN backtests, and daily research outputs.

The first production research window is `2024-01-01` through the latest date that has enough forward-return label coverage in `label_snapshot`.

## Problem

The `2026-01-28` to `2026-01-30` run proved that the pipeline can move data through the system, but it was not large enough to test factor effectiveness. A 3-day sample will naturally fail gates such as `min_ic_count` and cannot support stable IC, RankIC, quantile return, turnover, or TopN backtest conclusions.

The business rule needs to be explicit:

1. `factor.factor_daily` is the candidate factor fact table. A row in this table means the factor was computed, not that it is effective.
2. `factor.factor_approval` is the effectiveness registry. A factor becomes usable for scoring only after evaluation writes an `approved` status for the target `score_version`.
3. `factor.stock_score_daily` should be generated from approved factors for research workflows that claim to use validated factors.

## Scope

In scope:

- Historical candidate factor backfill from `2024-01-01` to the latest label-covered date.
- A preflight step that discovers the latest usable end date from `label_snapshot` for required horizons.
- Batch evaluation of candidate factors already stored in `factor.factor_daily`.
- Approved-only score generation over the same historical range.
- TopN research/backtest workflows consuming approved-only scores.
- Operator documentation that makes the candidate/effective distinction clear.

Out of scope:

- Changing V3 strategy thresholds or trading rules.
- Treating TopN output as trading instructions.
- Adding new factor formulas as part of this design.
- Replacing existing tables or rewriting stored historical rows unnecessarily.
- One-click automation before the underlying stages are reliable and resumable.

## Data Model

`factor.factor_daily` remains the canonical long table for all computed candidate factors:

- `trade_date`
- `asset_id`
- `factor_name`
- `factor_group`
- `factor_value`
- `calc_version`
- `source`
- `source_data_version`

`factor.factor_approval` remains the gate table for evaluation results:

- `factor_name`
- `calc_version`
- `score_version`
- `status`, with `approved` required for scoring promotion
- `reason`
- `primary_horizon`
- `metrics`

`factor.stock_score_daily` stores score outputs for a score version. Research workflows that depend on validated factors must generate these rows using approved-only factor loading.

No new table is required for the first version. If backfill tracking becomes operationally painful, add a later `factor.factor_backfill_run` table rather than overloading the factor fact table.

## Candidate Factor Backfill

The backfill runner should compute every factor that the current factor pipeline can produce and store it in `factor.factor_daily`, even if that factor is not yet approved. This includes custom technical factors and external-reference factors such as Alpha101-style, GTJA191-style, and Qlib-style factors that are already integrated into the pipeline.

The runner should be resumable by date. Because `upsert_factor_daily` is idempotent on `(trade_date, asset_id, factor_name, calc_version)`, rerunning a date is safe.

The first operational range is:

- `start_date`: `2024-01-01`
- `end_date`: the latest date where all required label horizons are available
- required horizons: `5, 10, 20, 60`

The backfill command should report progress per trade date, including current date index, total dates, and rows written.

## Label Coverage Preflight

Before factor evaluation, the system should find a usable end date from `label_snapshot`.

The preflight should:

- Check `label_set='forward_return'` and `label_version='v1'`.
- Require all configured horizons, initially `5, 10, 20, 60`.
- Return the latest date that exists for every required horizon.
- Report factor coverage for the candidate factor names and requested range.
- Block evaluation when factor rows or label rows are absent.

This prevents repeating the 3-day smoke-run problem where the pipeline works but the evaluation sample is too small to prove anything.

## Evaluation And Approval

Evaluation reads candidate factors from `factor.factor_daily` and forward returns from `label_snapshot`.

Batch evaluation should be the normal path. It should accept factor names or use a curated candidate list from configuration. Each evaluated factor writes a row to `factor.factor_approval` with either `approved` or `rejected`.

Minimum sample criteria should be enforced before interpreting metrics. A factor with insufficient IC observations should be rejected with an explicit reason such as `insufficient_ic_count`, not silently omitted.

The gate remains responsible for deciding effectiveness. Backfill does not imply approval.

## Approved-Only Scoring

Historical scoring for research workflows should use:

```python
score_stored_factor_daily(..., approved_only=True, score_version="manual_v1")
```

This ensures the loader joins `factor.factor_approval` and only includes factors with `status='approved'` for the requested `score_version`.

The existing compatible scoring path may remain available for diagnostics, but docs and research workflows should treat approved-only scoring as the default for validated strategy analysis.

When no factors are approved, scoring should return zero rows and report that state clearly. It should not raise due to an empty factor frame.

## Research Workflow

The recommended operator sequence is:

1. Apply schema.
2. Refresh labels through the latest market date.
3. Run preflight to discover the latest label-covered end date.
4. Backfill candidate factors from `2024-01-01` through that end date.
5. Run coverage preflight for candidate factors and horizons.
6. Batch evaluate candidate factors and write approvals.
7. Score the historical range with approved factors only.
8. Run TopN research/backtest workflow on the approved-only scores.
9. Inspect tear sheet and approval results before changing daily reporting behavior.

After this sequence is stable, a wrapper command can orchestrate these steps, but each stage should remain independently runnable for debugging and reruns.

## Error Handling

- If labels do not cover every required horizon, the preflight should report the missing horizons and latest available dates.
- If candidate factor rows are missing for the requested range, evaluation should stop before producing misleading approvals.
- If a backfill date fails, the runner should print the failed date and preserve all successfully upserted previous dates.
- If approved-only scoring finds no approved factors, it should return zero score rows with a clear message.
- Generated reports and local caches remain ignored by Git.

## Testing

Unit tests should cover:

- Latest common label date discovery across horizons.
- Factor and label coverage status output.
- Candidate backfill progress reporting and idempotent per-date calls.
- Batch evaluation rejects insufficient samples explicitly.
- Approved-only scoring range calls `score_stored_factor_daily(..., approved_only=True)`.
- Empty approved factor sets produce zero score rows, not exceptions.

Real-data smoke tests should use a window large enough to satisfy `min_ic_count`; the 3-day January window should remain documented only as pipeline smoke evidence.

## Success Criteria

- The system can backfill all current candidate factors from `2024-01-01` to the latest label-covered date.
- Candidate factors are stored in `factor.factor_daily` before evaluation.
- Evaluation writes explicit approved/rejected statuses to `factor.factor_approval`.
- Historical scoring and TopN research can be run using only approved factors.
- Operators can distinguish candidate factor storage from effective factor approval.
- Full tests pass before implementation is considered complete.

## Self-Review

No placeholders remain. The design separates candidate factor computation from factor effectiveness, preserves current tables, and avoids changing V3 strategy behavior. The scope is focused on historical research flow and does not bundle new factor formulas or trading logic.
