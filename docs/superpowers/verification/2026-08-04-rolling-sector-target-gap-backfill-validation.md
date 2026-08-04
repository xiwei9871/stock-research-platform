# Rolling-sector 302-THS target replay and gap-backfill validation

Date: 2026-08-04  
Strategy: `rolling_oversold_sector_v2`  
Frozen anchors: 2026-07-27 through 2026-07-31  
Forward evaluation cutoff: 2026-08-03  
Adjust type: `qfq`  
Database service: `stock_research`  
Target file: `/Users/xiwei/stock_research/outputs/research/concept_drawdown_over24_2026-08-01.csv`

Status: accepted for the operational latest-snapshot policy.  The structural
target replay, 302-code scope gate, and forward outcome checks pass.  The
historical positive-membership count remains a diagnostic only; it is not a
P2 blocker under the approved 2026-07-09 proxy / 2026-08-04 latest-snapshot
policy.

## Implemented gates and tests

The following changes are present in the current branch:

- `a9d06361`: explicit `concept_codes` scope, THS-only membership/bar SQL
  predicates, CLI target-file parsing, and exactly-one target-row fail-closed
  publication;
- `3cba9ae3`: target replay routing and bidirectional scope-cache
  fingerprints (`unscoped` versus the sorted THS-code set);
- `bff105cc`: read-only target-gap classifier and deterministic 302-code audit;
- `e39de041`: frozen five-anchor acceptance fixture now uses six-digit THS
  codes and asserts positive membership, 302 rows, no leakage, nuclear-sector
  visibility, and complete/pending outcomes.

Focused P2 acceptance tests:

```text
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest -q \
  tests/test_rolling_oversold_target_gap_audit.py \
  tests/test_rolling_oversold_target_scope.py \
  tests/test_rolling_oversold_target_membership_backfill.py \
  tests/test_rolling_oversold_target_coverage.py \
  tests/test_rolling_oversold_acceptance.py
```

Result: `61 passed, 2 warnings in 13.62s`.

The complete rolling-oversold regression is `309 passed, 2 warnings in
37.25s`.

## Frozen target replay

The database-only replay command was:

```text
rtk env PYTHONPATH=src \
  /Users/xiwei/stock_research/.venv/bin/python -m stock_research.cli \
  rolling-sector-oversold-replay \
  --anchor-start-date 2026-07-27 \
  --anchor-end-date 2026-07-31 \
  --output-dir /tmp/rolling_sector_target_replay_20260727_20260731 \
  --score-version rolling_oversold_sector_v2 \
  --service stock_research \
  --concept-codes-file \
    /Users/xiwei/stock_research/outputs/research/concept_drawdown_over24_2026-08-01.csv
```

Observed machine result: `blocked=0`, five anchors processed, total runtime
`192.45945516694337s`.  The immutable output root is
`/private/tmp/rolling_sector_target_replay_20260727_20260731`.

| Anchor | THS board rows | Duplicate sector keys | Nuclear rows/name | `blocked_data` rows | Target-scope gaps |
| --- | ---: | ---: | --- | ---: | ---: |
| 2026-07-27 | 302 | 0 | 1 / `核电` | 111 | 0 |
| 2026-07-28 | 302 | 0 | 1 / `核电` | 111 | 0 |
| 2026-07-29 | 302 | 0 | 1 / `核电` | 110 | 0 |
| 2026-07-30 | 302 | 0 | 1 / `核电` | 110 | 0 |
| 2026-07-31 | 302 | 0 | 1 / `核电` | 110 | 0 |

All five manifests carry the same target scope fingerprint
`ths:3570a3fd962335b0e166c30b27d7003ffc899a19b839d2b283c701cab79817a7`.
The board contains only `sector_system=ths`; no optional `em`, `csrc`, or
`em_core_conception` rows leak into this target run.

The 2026-07-27 and 2026-07-28 extra blocked row is `309268`, which has positive
membership but only 18/19 observations at those earlier cutoffs.  It becomes
publishable at 20+ observations on 2026-07-29.  This is a feature-history
boundary, not a membership backfill result.

## Historical membership diagnostic (non-blocking)

A read-only database audit using the same active-membership predicates as the
loader found:

| Anchor | Target concepts | Positive active non-BJ membership | Missing active membership |
| --- | ---: | ---: | ---: |
| 2026-07-27 | 302 | 192 | 110 |
| 2026-07-28 | 302 | 192 | 110 |
| 2026-07-29 | 302 | 192 | 110 |
| 2026-07-30 | 302 | 192 | 110 |
| 2026-07-31 | 302 | 192 | 110 |

Thus the 302 board-row assertion is satisfied by retaining blocked rows, but
the stronger “every target has a positive member set” assertion is not for the
historical proxy.  The 110 historical gaps are represented as
`blocked_data`/`sector_features` diagnostics; they are not silently treated
as a historical membership fact.

The current 2026-08-04 membership snapshot has 300/302 positive target
concepts.  Under the approved operational policy it is the latest membership
snapshot, while the 2026-07-09 capture is the historical replay proxy.  The
two current unmapped concepts are retained as explicit non-fatal coverage
gaps rather than being fabricated.

The read-only classifier also reproduces the old full-board audit buckets on
the 1,379-row replay: 302 target codes, 110 target membership gaps, and
deferred non-target rows split into 911 short-history, 9 missing-volume, and
23 non-target membership rows.  Those non-target rows remain outside this
P2 target task.

## Future-only outcome validation

Using the published snapshots and database qfq bars through 2026-08-03 (1,072
unique candidate assets; 5,358 future rows), all non-null target dates were
strictly later than their anchor.  Outcome states were:

| Anchor | Detail rows | Complete | Pending | Excluded invalidated | Invalid target dates |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2026-07-27 | 5,619 | 5,617 | 2 | 0 | 0 |
| 2026-07-28 | 6,183 | 3,752 | 1,876 | 555 | 0 |
| 2026-07-29 | 6,132 | 3,769 | 1,889 | 474 | 0 |
| 2026-07-30 | 6,309 | 1,891 | 3,782 | 636 | 0 |
| 2026-07-31 | 6,378 | 1,890 | 3,783 | 705 | 0 |

The complete/pending split is correct for the available future window; no
future bar was used to score an earlier anchor.

## Acceptance decision

P2 is **accepted for operational sector-first research**: scope isolation,
302-row target publication, nuclear visibility, latest-snapshot coverage,
no-leakage semantics, and forward outcome states pass.  The strict historical
membership result (192/302) remains available for attribution audits, but it no
longer blocks the rolling sector signal.  The current 8/4 snapshot has 300/302
positive concepts; `300037 智能电网` and `308874 国资云` remain explicit
blocked-data rows.

The latest-snapshot batch acceptance is recorded in
`docs/superpowers/verification/2026-08-04-rolling-sector-p2-latest-snapshot-acceptance.md`.
