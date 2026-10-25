# P1d.2a — Pre-Cutover Safety Patch Report

Baseline: `7916e236` (`fix/p1d2-backtest-consumer-gate`)
Branch: `fix/p1d2a-cutover-safety`
Scope: four review-confirmed defects only — no new audit sweeps, no
redesign of the tradeability system.

## P0 findings → fixes

### 1. Loaders still read v1 flags (62,937 confirmed mislabels unrepaired)

Loaders keep reading v1 for `legacy` mode (reproduction only, annotated in
`prices.attrs["qualification_note"]`). The explicit mode system now exists
so consumers never mistake stored flags for corrected truth:

- `legacy` — stored v1 flags; documented-risk annotation on the frame.
- `corrected_shadow` — flags recomputed by the shared rule engine
  (`compute_pit_limit_flags`); rule_unknown and absent rows fail closed;
  writes nothing to production.
- `verified_v2` — reads `is_limit_*_v2`/`limit_state_v2`; absent columns or
  non-verified state → all rows `limit_state_missing` (fail closed). Cannot
  auto-activate: it only returns verified state after migration exists.

### 2. `limit_state_missing` only checked `s.asset_id IS NULL`

All 7 status-join SQL sites now emit
`(s.asset_id IS NULL OR s.is_limit_up IS NULL OR s.is_limit_down IS NULL
 OR s.is_suspended IS NULL) AS limit_state_missing` — a status row with NULL
flags is missing, not "verified false". `_normalize_prices` computes the
marker from ANY-NULL across the three flags before filling, so NULL never
degenerates to False. `can_open_long`/`can_close_long` block it under
`block_missing_limit_state=True` (corrected mode).

### 3. `_effective_execution_constraints` dropped `block_missing_limit_state`

The nonzero-cost rebuild now uses `dataclasses.replace(constraints,
commission_bps=...)` — every configured field survives, including future
constraint flags. Parametrized test covers 0 and 15 bps: strict block works
in both, and legacy default remains reproducible.

### 4. Minute provider ignored `trade_date`

`LedgerMinuteQualificationProvider` now carries a `date_checker`
(asset, date, freq, source → bool). `load_tradeability_context` binds it to
`EXISTS` on `market.stock_minute_bar` (qfq). Verdict versions report tier:

- `r2_minute_v1:<sig>:date_rows_verified` — key done AND rows exist for the date
- `r2_minute_v1:<sig>:key_level_unverified_date` — checker bound, no rows
- `r2_minute_v1:<sig>:key_level` — no checker bound, key done only

`minute_date_verified=False` on a traded, status-present day →
`data_ready_minute=False` + reason `minute_date_unverified` (fail closed).
The DB proved the reviewer right: akshare "coverage" for 603213/605077 is a
single session (2026-06-17, 48 rows) — asserting readiness on other dates
was exactly the overclaim this patch removes.

## EOD write consistency (migration note)

`STORAGE_MIGRATION_READINESS.md` batch plan already covers historical v2
backfill; the EOD incremental path MUST emit v2 flags via the same rule
engine (not static thresholds) so repaired history is not re-polluted. That
writer change stays in the authorized migration step — none is applied now.
