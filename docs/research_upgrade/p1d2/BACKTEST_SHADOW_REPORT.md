# P1d.2 D — Expanded Backtest Shadow Report

Method: identical scores, prices, engine, params per leg; only the
`is_limit_up/down` flag values differ (stored vs recomputed under the
historically effective rule). rule_unknown rows are forced blocked in the
shadow leg (fail-closed). Costs are applied symmetrically to both legs.

## Shadow matrix (see BACKTEST_SHADOW_MATRIX.csv)

| Run | Window | Cost | Δequity | Diff keys | Verdict |
|---|---|---|---|---|---|
| modern cost0 (P1d.1) | 2024-01→2026-10 | 0 | −0.72pp | 63 | PASS |
| 2023 registration cost0 | 2023-01→2023-12 | 0 | +0.44pp | 4 | PASS |
| 2023 registration cost15 | same | 15bps | +0.35pp | 4 | PASS |
| modern cost15 | 2024-01→2026-10 | 15bps | −0.40pp | 63 | PASS |

- Every differing trade carries `shadow_rule_id` attribution;
  `rule_unknown` pass-through count = 0 in all runs.
- 2023 diffs: a wrongly-blocked sell (`main_10pct` stored limit_down on
  603729 that wasn't legally at limit) plus one knock-on portfolio change —
  explainable, not stochastic.
- Modern diffs (63 keys) identical set under both cost scenarios — the
  divergence is flag-driven, not cost-driven.
- Same-direction cost check: 15bps on both legs deepens the drawdown in
  both arms (−0.27→−0.37 MDD in 2023) while the baseline↔shadow delta
  stays in the same direction/magnitude — costs don't mask qualification
  effects.

## Windows without score coverage → NEEDS_REVALIDATION

`factor.stock_score_daily` covers ≥2023 only. For earlier regimes the
evidence is execution-decision diffs (REGIME_WINDOW_DECISION_AUDIT.csv):

| Window | Unique decisions | Wrongly flagged (FP) | Wrongly passed (FN) |
|---|---|---|---|
| pre-1996 no-limit era | 8,235 | 8,231 | 0 |
| ChiNext pre-reform 10% | 42,644 | 165 | **42,022** |
| STAR reform era 2019–2020 | 397 | 253 | 0 |
| ChiNext 20% transition 2020–21 | 2,473 | 667 | 0 |
| 2023 full-registration | 3,494 | 508 | 50 |
| modern 2024–2026 | 22,426 | 3,798 | 442 |

Interpretation: pre-reform ChiNext is dominated by false negatives —
real limit days were never flagged, so old backtests simulated fills
through locked boards (phantom fills). STAR/post-reform/pre-1996 are
dominated by false positives — trades blocked that could have executed.
Any historical backtest spanning those windows is NEEDS_REVALIDATION.

## Still unreproduced

Old production backtests whose raw inputs aren't persisted stay
NEEDS_REVALIDATION (listed in FINAL_GATE.json).
