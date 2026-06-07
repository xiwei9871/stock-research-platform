# Intraday Risk Control V2 Design

## Goal

Replace the first intraday risk-filter experiment with a strategy-aware design that treats short-horizon LHB/event trades and 10/20/30/60/90 day mid-trend trades differently.

The design remains research-only until separately approved. It must not write production scores, change cron behavior, or alter live portfolio decisions without a shadow-review step.

## Why V1 Needs Redesign

V1 used same-day cross-sectional top/bottom 20% thresholds for every signal and applied the result directly to TopN selection. That created three problems:

- The rule marked too many stocks as risky. In the 2025-01-02 to 2026-06-05 sample, `high` risk was about 28% of the full universe and `watch + high` exceeded 53%.
- Some features are ambiguous without context. High first-hour turnover can mean speculative exhaustion, but it can also mean better liquidity or active institutional trading.
- A single intraday state should not dominate mid-trend decisions. One weak afternoon is useful information, but it should not override a 20/60/90 day trend by itself.

## Strategy Split

### LHB Intraday Risk Filter

This channel is for LHB, event-driven, and short-horizon candidates where the next one to five trading days matter most.

Risk signals can have high weight because same-day liquidity, closing strength, and intraday reversal are directly relevant to next-day entry risk.

Allowed actions:

- Block new entry for severe one-day risk.
- Lower candidate rank for moderate one-day risk.
- Prefer candidates with strong close, stable VWAP support, and no abnormal front-loaded volume failure.
- Use next-day shadow backtest before any production use.

### Mid-Trend Intraday Risk Monitor

This channel is for 10/20/30/60/90 day trend positions.

Intraday risk is a slow risk monitor, not a one-day trading switch. Single-day risk only records evidence. Position reduction requires repeated risk or confirmation from trend deterioration.

Allowed actions:

- Single trigger: record only.
- Two to three recent triggers: reduce new-entry priority.
- Three or more triggers in five trading days: mark watch.
- Four to five or more triggers in ten trading days plus trend deterioration: allow score penalty or position reduction in research tests.
- No hard sell from intraday risk alone.

## Signal Construction

### Historical Normalization

V2 should compare a stock against its own recent history before comparing it with the market.

Candidate normalized features:

- `front_1h_ratio_zscore_20d`: first-hour turnover ratio relative to the stock's recent distribution.
- `intraday_volatility_zscore_20d`: same-day intraday volatility relative to the stock's recent distribution.
- `tail_weakness_zscore_20d`: last 30 minute return relative to the stock's recent distribution.
- `close_to_vwap_zscore_20d`: close versus VWAP relative to the stock's recent distribution.

Default lookback is 20 trading days. A 60 day lookback can be included in parameter scans for stability.

### Intraday Structure

V2 should use combinations that describe the day's path, not isolated raw extremes.

Primary structure rules:

- `front_loaded_failure`: first-hour volume is historically abnormal and afternoon return is weak.
- `morning_to_afternoon_reversal`: morning return is positive or strong, but afternoon return is materially weaker.
- `tail_confirmation_failure`: last 30 minute return is weak and close is below VWAP.
- `high_volatility_no_follow_through`: intraday volatility is abnormal, but close is weak relative to VWAP or morning high.

### Market And Industry Context

V2 should avoid penalizing a stock merely because the whole market or its industry sold off.

Context-adjusted candidates:

- stock afternoon return minus industry median afternoon return
- stock last 30 minute return minus industry median last 30 minute return
- stock close-to-VWAP minus industry median close-to-VWAP
- same-day market regime label based on index intraday return and breadth

For mid-trend use, stock-specific weakness should carry more weight than market-wide weakness.

## Risk Levels

### LHB Channel

Default one-day rules:

- `none`: no structural risk.
- `watch`: one moderate structural risk.
- `high`: two or more structural risks, or one severe front-loaded failure.

Initial actions for backtest:

- `watch`: score penalty only.
- `high`: compare both score penalty and entry block.

### Mid-Trend Channel

Default rolling rules:

- `none`: fewer than two recent risk triggers.
- `watch`: at least two triggers in five trading days, or at least three in ten trading days.
- `high`: at least three triggers in five trading days, or at least five in ten trading days.

Mid-trend `high` does not automatically sell. It becomes actionable only when at least one trend confirmation is present:

- close below 10 or 20 day moving average
- 20 day momentum turns negative
- industry relative strength deteriorates
- portfolio drawdown or position-level drawdown breaches the strategy threshold

## Backtest Design

### LHB Backtest

Compare baseline LHB candidates against:

- `lhb_penalty_watch_high`
- `lhb_block_high_entry`
- `lhb_block_high_plus_penalty_watch`

Evaluate one, three, and five trading day forward returns, drawdown, hit rate, and turnover.

### Mid-Trend Backtest

Compare baseline mid-trend TopN against:

- `trend_monitor_only`: records risk state without trading action.
- `trend_new_entry_penalty`: penalizes new entries when rolling risk is watch/high.
- `trend_confirmed_reduce`: acts only when rolling intraday risk and trend deterioration both trigger.

Evaluate 10/20/30/60/90 day behavior, turnover, transaction cost, max drawdown, and missed winners.

## Parameter Scan

Scan thresholds after the new structure is implemented:

- historical z-score thresholds: `1.0`, `1.5`, `2.0`
- cross-sectional residual thresholds: bottom/top `10%`, `15%`, `20%`
- rolling trigger windows: `5d`, `10d`, `20d`
- trigger counts: `2`, `3`, `4`, `5`
- penalty strengths: small, medium, large

Selection should prefer robustness across adjacent thresholds over the single best result.

## Promotion Gates

LHB promotion gate:

- improves next-day or five-day drawdown meaningfully
- does not materially reduce hit rate or expected return
- does not create excessive turnover
- survives at least one adjacent-threshold check

Mid-trend promotion gate:

- improves max drawdown by at least one percentage point
- total return drag is no worse than two percentage points
- turnover increase is controlled
- missed-winner count is acceptable
- confirmed-risk variant beats one-day direct filter variant

## Outputs

Research artifacts should include:

- daily signal table with raw, normalized, market-adjusted, and industry-adjusted fields
- LHB risk summary
- mid-trend rolling risk summary
- variant backtest summaries
- missed-winner diagnostics
- examples of high-risk days for manual inspection

## References Used For Design Direction

The design is aligned with intraday market microstructure findings that intraday volume, volatility, and returns have strong time-of-day patterns and that intraday return predictability is horizon-dependent. This supports normalizing by stock history and separating short-horizon event trades from mid-trend decisions.

- Heston, Korajczyk, and Sadka, intraday cross-sectional stock return patterns.
- Brock and Kleidon, intraday volume, volatility, and trading-pattern structure.
- A-share intraday predictability literature around early-session and late-session return behavior.

## Implementation Boundary

The next implementation should create new V2 research code and reports alongside V1. It should not delete V1 artifacts, mutate production score tables, or enable production cron behavior.
