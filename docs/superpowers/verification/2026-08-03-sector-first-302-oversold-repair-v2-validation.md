# Sector-first 302-concept oversold repair v2 acceptance

Date: 2026-08-03  
Strategy: `rolling_oversold_sector_v2`  
Frozen acceptance anchors: 2026-07-27 through 2026-07-31  
Forward evaluation cutoff: 2026-08-03  
Adjust type: `qfq`  
Database service: `stock_research`  
BSE/BJ scope: excluded by the database loader

## Acceptance scope

This record separates deterministic contract acceptance from the database-only
runtime measurement.  The pytest acceptance fixture does not connect to a
database and does not call Baostock or any other provider.  It supplies five
point-in-time input frames, one per frozen anchor, and validates:

- all five anchors are published in ascending order;
- every anchor retains all 302 sector identities;
- a membership-only sector is retained as `blocked_data` with a structured
  `sector_features` gap rather than being silently dropped;
- no source frame used for scoring contains a bar after its anchor;
- `ths:300238` / `核电` exists in the 2026-07-31 board;
- sector-scoped stock outcomes preserve sector identity/rank and expose both
  `complete` and `pending` states;
- every non-null outcome target date is strictly after its anchor; and
- rerunning the five historical snapshots is byte-identical and does not
  invoke scoring again.

The fixture has 301 stock candidates per anchor (one of the 302 sectors is an
intentional data-gap row), so the expected outcome-state counts are:

| Anchor | Complete rows | Pending rows | Total (301 candidates × 3 horizons) |
| --- | ---: | ---: | ---: |
| 2026-07-27 | 903 | 0 | 903 |
| 2026-07-28 | 602 | 301 | 903 |
| 2026-07-29 | 602 | 301 | 903 |
| 2026-07-30 | 301 | 602 | 903 |
| 2026-07-31 | 301 | 602 | 903 |
| **Total** | **2,709** | **1,806** | **4,515** |

The counts deliberately use only sessions through the 2026-08-03 cutoff.  A
five-day row is pending whenever five strictly future sessions are not yet
available.

## Deterministic acceptance command

```text
rtk /Users/xiwei/stock_research/.venv/bin/pytest -q \
  tests/test_rolling_oversold_acceptance.py
```

Result at the time of this record:

```text
4 passed in 13.35s
```

The two new v2 acceptance tests are:

- `test_sector_v2_acceptance_freezes_five_anchors_and_validates_future_states`
- `test_sector_v2_acceptance_keeps_historical_snapshots_immutable`

The two pre-existing v1 acceptance tests remain in the file and pass as well.

## Database-only 2026-07-31 batch evidence

The full-sector CLI batch was run against the configured PostgreSQL service
`stock_research`; no provider fallback was enabled.  The command shape was:

```text
rtk env PYTHONPATH=src \
  /Users/xiwei/stock_research/.venv/bin/python -m stock_research.cli \
  rolling-sector-oversold-batch \
  --anchor-date 2026-07-31 \
  --output-dir /tmp/rolling_sector_oversold_batch_2026-07-31 \
  --service stock_research \
  --sector-stock-top-n 10 \
  --runtime-budget-seconds 3600
```

Observed run evidence:

| Measure | Result |
| --- | ---: |
| blocked | `false` |
| sector board rows | 1,379 |
| sector-stock candidate rows | 3,062 |
| total runtime | 68.89 s |
| load | 21.43 s |
| market regime | 7.18 s |
| sector scoring | 21.38 s |
| stock scoring | 16.94 s |
| publication | 1.17 s |

The board row count is the complete configured industry/concept sector board
(the 302-concept target universe is included in that database input); the
candidate count is sector-local, so a stock belonging to multiple sectors is
retained once per sector.  The reported total includes stage overhead and is
therefore not expected to equal the rounded sum of the displayed stages.

## v1/v2 paired operational comparison

For the same 2026-07-31 database service and qfq data, the previous mixed-universe
v1 snapshot recorded 88.00 s, 1,379 sector rows, and 29 globally gated stock
rows.  The v2 full-sector batch recorded 68.89 s, the same 1,379 board rows,
and 3,062 sector-local candidate rows.

| Version | Runtime | Board rows | Candidate rows | Interpretation |
| --- | ---: | ---: | ---: | --- |
| v1 legacy gated snapshot | 88.00 s | 1,379 | 29 | Global/legacy gate output |
| v2 sector-first batch | 68.89 s | 1,379 | 3,062 | Independent sector-local output |

This is an operational breadth/runtime comparison, not a claim that the two
versions have identical ranking semantics.  The v2 result is intentionally
larger because it preserves independently ranked candidates for each research-
visible sector.

## Acceptance conclusion

The deterministic acceptance contract passes for all five frozen anchors.  It
proves point-in-time input isolation, full-sector row retention, explicit data
gaps, strict future-only outcome evaluation, delayed complete/pending states,
nuclear-sector visibility, and immutable historical publication.  The live
2026-07-31 batch completed in 68.89 seconds, below the 3,600-second budget,
with `blocked=false` and the full sector/candidate artifacts published to its
run directory.  Runtime artifacts are deliberately not committed to the code
repository; their paths and manifest evidence remain external to this record.
