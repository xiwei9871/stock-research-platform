# Trend Lifecycle V1 Design

## Goal

Build a label-first trend discovery research layer that can identify mid-sized trend stocks earlier than the current high-turnover Top20 rotation.

The current research proves that the factor stack contains alpha, but it does not prove that the strategy is practical for live trading. The main gaps are:

- Current Top20 selection tends to hit later lifecycle stages rather than early trend stages.
- Daily full rebalance creates very high turnover and short average holding periods.
- Previous strong backtests used idealized execution assumptions.
- Existing labels are mostly fixed forward returns, not trend-event lifecycle labels.

`trend_lifecycle_v1` should first improve labels and diagnostics, then test lower-turnover holding rules. It should not replace the current Top20 workflow until it passes explicit cost, drawdown, and turnover gates.

## Scope

In scope:

- Generate trend-event labels from historical daily bars.
- Classify trend lifecycle stages for small, mid, and large trends.
- Evaluate early and early-mid factor profiles for mid-trend stocks.
- Add point-in-time fundamental context as features and segmentation dimensions.
- Design a lower-turnover trend lifecycle backtest with realistic execution constraints.
- Produce reports that compare current Top20 hits against trend stages.

Out of scope:

- Broker integration or live order placement.
- Replacing production daily Top20 reports.
- Training a complex model before labels and diagnostics are validated.
- Hard maximum holding-day exits as a primary rule.

## Existing Context

Relevant current modules:

- `src/stock_research/labels.py` computes fixed-horizon forward return labels for 5, 10, 20, and 60 trading days.
- `src/stock_research/features.py` computes P0 daily features such as `ret_5d`, `ret_20d`, `ret_60d`, amount, turnover, volatility, MA20 deviation, and 20-day max drawdown.
- `src/stock_research/factor_pipeline.py` and `src/stock_research/factors/*` provide richer technical factors including 120-day momentum, trend structure, volume-price factors, and risk factors.
- `src/stock_research/vectorized_topn_backtest.py` supports TopN daily or weekly rebalance and transaction costs, but assumes target-weight execution and does not model limit-up or limit-down execution constraints.
- `src/stock_research/retention_backtest.py` already models next-open execution, retention, ST/suspension/liquidity filters, limit-up buy skips, MA20 exits, hard stops, and market/board filters.
- `reports/trend_lifecycle_20240527_20260508/trend_lifecycle_report.md` shows that current Top20 hit rate rises materially in later trend stages, implying the current score is better at confirming established moves than finding early trend entries.

## Trend Labels

Add a trend-event label set, separate from the existing forward-return label set.

Label set:

- `label_set = trend_event`
- `label_version = v1`

Trend event definitions:

| Label | Window | Low-to-future-high gain | Purpose |
| --- | ---: | ---: | --- |
| `small_trend` | 40-80 trading days | 25%-40% | Early warning pool |
| `mid_trend` | 60-120 trading days | 40%-80% | Main strategy target |
| `large_trend` | 120 trading days | >= 80% | Super trend study |

Event construction:

1. For each asset, scan daily bars in chronological order.
2. Use backward-visible lows only for features, but trend labels may use future highs because labels are supervised targets.
3. For each candidate low, find the maximum future high within the event window.
4. Create a trend segment when gain falls into the label bucket and average segment amount passes the liquidity threshold.
5. Deduplicate overlapping segments by keeping the stronger or earlier segment depending on label bucket:
   - for `large_trend`, keep highest gain;
   - for `mid_trend` and `small_trend`, prefer earlier non-overlapping segments when gains are similar, because the research goal is early intervention.

Each segment should include:

- `asset_id`
- `trend_label`
- `start_date`
- `peak_date`
- `start_close`
- `peak_close`
- `gain`
- `duration`
- `avg_amount`
- `max_drawdown_before_peak`

## Lifecycle Stages

Map each trend segment into lifecycle stages by progress from `start_date` to `peak_date`.

Stages:

