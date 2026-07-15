# LHB Rule Governance and Ranking v2 — Completion Record

## Final status

All seven approved work items are implemented and verified. `lhb_selection_score_v2` is intentionally **shadow-only** because it failed two untouched-holdout promotion gates; the existing production ranking remains active.

## Implemented controls

1. Delisting-period events are hard-rejected before ranking and cannot enter lifecycle or account fills.
2. Near-limit-down events use one point-in-time resolver and remain auditable `risk_watch` rows without occupying Top5 or account-entry slots.
3. Positive high-to-close drawdown is penalized with the correct sign.
4. Candidate, backtest, account, EOD, score audit, and Dashboard consume `lhb_eligibility_v2`; legacy 0.75/0.90 hard-threshold divergence is removed.
5. Historical ST and price-limit state prefer same-day evidence, and daily bars now join LHB candidates through `core.asset_master.ts_code` rather than incompatible internal asset IDs.
6. Dashboard states are distinct: `pending_confirmation`, `confirmed_follow`, `watch_only`, `risk_watch`, and `retreat`.
7. Ranking calibration uses chronological expanding-window validation and a final untouched holdout. Failed gates prevent promotion.

## Regression evidence

Focused final suite:

```text
174 passed, 2 third-party Python 3.14 deprecation warnings
```

The pre-existing `tech_bottleneck_review_universe_frontend_*` worktree changes remain untouched and uncommitted.

## Eligibility and replay evidence

Phase A safety results remain:

- rejected / filled overlap: 0
- parity mismatches: 0
- contract-version failures: 0
- rejected events: 356
- comparable final equity: 1.913312
- comparable total return: 91.33%
- comparable maximum drawdown: -5.12%
- comparable filled trades: 192

The contaminated prior run had final equity 2.839346, return 183.93%, drawdown -8.42%, and 245 fills. Ten old final-account fills are explicitly rejected by the new contract. Four were near-limit-down entries; three lost money and one outlier winner made their mean positive, so the evidence does not support a robust next-day rebound rule.

## Dashboard confirmation evidence

### 2026-07-14 current signal page

Artifact: `outputs/research/strategy_daily_eod/2026-07-14/strategy_lhb_shortline_review.csv`

- `pending_confirmation`: 10
- `risk_watch`: 4
- confirmed Top5 slots: 5, all pending confirmation
- ordinary watch rows: 5
- score-audit anomalies: 0
- 惠科股份 `001399.SZ`: score 69.36979856319499, `risk_watch`, not Top5 eligible, not account-entry eligible

Pending cards render `Top5 次日确认待定`; they no longer inherit confirmed-follow language.

### 2026-07-08 historical confirmation page

Artifact: `outputs/research/strategy_daily_eod/2026-07-08/strategy_lhb_shortline_review.csv`

- `confirmed_follow`: 3
- `pending_confirmation`: 2
- `watch_only`: 1
- `risk_watch`: 5
- `retreat`: 4
- score-audit anomalies: 0

Confirmed rows are sourced from the pre-account confirmation/scoring layer. Account simulation still enforces its original as-of cutoff, so showing historical confirmation does not introduce look-ahead fills.

## Ranking v2 holdout result

Artifacts: `outputs/research/lhb_selection_score_v2_calibration_20260105_20260714/`

- score version: `lhb_selection_score_v2`
- selected shadow formula: `capital_concentrated`
- eligible universe: 3,531 rows across 126 dates
- untouched holdout: 2026-06-08 through 2026-07-14, 26 dates
- baseline Top5 outcome sample: 105
- candidate Top5 outcome sample: 105

| Holdout metric | Baseline | Candidate |
|---|---:|---:|
| Mean future 5-day return | 1.0744% | 1.7688% |
| T+1 up rate | 63.08% | 60.77% |
| Mean future 5-day max drawdown | -8.4120% | -7.8939% |

Ranks 6-10 under the candidate formula had mean 5-day return 0.0159% and T+1 up rate 53.85%, so rank separation passed.

Promotion failed because:

- T+1 up rate was 2.31 percentage points below baseline, exceeding the allowed 2-point decline;
- positive holdout excess return was concentrated in one month (`monthly_excess_concentration = 1.0`), exceeding the 40% cap.

The return, drawdown, and rank-separation gates passed. Production therefore remains on the current score, and v2 remains available only in `lhb_selection_score_v2_shadow.csv`.

Feature coverage is recorded in the holdout report. Institution net-buy is missing for 45.79% of eligible rows and high-to-close drawdown for 73.83%; this is another reason not to force promotion.
