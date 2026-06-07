# Market Style Switch V1 Design

## Objective

Build a research-layer style switching framework that consumes daily market emotion state and decides which stock-selection style should be preferred. It must keep style selection separate from position sizing.

V1 answers: when market emotion changes, should the strategy prefer growth/momentum, rotation/balanced, defensive/yield-proxy, or wait/cash-like behavior?

## Core Boundary

The system has three separate layers:

1. `market_emotion_state_v1`: describes daily short-term market emotion and risk.
2. `market_style_switch_v1`: chooses the preferred stock-selection style for the day.
3. Position budget layer: decides how much capital to deploy.

`market_style_switch_v1` must not directly size positions. It may output a descriptive `position_budget_hint` for audit, but actual capital allocation remains a downstream module.

## Inputs

Required:

- `market_emotion_state_daily.csv` from `market_emotion_state_v1`.
- Existing mid-trend funnel detail, including score, rank, industry, volatility, drawdown, and trend fields.
- Daily prices from `market_daily_bar`.
- Industry membership from `core.industry_membership`.

Optional:

- `finance.indicator_quarter.roe`.
- `finance.cash_flow.net_operate_cash_flow` and `finance.cash_flow.capex`.

Not required in V1:

- Dividend yield.
- PB/PE/market-cap valuation.
- Real-time sector heat.
- Intraday order book or seal amount.

The local database currently does not expose a stable dividend-yield or valuation table, so V1 uses a defensive/yield proxy rather than a true high-dividend factor.

## Style States

V1 outputs one `style_state` per trade date:

- `growth_momentum`: growth, technology, high relative strength, strong trend continuation.
- `rotation_balanced`: balanced allocation when emotion is constructive but not decisive.
- `defensive_yield_proxy`: defensive/high-dividend-like proxy using industry, low volatility, drawdown quality, and basic profitability.
- `cash_or_wait`: style selection should not be trusted; downstream position budget should be conservative.

## Emotion-to-Style Mapping

Initial deterministic mapping:

| Emotion state | Risk state | Style state |
| --- | --- | --- |
| `euphoria` | `low` | `growth_momentum` |
| `euphoria` | `medium` | `growth_momentum` |
| `euphoria` | `high` | `rotation_balanced` |
| `hot` | `low` | `growth_momentum` |
| `hot` | `medium` | `rotation_balanced` |
| `hot` | `high` | `cash_or_wait` |
| `neutral` | `low` | `rotation_balanced` |
| `neutral` | `medium` | `rotation_balanced` |
| `neutral` | `high` | `defensive_yield_proxy` |
| `cold` | `medium` | `defensive_yield_proxy` |
| `cold` | `high` | `defensive_yield_proxy` |
| `panic` | `high` | `cash_or_wait` |

This mapping is intentionally transparent. The first research pass should test whether these style states explain 2023-2026 return paths before optimizing thresholds.

## Growth Momentum Sleeve

The growth sleeve should reuse the current best mid-trend research stack:

- Candidate source: aligned mid-trend watch funnel detail.
- Selection preference: high mid-trend score, high relative strength, strong industry/mainline support.
- Risk control: compatible with the existing intraday overlay and score floor experiments.
- Output: ranked daily growth candidates.

This sleeve represents the strategy that worked best in 2025-2026.

## Defensive Yield Proxy Sleeve

The defensive sleeve approximates high-dividend/defensive behavior without requiring dividend-yield data.

### Industry Preference

Prefer industries such as:

- Electricity and utilities.
- Coal.
- Banks.
- Food and beverage.
- Liquor-like consumer staples, where industry naming allows.
- Household appliances and other stable cash-flow industries, where available.

The industry list must be configurable and visible in outputs.

### Stock-Level Filters

Prefer:

- Lower volatility.
- Smaller recent drawdown.
- Non-broken medium-term trend.
- Positive or stable ROE when finance data is available.
- Stable operating cash flow when available.

Reject:

- ST and suspended names.
- Stocks with severe recent drawdown.
- Stocks with strong negative momentum unless explicitly in a mean-reversion research variant.

### Anchor Checks

V1 should not hard-code anchors into the portfolio. It should report whether example defensive anchors appear in the candidate universe:

- 长江电力
- 中国神华
- 农业银行
- 伊利股份
- 贵州茅台

These checks are diagnostic only.

## Rotation Balanced Sleeve

The balanced sleeve should avoid an extreme all-growth or all-defensive choice:

- Use growth candidates when emotion is not hostile.
- Allow defensive candidates as stabilizers.
- Cap single-style concentration in attribution tests.

V1 can implement this as a deterministic mix in research outputs, for example 50% growth sleeve and 50% defensive proxy sleeve by target slots. This is still a style selection output, not final capital sizing.

## Cash or Wait State

`cash_or_wait` means style signals are unreliable or market risk is too high. V1 should still output the best available style candidates for inspection, but downstream strategy tests may treat this state as:

- no new growth entries,
- defensive-only watch,
- or cash filler.

The behavior must be parameterized in backtests, not hard-coded into the style-state generator.

## Research Backtests

Run 2023-01-03 through 2026-06-05 with three strategy families:

1. `fixed_mid_trend`: current best baseline, no style switching.
2. `emotion_budget_only`: emotion controls position budget, but selection remains mid-trend.
3. `emotion_style_switch`: emotion controls style sleeve selection, while position budget remains separately configurable.

The goal is to isolate whether improvement comes from:

- avoiding exposure,
- changing style,
- or both.

## Required Outputs

Default output directory:

```text
outputs/research/market_style_switch_v1_<start>_<end>/
```

Files:

- `market_style_state_daily.csv`
- `growth_momentum_candidates.csv`
- `defensive_yield_proxy_candidates.csv`
- `rotation_balanced_candidates.csv`
- `anchor_diagnostics.csv`
- `style_switch_backtest_summary.csv`
- `style_switch_year_breakdown.csv`
- `style_switch_emotion_breakdown.csv`
- `market_style_switch_v1_report.md`

## CLI

Add a research CLI command:

```text
market-style-switch-v1-backtest
  --start-date
  --end-date
  --emotion-path
  --funnel-detail-path
  --output-dir
  --top-n 5
  --defensive-industry-keywords
  --position-mode fixed|emotion_budget|cash_or_wait_light
  --adjust-type hfq
```

The CLI should generate style state, candidate sleeves, and comparative research results.

## Validation Questions

The first pass must answer:

1. Do `defensive_yield_proxy` periods align with 2023/2024 weak market behavior?
2. Does switching away from growth during `cold/high`, `neutral/high`, and `panic/high` reduce drawdown?
3. Does defensive proxy selection preserve enough return, or does it simply behave like cash?
4. Does `emotion_style_switch` outperform `emotion_budget_only`, proving that selection style matters beyond exposure?
5. Are the diagnostic anchors visible in defensive candidate pools on appropriate dates?

## Acceptance Criteria

V1 is acceptable as a research module if:

- It produces full-period daily style states from 2023-01-03 to 2026-06-05.
- It keeps style selection and position sizing separate in code and outputs.
- It writes all required diagnostic files.
- It reports year-by-year and emotion-state performance for each strategy family.
- It makes no production trading changes.

V1 is not required to outperform the current best strategy on the first run. The first objective is to determine whether style switching has independent explanatory value.
