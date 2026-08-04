# Rolling-sector P1 stock-data coverage acceptance — 2026-08-04

## Scope

P1 audits the non-Beijing stocks newly exposed by the 2026-08-04 daily THS
membership snapshot.  The latest complete market cutoff available in the
database is 2026-07-31, so all stock inputs below are frozen at that cutoff.
The audit uses the database loader and stock scorer contract; it does not call
Baostock, AkShare, Tushare, or any other provider.

The required stock contract is:

- qfq positive anchor close and non-negative activity for a stock that is
  eligible at the cutoff;
- a latest cutoff status row;
- a PIT finance row with usable `roe` and positive `total_share`;
- a PIT valuation row with a positive `pe_ttm` or `ps_ttm` fallback.

## Decision

**P1 accepted for newly exposed stock-data coverage.** No confirmed actionable
market, status-cutoff, finance, or valuation gap remains, so no provider
backfill was executed.

This acceptance does not claim that every historical status date has a row, or
that the 2026-08-04 concept index bar has already been loaded. Those are
separate operational/data-continuity items.

## Coverage evidence

| Check | Result | Status |
|---|---:|---|
| Snapshot assets | 3,598 | pass |
| Snapshot membership rows | 13,080 | pass |
| Non-BSE snapshot assets | 3,598/3,598 | pass |
| Eligible at 2026-07-31 | 3,592 | pass |
| Ineligible at cutoff | 6 (2 ST, 4 suspended) | excluded by policy |
| Cutoff status rows | 3,598/3,598 | pass |
| Eligible qfq anchor closes | 3,592/3,592 | pass |
| Eligible qfq anchor activity | 3,592/3,592 | pass |
| Eligible status-days in 252-session window | 876,042 | audited |
| Missing qfq close on eligible status-days | 0 | pass |
| Missing qfq activity on eligible status-days | 0 | pass |
| Finance loader rows | 39,480 | pass |
| Assets with usable `roe` | 3,598/3,598 | pass |
| Assets with positive `total_share` | 3,598/3,598 | pass |
| Valuation loader rows | 3,598 | pass |
| Assets with positive PE/PS fallback | 3,598/3,598 | pass |

The six excluded assets are `CN:SH:600238`, `CN:SZ:002828`,
`CN:SZ:300615`, and `CN:SZ:300862` (suspended), plus `CN:SZ:000793` and
`CN:SZ:002667` (ST).  Their missing/zero activity does not enter stock
scoring because `_is_ineligible_status` excludes them before the stock data
contract is evaluated.

## Actual scorer smoke

The 2026-08-04 snapshot membership was supplied to the real
`_build_stock_features` path with market data frozen at 2026-07-31:

| Output | Result |
|---|---:|
| Snapshot assets | 3,598 |
| qfq bars loaded | 551,588 |
| Status rows loaded | 3,598 |
| Finance rows loaded | 39,480 |
| Valuation rows loaded | 3,598 |
| Feature rows | 13,063 |
| Distinct feature assets | 3,592 |
| `StockScoringDataGap` | none |

This smoke is intentionally anchored at 2026-08-04 so the 2026-08-04
membership snapshot is visible, while the latest market/finance/valuation
inputs remain frozen at 2026-07-31.  It does not make the 8/4 snapshot visible
to a 7/31 replay.

## Historical status continuity classification

The broad 252-session rectangle contains 1,608 absent status rows across 42
assets.  A direct join found zero qfq or hfq market-bar rows on all 1,608
dates.  These are therefore no-bar/non-trading or lifecycle-date gaps, not
confirmed status rows that can be reconstructed from an existing market bar.
The current rolling loader only consumes the latest status row at the cutoff,
which is complete for all 3,598 snapshot assets.  These historical continuity
rows are recorded as non-actionable and are not backfilled blindly.

## Pipeline verification

Database preflight at the 2026-07-31 cutoff passed with zero input coverage
gaps.  A single-anchor legacy replay then completed after the shared blocked
sector-feature-gap publication fix:

```text
anchor=2026-07-31
blocked=0
runtime_seconds=84.79
snapshot_id=rolling_oversold_v1|2026-07-31
```

The replay manifest records 1,053 structured `sector_features` gaps.  These
are blocked sector repair rows (mostly outside the 302-target stock-data
scope), not newly exposed stock market/finance/valuation gaps.  The fix is
implemented by the shared `_append_blocked_sector_feature_gaps` helper so the
legacy anchor path and full-sector batch path satisfy the same snapshot
contract.

## Remaining boundary

The 2026-08-04 concept index daily bar was not yet present at audit time.  The
next daily close should load that bar before publishing an 8/4 sector signal.
P2 remains the separate target replay and forward-outcome validation stage.

