# Watchlist Diagnostics Runbook

## Purpose

Run the short-term watchlist diagnostics workflow and accumulate review samples without turning the system into a trading signal engine.

This runbook is for:

- daily `watchlist diagnostics` generation
- daily `must_watch` review
- rolling effectiveness review on accumulated samples

This runbook is not for:

- automated trading
- position sizing
- formal strategy backtests

## Inputs

Required data layers should already be available for the target `trade_date`:

- `factor.stock_score_daily`
- `factor.factor_daily`
- `factor.stock_technical_features_daily`
- `market_daily_bar`
- Dragon / LHB research outputs in `outputs/research`

## Core Daily Commands

Build daily watchlist diagnostics:

```bash
cd /Users/xiwei/stock_research
./.venv/bin/python -m stock_research.cli build-watchlist-diagnostics \
  --trade-date YYYY-MM-DD \
  --score-version manual_v1 \
  --top-n 50 \
  --risk-watch-n 10 \
  --opportunity-watch-n 10 \
  --output-dir outputs/research
```

This writes:

- `watchlist_diagnostics_YYYY-MM-DD_diagnostics_v1.csv`
- `watchlist_diagnostics_must_watch_YYYY-MM-DD_diagnostics_v1.csv`
- `watchlist_diagnostics_YYYY-MM-DD_diagnostics_v1.md`

Run rolling effectiveness review on accumulated watchlist diagnostics:

```bash
cd /Users/xiwei/stock_research
./.venv/bin/python -m stock_research.cli review-watchlist-diagnostics \
  --diagnostics-dir outputs/research \
  --start-date YYYY-MM-DD \
  --end-date YYYY-MM-DD \
  --output-dir outputs/research
```

This writes:

- `watchlist_diagnostics_effectiveness_*_detail.csv`
- `watchlist_diagnostics_effectiveness_*_summary.csv`
- `watchlist_diagnostics_effectiveness_*.md`

## Daily Operating Sequence

1. Confirm the target `trade_date`.
2. Run `build-watchlist-diagnostics`.
3. Read `watchlist_diagnostics_must_watch_*.csv`.
4. Read `watchlist_diagnostics_*.md`.
5. Record any manual notes outside the system if needed.
6. After enough future bars exist, run `review-watchlist-diagnostics` for the rolling window.

## What To Read First

Read the `must_watch` markdown in this order:

1. `Risk Watch`
2. `Opportunity Watch`

Within `Opportunity Watch`, current ordering is:

1. `second_wave_candidate`
2. `break_then_reversal_candidate`
3. `weak_to_strong_candidate`
4. `trend_continuation_candidate`

Within `Risk Watch`, failed structures and high-risk co-signals rank ahead of generic technical heat.

## Review Window

Use a rolling review window, not a single date.

Recommended:

- minimum smoke window: `5` trade dates
- first useful operator window: `20` trade dates
- first review-grade window: `20-40` trade dates

## Review Questions

When reading `watchlist_diagnostics_effectiveness_*.md`, answer:

1. Is `opportunity_watch` better than `candidate` on `future_3d` and `future_5d`?
2. Is `risk_watch` worse than `candidate` on `future_3d`, `future_5d`, and `future_5d_max_drawdown`?
3. Are `second_wave_candidate` and `weak_to_strong_candidate` behaving differently from `trend_continuation_candidate`?
4. Are there too many false positives in `break_then_reversal_candidate`?

## Current Interpretation Guardrails

Do not over-read very small samples.

Examples:

- `sample_count = 1` is anecdotal
- `sample_count < 5` is directional only
- use `20+` dates before changing core watchlist rules

## Escalation Criteria

Only consider the watchlist system stable enough for deeper evaluation when:

- `opportunity_watch` keeps outperforming `candidate`
- `risk_watch` keeps underperforming with worse drawdowns
- structure-level separation is still visible after `20-40` trade dates

If these conditions fail, revise diagnostics rules before doing any strategy-layer work.
