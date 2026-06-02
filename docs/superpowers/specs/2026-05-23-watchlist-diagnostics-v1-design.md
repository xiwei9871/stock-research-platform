# Watchlist Diagnostics v1 Design

## 1. Objective

Build a diagnostics-oriented watchlist layer for short-term research. This is not a trading signal engine and does not produce live execution decisions.

The module should:

- use `manual_v1` top-ranked names as the base candidate pool;
- enrich candidates with Dragon / LHB / technical / event-risk diagnostics;
- output a full diagnostics table and a smaller daily must-watch list;
- prioritize interpretability over model complexity.

## 2. Scope

### In scope

- base candidate pool from `factor.stock_score_daily`;
- diagnostics enrichment from existing research outputs and factor tables;
- `risk_watch` and `opportunity_watch` grouping;
- full CSV diagnostics output;
- reduced must-watch CSV/Markdown output;
- graceful degradation when optional research artifacts are missing.

### Out of scope

- live trading signals;
- execution logic;
- entry/exit backtest logic;
- dynamic optimization or machine-learned ranking;
- expanding factor coverage beyond already-approved v1 inputs.

## 3. Default Behavior

### Candidate pool

- source: `manual_v1`
- default `top_n = 50`

### Must-watch output

- `risk_watch = 10`
- `opportunity_watch = 10`

### Allowed opportunity structures

- `second_wave_candidate`
- `break_then_reversal_candidate`
- `weak_to_strong_candidate`
- `trend_continuation_candidate`

### Explicitly excluded from opportunity watch

- `a_kill_failure`
- `failed_second_wave`
- `high_open_low_close_failure`
- `one_day_pump`

## 4. Architecture

Add a new module:

- `src/stock_research/watchlist/diagnostics.py`

Responsibilities:

1. load the base candidate pool from `stock_score_daily`;
2. align diagnostics inputs from factor / Dragon / LHB / event outputs;
3. assign `risk_watch` / `opportunity_watch` and rule-based priority;
4. return full diagnostics and reduced must-watch outputs.

Keep existing layers separated:

- `watchlist/workflow.py`: orchestration;
- `watchlist/diagnostics.py`: diagnostics logic;
- `reports/watchlist_report.py`: report rendering.

## 5. Inputs

### Required

1. `factor.stock_score_daily`
   - `score_version = manual_v1`
   - top-ranked names

2. factor / technical fields
   - `amount_vs_20d`
   - `volatility_5d`
   - `high_to_close_drawdown`
   - `score_total`
   - `rank`

### Preferred optional inputs

1. Dragon risk
   - `dragon_risk_score`
   - `overheat_avoid`
   - `crowded_late_entry`

2. LHB risk
   - `lhb_risk_score`
   - `lhb_negative_net_buy`
   - `lhb_institution_selling`
   - `lhb_high_pump_risk`
   - `lhb_after_event_attention`

3. Event / failure structure
   - `a_kill_failure`
   - `failed_second_wave`
   - `high_open_low_close_failure`
   - `one_day_pump`
   - `failed_reversal`
   - candidate opportunity labels

4. Market / mainline
   - `market_regime`
   - `sector_strength_rank`
   - `mainline_flag`

If optional sources are unavailable, set these fields to `unknown`, `null`, or `False` as appropriate and continue.

## 6. Outputs

### Full diagnostics table

Suggested file:

- `outputs/research/watchlist_diagnostics_full_<trade_date>.csv`

Fields:

- `trade_date`
- `asset_id`
- `ts_code`
- `stock_name`
- `score_version`
- `score_rank`
- `score_total`
- `market_regime`
- `sector_name`
- `sector_strength_rank`
- `mainline_flag`
- `dragon_risk_score`
- `overheat_avoid`
- `crowded_late_entry`
- `lhb_risk_score`
- `lhb_negative_net_buy`
- `lhb_institution_selling`
- `lhb_high_pump_risk`
- `lhb_after_event_attention`
- `amount_vs_20d`
- `volatility_5d`
- `high_to_close_drawdown`
- `event_structure`
- `failure_flag`
- `opportunity_flag`
- `watch_group`
- `watch_priority`
- `diagnostic_reason`
- `risk_note`
- `opportunity_note`

### Must-watch outputs

Suggested files:

- `outputs/research/watchlist_must_watch_<trade_date>.csv`
- `outputs/research/watchlist_must_watch_<trade_date>.md`

Fields:

- `trade_date`
- `asset_id`
- `stock_name`
- `watch_group`
- `watch_priority`
- `event_structure`
- `diagnostic_reason`
- `risk_note`
- `opportunity_note`

## 7. Rule Logic

### `risk_watch`

Include when any of the following holds:

- failure structure hit:
  - `a_kill_failure`
  - `failed_second_wave`
  - `high_open_low_close_failure`
  - `one_day_pump`
- high risk factor combination:
  - elevated `dragon_risk_score`
  - elevated `lhb_risk_score`
  - extreme `amount_vs_20d`
  - large `high_to_close_drawdown`
- multi-risk confirmation:
  - `overheat_avoid`
  - `crowded_late_entry`
  - `lhb_negative_net_buy`
  - `lhb_institution_selling`

### `opportunity_watch`

Include only when all of the following hold:

- `event_structure` is one of the approved candidate structures;
- candidate is not in the excluded failure set;
- `dragon_risk_score` is not high;
- `lhb_risk_score` is not high;
- `high_to_close_drawdown` is not large;
- `amount_vs_20d` is not extreme blow-off volume;
- if available, `mainline_flag` is preferred.

## 8. Priority Logic

Keep v1 rule-based and explainable.

### Risk watch priority

Higher priority when:

- direct failure structure exists;
- Dragon and LHB risk co-occur;
- technical risk confirms weakness.

### Opportunity watch priority

Higher priority when:

- candidate belongs to a mainline sector;
- total risk is lower;
- `manual_v1` rank is better;
- opportunity structure is stronger.

## 9. CLI and Workflow

Add a dedicated CLI entry for diagnostics generation rather than hiding behavior inside existing report commands.

Suggested CLI:

`stock-research build-watchlist-diagnostics --trade-date YYYY-MM-DD --score-version manual_v1 --top-n 50 --risk-watch-n 10 --opportunity-watch-n 10 --output-dir outputs/research`

The CLI should:

1. load candidate pool;
2. build diagnostics frame;
3. write full diagnostics CSV;
4. write must-watch CSV/Markdown;
5. print stable output paths.

## 10. Error Handling

- If `stock_score_daily` has no rows for the trade date, fail with a clear message.
- If optional diagnostics sources are missing, continue with warnings and degraded fields.
- If required identity fields are inconsistent, fail fast.

## 11. Testing

Minimum coverage:

1. candidate pool loads from `manual_v1 top_n=50`;
2. diagnostics build without optional sources;
3. `risk_watch` rules work;
4. `opportunity_watch` rules exclude failure structures;
5. must-watch counts default to `10 + 10`;
6. output files are generated;
7. existing watchlist/report flows are not broken.

## 12. Implementation Sequence

1. add diagnostics module;
2. add CLI entry;
3. add reduced Markdown/CSV outputs;
4. add tests;
5. run targeted tests;
6. run full pytest.
