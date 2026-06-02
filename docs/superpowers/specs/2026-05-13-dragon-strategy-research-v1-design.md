# Dragon Strategy Research V1 Design

## Goal

Build a diagnostic-first research module for identifying leaders inside hot A-share industries.

Dragon Strategy Research v1 only studies:

- which industries are hot;
- which stocks inside those industries look like leaders, core middle names, catch-up names, followers, overheated leaders, cooling-down names, or weak candidates;
- whether those role labels have explanatory power for future 1, 3, 5, 10, and 20 trading-day returns and drawdowns.

This version does not ingest Dragon-Tiger List data, does not place trades, does not persist new database tables, and does not optimize parameters for short-term backtest results.

## Scope

In scope:

- Add `src/stock_research/dragon_strategy_research.py` as a standalone diagnostic module.
- Add `stock-research dragon-research-v1`.
- Reuse daily bars, point-in-time industry membership, `industry_focus_v2` diagnostics, existing Top20/Top50/Top100 candidate scores, and optional `trend_lifecycle` samples.
- Produce CSV diagnostics and a Markdown research report under `outputs/research/`.
- Compute future returns and future drawdowns only after the role labels are produced.
- Add focused tests for scoring, role labels, effective-date membership, summaries, and report generation.

Out of scope:

- Dragon-Tiger List data, seat labels, institution/hot-money net buy fields, or next-day LHB confirmation.
- Broker integration or live trading recommendations.
- Database persistence for Dragon outputs.
- Changing `industry_focus_v2.py` into a stock-role module.
- Weight optimization or machine-learning models.

## Existing Context

Relevant current modules:

- `src/stock_research/industry_focus_v2.py` computes industry mainline diagnostics including amount-share change, Top20/50/100 density, trend persistence, leadership persistence, and risk tags.
- `src/stock_research/industry_focus_score.py` computes an earlier point-in-time industry focus score.
- `src/stock_research/trend_lifecycle.py` generates trend segments, lifecycle samples, and entry-success labels.
- `src/stock_research/trend_candidate_enrichment.py` builds candidate scores from factor profiles.
- `src/stock_research/trend_candidate_backtest.py` provides fixed-holding diagnostics for candidate-score outputs.
- `market_daily_bar` stores daily open/high/low/close/amount/turnover/trade status/ST fields.
- `core.industry_membership` stores industry membership with effective date windows.

Dragon v1 should compose these existing capabilities rather than move stock-role logic into industry modules.

## Point-In-Time Rule

For a trade date `t`, `dragon_score` may use only information available on or before `t`.

Allowed in scoring:

- daily bar fields with `trade_date <= t`;
- industry membership effective on `t`;
- industry diagnostics computed from histories ending at `t`;
- stock candidate scores computed from factors available on `t`;
- lifecycle stage samples where `trade_date = t`, because those samples are derived from a separate research label pipeline and must be treated as optional diagnostic context.

Forbidden in scoring:

- future 1/3/5/10/20-day returns;
- future max drawdowns;
- future industry ranks;
- future Top20/Top50/Top100 membership;
- Dragon-Tiger List events or future next-day carrying behavior.

Future returns and drawdowns are appended only after `dragon_score` and `dragon_role` are finalized for the date.

## Data Flow

The CLI loads data for the requested date range with enough lookback and forward buffer:

1. Load daily bars from `market_daily_bar`.
2. Load active asset names from `core.asset_master` or legacy `asset_master` where available.
3. Load point-in-time industry membership from `core.industry_membership`.
4. Load or compute `industry_focus_v2` diagnostics.
5. Load stock-level candidate scores where available.
6. Load lifecycle samples when a CSV path is provided or when generated outputs are available.
7. Build per-stock historical features per date.
8. Filter to hot industries.
9. Compute Dragon sub-scores and penalties.
10. Assign `dragon_role`.
11. Append future return and future drawdown diagnostics.
12. Write CSV outputs and Markdown report.

The first implementation can keep the in-memory working set bounded by date range plus lookback/forward windows. It should avoid reading unrelated full-history tables when the CLI date range is narrow.

## Hot Industry Selection

Use `industry_focus_v2` as the preferred hot-industry source.

For each date:

- `industry_focus_score_v2` is the v2 mainline score when present.
- `industry_heat_score` defaults to the same value in v1.
- `industry_rank` is the cross-sectional rank by descending heat score.

An industry is considered hot when:

