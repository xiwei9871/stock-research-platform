# Rolling-sector P0 acceptance — daily snapshot standard

Date: 2026-08-04  
Scope: 302 target THS concepts, excluding BSE stocks  
Acceptance standard: sector signals use concept-index history; each successful
daily constituent snapshot is treated as the latest PIT snapshot for its
capture date.

## Decision

**P0 accepted for sector-first rolling oversold research.**

The former requirement for a provider-verified historical membership export is
removed from the sector P0 gate. It remains a quality limitation for strict
historical stock-level attribution, not a blocker for sector detection or
forward research.

## Evidence

| Check | Result | Status |
|---|---:|---|
| Target concepts | 302 | pass |
| Target concepts with THS index bars | 302/302 | pass |
| Target concepts with bars through 2026-07-31 | 302/302 | pass |
| 2026-07-31 proxy membership anchor | 2026-07-09 snapshot | pass, assumed proxy |
| Eligible target concepts at 2026-07-31 | 192/302 | pass for sector P0; stock mapping gap tracked |
| 2026-08-04 successful daily member snapshots | 297/302 | pass, partial snapshot |
| 2026-08-04 valid non-BSE memberships | 13,080 | pass |
| 2026-08-04 database writes | 13,679 | pass |
| 2026-08-04 active eligible target concepts | 300/302 | pass; 2 remain unmapped |
| New BSE rows | 0 | pass |
| Duplicate `(asset, concept, start_date)` rows | 0 | pass |
| Stale active rows for successful concepts | 0 | pass |

The five concepts whose 2026-08-04 live fetch failed were not allowed to
close their prior relationships. Three retain the 2026-07-09 proxy rows; two
have no eligible active row and remain explicit coverage gaps. The fetch report
is at:

`outputs/research/rolling_sector_target_membership_2026-08-04/target_membership_backfill_summary.json`

The live source is capped at the first 50 THS-ranked members per concept. The
report records the cap for 217 concepts. This is sufficient for the current
candidate research contract but is not a claim of complete board membership.

## Replay isolation

Rows written with `start_date=2026-08-04` are not visible to a 2026-07-31
anchor. The 2026-07-31 replay therefore uses the 2026-07-09 proxy snapshot;
the 2026-08-04 snapshot becomes available only at an anchor on or after
2026-08-04.

The concept index table currently has no 2026-08-04 daily bar. The daily
sector signal should run after the 2026-08-04 market close bars are loaded.

## Verification commands

```text
pytest tests/test_rolling_oversold_target_membership_backfill.py \
  tests/test_rolling_oversold_acceptance.py \
  tests/test_rolling_oversold_pipeline.py \
  tests/test_rolling_oversold_cli.py -q
73 passed

pytest tests/test_rolling_oversold_*.py -q
294 passed
```

The strict historical source guard remains available for research runs that
require vendor-proven PIT dates. The daily operational command must use
`--assume-daily-snapshot-pit` and must retain its generated summary report.
