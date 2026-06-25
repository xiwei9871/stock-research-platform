# Mid Trend Soft Ownership Optimization Design

## Goal

Build a reproducible `Mid Trend soft ownership optimization` experiment layer on top of the existing `current_mid_trend_strategy_v1` workflow, keeping baseline behavior unchanged by default while evaluating four new variants over the fixed main window `2025-01-01` to `2026-06-12`.

The design must prioritize PnL over audit-label reduction. It must avoid hard veto entry/exit logic and instead test:

- `entry_soft_weight_v1`
- `ownership_hold_v1`
- `partial_exit_v1`
- `combined_soft_ownership_v1`

## Scope

This design covers:

- code audit artifact generation
- new experiment runner and variant configs
- baseline rerun on the same window
- variant execution on the same window
- trade / hold / exit diagnostics
- baseline-vs-variants PnL-first evaluation
- final interpretation report

This design does not:

- replace or rewrite the baseline `current_mid_trend_strategy_v1`
- change raw data loading logic
- change existing validation or replay-audit definitions globally
- introduce future-return features into live signal logic

## Current System Audit

### Strategy entrypoint

Primary live/backtest strategy runner:

- `src/stock_research/current_mid_trend_strategy_v1.py`
  - `run_current_mid_trend_strategy_v1_backtest(...)`
  - `build_current_mid_trend_strategy_v1_from_frames(...)`

Flow:

1. load regime / funnel / prices
2. build growth candidates from funnel
3. build regime selection
4. apply stock protection
5. build daily holdings
6. simulate equal-weight daily equity
7. derive trade changes and reports

### Backtest entrypoint

CLI entry:

- `src/stock_research/cli.py`
  - command: `current-mid-trend-strategy-v1`

Current outputs:

- `current_mid_trend_strategy_v1_equity.csv`
- `current_mid_trend_strategy_v1_summary.csv`
- `current_mid_trend_strategy_v1_daily_holdings.csv`
- `current_mid_trend_strategy_v1_trade_changes.csv`
- `current_mid_trend_strategy_v1_daily_holding_summary.csv`
- `current_mid_trend_strategy_v1_annual_summary.csv`
- `current_mid_trend_strategy_v1_quarterly_summary.csv`
- `current_mid_trend_strategy_v1_industry_exposure.csv`
- `current_mid_trend_strategy_v1_protection_events.csv`
- `current_mid_trend_strategy_v1_report.md`

### Signal fields available

From `mid_trend_watch_funnel` and merged funnel meta, the existing strategy already has:

- `mid_trend_funnel_score`
- `score_rank`
- `mid_trend_layer`
- `mainline_status`
- `industry_mainline_score_v1`
- `ret_20_score`
- `ret_60_score`
- `max_drawdown_20_score`
- `atr_pct_score`
- `stock_excess_ret_20_score`
- `industry_name`
- `stock_name`

From regime:

- `confirmed_regime_state`
- `emotion_score`
- `emotion_state`
- `risk_state`
- `target_exposure`
- `rebalance_allowed`
- `transition_reason`

From current holding/trade outputs:

- `target_weight`
- `cash_weight`
- `previous_weight`
- `delta_weight`
- `action`
- `protection_reason`

### Position state fields currently available

The current engine does not persist a rich explicit ownership state. It only has:

- current day selected assets
- daily `target_weight`
- rolling protection state internal to `apply_stock_protection_to_selection`
  - `entry_close`
  - `highest_close`
  - rank history
  - score history

These are not written out in detail today. This is the main gap the new experiment must fill.

### Current entry logic

Implemented in `current_mid_trend_strategy_v1` via:

- `build_growth_momentum_candidates(...)`
- `_build_strategy_selection(...)`
- `_build_regime_selection(...)`

Entry is effectively:

- fixed growth sleeve
- top `N` candidates per day
- daily invested weight determined by regime exposure
- equal-weight across chosen assets

There is no existing soft entry penalty. Selection is binary at the candidate layer, then equal-weight at the holding layer.

