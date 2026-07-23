# LHB Top5 Ranking Calibration — Phase C Plan

## Goal

Build a point-in-time, chronological shadow calibration for `lhb_selection_score_v2`. Promotion is allowed only when every untouched-holdout gate passes; otherwise the existing production score remains active.

## Tasks

1. Persist the complete Phase A eligible candidate universe, not only selected Top-N rows.
2. Add a calibration module that rejects future/outcome fields as features and builds chronological expanding-window validation plus a final untouched holdout.
3. Evaluate a small set of transparent monotonic formulas using only T-close LHB and technical features.
4. Select the formula on pre-holdout walk-forward results, then compute holdout mean 5-day return, T+1 up rate, 5-day drawdown, Top1-5 versus ranks 6-10, monthly excess-return concentration, sample size, and missing coverage.
5. Emit versioned shadow scores, formula metrics, acceptance gates, and promotion decision. A failed gate must keep production on the current score.
6. Run the 2026-01-05 through 2026-07-14 calibration dataset and document the honest result.

## Verification

Tests prove chronological/non-overlapping splits, future-feature rejection, identical eligible universes for baseline and candidate, holdout-only gates, and non-promotion after any failed gate.