| Stage | Segment progress |
| --- | ---: |
| `early` | 0%-20% |
| `early_mid` | 20%-40% |
| `mid` | 40%-60% |
| `late_mid` | 60%-80% |
| `late` | 80%-100% |

The primary research target is:

- `trend_label = mid_trend`
- `stage in ('early', 'early_mid')`

The existing `large_trend` report should remain useful, but it must not be the only training or validation target because it overrepresents extreme winners.

## Entry Success Labels

Add an entry-oriented label for practical signal validation.

For each signal date and asset:

- `entry_success_20d`: reaches +15% within 20 trading days before hitting -8%.
- `entry_success_40d`: reaches +25% within 40 trading days before hitting -12%.
- `entry_success_60d`: reaches +35% within 60 trading days before hitting -12%.

These labels answer whether a signal was early enough and tradable enough, not merely whether the stock eventually became a trend stock.

## Feature Families

### Technical Trend Features

Use existing factors and add missing derived features only when necessary:

- Momentum: `ret_5`, `ret_10`, `ret_20`, `ret_60`, `ret_120`, `momentum_20_5`, `momentum_60_5`.
- Trend structure: `close_above_ma20`, `close_above_ma60`, `ma20_slope`, `ma60_slope`, `ma_alignment`, `trend_r2_20`, `distance_ma20`, `distance_ma60`.
- Breakout and price-volume: `new_high_20`, `new_high_60`, `amount_ratio_5_20`, `volume_ratio_5_20`, `turnover_ratio_5_20`, `price_volume_corr_10`, `amount_breakout`, `volume_breakout`.
- Risk and exhaustion: `volatility_20`, `max_drawdown_20`, `atr_pct`, `upper_shadow_ratio`, `large_volume_down_day`.

Early trend scoring should reward sustained trend emergence and penalize late-stage overheating:

- penalize extreme `ret_5`;
- penalize excessive `distance_ma20`;
- penalize abnormal volatility and large short-window drawdown;
- distinguish healthy volume expansion from one-day blowoff volume.

### Market And Board Context

Keep market and board filters as context features, not only as hard gates:

- broad market up ratio;
- limit-up and limit-down balance;
- market amount relative to its 20-day mean;
- board median return;
- board up ratio;
- board volume/amount expansion;
- stock return versus board and broad index.

### Fundamental Context V1

Add point-in-time fundamental context. These features should initially be used for segmentation and soft scoring, not as aggressive hard filters.

Daily valuation and size features:

- total market capitalization;
- free-float market capitalization;
- PE, PB, PS, and their industry-relative ranks;
- turnover value and amount percentile;
- volume ratio / amount ratio where available.

Financial statement features:

- revenue growth;
- net profit growth;
- ROE;
- gross margin;
- operating cash flow quality;
- debt ratio;
- goodwill or impairment risk if available;
- consecutive loss / profit warning risk if available.

Point-in-time rule:

- Financial statement data must become available by announcement date, not report period end date.
- Daily market-derived fields such as market cap, PE, and volume ratio may use same-day available values.
- Any feature that cannot be reconstructed point-in-time must be excluded from backtest scoring or marked as research-only diagnostics.

Hard fundamental filters should be limited to severe risk cases:

- ST or delisting-risk names;
- suspended or non-tradable assets;
- extreme low liquidity;
- serious financial anomaly when a point-in-time flag exists.

Valuation should not be a strict early filter by default, because many trend leaders start with high or distorted valuation metrics.

## Candidate Scoring

The first version should remain interpretable.

Recommended score blocks:

- trend emergence score;
- relative strength score;
- volume confirmation score;
- risk/exhaustion penalty;
- market/board context adjustment;
- fundamental context adjustment.

The report must show the contribution of each block so failures can be diagnosed. A later ML classifier can be considered only after the label and feature diagnostics are stable.

## Backtest Design

The lifecycle backtest should test whether early trend signals can be held with lower turnover.

Portfolio rules:

