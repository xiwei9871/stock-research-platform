# Mid Trend Drawdown Control Validation v1

## Goal

Validate whether simple drawdown-control constraints can improve the mid-term trend funnel without changing the short-term event watchlist or producing trading instructions.

## Scope

This is a diagnostics-only layer for `mid_trend_watch`. It evaluates 20/30/40/60 day outcomes, maximum drawdown, max return within 60 days, and double-hit rate. It does not use 1/3/5/10 day short-event metrics as the decision target.

## Inputs

- `outputs/research/mid_trend_watch_funnel_detail.csv`
- `outputs/research/mid_trend_watch_top10.csv`

## Variants

- `baseline_top10`: current Top10 focus pool.
- `no_high_elasticity_top10`: exclude `high_elasticity_watch`.
- `high_elasticity_quota_1_top10`: allow at most one high-elasticity name per day.
- `max_drawdown_floor_60_top10`: require `max_drawdown_20_score >= 60`.
- `volatility_floor_20_top10`: require `volatility_20_score >= 20`.
- `atr_floor_20_top10`: require `atr_pct_score >= 20`.
- `vcp_like_contraction_top10`: strong trend with acceptable drawdown and no extreme volatility.
- `vcp_like_drawdown_floor_top10`: VCP-like plus drawdown floor.

## Outputs

- `mid_trend_drawdown_control_variant_detail.csv`
- `mid_trend_drawdown_control_effectiveness.csv`
- `mid_trend_drawdown_control_recommendations.csv`
- `mid_trend_drawdown_control_report.md`

## Non-Goals

- No short-event watchlist changes.
- No production watchlist changes.
- No buy/sell instructions.
- No position sizing or real execution.