- it ranks in the top `hot_industry_top_n`, default 6; or
- its heat score is in the top `hot_industry_min_percentile`, default 70th percentile.

If v2 diagnostics are unavailable, Dragon v1 may compute a fallback industry heat score from daily bars using industry return, amount-share change, breadth, and Top100 density if candidate scores are available. The report must disclose when fallback heat was used.

## Dragon Score

For each stock in a hot industry on date `t`:

```text
dragon_score =
  0.25 * stock_relative_strength_score
+ 0.20 * breakout_strength_score
+ 0.20 * turnover_amount_score
+ 0.15 * industry_leadership_score
+ 0.10 * lifecycle_score
+ 0.10 * liquidity_score
- overheat_penalty
- follower_penalty
```

Scores are normalized to a 0-1 range where practical. Penalties are also 0-1 range and subtracted directly, making overheated and follower names fall below clean leaders even when raw momentum is high.

### Stock Relative Strength Score

Inputs:

- stock 3/5/10/20-day returns;
- stock 5/20-day excess return versus industry equal-weight return;
- stock 5/20-day excess return versus broad-market equal-weight return.

Purpose:

- reward stocks that lead their industry and the market across more than one short horizon;
- avoid over-rewarding one-day spikes.

### Breakout Strength Score

Inputs:

- new 20-day high flag;
- new 60-day high flag;
- close versus 20-day rolling high before the signal date;
- number of recent days where stock return exceeds industry return.

Purpose:

- identify stocks breaking out from prior ranges;
- require repeated relative strength instead of a single isolated jump.

### Turnover Amount Score

Inputs:

- industry-relative amount rank;
- industry-relative turnover rank when available;
- `amount_vs_20d`;
- blowoff control that caps the reward when amount expansion is extreme.

Purpose:

- ensure leadership is supported by liquidity and attention;
- avoid treating a single abnormal volume day as healthy leadership.

### Industry Leadership Score

Inputs:

- stock return rank inside the industry;
- stock amount rank inside the industry;
- early-start signal from 20-day relative strength and 5-day relative strength;
- priority-up signal based on recent days outperforming the industry.

Purpose:

- distinguish leaders from stocks merely riding a hot industry.

### Lifecycle Score

Inputs:

- optional `trend_lifecycle` stage;
- fallback price-stage classification from historical returns and trend quality when lifecycle samples are unavailable.

Lifecycle stage mapping:

| Stage | Score |
| --- | ---: |
| `warming_up` | 0.85 |
| `breakout` | 1.00 |
| `acceleration` | 0.80 |
| `divergence` | 0.45 |
| `cooling_down` | 0.10 |
| missing/unknown | 0.50 |

Purpose:

- prefer startup, breakout, and early acceleration;
- penalize late divergence and cooling-down phases.

### Liquidity Score

Inputs:

- amount;
- 20-day average amount;
- trade status;
- ST flag;
- turnover rate where available.

Purpose:

- keep future strategy candidates tradable;
- make weak liquidity visible in diagnostics even before strategy rules exist.

### Overheat Penalty

Inputs:

- extreme 3/5/10-day returns;
- excessive close extension versus 20-day mean;
- extreme `amount_vs_20d`;
- extreme turnover rate.

Purpose:

- mark stocks that may still be leaders but have entered a high-risk zone.

### Follower Penalty

Inputs:

- hot industry but low stock rank;
- positive industry return but weak stock excess return;
- short-horizon catch-up after poor 20-day relative strength;
- low breakout score.

Purpose:

- penalize names that rise only after the industry has already moved.

## Dragon Role Labels

Role assignment is deterministic and explainable. Rules are evaluated after all sub-scores and penalties are computed.

### `overheated_leader`

- `dragon_rank_in_industry <= 5`; and
- `overheat_penalty >= 0.55`; and
- stock has strong 5/10/20-day returns or breakout score.

### `cooling_down`

- lifecycle stage is `cooling_down`; or
- 5-day excess return versus industry is negative and 20-day return or trend stage is deteriorating; or
- stock falls below industry return while the industry heat rank remains high.

### `dragon_leader`

- hot industry;
- `dragon_rank_in_industry <= 3`;
- 5-day or 20-day excess return versus industry is positive;
- liquidity score is at least 0.50;
- lifecycle is not `cooling_down`;
- overheat penalty is below the overheated threshold.

### `core_middle`

