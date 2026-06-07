# Market Regime Confirmation V1 Design

## Purpose

Build a market regime confirmation layer that turns daily raw market emotion into a continuous, confirmed market state for weekly mid-trend portfolio decisions.

The current market style switch uses same-day `emotion_state` and `risk_state` to change exposure and style. That is too reactive for this strategy. The mid-trend pipeline is a weekly trend-following strategy, so market state should influence portfolio-level exposure and style only after persistence is confirmed. Individual stock deterioration remains separate and can still trigger immediate replacement.

## Background

The 2024 policy cycle shows why daily state is not enough:

- From 2024-01-01 to 2024-09-23, fixed mid trend had deep losses and high drawdown. Emotion-aware exposure helped reduce losses.
- From 2024-09-24 to 2024-11-08, the market entered a policy-driven rally after financial policy support, and fast re-risking was necessary.
- After 2024-11-11, emotion cooled versus the rally peak, but the market was still materially better than the pre-924 period. A strategy should not treat this period as equivalent to the 2024 bear phase.

The new layer must distinguish:

- a true bear or broken market,
- a repair market,
- a confirmed impulse after policy/liquidity shock,
- a trend continuation phase after the impulse,
- a deteriorating but not yet broken phase.

## Scope

V1 produces a diagnostic and backtest-ready regime table. It does not directly replace live portfolio execution until the state logic is evaluated over 2023-present and specific policy/exposure rules are approved.

Inputs:

- `market_emotion_state_daily.csv` from market emotion v1.
- Optional index/market breadth fields already present in the emotion output.
- Optional policy event CSV for known major events, starting with 2024-09-24 as a manually auditable event.

Outputs:

- Daily confirmed regime table.
- Segment diagnostics for important windows.
- Backtest comparison against existing `fixed_mid_trend`, `emotion_budget_only`, and `emotion_style_switch`.

## Core Concepts

### Raw Emotion

Raw emotion remains daily and observational. It includes:

- `emotion_score`
- `emotion_state`
- `risk_state`
- breadth proxies
- turnover proxies
- limit-up / limit-down proxies where available

Raw daily state must not directly trigger portfolio-level style or exposure changes.

### Smoothed Regime Score

Create continuous features:

- `emotion_score_5d`
- `emotion_score_10d`
- `emotion_slope_5d`
- `risk_high_days_5d`
- `risk_high_days_10d`
- `hot_or_euphoria_days_5d`
- `panic_or_cold_days_5d`
- `score_rebound_from_20d_low`
- `score_drawdown_from_20d_high`

Then derive:

- `market_regime_score`, normalized to 0-100.
- `market_regime_state`, one of:
  - `bear`
  - `weak_repair`
  - `neutral`
  - `bull_impulse`
  - `bull_trend`
  - `trend_decay`
  - `overheated`

### Confirmation And Hysteresis

Regime changes require confirmation:

- Downgrades require persistence, generally 3-5 trading days.
- Upgrades require 2-3 trading days, except major policy impulse can accelerate re-risking.
- A confirmed `bull_impulse` can transition into `bull_trend` instead of falling directly to `bear` when emotion cools.
- A `bull_trend` should become `trend_decay` before exposure is cut aggressively.

This creates hysteresis: the state does not flip back and forth because of one bad or one good day.

### Policy Impulse

Policy information is a modifier, not the whole signal.

Policy events include financial policy, liquidity policy, policy-rate changes, market stabilization tools, capital market reforms, or other direct/indirect market support. V1 supports a manual event file with:

- `event_date`
- `event_type`
- `policy_strength`
- `description`
- `source`

Policy events only create a `policy_impulse_candidate`. Confirmation still requires market response, such as emotion rebound, breadth expansion, turnover expansion, or index trend confirmation.

## Trading Policy Layer

The confirmed regime feeds a separate trading policy. V1 should output recommendations but keep execution optional.

Exposure target:

- `bear`: 0.0-0.3
- `weak_repair`: 0.3-0.6
- `neutral`: 0.5-0.8
- `bull_impulse`: 0.8-1.0
- `bull_trend`: 0.8-1.0
- `trend_decay`: 0.5-0.8
- `overheated`: 0.6-1.0, depending on risk confirmation

Style bias:

- `bear`: cash/defensive bias, but do not force a weak defensive sleeve if it has not proven alpha.
- `weak_repair`: reduced growth plus quality filter.
- `neutral`: balanced, still anchored to mid trend quality.
- `bull_impulse`: growth/mid trend priority with fast re-risking.
- `bull_trend`: growth/mid trend priority with normal weekly rebalance.
- `trend_decay`: hold confirmed leaders, reduce new exposure, require stronger new-entry scores.
- `overheated`: keep leaders but tighten new-entry and drawdown controls.

Portfolio-level exposure and style changes happen on weekly rebalance dates. Individual stocks may still be removed immediately when stock-level risk rules fire.

## Required Diagnostics

The module must produce explicit diagnostics for:

- 2024-01-01 to 2024-09-23
- 2024-09-24 to 2024-11-08
- 2024-11-11 to 2024-12-31
- 2025-01-01 to latest available date
- Full 2023-present period

For each window, report:

- state distribution,
- average target exposure,
- regime transition dates,
- total return and max drawdown by strategy,
- days where raw daily emotion and confirmed regime disagree.

## Success Criteria

V1 is successful if diagnostics show:

- pre-924 2024 is mostly low or reduced exposure,
- 924 rally is re-risked quickly enough to participate,
- post-rally 2024 does not collapse back to the same state as pre-924 without persistence confirmation,
- the confirmed regime changes less frequently than raw daily emotion,
- full-period backtest reduces drawdown versus fixed mid trend with less return loss than the current `emotion_budget_only` baseline.

## Non-Goals

- Do not optimize the defensive stock sleeve in this version.
- Do not build an opaque machine-learning regime classifier.
- Do not make policy events alone sufficient to buy.
- Do not alter stock-level sell rules.
- Do not force daily portfolio-level rebalance.

## Open Implementation Preference

The recommended implementation is a new module, `market_regime_confirmation_v1.py`, plus a CLI command and tests. Existing market emotion and style switch modules should remain compatible.
