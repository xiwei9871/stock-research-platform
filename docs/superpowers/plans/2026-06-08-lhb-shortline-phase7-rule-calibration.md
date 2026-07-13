# LHB Shortline Phase 7 Rule Calibration Plan

## Goal

Build a versioned rule calibration layer from Phase 6 evidence. The output must explain which rules to keep, promote, downgrade, or review before changing daily selection behavior.

## Inputs

- `lhb_shortline_strategy_effectiveness_summary_v1.csv`
- `lhb_shortline_follow_combo_effectiveness_v1.csv`
- `lhb_shortline_exit_combo_effectiveness_v1.csv`
- Optional: `lhb_shortline_strategy_effectiveness_detail_v1.csv`

## Outputs

- `lhb_shortline_rule_registry_v1.csv`
- `lhb_shortline_rule_calibration_v1.md`

## Rules

- Follow rules:
  - Promote/keep combos with enough sample count, positive 5d average return, acceptable drawdown, and solid 5d win rate.
  - Mark sparse combos as `review_sparse`.
  - Downgrade weak combos to `watch_only`.

- Exit rules:
  - Keep strong exit rules with negative forward returns and high exit hit rate.
  - Downgrade or review rules with positive average future return or high win rate after exit.
  - Do not hard-code future values into daily execution. Future metrics only justify registry recommendations.

## Implementation

1. Add a failing builder test for `build_lhb_shortline_rule_calibration_v1`.
2. Implement registry generation and markdown report.
3. Add `run_lhb_shortline_rule_calibration_v1`.
4. Add CLI command `lhb-shortline-rule-calibration-v1`.
5. Run focused and regression tests.
6. Run Phase 7 against current Phase 6 artifacts.
