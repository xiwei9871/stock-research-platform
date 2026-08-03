# Rolling Sector Target Gap Audit — 2026-08-03

## Scope

This audit uses the database-only v2 replay published at:

`/tmp/rolling_sector_oversold_full_replay_20260727_20260731`

The target universe is the 302 `ths` concept codes in:

`/Users/xiwei/stock_research/outputs/research/concept_drawdown_over24_2026-08-01.csv`

The audit does not write PostgreSQL and does not invoke a provider.

## Current 2026-07-31 result

The replay board contains 1,379 rows across `csrc`, `em`,
`em_core_conception`, and `ths`.  Its 1,053 synthetic `sector_features` gaps
are the fail-closed representation of blocked sector rows, not 1,053
independent external-download tasks.

| Current condition | Rows | Systems | Interpretation |
| --- | ---: | --- | --- |
| Insufficient sector history | 911 | `em` 413, `em_core_conception` 498 | 17 bars only, 2026-07-09 through 2026-07-31; outside the 302-target universe |
| Missing sector volume | 9 | `em_core_conception` | Same 17-bar non-target rows; outside the 302-target universe |
| No active membership | 133 | `ths` 131, `csrc` 2 | Must be split into target membership gaps and optional non-target gaps |
| **Total** | **1,053** |  |  |

## Target 302 diagnosis

All 302 target `ths` concept codes have a concept bar series through
2026-07-31.  There are no target-code rows with a null close or volume.

| Target check | Result |
| --- | ---: |
| Target concept codes | 302 |
| Target codes with bars | 302 |
| Target codes with complete repair feature status | 302 |
| Target codes with active, eligible membership | 192 |
| **Target codes missing active membership** | **110** |
| Target code `ths:300238` / `核电` active membership | missing |

History is sufficient for all target rows: 299 have 280 observations, while
`309268` / `玻璃基板`, `309264` / `AI应用`, and `309261` / `雅下水电概念`
have 22, 133, and 251 observations respectively and still pass the repair
feature contract.  Therefore the target blocker is membership coverage, not
target concept-bar history.

The old 2026-07-21 audit's 3,750 raw preflight gaps have already been repaired
for the active non-BJ stock universe: the companion validation record reports
zero missing qfq market bars and zero missing status rows.  They should not be
reopened as a blanket backfill task.

## Priority classification

1. **P0 — 110 missing target `ths` memberships.**  This includes nuclear and
   the concepts needed to make the 302-sector output genuinely complete.
2. **P1 — newly exposed stock-data coverage.**  After P0 membership sync,
   audit qfq bars, status, PIT finance, and valuation for the newly exposed
   non-BJ assets.  Backfill only confirmed missing rows.
3. **P2 — target replay and outcome validation.**  Re-run 7/27–7/31 and verify
   target coverage, sector-local candidates, and future-only outcomes.
4. **Deferred — 911 short-history and 9 missing-volume rows** in `em`/
   `em_core_conception`, plus 21 extra `ths` and 2 `csrc` no-membership rows.
   These are not part of the 302 target scope.  If the product later requires
   all 1,379 board rows, they need a separate 252-session history plan.

## Reproduction commands

The target membership check is reproducible with this read-only query shape:

```text
SELECT m.concept_code,
       COUNT(*) FILTER (
         WHERE m.start_date <= DATE '2026-07-31'
           AND (m.end_date IS NULL OR m.end_date > DATE '2026-07-31')
       ) AS raw_active,
       COUNT(*) FILTER (
         WHERE m.start_date <= DATE '2026-07-31'
           AND (m.end_date IS NULL OR m.end_date > DATE '2026-07-31')
           AND (a.list_date IS NULL OR a.list_date <= DATE '2026-07-31')
           AND (a.delist_date IS NULL OR a.delist_date > DATE '2026-07-31')
           AND COALESCE(a.exchange, '') <> 'BJ'
       ) AS valid_active
FROM core.concept_membership m
LEFT JOIN core.asset_master a ON a.asset_id = m.asset_id
WHERE m.concept_system = 'ths'
  AND m.concept_code = ANY(:target_codes)
GROUP BY m.concept_code;
```

The exact missing-code list is generated from the target CSV and this query;
it is intentionally not embedded in strategy source or used as an implicit
download list.