### Current exit logic

Implemented through `mid_trend_stock_protection_v1.apply_stock_protection_to_selection(...)`.

Current exit trigger style:

- ATR trailing stop
- confirmed score/rank break
- if triggered, position disappears from that day selection
- downstream holdings/trades therefore become `sell` or `decrease`

This is a hard removal model. It does not support:

- ownership persistence
- partial exit
- explicit suppressed exit
- addback tracking beyond normal re-entry

### Current audit metrics

Replay audit is in:

- `src/stock_research/mid_trend_strategy_validation.py`

Current labels:

- `bad_buy`: `buy` forward return over replay horizon `< 0`
- `bad_sell`: `sell` forward return over replay horizon `> 0.02`

Known existing outputs:

- `trade_audit_detail.csv`
- `monthly_issue_summary.csv`
- downstream diagnosis reports in `.../replay_audit/analysis/`

### What can be safely changed

- add new experimental module(s)
- add new config dataclasses
- add new CLI command(s)
- extend diagnostics output
- add new holdings/trade metadata columns in experimental outputs
- introduce soft ownership logic in a new variant runner

### What must not be changed

- baseline `current_mid_trend_strategy_v1` default behavior
- raw DB read logic
- existing replay audit label definitions globally
- existing baseline output directories
- future return leakage into signal generation

## Recommended Architecture

Use a new experimental runner instead of mutating baseline internals in place:

- create `src/stock_research/mid_trend_soft_ownership_v1.py`
- keep `current_mid_trend_strategy_v1.py` unchanged for baseline reproducibility
- reuse its candidate/regime/price loading and meta-merging logic
- reuse current baseline rerun as the control
- add an explicit stateful holdings evolution layer for variants

This is slightly more code than patching the protection layer directly, but gives cleaner control over:

- ownership state
- partial exit
- addback
- audit columns
- baseline isolation

## Alternative Approaches Considered

### Approach A: extend `mid_trend_stock_protection_v1` directly

Pros:

- minimal code duplication
- close to current holding logic

Cons:

- current protection function is framed as hard filtering, not ownership state management
- partial exit and suppressed exit tracking would make the function much more complex
- higher risk of accidental baseline behavior change

### Approach B: new experimental runner

Pros:

- safest baseline isolation
- clean variant boundary
- can persist richer daily ownership/exit state
- easier to audit

Cons:

- some logic reuse must be wired explicitly

### Approach C: trade replay overlay only

Pros:

- fastest

Cons:

- too far from actual strategy engine
- weaker research credibility

Recommendation: `Approach B`.

## New Files

### Create

- `src/stock_research/mid_trend_soft_ownership_v1.py`
- `tests/test_mid_trend_soft_ownership_v1.py`
- `docs/research/mid_trend_soft_ownership_runbook.md`

### Modify

- `src/stock_research/cli.py`

## Data Model

### Config

Add a new config model in the experimental module:

- `MidTrendSoftOwnershipConfig`

Fields:

- `variant_name`
- `start_date`
- `end_date`
- `top_n`
- `base_weight_mode`
- `entry_weak_rank_threshold`
- `entry_extreme_rank_threshold`
- `entry_weak_rank_multiplier`
- `entry_weak_regime_multiplier`
- `entry_weak_rank_and_regime_multiplier`
- `entry_extreme_damage_multiplier`
- `ownership_profit_cushion_min`
- `ownership_top_rank_memory_threshold`
- `ownership_rank_break_threshold`
- `ownership_damage_rank_threshold`
- `partial_exit_fraction_weak`
- `partial_exit_fraction_damage`

Variants:

- `baseline`
- `entry_soft_weight_v1`
- `ownership_hold_v1`
- `partial_exit_v1`
- `combined_soft_ownership_v1`

### Daily experimental holding state

Persist one row per asset per day with:

