# LHB Risk Usage Calibration Design

## Goal

Calibrate how the short-term watchlist uses existing LHB risk fields. The LHB risk score already exists and should not be made stricter in this pass. This change separates hard withdrawal signals from high-elasticity risk signals so the short-term strategy does not remove every volatile emotional leader.

## Scope

In scope:

- Keep `lhb_risk_score` calculation unchanged.
- Keep negative LHB signals as hard risk:
  - `lhb_negative_net_buy`
  - `lhb_institution_selling`
  - Dragon/LHB high-risk confluence
  - confirmed failure event structures
- Reclassify standalone `lhb_high_pump_risk` as elasticity risk unless it appears with a hard risk signal.
- Preserve risk notes so high-pump samples remain visible in diagnostics.
- Update tests for `risk_split` and watchlist diagnostics.

Out of scope:

- No new alpha score.
- No new LHB ingestion or schema change.
- No future returns in live classification.
- No automatic buy signal.

## Design

`watchlist.risk_split` should treat `lhb_high_pump_risk` like `intraday_fade`, `extreme_amount`, and `high_volatility`: a reason to study the row as high-elasticity risk, not a standalone hard exclusion. Hard risk remains reserved for failure structures, LHB negative net buy, LHB institution selling, and Dragon/LHB confluence.

`watchlist.diagnostics` should follow the same boundary. A candidate with standalone high pump, strong rank, and active breakout-style context can remain in `high_odds_burst_watch`; the risk note still includes `lhb_high_pump_risk`. If high pump coincides with negative LHB selling or Dragon/LHB confluence, the row stays in `risk_watch`.

## Verification

Focused tests:

- `tests/test_risk_watch_split.py`
- `tests/test_watchlist_diagnostics.py`

The expected behavioral change is narrower filtering, not weaker observability: high-pump risk remains reported, but no longer acts as a standalone hard block.
