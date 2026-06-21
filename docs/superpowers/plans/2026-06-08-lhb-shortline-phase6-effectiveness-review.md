# LHB Shortline Phase 6 Effectiveness Review Plan

## Goal

Build `lhb_shortline_strategy_effectiveness_v1`, a repeatable review that evaluates the Phase 1-5 shortline groups without changing daily selection or exit rules.

## Scope

- Input: `lhb_shortline_event_replay_v1.csv`.
- Optional input: daily shortline watchlist CSVs or a merged watchlist frame.
- Output:
  - `lhb_shortline_strategy_effectiveness_detail_v1.csv`
  - `lhb_shortline_strategy_effectiveness_summary_v1.csv`
  - `lhb_shortline_follow_combo_effectiveness_v1.csv`
  - `lhb_shortline_exit_combo_effectiveness_v1.csv`
  - `lhb_shortline_strategy_effectiveness_v1.md`
- Add a CLI command: `lhb-shortline-strategy-effectiveness-v1`.

## Implementation Steps

1. Add tests for a pure builder:
   - Merge event replay and watchlist group context.
   - Compute group metrics by `watch_group`, `lhb_behavior_type`, `event_structure`, `entry_window_v2`, `mainline_flag`, and `short_market_state`.
   - Compute exit metrics by `exit_signal` and exploded `exit_reason`.
   - Flag low-sample groups.

2. Implement the builder in `src/stock_research/lhb_data.py`:
   - Normalize dates and keys.
   - Infer `watch_group` from `lhb_replay_action` / `exit_signal` if daily watchlist is absent.
   - Compute average returns, win rates, max drawdown, A-kill rate, limit-up rate, and second-wave success rate.
   - Write CSV and markdown artifacts.

3. Add a run wrapper:
   - Read input CSVs.
   - Return dataframes and artifact paths.

4. Add CLI parser and handler.

5. Verification:
   - Focused `tests/test_lhb_data.py` tests for Phase 6.
   - Relevant regression: `tests/test_lhb_data.py tests/test_watchlist_diagnostics.py tests/test_watchlist_workflow.py tests/test_watchlist_cli.py`.

## Non-Goals

- Do not change Phase 4 daily selection rules.
- Do not change Phase 5 watchlist diagnostics classification.
- Do not use future fields in any daily decision path.
