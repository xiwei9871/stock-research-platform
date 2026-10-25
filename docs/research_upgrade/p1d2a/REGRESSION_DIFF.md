# P1d.2a REGRESSION DIFF

Baseline: `7916e236` (`fix/p1d2-backtest-consumer-gate`)

## Test surface

```
.venv/bin/pytest \
  tests/test_tradeability_p1d.py tests/test_tradeability_p1d1.py \
  tests/test_tradeability_p1d2.py tests/test_tradeability_p1d2a.py \
  tests/test_backtest.py tests/test_backtest_constraints.py \
  tests/test_retention_backtest.py tests/test_dragon_case_library.py \
  tests/test_market_emotion_state_v1.py tests/test_lhb_eligibility.py \
  tests/test_mid_trend_shadow_backtest.py \
  tests/test_intraday_risk_filter_backtest.py \
  tests/test_dashboard_backtests.py tests/test_core_data.py \
  tests/test_intraday_risk_control_v2.py \
  tests/test_serenity_tight3b_c2_experiment.py \
  tests/test_portfolio_backtest.py tests/test_vectorized_topn_backtest.py -q
=> 383 passed, 0 failed
```

- New failures vs P1d.2 baseline: **0**
- `tests/test_vectorized_topn_backtest.py`: loader SQL assertion updated
  (`FROM market_daily_bar` → joined form + `limit_state_missing` presence)
- `tests/test_tradeability_p1d2a.py`: +9 tests (4 fix areas + 3 DB-gated
  end-to-end mode tests)
- `scripts/p1d2_db_assertions.py`: 16 → **18 cases** (date-bound alt-source
  coverage split into unverified/verified dates), all pass

## Behavioral changes vs P1d.2

| Change | Impact |
|---|---|
| `limit_state_missing` = row-missing OR any flag NULL | stricter missing detection; verified-False still distinct |
| `_effective_execution_constraints` → `dataclasses.replace` | strict block now survives nonzero cost config |
| Minute provider date binding | alt-source assets now fail closed on dates without that source's qfq rows — 603213/605077 lose the false "qualified on any date" claim |
| `qualification_mode` on loader | `legacy`/`corrected_shadow`/`verified_v2` explicit; default stays `legacy` for reproduction parity |
| `compute_pit_limit_flags`/`apply_pit_flags` in tradeability.py | shadow script delegates — one implementation, no parallel logic |

## Deliberately NOT changed

- Default constraint values, default `qualification_mode="legacy"`, all
  production signal/fill/EOD paths, `asset_status_daily` contents.
- The shadow legs re-ran byte-identical — the patch changed wiring
  correctness, not default-path outputs.

## Honest caveat (per review)

The deploy semantics changed for any consumer that NOW supplies real flags
where the gate was previously inert: once deployed, those backtests stop
simulating fills through real limit-locked days. Default parameters are
unchanged, but **default behavior is not bit-identical** for the paths that
were silently broken before — that is the point of the fix.
