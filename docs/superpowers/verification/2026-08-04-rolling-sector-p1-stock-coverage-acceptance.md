# Rolling-sector P1 stock-data coverage acceptance — 2026-08-04

## Scope

P1 audits the non-Beijing stocks newly exposed by the 2026-08-04 daily THS
membership snapshot.  The latest complete market cutoff available for the
stock bars and status window is 2026-07-31.  Finance and valuation are
queried explicitly as-of 2026-07-31 as well, so no post-cutoff fundamental or
valuation row is admitted to this acceptance.  The market audit uses the 252
distinct open sessions returned by `market.trading_calendar`; it does not
infer the window from whatever rows happen to be present.  The audit uses the
database loader and stock scorer contract; it does not call Baostock, AkShare,
Tushare, or any other provider.

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
| Distinct open sessions audited | 252 | pass |
| Eligible qfq rows in 252-session window | 997,005 | audited |
| Matching eligible status rows in 252-session window | 997,005 | audited |
| Missing qfq/status/activity rows | 0 | pass |
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
| qfq bars loaded | 998,684 |
| Status rows loaded | 3,598 |
| Finance rows loaded | 39,480 |
| Valuation rows loaded | 3,598 |
| Feature rows | 13,063 |
| Distinct feature assets | 3,592 |
| `StockScoringDataGap` | none |

This smoke is intentionally anchored at 2026-08-04 so the 2026-08-04
membership snapshot is visible.  Market bars and status are frozen at
2026-07-31, and the finance/valuation loaders are called with an explicit
2026-07-31 as-of cutoff.  It does not make the 8/4 snapshot visible to a 7/31
replay.

The reproducible target-asset audit API was run on the 3,592 assets eligible at
the 2026-07-31 cutoff, with the explicit 252-session calendar supplied.  It
reports the same zero-gap result:

```text
eligible_assets=3592
expected_trade_dates=252
market_missing_assets=0
market_activity_missing_assets=0
status_missing_assets=0
finance_missing_assets=0
valuation_missing_assets=0
```

## Historical status continuity classification

Status is sparse on lifecycle/non-trading dates, so a rectangular “one row for
every asset on every calendar date” count is not used as a backfill gate.  The
target audit instead requires status wherever a qfq bar is present and always
requires the latest cutoff status.  Under that contract, all 3,592 eligible
assets have complete market/status/activity coverage across the 252-session
window.  No provider backfill is therefore justified.

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

The historical target-gap diagnosis classified 1,053 blocked-sector
`sector_features` rows, mostly outside the 302-target stock-data scope.  The
successful 2026-07-31 manifest itself has `preflight.json` with
`blocked=false` and `gaps=[]`; the 1,053 diagnostic rows are not newly exposed
stock market/finance/valuation gaps.  The publication fix is implemented by
the shared `_append_blocked_sector_feature_gaps` helper so the legacy anchor
path and full-sector batch path satisfy the same snapshot contract.

## Remaining boundary

The 2026-08-04 concept index daily bar was not yet present at audit time.  The
next daily close should load that bar before publishing an 8/4 sector signal.
P2 remains the separate target replay and forward-outcome validation stage.