- `trade_date`
- `asset_id`
- `variant_name`
- `base_target_weight`
- `adjusted_target_weight`
- `entry_weight_multiplier`
- `entry_soft_reason`
- `ownership_state`
- `ownership_reason`
- `rank_memory_state`
- `profit_cushion_state`
- `damage_state`
- `exit_signal_state`
- `exit_action`
- `exit_fraction`
- `whether_exit_was_suppressed_by_ownership`
- `whether_addback_occurred`
- `confirmed_regime_state`
- `score_rank`
- `mid_trend_layer`
- `mid_trend_funnel_score`
- `ret_20_score`
- `ret_60_score`
- `max_drawdown_20_score`
- `stock_excess_ret_20_score`

### Trade/event diagnostics

Trade-level diagnostics must include:

- baseline action
- experimental action
- `entry_weight_multiplier`
- `entry_soft_reason`
- `ownership_state`
- `exit_action`
- `exit_fraction`
- `exit_reason`
- `confirmed_damage_flag`

## Variant Logic

### Baseline

Control path:

- rerun `current_mid_trend_strategy_v1` with
  - `start_date=2025-01-01`
  - `end_date=2026-06-12`
- confirm outputs match current known result within a small tolerance

### `entry_soft_weight_v1`

Intent:

- reduce weak entries instead of vetoing them

Minimal viable weak-rank rule with existing fields:

- `weak_rank_only` when:
  - `score_rank > 20`, or
  - `score_rank > 10` and `mid_trend_layer == high_elasticity_watch`

Minimal viable weak-regime rule:

- `confirmed_regime_state in {overheated, trend_decay}`

Minimal viable extreme-damage rule:

- `score_rank > 50`
- and weak regime
- and `max_drawdown_20_score < 45` or `stock_excess_ret_20_score < 40`

Multipliers:

- normal: `1.0`
- weak_rank_only: `0.7`
- weak_regime_only: `0.8`
- weak_rank_and_weak_regime: `0.5`
- extreme_damage: `0.1`

No hard veto except optional near-zero weight for extreme damage.

### `ownership_hold_v1`

Intent:

- preserve ownership of noisy winners when damage is not confirmed

Minimal rule-based ownership state using current fields:

- `owned_strong`
  - current `score_rank <= 10`
  - layer in `{stable_trend_watch, mainline_momentum_watch}`
  - no damage

- `owned_noisy_but_valid`
  - current rank deteriorated
  - but prior rank memory includes `<= 10`
  - and profit cushion positive
  - and not in confirmed damage

- `owned_weak`
  - weak rank / weak layer / small cushion
  - but still not confirmed damage

- `ownership_broken`
  - persistent rank deterioration or severe structure damage

Derived supporting states:

- `rank_memory_state`
  - `front_rank_memory`
  - `secondary_rank_memory`
  - `no_rank_memory`

- `profit_cushion_state`
  - `cushion_strong`
  - `cushion_small`
  - `no_cushion`

- `damage_state`
  - `none`
  - `soft_damage`
  - `confirmed_damage`

Minimal confirmed damage:

- `score_rank > 50` for repeated days, or
- `mid_trend_layer == risk_exclusion_watch`, or
- `max_drawdown_20_score < 35` and `stock_excess_ret_20_score < 35`

### `partial_exit_v1`

Intent:

- reduce instead of full exit for non-fatal deterioration

Rules:

- if `confirmed_damage`: `full_exit`, fraction `1.0`
- elif `ownership_state == owned_weak`: `reduce`, fraction `0.5`
- elif rank weakens but ownership intact: `hold`, fraction `0.0`
- addback allowed when later target weight implied by baseline exceeds current experimental weight and ownership damage clears

Implementation method:

- no engine rewrite
- use adjusted `target_weight` at holdings layer
- derive `buy / increase / decrease / sell` from experimental target weights

### `combined_soft_ownership_v1`

Combine:

- entry multipliers from `entry_soft_weight_v1`
- ownership suppression from `ownership_hold_v1`
- partial exit from `partial_exit_v1`

Only confirmed damage may force `full_exit`.

