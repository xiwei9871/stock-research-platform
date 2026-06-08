# Market Emotion State V1 Design

## Objective

Build a reproducible daily A-share market emotion factor from 2023-01-03 through the latest available trading date. The factor should estimate short-term market赚钱效应 using breadth, limit-up/limit-down ecology, relay strength, prior-day strong-stock feedback, and liquidity.

This module is an input layer only. It must not directly choose stocks or directly size positions. Style selection and position control consume the emotion factor separately.

## Scope

V1 produces daily market-level rows with:

- `emotion_score`: 0-100 composite score.
- `emotion_state`: `panic`, `cold`, `neutral`, `hot`, or `euphoria`.
- `risk_state`: `low`, `medium`, or `high`.
- Component scores: `breadth_score`, `limit_score`, `relay_score`, `feedback_score`, `liquidity_score`.
- Raw diagnostics needed to audit the score.
- Hints for downstream consumers: `style_signal_hint` and `position_budget_hint`.

V1 also writes research outputs for long-period analysis and joins the emotion state to existing mid-trend backtest equity paths for state-by-state attribution.

## Data Sources

Use only stable daily data available in the local database:

- `market_daily_bar`: daily stock OHLCV, `pct_chg`, `amount`, `turnover_rate`, `adjust_type`.
- `core.asset_status_daily`: `is_trade`, `is_st`, `is_suspended`, `is_limit_up`, `is_limit_down`, `limit_up_price`, `limit_down_price`.
- `core.asset`: board flags and listing dates, if needed for filters.

Do not depend on intraday minute bars in V1 because the current `market.stock_minute_bar` 5-minute `hfq` coverage is empty. Intraday-only indicators such as first seal time, seal amount, and open-count are out of scope for V1.

## Open-Like Emotion Mapping

V1 approximates the common market-emotion dashboard structure:

| Market emotion concept | V1 reproducible proxy |
| --- | --- |
| Turnover amount | Total A-share `amount`, plus 5/20 day amount ratio |
| Advancers / decliners | Counts of `pct_chg > 0` and `pct_chg < 0` |
| Limit-up / limit-down count | `is_limit_up` and `is_limit_down` counts |
| Relay performance | Consecutive limit-up streaks and 1-board/2-board/3-board/high-board counts |
| Height board | Maximum consecutive limit-up streak on the day |
| Broken limit-up rate | Daily proxy: `high >= limit_up_price` and `close < limit_up_price` |
| Yesterday limit-up feedback | Today's return, red-rate, and limit-down rate for yesterday's limit-up stocks |
| Yesterday relay feedback | Today's return and survival for yesterday's 2+ board stocks |
| Yesterday broken-board feedback | Today's return and repair rate for yesterday's broken limit-up stocks |

The mapping is intentionally transparent so future manual comparison against 开盘啦 screenshots or exported values can be reviewed metric by metric.

## Score Components

The composite score is:

```text
emotion_score =
  0.25 * breadth_score
+ 0.25 * limit_score
+ 0.20 * relay_score
+ 0.20 * feedback_score
+ 0.10 * liquidity_score
```

Each component is clipped to `[0, 100]`.

### Breadth Score

Captures broad赚钱效应:

- `up_ratio = up_count / traded_count`
- `down_ratio = down_count / traded_count`
- `strong_up_ratio = pct_chg >= 5%`
- `strong_down_ratio = pct_chg <= -5%`

High breadth requires many advancers and few broad losers. Breadth should penalize days where the index is strong but most stocks are weak.

### Limit Score

Captures涨跌停生态:

- `limit_up_count`
- `limit_down_count`
- `net_limit_count = limit_up_count - limit_down_count`
- `limit_up_ratio`
- `limit_down_ratio`
- `broken_limit_up_rate`

High scores require enough limit-up names, limited跌停 pressure, and acceptable broken-board pressure.

### Relay Score

Captures连板接力:

- `first_board_count`
- `second_board_count`
- `third_board_plus_count`
- `high_board_height`
- `relay_count = second_board_count + third_board_plus_count`
- `relay_ratio = relay_count / max(limit_up_count, 1)`

High scores require not only many first boards, but also visible relay height. Very high boards with poor breadth should not dominate the total score because relay is only 20% of the composite.

### Feedback Score

Captures yesterday's strong-stock next-day feedback:

- Yesterday limit-up basket: average return, red-rate, limit-down rate.
- Yesterday relay basket: average return, red-rate, continued-limit-up rate.
- Yesterday broken-board basket: average return, red-rate, limit-down rate.

Feedback is central because bear-market false rallies often show one-day limit-up activity followed by poor next-day performance.

### Liquidity Score

Captures whether market emotion is backed by active turnover:

- `total_amount`
- `amount_ratio_5_20`
- Optional percentile rank of total amount within a rolling 120-day window.

Liquidity is only 10% because active turnover can occur in both bullish expansion and panic liquidation.

## State Classification

Classify `emotion_state` from the composite score:

```text
emotion_score >= 80: euphoria
65 <= emotion_score < 80: hot
45 <= emotion_score < 65: neutral
30 <= emotion_score < 45: cold
emotion_score < 30: panic
```

Classify `risk_state` independently:

- `high`: severe limit-down pressure, very high broken-board rate, very weak prior-day feedback, or very poor breadth.
- `medium`: mixed breadth, shrinking liquidity, weak feedback, or elevated broken-board pressure.
- `low`: healthy breadth, stable or strong limit ecology, and non-negative prior-day feedback.

`risk_state` must not be a simple inverse of `emotion_score`. Euphoria with a high broken-board rate can still be risky.

## Downstream Contract

The factor exports two hints but does not enforce them:

- `style_signal_hint`: descriptive market context such as `growth_favorable`, `defensive_preferred`, `rotation`, or `unstable`.
- `position_budget_hint`: descriptive budget band such as `full`, `reduced`, `light`, or `blocked`.

These hints are audit fields only in V1. Actual style switching and position sizing must be implemented as separate strategy layers.

## Outputs

Default output directory:

```text
outputs/research/market_emotion_state_v1_<start>_<end>/
```

Files:

- `market_emotion_state_daily.csv`
- `market_emotion_state_report.md`
- `market_emotion_state_distribution.csv`
- `market_emotion_state_year_breakdown.csv`
- `market_emotion_mid_trend_state_breakdown.csv`

The daily CSV is the canonical factor output.

## CLI

Add a research CLI command:

```text
market-emotion-state-v1-backfill
  --start-date
  --end-date
  --adjust-type hfq
  --output-dir
  --mid-trend-equity-path optional
```

If `--mid-trend-equity-path` is provided, the command joins emotion states to the equity curve and writes state-by-state strategy attribution. If omitted, it only writes the factor outputs.

## Testing

Unit tests must cover:

- Limit-up streak calculation across dates.
- Broken-board proxy calculation.
- Prior-day limit-up and relay feedback.
- Score clipping and state classification.
- Risk state independence from raw score.
- CLI output smoke test using small synthetic frames.

## Validation Plan

Run the full backfill from 2023-01-03 to 2026-06-05 and inspect:

- Yearly distribution of `emotion_state` and `risk_state`.
- Whether 2023 and 2024 show more `panic/cold/high` states than 2025 and 2026.
- Existing mid-trend performance by emotion state.
- Cases where emotion score disagrees with intuitive market regime; these become tuning candidates.

The first acceptance criterion is diagnostic usefulness, not immediate strategy improvement.
