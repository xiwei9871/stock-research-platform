# LHB V1 Safe Top5 Design

## Goal

Preserve the original LHB Shortline V1 Top5 strategy identity while enforcing the shared eligibility contract. The strategy must select the original ranked Top5 first, remove unsafe members second, leave rejected slots in cash, and never refill from ranks 6-10.

## Context

The 2026-07-15 eligibility rollout correctly blocked near-limit-down and delisting-period events, but it also moved eligibility filtering before ranking and introduced a minimum ten-name candidate pool. That changed the historical account path from the original Top5 strategy into a different refill strategy. On the same database and parameters, the pre-change engine returned 182.33% with 247 trades while the current refill engine returned 90.25% with 194 trades.

This design keeps the safety contract but reverses the unintended strategy-identity change.

## Strategy Contract

The official `lhb_shortline` strategy follows these invariants:

1. Rank the complete daily LHB candidate universe using the existing V1 score.
2. Select the original ranks 1-5 for `top_n=5` before applying eligibility.
3. Apply `lhb_eligibility_v2` to those selected rows.
4. Keep only rows with `backtest_entry_eligible=true` as tradable entries.
5. Leave rejected Top5 slots as cash. Ranks 6-10 must not refill them.
6. Propagate the eligibility decision through phase12a, real entry, lifecycle, phase18c, and the market-regime account.
7. Preserve rejected Top5 rows in a separate risk-audit artifact with their original rank, score, and reason codes.
8. Do not publish risk-watch, hard-reject, retreat, or ranks 6-10 as official LHB strategy review entries.

The candidate pool may still contain more than five rows for diagnostics, but it cannot influence official selection, positions, trades, or the official review count.

## Data Flow

`build_lhb_full_market_pool_backtest_v1` will:

1. Build and score the complete evaluated candidate frame.
2. Rank and select TopN from the evaluated frame without eligibility pre-filtering.
3. Split the selected TopN into:
   - `selected_trades`: eligible official entries.
   - `selected_rejected_events`: rejected original-TopN rows that leave cash slots.
4. Continue writing the full-universe `rejected_events` artifact for research diagnostics.

Only `selected_trades` flows into the lifecycle and account engine. The original rank is retained so downstream code cannot silently compact rank 1, 3, 5 into a new rank 1, 2, 3 selection.

## Publication And Platform Semantics

The official `strategy_lhb_shortline_review.csv` contains only eligible original-Top5 entries. Its row count is therefore between zero and five.

Risk-watch and hard-reject rows remain available through a separate audit artifact and must not be counted as strategy entries. Platform copy must describe LHB as Top5; the generic Mid Trend Top10 label must not be applied to LHB.

Historical performance must be versioned:

- `lhb_v1_legacy`: original unfiltered Top5 benchmark.
- `lhb_v1_safe_top5`: this design, the official candidate after validation.
- `lhb_v2_refill`: the current eligibility-before-ranking refill experiment.

No version may overwrite another version's displayed historical curve without an explicit methodology label.

## Validation

Automated tests must prove:

- An ineligible rank-2 row is removed and rank 6 does not refill it.
- Eligible ranks retain their original rank values.
- Rejected original-Top5 rows are written to the selected-risk audit output.
- No ineligible row reaches any account-entry stage.
- Official LHB review output contains at most five rows and excludes risk-watch rows.
- Mid Trend Top10 behavior is unchanged.

The same-database backtest for 2026-01-01 through 2026-07-15 must report:

- final return, drawdown, trade count, and cash-slot count;
- exact differences versus legacy V1 and refill V2;
- direct eligibility rejections by reason;
- proof that no rank greater than five becomes an official entry.

## Rollout

The change is acceptable for platform publication only when unit tests, LHB lifecycle tests, strategy publication tests, score-audit tests, and a fresh same-database backtest all pass. The platform must display the safe-Top5 version label and its own metrics rather than retaining the 90.25% refill result under the generic LHB name.