- `max_positions = 20`; this is a maximum number of holdings, not a maximum holding-day limit.
- Do not set a fixed maximum holding period in V1.
- Daily scan for new candidates.
- Limit daily new buys or replacements to 2-4 assets.
- Equal-weight or capped equal-weight position sizing.
- Existing positions continue to be held while trend quality remains acceptable.

Entry rules:

- Signal generated after close on day T.
- Buy at next tradable open on T+1.
- Skip buy when stock is ST, suspended, below liquidity threshold, or opens at limit-up.
- Prefer candidates in `mid_trend` early/early-mid profile, but never use future labels in live-like scoring.

Exit rules:

Exit should be driven by trend damage, not by simply falling out of Top20.

Primary exit triggers:

- close or open proxy below MA20 for 2 consecutive signal days;
- MA20 slope turns negative;
- rank or score deteriorates for 3 consecutive signal days;
- drawdown from holding high reaches 12%-15%;
- hard stop loss reaches 8%-10%;
- severe liquidity/tradability deterioration.

If a sell cannot execute because the stock is suspended or limit-down, the exit should roll forward to the next tradable open.

Holding time:

- No fixed maximum holding days in the main rule.
- Report actual holding-day distribution.
- Add diagnostic buckets such as 1-5, 6-10, 11-20, 21-40, 41-60, and 60+ trading days.
- Optional future experiment: after 40 or 60 holding days, require either new highs, positive MA20 slope, or acceptable drawdown to continue holding.

## Transaction Costs And Execution

Run cost scenarios:

| Cost setting | Meaning |
| ---: | --- |
| 0 bps | idealized reference |
| 10 bps | 0.10% per traded notional |
| 20 bps | 0.20% per traded notional |
| 30 bps | 0.30% per traded notional |

For example, 20 bps means 0.20%. Buying 100,000 CNY costs 200 CNY, and selling another 100,000 CNY costs another 200 CNY if the cost is applied on each trade.

Execution assumptions must include:

- next-open execution;
- limit-up buy skip;
- limit-down or suspended sell roll-forward;
- ST and suspension filters;
- minimum amount/liquidity filters;
- integer lot sizing if using account-style simulation.

## Reports

Generate the following outputs:

1. Trend segment CSV for small, mid, and large trend labels.
2. Lifecycle sample CSV with stage assignments.
3. Factor profile report for `mid_trend` early and early-mid stages.
4. Current Top20 stage-hit report.
5. Entry success label report for 20/40/60-day horizons.
6. Backtest tear sheet across 0/10/20/30 bps costs.
7. Holding-time and turnover diagnostics.
8. Fundamental segmentation report:
   - market-cap buckets;
   - valuation buckets;
   - profitable versus loss-making;
   - growth versus non-growth;
   - industry-relative valuation and growth buckets.

## Acceptance Criteria

Research acceptance:

- Trend labels are generated without future leakage in features.
- `mid_trend` early and early-mid factor profiles are reported separately from `large_trend`.
- Current Top20 lifecycle-hit diagnostics are reproducible.
- Fundamental features either obey point-in-time availability or are clearly excluded from scoring.

Strategy prototype acceptance:

- Annual return greater than 25%.
- Maximum drawdown less than 20%.
- Annual turnover below 60-90.
- 20 bps cost scenario remains clearly positive.
- Average realized holding days greater than 5-10.
- No reliance on a fixed maximum holding-day exit.

## Implementation Notes

Prefer extending existing research modules instead of replacing them:

- Add a trend label module rather than overloading `labels.py` fixed forward-return labels.
- Reuse `factor_pipeline.py` and factor modules for technical feature extraction.
- Reuse `retention_backtest.py` execution semantics where possible, because it already models next-open execution and tradability constraints.
- Add point-in-time fundamental joins through the existing finance services once coverage is verified.
- Keep reports under `reports/trend_lifecycle_v1_<start>_<end>/`.

The first implementation plan should focus on labels and diagnostics before changing portfolio rules.

