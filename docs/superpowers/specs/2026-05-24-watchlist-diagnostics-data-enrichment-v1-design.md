# Watchlist Diagnostics Data Enrichment v1 Design

## 1. Objective

Enrich the existing `watchlist diagnostics v1` pipeline with real Dragon / LHB / failure-event inputs so `must_watch` is driven by actual research signals rather than empty placeholders.

This remains a diagnostics layer, not a trading signal or execution system.

## 2. Scope

### In scope

- enrich watchlist diagnostics with recent event-level Dragon / failure / LHB data;
- carry through `stock_name` and `volatility_5d` into diagnostics outputs;
- use a rolling event lookback window of 20 trading days;
- keep fallback behavior when no event matches;
- preserve existing watchlist diagnostics CLI/report contracts.

### Out of scope

- rebuilding daily event detection from scratch;
- new strategy scoring logic;
- backtesting or execution logic;
- expanding beyond the already-approved research artifacts.

## 3. Default Time Alignment

For each watchlist candidate:

- join by `ts_code`;
- only consider `event_date <= trade_date`;
- restrict to events within the last 20 trading days;
- select the most recent matching event;
- if no event is found, degrade to empty/default diagnostics.

This avoids contaminating the current watchlist with stale historical cases.

## 4. Data Sources

### A. Failure / case classification

File:

- `outputs/research/dragon_case_curated_library_failure_v2_1.csv`

Fields to use:

- `ts_code`
- `stock_name`
- `verified_case_type_v2_1`
- `success_or_failure`
- `event_date`
- `event_type`
- `confidence`

Mapped watchlist fields:

- `event_structure`
- `failure_flag`
- `case_event_date`
- `case_event_type`
- `case_confidence`

### B. Dragon factor snapshot

File:

- `outputs/research/dragon_case_factor_snapshot_2024_2026.csv`

Fields to use:

- `ts_code`
- `stock_name`
- `trade_date`
- `amount_vs_20d`
- `high_to_close_drawdown`
- `volatility_5d`

If available in the snapshot or aligned side data, also use:

- `dragon_risk_score`
- `overheat_avoid`
- `crowded_late_entry`

Mapped watchlist fields:

- `amount_vs_20d`
- `high_to_close_drawdown`
- `volatility_5d`
- `dragon_risk_score`
- `overheat_avoid`
- `crowded_late_entry`

### C. LHB risk detail

File:

- `outputs/research/lhb_risk_feature_case_detail_v2_1.csv`

Fields to use:

- `ts_code`
- `stock_name`
- `event_date`
- `lhb_risk_score`
- `lhb_negative_net_buy`
- `lhb_institution_selling`
- `lhb_high_pump_risk`
- `lhb_after_event_attention`
- `lhb_risk_level` if present

Mapped watchlist fields:

- `lhb_risk_score`
- `lhb_negative_net_buy`
- `lhb_institution_selling`
- `lhb_high_pump_risk`
- `lhb_after_event_attention`
- `lhb_risk_level`

### D. Asset identity

Source:

- `core.asset_master`

Use to map:

- `asset_id -> ts_code`
- optionally `asset_id -> stock_name` where diagnostics artifacts do not provide it.

## 5. Enrichment Rules

### Candidate identity

Base pool still comes from:

- `factor.stock_score_daily`
- `score_version = manual_v1`
- `top_n = 50`

Each candidate must be enriched with:

- `asset_id`
- `ts_code`
- `stock_name`

### Event attachment

For each source file above:

1. filter by candidate `ts_code`;
2. filter by `event_date <= trade_date` or `trade_date <= trade_date` for snapshots;
3. apply 20-trading-day lookback;
4. pick the most recent record.

### Fallbacks

If no matching record exists:

- `event_structure = ""`
- `failure_flag = False`
- Dragon/LHB fields default to low-risk / empty
- `stock_name` falls back to asset master or top-score row where possible

## 6. Effect on Watchlist Grouping

The existing diagnostics classifier should now operate on real inputs instead of placeholders.

### `risk_watch`

Should start firing when:

- `failure_flag = True`
- `event_structure` is one of:
  - `a_kill_failure`
  - `failed_second_wave`
  - `high_open_low_close_failure`
  - `one_day_pump`
  - `failed_reversal`
- high Dragon or LHB risk fields are present
- `amount_vs_20d` is extreme
- `high_to_close_drawdown` is large

### `opportunity_watch`

Should start firing when:

- event structure is one of the allowed candidate types:
  - `second_wave_candidate`
  - `break_then_reversal_candidate`
  - `weak_to_strong_candidate`
  - `trend_continuation_candidate`
- failure flag is false
- Dragon and LHB risk are not high

## 7. Output Expectations

After enrichment:

- `watchlist_diagnostics_full_<trade_date>.csv` should carry real:
  - `stock_name`
  - `ts_code`
  - `event_structure`
  - `failure_flag`
  - `dragon_risk_score`
  - `lhb_risk_score`
  - `volatility_5d`
- `must_watch` should no longer be systematically empty on dates where recent case-aligned diagnostics exist.

## 8. Error Handling

- Missing optional research files should not crash the build; use empty/default frames.
- Missing required columns in optional files should degrade cleanly after logging/normalization.
- Duplicate event rows for the same `ts_code` should be resolved deterministically by latest eligible date.

## 9. Testing

Minimum coverage:

1. map `asset_id` to `ts_code` for enrichment;
2. attach latest eligible event within 20 trading days;
3. ignore events outside the 20-trading-day window;
4. carry through real Dragon/LHB/failure fields into diagnostics output;
5. preserve empty/default behavior when no matches exist;
6. keep existing watchlist diagnostics CLI/report tests green.

## 10. Implementation Sequence

1. add failing workflow/diagnostics tests for real enrichment;
2. implement `asset_id -> ts_code` and recent-event attachment helpers;
3. enrich Dragon/LHB/failure fields in workflow before calling diagnostics classifier;
4. verify a real trade date produces non-empty `must_watch` when matching inputs exist;
5. run targeted tests;
6. run full pytest.
