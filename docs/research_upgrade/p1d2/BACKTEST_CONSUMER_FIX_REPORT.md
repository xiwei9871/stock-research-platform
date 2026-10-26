# P1d.2 B/C — Backtest Consumer Fix Report

## B: data-load chain fixes (all production-default behavior preserved)

| Path | Defect | Fix |
|---|---|---|
| `vectorized_topn_backtest.py` `load_vectorized_topn_inputs` | queried `is_limit_up/down/is_suspended` FROM `market_daily_bar` — columns don't exist → `UndefinedColumn` hard failure | join `core.asset_status_daily`; emits `limit_state_missing` marker |
| `backtest.py` `load_backtest_bars` / `load_backtest_inputs` | flag columns never loaded → `can_open_long` limit gate silently inert | same status join; `BAR_COLUMNS` extended; `BacktestBar` carries flags (`limit_state_missing` defaults True = fail-closed) |
| `retention_backtest.py` `_bars_by_date_asset` | mapped flag keys but loaders never supplied them | now supplied; `limit_state_missing` propagated |
| `backtest.py` `apply_buy_filter` | static `open >= preclose*1.095` limit heuristic | opt-in `use_status_flags=True`: real PIT flags, `limit_state_missing` blocks, `is_suspended`/`is_limit_up` reasons |
| `backtest.py` `sell_bar_for_holding` | rolled forward only on untradable bars | `use_status_flags=True` also rolls past suspended/limit-down/missing-state days |
| `dashboard/backtests.py` `load_vectorized_topn_prices` | `false AS is_limit_*` — gate permanently inert | status join (real flags + missing marker) |
| `mid_trend_shadow_backtest.py` | `false AS` ×3 | status join |
| `intraday_risk_control_v2.py` | `false AS` ×3 | status join |
| `intraday_risk_filter_backtest.py` | `false AS` ×3 | status join |
| `serenity_tight3b_c2_experiment.py` | `false AS` ×3 | status join |

New constraint: `BacktestExecutionConstraints.block_missing_limit_state`
(default False = legacy behavior; True = missing flag state blocks the order
with reason `limit_state_missing`). Missing flags can no longer silently
default to "not at limit" and simulate fills on the corrected path.

## C: rule consistency audit

| Consumer | Finding | Handling |
|---|---|---|
| `lhb_eligibility` | aligned in P1d.1 — `_regime_and_threshold` routes through shared engine | verified consistent, 127 LHB tests pass |
| `dragon_case_library._is_limit_up` | static `is_st ? 4.8% : 9.5%` thresholds, no date/board awareness — same defect class as the mislabeled flags | rewritten to `resolve_limit_rule` per (ts_code, date, is_st); adds `limit_rule_id` + `limit_day_verified` traceability; rule_unknown/no-limit → `limit_up_day=False`, `verified=False` (fail-closed) |
| `market_emotion_state_v1` | counts limit-up/down directly from stored `asset_status_daily` flags → counts are wrong wherever flags were mislabeled | documented NEEDS_REVALIDATION; not rewired (would change production regime series — prohibited) |
| 1990-12-19 anomalous ST rows | ST regime didn't exist until 1998 | `RULE_UNKNOWN` + fail-closed (8 unique rows) |
| Beijing ST rule | `verified=False` in LIMIT_RULES | resolves to `RULE_UNKNOWN` → fail-closed, no fallback |
| COALESCE-style flag fallback | forbidden `COALESCE(v2, v1)` pattern | audited: **no such fallback exists** anywhere in `src/`; migration design (see STORAGE_MIGRATION_READINESS) explicitly forbids it — v2 states are `not_computed / verified_true / verified_false / rule_unknown / data_insufficient` |

## Verification

- Focused suite: `.venv/bin/pytest` on tradeability, backtest,
  backtest_constraints, retention, dragon, emotion, lhb, mid_trend,
  intraday filter, dashboard backtests, core_data → **319 passed, 0 failed**.
- `tests/test_intraday_risk_filter_backtest.py` assertion updated to require
  the status join (`uses_literal_price_status_flags` renamed
  `uses_status_table_flags`).
- `tests/test_backtest.py` expected `BAR_COLUMNS` updated (13 cols).
