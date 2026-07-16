# LHB V1 Safe Top5 Design

## Goal

Preserve the original LHB Shortline V1 research and lifecycle behavior while separating review eligibility from account-entry eligibility. The internal strategy keeps its original Top10 research pool, Phase18C selects the final Top5 using the legacy strategy, unsafe final selections leave cash slots, and ranks 6-10 never refill those slots.

## Context

The 2026-07-15 eligibility rollout correctly blocked near-limit-down and delisting-period events, but it also moved eligibility filtering before ranking and introduced a minimum ten-name candidate pool. That changed the historical account path from the original Top5 strategy into a different refill strategy. On the same database and parameters, the pre-change engine returned 182.33% with 247 trades while the current refill engine returned 90.25% with 194 trades.

An initial implementation applied the Top5 cutoff before the legacy lifecycle. Its same-database replay returned only 17.33%, proving that the cutoff destroyed the original Top10 research and confirmation path rather than merely adding a safety gate. This design keeps the safety contract while restoring that internal path.

## Business Semantics

LHB review membership and an account buy signal are different decisions:

- A stock may remain in the LHB research pool or review output without being tradable.
- A limit-down or near-limit-down event is never a buy signal. It may remain in research and risk-audit artifacts, but it cannot enter the account or backtest trade stream.
- An ST stock may be an LHB candidate and may remain account-entry eligible when it passes all other gates. Every ST row must carry a prominent `st_high_risk` warning.
- An ST stock that is limit-down or near-limit-down remains non-tradable.
- A delisting-period stock remains a hard reject and is never tradable.
- LHB ranking, selection, and a displayed review entry must not be described as an automatic recommendation to buy.

## Strategy Contract

The official `lhb_shortline` strategy follows these invariants:

1. Rank the complete daily LHB candidate universe using the existing V1 score.
2. Preserve the legacy Top10 internal research pool for confirmation, real-entry analysis, lifecycle construction, and Phase18C scoring.
3. Carry the shared eligibility decision through the internal pipeline without removing research rows early.
4. Let Phase18C produce the final selection ranks 1-5 using the legacy strategy behavior.
5. Apply account-entry eligibility only after that final Top5 selection.
6. Keep only rows with `backtest_entry_eligible=true` as tradable account entries.
7. Leave rejected final-Top5 slots as cash. Ranks 6-10 must not refill them.
8. Preserve rejected final-Top5 rows in a separate risk-audit artifact with their original rank, score, warning codes, and rejection reasons.
9. Publish final Top5 review rows with an explicit buy-status field. Research-only rows must display `非买入信号` and must not reach the account.
10. Preserve ST rows that otherwise qualify, attach `st_high_risk`, and use the ST price-limit regime when evaluating limit-down risk.

The internal pool may contain ten rows because the legacy confirmation and lifecycle logic depends on it. Only the five rows selected by Phase18C may appear in the official review; rank 6 cannot become official merely because an earlier final selection is non-tradable.

## Data Flow

`build_lhb_full_market_pool_backtest_v1` will:

1. Build and score the complete evaluated candidate frame.
2. Rank and select the legacy internal Top10 from the evaluated frame without eligibility pre-filtering.
3. Carry eligible, risk-watch, and hard-reject decisions forward as research metadata.
4. Continue writing the full-universe `rejected_events` artifact for diagnostics.

The full internal Top10 flows through the research lifecycle. Phase18C then selects its final Top5 before splitting it into:

- `selected_trades`: final Top5 rows that are account-entry eligible;
- `selected_rejected_trades`: final Top5 rows that remain research-only and leave cash slots.

The Phase18C selection rank is retained so downstream code cannot compact surviving ranks or silently promote rank 6.

## Eligibility And Warning Contract

The shared eligibility contract must express these states independently:

- `backtest_entry_eligible`: whether the row may reach the account;
- `eligibility_status`: `eligible`, `risk_watch`, or `hard_reject`;
- `eligibility_warning_codes`: non-blocking warnings such as `st_high_risk`;
- `buy_signal_status`: `tradable` or `research_only` for platform and publication semantics.

Near-limit-down produces `risk_watch`, `backtest_entry_eligible=false`, and `buy_signal_status=research_only`. ST alone keeps the row eligible but appends `st_high_risk`. Delisting-period status produces `hard_reject`.

## Publication And Platform Semantics

The official `strategy_lhb_shortline_review.csv` contains at most the final Phase18C Top5. Tradable rows and research-only rejected final-Top5 rows must be visually distinct, and only tradable rows may feed account positions. If the existing consumer cannot safely represent both states, publication must place research-only rows in the separate risk-audit artifact rather than imply a buy signal.

Platform copy must describe LHB as Top5; the generic Mid Trend Top10 label must not be applied to LHB. Every ST row must display the ST risk warning. Every limit-down or near-limit-down row displayed for research must display `非买入信号`.

Historical performance must be versioned:

- `lhb_v1_legacy`: original unfiltered Top5 benchmark.
- `lhb_v1_safe_top5`: this design, the official candidate after validation.
- `lhb_v2_refill`: the current eligibility-before-ranking refill experiment.

No version may overwrite another version's displayed historical curve without an explicit methodology label.

## Validation

Automated tests must prove:

- The internal lifecycle receives the legacy Top10 pool, including rows carrying research-only eligibility states.
- An ineligible final rank-2 row is removed from account entry and rank 6 does not refill it.
- Eligible final ranks retain their original Phase18C selection ranks.
- Rejected final-Top5 rows are written to the selected-risk audit output.
- No ineligible row reaches any account-entry stage.
- A normal ST row remains eligible and carries `st_high_risk`.
- An ST near-limit-down row is research-only and never reaches the account.
- A normal-board, STAR, ChiNext, Beijing, and ST limit-down row uses the correct point-in-time threshold.
- A delisting-period row remains a hard reject.
- Official LHB review output contains at most five final selections and cannot imply that a research-only row is a buy signal.
- Mid Trend Top10 behavior is unchanged.

The same-database backtest for 2026-01-01 through 2026-07-15 must report:

- final return, drawdown, trade count, and cash-slot count;
- exact differences versus legacy V1 and refill V2;
- direct eligibility rejections by reason;
- proof that no Phase18C rank greater than five becomes an account entry;
- ST candidate, ST warning, and ST limit-down rejection counts;
- limit-down and near-limit-down research-only counts.

## Rollout

The change is acceptable for platform publication only when unit tests, LHB lifecycle tests, strategy publication tests, score-audit tests, and a fresh same-database backtest all pass. The replay must be compared with the legacy 182.33%, refill 90.25%, and invalid early-cutoff 17.33% runs. The platform must display the safe-Top5 version label and its own metrics rather than retaining another version's result under the generic LHB name.
