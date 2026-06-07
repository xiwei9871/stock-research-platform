# Intraday Risk Filter Backtest Design

## Goal

Validate whether intraday-derived risk signals can reduce bad entries and drawdown for existing TopN candidates without changing production scoring.

This is a research-only experiment. It must not write `factor.stock_score_daily`, must not approve factors, and must not alter daily cron behavior.

## Scope

The first version compares baseline TopN selection against two intraday risk-control variants over `2025-01-02` to `2026-06-05`.

Default backtest settings:

- score source: `factor.stock_score_daily`
- score version: `manual_v1`
- price source: `market_daily_bar`
- price adjust type: `hfq`
- intraday source: `factor.stock_intraday_features_daily`
- intraday feature version: `intraday_v1`
- intraday freq / adjust type: `5min` / `raw`
- rebalance frequency: `daily`
- transaction cost: `20` bps
- TopN values: `10` and `20`

## Inputs

### Scores

Load all candidate scores in the requested date range from `factor.stock_score_daily`.

Required columns:

- `trade_date`
- `asset_id`
- `rank`
- `score_total`

The baseline uses these scores unchanged.

### Prices

Load `market_daily_bar` for the same date range using `adjust_type='hfq'`.

Required columns follow `vectorized_topn_backtest.load_vectorized_topn_inputs` so the existing vectorized backtest engine can be reused.

### Intraday Risk Features

Use the risk-filter candidates identified by the intraday factor evaluation:

- `intraday_volatility_5min`
- `amount_front_1h_ratio`
- `last_30m_return`
- `afternoon_return`
- `close_to_vwap`

The experiment uses only same-day intraday features as an end-of-day signal. The existing backtest engine trades on the next execution date, so the design does not introduce same-day lookahead.

## Risk Signal Construction

Each trade date is evaluated cross-sectionally.

Version `v1` risk flags:

- `high_intraday_volatility`: `intraday_volatility_5min` is in the top 20% for that trade date.
- `high_front_loaded_amount`: `amount_front_1h_ratio` is in the top 20% for that trade date.
- `weak_last_30m`: `last_30m_return` is in the bottom 20% for that trade date.
- `weak_afternoon`: `afternoon_return` is in the bottom 20% for that trade date.
- `weak_close_to_vwap`: `close_to_vwap` is in the bottom 20% for that trade date.

Derived fields:

- `intraday_risk_flag_count`: number of active flags.
- `intraday_risk_level`:
  - `none`: 0 flags
  - `watch`: 1 flag
  - `high`: 2 or more flags

## Variants

### `baseline_topn`

Use original scores unchanged.

### `exclude_high_risk`

Remove assets with `intraday_risk_level='high'` from the candidate set before TopN selection. The next ranked assets are allowed to fill the portfolio.

If a trade date has insufficient non-high-risk candidates, the backtest may hold fewer than TopN positions. This must be visible in `holdings_count` and the summary.

### `penalty_high_risk`

Keep all assets but adjust scores:

- `watch`: subtract 5 points
- `high`: subtract 15 points

After adjustment, recompute rank per trade date by adjusted score descending, with `asset_id` as deterministic tie-breaker.

## Backtest Engine

Reuse `run_vectorized_topn_backtest` and `VectorizedTopNConfig`.

For each `top_n`, run all variants with identical:

- price input
- date range
- rebalance frequency
- transaction cost
- execution constraints

The experiment should produce directly comparable summary rows.

## Outputs

Create a report directory with:

- `intraday_risk_filter_variant_summary.csv`
- `intraday_risk_filter_daily_flags.csv`
- `intraday_risk_filter_variant_positions.csv`
- `intraday_risk_filter_variant_trades.csv`
- `intraday_risk_filter_report.md`

Summary metrics per `top_n` and variant:

- final equity
- total return
- annualized return
- annualized volatility
- Sharpe ratio
- max drawdown
- average turnover
- total transaction cost
- average holdings count
- minimum holdings count
- risk-flagged candidate count
- excluded high-risk count
- penalized candidate count

The Markdown report must lead with a concise comparison against baseline:

- whether max drawdown improved
- whether total return deteriorated
- whether Sharpe improved
- whether the result is suitable for promotion to shadow review

## Recommendation Rules

For each `top_n`, compare variants against `baseline_topn`.

- `promote_for_shadow_review`: max drawdown improves by at least 1 percentage point and total return is no worse by more than 2 percentage points.
- `watch_only`: drawdown improves, but total return deterioration is worse than 2 percentage points.
- `reject`: drawdown does not improve.

These rules are research gates only. They do not update production score configuration.

## Error Handling

- If no scores are available, produce empty artifacts and a report explaining missing score coverage.
- If no intraday features are available, run only `baseline_topn` and mark filter variants as unavailable.
- If prices are missing for a candidate, rely on the existing backtest engine behavior and surface the impact through holdings/trades output.

## Testing

Unit tests should cover:

- risk flag assignment by cross-sectional quantiles
- exclude variant removing high-risk assets and allowing lower-ranked replacements
- penalty variant recomputing ranks after score adjustment
- summary comparison and recommendation classification
- CLI parsing and dispatch

Integration verification should run the real 2025-01-02 to 2026-06-05 experiment for `top_n=10,20`.