## Execution Flow

New experimental runner:

1. load same regime, funnel, prices, asset names
2. build same baseline candidate selection
3. derive per-day baseline equal weights
4. simulate experimental stateful holdings day by day
5. compute experimental target weights
6. derive holdings, trades, equity, summary
7. build diagnostics and audit outputs
8. compare against rerun baseline over the same window

## Evaluation Outputs

Output directory:

- `outputs/research/mid_trend_soft_ownership_optimization_<timestamp>/`

Files:

- `code_audit.md`
- `baseline_vs_variants.csv`
- `baseline_vs_variants.md`
- `trade_level_diagnostics.csv`
- `ownership_event_diagnostics.csv`
- `exit_event_diagnostics.csv`
- `bucket_contribution_entry_weight.csv`
- `suppressed_exit_analysis.csv`
- `final_interpretation.md`

Additional acceptable files:

- per-variant equity / holdings / trades / summary CSVs
- rerun baseline snapshot

## Metrics

Primary:

- `total_return`
- `annualized_return`
- `max_drawdown`

Secondary:

- `win_rate`
- `avg_winner`
- `avg_loser`
- `profit_factor`
- `total_trades`
- `turnover`
- `avg_holding_days`
- `median_holding_days`
- `top_10_winners_contribution`
- `top_20_winners_contribution`
- `left_tail_10_losers_contribution`
- `bad_buy_count`
- `bad_buy_rate`
- `bad_sell_count`
- `bad_sell_rate`
- `issue_rate`

If current engine lacks a metric, the experimental runner may compute it from daily returns and round-trip trade diagnostics. Missing metrics must be explicitly marked, not silently omitted.

## Baseline Reproducibility

The experimental command must:

1. rerun baseline on `2025-01-01` to `2026-06-12`
2. verify main summary against current known baseline artifact
3. stop with a clear error if baseline materially mismatches

Known comparison artifact:

- `outputs/research/current_mid_trend_strategy_v1_20250101_20260612_retest/`

## CLI

Add one dedicated CLI command:

- `mid-trend-soft-ownership-optimize`

Parameters:

- `--start-date`, default `2025-01-01`
- `--end-date`, default `2026-06-12`
- `--regime-path`
- `--funnel-detail-path`
- `--output-dir`
- `--variants`
- `--baseline-reference-dir`
- optional robustness splits flag

Default variants:

- baseline
- entry_soft_weight_v1
- ownership_hold_v1
- partial_exit_v1
- combined_soft_ownership_v1

## Testing

Unit tests should cover:

- baseline pass-through behavior
- entry multiplier assignment
- ownership state transitions
- partial exit weight reduction
- addback after prior reduction
- variant output files
- CLI parse and dispatch

The tests should use small in-memory frames and avoid DB dependencies.

## Risks and Gaps

### Available field gaps

Not explicitly available today:

- a native trend-structure-break flag
- a native relative-strength deterioration flag across holding life
- persistent per-position realized/unrealized PnL state

Minimal substitutes:

- use `mid_trend_layer`
- use `score_rank`
- use `mid_trend_funnel_score`
- use `max_drawdown_20_score`
- use `stock_excess_ret_20_score`
- compute simple price-based profit cushion from held asset close series

### Engine limitation

The current strategy is naturally equal-weight and selection-driven, not portfolio-optimization-driven.

Therefore partial exit will be implemented by:

- stateful target weights in the experimental runner
- not by modifying the generic market style engine

This is acceptable for a research variant and keeps baseline intact.

## Success Criteria

The experiment is successful only if at least one soft-ownership variant:

- improves or preserves `total_return`, and
- does not create unacceptable drawdown expansion, and
- shows a credible mechanism of improvement in diagnostics

Reducing `bad_buy / bad_sell` alone is not success.

## Next Step After Approval

After spec approval:

1. write a detailed implementation plan
2. implement the experimental runner and CLI
3. rerun baseline and variants on the fixed full window
4. write the PnL-first interpretation
