# P1d.2 REGRESSION DIFF

Baseline branch: `fix/p1d1-historical-tradeability-gate` @ `7fe99ee8`

## Test surface

```
.venv/bin/pytest \
  tests/test_tradeability_p1d.py tests/test_tradeability_p1d1.py \
  tests/test_tradeability_p1d2.py tests/test_backtest.py \
  tests/test_backtest_constraints.py tests/test_retention_backtest.py \
  tests/test_dragon_case_library.py tests/test_market_emotion_state_v1.py \
  tests/test_lhb_eligibility.py tests/test_mid_trend_shadow_backtest.py \
  tests/test_intraday_risk_filter_backtest.py \
  tests/test_dashboard_backtests.py tests/test_core_data.py -q
=> 319 passed, 0 failed
```

- New failures vs P1d.1 baseline: **0**
- `tests/test_tradeability_p1d.py` (22) + `test_tradeability_p1d1.py` (33): unchanged, zero regression
- `tests/test_tradeability_p1d2.py`: +18 new tests
- `tests/test_backtest.py`: expected `BAR_COLUMNS` updated (+4 status cols)
- `tests/test_intraday_risk_filter_backtest.py`: SQL assertion updated
  (literal `false AS` → status join), test renamed `uses_status_table_flags`

## Behavioral changes vs P1d.1

| Change | Default impact |
|---|---|
| loaders join `core.asset_status_daily` | previously-inert limit gate now receives real flags — execution gates become ACTIVE where flags exist |
| `limit_state_missing` marker | no effect under default constraints; blocks only when `block_missing_limit_state=True` |
| `apply_buy_filter`/`sell_bar_for_holding` `use_status_flags` param | default False — legacy heuristic path byte-identical |
| `dragon_case_library._is_limit_up` | output changes: correct board/date/status-aware limit days + 2 new traceability columns |
| open-tier `tradeability_at` | no future OHLC in open decisions; `information_tier`/`ex_post_execution_assumption` fields added |
| `tradeability.py` provider semantics | required-source absence → `required_source_missing`; unknown minute state + gap block → fail closed |

## Production untouched

- No production backtest fill rules changed (all corrected paths opt-in).
- No `asset_status_daily` writes; no flag overwrites.
- No signal/admission/EOD/scheduling changes.
- `market_emotion_state_v1` still reads stored flags — flagged
  NEEDS_REVALIDATION rather than silently changed.