- hot industry;
- stock ranks high by amount or liquidity;
- stock is stronger than the industry average but is not the most extreme mover;
- overheat penalty is moderate or low.

### `laggard_catchup`

- hot industry;
- 3/5-day stock return has improved;
- 20-day excess return versus industry is weak or negative;
- follower penalty is moderate but not severe.

### `follower`

- hot industry;
- stock participates in industry strength but ranks behind leaders;
- excess returns and breakout score are not enough for leader/core labels.

### `weak_candidate`

- default role for hot-industry stocks with weak liquidity, weak relative strength, or insufficient breakout/leadership evidence.

## Diagnostic Output

Write `outputs/research/dragon_strategy_v1_diagnostics.csv` with at least:

- `trade_date`
- `industry_name`
- `industry_heat_score`
- `industry_focus_score_v2`
- `industry_rank`
- `asset_id`
- `stock_name`
- `close`
- `stock_return_3d`
- `stock_return_5d`
- `stock_return_10d`
- `stock_return_20d`
- `stock_excess_return_vs_industry_5d`
- `stock_excess_return_vs_industry_20d`
- `amount`
- `turnover_rate`
- `amount_vs_20d`
- `trend_lifecycle_stage`
- all Dragon sub-scores and penalties
- `dragon_score`
- `dragon_rank_in_industry`
- `dragon_role`
- future 1/3/5/10/20-day returns
- future 10/20-day max drawdown

Future columns must remain diagnostic-only.

## Summary Outputs

Write:

- `outputs/research/dragon_strategy_v1_monthly_summary.csv`
- `outputs/research/dragon_strategy_v1_role_effectiveness.csv`
- `outputs/research/dragon_strategy_v1_yearly_diagnosis.csv`
- `outputs/research/dragon_strategy_v1_report.md`

Role effectiveness groups by `dragon_role` and reports:

- sample count;
- average future 1/3/5/10/20-day returns;
- median future 5/10-day returns;
- 5/10-day win rates;
- average future 10/20-day max drawdown.

Yearly diagnosis groups by calendar year and role, then includes:

- role sample count;
- annual role win rates;
- annual average future returns;
- annual average drawdowns;
- annual hot industry count;
- annual industry mainline concentration.

Monthly summary gives a compact time-series view of role mix and hot-industry concentration.

## CLI

Add:

```bash
stock-research dragon-research-v1 \
  --start-date 2024-05-27 \
  --end-date 2026-05-12
```

Optional flags:

- `--outputs-dir`, default `/Users/xiwei/stock_research/outputs/research`
- `--hot-industry-top-n`, default `6`
- `--adjust-type`, default `hfq`
- `--lifecycle-samples-path`
- `--candidate-scores-path`
- `--industry-diagnostics-path`

The command prints output paths and row counts.

## Markdown Report

The report structure:

1. Research goal.
2. Method description.
3. Dragon role definitions.
4. Role effectiveness.
5. Yearly differences.
6. Current conclusions.
7. Next steps for Dragon-Tiger List integration.

The next-step section should list required v1.1/v2 fields:

- on-list event date;
- on-list reason;
- net buy amount;
- buy and sell amount;
- institution net buy;
- business-department net buy;
- top buyer concentration;
- top five concentration;
- repeat on-list count;
- next-day carrying/one-day-pump diagnostics.

## Tests

Add tests covering:

1. `dragon_score` does not use future return columns.
2. Industry membership effective-date logic picks the membership valid on the trade date.
3. Role labels classify leader, core middle, catch-up, follower, overheated leader, cooling down, and weak candidate examples.
4. `overheat_penalty` increases for short-window extreme moves and abnormal amount expansion.
5. `follower_penalty` increases when stock strength lags industry strength.
6. Role effectiveness aggregates average return, median return, win rate, and drawdown correctly.
7. Markdown report generation writes the required sections.

## Self-Review

- Future-function avoidance: `dragon_score` uses historical features only; future returns and drawdowns are appended afterward.
- Existing CLI safety: only add a new subcommand and import; do not change semantics of existing commands.
- Dragon-Tiger List exclusion: no LHB fields are loaded or scored in v1.
- Module boundary: stock role logic lives in `dragon_strategy_research.py`; `industry_focus_v2.py` remains an industry diagnostic module.
- Outputs: all required CSV and Markdown paths are specified.
- Tests: the required test cases are explicit and map to v1 requirements.
