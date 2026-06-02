# Dynamic Industry Focus Score V1 Design

## Goal

Build a point-in-time industry strength layer for the current high-turnover Top20 factor strategy.

The recent fixed three-industry test showed materially better 2026 returns, but those industries were selected after observing recent winners. That is not valid evidence for a 2024-2026 backtest. `industry_focus_score_v1` should decide which industries are focus industries each trading day using only information available on or before that date.

The first objective is not to replace the Top20 strategy. It is to test whether a dynamic industry gate can improve return, risk, and transaction-cost-adjusted performance versus the full-market Top20 baseline.

## Scope

In scope:

- Compute daily point-in-time industry strength scores.
- Rank industries cross-sectionally each trading day.
- Generate dynamic focus industry membership.
- Backtest current factor Top20 with dynamic industry gating.
- Compare fixed focus industries, dynamic focus industries, and the full-market baseline.
- Report industry selection history, turnover, coverage, and performance.

Out of scope:

- Broker integration or live trading.
- Replacing production daily Top20 reports.
- Training complex machine-learning models.
- Adding non-point-in-time fundamentals to scoring.
- Re-optimizing the existing stock-level factor formula in this phase.

## Existing Context

Relevant current modules and reports:

- `src/stock_research/factor_config.py` defines `manual_v1_config`, the current stock-level factor formula used in research tests.
- `src/stock_research/scoring/pipeline.py` computes stock scores from daily factor rows.
- `src/stock_research/vectorized_topn_backtest.py` runs TopN portfolio backtests with configurable transaction costs.
- Industry membership is available from `core.industry_membership`.
- Daily stock bars are available from `market_daily_bar`.
- The fixed-industry diagnostic report is in `reports/focus_industry_filter_20260101_20260512/`.

The fixed-industry diagnostic should be treated as hypothesis generation only. It must not be used as proof that the same three industries were knowable focus industries in 2024 or 2025.

## Point-In-Time Rule

For every rebalance date `t`:

1. Industry scores may use daily bar, factor, membership, and market data with `trade_date <= t`.
2. The selected focus industries for date `t` may be used to form holdings for the next return period.
3. No future industry return, future Top20 composition, future winner list, or report-period-end fundamental value may be used.
4. If a data field lacks a reliable as-of date, it is allowed only in diagnostics, not scoring.

## Industry Universe

Use first-level CSRC industries from `core.industry_membership` as the default industry system.

An industry is eligible on date `t` only if:

- it has at least 20 active tradable stocks after normal stock-level filters;
- it has enough price history to compute 60-day industry statistics;
- its aggregate daily amount is non-null for the scoring window.

The implementation should report excluded industries and exclusion reasons.

## Industry Score Components

Each component is computed daily per industry and then converted into a cross-sectional percentile rank across eligible industries. Higher is better unless explicitly marked as a penalty.

### 1. Industry Momentum

Purpose: identify industries already showing relative strength.

Candidate metrics:

- `industry_ret_20d`
- `industry_ret_60d`
- `industry_excess_ret_20d` versus equal-weight all-stock universe
- `industry_excess_ret_60d` versus equal-weight all-stock universe

Suggested component:

```text
momentum_score =
  0.35 * rank(industry_ret_20d)
+ 0.35 * rank(industry_ret_60d)
+ 0.15 * rank(industry_excess_ret_20d)
+ 0.15 * rank(industry_excess_ret_60d)
```

### 2. Industry Breadth

Purpose: distinguish broad industry strength from a small number of isolated stocks.

Candidate metrics:

- percentage of industry stocks with positive 20-day return;
- percentage above MA20;
- percentage above MA60;
- percentage making a 60-day high in the last 5 trading days.

Suggested component:

```text
breadth_score =
  0.30 * rank(up_ratio_20d)
+ 0.30 * rank(above_ma20_ratio)
+ 0.20 * rank(above_ma60_ratio)
+ 0.20 * rank(new_high_60d_ratio)
```

### 3. Volume And Amount Expansion

Purpose: identify industries with new capital attention without over-rewarding single-day blowoff volume.

Candidate metrics:

- industry amount 5-day average divided by 20-day average;
- industry amount 20-day average divided by 60-day average;
- percentage of industry stocks with amount 5/20 greater than 1.3.

Suggested component:

```text
volume_score =
  0.40 * rank(industry_amount_ratio_5_20)
+ 0.35 * rank(industry_amount_ratio_20_60)
+ 0.25 * rank(stock_amount_expansion_ratio)
```

### 4. Candidate Density

Purpose: measure whether the existing stock-level model is naturally concentrating in the industry.

Candidate metrics:

- count of stocks in current stock-level Top100 from the industry;
- Top100 industry share versus the industry's tradable-universe share;
- mean stock score of the industry's top decile.

Suggested component:

```text
candidate_density_score =
  0.45 * rank(top100_count)
+ 0.35 * rank(top100_overweight_ratio)
+ 0.20 * rank(top_decile_score_mean)
```

