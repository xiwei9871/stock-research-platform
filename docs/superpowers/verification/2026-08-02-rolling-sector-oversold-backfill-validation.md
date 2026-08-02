# Rolling Sector Oversold Backfill and Replay Validation — 2026-08-02

## Scope

- Strategy: `rolling_oversold_v1`
- Frozen replay window: 2026-07-21 through 2026-07-31
- Effective trading anchors: 2026-07-21, 22, 23, 24, 27, 28, 29, 30, 31
- Adjust type: `qfq`
- Limits: sector top 30, stock top 20
- Database service: `stock_research`
- BSE scope: excluded throughout

Strategy execution remained database-only.  Baostock was used only by explicit
backfill tasks; the rolling loader and scorer do not invoke a network source.

## Backfill evidence

The initial 2026-07-21 preflight contained 3,750 gap rows.  After the planned
master/membership, derived, finance, valuation, and market repairs, a direct
database audit over all nine open sessions returned zero missing qfq bars and
zero missing `core.asset_status_daily` rows for the active non-BJ universe.

| Repair | Result | Evidence |
| --- | ---: | --- |
| Industry membership refresh, 2026-07-21 | 5,200 rows | `sync-industry-memberships --trade-date 2026-07-21` |
| Industry membership refresh, 2026-07-31 | 5,202 rows | `sync-industry-memberships --trade-date 2026-07-31` |
| Original Baostock market backfill | 2,592 bars, 0 failed | `artifacts/rolling_sector_oversold/market_backfill_baostock_2026-07-21/market_backfill_report.json` |
| 2026-07-22 targeted repair | 3 bars, 0 failed, 0 missing | `artifacts/rolling_sector_oversold/market_backfill_baostock_2026-07-22_002199/market_backfill_report.json` |
| 2026-07-23 targeted repair | 6 bars, 0 failed, 0 missing | `artifacts/rolling_sector_oversold/market_backfill_baostock_2026-07-23_002036_300242/market_backfill_report.json` |
| 2026-07-24 targeted repair | 9 bars, 0 failed, 0 missing | `artifacts/rolling_sector_oversold/market_backfill_baostock_2026-07-24_3assets/market_backfill_report.json` |
| 2026-07-27—31 bulk repair | 195 bars, 0 failed, 0 missing | `artifacts/rolling_sector_oversold/market_backfill_baostock_2026-07-27_07-31_bulk/market_backfill_report.json` |
| Derived coverage | full range present | `artifacts/rolling_sector_oversold/derived_backfill_2026-07-21/derived_backfill_report.json` |
| PIT fundamentals | support union of 37 assets; incomplete rows retained in report | `artifacts/rolling_sector_oversold/fundamental_backfill_2026-07-21_acceptance_v3/fundamental_backfill.json` |

The original derived task covered `asset_status_daily`, CSRC industry bars,
concept bars, and `STAR_50`; `BSE_50` remained explicitly out of scope.  The
fundamental task derived only source-backed PE/PS rows and never fabricated
EV/EBITDA when EBITDA was absent.

## Baostock link stability

Three independent probe rounds each completed login, `query_stock_basic`,
daily-history queries for Shanghai/Shenzhen and STAR/ChiNext symbols, and
logout successfully.  The observed issue was missing source/lifecycle data for
individual dates, not link instability.  All targeted repair runs reported
zero failed and zero missing rows.

## Replay acceptance

Final replay output:

`artifacts/rolling_sector_oversold/replay_2026-07-21_2026-07-31_stock_research_v6/rolling_sector_oversold`

Every anchor produced an immutable snapshot and passed preflight:

| Anchor | Runtime (s) | Preflight | Previous snapshot |
| --- | ---: | --- | --- |
| 2026-07-21 | 83.39 | passed | — |
| 2026-07-22 | 83.98 | passed | 2026-07-21 |
| 2026-07-23 | 84.17 | passed | 2026-07-22 |
| 2026-07-24 | 84.79 | passed | 2026-07-23 |
| 2026-07-27 | 85.38 | passed | 2026-07-24 |
| 2026-07-28 | 85.65 | passed | 2026-07-27 |
| 2026-07-29 | 85.55 | passed | 2026-07-28 |
| 2026-07-30 | 86.62 | passed | 2026-07-29 |
| 2026-07-31 | 88.00 | passed | 2026-07-30 |

The CLI reported `blocked=0` and `runtime_seconds=769.5769` for the complete
window.  No `CN:BJ:` identifier appears in the replay artifacts.  A separate
focus report for the 2026-07-30 snapshot was generated at:

`artifacts/rolling_sector_oversold/validation_2026-07-30/rolling_sector_oversold_report.md`

It identifies the 2026-07-30 market regime as `risk_off` and preserves the
technology/consumer focus groups, including CPO, semiconductor, chip,
算力, technology, and consumer mappings.

## Runtime interpretation

The single-anchor daily command completed in about 84 seconds after the
vectorized PIT fallback and datetime fixes.  The nine-anchor historical replay
took about 12.8 minutes because it intentionally reloads the full 5,200-asset
PIT universe for every frozen date.  These are different operational paths:

- daily production: one anchor, database reads only, about 84 seconds in this
  run and well below the one-hour operational target;
- historical validation: repeated frozen loads, about 13 minutes for this
  nine-session window, within the 3,600-second replay budget.

## Verification commands

```text
pytest tests/test_rolling_oversold_*.py \
  tests/test_consumer_oversold_loaders.py \
  tests/test_consumer_oversold_pipeline.py \
  tests/test_consumer_oversold_v2_evaluation.py -q
355 passed, 2 warnings

python -m compileall -q src/stock_research
git diff --check
```

The code changes were committed as `e88f823` (`fix: complete rolling PIT
valuation and datetime handling`).  Runtime artifacts remain outside the code
commit and are referenced above by path for auditability.