This component may use the current day's stock-level score because that score is already computed from point-in-time factor rows.

### 5. Trend Quality And Risk Penalty

Purpose: prefer industries with clean trends and avoid industries that are already overheated.

Candidate positive metrics:

- 20-day industry trend R2;
- closeness to 60-day high without excessive extension;
- lower 20-day drawdown than peers.

Candidate penalty metrics:

- industry 5-day return too high relative to 60-day return;
- amount 5/20 extreme value;
- 20-day volatility rank;
- one-day industry return spike.

Suggested component:

```text
quality_score =
  0.35 * rank(industry_trend_r2_20)
+ 0.25 * rank(near_high_score)
+ 0.20 * rank(-max_drawdown_20d)
+ 0.20 * rank(-volatility_20d)
```

Suggested overheat penalty:

```text
overheat_penalty =
  0.35 * rank(ret_5d)
+ 0.30 * rank(industry_amount_ratio_5_20)
+ 0.20 * rank(volatility_20d)
+ 0.15 * rank(one_day_return_abs)
```

## Composite Score

Default composite:

```text
industry_focus_score =
  0.30 * momentum_score
+ 0.20 * breadth_score
+ 0.20 * volume_score
+ 0.20 * candidate_density_score
+ 0.10 * quality_score
- 0.10 * overheat_penalty
```

The first version should keep weights fixed and documented. Weight optimization is out of scope for V1.

## Focus Industry Selection

Implement three selection modes:

### Mode A: Fixed Focus Industries

Use the three industries from the recent diagnostic:

- `计算机、通信和其他电子设备制造业`
- `专用设备制造业`
- `软件和信息技术服务业`

This mode is a diagnostic upper-bound and should be labeled as ex-post.

### Mode B: Dynamic Top K

Each trading day selects the top `K` industries by `industry_focus_score`.

Default:

- `K = 4`
- minimum score percentile: top 35% of eligible industries

### Mode C: Dynamic With Hysteresis

Reduce industry churn:

- enter focus list when industry rank is in Top 4;
- remain in focus list until industry rank falls below Top 8;
- maximum focus industries: 6;
- if fewer than 2 industries qualify, fall back to Top 2 by score.

This should be the recommended research candidate because industry leadership usually persists but daily rank noise can be high.

## Backtest Variants

Run the following variants over `2024-05-27` to the latest available validated date:

1. `base_top20`: full-market current Top20 baseline.
2. `fixed_focus_pool_top20`: select Top20 only from fixed focus industries.
3. `dynamic_topk_focus_pool_top20`: select Top20 only from Mode B industries.
4. `dynamic_hysteresis_focus_pool_top20`: select Top20 only from Mode C industries.
5. `base_top20_focus_hit_diagnostic`: do not change holdings; only report how many original Top20 names fall inside the dynamic focus list.

For each variant, run:

- zero-cost backtest;
- 20 bps transaction-cost backtest.

The backtest should preserve the current stock-level scoring formula. It should not train or tune a new stock selector in this phase.

## Reports

Write reports under:

```text
reports/industry_focus_score_v1_<start>_<end>/
```

Required files:

- `industry_scores.csv`
- `focus_industries_daily.csv`
- `top100_industry_daily.csv`
- `summary.csv`
- `monthly_returns.csv`
- `<variant>_cost0_equity.csv`
- `<variant>_cost20_equity.csv`
- `<variant>_cost0_positions.csv`
- `<variant>_cost20_positions.csv`
- `industry_focus_score_report.md`

The Markdown report must include:

- data interval and industry system;
- point-in-time assumptions;
- score component definitions and weights;
- selected focus industries by month;
- focus industry churn statistics;
- Top20 focus coverage statistics;
- 0 bps and 20 bps performance summary;
- yearly and monthly return comparison;
- drawdown comparison;
- known data limitations and missing fields;
- conclusion on whether dynamic industry gating improves the strategy.

## Validation

Add tests for:

- score calculation uses only data up to the score date;
- cross-sectional percentile ranks are computed by date;
- industries below minimum stock count are excluded;
- dynamic Top K selection is deterministic;
- hysteresis enter/exit behavior;
- fixed focus mode is labeled as ex-post diagnostic;
- backtest report includes 20 bps cost metrics.

## Acceptance Criteria

The phase is complete when:

- dynamic industry scores can be generated reproducibly for a date range;
- the full 2024-05-27 to latest validated-date comparison can run without manual industry selection;
- reports clearly separate ex-post fixed industries from point-in-time dynamic industries;
- 20 bps results are included;
- tests for score construction and industry selection pass;
- no production Top20 workflow is replaced.

## Next-Phase Ideas

Only after V1 diagnostics are reviewed:

- evaluate whether fundamentals can improve industry selection using announcement-date point-in-time data;
- test a softer industry boost instead of a hard industry gate;
- combine dynamic industry focus with trend lifecycle entry-success labels;
- test lower-turnover retention rules inside dynamic focus industries.
